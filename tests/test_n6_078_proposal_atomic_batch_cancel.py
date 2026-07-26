"""Contract and isolated PostgreSQL 16 acceptance for N6 migration 078."""

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
FORWARD_PATH = ROOT / "sql/078_n6_proposal_atomic_batch_cancel.sql"
ROLLBACK_PATH = ROOT / "sql/078_n6_proposal_atomic_batch_cancel_rollback.sql"
CONTRACT_PATH = ROOT / "docs/N6_PROPOSAL_ATOMIC_BATCH_CANCEL_078_CONTRACT.json"
FORWARD = FORWARD_PATH.read_text(encoding="utf-8")
ROLLBACK = ROLLBACK_PATH.read_text(encoding="utf-8")
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
PG_ENABLED = os.environ.get("ASHARE_V3_N6_078_PG_INTEGRATION") == "1"
PG_BIN = Path(
    os.environ.get(
        "ASHARE_V3_N6_078_PG_BIN",
        "/opt/homebrew/opt/postgresql@16/bin",
    )
)
SESSION_A = "a" * 64
SESSION_B = "b" * 64
OLD_GUARD_SHA = "c93231dd1bd456c34c954769016442d7e7fb04f0c040a18ca3a346b6e9745a9c"
NEW_GUARD_SHA = "8c0e5f213c7c3e83eb7c488bb3302f94de86db98c4a95901f4776e44aec2ebf8"
CANCEL_SHA = "38560d8887b0ca6f626a51f4114f36e1de1c1864442b3bedd8db2a0541722b09"


def _function_source(text: str, name: str, *, create_or_replace: bool) -> str:
    prefix = "CREATE OR REPLACE FUNCTION" if create_or_replace else "CREATE FUNCTION"
    match = re.search(
        rf"{prefix} public\.{re.escape(name)}\(.*?AS \$function\$(.*?)\$function\$;",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing function source: {name}")
    return match.group(1)


def _dollar_block(text: str, tag: str) -> str:
    match = re.search(
        rf"\${re.escape(tag)}\$(.*?)\${re.escape(tag)}\$",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing dollar block: {tag}")
    return match.group(1)


def _baseline_guard() -> str:
    schema = (ROOT / "sql/042_n6_b_track_db_role_policy_schema.sql").read_text(
        encoding="utf-8"
    )
    guard = _function_source(
        schema,
        "n6_btrack_proposal_transition_guard",
        create_or_replace=True,
    )
    migration_064 = (
        ROOT / "sql/064_n6_btrack_trade_date_all_day_buy.sql"
    ).read_text(encoding="utf-8")
    return guard.replace(
        _dollar_block(migration_064, "proposal_guard_web_042"),
        _dollar_block(migration_064, "proposal_guard_web_064"),
    )


BASELINE_GUARD = _baseline_guard()
NEW_GUARD = BASELINE_GUARD.replace(
    _dollar_block(FORWARD, "guard_web_064"),
    _dollar_block(FORWARD, "guard_web_078"),
)
CANCEL_SOURCE = _function_source(
    FORWARD,
    "n6_btrack_proposals_cancel",
    create_or_replace=False,
)


class N6078StaticContractTests(unittest.TestCase):
    def test_candidate_baseline_and_exact_function_hashes(self) -> None:
        self.assertEqual(CONTRACT["layer_role"], "N6_user")
        self.assertEqual(CONTRACT["execution_mode"], "FULL_MODE")
        self.assertEqual(CONTRACT["baseline"]["highest_migration"], "077")
        self.assertEqual(CONTRACT["baseline"]["candidate_migration"], "078")
        self.assertEqual(sha256(BASELINE_GUARD.encode()).hexdigest(), OLD_GUARD_SHA)
        self.assertEqual(sha256(NEW_GUARD.encode()).hexdigest(), NEW_GUARD_SHA)
        self.assertEqual(sha256(CANCEL_SOURCE.encode()).hexdigest(), CANCEL_SHA)
        self.assertNotIn("__CANCEL_SHA__", FORWARD + ROLLBACK)
        self.assertNotIn("__GUARD_SHA__", FORWARD + ROLLBACK)

    def test_function_is_owner_scoped_atomic_and_fixed_order(self) -> None:
        for marker in (
            "public.n6_btrack_resolve_authority(p_session_token_hash)",
            "pg_catalog.cardinality(p_proposal_ids)",
            "requested_count > 100",
            "count(DISTINCT requested.proposal_id)",
            "ORDER BY proposal.proposal_id",
            "FOR UPDATE OF proposal",
            "proposal_row.user_id IS DISTINCT FROM",
            "proposal_row.principal_id IS DISTINCT FROM",
            "proposal_row.virtual_account_id IS DISTINCT FROM account_id",
            "proposal_row.executor_run_id IS NOT NULL",
            "existing_order.source_proposal_id",
            "existing_trade.source_proposal_id",
            "mixed_cancellation_state",
            "GET DIAGNOSTICS affected_count = ROW_COUNT",
            "078_atomic_update_count_mismatch",
        ):
            self.assertIn(marker, CANCEL_SOURCE)
        self.assertNotRegex(CANCEL_SOURCE, r"\bCOMMIT\b")
        self.assertNotRegex(CANCEL_SOURCE, r"\bROLLBACK\b")
        for forbidden in ("p_user_id", "p_principal_id", "p_virtual_account_id"):
            self.assertNotIn(forbidden, CANCEL_SOURCE)

    def test_status_audit_acl_and_rollback_boundaries(self) -> None:
        for marker in (
            "proposal_status = 'rejected'",
            "failure_reason = 'cancelled_by_user'",
            "'cancellation_audit'",
            "'cancelled_at'",
            "'cancelled_by_principal_id'",
            "'cancellation_policy_version'",
            "n6_btrack_proposal_cancel_078_v1",
        ):
            self.assertIn(marker, CANCEL_SOURCE)
        self.assertIn("TO n6_btrack_web", FORWARD)
        self.assertIn("web_role_direct_proposal_dml_detected", FORWARD)
        self.assertIn("DROP FUNCTION public.n6_btrack_proposals_cancel", ROLLBACK)
        self.assertNotRegex(
            ROLLBACK,
            r"(?i)UPDATE\s+public\.n6_virtual_trade_proposal",
        )
        self.assertFalse(CONTRACT["rollback"]["restores_cancelled_proposals"])
        self.assertFalse(CONTRACT["rollback"]["deletes_cancellation_audit"])

    def test_web_api_is_one_ids_only_database_call(self) -> None:
        authority_source = (
            ROOT / "src/ashare_v3/web/n6_btrack_authority.py"
        ).read_text(encoding="utf-8")
        app_source = (ROOT / "src/ashare_v3/web/n6_user_app.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"n6_btrack_proposals_cancel"', authority_source)
        self.assertIn("(self._session_hash(session_token_hash), list(proposal_ids))", authority_source)
        self.assertIn(
            '@app.post("/api/n6/app/v3/virtual-account/proposals/cancel")',
            app_source,
        )
        self.assertIn('if set(payload) != {"proposal_ids"}', app_source)
        self.assertIn("len(set(proposal_ids)) != len(proposal_ids)", app_source)
        self.assertEqual(
            app_source.count("btrack_authority_repository.cancel_trade_proposals"),
            1,
        )


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
            prefix="n6-078-it.", dir=str(parent) if parent else None
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
            raise AssertionError(
                "isolated PostgreSQL command failed:\n"
                + completed.stdout
                + completed.stderr
            )
        return completed

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
                "n6_ai_agent",
                "n6_btrack_web",
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
            [str(PG_BIN / "psql"), *self.connection_args(), "-v", "ON_ERROR_STOP=1", "-f", str(path)]
        )

    def apply(self, path: Path) -> None:
        env = _safe_environment()
        env["PGOPTIONS"] = "-c role=ashare_v3_user"
        self._run(
            [str(PG_BIN / "psql"), *self.connection_args(), "-v", "ON_ERROR_STOP=1", "-f", str(path)],
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

CREATE TABLE public.n6_virtual_account (
  virtual_account_id bigint PRIMARY KEY,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  virtual_account_status text NOT NULL
);
CREATE TABLE public.n6_virtual_trade_proposal (
  proposal_id bigint PRIMARY KEY,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint,
  virtual_account_id bigint NOT NULL,
  source_type text DEFAULT 'signal',
  source_id text,
  source_signal_projection_id bigint,
  source_virtual_position_id bigint,
  holding_episode_no integer,
  asset_kind text DEFAULT 'stock',
  identity_key text DEFAULT 'stock:SH:600000',
  proposal_side text DEFAULT 'buy',
  signal_reference_kind text DEFAULT 'action_price',
  signal_reference_price numeric DEFAULT 10,
  locked_target_price numeric,
  proposal_status text NOT NULL,
  expires_at timestamptz DEFAULT pg_catalog.clock_timestamp() + interval '1 day',
  confirmed_at timestamptz,
  confirm_idempotency_key text,
  executed_virtual_order_id bigint,
  executed_virtual_trade_id bigint,
  executor_run_id text,
  failure_reason text,
  policy_version text DEFAULT 'fixture',
  policy_hash text DEFAULT 'fixture',
  source_lineage_json jsonb DEFAULT '{{"origin":"fixture"}}'::jsonb,
  created_at timestamptz DEFAULT pg_catalog.clock_timestamp(),
  updated_at timestamptz DEFAULT pg_catalog.clock_timestamp(),
  actor_ai_user_id bigint,
  source_ai_decision_id bigint,
  strategy_action_id bigint
);
CREATE TABLE public.n6_virtual_order (
  virtual_order_id bigint PRIMARY KEY,
  source_proposal_id bigint
);
CREATE TABLE public.n6_virtual_trade (
  virtual_trade_id bigint PRIMARY KEY,
  source_proposal_id bigint
);
CREATE TABLE public.n6_virtual_cash_ledger (cash_ledger_id bigint PRIMARY KEY);
CREATE TABLE public.n6_virtual_cash_snapshot (cash_snapshot_id bigint PRIMARY KEY);
CREATE TABLE public.n6_virtual_position (virtual_position_id bigint PRIMARY KEY);
CREATE TABLE public.n6_virtual_position_lot (virtual_position_lot_id bigint PRIMARY KEY);

CREATE FUNCTION public.n6_btrack_resolve_authority(p_session_token_hash text)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog
AS $resolver$
  SELECT CASE p_session_token_hash
    WHEN repeat('a', 64) THEN pg_catalog.jsonb_build_object(
      'user_id', 1, 'principal_id', 1, 'principal_type', 'admin'
    )
    WHEN repeat('b', 64) THEN pg_catalog.jsonb_build_object(
      'user_id', 2, 'principal_id', 2, 'principal_type', 'human_user'
    )
    ELSE NULL
  END
$resolver$;
CREATE FUNCTION public.n6_btrack_manual_signal_buy_current_scope(
  bigint,text,bigint,bigint,bigint,text,text,numeric,text
) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog
AS $scope$ SELECT true $scope$;
CREATE FUNCTION public.n6_btrack_proposal_transition_guard()
RETURNS trigger LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog
AS $guard${BASELINE_GUARD}$guard$;
CREATE TRIGGER n6_btrack_proposal_transition_guard
BEFORE INSERT OR UPDATE ON public.n6_virtual_trade_proposal
FOR EACH ROW EXECUTE FUNCTION public.n6_btrack_proposal_transition_guard();

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, n6_btrack_web;
REVOKE ALL ON FUNCTION public.n6_btrack_proposal_transition_guard() FROM PUBLIC, n6_btrack_web;
REVOKE ALL ON FUNCTION public.n6_btrack_resolve_authority(text) FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO n6_btrack_web;
GRANT EXECUTE ON FUNCTION public.n6_btrack_resolve_authority(text) TO n6_btrack_web;
RESET ROLE;
"""


@unittest.skipUnless(
    PG_ENABLED,
    "set ASHARE_V3_N6_078_PG_INTEGRATION=1 for isolated PG16 acceptance",
)
class N6078PostgresIntegrationTests(unittest.TestCase):
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

    def _metadata(self, signature: str) -> dict[str, object] | None:
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
                WHERE p.oid = pg_catalog.to_regprocedure(%s)
                """,
                (signature,),
            ).fetchone()

    def _summary(self) -> tuple[int, ...]:
        with self.cluster.connect() as connection:
            row = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM public.n6_virtual_trade_proposal) proposal_count,
                  (SELECT count(*) FROM public.n6_virtual_order) order_count,
                  (SELECT count(*) FROM public.n6_virtual_trade) trade_count,
                  (SELECT count(*) FROM public.n6_virtual_cash_ledger) ledger_count,
                  (SELECT count(*) FROM public.n6_virtual_cash_snapshot) cash_count,
                  (SELECT count(*) FROM public.n6_virtual_position) position_count,
                  (SELECT count(*) FROM public.n6_virtual_position_lot) lot_count
                """
            ).fetchone()
        return tuple(int(value) for value in row.values())

    def _call(self, session_hash: str, proposal_ids: list[int] | None) -> dict:
        with self.cluster.connect(user="n6_btrack_web") as connection:
            row = connection.execute(
                "SELECT public.n6_btrack_proposals_cancel(%s,%s::bigint[]) AS payload",
                (session_hash, proposal_ids),
            ).fetchone()
        return dict(row["payload"]) if row["payload"] is not None else {}

    def _seed_proposal(
        self,
        proposal_id: int,
        status: str,
        *,
        owner: int = 1,
        executor_run_id: str | None = None,
        executed_order_id: int | None = None,
        executed_trade_id: int | None = None,
        failure_reason: str | None = None,
    ) -> None:
        principal_type = "admin" if owner == 1 else "human_user"
        with self.cluster.connect() as connection:
            connection.execute(
                """
                INSERT INTO public.n6_virtual_trade_proposal (
                  proposal_id, principal_id, principal_type, user_id,
                  virtual_account_id, proposal_status, executor_run_id,
                  executed_virtual_order_id, executed_virtual_trade_id,
                  failure_reason, source_lineage_json
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                          '{"origin":"fixture"}'::jsonb)
                """,
                (
                    proposal_id,
                    owner,
                    principal_type,
                    owner,
                    owner,
                    status,
                    executor_run_id,
                    executed_order_id,
                    executed_trade_id,
                    failure_reason,
                ),
            )

    def _status(self, proposal_id: int) -> dict:
        with self.cluster.connect() as connection:
            return connection.execute(
                """
                SELECT proposal_status, failure_reason, source_lineage_json,
                       executor_run_id, executed_virtual_order_id,
                       executed_virtual_trade_id
                FROM public.n6_virtual_trade_proposal WHERE proposal_id=%s
                """,
                (proposal_id,),
            ).fetchone()

    def test_forward_business_matrix_and_exact_rollback(self) -> None:
        before_summary = self._summary()
        before_guard = self._metadata(
            "public.n6_btrack_proposal_transition_guard()"
        )
        self.assertEqual(before_guard["source_sha"], OLD_GUARD_SHA)
        self.assertIsNone(
            self._metadata("public.n6_btrack_proposals_cancel(text,bigint[])")
        )

        self.cluster.apply(FORWARD_PATH)
        self.assertEqual(self._summary(), before_summary)
        cancel_meta = self._metadata(
            "public.n6_btrack_proposals_cancel(text,bigint[])"
        )
        guard_meta = self._metadata(
            "public.n6_btrack_proposal_transition_guard()"
        )
        self.assertEqual(cancel_meta["source_sha"], CANCEL_SHA)
        self.assertEqual(guard_meta["source_sha"], NEW_GUARD_SHA)
        for metadata in (cancel_meta, guard_meta):
            self.assertEqual(metadata["owner_name"], "ashare_v3_user")
            self.assertTrue(metadata["prosecdef"])
            self.assertEqual(metadata["provolatile"], "v")
            self.assertEqual(metadata["proparallel"], "u")
            self.assertEqual(metadata["proconfig"], ["search_path=pg_catalog"])
        with self.cluster.connect() as connection:
            acl = connection.execute(
                """
                SELECT pg_catalog.has_function_privilege(
                         'n6_btrack_web',
                         'public.n6_btrack_proposals_cancel(text,bigint[])',
                         'EXECUTE'
                       ) AS web_execute,
                       pg_catalog.has_function_privilege(
                         'n6_virtual_executor',
                         'public.n6_btrack_proposals_cancel(text,bigint[])',
                         'EXECUTE'
                       ) AS executor_execute,
                       pg_catalog.has_table_privilege(
                         'n6_btrack_web',
                         'public.n6_virtual_trade_proposal', 'UPDATE'
                       ) AS web_update
                """
            ).fetchone()
        self.assertEqual(acl, {"web_execute": True, "executor_execute": False, "web_update": False})

        with self.cluster.connect() as connection:
            connection.execute(
                """
                INSERT INTO public.n6_virtual_account VALUES
                  (1,1,'admin','active'),
                  (2,2,'human_user','active')
                """
            )
        self._seed_proposal(1, "pending")
        self._seed_proposal(2, "confirmed")
        self._seed_proposal(3, "confirmed", owner=2)
        self._seed_proposal(4, "confirmed")
        self._seed_proposal(5, "processing")
        self._seed_proposal(6, "executed")
        self._seed_proposal(7, "expired")
        self._seed_proposal(8, "failed")
        self._seed_proposal(9, "rejected", failure_reason="risk_rejected")
        self._seed_proposal(10, "confirmed", executor_run_id="executor-ref")
        self._seed_proposal(11, "confirmed")
        self._seed_proposal(12, "confirmed")
        self._seed_proposal(14, "pending")
        self._seed_proposal(15, "confirmed", executed_order_id=88)
        self._seed_proposal(16, "confirmed", executed_trade_id=89)
        with self.cluster.connect() as connection:
            connection.execute("INSERT INTO public.n6_virtual_order VALUES (1,11)")
            connection.execute("INSERT INTO public.n6_virtual_trade VALUES (1,12)")

        success = self._call(SESSION_A, [2, 1])
        self.assertEqual(success["status"], "cancelled")
        self.assertFalse(success["idempotent"])
        self.assertEqual(success["proposal_ids"], [1, 2])
        for proposal_id in (1, 2):
            row = self._status(proposal_id)
            self.assertEqual(row["proposal_status"], "rejected")
            self.assertEqual(row["failure_reason"], "cancelled_by_user")
            self.assertEqual(row["source_lineage_json"]["origin"], "fixture")
            audit = row["source_lineage_json"]["cancellation_audit"]
            self.assertEqual(len(audit), 1)
            self.assertEqual(audit[0]["cancelled_by_principal_id"], 1)
            self.assertEqual(
                audit[0]["cancellation_policy_version"],
                "n6_btrack_proposal_cancel_078_v1",
            )
            self.assertTrue(audit[0]["cancelled_at"])
        retry = self._call(SESSION_A, [1, 2])
        self.assertTrue(retry["ok"])
        self.assertTrue(retry["idempotent"])
        self.assertEqual(
            len(self._status(1)["source_lineage_json"]["cancellation_audit"]),
            1,
        )

        invalid_calls = (
            self._call(SESSION_A, None),
            self._call(SESSION_A, []),
            self._call(SESSION_A, [4, 4]),
            self._call(SESSION_A, [0]),
            self._call(SESSION_A, [-1]),
            self._call(SESSION_A, list(range(1000, 1101))),
            self._call(SESSION_A, [4, 999]),
            self._call(SESSION_A, [3]),
            self._call(SESSION_A, [1, 14]),
        )
        self.assertTrue(all(not result.get("ok") for result in invalid_calls))
        self.assertEqual(self._status(4)["proposal_status"], "confirmed")
        self.assertEqual(self._status(14)["proposal_status"], "pending")
        for proposal_id in range(5, 13):
            result = self._call(SESSION_A, [proposal_id])
            self.assertFalse(result["ok"])
        for proposal_id in (15, 16):
            result = self._call(SESSION_A, [proposal_id])
            self.assertFalse(result["ok"])

        with self.assertRaises(Exception):
            with self.cluster.connect(user="n6_btrack_web") as connection:
                connection.execute(
                    "UPDATE public.n6_virtual_trade_proposal SET proposal_status='rejected' WHERE proposal_id=4"
                )

        summary_before_rollback = self._summary()
        self.cluster.apply(ROLLBACK_PATH)
        self.assertEqual(self._summary(), summary_before_rollback)
        self.assertIsNone(
            self._metadata("public.n6_btrack_proposals_cancel(text,bigint[])")
        )
        restored_guard = self._metadata(
            "public.n6_btrack_proposal_transition_guard()"
        )
        self.assertEqual(restored_guard["source_sha"], OLD_GUARD_SHA)
        self.assertEqual(restored_guard["owner_name"], "ashare_v3_user")
        self.assertTrue(restored_guard["prosecdef"])
        self.assertEqual(restored_guard["proconfig"], ["search_path=pg_catalog"])
        self.assertEqual(self._status(1)["proposal_status"], "rejected")
        self.assertEqual(
            len(self._status(1)["source_lineage_json"]["cancellation_audit"]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
