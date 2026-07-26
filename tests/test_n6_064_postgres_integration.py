"""Opt-in PostgreSQL 16 acceptance for the N6 064 all-day manual buy gate.

The normal test suite skips this module.  Set
``ASHARE_V3_N6_064_PG_INTEGRATION=1`` and point
``ASHARE_V3_N6_064_SCHEMA_DUMP`` at an offline schema-only custom-format
dump to run it.  The fixture always creates a private PostgreSQL cluster and
never uses a libpq service, password, or the active application database.

The unmodified migration/rollback round-trip is tested in one database.  A
separate business template installs a test-only clock function *after* the
exact migration has passed, then rewrites only the time calls in the affected
functions.  This makes the fresh/lunch/pre-open price matrix deterministic
without changing the migration bytes or any runtime database.
"""

from __future__ import annotations

import getpass
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD_SQL = ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql"
ROLLBACK_SQL = ROOT / "sql/064_n6_btrack_trade_date_all_day_buy_rollback.sql"
ENABLED = os.environ.get("ASHARE_V3_N6_064_PG_INTEGRATION") == "1"
PG_BIN = Path(
    os.environ.get(
        "ASHARE_V3_N6_064_PG_BIN",
        "/opt/homebrew/opt/postgresql@16/bin",
    )
)
SCHEMA_DUMP = Path(
    os.environ.get("ASHARE_V3_N6_064_SCHEMA_DUMP", "")
).expanduser()
SESSION_HASH = "a" * 64
TRADE_DATE = "20260720"
NEXT_TRADE_DATE = "20260721"

ROLE_NAMES = (
    "ashare_v3_user",
    "n6_ai_agent",
    "n6_btrack_web",
    "n6_quote_writer",
    "n6_ui_readonly_role",
    "n6_virtual_executor",
)

TIME_SHIM_SIGNATURES = (
    "public.n6_btrack_manual_signal_buy_current_scope("
    "bigint,text,bigint,bigint,bigint,text,text,numeric,text)",
    "public.n6_btrack_proposal_create(text,text,bigint)",
    "public.n6_btrack_proposal_list(text,integer)",
    "public.n6_btrack_proposal_confirm(text,bigint,text)",
    "public.n6_btrack_proposal_transition_guard()",
    "public.n6_executor_claim_proposal(bigint,text)",
    "public.n6_executor_apply_claimed_proposal(bigint,text)",
)

ROUNDTRIP_SIGNATURES = (
    "public.n6_btrack_proposal_create(text,text,bigint)",
    "public.n6_btrack_proposal_list(text,integer)",
    "public.n6_btrack_proposal_confirm(text,bigint,text)",
    "public.n6_btrack_proposal_transition_guard()",
    "public.n6_executor_apply_claimed_proposal(bigint,text)",
)

MINIMAL_SEED_SQL = r"""
BEGIN;
SET LOCAL session_replication_role = replica;

INSERT INTO public.common_trade_calendar (
  trade_date, exchange, is_open, prev_trade_date, next_trade_date,
  source, source_batch_id, source_version
) VALUES
  ('20260720', 'SSE', true, '20260717', '20260721',
   'fixture', 'fixture-batch', 'fixture-v1'),
  ('20260721', 'SSE', true, '20260720', '20260722',
   'fixture', 'fixture-batch', 'fixture-v1');

INSERT INTO public.user_account (
  user_id, login_name, display_name, password_hash, password_hash_algo,
  password_updated_at, role, status, user_policy_json
) OVERRIDING SYSTEM VALUE VALUES (
  2, 'fixture_admin', 'Fixture Admin', 'fixture-password-hash', 'fixture',
  '2026-07-19 00:00:00+08'::timestamptz,
  'admin', 'active', '{}'::jsonb
);

INSERT INTO public.user_session (
  user_session_id, user_id, session_token_hash, session_token_hash_algo,
  issued_at, expires_at, client_info_json
) OVERRIDING SYSTEM VALUE VALUES (
  2, 2, repeat('a', 64), 'sha256',
  '2026-07-19 00:00:00+08'::timestamptz,
  '2026-07-22 00:00:00+08'::timestamptz, '{}'::jsonb
);

INSERT INTO public.n6_principal (
  principal_id, principal_type, owner_user_id, principal_status,
  principal_label, principal_policy_json
) OVERRIDING SYSTEM VALUE VALUES (
  2, 'admin', 2, 'active', 'Fixture Admin', '{}'::jsonb
);

INSERT INTO public.n6_virtual_cash_ledger (
  cash_ledger_id, virtual_account_id, ledger_type, amount, currency,
  trade_date, event_time, source_event_type, source_event_id, run_id,
  policy_version, policy_hash, rollback_scope, source_lineage_json,
  quality_status
) OVERRIDING SYSTEM VALUE VALUES (
  2, 2, 'initial_deposit', 1000000, 'CNY', 20260720,
  '2026-07-20 00:00:00+08'::timestamptz,
  'fixture_seed', 'fixture-initial-cash', 'fixture-seed',
  'fixture-v1', 'fixture-v1', 'fixture-seed',
  '{"fixture":true}'::jsonb, 'passed'
);

INSERT INTO public.n6_virtual_cash_snapshot (
  cash_snapshot_id, virtual_account_id, snapshot_time, trade_date,
  available_cash, frozen_cash, total_cash, currency, source_ledger_max_id,
  snapshot_status, run_id, policy_version, policy_hash, rollback_scope,
  source_lineage_json, quality_status
) OVERRIDING SYSTEM VALUE VALUES (
  2, 2, '2026-07-20 00:00:00+08'::timestamptz, 20260720,
  1000000, 0, 1000000, 'CNY', 2, 'active', 'fixture-seed',
  'fixture-v1', 'fixture-v1', 'fixture-seed',
  '{"fixture":true}'::jsonb, 'passed'
);

INSERT INTO public.n6_virtual_account (
  virtual_account_id, principal_id, principal_type, account_name,
  virtual_account_status, base_currency, initial_cash,
  current_cash_snapshot_id, run_id, policy_version, policy_hash,
  rollback_scope, source_lineage_json, quality_status
) OVERRIDING SYSTEM VALUE VALUES (
  2, 2, 'admin', 'fixture-account', 'active', 'CNY', 1000000, 2,
  'fixture-seed', 'fixture-v1', 'fixture-v1', 'fixture-seed',
  '{"fixture":true}'::jsonb, 'passed'
);

INSERT INTO public.user_projection_run (
  user_projection_run_id, projection_contract_version, source_layer,
  source_action_run_id, source_n5_outbox_range, input_event_count,
  output_projection_count, p0_count, p1_count, p2_count,
  quality_summary_json, status, started_at, finished_at
) OVERRIDING SYSTEM VALUE VALUES (
  'fixture-projection-run', 'N6-user-projection-mvp-v1', 'N5_action',
  'fixture-action-run', '{}'::jsonb, 0, 0, 0, 0, 0, '{}'::jsonb,
  'passed', '2026-07-20 00:00:00+08'::timestamptz,
  '2026-07-20 00:00:01+08'::timestamptz
);

INSERT INTO public.stock_condition_display_basis (
  stock_condition_display_basis_id, run_id, for_trade_date,
  source_trade_date, prev_trade_date, stock_identity_key, code, exchange,
  name, display_policy_hash, primary_source_condition_basis_id,
  source_version, display_status, quality_status
) OVERRIDING SYSTEM VALUE VALUES (
  2, 'fixture-condition-run', '20260720', '20260717', '20260717',
  'stock:SH:600000', '600000', 'SH', 'Fixture Stock',
  'fixture-display-hash', 999999, 'fixture-v1', 'visible', 'passed'
);

INSERT INTO public.user_signal_projection (
  user_signal_projection_id, user_projection_run_id, user_id,
  permission_scope, source_layer, source_event_id, source_event_type,
  source_event_schema_version, source_event_dedup_key,
  source_action_event_id, source_action_run_id, asset_kind, identity_key,
  code, name, direction, signal_type, projection_status,
  source_payload_json, display_payload_json, source_action_event_type,
  action_state, action_mark, projection_policy
) OVERRIDING SYSTEM VALUE VALUES (
  2, 'fixture-projection-run', 2, 'self', 'N5_action',
  'fixture-event-eligible', 'ActionEligible', 'fixture-v1',
  'fixture-dedup-eligible', 'fixture-action-event-eligible',
  'fixture-action-run', 'stock', 'stock:SH:600000', '600000',
  'Fixture Stock', 'buy', 'B_BUY', 'visible',
  '{"trade_date":"20260720"}'::jsonb,
  '{"score":{"value":80},"trade_date":"20260720",'
    '"action_state":"eligible","trigger_price":"10.00"}'::jsonb,
  'ActionEligible', 'eligible', 'normal', 'fixture-policy'
);

INSERT INTO public.user_signal_card (
  user_signal_card_id, user_signal_projection_id, user_projection_run_id,
  user_id, card_type, card_status, display_priority, title, asset_kind,
  identity_key, code, name, direction, signal_type, source_action_run_id,
  source_event_id, card_payload_json, source_action_event_id,
  source_action_event_type, action_state, action_mark, projection_policy
) OVERRIDING SYSTEM VALUE VALUES (
  2, 2, 'fixture-projection-run', 2, 'signal', 'candidate', 100,
  'Fixture eligible buy', 'stock', 'stock:SH:600000', '600000',
  'Fixture Stock', 'buy', 'B_BUY', 'fixture-action-run',
  'fixture-event-eligible',
  '{"score":{"value":80},"trade_date":"20260720",'
    '"for_trade_date":"20260720","action_state":"eligible",'
    '"trigger_price":"10.00"}'::jsonb,
  'fixture-action-event-eligible', 'ActionEligible', 'eligible',
  'normal', 'fixture-policy'
);

INSERT INTO public.user_realtime_monitor_scope (
  realtime_scope_id, principal_id, principal_type, user_id, asset_kind,
  identity_key, display_name, source_type, source_snapshot_json,
  is_default_seed, status
) OVERRIDING SYSTEM VALUE VALUES (
  1, 2, 'admin', 2, 'stock', 'stock:SH:600000', 'Fixture Stock',
  'single_row', '{"identity_key":"stock:SH:600000"}'::jsonb,
  false, 'active'
);

SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence('public.user_account', 'user_id'),
  2, true
);
SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence('public.user_session', 'user_session_id'),
  2, true
);
SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence('public.n6_principal', 'principal_id'),
  2, true
);
SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence(
    'public.n6_virtual_cash_ledger', 'cash_ledger_id'
  ),
  2, true
);
SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence(
    'public.n6_virtual_cash_snapshot', 'cash_snapshot_id'
  ),
  2, true
);
SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence(
    'public.n6_virtual_account', 'virtual_account_id'
  ),
  2, true
);
SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence(
    'public.stock_condition_display_basis',
    'stock_condition_display_basis_id'
  ),
  2, true
);
SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence(
    'public.user_signal_projection', 'user_signal_projection_id'
  ),
  2, true
);
SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence(
    'public.user_signal_card', 'user_signal_card_id'
  ),
  2, true
);
SELECT pg_catalog.setval(
  pg_catalog.pg_get_serial_sequence(
    'public.user_realtime_monitor_scope', 'realtime_scope_id'
  ),
  1, true
);

SET LOCAL session_replication_role = origin;
COMMIT;
"""


def _safe_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in (
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGPASSFILE",
        "PGPASSWORD",
        "PGOPTIONS",
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
        temp_parent = (
            Path("/private/tmp")
            if Path("/private/tmp").is_dir()
            else Path(tempfile.gettempdir())
        )
        self._temporary = tempfile.TemporaryDirectory(
            prefix="n6-064-it.", dir=temp_parent
        )
        self.root = Path(self._temporary.name)
        self.data = self.root / "data"
        self.socket_dir = self.root / "socket"
        self.socket_dir.mkdir()
        self.port = _free_port()
        self.superuser = getpass.getuser()
        self._counter = 0

    def _binary(self, name: str) -> str:
        return str(PG_BIN / name)

    def _run(
        self,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            env=env or _safe_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode:
            command = " ".join(Path(part).name if index == 0 else part
                               for index, part in enumerate(args))
            raise AssertionError(
                f"isolated PostgreSQL command failed ({command}):\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
        return completed

    def _connection_args(self, database: str) -> list[str]:
        return [
            "--host",
            str(self.socket_dir),
            "--port",
            str(self.port),
            "--username",
            self.superuser,
            "--dbname",
            database,
        ]

    def start(self) -> None:
        self._run(
            [
                self._binary("initdb"),
                "--pgdata",
                str(self.data),
                "--username",
                self.superuser,
                "--auth",
                "trust",
                "--encoding",
                "UTF8",
                "--no-locale",
                "--no-sync",
            ]
        )
        self._run(
            [
                self._binary("pg_ctl"),
                "--pgdata",
                str(self.data),
                "--log",
                str(self.root / "postgres.log"),
                "--options",
                (
                    f"-F -k {self.socket_dir} -p {self.port} "
                    "-c listen_addresses=''"
                ),
                "--wait",
                "start",
            ]
        )
        role_sql = "\n".join(
            f"CREATE ROLE {role} NOLOGIN;" for role in ROLE_NAMES
        )
        self.run_sql("postgres", role_sql, label="roles")

    def stop(self) -> None:
        if (self.data / "postmaster.pid").exists():
            self._run(
                [
                    self._binary("pg_ctl"),
                    "--pgdata",
                    str(self.data),
                    "--mode",
                    "fast",
                    "--wait",
                    "stop",
                ]
            )
        self._temporary.cleanup()

    def create_database(
        self, database: str, *, template: str | None = None
    ) -> None:
        args = [
            self._binary("createdb"),
            "--host",
            str(self.socket_dir),
            "--port",
            str(self.port),
            "--username",
            self.superuser,
        ]
        if template:
            args.extend(["--template", template])
        args.append(database)
        self._run(args)

    def clone_database(self, template: str, prefix: str) -> str:
        self._counter += 1
        database = f"{prefix}_{self._counter:03d}"
        self.create_database(database, template=template)
        return database

    def restore_schema(self, database: str) -> None:
        self._run(
            [
                self._binary("pg_restore"),
                "--exit-on-error",
                "--host",
                str(self.socket_dir),
                "--port",
                str(self.port),
                "--username",
                self.superuser,
                "--dbname",
                database,
                str(SCHEMA_DUMP),
            ]
        )

    def apply_file(
        self, database: str, path: Path, *, role: str | None = None
    ) -> None:
        env = _safe_environment()
        if role:
            env["PGOPTIONS"] = f"-c role={role}"
        self._run(
            [
                self._binary("psql"),
                *self._connection_args(database),
                "--set",
                "ON_ERROR_STOP=1",
                "--file",
                str(path),
            ],
            env=env,
        )

    def run_sql(
        self,
        database: str,
        sql_text: str,
        *,
        label: str,
        role: str | None = None,
    ) -> None:
        sql_path = self.root / f"{label}.sql"
        sql_path.write_text(sql_text, encoding="utf-8")
        self.apply_file(database, sql_path, role=role)

    def connect(self, database: str):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            host=str(self.socket_dir),
            port=self.port,
            dbname=database,
            user=self.superuser,
            row_factory=dict_row,
        )

    def install_clock_shim(self, database: str) -> None:
        with self.connect(database) as connection:
            connection.execute(
                """
                CREATE OR REPLACE FUNCTION public.n6_064_test_now()
                RETURNS timestamptz
                LANGUAGE sql
                STABLE
                SET search_path = pg_catalog
                AS $clock$
                  SELECT pg_catalog.current_setting(
                    'n6.test_clock', false
                  )::timestamptz
                $clock$
                """
            )
            definitions: list[str] = []
            for signature in TIME_SHIM_SIGNATURES:
                row = connection.execute(
                    """
                    SELECT pg_catalog.pg_get_functiondef(
                      %s::pg_catalog.regprocedure
                    ) AS definition
                    """,
                    (signature,),
                ).fetchone()
                self.assert_definition(row, signature)
                definition = str(row["definition"])
                rewritten = definition.replace(
                    "pg_catalog.clock_timestamp()",
                    "public.n6_064_test_now()",
                ).replace(
                    "pg_catalog.now()",
                    "public.n6_064_test_now()",
                )
                rewritten = re.sub(
                    r"(?<![A-Za-z0-9_.])clock_timestamp\(\)",
                    "public.n6_064_test_now()",
                    rewritten,
                )
                rewritten = re.sub(
                    r"(?<![A-Za-z0-9_.])now\(\)",
                    "public.n6_064_test_now()",
                    rewritten,
                )
                if rewritten == definition:
                    raise AssertionError(
                        f"time shim found no clock call in {signature}"
                    )
                definitions.append(rewritten)
            connection.execute("SET ROLE ashare_v3_user")
            for definition in definitions:
                connection.execute(definition)
            connection.execute(
                """
                ALTER TABLE public.n6_virtual_trade_proposal
                  ALTER COLUMN created_at
                    SET DEFAULT public.n6_064_test_now(),
                  ALTER COLUMN updated_at
                    SET DEFAULT public.n6_064_test_now()
                """
            )
            connection.commit()

    @staticmethod
    def assert_definition(row, signature: str) -> None:
        if not row or not row.get("definition"):
            raise AssertionError(f"missing function definition: {signature}")


@unittest.skipUnless(
    ENABLED,
    "set ASHARE_V3_N6_064_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6064PostgresIntegrationTest(unittest.TestCase):
    cluster: _Pg16Cluster
    schema_database = "n6_064_schema"
    business_template = "n6_064_business"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        missing = [
            str(PG_BIN / binary)
            for binary in (
                "createdb",
                "initdb",
                "pg_ctl",
                "pg_restore",
                "postgres",
                "psql",
            )
            if not (PG_BIN / binary).is_file()
        ]
        if missing:
            raise AssertionError(
                "PostgreSQL 16 binaries missing: " + ", ".join(missing)
            )
        version = subprocess.run(
            [str(PG_BIN / "postgres"), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if version.returncode or " 16." not in version.stdout:
            raise AssertionError(
                f"PostgreSQL 16 required, got: {version.stdout}"
            )
        if not str(SCHEMA_DUMP) or not SCHEMA_DUMP.is_absolute():
            raise AssertionError(
                "ASHARE_V3_N6_064_SCHEMA_DUMP must be an absolute path"
            )
        if not SCHEMA_DUMP.is_file():
            raise AssertionError(
                f"offline schema dump not found: {SCHEMA_DUMP}"
            )
        if importlib.util.find_spec("psycopg") is None:
            raise AssertionError("psycopg is required when integration is enabled")

        cls.cluster = _Pg16Cluster()
        try:
            cls.cluster.start()
            cls.cluster.create_database(cls.schema_database)
            cls.cluster.restore_schema(cls.schema_database)
            cls.cluster.create_database(
                cls.business_template, template=cls.schema_database
            )
            cls.cluster.apply_file(
                cls.business_template,
                FORWARD_SQL,
                role="ashare_v3_user",
            )
            cls.cluster.run_sql(
                cls.business_template,
                MINIMAL_SEED_SQL,
                label="minimal_seed",
            )
            cls.cluster.install_clock_shim(cls.business_template)
        except Exception:
            cls.cluster.stop()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    def _connect(
        self,
        database: str,
        *,
        role: str | None = None,
        clock: str | None = None,
    ):
        connection = self.cluster.connect(database)
        if clock:
            connection.execute(
                "SELECT pg_catalog.set_config('n6.test_clock', %s, false)",
                (clock,),
            )
        if role:
            if role not in ROLE_NAMES:
                connection.close()
                raise AssertionError(f"unexpected fixture role: {role}")
            connection.execute(f"SET ROLE {role}")
        return connection

    def _configure_signal(
        self,
        database: str,
        *,
        action_state: str,
        target_price: float | None,
        reference_text: str | None = None,
        trade_date: str = TRADE_DATE,
    ) -> tuple[str, float]:
        if action_state not in {"eligible", "executed"}:
            raise AssertionError(action_state)
        reference_kind = (
            "trigger_price" if action_state == "eligible" else "action_price"
        )
        reference_price = 10.0 if action_state == "eligible" else 11.0
        payload_reference = (
            reference_text
            if reference_text is not None
            else f"{reference_price:.2f}"
        )
        payload = {
            "score": {"value": 80},
            "trade_date": trade_date,
            "action_state": action_state,
            reference_kind: payload_reference,
        }
        card_payload = dict(payload, for_trade_date=trade_date)
        event_type = (
            "ActionEligible"
            if action_state == "eligible"
            else "ActionExecuted"
        )
        card_status = (
            "candidate"
            if action_state == "eligible"
            else "action_confirmed"
        )
        with self.cluster.connect(database) as connection:
            connection.execute(
                """
                UPDATE public.user_signal_projection
                SET action_state=%s,
                    source_event_type=%s,
                    source_action_event_type=%s,
                    target_price=%s,
                    source_payload_json=%s::jsonb,
                    display_payload_json=%s::jsonb
                WHERE user_signal_projection_id=2
                """,
                (
                    action_state,
                    event_type,
                    event_type,
                    target_price,
                    json.dumps({"trade_date": trade_date}),
                    json.dumps(payload),
                ),
            )
            connection.execute(
                """
                UPDATE public.user_signal_card
                SET action_state=%s,
                    card_status=%s,
                    source_action_event_type=%s,
                    target_price=%s,
                    card_payload_json=%s::jsonb
                WHERE user_signal_card_id=2
                """,
                (
                    action_state,
                    card_status,
                    event_type,
                    target_price,
                    json.dumps(card_payload),
                ),
            )
            connection.commit()
        return reference_kind, reference_price

    def _insert_quote(
        self,
        database: str,
        *,
        quote_minute: str,
        fetched_at: str,
        price: float,
    ) -> None:
        with self.cluster.connect(database) as connection:
            connection.execute(
                """
                INSERT INTO public.n6_virtual_quote_snapshot (
                  identity_key, exchange, stock_code, quote_minute,
                  provider_batch_id, provider_contract_version,
                  source_adapter, source_version, source_time_semantics,
                  requested_at, completed_at, batch_status, market,
                  current_price, last_close, day_open, day_high, day_low,
                  source_time_text, fetched_at, quality_status,
                  quality_reason
                ) VALUES (
                  'stock:SH:600000', 'SH', '600000', %s::timestamptz,
                  pg_catalog.gen_random_uuid(), '1.0.0', 'mootdx.std',
                  'fixture-v1',
                  'provider_intraday_time_without_trade_date',
                  %s::timestamptz, %s::timestamptz, 'passed', 1,
                  %s, %s, %s, %s, %s, 'fixture-time',
                  %s::timestamptz, 'passed', 'ok'
                )
                """,
                (
                    quote_minute,
                    quote_minute,
                    fetched_at,
                    price,
                    price,
                    price,
                    price,
                    price,
                    fetched_at,
                ),
            )
            connection.commit()

    def _create_and_confirm(
        self, database: str, *, clock: str
    ) -> tuple[int, str]:
        with self._connect(
            database, role="n6_btrack_web", clock=clock
        ) as connection:
            created = connection.execute(
                """
                SELECT public.n6_btrack_proposal_create(
                  %s, 'signal', 2
                ) AS result
                """,
                (SESSION_HASH,),
            ).fetchone()["result"]
            self.assertTrue(created["ok"], created)
            item = created["item"]
            proposal_id = int(item["proposal_id"])
            generation = item["confirmation_generation_token"]
            idempotency_key = f"n6v3:{generation}:integration"
            confirmed = connection.execute(
                """
                SELECT public.n6_btrack_proposal_confirm(
                  %s, %s, %s
                ) AS result
                """,
                (SESSION_HASH, proposal_id, idempotency_key),
            ).fetchone()["result"]
            self.assertTrue(confirmed["ok"], confirmed)
            self.assertEqual(confirmed["status"], "confirmed")
            connection.commit()
        return proposal_id, idempotency_key

    def _create_only(self, database: str, *, clock: str) -> dict:
        with self._connect(
            database, role="n6_btrack_web", clock=clock
        ) as connection:
            result = connection.execute(
                """
                SELECT public.n6_btrack_proposal_create(
                  %s, 'signal', 2
                ) AS result
                """,
                (SESSION_HASH,),
            ).fetchone()["result"]
            connection.commit()
            return dict(result)

    def _execute(
        self,
        database: str,
        *,
        proposal_id: int,
        executor_run_id: str,
        clock: str,
    ) -> dict:
        from ashare_v3.user.virtual_executor import (
            VirtualExecutorRequest,
            execute_proposal,
        )

        connection = self._connect(
            database, role="n6_virtual_executor", clock=clock
        )
        try:
            return execute_proposal(
                connection,
                VirtualExecutorRequest(
                    proposal_id=proposal_id,
                    executor_run_id=executor_run_id,
                ),
            )
        finally:
            connection.close()

    def _counts(self, database: str) -> dict[str, int]:
        statements = {
            "proposal": "SELECT count(*) AS n FROM public.n6_virtual_trade_proposal",
            "order": "SELECT count(*) AS n FROM public.n6_virtual_order",
            "trade": "SELECT count(*) AS n FROM public.n6_virtual_trade",
            "buy_ledger": (
                "SELECT count(*) AS n FROM public.n6_virtual_cash_ledger "
                "WHERE ledger_type='virtual_buy'"
            ),
            "cash_snapshot": (
                "SELECT count(*) AS n FROM public.n6_virtual_cash_snapshot"
            ),
            "position": "SELECT count(*) AS n FROM public.n6_virtual_position",
            "lot": "SELECT count(*) AS n FROM public.n6_virtual_position_lot",
            "event": (
                "SELECT count(*) AS n FROM public.n6_virtual_position_event"
            ),
        }
        with self.cluster.connect(database) as connection:
            return {
                key: int(connection.execute(sql).fetchone()["n"])
                for key, sql in statements.items()
            }

    def _fingerprint(self, database: str) -> str:
        rows: list[dict] = []
        with self.cluster.connect(database) as connection:
            for signature in ROUNDTRIP_SIGNATURES:
                row = connection.execute(
                    """
                    SELECT %s AS signature,
                           pg_catalog.pg_get_functiondef(
                             %s::pg_catalog.regprocedure
                           ) AS definition,
                           owner.rolname AS owner_name,
                           proc.prosecdef,
                           proc.proconfig,
                           proc.proacl::text AS proacl
                    FROM pg_catalog.pg_proc proc
                    JOIN pg_catalog.pg_roles owner
                      ON owner.oid=proc.proowner
                    WHERE proc.oid=%s::pg_catalog.regprocedure
                    """,
                    (signature, signature, signature),
                ).fetchone()
                self.assertIsNotNone(row, signature)
                rows.append(dict(row))
        encoded = json.dumps(
            rows, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def test_064_unmodified_forward_and_rollback_round_trip(self) -> None:
        database = self.cluster.clone_database(
            self.schema_database, "roundtrip"
        )
        before = self._fingerprint(database)
        self.cluster.apply_file(
            database, FORWARD_SQL, role="ashare_v3_user"
        )
        with self.cluster.connect(database) as connection:
            helper = connection.execute(
                """
                SELECT pg_catalog.to_regprocedure(
                  'public.n6_btrack_manual_signal_buy_current_scope('
                  'bigint,text,bigint,bigint,bigint,text,text,numeric,text)'
                ) IS NOT NULL AS present
                """
            ).fetchone()["present"]
            self.assertTrue(helper)
        self.cluster.apply_file(
            database, ROLLBACK_SQL, role="ashare_v3_user"
        )
        after = self._fingerprint(database)
        self.assertEqual(after, before)
        with self.cluster.connect(database) as connection:
            helper = connection.execute(
                """
                SELECT pg_catalog.to_regprocedure(
                  'public.n6_btrack_manual_signal_buy_current_scope('
                  'bigint,text,bigint,bigint,bigint,text,text,numeric,text)'
                ) IS NULL AS absent
                """
            ).fetchone()["absent"]
            self.assertTrue(helper)

    def test_064_success_matrix_real_functions_and_atomic_facts(self) -> None:
        price_cases = {
            "fresh": {
                "clock": "2026-07-20 10:00:00+08",
                "quote": (
                    "2026-07-20 09:59:00+08",
                    "2026-07-20 09:59:30+08",
                    12.0,
                ),
                "source": "quote_current_price",
                "field": "current_price",
                "policy": "n6_064_fresh_quote_fill_v1",
                "price": 12.0,
            },
            "same_day_last": {
                "clock": "2026-07-20 12:00:00+08",
                "quote": (
                    "2026-07-20 11:29:00+08",
                    "2026-07-20 11:29:30+08",
                    13.0,
                ),
                "source": "same_day_last_quote_current_price",
                "field": "current_price",
                "policy": "n6_064_same_day_last_quote_fill_v1",
                "price": 13.0,
            },
            "reference": {
                "clock": "2026-07-20 08:00:00+08",
                "quote": None,
                "source": "signal_reference_price",
                "policy": "n6_064_signal_reference_fill_v1",
            },
        }
        matrix_index = 0
        for action_state in ("eligible", "executed"):
            for target_price in (None, 15.0):
                for price_name, price_case in price_cases.items():
                    matrix_index += 1
                    with self.subTest(
                        action_state=action_state,
                        target_price=target_price,
                        price_source=price_name,
                    ):
                        database = self.cluster.clone_database(
                            self.business_template, "success"
                        )
                        reference_kind, reference_price = (
                            self._configure_signal(
                                database,
                                action_state=action_state,
                                target_price=target_price,
                            )
                        )
                        if price_case["quote"]:
                            quote_minute, fetched_at, quote_price = (
                                price_case["quote"]
                            )
                            self._insert_quote(
                                database,
                                quote_minute=quote_minute,
                                fetched_at=fetched_at,
                                price=quote_price,
                            )
                        proposal_id, _ = self._create_and_confirm(
                            database, clock=price_case["clock"]
                        )
                        executor_run_id = (
                            f"n6-064-integration-{matrix_index:02d}"
                        )
                        result = self._execute(
                            database,
                            proposal_id=proposal_id,
                            executor_run_id=executor_run_id,
                            clock=price_case["clock"],
                        )
                        self.assertTrue(result["ok"], result)
                        self.assertEqual(result["status"], "executed")

                        expected_price = float(
                            price_case.get("price", reference_price)
                        )
                        expected_field = str(
                            price_case.get("field", reference_kind)
                        )
                        expected_quantity = (
                            math.floor(300000 / expected_price / 100) * 100
                        )
                        expected_gross = (
                            expected_quantity * expected_price
                        )
                        with self.cluster.connect(database) as connection:
                            row = connection.execute(
                                """
                                SELECT trade.filled_price,
                                       trade.filled_quantity,
                                       trade.fill_quote_snapshot_id,
                                       trade.fill_policy_version,
                                       trade.source_lineage_json,
                                       position.locked_target_price,
                                       position.target_price_status,
                                       position.target_price_source_signal_projection_id,
                                       lot.open_trade_date,
                                       lot.available_trade_date,
                                       lot.lot_status,
                                       cash.available_cash,
                                       account.current_cash_snapshot_id
                                FROM public.n6_virtual_trade trade
                                JOIN public.n6_virtual_position position
                                  ON position.virtual_account_id=
                                     trade.virtual_account_id
                                 AND position.identity_key=
                                     trade.identity_key
                                JOIN public.n6_virtual_position_lot lot
                                  ON lot.virtual_position_id=
                                     position.virtual_position_id
                                 AND lot.source_virtual_trade_id=
                                     trade.virtual_trade_id
                                JOIN public.n6_virtual_account account
                                  ON account.virtual_account_id=
                                     trade.virtual_account_id
                                JOIN public.n6_virtual_cash_snapshot cash
                                  ON cash.cash_snapshot_id=
                                     account.current_cash_snapshot_id
                                WHERE trade.source_proposal_id=%s
                                """,
                                (proposal_id,),
                            ).fetchone()
                        self.assertAlmostEqual(
                            float(row["filled_price"]), expected_price
                        )
                        self.assertEqual(
                            int(row["filled_quantity"]), expected_quantity
                        )
                        lineage = row["source_lineage_json"]
                        self.assertEqual(
                            lineage["fill_price_source"],
                            price_case["source"],
                        )
                        self.assertEqual(
                            lineage["fill_price_field"], expected_field
                        )
                        self.assertEqual(
                            row["fill_policy_version"],
                            price_case["policy"],
                        )
                        self.assertEqual(
                            lineage["fill_policy_version"],
                            price_case["policy"],
                        )
                        self.assertEqual(
                            lineage["for_trade_date"], TRADE_DATE
                        )
                        if price_name == "reference":
                            self.assertIsNone(
                                row["fill_quote_snapshot_id"]
                            )
                        else:
                            self.assertIsNotNone(
                                row["fill_quote_snapshot_id"]
                            )
                        if target_price is None:
                            self.assertIsNone(row["locked_target_price"])
                            self.assertEqual(
                                row["target_price_status"], "not_ready"
                            )
                            self.assertIsNone(
                                row[
                                    "target_price_source_signal_projection_id"
                                ]
                            )
                        else:
                            self.assertAlmostEqual(
                                float(row["locked_target_price"]),
                                target_price,
                            )
                            self.assertEqual(
                                row["target_price_status"], "frozen"
                            )
                            self.assertEqual(
                                int(
                                    row[
                                        "target_price_source_signal_projection_id"
                                    ]
                                ),
                                2,
                            )
                        self.assertEqual(
                            str(row["open_trade_date"]), "2026-07-20"
                        )
                        self.assertEqual(
                            str(row["available_trade_date"]),
                            "2026-07-21",
                        )
                        self.assertEqual(row["lot_status"], "locked_t1")
                        self.assertAlmostEqual(
                            float(row["available_cash"]),
                            1000000 - expected_gross,
                        )
                        self.assertEqual(
                            self._counts(database),
                            {
                                "proposal": 1,
                                "order": 1,
                                "trade": 1,
                                "buy_ledger": 1,
                                "cash_snapshot": 2,
                                "position": 1,
                                "lot": 1,
                                "event": 1,
                            },
                        )

                        if matrix_index == 1:
                            before_replay = self._counts(database)
                            with self._connect(
                                database,
                                role="n6_virtual_executor",
                                clock=price_case["clock"],
                            ) as connection:
                                replay = connection.execute(
                                    """
                                    SELECT public.n6_executor_apply_claimed_proposal(
                                      %s, %s
                                    ) AS result
                                    """,
                                    (proposal_id, executor_run_id),
                                ).fetchone()["result"]
                                connection.commit()
                            self.assertTrue(replay["ok"], replay)
                            self.assertTrue(replay["idempotent"], replay)
                            self.assertEqual(
                                self._counts(database), before_replay
                            )

    def test_064_rejections_are_classified_and_zero_write(self) -> None:
        cases = (
            (
                "closed_day",
                "current_open_trade_date_required",
                lambda db: self._sql_update(
                    db,
                    "UPDATE public.common_trade_calendar "
                    "SET is_open=false WHERE trade_date='20260720'",
                ),
            ),
            (
                "historical",
                "signal_not_in_effective_scope",
                lambda db: self._configure_signal(
                    db,
                    action_state="eligible",
                    target_price=None,
                    trade_date="20260719",
                ),
            ),
            (
                "future",
                "signal_not_in_effective_scope",
                lambda db: self._configure_signal(
                    db,
                    action_state="eligible",
                    target_price=None,
                    trade_date="20260721",
                ),
            ),
            (
                "out_of_scope",
                "signal_not_in_effective_scope",
                lambda db: self._sql_update(
                    db,
                    "DELETE FROM public.user_realtime_monitor_scope",
                ),
            ),
            (
                "non_self",
                "signal_not_in_effective_scope",
                self._make_signal_non_self,
            ),
            (
                "invalid_reference",
                "signal_reference_price_invalid",
                lambda db: self._configure_signal(
                    db,
                    action_state="eligible",
                    target_price=None,
                    reference_text="0",
                ),
            ),
        )
        for case_name, expected_error, mutate in cases:
            with self.subTest(case=case_name):
                database = self.cluster.clone_database(
                    self.business_template, "reject"
                )
                self._configure_signal(
                    database,
                    action_state="eligible",
                    target_price=None,
                )
                mutate(database)
                before = self._counts(database)
                result = self._create_only(
                    database, clock="2026-07-20 20:00:00+08"
                )
                self.assertFalse(result["ok"], result)
                self.assertEqual(result["error"], expected_error)
                self.assertEqual(self._counts(database), before)

    def _sql_update(self, database: str, statement: str) -> None:
        with self.cluster.connect(database) as connection:
            connection.execute(statement)
            connection.commit()

    def _make_signal_non_self(self, database: str) -> None:
        with self.cluster.connect(database) as connection:
            connection.execute("SET session_replication_role=replica")
            connection.execute(
                "UPDATE public.user_signal_projection SET user_id=99"
            )
            connection.execute(
                "UPDATE public.user_signal_card SET user_id=99"
            )
            connection.execute("SET session_replication_role=origin")
            connection.commit()

    def test_064_manual_sell_and_stop_loss_keep_quote_fail_closed(self) -> None:
        for source_type in ("manual_position", "stop_loss"):
            with self.subTest(source_type=source_type):
                database = self.cluster.clone_database(
                    self.business_template, "nonmanual"
                )
                self._configure_signal(
                    database,
                    action_state="eligible",
                    target_price=None,
                )
                proposal_id, _ = self._create_and_confirm(
                    database, clock="2026-07-20 20:00:00+08"
                )
                with self.cluster.connect(database) as connection:
                    connection.execute(
                        "SET session_replication_role=replica"
                    )
                    connection.execute(
                        """
                        UPDATE public.n6_virtual_trade_proposal
                        SET source_type=%s,
                            proposal_side='sell',
                            source_signal_projection_id=NULL,
                            source_virtual_position_id=999,
                            signal_reference_kind='manual',
                            signal_reference_price=NULL
                        WHERE proposal_id=%s
                        """,
                        (source_type, proposal_id),
                    )
                    connection.execute(
                        "SET session_replication_role=origin"
                    )
                    connection.commit()
                before = self._counts(database)
                result = self._execute(
                    database,
                    proposal_id=proposal_id,
                    executor_run_id=f"n6-064-{source_type}",
                    clock="2026-07-20 20:00:00+08",
                )
                self.assertFalse(result["ok"], result)
                self.assertEqual(result["status"], "quote_not_ready")
                self.assertEqual(self._counts(database), before)

    def test_064_late_failure_rolls_back_claim_and_all_account_facts(
        self,
    ) -> None:
        database = self.cluster.clone_database(
            self.business_template, "rollback"
        )
        self._configure_signal(
            database, action_state="eligible", target_price=None
        )
        proposal_id, _ = self._create_and_confirm(
            database, clock="2026-07-20 08:00:00+08"
        )
        with self.cluster.connect(database) as connection:
            connection.execute(
                """
                CREATE FUNCTION public.n6_064_fail_position_event()
                RETURNS trigger LANGUAGE plpgsql AS $fail$
                BEGIN
                  RAISE EXCEPTION 'n6_064_injected_position_event_failure';
                END
                $fail$
                """
            )
            connection.execute(
                """
                CREATE TRIGGER n6_064_fail_position_event
                BEFORE INSERT ON public.n6_virtual_position_event
                FOR EACH ROW
                EXECUTE FUNCTION public.n6_064_fail_position_event()
                """
            )
            connection.commit()
        before = self._counts(database)
        with self.assertRaises(Exception) as raised:
            self._execute(
                database,
                proposal_id=proposal_id,
                executor_run_id="n6-064-injected-failure",
                clock="2026-07-20 08:00:00+08",
            )
        self.assertIn(
            "n6_064_injected_position_event_failure", str(raised.exception)
        )
        self.assertEqual(self._counts(database), before)
        with self.cluster.connect(database) as connection:
            proposal = connection.execute(
                """
                SELECT proposal_status,executor_run_id,
                       executed_virtual_order_id,
                       executed_virtual_trade_id
                FROM public.n6_virtual_trade_proposal
                WHERE proposal_id=%s
                """,
                (proposal_id,),
            ).fetchone()
            account = connection.execute(
                """
                SELECT current_cash_snapshot_id
                FROM public.n6_virtual_account
                WHERE virtual_account_id=2
                """
            ).fetchone()
        self.assertEqual(proposal["proposal_status"], "confirmed")
        self.assertIsNone(proposal["executor_run_id"])
        self.assertIsNone(proposal["executed_virtual_order_id"])
        self.assertIsNone(proposal["executed_virtual_trade_id"])
        self.assertEqual(int(account["current_cash_snapshot_id"]), 2)


if __name__ == "__main__":
    unittest.main()
