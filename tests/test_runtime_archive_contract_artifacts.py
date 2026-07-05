import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RuntimeArchiveContractArtifactsTest(unittest.TestCase):
    def test_contract_and_preflight_are_readonly_and_use_macraid_cold_root(self) -> None:
        contract = json.loads((ROOT / "docs/V3_RUNTIME_ARCHIVE_CONTRACT.json").read_text(encoding="utf-8"))
        preflight = json.loads((ROOT / "docs/V3_RUNTIME_ARCHIVE_PREFLIGHT.json").read_text(encoding="utf-8"))

        self.assertEqual(contract["result"], "CONTRACT_PASS")
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(contract["archive_root"], "/Volumes/MacRaid/stock_db_archive/v3_runtime")
        self.assertEqual(contract["runtime_hot_database"], "local_ssd_postgresql")
        self.assertEqual(contract["cold_storage_role"], "macraid_parquet_archive_only")
        self.assertFalse(contract["side_effects"]["writes_database"])
        self.assertFalse(contract["side_effects"]["writes_archive_files"])
        self.assertFalse(contract["side_effects"]["cleanup_local_runtime"])
        self.assertEqual(preflight["P0"], 0)
        self.assertEqual(preflight["P1"], 0)
        self.assertEqual(preflight["P2"], 0)
        self.assertFalse(preflight["execute_authorized"])
        self.assertFalse(preflight["cleanup_authorized"])

    def test_cleanup_sql_hard_fails_before_delete_and_has_no_broad_destructive_tokens(self) -> None:
        sql = (ROOT / "sql/V3_runtime_archive_manual_cleanup_guard.sql").read_text(encoding="utf-8")
        upper = sql.upper()

        self.assertIn("RAISE EXCEPTION", upper)
        self.assertIn("ASHARE_V3.ALLOW_V3_RUNTIME_ARCHIVE_MANUAL_CLEANUP", upper)
        self.assertLess(upper.index("RAISE EXCEPTION"), upper.index("DELETE"))
        self.assertNotIn("TRUNCATE", upper)
        self.assertNotIn("DROP TABLE", upper)
        self.assertNotIn("CASCADE", upper)
        self.assertIn("TRADE_DATE", upper)
        self.assertIn("ARCHIVE_MANIFEST_VERIFIED", upper)

    def test_cleanup_sql_is_scoped_executable_after_verified_manifest(self) -> None:
        sql = (ROOT / "sql/V3_runtime_archive_manual_cleanup_guard.sql").read_text(encoding="utf-8")
        upper = sql.upper()

        self.assertNotIn("WHERE FALSE", upper)
        self.assertIn("STOCK_PREVIOUS_DAY_MINUTE_PRELOAD_STATUS", upper)
        self.assertIn("INDEX_PREVIOUS_DAY_MINUTE_PRELOAD_STATUS", upper)
        self.assertIn("BOARD_PREVIOUS_DAY_MINUTE_PRELOAD_STATUS", upper)
        self.assertIn("COMMON_EVENT_CONSUMER_CHECKPOINT", upper)
        self.assertIn("COMMON_EVENT_INBOX", upper)
        self.assertIn("COMMON_EVENT_OUTBOX", upper)
        self.assertIn("COMMON_MARKET_DATA_RUN", upper)
        self.assertIn("COMMON_TRIGGER_RUN", upper)
        self.assertIn("COMMON_ACTION_RUN", upper)

    def test_cleanup_sql_preserves_high_fanout_n3_lineage_metadata(self) -> None:
        sql = (ROOT / "sql/V3_runtime_archive_manual_cleanup_guard.sql").read_text(encoding="utf-8")
        upper = sql.upper()

        self.assertIn("N3 LINEAGE METADATA RETAINED", upper)
        self.assertNotIn("DELETE FROM COMMON_MARKET_DATA_SUBSCRIPTION\n", upper)
        self.assertNotIn("DELETE FROM COMMON_MARKET_DATA_RUN\n", upper)
        self.assertNotIn("DELETE FROM COMMON_MARKET_DATA_PULL_PLAN\n", upper)
        self.assertIn("COMMON_MARKET_DATA_SUBSCRIPTION", upper)
        self.assertIn("COMMON_MARKET_DATA_RUN", upper)

    def test_cleanup_performance_index_sql_covers_trigger_state_fk(self) -> None:
        sql = (ROOT / "sql/V3_runtime_archive_cleanup_performance_indexes.sql").read_text(encoding="utf-8")
        upper = sql.upper()

        self.assertIn("CREATE INDEX CONCURRENTLY IF NOT EXISTS", upper)
        self.assertIn("IDX_COMMON_TRIGGER_MATCH_TRIGGER_STATE_ID", upper)
        self.assertIn("COMMON_TRIGGER_MATCH", upper)
        self.assertIn("TRIGGER_STATE_ID", upper)
        self.assertNotIn("DROP", upper)
        self.assertNotIn("TRUNCATE", upper)
        self.assertNotIn("DELETE", upper)

    def test_cleanup_sql_blocks_recent_trade_date_without_explicit_override(self) -> None:
        sql = (ROOT / "sql/V3_runtime_archive_manual_cleanup_guard.sql").read_text(encoding="utf-8")
        upper = sql.upper()

        self.assertIn("ASHARE_V3.ALLOW_V3_RUNTIME_ARCHIVE_CLEANUP_RECENT_TRADE_DATE", upper)
        self.assertIn("RECENT_TRADE_DATES", upper)
        self.assertIn("COMMON_TRADE_CALENDAR", upper)
        self.assertIn("TODAY_PLUS_RECENT_5_TRADE_DAYS", upper)


if __name__ == "__main__":
    unittest.main()
