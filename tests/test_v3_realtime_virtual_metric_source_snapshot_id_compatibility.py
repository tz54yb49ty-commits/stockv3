import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_SQL = ROOT / "sql/V3_realtime_virtual_metric_source_snapshot_id_nullable_compatibility.sql"
ROLLBACK_SQL = ROOT / "sql/V3_realtime_virtual_metric_source_snapshot_id_nullable_compatibility_rollback.sql"


class V3RealtimeVirtualMetricSourceSnapshotIdCompatibilityTest(unittest.TestCase):
    def test_migration_drops_source_snapshot_id_not_null_without_dropping_fk(self) -> None:
        sql = MIGRATION_SQL.read_text()

        for table in (
            "stock_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "board_action_confirmation_projection_metric",
        ):
            self.assertIn(f"ALTER TABLE {table}", sql)
            self.assertIn("ALTER COLUMN source_snapshot_id DROP NOT NULL", sql)
            self.assertIn("source_snapshot_id nullable for minute-source realtime virtual metrics", sql)

        self.assertNotIn("DROP CONSTRAINT", sql)
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("TRUNCATE", sql)
        self.assertNotIn("DELETE", sql)
        self.assertNotIn("CASCADE", sql)

    def test_rollback_hard_fails_before_restoring_not_null(self) -> None:
        rollback = ROLLBACK_SQL.read_text()

        first_raise = rollback.index("RAISE EXCEPTION")
        first_alter = rollback.index("ALTER TABLE")
        self.assertLess(first_raise, first_alter)
        self.assertIn("source_snapshot_id nullable compatibility rollback blocked by default", rollback)
        self.assertIn("source_snapshot_id IS NULL", rollback)
        self.assertIn("ALTER COLUMN source_snapshot_id SET NOT NULL", rollback)
        self.assertNotIn("DROP TABLE", rollback)
        self.assertNotIn("TRUNCATE", rollback)
        self.assertNotIn("CASCADE", rollback)


if __name__ == "__main__":
    unittest.main()
