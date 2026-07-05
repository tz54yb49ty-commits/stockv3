import unittest

from scripts.plan_n2_context_enrichment_dry_run import (
    build_context_refresh_summary,
    context_table_specs,
)


def enriched_row(identity_key: str, *, ready: bool = True, condition_key: str = "BUY:D") -> dict[str, object]:
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
        "context_enrichment_hash": "a" * 64,
        "trigger_amount_chain_baseline_json": {"periods": periods},
        "trigger_amount_chain_formula_hash": "b" * 64,
        "FULL_prerequisite_trace_json": {"execute_matcher_allowed": False},
        "FULL_prerequisite_quality_status": "blocked_trace_only" if condition_key == "BUY:FULL" else "not_applicable",
        "HINT_prerequisite_trace_json": {"buy_hint": {"present": condition_key == "BUY_HINT"}},
        "HINT_prerequisite_quality_status": "passed" if condition_key == "BUY_HINT" else "not_applicable",
        "period_trigger_baseline_json": {"periods": periods, "context_enrichment": {"freshness_status": "fresh"}},
    }


class ConditionContextEnrichmentRefreshTest(unittest.TestCase):
    def test_scope_context_table_specs_use_minute_target_scope_tables(self) -> None:
        specs = context_table_specs("scope")

        self.assertEqual(specs["stock"]["table"], "stock_minute_target_scope")
        self.assertEqual(specs["index"]["table"], "index_minute_target_scope")
        self.assertEqual(specs["board"]["table"], "board_minute_target_scope")
        self.assertEqual(specs["stock"]["source_id_column"], "stock_minute_target_scope_id")
        self.assertEqual(specs["index"]["source_id_column"], "index_minute_target_scope_id")
        self.assertEqual(specs["board"]["source_id_column"], "board_minute_target_scope_id")

    def test_refresh_summary_counts_context_candidates_and_trace_coverage(self) -> None:
        rows_by_domain = {
            "stock": [enriched_row("stock:SZ:000001"), enriched_row("stock:SZ:000002", condition_key="BUY_HINT")],
            "index": [enriched_row("index:SH:000001", condition_key="BUY:FULL")],
            "board": [enriched_row("board:TDX:881001", ready=False, condition_key="BUY_HINT")],
        }

        summary = build_context_refresh_summary(rows_by_domain, expected_context_candidates=4)

        self.assertEqual(summary["context_row_count"], 4)
        self.assertEqual(summary["context_enrichment_rows"], 4)
        self.assertEqual(summary["previous_transition_rows"], 4)
        self.assertEqual(summary["trigger_previous_entity_bound_rows"], 4)
        self.assertEqual(summary["trigger_previous_amount_baseline_rows"], 4)
        self.assertEqual(summary["previous_amount_baseline_rows"], 4)
        self.assertEqual(summary["period_baseline_ready_distribution"], {"all_ready": 3, "partial_or_not_ready": 1})
        self.assertEqual(summary["required_period_baseline_missing_rows"], 0)
        self.assertEqual(summary["FULL_trace_rows"], 4)
        self.assertEqual(summary["HINT_trace_rows"], 4)
        self.assertEqual(summary["expected_context_candidates"], 4)
        self.assertEqual(summary["context_candidate_mismatch"], 0)


if __name__ == "__main__":
    unittest.main()
