import unittest

from ashare_v3.market.action_confirmation_metric_20260608_scoped_repair import (
    METRIC_REPAIR_RUN_ID,
    PREVIOUS_DAY_REPAIR_RUN_ID,
    REPAIR_SUBSCRIPTION_RUN_ID,
    TODAY_MINUTE_REPAIR_RUN_ID,
    build_combined_rollback_sql,
    build_scoped_subscription_dry_run_report,
)


class N3ActionConfirmationMetric20260608CoverageRepairTests(unittest.TestCase):
    def test_scoped_subscription_report_plans_previous_and_today_minutes_only(self):
        scope_rows = [
            {
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "exchange": "SH",
                "code": "600000",
                "display_code": "600000.SH",
                "name": "sample stock",
                "source_scope_ids": [101, 102],
                "source_condition_pool_ids": [201, 202],
                "condition_keys": ["BUY:D"],
                "directions": ["buy"],
                "allowed_signal_types": ["BUY"],
                "source_trigger_match_ids": [1],
                "source_trigger_event_ids": ["evt_stock"],
            },
            {
                "asset_kind": "board",
                "identity_key": "board:TDX:881001",
                "exchange": "TDX",
                "code": "881001",
                "display_code": "881001",
                "name": "sample board",
                "source_scope_ids": [301],
                "source_condition_pool_ids": [401],
                "condition_keys": ["SELL:D"],
                "directions": ["sell"],
                "allowed_signal_types": ["SELL"],
                "source_trigger_match_ids": [2],
                "source_trigger_event_ids": ["evt_board"],
            },
        ]

        report = build_scoped_subscription_dry_run_report(scope_rows)

        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["market_data_run_id"], REPAIR_SUBSCRIPTION_RUN_ID)
        self.assertEqual(report["candidate_row_count"], 4)
        self.assertEqual(report["subscription_row_count"], 4)
        self.assertEqual(report["subscription_object_count"], 2)
        self.assertEqual(
            report["required_data_kind_counts"],
            {"minute_bar_1m": 2, "previous_day_minute_bar_1m": 2},
        )
        self.assertEqual(report["object_count_by_asset_kind"], {"stock": 1, "index": 0, "board": 1})
        self.assertEqual(report["market_data_pull_plan_row_count"], 4)
        self.assertTrue(report["passed"])
        self.assertFalse(report["blocked"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertFalse(report["side_effects"]["market_data_pulled"])
        self.assertFalse(report["side_effects"]["market_data_fact_written"])

    def test_combined_rollback_hard_fails_before_delete_and_scopes_all_repair_runs(self):
        sql = build_combined_rollback_sql()
        lower = sql.lower()

        self.assertIn("raise exception", lower)
        self.assertLess(lower.index("raise exception"), lower.index("delete"))
        for token in [
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "common_trigger",
            "common_action",
            "n6_",
            "user_",
            "worker_started",
            "downstream_layers_touched",
            "stock_minute_bar_1m",
            "index_minute_bar_1m",
            "board_minute_bar_1m",
            "stock_action_confirmation_projection_metric",
            "index_action_confirmation_projection_metric",
            "board_action_confirmation_projection_metric",
            "common_market_data_subscription_candidate",
            "common_market_data_subscription",
            "common_market_data_pull_plan",
            REPAIR_SUBSCRIPTION_RUN_ID.lower(),
            PREVIOUS_DAY_REPAIR_RUN_ID.lower(),
            TODAY_MINUTE_REPAIR_RUN_ID.lower(),
            METRIC_REPAIR_RUN_ID.lower(),
        ]:
            self.assertIn(token, lower)
        self.assertNotIn(" cascade", lower)
        self.assertNotIn("truncate", lower)
        self.assertNotIn("drop table", lower)


if __name__ == "__main__":
    unittest.main()
