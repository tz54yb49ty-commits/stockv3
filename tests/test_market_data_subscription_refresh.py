import unittest

from ashare_v3.market.subscription_refresh import (
    build_old_new_comparison,
    build_refresh_quality_items,
    build_subscription_refresh_report_from_inputs,
)


class MarketDataSubscriptionRefreshTest(unittest.TestCase):
    def test_refresh_report_passes_with_new_active_and_stale_old_run(self) -> None:
        report = build_subscription_refresh_report_from_inputs(
            dry_run=sample_dry_run(),
            db_state=sample_db_state(),
            new_condition_run_id="condition_layer_new",
            expected_scope_counts={"stock": 4236, "index": 18, "board": 258},
            expected_object_counts={"stock": 2052, "index": 9, "board": 127},
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertGreaterEqual(report["quality"]["p1_count"], 1)
        self.assertTrue(report["old_n3_subscription_run_is_stale"])
        self.assertFalse(report["decision"]["old_n3_run_can_continue_as_final_chain"])
        self.assertEqual(report["suggested_execute_run_id"], "market_data_subscription_20260525_condition_layer_new")

    def test_scope_count_mismatch_is_p0(self) -> None:
        dry_run = sample_dry_run()
        dry_run["source_scope_row_count_by_asset_kind"] = {"stock": 1, "index": 18, "board": 258}

        items = build_refresh_quality_items(
            dry_run=dry_run,
            db_state=sample_db_state(),
            new_condition_run_id="condition_layer_new",
            expected_scope_counts={"stock": 4236, "index": 18, "board": 258},
            expected_object_counts={"stock": 2052, "index": 9, "board": 127},
            old_run=sample_old_run(),
            old_run_is_stale=True,
            new_existing_runs=[],
        )

        failed_codes = {item["gate_code"] for item in items if item["severity"] == "P0" and item["status"] == "failed"}
        self.assertIn("n3_after_n2_r2_scope_row_counts_match_expected", failed_codes)

    def test_object_count_mismatch_is_p0(self) -> None:
        dry_run = sample_dry_run()
        dry_run["object_count_by_asset_kind"] = {"stock": 2051, "index": 9, "board": 127}

        report = build_subscription_refresh_report_from_inputs(
            dry_run=dry_run,
            db_state=sample_db_state(),
            new_condition_run_id="condition_layer_new",
            expected_scope_counts={"stock": 4236, "index": 18, "board": 258},
            expected_object_counts={"stock": 2052, "index": 9, "board": 127},
        )

        self.assertFalse(report["passed"])
        failed_codes = {item["gate_code"] for item in report["quality"]["items"] if item["severity"] == "P0" and item["status"] == "failed"}
        self.assertIn("n3_after_n2_r2_object_counts_match_expected", failed_codes)

    def test_old_new_comparison_marks_lineage_changed_even_when_counts_match(self) -> None:
        comparison = build_old_new_comparison(
            dry_run=sample_dry_run(),
            old_run=sample_old_run(),
            old_control_counts={
                "common_market_data_subscription_candidate": 13536,
                "common_market_data_subscription": 6564,
                "common_market_data_pull_plan": 9,
            },
        )

        self.assertTrue(comparison["lineage_changed"])
        self.assertEqual(comparison["delta"]["subscription_row_count"], 0)
        self.assertEqual(comparison["old_source_condition_run_id"], "condition_layer_old")
        self.assertEqual(comparison["new_source_condition_run_id"], "condition_layer_new")

    def test_side_effect_flags_block_when_market_fact_written(self) -> None:
        dry_run = sample_dry_run()
        dry_run["market_data_fact_written"] = True

        items = build_refresh_quality_items(
            dry_run=dry_run,
            db_state=sample_db_state(),
            new_condition_run_id="condition_layer_new",
            expected_scope_counts={"stock": 4236, "index": 18, "board": 258},
            expected_object_counts={"stock": 2052, "index": 9, "board": 127},
            old_run=sample_old_run(),
            old_run_is_stale=True,
            new_existing_runs=[],
        )

        failed_codes = {item["gate_code"] for item in items if item["severity"] == "P0" and item["status"] == "failed"}
        self.assertIn("n3_after_n2_r2_no_market_fact_outbox_or_worker", failed_codes)


def sample_dry_run() -> dict[str, object]:
    return {
        "stage": "N3-0",
        "mode": "dry_run",
        "market_data_run_id": "market_data_subscription_20260525_condition_layer_new_dry_run",
        "source_condition_run_id": "condition_layer_new",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "source_scope_row_count": 4512,
        "source_scope_row_count_by_asset_kind": {"stock": 4236, "index": 18, "board": 258},
        "object_count_by_asset_kind": {"stock": 2052, "index": 9, "board": 127},
        "subscription_candidate_count": 13536,
        "dedup_subscription_count": 6564,
        "subscription_object_count": 2188,
        "required_data_kind_counts": {
            "realtime_daily_snapshot": 2188,
            "minute_bar_1m": 2188,
            "previous_day_minute_bar_1m": 2188,
        },
        "market_data_pull_plan_row_count": 9,
        "market_data_pull_plan": {"row_count": 9, "rows_included": False},
        "market_data_subscription_candidate": {"row_count": 13536, "rows_included": False},
        "market_data_subscription_dedup": {"row_count": 6564, "rows_included": False},
        "dedup_ratio": "0.484929",
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": []},
        "passed": True,
        "blocked": False,
        "market_data_pulled": False,
        "market_data_fact_written": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }


def sample_db_state() -> dict[str, object]:
    return {
        "active_passed_runs": [{"run_id": "condition_layer_new", "status": "passed", "p0_count": 0}],
        "old_market_data_run": sample_old_run(),
        "existing_subscription_runs": [sample_old_run()],
        "control_row_counts_by_run": {
            "market_data_subscription_20260525_condition_layer_old": {
                "common_market_data_subscription_candidate": 13536,
                "common_market_data_subscription": 6564,
                "common_market_data_pull_plan": 9,
            }
        },
        "fact_event_row_counts": {"common_event_outbox": 0},
    }


def sample_old_run() -> dict[str, object]:
    return {
        "run_id": "market_data_subscription_20260525_condition_layer_old",
        "source_condition_run_id": "condition_layer_old",
        "for_trade_date": "20260525",
        "source_scope_row_count": 4512,
        "candidate_row_count": 13536,
        "subscription_row_count": 6564,
        "subscription_object_count": 2188,
        "status": "passed",
    }


if __name__ == "__main__":
    unittest.main()
