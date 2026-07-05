import unittest
from datetime import date
from pathlib import Path

from ashare_v3.trigger.rule_v4_matcher import (
    TRIGGER_RULE_SPEC_VERSION,
    build_v4_dry_run_report,
    evaluate_v4_plan,
)

UNIFIED_FIELD_NAMES = (
    "signal_type",
    "runtime_signal_type",
    "direction",
    "condition_signal_type",
    "condition_key",
    "original_condition_key",
    "trigger_kind",
    "trigger_mark_candidate",
    "requested_periods",
    "triggered_periods",
    "all_trigger_periods",
    "primary_trigger_period",
    "triggered_period_details",
    "trigger_period",
    "trigger_price",
    "trigger_time",
    "event_time",
    "price_source",
    "match_basis",
    "baseline_source",
    "projection_30m_required",
    "projection_30m_flag",
    "projection_30m_type",
    "projection_period",
    "projection_30m_volume_up_flag",
    "projection_30m_shrink_down_flag",
    "trigger_live",
    "current_status",
    "n5_entry_allowed",
    "data_quality_status",
)


def _expected_period_key(for_trade_date, period):
    parsed = date(int(for_trade_date[:4]), int(for_trade_date[4:6]), int(for_trade_date[6:8]))
    if period == "W":
        iso = parsed.isocalendar()
        return f"{iso.year}W{iso.week:02d}"
    if period == "M":
        return f"{parsed.year}{parsed.month:02d}"
    if period == "Q":
        return f"{parsed.year}Q{((parsed.month - 1) // 3) + 1}"
    if period == "Y":
        return str(parsed.year)
    return None


def _context_row(
    condition_key,
    direction="buy",
    periods=None,
    original_condition_key=None,
    *,
    enrich_trigger_baseline=True,
    enrich_period_keys=True,
    for_trade_date="20260603",
):
    period_values = periods or {
        "Y": {
            "previous_transition": "flat",
            "previous_entity_high": 20,
            "previous_entity_low": 18,
            "previous_amount_baseline": 1000,
            "period_baseline_ready": True,
        },
        "Q": {
            "previous_transition": "flat",
            "previous_entity_high": 18,
            "previous_entity_low": 16,
            "previous_amount_baseline": 800,
            "period_baseline_ready": True,
        },
        "M": {
            "previous_transition": "volume_up",
            "previous_entity_high": 16,
            "previous_entity_low": 14,
            "previous_amount_baseline": 700,
            "period_baseline_ready": True,
        },
        "W": {
            "previous_transition": "flat",
            "previous_entity_high": 10,
            "previous_entity_low": 9,
            "previous_amount_baseline": 100,
            "period_baseline_ready": True,
        },
        "D": {
            "previous_transition": "flat",
            "previous_entity_high": 10.5,
            "previous_entity_low": 9.5,
            "previous_amount_baseline": 90,
            "period_baseline_ready": True,
        },
    }
    if enrich_trigger_baseline:
        period_values = {
            period: {
                **dict(entry),
                "trigger_previous_entity_high": dict(entry).get(
                    "trigger_previous_entity_high",
                    dict(entry).get("previous_entity_high"),
                ),
                "trigger_previous_entity_low": dict(entry).get(
                    "trigger_previous_entity_low",
                    dict(entry).get("previous_entity_low"),
                ),
                "trigger_previous_amount_baseline": dict(entry).get(
                    "trigger_previous_amount_baseline",
                    dict(entry).get("previous_amount_baseline"),
                ),
                "trigger_previous_amount_baseline_unit": dict(entry).get(
                    "trigger_previous_amount_baseline_unit",
                    dict(entry).get("amount_unit", "yuan"),
                ),
            }
            for period, entry in period_values.items()
        }
    if enrich_period_keys:
        period_values = {
            period: {
                **dict(entry),
                **(
                    {
                        "period_key_current": dict(entry).get(
                            "period_key_current",
                            _expected_period_key(for_trade_date, period),
                        ),
                        "period_key_previous": dict(entry).get("period_key_previous", "previous_period_test"),
                        "baseline_source_trade_date": dict(entry).get("baseline_source_trade_date", "20260602"),
                    }
                    if period in {"W", "M", "Q", "Y"}
                    else {}
                ),
            }
            for period, entry in period_values.items()
        }
    return {
        "asset_kind": "stock",
        "identity_key": "stock:SZ:000001",
        "trade_date": for_trade_date,
        "for_trade_date": for_trade_date,
        "condition_key": condition_key,
        "original_condition_key": original_condition_key or condition_key,
        "direction": direction,
        "period_trigger_baseline_json": {
            "context_enrichment": {"ready": True},
            "periods": period_values,
        },
    }


def _projection(
    *,
    price=11,
    amount=130,
    today_virt_amount=None,
    weekly_avg_with_today=None,
    monthly_avg_with_today=None,
    quarterly_avg_with_today=None,
    yearly_avg_with_today=None,
    amount_source_kind="N3_standard_period_metric",
    trigger_amount_chain_pass=None,
    projection_30m_flag=False,
    projection_30m_type="none",
    current_30m_virtual_amount=None,
    reference_30m_amount=None,
    quality="passed",
    for_trade_date="20260603",
):
    result = {
        "projection_run_id": "projection_v4_test",
        "asset_kind": "stock",
        "identity_key": "stock:SZ:000001",
        "trade_date": for_trade_date,
        "for_trade_date": for_trade_date,
        "source_condition_run_id": "condition_v4_test",
        "raw_json": {
            "enrichment_v1": {
                "current_price_or_close": price,
                "current_amount_metric": amount,
                "today_virt_amount": amount if today_virt_amount is None else today_virt_amount,
                "current_amount_metric_unit": "yuan",
                "current_amount_metric_source_kind": amount_source_kind,
                "current_metric_quality_status": quality,
                "trigger_amount_chain_pass": trigger_amount_chain_pass
                if trigger_amount_chain_pass is not None
                else {"W": True, "D": True},
                "projection_period": "30m",
                "projection_30m_flag": projection_30m_flag,
                "projection_30m_type": projection_30m_type,
                "current_30m_virtual_amount": current_30m_virtual_amount,
                "reference_30m_amount": reference_30m_amount,
                "projection_lineage_json": {
                    "source": "n3_standard_projection_enrichment"
                },
            }
        },
    }
    enrichment = result["raw_json"]["enrichment_v1"]
    for key, value in {
        "weekly_avg_with_today": weekly_avg_with_today,
        "monthly_avg_with_today": monthly_avg_with_today,
        "quarterly_avg_with_today": quarterly_avg_with_today,
        "yearly_avg_with_today": yearly_avg_with_today,
    }.items():
        if value is not None:
            enrichment[key] = value
    return result


def _projection_v4_row(
    *,
    price=11,
    amount=130,
    amount_source_kind="N3_standard_period_metric",
    trigger_amount_chain_pass=None,
    metric_ready=True,
    metric_quality_status="passed",
    current_metric_quality_status="passed",
    source_freshness_status="fresh_complete_lineage",
    quality_visible=False,
    quality_reason=None,
    for_trade_date="20260603",
):
    return {
        "projection_enrichment_id": 1,
        "projection_run_id": "projection_v4_materialized_test",
        "asset_kind": "stock",
        "identity_key": "stock:SZ:000001",
        "trade_date": for_trade_date,
        "for_trade_date": for_trade_date,
        "source_condition_run_id": "condition_v4_test",
        "current_price_or_close": price,
        "current_amount_metric": amount,
        "today_virt_amount": amount,
        "weekly_avg_with_today": amount,
        "monthly_avg_with_today": amount,
        "quarterly_avg_with_today": amount,
        "yearly_avg_with_today": amount,
        "current_amount_metric_unit": "yuan",
        "current_amount_metric_source_kind": amount_source_kind,
        "current_metric_quality_status": current_metric_quality_status,
        "projection_period": "30m",
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "trigger_amount_chain_pass": trigger_amount_chain_pass
        if trigger_amount_chain_pass is not None
        else {"period_baseline_pass": {"W": True, "D": True}},
        "projection_lineage_json": {"source": "n3_projection_enrichment_v4_metric"},
        "source_freshness_status": source_freshness_status,
        "metric_ready": metric_ready,
        "metric_quality_status": metric_quality_status,
        "quality_visible": quality_visible,
        "quality_reason": quality_reason,
    }


class N4TriggerRuleV4MatcherTest(unittest.TestCase):
    def assert_unified_fields(
        self,
        plan,
        *,
        condition_signal_type,
        requested_periods,
        projection_30m_required,
        projection_30m_volume_up_flag=False,
        projection_30m_shrink_down_flag=False,
    ):
        for field in UNIFIED_FIELD_NAMES:
            self.assertIn(field, plan, field)
        self.assertEqual(plan["runtime_signal_type"], plan["signal_type"])
        self.assertEqual(plan["condition_signal_type"], condition_signal_type)
        self.assertEqual(plan["requested_periods"], requested_periods)
        self.assertEqual(plan["price_source"], "n3_projection_enrichment")
        self.assertEqual(plan["baseline_source"], "trigger_baseline")
        self.assertEqual(plan["projection_30m_required"], projection_30m_required)
        self.assertEqual(plan["projection_30m_volume_up_flag"], projection_30m_volume_up_flag)
        self.assertEqual(plan["projection_30m_shrink_down_flag"], projection_30m_shrink_down_flag)
        self.assertNotIn("action_mark", plan)

    def test_buy_upgrade_reports_only_triggered_periods(self):
        plan = evaluate_v4_plan(
            _context_row("BUY:Y,Q,M,W,D"),
            _projection(
                weekly_avg_with_today=130,
                monthly_avg_with_today=130,
                quarterly_avg_with_today=130,
                yearly_avg_with_today=130,
                trigger_amount_chain_pass={"Y": True, "Q": True, "M": True, "W": True, "D": True},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["trigger_rule_spec_version"], TRIGGER_RULE_SPEC_VERSION)
        self.assertEqual(plan["signal_type"], "B_BUY")
        self.assertEqual(plan["trigger_kind"], "trigger")
        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["W", "D"])
        self.assertEqual(plan["all_trigger_periods"], ["W", "D"])
        self.assertEqual(plan["primary_trigger_period"], "W")
        self.assertEqual(
            [detail["period"] for detail in plan["triggered_period_details"]],
            ["W", "D"],
        )
        for field in (
            "previous_entity_high",
            "previous_entity_low",
            "current_price_or_close",
            "current_amount_metric",
            "previous_amount_baseline",
            "amount_metric",
            "source_field_trace",
        ):
            self.assertIn(field, plan["triggered_period_details"][0])
        self.assertTrue(plan["trigger_live"])
        self.assertTrue(plan["n5_entry_allowed"])
        self.assertNotIn("action_mark", plan)
        self.assert_unified_fields(
            plan,
            condition_signal_type="BUY",
            requested_periods=["Y", "Q", "M", "W", "D"],
            projection_30m_required=False,
        )

    def test_sell_downgrade_reports_matched_period(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("SELL:D", direction="sell", periods=periods),
            _projection(price=7.5, amount=80, trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["signal_type"], "S_SELL")
        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        self.assertEqual(plan["primary_trigger_period"], "D")
        self.assertTrue(plan["n5_entry_allowed"])
        self.assert_unified_fields(
            plan,
            condition_signal_type="SELL",
            requested_periods=["D"],
            projection_30m_required=False,
        )

    def test_sell_complete_evidence_without_downgrade_is_no_op(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("SELL:D", direction="sell", periods=periods),
            _projection(price=9, amount=120, trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["signal_type"], "S_SELL")
        self.assertEqual(plan["outcome_classification"], "no_op")
        self.assertFalse(plan["trigger_live"])
        self.assertFalse(plan["n5_entry_allowed"])
        self.assertIsNone(plan["output_event_type"])

    def test_buy_price_break_without_amount_upgrade_is_low_volume_up_not_triggered(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("BUY:D", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=11,
                amount=99,
                today_virt_amount=99,
                amount_source_kind="N3_standard_period_metric",
                trigger_amount_chain_pass={"D": True},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        detail = plan["period_evaluation_details"][0]
        self.assertEqual(plan["outcome_classification"], "no_op")
        self.assertEqual(detail["current_transition"], "low_volume_up")
        self.assertFalse(detail["transition_amount_pass"])
        self.assertTrue(detail["trigger_amount_chain_pass"])

    def test_buy_m_transition_uses_monthly_avg_with_today_not_today_virt_amount(self):
        periods = {
            "M": {
                "previous_transition": "low_volume_up",
                "trigger_previous_entity_high": 1751.32,
                "trigger_previous_entity_low": 1634.31,
                "previous_avg_amount": 176_714_129_780.36365,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            },
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 2034.43,
                "trigger_previous_entity_low": 2032.28,
                "previous_avg_amount": 201_727_508_480.0,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            },
        }

        plan = evaluate_v4_plan(
            _context_row("BUY:M,D", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=2126.895,
                today_virt_amount=230_573_832_845.2707,
                monthly_avg_with_today=165_293_766_586.26352,
                trigger_amount_chain_pass={"M": True, "D": True},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        details = {detail["period"]: detail for detail in plan["period_evaluation_details"]}
        self.assertEqual(plan["triggered_periods"], ["D"])
        self.assertEqual(plan["trigger_period"], "D")
        self.assertEqual(details["M"]["classification"], "no_op")
        self.assertEqual(details["M"]["current_transition"], "low_volume_up")
        self.assertFalse(details["M"]["transition_amount_pass"])
        self.assertEqual(details["M"]["transition_amount_field"], "monthly_avg_with_today")
        self.assertEqual(details["M"]["transition_amount_value"], 165_293_766_586.26352)
        self.assertEqual(details["M"]["used_for_period"], "M")
        self.assertEqual(details["M"]["compare_to"], "previous_avg_amount[M]")
        self.assertEqual(details["D"]["classification"], "triggered")
        self.assertEqual(details["D"]["transition_amount_field"], "today_virt_amount")

    def test_stale_w_rollover_baseline_blocks_w_but_not_d_no_op(self):
        periods = {
            "W": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
                "period_key_current": "2026W26",
                "period_key_previous": "2026W25",
                "baseline_source_trade_date": "20260626",
            },
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 12,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            },
        }

        plan = evaluate_v4_plan(
            _context_row("BUY:W,D", periods=periods, enrich_trigger_baseline=False, for_trade_date="20260629"),
            _projection(
                price=11,
                today_virt_amount=130,
                weekly_avg_with_today=130,
                trigger_amount_chain_pass={"W": True, "D": True},
                for_trade_date="20260629",
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        details = {detail["period"]: detail for detail in plan["period_evaluation_details"]}
        self.assertEqual(plan["outcome_classification"], "quality_blocked")
        self.assertEqual(plan["output_event_type"], None)
        self.assertEqual(plan["triggered_periods"], [])
        self.assertEqual(details["W"]["classification"], "quality_blocked")
        self.assertEqual(details["W"]["reason"], "stale_period_baseline_for_trade_date_rollover")
        self.assertEqual(details["W"]["baseline_period_key_current"], "2026W26")
        self.assertEqual(details["W"]["expected_period_key_current"], "2026W27")
        self.assertEqual(details["W"]["baseline_period_key_previous"], "2026W25")
        self.assertEqual(details["W"]["baseline_source_trade_date"], "20260626")
        self.assertTrue(details["W"]["stale_period_baseline"])
        self.assertEqual(details["D"]["classification"], "no_op")
        self.assertFalse(plan["n5_entry_allowed"])

    def test_stale_w_rollover_baseline_does_not_block_fresh_d_trigger(self):
        periods = {
            "W": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
                "period_key_current": "2026W26",
            },
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            },
        }

        plan = evaluate_v4_plan(
            _context_row("BUY:W,D", periods=periods, enrich_trigger_baseline=False, for_trade_date="20260629"),
            _projection(
                price=11,
                today_virt_amount=130,
                weekly_avg_with_today=130,
                trigger_amount_chain_pass={"W": True, "D": True},
                for_trade_date="20260629",
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        details = {detail["period"]: detail for detail in plan["period_evaluation_details"]}
        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        self.assertEqual(plan["primary_trigger_period"], "D")
        self.assertEqual(details["W"]["classification"], "quality_blocked")
        self.assertEqual(details["D"]["classification"], "triggered")
        self.assertTrue(plan["n5_entry_allowed"])

    def test_missing_w_period_key_current_fails_closed_without_pending_market_data(self):
        periods = {
            "W": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
        }

        plan = evaluate_v4_plan(
            _context_row(
                "BUY:W",
                periods=periods,
                enrich_trigger_baseline=False,
                enrich_period_keys=False,
                for_trade_date="20260629",
            ),
            _projection(
                price=11,
                weekly_avg_with_today=130,
                trigger_amount_chain_pass={"W": True},
                for_trade_date="20260629",
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        detail = plan["period_evaluation_details"][0]
        self.assertEqual(plan["outcome_classification"], "quality_blocked")
        self.assertIsNone(plan["output_event_type"])
        self.assertEqual(detail["classification"], "quality_blocked")
        self.assertEqual(detail["reason"], "stale_period_baseline_for_trade_date_rollover")
        self.assertIsNone(detail["baseline_period_key_current"])
        self.assertEqual(detail["expected_period_key_current"], "2026W27")
        self.assertFalse(plan["n5_entry_allowed"])

    def test_for_trade_date_mismatch_with_projection_fails_closed_for_upper_period(self):
        plan = evaluate_v4_plan(
            _context_row("BUY:W", for_trade_date="20260628"),
            _projection(weekly_avg_with_today=130, trigger_amount_chain_pass={"W": True}, for_trade_date="20260629"),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        detail = plan["period_evaluation_details"][0]
        self.assertEqual(plan["outcome_classification"], "quality_blocked")
        self.assertEqual(detail["reason"], "for_trade_date_mismatch")
        self.assertEqual(detail["for_trade_date"], "20260628")
        self.assertEqual(detail["projection_for_trade_date"], "20260629")

    def test_buy_w_q_y_transition_uses_same_period_avg_fields(self):
        periods = {
            period: {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
            for period in ("Y", "Q", "W")
        }

        plan = evaluate_v4_plan(
            _context_row("BUY:Y,Q,W", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=11,
                today_virt_amount=999,
                weekly_avg_with_today=101,
                quarterly_avg_with_today=102,
                yearly_avg_with_today=103,
                trigger_amount_chain_pass={"Y": "not_applicable", "Q": True, "W": True},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        details = {detail["period"]: detail for detail in plan["period_evaluation_details"]}
        self.assertEqual(details["W"]["transition_amount_field"], "weekly_avg_with_today")
        self.assertEqual(details["W"]["transition_amount_value"], 101.0)
        self.assertEqual(details["Q"]["transition_amount_field"], "quarterly_avg_with_today")
        self.assertEqual(details["Q"]["transition_amount_value"], 102.0)
        self.assertEqual(details["Y"]["transition_amount_field"], "yearly_avg_with_today")
        self.assertEqual(details["Y"]["transition_amount_value"], 103.0)
        self.assertEqual(plan["triggered_periods"], ["Y", "Q", "W"])

    def test_missing_period_amount_field_fails_closed_without_today_fallback(self):
        periods = {
            "M": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
        }

        plan = evaluate_v4_plan(
            _context_row("BUY:M", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=11,
                today_virt_amount=999,
                trigger_amount_chain_pass={"M": True},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        detail = plan["period_evaluation_details"][0]
        self.assertEqual(plan["outcome_classification"], "pending_market_data")
        self.assertEqual(detail["classification"], "pending")
        self.assertIn("missing_monthly_avg_with_today", detail["reason"])
        self.assertEqual(detail["transition_amount_field"], "monthly_avg_with_today")
        self.assertIsNone(detail["transition_amount_value"])

    def test_sell_price_break_without_amount_shrink_is_volume_down_not_triggered(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("SELL:D", direction="sell", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=7.5,
                amount=120,
                today_virt_amount=120,
                amount_source_kind="N3_standard_period_metric",
                trigger_amount_chain_pass={"D": True},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        detail = plan["period_evaluation_details"][0]
        self.assertEqual(plan["outcome_classification"], "no_op")
        self.assertEqual(detail["current_transition"], "volume_down")
        self.assertFalse(detail["transition_amount_pass"])
        self.assertTrue(detail["trigger_amount_chain_pass"])

    def test_formal_trigger_uses_trigger_previous_entity_and_amount_baseline(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "classification_previous_entity_high": 110.1,
                "classification_previous_entity_low": 108.55,
                "previous_entity_high": 110.1,
                "previous_entity_low": 108.55,
                "previous_amount_baseline": 1903711,
                "trigger_previous_entity_high": 117,
                "trigger_previous_entity_low": 108.55,
                "trigger_previous_amount_baseline": 2948974.34197,
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("BUY:D", periods=periods),
            _projection(price=113.15, amount=3000000, trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["signal_type"], "B_BUY")
        self.assertEqual(plan["outcome_classification"], "no_op")
        self.assertEqual(plan["triggered_periods"], [])
        detail = plan["period_evaluation_details"][0]
        self.assertEqual(detail["previous_entity_high"], 117)
        self.assertEqual(detail["previous_amount_baseline"], 1903711.0)
        self.assertFalse(plan["n5_entry_allowed"])

    def test_missing_trigger_previous_baseline_does_not_fallback_to_legacy_previous_fields(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "previous_entity_high": 10,
                "previous_entity_low": 9,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("BUY:D", periods=periods, enrich_trigger_baseline=False),
            _projection(price=11, amount=130, trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "pending_market_data")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["triggered_periods"], [])
        self.assertIn("missing_trigger_previous_entity_high", plan["pending_reasons"][0])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_missing_amount_unit_proof_does_not_match(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 9,
                "trigger_previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        projection = _projection(price=11, amount=130, trigger_amount_chain_pass={"D": True})
        projection["raw_json"]["enrichment_v1"].pop("current_amount_metric_unit", None)

        plan = evaluate_v4_plan(
            _context_row("BUY:D", periods=periods, enrich_trigger_baseline=False),
            projection,
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "pending_market_data")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertIn("trigger_amount_unit_not_proven", plan["pending_reasons"][0])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_raw_snapshot_amount_source_does_not_match_formal_period(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 55.87,
                "trigger_previous_entity_low": 55.64,
                "trigger_previous_amount_baseline": 330870.448,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("BUY:D", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=56.6,
                amount=58861092,
                amount_source_kind="N3_realtime_daily_snapshot",
                trigger_amount_chain_pass={"D": True},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "pending_market_data")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertEqual(plan["triggered_periods"], [])
        self.assertIn("formal_period_metric_source_not_allowed", plan["pending_reasons"][0])
        detail = plan["period_evaluation_details"][0]
        self.assertEqual(detail["classification"], "pending")
        self.assertEqual(detail["current_amount_metric"], 58861092.0)
        self.assertFalse(plan["n5_entry_allowed"])

    def test_standardized_period_metric_with_unit_proof_can_match(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 9,
                "trigger_previous_amount_baseline": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("BUY:D", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=11,
                amount=130,
                amount_source_kind="N3_standard_period_metric",
                trigger_amount_chain_pass={"D": True},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        self.assertTrue(plan["n5_entry_allowed"])

    def test_formal_amount_chain_replaces_trigger_previous_amount_baseline(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 9,
                "trigger_previous_amount_baseline": 999999999,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("BUY:D", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=11,
                amount=1,
                amount_source_kind="N3_standard_period_metric",
                trigger_amount_chain_pass={"D": True},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "no_op")
        detail = plan["period_evaluation_details"][0]
        self.assertFalse(detail["transition_amount_pass"])
        self.assertTrue(detail["trigger_amount_chain_pass"])
        self.assertEqual(detail["previous_amount_baseline"], 999999999.0)
        self.assertEqual(detail["amount_rule"], "price_break_plus_current_period_avg_with_today_vs_previous_avg_amount")

    def test_formal_amount_chain_failure_blocks_even_when_old_amount_baseline_passes(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 9,
                "trigger_previous_amount_baseline": 1,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("BUY:D", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=11,
                amount=999999999,
                amount_source_kind="N3_standard_period_metric",
                trigger_amount_chain_pass={"D": False},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "no_op")
        self.assertEqual(plan["triggered_periods"], [])
        detail = plan["period_evaluation_details"][0]
        self.assertTrue(detail["transition_amount_pass"])
        self.assertFalse(detail["trigger_amount_chain_pass"])
        self.assertEqual(detail["amount_rule"], "price_break_plus_current_period_avg_with_today_vs_previous_avg_amount")

    def test_missing_amount_chain_is_pending_market_data(self):
        plan = evaluate_v4_plan(
            _context_row("BUY:D"),
            _projection(trigger_amount_chain_pass={}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "pending_market_data")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertFalse(plan["trigger_live"])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_y_period_keeps_not_applicable_and_is_not_booleanized(self):
        periods = {
            "Y": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "trigger_previous_amount_baseline_unit": "yuan",
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("BUY:Y", periods=periods, enrich_trigger_baseline=False),
            _projection(
                price=11,
                amount=130,
                today_virt_amount=130,
                yearly_avg_with_today=130,
                amount_source_kind="N3_standard_period_metric",
                trigger_amount_chain_pass={},
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        detail = plan["triggered_period_details"][0]
        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["triggered_periods"], ["Y"])
        self.assertEqual(detail["trigger_amount_chain_pass"], "not_applicable")
        self.assertNotIsInstance(detail["trigger_amount_chain_pass"], bool)

    def test_materialized_v4_projection_period_baseline_pass_matches(self):
        plan = evaluate_v4_plan(
            _context_row("BUY:W,D"),
            _projection_v4_row(trigger_amount_chain_pass={"period_baseline_pass": {"W": True, "D": True}}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["triggered_periods"], ["W", "D"])
        self.assertTrue(plan["n5_entry_allowed"])

    def test_bj_quality_visible_projection_is_quality_blocked(self):
        plan = evaluate_v4_plan(
            _context_row("BUY:W,D"),
            _projection_v4_row(
                metric_ready=False,
                metric_quality_status="missing",
                current_metric_quality_status="missing",
                source_freshness_status="source_minute_missing_quality_visible",
                quality_visible=True,
                quality_reason="BJ source minute missing quality-visible; no silent fallback",
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "quality_blocked")
        self.assertEqual(plan["blocked_reason"], "BJ source minute missing quality-visible; no silent fallback")
        self.assertFalse(plan["trigger_live"])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_buy_full_d_volume_up_and_amount_chain_pass_matches(self):
        plan = evaluate_v4_plan(
            _context_row("BUY:FULL"),
            _projection(trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["signal_type"], "B_BUY")
        self.assertEqual(plan["trigger_kind"], "trigger")
        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        self.assertEqual(plan["all_trigger_periods"], ["D"])
        self.assertEqual(plan["primary_trigger_period"], "D")
        self.assertEqual(plan["trigger_mark_candidate"], "normal")
        self.assertFalse(plan["projection_30m_flag"])
        self.assertEqual(plan["projection_30m_type"], "none")
        self.assertTrue(plan["trigger_live"])
        self.assertTrue(plan["n5_entry_allowed"])
        self.assert_unified_fields(
            plan,
            condition_signal_type="BUY:FULL",
            requested_periods=["D"],
            projection_30m_required=False,
        )

    def test_sell_full_d_low_volume_down_and_amount_chain_pass_matches(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("SELL:FULL", direction="sell", periods=periods),
            _projection(price=7.5, amount=80, trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["signal_type"], "S_SELL")
        self.assertEqual(plan["trigger_kind"], "trigger")
        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        self.assertEqual(plan["all_trigger_periods"], ["D"])
        self.assertEqual(plan["primary_trigger_period"], "D")
        self.assertEqual(plan["trigger_mark_candidate"], "normal")
        self.assertTrue(plan["n5_entry_allowed"])
        self.assert_unified_fields(
            plan,
            condition_signal_type="SELL:FULL",
            requested_periods=["D"],
            projection_30m_required=False,
        )

    def test_buy_full_current_volume_up_matches_even_when_previous_was_volume_up(self):
        periods = {
            "D": {
                "previous_transition": "volume_up",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("BUY:FULL", periods=periods),
            _projection(price=11, amount=130, trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        detail = plan["triggered_period_details"][0]
        self.assertEqual(detail["previous_transition"], "volume_up")
        self.assertEqual(detail["current_transition"], "volume_up")
        self.assertTrue(detail["transition_amount_pass"])
        self.assertTrue(detail["trigger_amount_chain_pass"])

    def test_sell_full_current_low_volume_down_matches_even_when_previous_was_low_volume_down(self):
        periods = {
            "D": {
                "previous_transition": "low_volume_down",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        plan = evaluate_v4_plan(
            _context_row("SELL:FULL", direction="sell", periods=periods),
            _projection(price=7.5, amount=80, trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["D"])
        detail = plan["triggered_period_details"][0]
        self.assertEqual(detail["previous_transition"], "low_volume_down")
        self.assertEqual(detail["current_transition"], "low_volume_down")
        self.assertTrue(detail["transition_amount_pass"])
        self.assertTrue(detail["trigger_amount_chain_pass"])

    def test_full_current_state_still_requires_amount_chain(self):
        buy_periods = {
            "D": {
                "previous_transition": "volume_up",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        sell_periods = {
            "D": {
                "previous_transition": "low_volume_down",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }

        buy_plan = evaluate_v4_plan(
            _context_row("BUY:FULL", periods=buy_periods),
            _projection(price=11, amount=130, trigger_amount_chain_pass={"D": False}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )
        sell_plan = evaluate_v4_plan(
            _context_row("SELL:FULL", direction="sell", periods=sell_periods),
            _projection(price=7.5, amount=80, trigger_amount_chain_pass={"D": False}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(buy_plan["outcome_classification"], "no_op")
        self.assertEqual(sell_plan["outcome_classification"], "no_op")
        self.assertIsNone(buy_plan["output_event_type"])
        self.assertIsNone(sell_plan["output_event_type"])

    def test_ordinary_buy_sell_still_require_transition_upgrade(self):
        buy_periods = {
            "D": {
                "previous_transition": "volume_up",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        sell_periods = {
            "D": {
                "previous_transition": "low_volume_down",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }

        buy_plan = evaluate_v4_plan(
            _context_row("BUY:D", periods=buy_periods),
            _projection(price=11, amount=130, trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )
        sell_plan = evaluate_v4_plan(
            _context_row("SELL:D", direction="sell", periods=sell_periods),
            _projection(price=7.5, amount=80, trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(buy_plan["outcome_classification"], "no_op")
        self.assertEqual(sell_plan["outcome_classification"], "no_op")
        self.assertIsNone(buy_plan["output_event_type"])
        self.assertIsNone(sell_plan["output_event_type"])

    def test_full_requires_matching_n2_context_condition_keys(self):
        plan = evaluate_v4_plan(
            _context_row("BUY:FULL", original_condition_key="BUY:D"),
            _projection(trigger_amount_chain_pass={"D": True}),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "quality_blocked")
        self.assertEqual(plan["blocked_reason"], "full_n2_context_missing")
        self.assertFalse(plan["trigger_live"])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_hint_uses_buy_sell_signal_and_30m_projection_not_periods(self):
        plan = evaluate_v4_plan(
            _context_row("BUY_HINT"),
            _projection(
                trigger_amount_chain_pass={"projection_30m": True},
                projection_30m_flag=True,
                projection_30m_type="volume_up",
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["signal_type"], "B_BUY")
        self.assertEqual(plan["trigger_kind"], "hint")
        self.assertEqual(plan["condition_key"], "BUY_HINT")
        self.assertEqual(plan["trigger_mark_candidate"], "30m_volume")
        self.assertEqual(plan["projection_period"], "30m")
        self.assertEqual(plan["triggered_periods"], [])
        self.assertEqual(plan["all_trigger_periods"], [])
        self.assertIsNone(plan["primary_trigger_period"])
        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertTrue(plan["n5_entry_allowed"])
        self.assertEqual(plan["triggered_period_details"], [])
        self.assert_unified_fields(
            plan,
            condition_signal_type="BUY_HINT",
            requested_periods=[],
            projection_30m_required=True,
            projection_30m_volume_up_flag=True,
            projection_30m_shrink_down_flag=False,
        )

    def test_sell_hint_uses_sell_signal_and_shrink_projection(self):
        plan = evaluate_v4_plan(
            _context_row("SELL_HINT", direction="sell"),
            _projection(
                trigger_amount_chain_pass={"projection_30m": True},
                projection_30m_flag=True,
                projection_30m_type="shrink_down",
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["signal_type"], "S_SELL")
        self.assertEqual(plan["trigger_kind"], "hint")
        self.assertEqual(plan["trigger_mark_candidate"], "30m_shrink")
        self.assertEqual(plan["triggered_periods"], [])
        self.assertIsNone(plan["primary_trigger_period"])
        self.assertEqual(plan["outcome_classification"], "matched")
        self.assertTrue(plan["n5_entry_allowed"])
        self.assertEqual(plan["triggered_period_details"], [])
        self.assert_unified_fields(
            plan,
            condition_signal_type="SELL_HINT",
            requested_periods=[],
            projection_30m_required=True,
            projection_30m_volume_up_flag=False,
            projection_30m_shrink_down_flag=True,
        )

    def test_hint_unknown_projection_evidence_is_pending_market_data(self):
        plan = evaluate_v4_plan(
            _context_row("BUY_HINT"),
            _projection(
                projection_30m_flag=False,
                projection_30m_type="unknown",
                current_30m_virtual_amount=None,
                reference_30m_amount=100,
            ),
            v4_run_id="trigger_rule_v4_dry_run_test",
        )

        self.assertEqual(plan["outcome_classification"], "pending_market_data")
        self.assertEqual(plan["output_event_type"], "TriggerPendingMarketData")
        self.assertIn("projection_30m_unknown", plan["pending_reasons"])
        self.assertFalse(plan["n5_entry_allowed"])

    def test_six_condition_signal_types_emit_unified_payload_fields(self):
        sell_periods = {
            "D": {
                "previous_transition": "flat",
                "previous_entity_high": 10,
                "previous_entity_low": 8,
                "previous_amount_baseline": 100,
                "period_baseline_ready": True,
            }
        }
        cases = [
            (
                "BUY:D",
                _context_row("BUY:D"),
                _projection(trigger_amount_chain_pass={"D": True}),
                "BUY",
                ["D"],
            ),
            (
                "SELL:D",
                _context_row("SELL:D", direction="sell", periods=sell_periods),
                _projection(price=7.5, amount=80, trigger_amount_chain_pass={"D": True}),
                "SELL",
                ["D"],
            ),
            (
                "BUY:FULL",
                _context_row("BUY:FULL"),
                _projection(trigger_amount_chain_pass={"D": True}),
                "BUY:FULL",
                ["D"],
            ),
            (
                "SELL:FULL",
                _context_row("SELL:FULL", direction="sell", periods=sell_periods),
                _projection(price=7.5, amount=80, trigger_amount_chain_pass={"D": True}),
                "SELL:FULL",
                ["D"],
            ),
            (
                "BUY_HINT",
                _context_row("BUY_HINT"),
                _projection(projection_30m_flag=True, projection_30m_type="volume_up"),
                "BUY_HINT",
                [],
            ),
            (
                "SELL_HINT",
                _context_row("SELL_HINT", direction="sell"),
                _projection(projection_30m_flag=True, projection_30m_type="shrink_down"),
                "SELL_HINT",
                [],
            ),
        ]

        for label, context, projection, condition_signal_type, requested_periods in cases:
            with self.subTest(label=label):
                plan = evaluate_v4_plan(
                    context,
                    projection,
                    v4_run_id="trigger_rule_v4_dry_run_test",
                )

                self.assertEqual(plan["outcome_classification"], "matched")
                self.assert_unified_fields(
                    plan,
                    condition_signal_type=condition_signal_type,
                    requested_periods=requested_periods,
                    projection_30m_required=condition_signal_type.endswith("_HINT"),
                    projection_30m_volume_up_flag=condition_signal_type == "BUY_HINT",
                    projection_30m_shrink_down_flag=condition_signal_type == "SELL_HINT",
                )

    def test_report_proves_n5_entry_guard(self):
        plans = [
            evaluate_v4_plan(_context_row("BUY:D"), _projection(), v4_run_id="v4"),
            evaluate_v4_plan(_context_row("BUY:D"), None, v4_run_id="v4"),
            evaluate_v4_plan(_context_row("BUY:FULL", original_condition_key="BUY:D"), _projection(), v4_run_id="v4"),
        ]
        report = build_v4_dry_run_report(plans, v3_summary={"TriggerMatched": 3})

        self.assertEqual(report["n5_entry_guard"]["violations"], 0)
        self.assertEqual(report["event_counts"]["TriggerMatched"], 1)
        self.assertEqual(report["outcome_counts"]["pending_market_data"], 1)
        self.assertEqual(report["outcome_counts"]["quality_blocked"], 1)

    def test_matcher_source_does_not_reference_forbidden_upstream_raw_sources(self):
        source = Path("src/ashare_v3/trigger/rule_v4_matcher.py").read_text()
        forbidden_terms = [
            "stock_daily_bar_fact",
            "index_daily_bar_fact",
            "board_daily_bar_fact",
            "minute_bar_1m",
            "previous_day_minute",
            "psycopg.connect",
            "mootdx",
            "tushare",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
