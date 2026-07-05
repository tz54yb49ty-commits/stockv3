import unittest
from unittest.mock import patch

import run_v3_20260612_n4_full_day_trigger_replay_once as replay_runner
from ashare_v3.market import v3_full_day_replay_plan as replay_plan


def context_row(
    *,
    identity_key: str = "stock:SZ:000001",
    direction: str = "buy",
    condition_key: str = "BUY:D",
    allowed_signal_types: list[str] | None = None,
) -> dict:
    allowed_signal_types = allowed_signal_types or (["B_BUY"] if direction == "buy" else ["S_SELL"])
    return {
        "run_id": replay_plan.TRIGGER_CONTEXT_RUN_ID,
        "asset_kind": "stock",
        "identity_key": identity_key,
        "direction": direction,
        "condition_key": condition_key,
        "allowed_signal_types": allowed_signal_types,
        "trigger_context_id": 101,
        "source_condition_run_id": replay_plan.SOURCE_CONDITION_RUN_ID,
        "source_condition_pool_id": 201,
        "source_condition_basis_id": 301,
        "source_minute_target_scope_id": 401,
        "source_market_subscription_id": 501,
        "context_hash": "ctx-hash",
    }


def metric_row(metric_id: int, label: str = "2026-06-12T09:31:00+08:00") -> dict:
    return {
        "action_confirmation_metric_id": metric_id,
        "metric_time": label,
        "metric_minute_label": label[:16].replace("T", " "),
    }


def metric_plan(
    *,
    output_event_type: str | None = "TriggerMatched",
    plan_status: str = "would_trigger",
    identity_key: str = "stock:SZ:000001",
    direction: str = "buy",
    signal_type: str = "B_BUY",
    condition_key: str = "BUY:D",
    primary_trigger_period: str | None = "D",
    all_trigger_periods: list[str] | None = None,
    trigger_mark_candidate: str = "normal",
    projection_30m_flag: bool = False,
    projection_30m_type: str = "none",
    not_ready_reason: str | None = None,
    source_event_id: str = "evt_metric_1",
) -> dict:
    all_trigger_periods = ["D"] if all_trigger_periods is None else all_trigger_periods
    trigger_live = output_event_type == "TriggerMatched"
    current_status = "matched" if trigger_live else "pending_market_data"
    return {
        "plan_id": f"plan-{source_event_id}",
        "plan_status": plan_status,
        "output_event_type": output_event_type,
        "source_event_id": source_event_id,
        "source_event_type": "MarketSnapshotUpdated",
        "source_market_event_or_projection_id": source_event_id,
        "asset_kind": "stock",
        "identity_key": identity_key,
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": condition_key,
        "legacy_signal_type": signal_type,
        "match_basis": "n3_action_confirmation_metric",
        "trigger_period": primary_trigger_period or "30m",
        "trigger_bucket": primary_trigger_period or "30m",
        "trigger_live": trigger_live,
        "current_status": current_status,
        "primary_trigger_period": primary_trigger_period,
        "all_trigger_periods": all_trigger_periods,
        "projection_30m_flag": projection_30m_flag,
        "projection_30m_type": projection_30m_type,
        "trigger_mark_candidate": trigger_mark_candidate,
        "data_quality_status": "passed",
        "not_ready_reason": not_ready_reason,
        "metric_trace": {"metric_time": "2026-06-12T09:31:00+08:00"},
    }


class V320260612N4TriggerStateMachineTests(unittest.TestCase):
    def test_matched_then_ready_not_satisfied_emits_live_false_state_changed(self) -> None:
        context = context_row()
        plans = [
            metric_plan(source_event_id="evt_buy_live"),
            metric_plan(
                output_event_type="TriggerPendingMarketData",
                plan_status="would_pending",
                not_ready_reason="metric_ready_but_side_trigger_evidence_not_satisfied",
                source_event_id="evt_buy_inactive",
            ),
        ]

        with patch.object(replay_runner, "evaluate_action_confirmation_metric_candidate", side_effect=plans):
            output = list(
                replay_runner.iter_full_day_plans(
                    context_rows=[context],
                    metric_lookup={("stock", "stock:SZ:000001"): [metric_row(1), metric_row(2)]},
                    trigger_context_run_id=replay_plan.TRIGGER_CONTEXT_RUN_ID,
                    projection_run_id=replay_plan.FULL_DAY_METRIC_RUN_ID,
                    source_condition_run_id=replay_plan.SOURCE_CONDITION_RUN_ID,
                    source_subscription_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                    source_snapshot_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                    for_trade_date=replay_plan.FOR_TRADE_DATE,
                )
            )

        self.assertEqual([item["output_event_type"] for item in output], ["TriggerMatched", "TriggerStateChanged", "TriggerStateChanged"])
        self.assertEqual(output[-1]["state_change_reason"], "deactivated")
        self.assertFalse(output[-1]["trigger_live"])
        self.assertEqual(output[-1]["current_status"], "inactive")
        self.assertFalse(output[-1]["writes_common_trigger_match"])
        self.assertNotIn("TriggerPendingMarketData", [item["output_event_type"] for item in output])

    def test_period_upgrade_emits_state_changed_not_second_trigger_matched(self) -> None:
        context = context_row()
        plans = [
            metric_plan(source_event_id="evt_buy_d", primary_trigger_period="D", all_trigger_periods=["D"]),
            metric_plan(source_event_id="evt_buy_w", primary_trigger_period="W", all_trigger_periods=["W", "D"]),
        ]

        with patch.object(replay_runner, "evaluate_action_confirmation_metric_candidate", side_effect=plans):
            output = list(
                replay_runner.iter_full_day_plans(
                    context_rows=[context],
                    metric_lookup={("stock", "stock:SZ:000001"): [metric_row(1), metric_row(2)]},
                    trigger_context_run_id=replay_plan.TRIGGER_CONTEXT_RUN_ID,
                    projection_run_id=replay_plan.FULL_DAY_METRIC_RUN_ID,
                    source_condition_run_id=replay_plan.SOURCE_CONDITION_RUN_ID,
                    source_subscription_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                    source_snapshot_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                    for_trade_date=replay_plan.FOR_TRADE_DATE,
                )
            )

        self.assertEqual(sum(1 for item in output if item["output_event_type"] == "TriggerMatched"), 1)
        self.assertEqual(output[-1]["output_event_type"], "TriggerStateChanged")
        self.assertEqual(output[-1]["state_change_reason"], "period_upgrade")
        self.assertFalse(output[-1]["is_n5_action_entry"])

    def test_metric_missing_emits_pending_market_data_and_state_changed(self) -> None:
        context = context_row()
        pending = metric_plan(
            output_event_type="TriggerPendingMarketData",
            plan_status="would_pending",
            not_ready_reason="metric_row_missing",
            source_event_id="evt_metric_missing",
        )

        with patch.object(replay_runner, "evaluate_action_confirmation_metric_candidate", return_value=pending):
            output = list(
                replay_runner.iter_full_day_plans(
                    context_rows=[context],
                    metric_lookup={},
                    trigger_context_run_id=replay_plan.TRIGGER_CONTEXT_RUN_ID,
                    projection_run_id=replay_plan.FULL_DAY_METRIC_RUN_ID,
                    source_condition_run_id=replay_plan.SOURCE_CONDITION_RUN_ID,
                    source_subscription_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                    source_snapshot_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                    for_trade_date=replay_plan.FOR_TRADE_DATE,
                )
            )

        self.assertEqual([item["output_event_type"] for item in output], ["TriggerPendingMarketData", "TriggerStateChanged"])
        self.assertFalse(output[0]["writes_common_trigger_match"])
        self.assertFalse(output[0]["is_n5_action_entry"])

    def test_direction_switch_is_old_direction_deactivation_plus_new_direction_match(self) -> None:
        buy = context_row(direction="buy", condition_key="BUY:D", allowed_signal_types=["B_BUY"])
        sell = context_row(direction="sell", condition_key="SELL:D", allowed_signal_types=["S_SELL"])

        def fake_evaluate(*, row, metric, **_kwargs):
            metric_id = int(metric["action_confirmation_metric_id"])
            if row["direction"] == "buy" and metric_id == 1:
                return metric_plan(source_event_id="evt_buy_live")
            if row["direction"] == "buy":
                return metric_plan(
                    output_event_type="TriggerPendingMarketData",
                    plan_status="would_pending",
                    not_ready_reason="metric_ready_but_side_trigger_evidence_not_satisfied",
                    source_event_id=f"evt_buy_inactive_{metric_id}",
                )
            if metric_id == 3:
                return metric_plan(
                    direction="sell",
                    signal_type="S_SELL",
                    condition_key="SELL:D",
                    source_event_id="evt_sell_live",
                )
            return metric_plan(
                output_event_type=None,
                plan_status="no_op",
                direction="sell",
                signal_type="S_SELL",
                condition_key="SELL:D",
                source_event_id=f"evt_sell_noop_{metric_id}",
            )

        with patch.object(replay_runner, "evaluate_action_confirmation_metric_candidate", side_effect=fake_evaluate):
            output = list(
                replay_runner.iter_full_day_plans(
                    context_rows=[buy, sell],
                    metric_lookup={
                        ("stock", "stock:SZ:000001"): [metric_row(1), metric_row(2), metric_row(3)],
                    },
                    trigger_context_run_id=replay_plan.TRIGGER_CONTEXT_RUN_ID,
                    projection_run_id=replay_plan.FULL_DAY_METRIC_RUN_ID,
                    source_condition_run_id=replay_plan.SOURCE_CONDITION_RUN_ID,
                    source_subscription_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                    source_snapshot_run_id=replay_plan.FULL_DAY_1M_BACKFILL_RUN_ID,
                    for_trade_date=replay_plan.FOR_TRADE_DATE,
                )
            )

        self.assertEqual(sum(1 for item in output if item["output_event_type"] == "TriggerMatched"), 2)
        deactivated = [item for item in output if item.get("state_change_reason") == "deactivated"]
        self.assertEqual(len(deactivated), 1)
        self.assertEqual(deactivated[0]["direction"], "buy")
        self.assertFalse(deactivated[0]["trigger_live"])

    def test_main_execute_allows_state_changed_after_persistence_alignment(self) -> None:
        report = {
            "summary": {"state_changed_count": 1},
            "quality": {"items": []},
        }
        final_preflight = {"result": "PREFLIGHT_PASS"}
        with (
            patch.object(
                replay_runner,
                "build_report_and_artifacts",
                return_value=(report, {}, {}, final_preflight, [], {}, {}),
            ),
            patch.object(
                replay_runner,
                "execute_replay",
                return_value={"common_trigger_run": 1, "common_trigger_state": 1, "common_trigger_match": 0, "common_event_outbox": 1},
            ) as execute_replay,
            patch.object(replay_runner, "write_json"),
            patch.object(replay_runner, "write_text"),
            patch("sys.argv", ["run_v3_20260612_n4_full_day_trigger_replay_once.py", "--execute", "--user-confirmed"]),
        ):
            return_code = replay_runner.main()

        self.assertEqual(return_code, 0)
        execute_replay.assert_called_once()

    def test_main_passes_explicit_run_id_and_artifact_paths_to_builder(self) -> None:
        target_run_id = "v3_n4_trigger_replay_20260612_after_trigger_period_baseline_fix_v1"
        report = {
            "summary": {"state_changed_count": 0},
            "quality": {"items": []},
        }
        final_preflight = {"result": "PREFLIGHT_PASS"}
        with (
            patch.object(
                replay_runner,
                "build_report_and_artifacts",
                return_value=(report, {}, {}, final_preflight, [], {}, {}),
            ) as build_report,
            patch("sys.argv", [
                "run_v3_20260612_n4_full_day_trigger_replay_once.py",
                "--execute-run-id",
                target_run_id,
                "--dry-run-json-path",
                "docs/custom_dry_run.json",
                "--contract-json-path",
                "docs/custom_contract.json",
                "--preflight-json-path",
                "docs/custom_preflight.json",
                "--rollback-sql-path",
                "sql/custom_rollback.sql",
            ]),
        ):
            return_code = replay_runner.main()

        self.assertEqual(return_code, 0)
        build_report.assert_called_once()
        kwargs = build_report.call_args.kwargs
        self.assertEqual(kwargs["execute_run_id"], target_run_id)
        self.assertEqual(kwargs["dry_run_json_path"], "docs/custom_dry_run.json")
        self.assertEqual(kwargs["contract_json_path"], "docs/custom_contract.json")
        self.assertEqual(kwargs["preflight_json_path"], "docs/custom_preflight.json")
        self.assertEqual(kwargs["rollback_sql_path"], "sql/custom_rollback.sql")


if __name__ == "__main__":
    unittest.main()
