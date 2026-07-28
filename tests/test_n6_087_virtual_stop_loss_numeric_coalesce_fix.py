"""Contract and isolated PostgreSQL 16 acceptance for N6 migration 087."""

from __future__ import annotations

import getpass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FORWARD_PATH = ROOT / "sql/087_n6_virtual_stop_loss_numeric_coalesce_fix.sql"
ROLLBACK_PATH = (
    ROOT / "sql/087_n6_virtual_stop_loss_numeric_coalesce_fix_rollback.sql"
)
CONTRACT_PATH = (
    ROOT / "docs/N6_VIRTUAL_STOP_LOSS_NUMERIC_COALESCE_FIX_087_CONTRACT.json"
)
BASELINE_PATH = ROOT / "sql/057_n6_ai_agent_execution_compat.sql"
FORWARD = FORWARD_PATH.read_text(encoding="utf-8")
ROLLBACK = ROLLBACK_PATH.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
PG_ENABLED = os.environ.get("ASHARE_V3_N6_087_PG_INTEGRATION") == "1"
PG_BIN = Path(
    os.environ.get(
        "ASHARE_V3_N6_087_PG_BIN",
        "/opt/homebrew/opt/postgresql@16/bin",
    )
)
OLD_EXPRESSION = "IF pg_catalog.coalesce(matured_quantity, 0) <= 0 THEN"
NEW_EXPRESSION = "IF COALESCE(matured_quantity, 0::numeric) <= 0 THEN"
OLD_SHA = "a858e12f58ef032946fa08c8eb067ae680cd6660389880f4c664fd739fdebccb"
NEW_SHA = "fe3b0ac7297f24fc0a5925d178ccb1f26e575716baea48dce40ef6b2af0a1443"


def _function_source(text: str, name: str) -> str:
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{re.escape(name)}\(.*?"
        r"AS \$function\$(.*?)\$function\$;",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function source: {name}")
    return match.group(1)


BASELINE_SOURCE = _function_source(
    BASELINE_PATH.read_text(encoding="utf-8"),
    "n6_executor_evaluate_next_stop_loss",
)
FIXED_SOURCE = BASELINE_SOURCE.replace(OLD_EXPRESSION, NEW_EXPRESSION)


class N6087StaticContractTests(unittest.TestCase):
    def test_exact_baseline_and_fixed_function_hashes(self) -> None:
        self.assertEqual(sha256(BASELINE_SOURCE.encode()).hexdigest(), OLD_SHA)
        self.assertEqual(BASELINE_SOURCE.count(OLD_EXPRESSION), 1)
        self.assertNotIn(NEW_EXPRESSION, BASELINE_SOURCE)
        self.assertEqual(sha256(FIXED_SOURCE.encode()).hexdigest(), NEW_SHA)
        self.assertEqual(FIXED_SOURCE.count(NEW_EXPRESSION), 1)
        self.assertNotIn(OLD_EXPRESSION, FIXED_SOURCE)
        self.assertEqual(CONTRACT["baseline"]["candidate_migration"], "087")
        self.assertEqual(
            CONTRACT["repair"]["new_evaluator_source_sha256"], NEW_SHA
        )

    def test_migration_is_one_expression_function_only_rewrite(self) -> None:
        for marker in (
            OLD_SHA,
            NEW_SHA,
            OLD_EXPRESSION,
            NEW_EXPRESSION,
            "087_stop_loss_evaluator_rewrite_scope_drift",
            "087_unexpected_business_dml",
        ):
            self.assertIn(marker, FORWARD)
        self.assertIn("pg_catalog.replace(source_text, old_text, new_text)", FORWARD)
        self.assertIn(
            "CREATE OR REPLACE FUNCTION public.n6_executor_evaluate_next_stop_loss(",
            FORWARD,
        )
        self.assertNotRegex(
            FORWARD,
            r"(?i)\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
            r"public\.n6_virtual_(?:trade_proposal|order|trade|cash|position)",
        )

    def test_acl_attributes_and_rollback_are_exact(self) -> None:
        for text in (FORWARD, ROLLBACK):
            for marker in (
                "OWNER TO ashare_v3_user",
                "FROM PUBLIC",
                "FROM n6_btrack_web",
                "FROM n6_ai_agent",
                "FROM n6_quote_writer",
                "TO n6_virtual_executor",
                "search_path = pg_catalog",
                "SECURITY DEFINER",
                "VOLATILE",
            ):
                self.assertIn(marker, text)
        self.assertIn(NEW_SHA, ROLLBACK)
        self.assertIn(OLD_SHA, ROLLBACK)
        self.assertIn("087_rollback_unexpected_business_dml", ROLLBACK)
        self.assertFalse(CONTRACT["rollback"]["deletes_history"])
        self.assertFalse(CONTRACT["historical_missed_stops"]["backfilled"])

    def test_stop_policy_and_trade_log_contract_remain_unchanged(self) -> None:
        self.assertTrue(
            CONTRACT["preserved_rules"]["two_adjacent_minutes_at_or_below_stop"]
        )
        self.assertTrue(CONTRACT["preserved_rules"]["matured_t1_lots_required"])
        stop_sql = (
            ROOT / "sql/049_n6_virtual_stop_loss_freeze_evaluate_execute.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("proposal.source_type = 'stop_loss'", stop_sql)
        self.assertIn("q1.current_price <= p.stop_loss_price", BASELINE_SOURCE)
        self.assertIn("q2.current_price <= p.stop_loss_price", BASELINE_SOURCE)
        trade_list_sql = (
            ROOT / "sql/042_n6_b_track_db_role_policy_schema.sql"
        ).read_text(encoding="utf-8")
        trade_list = _function_source(
            trade_list_sql,
            "n6_btrack_virtual_trade_list",
        )
        self.assertIn("FROM public.n6_virtual_trade t,authority a", trade_list)
        self.assertNotIn("source_type", trade_list)


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
        parent = Path("/private/tmp") if Path("/private/tmp").is_dir() else None
        self.temporary = tempfile.TemporaryDirectory(
            prefix="n6-087-it.", dir=str(parent) if parent else None
        )
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.socket_dir = self.root / "socket"
        self.socket_dir.mkdir()
        self.port = _free_port()
        self.superuser = getpass.getuser()

    def _run(
        self,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args,
            cwd=ROOT,
            env=env or _safe_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            raise AssertionError(
                "isolated PostgreSQL command failed:\n"
                + result.stdout
                + result.stderr
            )
        return result

    def connection_args(self, *, user: str | None = None) -> list[str]:
        return [
            "--host",
            str(self.socket_dir),
            "--port",
            str(self.port),
            "--username",
            user or self.superuser,
            "--dbname",
            "postgres",
        ]

    def start(self) -> None:
        self._run(
            [
                str(PG_BIN / "initdb"),
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
                str(PG_BIN / "pg_ctl"),
                "--pgdata",
                str(self.data),
                "--log",
                str(self.root / "postgres.log"),
                "--options",
                f"-F -k {self.socket_dir} -p {self.port} -c listen_addresses=''",
                "--wait",
                "start",
            ]
        )
        roles = "\n".join(
            f"CREATE ROLE {role} LOGIN;"
            for role in (
                "ashare_v3_user",
                "n6_btrack_web",
                "n6_ai_agent",
                "n6_quote_writer",
                "n6_virtual_executor",
            )
        )
        self.run_sql(roles, label="roles")

    def stop(self) -> None:
        if (self.data / "postmaster.pid").exists():
            self._run(
                [
                    str(PG_BIN / "pg_ctl"),
                    "--pgdata",
                    str(self.data),
                    "--mode",
                    "fast",
                    "--wait",
                    "stop",
                ]
            )
        self.temporary.cleanup()

    def run_sql(self, text: str, *, label: str) -> None:
        path = self.root / f"{label}.sql"
        path.write_text(text, encoding="utf-8")
        self._run(
            [
                str(PG_BIN / "psql"),
                *self.connection_args(),
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(path),
            ]
        )

    def apply(self, path: Path) -> None:
        env = _safe_environment()
        env["PGOPTIONS"] = "-c role=ashare_v3_user"
        self._run(
            [
                str(PG_BIN / "psql"),
                *self.connection_args(),
                "-v",
                "ON_ERROR_STOP=1",
                "-f",
                str(path),
            ],
            env=env,
        )

    def connect(self, *, user: str | None = None):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(
            host=str(self.socket_dir),
            port=self.port,
            dbname="postgres",
            user=user or self.superuser,
            row_factory=dict_row,
        )


def _fixture_schema_sql() -> str:
    return f"""
GRANT USAGE, CREATE ON SCHEMA public TO ashare_v3_user;
SET ROLE ashare_v3_user;

CREATE TABLE public.common_trade_calendar (
  trade_date text PRIMARY KEY,
  is_open boolean NOT NULL
);
CREATE TABLE public.n6_principal (
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  owner_user_id bigint,
  principal_status text NOT NULL,
  PRIMARY KEY (principal_id, principal_type)
);
CREATE TABLE public.n6_ai_user (
  ai_user_id bigint PRIMARY KEY,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  status text NOT NULL
);
CREATE TABLE public.n6_virtual_position (
  virtual_position_id bigint PRIMARY KEY,
  virtual_account_id bigint NOT NULL,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  asset_kind text NOT NULL,
  identity_key text NOT NULL,
  position_status text NOT NULL,
  quantity numeric(24,4) NOT NULL,
  holding_episode_no integer NOT NULL,
  stop_loss_status text,
  stop_loss_effective_trade_date date,
  stop_loss_price numeric(24,8),
  stop_loss_source_quote_snapshot_id bigint,
  stop_loss_policy_version text,
  stop_loss_policy_hash text
);
CREATE TABLE public.n6_virtual_position_lot (
  virtual_position_lot_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_position_id bigint NOT NULL,
  virtual_account_id bigint NOT NULL,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  identity_key text NOT NULL,
  holding_episode_no integer NOT NULL,
  remaining_quantity numeric(24,4) NOT NULL,
  available_trade_date date NOT NULL,
  lot_status text NOT NULL
);
CREATE TABLE public.n6_virtual_quote_snapshot (
  virtual_quote_snapshot_id bigint PRIMARY KEY,
  identity_key text NOT NULL,
  exchange text NOT NULL,
  quote_minute timestamptz NOT NULL,
  fetched_at timestamptz NOT NULL,
  quality_status text NOT NULL,
  quality_reason text NOT NULL,
  current_price numeric(24,8)
);
CREATE TABLE public.n6_virtual_trade_proposal (
  proposal_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint,
  actor_ai_user_id bigint,
  source_ai_decision_id bigint,
  virtual_account_id bigint NOT NULL,
  source_type text NOT NULL,
  source_id text,
  source_signal_projection_id bigint,
  source_virtual_position_id bigint,
  holding_episode_no integer,
  asset_kind text NOT NULL,
  identity_key text NOT NULL,
  proposal_side text NOT NULL,
  signal_reference_kind text,
  signal_reference_price numeric(24,8),
  locked_target_price numeric(24,8),
  proposal_status text NOT NULL,
  expires_at timestamptz,
  confirmed_at timestamptz,
  confirm_idempotency_key text UNIQUE,
  executed_virtual_order_id bigint,
  executed_virtual_trade_id bigint,
  executor_run_id text,
  failure_reason text,
  policy_version text,
  policy_hash text,
  source_lineage_json jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);
CREATE TABLE public.n6_virtual_order (
  virtual_order_id bigint PRIMARY KEY
);
CREATE TABLE public.n6_virtual_trade (
  virtual_trade_id bigint PRIMARY KEY
);
CREATE TABLE public.n6_virtual_cash_ledger (
  cash_ledger_id bigint PRIMARY KEY
);
CREATE TABLE public.n6_virtual_cash_snapshot (
  cash_snapshot_id bigint PRIMARY KEY
);

CREATE OR REPLACE FUNCTION public.n6_executor_evaluate_next_stop_loss(
  p_executor_run_id text
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog AS $function${BASELINE_SOURCE}$function$;
ALTER FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  OWNER TO ashare_v3_user;
REVOKE ALL ON FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
GRANT EXECUTE ON FUNCTION public.n6_executor_evaluate_next_stop_loss(text)
  TO n6_virtual_executor;
RESET ROLE;
"""


@unittest.skipUnless(
    PG_ENABLED,
    "set ASHARE_V3_N6_087_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6087PostgresIntegrationTests(unittest.TestCase):
    cluster: _Pg16Cluster

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        for binary in ("initdb", "pg_ctl", "postgres", "psql"):
            if not (PG_BIN / binary).is_file():
                raise AssertionError(f"PostgreSQL 16 binary missing: {binary}")
        version = subprocess.run(
            [str(PG_BIN / "postgres"), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if version.returncode or " 16." not in version.stdout:
            raise AssertionError(f"PostgreSQL 16 required: {version.stdout}")
        cls.cluster = _Pg16Cluster()
        cls.cluster.start()
        cls.cluster.run_sql(_fixture_schema_sql(), label="fixture_schema")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.cluster.stop()
        super().tearDownClass()

    def _metadata(self) -> dict[str, object]:
        with self.cluster.connect() as connection:
            return connection.execute(
                """
                SELECT pg_catalog.encode(
                         pg_catalog.sha256(
                           pg_catalog.convert_to(p.prosrc, 'UTF8')
                         ), 'hex'
                       ) AS source_sha,
                       owner.rolname AS owner_name,
                       p.prosecdef, p.provolatile, p.proparallel, p.proconfig
                FROM pg_catalog.pg_proc p
                JOIN pg_catalog.pg_roles owner ON owner.oid = p.proowner
                WHERE p.oid = pg_catalog.to_regprocedure(
                  'public.n6_executor_evaluate_next_stop_loss(text)'
                )
                """
            ).fetchone()

    def _summary(self) -> tuple[int, ...]:
        with self.cluster.connect() as connection:
            row = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM public.n6_virtual_trade_proposal)
                    AS proposal_count,
                  (SELECT count(*) FROM public.n6_virtual_order)
                    AS order_count,
                  (SELECT count(*) FROM public.n6_virtual_trade)
                    AS trade_count,
                  (SELECT count(*) FROM public.n6_virtual_cash_ledger)
                    AS ledger_count,
                  (SELECT count(*) FROM public.n6_virtual_cash_snapshot)
                    AS cash_count,
                  (SELECT count(*) FROM public.n6_virtual_position)
                    AS position_count,
                  (SELECT count(*) FROM public.n6_virtual_position_lot)
                    AS lot_count
                """
            ).fetchone()
        return tuple(int(value) for value in row.values())

    def _install_test_clock(self) -> None:
        from psycopg import sql

        with self.cluster.connect() as connection:
            connection.execute(
                """
                CREATE TABLE public.n6_test_clock_state (
                  instant timestamptz NOT NULL
                );
                INSERT INTO public.n6_test_clock_state VALUES
                  ('2026-07-24 10:02:00+08'::timestamptz);
                GRANT SELECT ON public.n6_test_clock_state TO ashare_v3_user;
                CREATE FUNCTION public.n6_test_clock()
                RETURNS timestamptz LANGUAGE sql STABLE
                AS $clock$
                  SELECT instant FROM public.n6_test_clock_state LIMIT 1
                $clock$;
                """
            )
            source = connection.execute(
                """
                SELECT p.prosrc FROM pg_catalog.pg_proc p
                WHERE p.oid = pg_catalog.to_regprocedure(
                  'public.n6_executor_evaluate_next_stop_loss(text)'
                )
                """
            ).fetchone()["prosrc"]
            source = source.replace(
                "pg_catalog.clock_timestamp()",
                "public.n6_test_clock()",
            )
            connection.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION "
                    "public.n6_executor_evaluate_next_stop_loss("
                    "p_executor_run_id text) RETURNS jsonb LANGUAGE plpgsql "
                    "VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS {}"
                ).format(sql.Literal(source))
            )
            connection.execute(
                """
                ALTER FUNCTION
                  public.n6_executor_evaluate_next_stop_loss(text)
                  OWNER TO ashare_v3_user;
                REVOKE ALL ON FUNCTION
                  public.n6_executor_evaluate_next_stop_loss(text)
                  FROM PUBLIC, n6_btrack_web, n6_ai_agent, n6_quote_writer;
                GRANT EXECUTE ON FUNCTION
                  public.n6_executor_evaluate_next_stop_loss(text)
                  TO n6_virtual_executor;
                """
            )

    def _call(self) -> dict[str, object]:
        with self.cluster.connect(user="n6_virtual_executor") as connection:
            row = connection.execute(
                """
                SELECT public.n6_executor_evaluate_next_stop_loss(
                  'n6-087-isolated-pg16'
                ) AS payload
                """
            ).fetchone()
        return dict(row["payload"])

    def test_forward_business_path_and_exact_rollback(self) -> None:
        before_summary = self._summary()
        self.assertEqual(self._metadata()["source_sha"], OLD_SHA)

        self.cluster.apply(FORWARD_PATH)
        self.assertEqual(self._summary(), before_summary)
        metadata = self._metadata()
        self.assertEqual(metadata["source_sha"], NEW_SHA)
        self.assertEqual(metadata["owner_name"], "ashare_v3_user")
        self.assertTrue(metadata["prosecdef"])
        self.assertEqual(metadata["provolatile"], "v")
        self.assertEqual(metadata["proparallel"], "u")
        self.assertEqual(metadata["proconfig"], ["search_path=pg_catalog"])
        with self.cluster.connect() as connection:
            acl = connection.execute(
                """
                SELECT pg_catalog.has_function_privilege(
                         'n6_virtual_executor',
                         'public.n6_executor_evaluate_next_stop_loss(text)',
                         'EXECUTE'
                       ) AS executor_execute,
                       pg_catalog.has_function_privilege(
                         'n6_btrack_web',
                         'public.n6_executor_evaluate_next_stop_loss(text)',
                         'EXECUTE'
                       ) AS web_execute
                """
            ).fetchone()
        self.assertEqual(
            acl,
            {"executor_execute": True, "web_execute": False},
        )

        self.cluster.apply(ROLLBACK_PATH)
        self.assertEqual(self._summary(), before_summary)
        self.assertEqual(self._metadata()["source_sha"], OLD_SHA)
        self.cluster.apply(FORWARD_PATH)
        self.assertEqual(self._metadata()["source_sha"], NEW_SHA)

        with self.cluster.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(NULL::numeric, 0::numeric) AS null_value,
                       COALESCE(0::numeric, 0::numeric) AS zero_value,
                       COALESCE(125::numeric, 0::numeric) AS positive_value
                """
            ).fetchone()
        self.assertEqual(tuple(row.values()), (0, 0, 125))

        self._install_test_clock()
        with self.cluster.connect() as connection:
            connection.execute(
                """
                INSERT INTO public.common_trade_calendar VALUES
                  ('20260724', true);
                INSERT INTO public.n6_principal VALUES
                  (1, 'admin', 1, 'active');
                INSERT INTO public.n6_virtual_position VALUES (
                  1, 1, 1, 'admin', 'stock', 'stock:SH:600000',
                  'open_virtual', 100, 1, 'frozen', '2026-07-24', 10,
                  90, 'n6_virtual_stop_loss_049_v1', 'hash-049'
                );
                INSERT INTO public.n6_virtual_position_lot (
                  virtual_position_id, virtual_account_id, principal_id,
                  principal_type, identity_key, holding_episode_no,
                  remaining_quantity, available_trade_date, lot_status
                ) VALUES (
                  1, 1, 1, 'admin', 'stock:SH:600000', 1,
                  100, '2026-07-24', 'available'
                );
                INSERT INTO public.n6_virtual_quote_snapshot VALUES
                  (101, 'stock:SH:600000', 'SH',
                   '2026-07-24 10:01:00+08', '2026-07-24 10:01:05+08',
                   'passed', 'ok', 9.90);
                """
            )

        one_minute = self._call()
        self.assertEqual(one_minute["status"], "not_ready")
        self.assertEqual(one_minute["reason"], "no_evaluation_candidate")
        self.assertEqual(self._summary()[0], 0)

        with self.cluster.connect() as connection:
            connection.execute(
                """
                INSERT INTO public.n6_virtual_quote_snapshot VALUES
                  (100, 'stock:SH:600000', 'SH',
                   '2026-07-24 10:00:00+08', '2026-07-24 10:00:05+08',
                   'passed', 'ok', 9.95);
                """
            )
        confirmed = self._call()
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["proposal_id"], 1)
        with self.cluster.connect() as connection:
            proposal = connection.execute(
                """
                SELECT source_type, proposal_side, proposal_status,
                       signal_reference_kind, signal_reference_price,
                       source_virtual_position_id, holding_episode_no
                FROM public.n6_virtual_trade_proposal
                """
            ).fetchone()
        self.assertEqual(
            proposal,
            {
                "source_type": "stop_loss",
                "proposal_side": "sell",
                "proposal_status": "confirmed",
                "signal_reference_kind": "stop_loss",
                "signal_reference_price": 10,
                "source_virtual_position_id": 1,
                "holding_episode_no": 1,
            },
        )
        duplicate = self._call()
        self.assertEqual(duplicate["status"], "not_ready")
        self.assertEqual(self._summary()[0], 1)


if __name__ == "__main__":
    unittest.main()
