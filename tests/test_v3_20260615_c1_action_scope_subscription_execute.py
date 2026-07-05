from __future__ import annotations

from pathlib import Path
import tempfile
import unittest


class V320260615C1ActionScopeSubscriptionExecuteTests(unittest.TestCase):
    def _minimal_dry_run(self) -> dict:
        return {
            "stage": "V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_CONTROL_ROW_DRY_RUN",
            "mode": "dry_run",
            "blocked": False,
            "passed": True,
            "market_data_run_id": "market_data_subscription_20260615_action_confirmation_c1_1005_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1",
            "source_condition_run_id": "condition_layer_20260612_source_20260612_for_20260615_v1",
            "for_trade_date": "20260615",
            "source_trade_date": "20260612",
            "prev_trade_date": "20260612",
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
            "market_data_subscription_candidate": {"rows_included": True, "row_count": 0, "rows": []},
            "market_data_subscription_dedup": {"rows_included": True, "row_count": 0, "rows": []},
            "market_data_pull_plan": {"rows_included": True, "row_count": 0, "rows": []},
        }

    def test_validate_scoped_dry_run_accepts_reviewed_stage(self) -> None:
        from ashare_v3.market.v3_20260615_c1_action_scope_subscription_execute import (
            validate_scoped_subscription_dry_run,
        )

        validate_scoped_subscription_dry_run(self._minimal_dry_run())

    def test_validate_scoped_dry_run_rejects_wrong_run_id(self) -> None:
        from ashare_v3.market.v3_20260615_c1_action_scope_subscription_execute import (
            validate_scoped_subscription_dry_run,
        )

        report = self._minimal_dry_run()
        report["market_data_run_id"] = "wrong"
        with self.assertRaisesRegex(RuntimeError, "run_id mismatch"):
            validate_scoped_subscription_dry_run(report)

    def test_execute_requires_flags_before_dry_run_file_read(self) -> None:
        from ashare_v3.market.v3_20260615_c1_action_scope_subscription_execute import (
            run_scoped_subscription_execute,
        )

        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            with self.assertRaisesRegex(RuntimeError, "missing --execute"):
                run_scoped_subscription_execute(
                    dsn="postgresql://invalid",
                    dry_run_path=str(missing),
                    json_report_path=str(Path(tmp) / "r.json"),
                    markdown_report_path=str(Path(tmp) / "r.md"),
                    execute=False,
                    user_confirmed=True,
                )

    def test_subscription_raw_json_preserves_source_trace(self) -> None:
        from ashare_v3.market.subscription_execute import build_candidate_raw_json

        raw = build_candidate_raw_json(
            {
                "candidate_ref": "dry_run:candidate:1",
                "source_scope_ref": "stock_minute_target_scope:1",
                "run_id": "dry_run_id",
                "raw_json": {"source_trigger_match_id": 123, "source_trigger_run_id": "n4_run"},
            }
        )
        self.assertEqual(raw["source_trace"]["source_trigger_match_id"], 123)
        self.assertEqual(raw["source_trace"]["source_trigger_run_id"], "n4_run")


if __name__ == "__main__":
    unittest.main()
