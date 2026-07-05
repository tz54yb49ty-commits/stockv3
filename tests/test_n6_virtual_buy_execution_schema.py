import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "sql" / "B_TRACK_V2_virtual_buy_execution_schema.sql"
ROLLBACK_PATH = ROOT / "sql" / "B_TRACK_V2_virtual_buy_execution_schema_rollback.sql"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class N6VirtualBuyExecutionSchemaTest(unittest.TestCase):
    def test_schema_files_exist(self) -> None:
        self.assertTrue(MIGRATION_PATH.exists())
        self.assertTrue(ROLLBACK_PATH.exists())

    def test_migration_contains_required_columns_and_index(self) -> None:
        sql = _read(MIGRATION_PATH)
        required_tokens = [
            "BEGIN;",
            "COMMIT;",
            "ADD COLUMN IF NOT EXISTS idempotency_key TEXT",
            "ADD COLUMN IF NOT EXISTS source_message_key TEXT",
            "ADD COLUMN IF NOT EXISTS source_signal_identity_key TEXT",
            "ADD COLUMN IF NOT EXISTS source_condition_key TEXT",
            "ADD COLUMN IF NOT EXISTS source_event_time TIMESTAMPTZ",
            "ADD COLUMN IF NOT EXISTS source_for_trade_date TEXT",
            "ADD COLUMN IF NOT EXISTS source_json JSONB NOT NULL DEFAULT '{}'::JSONB",
            "ux_n6_virtual_order_principal_account_idempotency",
            "ON n6_virtual_order(principal_id, principal_type, virtual_account_id, idempotency_key)",
            "WHERE idempotency_key IS NOT NULL",
            "ADD COLUMN IF NOT EXISTS available_quantity_delta NUMERIC(24, 4) NOT NULL DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS locked_quantity_delta NUMERIC(24, 4) NOT NULL DEFAULT 0",
            "ADD COLUMN IF NOT EXISTS price NUMERIC(24, 6)",
            "ADD COLUMN IF NOT EXISTS trade_date INTEGER",
            "ADD COLUMN IF NOT EXISTS available_date INTEGER",
        ]
        for token in required_tokens:
            self.assertIn(token, sql)

    def test_migration_has_no_business_writes_or_forbidden_scope(self) -> None:
        sql = _read(MIGRATION_PATH).lower()
        forbidden_tokens = [
            "insert into",
            "update ",
            "delete from",
            "common_event_outbox",
            "n4_",
            "n5_",
            "real_trade",
            "worker",
            "initial_cash",
            "1000000",
            "10000000",
        ]
        for token in forbidden_tokens:
            self.assertNotIn(token, sql)

    def test_rollback_has_hard_fail_guards(self) -> None:
        sql = _read(ROLLBACK_PATH)
        lower = sql.lower()
        self.assertIn("BEGIN;", sql)
        self.assertIn("COMMIT;", sql)
        self.assertIn("RAISE EXCEPTION", sql)
        self.assertIn("idempotency_key IS NOT NULL", sql)
        self.assertIn("source_message_key IS NOT NULL", sql)
        self.assertIn("source_signal_identity_key IS NOT NULL", sql)
        self.assertIn("source_condition_key IS NOT NULL", sql)
        self.assertIn("source_event_time IS NOT NULL", sql)
        self.assertIn("source_for_trade_date IS NOT NULL", sql)
        self.assertIn("source_json <> '{}'::jsonb", sql)
        self.assertIn("available_quantity_delta <> 0", sql)
        self.assertIn("locked_quantity_delta <> 0", sql)
        self.assertIn("price IS NOT NULL", sql)
        self.assertIn("trade_date IS NOT NULL", sql)
        self.assertIn("available_date IS NOT NULL", sql)
        self.assertIn("drop index if exists ux_n6_virtual_order_principal_account_idempotency", lower)
        self.assertRegex(lower, r"alter\s+table\s+n6_virtual_order\s+drop\s+column")
        self.assertRegex(lower, r"alter\s+table\s+n6_virtual_position_event\s+drop\s+column")

    def test_rollback_drops_index_before_columns(self) -> None:
        sql = _read(ROLLBACK_PATH).lower()
        drop_index_pos = sql.find("drop index if exists ux_n6_virtual_order_principal_account_idempotency")
        first_drop_column_pos = sql.find("drop column")
        self.assertGreaterEqual(drop_index_pos, 0)
        self.assertGreaterEqual(first_drop_column_pos, 0)
        self.assertLess(drop_index_pos, first_drop_column_pos)

    def test_rollback_has_no_business_delete_update_or_seed_touch(self) -> None:
        sql = _read(ROLLBACK_PATH).lower()
        forbidden_patterns = [
            r"\binsert\s+into\b",
            r"\bupdate\s+",
            r"\bdelete\s+from\b",
            r"\btruncate\b",
            r"\bdrop\s+table\b",
            r"\bcascade\b",
            r"common_event_outbox",
            r"n4_",
            r"n5_",
            r"real_trade",
            r"worker",
            r"initial_cash",
            r"admin",
            r"1000000",
            r"10000000",
        ]
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, sql), pattern)


if __name__ == "__main__":
    unittest.main()
