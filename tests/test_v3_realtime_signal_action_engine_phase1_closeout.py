import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT_JSON = ROOT / "docs/V3_REALTIME_SIGNAL_ACTION_ENGINE_PHASE1_CLOSEOUT.json"
CLOSEOUT_MD = ROOT / "docs/V3_REALTIME_SIGNAL_ACTION_ENGINE_PHASE1_CLOSEOUT.md"


class V3RealtimeSignalActionEnginePhase1CloseoutTest(unittest.TestCase):
    def test_phase1_closeout_registers_completed_scope_without_overclaiming_execute_ready(self) -> None:
        closeout = json.loads(CLOSEOUT_JSON.read_text())

        self.assertEqual(closeout["result"], "PHASE1_CLOSEOUT_PASS")
        self.assertTrue(closeout["completed_scope"]["executable_plan"])
        self.assertTrue(closeout["completed_scope"]["n3_metric_schema_contract"])
        self.assertTrue(closeout["completed_scope"]["n3_metric_pure_builder"])
        self.assertTrue(closeout["completed_scope"]["target_machine_replay_compare_20260612"])
        self.assertFalse(closeout["execute_readiness"]["schema_migration_executed"])
        self.assertFalse(closeout["execute_readiness"]["n3_runner_wired"])
        self.assertFalse(closeout["execute_readiness"]["n4_runner_wired"])
        self.assertFalse(closeout["execute_readiness"]["n5_runner_wired"])
        self.assertEqual(closeout["execute_readiness"]["overall"], "NOT_YET_EXECUTE_READY")

    def test_phase1_closeout_preserves_forbidden_scope(self) -> None:
        closeout = json.loads(CLOSEOUT_JSON.read_text())
        forbidden = closeout["forbidden_scope_proof"]

        self.assertFalse(forbidden["database_written"])
        self.assertFalse(forbidden["scheduler_started"])
        self.assertFalse(forbidden["worker_started"])
        self.assertFalse(forbidden["n4_executed"])
        self.assertFalse(forbidden["n5_executed"])
        self.assertFalse(forbidden["n6_entered"])
        self.assertFalse(forbidden["voice_mobile_sim_trade_touched"])

    def test_markdown_states_next_gate_and_no_business_rule_change(self) -> None:
        md = CLOSEOUT_MD.read_text()

        self.assertIn("PHASE1_CLOSEOUT_PASS", md)
        self.assertIn("不改 N4/N5 当前业务规则", md)
        self.assertIn("NOT_YET_EXECUTE_READY", md)
        self.assertIn("V3_REALTIME_VIRTUAL_METRIC_RUNNER_CONTRACT_PREFLIGHT_GATE", md)


if __name__ == "__main__":
    unittest.main()
