import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ashare_v3.runtime_control.fast_gate import (
    BLOCK,
    PASS,
    assert_fast_gate_payload,
    build_fast_gate_decision,
    mark_deferred_analysis,
    mark_repair_follow_up,
)
from ashare_v3.runtime_control.intraday import build_intraday_fast_gate
from ashare_v3.runtime_control.premarket import build_premarket_fast_gate


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH = f"{PROJECT_ROOT / 'src'}:{PROJECT_ROOT / 'scripts'}"


class RuntimeFastGateTest(unittest.TestCase):
    def test_fast_gate_payload_contains_only_result(self) -> None:
        decision = build_fast_gate_decision(blockers=[], failures=[])

        self.assertEqual(decision.result, PASS)
        self.assertEqual(decision.to_dict(), {"result": "PASS"})
        self.assertEqual(set(decision.to_dict()), {"result"})

    def test_fast_gate_blocks_without_explaining_analysis(self) -> None:
        decision = build_fast_gate_decision(blockers=["missing_rollback"], failures=[])

        self.assertEqual(decision.result, BLOCK)
        self.assertEqual(decision.to_dict(), {"result": "BLOCK"})
        self.assertNotIn("blockers", decision.to_dict())
        self.assertNotIn("analysis", decision.to_dict())
        self.assertNotIn("repair", decision.to_dict())

    def test_fast_gate_payload_rejects_expanded_analysis_keys(self) -> None:
        with self.assertRaises(ValueError):
            assert_fast_gate_payload({"result": "BLOCK", "blockers": ["missing_rollback"]})

    def test_deferred_analysis_is_marked_outside_fast_gate(self) -> None:
        report = {"result": "BLOCKED", "blockers": ["missing_rollback"], "stages": [{"stage_id": "n3"}]}

        deferred = mark_deferred_analysis(report)

        self.assertEqual(deferred["module_role"], "DEFERRED_ANALYSIS")
        self.assertEqual(deferred["result"], "BLOCKED")
        self.assertIn("blockers", deferred)

    def test_repair_follow_up_is_marked_outside_fast_gate(self) -> None:
        repair = mark_repair_follow_up("V3_REPAIR_GATE")

        self.assertEqual(repair["module_role"], "REPAIR_FOLLOW_UP")
        self.assertEqual(repair["next_gate"], "V3_REPAIR_GATE")
        self.assertFalse(repair["execute_in_fast_gate"])

    def test_premarket_fast_gate_omits_readiness_analysis(self) -> None:
        report = build_premarket_fast_gate(
            source_trade_date="20260529",
            for_trade_date="20260601",
            condition_run_id="condition_layer_20260529_source_20260529_v6",
            sql_dir=PROJECT_ROOT / "sql",
        )

        self.assertEqual(report, {"result": "PASS"})

    def test_premarket_fast_gate_blocks_missing_static_rollback_without_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sql_dir = Path(tmp)
            report = build_premarket_fast_gate(
                source_trade_date="20260529",
                for_trade_date="20260601",
                condition_run_id="condition_layer_20260529_source_20260529_v6",
                sql_dir=sql_dir,
            )

        self.assertEqual(report, {"result": "BLOCK"})
        self.assertEqual(json.dumps(report), '{"result": "BLOCK"}')

    def test_intraday_fast_gate_omits_readiness_analysis(self) -> None:
        report = build_intraday_fast_gate(
            for_trade_date="20260602",
            minute_label="1105",
            condition_run_id="condition_layer_20260601_source_20260601_v1",
            b1_label="live3_outbox",
            sql_dir=PROJECT_ROOT / "sql",
        )

        self.assertEqual(report, {"result": "PASS"})

    def test_intraday_fast_gate_blocks_invalid_run_id_without_details(self) -> None:
        report = build_intraday_fast_gate(
            for_trade_date="20260602",
            minute_label="1105",
            condition_run_id="bad_run_id",
            b1_label="live3_outbox",
            sql_dir=PROJECT_ROOT / "sql",
        )

        self.assertEqual(report, {"result": "BLOCK"})

    def test_premarket_cli_defaults_to_fast_gate_payload(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "plan_premarket_pipeline_readiness.py"),
                "--source-trade-date",
                "20260529",
                "--for-trade-date",
                "20260601",
                "--condition-run-id",
                "condition_layer_20260529_source_20260529_v6",
            ],
            check=True,
            capture_output=True,
            env={"PYTHONPATH": PYTHONPATH},
            text=True,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload, {"result": "PASS"})

    def test_premarket_cli_analysis_outputs_deferred_report(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "plan_premarket_pipeline_readiness.py"),
                "--source-trade-date",
                "20260529",
                "--for-trade-date",
                "20260601",
                "--condition-run-id",
                "condition_layer_20260529_source_20260529_v6",
                "--analysis",
                "--json",
            ],
            check=True,
            capture_output=True,
            env={"PYTHONPATH": PYTHONPATH},
            text=True,
        )

        payload = json.loads(completed.stdout)
        self.assertIn("stages", payload)
        self.assertIn("blockers", payload)
        self.assertIn("rollback_registry", payload)

    def test_intraday_cli_defaults_to_fast_gate_payload(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "plan_intraday_pipeline_readiness.py"),
                "--for-trade-date",
                "20260602",
                "--minute-label",
                "1105",
                "--condition-run-id",
                "condition_layer_20260601_source_20260601_v1",
                "--b1-label",
                "live3_outbox",
            ],
            check=True,
            capture_output=True,
            env={"PYTHONPATH": PYTHONPATH},
            text=True,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(payload, {"result": "PASS"})

    def test_intraday_cli_analysis_outputs_deferred_report(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "plan_intraday_pipeline_readiness.py"),
                "--for-trade-date",
                "20260602",
                "--minute-label",
                "1105",
                "--condition-run-id",
                "condition_layer_20260601_source_20260601_v1",
                "--b1-label",
                "live3_outbox",
                "--deferred-analysis",
                "--json",
            ],
            check=True,
            capture_output=True,
            env={"PYTHONPATH": PYTHONPATH},
            text=True,
        )

        payload = json.loads(completed.stdout)
        self.assertIn("stages", payload)
        self.assertIn("blockers", payload)
        self.assertIn("rollback_registry", payload)


if __name__ == "__main__":
    unittest.main()
