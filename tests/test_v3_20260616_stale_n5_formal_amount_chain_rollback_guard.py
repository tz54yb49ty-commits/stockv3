from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ROLLBACK_SQL = ROOT / "sql/V3_20260616_n5_action_after_n4_trigger_price_repair_rollback.sql"
ACTION_RUN_ID = "v3_n5_action_replay_20260616_after_n4_trigger_price_repair_v1"
SOURCE_TRIGGER_RUN_ID = "v3_n4_trigger_replay_20260616_until_1401_v1"
CONSUMER_NAME = "n5_action_consumer_v1_20260616_trigger_price_repair_replay"


def _without_line_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def _first_delete_or_update(sql: str) -> int:
    cleaned = _without_line_comments(sql).lower()
    matches = [m.start() for m in re.finditer(r"\b(delete|update)\s+", cleaned)]
    return min(matches) if matches else -1


class V320260616StaleN5FormalAmountChainRollbackGuardTest(unittest.TestCase):
    def test_scope_constants_are_the_reviewed_20260616_n5_run(self) -> None:
        sql = ROLLBACK_SQL.read_text(encoding="utf-8")

        self.assertIn(ACTION_RUN_ID, sql)
        self.assertIn(SOURCE_TRIGGER_RUN_ID, sql)
        self.assertIn(CONSUMER_NAME, sql)

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

    def test_checkpoint_delete_scope_remains_dedicated_consumer_only(self) -> None:
        sql = _without_line_comments(ROLLBACK_SQL.read_text(encoding="utf-8")).lower()

        self.assertIn("delete from common_event_consumer_checkpoint", sql)
        self.assertIn("consumer_name = :'consumer_name'", sql)
        self.assertIn("source_layer = 'n4_trigger'", sql)
        self.assertIn("source_run_id = :'source_trigger_run_id'", sql)
        self.assertIn("partition_key in (select partition_key from scoped_partitions)", sql)
        self.assertNotIn("delete from common_event_consumer_checkpoint\nwhere source_layer = 'n4_trigger'", sql)

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
