import re
import unittest
from pathlib import Path


MIGRATION_PATH = Path("sql/030_condition_symmetry_secondary_anchor_columns_migration.sql")
ROLLBACK_PATH = Path("sql/030_condition_symmetry_secondary_anchor_columns_rollback.sql")

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

SECONDARY_FIELDS = (
    "up_secondary_anchor",
    "up_secondary_reference_period",
    "up_secondary_trend_start_date",
    "up_secondary_trend_end_date",
    "up_secondary_amplitude",
    "up_secondary_base_price",
    "up_secondary_target_price",
    "up_secondary_expected_return_pct",
    "down_secondary_anchor",
    "down_secondary_reference_period",
    "down_secondary_trend_start_date",
    "down_secondary_trend_end_date",
    "down_secondary_amplitude",
    "down_secondary_base_price",
    "down_secondary_target_price",
    "down_secondary_expected_return_pct",
)

FORBIDDEN_FIELDS = (
    "locked_target_price",
    "target_lock_status",
    "position_id",
    "action_id",
    "user_policy_hint",
)


class ConditionSymmetrySecondaryAnchorMigrationDraftTest(unittest.TestCase):
    def test_migration_is_additive_nullable_n2_only(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")
        executable_sql = strip_sql_comments(sql)

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertNotRegex(executable_sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY|CREATE\s+TABLE|DROP\s+TABLE)\b")
        for table in N2_TARGET_TABLES:
            self.assertIn(f"'{table}'", sql)
        for field in SECONDARY_FIELDS:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {field}", sql)
        for forbidden in FORBIDDEN_FIELDS:
            self.assertNotIn(forbidden, executable_sql)

    def test_migration_constraints_cover_anchor_reference_date_and_nonnegative_numeric_fields(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")

        self.assertIn("up_secondary_anchor IS NULL OR up_secondary_anchor IN (''Y'', ''Q'', ''M'', ''W'')", sql)
        self.assertIn("down_secondary_anchor IS NULL OR down_secondary_anchor IN (''Y'', ''Q'', ''M'', ''W'')", sql)
        self.assertIn("up_secondary_reference_period IS NULL OR up_secondary_reference_period IN (''Q'', ''M'', ''W'', ''D'')", sql)
        self.assertIn("down_secondary_reference_period IS NULL OR down_secondary_reference_period IN (''Q'', ''M'', ''W'', ''D'')", sql)
        self.assertIn("up_secondary_trend_start_date", sql)
        self.assertIn("down_secondary_trend_end_date", sql)
        for field in (
            "up_secondary_amplitude",
            "up_secondary_base_price",
            "up_secondary_target_price",
            "down_secondary_amplitude",
            "down_secondary_base_price",
            "down_secondary_target_price",
        ):
            self.assertIn(field, sql)
            self.assertIn("%I IS NULL OR %I >= 0", sql)

    def test_rollback_only_drops_030_columns_and_constraints(self) -> None:
        sql = ROLLBACK_PATH.read_text(encoding="utf-8")
        executable_sql = strip_sql_comments(sql)

        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertNotRegex(executable_sql, r"\b(INSERT|UPDATE|DELETE|TRUNCATE|COPY|CREATE\s+TABLE)\b")
        for table in N2_TARGET_TABLES:
            self.assertIn(f"'{table}'", sql)
        for field in SECONDARY_FIELDS:
            self.assertIn(f"DROP COLUMN IF EXISTS {field}", sql)
        for forbidden in FORBIDDEN_FIELDS:
            self.assertNotIn(forbidden, sql)

    def test_no_downstream_schema_names_are_modified(self) -> None:
        combined = "\n".join(
            (
                MIGRATION_PATH.read_text(encoding="utf-8"),
                ROLLBACK_PATH.read_text(encoding="utf-8"),
            )
        )

        self.assertIsNone(re.search(r"\b(common_trigger_|stock_trigger_|index_trigger_|board_trigger_)", combined))
        self.assertIsNone(re.search(r"\b(common_action_|stock_action_|index_action_|board_action_)", combined))
        self.assertIsNone(re.search(r"\b(user_projection_|user_signal_projection|user_card_)", combined))


def strip_sql_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))


if __name__ == "__main__":
    unittest.main()
