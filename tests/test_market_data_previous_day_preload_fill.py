import unittest

from ashare_v3.market.previous_day_preload_fill import (
    PreviousDayMinutePreloadFillError,
    build_status_restore_rollback_sql,
    ensure_fill_facts_contract,
    ensure_metadata_only_fill_target,
    format_fill_facts_execute_report,
    prefix_fill_quality_items,
)


class PreviousDayMinutePreloadFillTest(unittest.TestCase):
    def test_fill_contract_requires_double_confirmation(self) -> None:
        with self.assertRaises(PreviousDayMinutePreloadFillError):
            ensure_fill_facts_contract(
                sample_fill_contract(),
                execute=True,
                user_confirmed=False,
                preload_run_id="previous_day_minute_preload_current",
                for_trade_date="20260525",
            )

    def test_fill_target_allows_unrelated_global_outbox_rows(self) -> None:
        ensure_metadata_only_fill_target(sample_fill_backup(global_outbox_count=55492))

    def test_fill_target_rejects_fact_rows_for_current_preload_run(self) -> None:
        backup = sample_fill_backup(global_outbox_count=55492)
        backup["target_preload_run_row_counts_by_asset"]["stock"]["minute_row_count"] = 1

        with self.assertRaisesRegex(PreviousDayMinutePreloadFillError, "minute fact rows"):
            ensure_metadata_only_fill_target(backup)

    def test_fill_target_rejects_outbox_for_this_preload_run(self) -> None:
        backup = sample_fill_backup(global_outbox_count=55492)
        backup["outbox_rows_for_run"] = 1

        with self.assertRaisesRegex(PreviousDayMinutePreloadFillError, "outbox rows"):
            ensure_metadata_only_fill_target(backup)

    def test_fill_quality_items_are_prefixed_for_rollback_scope(self) -> None:
        items = prefix_fill_quality_items(
            [
                {
                    "severity": "P0",
                    "status": "passed",
                    "gate_code": "n3_a1_duplicate_minute_key_zero",
                    "gate_name": "duplicate key count",
                },
                {
                    "severity": "P1",
                    "status": "warning",
                    "gate_code": "n3_a1_current_fill_existing",
                    "gate_name": "already prefixed",
                },
            ]
        )

        self.assertEqual(items[0]["gate_code"], "n3_a1_current_fill_duplicate_minute_key_zero")
        self.assertEqual(items[1]["gate_code"], "n3_a1_current_fill_existing")

    def test_status_snapshot_rollback_restores_status_rows_without_outbox(self) -> None:
        rollback_sql = build_status_restore_rollback_sql(
            preload_run_id="previous_day_minute_preload_current",
            previous_day_minute_date="20260522",
            status_snapshot={
                "stock": [
                    {
                        "run_id": "previous_day_minute_preload_current",
                        "subscription_id": 11,
                        "source_condition_run_id": "condition_run",
                        "for_trade_date": "20260525",
                        "trade_date": "20260522",
                        "stock_identity_key": "stock:SH:600000",
                        "exchange": "SH",
                        "code": "600000",
                        "display_code": "600000.SH",
                        "name": "浦发银行",
                        "expected_bar_count": 240,
                        "actual_bar_count": 0,
                        "missing_bar_count": 240,
                        "first_bar_time": None,
                        "last_bar_time": None,
                        "status": "missing",
                        "quality_status": "missing",
                        "source_adapter": "StockMarketDataAdapter",
                        "error_message": None,
                        "source_scope_ids": [1],
                        "source_condition_pool_ids": [101],
                        "raw_json": {"lineage_rebuild": True},
                    }
                ],
                "index": [],
                "board": [],
            },
        )

        self.assertIn("DELETE FROM stock_previous_day_minute_preload_status", rollback_sql)
        self.assertIn("INSERT INTO stock_previous_day_minute_preload_status", rollback_sql)
        self.assertIn("previous_day_minute_preload_current", rollback_sql)
        self.assertNotIn("common_event_outbox", rollback_sql.lower())

    def test_fill_report_uses_current_lineage_rollback_path_only(self) -> None:
        report = {
            "stage": "N3-A1-current-lineage-fill-facts",
            "layer_role": "N3_market_data",
            "source_run_id": "market_data_subscription_current",
            "preload_run_id": "previous_day_minute_preload_current",
            "previous_day_minute_date": "20260522",
            "status_snapshot_path": "docs/status_snapshot.json",
            "rollback_sql_path": "sql/current_rollback.sql",
            "write_result": {
                "objects_processed": 1,
                "minute_rows_written": 240,
                "preload_status_rows_written": 1,
                "quality_item_rows_written": 1,
                "event_outbox_rows_written": 0,
            },
            "quality": {"p0_count": 0, "p1_count": 0, "p2_count": 0},
            "actual_asset_counts": {
                "stock": {
                    "object_count": 1,
                    "minute_rows_written": 240,
                    "passed_count": 1,
                    "partial_count": 0,
                    "missing_count": 0,
                    "failed_count": 0,
                }
            },
            "post_checks": {},
            "side_effects": {},
        }

        markdown = format_fill_facts_execute_report(report)

        self.assertIn("sql/current_rollback.sql", markdown)
        self.assertNotIn("sql/N3_A1_previous_day_minute_rollback.sql", markdown)


def sample_fill_contract() -> dict[str, object]:
    return {
        "stage": "N3-A1-current-lineage-preflight-correction",
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_PASS",
        "source_run_id": "market_data_subscription_current",
        "preload_run_id": "previous_day_minute_preload_current",
        "source_condition_run_id": "condition_run",
        "for_trade_date": "20260525",
        "source_trade_date": "20260522",
        "previous_day_minute_date": "20260522",
        "execution_mode": "previous_day_minute_preload_fill_facts_for_existing_metadata_run",
        "recommended_metadata_only_run_handling": "scheme_b_fill_facts_resume_existing_run",
        "writes_outbox": False,
        "generated_event_types": [],
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0},
    }


def sample_fill_backup(*, global_outbox_count: int = 0) -> dict[str, object]:
    return {
        "preload_run_exists": True,
        "preload_run_row": {
            "run_id": "previous_day_minute_preload_current",
            "status": "passed",
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
        "target_preload_run_row_counts": {
            "stock_minute_bar_1m": 0,
            "index_minute_bar_1m": 0,
            "board_minute_bar_1m": 0,
            "stock_previous_day_minute_preload_status": 2052,
            "index_previous_day_minute_preload_status": 9,
            "board_previous_day_minute_preload_status": 127,
            "common_market_data_quality_item": 9,
            "common_market_data_run": 1,
        },
        "target_preload_run_row_counts_by_asset": {
            "stock": {"minute_row_count": 0, "preload_status_object_count": 2052},
            "index": {"minute_row_count": 0, "preload_status_object_count": 9},
            "board": {"minute_row_count": 0, "preload_status_object_count": 127},
        },
        "outbox_rows_for_run": 0,
        "inbox_rows_for_run": 0,
        "common_event_outbox_row_count": global_outbox_count,
    }


if __name__ == "__main__":
    unittest.main()
