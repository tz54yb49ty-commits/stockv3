import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_SQL = PROJECT_ROOT / "sql" / "015_condition_run_passed_active_status_migration.sql"
ROLLBACK_SQL = PROJECT_ROOT / "sql" / "015_condition_run_passed_active_status_rollback.sql"


class ConditionActiveStatusMigrationTest(unittest.TestCase):
    def test_migration_adds_passed_active_status_and_unique_canonical_active_index(self) -> None:
        sql = MIGRATION_SQL.read_text(encoding="utf-8")

        self.assertIn("passed_active", sql)
        self.assertIn("common_condition_run_status_check", sql)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS", sql)
        self.assertIn("WHERE status = 'passed_active'", sql)
        self.assertNotIn("UPDATE common_condition_run", sql)
        self.assertNotIn("DELETE FROM common_condition_run", sql)
        self.assertNotIn("INSERT INTO common_condition_run", sql)

    def test_rollback_guards_existing_passed_active_rows_before_reverting_check(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")

        self.assertIn("passed_active", sql)
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertIn("DROP INDEX IF EXISTS", sql)
        self.assertIn("common_condition_run_status_check", sql)
        self.assertNotIn("UPDATE common_condition_run", sql)
        self.assertNotIn("DELETE FROM common_condition_run", sql)
        self.assertNotIn("INSERT INTO common_condition_run", sql)


if __name__ == "__main__":
    unittest.main()
