import re
import unittest
from pathlib import Path


MIGRATION_PATH = Path("sql/022_condition_canonical_signal_check_migration.sql")
ROLLBACK_PATH = Path("sql/022_condition_canonical_signal_check_rollback.sql")

SIGNAL_TABLES = (
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
CANONICAL_SIGNALS = ("BUY", "BUY:FULL", "SELL", "SELL:FULL", "BUY_HINT", "SELL_HINT")
DEPRECATED_SIGNALS = ("B_BUY", "B_BUY_30M_VOL", "S_SELL", "S_SELL_30M_SHRINK")


class ConditionCanonicalSignalCheckMigrationTest(unittest.TestCase):
    def test_migration_is_compatible_check_only(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|CREATE\s+TABLE|DROP\s+TABLE)\b")
        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        for table in SIGNAL_TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
        for signal in CANONICAL_SIGNALS + DEPRECATED_SIGNALS:
            self.assertIn(f"'{signal}'", sql)

    def test_rollback_restores_legacy_check_with_guard(self) -> None:
        sql = ROLLBACK_PATH.read_text(encoding="utf-8")

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|CREATE\s+TABLE|DROP\s+TABLE)\b")
        self.assertIn("RAISE EXCEPTION", sql)
        for table in SIGNAL_TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
        for signal in DEPRECATED_SIGNALS + ("BUY_HINT", "SELL_HINT"):
            self.assertIn(f"'{signal}'", sql)
        for signal in ("BUY:FULL", "SELL:FULL"):
            self.assertNotIn(f"'{signal}'", rollback_check_body(sql))


def rollback_check_body(sql: str) -> str:
    match = re.search(r"-- Restore legacy CHECK constraints\.(.*)", sql, flags=re.DOTALL)
    return match.group(1) if match else sql


if __name__ == "__main__":
    unittest.main()
