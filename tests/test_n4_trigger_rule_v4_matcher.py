import copy
import hashlib
import json
import unittest
from datetime import date, timedelta
from pathlib import Path

from ashare_v3.trigger.provisional_ordinary_matcher import build_provisional_ordinary_plan
from ashare_v3.trigger.provisional_trigger_lifecycle import build_lifecycle_output_plans
from ashare_v3.trigger.rule_v4_matcher import (
    ORDINARY_PERIOD_ESCALATION_POLICY_VERSION,
    TRIGGER_RULE_SPEC_VERSION,
    _resolve_period_escalation_context_identity,
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


def _stable_contract_hash(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _period_escalation_window_start(for_trade_date, period):
    parsed = date(int(for_trade_date[:4]), int(for_trade_date[4:6]), int(for_trade_date[6:8]))
    if period == "W":
        parsed = parsed - timedelta(days=parsed.weekday())
    elif period == "M":
        parsed = parsed.replace(day=1)
    elif period == "Q":
        parsed = parsed.replace(month=((parsed.month - 1) // 3) * 3 + 1, day=1)
    elif period == "Y":
        parsed = parsed.replace(month=1, day=1)
    return parsed.strftime("%Y%m%d")


def _period_escalation_context(*, asset_kind, identity_key, for_trade_date):
    requirements = {
        "W": ("D", "week"),
        "M": ("W", "month"),
        "Q": ("M", "quarter"),
        "Y": ("Q", "year"),
    }
    directions = {}
    for direction, transition in (("buy", "volume_up"), ("sell", "low_volume_down")):
        entries = {}
        for period, (prerequisite_period, window_kind) in requirements.items():
            payload = {
                "target_period": period,
                "prerequisite_period": prerequisite_period,
                "window_kind": window_kind,
                "window_key": _expected_period_key(for_trade_date, period),
                "window_start": _period_escalation_window_start(for_trade_date, period),
                "observation_end": for_trade_date,
                "reset_for_trade_date": False,
                "required_transition": transition,
                "status": "ready",
                "coverage_status": "passed",
                "seen": True,
                "expected_source_trade_date_count": 1,
                "observed_source_trade_date_count": 1,
                "missing_source_trade_dates": [],
                "observation_count": 1,
                "first_source_trade_date": for_trade_date,
                "last_source_trade_date": for_trade_date,
                "latest_source_condition_run_id": "condition_period_escalation_test",
                "latest_source_basis_ref": f"basis:{asset_kind}:{identity_key}:{direction}:{period}",
            }
            entries[period] = {**payload, "entry_hash": _stable_contract_hash(payload)}
        directions[direction] = entries
    payload = {
        "contract_version": "N2-period-escalation-context-v1",
        "source_layer": "N2_condition",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "for_trade_date": for_trade_date,
        "source_trade_date": for_trade_date,
        "directions": directions,
    }
    return {**payload, "context_hash": _stable_contract_hash(payload)}


def _rehash_period_escalation_context(context):
    for entries in context.get("directions", {}).values():
        for entry in entries.values():
            entry.pop("entry_hash", None)
            entry["entry_hash"] = _stable_contract_hash(entry)
    context.pop("context_hash", None)
    context["context_hash"] = _stable_contract_hash(context)
    return context


def _context_row(
    condition_key,
    direction="buy",
    periods=None,
    original_condition_key=None,
    *,
    enrich_trigger_baseline=True,
    enrich_period_keys=True,
    for_trade_date="20260603",
    asset_kind="stock",
    identity_key="stock:SZ:000001",
    include_period_escalation_context=True,
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
                "amount_unit": dict(entry).get("amount_unit", "yuan"),
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
    baseline = {
        "context_enrichment": {"ready": True},
        "periods": period_values,
    }
    if include_period_escalation_context:
        baseline["period_escalation_context"] = _period_escalation_context(
            asset_kind=asset_kind,
            identity_key=identity_key,
            for_trade_date=for_trade_date,
        )
    return {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "trade_date": for_trade_date,
        "for_trade_date": for_trade_date,
        "source_trade_date": for_trade_date,
        "condition_key": condition_key,
        "original_condition_key": original_condition_key or condition_key,
        "direction": direction,
        "period_trigger_baseline_json": baseline,
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
        self.assertEqual(plan["triggered_periods"], ["W"])
        self.assertEqual(plan["all_trigger_periods"], ["W", "D"])
        self.assertEqual(plan["primary_trigger_period"], "W")
        self.assertEqual(plan["prerequisite_periods"], ["D"])
        self.assertEqual(
            [detail["period"] for detail in plan["triggered_period_details"]],
            ["W"],
        )
        self.assertEqual(
            plan["triggered_period_details"][0]["period_escalation_trace"]["evidence_source"],
            "current_same_day_formal_pass",
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
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount_unit": "yuan",
                "period_baseline_ready": True,
            },
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 2034.43,
                "trigger_previous_entity_low": 2032.28,
                "previous_avg_amount": 201_727_508_480.0,
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount_unit": "yuan",
                "period_baseline_ready": True,
                "period_key_current": "2026W26",
            },
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount_unit": "yuan",
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
        self.assertEqual(plan["triggered_periods"], ["Y", "W"])
        self.assertEqual(plan["all_trigger_periods"], ["Y", "Q", "W"])

    def test_missing_period_amount_field_fails_closed_without_today_fallback(self):
        periods = {
            "M": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 8,
                "previous_avg_amount": 100,
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount": 330870.448,
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount": 100,
                "previous_avg_amount_unit": "yuan",
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

    def test_trigger_previous_amount_baseline_is_not_an_allowed_transition_fallback(self):
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

        self.assertEqual(plan["outcome_classification"], "pending_market_data")
        detail = plan["period_evaluation_details"][0]
        self.assertIsNone(detail["transition_amount_pass"])
        self.assertTrue(detail["trigger_amount_chain_pass"])
        self.assertIsNone(detail["previous_amount_baseline"])
        self.assertIsNone(detail["previous_amount_source_field"])
        self.assertIn("missing_previous_avg_amount", detail["reason"])
        self.assertEqual(detail["amount_rule"], "price_break_plus_current_period_avg_with_today_vs_previous_avg_amount")

    def test_formal_amount_chain_failure_blocks_even_when_old_amount_baseline_passes(self):
        periods = {
            "D": {
                "previous_transition": "flat",
                "trigger_previous_entity_high": 10,
                "trigger_previous_entity_low": 9,
                "previous_avg_amount": 1,
                "previous_avg_amount_unit": "yuan",
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
                "previous_avg_amount_unit": "yuan",
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
        self.assertEqual(plan["triggered_periods"], ["W"])
        self.assertEqual(plan["all_trigger_periods"], ["W", "D"])
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

    def test_period_escalation_ready_gates_buy_sell_all_periods_and_assets(self):
        for asset_kind, identity_key in (
            ("stock", "stock:SZ:000001"),
            ("index", "index:SH:000300"),
            ("board", "board:TDX:881001"),
        ):
            for direction in ("buy", "sell"):
                for period in ("W", "M", "Q", "Y"):
                    with self.subTest(asset_kind=asset_kind, direction=direction, period=period):
                        periods = {
                            period: {
                                "previous_transition": "flat",
                                "previous_entity_high": 10,
                                "previous_entity_low": 9,
                                "previous_avg_amount": 100,
                                "period_baseline_ready": True,
                            }
                        }
                        condition_key = f"{'BUY' if direction == 'buy' else 'SELL'}:{period}"
                        context = _context_row(
                            condition_key,
                            direction=direction,
                            periods=periods,
                            asset_kind=asset_kind,
                            identity_key=identity_key,
                        )
                        amount = 130 if direction == "buy" else 70
                        projection = _projection(
                            price=11 if direction == "buy" else 8,
                            amount=amount,
                            today_virt_amount=amount,
                            weekly_avg_with_today=amount,
                            monthly_avg_with_today=amount,
                            quarterly_avg_with_today=amount,
                            yearly_avg_with_today=amount,
                            trigger_amount_chain_pass={period: "not_applicable" if period == "Y" else True},
                        )

                        plan = evaluate_v4_plan(context, projection, v4_run_id="period_escalation_v1")

                        self.assertEqual(plan["output_event_type"], "TriggerMatched")
                        self.assertEqual(plan["triggered_periods"], [period])
                        self.assertEqual(plan["all_trigger_periods"], [period])
                        self.assertEqual(plan["primary_trigger_period"], period)
                        expected_prerequisite = {"W": "D", "M": "W", "Q": "M", "Y": "Q"}[period]
                        self.assertEqual(plan["prerequisite_periods"], [expected_prerequisite])
                        self.assertEqual(
                            plan["ordinary_period_escalation_policy_version"],
                            ORDINARY_PERIOD_ESCALATION_POLICY_VERSION,
                        )
                        self.assertTrue(plan["period_escalation_trace"]["periods"][period]["gate_pass"])

    def test_same_day_formal_evidence_upgrades_all_assets_directions_and_adjacent_periods(self):
        adjacent_periods = (("D", "W"), ("W", "M"), ("M", "Q"), ("Q", "Y"))
        assets = (
            ("stock", "stock:SZ:000001"),
            ("index", "index:SH:000300"),
            ("board", "board:TDX:881001"),
        )

        for asset_kind, identity_key in assets:
            for direction in ("buy", "sell"):
                for prerequisite_period, target_period in adjacent_periods:
                    with self.subTest(
                        asset_kind=asset_kind,
                        direction=direction,
                        prerequisite_period=prerequisite_period,
                        target_period=target_period,
                    ):
                        periods = {
                            period: {
                                "previous_transition": "flat",
                                "previous_entity_high": 10,
                                "previous_entity_low": 9,
                                "previous_avg_amount": 100,
                                "period_baseline_ready": True,
                            }
                            for period in (target_period, prerequisite_period)
                        }
                        prefix = "BUY" if direction == "buy" else "SELL"
                        context = _context_row(
                            f"{prefix}:{target_period},{prerequisite_period}",
                            direction=direction,
                            periods=periods,
                            asset_kind=asset_kind,
                            identity_key=identity_key,
                            include_period_escalation_context=False,
                        )
                        amount = 130 if direction == "buy" else 70
                        projection = _projection(
                            price=11 if direction == "buy" else 8,
                            amount=amount,
                            today_virt_amount=amount,
                            weekly_avg_with_today=amount,
                            monthly_avg_with_today=amount,
                            quarterly_avg_with_today=amount,
                            yearly_avg_with_today=amount,
                            trigger_amount_chain_pass={
                                target_period: "not_applicable" if target_period == "Y" else True,
                                prerequisite_period: (
                                    "not_applicable" if prerequisite_period == "Y" else True
                                ),
                            },
                        )

                        plan = evaluate_v4_plan(
                            context,
                            projection,
                            v4_run_id="period_escalation_same_day_v2",
                        )

                        self.assertEqual(
                            plan["ordinary_period_escalation_policy_version"],
                            "N4-ordinary-period-escalation-v2",
                        )
                        self.assertEqual(plan["output_event_type"], "TriggerMatched")
                        self.assertEqual(plan["pending_reasons"], [])
                        self.assertEqual(plan["quality_reasons"], [])
                        self.assertEqual(plan["triggered_periods"], [target_period])
                        self.assertEqual(
                            plan["all_trigger_periods"],
                            [target_period, prerequisite_period],
                        )
                        self.assertEqual(plan["primary_trigger_period"], target_period)
                        self.assertEqual(plan["prerequisite_periods"], [prerequisite_period])
                        self.assertEqual(
                            [detail["period"] for detail in plan["triggered_period_details"]],
                            [target_period],
                        )
                        target_detail = plan["triggered_period_details"][0]
                        trace = target_detail["period_escalation_trace"]
                        self.assertEqual(trace["evidence_source"], "current_same_day_formal_pass")
                        self.assertTrue(trace["gate_pass"])
                        self.assertTrue(plan["period_escalation_trace"]["same_day_formal_evidence"])
                        self.assertIn(target_period, trace["current_formal_pass_periods"])
                        self.assertIn(prerequisite_period, trace["current_formal_pass_periods"])
                        self.assertIsNone(trace["context_contract_version"])
                        self.assertIsNone(trace["context_hash"])

    def test_period_escalation_top_context_uses_unique_n2_identity_independent_of_order(self):
        same_day = {
            "evidence_source": "current_same_day_formal_pass",
            "context_contract_version": None,
            "context_hash": None,
        }
        n2 = {
            "evidence_source": "n2_period_escalation_context",
            "context_contract_version": "N2-period-escalation-context-v1",
            "context_hash": "context_hash_a",
        }
        expected = ("N2-period-escalation-context-v1", "context_hash_a")

        for traces in (
            {"Y": copy.deepcopy(same_day), "W": copy.deepcopy(n2)},
            {"W": copy.deepcopy(n2), "Y": copy.deepcopy(same_day)},
        ):
            with self.subTest(period_order=list(traces)):
                original = copy.deepcopy(traces)
                self.assertEqual(_resolve_period_escalation_context_identity(traces), expected)
                self.assertEqual(traces, original)

        self.assertEqual(
            _resolve_period_escalation_context_identity(
                {"Y": copy.deepcopy(same_day), "Q": copy.deepcopy(same_day)}
            ),
            (None, None),
        )
        self.assertEqual(
            _resolve_period_escalation_context_identity(
                {
                    "Y": copy.deepcopy(same_day),
                    "W": {
                        "evidence_source": "n2_period_escalation_context",
                        "context_contract_version": "N2-period-escalation-context-v1",
                        "context_hash": None,
                    },
                }
            ),
            (None, None),
        )

    def test_period_escalation_top_context_multiple_n2_identities_fail_closed(self):
        for second_version, second_hash in (
            ("N2-period-escalation-context-v1", "context_hash_b"),
            ("N2-period-escalation-context-v2", "context_hash_a"),
            ("N2-period-escalation-context-v2", "context_hash_b"),
        ):
            with self.subTest(second_version=second_version, second_hash=second_hash):
                traces = {
                    "Q": {
                        "evidence_source": "n2_period_escalation_context",
                        "context_contract_version": "N2-period-escalation-context-v1",
                        "context_hash": "context_hash_a",
                    },
                    "W": {
                        "evidence_source": "n2_period_escalation_context",
                        "context_contract_version": second_version,
                        "context_hash": second_hash,
                    },
                }

                with self.assertRaisesRegex(ValueError, "context identity conflicting"):
                    _resolve_period_escalation_context_identity(traces)

    def test_same_day_condition_key_without_prerequisite_formal_pass_fails_closed(self):
        periods = {
            period: {
                "previous_transition": "flat",
                "previous_entity_high": 10,
                "previous_entity_low": 9,
                "previous_avg_amount": 100,
                "period_baseline_ready": True,
            }
            for period in ("M", "W")
        }
        context = _context_row(
            "BUY:M,W",
            periods=periods,
            include_period_escalation_context=False,
        )
        projection = _projection(
            price=11,
            amount=130,
            weekly_avg_with_today=90,
            monthly_avg_with_today=130,
            trigger_amount_chain_pass={"M": True, "W": True},
        )

        plan = evaluate_v4_plan(context, projection, v4_run_id="period_escalation_same_day_v2")

        details = {detail["period"]: detail for detail in plan["period_evaluation_details"]}
        self.assertEqual(plan["outcome_classification"], "quality_blocked")
        self.assertFalse(details["W"]["existing_formal_pass"])
        self.assertEqual(
            details["M"]["period_escalation_trace"]["evidence_source"],
            "n2_period_escalation_context",
        )
        self.assertIn("context_missing", details["M"]["reason"])
        self.assertNotEqual(
            details["M"]["period_escalation_trace"]["evidence_source"],
            "current_same_day_formal_pass",
        )

    def test_high_period_without_same_day_evidence_keeps_not_ready_fail_closed(self):
        context = _context_row(
            "BUY:M",
            periods={
                "M": {
                    "previous_transition": "flat",
                    "previous_entity_high": 10,
                    "previous_entity_low": 9,
                    "previous_avg_amount": 100,
                    "period_baseline_ready": True,
                }
            },
        )
        entry = context["period_trigger_baseline_json"]["period_escalation_context"]["directions"]["buy"]["M"]
        entry.update(
            {
                "status": "not_ready",
                "coverage_status": "incomplete",
                "seen": False,
                "expected_source_trade_date_count": 2,
                "observed_source_trade_date_count": 1,
                "missing_source_trade_dates": ["20260602"],
            }
        )
        _rehash_period_escalation_context(
            context["period_trigger_baseline_json"]["period_escalation_context"]
        )

        plan = evaluate_v4_plan(
            context,
            _projection(monthly_avg_with_today=130, trigger_amount_chain_pass={"M": True}),
            v4_run_id="period_escalation_same_day_v2",
        )

        self.assertEqual(plan["outcome_classification"], "quality_blocked")
        self.assertIsNone(plan["output_event_type"])
        self.assertIn("prerequisite_not_ready:M", plan["blocked_reason"])

    def test_positive_n2_evidence_with_incomplete_coverage_remains_ready(self):
        context = _context_row(
            "BUY:M",
            periods={
                "M": {
                    "previous_transition": "flat",
                    "previous_entity_high": 10,
                    "previous_entity_low": 9,
                    "previous_avg_amount": 100,
                    "period_baseline_ready": True,
                }
            },
        )
        escalation = context["period_trigger_baseline_json"]["period_escalation_context"]
        escalation["generation_mode"] = "N2-period-escalation-daily-incremental-v1"
        entry = escalation["directions"]["buy"]["M"]
        entry.update(
            {
                "status": "ready",
                "coverage_status": "incomplete",
                "seen": True,
                "expected_source_trade_date_count": 3,
                "observed_source_trade_date_count": 1,
                "missing_source_trade_dates": ["20260601", "20260602"],
            }
        )
        _rehash_period_escalation_context(escalation)

        plan = evaluate_v4_plan(
            context,
            _projection(monthly_avg_with_today=130, trigger_amount_chain_pass={"M": True}),
            v4_run_id="period_escalation_same_day_v2",
        )

        self.assertEqual(plan["output_event_type"], "TriggerMatched")
        self.assertEqual(plan["triggered_periods"], ["M"])
        trace = plan["triggered_period_details"][0]["period_escalation_trace"]
        self.assertEqual(trace["evidence_source"], "n2_period_escalation_context")
        self.assertEqual(trace["coverage_status"], "incomplete")
        self.assertTrue(trace["gate_pass"])

        legacy_context = copy.deepcopy(context)
        legacy_escalation = legacy_context["period_trigger_baseline_json"]["period_escalation_context"]
        legacy_escalation.pop("generation_mode")
        _rehash_period_escalation_context(legacy_escalation)
        legacy_plan = evaluate_v4_plan(
            legacy_context,
            _projection(monthly_avg_with_today=130, trigger_amount_chain_pass={"M": True}),
            v4_run_id="period_escalation_same_day_v2",
        )
        self.assertEqual(legacy_plan["outcome_classification"], "quality_blocked")
        self.assertIn("ready_invariant_failed:M", legacy_plan["blocked_reason"])

    def test_period_escalation_distinguishes_not_seen_not_ready_and_missing(self):
        ready_context = _context_row("BUY:W")
        not_seen_context = copy.deepcopy(ready_context)
        not_seen_entry = not_seen_context["period_trigger_baseline_json"]["period_escalation_context"]["directions"]["buy"]["W"]
        not_seen_entry.update(
            {
                "status": "not_seen",
                "coverage_status": "passed",
                "seen": False,
                "observation_count": 0,
                "first_source_trade_date": None,
                "last_source_trade_date": None,
                "latest_source_condition_run_id": None,
                "latest_source_basis_ref": None,
            }
        )
        _rehash_period_escalation_context(
            not_seen_context["period_trigger_baseline_json"]["period_escalation_context"]
        )
        not_ready_context = copy.deepcopy(ready_context)
        not_ready_entry = not_ready_context["period_trigger_baseline_json"]["period_escalation_context"]["directions"]["buy"]["W"]
        not_ready_entry.update(
            {
                "status": "not_ready",
                "coverage_status": "incomplete",
                "seen": False,
                "expected_source_trade_date_count": 2,
                "observed_source_trade_date_count": 1,
                "missing_source_trade_dates": ["20260602"],
            }
        )
        _rehash_period_escalation_context(
            not_ready_context["period_trigger_baseline_json"]["period_escalation_context"]
        )
        missing_context = _context_row("BUY:W", include_period_escalation_context=False)
        projection = _projection(weekly_avg_with_today=130, trigger_amount_chain_pass={"W": True})

        not_seen = evaluate_v4_plan(not_seen_context, projection, v4_run_id="period_escalation_v1")
        not_ready = evaluate_v4_plan(not_ready_context, projection, v4_run_id="period_escalation_v1")
        missing = evaluate_v4_plan(missing_context, projection, v4_run_id="period_escalation_v1")

        self.assertEqual(not_seen["outcome_classification"], "no_op")
        self.assertEqual(not_seen["period_evaluation_details"][0]["classification"], "no_op")
        self.assertIn("prerequisite_not_seen", not_seen["period_evaluation_details"][0]["reason"])
        self.assertEqual(not_ready["outcome_classification"], "quality_blocked")
        self.assertIn("prerequisite_not_ready", not_ready["blocked_reason"])
        self.assertEqual(missing["outcome_classification"], "quality_blocked")
        self.assertIn("context_missing", missing["blocked_reason"])

    def test_period_escalation_contract_mismatches_fail_closed(self):
        def mutated(mutator, *, rehash=True):
            context = _context_row("BUY:W")
            escalation = context["period_trigger_baseline_json"]["period_escalation_context"]
            mutator(escalation)
            if rehash:
                _rehash_period_escalation_context(escalation)
            return context

        invalid_contexts = {
            "version": mutated(lambda value: value.__setitem__("contract_version", "legacy")),
            "source_layer": mutated(lambda value: value.__setitem__("source_layer", "N3_market_data")),
            "generation_mode": mutated(
                lambda value: value.__setitem__("generation_mode", "unknown_incremental_mode")
            ),
            "direction": mutated(lambda value: value["directions"].pop("buy")),
            "asset": mutated(lambda value: value.__setitem__("asset_kind", "index")),
            "identity": mutated(lambda value: value.__setitem__("identity_key", "stock:SH:600000")),
            "date": mutated(lambda value: value.__setitem__("for_trade_date", "20260604")),
            "source_date": mutated(lambda value: value.__setitem__("source_trade_date", "invalid")),
            "target": mutated(lambda value: value["directions"]["buy"]["W"].__setitem__("target_period", "M")),
            "prerequisite": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__("prerequisite_period", "M")
            ),
            "window_kind": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__("window_kind", "month")
            ),
            "window_type_alias": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__("window_type", "week")
            ),
            "window_key": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__("window_key", "2026W99")
            ),
            "window_start": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__("window_start", "20260101")
            ),
            "transition": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__(
                    "required_transition", "low_volume_down"
                )
            ),
            "status": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__("status", "unknown")
            ),
            "seen": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__("seen", "true")
            ),
            "coverage": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__("coverage_status", "incomplete")
            ),
            "entry_hash": mutated(
                lambda value: value["directions"]["buy"]["W"].__setitem__("entry_hash", "bad"),
                rehash=False,
            ),
            "context_hash": mutated(lambda value: value.__setitem__("context_hash", "bad"), rehash=False),
        }
        projection = _projection(weekly_avg_with_today=130, trigger_amount_chain_pass={"W": True})

        for label, context in invalid_contexts.items():
            with self.subTest(label=label):
                plan = evaluate_v4_plan(context, projection, v4_run_id="period_escalation_v1")
                self.assertIsNone(plan["output_event_type"])
                self.assertEqual(plan["outcome_classification"], "quality_blocked")
                self.assertEqual(plan["period_evaluation_details"][0]["classification"], "quality_blocked")

    def test_period_escalation_d_full_and_hint_rules_remain_unchanged(self):
        d_plan = evaluate_v4_plan(
            _context_row("BUY:D", include_period_escalation_context=False),
            _projection(trigger_amount_chain_pass={"D": True}),
            v4_run_id="period_escalation_v1",
        )
        full_plan = evaluate_v4_plan(
            _context_row("BUY:FULL", include_period_escalation_context=False),
            _projection(trigger_amount_chain_pass={"D": True}),
            v4_run_id="period_escalation_v1",
        )
        hint_plan = evaluate_v4_plan(
            _context_row("BUY_HINT", include_period_escalation_context=False),
            _projection(projection_30m_flag=True, projection_30m_type="volume_up"),
            v4_run_id="period_escalation_v1",
        )

        self.assertEqual(d_plan["output_event_type"], "TriggerMatched")
        self.assertEqual(d_plan["triggered_periods"], ["D"])
        self.assertEqual(full_plan["output_event_type"], "TriggerMatched")
        self.assertEqual(full_plan["triggered_periods"], ["D"])
        self.assertEqual(hint_plan["output_event_type"], "TriggerMatched")
        self.assertNotIn("ordinary_period_escalation_policy_version", full_plan)
        self.assertNotIn("ordinary_period_escalation_policy_version", hint_plan)

    def test_period_escalation_current_period_set_trace_and_lifecycle_are_stable(self):
        w_only = evaluate_v4_plan(
            _context_row("BUY:W"),
            _projection(weekly_avg_with_today=130, trigger_amount_chain_pass={"W": True}),
            v4_run_id="period_escalation_v1",
            previous_state={
                "trigger_live": True,
                "current_status": "matched",
                "primary_trigger_period": "D",
                "all_trigger_periods": ["D"],
            },
        )
        self.assertEqual(w_only["triggered_periods"], ["W"])
        self.assertEqual(w_only["all_trigger_periods"], ["W"])
        self.assertEqual(w_only["prerequisite_periods"], ["D"])

        context = _context_row("BUY:W,D")
        w_projection = _projection(
            today_virt_amount=130,
            weekly_avg_with_today=130,
            trigger_amount_chain_pass={"W": True, "D": True},
        )
        w_rule_plan = evaluate_v4_plan(
            context,
            w_projection,
            v4_run_id="period_escalation_v1",
            previous_state={
                "trigger_live": True,
                "current_status": "matched",
                "primary_trigger_period": "D",
                "all_trigger_periods": ["D"],
            },
        )

        self.assertEqual(w_rule_plan["all_trigger_periods"], ["W", "D"])
        self.assertEqual(w_rule_plan["prerequisite_periods"], ["D"])
        self.assertEqual(w_rule_plan["previous_all_trigger_periods"], ["D"])
        self.assertIn("period_escalation_trace", w_rule_plan["triggered_period_details"][0])

        metric = {
            "projection_run_id": "n3p_period_escalation_test",
            "action_confirmation_metric_id": 1,
            "metric_time": "2026-06-03T10:00:00+08:00",
            "metric_time_label": "2026-06-03 10:00",
            "metric_minute_label": "10:00",
            "is_closed_1m": True,
            "metric_ready": True,
        }
        w_plan = build_provisional_ordinary_plan(
            context=context,
            metric=metric,
            source_metric_run_id="n3p_period_escalation_test",
            trigger_type="BUY",
            rule_plan=w_rule_plan,
        )
        trace_variant = copy.deepcopy(w_rule_plan)
        trace_variant["period_escalation_trace"]["audit_note"] = "dedup_must_ignore_optional_trace"
        trace_variant_plan = build_provisional_ordinary_plan(
            context=context,
            metric=metric,
            source_metric_run_id="n3p_period_escalation_test",
            trigger_type="BUY",
            rule_plan=trace_variant,
        )
        self.assertEqual(trace_variant_plan["plan_id"], w_plan["plan_id"])
        self.assertEqual(
            trace_variant_plan["candidate_trigger_identity_key"],
            w_plan["candidate_trigger_identity_key"],
        )
        self.assertIn(
            "period_escalation_trace",
            w_plan["rule_proof"]["triggered_period_details"][0],
        )
        activated = build_lifecycle_output_plans([w_plan], previous_states=[])
        self.assertEqual([item["output_event_type"] for item in activated], ["TriggerMatched"])
        self.assertEqual(build_lifecycle_output_plans([w_plan], previous_states=activated), [])

        d_projection = _projection(
            today_virt_amount=130,
            weekly_avg_with_today=80,
            trigger_amount_chain_pass={"W": True, "D": True},
        )
        d_rule_plan = evaluate_v4_plan(context, d_projection, v4_run_id="period_escalation_v1")
        d_plan = build_provisional_ordinary_plan(
            context=context,
            metric={**metric, "action_confirmation_metric_id": 2, "metric_time": "2026-06-03T09:59:00+08:00"},
            source_metric_run_id="n3p_period_escalation_test",
            trigger_type="BUY",
            rule_plan=d_rule_plan,
        )
        d_activated = build_lifecycle_output_plans([d_plan], previous_states=[])
        upgraded = build_lifecycle_output_plans([w_plan], previous_states=d_activated)
        self.assertEqual([item["output_event_type"] for item in upgraded], ["TriggerStateChanged"])
        self.assertFalse(upgraded[0]["n5_entry_allowed"])

    def test_period_escalation_not_ready_does_not_clear_live_state(self):
        ready_context = _context_row("BUY:W")
        not_ready_context = copy.deepcopy(ready_context)
        entry = not_ready_context["period_trigger_baseline_json"]["period_escalation_context"]["directions"]["buy"]["W"]
        entry.update(
            {
                "status": "not_ready",
                "coverage_status": "incomplete",
                "seen": False,
                "expected_source_trade_date_count": 2,
                "observed_source_trade_date_count": 1,
                "missing_source_trade_dates": ["20260602"],
            }
        )
        _rehash_period_escalation_context(
            not_ready_context["period_trigger_baseline_json"]["period_escalation_context"]
        )
        projection = _projection(weekly_avg_with_today=130, trigger_amount_chain_pass={"W": True})
        ready_rule = evaluate_v4_plan(ready_context, projection, v4_run_id="period_escalation_v1")
        not_ready_rule = evaluate_v4_plan(not_ready_context, projection, v4_run_id="period_escalation_v1")
        metric = {
            "projection_run_id": "n3p_period_escalation_test",
            "action_confirmation_metric_id": 1,
            "metric_time": "2026-06-03T10:00:00+08:00",
            "metric_ready": True,
        }
        ready_plan = build_provisional_ordinary_plan(
            context=ready_context,
            metric=metric,
            source_metric_run_id="n3p_period_escalation_test",
            trigger_type="BUY",
            rule_plan=ready_rule,
        )
        not_ready_plan = build_provisional_ordinary_plan(
            context=not_ready_context,
            metric=metric,
            source_metric_run_id="n3p_period_escalation_test",
            trigger_type="BUY",
            rule_plan=not_ready_rule,
        )
        live = build_lifecycle_output_plans([ready_plan], previous_states=[])

        outputs = build_lifecycle_output_plans([not_ready_plan], previous_states=live)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["output_event_type"], "TriggerStateChanged")
        self.assertEqual(outputs[0]["current_status"], "inactive")
        self.assertFalse(outputs[0]["writes_trigger_match"])

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
