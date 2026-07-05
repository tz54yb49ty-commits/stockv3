from __future__ import annotations

from pathlib import Path
import tempfile
import unittest


class V320260615C1ActionScopeMergedSubscriptionExecuteTests(unittest.TestCase):
    def _minimal_dry_run(self) -> dict:
        return {
            "stage": "V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_MERGED_SUBSCRIPTION_CONTROL_ROW_DRY_RUN",
            "mode": "dry_run",
            "blocked": False,
            "passed": True,
            "market_data_run_id": (
                "market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__"
                "n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1"
            ),
            "source_condition_run_id": "condition_layer_20260612_source_20260612_for_20260615_v1",
            "for_trade_date": "20260615",
            "source_trade_date": "20260612",
            "prev_trade_date": "20260612",
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
            "market_data_subscription_candidate": {"rows_included": True, "row_count": 0, "rows": []},
            "market_data_subscription_dedup": {"rows_included": True, "row_count": 0, "rows": []},
            "market_data_pull_plan": {"rows_included": True, "row_count": 0, "rows": []},
        }

    def test_validate_merged_dry_run_accepts_reviewed_stage(self) -> None:
        from ashare_v3.market.v3_20260615_c1_action_scope_merged_subscription_execute import (
            validate_merged_subscription_dry_run,
        )

        validate_merged_subscription_dry_run(self._minimal_dry_run())

    def test_validate_merged_dry_run_rejects_gap_stage(self) -> None:
        from ashare_v3.market.v3_20260615_c1_action_scope_merged_subscription_execute import (
            validate_merged_subscription_dry_run,
        )

        report = self._minimal_dry_run()
        report["stage"] = "V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_CONTROL_ROW_DRY_RUN"
        with self.assertRaisesRegex(RuntimeError, "stage mismatch"):
            validate_merged_subscription_dry_run(report)

    def test_validate_merged_dry_run_rejects_wrong_run_id(self) -> None:
        from ashare_v3.market.v3_20260615_c1_action_scope_merged_subscription_execute import (
            validate_merged_subscription_dry_run,
        )

        report = self._minimal_dry_run()
        report["market_data_run_id"] = "wrong"
        with self.assertRaisesRegex(RuntimeError, "run_id mismatch"):
            validate_merged_subscription_dry_run(report)

    def test_execute_requires_flags_before_dry_run_file_read(self) -> None:
        from ashare_v3.market.v3_20260615_c1_action_scope_merged_subscription_execute import (
            run_merged_subscription_execute,
        )

        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            with self.assertRaisesRegex(RuntimeError, "missing --execute"):
                run_merged_subscription_execute(
                    dsn="postgresql://invalid",
                    dry_run_path=str(missing),
                    json_report_path=str(Path(tmp) / "r.json"),
                    markdown_report_path=str(Path(tmp) / "r.md"),
                    execute=False,
                    user_confirmed=True,
                )

    def test_rollback_sql_hard_fails_before_delete_and_scopes_merged_run_only(self) -> None:
        sql_path = Path("sql/V3_20260615_c1_action_confirmation_scope_merged_subscription_control_rollback.sql")
        sql = sql_path.read_text()
        self.assertLess(sql.index("RAISE EXCEPTION 'HARD_FAIL"), sql.index("DELETE FROM"))
        self.assertNotIn("DROP ", sql.upper())
        self.assertNotIn("TRUNCATE", sql.upper())
        self.assertNotIn("CASCADE", sql.upper())
        for table in (
            "common_market_data_pull_plan",
            "common_market_data_subscription",
            "common_market_data_subscription_candidate",
            "common_market_data_quality_item",
            "common_market_data_run",
        ):
            self.assertIn(f"DELETE FROM {table} WHERE run_id =", sql)
        self.assertIn("market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__", sql)
        self.assertIn("today_minute_bar_1m_20260615_until_1005_action_confirmation_scope__", sql)
        self.assertNotIn(
            "DELETE FROM stock_minute_bar_1m",
            sql,
        )
        self.assertNotIn(
            "DELETE FROM common_event_outbox",
            sql,
        )


if __name__ == "__main__":
    unittest.main()
