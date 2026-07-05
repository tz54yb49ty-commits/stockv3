import unittest

from ashare_v3.market.action_confirmation_metric_20260608_unified_retry import (
    TARGET_METRIC_RUN_ID,
    derive_condition_signal_type,
    rollback_static_check,
    sanitize_static_rollback_comments,
)
from ashare_v3.market.action_confirmation_metric_materialization_execute import build_rollback_sql


class N3ActionConfirmationMetric20260608UnifiedRetryTests(unittest.TestCase):
    def test_condition_signal_type_derives_canonical_signal(self):
        self.assertEqual(derive_condition_signal_type("BUY:Y,M,W,D"), "BUY")
        self.assertEqual(derive_condition_signal_type("SELL:D"), "SELL")
        self.assertEqual(derive_condition_signal_type("BUY_HINT:30M"), "BUY_HINT")
        self.assertEqual(derive_condition_signal_type("SELL_HINT:D"), "SELL_HINT")
        self.assertEqual(derive_condition_signal_type("BUY:FULL:Y"), "BUY:FULL")
        self.assertEqual(derive_condition_signal_type("SELL:FULL:W"), "SELL:FULL")

    def test_rollback_static_check_uses_executable_delete_order(self):
        sql = sanitize_static_rollback_comments(
            build_rollback_sql(TARGET_METRIC_RUN_ID, label="20260608_until_1500_unified_output_retry")
        )
        check = rollback_static_check(sql)

        self.assertTrue(check["passed"], check)
        self.assertTrue(check["raise_exception_before_delete"])
        lower = sql.lower()
        for token in [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger_match",
            "common_action_event",
            "user_",
            "n6_",
            "worker_started",
            "downstream_layers_touched",
            "stock_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "board_action_confirmation_projection_metric",
            TARGET_METRIC_RUN_ID.lower(),
        ]:
            self.assertIn(token, lower)
        self.assertNotIn(" cascade", lower)
        self.assertNotIn("drop table", lower)
        self.assertNotIn("truncate", lower)


if __name__ == "__main__":
    unittest.main()
