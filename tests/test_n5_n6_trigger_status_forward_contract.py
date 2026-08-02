import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "N5_N6_TRIGGER_STATUS_FORWARD_CONTRACT_V1.md"
STATE_FLOW = ROOT / "docs" / "N4_N5_TRIGGER_ACTION_STATE_FLOW_v0.1.md"
ACTION_FLOW = ROOT / "docs" / "N5_CANONICAL_ACTION_FLOW_v0.1.md"
ARCHITECTURE = ROOT / "docs" / "Architecture.md"
TASKS = ROOT / "docs" / "Tasks.md"
GOVERNANCE = ROOT / "docs" / "N6_B_TRACK_DELIVERY_GOVERNANCE_V1.json"


class TriggerStatusForwardContractTests(unittest.TestCase):
    def test_trigger_status_contract_is_l2_without_one_off_policy(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        governance = GOVERNANCE.read_text(encoding="utf-8")

        self.assertIn("contract_version = N5-N6-trigger-status-forward-v1", text)
        self.assertIn("delivery_lane = n6_btrack_delivery_l2_n6_business_v1", text)
        self.assertIn("It does not create a one-off runtime policy", text)
        self.assertIn('"policy_id": "n6_btrack_delivery_l2_n6_business_v1"', governance)
        self.assertNotIn("n6_trigger_status_current_projection_bounded_run_once_v1", text)

    def test_status_messages_are_non_action_and_keep_action_outcomes_closed(self) -> None:
        contract = CONTRACT.read_text(encoding="utf-8")
        state_flow = STATE_FLOW.read_text(encoding="utf-8")
        action_flow = ACTION_FLOW.read_text(encoding="utf-8")

        for event_type in ("TriggerStatusUpdated", "TriggerStatusInvalidated"):
            self.assertIn(event_type, contract)
            self.assertIn(event_type, state_flow)
            self.assertIn(event_type, action_flow)

        for event_type in (
            "ActionEligible",
            "ActionBlocked",
            "ActionExecuted",
            "ActionSkipped",
        ):
            self.assertIn(event_type, contract)
            self.assertIn(event_type, action_flow)

        for marker in (
            "source_layer = N5_action",
            "message_role = n6_trigger_status_projection_only",
            "action_eligible_entry_allowed = false",
            "They must not write\n`common_action_event`",
            "enter the existing N6 signal/message/card projection consumer",
        ):
            self.assertIn(marker, contract)

    def test_status_payload_and_lifecycle_are_decision_complete(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        for field in (
            "contract_version",
            "operation",
            "trade_date",
            "tracking_state_key",
            "entry_trigger_event_id",
            "action_eligible_event_id",
            "source_trigger_event_id",
            "asset_kind",
            "identity_key",
            "asset_code",
            "asset_name",
            "direction",
            "signal_type",
            "condition_key",
            "trigger_time",
            "trigger_price",
            "trigger_pct",
            "trigger_period",
            "triggered_periods",
            "trigger_live",
            "current_status",
        ):
            self.assertIn(field, text)

        for rule in (
            "ActionEligible -> idempotent insert",
            "TriggerStatusUpdated -> update trigger_pct, trigger_price, trigger_period,",
            "TriggerStatusInvalidated -> delete the exact episode; missing delete is idempotent",
            "missing update target -> fail closed; do not advance inbox/checkpoint",
            "ActionExecuted -> no current-trigger-status mutation",
            "asset_kind + identity_key + direction",
        ):
            self.assertIn(rule, text)

    def test_architecture_and_tasks_register_the_isolated_status_branch(self) -> None:
        architecture = ARCHITECTURE.read_text(encoding="utf-8")
        tasks = TASKS.read_text(encoding="utf-8")

        self.assertIn(
            "n6_trigger_status_current (isolated L2 current-state read model)",
            architecture,
        )
        self.assertIn("T0.N5-N6-TRIGGER-STATUS", tasks)
        self.assertIn("N5_action 独立实现/离线测试", tasks)
        self.assertIn("N6_user 独立实现/PG16 测试", tasks)
        self.assertIn("首版禁止 scheduler、LaunchAgent、SSE、worker", tasks)


if __name__ == "__main__":
    unittest.main()
