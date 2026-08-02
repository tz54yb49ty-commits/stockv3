"""Opt-in isolated PostgreSQL 16 acceptance for N6 trigger status migration."""

from __future__ import annotations

import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

import psycopg
from psycopg.rows import dict_row

from ashare_v3.user.trigger_status_projection import (
    CONTRACT_VERSION,
    MESSAGE_ROLE,
    PostgresTriggerStatusProjectionConsumer,
    TriggerStatusProjectionError,
)
from ashare_v3.web.n6_user_app import PostgresN6UserRepository


ROOT = Path(__file__).resolve().parents[1]
FORWARD = ROOT / "sql/089_n6_trigger_status_current.sql"
ROLLBACK = ROOT / "sql/089_n6_trigger_status_current_rollback.sql"
EXACT_BACKFILL_ROLLBACK = (
    ROOT / "sql/N6_trigger_status_projection_20260731_backfill_v1_exact_rollback.sql"
)
PG_ENABLED = os.environ.get("ASHARE_V3_N6_TRIGGER_STATUS_PG16") == "1"
PG_BIN = Path(
    os.environ.get(
        "ASHARE_V3_N6_TRIGGER_STATUS_PG_BIN",
        "/opt/homebrew/opt/postgresql@16/bin",
    )
)
TRADE_DATE = "20260731"
SCHEMA_HASH = "e50cea0987f7f3b99989e2c23ef2d0f9d526617c688ac7f61a18e765ec439ef2"
COLUMN_SIGNATURE = (
    "trigger_status_episode_id:bigint,contract_version:text,consumer_name:text,"
    "projection_run_id:text,trade_date:text,tracking_state_key:text,"
    "entry_trigger_event_id:text,action_eligible_event_id:text,asset_kind:text,"
    "identity_key:text,asset_code:text,asset_name:text,direction:text,"
    "signal_type:text,condition_key:text,trigger_time:timestamp with time zone,"
    "trigger_price:numeric(24,6),trigger_period:text,triggered_periods:text[],"
    "action_eligible_outbox_id:bigint,last_status_outbox_id:bigint,last_event_id:text,"
    "last_event_type:text,source_action_run_id:text,source_trigger_event_id:text,"
    "created_at:timestamp with time zone,updated_at:timestamp with time zone"
)


def _safe_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in (
        "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGSERVICE",
        "PGSERVICEFILE", "PGPASSFILE", "PGPASSWORD", "PGOPTIONS",
    ):
        env.pop(key, None)
    env["LC_ALL"] = "C"
    return env


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class _Pg16Cluster:
    def __init__(self) -> None:
        parent = Path("/private/tmp") if Path("/private/tmp").is_dir() else None
        self.temporary = tempfile.TemporaryDirectory(
            prefix="n6-trigger-status-it.", dir=str(parent) if parent else None
        )
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.socket_dir = self.root / "socket"
        self.socket_dir.mkdir()
        self.port = _free_port()
        self.superuser = getpass.getuser()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=_safe_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            raise AssertionError(
                "isolated PostgreSQL command failed:\n" + result.stdout + result.stderr
            )
        return result

    def connection_args(self, *, database: str = "postgres", user: str | None = None) -> list[str]:
        return [
            "--host", str(self.socket_dir), "--port", str(self.port),
            "--username", user or self.superuser, "--dbname", database,
        ]

    def start(self) -> None:
        self._run(
            [
                str(PG_BIN / "initdb"), "--pgdata", str(self.data),
                "--username", self.superuser, "--auth", "trust",
                "--encoding", "UTF8", "--no-locale", "--no-sync",
            ]
        )
        self._run(
            [
                str(PG_BIN / "pg_ctl"), "--pgdata", str(self.data),
                "--log", str(self.root / "postgres.log"), "--options",
                f"-F -k {self.socket_dir} -p {self.port} -c listen_addresses=''",
                "--wait", "start",
            ]
        )
        self.run_sql(
            "CREATE ROLE ashare_v3_user LOGIN; CREATE ROLE n6_btrack_web LOGIN;",
            database="postgres",
            user=self.superuser,
            label="roles",
        )
        self._run(
            [
                str(PG_BIN / "createdb"), "--host", str(self.socket_dir),
                "--port", str(self.port), "--username", self.superuser,
                "--owner", "ashare_v3_user", "ashare_v3",
            ]
        )

    def stop(self) -> None:
        if (self.data / "postmaster.pid").exists():
            self._run(
                [
                    str(PG_BIN / "pg_ctl"), "--pgdata", str(self.data),
                    "--mode", "fast", "--wait", "stop",
                ]
            )
        self.temporary.cleanup()

    def run_sql(self, text: str, *, database: str, user: str, label: str) -> None:
        path = self.root / f"{label}.sql"
        path.write_text(text, encoding="utf-8")
        self._run(
            [
                str(PG_BIN / "psql"),
                *self.connection_args(database=database, user=user),
                "-v", "ON_ERROR_STOP=1", "-f", str(path),
            ]
        )

    def apply(self, path: Path) -> None:
        self._run(
            [
                str(PG_BIN / "psql"),
                *self.connection_args(database="ashare_v3", user="ashare_v3_user"),
                "-v", "ON_ERROR_STOP=1", "-f", str(path),
            ]
        )

    @property
    def dsn(self) -> str:
        return (
            f"host={self.socket_dir} port={self.port} dbname=ashare_v3 "
            "user=ashare_v3_user"
        )

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)


def _fixture_schema_sql() -> str:
    return """
CREATE TABLE common_event_outbox (
  outbox_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id text NOT NULL UNIQUE,
  event_type text NOT NULL,
  event_schema_version text NOT NULL,
  trade_date text NOT NULL,
  asset_kind text NOT NULL,
  identity_key text NOT NULL,
  event_time timestamptz NOT NULL,
  source_layer text NOT NULL,
  source_run_id text NOT NULL,
  dedup_key text NOT NULL,
  partition_key text NOT NULL,
  payload_json jsonb NOT NULL,
  status text NOT NULL DEFAULT 'pending'
);
CREATE TABLE common_event_inbox (
  inbox_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  consumer_name text NOT NULL,
  event_id text NOT NULL,
  event_type text NOT NULL,
  event_schema_version text NOT NULL,
  source_layer text NOT NULL,
  source_run_id text NOT NULL,
  dedup_key text NOT NULL,
  partition_key text NOT NULL,
  payload_json jsonb NOT NULL,
  status text NOT NULL,
  attempt_count integer NOT NULL,
  received_at timestamptz NOT NULL,
  processed_at timestamptz,
  last_error text,
  raw_json jsonb,
  UNIQUE (consumer_name, event_id),
  UNIQUE (consumer_name, source_layer, event_type, source_run_id, dedup_key, event_schema_version)
);
CREATE TABLE common_event_consumer_checkpoint (
  consumer_name text NOT NULL,
  partition_key text NOT NULL,
  source_layer text NOT NULL,
  last_event_id text,
  last_event_time timestamptz,
  last_outbox_id bigint,
  checkpoint_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (consumer_name, partition_key, source_layer)
);
CREATE TABLE user_monitor_stock (
  monitor_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id bigint NOT NULL, principal_type text NOT NULL, user_id bigint NOT NULL,
  identity_key text NOT NULL, direction text NOT NULL, source_type text NOT NULL,
  source_run_id text, source_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_source_trade_date text, valid_for_trade_date text,
  valid_source_run_id text, status text NOT NULL
);
CREATE TABLE user_monitor_index (LIKE user_monitor_stock INCLUDING ALL);
CREATE TABLE user_monitor_board (LIKE user_monitor_stock INCLUDING ALL);
CREATE TABLE v_n6_stock_condition_display_basis (
  identity_key text, source_trade_date text, for_trade_date text, run_id text
);
CREATE TABLE v_n6_index_condition_display_basis (
  identity_key text, source_trade_date text, for_trade_date text, run_id text
);
CREATE TABLE v_n6_board_condition_display_basis (
  identity_key text, source_trade_date text, for_trade_date text, run_id text
);
CREATE TABLE v_n6_board_membership_fact (
  trade_date text, board_identity_key text, stock_identity_key text,
  board_code text, board_name text, board_type text
);
CREATE TABLE user_realtime_monitor_scope (
  realtime_scope_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id bigint NOT NULL, principal_type text NOT NULL, user_id bigint NOT NULL,
  asset_kind text NOT NULL, identity_key text NOT NULL,
  source_type text, status text NOT NULL
);
CREATE TABLE n6_virtual_account (
  virtual_account_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id bigint NOT NULL, principal_type text NOT NULL,
  virtual_account_status text NOT NULL
);
CREATE TABLE n6_virtual_position (
  virtual_position_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id bigint NOT NULL, principal_id bigint NOT NULL,
  principal_type text NOT NULL, asset_kind text NOT NULL,
  identity_key text NOT NULL, position_status text NOT NULL, quantity numeric NOT NULL
);
"""


def _eligible_payload(
    *, asset_kind: str, identity_key: str, code: str, name: str,
    direction: str, entry_id: str, condition_key: str = "BUY:W,D",
    trigger_time: str = "2026-07-31T09:31:00+08:00",
    periods: list[str] | None = None,
) -> dict:
    signal_type = "B_BUY" if direction == "buy" else "S_SELL"
    return {
        "trade_date": TRADE_DATE, "asset_kind": asset_kind,
        "identity_key": identity_key, "asset_code": code, "asset_name": name,
        "direction": direction, "signal_type": signal_type,
        "condition_key": condition_key, "projection_message_status": "ready",
        "trigger_time": trigger_time, "trigger_pct": "must-not-be-read",
        "trigger_price": "10.000000", "trigger_period": "W",
        "triggered_periods": periods or ["W", "D"],
        "source_trigger_event_id": entry_id,
        "trace_json": {"tracking_state_key": f"state:{entry_id}"},
        "action_entry_trigger_matched_ref": {
            "source_trigger_event_id": entry_id,
            "source_trigger_event_type": "TriggerMatched",
            "source_trigger_event_time": trigger_time,
            "source_trigger_run_id": "n4-entry-run",
            "source_n4_payload": {
                "trade_date": TRADE_DATE, "asset_kind": asset_kind,
                "identity_key": identity_key, "asset_code": code, "asset_name": name,
                "direction": direction, "signal_type": signal_type,
                "condition_key": condition_key,
            },
        },
    }


def _status_payload(
    *, operation: str, asset_kind: str, identity_key: str, direction: str,
    entry_id: str, eligible_id: str, condition_key: str = "BUY:W,D",
    periods: list[str] | None = None,
) -> dict:
    signal_type = "B_BUY" if direction == "buy" else "S_SELL"
    payload = {
        "contract_version": CONTRACT_VERSION, "message_role": MESSAGE_ROLE,
        "operation": operation, "trade_date": TRADE_DATE,
        "tracking_state_key": f"state:{entry_id}",
        "entry_trigger_event_id": entry_id,
        "action_eligible_event_id": eligible_id,
        "source_trigger_event_id": f"n4-state:{entry_id}:{operation}",
        "asset_kind": asset_kind, "identity_key": identity_key,
        "asset_code": "UNCHANGED", "asset_name": "UNCHANGED",
        "direction": direction, "signal_type": signal_type,
        "condition_key": condition_key,
        "trigger_time": "2099-01-01T00:00:00+08:00",
        "trigger_live": operation == "update",
        "current_status": "matched" if operation == "update" else "inactive",
        "action_eligible_entry_allowed": False,
    }
    if operation == "update":
        payload.update(
            {
                "trigger_price": "10.555556",
                "trigger_period": "M",
                "triggered_periods": periods or ["M", "D"],
            }
        )
    return payload


class N6TriggerStatusPg16StaticContractTests(unittest.TestCase):
    def test_forward_and_rollback_share_exact_no_pct_schema_identity(self) -> None:
        forward = FORWARD.read_text(encoding="utf-8")
        rollback = ROLLBACK.read_text(encoding="utf-8")
        create_block = forward.split(
            "CREATE TABLE public.n6_trigger_status_current", 1
        )[1].split(");", 1)[0]
        self.assertNotIn("trigger_pct", create_block)
        self.assertNotIn("trigger_pct", rollback)
        self.assertEqual(sha256(COLUMN_SIGNATURE.encode()).hexdigest(), SCHEMA_HASH)
        marker = f"schema_hash=sha256:{SCHEMA_HASH}"
        self.assertIn(marker, forward)
        self.assertIn(marker, rollback)
        self.assertIn(COLUMN_SIGNATURE, rollback)

    def test_exact_backfill_rollback_is_projection_scoped_and_non_uninstalling(self) -> None:
        text = EXACT_BACKFILL_ROLLBACK.read_text(encoding="utf-8")
        for marker in (
            "n6_trigger_status_projection_20260731_backfill_v1",
            "n6_trigger_status_projection_v1",
            "trigger-status:20260731",
            "4103761 AND 4107616",
            "eligible_count <> 1042",
            "executed_count <> 723",
            "updated_count <> 194",
            "invalidated_count <> 337",
            "deleted_current_count <> 705",
            "deleted_inbox_count <> 2296",
            "deleted_checkpoint_count <> 1",
            "before_outbox_range_fingerprint",
            "after_outbox_range_fingerprint",
            "immutable external backup",
        ):
            self.assertIn(marker, text)
        self.assertNotIn("trigger_pct", text)
        self.assertNotRegex(text, r"(?i)\bTRUNCATE\s+(?:TABLE\s+)?public\.")
        self.assertNotRegex(text, r"(?i)\bDROP\s+(?:TABLE\s+)?")
        self.assertNotRegex(text, r"(?i)\bCASCADE\b")
        self.assertNotRegex(
            text, r"(?i)(?:DELETE\s+FROM|UPDATE)\s+public\.common_event_outbox"
        )
        self.assertNotIn("089_n6_trigger_status_current_rollback.sql", text)
        self.assertIn(
            "DELETE FROM public.common_event_inbox inbox\n  USING public.common_event_outbox outbox",
            text,
        )


@unittest.skipUnless(
    PG_ENABLED,
    "set ASHARE_V3_N6_TRIGGER_STATUS_PG16=1 for isolated PG16 acceptance",
)
class N6TriggerStatusPg16Tests(unittest.TestCase):
    cluster: _Pg16Cluster

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        for binary in ("initdb", "pg_ctl", "postgres", "psql", "createdb"):
            if not (PG_BIN / binary).is_file():
                raise AssertionError(f"PostgreSQL 16 binary missing: {binary}")
        version = subprocess.run(
            [str(PG_BIN / "postgres"), "--version"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if version.returncode or " 16." not in version.stdout:
            raise AssertionError(f"PostgreSQL 16 required: {version.stdout}")
        cls.cluster = _Pg16Cluster()
        cls.cluster.start()
        cls.cluster.run_sql(
            _fixture_schema_sql(), database="ashare_v3", user="ashare_v3_user",
            label="fixture",
        )
        cls.cluster.apply(FORWARD)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    def setUp(self) -> None:
        with self.cluster.connect() as conn:
            conn.execute("TRUNCATE n6_trigger_status_current RESTART IDENTITY")
            conn.execute("TRUNCATE common_event_outbox, common_event_inbox RESTART IDENTITY")
            conn.execute("TRUNCATE common_event_consumer_checkpoint")
            conn.execute("TRUNCATE user_monitor_stock, user_monitor_index, user_monitor_board RESTART IDENTITY")
            conn.execute("TRUNCATE user_realtime_monitor_scope RESTART IDENTITY")
            conn.execute("TRUNCATE n6_virtual_position, n6_virtual_account RESTART IDENTITY CASCADE")
            conn.execute("TRUNCATE v_n6_stock_condition_display_basis, v_n6_index_condition_display_basis, v_n6_board_condition_display_basis")

    def _insert_event(
        self, *, event_id: str, event_type: str, asset_kind: str,
        identity_key: str, payload: dict, event_time: str = "2026-07-31T09:31:00+08:00",
    ) -> int:
        with self.cluster.connect() as conn:
            return int(
                conn.execute(
                    """
                    INSERT INTO common_event_outbox (
                      event_id, event_type, event_schema_version, trade_date,
                      asset_kind, identity_key, event_time, source_layer,
                      source_run_id, dedup_key, partition_key, payload_json, status
                    ) VALUES (%s, %s, 'v1', %s, %s, %s, %s, 'N5_action',
                              'n5-test-run', %s, %s, %s::jsonb, 'pending')
                    RETURNING outbox_id
                    """,
                    (
                        event_id, event_type, TRADE_DATE, asset_kind, identity_key,
                        event_time, event_id, identity_key,
                        json.dumps(payload, ensure_ascii=False),
                    ),
                ).fetchone()["outbox_id"]
            )

    def test_consumer_episode_lifecycle_atomicity_and_aggregation(self) -> None:
        consumer = PostgresTriggerStatusProjectionConsumer(self.cluster.dsn)
        identity = "stock:SH:600000"
        eligible_id = "eligible-1"
        entry_id = "entry-1"
        self._insert_event(
            event_id=eligible_id, event_type="ActionEligible", asset_kind="stock",
            identity_key=identity,
            payload=_eligible_payload(
                asset_kind="stock", identity_key=identity, code="600000",
                name="浦发银行", direction="buy", entry_id=entry_id,
            ),
        )
        self._insert_event(
            event_id="update-1", event_type="TriggerStatusUpdated", asset_kind="stock",
            identity_key=identity,
            payload=_status_payload(
                operation="update", asset_kind="stock", identity_key=identity,
                direction="buy", entry_id=entry_id, eligible_id=eligible_id,
                periods=["D", "M", "W"],
            ),
            event_time="2026-07-31T09:35:00+08:00",
        )
        self._insert_event(
            event_id="executed-1", event_type="ActionExecuted", asset_kind="stock",
            identity_key=identity, payload={"action_state": "executed"},
            event_time="2026-07-31T09:36:00+08:00",
        )
        first = consumer.consume_once(
            trade_date=TRADE_DATE, projection_run_id="projection-1"
        )
        self.assertEqual((first.inserted, first.updated, first.ignored_action_outcomes), (1, 1, 1))
        self.assertEqual(first.outbox_status_updates, 0)
        with self.cluster.connect() as conn:
            row = conn.execute("SELECT * FROM n6_trigger_status_current").fetchone()
            self.assertEqual(row["asset_name"], "浦发银行")
            self.assertNotIn("trigger_pct", row)
            self.assertEqual(row["triggered_periods"], ["M", "W", "D"])
            self.assertEqual(row["trigger_time"].isoformat(), "2026-07-31T09:31:00+08:00")
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM common_event_outbox WHERE status <> 'pending'").fetchone()["n"], 0)

        for number in (1, 2):
            self._insert_event(
                event_id=f"invalidate-{number}", event_type="TriggerStatusInvalidated",
                asset_kind="stock", identity_key=identity,
                payload=_status_payload(
                    operation="invalidate", asset_kind="stock", identity_key=identity,
                    direction="buy", entry_id=entry_id, eligible_id=eligible_id,
                ),
            )
        deleted = consumer.consume_once(
            trade_date=TRADE_DATE, projection_run_id="projection-1"
        )
        self.assertEqual(deleted.invalidated, 1)
        with self.cluster.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM n6_trigger_status_current").fetchone()["n"], 0)

        for suffix, time, periods in (
            ("2", "2026-07-31T10:00:00+08:00", ["W", "D"]),
            ("3", "2026-07-31T10:05:00+08:00", ["Q", "D"]),
        ):
            self._insert_event(
                event_id=f"eligible-{suffix}", event_type="ActionEligible",
                asset_kind="stock", identity_key=identity,
                payload=_eligible_payload(
                    asset_kind="stock", identity_key=identity, code="600000",
                    name="浦发银行", direction="buy", entry_id=f"entry-{suffix}",
                    trigger_time=time, periods=periods,
                ),
                event_time=time,
            )
        consumer.consume_once(trade_date=TRADE_DATE, projection_run_id="projection-2")
        with self.cluster.connect() as conn:
            rows = conn.execute(
                "SELECT entry_trigger_event_id, triggered_periods FROM n6_trigger_status_current ORDER BY entry_trigger_event_id"
            ).fetchall()
            self.assertEqual(len(rows), 2)

        self._insert_event(
            event_id="invalidate-new-2", event_type="TriggerStatusInvalidated",
            asset_kind="stock", identity_key=identity,
            payload=_status_payload(
                operation="invalidate", asset_kind="stock", identity_key=identity,
                direction="buy", entry_id="entry-2", eligible_id="eligible-2",
            ),
        )
        consumer.consume_once(trade_date=TRADE_DATE, projection_run_id="projection-2")
        with self.cluster.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM n6_trigger_status_current").fetchone()["n"], 1)
        self._insert_event(
            event_id="invalidate-new-3", event_type="TriggerStatusInvalidated",
            asset_kind="stock", identity_key=identity,
            payload=_status_payload(
                operation="invalidate", asset_kind="stock", identity_key=identity,
                direction="buy", entry_id="entry-3", eligible_id="eligible-3",
            ),
        )
        consumer.consume_once(trade_date=TRADE_DATE, projection_run_id="projection-2")
        with self.cluster.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM n6_trigger_status_current").fetchone()["n"], 0)

        checkpoint_before: int
        with self.cluster.connect() as conn:
            checkpoint_before = int(conn.execute("SELECT last_outbox_id FROM common_event_consumer_checkpoint").fetchone()["last_outbox_id"])
        self._insert_event(
            event_id="blocked-before-missing", event_type="ActionBlocked",
            asset_kind="stock", identity_key=identity, payload={"action_state": "blocked"},
        )
        self._insert_event(
            event_id="missing-update", event_type="TriggerStatusUpdated",
            asset_kind="stock", identity_key=identity,
            payload=_status_payload(
                operation="update", asset_kind="stock", identity_key=identity,
                direction="buy", entry_id="missing-entry", eligible_id="missing-eligible",
            ),
        )
        with self.assertRaisesRegex(TriggerStatusProjectionError, "missing_status_update_target"):
            consumer.consume_once(trade_date=TRADE_DATE, projection_run_id="projection-3")
        with self.cluster.connect() as conn:
            checkpoint_after = int(conn.execute("SELECT last_outbox_id FROM common_event_consumer_checkpoint").fetchone()["last_outbox_id"])
            self.assertEqual(checkpoint_after, checkpoint_before)
            self.assertEqual(
                conn.execute("SELECT count(*) AS n FROM common_event_inbox WHERE event_id IN ('blocked-before-missing', 'missing-update')").fetchone()["n"],
                0,
            )

    def test_multi_user_three_channel_effective_scope_and_group_union(self) -> None:
        with self.cluster.connect() as conn:
            for table, kind, identities in (
                ("v_n6_stock_condition_display_basis", "stock", ["stock:SH:600000", "stock:SH:600001", "stock:SH:600002"]),
                ("v_n6_index_condition_display_basis", "index", ["index:SH:000300"]),
                ("v_n6_board_condition_display_basis", "board", ["board:TDX:881001"]),
            ):
                for identity in identities:
                    conn.execute(
                        f"INSERT INTO {table} VALUES (%s, '20260730', %s, %s)",
                        (identity, TRADE_DATE, f"{kind}-display-run"),
                    )
            conn.execute(
                """INSERT INTO user_monitor_stock (
                     principal_id, principal_type, user_id, identity_key, direction,
                     source_type, source_run_id, valid_source_trade_date,
                     valid_for_trade_date, valid_source_run_id, status
                   ) VALUES (1, 'human_user', 11, 'stock:SH:600000', 'buy',
                     'single_row', 'stock-display-run', '20260730', %s,
                     'stock-display-run', 'active'),
                    (2, 'human_user', 22, 'stock:SH:600002', 'buy',
                     'single_row', 'stock-display-run', '20260730', %s,
                     'stock-display-run', 'active')""",
                (TRADE_DATE, TRADE_DATE),
            )
            conn.execute(
                """INSERT INTO user_monitor_board (
                     principal_id, principal_type, user_id, identity_key, direction,
                     source_type, source_run_id, valid_source_trade_date,
                     valid_for_trade_date, valid_source_run_id, status
                   ) VALUES (1, 'human_user', 11, 'board:TDX:881001', 'sell',
                     'single_row', 'board-display-run', '20260730', %s,
                     'board-display-run', 'active')""",
                (TRADE_DATE,),
            )
            conn.execute(
                "INSERT INTO n6_virtual_account (principal_id, principal_type, virtual_account_status) VALUES (1, 'human_user', 'active') RETURNING virtual_account_id"
            )
            account_id = conn.execute("SELECT virtual_account_id FROM n6_virtual_account").fetchone()["virtual_account_id"]
            conn.execute(
                """INSERT INTO n6_virtual_position (
                     virtual_account_id, principal_id, principal_type, asset_kind,
                     identity_key, position_status, quantity
                   ) VALUES (%s, 1, 'human_user', 'stock', 'stock:SH:600001',
                     'open_virtual', 100)""",
                (account_id,),
            )

            episode_values = (
                CONTRACT_VERSION, "n6_trigger_status_projection_v1", "projection-scope",
                TRADE_DATE,
            )
            rows = [
                ("stock:SH:600000", "600000", "浦发银行", "buy", "B_BUY", "BUY:W,D", "entry-stock-direct", 10, ["W", "D"], "2026-07-31 09:31+08", "10.000000", "W"),
                ("stock:SH:600000", "600000", "浦发银行", "buy", "B_BUY", "BUY:Q,D", "entry-stock-direct-2", 20, ["Q", "D"], "2026-07-31 09:40+08", "11.000000", "Q"),
                ("stock:SH:600001", "600001", "邯郸钢铁", "buy", "B_BUY", "BUY:D", "entry-stock-holding", 11, ["D"], "2026-07-31 09:32+08", "10.000000", "D"),
                ("stock:SH:600002", "600002", "齐鲁石化", "buy", "B_BUY", "BUY:D", "entry-stock-user2", 12, ["D"], "2026-07-31 09:33+08", "10.000000", "D"),
                ("index:SH:000300", "000300", "沪深300", "buy", "B_BUY", "BUY:D", "entry-index", 13, ["D"], "2026-07-31 09:34+08", "10.000000", "D"),
                ("board:TDX:881001", "881001", "银行", "sell", "S_SELL", "SELL:M", "entry-board", 14, ["M"], "2026-07-31 09:35+08", "10.000000", "M"),
            ]
            for (
                identity, code, name, direction, signal_type, condition_key,
                entry, watermark, periods, trigger_time, trigger_price, trigger_period,
            ) in rows:
                kind = identity.split(":", 1)[0]
                conn.execute(
                    """INSERT INTO n6_trigger_status_current (
                         contract_version, consumer_name, projection_run_id, trade_date,
                         tracking_state_key, entry_trigger_event_id, action_eligible_event_id,
                         asset_kind, identity_key, asset_code, asset_name, direction,
                         signal_type, condition_key, trigger_time, trigger_price,
                         trigger_period, triggered_periods, action_eligible_outbox_id,
                         last_status_outbox_id, last_event_id, last_event_type,
                         source_action_run_id, source_trigger_event_id
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                 %s, %s, %s, %s, %s,
                                 %s, %s, %s, %s, %s, 'ActionEligible',
                                 'n5-entry', %s)""",
                    (
                        *episode_values, f"state:{entry}", entry, f"eligible:{entry}",
                        kind, identity, code, name, direction, signal_type, condition_key,
                        trigger_time, trigger_price, trigger_period, periods,
                        watermark, watermark, f"eligible:{entry}", entry,
                    ),
                )
        repo = PostgresN6UserRepository(self.cluster.dsn)
        user1 = repo.fetch_app_trigger_status(
            principal_id=1, principal_type="human_user", user_id=11,
            trade_date=TRADE_DATE, limit=100,
        )
        user2 = repo.fetch_app_trigger_status(
            principal_id=2, principal_type="human_user", user_id=22,
            trade_date=TRADE_DATE, limit=100,
        )
        user1_stock = repo.fetch_app_trigger_status(
            principal_id=1, principal_type="human_user", user_id=11,
            trade_date=TRADE_DATE, limit=100, asset_kind="stock",
        )
        user1_ids = {row["identity_key"] for row in user1}
        user2_ids = {row["identity_key"] for row in user2}
        self.assertTrue({"stock:SH:600000", "stock:SH:600001", "board:TDX:881001", "index:SH:000300"}.issubset(user1_ids))
        self.assertIn("stock:SH:600002", user2_ids)
        self.assertNotIn("stock:SH:600002", user1_ids)
        self.assertNotIn("stock:SH:600000", user2_ids)
        self.assertEqual({row["asset_kind"] for row in user1_stock}, {"stock"})
        self.assertEqual(
            {row["identity_key"] for row in user1_stock},
            {"stock:SH:600000", "stock:SH:600001"},
        )
        grouped = next(row for row in user1 if row["identity_key"] == "stock:SH:600000")
        self.assertEqual(grouped["episode_count"], 2)
        self.assertEqual(grouped["trigger_time"], "2026-07-31 09:31:00+08")
        self.assertNotIn("trigger_pct", grouped)
        self.assertEqual(grouped["trigger_price"], "11.000000")
        self.assertEqual(grouped["trigger_period"], "Q")
        self.assertEqual(grouped["triggered_periods"], ["Q", "W", "D"])

    def test_y_exact_20260731_backfill_rollback_preserves_sentinels(self) -> None:
        target_rows: list[tuple] = []
        for entry_number in range(1, 1043):
            ordinal = entry_number
            outbox_id = 4103760 + ordinal
            event_id = f"eligible:{entry_number}"
            identity_key = f"stock:TEST:{entry_number:06d}"
            payload = {
                "trade_date": TRADE_DATE,
                "asset_kind": "stock",
                "identity_key": identity_key,
                "asset_code": f"{entry_number:06d}",
                "asset_name": f"测试{entry_number}",
                "direction": "buy",
                "signal_type": "B_BUY",
                "condition_key": "BUY:D",
                "projection_message_status": "ready",
                "trace_json": {"tracking_state_key": f"state:{entry_number}"},
                "action_entry_trigger_matched_ref": {
                    "source_trigger_event_id": f"entry:{entry_number}",
                    "source_trigger_event_type": "TriggerMatched",
                },
            }
            target_rows.append(
                (
                    outbox_id, event_id, "ActionEligible", "n5.action.v1",
                    identity_key, event_id, identity_key,
                    json.dumps(payload, ensure_ascii=False),
                )
            )
        for executed_number in range(1, 724):
            ordinal = 1042 + executed_number
            event_id = f"executed:{executed_number}"
            identity_key = f"stock:EXEC:{executed_number:06d}"
            target_rows.append(
                (
                    4103760 + ordinal, event_id, "ActionExecuted", "n5.action.v1",
                    identity_key, event_id, identity_key,
                    json.dumps({"action_state": "executed"}),
                )
            )
        for entry_number in range(1, 195):
            ordinal = 1765 + entry_number
            event_id = f"updated:{entry_number}"
            identity_key = f"stock:TEST:{entry_number:06d}"
            payload = {
                "contract_version": CONTRACT_VERSION,
                "message_role": MESSAGE_ROLE,
                "operation": "update",
                "trade_date": TRADE_DATE,
                "action_eligible_event_id": f"eligible:{entry_number}",
                "source_trigger_event_id": f"state-change:{entry_number}",
            }
            target_rows.append(
                (
                    4103760 + ordinal, event_id, "TriggerStatusUpdated",
                    "n5.trigger-status.v1", identity_key, event_id, identity_key,
                    json.dumps(payload),
                )
            )
        for entry_number in range(706, 1043):
            ordinal = 1254 + entry_number
            outbox_id = 4107616 if ordinal == 2296 else 4103760 + ordinal
            event_id = f"invalidated:{entry_number}"
            identity_key = f"stock:TEST:{entry_number:06d}"
            payload = {
                "contract_version": CONTRACT_VERSION,
                "message_role": MESSAGE_ROLE,
                "operation": "invalidate",
                "trade_date": TRADE_DATE,
                "action_eligible_event_id": f"eligible:{entry_number}",
                "source_trigger_event_id": f"state-change:{entry_number}",
            }
            target_rows.append(
                (
                    outbox_id, event_id, "TriggerStatusInvalidated",
                    "n5.trigger-status.v1", identity_key, event_id, identity_key,
                    json.dumps(payload),
                )
            )
        self.assertEqual(len(target_rows), 2296)

        with self.cluster.connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO common_event_outbox (
                      outbox_id, event_id, event_type, event_schema_version,
                      trade_date, asset_kind, identity_key, event_time,
                      source_layer, source_run_id, dedup_key, partition_key,
                      payload_json, status
                    ) OVERRIDING SYSTEM VALUE
                    VALUES (%s, %s, %s, %s, %s, 'stock', %s,
                            '2026-07-31 15:00:00+08', 'N5_action',
                            'n5-source-run', %s, %s, %s::jsonb, 'pending')
                    """,
                    [
                        (
                            outbox_id, event_id, event_type, schema_version,
                            TRADE_DATE, identity_key, dedup_key, partition_key,
                            payload_json,
                        )
                        for (
                            outbox_id, event_id, event_type, schema_version,
                            identity_key, dedup_key, partition_key, payload_json,
                        ) in target_rows
                    ],
                )
            conn.execute(
                """
                INSERT INTO common_event_inbox (
                  consumer_name, event_id, event_type, event_schema_version,
                  source_layer, source_run_id, dedup_key, partition_key,
                  payload_json, status, attempt_count, received_at, processed_at,
                  raw_json
                )
                SELECT 'n6_trigger_status_projection_v1', event_id, event_type,
                       event_schema_version, source_layer, source_run_id, dedup_key,
                       partition_key, payload_json, 'processed', 1,
                       pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp(),
                       pg_catalog.jsonb_build_object(
                         'outbox_id', outbox_id, 'event_id', event_id,
                         'event_type', event_type,
                         'trade_date', trade_date, 'source_layer', source_layer,
                         'payload_json', payload_json
                       )
                FROM common_event_outbox
                WHERE outbox_id BETWEEN 4103761 AND 4107616
                ORDER BY outbox_id
                """
            )
            conn.execute(
                """
                INSERT INTO n6_trigger_status_current (
                  contract_version, consumer_name, projection_run_id, trade_date,
                  tracking_state_key, entry_trigger_event_id,
                  action_eligible_event_id, asset_kind, identity_key, asset_code,
                  asset_name, direction, signal_type, condition_key, trigger_time,
                  trigger_price, trigger_period, triggered_periods,
                  action_eligible_outbox_id, last_status_outbox_id, last_event_id,
                  last_event_type, source_action_run_id, source_trigger_event_id
                )
                SELECT %s, 'n6_trigger_status_projection_v1',
                       'n6_trigger_status_projection_20260731_backfill_v1',
                       %s, 'state:' || number, 'entry:' || number,
                       'eligible:' || number, 'stock',
                       'stock:TEST:' || pg_catalog.lpad(number::text, 6, '0'),
                       pg_catalog.lpad(number::text, 6, '0'), '测试' || number,
                       'buy', 'B_BUY', 'BUY:D',
                       '2026-07-31 09:31:00+08', 10, 'D', ARRAY['D']::text[],
                       4103760 + number,
                       CASE WHEN number <= 194
                            THEN 4103760 + 1765 + number
                            ELSE 4103760 + number END,
                       CASE WHEN number <= 194
                            THEN 'updated:' || number
                            ELSE 'eligible:' || number END,
                       CASE WHEN number <= 194
                            THEN 'TriggerStatusUpdated'
                            ELSE 'ActionEligible' END,
                       'n5-source-run',
                       CASE WHEN number <= 194
                            THEN 'state-change:' || number
                            ELSE 'entry:' || number END
                FROM pg_catalog.generate_series(1, 705) AS number
                """,
                (CONTRACT_VERSION, TRADE_DATE),
            )
            conn.execute(
                """
                INSERT INTO common_event_consumer_checkpoint (
                  consumer_name, partition_key, source_layer, last_event_id,
                  last_event_time, last_outbox_id, checkpoint_payload, updated_at
                )
                SELECT 'n6_trigger_status_projection_v1',
                       'trigger-status:20260731', 'N5_action', event_id, event_time,
                       outbox_id,
                       pg_catalog.jsonb_build_object(
                         'contract_version', %s::text,
                         'projection_run_id',
                           'n6_trigger_status_projection_20260731_backfill_v1',
                         'trade_date', %s::text
                       ),
                       pg_catalog.clock_timestamp()
                FROM common_event_outbox WHERE outbox_id = 4107616
                """,
                (CONTRACT_VERSION, TRADE_DATE),
            )

            other_consumer_payload = json.dumps(
                {"sentinel": "other-consumer-same-date"}
            )
            conn.execute(
                """
                INSERT INTO common_event_outbox (
                  outbox_id, event_id, event_type, event_schema_version,
                  trade_date, asset_kind, identity_key, event_time, source_layer,
                  source_run_id, dedup_key, partition_key, payload_json, status
                ) OVERRIDING SYSTEM VALUE
                VALUES (4107000, 'sentinel-other-consumer', 'ActionEligible',
                        'n5.action.v1', %s, 'stock', 'stock:SENTINEL:OTHER',
                        '2026-07-31 15:01:00+08', 'N5_action', 'sentinel-run',
                        'sentinel-other-consumer', 'stock:SENTINEL:OTHER',
                        %s::jsonb, 'delivered')
                """,
                (TRADE_DATE, other_consumer_payload),
            )
            conn.execute(
                """
                INSERT INTO common_event_inbox (
                  consumer_name, event_id, event_type, event_schema_version,
                  source_layer, source_run_id, dedup_key, partition_key,
                  payload_json, status, attempt_count, received_at, processed_at,
                  raw_json
                ) VALUES (
                  'sentinel_other_consumer', 'sentinel-other-consumer',
                  'ActionEligible', 'n5.action.v1', 'N5_action', 'sentinel-run',
                  'sentinel-other-consumer', 'stock:SENTINEL:OTHER', %s::jsonb,
                  'processed', 1, pg_catalog.clock_timestamp(),
                  pg_catalog.clock_timestamp(), '{}'::jsonb
                )
                """,
                (other_consumer_payload,),
            )

            other_date_payload = json.dumps({"sentinel": "other-date"})
            conn.execute(
                """
                INSERT INTO common_event_outbox (
                  outbox_id, event_id, event_type, event_schema_version,
                  trade_date, asset_kind, identity_key, event_time, source_layer,
                  source_run_id, dedup_key, partition_key, payload_json, status
                ) OVERRIDING SYSTEM VALUE
                VALUES (5000000, 'sentinel-other-date', 'ActionEligible',
                        'n5.action.v1', '20260730', 'stock',
                        'stock:SENTINEL:OLD', '2026-07-30 15:00:00+08',
                        'N5_action', 'old-run', 'sentinel-other-date',
                        'stock:SENTINEL:OLD', %s::jsonb, 'pending')
                """,
                (other_date_payload,),
            )
            conn.execute(
                """
                INSERT INTO common_event_inbox (
                  consumer_name, event_id, event_type, event_schema_version,
                  source_layer, source_run_id, dedup_key, partition_key,
                  payload_json, status, attempt_count, received_at, processed_at,
                  raw_json
                ) VALUES (
                  'n6_trigger_status_projection_v1', 'sentinel-other-date',
                  'ActionEligible', 'n5.action.v1', 'N5_action', 'old-run',
                  'sentinel-other-date', 'stock:SENTINEL:OLD', %s::jsonb,
                  'processed', 1, pg_catalog.clock_timestamp(),
                  pg_catalog.clock_timestamp(), '{}'::jsonb
                )
                """,
                (other_date_payload,),
            )
            conn.execute(
                """
                INSERT INTO n6_trigger_status_current (
                  contract_version, consumer_name, projection_run_id, trade_date,
                  tracking_state_key, entry_trigger_event_id,
                  action_eligible_event_id, asset_kind, identity_key, asset_code,
                  asset_name, direction, signal_type, condition_key, trigger_time,
                  trigger_price, trigger_period, triggered_periods,
                  action_eligible_outbox_id, last_status_outbox_id, last_event_id,
                  last_event_type, source_action_run_id, source_trigger_event_id
                ) VALUES (
                  %s, 'n6_trigger_status_projection_v1', 'older-projection',
                  '20260730', 'state:old', 'entry:old', 'sentinel-other-date',
                  'stock', 'stock:SENTINEL:OLD', 'OLD', '旧投影', 'buy',
                  'B_BUY', 'BUY:D', '2026-07-30 09:31:00+08', 9, 'D',
                  ARRAY['D']::text[], 5000000, 5000000,
                  'sentinel-other-date', 'ActionEligible', 'old-run', 'entry:old'
                )
                """,
                (CONTRACT_VERSION,),
            )
            conn.execute(
                """
                INSERT INTO common_event_consumer_checkpoint (
                  consumer_name, partition_key, source_layer, last_event_id,
                  last_event_time, last_outbox_id, checkpoint_payload, updated_at
                ) VALUES
                  ('n6_trigger_status_projection_v1', 'trigger-status:20260730',
                   'N5_action', 'sentinel-other-date',
                   '2026-07-30 15:00:00+08', 5000000,
                   '{"sentinel":"other-date"}'::jsonb,
                   pg_catalog.clock_timestamp()),
                  ('sentinel_other_consumer', 'trigger-status:20260731',
                   'N5_action', 'sentinel-other-consumer',
                   '2026-07-31 15:01:00+08', 4107000,
                   '{"sentinel":"other-consumer"}'::jsonb,
                   pg_catalog.clock_timestamp())
                """
            )

        with self.cluster.connect() as conn:
            before_outbox = conn.execute(
                "SELECT count(*) AS n, count(*) FILTER (WHERE status = 'delivered') AS delivered FROM common_event_outbox"
            ).fetchone()
        self.cluster.apply(EXACT_BACKFILL_ROLLBACK)
        with self.cluster.connect() as conn:
            after_outbox = conn.execute(
                "SELECT count(*) AS n, count(*) FILTER (WHERE status = 'delivered') AS delivered FROM common_event_outbox"
            ).fetchone()
            self.assertEqual(dict(after_outbox), dict(before_outbox))
            self.assertEqual(
                conn.execute(
                    "SELECT count(*) AS n FROM n6_trigger_status_current WHERE projection_run_id = 'n6_trigger_status_projection_20260731_backfill_v1'"
                ).fetchone()["n"],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT projection_run_id FROM n6_trigger_status_current"
                ).fetchone()["projection_run_id"],
                "older-projection",
            )
            self.assertEqual(
                conn.execute(
                    "SELECT count(*) AS n FROM common_event_inbox WHERE consumer_name = 'n6_trigger_status_projection_v1'"
                ).fetchone()["n"],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT count(*) AS n FROM common_event_inbox WHERE consumer_name = 'sentinel_other_consumer'"
                ).fetchone()["n"],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT count(*) AS n FROM common_event_consumer_checkpoint"
                ).fetchone()["n"],
                2,
            )
            self.assertIsNotNone(
                conn.execute(
                    "SELECT pg_catalog.to_regclass('public.n6_trigger_status_current') AS oid"
                ).fetchone()["oid"]
            )
            self.assertIsNotNone(
                conn.execute(
                    "SELECT pg_catalog.to_regclass('public.n6_trigger_status_current_trigger_status_episode_id_seq') AS oid"
                ).fetchone()["oid"]
            )
            self.assertIsNotNone(
                conn.execute(
                    "SELECT pg_catalog.to_regclass('public.idx_089_n6_trigger_status_public_group') AS oid"
                ).fetchone()["oid"]
            )
        with self.assertRaisesRegex(AssertionError, "input/inbox scope drift"):
            self.cluster.apply(EXACT_BACKFILL_ROLLBACK)

    def test_z_forward_rollback_reapply(self) -> None:
        with self.cluster.connect() as conn:
            before = conn.execute(
                "SELECT count(*) AS outbox_count FROM common_event_outbox"
            ).fetchone()["outbox_count"]
        self.cluster.apply(ROLLBACK)
        with self.cluster.connect() as conn:
            self.assertIsNone(conn.execute("SELECT pg_catalog.to_regclass('public.n6_trigger_status_current') AS oid").fetchone()["oid"])
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM common_event_outbox").fetchone()["n"], before)
        self.cluster.apply(FORWARD)
        with self.cluster.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT pg_catalog.to_regclass('public.n6_trigger_status_current') AS oid").fetchone()["oid"])


if __name__ == "__main__":
    unittest.main()
