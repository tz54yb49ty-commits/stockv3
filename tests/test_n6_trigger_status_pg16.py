"""Opt-in isolated PostgreSQL 16 acceptance for N6 trigger status migration."""

from __future__ import annotations

import getpass
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
PG_ENABLED = os.environ.get("ASHARE_V3_N6_TRIGGER_STATUS_PG16") == "1"
PG_BIN = Path(
    os.environ.get(
        "ASHARE_V3_N6_TRIGGER_STATUS_PG_BIN",
        "/opt/homebrew/opt/postgresql@16/bin",
    )
)
TRADE_DATE = "20260731"


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
        "trigger_time": trigger_time, "trigger_pct": "1.000000",
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
    return {
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
        "trigger_pct": "5.555556", "trigger_price": "10.555556",
        "trigger_period": "M", "triggered_periods": periods or ["M", "D"],
        "trigger_live": operation == "update",
        "current_status": "matched" if operation == "update" else "inactive",
        "action_eligible_entry_allowed": False,
    }


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
            self.assertEqual(str(row["trigger_pct"]), "5.555556")
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
                ("stock:SH:600000", "600000", "浦发银行", "buy", "B_BUY", "BUY:W,D", "entry-stock-direct", 10, ["W", "D"], "2026-07-31 09:31+08", "1.000000", "10.000000", "W"),
                ("stock:SH:600000", "600000", "浦发银行", "buy", "B_BUY", "BUY:Q,D", "entry-stock-direct-2", 20, ["Q", "D"], "2026-07-31 09:40+08", "2.000000", "11.000000", "Q"),
                ("stock:SH:600001", "600001", "邯郸钢铁", "buy", "B_BUY", "BUY:D", "entry-stock-holding", 11, ["D"], "2026-07-31 09:32+08", "1.000000", "10.000000", "D"),
                ("stock:SH:600002", "600002", "齐鲁石化", "buy", "B_BUY", "BUY:D", "entry-stock-user2", 12, ["D"], "2026-07-31 09:33+08", "1.000000", "10.000000", "D"),
                ("index:SH:000300", "000300", "沪深300", "buy", "B_BUY", "BUY:D", "entry-index", 13, ["D"], "2026-07-31 09:34+08", "1.000000", "10.000000", "D"),
                ("board:TDX:881001", "881001", "银行", "sell", "S_SELL", "SELL:M", "entry-board", 14, ["M"], "2026-07-31 09:35+08", "1.000000", "10.000000", "M"),
            ]
            for (
                identity, code, name, direction, signal_type, condition_key,
                entry, watermark, periods, trigger_time, trigger_pct,
                trigger_price, trigger_period,
            ) in rows:
                kind = identity.split(":", 1)[0]
                conn.execute(
                    """INSERT INTO n6_trigger_status_current (
                         contract_version, consumer_name, projection_run_id, trade_date,
                         tracking_state_key, entry_trigger_event_id, action_eligible_event_id,
                         asset_kind, identity_key, asset_code, asset_name, direction,
                         signal_type, condition_key, trigger_time, trigger_pct, trigger_price,
                         trigger_period, triggered_periods, action_eligible_outbox_id,
                         last_status_outbox_id, last_event_id, last_event_type,
                         source_action_run_id, source_trigger_event_id
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                 %s, %s, %s, %s, %s,
                                 %s, %s, %s, %s, %s, %s, 'ActionEligible',
                                 'n5-entry', %s)""",
                    (
                        *episode_values, f"state:{entry}", entry, f"eligible:{entry}",
                        kind, identity, code, name, direction, signal_type, condition_key,
                        trigger_time, trigger_pct, trigger_price, trigger_period, periods,
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
        self.assertEqual(grouped["trigger_pct"], "2.000000")
        self.assertEqual(grouped["trigger_price"], "11.000000")
        self.assertEqual(grouped["trigger_period"], "Q")
        self.assertEqual(grouped["triggered_periods"], ["Q", "W", "D"])

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
