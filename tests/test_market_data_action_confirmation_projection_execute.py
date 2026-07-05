import unittest

from ashare_v3.market.action_confirmation_projection_execute import (
    ACTION_CONFIRMATION_ALLOWED_WRITE_TABLES,
    ACTION_CONFIRMATION_FORBIDDEN_WRITE_TABLES,
    ACTION_CONFIRMATION_METRIC_SCOPE,
    ACTION_CONFIRMATION_QUALITY_LAYER_SCOPE,
    ActionConfirmationProjectionExecuteError,
    build_action_confirmation_execute_contract,
    build_action_confirmation_execute_preflight,
    build_action_confirmation_execute_quality_items,
    ensure_action_confirmation_execute_authorized,
)


class ActionConfirmationProjectionExecuteTest(unittest.TestCase):
    def _dry_run(self) -> dict:
        return {
            "result": "DRY_RUN_PASS",
            "blocked": False,
            "projection_run_id": "action_confirmation_projection_metric_20260602_1105__snapshot",
            "projection_schema_version": "n3.action_confirmation_metric.v1",
            "for_trade_date": "20260602",
            "source_condition_run_id": "condition_layer_20260601_source_20260601_v1",
            "source_subscription_run_id": "market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1",
            "source_snapshot_run_id": "snapshot_run",
            "source_today_minute_run_id": "today_minute_run",
            "source_previous_day_minute_run_id": "previous_minute_run",
            "candidate_summary": {"stock": 765, "index": 54, "board": 150, "total": 969},
            "would_write_rows": {"stock": 765, "index": 54, "board": 150, "total": 969},
            "metric_ready_distribution": {
                "ready_total": 969,
                "not_ready_total": 0,
                "by_asset": {
                    "stock": {"ready": 765, "not_ready": 0},
                    "index": {"ready": 54, "not_ready": 0},
                    "board": {"ready": 150, "not_ready": 0},
                },
            },
            "trace_refs_proof": {
                "source_fact_ids_non_empty": 969,
                "source_minute_refs_non_empty": 969,
                "previous_day_refs_required": 969,
                "previous_day_refs_non_empty": 969,
                "db_check_pass_total": 969,
                "db_check_fail_total": 0,
            },
            "baseline_summary": {
                "common_market_data_run": 0,
                "common_market_data_quality_item": 0,
                "stock_action_confirmation_projection_metric": 0,
                "index_action_confirmation_projection_metric": 0,
                "board_action_confirmation_projection_metric": 0,
                "common_event_outbox": 0,
                "common_event_inbox": 0,
                "common_event_consumer_checkpoint": 0,
            },
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
        }

    def test_execute_requires_execute_and_user_confirmed(self) -> None:
        with self.assertRaises(ActionConfirmationProjectionExecuteError):
            ensure_action_confirmation_execute_authorized(execute=False, user_confirmed=True)

        with self.assertRaises(ActionConfirmationProjectionExecuteError):
            ensure_action_confirmation_execute_authorized(execute=True, user_confirmed=False)

        ensure_action_confirmation_execute_authorized(execute=True, user_confirmed=True)

    def test_contract_has_fixed_scope_and_rollback_predicate(self) -> None:
        contract = build_action_confirmation_execute_contract(self._dry_run())

        self.assertFalse(contract["execute_authorized_now"])
        self.assertTrue(contract["runner_exists"])
        self.assertEqual(contract["runner_readiness"], "ready")
        self.assertEqual(contract["expected_rows"], {"stock": 765, "index": 54, "board": 150, "total": 969})
        self.assertEqual(contract["metric_ready_expected"], 969)
        self.assertIn("common_market_data_run", ACTION_CONFIRMATION_ALLOWED_WRITE_TABLES)
        self.assertIn("common_event_outbox", ACTION_CONFIRMATION_FORBIDDEN_WRITE_TABLES)
        self.assertEqual(contract["quality_rollback_predicate"]["layer_scope"], "market_data_run")
        self.assertEqual(contract["quality_rollback_predicate"]["details.metric_scope"], ACTION_CONFIRMATION_METRIC_SCOPE)
        self.assertFalse(contract["run_row_contract"]["downstream_layers_touched"])
        self.assertFalse(contract["run_row_contract"]["worker_started"])

    def test_preflight_passes_when_dry_run_baseline_and_trace_are_clean(self) -> None:
        dry_run = self._dry_run()
        contract = build_action_confirmation_execute_contract(dry_run)
        preflight = build_action_confirmation_execute_preflight(contract, dry_run)

        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertFalse(preflight["blocked"])
        self.assertEqual(preflight["would_write_rows"], dry_run["would_write_rows"])
        self.assertEqual(preflight["metric_ready_distribution"]["ready_total"], 969)
        self.assertEqual(preflight["quality"]["p0_count"], 0)

    def test_quality_items_match_business_rollback_predicate(self) -> None:
        dry_run = self._dry_run()
        contract = build_action_confirmation_execute_contract(dry_run)
        items = build_action_confirmation_execute_quality_items(contract, dry_run)

        self.assertGreaterEqual(len(items), 3)
        self.assertEqual({item["layer_scope"] for item in items}, {ACTION_CONFIRMATION_QUALITY_LAYER_SCOPE})
        self.assertEqual({item["details"]["metric_scope"] for item in items}, {ACTION_CONFIRMATION_METRIC_SCOPE})
        self.assertEqual({item["run_id"] for item in items}, {dry_run["projection_run_id"]})


if __name__ == "__main__":
    unittest.main()
