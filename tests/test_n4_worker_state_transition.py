import unittest

from ashare_v3.trigger.worker_state_transition import (
    build_transition_event_plans,
    source_event_consume_key,
    trigger_match_dedup_key,
    trigger_pending_dedup_key,
    trigger_state_changed_dedup_key,
    trigger_state_key,
)


def state(**overrides):
    row = {
        "trade_date": "20260608",
        "asset_kind": "stock",
        "identity_key": "stock:SZ:000001",
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": "BUY:D",
        "current_status": "inactive",
        "trigger_live": False,
        "primary_trigger_period": None,
        "all_trigger_periods": [],
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "trigger_mark_candidate": "normal",
        "data_quality_status": "passed",
    }
    row.update(overrides)
    return row


def evaluation(**overrides):
    row = state(
        current_status="matched",
        trigger_live=True,
        primary_trigger_period="D",
        all_trigger_periods=["D"],
        output_event_type="TriggerMatched",
        trigger_price=10.5,
        trigger_kind="trigger",
        n5_entry_allowed=True,
        match_basis="worker_smoke_fixture",
        source_market_event_or_projection_id="evt_source_1",
        new_trigger_fact=True,
    )
    row.update(overrides)
    return row


class N4WorkerStateTransitionTests(unittest.TestCase):
    def test_idempotency_keys_are_stable_and_separate(self):
        state_key = trigger_state_key(
            trade_date="20260608",
            asset_kind="stock",
            identity_key="stock:SZ:000001",
            direction="buy",
            signal_type="B_BUY",
            condition_key="BUY:D",
        )

        self.assertEqual(source_event_consume_key("n4_trigger_worker_v1", "evt_1"), "n4_trigger_worker_v1|evt_1")
        self.assertIn("stock:SZ:000001", state_key)
        self.assertNotEqual(
            trigger_match_dedup_key(
                trade_date="20260608",
                asset_kind="stock",
                identity_key="stock:SZ:000001",
                direction="buy",
                signal_type="B_BUY",
                condition_key="BUY:D",
                primary_trigger_period="D",
                trigger_mark_candidate="normal",
                match_basis="snapshot",
                source_market_event_or_projection_id="evt_1",
            ),
            trigger_pending_dedup_key(
                trade_date="20260608",
                asset_kind="stock",
                identity_key="stock:SZ:000001",
                direction="buy",
                signal_type="B_BUY",
                condition_key="BUY:D",
                expected_primary_trigger_period="D",
                trigger_mark_candidate="normal",
                missing_evidence_kind="projection_missing",
                source_market_event_or_projection_id="evt_1",
            ),
        )
        self.assertIn(
            "TriggerStateChanged",
            trigger_state_changed_dedup_key(
                state_key=state_key,
                previous_status="inactive",
                current_status="matched",
                previous_trigger_live=False,
                trigger_live=True,
                previous_primary_trigger_period=None,
                primary_trigger_period="D",
                previous_projection_30m_type="none",
                projection_30m_type="none",
                state_change_reason="activated",
                source_event_id="evt_1",
            ),
        )

    def test_pending_market_data_does_not_write_match_or_enter_n5(self):
        plans = build_transition_event_plans(
            previous_state=state(),
            current_evaluation=evaluation(
                current_status="pending_market_data",
                trigger_live=False,
                output_event_type="TriggerPendingMarketData",
                n5_entry_allowed=False,
                missing_evidence_kind="projection_missing",
                new_trigger_fact=False,
            ),
            source_event_id="evt_pending",
            trade_date="20260608",
        )

        pending = [plan for plan in plans if plan["output_event_type"] == "TriggerPendingMarketData"]
        state_changes = [plan for plan in plans if plan["output_event_type"] == "TriggerStateChanged"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(len(state_changes), 1)
        self.assertFalse(pending[0]["writes_common_trigger_match"])
        self.assertFalse(pending[0]["n5_entry_allowed"])
        self.assertFalse(pending[0]["trigger_live"])

    def test_pending_to_matched_emits_matched_and_state_changed(self):
        plans = build_transition_event_plans(
            previous_state=state(current_status="pending_market_data"),
            current_evaluation=evaluation(),
            source_event_id="evt_matched",
            trade_date="20260608",
        )

        self.assertEqual([plan["output_event_type"] for plan in plans], ["TriggerMatched", "TriggerStateChanged"])
        self.assertTrue(plans[0]["writes_common_trigger_match"])
        self.assertTrue(plans[0]["n5_entry_allowed"])
        self.assertEqual(plans[1]["state_change_reason"], "activated")
        self.assertFalse(plans[1]["writes_common_trigger_match"])
        self.assertFalse(plans[1]["is_n5_action_entry"])

    def test_matched_to_inactive_emits_state_changed_only(self):
        plans = build_transition_event_plans(
            previous_state=state(current_status="matched", trigger_live=True, primary_trigger_period="D", all_trigger_periods=["D"]),
            current_evaluation=evaluation(
                current_status="inactive",
                trigger_live=False,
                output_event_type=None,
                n5_entry_allowed=False,
                new_trigger_fact=False,
            ),
            source_event_id="evt_inactive",
            trade_date="20260608",
        )

        self.assertEqual([plan["output_event_type"] for plan in plans], ["TriggerStateChanged"])
        self.assertEqual(plans[0]["state_change_reason"], "deactivated")
        self.assertFalse(plans[0]["trigger_live"])

    def test_period_upgrade_and_projection_change_emit_one_state_change(self):
        previous = state(current_status="matched", trigger_live=True, primary_trigger_period="D", all_trigger_periods=["D"])

        upgraded = build_transition_event_plans(
            previous_state=previous,
            current_evaluation=evaluation(primary_trigger_period="W", all_trigger_periods=["W", "D"], new_trigger_fact=False),
            source_event_id="evt_upgrade",
            trade_date="20260608",
        )
        projection_changed = build_transition_event_plans(
            previous_state=previous,
            current_evaluation=evaluation(
                projection_30m_flag=True,
                projection_30m_type="volume_up",
                trigger_mark_candidate="30m_volume",
                new_trigger_fact=False,
            ),
            source_event_id="evt_projection",
            trade_date="20260608",
        )

        self.assertEqual([plan["output_event_type"] for plan in upgraded], ["TriggerStateChanged"])
        self.assertEqual(upgraded[0]["state_change_reason"], "period_upgrade")
        self.assertEqual([plan["output_event_type"] for plan in projection_changed], ["TriggerStateChanged"])
        self.assertEqual(projection_changed[0]["state_change_reason"], "projection_state_changed")

    def test_repeated_identical_state_evaluation_emits_no_event(self):
        previous = state(current_status="matched", trigger_live=True, primary_trigger_period="D", all_trigger_periods=["D"])
        plans = build_transition_event_plans(
            previous_state=previous,
            current_evaluation=evaluation(new_trigger_fact=False),
            source_event_id="evt_same",
            trade_date="20260608",
        )

        self.assertEqual(plans, [])


if __name__ == "__main__":
    unittest.main()
