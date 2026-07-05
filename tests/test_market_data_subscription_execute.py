import unittest

from ashare_v3.market.subscription_execute import (
    build_post_subscription_execute_checks,
    derive_execute_run_id,
    ensure_executable_dry_run_report,
    summarize_dry_run_report,
)


class MarketDataSubscriptionExecuteTest(unittest.TestCase):
    def test_derive_execute_run_id_is_stable_and_does_not_reuse_dry_run_suffix(self) -> None:
        report = sample_dry_run_report()

        run_id = derive_execute_run_id(report)

        self.assertEqual(
            run_id,
            "market_data_subscription_20260525_condition_layer_20260522_to_20260525_test_execute",
        )
        self.assertNotIn("_dry_run", run_id)

    def test_preflight_blocks_when_dry_run_has_p0(self) -> None:
        report = sample_dry_run_report()
        report["quality"]["p0_count"] = 1

        with self.assertRaises(RuntimeError):
            ensure_executable_dry_run_report(report)

    def test_preflight_requires_included_rows(self) -> None:
        report = sample_dry_run_report()
        report["market_data_subscription_candidate"]["rows_included"] = False

        with self.assertRaises(RuntimeError):
            ensure_executable_dry_run_report(report)

    def test_summary_keeps_counts_without_expanding_rows(self) -> None:
        summary = summarize_dry_run_report(sample_dry_run_report())

        self.assertEqual(summary["source_scope_row_count"], 2)
        self.assertEqual(summary["subscription_candidate_count"], 3)
        self.assertEqual(summary["dedup_subscription_count"], 2)
        self.assertNotIn("market_data_subscription_candidate", summary)

    def test_post_checks_pass_for_control_rows_only_write(self) -> None:
        report = sample_dry_run_report()
        run_id = derive_execute_run_id(report)
        pre_backup = {
            "active_snapshot": {"common_condition_run_active": {"rows": [{"run_id": "n2"}]}},
            "n3_fact_and_event_row_counts": {"stock_minute_bar_1m": 0, "common_event_outbox": 0},
        }
        post_backup = {
            "active_snapshot": pre_backup["active_snapshot"],
            "n3_fact_and_event_row_counts": pre_backup["n3_fact_and_event_row_counts"],
            "target_run_row_counts": {
                "common_market_data_run": 1,
                "common_market_data_quality_item": 1,
                "common_market_data_subscription_candidate": 3,
                "common_market_data_subscription": 2,
                "common_market_data_pull_plan": 1,
            },
            "market_data_run_row": {
                "run_id": run_id,
                "mode": "execute",
                "status": "passed",
                "market_data_pulled": False,
                "market_data_fact_written": False,
                "downstream_layers_touched": False,
                "worker_started": False,
            },
        }

        checks = build_post_subscription_execute_checks(
            pre_backup=pre_backup,
            post_backup=post_backup,
            dry_run_report=report,
            write_result={
                "quality_item_rows_written": 1,
                "candidate_rows_written": 3,
                "subscription_rows_written": 2,
                "pull_plan_rows_written": 1,
            },
            execute_run_id=run_id,
        )

        self.assertTrue(all(checks.values()))

    def test_post_checks_detect_fact_or_outbox_write(self) -> None:
        report = sample_dry_run_report()
        run_id = derive_execute_run_id(report)
        pre_backup = {
            "active_snapshot": {"common_condition_run_active": {"rows": [{"run_id": "n2"}]}},
            "n3_fact_and_event_row_counts": {"stock_minute_bar_1m": 0, "common_event_outbox": 0},
        }
        post_backup = {
            "active_snapshot": pre_backup["active_snapshot"],
            "n3_fact_and_event_row_counts": {"stock_minute_bar_1m": 1, "common_event_outbox": 0},
            "target_run_row_counts": {
                "common_market_data_run": 1,
                "common_market_data_quality_item": 1,
                "common_market_data_subscription_candidate": 3,
                "common_market_data_subscription": 2,
                "common_market_data_pull_plan": 1,
            },
            "market_data_run_row": {
                "run_id": run_id,
                "mode": "execute",
                "status": "passed",
                "market_data_pulled": False,
                "market_data_fact_written": False,
                "downstream_layers_touched": False,
                "worker_started": False,
            },
        }

        checks = build_post_subscription_execute_checks(
            pre_backup=pre_backup,
            post_backup=post_backup,
            dry_run_report=report,
            write_result={
                "quality_item_rows_written": 1,
                "candidate_rows_written": 3,
                "subscription_rows_written": 2,
                "pull_plan_rows_written": 1,
            },
            execute_run_id=run_id,
        )

        self.assertFalse(checks["n3_6_no_market_fact_or_event_rows_written"])


def sample_dry_run_report() -> dict[str, object]:
    return {
        "mode": "dry_run",
        "blocked": False,
        "passed": True,
        "market_data_run_id": "market_data_subscription_20260525_condition_layer_20260522_to_20260525_test_execute_dry_run",
        "source_condition_run_id": "condition_layer_20260522_to_20260525_test_execute",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "source_scope_row_count": 2,
        "source_scope_row_count_by_asset_kind": {"stock": 2, "index": 0, "board": 0},
        "subscription_candidate_count": 3,
        "candidate_row_count": 3,
        "dedup_subscription_count": 2,
        "subscription_row_count": 2,
        "subscription_object_count": 1,
        "object_count_by_asset_kind": {"stock": 1, "index": 0, "board": 0},
        "required_data_kind_counts": {"realtime_daily_snapshot": 1, "minute_bar_1m": 1},
        "previous_day_minute_required_count": 1,
        "previous_day_minute_date_counts": {"20260522": 1},
        "dedup_ratio": 0.666667,
        "dedup_reduction_ratio": 0.333333,
        "market_data_pull_plan_row_count": 1,
        "quality": {
            "p0_count": 0,
            "p1_count": 0,
            "p2_count": 0,
            "items": [
                {
                    "severity": "P0",
                    "status": "passed",
                    "gate_code": "no_market_data_fact_write",
                    "gate_name": "dry-run does not write market data facts",
                }
            ],
        },
        "market_data_subscription_candidate": {
            "row_count": 3,
            "rows_included": True,
            "rows": [{}, {}, {}],
        },
        "market_data_subscription_dedup": {
            "row_count": 2,
            "rows_included": True,
            "rows": [{}, {}],
        },
        "market_data_pull_plan": {
            "row_count": 1,
            "rows_included": True,
            "rows": [{}],
        },
    }


if __name__ == "__main__":
    unittest.main()
