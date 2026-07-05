import argparse
import unittest

from scripts.run_n2_context_enrichment_materialization_execute import (
    ALLOWED_WRITE_TABLES,
    blocked_report,
    build_arg_parser,
    count_rows_by_asset,
    period_baseline_ready_json,
    row_insert_params,
    run,
)


def args(**overrides: object) -> argparse.Namespace:
    base = {
        "dsn": "postgresql://unused",
        "payload_path": "docs/N2_20260603_context_enrichment_row_level_payload.jsonl",
        "contract_path": "docs/N2_20260603_context_enrichment_row_level_materialization_contract.json",
        "execute": False,
        "user_confirmed": False,
        "operator": "codex",
        "confirmation_note": "",
        "report_path": "docs/test.json",
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class ConditionContextMaterializationExecuteRunnerTest(unittest.TestCase):
    def test_cli_requires_payload_and_contract_and_explicit_flags(self) -> None:
        parser = build_arg_parser()
        parsed = parser.parse_args(
            [
                "--payload-path",
                "payload.jsonl",
                "--contract-path",
                "contract.json",
                "--execute",
                "--user-confirmed",
            ]
        )

        self.assertTrue(parsed.execute)
        self.assertTrue(parsed.user_confirmed)

    def test_missing_execute_blocks_before_database_write(self) -> None:
        report = run(args(execute=False, user_confirmed=True))

        self.assertEqual(report["execute_result"], "BLOCKED")
        self.assertEqual(report["blocked_reasons"], ["missing_execute_flag"])
        self.assertEqual(report["writes_performed"], False)
        self.assertEqual(report["will_execute_sql"], False)
        self.assertEqual(report["blocked_before_database_write"], True)

    def test_missing_user_confirmed_blocks_before_database_write(self) -> None:
        report = run(args(execute=True, user_confirmed=False))

        self.assertEqual(report["execute_result"], "BLOCKED")
        self.assertEqual(report["blocked_reasons"], ["missing_user_confirmed_flag"])
        self.assertEqual(report["writes_performed"], False)

    def test_allowed_write_tables_are_n2_context_only(self) -> None:
        self.assertEqual(
            ALLOWED_WRITE_TABLES,
            [
                "common_condition_context_enrichment_run",
                "stock_condition_context_enrichment",
                "index_condition_context_enrichment",
                "board_condition_context_enrichment",
            ],
        )
        self.assertNotIn("stock_minute_target_scope", ALLOWED_WRITE_TABLES)
        self.assertNotIn("common_event_outbox", ALLOWED_WRITE_TABLES)
        self.assertNotIn("common_trigger_state", ALLOWED_WRITE_TABLES)

    def test_row_insert_params_preserve_payload_context(self) -> None:
        row = {
            "materialization_run_id": "context_run",
            "source_condition_run_id": "condition_run",
            "for_trade_date": "20260603",
            "source_trade_date": "20260602",
            "spec_version": "spec",
            "policy_hash": "a" * 64,
            "identity_key": "stock:SZ:000001",
            "condition_key": "BUY:D",
            "direction": "buy",
            "allowed_signal_types": ["BUY"],
            "source_scope_table": "stock_minute_target_scope",
            "source_scope_id": 1,
            "context_materialization_row_key": "b" * 64,
            "context_enrichment_hash": "c" * 64,
            "payload_json": {
                "context_enrichment_version": "N2-context-enrichment-v1",
                "period_trigger_baseline_json": {
                    "periods": {"D": {"period_baseline_ready": True}},
                    "context_enrichment": {"freshness_status": "fresh"},
                },
                "trigger_amount_chain_baseline_json": {},
                "trigger_amount_chain_formula_hash": "d" * 64,
                "FULL_prerequisite_trace_json": {},
                "FULL_prerequisite_quality_status": "not_applicable",
                "HINT_prerequisite_trace_json": {},
                "HINT_prerequisite_quality_status": "not_applicable",
            },
        }

        params = row_insert_params(row)

        self.assertEqual(params["source_trade_date"], "20260602")
        self.assertEqual(params["allowed_signal_types"], ["BUY"])
        self.assertEqual(params["freshness_status"], "fresh")
        self.assertEqual(period_baseline_ready_json(row["payload_json"]["period_trigger_baseline_json"])["D"], True)

    def test_count_rows_by_asset(self) -> None:
        counts = count_rows_by_asset(
            [
                {"asset_kind": "stock"},
                {"asset_kind": "stock"},
                {"asset_kind": "index"},
                {"asset_kind": "board"},
                {"asset_kind": "unknown"},
            ]
        )

        self.assertEqual(counts, {"stock": 2, "index": 1, "board": 1, "total": 4})

    def test_blocked_report_keeps_allowed_scope_and_no_writes(self) -> None:
        report = blocked_report(args(), ["missing_execute_flag"])

        self.assertEqual(report["allowed_write_tables"], ALLOWED_WRITE_TABLES)
        self.assertEqual(report["writes_performed"], False)
        self.assertEqual(report["will_execute_sql"], False)


if __name__ == "__main__":
    unittest.main()
