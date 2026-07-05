from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.market.scoped_subscription_control_execute import (
    ScopedSubscriptionControlExecuteBlocked,
    normalize_candidate_directions,
    run_scoped_subscription_control_execute,
    validate_scoped_control_manifest,
)


def _manifest() -> dict:
    return {
        "mode": "dry_run",
        "passed": True,
        "blocked": False,
        "market_data_run_id": "market_data_subscription_scoped_manifest",
        "source_condition_run_id": "condition_layer",
        "source_trade_date": "20260615",
        "for_trade_date": "20260616",
        "prev_trade_date": "20260615",
        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
        "allowed_write_tables": [
            "common_market_data_run",
            "common_market_data_quality_item",
            "common_market_data_subscription_candidate",
            "common_market_data_subscription",
            "common_market_data_pull_plan",
        ],
        "market_data_subscription_candidate": {"rows_included": True, "row_count": 0, "rows": []},
        "market_data_subscription_dedup": {"rows_included": True, "row_count": 0, "rows": []},
        "market_data_pull_plan": {"rows_included": True, "row_count": 0, "rows": []},
    }


class V3ScopedSubscriptionControlExecuteTests(unittest.TestCase):
    def test_validate_manifest_accepts_reviewed_control_rows(self) -> None:
        validate_scoped_control_manifest(_manifest(), expected_run_id="market_data_subscription_scoped_manifest")

    def test_validate_manifest_rejects_replan_or_fact_write_scope(self) -> None:
        report = _manifest()
        report["allowed_write_tables"].append("stock_minute_bar_1m")
        with self.assertRaisesRegex(ScopedSubscriptionControlExecuteBlocked, "control-only"):
            validate_scoped_control_manifest(report)

    def test_validate_manifest_rejects_missing_rows(self) -> None:
        report = _manifest()
        report["market_data_subscription_candidate"]["rows_included"] = False
        with self.assertRaisesRegex(ScopedSubscriptionControlExecuteBlocked, "rows missing"):
            validate_scoped_control_manifest(report)

    def test_validate_manifest_rejects_pull_plan_execute_allowed(self) -> None:
        report = _manifest()
        report["market_data_pull_plan"] = {
            "rows_included": True,
            "row_count": 1,
            "rows": [{"execute_allowed": True}],
        }
        with self.assertRaisesRegex(ScopedSubscriptionControlExecuteBlocked, "execute_allowed"):
            validate_scoped_control_manifest(report)

    def test_normalize_candidate_directions_expands_mixed_candidate_rows(self) -> None:
        report = _manifest()
        report["subscription_row_count"] = 1
        report["candidate_row_count"] = 1
        report["subscription_candidate_count"] = 1
        report["planned_rows"] = {"candidate": 1, "subscription": 1, "pull_plan": 0}
        report["market_data_subscription_candidate"] = {
            "rows_included": True,
            "row_count": 1,
            "rows": [
                {
                    "candidate_ref": "candidate:1",
                    "source_scope_table": "stock_minute_target_scope",
                    "source_scope_id": 10,
                    "source_condition_pool_id": 20,
                    "direction": "mixed",
                    "condition_key": "BUY:D,SELL:D",
                    "allowed_signal_types": ["BUY", "SELL"],
                    "raw_json": {
                        "source_trigger_context_condition_keys": ["BUY:D", "SELL:D"],
                        "all_source_scope_ids": [10, 11],
                        "all_source_condition_pool_ids": [20, 21],
                    },
                }
            ],
        }

        normalized = normalize_candidate_directions(report)

        rows = normalized["market_data_subscription_candidate"]["rows"]
        self.assertEqual(normalized["candidate_row_count"], 2)
        self.assertEqual(normalized["subscription_candidate_count"], 2)
        self.assertEqual(normalized["planned_rows"]["candidate"], 2)
        self.assertEqual([row["direction"] for row in rows], ["buy", "sell"])
        self.assertEqual([row["condition_key"] for row in rows], ["BUY:D", "SELL:D"])
        self.assertEqual([row["allowed_signal_types"] for row in rows], [["BUY"], ["SELL"]])
        self.assertEqual([row["source_scope_id"] for row in rows], [10, 11])
        self.assertEqual([row["source_condition_pool_id"] for row in rows], [20, 21])
        self.assertTrue(normalized["candidate_direction_normalization"]["applied"])

    def test_validate_manifest_rejects_unexpanded_noncanonical_direction(self) -> None:
        report = _manifest()
        report["market_data_subscription_candidate"] = {
            "rows_included": True,
            "row_count": 1,
            "rows": [{"direction": "mixed"}],
        }
        with self.assertRaisesRegex(ScopedSubscriptionControlExecuteBlocked, "candidate direction"):
            validate_scoped_control_manifest(report)

    def test_plan_only_does_not_touch_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dry = Path(tmp) / "dry.json"
            out = Path(tmp) / "report.json"
            md = Path(tmp) / "report.md"
            dry.write_text(json.dumps(_manifest()), encoding="utf-8")
            report = run_scoped_subscription_control_execute(
                dsn="postgresql://must-not-be-used",
                dry_run_path=dry,
                json_report_path=out,
                markdown_report_path=md,
            )
            self.assertEqual(report["result"], "PLAN_ONLY")
            self.assertFalse(report["database_written"])
            self.assertEqual(json.loads(out.read_text())["result"], "PLAN_ONLY")

    def test_half_confirmed_blocks_before_file_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ScopedSubscriptionControlExecuteBlocked, "missing --user-confirmed"):
                run_scoped_subscription_control_execute(
                    dsn="postgresql://must-not-be-used",
                    dry_run_path=Path(tmp) / "missing.json",
                    json_report_path=Path(tmp) / "report.json",
                    markdown_report_path=Path(tmp) / "report.md",
                    execute=True,
                    user_confirmed=False,
                )


if __name__ == "__main__":
    unittest.main()
