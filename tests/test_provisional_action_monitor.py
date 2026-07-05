import unittest

from ashare_v3.action.provisional_action_monitor import (
    build_monitor_window_id,
    build_provisional_action_monitor_plan,
)


def n4_event(
    index: int,
    *,
    event_type: str = "TriggerMatched",
    current_status: str = "matched",
    trigger_live: bool = True,
    trigger_period: str = "D",
    triggered_periods: list[str] | None = None,
) -> dict[str, object]:
    event_id = f"evt_n4_{index}"
    return {
        "event_id": event_id,
        "event_type": event_type,
        "source_run_id": "trigger_run",
        "trade_date": "20260625",
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "event_time": f"2026-06-25T10:{index:02d}:00+08:00",
        "payload_json": {
            "event_type": event_type,
            "run_id": "trigger_run",
            "source_condition_run_id": "condition_run",
            "source_trigger_state_id": 100 + index,
            "source_trigger_match_id": 200 + index if event_type == "TriggerMatched" else None,
            "identity_key": "stock:SH:600000",
            "asset_kind": "stock",
            "direction": "buy",
            "signal_type": "B_BUY",
            "condition_key": "BUY:D",
            "trigger_type": "BUY",
            "trigger_live": trigger_live,
            "current_status": current_status,
            "trigger_period": trigger_period,
            "triggered_periods": triggered_periods or [trigger_period],
            "all_trigger_periods": triggered_periods or [trigger_period],
            "primary_trigger_period": trigger_period,
            "trigger_price": "10.50" if trigger_period == "D" else "11.20",
            "trigger_mark_candidate": "normal",
            "n4_boundary": {"enters_n5": event_type == "TriggerMatched"},
        },
    }


def active_state(event: dict[str, object]) -> dict[str, object]:
    payload = event["payload_json"]
    if not isinstance(payload, dict):
        raise AssertionError("payload must be dict")
    return {
        "monitor_window_id": build_monitor_window_id(str(event["event_id"])),
        "for_trade_date": "20260625",
        "asset_kind": payload["asset_kind"],
        "identity_key": payload["identity_key"],
        "signal_type": payload["signal_type"],
        "condition_key": payload["condition_key"],
        "trigger_type": payload["trigger_type"],
        "tracking_status": "tracking",
        "trigger_live": True,
        "current_status": "matched",
        "latest_n4_event_id": event["event_id"],
        "last_seen_metric_key": None,
        "last_final_evaluated_metric_key": None,
        "raw_json": {"latest_trigger_context": payload},
    }


class ProvisionalActionMonitorTest(unittest.TestCase):
    def test_trigger_matched_creates_monitor_window_and_actioneligible_once(self) -> None:
        event = n4_event(3, event_type="TriggerMatched")

        plan = build_provisional_action_monitor_plan(
            n4_event_rows=[event],
            existing_tracking_states=[],
            existing_action_event_keys=set(),
            action_run_id="action_monitor_run",
            consumer_mode="outbox_consumer",
        )

        self.assertEqual(plan["event_counts"], {"ActionEligible": 1})
        self.assertEqual(plan["tracking_plan_counts"], {"create_window": 1})
        tracking = plan["tracking_state_plans"][0]
        eligible = plan["action_event_plans"][0]
        self.assertEqual(tracking["monitor_window_id"], build_monitor_window_id("evt_n4_3"))
        self.assertEqual(eligible["event_type"], "ActionEligible")
        self.assertEqual(eligible["monitor_window_id"], tracking["monitor_window_id"])
        self.assertEqual(eligible["action_state"], "eligible")
        self.assertEqual(eligible["confirmation_status"], "pending")

    def test_replayed_trigger_matched_does_not_duplicate_actioneligible(self) -> None:
        event = n4_event(3, event_type="TriggerMatched")
        existing_key = build_monitor_window_id("evt_n4_3")

        plan = build_provisional_action_monitor_plan(
            n4_event_rows=[event],
            existing_tracking_states=[active_state(event)],
            existing_action_event_keys={existing_key},
            action_run_id="action_monitor_run",
            consumer_mode="outbox_consumer",
        )

        self.assertEqual(plan["event_counts"], {})
        self.assertEqual(plan["tracking_plan_counts"], {"noop_existing_window": 1})

    def test_trigger_state_changed_updates_active_window_context_without_action_event(self) -> None:
        matched = n4_event(3, event_type="TriggerMatched", trigger_period="D")
        changed = n4_event(
            20,
            event_type="TriggerStateChanged",
            trigger_period="W",
            triggered_periods=["W", "D"],
        )

        plan = build_provisional_action_monitor_plan(
            n4_event_rows=[changed],
            existing_tracking_states=[active_state(matched)],
            existing_action_event_keys=set(),
            action_run_id="action_monitor_run",
            consumer_mode="outbox_consumer",
        )

        self.assertEqual(plan["event_counts"], {})
        self.assertEqual(plan["tracking_plan_counts"], {"update_context": 1})
        update = plan["tracking_state_plans"][0]
        self.assertEqual(update["latest_n4_event_id"], "evt_n4_20")
        self.assertEqual(update["trigger_period"], "W")
        self.assertEqual(update["triggered_periods"], ["W", "D"])
        self.assertEqual(update["trigger_price"], "11.20")

    def test_trigger_state_changed_inactive_expires_window_and_writes_one_actionskipped(self) -> None:
        matched = n4_event(3, event_type="TriggerMatched")
        inactive = n4_event(20, event_type="TriggerStateChanged", current_status="inactive", trigger_live=False)

        plan = build_provisional_action_monitor_plan(
            n4_event_rows=[inactive],
            existing_tracking_states=[active_state(matched)],
            existing_action_event_keys=set(),
            action_run_id="action_monitor_run",
            consumer_mode="outbox_consumer",
        )

        self.assertEqual(plan["event_counts"], {"ActionSkipped": 1})
        self.assertEqual(plan["tracking_plan_counts"], {"expire_window": 1})
        skipped = plan["action_event_plans"][0]
        self.assertEqual(skipped["event_type"], "ActionSkipped")
        self.assertEqual(skipped["action_state"], "expired")
        self.assertEqual(skipped["reason"], "trigger_live_false")

    def test_direct_replay_mode_does_not_write_inbox_or_checkpoint(self) -> None:
        plan = build_provisional_action_monitor_plan(
            n4_event_rows=[n4_event(3)],
            existing_tracking_states=[],
            existing_action_event_keys=set(),
            action_run_id="action_monitor_run",
            consumer_mode="direct_source_replay_no_inbox_checkpoint",
        )

        self.assertFalse(plan["side_effect_guard"]["inbox_written"])
        self.assertFalse(plan["side_effect_guard"]["checkpoint_written"])


if __name__ == "__main__":
    unittest.main()
