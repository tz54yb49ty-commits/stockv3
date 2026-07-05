import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SQL = ROOT / "sql/N3_20260611_B1_market_snapshot_updated_standard_outbox_rollback.sql"


class N3B120260611StandardOutboxRollbackHardFailTest(unittest.TestCase):
    def test_default_hard_fail_is_executable_before_first_delete_or_update(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")
        lowered = sql.lower()
        first_delete = lowered.find("delete from")
        first_update = lowered.find("update ")
        first_dml = min(index for index in [first_delete, first_update] if index >= 0)
        default_marker = lowered.find("rollback blocked by default")

        self.assertNotIn("default hard-fail removed", lowered)
        self.assertGreaterEqual(default_marker, 0)
        self.assertLess(default_marker, first_dml)
        self.assertLess(lowered.find("raise exception", default_marker), first_dml)

    def test_delete_scope_stays_scoped_and_forbidden_ddl_absent(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")
        lowered = sql.lower()

        self.assertIn("delete from common_event_outbox", lowered)
        self.assertIn("delete from stock_realtime_daily_snapshot", lowered)
        self.assertIn("delete from index_realtime_daily_snapshot", lowered)
        self.assertIn("delete from board_realtime_daily_snapshot", lowered)
        self.assertIn("delete from common_market_data_quality_item", lowered)
        self.assertIn("delete from common_market_data_run", lowered)
        self.assertIn("run_id = 'realtime_daily_snapshot_20260611_standard_outbox__", lowered)
        self.assertNotIn("drop ", lowered)
        self.assertNotIn("truncate ", lowered)
        self.assertNotIn("cascade", lowered)


if __name__ == "__main__":
    unittest.main()
