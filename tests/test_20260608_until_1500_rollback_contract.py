from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]

ROLLBACK_FILES = {
    "n3_c1": ROOT / "sql/N3_C1_today_minute_bar_1m_20260608_until_1500_rollback.sql",
    "n3_b2": ROOT / "sql/N3_B2_realtime_projection_20260608_v13_index_all_until_1500_rollback.sql",
    "n4": ROOT / "sql/N4_projection_matcher_20260608_v13_index_all_until_1500_v4_repair_retry_rollback.sql",
    "n3_metric": ROOT / "sql/N3_action_confirmation_metric_20260608_until_1500_rollback.sql",
    "n5": ROOT / "sql/N5_action_confirmation_20260608_until_1500_metric_aware_retry_rollback.sql",
    "n6": ROOT / "sql/N6_projection_20260608_until_1500_metric_aware_retry_rollback.sql",
}


def _without_line_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def _first_executable_delete_or_update(sql: str) -> int:
    cleaned = _without_line_comments(sql).lower()
    matches = [m.start() for m in re.finditer(r"\b(delete|update)\s+", cleaned)]
    return min(matches) if matches else -1


class RollbackContract20260608Until1500Test(unittest.TestCase):
    def test_scoped_rollbacks_hard_fail_before_delete_or_update(self) -> None:
        for name, path in ROLLBACK_FILES.items():
            with self.subTest(name=name):
                sql = path.read_text(encoding="utf-8")
                cleaned = _without_line_comments(sql).lower()
                first_destructive = _first_executable_delete_or_update(sql)
                self.assertGreaterEqual(first_destructive, 0)
                first_raise = cleaned.find("raise exception")
                self.assertGreaterEqual(first_raise, 0)
                self.assertLess(first_raise, first_destructive)

    def test_scoped_rollbacks_guard_delivered_or_delivering_outbox(self) -> None:
        for name, path in ROLLBACK_FILES.items():
            with self.subTest(name=name):
                sql = path.read_text(encoding="utf-8").lower()
                self.assertIn("common_event_outbox", sql)
                self.assertIn("delivering", sql)
                self.assertIn("delivered", sql)
                self.assertIn("status in", sql)

    def test_scoped_rollbacks_guard_downstream_refs_and_forbid_broad_destructive_sql(self) -> None:
        for name, path in ROLLBACK_FILES.items():
            with self.subTest(name=name):
                sql = path.read_text(encoding="utf-8").lower()
                self.assertIn("20260608", sql)
                self.assertTrue(
                    any(
                        marker in sql
                        for marker in (
                            "downstream",
                            "user_signal_projection",
                            "user_signal_card",
                            "user_notification_queue",
                            "common_action",
                            "common_trigger",
                            "n6_virtual",
                        )
                    )
                )
                self.assertNotIn(" cascade", sql)
                self.assertNotIn("drop table", sql)
                self.assertNotIn("truncate", sql)


if __name__ == "__main__":
    unittest.main()
