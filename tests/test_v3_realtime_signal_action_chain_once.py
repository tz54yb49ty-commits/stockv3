import json
import tempfile
import unittest
from pathlib import Path

import run_v3_realtime_signal_action_chain_once as chain


def replay_report():
    return {
        "result": "REPLAY_COMPARE_PASS",
        "trade_date": "20260612",
        "target_golden_counts": {"B_BUY": 76, "S_SELL": 24},
        "v3_replay_counts": {"B_BUY": 76, "S_SELL": 20},
        "metric_ready_counts": {"ready": 100},
        "diff_summary": {"matched": 96, "missing_in_v3": 4, "extra_in_v3": 0},
        "side_effects": {
            "target_machine_read_only": True,
            "database_written": False,
            "worker_started": False,
            "n6_entered": False,
            "voice_mobile_sim_trade_touched": False,
        },
    }


class V3RealtimeSignalActionChainOnceTest(unittest.TestCase):
    def test_plan_only_default_does_not_run_dry_run_or_write_database(self) -> None:
        report = chain.build_chain_report(replay_report(), execute=False, user_confirmed=False)

        self.assertEqual(report["result"], "PLAN_ONLY")
        self.assertFalse(report["execute"])
        self.assertFalse(report["child_invoked"])
        self.assertFalse(report["forbidden_scope_proof"]["database_written"])
        self.assertFalse(report["forbidden_scope_proof"]["n6_entered"])

    def test_execute_requires_user_confirmed(self) -> None:
        report = chain.build_chain_report(replay_report(), execute=True, user_confirmed=False)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "missing --user-confirmed")
        self.assertFalse(report["child_invoked"])

    def test_user_confirmed_requires_execute(self) -> None:
        report = chain.build_chain_report(replay_report(), execute=False, user_confirmed=True)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["blocked_reason"], "missing --execute")
        self.assertFalse(report["child_invoked"])

    def test_execute_dry_run_chains_n3_to_n4_to_n5_without_db_writes(self) -> None:
        report = chain.build_chain_report(replay_report(), execute=True, user_confirmed=True)

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["stages"]["n3_metric_replay"]["result"], "REPLAY_COMPARE_PASS")
        self.assertEqual(report["stages"]["n4_trigger_dry_run"]["TriggerMatched"], 96)
        self.assertEqual(report["stages"]["n4_trigger_dry_run"]["TriggerPendingMarketData"], 0)
        self.assertEqual(report["stages"]["n5_action_dry_run"]["ActionEligible"], 96)
        self.assertEqual(report["stages"]["n5_action_dry_run"]["ActionExecuted"], 96)
        self.assertEqual(report["stages"]["n5_action_dry_run"]["non_entry_events_ignored"], ["TriggerPendingMarketData", "TriggerStateChanged"])
        self.assertFalse(report["forbidden_scope_proof"]["database_written"])
        self.assertFalse(report["forbidden_scope_proof"]["scheduler_started"])
        self.assertFalse(report["forbidden_scope_proof"]["voice_mobile_sim_trade_touched"])

    def test_main_writes_json_and_markdown_reports_from_existing_replay_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            replay_path = root / "replay.json"
            json_path = root / "chain.json"
            md_path = root / "chain.md"
            replay_path.write_text(json.dumps(replay_report()), encoding="utf-8")

            exit_code = chain.main(
                [
                    "--replay-report-path",
                    str(replay_path),
                    "--json-report-path",
                    str(json_path),
                    "--markdown-report-path",
                    str(md_path),
                    "--execute",
                    "--user-confirmed",
                ]
            )

            self.assertEqual(exit_code, 0)
            report = json.loads(json_path.read_text())
            self.assertEqual(report["result"], "DRY_RUN_PASS")
            self.assertIn("N3 -> N4 -> N5", md_path.read_text())


if __name__ == "__main__":
    unittest.main()
