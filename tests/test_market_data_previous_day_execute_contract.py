import unittest

from ashare_v3.market.preload_execute_contract import (
    build_execute_preflight_from_contract,
    build_execute_contract_from_reports,
    build_post_execute_quality_gates,
    derive_preload_run_id,
    format_previous_day_minute_execute_preflight_markdown,
    format_previous_day_minute_rollback_sql,
    rollback_sql_touches_event_outbox,
)


class PreviousDayMinuteExecuteContractTest(unittest.TestCase):
    def test_preload_run_id_is_stable_and_distinct_from_source(self) -> None:
        source_run_id = "market_data_subscription_20260525_test_execute"
        preload_run_id = derive_preload_run_id(sample_a0_report(), source_run_id)

        self.assertEqual(
            preload_run_id,
            "previous_day_minute_preload_20260522_for_20260525__market_data_subscription_20260525_test_execute",
        )
        self.assertNotEqual(preload_run_id, source_run_id)

    def test_contract_carries_expected_counts_and_outbox_false(self) -> None:
        contract = build_execute_contract_from_reports(
            a0_report=sample_a0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
        )

        self.assertEqual(contract["expected_row_count"], 720)
        self.assertEqual(contract["expected_asset_counts"]["stock"]["object_count"], 1)
        self.assertEqual(contract["expected_asset_counts"]["index"]["expected_minute_bar_rows"], 240)
        self.assertEqual(contract["source_subscription_run_id"], "market_data_subscription_20260525_test_execute")
        self.assertEqual(contract["required_data_kind"], "previous_day_minute_bar_1m")
        self.assertEqual(contract["data_trade_date"], "20260522")
        self.assertTrue(contract["historical_preload"])
        self.assertFalse(contract["writes_outbox"])
        self.assertEqual(contract["idempotency_policy"]["execute_requires_flags"], ["--execute", "--user-confirmed"])
        self.assertEqual(contract["quality"]["p0_count"], 0)
        self.assertEqual(contract["quality"]["p1_count"], 1)

    def test_contract_blocks_asset_count_mismatch(self) -> None:
        persisted = sample_persisted_report()
        persisted["market_data_subscription_dedup"]["rows"] = persisted["market_data_subscription_dedup"]["rows"][:-1]

        contract = build_execute_contract_from_reports(
            a0_report=sample_a0_report(),
            persisted_report=persisted,
            market_data_run_id="market_data_subscription_20260525_test_execute",
        )

        failed_codes = {
            item["gate_code"]
            for item in contract["quality"]["items"]
            if item["status"] == "failed"
        }
        self.assertIn("n3_a1_asset_counts_match_n3_6", failed_codes)
        self.assertGreater(contract["quality"]["p0_count"], 0)

    def test_contract_allows_zero_object_asset_without_adapter_plan(self) -> None:
        a0_report = sample_a0_report()
        a0_report["previous_day_minute_object_count_by_asset_kind"] = {"stock": 1, "index": 0, "board": 1}
        a0_report["estimated_minute_bar_row_count"] = 480
        a0_report["estimated_minute_bar_row_count_by_asset_kind"] = {"stock": 240, "index": 0, "board": 240}
        a0_report["source_adapter_plan"]["rows"] = [
            adapter_row("stock", "StockMarketDataAdapter", 1, 1, 240),
            adapter_row("board", "BoardMarketDataAdapter", 3, 1, 240),
        ]
        persisted = sample_persisted_report()
        persisted["market_data_subscription_dedup"]["rows"] = [
            subscription_row("stock", "stock:SH:600000"),
            subscription_row("board", "board:TDX:881001"),
        ]

        contract = build_execute_contract_from_reports(
            a0_report=a0_report,
            persisted_report=persisted,
            market_data_run_id="market_data_subscription_20260525_test_execute",
        )

        adapter_gate = next(
            item for item in contract["quality"]["items"] if item["gate_code"] == "n3_a1_source_adapter_plan_covers_assets"
        )
        self.assertEqual(adapter_gate["status"], "passed")
        self.assertEqual(contract["expected_asset_counts"]["index"]["object_count"], 0)
        self.assertEqual(contract["expected_asset_counts"]["index"]["expected_minute_bar_rows"], 0)
        self.assertEqual(contract["quality"]["p0_count"], 0)

    def test_contract_blocks_adapter_plan_for_zero_object_asset(self) -> None:
        a0_report = sample_a0_report()
        a0_report["previous_day_minute_object_count_by_asset_kind"] = {"stock": 1, "index": 0, "board": 1}
        a0_report["estimated_minute_bar_row_count"] = 480
        a0_report["estimated_minute_bar_row_count_by_asset_kind"] = {"stock": 240, "index": 0, "board": 240}
        a0_report["source_adapter_plan"]["rows"] = [
            adapter_row("stock", "StockMarketDataAdapter", 1, 1, 240),
            adapter_row("index", "IndexMarketDataAdapter", 2, 0, 0),
            adapter_row("board", "BoardMarketDataAdapter", 3, 1, 240),
        ]
        persisted = sample_persisted_report()
        persisted["market_data_subscription_dedup"]["rows"] = [
            subscription_row("stock", "stock:SH:600000"),
            subscription_row("board", "board:TDX:881001"),
        ]

        contract = build_execute_contract_from_reports(
            a0_report=a0_report,
            persisted_report=persisted,
            market_data_run_id="market_data_subscription_20260525_test_execute",
        )

        failed_codes = {
            item["gate_code"]
            for item in contract["quality"]["items"]
            if item["status"] == "failed"
        }
        self.assertIn("n3_a1_source_adapter_plan_covers_assets", failed_codes)
        self.assertGreater(contract["quality"]["p0_count"], 0)

    def test_rollback_sql_deletes_by_source_and_preload_run_without_outbox(self) -> None:
        contract = build_execute_contract_from_reports(
            a0_report=sample_a0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            preload_run_id="previous_day_minute_preload_test",
        )
        sql = format_previous_day_minute_rollback_sql(contract)

        self.assertIn("\\set source_run_id 'market_data_subscription_20260525_test_execute'", sql)
        self.assertIn("\\set preload_run_id 'previous_day_minute_preload_test'", sql)
        self.assertIn("DELETE FROM stock_minute_bar_1m", sql)
        self.assertIn("DELETE FROM index_previous_day_minute_preload_status", sql)
        self.assertIn("DELETE FROM common_market_data_quality_item", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertFalse(rollback_sql_touches_event_outbox(sql))
        self.assertIn("raw_json ->> 'source_run_id'", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("checkpoint_payload::TEXT LIKE", sql)

    def test_rollback_sql_hard_guards_downstream_refs_before_first_delete(self) -> None:
        contract = build_execute_contract_from_reports(
            a0_report=sample_a0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            preload_run_id="previous_day_minute_preload_test",
        )
        sql = format_previous_day_minute_rollback_sql(contract)
        prefix = sql[: sql.upper().index("DELETE FROM")]

        self.assertIn("RAISE EXCEPTION", prefix)
        self.assertIn("common_event_outbox", prefix)
        self.assertIn("common_event_inbox", prefix)
        self.assertIn("common_event_consumer_checkpoint", prefix)
        self.assertIn("downstream_layers_touched", prefix)
        self.assertIn("worker_started", prefix)
        self.assertIn("stock_realtime_daily_snapshot", prefix)
        self.assertIn("index_realtime_daily_snapshot", prefix)
        self.assertIn("board_realtime_daily_snapshot", prefix)
        self.assertIn("common_trigger_run", prefix)
        self.assertIn("common_trigger_state", prefix)
        self.assertIn("common_trigger_match", prefix)
        self.assertIn("common_action_run", prefix)
        self.assertIn("common_action_event", prefix)
        self.assertIn("user_projection_run", prefix)
        self.assertIn("user_signal_projection", prefix)
        self.assertIn("user_signal_card", prefix)
        self.assertIn("user_notification_queue", prefix)
        self.assertIn("user_sim_order", prefix)
        self.assertIn("user_sim_trade", prefix)
        self.assertIn("user_sim_position", prefix)
        self.assertIn("n6_virtual_account", prefix)
        self.assertIn("n6_virtual_order", prefix)
        self.assertIn("n6_virtual_trade", prefix)
        self.assertIn("n6_virtual_position", prefix)
        self.assertIn("n6_virtual_position_event", prefix)
        self.assertIn("n6_virtual_pnl_snapshot", prefix)
        self.assertIn("stock_closed_30m_summary", prefix)
        self.assertIn("index_closed_30m_summary", prefix)
        self.assertIn("board_closed_30m_summary", prefix)
        self.assertIn("stock_closed_30m_signal_enrichment", prefix)
        self.assertIn("index_closed_30m_signal_enrichment", prefix)
        self.assertIn("board_closed_30m_signal_enrichment", prefix)
        self.assertIn("stock_realtime_projection_metric", prefix)
        self.assertIn("index_realtime_projection_metric", prefix)
        self.assertIn("board_realtime_projection_metric", prefix)
        self.assertIn("stock_projection_enrichment_v4_metric", prefix)
        self.assertIn("index_projection_enrichment_v4_metric", prefix)
        self.assertIn("board_projection_enrichment_v4_metric", prefix)
        self.assertIn("stock_action_confirmation_projection_metric", prefix)
        self.assertIn("index_action_confirmation_projection_metric", prefix)
        self.assertIn("board_action_confirmation_projection_metric", prefix)
        self.assertIn("payload_json::TEXT LIKE", prefix)
        self.assertIn("raw_json::TEXT LIKE", prefix)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertNotIn("DELETE FROM common_event_inbox", sql)
        self.assertNotIn("DELETE FROM common_event_consumer_checkpoint", sql)

    def test_execute_preflight_passes_with_clean_scoped_baseline(self) -> None:
        contract = build_execute_contract_from_reports(
            a0_report=sample_a0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            preload_run_id="previous_day_minute_preload_test",
        )
        preflight = build_execute_preflight_from_contract(contract, sample_clean_baseline())

        self.assertEqual(preflight["stage"], "N3-A1-execute-preflight")
        self.assertEqual(preflight["result"], "PREFLIGHT_PASS")
        self.assertEqual(preflight["preload_run_id"], "previous_day_minute_preload_test")
        self.assertFalse(preflight["execute_authorized"])
        self.assertEqual(preflight["execute_requires_flags"], ["--execute", "--user-confirmed"])
        self.assertIn("--user-confirmed", preflight["execute_command_template"])
        self.assertNotIn("<contract_json_path>", preflight["execute_command_template"])
        self.assertIn("--contract-path docs/N3_A1_previous_day_minute_execute_contract.json", preflight["execute_command_template"])
        self.assertEqual(preflight["baseline"]["scoped_rows"]["total"], 0)
        self.assertEqual(preflight["quality"]["p0_count"], 0)
        self.assertIn("stock_minute_bar_1m", preflight["future_write_scope"]["allowed_tables"])
        self.assertIn("common_event_outbox", preflight["future_write_scope"]["forbidden_tables"])

    def test_preflight_markdown_uses_current_contract_path_in_execute_command(self) -> None:
        contract = build_execute_contract_from_reports(
            a0_report=sample_a0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            preload_run_id="previous_day_minute_preload_test",
            contract_json_path="docs/N3_A1_previous_day_full_context_minute_preload_expansion_20260603_execute_contract.json",
        )
        preflight = build_execute_preflight_from_contract(contract, sample_clean_baseline())
        markdown = format_previous_day_minute_execute_preflight_markdown(preflight)

        self.assertIn(
            "--contract-path docs/N3_A1_previous_day_full_context_minute_preload_expansion_20260603_execute_contract.json",
            preflight["execute_command_template"],
        )
        self.assertNotIn("<contract_json_path>", preflight["execute_command_template"])
        self.assertIn(
            "--contract-path docs/N3_A1_previous_day_full_context_minute_preload_expansion_20260603_execute_contract.json",
            markdown,
        )
        self.assertNotIn("20260527", markdown)

    def test_execute_preflight_blocks_when_scoped_baseline_is_not_clean(self) -> None:
        baseline = sample_clean_baseline()
        baseline["common_event_outbox"] = 1
        contract = build_execute_contract_from_reports(
            a0_report=sample_a0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            preload_run_id="previous_day_minute_preload_test",
        )
        preflight = build_execute_preflight_from_contract(contract, baseline)

        self.assertEqual(preflight["result"], "PREFLIGHT_BLOCKED")
        self.assertGreater(preflight["quality"]["p0_count"], 0)
        failed_codes = {
            item["gate_code"]
            for item in preflight["quality"]["items"]
            if item["status"] == "failed"
        }
        self.assertIn("n3_a1_preload_scoped_baseline_zero", failed_codes)

    def test_post_execute_quality_gate_definitions_include_duplicate_and_missing_rules(self) -> None:
        gates = build_post_execute_quality_gates(sample_a0_report())
        gate_codes = {gate["gate_code"] for gate in gates}

        self.assertIn("n3_a1_duplicate_minute_key_zero", gate_codes)
        self.assertIn("n3_a1_missing_object_not_silent", gate_codes)
        self.assertIn("n3_a1_physical_table_isolation", gate_codes)


def sample_a0_report() -> dict[str, object]:
    return {
        "stage": "N3-A0",
        "blocked": False,
        "market_data_run_id": "market_data_subscription_20260525_test_execute",
        "source_condition_run_id": "condition_layer_20260522_to_20260525_test_execute",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "expected_previous_day_minute_date": "20260522",
        "previous_day_minute_object_count_by_asset_kind": {"stock": 1, "index": 1, "board": 1},
        "estimated_minute_bar_row_count": 720,
        "estimated_minute_bar_row_count_by_asset_kind": {"stock": 240, "index": 240, "board": 240},
        "expected_minute_bar_count_per_object": 240,
        "source_adapter_plan": {
            "rows": [
                adapter_row("stock", "StockMarketDataAdapter", 1, 1, 240),
                adapter_row("index", "IndexMarketDataAdapter", 1, 1, 240),
                adapter_row("board", "BoardMarketDataAdapter", 1, 1, 240),
            ]
        },
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": []},
    }


def adapter_row(
    asset_kind: str,
    adapter_name: str,
    source_pull_plan_id: int,
    object_count: int,
    expected_rows: int,
) -> dict[str, object]:
    return {
        "asset_kind": asset_kind,
        "source_pull_plan_id": source_pull_plan_id,
        "adapter_name": adapter_name,
        "previous_day_minute_date": "20260522",
        "subscription_count": object_count,
        "object_count": object_count,
        "expected_minute_bar_rows": expected_rows,
        "target_minute_fact_table": f"{asset_kind}_minute_bar_1m",
        "target_preload_status_table": f"{asset_kind}_previous_day_minute_preload_status",
    }


def sample_persisted_report() -> dict[str, object]:
    return {
        "market_data_run_id": "market_data_subscription_20260525_test_execute",
        "passed": True,
        "quality": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "items": []},
        "market_data_subscription_dedup": {
            "rows": [
                subscription_row("stock", "stock:SH:600000"),
                subscription_row("index", "index:SH:000905"),
                subscription_row("board", "board:TDX:881001"),
            ]
        },
    }


def subscription_row(asset_kind: str, identity_key: str) -> dict[str, object]:
    return {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "required_data_kind": "previous_day_minute_bar_1m",
    }


def sample_clean_baseline() -> dict[str, object]:
    return {
        "common_market_data_run": 0,
        "common_market_data_quality_item": 0,
        "stock_minute_bar_1m": 0,
        "index_minute_bar_1m": 0,
        "board_minute_bar_1m": 0,
        "stock_previous_day_minute_preload_status": 0,
        "index_previous_day_minute_preload_status": 0,
        "board_previous_day_minute_preload_status": 0,
        "common_event_outbox": 0,
        "common_event_inbox": 0,
        "common_event_consumer_checkpoint": 0,
    }


if __name__ == "__main__":
    unittest.main()
