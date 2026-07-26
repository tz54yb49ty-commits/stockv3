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
