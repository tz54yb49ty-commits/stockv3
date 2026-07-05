import unittest
import json
from pathlib import Path

from run_n4_20260605_matched_only_execute_once import build_arg_parser

from ashare_v3.trigger.matched_only_combined_execute import (
    CombinedExecuteBlocked,
    assert_combined_execute_confirmed,
    build_combined_matched_only_write_plan,
)
from ashare_v3.trigger.v4_enforcement import (
    V4EnforcementBlocked,
    assert_v4_write_plan_enforceable,
)


def _local_plan(identity_key: str = "stock:SH:600000") -> dict:
    return {
        "plan_id": f"local:{identity_key}",
        "plan_status": "matched",
        "output_event_type": "TriggerMatched",
        "source_event_id": f"fact_only:snapshot:{identity_key}",
        "source_event_type": "MarketSnapshotUpdated",
        "source_snapshot_run_id": "snapshot_run",
        "snapshot_id": 1,
        "asset_kind": "stock",
        "identity_key": identity_key,
        "direction": "buy",
        "signal_type": "B_BUY",
        "trigger_mark_candidate": "normal",
        "condition_key": "BUY:D",
        "original_condition_key": "BUY:D",
        "legacy_signal_type": "B_BUY",
        "match_basis": "realtime_snapshot",
        "trigger_price": "10.50",
        "trigger_kind": "trigger",
        "trigger_time": "2026-06-05T14:30:00+08:00",
        "triggered_periods": ["D"],
        "trigger_period": "D",
        "trigger_bucket": "trading_day",
        "trigger_live": True,
        "current_status": "matched",
        "n5_entry_allowed": True,
        "data_quality_status": "passed",
        "source_condition_run_id": "condition_run",
        "source_condition_pool_id": 10,
        "source_condition_basis_id": 20,
        "source_minute_target_scope_id": 30,
        "source_market_subscription_id": 40,
        "context_hash": "ctxhash",
        "snapshot_trace": {
            "snapshot_run_id": "snapshot_run",
            "snapshot_id": 1,
            "snapshot_time": "2026-06-05T14:30:00+08:00",
            "source_confirmed_time": "2026-06-05T14:30:00+08:00",
            "current_price": "10.50",
            "quality_status": "passed",
        },
        "all_trigger_periods": ["D"],
        "primary_trigger_period": "D",
    }


def _projection_plan(identity_key: str = "stock:SH:688692") -> dict:
    return {
        "plan_id": f"projection:{identity_key}",
        "plan_status": "matched",
        "output_event_type": "TriggerMatched",
        "source_event_id": f"projection_missing:projection_run:{identity_key}",
        "source_event_type": "MarketSnapshotUpdated",
        "source_projection_id": 99,
        "projection_run_id": "projection_run",
        "projection_window_id": "20260605_1100_1130",
        "asset_kind": "stock",
        "identity_key": identity_key,
        "direction": "sell",
        "signal_type": "S_SELL",
        "trigger_mark_candidate": "30m_shrink",
        "condition_key": "SELL:Y,Q,M,W",
        "original_condition_key": "SELL:Y,Q,M,W",
        "legacy_signal_type": "S_SELL_30M_SHRINK",
        "match_basis": "intraday_projection",
        "trigger_price": "20.20",
        "trigger_kind": "trigger",
        "trigger_time": "2026-06-05T11:30:00+08:00",
        "triggered_periods": ["D"],
        "trigger_period": "30m",
        "trigger_bucket": "20260605_1100_1130",
        "trigger_live": True,
        "current_status": "matched",
        "n5_entry_allowed": True,
        "data_quality_status": "passed",
        "source_condition_run_id": "condition_run",
        "source_condition_pool_id": 11,
        "source_condition_basis_id": 21,
        "source_minute_target_scope_id": 31,
        "source_market_subscription_id": 41,
        "context_hash": "ctxhash2",
        "projection_trace": {
            "projection_run_id": "projection_run",
            "projection_id": 99,
            "trigger_price": "20.20",
            "trigger_time": "2026-06-05T11:30:00+08:00",
            "approved_projection_closed_label_used": "2026-06-05T11:30:00+08:00",
            "source_confirmed_time": "2026-06-05T11:30:00+08:00",
            "quality_status": "passed",
        },
        "all_trigger_periods": ["D"],
        "primary_trigger_period": "D",
    }


class N420260605MatchedOnlyExecuteTests(unittest.TestCase):
    def test_missing_execute_blocks_before_db_write(self) -> None:
        with self.assertRaises(CombinedExecuteBlocked):
            assert_combined_execute_confirmed(execute=False, user_confirmed=True)

    def test_missing_user_confirmed_blocks_before_db_write(self) -> None:
        with self.assertRaises(CombinedExecuteBlocked):
            assert_combined_execute_confirmed(execute=True, user_confirmed=False)

    def test_combined_write_plan_is_matched_only_and_preserves_lineage(self) -> None:
        write_plan = build_combined_matched_only_write_plan(
            local_plans=[_local_plan(), {**_local_plan("stock:SH:600001"), "output_event_type": "TriggerPendingMarketData"}],
            projection_plans=[
                _projection_plan(),
                {**_projection_plan("stock:SH:688693"), "output_event_type": "TriggerPendingMarketData"},
            ],
            execute_run_id="trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
            trigger_context_run_id="trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1",
            snapshot_run_id="snapshot_run",
            projection_run_id="projection_run",
        )

        self.assertEqual(write_plan["write_counts"]["TriggerMatched"], 2)
        self.assertEqual(write_plan["write_counts"]["TriggerPendingMarketData"], 0)
        self.assertEqual(write_plan["write_counts"]["TriggerStateChanged"], 0)
        self.assertEqual(write_plan["invalid_n5_entry_count"], 0)
        self.assertEqual(write_plan["matched_by_basis"], {"intraday_projection": 1, "realtime_snapshot": 1})
        self.assertEqual(write_plan["suppressed_counts"]["TriggerPendingMarketData"], 2)
        self.assertEqual(write_plan["matched_write_plans"][0]["source_snapshot_run_id"], "snapshot_run")
        self.assertEqual(write_plan["matched_write_plans"][1]["projection_run_id"], "projection_run")

    def test_invalid_signal_type_is_not_written(self) -> None:
        invalid = {**_local_plan(), "signal_type": "BUY_HINT"}
        write_plan = build_combined_matched_only_write_plan(
            local_plans=[invalid],
            projection_plans=[],
            execute_run_id="run",
            trigger_context_run_id="ctx",
            snapshot_run_id="snapshot_run",
            projection_run_id="projection_run",
        )

        self.assertEqual(write_plan["write_counts"]["TriggerMatched"], 0)
        self.assertEqual(write_plan["invalid_n5_entry_count"], 1)

    def test_enforcement_blocks_noncompliant_write_plan_before_db_write(self) -> None:
        noncompliant = _local_plan()
        noncompliant.pop("trigger_price")
        write_plan = build_combined_matched_only_write_plan(
            local_plans=[noncompliant],
            projection_plans=[],
            execute_run_id="run",
            trigger_context_run_id="ctx",
            snapshot_run_id="snapshot_run",
            projection_run_id="projection_run",
        )

        with self.assertRaisesRegex(V4EnforcementBlocked, "trigger_price"):
            assert_v4_write_plan_enforceable(write_plan)

    def test_runner_cli_accepts_20260605_artifact_paths(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args(
            [
                "--execute-run-id",
                "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
                "--local-dry-run-json-path",
                "docs/N4_20260605_local_trigger_dry_run_report.json",
                "--projection-dry-run-json-path",
                "docs/N4_20260605_projection_matcher_dry_run_report.json",
                "--contract-path",
                "docs/N4_20260605_execute_contract.json",
                "--preflight-path",
                "docs/N4_20260605_execute_preflight.json",
                "--rollback-sql-path",
                "sql/N4_20260605_execute_rollback.sql",
            ]
        )

        self.assertEqual(args.execute_run_id, "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1")
        self.assertEqual(args.local_dry_run_json_path, "docs/N4_20260605_local_trigger_dry_run_report.json")
        self.assertEqual(args.projection_dry_run_json_path, "docs/N4_20260605_projection_matcher_dry_run_report.json")

    def test_runner_source_does_not_use_old_outbox_consuming_projection_route(self) -> None:
        source = Path("scripts/run_n4_20260605_matched_only_execute_once.py").read_text()

        self.assertNotIn("projection_matcher_execute", source)
        self.assertNotIn("run_projection_matcher_once", source)

    def test_runner_source_calls_v4_enforcement_before_db_write(self) -> None:
        source = Path("scripts/run_n4_20260605_matched_only_execute_once.py").read_text()

        self.assertIn("assert_v4_write_plan_enforceable(write_plan", source)
        self.assertLess(
            source.index("assert_v4_write_plan_enforceable(write_plan"),
            source.index("execute_v4_matched_only_transaction("),
        )

    def test_20260605_contract_preflight_expected_counts_are_matched_only(self) -> None:
        contract = json.loads(Path("docs/N4_20260605_execute_contract.json").read_text())
        preflight = json.loads(Path("docs/N4_20260605_execute_preflight.json").read_text())

        self.assertEqual(contract["expected_writes_after_final_confirmation"]["TriggerMatched"], 1537)
        self.assertEqual(contract["expected_writes_after_final_confirmation"]["TriggerPendingMarketData"], 0)
        self.assertEqual(contract["expected_writes_after_final_confirmation"]["TriggerStateChanged"], 0)
        self.assertEqual(preflight["expected_future_writes"]["TriggerMatched"], 1537)
        self.assertEqual(preflight["quality"]["p0_count"], 0)
        self.assertTrue(preflight["runner_readiness"]["ready"])
        self.assertFalse(contract["input_contract"]["uses_old_outbox_consuming_projection_matcher_execute_route"])
        self.assertFalse(contract["runner_readiness"]["uses_old_outbox_consuming_projection_matcher_execute_route"])
        self.assertFalse(preflight["runner_readiness"]["uses_old_outbox_consuming_projection_matcher_execute_route"])


if __name__ == "__main__":
    unittest.main()
