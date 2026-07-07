import unittest
from pathlib import Path

from ashare_v3.action.provisional_monitor_action_executed_dry_run import (
    ACTION_EXECUTED_PLAN,
    SKIPPED_AMBIGUOUS_JOIN,
    SKIPPED_ADAPTER_BLOCKED,
    SKIPPED_DUPLICATE_ACTION_EXECUTED,
    SKIPPED_EXPIRED_WINDOW,
    SKIPPED_FAILED_METRIC,
    SKIPPED_NO_MATCH,
    adapt_confirmation_metric_row,
    build_monitor_action_executed_dry_run_report,
)


def tracking_state(*, status: str = "tracking", trigger_period: str = "D") -> dict[str, object]:
    return {
        "monitor_window_id": "window-1",
        "for_trade_date": "20260625",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "signal_type": "B_BUY",
        "condition_key": "BUY:D",
        "trigger_type": "BUY",
        "tracking_status": status,
        "trigger_live": status == "tracking",
        "current_status": "matched" if status == "tracking" else "inactive",
        "latest_n4_event_id": "evt_n4_latest",
        "latest_n4_event_type": "TriggerStateChanged" if trigger_period == "W" else "TriggerMatched",
        "latest_n4_event_time": "2026-06-25T11:20:00+08:00",
        "trigger_period": trigger_period,
        "triggered_periods": [trigger_period, "D"] if trigger_period == "W" else [trigger_period],
        "trigger_price": "11.20" if trigger_period == "W" else "10.50",
        "trigger_mark_candidate": "normal",
        "trigger_context_version": "evt_n4_latest",
        "last_seen_metric_key": None,
        "last_final_evaluated_metric_key": None,
    }


def tracking_state_for(
    *,
    identity_key: str,
    condition_key: str,
    signal_type: str = "B_BUY",
    trigger_type: str = "BUY",
    latest_n4_event_time: str = "2026-06-25T11:20:00+08:00",
) -> dict[str, object]:
    state = tracking_state()
    state["identity_key"] = identity_key
    state["condition_key"] = condition_key
    state["signal_type"] = signal_type
    state["trigger_type"] = trigger_type
    state["latest_n4_event_time"] = latest_n4_event_time
    return state


def metric(index: int, *, metric_id: int | None = None, action_mark: str = "30m_volume", minute: str = "10:04") -> dict[str, object]:
    resolved_metric_id = metric_id if metric_id is not None else 950000 + index
    return {
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "signal_type": "B_BUY",
        "condition_key": "BUY:D",
        "original_condition_key": "BUY:D",
        "condition_keys": ["BUY:D"],
        "source_metric_kind": "realtime_action_confirmation_metric",
        "source_metric_run_id": "n3p_run",
        "projection_run_id": "n3p_run",
        "confirmation_metric_run_id": "n3p_run",
        "action_confirmation_metric_id": resolved_metric_id,
        "confirmation_metric_id": resolved_metric_id,
        "metric_version": "v1",
        "metric_time": f"2026-06-25T{minute}:00+08:00",
        "metric_minute_label": minute,
        "metric_quality_status": "passed",
        "metric_ready": True,
        "is_closed_1m": True,
        "all_period_confirmation_pass": True,
        "action_mark": action_mark,
        "raw_json": {
            "signal_type": "B_BUY",
            "original_condition_key": "BUY:D",
            "condition_keys": ["BUY:D"],
        },
    }


def evaluator_metric(
    index: int,
    *,
    metric_id: int | None = None,
    signal_type: str = "B_BUY",
    condition_key: str = "LIVE_CURRENT_1M:B_BUY",
    original_condition_key: str = "BUY:D",
    buy_pass: bool = True,
    minute: str = "11:20",
    source_metric_kind: str = "realtime_action_confirmation_metric",
) -> dict[str, object]:
    resolved_metric_id = metric_id if metric_id is not None else 970000 + index
    previous_high = "9.50"
    current_price = "10.00" if buy_pass else "9.00"
    current_1m_amount = "1000" if buy_pass else "800"
    previous_1m_amount = "900"
    current_5m_virtual_amount = "1000" if buy_pass else "800"
    previous_5m_full_amount = "900"
    return {
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "signal_type": signal_type,
        "condition_key": condition_key,
        "source_metric_kind": source_metric_kind,
        "projection_run_id": "n3p_run",
        "action_confirmation_metric_id": resolved_metric_id,
        "metric_version": "v1",
        "metric_time": f"2026-06-25T{minute}:00+08:00",
        "metric_minute_label": minute,
        "metric_quality_status": "passed",
        "metric_ready": True,
        "is_closed_1m": True,
        "all_period_confirmation_pass": None,
        "action_mark": "30m_volume",
        "current_price": current_price,
        "previous_120m_body_high": previous_high,
        "previous_120m_body_low": previous_high,
        "previous_30m_body_high": previous_high,
        "previous_30m_body_low": previous_high,
        "previous_5m_body_high": previous_high,
        "previous_5m_body_low": previous_high,
        "previous_1m_body_high": previous_high,
        "previous_1m_body_low": previous_high,
        "current_1m_amount": current_1m_amount,
        "previous_1m_amount": previous_1m_amount,
        "current_5m_virtual_amount": current_5m_virtual_amount,
        "previous_5m_full_amount": previous_5m_full_amount,
        "current_30m_virtual_amount": "1200",
        "previous_day_same_window_amount": "1000",
        "previous_30m_full_amount": "1000",
        "virtual_amount_policy_version": "previous_day_same_window_elapsed_ratio_v1",
        "projection_schema_version": "n3.action_confirmation_metric.v1",
        "source_fact_ids": {"source_snapshot_id": 1},
        "previous_1m_period_source": "same_trade_date_previous_period",
        "previous_5m_period_source": "same_trade_date_previous_period",
        "previous_30m_period_source": "same_trade_date_previous_period",
        "previous_120m_period_source": "same_trade_date_previous_period",
        "is_first_1m_of_day": False,
        "is_first_5m_of_day": False,
        "is_first_30m_of_day": False,
        "is_first_120m_of_day": False,
        "first_1m_amount_default_pass": False,
        "first_5m_amount_default_pass": False,
        "raw_json": {
            "signal_type": signal_type,
            "original_condition_key": original_condition_key,
            "condition_keys": [original_condition_key],
            "trigger_amount_chain_pass": {"D": True, "M": True, "Q": True, "W": True, "Y": "not_applicable"},
        },
    }


def raw_json_only_metric(
    *,
    metric_id: int = 9502959,
    identity_key: str = "stock:SZ:002668",
    signal_type: str = "B_BUY",
    condition_key: str = "LIVE_CURRENT_1M:B_BUY",
    original_condition_key: str = "BUY:Y,D",
    condition_keys: list[str] | None = None,
    metric_ready: bool = True,
    metric_quality_status: str = "passed",
    source_metric_run_id: str = "n3p_live_current_run",
    current_price: str = "10.00",
    previous_high: str = "9.50",
) -> dict[str, object]:
    return {
        "asset_kind": "stock",
        "identity_key": identity_key,
        "signal_type": None,
        "condition_key": None,
        "source_metric_kind": None,
        "projection_run_id": source_metric_run_id,
        "action_confirmation_metric_id": metric_id,
        "confirmation_metric_run_id": None,
        "metric_version": "v2",
        "metric_time": "2026-06-26T14:47:00+08:00",
        "metric_minute_label": "14:47",
        "metric_quality_status": metric_quality_status,
        "metric_ready": metric_ready,
        "is_closed_1m": None,
        "all_period_confirmation_pass": None,
        "action_mark": None,
        "current_price": current_price,
        "previous_120m_body_high": previous_high,
        "previous_120m_body_low": previous_high,
        "previous_30m_body_high": previous_high,
        "previous_30m_body_low": previous_high,
        "previous_5m_body_high": previous_high,
        "previous_5m_body_low": previous_high,
        "previous_1m_body_high": previous_high,
        "previous_1m_body_low": previous_high,
        "current_1m_amount": "1000",
        "previous_1m_amount": "900",
        "current_5m_virtual_amount": "1000",
        "previous_5m_full_amount": "900",
        "current_30m_virtual_amount": "1200",
        "previous_day_same_window_amount": "1000",
        "previous_30m_full_amount": "1000",
        "virtual_amount_policy_version": "previous_day_same_window_elapsed_ratio_v1",
        "projection_schema_version": "n3.action_confirmation_metric.v2",
        "source_fact_ids": {"source_snapshot_id": 1},
        "previous_1m_period_source": "same_trade_date_previous_period",
        "previous_5m_period_source": "same_trade_date_previous_period",
        "previous_30m_period_source": "same_trade_date_previous_period",
        "previous_120m_period_source": "same_trade_date_previous_period",
        "is_first_1m_of_day": False,
        "is_first_5m_of_day": False,
        "is_first_30m_of_day": False,
        "is_first_120m_of_day": False,
        "first_1m_amount_default_pass": False,
        "first_5m_amount_default_pass": False,
        "raw_json": {
            "signal_type": signal_type,
            "condition_key": condition_key,
            "original_condition_key": original_condition_key,
            "condition_keys": condition_keys or [original_condition_key],
            "source_metric_kind": "realtime_action_confirmation_metric",
            "metric_ready": metric_ready,
            "is_closed_1m": True,
            "metric_quality_status": metric_quality_status,
            "action_mark": "30m_volume",
            "confirmation_metric_run_id": source_metric_run_id,
            "source_metric_run_id": source_metric_run_id,
            "action_confirmation_metric_id": metric_id,
            "closed_minute_proof": {
                "is_closed_1m": True,
                "metric_minute_label": "14:47",
            },
            "trigger_amount_chain_pass": {"D": True, "M": True, "Q": False, "W": True, "Y": "not_applicable"},
        },
    }


class ProvisionalMonitorActionExecutedDryRunTest(unittest.TestCase):
    def test_raw_json_only_metric_is_normalized_to_standard_fields(self) -> None:
        adapted = adapt_confirmation_metric_row(raw_json_only_metric())

        self.assertEqual(adapted["signal_type"], "B_BUY")
        self.assertEqual(adapted["condition_key"], "LIVE_CURRENT_1M:B_BUY")
        self.assertEqual(adapted["original_condition_key"], "BUY:Y,D")
        self.assertEqual(adapted["condition_keys"], ["BUY:Y,D"])
        self.assertEqual(adapted["source_metric_kind"], "realtime_action_confirmation_metric")
        self.assertTrue(adapted["metric_ready"])
        self.assertTrue(adapted["is_closed_1m"])
        self.assertEqual(adapted["metric_quality_status"], "passed")
        self.assertEqual(adapted["confirmation_metric_run_id"], "n3p_live_current_run")
        self.assertEqual(adapted["confirmation_metric_id"], 9502959)
        self.assertIsNone(adapted["all_period_confirmation_pass"])
        self.assertEqual(adapted["adapter_trace"]["normalization_status"], "adapted_from_raw_json")

    def test_already_normalized_metric_is_idempotent(self) -> None:
        adapted = adapt_confirmation_metric_row(metric(1))

        self.assertEqual(adapted["signal_type"], "B_BUY")
        self.assertEqual(adapted["condition_key"], "BUY:D")
        self.assertEqual(adapted["source_metric_kind"], "realtime_action_confirmation_metric")
        self.assertTrue(adapted["all_period_confirmation_pass"])
        self.assertEqual(adapted["adapter_trace"]["normalization_status"], "already_normalized")

    def test_missing_metric_id_or_source_run_id_fails_closed(self) -> None:
        missing_metric_id = raw_json_only_metric(metric_id=0)
        missing_source_run_id = raw_json_only_metric(source_metric_run_id="")

        self.assertEqual(adapt_confirmation_metric_row(missing_metric_id)["adapter_trace"]["normalization_status"], "blocked_missing_required_fields")
        self.assertEqual(adapt_confirmation_metric_row(missing_source_run_id)["adapter_trace"]["normalization_status"], "blocked_missing_required_fields")

    def test_active_window_emits_one_actionexecuted_per_distinct_confirmation_metric(self) -> None:
        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric(i, minute=f"10:{i:02d}") for i in (4, 10, 30, 55, 59)],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 5})
        self.assertEqual(report["action_executed_plan_count"], 5)
        keys = {plan["idempotency_key"] for plan in report["action_executed_plans"]}
        self.assertEqual(len(keys), 5)

    def test_duplicate_confirmation_metric_id_replay_is_skipped(self) -> None:
        first = metric(1, metric_id=950001, action_mark="30m_volume")
        second = metric(2, metric_id=950001, action_mark="normal")

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[first, second],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1, SKIPPED_DUPLICATE_ACTION_EXECUTED: 1})
        self.assertEqual(report["action_executed_plan_count"], 1)
        self.assertNotIn("normal", report["action_executed_plans"][0]["idempotency_key"])

    def test_expired_window_never_emits_actionexecuted(self) -> None:
        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state(status="expired")],
            confirmation_metric_rows=[metric(1)],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {SKIPPED_EXPIRED_WINDOW: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)

    def test_actionexecuted_freezes_latest_n4_context(self) -> None:
        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state(trigger_period="W")],
            confirmation_metric_rows=[metric(1)],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        payload = report["action_executed_plans"][0]["payload"]
        self.assertEqual(payload["latest_n4_event_id"], "evt_n4_latest")
        self.assertEqual(payload["trigger_period"], "W")
        self.assertEqual(payload["triggered_periods"], ["W", "D"])
        self.assertEqual(payload["trigger_price"], "11.20")
        self.assertEqual(payload["confirmation_metric_run_id"], "n3p_run")
        self.assertEqual(payload["confirmation_metric_id"], 950001)

    def test_exact_condition_key_join_still_works(self) -> None:
        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric(1)],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        payload = report["action_executed_plans"][0]["payload"]
        self.assertEqual(payload["confirmation_metric_join_trace"]["join_strategy"], "exact_condition_key")
        self.assertEqual(payload["confirmation_metric_passing_rule_trace"]["passing_rule_strategy"], "legacy_top_level")

    def test_top_level_pass_null_and_evaluator_true_is_accepted(self) -> None:
        metric_row = evaluator_metric(1, original_condition_key="BUY:D", buy_pass=True)

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric_row],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        payload = report["action_executed_plans"][0]["payload"]
        self.assertEqual(payload["confirmation_metric_join_trace"]["join_strategy"], "raw_original_condition_key")
        self.assertEqual(payload["confirmation_metric_passing_rule_trace"]["passing_rule_strategy"], "shared_evaluator_fallback")
        self.assertTrue(payload["confirmation_metric_passing_rule_trace"]["evaluator_all_period_confirmation_pass"])

    def test_top_level_pass_null_and_evaluator_false_is_rejected(self) -> None:
        metric_row = evaluator_metric(1, original_condition_key="BUY:D", buy_pass=False)

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric_row],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {SKIPPED_FAILED_METRIC: 1})
        self.assertEqual(report["decisions"][0]["passing_rule_trace"]["passing_rule_strategy"], "evaluator_failed")
        self.assertFalse(report["decisions"][0]["passing_rule_trace"]["evaluator_all_period_confirmation_pass"])

    def test_raw_trigger_amount_chain_alone_is_not_sufficient_when_evaluator_fails(self) -> None:
        metric_row = evaluator_metric(1, original_condition_key="BUY:D", buy_pass=False)
        metric_row["raw_json"]["trigger_amount_chain_pass"] = {
            "D": True,
            "M": True,
            "Q": True,
            "W": True,
            "Y": "not_applicable",
        }

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric_row],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {SKIPPED_FAILED_METRIC: 1})
        self.assertEqual(report["decisions"][0]["passing_rule_trace"]["passing_rule_strategy"], "evaluator_failed")

    def test_exact_miss_falls_back_to_raw_original_condition_key(self) -> None:
        metric_row = metric(1)
        metric_row["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        metric_row["raw_json"] = {
            "signal_type": "B_BUY",
            "original_condition_key": "BUY:D",
            "condition_keys": ["BUY:X"],
        }

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric_row],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        payload = report["action_executed_plans"][0]["payload"]
        self.assertEqual(payload["confirmation_metric_join_trace"]["join_strategy"], "raw_original_condition_key")

    def test_exact_miss_falls_back_to_raw_condition_keys(self) -> None:
        metric_row = metric(1)
        metric_row["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        metric_row["raw_json"] = {
            "signal_type": "B_BUY",
            "original_condition_key": "BUY:W",
            "condition_keys": ["BUY:D", "BUY:W"],
        }

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric_row],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        payload = report["action_executed_plans"][0]["payload"]
        self.assertEqual(payload["confirmation_metric_join_trace"]["join_strategy"], "raw_condition_keys")

    def test_same_identity_signal_without_original_key_match_does_not_execute(self) -> None:
        metric_row = metric(1)
        metric_row["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        metric_row["raw_json"] = {
            "signal_type": "B_BUY",
            "original_condition_key": "BUY:W",
            "condition_keys": ["BUY:M"],
        }

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric_row],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {SKIPPED_NO_MATCH: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)

    def test_multiple_fallback_window_matches_fail_closed(self) -> None:
        first_state = tracking_state()
        second_state = tracking_state()
        second_state["monitor_window_id"] = "window-2"
        second_state["condition_key"] = "BUY:W"
        metric_row = metric(1)
        metric_row["condition_key"] = "LIVE_CURRENT_1M:B_BUY"
        metric_row["raw_json"] = {
            "signal_type": "B_BUY",
            "original_condition_key": "BUY:Q",
            "condition_keys": ["BUY:D", "BUY:W"],
        }

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[first_state, second_state],
            confirmation_metric_rows=[metric_row],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {SKIPPED_AMBIGUOUS_JOIN: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)
        self.assertEqual(report["decisions"][0]["reason"], "ambiguous_confirmation_metric_join")

    def test_hint_metric_never_becomes_final_proof(self) -> None:
        metric_row = evaluator_metric(
            1,
            signal_type="BUY_HINT",
            condition_key="BUY_HINT",
            original_condition_key="BUY_HINT",
            source_metric_kind="realtime_projection_metric",
        )

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric_row],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {SKIPPED_NO_MATCH: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)

    def test_not_ready_metric_does_not_execute(self) -> None:
        metric_row = evaluator_metric(1)
        metric_row["metric_ready"] = False

        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state()],
            confirmation_metric_rows=[metric_row],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260625",
        )

        self.assertEqual(report["decision_counts"], {SKIPPED_FAILED_METRIC: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)

    def test_raw_json_only_9502959_shape_yields_one_actionexecuted(self) -> None:
        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[
                tracking_state_for(
                    identity_key="stock:SZ:002668",
                    condition_key="BUY:D",
                    latest_n4_event_time="2026-06-26T14:47:00+08:00",
                )
            ],
            confirmation_metric_rows=[raw_json_only_metric(original_condition_key="BUY:D", condition_keys=["BUY:D"])],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260626",
        )

        self.assertEqual(report["decision_counts"], {ACTION_EXECUTED_PLAN: 1})
        self.assertEqual(report["action_executed_plan_count"], 1)
        self.assertEqual(report["accepted_metric_ids"], [9502959])
        self.assertEqual(report["adapter_counts"]["adapted_from_raw_json"], 1)
        self.assertEqual(report["adapter_counts"]["already_normalized"], 0)
        self.assertEqual(report["adapter_counts"]["blocked_missing_required_fields"], 0)
        payload = report["action_executed_plans"][0]["payload"]
        self.assertEqual(payload["confirmation_metric_join_trace"]["join_strategy"], "raw_original_condition_key")
        self.assertEqual(payload["confirmation_metric_passing_rule_trace"]["passing_rule_strategy"], "shared_evaluator_fallback")

    def test_raw_json_only_nonpassing_metric_remains_skipped_failed_metric(self) -> None:
        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[
                tracking_state_for(
                    identity_key="stock:SZ:002668",
                    condition_key="BUY:D",
                    latest_n4_event_time="2026-06-26T14:47:00+08:00",
                )
            ],
            confirmation_metric_rows=[raw_json_only_metric(original_condition_key="BUY:D", condition_keys=["BUY:D"], current_price="9.00")],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260626",
        )

        self.assertEqual(report["decision_counts"], {SKIPPED_FAILED_METRIC: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)
        self.assertEqual(report["accepted_metric_ids"], [])

    def test_adapter_blocked_metric_is_reported_fail_closed(self) -> None:
        report = build_monitor_action_executed_dry_run_report(
            active_tracking_states=[tracking_state_for(identity_key="stock:SZ:002668", condition_key="BUY:D")],
            confirmation_metric_rows=[raw_json_only_metric(source_metric_run_id="")],
            existing_actionexecuted_keys=set(),
            for_trade_date="20260626",
        )

        self.assertEqual(report["decision_counts"], {SKIPPED_ADAPTER_BLOCKED: 1})
        self.assertEqual(report["action_executed_plan_count"], 0)
        self.assertEqual(report["adapter_counts"]["blocked_missing_required_fields"], 1)

    def test_unified_rollback_sql_contains_target_and_required_guards(self) -> None:
        sql = Path("sql/N5_20260626_active_monitor_v2_unified_n4_trigger_events_rollback.sql").read_text(encoding="utf-8")

        self.assertIn("action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1", sql)
        self.assertIn("trigger_provisional_ordinary_20260626_until_1447__realtime_action_confirmation_metric_20260626_until_1447__asset_all__live_current_1m_amount_chain_v2_unified_payload_v1__atomic_rule_v1", sql)
        self.assertIn("trigger_provisional_b2_20260626_until_1447__realtime_projection_metric_20260626_until_1447__live_current_1m_unified_payload_v1__atomic_rule_v1", sql)
        self.assertIn("status IN ('delivering', 'delivered')", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("common_action_tracking_state", sql)
        self.assertIn("common_action_event", sql)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("stock_action_fact", sql)
        self.assertIn("index_action_fact", sql)
        self.assertIn("board_action_fact", sql)
        self.assertIn("source_layer = 'N5_action'", sql)
        self.assertIn("source_layer = 'N4_trigger'", sql)
        self.assertIn("consumer_name LIKE 'n5%'", sql)
        self.assertNotIn("DELETE FROM user_", sql)
        self.assertNotIn("DELETE FROM sim_", sql)
        self.assertNotIn("DELETE FROM n6_", sql)


if __name__ == "__main__":
    unittest.main()
