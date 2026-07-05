import unittest

from ashare_v3.market.realtime_snapshot_execute_contract import (
    build_event_contract,
    build_execute_contract_from_reports,
    build_post_execute_quality_gates,
    derive_snapshot_run_id,
    format_realtime_snapshot_rollback_sql,
)


class RealtimeSnapshotExecuteContractTest(unittest.TestCase):
    def test_snapshot_run_id_is_stable_and_distinct_from_source(self) -> None:
        source_run_id = "market_data_subscription_20260525_test_execute"
        snapshot_run_id = derive_snapshot_run_id(sample_b0_report(), source_run_id)

        self.assertEqual(
            snapshot_run_id,
            "realtime_daily_snapshot_20260525__market_data_subscription_20260525_test_execute",
        )
        self.assertNotEqual(snapshot_run_id, source_run_id)

    def test_contract_carries_expected_counts_and_outbox_true(self) -> None:
        contract = build_execute_contract_from_reports(
            b0_report=sample_b0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
        )

        self.assertEqual(contract["expected_row_count"], 3)
        self.assertEqual(contract["expected_asset_counts"]["stock"]["object_count"], 1)
        self.assertEqual(contract["expected_asset_counts"]["index"]["expected_snapshot_rows"], 1)
        self.assertTrue(contract["writes_outbox"])
        self.assertTrue(contract["writes_market_snapshot_updated"])
        self.assertFalse(contract["writes_market_display_snapshot_updated"])
        self.assertEqual(contract["quality"]["p0_count"], 0)
        self.assertEqual(contract["quality"]["p1_count"], 1)
        self.assertTrue(contract["source_time_policy"]["source_time_future_guard_enabled"])
        self.assertEqual(contract["source_time_policy"]["future_tolerance_seconds"], 120)
        self.assertEqual(contract["source_time_policy"]["future_source_time_handling"], "P0_BLOCK_NO_OUTBOX")

    def test_contract_blocks_asset_count_mismatch(self) -> None:
        persisted = sample_persisted_report()
        persisted["market_data_subscription_dedup"]["rows"] = [
            row
            for row in persisted["market_data_subscription_dedup"]["rows"]
            if row.get("asset_kind") != "board"
        ]

        contract = build_execute_contract_from_reports(
            b0_report=sample_b0_report(),
            persisted_report=persisted,
            market_data_run_id="market_data_subscription_20260525_test_execute",
        )

        failed_codes = {
            item["gate_code"]
            for item in contract["quality"]["items"]
            if item["status"] == "failed"
        }
        self.assertIn("n3_b1_asset_counts_match_n3_6", failed_codes)
        self.assertGreater(contract["quality"]["p0_count"], 0)

    def test_event_contract_defaults_to_snapshot_updated_only(self) -> None:
        contract = build_event_contract(publish_display_event=False)

        self.assertEqual(contract["required_outbox_events"], ["MarketSnapshotUpdated"])
        self.assertEqual(contract["generated_outbox_events_in_b1_default"], ["MarketSnapshotUpdated"])
        self.assertEqual(contract["optional_outbox_events"], [])
        self.assertIn("snapshot_id", contract["payload_required_fields"]["MarketSnapshotUpdated"])
        self.assertEqual(set(contract["payload_required_fields"]), {"MarketSnapshotUpdated"})
        self.assertTrue(contract["display_event_policy"]["does_not_trigger_voice"])

    def test_display_event_request_stays_disabled_for_standard_b1_contract(self) -> None:
        contract = build_execute_contract_from_reports(
            b0_report=sample_b0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            publish_display_event=True,
        )

        self.assertFalse(contract["writes_market_display_snapshot_updated"])
        self.assertEqual(contract["event_contract"]["generated_outbox_events_in_b1_default"], ["MarketSnapshotUpdated"])
        self.assertEqual(contract["event_contract"]["optional_outbox_events"], [])
        self.assertFalse(contract["side_effects"]["downstream_layers_touched"])

    def test_no_outbox_contract_keeps_target_tables_fact_only(self) -> None:
        contract = build_execute_contract_from_reports(
            b0_report=sample_b0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            snapshot_run_id="realtime_snapshot_test",
            writes_outbox=False,
        )

        self.assertFalse(contract["writes_outbox"])
        self.assertFalse(contract["writes_market_snapshot_updated"])
        self.assertEqual(contract["event_contract"]["generated_outbox_events_in_b1_default"], [])
        self.assertEqual(contract["event_contract"]["required_outbox_events"], [])
        self.assertTrue(
            all("event_outbox_table" not in tables for tables in contract["target_tables"].values())
        )
        self.assertEqual(contract["quality"]["p0_count"], 0)
        self.assertTrue(contract["execute_runner_readiness"]["execute_final_gate_allowed"])
        self.assertTrue(contract["execute_runner_readiness"]["runner_supports_writes_outbox_false"])
        self.assertTrue(contract["execute_runner_readiness"]["runner_requires_no_outbox_flag"])

    def test_writes_outbox_contract_requires_explicit_true_flag_and_is_runner_ready(self) -> None:
        contract = build_execute_contract_from_reports(
            b0_report=sample_b0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            snapshot_run_id="realtime_snapshot_test",
            writes_outbox=True,
        )

        self.assertTrue(contract["writes_outbox"])
        self.assertTrue(contract["writes_market_snapshot_updated"])
        self.assertTrue(contract["execute_runner_readiness"]["execute_final_gate_allowed"])
        self.assertTrue(contract["execute_runner_readiness"]["runner_supports_writes_outbox_true"])
        self.assertTrue(contract["execute_runner_readiness"]["runner_requires_writes_outbox_true_flag"])
        self.assertFalse(contract["execute_runner_readiness"]["runner_requires_no_outbox_flag"])

    def test_rollback_sql_scopes_snapshot_and_outbox_without_downstream_dml(self) -> None:
        contract = build_execute_contract_from_reports(
            b0_report=sample_b0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            snapshot_run_id="realtime_daily_snapshot_test",
        )
        sql = format_realtime_snapshot_rollback_sql(contract)

        self.assertIn("\\set source_run_id 'market_data_subscription_20260525_test_execute'", sql)
        self.assertIn("\\set snapshot_run_id 'realtime_daily_snapshot_test'", sql)
        self.assertIn("DELETE FROM stock_realtime_daily_snapshot", sql)
        self.assertIn("DELETE FROM index_realtime_daily_snapshot", sql)
        self.assertIn("DELETE FROM board_realtime_daily_snapshot", sql)
        self.assertIn("DELETE FROM common_event_outbox", sql)
        self.assertIn("delivered_or_delivering_outbox_rows_must_be_zero", sql)
        self.assertIn("downstream_inbox_rows_must_be_zero", sql)
        self.assertIn("checkpoint_refs_must_be_zero", sql)
        self.assertNotIn("DELETE FROM trigger_", sql)
        self.assertNotIn("DELETE FROM action_", sql)
        self.assertNotIn("DELETE FROM user_", sql)
        self.assertIn("raw_json ->> 'source_run_id'", sql)
        self.assertIn("raw_json ->> 'snapshot_run_id'", sql)

    def test_no_outbox_rollback_sql_guards_event_refs_without_outbox_delete(self) -> None:
        contract = build_execute_contract_from_reports(
            b0_report=sample_b0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            snapshot_run_id="realtime_snapshot_test",
            writes_outbox=False,
        )
        sql = format_realtime_snapshot_rollback_sql(contract)

        self.assertIn("scoped_outbox_refs_must_be_zero", sql)
        self.assertIn("downstream_inbox_rows_must_be_zero", sql)
        self.assertIn("checkpoint_refs_must_be_zero", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertIn("DELETE FROM stock_realtime_daily_snapshot", sql)
        self.assertIn("DELETE FROM common_market_data_quality_item", sql)
        self.assertIn("DELETE FROM common_market_data_run", sql)
        self.assertNotIn("DELETE FROM trigger_", sql)
        self.assertNotIn("DELETE FROM action_", sql)

    def test_rollback_sql_hard_fails_before_delete_for_fact_only(self) -> None:
        contract = build_execute_contract_from_reports(
            b0_report=sample_b0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            snapshot_run_id="realtime_snapshot_test",
            writes_outbox=False,
        )
        sql = format_realtime_snapshot_rollback_sql(contract)

        self.assertIn("RAISE EXCEPTION", sql)
        self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("DELETE FROM"))
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertIn("downstream_layers_touched", sql)
        self.assertIn("worker_started", sql)

    def test_rollback_sql_guards_projection_and_trigger_state_refs(self) -> None:
        contract = build_execute_contract_from_reports(
            b0_report=sample_b0_report(),
            persisted_report=sample_persisted_report(),
            market_data_run_id="market_data_subscription_20260525_test_execute",
            snapshot_run_id="realtime_snapshot_test",
            writes_outbox=False,
        )
        sql = format_realtime_snapshot_rollback_sql(contract)

        self.assertIn("stock_realtime_projection_metric", sql)
        self.assertIn("index_realtime_projection_metric", sql)
        self.assertIn("board_realtime_projection_metric", sql)
        self.assertIn("common_trigger_state", sql)
        self.assertIn("realtime_projection_refs", sql)
        self.assertIn("trigger_state_refs", sql)
        self.assertLess(sql.index("RAISE EXCEPTION"), sql.index("DELETE FROM"))

    def test_post_execute_quality_gates_include_outbox_and_isolation_rules(self) -> None:
        gates = build_post_execute_quality_gates(b0_report=sample_b0_report(), publish_display_event=False)
        gate_codes = {gate["gate_code"] for gate in gates}

        self.assertIn("n3_b1_market_snapshot_outbox_matches_successful_facts", gate_codes)
        self.assertIn("n3_b1_no_non_snapshot_outbox_events", gate_codes)
        self.assertIn("n3_b1_duplicate_snapshot_key_zero", gate_codes)
        self.assertIn("n3_b1_no_downstream_consumption_before_rollback", gate_codes)

    def test_post_execute_quality_gates_fact_only_have_no_outbox_match_requirement(self) -> None:
        gates = build_post_execute_quality_gates(
            b0_report=sample_b0_report(),
            publish_display_event=False,
            writes_outbox=False,
        )
        gate_codes = {gate["gate_code"] for gate in gates}

        self.assertIn("n3_b1_writes_outbox_false", gate_codes)
        self.assertIn("n3_b1_scoped_event_refs_zero", gate_codes)
        self.assertNotIn("n3_b1_market_snapshot_outbox_matches_successful_facts", gate_codes)
        self.assertNotIn("n3_b1_no_non_snapshot_outbox_events", gate_codes)


def sample_b0_report() -> dict[str, object]:
    return {
        "stage": "N3-B0",
        "blocked": False,
        "market_data_run_id": "market_data_subscription_20260525_test_execute",
        "source_condition_run_id": "condition_layer_20260522_to_20260525_test_execute",
        "source_trade_date": "20260522",
        "for_trade_date": "20260525",
        "prev_trade_date": "20260522",
        "snapshot_object_count_by_asset_kind": {"stock": 1, "index": 1, "board": 1},
        "expected_snapshot_rows": 3,
        "expected_snapshot_rows_by_asset_kind": {"stock": 1, "index": 1, "board": 1},
        "source_adapter_plan": {
            "rows": [
                adapter_row("stock", "StockMarketDataAdapter", 1, 1),
                adapter_row("index", "IndexMarketDataAdapter", 2, 1),
                adapter_row("board", "BoardMarketDataAdapter", 3, 1),
            ]
        },
        "quality": {"p0_count": 0, "p1_count": 2, "p2_count": 0, "items": []},
    }


def adapter_row(asset_kind: str, adapter_name: str, source_pull_plan_id: int, object_count: int) -> dict[str, object]:
    return {
        "asset_kind": asset_kind,
        "source_pull_plan_id": source_pull_plan_id,
        "adapter_name": adapter_name,
        "trade_date": "20260525",
        "subscription_count": object_count,
        "object_count": object_count,
        "expected_snapshot_rows": object_count,
        "target_snapshot_table": f"{asset_kind}_realtime_daily_snapshot",
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
                {**subscription_row("stock", "stock:SH:600000"), "required_data_kind": "minute_bar_1m"},
            ]
        },
    }


def subscription_row(asset_kind: str, identity_key: str) -> dict[str, object]:
    return {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "required_data_kind": "realtime_daily_snapshot",
    }


if __name__ == "__main__":
    unittest.main()
