import json
import unittest

from ashare_v3.market.closed_30m_replay_plan import (
    bucket_definitions,
    build_closed_summary_plan,
    build_delta_plan,
    build_full_day_minute_labels,
    build_replay_dry_run_report,
    build_write_scope_contract,
    identify_bj_missing_candidates,
)


class Closed30mReplayPlanTests(unittest.TestCase):
    def test_bucket_rule_has_eight_30m_windows(self) -> None:
        buckets = bucket_definitions()

        self.assertEqual(
            [bucket["bucket_id"] for bucket in buckets],
            [
                "0931_1000",
                "1001_1030",
                "1031_1100",
                "1101_1130",
                "1301_1330",
                "1331_1400",
                "1401_1430",
                "1431_1500",
            ],
        )
        self.assertTrue(all(len(bucket["labels"]) == 30 for bucket in buckets))
        self.assertEqual(len(build_full_day_minute_labels()), 240)

    def test_c1_latest_1411_gap_estimate(self) -> None:
        delta_plan = build_delta_plan(
            latest_closed_label="14:11",
            object_counts_by_asset={"stock": 2052, "index": 9, "board": 127},
            bj_missing_count=9,
        )

        self.assertEqual(delta_plan["main_gap"]["from_label"], "14:12")
        self.assertEqual(delta_plan["main_gap"]["to_label"], "15:00")
        self.assertEqual(delta_plan["main_gap"]["label_count"], 49)
        self.assertEqual(delta_plan["main_gap"]["available_non_bj_objects"], 2179)
        self.assertEqual(delta_plan["delta_minute_rows_estimate"], 106771)
        self.assertEqual(delta_plan["bj_retry_capacity"]["estimated_rows_if_available"], 2160)
        self.assertTrue(delta_plan["replay_diff_check_required"])

    def test_closed_summary_status_counts_with_bj_missing(self) -> None:
        summary_plan = build_closed_summary_plan(
            latest_closed_label="14:11",
            object_counts_by_asset={"stock": 2052, "index": 9, "board": 127},
            missing_candidate_counts_by_asset={"stock": 9, "index": 0, "board": 0},
        )

        self.assertEqual(summary_plan["expected_summary_rows"]["total"], 17504)
        self.assertEqual(summary_plan["status_counts"]["closed"], 13074)
        self.assertEqual(summary_plan["status_counts"]["partial"], 2179)
        self.assertEqual(summary_plan["status_counts"]["missing"], 2251)
        self.assertEqual(summary_plan["status_counts_by_asset"]["stock"]["missing"], 2115)
        self.assertEqual(summary_plan["status_counts_by_asset"]["board"]["partial"], 127)
        self.assertEqual(summary_plan["status_counts_by_asset"]["board"]["missing"], 127)

    def test_identifies_bj_missing_candidates(self) -> None:
        subscriptions = [
            {"asset_kind": "stock", "identity_key": "stock:BJ:920001", "exchange": "BJ", "code": "920001"},
            {"asset_kind": "stock", "identity_key": "stock:SH:600000", "exchange": "SH", "code": "600000"},
            {"asset_kind": "board", "identity_key": "board:TDX:881001", "exchange": "TDX", "code": "881001"},
        ]
        baseline_counts = {
            "stock:BJ:920001": 0,
            "stock:SH:600000": 191,
            "board:TDX:881001": 191,
        }

        candidates = identify_bj_missing_candidates(subscriptions, baseline_counts)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["identity_key"], "stock:BJ:920001")
        self.assertEqual(candidates[0]["replay_status"], "replay_required")

    def test_write_scope_is_no_outbox_no_downstream(self) -> None:
        scope = build_write_scope_contract()

        self.assertFalse(scope["writes_outbox"])
        self.assertIn("common_market_data_run", scope["allowed_write_tables"])
        self.assertIn("stock_closed_30m_summary", scope["allowed_write_tables"])
        self.assertIn("common_event_outbox", scope["forbidden_write_tables"])
        self.assertIn("common_event_inbox", scope["forbidden_write_tables"])
        self.assertIn("common_event_consumer_checkpoint", scope["forbidden_write_tables"])
        self.assertIn("trigger/action/user/voice/mobile/sim/position tables", scope["forbidden_write_tables"])

    def test_report_json_valid_and_read_only(self) -> None:
        report = build_replay_dry_run_report(
            c2_run_id="closed_minute_30m_replay_20260525_until_1500__market_data_subscription_x",
            source_condition_run_id="condition_layer_20260522_to_20260525_20260525102249_execute",
            source_subscription_run_id="market_data_subscription_x",
            today_minute_run_id="today_minute_bar_1m_20260525_until_1411__market_data_subscription_x",
            projection_run_id="realtime_projection_metric_x",
            for_trade_date="20260525",
            latest_closed_label="14:11",
            object_counts_by_asset={"stock": 2052, "index": 9, "board": 127},
            baseline_rows_by_asset={"stock": 390213, "index": 1719, "board": 24257},
            missing_candidate_counts_by_asset={"stock": 9, "index": 0, "board": 0},
            bj_missing_candidates=[{"identity_key": "stock:BJ:920001"}],
            target_audit={
                "run_exists": False,
                "minute_rows_for_c2_run": {"stock": 0, "index": 0, "board": 0},
                "summary_rows_for_c2_run": {"stock": 0, "index": 0, "board": 0},
                "quality_rows_for_c2_run": 0,
                "outbox_rows_for_c2_run": 0,
                "inbox_rows_for_c2_run": 0,
                "checkpoint_rows_for_c2_run": 0,
            },
        )

        json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertFalse(report["blocked"])
        self.assertFalse(report["side_effects"]["writes_performed"])
        self.assertFalse(report["side_effects"]["market_data_pulled"])
        self.assertFalse(report["side_effects"]["event_outbox_written"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertGreaterEqual(report["quality"]["p1_count"], 1)


if __name__ == "__main__":
    unittest.main()
