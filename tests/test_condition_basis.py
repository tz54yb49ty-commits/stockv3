import unittest
from unittest.mock import patch

from ashare_v3.condition.basis import (
    CONDITION_PROJECTION_CONTEXT_VERSION,
    DateContext,
    DEFAULT_INDEX_POOL_IDENTITIES,
    PERIOD_ESCALATION_CONTEXT_GENERATION_MODE,
    PERIOD_ESCALATION_CONTEXT_VERSION,
    SYMMETRY_TARGET_BASE_PRICE_POLICY,
    PERIOD_TRIGGER_BASELINE_VERSION,
    PERIODS,
    active_versions_from_ready_check,
    attach_period_escalation_contexts,
    attach_period_escalation_context_to_row,
    build_condition_projection_context,
    build_period_escalation_context,
    build_quality_items,
    canonical_target_fields_for_direction,
    computed_condition_fields,
    condition_projection_context_hash_valid,
    count_quality_severities,
    empty_necessary_condition_fields,
    empty_static_structure_fields,
    fetch_period_escalation_previous_context_run,
    fetch_period_escalation_previous_context_rows,
    fetch_period_contexts,
    index_period_escalation_previous_context_rows,
    period_grade,
    period_trigger_baseline_has_required_shape,
    period_trigger_baseline_not_ready_periods,
    period_trigger_baseline_period_ready,
    ready_check_failure_quality_items,
    stable_json_hash,
    stock_condition_universe_summary,
    transition_grade,
)
from ashare_v3.condition.context_materialization import build_materialization_payload_rows


class RecordingCursor:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.sql_calls: list[str] = []
        self.params_calls: list[object] = []
        self.rows = list(rows or [])

    def execute(self, sql: str, params: object = None) -> None:
        self.sql_calls.append(sql)
        self.params_calls.append(params)

    def fetchall(self) -> list[dict[str, object]]:
        return list(self.rows)


def condition_projection_basis_row(asset_kind: str) -> dict[str, object]:
    identity_fields = {
        "stock": {"stock_identity_key": "stock:SH:600000", "name": "浦发银行"},
        "index": {"index_identity_key": "index:SH:000001", "name": "上证指数"},
        "board": {"board_identity_key": "board:TDX:881155", "board_name": "银行"},
    }
    return {
        "asset_kind": asset_kind,
        **identity_fields[asset_kind],
        "source_trade_date": "20260710",
        "for_trade_date": "20260713",
        "source_version": f"{asset_kind}_daily_20260710_v1",
        "raw_json": {"close": "10.5000"},
        "period_trigger_baseline_json": {
            "periods": {
                period: {"current_close_seed": "10.5" if period == "D" else None}
                for period in PERIODS
            }
        },
        "up_reference_period": "W",
        "buy_target_price": "12.3400",
        "buy_expected_return_pct": "17.523800",
        "down_reference_period": "M",
        "sell_target_price": "9.1000",
        "sell_expected_return_pct": "13.333300",
        "up_sell_reference_period": "W",
        "clear_sell_ref_period": "W",
        "up_secondary_target_price": "13.2500",
        "up_secondary_expected_return_pct": "26.190500",
        "score": "80.5000",
        "pe_core": "12.3000",
    }


class ConditionBasisTest(unittest.TestCase):
    def test_fetch_period_contexts_uses_fast_fact_scan_without_distinct_sort(self) -> None:
        cursor = RecordingCursor()

        contexts = fetch_period_contexts(
            cursor,
            table_name="stock_daily_bar_fact",
            identity_column="stock_identity_key",
            source_trade_date="20260608",
            source_prev_trade_date="20260605",
            current_source_version="stock_daily_20260608_v1",
        )

        self.assertEqual(contexts, {})
        self.assertEqual(len(cursor.sql_calls), 2)
        joined_sql = "\n".join(cursor.sql_calls)
        self.assertNotIn("DISTINCT ON", joined_sql)
        self.assertIn("trade_date <> %s OR f.source_version = %s", joined_sql)
        self.assertIn("ORDER BY f.stock_identity_key, f.trade_date", cursor.sql_calls[1])

    def test_fetch_period_contexts_stock_prices_are_adjusted_to_source_trade_date_factor(self) -> None:
        cursor = RecordingCursor()

        fetch_period_contexts(
            cursor,
            table_name="stock_daily_bar_fact",
            identity_column="stock_identity_key",
            source_trade_date="20260615",
            source_prev_trade_date="20260612",
            current_source_version="stock_daily_20260615_v1",
        )

        joined_sql = "\n".join(cursor.sql_calls)
        self.assertIn("current_adj_factor", joined_sql)
        self.assertIn("ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR", joined_sql)
        self.assertIn("raw_open", joined_sql)
        self.assertIn("raw_close", joined_sql)
        self.assertIn("f.open * f.adj_factor / NULLIF(ca.current_adj_factor, 0)", joined_sql)
        self.assertIn("f.close * f.adj_factor / NULLIF(ca.current_adj_factor, 0)", joined_sql)

    def test_fetch_period_contexts_index_does_not_apply_stock_adjustment_factor(self) -> None:
        cursor = RecordingCursor()

        fetch_period_contexts(
            cursor,
            table_name="index_daily_bar_fact",
            identity_column="index_identity_key",
            source_trade_date="20260615",
            source_prev_trade_date="20260612",
            current_source_version="index_daily_20260615_v1",
        )

        joined_sql = "\n".join(cursor.sql_calls)
        self.assertNotIn("ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR", joined_sql)
        self.assertNotIn("current_adj_factor", joined_sql)

    def test_active_versions_from_ready_check_indexes_by_data_type(self) -> None:
        ready = {
            "checks": [
                {"data_type": "stock_daily", "active_source_version": "stock_daily_20260522_v1"},
                {"data_type": "board_daily", "active_source_version": "board_daily_20260522_v1"},
            ]
        }

        versions = active_versions_from_ready_check(ready)

        self.assertEqual(versions["stock_daily"]["active_source_version"], "stock_daily_20260522_v1")
        self.assertEqual(versions["board_daily"]["active_source_version"], "board_daily_20260522_v1")

    def test_count_quality_severities_counts_only_warnings_and_failures(self) -> None:
        items = [
            {"severity": "P0", "status": "passed"},
            {"severity": "P0", "status": "failed"},
            {"severity": "P1", "status": "warning"},
            {"severity": "P2", "status": "skipped"},
            {"severity": "P2", "status": "warning"},
        ]

        self.assertEqual(count_quality_severities(items), {"P0": 1, "P1": 1, "P2": 1})

    def test_schema_aligned_empty_fields_include_full_and_hint_conditions(self) -> None:
        necessary = empty_necessary_condition_fields()
        static = empty_static_structure_fields()

        self.assertIn("buy_full_necessary_base", necessary)
        self.assertIn("sell_full_necessary_key", necessary)
        self.assertIn("oversold_hint_key", necessary)
        self.assertIn("overbought_hint_necessary_base", necessary)
        self.assertIn("buy_target_price", static)
        self.assertIn("sell_target_price", static)
        self.assertIn("up_sell_reference_period", static)
        self.assertIn("down_buy_reference_period", static)
        self.assertIn("clear_sell_ref_period", static)

    def test_ready_check_failures_become_p0_diagnostics(self) -> None:
        ready = {
            "checks": [
                {
                    "data_type": "stock_financial",
                    "passed": False,
                    "failure_reasons": ["stock_financial row_count does not match stock universe"],
                    "fact": {"row_count": 2, "stock_universe_row_count": 5501},
                }
            ]
        }

        items = ready_check_failure_quality_items(ready)

        self.assertEqual(items[0]["severity"], "P0")
        self.assertEqual(items[0]["status"], "failed")
        self.assertEqual(items[0]["gate_code"], "condition_source_ready_stock_financial")
        self.assertEqual(items[0]["details"]["row_count"], 2)

    def test_stock_condition_universe_gap_manifest_is_reported_as_excluded_from_basis(self) -> None:
        ready = {
            "passed": True,
            "expected_condition_stock_universe": 5504,
            "excluded_from_condition_universe": 16,
            "condition_source_gap_manifest": {
                "manifest_count": 16,
                "valid_exclusion_actions": True,
            },
        }
        date_context = DateContext(
            source_trade_date="20260526",
            source_prev_trade_date="20260525",
            for_trade_date="20260527",
            prev_trade_date="20260526",
            for_trade_calendar_row_exists=True,
        )
        stock_summary = {
            "row_count": 5504,
            "stock_daily_fact_row_count": 5520,
            "missing_identity_key_count": 0,
            "board_code_violation_count": 0,
            "official_daily_unproved_count": 0,
            "daily_basic_join_count": 5504,
            "financial_join_count": 5504,
            "static_structure_coverage": {},
            "period_trigger_baseline_coverage": {},
            **stock_condition_universe_summary(ready),
        }

        items = build_quality_items(
            ready_check=ready,
            date_context=date_context,
            monitor_targets={
                "stock": {"exists": True, "active_count": 1},
                "index": {"exists": True, "active_count": 1},
                "board": {"exists": True, "active_count": 1},
            },
            stock_summary=stock_summary,
            index_summary={"missing_identity_key_count": 0, "fixed_default_index_missing_basis": [], "fixed_default_index_amount_baseline_warnings": [], "static_structure_coverage": {}, "period_trigger_baseline_coverage": {}},
            board_summary={"missing_identity_key_count": 0, "non_board_code_count": 0, "static_structure_coverage": {}, "period_trigger_baseline_coverage": {}},
        )

        by_code = {item["gate_code"]: item for item in items}
        self.assertEqual(by_code["stock_condition_universe_count"]["status"], "passed")
        self.assertEqual(by_code["condition_source_gap_excluded_from_basis"]["status"], "passed")
        self.assertEqual(by_code["condition_source_gap_excluded_from_basis"]["actual_value"], "16")

    def test_period_grade_uses_price_direction_and_amount_expansion(self) -> None:
        current = {"close": "11", "amount": "200"}
        previous = {"open": "9.5", "close": "10", "amount": "100"}

        self.assertEqual(period_grade(current, previous), "volume_up")
        self.assertEqual(period_grade({"close": "11", "amount": "80"}, previous), "low_volume_up")
        self.assertEqual(period_grade({"close": "9", "amount": "200"}, previous), "volume_down")
        self.assertEqual(period_grade({"close": "9", "amount": "80"}, previous), "low_volume_down")
        self.assertEqual(period_grade({"close": "10", "amount": "200"}, previous), "flat")

    def test_period_grade_uses_previous_entity_bounds_not_previous_close_only(self) -> None:
        previous = {"open": "12", "close": "10", "amount": "100"}

        self.assertEqual(period_grade({"close": "11", "amount": "200"}, previous), "flat")
        self.assertEqual(period_grade({"close": "12.1", "amount": "200"}, previous), "volume_up")
        self.assertEqual(period_grade({"close": "9.9", "amount": "80"}, previous), "low_volume_down")

    def test_002831_20260615_qfq_asof_period_context_matches_target_machine_level_score(self) -> None:
        dates = DateContext(
            source_trade_date="20260615",
            source_prev_trade_date="20260612",
            for_trade_date="20260616",
            prev_trade_date="20260615",
            for_trade_calendar_row_exists=True,
        )
        context = {
            "Y": {
                "current": {"open": "28.41", "close": "30.50", "amount": "451409.625539622642", "day_count": 106},
                "previous": {"open": "27.18", "close": "28.51", "amount": "138114.031938271605"},
                "seed": {"open": "20", "close": "21", "amount": "100000"},
            },
            "Q": {
                "current": {"open": "22.8568316482801615", "close": "30.50", "amount": "557877.921064", "day_count": 50},
                "previous": {"open": "19.9007841595966715", "close": "22.2053804244707668", "amount": "356348.647392857143"},
                "seed": {"open": "24", "close": "23", "amount": "300000"},
            },
            "M": {
                "current": {"open": "27.8653007345566910", "close": "30.50", "amount": "553417.225758181818", "day_count": 11},
                "previous": {"open": "26.4783400645108828", "close": "26.9966991028108313", "amount": "661125.065214444444"},
                "seed": {"open": "25", "close": "25.5", "amount": "500000"},
            },
            "W": {
                "current": {"open": "30.27", "close": "30.50", "amount": "638209.98932", "day_count": 1},
                "previous": {"open": "26.26", "close": "29.66", "amount": "649146.294768"},
                "seed": {"open": "25", "close": "26", "amount": "500000"},
            },
            "D": {
                "current": {"open": "30.27", "close": "30.50", "amount": "638209.98932", "day_count": 1},
                "previous": {"open": "30.46", "close": "29.66", "amount": "745660.38741"},
                "seed": {"open": "29", "close": "30", "amount": "500000"},
            },
        }
        for period, node in context.items():
            node["grade"] = period_grade(node["current"], node["previous"])
            seed_grade = period_grade(node["previous"], node["seed"])
            node["transition"] = transition_grade(period, node["grade"], seed_grade, node["current"])

        fields = computed_condition_fields(context, dates)

        self.assertEqual(fields["period_grade_y"], "volume_up")
        self.assertEqual(fields["period_grade_q"], "volume_up")
        self.assertEqual(fields["period_grade_m"], "low_volume_up")
        self.assertEqual(fields["period_grade_w"], "low_volume_up")
        self.assertEqual(fields["period_grade_d"], "low_volume_up")
        self.assertEqual(fields["period_transition_y"], "volume_up")
        self.assertEqual(fields["period_transition_q"], "volume_up")
        self.assertEqual(fields["period_transition_m"], "low_volume_up")
        self.assertEqual(fields["period_transition_w"], "volume_up")
        self.assertEqual(fields["period_transition_d"], "low_volume_up")
        self.assertEqual(fields["level_up_score"], 3098)

    def test_computed_condition_fields_keep_full_and_hint_separate(self) -> None:
        dates = DateContext(
            source_trade_date="20260522",
            source_prev_trade_date="20260521",
            for_trade_date="20260525",
            prev_trade_date="20260522",
            for_trade_calendar_row_exists=False,
        )
        context = {
            period: {
                "current": {"close": "11", "amount": "200", "day_count": 1},
                "previous": {"open": "9.5", "close": "10", "amount": "100"},
                "grade": "volume_up",
                "transition": "volume_up",
            }
            for period in ("Y", "Q", "M", "W", "D")
        }

        fields = computed_condition_fields(context, dates)

        self.assertEqual(fields["prev_up_str"], "YQMWD")
        self.assertEqual(fields["buy_necessary_periods"], [])
        self.assertEqual(fields["sell_necessary_periods"], ["Y", "Q", "M", "W", "D"])
        self.assertTrue(fields["buy_full_necessary_base"])
        self.assertEqual(fields["buy_full_necessary_key"], "BUY:FULL")
        self.assertFalse(fields["sell_full_necessary_base"])
        self.assertIsNone(fields["overbought_hint_key"])
        self.assertIsNone(fields["oversold_hint_key"])

    def test_computed_condition_fields_calculates_static_targets_and_clear_period(self) -> None:
        dates = DateContext(
            source_trade_date="20260522",
            source_prev_trade_date="20260521",
            for_trade_date="20260525",
            prev_trade_date="20260522",
            for_trade_calendar_row_exists=False,
        )
        context = {
            "Y": {
                "current": {"high": "20", "low": "10", "close": "18", "min_close": "12", "max_close": "18", "amount": "200", "start_trade_date": "20260102", "end_trade_date": "20260522"},
                "previous": {"open": "16", "close": "17", "amount": "100"},
                "grade": "volume_up",
                "transition": "volume_up",
            },
            "Q": {
                "current": {"high": "20", "low": "11", "close": "19", "min_close": "13", "max_close": "19", "amount": "200", "start_trade_date": "20260401", "end_trade_date": "20260522"},
                "previous": {"open": "17", "close": "18", "amount": "100"},
                "grade": "volume_up",
                "transition": "volume_up",
            },
            "M": {
                "current": {"high": "15", "low": "12", "close": "14", "min_close": "14", "max_close": "15", "amount": "200", "start_trade_date": "20260501", "end_trade_date": "20260522"},
                "previous": {"open": "13", "close": "14", "amount": "100"},
                "grade": "flat",
                "transition": "flat",
            },
            "W": {
                "current": {"high": "14", "low": "12", "close": "13", "min_close": "13", "max_close": "14", "amount": "80", "start_trade_date": "20260518", "end_trade_date": "20260522"},
                "previous": {"open": "14", "close": "15", "amount": "100"},
                "grade": "low_volume_down",
                "transition": "low_volume_down",
            },
            "D": {
                "current": {"high": "13", "low": "12", "close": "13", "min_close": "13", "max_close": "13", "amount": "80", "start_trade_date": "20260522", "end_trade_date": "20260522"},
                "previous": {"open": "14", "close": "14", "amount": "100"},
                "grade": "low_volume_down",
                "transition": "low_volume_down",
            },
        }

        fields = computed_condition_fields(context, dates)

        self.assertEqual(fields["main_up_anchor"], "Q")
        self.assertEqual(fields["up_reference_period"], "M")
        self.assertEqual(fields["up_amplitude"], "10")
        self.assertEqual(fields["up_base_price"], "14")
        self.assertEqual(fields["buy_target_price"], "24")
        self.assertEqual(fields["up_sell_reference_period"], "M")
        self.assertEqual(fields["clear_sell_ref_period"], "M")
        self.assertEqual(fields["main_down_anchor"], "W")
        self.assertEqual(fields["down_reference_period"], "D")
        self.assertEqual(fields["down_amplitude"], "3")
        self.assertEqual(fields["down_base_price"], "13")
        self.assertEqual(fields["sell_target_price"], "10")
        self.assertEqual(fields["down_buy_reference_period"], "D")
        self.assertEqual(fields["base_price_policy"], SYMMETRY_TARGET_BASE_PRICE_POLICY)
        self.assertEqual(fields["symmetry_anchor"], "Q")
        self.assertIsNone(fields["secondary_symmetry_anchor"])
        self.assertEqual(fields["amplitude_source_period"], "Q")
        self.assertEqual(fields["a_segment_start_date"], "20260102")
        self.assertEqual(fields["a_segment_end_date"], "20260522")
        self.assertEqual(fields["a_segment_high"], "20")
        self.assertEqual(fields["a_segment_low"], "10")
        self.assertEqual(fields["a_segment_amplitude"], "10")
        self.assertEqual(fields["base_price"], "14")
        self.assertEqual(fields["reference_target_price"], fields["buy_target_price"])
        self.assertIsNone(fields["secondary_target_price"])
        self.assertEqual(fields["target_price_trace_json"]["primary_direction"], "buy")
        self.assertEqual(fields["target_price_trace_json"]["legacy_alias"]["clear_sell_ref_period"], "M")
        self.assertNotIn("locked_target_price", fields)
        self.assertNotIn("target_lock_status", fields)

    def test_canonical_target_fields_null_negative_reference_target_price(self) -> None:
        fields = canonical_target_fields_for_direction(
            {
                "direction": "sell",
                "main_down_anchor": "Q",
                "down_reference_period": "M",
                "down_amplitude": "57.99",
                "down_base_price": "50.62761506276150627615062762",
                "sell_target_price": "-7.36238493723849372384937238",
                "down_buy_reference_period": "D",
                "down_trend_start_date": "20260105",
                "down_trend_end_date": "20260528",
                "down_segment_high": "95",
                "down_segment_low": "37.01",
                "up_sell_reference_period": "D",
                "clear_sell_ref_period": "D",
            },
            "sell",
        )

        self.assertEqual(fields["symmetry_anchor"], "Q")
        self.assertEqual(fields["base_price_policy"], SYMMETRY_TARGET_BASE_PRICE_POLICY)
        self.assertIsNone(fields["reference_target_price"])
        self.assertEqual(fields["target_price_trace_json"]["sell"]["target_price"], "-7.36238493723849372384937238")
        self.assertNotIn("locked_target_price", fields)
        self.assertNotIn("target_lock_status", fields)

    def test_computed_condition_fields_freezes_period_trigger_baseline(self) -> None:
        dates = DateContext(
            source_trade_date="20260522",
            source_prev_trade_date="20260521",
            for_trade_date="20260525",
            prev_trade_date="20260522",
            for_trade_calendar_row_exists=True,
        )
        context = {
            period: {
                "current": {
                    "period_key": f"current-{period}",
                    "open": "10",
                    "close": "11",
                    "amount": "200",
                    "avg_amount": "200",
                    "amount_total": "1000",
                    "day_count": 5,
                    "start_trade_date": "20260501",
                    "end_trade_date": "20260522",
                },
                "previous": {
                    "period_key": f"previous-{period}",
                    "open": "12",
                    "close": "10",
                    "amount": "100",
                    "avg_amount": "100",
                    "amount_total": "500",
                    "start_trade_date": "20260401",
                    "end_trade_date": "20260430",
                },
                "grade": "flat",
                "transition": "flat",
            }
            for period in PERIODS
        }

        baseline = computed_condition_fields(context, dates)["period_trigger_baseline_json"]

        self.assertEqual(baseline["baseline_version"], PERIOD_TRIGGER_BASELINE_VERSION)
        self.assertTrue(period_trigger_baseline_has_required_shape(baseline))
        self.assertEqual(baseline["periods"]["Y"]["previous_entity_high"], "12")
        self.assertEqual(baseline["periods"]["Y"]["previous_entity_low"], "10")
        self.assertTrue(baseline["periods"]["Y"]["baseline_ready"])
        self.assertEqual(baseline["periods"]["Y"]["baseline_missing_fields"], [])
        self.assertEqual(baseline["periods"]["Y"]["amount_metric"], "avg_amount")
        self.assertEqual(baseline["periods"]["D"]["amount_metric"], "amount")
        self.assertEqual(baseline["periods"]["W"]["current_trade_days_seed"], 5)
        self.assertTrue(period_trigger_baseline_period_ready(baseline, "Y"))
        self.assertEqual(period_trigger_baseline_not_ready_periods(baseline, PERIODS), [])

    def test_period_trigger_baseline_marks_missing_previous_entity_bounds_not_ready(self) -> None:
        dates = DateContext(
            source_trade_date="20260522",
            source_prev_trade_date="20260521",
            for_trade_date="20260525",
            prev_trade_date="20260522",
            for_trade_calendar_row_exists=True,
        )
        context = {
            period: {
                "current": {"period_key": f"current-{period}", "open": "10", "close": "11", "amount": "200", "avg_amount": "200"},
                "previous": {"period_key": f"previous-{period}", "amount": "100", "avg_amount": "100"},
                "grade": "unknown",
                "transition": "unknown",
            }
            for period in PERIODS
        }

        baseline = computed_condition_fields(context, dates)["period_trigger_baseline_json"]

        self.assertTrue(period_trigger_baseline_has_required_shape(baseline))
        self.assertFalse(period_trigger_baseline_period_ready(baseline, "Y"))
        self.assertEqual(period_trigger_baseline_not_ready_periods(baseline, ["Y", "D"]), ["Y", "D"])
        self.assertIn("previous_entity_high", baseline["periods"]["Y"]["baseline_missing_fields"])
        self.assertIn("previous_entity_low", baseline["periods"]["Y"]["baseline_missing_fields"])


    def test_static_reference_periods_fallback_to_d_when_no_anchor_exists(self) -> None:
        dates = DateContext(
            source_trade_date="20260522",
            source_prev_trade_date="20260521",
            for_trade_date="20260525",
            prev_trade_date="20260522",
            for_trade_calendar_row_exists=True,
        )
        context = {period: {"transition": "unknown", "current": {"close": "10"}} for period in PERIODS}

        fields = computed_condition_fields(context, dates)

        self.assertEqual(fields["up_sell_reference_period"], "D")
        self.assertEqual(fields["down_buy_reference_period"], "D")
        self.assertEqual(fields["clear_sell_ref_period"], "D")

    def test_n2r_fixed_index_golden_conditions_match_target_precompute(self) -> None:
        dates = DateContext(
            source_trade_date="20260522",
            source_prev_trade_date="20260521",
            for_trade_date="20260525",
            prev_trade_date="20260522",
            for_trade_calendar_row_exists=True,
        )
        golden = {
            "000001": ("YQM--", "---w-", "BUY:W,D", "SELL:Y,Q,M,D", ("volume_up", "volume_up", "volume_up", "low_volume_down", "flat")),
            "000016": ("-----", "---w-", "BUY:Y,Q,M,W,D", "SELL:Y,Q,M,D", ("flat", "flat", "flat", "low_volume_down", "flat")),
            "000300": ("YQM--", "---w-", "BUY:W,D", "SELL:Y,Q,M,D", ("volume_up", "volume_up", "volume_up", "low_volume_down", "flat")),
            "000688": ("YQMW-", "-----", "BUY:D", "SELL:Y,Q,M,W,D", ("volume_up", "volume_up", "volume_up", "volume_up", "flat")),
            "000852": ("YQM--", "-----", "BUY:W,D", "SELL:Y,Q,M,W,D", ("volume_up", "volume_up", "volume_up", "flat", "flat")),
            "000905": ("YQM--", "-----", "BUY:W,D", "SELL:Y,Q,M,W,D", ("volume_up", "volume_up", "volume_up", "flat", "flat")),
            "399001": ("YQM--", "-----", "BUY:W,D", "SELL:Y,Q,M,W,D", ("volume_up", "volume_up", "volume_up", "flat", "flat")),
            "399006": ("YQM--", "-----", "BUY:W,D", "SELL:Y,Q,M,W,D", ("volume_up", "volume_up", "volume_up", "low_volume_up", "flat")),
            "399303": ("YQM--", "-----", "BUY:W,D", "SELL:Y,Q,M,W,D", ("volume_up", "volume_up", "volume_up", "flat", "flat")),
        }

        self.assertEqual(len(DEFAULT_INDEX_POOL_IDENTITIES), 9)
        for code, (up_str, dn_str, buy_key, sell_key, transitions) in golden.items():
            context = {
                period: {
                    "current": {"amount": "200", "day_count": 1},
                    "previous": {"amount": "100"},
                    "grade": transition,
                    "transition": transition,
                }
                for period, transition in zip(("Y", "Q", "M", "W", "D"), transitions)
            }

            fields = computed_condition_fields(context, dates)

            self.assertEqual(fields["prev_up_str"], up_str, code)
            self.assertEqual(fields["prev_dn_str"], dn_str, code)
            self.assertEqual(fields["buy_necessary_key"], buy_key, code)
            self.assertEqual(fields["sell_necessary_key"], sell_key, code)
            self.assertFalse(fields["oversold_hint_necessary_base"], code)
            self.assertFalse(fields["overbought_hint_necessary_base"], code)

    def test_period_escalation_context_uses_same_window_predecessor_only(self) -> None:
        open_source_dates = [
            "20260701", "20260702", "20260703", "20260706", "20260707",
            "20260708", "20260709", "20260710", "20260713", "20260714",
        ]
        first = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260713", source_prev_trade_date="20260710",
                for_trade_date="20260714", prev_trade_date="20260713",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SH:600000",
            current_row={"period_transition_d": "volume_up"},
            previous_context=None,
            open_source_dates=open_source_dates,
        )
        context = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260714", source_prev_trade_date="20260713",
                for_trade_date="20260715", prev_trade_date="20260714",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SH:600000",
            current_row={"period_transition_d": "flat"},
            previous_context=first,
            open_source_dates=open_source_dates,
        )

        weekly = context["directions"]["buy"]["W"]
        self.assertEqual(context["contract_version"], PERIOD_ESCALATION_CONTEXT_VERSION)
        self.assertEqual(context["generation_mode"], "N2-period-escalation-daily-incremental-v1")
        self.assertEqual(context["state_epoch_trade_date"], "20260714")
        self.assertEqual(weekly["prerequisite_period"], "D")
        self.assertEqual(weekly["status"], "ready")
        self.assertTrue(weekly["seen"])
        self.assertTrue(weekly["previous_incremental_state_used"])
        self.assertEqual(weekly["observation_count"], 1)
        self.assertEqual(weekly["last_source_trade_date"], "20260713")
        sell_weekly = context["directions"]["sell"]["W"]
        self.assertEqual(sell_weekly["status"], "not_seen")
        self.assertFalse(sell_weekly["seen"])
        self.assertTrue(sell_weekly["previous_incremental_state_used"])
        for target_period in ("M", "Q", "Y"):
            self.assertEqual(context["directions"]["buy"][target_period]["status"], "not_ready")

    def test_20260713_positive_evidence_is_ready_while_missing_coverage_is_retained(self) -> None:
        open_source_dates = [
            "20260701", "20260702", "20260703", "20260706", "20260707",
            "20260708", "20260709", "20260710", "20260713",
        ]
        context = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260713", source_prev_trade_date="20260710",
                for_trade_date="20260714", prev_trade_date="20260713",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="index",
            identity_key="index:SH:000300",
            current_row={
                "period_transition_d": "volume_up",
                "period_transition_w": "volume_up",
                "period_transition_m": "volume_up",
                "period_transition_q": "volume_up",
            },
            previous_context=None,
            open_source_dates=open_source_dates,
        )

        weekly = context["directions"]["buy"]["W"]
        self.assertEqual(weekly["coverage_status"], "passed")
        self.assertEqual(weekly["expected_source_trade_date_count"], 1)
        self.assertEqual(weekly["observed_source_trade_date_count"], 1)
        self.assertEqual(weekly["status"], "ready")
        for target_period in ("M", "Q", "Y"):
            entry = context["directions"]["buy"][target_period]
            self.assertEqual(entry["coverage_status"], "incomplete")
            self.assertEqual(entry["status"], "ready")
            self.assertTrue(entry["seen"])
            self.assertEqual(entry["expected_source_trade_date_count"], 9)
            self.assertEqual(entry["observed_source_trade_date_count"], 1)
            self.assertEqual(entry["observation_count"], 1)
            self.assertEqual(entry["first_source_trade_date"], "20260713")
            self.assertEqual(entry["last_source_trade_date"], "20260713")
            self.assertEqual(entry["missing_source_trade_dates"], open_source_dates[:-1])

    def test_period_escalation_context_applies_current_sell_grade_without_cross_direction_pollution(self) -> None:
        context = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260713", source_prev_trade_date="20260710",
                for_trade_date="20260714", prev_trade_date="20260713",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="index",
            identity_key="index:SH:000300",
            current_row={"period_transition_d": "low_volume_down"},
            previous_context=None,
            open_source_dates=["20260713"],
        )

        self.assertEqual(context["directions"]["sell"]["W"]["status"], "ready")
        self.assertEqual(context["directions"]["buy"]["W"]["status"], "not_seen")

    def test_positive_evidence_is_directional_for_all_target_periods(self) -> None:
        for direction, transition, other_direction in (
            ("buy", "volume_up", "sell"),
            ("sell", "low_volume_down", "buy"),
        ):
            with self.subTest(direction=direction):
                context = build_period_escalation_context(
                    dates=DateContext(
                        source_trade_date="20260713", source_prev_trade_date="20260710",
                        for_trade_date="20260714", prev_trade_date="20260713",
                        for_trade_calendar_row_exists=True,
                    ),
                    asset_kind="board",
                    identity_key="board:TDX:881001",
                    current_row={
                        f"period_transition_{period}": transition
                        for period in ("d", "w", "m", "q")
                    },
                    previous_context=None,
                    open_source_dates=[
                        "20260701", "20260702", "20260703", "20260706", "20260707",
                        "20260708", "20260709", "20260710", "20260713",
                    ],
                )

                for target_period in ("W", "M", "Q", "Y"):
                    entry = context["directions"][direction][target_period]
                    self.assertEqual(entry["status"], "ready")
                    self.assertTrue(entry["seen"])
                    self.assertEqual(entry["observation_count"], 1)
                    self.assertFalse(context["directions"][other_direction][target_period]["seen"])

    def test_period_escalation_context_does_not_inherit_legacy_or_hash_tampered_context(self) -> None:
        open_source_dates = ["20260713", "20260714"]
        first = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260713", source_prev_trade_date="20260710",
                for_trade_date="20260714", prev_trade_date="20260713",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="board",
            identity_key="board:TDX:881001",
            current_row={"period_transition_d": "volume_up"},
            previous_context=None,
            open_source_dates=open_source_dates,
        )
        dates = DateContext(
            source_trade_date="20260714", source_prev_trade_date="20260713",
            for_trade_date="20260715", prev_trade_date="20260714",
            for_trade_calendar_row_exists=True,
        )
        legacy = dict(first)
        legacy.pop("generation_mode")
        tampered = dict(first)
        tampered["context_hash"] = "0" * 64
        epoch_tampered = dict(first)
        epoch_tampered["state_epoch_trade_date"] = "20260712"
        epoch_payload = dict(epoch_tampered)
        epoch_payload.pop("context_hash", None)
        epoch_tampered["context_hash"] = stable_json_hash(epoch_payload)
        for invalid_previous in (legacy, tampered, epoch_tampered):
            context = build_period_escalation_context(
                dates=dates,
                asset_kind="board",
                identity_key="board:TDX:881001",
                current_row={"period_transition_d": "flat"},
                previous_context=invalid_previous,
                open_source_dates=open_source_dates,
            )
            entry = context["directions"]["buy"]["W"]
            self.assertEqual(entry["status"], "not_ready")
            self.assertFalse(entry["seen"])
            self.assertFalse(entry["previous_incremental_state_used"])
            self.assertEqual(entry["expected_source_trade_date_count"], 2)
            self.assertEqual(entry["observed_source_trade_date_count"], 1)
            self.assertEqual(entry["missing_source_trade_dates"], ["20260713"])

    def test_attach_traces_the_exact_previous_source_condition_run(self) -> None:
        open_source_dates = ["20260713", "20260714"]
        previous_context = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260713", source_prev_trade_date="20260710",
                for_trade_date="20260714", prev_trade_date="20260713",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SH:600000",
            current_row={"period_transition_d": "volume_up"},
            previous_context=None,
            open_source_dates=open_source_dates,
        )
        attached = attach_period_escalation_context_to_row(
            {
                "asset_kind": "stock",
                "stock_identity_key": "stock:SH:600000",
                "period_transition_d": "flat",
                "period_trigger_baseline_json": {"periods": {period: {} for period in PERIODS}},
                "raw_json": {},
            },
            dates=DateContext(
                source_trade_date="20260714", source_prev_trade_date="20260713",
                for_trade_date="20260715", prev_trade_date="20260714",
                for_trade_calendar_row_exists=True,
            ),
            previous_context_by_identity={
                "stock:SH:600000": {
                    "identity_key": "stock:SH:600000",
                    "source_condition_run_id": "condition_layer_20260713_v1",
                    "period_trigger_baseline_json": {"period_escalation_context": previous_context},
                },
            },
            open_source_dates=open_source_dates,
        )
        context = attached["period_trigger_baseline_json"]["period_escalation_context"]
        entry = context["directions"]["buy"]["W"]
        self.assertTrue(entry["previous_incremental_state_used"])
        self.assertEqual(context["previous_context_hash"], previous_context["context_hash"])
        self.assertEqual(context["previous_source_condition_run_id"], "condition_layer_20260713_v1")

    def test_period_escalation_context_keeps_positive_evidence_despite_date_gap(self) -> None:
        context = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260715", source_prev_trade_date="20260714",
                for_trade_date="20260716", prev_trade_date="20260715",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SZ:000001",
            current_row={"period_transition_d": "volume_up"},
            previous_context=None,
            open_source_dates=["20260713", "20260714", "20260715"],
        )

        weekly = context["directions"]["buy"]["W"]
        self.assertEqual(weekly["status"], "ready")
        self.assertTrue(weekly["seen"])
        self.assertEqual(weekly["coverage_status"], "incomplete")
        self.assertEqual(weekly["expected_source_trade_date_count"], 3)
        self.assertEqual(weekly["observed_source_trade_date_count"], 1)
        self.assertEqual(weekly["missing_source_trade_dates"], ["20260713", "20260714"])
        self.assertEqual(weekly["observation_count"], 1)

    def test_incomplete_positive_state_is_inherited_without_losing_source_evidence(self) -> None:
        open_source_dates = ["20260713", "20260714", "20260715", "20260716"]
        first = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260715", source_prev_trade_date="20260714",
                for_trade_date="20260716", prev_trade_date="20260715",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SZ:000001",
            current_row={"period_transition_d": "volume_up"},
            previous_context=None,
            open_source_dates=open_source_dates,
        )
        inherited = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260716", source_prev_trade_date="20260715",
                for_trade_date="20260717", prev_trade_date="20260716",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SZ:000001",
            current_row={"period_transition_d": "flat"},
            previous_context=first,
            open_source_dates=open_source_dates,
        )

        weekly = inherited["directions"]["buy"]["W"]
        self.assertEqual(weekly["status"], "ready")
        self.assertTrue(weekly["seen"])
        self.assertEqual(weekly["coverage_status"], "incomplete")
        self.assertTrue(weekly["previous_incremental_state_used"])
        self.assertEqual(weekly["state_epoch_trade_date"], "20260715")
        self.assertEqual(weekly["observed_source_trade_date_count"], 2)
        self.assertEqual(weekly["missing_source_trade_dates"], ["20260713", "20260714"])
        self.assertEqual(weekly["observation_count"], 1)
        self.assertEqual(weekly["first_source_trade_date"], "20260715")
        self.assertEqual(weekly["last_source_trade_date"], "20260715")
        self.assertEqual(
            weekly["latest_source_basis_ref"],
            "current:stock:stock:SZ:000001:20260715",
        )

    def test_incomplete_negative_state_stays_not_ready_until_current_positive_match(self) -> None:
        open_source_dates = ["20260713", "20260714", "20260715", "20260716"]
        first = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260715", source_prev_trade_date="20260714",
                for_trade_date="20260716", prev_trade_date="20260715",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SZ:000001",
            current_row={"period_transition_d": "flat"},
            previous_context=None,
            open_source_dates=open_source_dates,
        )
        second = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260716", source_prev_trade_date="20260715",
                for_trade_date="20260717", prev_trade_date="20260716",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SZ:000001",
            current_row={"period_transition_d": "volume_up"},
            previous_context=first,
            open_source_dates=open_source_dates,
        )

        first_weekly = first["directions"]["buy"]["W"]
        self.assertEqual(first_weekly["status"], "not_ready")
        self.assertFalse(first_weekly["seen"])
        weekly = second["directions"]["buy"]["W"]
        self.assertEqual(weekly["status"], "ready")
        self.assertTrue(weekly["seen"])
        self.assertTrue(weekly["previous_incremental_state_used"])
        self.assertEqual(weekly["coverage_status"], "incomplete")
        self.assertEqual(weekly["observed_source_trade_date_count"], 2)
        self.assertEqual(weekly["missing_source_trade_dates"], ["20260713", "20260714"])
        self.assertEqual(weekly["observation_count"], 1)
        self.assertEqual(weekly["first_source_trade_date"], "20260716")
        self.assertEqual(weekly["last_source_trade_date"], "20260716")

    def test_rehashed_entry_semantic_invariant_tampering_fails_closed(self) -> None:
        open_source_dates = ["20260713", "20260714", "20260715", "20260716"]
        first = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260715", source_prev_trade_date="20260714",
                for_trade_date="20260716", prev_trade_date="20260715",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SZ:000001",
            current_row={"period_transition_d": "volume_up"},
            previous_context=None,
            open_source_dates=open_source_dates,
        )
        invalid_values = {
            "target_period": "M",
            "prerequisite_period": "W",
            "window_kind": "month",
            "window_key": "W:2026-99",
            "window_start": "20260714",
            "reset_for_trade_date": True,
            "required_transition": "low_volume_down",
            "state_epoch_trade_date": "20260713",
            "observation_end": "20260714",
            "previous_incremental_state_used": True,
            "observation_count": 0,
            "latest_source_basis_ref": "current:stock:stock:SZ:000001:20260714",
        }
        for field, invalid_value in invalid_values.items():
            with self.subTest(field=field):
                tampered = dict(first)
                tampered_directions = {
                    direction: dict(entries)
                    for direction, entries in first["directions"].items()
                }
                tampered_buy = dict(tampered_directions["buy"])
                tampered_weekly = dict(tampered_buy["W"])
                tampered_weekly[field] = invalid_value
                tampered_weekly_payload = dict(tampered_weekly)
                tampered_weekly_payload.pop("entry_hash", None)
                tampered_weekly["entry_hash"] = stable_json_hash(tampered_weekly_payload)
                tampered_buy["W"] = tampered_weekly
                tampered_directions["buy"] = tampered_buy
                tampered["directions"] = tampered_directions
                tampered_payload = dict(tampered)
                tampered_payload.pop("context_hash", None)
                tampered["context_hash"] = stable_json_hash(tampered_payload)

                second = build_period_escalation_context(
                    dates=DateContext(
                        source_trade_date="20260716", source_prev_trade_date="20260715",
                        for_trade_date="20260717", prev_trade_date="20260716",
                        for_trade_calendar_row_exists=True,
                    ),
                    asset_kind="stock",
                    identity_key="stock:SZ:000001",
                    current_row={"period_transition_d": "flat"},
                    previous_context=tampered,
                    open_source_dates=open_source_dates,
                )

                weekly = second["directions"]["buy"]["W"]
                self.assertEqual(weekly["status"], "not_ready")
                self.assertFalse(weekly["seen"])
                self.assertFalse(weekly["previous_incremental_state_used"])
                self.assertEqual(
                    weekly["missing_source_trade_dates"],
                    ["20260713", "20260714", "20260715"],
                )

    def test_all_target_windows_reset_without_inheriting_previous_state(self) -> None:
        cases = (
            ("W", "20260710", "20260709", "20260713", ["20260706", "20260710"]),
            ("M", "20260731", "20260730", "20260803", ["20260730", "20260731"]),
            ("Q", "20260930", "20260929", "20261008", ["20260929", "20260930"]),
            ("Y", "20261231", "20261230", "20270104", ["20261230", "20261231"]),
        )
        for target_period, source_date, source_prev_date, for_date, open_dates in cases:
            with self.subTest(target_period=target_period):
                context = build_period_escalation_context(
                    dates=DateContext(
                        source_trade_date=source_date,
                        source_prev_trade_date=source_prev_date,
                        for_trade_date=for_date,
                        prev_trade_date=source_date,
                        for_trade_calendar_row_exists=True,
                    ),
                    asset_kind="stock",
                    identity_key="stock:SZ:000001",
                    current_row={
                        "period_transition_d": "volume_up",
                        "period_transition_w": "volume_up",
                        "period_transition_m": "volume_up",
                        "period_transition_q": "volume_up",
                    },
                    previous_context=None,
                    open_source_dates=open_dates,
                )

                entry = context["directions"]["buy"][target_period]
                self.assertTrue(entry["reset_for_trade_date"])
                self.assertEqual(entry["coverage_status"], "not_applicable")
                self.assertEqual(entry["status"], "not_seen")
                self.assertFalse(entry["seen"])
                self.assertEqual(entry["expected_source_trade_date_count"], 0)

    def test_period_escalation_context_resets_week_on_new_for_trade_date(self) -> None:
        context = build_period_escalation_context(
            dates=DateContext(
                source_trade_date="20260710", source_prev_trade_date="20260709",
                for_trade_date="20260713", prev_trade_date="20260710",
                for_trade_calendar_row_exists=True,
            ),
            asset_kind="stock",
            identity_key="stock:SZ:000001",
            current_row={"period_transition_d": "volume_up"},
            previous_context=None,
            open_source_dates=["20260706", "20260707", "20260708", "20260709", "20260710"],
        )

        weekly = context["directions"]["buy"]["W"]
        self.assertTrue(weekly["reset_for_trade_date"])
        self.assertEqual(weekly["expected_source_trade_date_count"], 0)
        self.assertEqual(weekly["status"], "not_seen")
        self.assertFalse(weekly["seen"])

    def test_condition_projection_context_stock_is_ready_and_hash_stable(self) -> None:
        dates = DateContext("20260710", "20260709", "20260713", "20260710", True)
        row = condition_projection_basis_row("stock")
        expected_common_fields = (
            "name", "close", "up_reference_period", "buy_target_price",
            "buy_expected_return_pct", "down_reference_period", "sell_target_price",
            "sell_expected_return_pct", "clear_sell_ref_period",
            "up_secondary_target_price", "up_secondary_expected_return_pct",
        )

        first = build_condition_projection_context(dates=dates, current_row=row)
        second = build_condition_projection_context(dates=dates, current_row=row)

        self.assertEqual(first["contract_version"], CONDITION_PROJECTION_CONTEXT_VERSION)
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first["not_ready_reasons"], [])
        self.assertEqual(first["fields"]["name"], "浦发银行")
        self.assertEqual(first["fields"]["close"], "10.5")
        self.assertEqual(first["fields"]["buy_target_price"], "12.34")
        self.assertEqual(first["fields"]["score"], "80.5")
        self.assertEqual(first["fields"]["pe_core"], "12.3")
        self.assertEqual(tuple(first["fields"]), expected_common_fields + ("score", "pe_core"))
        self.assertEqual(first["context_hash"], second["context_hash"])
        self.assertTrue(condition_projection_context_hash_valid(first))
        changed = condition_projection_basis_row("stock")
        changed["buy_target_price"] = "12.35"
        self.assertNotEqual(
            first["context_hash"],
            build_condition_projection_context(dates=dates, current_row=changed)["context_hash"],
        )
        tampered = {**first, "fields": {**first["fields"], "close": "10.6"}}
        self.assertFalse(condition_projection_context_hash_valid(tampered))

    def test_condition_projection_context_index_and_board_use_exact_shapes(self) -> None:
        dates = DateContext("20260710", "20260709", "20260713", "20260710", True)
        expected_common_fields = (
            "name", "close", "up_reference_period", "buy_target_price",
            "buy_expected_return_pct", "down_reference_period", "sell_target_price",
            "sell_expected_return_pct", "clear_sell_ref_period",
            "up_secondary_target_price", "up_secondary_expected_return_pct",
        )

        index_context = build_condition_projection_context(
            dates=dates,
            current_row=condition_projection_basis_row("index"),
        )
        board_context = build_condition_projection_context(
            dates=dates,
            current_row=condition_projection_basis_row("board"),
        )

        self.assertEqual(index_context["status"], "ready")
        self.assertEqual(index_context["fields"]["name"], "上证指数")
        self.assertEqual(tuple(index_context["fields"]), expected_common_fields)
        self.assertEqual(tuple(board_context["fields"]), expected_common_fields)
        self.assertNotIn("score", index_context["fields"])
        self.assertNotIn("pe_core", index_context["fields"])
        self.assertEqual(board_context["status"], "ready")
        self.assertEqual(board_context["fields"]["name"], "银行")

    def test_condition_projection_context_index_and_board_validate_nullable_not_ready_and_hash(self) -> None:
        dates = DateContext("20260710", "20260709", "20260713", "20260710", True)
        optional_fields = (
            "up_reference_period", "buy_target_price", "buy_expected_return_pct",
            "down_reference_period", "sell_target_price", "sell_expected_return_pct",
            "clear_sell_ref_period", "up_secondary_target_price",
            "up_secondary_expected_return_pct",
        )

        for asset_kind, name_field in (("index", "name"), ("board", "board_name")):
            with self.subTest(asset_kind=asset_kind, case="nullable"):
                row = condition_projection_basis_row(asset_kind)
                for field in optional_fields:
                    row[field] = None
                row["up_sell_reference_period"] = None
                context = build_condition_projection_context(dates=dates, current_row=row)
                self.assertEqual(context["status"], "ready")
                self.assertEqual(context["nullable_fields"], list(optional_fields))
                self.assertTrue(condition_projection_context_hash_valid(context))
                tampered = {**context, "fields": {**context["fields"], "close": "10.6"}}
                self.assertFalse(condition_projection_context_hash_valid(tampered))

            with self.subTest(asset_kind=asset_kind, case="not_ready"):
                row = condition_projection_basis_row(asset_kind)
                row[name_field] = None
                context = build_condition_projection_context(dates=dates, current_row=row)
                self.assertEqual(context["status"], "not_ready")
                self.assertIn("name_missing", context["not_ready_reasons"])
                self.assertTrue(condition_projection_context_hash_valid(context))

    def test_condition_projection_context_optional_nulls_do_not_block_ready(self) -> None:
        dates = DateContext("20260710", "20260709", "20260713", "20260710", True)
        row = condition_projection_basis_row("stock")
        for field in (
            "up_reference_period", "buy_target_price", "buy_expected_return_pct",
            "down_reference_period", "sell_target_price", "sell_expected_return_pct",
            "clear_sell_ref_period", "up_secondary_target_price",
            "up_secondary_expected_return_pct", "score", "pe_core",
        ):
            row[field] = None
        row["up_sell_reference_period"] = None

        context = build_condition_projection_context(dates=dates, current_row=row)

        self.assertEqual(context["status"], "ready")
        self.assertEqual(context["not_ready_reasons"], [])
        self.assertEqual(
            context["nullable_fields"],
            [field for field in context["fields"] if field not in {"name", "close"}],
        )

    def test_condition_projection_context_fails_closed_for_core_contract_errors(self) -> None:
        good_dates = DateContext("20260710", "20260709", "20260713", "20260710", True)
        cases = []
        for mutation, reason in (
            (("name", None), "name_missing"),
            (("raw_json", {"close": "0"}), "raw_close_missing_or_non_positive"),
            (("raw_json", {}), "raw_close_missing_or_non_positive"),
            (("raw_json", {"close": "not-a-number"}), "raw_close_missing_or_non_positive"),
            (("stock_identity_key", "index:SH:600000"), "invalid_identity_key"),
            (("source_trade_date", "20260709"), "source_trade_date_mismatch"),
            (("for_trade_date", "20260714"), "for_trade_date_mismatch"),
            (("clear_sell_ref_period", "Q"), "clear_sell_ref_period_alias_mismatch"),
            (("clear_sell_ref_period", None), "clear_sell_ref_period_alias_mismatch"),
            (("up_sell_reference_period", None), "clear_sell_ref_period_alias_mismatch"),
        ):
            row = condition_projection_basis_row("stock")
            row[mutation[0]] = mutation[1]
            cases.append((good_dates, row, reason))
        missing_d_seed = condition_projection_basis_row("stock")
        missing_d_seed["period_trigger_baseline_json"]["periods"]["D"]["current_close_seed"] = None
        cases.append((good_dates, missing_d_seed, "d_current_close_seed_missing_or_non_positive"))
        mismatch = condition_projection_basis_row("stock")
        mismatch["raw_json"] = {"close": "10.6"}
        cases.append((good_dates, mismatch, "close_source_mismatch"))
        cases.append((
            DateContext("20260713", "20260710", "20260710", "20260713", True),
            condition_projection_basis_row("stock"),
            "trade_date_order_invalid",
        ))
        cases.append((
            DateContext("2026-07-10", "20260709", "20260713", "20260710", True),
            condition_projection_basis_row("stock"),
            "invalid_source_trade_date",
        ))

        for dates, row, reason in cases:
            with self.subTest(reason=reason):
                context = build_condition_projection_context(dates=dates, current_row=row)
                self.assertEqual(context["status"], "not_ready")
                self.assertIn(reason, context["not_ready_reasons"])
                self.assertTrue(condition_projection_context_hash_valid(context))

    def test_condition_projection_context_is_attached_after_incremental_context(self) -> None:
        dates = DateContext("20260710", "20260709", "20260713", "20260710", True)

        enriched = attach_period_escalation_context_to_row(
            condition_projection_basis_row("stock"),
            dates=dates,
            previous_context_by_identity={},
            open_source_dates=["20260706", "20260707", "20260708", "20260709", "20260710"],
        )
        baseline = enriched["period_trigger_baseline_json"]

        self.assertEqual(
            baseline["condition_projection_context"]["contract_version"],
            CONDITION_PROJECTION_CONTEXT_VERSION,
        )
        self.assertTrue(condition_projection_context_hash_valid(baseline["condition_projection_context"]))
        self.assertEqual(
            baseline["period_escalation_context"]["generation_mode"],
            PERIOD_ESCALATION_CONTEXT_GENERATION_MODE,
        )
        self.assertTrue(enriched["context_enrichment_hash"])

    def test_period_escalation_context_is_reenriched_and_materialized_without_new_columns(self) -> None:
        dates = DateContext(
            source_trade_date="20260714", source_prev_trade_date="20260713",
            for_trade_date="20260715", prev_trade_date="20260714",
            for_trade_calendar_row_exists=True,
        )
        enriched = attach_period_escalation_context_to_row(
            {
                "asset_kind": "stock",
                "stock_identity_key": "stock:SH:600000",
                "source_trade_date": dates.source_trade_date,
                "source_version": "stock_daily_20260714_v1",
                "period_transition_d": "volume_up",
                "period_trigger_baseline_json": {"periods": {period: {} for period in PERIODS}},
                "raw_json": {},
            },
            dates=dates,
            previous_context_by_identity={},
            open_source_dates=["20260713", "20260714"],
        )
        enriched.update(
            {
                "identity_key": "stock:SH:600000",
                "condition_key": "BUY:W",
                "source_row_id": 101,
                "context_source_table": "stock_minute_target_scope",
                "allowed_signal_types": ["BUY"],
            }
        )

        rows = build_materialization_payload_rows(
            {"stock": [enriched], "index": [], "board": []},
            source_condition_run_id="condition_layer_20260714_v1",
            target_run_id="condition_context_escalation_20260715_v1",
            for_trade_date="20260715",
        )
        baseline = rows["stock"][0]["payload_json"]["period_trigger_baseline_json"]

        self.assertEqual(baseline["period_escalation_context"]["contract_version"], PERIOD_ESCALATION_CONTEXT_VERSION)
        self.assertTrue(enriched["context_enrichment_hash"])

    def test_previous_context_run_and_row_reads_are_exact_and_fail_closed_on_duplicates(self) -> None:
        dates = DateContext(
            source_trade_date="20260714", source_prev_trade_date="20260713",
            for_trade_date="20260715", prev_trade_date="20260714",
            for_trade_calendar_row_exists=True,
        )
        duplicate_cursor = RecordingCursor(rows=[
            {"run_id": "condition_a", "updated_at": "2026-07-13T18:00:00+08:00"},
            {"run_id": "condition_b", "updated_at": "2026-07-13T18:00:01+08:00"},
        ])
        with self.assertRaisesRegex(ValueError, "period_escalation_previous_run_ambiguous"):
            fetch_period_escalation_previous_context_run(duplicate_cursor, dates)
        self.assertEqual(duplicate_cursor.params_calls[0], ("20260713", "20260714"))
        self.assertIn("status = 'passed_active'", duplicate_cursor.sql_calls[0])
        self.assertIn("for_trade_date = %s", duplicate_cursor.sql_calls[0])

        single_cursor = RecordingCursor(rows=[{"run_id": "condition_layer_20260713_v1", "updated_at": "stamp"}])
        self.assertEqual(
            fetch_period_escalation_previous_context_run(single_cursor, dates),
            {"run_id": "condition_layer_20260713_v1", "updated_at": "stamp"},
        )
        self.assertIsNone(fetch_period_escalation_previous_context_run(RecordingCursor(), dates))

        row_cursor = RecordingCursor()
        self.assertEqual(
            fetch_period_escalation_previous_context_rows(
                row_cursor,
                asset_kind="stock",
                identity_keys=["stock:SH:600000"],
                source_prev_trade_date="20260713",
                previous_run_id="condition_layer_20260713_v1",
            ),
            [],
        )
        self.assertEqual(row_cursor.params_calls[0], ("condition_layer_20260713_v1", "20260713", ["stock:SH:600000"]))
        query = row_cursor.sql_calls[0]
        self.assertIn("b.run_id = %s", query)
        self.assertIn("b.source_trade_date = %s", query)
        self.assertNotIn("b.source_trade_date >=", query)
        self.assertNotIn("common_trade_calendar", query)
        self.assertIn("period_trigger_baseline_json", query)

    def test_previous_context_rows_are_indexed_once_per_asset_batch_and_duplicates_fail_closed(self) -> None:
        class SinglePassRows:
            def __init__(self, rows: list[dict[str, object]]) -> None:
                self.rows = rows
                self.iteration_count = 0

            def __iter__(self):
                self.iteration_count += 1
                if self.iteration_count > 1:
                    raise AssertionError("previous context rows were traversed more than once")
                return iter(self.rows)

        current_rows = [
            {
                "asset_kind": "stock",
                "stock_identity_key": f"stock:SH:{index:06d}",
                "period_transition_d": "flat",
                "period_trigger_baseline_json": {"periods": {period: {} for period in PERIODS}},
                "raw_json": {},
            }
            for index in range(256)
        ]
        previous_rows = SinglePassRows([
            {"identity_key": f"stock:SH:{index:06d}"}
            for index in range(256)
        ])
        summaries = {"stock": {"basis_rows": current_rows}}
        dates = DateContext(
            source_trade_date="20260714", source_prev_trade_date="20260713",
            for_trade_date="20260715", prev_trade_date="20260714",
            for_trade_calendar_row_exists=True,
        )

        with patch(
            "ashare_v3.condition.basis.fetch_period_escalation_previous_context_rows",
            return_value=previous_rows,
        ) as fetch_previous:
            attach_period_escalation_contexts(
                object(),
                dates,
                summaries,
                previous_context_run={"run_id": "condition_layer_20260713_v1"},
                open_source_dates=["20260713", "20260714"],
            )

        self.assertEqual(previous_rows.iteration_count, 1)
        fetch_previous.assert_called_once()
        self.assertEqual(len(summaries["stock"]["basis_rows"]), 256)
        self.assertEqual(len(summaries["stock"]["sample_basis_rows"]), 3)
        with self.assertRaisesRegex(ValueError, "period_escalation_previous_context_duplicate_identity"):
            index_period_escalation_previous_context_rows([
                {"identity_key": "stock:SH:600000"},
                {"identity_key": "stock:SH:600000"},
            ])

    def test_current_row_uses_one_previous_context_mapping_lookup(self) -> None:
        class LookupSpy(dict[str, object]):
            def __init__(self) -> None:
                super().__init__({"stock:SH:600000": {"identity_key": "stock:SH:600000"}})
                self.get_call_count = 0

            def get(self, key: object, default: object = None) -> object:
                self.get_call_count += 1
                return super().get(key, default)

            def __iter__(self):
                raise AssertionError("row-level previous-context lookup must not iterate the mapping")

        previous_context_by_identity = LookupSpy()
        attached = attach_period_escalation_context_to_row(
            {
                "asset_kind": "stock",
                "stock_identity_key": "stock:SH:600000",
                "period_transition_d": "flat",
                "period_trigger_baseline_json": {"periods": {period: {} for period in PERIODS}},
                "raw_json": {},
            },
            dates=DateContext(
                source_trade_date="20260714", source_prev_trade_date="20260713",
                for_trade_date="20260715", prev_trade_date="20260714",
                for_trade_calendar_row_exists=True,
            ),
            previous_context_by_identity=previous_context_by_identity,
            open_source_dates=["20260713", "20260714"],
        )

        self.assertEqual(previous_context_by_identity.get_call_count, 1)
        self.assertIn("period_escalation_context", attached["period_trigger_baseline_json"])


if __name__ == "__main__":
    unittest.main()
