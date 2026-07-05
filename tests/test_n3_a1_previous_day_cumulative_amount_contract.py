from pathlib import Path
import re
import unittest


MIGRATION_SQL = Path("sql/N3_A1_previous_day_minute_cumulative_schema.sql")
ROLLBACK_SQL = Path("sql/N3_A1_previous_day_minute_cumulative_schema_rollback.sql")

ASSETS = ("stock", "index", "board")
TABLES = tuple(f"{asset}_previous_day_minute_cumulative" for asset in ASSETS)
FORBIDDEN_SQL_TOKENS = (
    "INSERT ",
    "UPDATE ",
    "DELETE ",
    "TRUNCATE ",
    "COMMON_EVENT_OUTBOX",
    "COMMON_EVENT_INBOX",
    "COMMON_EVENT_CONSUMER_CHECKPOINT",
    "COMMON_TRIGGER_RUN",
    "COMMON_ACTION_RUN",
)


def _normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


class N3A1PreviousDayCumulativeAmountContractTest(unittest.TestCase):
    def test_migration_creates_only_physical_cumulative_tables_and_indexes(self) -> None:
        sql = MIGRATION_SQL.read_text()
        upper = sql.upper()

        for forbidden in FORBIDDEN_SQL_TOKENS:
            self.assertNotIn(forbidden, upper)
        self.assertNotIn("DROP TABLE", upper)
        self.assertNotIn("ALTER TABLE", upper)

        for table in TABLES:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
            self.assertIn("cumulative_id TEXT PRIMARY KEY", sql)
            self.assertIn("source_previous_day_minute_run_id TEXT NOT NULL", sql)
            self.assertIn("for_trade_date TEXT NOT NULL", sql)
            self.assertIn("source_trade_date TEXT NOT NULL", sql)
            self.assertIn("canonical_minute_label TEXT NOT NULL", sql)
            self.assertIn("canonical_bar_time TIMESTAMPTZ NOT NULL", sql)
            self.assertIn("raw_bar_time TIMESTAMPTZ NOT NULL", sql)
            self.assertIn("cumulative_amount_yuan NUMERIC NOT NULL", sql)
            self.assertIn("full_day_amount_yuan NUMERIC NOT NULL", sql)
            self.assertIn(f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_source_identity_minute_uidx", sql)
            self.assertIn("(source_previous_day_minute_run_id, identity_key, canonical_minute_label)", sql)
            self.assertIn(f"COMMENT ON TABLE {table}", sql)

    def test_stock_index_board_migration_blocks_are_symmetric_except_table_name(self) -> None:
        sql = MIGRATION_SQL.read_text()
        blocks = []
        for table in TABLES:
            start = sql.index(f"CREATE TABLE IF NOT EXISTS {table}")
            end = sql.index(f"COMMENT ON TABLE {table}", start)
            block = sql[start:end].replace(table, "<table>")
            blocks.append(_normalize(block))

        self.assertEqual(blocks[0], blocks[1])
        self.assertEqual(blocks[1], blocks[2])

    def test_rollback_drops_only_new_cumulative_objects(self) -> None:
        sql = ROLLBACK_SQL.read_text()
        upper = sql.upper()

        for forbidden in FORBIDDEN_SQL_TOKENS:
            self.assertNotIn(forbidden, upper)
        for table in TABLES:
            self.assertIn(f"DROP INDEX IF EXISTS {table}_source_identity_minute_uidx;", sql)
            self.assertIn(f"DROP TABLE IF EXISTS {table};", sql)
        self.assertNotIn("common_market_data_run", sql)
        self.assertNotIn("previous_day_minute_preload_status", sql)


if __name__ == "__main__":
    unittest.main()
