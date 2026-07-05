import unittest
from unittest.mock import patch

import scripts.run_market_data_subscription_execute as runner


SAMPLE_REPORT = {
    "stage": "N3-6",
    "layer_role": "N3_market_data",
    "market_data_run_id": "market_data_subscription_test",
    "source_condition_run_id": "condition_layer_test",
    "source_trade_date": "20260528",
    "for_trade_date": "20260529",
    "prev_trade_date": "20260528",
    "dry_run_summary": {"source_scope_row_count": 0},
    "write_result": {
        "candidate_rows_written": 0,
        "subscription_rows_written": 0,
        "pull_plan_rows_written": 0,
        "quality_item_rows_written": 0,
        "market_data_fact_rows_written": 0,
        "event_outbox_rows_written": 0,
    },
    "post_checks": {
        "n3_6_n1_n2_active_snapshot_unchanged": True,
        "n3_6_no_market_fact_or_event_rows_written": True,
    },
    "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
}


class MarketDataSubscriptionExecuteRunnerGuardTest(unittest.TestCase):
    def test_missing_execute_blocks_before_db_write(self) -> None:
        with patch.object(runner, "run_market_data_subscription_execute") as execute:
            rc = runner.main(
                [
                    "--user-confirmed",
                    "--source-condition-run-id",
                    "condition_layer_test",
                    "--market-data-run-id",
                    "market_data_subscription_test",
                    "--report-path",
                    "docs/test_report.json",
                ]
            )

        self.assertEqual(rc, 2)
        execute.assert_not_called()

    def test_missing_user_confirmed_blocks_before_db_write(self) -> None:
        with patch.object(runner, "run_market_data_subscription_execute") as execute:
            rc = runner.main(
                [
                    "--execute",
                    "--source-condition-run-id",
                    "condition_layer_test",
                    "--market-data-run-id",
                    "market_data_subscription_test",
                    "--report-path",
                    "docs/test_report.json",
                ]
            )

        self.assertEqual(rc, 2)
        execute.assert_not_called()

    def test_new_aliases_call_execute_only_when_double_confirmed(self) -> None:
        with patch.object(
            runner,
            "run_market_data_subscription_execute",
            return_value=SAMPLE_REPORT,
        ) as execute:
            rc = runner.main(
                [
                    "--execute",
                    "--user-confirmed",
                    "--source-condition-run-id",
                    "condition_layer_test",
                    "--market-data-run-id",
                    "market_data_subscription_test",
                    "--report-path",
                    "docs/test_report.json",
                    "--json",
                ]
            )

        self.assertEqual(rc, 0)
        execute.assert_called_once()
        kwargs = execute.call_args.kwargs
        self.assertEqual(kwargs["condition_run_id"], "condition_layer_test")
        self.assertEqual(kwargs["execute_run_id"], "market_data_subscription_test")
        self.assertEqual(kwargs["json_report_path"], "docs/test_report.json")

    def test_legacy_run_id_and_json_report_path_remain_supported(self) -> None:
        with patch.object(
            runner,
            "run_market_data_subscription_execute",
            return_value=SAMPLE_REPORT,
        ) as execute:
            rc = runner.main(
                [
                    "--execute",
                    "--user-confirmed",
                    "--run-id",
                    "condition_layer_legacy",
                    "--market-data-run-id",
                    "market_data_subscription_legacy",
                    "--json-report-path",
                    "docs/legacy_report.json",
                    "--json",
                ]
            )

        self.assertEqual(rc, 0)
        kwargs = execute.call_args.kwargs
        self.assertEqual(kwargs["condition_run_id"], "condition_layer_legacy")
        self.assertEqual(kwargs["execute_run_id"], "market_data_subscription_legacy")
        self.assertEqual(kwargs["json_report_path"], "docs/legacy_report.json")


if __name__ == "__main__":
    unittest.main()
