import unittest

from ashare_v3.condition.basis import (
    DateContext,
    DEFAULT_INDEX_POOL_IDENTITIES,
    SYMMETRY_TARGET_BASE_PRICE_POLICY,
    PERIOD_TRIGGER_BASELINE_VERSION,
    PERIODS,
    active_versions_from_ready_check,
    build_quality_items,
    canonical_target_fields_for_direction,
    computed_condition_fields,
    count_quality_severities,
    empty_necessary_condition_fields,
    empty_static_structure_fields,
    fetch_period_contexts,
    period_grade,
    period_trigger_baseline_has_required_shape,
    period_trigger_baseline_not_ready_periods,
    period_trigger_baseline_period_ready,
    ready_check_failure_quality_items,
    stock_condition_universe_summary,
    transition_grade,
)


class RecordingCursor:
    def __init__(self) -> None:
        self.sql_calls: list[str] = []

    def execute(self, sql: str, params: object = None) -> None:
        del params
        self.sql_calls.append(sql)

    def fetchall(self) -> list[dict[str, object]]:
        return []


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


if __name__ == "__main__":
    unittest.main()
