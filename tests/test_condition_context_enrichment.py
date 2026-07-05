import unittest

from ashare_v3.condition.context_enrichment import (
    CONTEXT_ENRICHMENT_VERSION,
    attach_context_enrichment_to_row,
    build_context_enrichment_contract,
    build_context_enrichment_snapshot,
    summarize_context_enrichment_rows,
)
from ashare_v3.condition.display_basis import DOMAIN_CONFIGS, build_display_rows_for_domain
from ashare_v3.condition.pool import build_pool_rows_for_basis
from ashare_v3.condition.scope import make_stock_scope_row
from ashare_v3.condition.basis import DateContext, make_stock_sample_basis


def baseline_json() -> dict[str, object]:
    return {
        "baseline_version": "N2-R4-period-trigger-baseline-v1",
        "baseline_source": "condition_basis",
        "periods": {
            period: {
                "period": period,
                "baseline_ready": True,
                "baseline_missing_fields": [],
                "period_transition": "volume_up" if period in {"Y", "W"} else "flat",
                "current_open_seed": "10",
                "current_close_seed": "11",
                "current_amount_seed": "200",
                "current_avg_amount_seed": "200",
                "previous_open": "12",
                "previous_close": "10",
                "previous_entity_high": "12",
                "previous_entity_low": "10",
                "previous_amount": "100",
                "previous_avg_amount": "88",
                "amount_metric": "amount" if period == "D" else "avg_amount",
                "current_window_start": "20260501",
                "current_window_end": "20260529",
                "previous_window_start": "20260401",
                "previous_window_end": "20260430",
            }
            for period in ("Y", "Q", "M", "W", "D")
        },
    }


def basis_row() -> dict[str, object]:
    return {
        "run_id": "condition_layer_test",
        "source_trade_date": "20260529",
        "for_trade_date": "20260601",
        "stock_identity_key": "stock:SZ:000001",
        "condition_key": "BUY:Y,W",
        "period_trigger_baseline_json": baseline_json(),
        "buy_full_necessary_base": True,
        "buy_full_necessary_key": "BUY:FULL",
        "sell_full_necessary_base": False,
        "sell_full_necessary_key": None,
        "oversold_hint_necessary_base": True,
        "oversold_hint_key": "BUY_HINT",
        "overbought_hint_necessary_base": False,
        "overbought_hint_key": None,
        "source_version": "stock_daily_20260529_v1",
    }


class ConditionContextEnrichmentTest(unittest.TestCase):
    def test_contract_prefers_json_extension_without_physical_columns(self) -> None:
        contract = build_context_enrichment_contract()

        self.assertFalse(contract["physical_columns_required"])
        self.assertFalse(contract["schema_migration_required"])
        self.assertIn("period_trigger_baseline_json.context_enrichment", contract["json_extension_paths"])
        self.assertEqual(contract["downstream_consumer"], "N4_trigger")
        self.assertFalse(contract["n4_can_recompute_context"])

    def test_snapshot_enriches_period_baseline_and_context_hash(self) -> None:
        snapshot = build_context_enrichment_snapshot(
            basis_row(),
            baseline_source_trade_date="20260529",
            baseline_source_version="stock_daily_20260529_v1",
        )
        enriched = snapshot["period_trigger_baseline_json"]
        period_y = enriched["periods"]["Y"]
        period_d = enriched["periods"]["D"]

        self.assertEqual(snapshot["context_enrichment_version"], CONTEXT_ENRICHMENT_VERSION)
        self.assertEqual(period_y["previous_transition"], "volume_up")
        self.assertEqual(period_y["previous_amount_baseline"], "88")
        self.assertEqual(period_d["previous_amount_baseline"], "200")
        self.assertTrue(period_y["period_baseline_ready"])
        self.assertEqual(period_y["baseline_source_trade_date"], "20260529")
        self.assertEqual(period_y["source_version"], "stock_daily_20260529_v1")
        self.assertEqual(period_y["freshness_status"], "fresh")
        context = enriched["context_enrichment"]
        self.assertEqual(context["trigger_amount_chain_formula_hash"], snapshot["trigger_amount_chain_formula_hash"])
        self.assertEqual(context["FULL_prerequisite_quality_status"], "blocked_trace_only")
        self.assertEqual(context["HINT_prerequisite_quality_status"], "passed")
        self.assertRegex(snapshot["context_enrichment_hash"], r"^[0-9a-f]{64}$")

    def test_snapshot_splits_classification_trace_from_n4_trigger_baseline(self) -> None:
        row = basis_row()
        baseline = row["period_trigger_baseline_json"]
        baseline["periods"]["D"].update(
            {
                "current_open_seed": "9.66",
                "current_close_seed": "9.45",
                "current_amount_seed": "43678.117",
                "current_avg_amount_seed": "43678.117",
                "current_amount_total_seed": "43678.117",
                "period_key_current": "20260604",
                "current_window_start": "20260604",
                "current_window_end": "20260604",
                "previous_open": "9.79",
                "previous_close": "9.67",
                "previous_entity_high": "9.79",
                "previous_entity_low": "9.67",
                "previous_amount": "57061.027",
                "previous_avg_amount": "57061.027",
                "previous_amount_baseline": "57061.027",
                "period_key_previous": "20260603",
            }
        )

        snapshot = build_context_enrichment_snapshot(
            row,
            baseline_source_trade_date="20260604",
            baseline_source_version="stock_daily_20260604_v1",
        )
        period_d = snapshot["period_trigger_baseline_json"]["periods"]["D"]

        self.assertEqual(period_d["classification_previous_entity_high"], "9.79")
        self.assertEqual(period_d["classification_previous_entity_low"], "9.67")
        self.assertEqual(period_d["classification_previous_amount_baseline"], "57061.027")
        self.assertEqual(period_d["classification_period_key_previous"], "20260603")
        self.assertEqual(period_d["period_key_previous"], "20260604")
        self.assertEqual(period_d["previous_window_start"], "20260604")
        self.assertEqual(period_d["previous_window_end"], "20260604")
        self.assertEqual(period_d["previous_amount"], "43678.117")
        self.assertEqual(period_d["previous_amount_baseline"], "43678.117")
        self.assertEqual(period_d["trigger_previous_open"], "9.66")
        self.assertEqual(period_d["trigger_previous_close"], "9.45")
        self.assertEqual(period_d["trigger_previous_entity_high"], "9.66")
        self.assertEqual(period_d["trigger_previous_entity_low"], "9.45")
        self.assertEqual(period_d["current_seed_entity_high"], "9.66")
        self.assertEqual(period_d["current_seed_entity_low"], "9.45")
        self.assertEqual(period_d["trigger_previous_amount_baseline"], "43678.117")
        self.assertEqual(period_d["baseline_source_trade_date"], "20260604")
        self.assertEqual(period_d["previous_entity_high"], "9.66")
        self.assertEqual(period_d["previous_entity_low"], "9.45")

    def test_stock_000012_d_trigger_baseline_anchors_to_source_trade_date(self) -> None:
        row = basis_row()
        row["stock_identity_key"] = "stock:SZ:000012"
        baseline = row["period_trigger_baseline_json"]
        baseline["periods"]["D"].update(
            {
                "current_open_seed": "4.1",
                "current_close_seed": "4.52",
                "current_amount_seed": "189512.92713",
                "current_avg_amount_seed": "189512.92713",
                "current_amount_total_seed": "189512.92713",
                "period_key_current": "20260616",
                "current_window_start": "20260616",
                "current_window_end": "20260616",
                "previous_open": "4",
                "previous_close": "4.11",
                "previous_entity_high": "4.11",
                "previous_entity_low": "4",
                "previous_amount": "210047.09253",
                "previous_avg_amount": "210047.09253",
                "previous_amount_baseline": "210047.09253",
                "period_key_previous": "20260615",
                "previous_window_start": "20260615",
                "previous_window_end": "20260615",
            }
        )

        snapshot = build_context_enrichment_snapshot(
            row,
            baseline_source_trade_date="20260616",
            baseline_source_version="stock_daily_20260616_v1",
        )
        period_d = snapshot["period_trigger_baseline_json"]["periods"]["D"]

        self.assertEqual(period_d["classification_period_key_previous"], "20260615")
        self.assertEqual(period_d["classification_previous_entity_high"], "4.11")
        self.assertEqual(period_d["classification_previous_entity_low"], "4")
        self.assertEqual(period_d["classification_previous_amount_baseline"], "210047.09253")
        self.assertEqual(period_d["period_key_previous"], "20260616")
        self.assertEqual(period_d["previous_window_start"], "20260616")
        self.assertEqual(period_d["previous_window_end"], "20260616")
        self.assertEqual(period_d["trigger_previous_entity_high"], "4.52")
        self.assertEqual(period_d["trigger_previous_entity_low"], "4.1")
        self.assertEqual(period_d["previous_entity_high"], "4.52")
        self.assertEqual(period_d["previous_entity_low"], "4.1")
        self.assertEqual(period_d["previous_amount"], "189512.92713")
        self.assertEqual(period_d["previous_amount_baseline"], "189512.92713")
        self.assertEqual(period_d["trigger_previous_amount_baseline"], "189512.92713")

    def test_board_881078_w_trigger_baseline_uses_previous_complete_week_entity(self) -> None:
        row = basis_row()
        row["condition_key"] = "SELL:Y,Q,M,W,D"
        baseline = row["period_trigger_baseline_json"]
        baseline["periods"]["W"].update(
            {
                "current_open_seed": "706.84",
                "current_close_seed": "712.3",
                "current_amount_seed": "1000",
                "current_avg_amount_seed": "1000",
                "period_key_current": "2026W25",
                "current_window_start": "20260615",
                "current_window_end": "20260616",
                "previous_open": "696.8",
                "previous_close": "632.78",
                "previous_entity_high": "696.8",
                "previous_entity_low": "632.78",
                "previous_amount": "900",
                "previous_avg_amount": "900",
                "period_key_previous": "2026W24",
                "previous_window_start": "20260608",
                "previous_window_end": "20260612",
            }
        )

        snapshot = build_context_enrichment_snapshot(
            row,
            baseline_source_trade_date="20260616",
            baseline_source_version="board_daily_20260616_v1",
        )
        period_w = snapshot["period_trigger_baseline_json"]["periods"]["W"]

        self.assertEqual(period_w["trigger_previous_entity_low"], "632.78")
        self.assertEqual(period_w["trigger_previous_entity_high"], "696.8")
        self.assertEqual(period_w["current_seed_entity_low"], "706.84")
        self.assertEqual(period_w["current_seed_entity_high"], "712.3")

    def test_amount_chain_and_prerequisite_traces_are_frozen_for_n4(self) -> None:
        snapshot = build_context_enrichment_snapshot(
            basis_row(),
            baseline_source_trade_date="20260529",
            baseline_source_version="stock_daily_20260529_v1",
        )

        amount_chain = snapshot["trigger_amount_chain_baseline_json"]
        self.assertIn("ordinary_buy", amount_chain["rules"])
        self.assertEqual(amount_chain["periods"]["Y"]["trigger_previous_amount_baseline"], "200")
        self.assertRegex(snapshot["trigger_amount_chain_formula_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(snapshot["FULL_prerequisite_quality_status"], "blocked_trace_only")
        self.assertEqual(snapshot["FULL_prerequisite_trace_json"]["execute_matcher_allowed"], False)
        self.assertEqual(snapshot["HINT_prerequisite_quality_status"], "passed")
        self.assertEqual(snapshot["HINT_prerequisite_trace_json"]["buy_hint"]["condition_key"], "BUY_HINT")

    def test_scope_condition_key_drives_full_and_hint_trace_status(self) -> None:
        full_snapshot = build_context_enrichment_snapshot(
            {**basis_row(), "buy_full_necessary_base": False, "buy_full_necessary_key": None, "condition_key": "BUY:FULL"},
            baseline_source_trade_date="20260529",
            baseline_source_version="stock_daily_20260529_v1",
        )
        hint_snapshot = build_context_enrichment_snapshot(
            {**basis_row(), "oversold_hint_necessary_base": False, "oversold_hint_key": None, "condition_key": "BUY_HINT"},
            baseline_source_trade_date="20260529",
            baseline_source_version="stock_daily_20260529_v1",
        )

        self.assertEqual(full_snapshot["FULL_prerequisite_quality_status"], "blocked_trace_only")
        self.assertEqual(full_snapshot["FULL_prerequisite_trace_json"]["buy_full"]["condition_key"], "BUY:FULL")
        self.assertEqual(hint_snapshot["HINT_prerequisite_quality_status"], "passed")
        self.assertEqual(hint_snapshot["HINT_prerequisite_trace_json"]["buy_hint"]["condition_key"], "BUY_HINT")

    def test_summary_reports_coverage_and_no_database_writes(self) -> None:
        snapshots = [
            build_context_enrichment_snapshot(
                basis_row(),
                baseline_source_trade_date="20260529",
                baseline_source_version="stock_daily_20260529_v1",
            )
        ]

        summary = summarize_context_enrichment_rows({"stock": snapshots, "index": [], "board": []})

        self.assertEqual(summary["writes_performed"], False)
        self.assertEqual(summary["rows"]["stock"], 1)
        self.assertEqual(summary["coverage"]["context_hash_missing"], 0)
        self.assertEqual(summary["coverage"]["amount_chain_missing"], 0)
        self.assertEqual(summary["full_prerequisite_quality_status_counts"], {"blocked_trace_only": 1})
        self.assertEqual(summary["hint_prerequisite_quality_status_counts"], {"passed": 1})

    def test_basis_pool_scope_display_generation_inherits_context_without_recompute(self) -> None:
        enriched_basis = attach_context_enrichment_to_row(basis_row())
        pool_row = build_pool_rows_for_basis("stock", enriched_basis)[0]
        scope_row = make_stock_scope_row(
            {**pool_row, "stock_condition_pool_id": 10},
            DateContext(
                source_trade_date="20260529",
                source_prev_trade_date="20260528",
                for_trade_date="20260601",
                prev_trade_date="20260529",
                for_trade_calendar_row_exists=True,
            ),
        )
        display_row = build_display_rows_for_domain(
            DOMAIN_CONFIGS["stock"],
            basis_rows=[{**enriched_basis, "stock_condition_basis_id": 1}],
            pool_rows=[{**pool_row, "stock_condition_pool_id": 10}],
            scope_rows=[{**scope_row, "stock_minute_target_scope_id": 100}],
        )[0]

        for row in (enriched_basis, pool_row, scope_row, display_row):
            context = row["period_trigger_baseline_json"]["context_enrichment"]
            self.assertEqual(context["context_enrichment_version"], CONTEXT_ENRICHMENT_VERSION)
            self.assertEqual(context["FULL_prerequisite_quality_status"], "blocked_trace_only")
            self.assertEqual(context["HINT_prerequisite_quality_status"], "passed")
            self.assertRegex(context["context_enrichment_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            scope_row["period_trigger_baseline_json"]["context_enrichment"]["context_enrichment_hash"],
            enriched_basis["period_trigger_baseline_json"]["context_enrichment"]["context_enrichment_hash"],
        )
        self.assertEqual(
            display_row["period_trigger_baseline_json"]["context_enrichment"]["context_enrichment_hash"],
            enriched_basis["period_trigger_baseline_json"]["context_enrichment"]["context_enrichment_hash"],
        )

    def test_stock_basis_generation_path_attaches_context_enrichment(self) -> None:
        row = {
            "stock_identity_key": "stock:SZ:000001",
            "exchange": "SZ",
            "ts_code": "000001.SZ",
            "code": "000001",
            "name": "平安银行",
            "is_st": False,
            "stock_status": "active",
            "official_daily_proof": True,
            "pe_core": "10",
            "total_mv": "2000000",
            "circ_mv": "1000000",
            "score": "80",
            "financial_asof_date": "20260529",
            "financial_quality_status": "passed",
            "financial_source_version": "stock_financial_20260529_v2",
            "source_version": "stock_daily_20260529_v1",
        }

        basis = make_stock_sample_basis(
            row,
            DateContext(
                source_trade_date="20260529",
                source_prev_trade_date="20260528",
                for_trade_date="20260601",
                prev_trade_date="20260529",
                for_trade_calendar_row_exists=True,
            ),
            {
                period: {
                    "current": {"period_key": f"current-{period}", "open": "10", "close": "11", "amount": "200", "avg_amount": "200"},
                    "previous": {"period_key": f"previous-{period}", "open": "12", "close": "10", "amount": "100", "avg_amount": "88"},
                    "grade": "volume_up",
                    "transition": "volume_up",
                }
                for period in ("Y", "Q", "M", "W", "D")
            },
        )

        context = basis["period_trigger_baseline_json"]["context_enrichment"]
        self.assertEqual(context["context_enrichment_version"], CONTEXT_ENRICHMENT_VERSION)
        self.assertRegex(context["context_enrichment_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(context["trigger_amount_chain_baseline_json"]["periods"]["Y"]["trigger_previous_amount_baseline"], "200")
        self.assertEqual(basis["raw_json"]["context_enrichment"]["context_enrichment_hash"], context["context_enrichment_hash"])


if __name__ == "__main__":
    unittest.main()
