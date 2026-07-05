from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import run_market_data_subscription_control_from_dry_run_once as runner


class MarketDataSubscriptionControlFromDryRunTests(unittest.TestCase):
    def test_execute_requires_flag_before_reading_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            with self.assertRaisesRegex(RuntimeError, "missing --execute"):
                runner.run_subscription_control_from_dry_run(
                    dsn="postgresql://invalid",
                    dry_run_path=str(missing),
                    json_report_path=str(Path(tmp) / "report.json"),
                    markdown_report_path=str(Path(tmp) / "report.md"),
                    execute=False,
                    user_confirmed=True,
                )

    def test_validate_dry_run_rejects_mutating_or_wrong_layer_payloads(self) -> None:
        report = {
            "mode": "dry_run",
            "layer_role": "N4_trigger",
            "blocked": False,
            "passed": True,
            "quality": {"p0_count": 0},
            "side_effects": {"market_data_pulled": False},
            "market_data_subscription_candidate": {"rows_included": True, "row_count": 0, "rows": []},
            "market_data_subscription_dedup": {"rows_included": True, "row_count": 0, "rows": []},
            "market_data_pull_plan": {"rows_included": True, "row_count": 0, "rows": []},
        }
        with self.assertRaisesRegex(RuntimeError, "layer_role"):
            runner.validate_dry_run(report)
        report["layer_role"] = "N3_market_data"
        report["side_effects"] = {"market_data_pulled": True}
        with self.assertRaisesRegex(RuntimeError, "pulled market data"):
            runner.validate_dry_run(report)


if __name__ == "__main__":
    unittest.main()
