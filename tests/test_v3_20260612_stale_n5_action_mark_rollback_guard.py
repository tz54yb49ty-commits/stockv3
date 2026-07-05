from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SQL = ROOT / "sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql"
DEFAULT_CONSUMER = "n5_action_consumer_v1"
WRAPPER_CONSUMER = "v3_realtime_engine_n5_consumer_20260612"


def _without_line_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def _first_delete_or_update(sql: str) -> int:
    cleaned = _without_line_comments(sql).lower()
    matches = [m.start() for m in re.finditer(r"\b(delete|update)\s+", cleaned)]
    return min(matches) if matches else -1


class V320260612StaleN5ActionMarkRollbackGuardTest(unittest.TestCase):
    def test_hard_fail_guard_still_runs_before_first_destructive_statement(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")
        cleaned = _without_line_comments(sql).lower()

        first_destructive = _first_delete_or_update(sql)
        self.assertGreaterEqual(first_destructive, 0)
        first_raise = cleaned.find("raise exception")
        self.assertGreaterEqual(first_raise, 0)
        self.assertLess(first_raise, first_destructive)

    def test_preserved_n4_non_scoped_checkpoint_refs_do_not_block(self) -> None:
        sql = _without_line_comments(ROLLBACK_SQL.read_text(encoding="utf-8")).lower()

        self.assertNotIn("non-scoped consumer checkpoint refs exist for source_trigger_run_id", sql)
        checkpoint_blocks = re.findall(
            r"from\s+common_event_consumer_checkpoint[\s\S]*?(?:;|if\s+v_count\s+>\s+0\s+then)",
            sql,
        )
        self.assertTrue(checkpoint_blocks)
        for block in checkpoint_blocks:
            if "source_layer = 'n4_trigger'" in block:
                self.assertNotIn("consumer_name <>", block)

    def test_rollback_scope_includes_reviewed_stale_consumers_for_scoped_n4_source(self) -> None:
        sql = _without_line_comments(ROLLBACK_SQL.read_text(encoding="utf-8")).lower()

        self.assertIn(DEFAULT_CONSUMER, sql)
        self.assertIn(WRAPPER_CONSUMER, sql)
        self.assertIn("stale_consumer_names", sql)
        self.assertIn("consumer_name = any", sql)

    def test_checkpoint_delete_scope_remains_stale_consumers_for_scoped_n4_source(self) -> None:
        sql = _without_line_comments(ROLLBACK_SQL.read_text(encoding="utf-8")).lower()

        self.assertIn("delete from common_event_consumer_checkpoint", sql)
        self.assertIn("consumer_name = any", sql)
        self.assertIn("source_layer = 'n4_trigger'", sql)
        self.assertIn("source_run_id = :'source_trigger_run_id'", sql)
        self.assertIn("partition_key in (select partition_key from scoped_partitions)", sql)

    def test_n5_downstream_and_user_layer_guards_remain(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8").lower()

        self.assertIn("scoped n5 outbox has delivered/delivering rows", sql)
        self.assertIn("scoped n5 outbox has downstream inbox refs", sql)
        self.assertIn("scoped n5 outbox has downstream checkpoint refs", sql)
        for table_name in (
            "user_projection_run",
            "user_signal_projection",
            "user_notification_queue",
            "user_voice_delivery",
            "mobile_projection",
            "sim_projection",
            "common_position_state",
            "common_position_event",
        ):
            self.assertIn(table_name, sql)

    def test_rollback_does_not_delete_n4_n3_or_downstream_business_facts(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8").lower()

        forbidden = (
            "delete from common_trigger",
            "delete from stock_trigger",
            "delete from index_trigger",
            "delete from board_trigger",
            "delete from common_market_data",
            "delete from stock_action_confirmation_projection_metric",
            "delete from index_action_confirmation_projection_metric",
            "delete from board_action_confirmation_projection_metric",
            "delete from user_signal_projection",
            "delete from user_notification_queue",
            "delete from common_position_state",
            "drop table",
            "truncate",
            " cascade",
        )
        for snippet in forbidden:
            self.assertNotIn(snippet, sql)


if __name__ == "__main__":
    unittest.main()
