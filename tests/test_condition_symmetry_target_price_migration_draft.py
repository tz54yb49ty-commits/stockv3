import json
import re
import unittest
from pathlib import Path


MIGRATION_PATH = Path("sql/027_condition_symmetry_target_price_compatibility_migration.sql")
ROLLBACK_PATH = Path("sql/027_condition_symmetry_target_price_compatibility_rollback.sql")
READINESS_PATH = Path("docs/N2_symmetry_target_price_canonical_compatibility_readiness.json")
SPEC_PATH = Path("docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md")

BASE_PRICE_POLICY_ENUM = "MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN"

N2_TARGET_TABLES = (
    "stock_condition_basis",
    "index_condition_basis",
    "board_condition_basis",
    "stock_condition_pool",
    "index_condition_pool",
    "board_condition_pool",
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
)

CANONICAL_FIELDS = (
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
)

FORBIDDEN_FIELDS = (
    "locked_target_price",
    "target_lock_status",
    "position_id",
    "action_id",
    "user_policy_hint",
)


class ConditionSymmetryTargetPriceMigrationDraftTest(unittest.TestCase):
    def test_migration_is_n2_schema_only_and_nullable(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        executable_sql = strip_sql_comments(sql)

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertNotRegex(executable_sql, r"\b(INSERT|UPDATE|DELETE|CREATE\s+TABLE|DROP\s+TABLE)\b")
        for table in N2_TARGET_TABLES:
            self.assertIn(f"'{table}'", sql)
        for field in CANONICAL_FIELDS:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {field}", sql)
        for forbidden in FORBIDDEN_FIELDS:
            self.assertNotIn(forbidden, executable_sql)

    def test_migration_constraints_match_canonical_compatibility_contract(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")

        for field in ("symmetry_anchor", "secondary_symmetry_anchor", "amplitude_source_period"):
            self.assertIn(f"{field} IS NULL OR {field} IN (''Y'', ''Q'', ''M'', ''W'')", sql)
        self.assertIn(BASE_PRICE_POLICY_ENUM, sql)
        for field in (
            "a_segment_high",
            "a_segment_low",
            "a_segment_amplitude",
            "base_price",
            "reference_target_price",
            "secondary_target_price",
        ):
            self.assertIn(f"{field} IS NULL OR {field} >= 0", sql)
        self.assertIn("target_price_trace_json IS NULL OR jsonb_typeof(target_price_trace_json) = ''object''", sql)

    def test_rollback_only_removes_027_columns_and_constraints(self) -> None:
        sql = ROLLBACK_PATH.read_text(encoding="utf-8")
        executable_sql = strip_sql_comments(sql)

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertNotRegex(executable_sql, r"\b(INSERT|UPDATE|DELETE|CREATE\s+TABLE)\b")
        for table in N2_TARGET_TABLES:
            self.assertIn(f"'{table}'", sql)
        for field in CANONICAL_FIELDS:
            self.assertIn(f"DROP COLUMN IF EXISTS {field}", sql)
        for forbidden in FORBIDDEN_FIELDS:
            self.assertNotIn(forbidden, sql)

    def test_readiness_documents_no_migration_compatibility_and_blockers(self) -> None:
        readiness = json.loads(READINESS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(readiness["status"], "DRAFT_PASS")
        self.assertEqual(readiness["layer_role"], "N2_condition")
        self.assertFalse(readiness["ready_to_execute_migration"])
        self.assertTrue(readiness["no_migration_compatibility"]["available"])
        self.assertEqual(
            readiness["no_migration_compatibility"]["clear_sell_ref_period_alias"],
            "up_sell_reference_period",
        )
        self.assertIn("user_confirmation_required_before_execute", readiness["remaining_blockers"])
        self.assertNotIn(
            "base_price_policy_enum_needs_reconciliation_with_frozen_spec_if_docs_are_not_updated",
            readiness["remaining_blockers"],
        )
        self.assertTrue(readiness["constraints"]["base_price_policy_enum_reconciled_with_spec"])
        self.assertFalse(readiness["constraints"]["legacy_reference_body_boundary_is_db_enum"])
        self.assertEqual(readiness["migration_scope"], list(N2_TARGET_TABLES))
        self.assertEqual(readiness["new_nullable_fields"], list(CANONICAL_FIELDS))

    def test_spec_freezes_same_base_price_policy_enum_as_migration(self) -> None:
        spec = SPEC_PATH.read_text(encoding="utf-8")
        sql = MIGRATION_PATH.read_text(encoding="utf-8")

        self.assertIn(f"base_price_policy = {BASE_PRICE_POLICY_ENUM}", spec)
        self.assertIn(f"base_price_policy = ''{BASE_PRICE_POLICY_ENUM}''", sql)
        self.assertNotIn("base_price_policy = reference_body_boundary", spec)
        self.assertIn("not a canonical", spec)

    def test_no_n4_n5_schema_names_are_modified(self) -> None:
        combined = "\n".join(
            (
                MIGRATION_PATH.read_text(encoding="utf-8"),
                ROLLBACK_PATH.read_text(encoding="utf-8"),
            )
        )

        self.assertIsNone(re.search(r"\b(common_trigger_|stock_trigger_|index_trigger_|board_trigger_)", combined))
        self.assertIsNone(re.search(r"\b(common_action_|stock_action_|index_action_|board_action_)", combined))


def strip_sql_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


if __name__ == "__main__":
    unittest.main()
