import re
import unittest
from pathlib import Path


MIGRATION_PATH = Path("sql/023_market_data_subscription_canonical_v2_check_migration.sql")
ROLLBACK_PATH = Path("sql/023_market_data_subscription_canonical_v2_check_rollback.sql")

CONTROL_TABLES = (
    "common_market_data_subscription_candidate",
    "common_market_data_subscription",
)
CANONICAL_SIGNALS = ("BUY", "BUY:FULL", "SELL", "SELL:FULL", "BUY_HINT", "SELL_HINT")
LEGACY_SIGNALS = ("B_BUY", "S_SELL", "B_BUY_30M_VOL", "S_SELL_30M_SHRINK")


class MarketDataSubscriptionCanonicalV2MigrationTest(unittest.TestCase):
    def test_migration_only_updates_subscription_signal_check_constraints(self) -> None:
        sql = MIGRATION_PATH.read_text(encoding="utf-8")

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|CREATE\s+TABLE|DROP\s+TABLE|TRUNCATE)\b")
        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        for table in CONTROL_TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
        for signal in CANONICAL_SIGNALS + LEGACY_SIGNALS:
            self.assertIn(f"'{signal}'", sql)
        self.assertNotIn("common_event_outbox", sql)
        self.assertNotIn("stock_realtime_daily_snapshot", sql)

    def test_rollback_restores_legacy_check_with_canonical_guard(self) -> None:
        sql = ROLLBACK_PATH.read_text(encoding="utf-8")

        self.assertNotRegex(sql, r"\b(INSERT|UPDATE|DELETE|CREATE\s+TABLE|DROP\s+TABLE|TRUNCATE)\b")
        self.assertIn("RAISE EXCEPTION", sql)
        for table in CONTROL_TABLES:
            self.assertIn(f"ALTER TABLE {table}", sql)
        body = rollback_check_body(sql)
        for signal in LEGACY_SIGNALS + ("BUY_HINT", "SELL_HINT"):
            self.assertIn(f"'{signal}'", body)
        for signal in ("BUY", "BUY:FULL", "SELL", "SELL:FULL"):
            self.assertNotIn(f"'{signal}'", body)


def rollback_check_body(sql: str) -> str:
    match = re.search(r"-- Restore legacy CHECK constraints\.(.*)", sql, flags=re.DOTALL)
    return match.group(1) if match else sql


if __name__ == "__main__":
    unittest.main()
