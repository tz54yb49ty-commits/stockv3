from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SQL = ROOT / "sql" / "N2_condition_layer_20260602_rollback.sql"


def _strip_line_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


class Condition20260602RollbackHardeningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sql = ROLLBACK_SQL.read_text(encoding="utf-8")
        self.executable_sql = _strip_line_comments(self.sql)
        self.before_first_delete = self.executable_sql.split("DELETE FROM", 1)[0]

    def test_event_infra_guards_exist_before_first_delete(self) -> None:
        for table_name in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        ):
            with self.subTest(table_name=table_name):
                self.assertIn(table_name, self.before_first_delete)

        self.assertIn("RAISE EXCEPTION", self.before_first_delete)
        self.assertRegex(
            self.before_first_delete,
            r"event infra refs exist|outbox.*refs|inbox.*refs|checkpoint.*refs",
        )

    def test_event_infra_tables_are_not_deleted_or_updated(self) -> None:
        for table_name in (
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        ):
            with self.subTest(table_name=table_name):
                self.assertNotRegex(
                    self.executable_sql,
                    rf"\b(DELETE|UPDATE|INSERT)\s+(?:INTO\s+|FROM\s+)?{re.escape(table_name)}\b",
                )

    def test_n2_delete_scope_remains_run_id_only(self) -> None:
        self.assertIn("condition_layer_20260602_source_20260602_v1", self.executable_sql)
        self.assertIn("DELETE FROM stock_condition_basis", self.executable_sql)
        self.assertIn("DELETE FROM common_condition_run", self.executable_sql)
        self.assertNotIn("stock_daily_bar_fact", self.executable_sql)
        self.assertNotIn("common_active_source_version", self.executable_sql)


if __name__ == "__main__":
    unittest.main()
