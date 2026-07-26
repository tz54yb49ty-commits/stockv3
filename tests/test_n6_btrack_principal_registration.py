import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/043_n6_btrack_legacy_principal_registration.sql"
ROLLBACK = ROOT / "sql/043_n6_btrack_legacy_principal_registration_rollback.sql"
CONTRACT = ROOT / "docs/N6_B_TRACK_PRODUCT_V3_LEGACY_PRINCIPAL_REGISTRATION_CONTRACT.json"
MARKER = "043_n6_btrack_legacy_principal_registration_v1"


class N6BTrackPrincipalRegistration043Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text()
        cls.rollback = ROLLBACK.read_text()
        cls.contract = json.loads(CONTRACT.read_text())

    def test_contract_has_exact_four_deterministic_rows(self) -> None:
        rows = self.contract["target_principals"]
        self.assertEqual([row["principal_id"] for row in rows], [3, 4, 5, 6])
        for row in rows:
            self.assertEqual(row["principal_id"], row["owner_user_id"])
            self.assertEqual(row["principal_type"], "human_user")
            self.assertEqual(row["principal_status"], "active")
            self.assertIsNone(row["principal_label"])
        self.assertEqual(self.contract["registration_marker"], MARKER)

    def test_migration_is_one_transaction_with_required_locks(self) -> None:
        self.assertEqual(self.migration.count("BEGIN;"), 1)
        self.assertEqual(self.migration.count("COMMIT;"), 1)
        self.assertIn("LOCK TABLE public.user_account IN SHARE MODE", self.migration)
        self.assertIn("LOCK TABLE public.n6_principal IN SHARE ROW EXCLUSIVE MODE", self.migration)
        self.assertIsNotNone(
            re.search(
                r"WHERE u\.user_id IN \(3, 4, 5, 6\).*?FOR SHARE;",
                self.migration,
                re.DOTALL,
            )
        )

    def test_generated_always_identity_uses_only_explicit_system_values(self) -> None:
        self.assertIn("OVERRIDING SYSTEM VALUE", self.migration)
        self.assertNotRegex(self.migration, r"\bnextval\s*\(")
        target_block = self.migration.split(
            "WITH target(principal_id, principal_type, owner_user_id, principal_status)",
            1,
        )[1].split("GET DIAGNOSTICS inserted_count", 1)[0]
        for principal_id in (3, 4, 5, 6):
            self.assertIn(
                f"({principal_id}::bigint, 'human_user'::text, {principal_id}::bigint, 'active'::text)",
                target_block,
            )

    def test_first_run_and_exact_rerun_are_bounded_to_four_then_zero(self) -> None:
        self.assertIn("existing_exact_count NOT IN (0, 4)", self.migration)
        self.assertIn("WHERE NOT EXISTS", self.migration)
        self.assertIn("inserted_count <> 4 - existing_exact_count", self.migration)
        self.assertIn("registered_count <> 4", self.migration)

    def test_authority_conflicts_and_marker_drift_fail_closed(self) -> None:
        for token in (
            "043 active admin/user authority set drifted",
            "043 target principal id collision or marker/field drift",
            "043 target owner already has conflicting principal",
            "043 partial registration state rejected",
            "043 legacy principal ownership mismatch",
            "043 frozen legacy scope matrix drifted",
        ):
            self.assertIn(token, self.migration)
        self.assertIn("u.status = 'active'", self.migration)
        self.assertIn("u.role IN ('admin', 'user')", self.migration)
        self.assertIn("p.principal_policy_json = registration_marker", self.migration)

    def test_legacy_scope_matrix_is_exact_and_has_no_scope_dml(self) -> None:
        expected = {
            "3": {"stock": 1074, "index": 79, "board": 256, "realtime": 1886},
            "4": {"stock": 0, "index": 0, "board": 0, "realtime": 9},
            "5": {"stock": 2586, "index": 18, "board": 273, "realtime": 0},
            "6": {"stock": 1850, "index": 0, "board": 0, "realtime": 9},
        }
        self.assertEqual(self.contract["legacy_scope_matrix"], expected)
        for source, table in (
            ("stock", "user_monitor_stock"),
            ("index", "user_monitor_index"),
            ("board", "user_monitor_board"),
            ("realtime", "user_realtime_monitor_scope"),
        ):
            self.assertIn(f"'{source}'", self.migration)
            self.assertIn(f"public.{table}", self.migration)
            self.assertNotRegex(
                self.migration,
                rf"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+public\.{table}\b",
            )
            self.assertNotRegex(
                self.rollback,
                rf"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+public\.{table}\b",
            )
        for sql in (self.migration, self.rollback):
            self.assertIn(
                "COALESCE(a.row_count, 0) IS DISTINCT FROM e.row_count",
                sql,
            )
            self.assertNotIn("OR a.source_name IS NULL", sql)

    def test_sequence_advances_monotonically_and_rollback_never_rewinds(self) -> None:
        self.assertIn("pg_catalog.setval(", self.migration)
        self.assertIn("GREATEST(", self.migration)
        self.assertIn("(SELECT max(principal_id) FROM public.n6_principal)", self.migration)
        self.assertIn("sequence_result < 6", self.migration)
        self.assertNotIn("pg_catalog.setval(", self.rollback)
        self.assertIn("sequence_last_value < 6", self.rollback)
        self.assertIn("must not lower principal identity sequence", self.rollback)

    def test_migration_dml_is_only_principal_insert_and_sequence_setval(self) -> None:
        dml_targets = re.findall(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?)\s+(public\.[a-zA-Z0-9_]+)",
            self.migration,
            re.IGNORECASE,
        )
        self.assertEqual(dml_targets, ["public.n6_principal"])
        self.assertNotRegex(self.migration, r"\bCREATE\s+TABLE\b")
        self.assertNotRegex(self.migration, r"\bALTER\s+TABLE\b")

    def test_rollback_has_exact_dependency_blockers_and_only_principal_delete(self) -> None:
        for table in self.contract["rollback"]["protected_dependency_tables"]:
            self.assertIn(f"public.{table}", self.rollback)
        self.assertIn("protected_dependency_count <> 0", self.rollback)
        self.assertIn("registered_count <> 4", self.rollback)
        self.assertIn("deleted_count <> 4", self.rollback)
        dml_targets = re.findall(
            r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE(?:\s+TABLE)?)\s+(public\.[a-zA-Z0-9_]+)",
            self.rollback,
            re.IGNORECASE,
        )
        self.assertEqual(dml_targets, ["public.n6_principal"])

        # Keep these assertions independent of the canonical dependency list so
        # the SQL and JSON cannot omit the same cash-ledger boundary together.
        lock_block = self.rollback.split("LOCK TABLE\n", 1)[1].split(
            "IN SHARE ROW EXCLUSIVE MODE;",
            1,
        )[0]
        self.assertIn("public.n6_virtual_cash_ledger", lock_block)

        dependency_block = self.rollback.split(
            "INTO protected_dependency_count",
            1,
        )[1].split(") dependencies;", 1)[0]
        self.assertIn(
            "FROM public.n6_virtual_cash_ledger cash_ledger",
            dependency_block,
        )
        self.assertIn(
            "JOIN public.n6_virtual_account cash_ledger_account",
            dependency_block,
        )
        self.assertIn(
            "cash_ledger_account.virtual_account_id = cash_ledger.virtual_account_id",
            dependency_block,
        )
        self.assertIn(
            "cash_ledger_account.principal_id IN (3, 4, 5, 6)",
            dependency_block,
        )

    def test_rollback_locks_dependencies_and_preserves_history(self) -> None:
        self.assertEqual(self.rollback.count("BEGIN;"), 1)
        self.assertEqual(self.rollback.count("COMMIT;"), 1)
        self.assertIn("IN SHARE ROW EXCLUSIVE MODE", self.rollback)
        for forbidden in (
            "DROP TABLE",
            "TRUNCATE",
            "CASCADE",
            "DELETE FROM public.user_monitor_",
            "DELETE FROM public.user_realtime_monitor_scope",
            "DELETE FROM public.n6_virtual_account",
            "DELETE FROM public.n6_virtual_trade_proposal",
            "DELETE FROM public.n6_virtual_order",
            "DELETE FROM public.n6_virtual_trade",
            "DELETE FROM public.n6_virtual_position",
            "DELETE FROM public.n6_virtual_position_lot",
        ):
            self.assertNotIn(forbidden.upper(), self.rollback.upper())

    def test_files_and_sql_contain_no_runtime_or_executor_activation(self) -> None:
        self.assertEqual(
            self.contract["file_allowlist"],
            [
                "sql/043_n6_btrack_legacy_principal_registration.sql",
                "sql/043_n6_btrack_legacy_principal_registration_rollback.sql",
                "tests/test_n6_btrack_principal_registration.py",
                "docs/N6_B_TRACK_PRODUCT_V3_LEGACY_PRINCIPAL_REGISTRATION_CONTRACT.json",
            ],
        )
        combined = self.migration + "\n" + self.rollback
        for pattern in (
            r"\bCREATE\s+(?:ROLE|USER)\b",
            r"\bCREATE\s+TABLE\b",
            r"\bGRANT\b",
            r"\bPASSWORD\b",
            r"\blaunchctl\b",
            r"\bexecutor\b",
            r"\bfeature[_ ]flags?\b",
            r"\.plist\b",
        ):
            self.assertIsNone(re.search(pattern, combined, re.IGNORECASE), pattern)


if __name__ == "__main__":
    unittest.main()
