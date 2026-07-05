import unittest

from ashare_v3.condition.context_materialization import (
    MATERIALIZATION_SPEC_VERSION,
    build_execute_command_candidate,
    build_materialization_payload_rows,
    build_materialization_rollback_sql,
    materialization_table_plan,
    summarize_materialization_payload_rows,
    validate_execute_flags,
)


def enriched_scope_row(identity_key: str, *, condition_key: str = "BUY:D", ready: bool = True) -> dict[str, object]:
    periods = {
        period: {
            "previous_transition": "volume_up",
            "previous_entity_high": "12",
            "previous_entity_low": "10",
            "previous_amount_baseline": "100",
            "classification_previous_entity_high": "12",
            "classification_previous_entity_low": "10",
            "classification_previous_amount_baseline": "100",
            "classification_period_key_previous": "20260528",
            "trigger_previous_entity_high": "11",
            "trigger_previous_entity_low": "9",
            "trigger_previous_amount_baseline": "200",
            "baseline_source_trade_date": "20260529",
            "period_baseline_ready": ready,
        }
        for period in ("Y", "Q", "M", "W", "D")
    }
    return {
        "identity_key": identity_key,
        "condition_key": condition_key,
        "source_row_id": 101,
        "context_source_table": "stock_minute_target_scope",
        "context_enrichment_version": "N2-context-enrichment-v1",
        "context_enrichment_hash": "a" * 64,
        "trigger_amount_chain_baseline_json": {"periods": periods},
        "trigger_amount_chain_formula_hash": "b" * 64,
        "FULL_prerequisite_trace_json": {"execute_matcher_allowed": False},
        "FULL_prerequisite_quality_status": "blocked_trace_only",
        "HINT_prerequisite_trace_json": {"buy_hint": {"present": condition_key == "BUY_HINT"}},
        "HINT_prerequisite_quality_status": "passed" if condition_key == "BUY_HINT" else "not_applicable",
        "period_trigger_baseline_json": {
            "periods": periods,
            "context_enrichment": {
                "context_enrichment_version": "N2-context-enrichment-v1",
                "freshness_status": "fresh",
            },
        },
    }


class ConditionContextMaterializationTest(unittest.TestCase):
    def test_payload_rows_have_independent_materialization_run_spec_and_policy(self) -> None:
        rows = build_materialization_payload_rows(
            {"stock": [enriched_scope_row("stock:SZ:000001", condition_key="BUY_HINT")], "index": [], "board": []},
            source_condition_run_id="condition_layer_20260602_source_20260602_v1",
            target_run_id="condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1",
            for_trade_date="20260603",
        )

        row = rows["stock"][0]

        self.assertEqual(row["materialization_run_id"], "condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1")
        self.assertEqual(row["source_condition_run_id"], "condition_layer_20260602_source_20260602_v1")
        self.assertEqual(row["spec_version"], MATERIALIZATION_SPEC_VERSION)
        self.assertRegex(row["policy_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(row["context_materialization_row_key"], r"^[0-9a-f]{64}$")
        self.assertEqual(row["asset_kind"], "stock")
        self.assertEqual(row["identity_key"], "stock:SZ:000001")
        self.assertEqual(row["condition_key"], "BUY_HINT")
        self.assertEqual(row["source_scope_table"], "stock_minute_target_scope")
        self.assertEqual(row["source_scope_id"], 101)
        self.assertEqual(row["payload_json"]["context_enrichment_hash"], "a" * 64)
        self.assertFalse(row["payload_json"]["n4_can_recompute_context"])

    def test_summary_counts_row_level_coverage(self) -> None:
        rows = build_materialization_payload_rows(
            {
                "stock": [enriched_scope_row("stock:SZ:000001"), enriched_scope_row("stock:SZ:000002", ready=False)],
                "index": [enriched_scope_row("index:SH:000001")],
                "board": [enriched_scope_row("board:TDX:881001")],
            },
            source_condition_run_id="condition_layer_20260602_source_20260602_v1",
            target_run_id="condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1",
            for_trade_date="20260603",
        )

        summary = summarize_materialization_payload_rows(rows, expected_context_rows=4)

        self.assertEqual(summary["rows"], {"stock": 2, "index": 1, "board": 1, "total": 4})
        self.assertEqual(summary["context_enrichment_hash_rows"], 4)
        self.assertEqual(summary["previous_transition_rows"], 4)
        self.assertEqual(summary["trigger_previous_entity_bound_rows"], 4)
        self.assertEqual(summary["trigger_previous_amount_baseline_rows"], 4)
        self.assertEqual(summary["period_baseline_ready_distribution"], {"all_ready": 3, "partial_or_not_ready": 1})
        self.assertEqual(summary["FULL_trace_rows"], 4)
        self.assertEqual(summary["HINT_trace_rows"], 4)
        self.assertEqual(summary["expected_context_rows"], 4)
        self.assertEqual(summary["context_row_mismatch"], 0)

    def test_table_plan_and_rollback_are_n2_scoped_with_hard_guards(self) -> None:
        plan = materialization_table_plan()
        rollback_sql = build_materialization_rollback_sql(
            "condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1",
            plan["future_execute_write_tables"],
        )

        self.assertEqual(plan["current_gate_write_tables"], [])
        self.assertIn("stock_condition_context_enrichment", plan["future_execute_write_tables"])
        self.assertNotIn("common_trigger", " ".join(plan["future_execute_write_tables"]))
        self.assertIn("common_event_outbox", rollback_sql)
        self.assertIn("common_event_inbox", rollback_sql)
        self.assertIn("common_event_consumer_checkpoint", rollback_sql)
        self.assertIn("common_market_data_run", rollback_sql)
        self.assertIn("common_trigger_run", rollback_sql)
        self.assertIn("common_trigger_state", rollback_sql)
        self.assertIn("common_trigger_match", rollback_sql)
        self.assertIn("common_action_run", rollback_sql)
        self.assertIn("common_action_event", rollback_sql)
        self.assertIn("user_projection_run", rollback_sql)
        self.assertIn("user_signal_projection", rollback_sql)
        self.assertIn("user_signal_card", rollback_sql)
        self.assertIn("user_notification_queue", rollback_sql)
        self.assertIn("downstream_layers_touched", rollback_sql)
        self.assertIn("worker_started", rollback_sql)
        self.assertLess(rollback_sql.index("RAISE EXCEPTION"), rollback_sql.index("DELETE FROM"))
        self.assertIn("DELETE FROM stock_condition_context_enrichment", rollback_sql)
        self.assertIn("DELETE FROM common_condition_context_enrichment_run", rollback_sql)
        self.assertNotIn("DELETE FROM stock_minute_target_scope", rollback_sql)
        self.assertNotIn("DELETE FROM common_trigger_state", rollback_sql)
        self.assertNotIn("DELETE FROM common_action_event", rollback_sql)

    def test_execute_requires_execute_and_user_confirmed_flags(self) -> None:
        missing_execute = validate_execute_flags(execute=False, user_confirmed=True)
        missing_confirm = validate_execute_flags(execute=True, user_confirmed=False)
        ok = validate_execute_flags(execute=True, user_confirmed=True)

        self.assertEqual(missing_execute["gate_result"], "BLOCKED")
        self.assertEqual(missing_execute["blocked_reasons"], ["missing_execute_flag"])
        self.assertEqual(missing_execute["writes_allowed"], False)
        self.assertEqual(missing_confirm["blocked_reasons"], ["missing_user_confirmed_flag"])
        self.assertEqual(ok["gate_result"], "PASS")
        self.assertEqual(ok["writes_allowed"], True)

    def test_execute_command_candidate_is_explicit_and_n2_scoped(self) -> None:
        command = build_execute_command_candidate(
            payload_path="docs/N2_20260603_context_enrichment_row_level_payload.jsonl",
            contract_path="docs/N2_20260603_context_enrichment_row_level_materialization_contract.json",
        )

        self.assertIn("scripts/run_n2_context_enrichment_materialization_execute.py", command)
        self.assertIn("--execute", command)
        self.assertIn("--user-confirmed", command)
        self.assertIn("--payload-path docs/N2_20260603_context_enrichment_row_level_payload.jsonl", command)
        self.assertIn("--contract-path docs/N2_20260603_context_enrichment_row_level_materialization_contract.json", command)


if __name__ == "__main__":
    unittest.main()
