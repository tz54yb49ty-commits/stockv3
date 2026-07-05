import unittest
from decimal import Decimal

from ashare_v3.condition.basis import (
    SYMMETRY_TARGET_AMPLITUDE_PRICE_POLICY,
    SYMMETRY_TARGET_BASE_PRICE_POLICY,
    canonical_target_fields_for_direction,
    compute_static_structure_fields,
    compute_secondary_static_fields,
    target_machine_adjusted_bounds_for_daily_rows,
)
from ashare_v3.condition.display_basis import DOMAIN_CONFIGS, build_display_rows_for_domain
from ashare_v3.condition.pool import static_pool_fields
from ashare_v3.condition.scope import scope_static_filter_fields


class ConditionSymmetryTargetPriceTest(unittest.TestCase):
    def test_000600_20260529_buy_symmetry_target_uses_current_w_volume_up_segment(self) -> None:
        fields = compute_static_structure_fields(context_000600_20260529_buy())

        self.assertEqual(fields["main_up_anchor"], "W")
        self.assertEqual(fields["up_reference_period"], "D")
        self.assertEqual(fields["up_trend_start_date"], "20260518")
        self.assertEqual(fields["up_trend_end_date"], "20260529")
        self.assertEqual(fields["up_segment_low"], "9.75")
        self.assertEqual(fields["up_segment_high"], "12.55")
        self.assertEqual(fields["up_amplitude"], "2.8")
        self.assertEqual(fields["up_trend_break_date"], "20260519")
        self.assertEqual(fields["up_reference_window_start"], "20260520")
        self.assertEqual(fields["up_reference_window_end"], "20260529")
        self.assertEqual(fields["up_base_price"], "10.13")
        self.assertEqual(fields["buy_target_price"], "12.93")
        self.assertEqual(fields["reference_target_price"], "12.93")
        self.assertIsNone(fields["secondary_target_price"])

        trace = fields["target_price_trace_json"]
        self.assertEqual(trace["primary"]["anchor"], "W")
        self.assertEqual(trace["primary"]["segment_start_date"], "20260518")
        self.assertEqual(trace["primary"]["segment_end_date"], "20260529")
        self.assertEqual(trace["primary"]["segment_low"], "9.75")
        self.assertEqual(trace["primary"]["segment_high"], "12.55")
        self.assertEqual(trace["primary"]["amplitude"], "2.8")
        self.assertEqual(trace["primary"]["base_price"], "10.13")
        self.assertEqual(trace["primary"]["target_price"], "12.93")

    def test_300327_20260529_buy_symmetry_target_uses_y_primary_and_w_secondary_anchor(self) -> None:
        fields = compute_static_structure_fields(context_300327_20260529_buy())

        self.assertEqual(fields["main_up_anchor"], "Y")
        self.assertEqual(fields["up_reference_period"], "Q")
        self.assertEqual(fields["up_trend_break_date"], "20260331")
        self.assertEqual(fields["up_reference_window_start"], "20260401")
        self.assertEqual(fields["up_reference_window_end"], "20260529")
        self.assertEqual(fields["up_base_price"], "30")
        self.assertEqual(fields["up_amplitude"], "8.27")
        self.assertEqual(fields["buy_target_price"], "38.27")
        self.assertEqual(fields["reference_target_price"], "38.27")

        self.assertEqual(fields["up_secondary_anchor"], "W")
        self.assertEqual(fields["up_secondary_reference_period"], "D")
        self.assertEqual(fields["up_secondary_trend_start_date"], "20260518")
        self.assertEqual(fields["up_secondary_trend_end_date"], "20260529")
        self.assertEqual(fields["up_secondary_amplitude"], "2.8")
        self.assertEqual(fields["up_secondary_base_price"], "30.24")
        self.assertEqual(fields["up_secondary_target_price"], "33.04")
        self.assertEqual(fields["secondary_symmetry_anchor"], "W")
        self.assertEqual(fields["secondary_target_price"], "33.04")

        trace = fields["target_price_trace_json"]
        self.assertEqual(trace["primary"]["anchor"], "Y")
        self.assertEqual(trace["primary"]["reference_period"], "Q")
        self.assertEqual(trace["primary"]["trend_break_date"], "20260331")
        self.assertEqual(trace["secondary"]["anchor"], "W")
        self.assertEqual(trace["secondary"]["reference_period"], "D")
        self.assertEqual(trace["secondary"]["target_price"], "33.04")

    def test_target_machine_bounds_normalize_historical_entity_prices_by_current_adj_factor(self) -> None:
        segment_high, segment_low = target_machine_adjusted_bounds_for_daily_rows(
            [
                row("20250407", "22.00", "22.57", "18.73", "19.41", "100", adj_factor="3.1057"),
                row("20260128", "32.43", "34.28", "31.90", "34.28", "100", adj_factor="3.1316"),
                row("20260529", "29.36", "32.43", "29.33", "31.43", "100", adj_factor="3.1316"),
            ]
        )

        self.assertEqual(segment_high, Decimal("34.28"))
        self.assertEqual(segment_low, Decimal("19.25"))

    def test_target_machine_bounds_do_not_double_adjust_already_normalized_rows(self) -> None:
        segment_high, segment_low = target_machine_adjusted_bounds_for_daily_rows(
            [
                {
                    "trade_date": "20251021",
                    "open": "17.8553674138725503",
                    "close": "19.6766288997912883",
                    "adj_factor": "2.5843",
                    "current_adj_factor": "3.6893",
                    "adjustment_policy": "ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR",
                },
                {
                    "trade_date": "20260615",
                    "open": "30.27",
                    "close": "30.50",
                    "adj_factor": "3.6893",
                    "current_adj_factor": "3.6893",
                    "adjustment_policy": "ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR",
                },
            ]
        )

        self.assertEqual(segment_high, Decimal("30.50"))
        self.assertEqual(segment_low, Decimal("17.86"))

    def test_002831_20260615_buy_target_uses_single_adjusted_q_anchor_and_w_secondary(self) -> None:
        fields = compute_static_structure_fields(context_002831_20260615_buy())

        self.assertEqual(fields["main_up_anchor"], "Q")
        self.assertEqual(fields["up_reference_period"], "M")
        self.assertEqual(fields["up_trend_start_date"], "20251009")
        self.assertEqual(fields["up_trend_end_date"], "20260615")
        self.assertEqual(fields["up_segment_low"], "17.86")
        self.assertNotEqual(fields["up_segment_low"], "12.51")
        self.assertEqual(fields["up_segment_high"], "31.65")
        self.assertEqual(fields["up_amplitude"], "13.79")
        self.assertEqual(fields["up_base_price"], "26.88")
        self.assertEqual(fields["buy_target_price"], "40.67")
        self.assertEqual(fields["reference_target_price"], "40.67")

        self.assertEqual(fields["up_secondary_anchor"], "W")
        self.assertEqual(fields["up_secondary_reference_period"], "D")
        self.assertEqual(fields["up_secondary_trend_start_date"], "20260608")
        self.assertEqual(fields["up_secondary_trend_end_date"], "20260615")
        self.assertEqual(fields["up_secondary_amplitude"], "4.24")
        self.assertEqual(fields["up_secondary_base_price"], "29.66")
        self.assertEqual(fields["up_secondary_target_price"], "33.9")
        self.assertEqual(fields["secondary_target_price"], "33.9")

        trace = fields["target_price_trace_json"]
        self.assertEqual(trace["primary"]["segment_low_date"], "20251021")
        self.assertEqual(trace["primary"]["segment_high_date"], "20260520")
        self.assertEqual(trace["secondary"]["segment_low_date"], "20260608")
        self.assertEqual(trace["secondary"]["segment_high_date"], "20260615")

    def test_anchor_segment_does_not_merge_initial_unknown_week(self) -> None:
        fields = compute_static_structure_fields(context_unknown_first_week_buy())

        self.assertEqual(fields["main_up_anchor"], "W")
        self.assertEqual(fields["up_trend_start_date"], "20260512")
        self.assertEqual(fields["up_trend_end_date"], "20260516")
        self.assertEqual(fields["up_segment_low"], "10.2")
        self.assertEqual(fields["up_segment_high"], "11.2")

    def test_000543_20260529_buy_symmetry_target_uses_completed_d_volume_up_segment_end(self) -> None:
        fields = compute_static_structure_fields(context_000543_20260529_buy())

        self.assertEqual(fields["main_up_anchor"], "W")
        self.assertEqual(fields["up_reference_period"], "D")
        self.assertEqual(fields["up_trend_start_date"], "20260506")
        self.assertEqual(fields["up_trend_end_date"], "20260529")
        self.assertEqual(fields["up_segment_low"], "8.09")
        self.assertEqual(fields["up_segment_high"], "9.8")
        self.assertEqual(fields["up_amplitude"], "1.71")
        self.assertEqual(fields["up_trend_break_date"], "20260526")
        self.assertEqual(fields["up_reference_window_start"], "20260527")
        self.assertEqual(fields["up_reference_window_end"], "20260529")
        self.assertEqual(fields["up_base_price"], "9.11")
        self.assertEqual(fields["buy_target_price"], "10.82")
        self.assertEqual(fields["reference_target_price"], "10.82")
        self.assertIsNone(fields["secondary_target_price"])

        trace = fields["target_price_trace_json"]
        self.assertEqual(trace["amplitude_price_policy"], "OFFICIAL_HIGH_LOW")
        self.assertEqual(trace["primary"]["anchor"], "W")
        self.assertEqual(trace["primary"]["reference_period"], "D")
        self.assertEqual(trace["primary"]["segment_start_date"], "20260506")
        self.assertEqual(trace["primary"]["segment_end_date"], "20260529")
        self.assertEqual(trace["primary"]["segment_low"], "8.09")
        self.assertEqual(trace["primary"]["segment_high"], "9.8")
        self.assertEqual(trace["primary"]["amplitude"], "1.71")
        self.assertEqual(trace["primary"]["amplitude_price_policy"], "OFFICIAL_HIGH_LOW")
        self.assertEqual(trace["primary"]["trend_break_date"], "20260526")
        self.assertEqual(trace["primary"]["base_window_start"], "20260527")
        self.assertEqual(trace["primary"]["base_window_end"], "20260529")
        self.assertEqual(trace["primary"]["base_price"], "9.11")
        self.assertEqual(trace["primary"]["target_price"], "10.82")
        self.assertIsNone(trace["secondary_anchor"])
        self.assertIsNone(trace["secondary_target_price"])
        self.assertEqual(SYMMETRY_TARGET_AMPLITUDE_PRICE_POLICY, "OFFICIAL_HIGH_LOW")

    def test_000027_20260529_buy_symmetry_target_remains_target_machine_golden(self) -> None:
        fields = compute_static_structure_fields(context_000027_20260529_buy())

        self.assertEqual(fields["main_up_anchor"], "W")
        self.assertEqual(fields["up_reference_period"], "D")
        self.assertEqual(fields["up_base_price"], "7.25")
        self.assertEqual(fields["up_amplitude"], "1.2")
        self.assertEqual(fields["buy_target_price"], "8.45")
        self.assertEqual(fields["reference_target_price"], "8.45")
        self.assertEqual(fields["up_trend_break_date"], "20260519")
        self.assertEqual(fields["target_price_trace_json"]["primary"]["target_price"], "8.45")

    def test_000027_20260528_buy_symmetry_target_uses_anchor_segment_and_post_break_min_close(self) -> None:
        fields = compute_static_structure_fields(context_000027_buy())

        self.assertEqual(fields["main_up_anchor"], "W")
        self.assertEqual(fields["up_reference_period"], "D")
        self.assertEqual(fields["up_trend_start_date"], "20260506")
        self.assertEqual(fields["up_trend_end_date"], "20260528")
        self.assertEqual(fields["up_segment_low"], "6.88")
        self.assertEqual(fields["up_segment_high"], "8.05")
        self.assertEqual(fields["up_amplitude"], "1.17")
        self.assertEqual(fields["up_reference_window_start"], "20260520")
        self.assertEqual(fields["up_reference_window_end"], "20260528")
        self.assertEqual(fields["up_base_price"], "7.25")
        self.assertEqual(fields["buy_target_price"], "8.42")
        self.assertEqual(fields["reference_target_price"], "8.42")
        self.assertEqual(fields["symmetry_anchor"], "W")
        self.assertEqual(fields["amplitude_source_period"], "W")
        self.assertEqual(fields["base_price"], "7.25")

        trace = fields["target_price_trace_json"]
        self.assertEqual(trace["primary_direction"], "buy")
        self.assertEqual(trace["base_price_policy"], SYMMETRY_TARGET_BASE_PRICE_POLICY)
        self.assertEqual(trace["primary"]["anchor"], "W")
        self.assertEqual(trace["primary"]["reference_period"], "D")
        self.assertEqual(trace["primary"]["segment_start_date"], "20260506")
        self.assertEqual(trace["primary"]["segment_end_date"], "20260528")
        self.assertEqual(trace["primary"]["segment_low"], "6.88")
        self.assertEqual(trace["primary"]["segment_high"], "8.05")
        self.assertEqual(trace["primary"]["amplitude"], "1.17")
        self.assertEqual(trace["primary"]["amplitude_price_policy"], "OFFICIAL_HIGH_LOW")
        self.assertEqual(trace["primary"]["trend_break_date"], "20260519")
        self.assertEqual(trace["primary"]["base_window_start"], "20260520")
        self.assertEqual(trace["primary"]["base_window_end"], "20260528")
        self.assertEqual(trace["primary"]["base_price"], "7.25")
        self.assertEqual(trace["primary"]["target_price"], "8.42")
        self.assertNotIn("locked_target_price", fields)
        self.assertNotIn("target_lock_status", fields)

    def test_down_symmetry_target_mirrors_buy_formula_with_post_break_max_close(self) -> None:
        fields = compute_static_structure_fields(context_down_mirror())

        self.assertEqual(fields["main_down_anchor"], "W")
        self.assertEqual(fields["down_reference_period"], "D")
        self.assertEqual(fields["down_trend_start_date"], "20260506")
        self.assertEqual(fields["down_trend_end_date"], "20260528")
        self.assertEqual(fields["down_segment_high"], "10")
        self.assertEqual(fields["down_segment_low"], "8.8")
        self.assertEqual(fields["down_amplitude"], "1.2")
        self.assertEqual(fields["down_reference_window_start"], "20260520")
        self.assertEqual(fields["down_reference_window_end"], "20260528")
        self.assertEqual(fields["down_base_price"], "9.6")
        self.assertEqual(fields["sell_target_price"], "8.4")

        sell_fields = {
            **fields,
            **{
                "direction": "sell",
            },
        }
        pool_fields = static_pool_fields(sell_fields, direction="sell")
        self.assertEqual(pool_fields["reference_target_price"], "8.4")
        self.assertEqual(pool_fields["symmetry_anchor"], "W")
        self.assertEqual(pool_fields["amplitude_source_period"], "W")
        self.assertEqual(pool_fields["target_price_trace_json"]["primary"]["trend_break_date"], "20260519")

    def test_negative_down_secondary_target_price_is_stored_as_null_with_trace(self) -> None:
        side = {
            "direction": "sell",
            "anchor": "M",
            "reference_period": "W",
            "segment_start_date": "20260506",
            "segment_end_date": "20260630",
            "amplitude": "1.54",
            "base_price": "1.24",
            "target_price": "-0.3",
        }

        fields = compute_secondary_static_fields({}, side, "sell")

        self.assertIsNone(fields["down_secondary_target_price"])
        self.assertEqual(fields["_down_secondary_target_price_raw_candidate"], "-0.3")
        self.assertEqual(fields["_down_secondary_target_price_warning_reason"], "down_secondary_target_price_non_positive")

        canonical = canonical_target_fields_for_direction(
            {
                **fields,
                "_secondary_sell_target_side": side,
                "direction": "buy",
                "main_up_anchor": "W",
                "up_reference_period": "D",
                "up_amplitude": "1",
                "up_base_price": "9",
                "buy_target_price": "10",
            },
            "buy",
        )

        trace = canonical["target_price_trace_json"]
        self.assertIn("down_secondary_target_price_non_positive", trace["warnings"])
        self.assertEqual(trace["down_secondary"]["target_price"], "-0.3")
        self.assertIsNone(trace["target_price_normalization"]["down_secondary_target_price"]["stored_target_price"])

    def test_positive_down_secondary_target_price_is_unchanged(self) -> None:
        fields = compute_secondary_static_fields(
            {},
            {
                "direction": "sell",
                "anchor": "M",
                "reference_period": "W",
                "amplitude": "1",
                "base_price": "3",
                "target_price": "2",
            },
            "sell",
        )

        self.assertEqual(fields["down_secondary_target_price"], "2")
        self.assertNotIn("_down_secondary_target_price_warning_reason", fields)

    def test_pool_scope_display_inherit_canonical_target_fields_without_locked_target_fields(self) -> None:
        basis = {
            "for_trade_date": "20260529",
            "source_trade_date": "20260528",
            "prev_trade_date": "20260528",
            "stock_identity_key": "stock:SZ:000027",
            "code": "000027",
            "exchange": "SZ",
            "name": "深圳能源",
            "direction": "buy",
            "up_sell_reference_period": "D",
            "down_buy_reference_period": "D",
            "clear_sell_ref_period": "D",
            **compute_static_structure_fields(context_000027_buy()),
        }

        pool_fields = static_pool_fields(basis, direction="buy")
        scope_fields = scope_static_filter_fields(pool_fields)
        display_fields = build_display_rows_for_domain(
            DOMAIN_CONFIGS["stock"],
            basis_rows=[{**basis, "stock_condition_basis_id": 1, "source_version": "run1", "run_id": "run1"}],
            pool_rows=[
                {
                    **pool_fields,
                    "stock_condition_pool_id": 10,
                    "stock_identity_key": "stock:SZ:000027",
                    "condition_key": "BUY:D",
                    "allowed_signal_types": ["BUY"],
                    "lane": "stock_trade",
                    "monitor_type": "stock_buy_monitor",
                    "selected_reason": ["test"],
                    "excluded_reason": [],
                }
            ],
            scope_rows=[
                {
                    **scope_fields,
                    "stock_minute_target_scope_id": 100,
                    "stock_identity_key": "stock:SZ:000027",
                    "condition_key": "BUY:D",
                    "source_condition_pool_id": 10,
                }
            ],
        )[0]

        for row in (pool_fields, scope_fields, display_fields):
            self.assertEqual(row["reference_target_price"], "8.42")
            self.assertEqual(row["target_price_trace_json"]["primary"]["target_price"], "8.42")
            self.assertNotIn("locked_target_price", row)
            self.assertNotIn("target_lock_status", row)
        self.assertEqual(pool_fields["target_price_trace_json"], basis["target_price_trace_json"])
        self.assertEqual(scope_fields["target_price_trace_json"], pool_fields["target_price_trace_json"])
        self.assertEqual(display_fields["target_price_trace_json"], basis["target_price_trace_json"])
        self.assertEqual(display_fields["clear_sell_ref_period"], display_fields["up_sell_reference_period"])


def context_000027_buy() -> dict[str, object]:
    context = base_period_context("volume_up", daily_rows_000027_buy())
    # Keep aggregate values that reproduce the legacy wrong 10.01 path if daily
    # segment logic is not used: 8.05 + (8.48 - 6.52).
    for period in ("Y", "Q"):
        context[period]["current"].update(
            {
                "start_trade_date": "20260105",
                "end_trade_date": "20260528",
                "high": "8.48",
                "low": "6.52",
                "min_close": "6.52",
                "max_close": "8.48",
            }
        )
    context["M"]["current"].update(
        {
            "start_trade_date": "20260506",
            "end_trade_date": "20260528",
            "high": "8.05",
            "low": "6.88",
            "min_close": "6.88",
            "max_close": "8.05",
        }
    )
    context["W"]["current"].update(
        {
            "start_trade_date": "20260525",
            "end_trade_date": "20260528",
            "high": "8.05",
            "low": "7.56",
            "min_close": "7.56",
            "max_close": "8.05",
        }
    )
    context["D"]["current"].update(
        {
            "start_trade_date": "20260528",
            "end_trade_date": "20260528",
            "high": "8.05",
            "low": "8.05",
            "close": "8.05",
            "min_close": "8.05",
            "max_close": "8.05",
        }
    )
    return context


def context_000027_20260529_buy() -> dict[str, object]:
    context = base_period_context("volume_up", daily_rows_000027_20260529_buy())
    for period in ("Y", "Q"):
        context[period]["current"].update(
            {
                "start_trade_date": "20260105",
                "end_trade_date": "20260529",
                "high": "8.48",
                "low": "6.52",
                "min_close": "6.52",
                "max_close": "8.48",
            }
        )
    context["M"]["current"].update(
        {
            "start_trade_date": "20260506",
            "end_trade_date": "20260529",
            "high": "8.08",
            "low": "6.88",
            "min_close": "6.88",
            "max_close": "8.08",
        }
    )
    context["W"]["current"].update(
        {
            "start_trade_date": "20260525",
            "end_trade_date": "20260529",
            "high": "8.08",
            "low": "7.56",
            "min_close": "7.56",
            "max_close": "8.08",
        }
    )
    context["D"]["current"].update(
        {
            "start_trade_date": "20260529",
            "end_trade_date": "20260529",
            "high": "8.08",
            "low": "8.08",
            "close": "8.08",
            "min_close": "8.08",
            "max_close": "8.08",
        }
    )
    return context


def context_000543_20260529_buy() -> dict[str, object]:
    context = base_period_context("volume_up", daily_rows_000543_20260529_buy())
    for period in ("Y", "Q"):
        context[period]["current"].update(
            {
                "start_trade_date": "20260105",
                "end_trade_date": "20260529",
                "high": "11.00",
                "low": "7.51",
                "min_close": "7.51",
                "max_close": "11.00",
            }
        )
    context["M"]["current"].update(
        {
            "start_trade_date": "20260506",
            "end_trade_date": "20260529",
            "high": "9.80",
            "low": "8.09",
            "min_close": "8.09",
            "max_close": "9.80",
        }
    )
    context["W"]["current"].update(
        {
            "start_trade_date": "20260525",
            "end_trade_date": "20260529",
            "high": "9.80",
            "low": "8.70",
            "min_close": "8.98",
            "max_close": "9.80",
        }
    )
    context["D"]["current"].update(
        {
            "start_trade_date": "20260529",
            "end_trade_date": "20260529",
            "high": "9.80",
            "low": "9.34",
            "close": "9.80",
            "min_close": "9.80",
            "max_close": "9.80",
        }
    )
    return context


def context_000600_20260529_buy() -> dict[str, object]:
    context = base_period_context("volume_up", daily_rows_000600_20260529_buy())
    for period in ("Y", "Q"):
        context[period]["current"].update(
            {
                "start_trade_date": "20260105",
                "end_trade_date": "20260529",
                "high": "13.07",
                "low": "8.80",
                "min_close": "8.80",
                "max_close": "12.55",
            }
        )
    context["M"]["current"].update(
        {
            "start_trade_date": "20260506",
            "end_trade_date": "20260529",
            "high": "13.07",
            "low": "9.46",
            "min_close": "9.65",
            "max_close": "12.55",
        }
    )
    context["W"]["current"].update(
        {
            "start_trade_date": "20260525",
            "end_trade_date": "20260529",
            "high": "13.07",
            "low": "9.85",
            "min_close": "10.28",
            "max_close": "12.55",
        }
    )
    context["D"]["current"].update(
        {
            "start_trade_date": "20260529",
            "end_trade_date": "20260529",
            "high": "13.07",
            "low": "12.10",
            "close": "12.55",
            "min_close": "12.55",
            "max_close": "12.55",
        }
    )
    return context


def context_300327_20260529_buy() -> dict[str, object]:
    context = base_period_context("flat", daily_rows_300327_20260529_buy())
    for period in ("Y", "Q", "M", "W", "D"):
        context[period]["transition"] = "flat"
        context[period]["grade"] = "flat"
    context["Y"]["transition"] = "volume_up"
    context["Y"]["grade"] = "volume_up"
    context["W"]["transition"] = "volume_up"
    context["W"]["grade"] = "volume_up"
    context["Y"]["current"].update(
        {
            "start_trade_date": "20260102",
            "end_trade_date": "20260529",
            "high": "38.27",
            "low": "30",
            "min_close": "30",
            "max_close": "38.27",
        }
    )
    context["Q"]["current"].update(
        {
            "start_trade_date": "20260401",
            "end_trade_date": "20260529",
            "high": "33.04",
            "low": "30",
            "min_close": "30",
            "max_close": "33.04",
        }
    )
    context["M"]["current"].update(
        {
            "start_trade_date": "20260501",
            "end_trade_date": "20260529",
            "high": "33.04",
            "low": "30.24",
            "min_close": "30.24",
            "max_close": "33.04",
        }
    )
    context["W"]["current"].update(
        {
            "start_trade_date": "20260525",
            "end_trade_date": "20260529",
            "high": "33.04",
            "low": "30.24",
            "min_close": "30.24",
            "max_close": "33.04",
        }
    )
    context["D"]["current"].update(
        {
            "start_trade_date": "20260529",
            "end_trade_date": "20260529",
            "high": "33.04",
            "low": "33.04",
            "close": "33.04",
            "min_close": "33.04",
            "max_close": "33.04",
        }
    )
    return context


def context_002831_20260615_buy() -> dict[str, object]:
    context = base_period_context("flat", daily_rows_002831_20260615_buy())
    for period in ("Y", "Q", "M", "W", "D"):
        context[period]["transition"] = "flat"
        context[period]["grade"] = "flat"
    context["Y"]["transition"] = "volume_up"
    context["Y"]["grade"] = "volume_up"
    context["Q"]["transition"] = "volume_up"
    context["Q"]["grade"] = "volume_up"
    context["M"]["transition"] = "low_volume_up"
    context["M"]["grade"] = "low_volume_up"
    context["W"]["transition"] = "volume_up"
    context["W"]["grade"] = "low_volume_up"
    context["D"]["transition"] = "low_volume_up"
    context["D"]["grade"] = "low_volume_up"
    return context


def context_unknown_first_week_buy() -> dict[str, object]:
    context = base_period_context("flat", daily_rows_unknown_first_week_buy())
    for period in ("Y", "Q", "M", "W", "D"):
        context[period]["transition"] = "flat"
        context[period]["grade"] = "flat"
    context["W"]["transition"] = "volume_up"
    context["W"]["grade"] = "volume_up"
    return context


def context_down_mirror() -> dict[str, object]:
    context = base_period_context("low_volume_down", daily_rows_down_mirror())
    for period in ("Y", "Q"):
        context[period]["current"].update(
            {
                "start_trade_date": "20260105",
                "end_trade_date": "20260528",
                "high": "10",
                "low": "8.8",
                "min_close": "8.8",
                "max_close": "10",
            }
        )
    context["M"]["current"].update(
        {
            "start_trade_date": "20260506",
            "end_trade_date": "20260528",
            "high": "10",
            "low": "8.8",
            "min_close": "8.8",
            "max_close": "10",
        }
    )
    context["W"]["current"].update(
        {
            "start_trade_date": "20260525",
            "end_trade_date": "20260528",
            "high": "9.4",
            "low": "9.1",
            "min_close": "9.1",
            "max_close": "9.4",
        }
    )
    context["D"]["current"].update(
        {
            "start_trade_date": "20260528",
            "end_trade_date": "20260528",
            "high": "9.1",
            "low": "9.1",
            "close": "9.1",
            "min_close": "9.1",
            "max_close": "9.1",
        }
    )
    return context


def base_period_context(transition: str, daily_rows: list[dict[str, str]]) -> dict[str, object]:
    context: dict[str, object] = {
        "_daily_rows": daily_rows,
    }
    for period in ("Y", "Q", "M", "W", "D"):
        context[period] = {
            "current": {
                "open": daily_rows[-1]["open"],
                "high": daily_rows[-1]["high"],
                "low": daily_rows[-1]["low"],
                "close": daily_rows[-1]["close"],
                "amount": "200",
                "avg_amount": "200",
                "amount_total": "1000",
                "day_count": len(daily_rows),
                "start_trade_date": daily_rows[0]["trade_date"],
                "end_trade_date": daily_rows[-1]["trade_date"],
                "min_close": min(row["close"] for row in daily_rows),
                "max_close": max(row["close"] for row in daily_rows),
            },
            "previous": {
                "open": "7",
                "close": "7",
                "amount": "100",
                "avg_amount": "100",
                "amount_total": "500",
                "start_trade_date": "20260401",
                "end_trade_date": "20260430",
            },
            "grade": transition,
            "transition": transition,
        }
    return context


def daily_rows_000027_buy() -> list[dict[str, str]]:
    return [
        row("20260430", "6.40", "6.45", "6.35", "6.40", "100000"),
        row("20260506", "6.88", "7.04", "6.88", "7.04", "360474.661"),
        row("20260507", "7.04", "7.09", "7.00", "7.09", "345599.325"),
        row("20260508", "7.09", "7.10", "7.03", "7.08", "307030.82"),
        row("20260511", "7.08", "7.20", "7.05", "7.19", "307886.048"),
        row("20260512", "7.19", "7.34", "7.16", "7.32", "466929.197"),
        row("20260513", "7.32", "7.56", "7.30", "7.54", "645121.137"),
        row("20260514", "7.54", "7.55", "7.30", "7.33", "652801.034"),
        row("20260515", "7.33", "7.35", "7.22", "7.26", "439868.241"),
        row("20260518", "7.26", "7.43", "7.24", "7.41", "431654.748"),
        row("20260519", "7.42", "8.05", "7.40", "7.76", "779177.527"),
        row("20260520", "7.76", "7.80", "7.35", "7.39", "614923.553"),
        row("20260521", "7.39", "7.41", "7.21", "7.25", "422864.768"),
        row("20260522", "7.25", "7.34", "7.24", "7.31", "289699.999"),
        row("20260525", "7.31", "7.58", "7.30", "7.56", "381192.946"),
        row("20260526", "7.56", "7.64", "7.53", "7.62", "515137.892"),
        row("20260527", "7.62", "7.72", "7.60", "7.69", "549023.054"),
        row("20260528", "7.69", "8.05", "7.68", "8.05", "996328.34"),
    ]


def daily_rows_000027_20260529_buy() -> list[dict[str, str]]:
    return [
        row("20260430", "6.40", "6.45", "6.35", "6.40", "100000"),
        row("20260506", "6.88", "7.04", "6.88", "7.04", "360474.661"),
        row("20260507", "7.04", "7.09", "7.00", "7.09", "345599.325"),
        row("20260508", "7.07", "7.10", "7.03", "7.08", "307030.82"),
        row("20260511", "7.10", "7.20", "7.05", "7.19", "307886.048"),
        row("20260512", "7.20", "7.34", "7.16", "7.32", "466929.197"),
        row("20260513", "7.33", "7.56", "7.30", "7.54", "645121.137"),
        row("20260514", "7.54", "7.55", "7.30", "7.33", "652801.034"),
        row("20260515", "7.32", "7.35", "7.22", "7.26", "439868.241"),
        row("20260518", "7.21", "7.43", "7.21", "7.41", "431654.748"),
        row("20260519", "7.42", "8.08", "7.40", "7.76", "779177.527"),
        row("20260520", "7.73", "7.80", "7.35", "7.39", "614923.553"),
        row("20260521", "7.30", "7.41", "7.21", "7.25", "422864.768"),
        row("20260522", "7.27", "7.34", "7.24", "7.31", "289699.999"),
        row("20260525", "7.31", "7.58", "7.30", "7.56", "381192.946"),
        row("20260526", "7.49", "7.64", "7.49", "7.62", "515137.892"),
        row("20260527", "7.57", "7.72", "7.57", "7.69", "549023.054"),
        row("20260528", "7.75", "8.05", "7.75", "8.05", "996328.34"),
        row("20260529", "7.98", "8.08", "7.98", "8.08", "1313402.42209"),
    ]


def daily_rows_000543_20260529_buy() -> list[dict[str, str]]:
    return [
        row("20260430", "7.60", "7.65", "7.55", "7.60", "100000"),
        row("20260506", "8.09", "8.20", "8.09", "8.20", "299229.579"),
        row("20260507", "8.20", "8.28", "8.20", "8.28", "317322.871"),
        row("20260508", "8.26", "8.28", "8.24", "8.24", "328711.267"),
        row("20260511", "8.25", "8.38", "8.25", "8.38", "385531.397"),
        row("20260512", "8.36", "8.44", "8.36", "8.44", "411266.329"),
        row("20260513", "8.45", "8.58", "8.45", "8.58", "704858.375"),
        row("20260514", "8.64", "8.64", "8.43", "8.43", "584046.851"),
        row("20260515", "8.41", "8.43", "8.41", "8.43", "518913.354"),
        row("20260518", "8.52", "8.64", "8.52", "8.64", "692555.945"),
        row("20260519", "8.65", "9.00", "8.65", "9.00", "972960.835"),
        row("20260520", "8.87", "8.87", "8.41", "8.41", "789364.141"),
        row("20260521", "8.44", "8.46", "8.44", "8.46", "653446.167"),
        row("20260522", "8.51", "8.73", "8.51", "8.73", "615851.741"),
        row("20260525", "8.70", "8.98", "8.70", "8.98", "608648.367"),
        row("20260526", "8.91", "9.04", "8.91", "9.04", "710061.685"),
        row("20260527", "9.00", "9.11", "9.00", "9.11", "652401.968"),
        row("20260528", "9.13", "9.33", "9.13", "9.33", "1140612.395"),
        row("20260529", "9.34", "9.80", "9.34", "9.80", "1461951.14915"),
    ]


def daily_rows_000600_20260529_buy() -> list[dict[str, str]]:
    return [
        row("20260506", "9.65", "9.70", "9.49", "9.65", "519714.263"),
        row("20260507", "9.65", "10.04", "9.62", "10.00", "629299.155"),
        row("20260508", "9.90", "10.14", "9.79", "9.93", "474458.704"),
        row("20260511", "9.92", "10.08", "9.84", "9.97", "418820.837"),
        row("20260512", "9.95", "10.14", "9.83", "9.99", "584507.006"),
        row("20260513", "9.99", "10.36", "9.92", "10.06", "828360.633"),
        row("20260514", "10.28", "10.43", "9.91", "9.92", "707078.161"),
        row("20260515", "9.83", "9.92", "9.46", "9.73", "546396.465"),
        row("20260518", "9.75", "9.97", "9.65", "9.89", "349681.921"),
        row("20260519", "9.89", "10.88", "9.76", "10.88", "1044346.923"),
        row("20260520", "11.00", "11.15", "10.13", "10.16", "1348900.321"),
        row("20260521", "9.99", "10.57", "9.91", "10.13", "926053.271"),
        row("20260522", "10.13", "10.35", "9.95", "10.13", "614482.314"),
        row("20260525", "10.03", "10.30", "9.85", "10.28", "646521.304"),
        row("20260526", "10.13", "10.67", "9.96", "10.48", "801414.184"),
        row("20260527", "10.38", "11.00", "10.31", "11.00", "1062818.893"),
        row("20260528", "10.80", "12.10", "10.71", "12.10", "1545029.808"),
        row("20260529", "12.11", "13.07", "12.10", "12.55", "2122483.376"),
    ]


def daily_rows_300327_20260529_buy() -> list[dict[str, str]]:
    q2_flat_rows = [
        row(f"202604{day:02d}", "30.00", "30.20", "30.00", "30.00", "10")
        for day in range(1, 24)
    ]
    return [
        row("20251231", "20.00", "25.00", "20.00", "25.00", "100"),
        row("20260102", "30.00", "30.00", "30.00", "30.00", "600"),
        row("20260210", "38.27", "38.27", "38.27", "38.27", "700"),
        row("20260331", "30.00", "31.00", "30.00", "31.00", "600"),
        *q2_flat_rows,
        row("20260512", "30.20", "30.40", "30.20", "30.30", "5"),
        row("20260513", "30.30", "30.50", "30.30", "30.40", "5"),
        row("20260514", "30.40", "30.60", "30.40", "30.50", "5"),
        row("20260515", "30.50", "30.70", "30.50", "30.60", "5"),
        row("20260518", "30.24", "30.80", "30.24", "30.60", "40"),
        row("20260519", "30.60", "31.00", "30.60", "31.00", "80"),
        row("20260520", "30.90", "31.00", "30.80", "30.80", "40"),
        row("20260521", "30.80", "30.90", "30.70", "30.70", "30"),
        row("20260522", "30.24", "31.20", "30.24", "31.20", "120"),
        row("20260525", "30.70", "31.00", "30.70", "31.00", "150"),
        row("20260526", "31.00", "31.50", "31.00", "31.50", "150"),
        row("20260527", "30.24", "30.50", "30.24", "30.24", "100"),
        row("20260528", "30.30", "30.40", "30.30", "30.30", "100"),
        row("20260529", "33.04", "33.04", "33.04", "33.04", "100"),
    ]


def daily_rows_002831_20260615_buy() -> list[dict[str, str]]:
    return [
        row("20250701", "16.15", "16.20", "16.10", "16.15", "100000"),
        row("20250930", "19.18", "19.20", "19.10", "19.19", "100000"),
        row("20251009", "19.1862892689670127", "19.20", "19.10", "19.1862892689670127", "173750"),
        adjusted_stock_row(
            "20251021",
            adjusted_open="17.8553674138725503",
            adjusted_high="19.6766288997912883",
            adjusted_low="17.8553674138725503",
            adjusted_close="19.6766288997912883",
            amount="173750",
            raw_open="25.49",
            raw_high="28.09",
            raw_low="25.49",
            raw_close="28.09",
            adj_factor="2.5843",
            current_adj_factor="3.6893",
        ),
        row("20251231", "19.90", "20.00", "19.80", "19.9708326782858537", "173750"),
        row("20260105", "19.9007841595966715", "20.00", "19.80", "19.9007841595966715", "356348"),
        row("20260331", "22.00", "22.30", "21.90", "22.2053804244707668", "356348"),
        row("20260401", "22.8568316482801615", "23.00", "22.80", "22.8568316482801615", "200000"),
        adjusted_stock_row(
            "20260520",
            adjusted_open="31.6549255956414496",
            adjusted_high="31.9421245222670967",
            adjusted_low="30.2609600737267232",
            adjusted_close="31.1785956685550104",
            amount="600000",
            raw_open="45.19",
            raw_high="45.60",
            raw_low="43.20",
            raw_close="44.51",
            adj_factor="2.5843",
            current_adj_factor="3.6893",
        ),
        row("20260529", "31.00", "31.20", "30.80", "31.18", "600000"),
        row("20260601", "27.00", "27.10", "26.80", "26.88", "200000"),
        adjusted_stock_row(
            "20260608",
            adjusted_open="26.26",
            adjusted_high="27.40",
            adjusted_low="26.26",
            adjusted_close="27.40",
            amount="800000",
            raw_open="26.26",
            raw_high="27.40",
            raw_low="26.26",
            raw_close="27.40",
            adj_factor="3.6893",
            current_adj_factor="3.6893",
        ),
        row("20260611", "29.00", "30.00", "29.00", "30.00", "1000000"),
        row("20260612", "29.66", "29.70", "29.60", "29.66", "500000"),
        adjusted_stock_row(
            "20260615",
            adjusted_open="30.27",
            adjusted_high="31.20",
            adjusted_low="29.75",
            adjusted_close="30.50",
            amount="400000",
            raw_open="30.27",
            raw_high="31.20",
            raw_low="29.75",
            raw_close="30.50",
            adj_factor="3.6893",
            current_adj_factor="3.6893",
        ),
    ]


def daily_rows_unknown_first_week_buy() -> list[dict[str, str]]:
    return [
        row("20260505", "10.00", "10.10", "10.00", "10.00", "100"),
        row("20260506", "10.00", "10.10", "10.00", "10.00", "100"),
        row("20260507", "10.00", "10.10", "10.00", "10.00", "100"),
        row("20260508", "10.00", "10.10", "10.00", "10.00", "100"),
        row("20260512", "10.20", "10.60", "10.20", "10.60", "200"),
        row("20260513", "10.60", "10.80", "10.60", "10.80", "220"),
        row("20260514", "10.80", "11.00", "10.80", "11.00", "240"),
        row("20260515", "11.00", "11.10", "11.00", "11.10", "260"),
        row("20260516", "11.10", "11.20", "11.10", "11.20", "280"),
    ]


def daily_rows_down_mirror() -> list[dict[str, str]]:
    return [
        row("20260506", "10.00", "10.05", "9.85", "9.90", "1000"),
        row("20260507", "9.90", "9.95", "9.65", "9.70", "900"),
        row("20260508", "9.70", "9.75", "9.45", "9.50", "800"),
        row("20260511", "9.50", "9.55", "9.25", "9.30", "700"),
        row("20260512", "9.30", "9.35", "9.05", "9.10", "600"),
        row("20260513", "9.10", "9.15", "8.95", "9.00", "500"),
        row("20260514", "9.00", "9.05", "8.90", "8.95", "450"),
        row("20260515", "8.95", "9.00", "8.88", "8.92", "430"),
        row("20260518", "8.92", "8.96", "8.86", "8.91", "420"),
        row("20260519", "8.91", "8.95", "8.80", "8.80", "410"),
        row("20260520", "8.80", "9.25", "8.78", "9.20", "800"),
        row("20260521", "9.20", "9.65", "9.18", "9.60", "900"),
        row("20260522", "9.60", "9.62", "9.45", "9.50", "850"),
        row("20260525", "9.50", "9.54", "9.35", "9.40", "700"),
        row("20260526", "9.40", "9.43", "9.26", "9.30", "600"),
        row("20260527", "9.30", "9.32", "9.16", "9.20", "500"),
        row("20260528", "9.20", "9.23", "9.06", "9.10", "400"),
    ]


def row(
    trade_date: str,
    open_: str,
    high: str,
    low: str,
    close: str,
    amount: str | None = None,
    *,
    adj_factor: str | None = None,
) -> dict[str, str]:
    values = {
        "trade_date": trade_date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }
    if amount is not None:
        values["amount"] = amount
    if adj_factor is not None:
        values["adj_factor"] = adj_factor
    return values


def adjusted_stock_row(
    trade_date: str,
    *,
    adjusted_open: str,
    adjusted_high: str,
    adjusted_low: str,
    adjusted_close: str,
    amount: str,
    raw_open: str,
    raw_high: str,
    raw_low: str,
    raw_close: str,
    adj_factor: str,
    current_adj_factor: str,
) -> dict[str, str]:
    return {
        "trade_date": trade_date,
        "open": adjusted_open,
        "high": adjusted_high,
        "low": adjusted_low,
        "close": adjusted_close,
        "amount": amount,
        "raw_open": raw_open,
        "raw_high": raw_high,
        "raw_low": raw_low,
        "raw_close": raw_close,
        "adj_factor": adj_factor,
        "current_adj_factor": current_adj_factor,
        "adjustment_policy": "ROW_ADJ_FACTOR_TO_CURRENT_ADJ_FACTOR",
    }


if __name__ == "__main__":
    unittest.main()
