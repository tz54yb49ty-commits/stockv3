import copy
import unittest

from ashare_v3.trigger.provisional_trigger_lifecycle import (
    TRIGGER_MATCHED_EVENT_TYPE,
    TRIGGER_STATE_CHANGED_EVENT_TYPE,
    build_lifecycle_output_plans,
    lifecycle_state_key,
)


def plan(
    *,
    condition_key: str = "BUY_HINT",
    signal_type: str = "B_BUY",
    trigger_type: str = "BUY_HINT",
    status: str = "matched",
    projection_30m_type: str = "volume_up",
    trigger_mark_candidate: str = "30m_volume",
    trigger_period: str = "30m",
    triggered_periods: list[str] | None = None,
    trigger_price: str = "10.00",
    primary_trigger_period: str | None = None,
    all_trigger_periods: list[str] | None = None,
    prerequisite_periods: list[str] | None = None,
    period_escalation_trace: dict[str, object] | None = None,
) -> dict[str, object]:
    matched = status == "matched"
    return {
        "for_trade_date": "20260625",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "direction": "buy",
        "condition_key": condition_key,
        "signal_type": signal_type,
        "trigger_type": trigger_type,
        "plan_status": status,
        "output_event_type": "TriggerMatched" if matched else None,
        "trigger_live": matched,
        "current_status": "matched" if matched else "no_op",
        "projection_status": "ready",
        "projection_quality_status": "passed",
        "trace_status": "passed",
        "projection_30m_type": projection_30m_type if matched else "none",
        "trigger_mark_candidate": trigger_mark_candidate if matched else "none",
        "projection_30m_flag": matched,
        "projection_signal_status": "up_volume_expanding" if matched else "flat",
        "trigger_period": trigger_period,
        "triggered_periods": triggered_periods or [trigger_period],
        "trigger_price": trigger_price,
        "primary_trigger_period": primary_trigger_period or trigger_period,
        "all_trigger_periods": all_trigger_periods or [trigger_period],
        "prerequisite_periods": prerequisite_periods or [],
        "period_escalation_trace": period_escalation_trace or {},
        "event_time": "2026-06-25T11:29:00+08:00",
    }


def previous_state(current: dict[str, object], *, status: str = "matched") -> dict[str, object]:
    return {
        "for_trade_date": current["for_trade_date"],
        "asset_kind": current["asset_kind"],
        "identity_key": current["identity_key"],
        "direction": current["direction"],
        "signal_type": current["signal_type"],
        "condition_key": current["condition_key"],
        "trigger_period": "30m",
        "current_status": status,
        "match_count": 1 if status == "matched" else 0,
        "dedup_key": "previous-key",
        "raw_json": {
            "trigger_type": current["trigger_type"],
            "projection_30m_type": current["projection_30m_type"],
            "trigger_mark_candidate": current["trigger_mark_candidate"],
            "projection_30m_flag": current["projection_30m_flag"],
            "trigger_period": current["trigger_period"],
            "triggered_periods": current["triggered_periods"],
            "trigger_price": current["trigger_price"],
            "primary_trigger_period": current["primary_trigger_period"],
            "all_trigger_periods": current["all_trigger_periods"],
        },
    }


def formal_period_detail(
    *,
    period: str,
    direction: str,
    classification: str,
    current_transition: str,
) -> dict[str, object]:
    amount_fields = {
        "D": "today_virt_amount",
        "W": "weekly_avg_with_today",
        "M": "monthly_avg_with_today",
        "Q": "quarterly_avg_with_today",
        "Y": "yearly_avg_with_today",
    }
    target_transition = "volume_up" if direction == "buy" else "low_volume_down"
    return {
        "period": period,
        "classification": classification,
        "reason": None if classification == "triggered" else "transition_or_chain_not_triggered",
        "current_transition": current_transition,
        "previous_transition": "flat",
        "current_price_or_close": 10.0,
        "current_amount_metric": 200.0,
        "transition_amount_field": amount_fields[period],
        "transition_amount_value": 200.0,
        "used_for_period": period,
        "compare_to": f"previous_avg_amount[{period}]",
        "previous_amount_source_field": f"previous_avg_amount_{period}",
        "previous_amount_baseline": 100.0,
        "trigger_previous_entity_high": 9.0,
        "trigger_previous_entity_low": 11.0,
        "transition_amount_pass": True,
        "trigger_amount_chain_pass": "not_applicable" if period == "Y" else True,
        "amount_unit_status": {"status": "matched"},
        "amount_source_status": {"status": "matched"},
        "amount_metric": amount_fields[period],
        "amount_rule": "price_break_plus_current_period_avg_with_today_vs_previous_avg_amount",
        "source_field_trace": {"period": period, "target_transition": target_transition},
        "baseline_period_key_current": f"current:{period}",
        "baseline_period_key_previous": f"previous:{period}",
        "baseline_source_trade_date": "20260624",
        "for_trade_date": "20260625",
        "projection_for_trade_date": "20260625",
        "stale_period_baseline": False,
        "stale_period_baseline_reason": None,
    }


def scoped_deactivation_case(
    *,
    period: str = "D",
    direction: str = "buy",
    asset_kind: str = "stock",
) -> tuple[dict[str, object], dict[str, object]]:
    condition_prefix = "BUY" if direction == "buy" else "SELL"
    signal_type = "B_BUY" if direction == "buy" else "S_SELL"
    target_transition = "volume_up" if direction == "buy" else "low_volume_down"
    period_escalation_trace = {
        "policy_version": "N4-ordinary-period-escalation-v2",
        "policy_hash": "3a0aa136ff3393c7",
        "context_hash": "fixture-period-escalation-context-hash",
        "periods": {
            blocked_period: {
                "reason": f"period_escalation_prerequisite_not_ready:{blocked_period}",
                "gate_pass": False,
                "evidence_ready": False,
                "gate_status": "not_ready",
                "source_entry": {
                    "status": "not_ready",
                    "entry_hash": f"fixture-entry-hash-{blocked_period}",
                    "window_key": f"fixture-window-{blocked_period}",
                    "window_start": "20260101",
                    "observation_end": "20260624",
                },
            }
            for blocked_period in ("Q", "Y")
        },
    }
    current = plan(
        condition_key=f"{condition_prefix}:Y,Q,M,W,D",
        signal_type=signal_type,
        trigger_type=condition_prefix,
        status="no_op",
        trigger_period=period,
        primary_trigger_period=period,
        all_trigger_periods=[period],
    )
    current.update(
        {
            "asset_kind": asset_kind,
            "identity_key": f"{asset_kind}:fixture:{period}:{direction}",
            "direction": direction,
            "metric_ready": True,
            "data_quality_status": "passed",
            "metric_quality_status": "passed",
            "triggered_periods": [],
            "all_trigger_periods": [],
            "primary_trigger_period": None,
            "period_escalation_trace": copy.deepcopy(period_escalation_trace),
            "ordinary_period_escalation_policy_version": "N4-ordinary-period-escalation-v2",
            "ordinary_period_escalation_policy_hash": "3a0aa136ff3393c7",
            "rule_proof": {
                "selected_metric": {"metric_ready": True},
                "period_evaluation_details": [
                    formal_period_detail(
                        period=period,
                        direction=direction,
                        classification="no_op",
                        current_transition="other",
                    )
                ],
            },
            "rule_eval_result": {
                "outcome_classification": "quality_blocked",
                "pending_reasons": [],
                "quality_reasons": [
                    "period_escalation_prerequisite_not_ready:Q",
                    "period_escalation_prerequisite_not_ready:Y",
                ],
                "blocked_reason": "period_escalation_prerequisite_not_ready:Q",
            },
        }
    )
    matched = plan(
        condition_key=f"{condition_prefix}:Y,Q,M,W,D",
        signal_type=signal_type,
        trigger_type=condition_prefix,
        trigger_period=period,
        triggered_periods=[period],
        primary_trigger_period=period,
        all_trigger_periods=[period],
    )
    matched.update(
        {
            "asset_kind": asset_kind,
            "identity_key": current["identity_key"],
            "direction": direction,
        }
    )
    prior = previous_state(matched)
    prior["raw_json"]["rule_proof"] = {
        "selected_metric": {"metric_ready": True},
        "period_evaluation_details": [
            formal_period_detail(
                period=period,
                direction=direction,
                classification="triggered",
                current_transition=target_transition,
            )
        ],
    }
    prior["raw_json"]["period_escalation_trace"] = copy.deepcopy(period_escalation_trace)
    prior["raw_json"]["ordinary_period_escalation_policy_version"] = (
        "N4-ordinary-period-escalation-v2"
    )
    prior["raw_json"]["ordinary_period_escalation_policy_hash"] = "3a0aa136ff3393c7"
    return current, prior


class ProvisionalTriggerLifecycleTest(unittest.TestCase):
    def test_inactive_to_matched_outputs_trigger_matched(self) -> None:
        outputs = build_lifecycle_output_plans([plan()], previous_states=[])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["output_event_type"], TRIGGER_MATCHED_EVENT_TYPE)
        self.assertTrue(outputs[0]["writes_trigger_match"])
        self.assertTrue(outputs[0]["n5_entry_allowed"])

    def test_matched_unchanged_outputs_noop(self) -> None:
        current = plan()

        outputs = build_lifecycle_output_plans([current], previous_states=[previous_state(current)])

        self.assertEqual(outputs, [])

    def test_matched_changed_outputs_state_changed_only(self) -> None:
        current = plan(projection_30m_type="volume_up", trigger_mark_candidate="30m_volume")
        prior = previous_state(current)
        prior["raw_json"]["projection_30m_type"] = "shrink_down"
        prior["raw_json"]["trigger_mark_candidate"] = "30m_shrink"

        outputs = build_lifecycle_output_plans([current], previous_states=[prior])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["output_event_type"], TRIGGER_STATE_CHANGED_EVENT_TYPE)
        self.assertFalse(outputs[0]["writes_trigger_match"])
        self.assertFalse(outputs[0]["n5_entry_allowed"])

    def test_matched_period_upgrade_outputs_state_changed_only(self) -> None:
        current = plan(
            trigger_period="W",
            triggered_periods=["W", "D"],
            primary_trigger_period="W",
            all_trigger_periods=["W", "D"],
            trigger_price="11.20",
        )
        prior_current = plan(
            trigger_period="D",
            triggered_periods=["D"],
            primary_trigger_period="D",
            all_trigger_periods=["D"],
            trigger_price="10.50",
        )

        outputs = build_lifecycle_output_plans([current], previous_states=[previous_state(prior_current)])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["output_event_type"], TRIGGER_STATE_CHANGED_EVENT_TYPE)
        self.assertEqual(outputs[0]["state_change_reason"], "matched_changed")
        self.assertEqual(outputs[0]["trigger_period"], "W")
        self.assertEqual(outputs[0]["triggered_periods"], ["W", "D"])
        self.assertEqual(outputs[0]["trigger_price"], "11.20")
        self.assertEqual(outputs[0]["primary_trigger_period"], "W")
        self.assertEqual(outputs[0]["all_trigger_periods"], ["W", "D"])
        self.assertFalse(outputs[0]["writes_trigger_match"])
        self.assertFalse(outputs[0]["n5_entry_allowed"])

    def test_same_day_v2_fields_survive_lifecycle_annotation_without_fallback(self) -> None:
        trace = {
            "policy_version": "N4-ordinary-period-escalation-v2",
            "policy_hash": "policy-hash",
            "direction": "buy",
            "same_day_formal_evidence": True,
            "periods": {
                "W": {
                    "evidence_source": "current_same_day_formal_pass",
                    "target_period": "W",
                    "prerequisite_period": "D",
                }
            },
        }
        current = plan(
            condition_key="BUY:W,D",
            signal_type="B_BUY",
            trigger_type="BUY",
            trigger_period="W",
            triggered_periods=["W"],
            primary_trigger_period="W",
            all_trigger_periods=["W", "D"],
            prerequisite_periods=["D"],
            period_escalation_trace=trace,
        )
        current["ordinary_period_escalation_policy_version"] = "N4-ordinary-period-escalation-v2"
        current["ordinary_period_escalation_policy_hash"] = "policy-hash"

        outputs = build_lifecycle_output_plans([current], previous_states=[])

        self.assertEqual(outputs[0]["triggered_periods"], ["W"])
        self.assertEqual(outputs[0]["all_trigger_periods"], ["W", "D"])
        self.assertEqual(outputs[0]["primary_trigger_period"], "W")
        self.assertEqual(outputs[0]["prerequisite_periods"], ["D"])
        self.assertEqual(outputs[0]["period_escalation_trace"], trace)
        self.assertEqual(
            outputs[0]["ordinary_period_escalation_policy_version"],
            "N4-ordinary-period-escalation-v2",
        )

    def test_matched_to_inactive_outputs_state_changed_only(self) -> None:
        current = plan(status="no_op")

        outputs = build_lifecycle_output_plans([current], previous_states=[previous_state(plan())])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["output_event_type"], TRIGGER_STATE_CHANGED_EVENT_TYPE)
        self.assertEqual(outputs[0]["current_status"], "inactive")
        self.assertFalse(outputs[0]["trigger_live"])
        self.assertEqual(outputs[0]["trigger_mark_candidate"], "normal")
        self.assertEqual(outputs[0]["previous_trigger_mark_candidate"], "30m_volume")
        self.assertFalse(outputs[0]["projection_30m_flag"])
        self.assertEqual(outputs[0]["projection_30m_type"], "none")
        self.assertFalse(outputs[0]["writes_trigger_match"])
        self.assertEqual(outputs[0]["state_change_reason"], "deactivated")
        self.assertEqual(outputs[0]["lifecycle_output_reason"], "matched_to_inactive")

    def test_matched_to_inactive_revalidates_buy_signal_type_alias(self) -> None:
        current = plan(condition_key="BUY:FULL", signal_type="BUY", trigger_type="BUY:FULL", status="no_op")
        prior = previous_state(plan(condition_key="BUY:FULL", signal_type="B_BUY", trigger_type="BUY:FULL"))

        outputs = build_lifecycle_output_plans([current], previous_states=[prior])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["output_event_type"], TRIGGER_STATE_CHANGED_EVENT_TYPE)
        self.assertEqual(outputs[0]["state_change_reason"], "deactivated")
        self.assertEqual(outputs[0]["lifecycle_output_reason"], "matched_to_inactive")
        self.assertEqual(outputs[0]["current_status"], "inactive")
        self.assertFalse(outputs[0]["trigger_live"])
        self.assertFalse(outputs[0]["writes_trigger_match"])
        self.assertFalse(outputs[0]["n5_entry_allowed"])

    def test_missing_or_unready_current_evidence_does_not_clear_live_state(self) -> None:
        current = plan(status="no_op")
        current["projection_status"] = "pending"
        current["projection_quality_status"] = "pending"
        current["trace_status"] = "pending"
        current["rule_proof"] = {"selected_metric": {"metric_ready": False}}
        prior = previous_state(plan())

        outputs = build_lifecycle_output_plans([current], previous_states=[prior])

        self.assertEqual(outputs, [])

    def test_scoped_deactivation_accepts_strict_formal_proof_across_periods_and_assets(self) -> None:
        cases = (
            ("D", "buy", "stock"),
            ("W", "sell", "index"),
            ("M", "buy", "board"),
            ("Q", "sell", "stock"),
            ("Y", "buy", "index"),
        )
        for period, direction, asset_kind in cases:
            with self.subTest(period=period, direction=direction, asset_kind=asset_kind):
                current, prior = scoped_deactivation_case(
                    period=period,
                    direction=direction,
                    asset_kind=asset_kind,
                )

                outputs = build_lifecycle_output_plans([current], previous_states=[prior])

                self.assertEqual(len(outputs), 1)
                self.assertEqual(outputs[0]["output_event_type"], TRIGGER_STATE_CHANGED_EVENT_TYPE)
                self.assertEqual(outputs[0]["current_status"], "inactive")
                self.assertFalse(outputs[0]["trigger_live"])
                self.assertEqual(outputs[0]["trigger_mark_candidate"], "normal")
                self.assertEqual(outputs[0]["previous_trigger_mark_candidate"], "30m_volume")
                self.assertFalse(outputs[0]["writes_trigger_match"])
                self.assertFalse(outputs[0]["n5_entry_allowed"])

    def test_scoped_deactivation_keeps_live_state_when_persistent_predicate_is_true(self) -> None:
        current, prior = scoped_deactivation_case()
        current_detail = current["rule_proof"]["period_evaluation_details"][0]
        current_detail["current_transition"] = "volume_up"

        outputs = build_lifecycle_output_plans([current], previous_states=[prior])

        self.assertEqual(outputs, [])

    def test_scoped_deactivation_accepts_canonical_not_seen_blocker(self) -> None:
        current, prior = scoped_deactivation_case()
        reason = "period_escalation_prerequisite_not_seen:Q"
        current["rule_eval_result"]["quality_reasons"] = [reason]
        current["rule_eval_result"]["blocked_reason"] = reason
        q_trace = current["period_escalation_trace"]["periods"]["Q"]
        q_trace.update(
            {
                "reason": reason,
                "gate_status": "not_seen",
            }
        )
        q_trace["source_entry"]["status"] = "not_seen"

        outputs = build_lifecycle_output_plans([current], previous_states=[prior])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["current_status"], "inactive")

    def test_scoped_deactivation_fails_closed_for_noncanonical_or_drifted_proof(self) -> None:
        def unknown_blocker(current: dict[str, object], prior: dict[str, object]) -> None:
            current["rule_eval_result"]["quality_reasons"] = ["source_hash_conflicting"]
            current["rule_eval_result"]["blocked_reason"] = "source_hash_conflicting"

        def pending_reason(current: dict[str, object], prior: dict[str, object]) -> None:
            current["rule_eval_result"]["pending_reasons"] = ["metric_pending"]

        def baseline_drift(current: dict[str, object], prior: dict[str, object]) -> None:
            current["rule_proof"]["period_evaluation_details"][0]["previous_amount_baseline"] = 101.0

        def missing_previous_detail(current: dict[str, object], prior: dict[str, object]) -> None:
            prior["raw_json"]["rule_proof"]["period_evaluation_details"] = []

        def duplicate_current_detail(current: dict[str, object], prior: dict[str, object]) -> None:
            current["rule_proof"]["period_evaluation_details"].append(
                copy.deepcopy(current["rule_proof"]["period_evaluation_details"][0])
            )

        def source_status_mismatch(current: dict[str, object], prior: dict[str, object]) -> None:
            current["rule_proof"]["period_evaluation_details"][0]["amount_source_status"] = {
                "status": "not_allowed"
            }

        def context_hash_drift(current: dict[str, object], prior: dict[str, object]) -> None:
            current["period_escalation_trace"]["context_hash"] = "drifted-context-hash"

        def period_window_drift(current: dict[str, object], prior: dict[str, object]) -> None:
            current["rule_proof"]["period_evaluation_details"][0][
                "baseline_period_key_current"
            ] = "drifted-window"

        def unknown_previous_period(current: dict[str, object], prior: dict[str, object]) -> None:
            prior["raw_json"]["triggered_periods"] = ["Z"]

        for name, mutate in (
            ("unknown_blocker", unknown_blocker),
            ("pending_reason", pending_reason),
            ("baseline_drift", baseline_drift),
            ("missing_previous_detail", missing_previous_detail),
            ("duplicate_current_detail", duplicate_current_detail),
            ("source_status_mismatch", source_status_mismatch),
            ("context_hash_drift", context_hash_drift),
            ("period_window_drift", period_window_drift),
            ("unknown_previous_period", unknown_previous_period),
        ):
            with self.subTest(name=name):
                current, prior = scoped_deactivation_case()
                mutate(current, prior)

                outputs = build_lifecycle_output_plans([current], previous_states=[prior])

                self.assertEqual(outputs, [])

    def test_inactive_to_inactive_drops_plan(self) -> None:
        outputs = build_lifecycle_output_plans([plan(status="no_op")], previous_states=[])

        self.assertEqual(outputs, [])

    def test_lifecycle_state_key_is_stable_for_trigger_contract_fields(self) -> None:
        key = lifecycle_state_key(plan())

        self.assertEqual(
            key,
            "20260625|stock|stock:SH:600000|B_BUY|BUY_HINT|BUY_HINT",
        )


if __name__ == "__main__":
    unittest.main()
