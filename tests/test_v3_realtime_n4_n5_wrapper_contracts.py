import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
N4_JSON = ROOT / "docs/V3_REALTIME_METRIC_N4_CONTRACT_ALIGNMENT.json"
N4_MD = ROOT / "docs/V3_REALTIME_METRIC_N4_CONTRACT_ALIGNMENT.md"
N5_JSON = ROOT / "docs/V3_REALTIME_METRIC_N5_CONTRACT_ALIGNMENT.json"
N5_MD = ROOT / "docs/V3_REALTIME_METRIC_N5_CONTRACT_ALIGNMENT.md"
WRAPPER_JSON = ROOT / "docs/V3_REALTIME_SIGNAL_ACTION_RUN_ONCE_WRAPPER_CONTRACT.json"
WRAPPER_MD = ROOT / "docs/V3_REALTIME_SIGNAL_ACTION_RUN_ONCE_WRAPPER_CONTRACT.md"


class V3RealtimeN4N5WrapperContractsTest(unittest.TestCase):
    def test_n4_contract_uses_only_n3_standard_metric_inputs(self) -> None:
        contract = json.loads(N4_JSON.read_text())

        self.assertEqual(contract["result"], "ALIGNMENT_PASS")
        self.assertEqual(contract["layer_owner"], "N4_trigger")
        self.assertEqual(
            contract["canonical_outputs"],
            ["TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged"],
        )
        self.assertTrue(contract["input_policy"]["allow_n3_realtime_virtual_metric"])
        self.assertFalse(contract["input_policy"]["allow_raw_minute_rows"])
        self.assertFalse(contract["input_policy"]["allow_market_adapter_calls"])
        self.assertFalse(contract["input_policy"]["minute_bar_closed_required_for_fast_lane"])
        self.assertEqual(contract["quality_routes"]["metric_missing"], "TriggerPendingMarketData")
        self.assertEqual(contract["state_routes"]["matched_then_invalid"], "TriggerStateChanged(trigger_live=false)")

    def test_n5_contract_keeps_trigger_matched_as_only_entry(self) -> None:
        contract = json.loads(N5_JSON.read_text())

        self.assertEqual(contract["result"], "ALIGNMENT_PASS")
        self.assertEqual(contract["layer_owner"], "N5_action")
        self.assertEqual(contract["entry_event"], "TriggerMatched")
        self.assertEqual(
            contract["canonical_outputs"],
            ["ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped"],
        )
        self.assertTrue(contract["action_eligible"]["realtime_after_trigger_matched"])
        self.assertEqual(
            contract["action_executed"]["evidence"],
            "trigger_time_virtual_120m_30m_5m_plus_closed_trigger_minute_1m",
        )
        self.assertFalse(contract["forbidden_meanings"]["real_order"])
        self.assertFalse(contract["forbidden_meanings"]["sim_order"])
        self.assertFalse(contract["forbidden_meanings"]["n6_display"])
        self.assertEqual(contract["non_entry_events"], ["TriggerPendingMarketData", "TriggerStateChanged"])

    def test_wrapper_contract_is_plan_only_no_overlap_and_three_second_interval(self) -> None:
        contract = json.loads(WRAPPER_JSON.read_text())

        self.assertEqual(contract["result"], "CONTRACT_PASS")
        self.assertEqual(contract["runtime_model"], "launchd_StartInterval_3_run_once")
        self.assertTrue(contract["default_plan_only"])
        self.assertEqual(contract["execute_required_flags"], ["--execute", "--user-confirmed"])
        self.assertTrue(contract["no_overlap_lock"]["required"])
        self.assertFalse(contract["side_effects"]["scheduler_installed_or_enabled"])
        self.assertFalse(contract["side_effects"]["worker_started"])
        self.assertFalse(contract["side_effects"]["database_written"])
        self.assertFalse(contract["n6_voice_mobile_sim_trade_allowed"])

    def test_markdown_contracts_state_no_rule_change_and_no_n6(self) -> None:
        n4_md = N4_MD.read_text()
        n5_md = N5_MD.read_text()
        wrapper_md = WRAPPER_MD.read_text()

        self.assertIn("不改 N4 当前业务规则", n4_md)
        self.assertIn("N4 不直接读取 raw minute rows", n4_md)
        self.assertIn("不改 N5 当前业务规则", n5_md)
        self.assertIn("ActionExecuted 不代表真实下单", n5_md)
        self.assertIn("StartInterval=3", wrapper_md)
        self.assertIn("不进入 N6", wrapper_md)


if __name__ == "__main__":
    unittest.main()
