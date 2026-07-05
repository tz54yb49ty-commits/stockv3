import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT_JSON = ROOT / "docs/V3_REALTIME_SIGNAL_ACTION_ENGINE_N3_N4_N5_CLOSEOUT.json"
CLOSEOUT_MD = ROOT / "docs/V3_REALTIME_SIGNAL_ACTION_ENGINE_N3_N4_N5_CLOSEOUT.md"


class V3RealtimeSignalActionEngineN3N4N5CloseoutTest(unittest.TestCase):
    def test_closeout_registers_completed_contracts_and_remaining_runner_blockers(self) -> None:
        closeout = json.loads(CLOSEOUT_JSON.read_text())

        self.assertEqual(closeout["result"], "CLOSEOUT_PASS")
        self.assertTrue(closeout["completed_stages"]["n3_metric_schema_contract"])
        self.assertTrue(closeout["completed_stages"]["n3_metric_builder"])
        self.assertTrue(closeout["completed_stages"]["n3_replay_validation"])
        self.assertTrue(closeout["completed_stages"]["n4_contract_alignment"])
        self.assertTrue(closeout["completed_stages"]["n5_contract_alignment"])
        self.assertTrue(closeout["completed_stages"]["run_once_wrapper_contract"])
        self.assertTrue(closeout["completed_stages"]["end_to_end_dry_run"])
        self.assertEqual(closeout["remaining_blockers"], [])
        self.assertIn("schema_migration_final_gate", closeout["remaining_production_execute_requirements"])
        self.assertIn("user_confirmed_execute_gate", closeout["remaining_production_execute_requirements"])

    def test_closeout_forbidden_scope_is_clean(self) -> None:
        closeout = json.loads(CLOSEOUT_JSON.read_text())
        forbidden = closeout["forbidden_scope_proof"]

        self.assertFalse(forbidden["database_written"])
        self.assertFalse(forbidden["scheduler_started"])
        self.assertFalse(forbidden["worker_started"])
        self.assertFalse(forbidden["n4_executed"])
        self.assertFalse(forbidden["n5_executed"])
        self.assertFalse(forbidden["n6_entered"])
        self.assertFalse(forbidden["voice_mobile_sim_trade_touched"])

    def test_closeout_markdown_contains_next_single_goal_prompt(self) -> None:
        md = CLOSEOUT_MD.read_text()

        self.assertIn("V3_REALTIME_SIGNAL_ACTION_ENGINE_N3_N4_N5_CLOSEOUT", md)
        self.assertIn("CLOSEOUT_PASS", md)
        self.assertIn("V3_REALTIME_SIGNAL_ACTION_RUNNER_IMPLEMENTATION_GATE", md)
        self.assertIn("不改 N4/N5 当前业务规则", md)


if __name__ == "__main__":
    unittest.main()
