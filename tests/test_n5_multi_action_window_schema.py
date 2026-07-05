from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_SQL = ROOT / "sql" / "N5_multi_action_window_fact_grain_migration.sql"
ROLLBACK_SQL = ROOT / "sql" / "N5_multi_action_window_fact_grain_rollback.sql"

ACTION_FACT_TABLES = (
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class N5MultiActionWindowSchemaTest(unittest.TestCase):
    def test_migration_drops_old_unique_grain_and_adds_nonunique_lookup_indexes(self) -> None:
        sql = _read(MIGRATION_SQL)
        lowered = sql.lower()

        for table in ACTION_FACT_TABLES:
            with self.subTest(table=table):
                old_constraint = f"{table}_run_id_source_trigger_event_id_action_typ_key"
                self.assertIn(f"alter table public.{table}", lowered)
                self.assertIn(f"drop constraint if exists {old_constraint}", lowered)
                self.assertIn(f"create index if not exists idx_{table}_source_trigger_action_lookup", lowered)
                self.assertIn(
                    f"on public.{table} (run_id, source_trigger_event_id, action_type)",
                    lowered,
                )
                self.assertNotRegex(
                    lowered,
                    rf"create\s+unique\s+index[^\n]+idx_{table}_source_trigger_action_lookup",
                )

        self.assertIn("multi action window", lowered)
        for table in ("common_action_event", "common_event_outbox", "common_action_tracking_state"):
            with self.subTest(non_target_table=table):
                self.assertNotRegex(lowered, rf"alter\s+table\s+public\.{table}\b")
                self.assertNotRegex(lowered, rf"create\s+(unique\s+)?index[^\n]+on\s+public\.{table}\b")
                self.assertNotRegex(lowered, rf"drop\s+(index|constraint|table)[^\n]+{table}\b")

    def test_migration_keeps_action_key_and_dedup_key_uniques(self) -> None:
        sql = _read(MIGRATION_SQL).lower()

        for table in ACTION_FACT_TABLES:
            with self.subTest(table=table):
                self.assertNotIn(f"drop constraint if exists {table}_run_id_action_key_key", sql)
                self.assertNotIn(f"drop constraint if exists {table}_run_id_dedup_key_key", sql)
                self.assertIn(f"{table}_run_id_action_key_key", sql)
                self.assertIn(f"{table}_run_id_dedup_key_key", sql)

    def test_rollback_has_duplicate_guard_before_restoring_unique_constraints(self) -> None:
        sql = _read(ROLLBACK_SQL)
        lowered = sql.lower()

        for table in ACTION_FACT_TABLES:
            with self.subTest(table=table):
                old_constraint = f"{table}_run_id_source_trigger_event_id_action_typ_key"
                self.assertIn(f"drop index if exists public.idx_{table}_source_trigger_action_lookup", lowered)
                self.assertIn(f"alter table public.{table}", lowered)
                self.assertIn(f"add constraint {old_constraint}", lowered)
                self.assertIn("group by run_id, source_trigger_event_id, action_type", lowered)
                self.assertRegex(
                    lowered,
                    rf"(?s)if\s+exists\s*\(.*?from\s+public\.{table}.*?having\s+count\(\*\)\s*>\s*1",
                )

        self.assertIn("raise exception", lowered)
        self.assertIn("rollback blocked", lowered)
        self.assertNotIn("delete from", lowered)


if __name__ == "__main__":
    unittest.main()
