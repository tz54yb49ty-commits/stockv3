from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from ashare_v3.ingestion.windows_n1_bootstrap import (
    N1_BOOTSTRAP_STAGES, BootstrapResult, WindowsN1BootstrapConfig,
    execute_bootstrap, run_security_items,
)


class WindowsN1BootstrapTest(unittest.TestCase):
    def test_exact_dag_has_no_calendar_or_downstream_stage(self):
        self.assertEqual(N1_BOOTSTRAP_STAGES[0], "schema")
        self.assertEqual(N1_BOOTSTRAP_STAGES[-1], "n1_data_ready")
        self.assertFalse({"trade_calendar", "calendar_repair", "n2", "n3", "n4", "n5", "n6"} & set(N1_BOOTSTRAP_STAGES))

    def test_finance_gate_fails_closed_without_fallback(self):
        handlers = {stage: (lambda result: None) for stage in N1_BOOTSTRAP_STAGES}
        with tempfile.TemporaryDirectory() as root:
            config = WindowsN1BootstrapConfig.for_today(artifact_root=Path(root), today=date(2026, 8, 26))
            with self.assertRaisesRegex(RuntimeError, "no fallback"):
                execute_bootstrap(config=config, stage_handlers=handlers)

    def test_successful_dag_reaches_n1_data_ready(self):
        handlers = {stage: (lambda result: None) for stage in N1_BOOTSTRAP_STAGES}
        handlers["eltdx_finance"] = lambda result: setattr(result, "finance_gate_passed", True)
        with tempfile.TemporaryDirectory() as root:
            result = execute_bootstrap(config=WindowsN1BootstrapConfig.for_today(artifact_root=Path(root), today=date(2026, 8, 26)), stage_handlers=handlers)
        self.assertTrue(result.n1_data_ready)

    def test_single_security_failure_writes_one_artifact_and_continues(self):
        seen = []
        def worker(symbol):
            seen.append(symbol)
            if symbol == "bad": raise ValueError("broken")
        with tempfile.TemporaryDirectory() as root:
            result = BootstrapResult(run_id="run1")
            run_security_items(items=["good1", "bad", "good2"], stage="daily", run_id="run1", artifact_root=Path(root), worker=worker, result=result)
            self.assertEqual(seen, ["good1", "bad", "good2"])
            self.assertEqual(len(result.security_failures), 1)
            self.assertTrue(Path(result.security_failures[0]["artifact"]).exists())


if __name__ == "__main__": unittest.main()
