import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ashare_v3.market.full_context_expansion_subscription_plan import (
    EXPANSION_SUBSCRIPTION_RUN_ID,
    build_full_context_expansion_subscription_scope_report,
    build_expansion_pull_plan_rows,
    build_expansion_subscription_candidates,
    build_subscription_expansion_rollback_sql,
    deduplicate_expansion_candidates,
    run_full_context_expansion_subscription_execute,
)


class FullContextExpansionSubscriptionPlanTest(unittest.TestCase):
    def _source_runs(self) -> dict[str, dict[str, str]]:
        return {
            "source_condition": {
                "run_id": "condition_layer_20260618_source_20260618_for_20260622_v1",
                "status": "passed",
                "source_trade_date": "20260618",
                "for_trade_date": "20260622",
                "prev_trade_date": "20260618",
            },
            "source_subscription": {
                "run_id": "market_data_subscription_20260622_condition_layer_20260618_source_20260618_for_20260622_v1",
                "status": "passed",
            },
            "source_snapshot": {
                "run_id": "realtime_daily_snapshot_20260622_until_1013__market_data_subscription_20260622_condition_layer_20260618_source_20260618_for_20260622_v1",
                "status": "passed",
            },
            "trigger_context": {
                "run_id": "trigger_context_snapshot_20260622_condition_layer_20260618_source_20260618_for_20260622_v1",
                "status": "passed",
            },
        }

    def _context_row(self, asset_kind: str, identity_key: str, scope_id: int, *, direction: str = "buy") -> dict[str, object]:
        return {
            "trigger_context_id": scope_id + 1000,
            "source_scope_table": f"{asset_kind}_minute_target_scope",
            "source_minute_target_scope_id": scope_id,
            "source_condition_pool_id": scope_id + 2000,
            "source_condition_run_id": "condition_layer_20260618_source_20260618_for_20260622_v1",
            "for_trade_date": "20260622",
            "source_trade_date": "20260618",
            "prev_trade_date": "20260618",
            "previous_day_minute_date": "20260618",
            "asset_kind": asset_kind,
            "identity_key": identity_key,
            "exchange": identity_key.split(":")[1],
            "code": identity_key.split(":")[2],
            "display_code": identity_key.split(":")[2],
            "name": identity_key,
            "direction": direction,
            "condition_key": "BUY:D" if direction == "buy" else "SELL:D",
            "allowed_signal_types": ["B_BUY"] if direction == "buy" else ["S_SELL"],
        }

    def _report(
        self,
        *,
        scope_mode: str,
        context_rows_by_asset: dict[str, list[dict[str, object]]],
        existing: dict[str, dict[str, set[str]]] | None = None,
        baseline: dict[str, int] | None = None,
        source_runs: dict[str, dict[str, str] | None] | None = None,
    ) -> dict[str, object]:
        return build_full_context_expansion_subscription_scope_report(
            expansion_run_id="market_data_subscription_20260622_full_context_expansion_condition_layer_20260618_source_20260618_for_20260622_v1",
            for_trade_date="20260622",
            source_condition_run_id="condition_layer_20260618_source_20260618_for_20260622_v1",
            source_subscription_run_id="market_data_subscription_20260622_condition_layer_20260618_source_20260618_for_20260622_v1",
            source_snapshot_run_id="realtime_daily_snapshot_20260622_until_1013__market_data_subscription_20260622_condition_layer_20260618_source_20260618_for_20260622_v1",
            trigger_context_run_id="trigger_context_snapshot_20260622_condition_layer_20260618_source_20260618_for_20260622_v1",
            scope_mode=scope_mode,
            target_db={},
            source_runs=source_runs if source_runs is not None else self._source_runs(),
            context_rows_by_asset=context_rows_by_asset,
            existing_subscription_identity_keys=existing
            if existing is not None
            else {"minute_bar_1m": {}, "previous_day_minute_bar_1m": {}},
            baseline=baseline
            if baseline is not None
            else {
                "common_market_data_run": 0,
                "common_market_data_quality_item": 0,
                "common_market_data_subscription_candidate": 0,
                "common_market_data_subscription": 0,
                "common_market_data_pull_plan": 0,
                "common_event_outbox_refs": 0,
                "common_event_inbox_refs": 0,
                "common_event_consumer_checkpoint_refs": 0,
            },
            event_global_counts={},
            include_rows=True,
        )

    def test_full_context_all_plans_today_and_previous_day_for_all_context_identities(self) -> None:
        context_rows_by_asset = {
            "stock": [
                self._context_row("stock", "stock:SH:600000", 1, direction="buy"),
                self._context_row("stock", "stock:SH:600000", 2, direction="sell"),
            ],
            "index": [self._context_row("index", "index:SH:000001", 3)],
            "board": [self._context_row("board", "board:TDX:880001", 4)],
        }
        report = self._report(scope_mode="full-context-all", context_rows_by_asset=context_rows_by_asset)

        self.assertFalse(report["blocked"])
        self.assertEqual(report["scope_mode"], "full-context-all")
        self.assertEqual(report["context_rows_by_asset_kind"], {"stock": 2, "index": 1, "board": 1})
        self.assertEqual(report["context_identity_count_by_asset_kind"], {"stock": 1, "index": 1, "board": 1})
        self.assertEqual(report["expansion_identity_count_by_asset_kind"], {"stock": 1, "index": 1, "board": 1})
        self.assertEqual(report["today_minute_subscription_rows_planned"], 3)
        self.assertEqual(report["previous_day_minute_subscription_rows_planned"], 3)
        self.assertEqual(report["candidate_row_count_by_required_data_kind"], {"minute_bar_1m": 4, "previous_day_minute_bar_1m": 4})
        self.assertEqual(report["required_data_kind_counts"], {"minute_bar_1m": 3, "previous_day_minute_bar_1m": 3})
        self.assertEqual(report["market_data_pull_plan_row_count"], 6)

    def test_gap_only_excludes_identities_that_already_have_today_and_previous_day_minute_scope(self) -> None:
        context_rows_by_asset = {
            "stock": [
                self._context_row("stock", "stock:SH:600000", 1),
                self._context_row("stock", "stock:SH:600001", 2),
            ],
            "index": [],
            "board": [self._context_row("board", "board:TDX:880001", 3)],
        }
        existing = {
            "minute_bar_1m": {"stock": {"stock:SH:600000"}},
            "previous_day_minute_bar_1m": {"stock": {"stock:SH:600000"}},
        }
        report = self._report(scope_mode="gap-only", context_rows_by_asset=context_rows_by_asset, existing=existing)

        self.assertFalse(report["blocked"])
        self.assertEqual(report["scope_mode"], "gap-only")
        self.assertEqual(report["current_minute_subscription_identity_count_by_asset_kind"], {"stock": 1, "index": 0, "board": 0})
        self.assertEqual(report["expansion_identity_count_by_asset_kind"], {"stock": 1, "index": 0, "board": 1})
        self.assertEqual(report["candidate_row_count_by_required_data_kind"], {"minute_bar_1m": 2, "previous_day_minute_bar_1m": 2})
        rows = report["market_data_subscription_candidate"]["rows"]
        self.assertNotIn("stock:SH:600000", {row["identity_key"] for row in rows})

    def test_existing_expansion_run_id_blocks_plan(self) -> None:
        report = self._report(
            scope_mode="full-context-all",
            context_rows_by_asset={"stock": [self._context_row("stock", "stock:SH:600000", 1)], "index": [], "board": []},
            baseline={"common_market_data_run": 1},
        )

        self.assertTrue(report["blocked"])
        self.assertIn("n3_c1_full_context_expansion_subscription_baseline_zero", report["blockers"])

    def test_missing_context_run_blocks_plan(self) -> None:
        source_runs = self._source_runs()
        source_runs["trigger_context"] = None
        report = self._report(
            scope_mode="full-context-all",
            context_rows_by_asset={"stock": [], "index": [], "board": []},
            source_runs=source_runs,
        )

        self.assertTrue(report["blocked"])
        self.assertIn("n3_c1_full_context_expansion_trigger_context_run_ready", report["blockers"])
        self.assertIn("n3_c1_full_context_expansion_candidate_rows_nonzero", report["blockers"])

    def test_candidates_use_original_minute_target_scope_tables(self) -> None:
        rows = [
            {
                "source_scope_table": "stock_minute_target_scope",
                "source_scope_id": 101,
                "source_condition_pool_id": 201,
                "for_trade_date": "20260603",
                "source_trade_date": "20260602",
                "prev_trade_date": "20260602",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "exchange": "SH",
                "code": "600000",
                "display_code": "600000",
                "name": "sample",
                "direction": "buy",
                "condition_key": "B_BUY",
                "allowed_signal_types": ["BUY"],
                "trigger_context_ref": "stock_trigger_context_snapshot:1",
            }
        ]
        candidates = build_expansion_subscription_candidates(
            market_data_run_id=EXPANSION_SUBSCRIPTION_RUN_ID,
            gap_rows=rows,
        )
        self.assertEqual(candidates[0]["source_scope_table"], "stock_minute_target_scope")
        self.assertEqual(candidates[0]["source_scope_id"], 101)
        self.assertEqual(candidates[0]["required_data_kind"], "minute_bar_1m")
        self.assertTrue(candidates[0]["source_scope_required_flags"]["full_context_expansion"])

    def test_dedup_keeps_unique_identity_subscription(self) -> None:
        base = {
            "run_id": EXPANSION_SUBSCRIPTION_RUN_ID,
            "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
            "for_trade_date": "20260603",
            "source_trade_date": "20260602",
            "prev_trade_date": "20260602",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "exchange": "SH",
            "code": "600000",
            "display_code": "600000",
            "name": "sample",
            "required_data_kind": "minute_bar_1m",
            "data_trade_date": "20260603",
            "source_scope_table": "stock_minute_target_scope",
            "source_condition_pool_id": 201,
            "direction": "buy",
            "allowed_signal_types": ["BUY"],
            "candidate_status": "planned",
        }
        candidates = [
            {**base, "candidate_ref": "c1", "source_scope_id": 101, "source_scope_ref": "stock_minute_target_scope:101", "condition_key": "B_BUY"},
            {**base, "candidate_ref": "c2", "source_scope_id": 102, "source_scope_ref": "stock_minute_target_scope:102", "condition_key": "BUY_HINT"},
        ]
        subscriptions = deduplicate_expansion_candidates(
            market_data_run_id=EXPANSION_SUBSCRIPTION_RUN_ID,
            candidates=candidates,
        )
        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions[0]["source_scope_row_count"], 2)
        self.assertEqual(subscriptions[0]["source_scope_ids"], [101, 102])
        self.assertEqual(subscriptions[0]["condition_keys"], ["B_BUY", "BUY_HINT"])

    def test_pull_plan_has_asset_adapter(self) -> None:
        subscriptions = [
            {
                "subscription_ref": "s1",
                "asset_kind": "board",
                "identity_key": "board:TDX:880001",
            }
        ]
        rows = build_expansion_pull_plan_rows(
            market_data_run_id=EXPANSION_SUBSCRIPTION_RUN_ID,
            subscriptions=subscriptions,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asset_kind"], "board")
        self.assertEqual(rows[0]["adapter_name"], "BoardMarketDataAdapter")
        self.assertEqual(rows[0]["object_count"], 1)

    def test_rollback_hard_fails_before_delete_and_never_deletes_event_tables(self) -> None:
        sql = build_subscription_expansion_rollback_sql(EXPANSION_SUBSCRIPTION_RUN_ID)
        first_raise = sql.upper().find("RAISE EXCEPTION")
        first_delete = sql.upper().find("DELETE FROM")
        self.assertNotEqual(first_raise, -1)
        self.assertLess(first_raise, first_delete)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertNotIn("DELETE FROM common_event_inbox", sql)
        self.assertNotIn("DELETE FROM common_event_consumer_checkpoint", sql)

    def test_execute_runner_requires_double_confirmation_before_loading_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = str(Path(tmpdir) / "missing.json")
            with self.assertRaisesRegex(RuntimeError, "missing --execute"):
                run_full_context_expansion_subscription_execute(
                    dsn="postgresql://unused",
                    dry_run_path=missing_path,
                    execute=False,
                    user_confirmed=True,
                )
            with self.assertRaisesRegex(RuntimeError, "missing --user-confirmed"):
                run_full_context_expansion_subscription_execute(
                    dsn="postgresql://unused",
                    dry_run_path=missing_path,
                    execute=True,
                    user_confirmed=False,
                )

    def test_execute_report_uses_dry_run_rollback_sql_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dry_run_path = Path(tmpdir) / "dry_run.json"
            report_path = Path(tmpdir) / "execute_report.json"
            markdown_path = Path(tmpdir) / "execute_report.md"
            rollback_sql_path = "sql/custom_b2_lineage_expansion_rollback.sql"
            dry_run_path.write_text(
                json.dumps(
                    {
                        "stage": "N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE",
                        "mode": "dry_run",
                        "blocked": False,
                        "market_data_run_id": "market_data_subscription_custom_expansion",
                        "source_condition_run_id": "condition_layer_custom",
                        "for_trade_date": "20260605",
                        "source_trade_date": "20260604",
                        "prev_trade_date": "20260604",
                        "source_scope_row_count": 0,
                        "candidate_row_count": 0,
                        "subscription_row_count": 0,
                        "subscription_object_count": 0,
                        "market_data_pull_plan_row_count": 0,
                        "dedup_ratio": 0,
                        "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0, "items": []},
                        "market_data_subscription_candidate": {"rows_included": True, "row_count": 0, "rows": []},
                        "market_data_subscription_dedup": {"rows_included": True, "row_count": 0, "rows": []},
                        "market_data_pull_plan": {"rows_included": True, "row_count": 0, "rows": []},
                        "rollback": {"rollback_sql_path": rollback_sql_path},
                    }
                ),
                encoding="utf-8",
            )
            pre_backup = {
                "target_run_exists": False,
                "n3_fact_and_event_row_counts": {},
            }
            post_backup = {
                "target_run_row_counts": {},
                "n3_fact_and_event_row_counts": {},
                "market_data_run_row": {"status": "passed"},
            }
            with patch(
                "ashare_v3.market.full_context_expansion_subscription_plan.capture_subscription_execution_backup",
                side_effect=[pre_backup, post_backup],
            ), patch(
                "ashare_v3.market.full_context_expansion_subscription_plan.persist_subscription_plan",
                return_value={
                    "market_data_run_rows_written": 1,
                    "quality_item_rows_written": 0,
                    "candidate_rows_written": 0,
                    "subscription_rows_written": 0,
                    "pull_plan_rows_written": 0,
                    "market_data_fact_rows_written": 0,
                    "event_outbox_rows_written": 0,
                },
            ), patch(
                "ashare_v3.market.full_context_expansion_subscription_plan.build_post_subscription_execute_checks",
                return_value={},
            ), patch(
                "ashare_v3.market.full_context_expansion_subscription_plan.build_post_quality_items",
                return_value=[],
            ):
                report = run_full_context_expansion_subscription_execute(
                    dsn="postgresql://unused",
                    dry_run_path=str(dry_run_path),
                    json_report_path=str(report_path),
                    markdown_report_path=str(markdown_path),
                    execute=True,
                    user_confirmed=True,
                )

            self.assertEqual(report["rollback"]["rollback_sql_path"], rollback_sql_path)
            persisted_report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted_report["rollback"]["rollback_sql_path"], rollback_sql_path)


if __name__ == "__main__":
    unittest.main()
