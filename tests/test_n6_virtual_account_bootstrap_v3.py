import inspect
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from ashare_v3.user import virtual_account_bootstrap_v3 as bootstrap


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/047_n6_virtual_account_bootstrap.sql"
ROLLBACK = ROOT / "sql/047_n6_virtual_account_bootstrap_rollback.sql"
CONTRACT = ROOT / (
    "docs/N6_B_TRACK_PRODUCT_V3_MULTI_USER_VIRTUAL_ACCOUNT_BOOTSTRAP_047_CONTRACT.json"
)
SCRIPT = ROOT / "scripts/run_n6_virtual_account_bootstrap_once.py"


class FakeRepository:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute_migration(self, sql: str) -> dict[str, object]:
        self.calls.append(sql)
        return {"executed": True, "owner_identity_verified": True}


def accepted_env() -> dict[str, str]:
    return {
        "PGSERVICE": "ashare_v3_owner",
        "PGSERVICEFILE": "/nonsecret/pg_service.conf",
        "PGPASSFILE": "/nonsecret/owner.pgpass",
    }


class N6VirtualAccountBootstrap047Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_targets_admin_and_four_humans_at_exact_100m(self) -> None:
        self.assertEqual(self.contract["initial_cash"], "100000000.0000")
        self.assertEqual(
            self.contract["target_principals"],
            [
                {"principal_id": 1, "principal_type": "admin", "mode": "audit_top_up"},
                {"principal_id": 3, "principal_type": "human_user", "mode": "create"},
                {"principal_id": 4, "principal_type": "human_user", "mode": "create"},
                {"principal_id": 5, "principal_type": "human_user", "mode": "create"},
                {"principal_id": 6, "principal_type": "human_user", "mode": "create"},
            ],
        )
        self.assertEqual(
            self.contract["cash_authority"]["admin_adjustment"],
            "99000000.0000",
        )

    def test_default_plan_is_local_and_makes_zero_repository_calls(self) -> None:
        repo = FakeRepository()
        report = bootstrap.run_bootstrap(repository=repo)
        self.assertEqual(report["result"], "PLAN_READY")
        self.assertEqual(report["mode"], "read_only_local_plan")
        self.assertFalse(report["execute_authorized"])
        self.assertEqual(
            report["execute_runtime_preflight_status"],
            "future_runtime_control_credential_gate_required",
        )
        self.assertFalse(report["database_connected"])
        self.assertFalse(report["database_written"])
        self.assertEqual(repo.calls, [])

    def test_parser_has_no_dsn_or_password_surface(self) -> None:
        parser = bootstrap.build_parser()
        options = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertIn("--execute", options)
        self.assertIn("--user-confirmed", options)
        self.assertNotIn("--dsn", options)
        self.assertNotIn("--password", options)
        self.assertNotIn("dsn", inspect.signature(bootstrap.run_bootstrap).parameters)
        self.assertNotIn("password", inspect.signature(bootstrap.run_bootstrap).parameters)

    def test_execute_requires_confirmation_and_exact_owner_environment(self) -> None:
        repo = FakeRepository()
        report = bootstrap.run_bootstrap(
            execute=True,
            repository=repo,
            env=accepted_env(),
        )
        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_user_confirmed", report["blockers"])
        self.assertEqual(repo.calls, [])

        rejected = (
            {},
            {**accepted_env(), "PGSERVICE": "n6_btrack_web"},
            {**accepted_env(), "PGPASSWORD": "secret"},
            {**accepted_env(), "ASHARE_V3_POSTGRES_DSN": "postgresql://secret"},
            {**accepted_env(), "PGSERVICEFILE": "relative/pg_service.conf"},
            {**accepted_env(), "PGPASSFILE": "relative/owner.pgpass"},
            {**accepted_env(), "PGSERVICEFILE": "/safe/service\n.conf"},
            {**accepted_env(), "PGPASSFILE": "/safe/pass\x00file"},
        )
        for env in rejected:
            with self.subTest(keys=sorted(env)):
                repo = FakeRepository()
                report = bootstrap.run_bootstrap(
                    execute=True,
                    user_confirmed=True,
                    repository=repo,
                    env=env,
                )
                self.assertEqual(report["result"], "BLOCKED")
                self.assertEqual(repo.calls, [])

    def test_repository_rejects_wrong_database_before_migration_sql(self) -> None:
        class Cursor:
            def __init__(self) -> None:
                self.statements: list[str] = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, sql):
                self.statements.append(sql)

            def fetchone(self):
                return {
                    "database_name": "wrong_database",
                    "current_role": "ashare_v3_user",
                    "session_role": "ashare_v3_user",
                    "database_owner": "ashare_v3_user",
                }

        class Connection:
            def __init__(self) -> None:
                self.cursor_instance = Cursor()
                self.committed = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def cursor(self):
                return self.cursor_instance

            def commit(self):
                self.committed = True

        connection = Connection()

        def connect(*_args, **_kwargs):
            return connection

        repository = bootstrap.PostgresBootstrapRepository(connect=connect)
        with self.assertRaisesRegex(
            RuntimeError,
            "047_owner_migration_identity_rejected",
        ):
            repository.execute_migration("SELECT forbidden_migration")
        self.assertEqual(len(connection.cursor_instance.statements), 1)
        self.assertNotIn(
            "SELECT forbidden_migration",
            connection.cursor_instance.statements,
        )
        self.assertFalse(connection.committed)

    def test_execute_passes_only_sql_to_injected_owner_repository(self) -> None:
        repo = FakeRepository()
        report = bootstrap.run_bootstrap(
            execute=True,
            user_confirmed=True,
            repository=repo,
            env=accepted_env(),
        )
        self.assertEqual(report["result"], "EXECUTED")
        self.assertTrue(report["database_connected"])
        self.assertTrue(report["database_written"])
        self.assertEqual(repo.calls, [self.migration])
        serialized = json.dumps(report)
        self.assertNotIn("owner.pgpass", serialized)
        self.assertNotIn("pg_service.conf", serialized)

    def test_contract_validation_is_canonical_and_fail_closed(self) -> None:
        payload, blockers = bootstrap.validate_contract(CONTRACT)
        self.assertEqual(blockers, [])
        self.assertEqual(payload["contract_version"], bootstrap.RUN_ID)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "contract.json"
            changed = dict(payload)
            changed["initial_cash"] = "100000000"
            path.write_text(json.dumps(changed), encoding="utf-8")
            _, blockers = bootstrap.validate_contract(path)
        self.assertIn("contract_initial_cash_mismatch", blockers)

    def test_sql_is_one_transaction_and_uses_locks_not_schema_changes(self) -> None:
        self.assertEqual(self.migration.count("BEGIN;"), 1)
        self.assertEqual(self.migration.count("COMMIT;"), 1)
        self.assertIn("pg_advisory_xact_lock", self.migration)
        self.assertIn("FOR UPDATE", self.migration)
        self.assertIn("public.n6_principal", self.migration)
        self.assertIn("IN SHARE ROW EXCLUSIVE MODE", self.migration)
        for sql in (self.migration, self.rollback):
            self.assertNotRegex(sql, r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\b")
            self.assertNotRegex(sql, r"\bALTER\s+TABLE\b")
            self.assertNotRegex(sql, r"\bCREATE\s+TABLE\b")
            self.assertNotRegex(sql, r"\bADD\s+CONSTRAINT\b")
        self.assertFalse(
            self.contract["idempotency"]["schema_index_or_constraint_change"]
        )

    def test_principal_authority_is_exact_and_rejects_role_or_status_drift(self) -> None:
        for token in (
            "(1::bigint, 'admin'::text, 1::bigint, 'admin'::text)",
            "(3::bigint, 'human_user'::text, 3::bigint, 'user'::text)",
            "(4::bigint, 'human_user'::text, 4::bigint, 'user'::text)",
            "(5::bigint, 'human_user'::text, 5::bigint, 'user'::text)",
            "(6::bigint, 'human_user'::text, 6::bigint, 'user'::text)",
            "a.principal_status IS DISTINCT FROM 'active'",
            "a.status IS DISTINCT FROM 'active'",
            "system ai or inactive principal rejected",
            "current_database() IS DISTINCT FROM 'ashare_v3'",
        ):
            self.assertIn(token, self.migration)

    def test_human_bootstrap_and_admin_top_up_are_append_audited(self) -> None:
        for value in (
            "100000000.0000",
            "99000000.0000",
            "'initial_deposit'",
            "'adjustment'",
            "'047:principal:1:admin_top_up'",
            "'n6_virtual_account_bootstrap_047'",
        ):
            self.assertIn(value, self.migration)
        self.assertIn("admin_ledger_count <> 1", self.migration)
        self.assertIn("admin_snapshot_count <> 1", self.migration)
        self.assertIn("admin_account.initial_cash <> 1000000.0000", self.migration)
        self.assertNotRegex(
            self.migration,
            r"UPDATE\s+public\.n6_virtual_account\s+SET\s+initial_cash",
        )
        self.assertNotRegex(
            self.migration,
            r"UPDATE\s+public\.n6_virtual_cash_ledger",
        )
        self.assertIn("snapshot_status = 'superseded'", self.migration)

    def test_exact_one_cash_pointer_and_rerun_zero_dml_guards_exist(self) -> None:
        for token in (
            "completed_human_count = 0 AND admin_adjustment_count = 0",
            "completed_human_count = 4 AND admin_adjustment_count = 1",
            "partial bootstrap state rejected",
            "current_cash_snapshot_id IS DISTINCT FROM",
            "snapshot_status = 'active'",
            "post-write exactly-one account/cash authority failed",
            "admin_ledger_count <> 2",
            "admin_snapshot_count <> 2",
            "s.source_ledger_max_id = admin_adjustment_id",
            "phase3_admin_initial_cash_snapshot",
            "rerun admin cash history or pointer drifted",
        ):
            self.assertIn(token, self.migration)

    def test_main_migration_dml_is_only_three_allowed_tables(self) -> None:
        dml_targets = re.findall(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?)\s+"
            r"(public\.[a-zA-Z0-9_]+)",
            self.migration,
            re.IGNORECASE,
        )
        self.assertTrue(dml_targets)
        self.assertEqual(
            set(dml_targets),
            {
                "public.n6_virtual_account",
                "public.n6_virtual_cash_ledger",
                "public.n6_virtual_cash_snapshot",
            },
        )
        for table in self.contract["forbidden_dml_tables"]:
            self.assertNotRegex(
                self.migration,
                rf"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+"
                rf"(?:public\.)?{re.escape(table)}\b",
            )

    def test_dirty_accounts_cash_authority_and_business_dependencies_block(self) -> None:
        for token in (
            "already has account",
            "admin account has business dependencies",
            "admin cash authority audit rejected",
            "cash history contaminated",
            "n6_virtual_trade_proposal",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "n6_virtual_position_lot",
            "n6_virtual_position_event",
        ):
            self.assertIn(token, self.migration)

    def test_rollback_is_dependency_protected_and_admin_default_blocked(self) -> None:
        self.assertIn(
            "n6.bootstrap_047_allow_admin_reverse_adjustment",
            self.rollback,
        )
        self.assertIn("admin rollback blocked", self.rollback)
        self.assertIn("-99000000.0000", self.rollback)
        self.assertIn("append_only_admin_reverse_adjustment", self.rollback)
        self.assertNotIn("setval(", self.rollback.lower())
        self.assertNotRegex(
            self.rollback,
            r"DELETE\s+FROM\s+public\.n6_virtual_(?:cash_ledger|cash_snapshot)"
            r".*principal_id\s*=\s*1",
        )
        for table in (
            "n6_virtual_trade_proposal",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "n6_virtual_position_lot",
            "n6_virtual_position_event",
            "n6_virtual_pnl_snapshot",
        ):
            self.assertIn(f"public.{table}", self.rollback)

    def test_rollback_nulls_exact_four_human_pointers_before_deletes(self) -> None:
        pointer_update = self.rollback.index(
            "UPDATE public.n6_virtual_account\n"
            "  SET current_cash_snapshot_id = NULL"
        )
        pointer_count = self.rollback.index(
            "IF nulled_human_pointer_count <> 4"
        )
        snapshot_delete = self.rollback.index(
            "DELETE FROM public.n6_virtual_cash_snapshot s"
        )
        ledger_delete = self.rollback.index(
            "DELETE FROM public.n6_virtual_cash_ledger l"
        )
        account_delete = self.rollback.index(
            "DELETE FROM public.n6_virtual_account a"
        )
        self.assertLess(pointer_update, pointer_count)
        self.assertLess(pointer_count, snapshot_delete)
        self.assertLess(snapshot_delete, ledger_delete)
        self.assertLess(ledger_delete, account_delete)

    def test_no_runtime_executor_quote_outbox_or_secret_output_path(self) -> None:
        combined = "\n".join(
            (
                self.migration,
                self.rollback,
                inspect.getsource(bootstrap),
                SCRIPT.read_text(encoding="utf-8"),
            )
        )
        for pattern in (
            r"\blaunchctl\b",
            r"\bplist\b",
            r"\bCREATE\s+(?:ROLE|USER)\b",
            r"\bGRANT\b",
            r"\bNOTIFY\b",
            r"\bpg_notify\b",
        ):
            self.assertIsNone(re.search(pattern, combined, re.IGNORECASE), pattern)
        for table in (
            "common_event_outbox",
            "n6_virtual_quote_snapshot",
            "user_monitor_stock",
            "user_projection_run",
        ):
            self.assertNotRegex(
                self.migration,
                rf"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"
                rf"(?:public\.)?{table}\b",
            )


if __name__ == "__main__":
    unittest.main()
