"""Dry-run matcher for N4 trigger rule spec v4.

The module is intentionally pure: callers pass localized N2 context enrichment
and N3 projection enrichment rows. It does not open database connections or
derive upstream facts from lower-level market sources.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from typing import Any, Mapping


TRIGGER_RULE_SPEC_VERSION = "N4_TRIGGER_RULE_SPEC_v4"
TRIGGER_RULE_POLICY_HASH = hashlib.sha1(
    json.dumps(
        {
            "spec": TRIGGER_RULE_SPEC_VERSION,
            "policy": "ordinary-upgrade-downgrade-hint-projection-full-d-trigger",
        },
        sort_keys=True,
    ).encode("utf-8")
).hexdigest()[:16]

PERIOD_PRIORITY = ("Y", "Q", "M", "W", "D")
ROLLOVER_GUARDED_PERIODS = {"Y", "Q", "M", "W"}
STALE_PERIOD_BASELINE_REASON = "stale_period_baseline_for_trade_date_rollover"
CURRENT_PERIOD_AVG_FIELD_BY_PERIOD = {
    "D": "today_virt_amount",
    "W": "weekly_avg_with_today",
    "M": "monthly_avg_with_today",
    "Q": "quarterly_avg_with_today",
    "Y": "yearly_avg_with_today",
}
RUNTIME_SIGNAL_TYPES = {"B_BUY", "S_SELL"}
CONDITION_SIGNAL_TYPES = {
    "BUY",
    "SELL",
    "BUY:FULL",
    "SELL:FULL",
    "BUY_HINT",
    "SELL_HINT",
}
FORMAL_AMOUNT_METRIC_SOURCE_KIND = "N3_standard_period_metric"
DEPRECATED_RUNTIME_SIGNAL_TYPES = {
    "B_BUY_30M_VOL",
    "S_SELL_30M_SHRINK",
    "BUY_HINT",
    "SELL_HINT",
}

OUTCOME_TO_EVENT_TYPE = {
    "matched": "TriggerMatched",
    "pending_market_data": "TriggerPendingMarketData",
    "no_op": None,
    "quality_blocked": None,
    "inactive": None,
}


def evaluate_v4_plan(
    context_row: Mapping[str, Any],
    projection_row: Mapping[str, Any] | None,
    *,
    v4_run_id: str,
    previous_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one v4 dry-run outcome plan for a trigger context row."""

    condition_key = str(
        context_row.get("condition_key")
        or context_row.get("original_condition_key")
        or ""
    )
    direction, condition_family, periods = _parse_condition_key(condition_key, context_row)
    signal_type = "B_BUY" if direction == "buy" else "S_SELL"
    condition_signal_type = condition_signal_type_for_condition_key(
        condition_key,
        direction=direction,
        condition_family=condition_family,
    )
    projection = _extract_projection_enrichment(projection_row)
    context_for_trade_date = _normalize_trade_date(
        context_row.get("for_trade_date") or context_row.get("trade_date")
    )
    projection_for_trade_date = _normalize_trade_date(
        projection.get("for_trade_date")
        or projection.get("trade_date")
        or (projection_row.get("for_trade_date") if projection_row else None)
        or (projection_row.get("trade_date") if projection_row else None)
    )
    for_trade_date = context_for_trade_date or projection_for_trade_date
    period_baselines = _extract_period_baselines(context_row)
    projection_30m_type = projection.get("projection_30m_type") or "none"
    projection_30m_flag = bool(projection.get("projection_30m_flag") or False)
    projection_30m_volume_up_flag, projection_30m_shrink_down_flag = projection_30m_flags(
        projection_30m_type,
        projection_30m_flag=projection_30m_flag,
    )

    base_plan: dict[str, Any] = {
        "trigger_rule_spec_version": TRIGGER_RULE_SPEC_VERSION,
        "trigger_rule_policy_hash": TRIGGER_RULE_POLICY_HASH,
        "v4_run_id": v4_run_id,
        "asset_kind": context_row.get("asset_kind"),
        "identity_key": context_row.get("identity_key"),
        "trade_date": str(context_row.get("trade_date") or ""),
        "for_trade_date": for_trade_date,
        "projection_for_trade_date": projection_for_trade_date,
        "direction": direction,
        "signal_type": signal_type,
        "runtime_signal_type": signal_type,
        "condition_signal_type": condition_signal_type,
        "condition_key": condition_key,
        "original_condition_key": context_row.get("original_condition_key") or condition_key,
        "trigger_kind": "hint" if condition_family == "hint" else "trigger",
        "requested_periods": list(periods),
        "projection_period": projection.get("projection_period"),
        "projection_30m_required": condition_family == "hint",
        "projection_30m_flag": projection_30m_flag,
        "projection_30m_type": projection_30m_type,
        "projection_30m_volume_up_flag": projection_30m_volume_up_flag,
        "projection_30m_shrink_down_flag": projection_30m_shrink_down_flag,
        "trigger_mark_candidate": _trigger_mark_candidate(direction, projection),
        "trigger_price": projection.get("current_price_or_close"),
        "trigger_time": projection.get("current_metric_time"),
        "event_time": projection.get("current_metric_time"),
        "price_source": "n3_projection_enrichment" if projection else "missing_n3_projection_enrichment",
        "baseline_source": "trigger_baseline",
        "data_quality_status": projection.get("current_metric_quality_status") or "unknown",
        "match_basis": "v4_context_projection_enrichment",
        "source_event_id": projection_row.get("source_event_id") if projection_row else None,
        "source_event_type": projection_row.get("source_event_type") if projection_row else None,
        "source_condition_run_id": (
            projection_row.get("source_condition_run_id")
            if projection_row
            else context_row.get("source_condition_run_id")
        ),
        "source_market_data_run_id": (
            projection_row.get("source_market_data_run_id") if projection_row else None
        ),
        "context_snapshot_id": (
            context_row.get("context_snapshot_id")
            or context_row.get("trigger_context_snapshot_id")
            or context_row.get("snapshot_id")
        ),
        "period_trigger_baseline_trace": _json_object(
            context_row.get("period_trigger_baseline_json")
        ),
        "n3_trace": projection.get("projection_lineage_json") or {},
        "triggered_periods": [],
        "all_trigger_periods": [],
        "primary_trigger_period": None,
        "triggered_period_details": [],
        "previous_trigger_live": bool(previous_state.get("trigger_live")) if previous_state else False,
        "previous_status": previous_state.get("current_status") if previous_state else "inactive",
        "previous_primary_trigger_period": (
            previous_state.get("primary_trigger_period") if previous_state else None
        ),
        "previous_all_trigger_periods": (
            list(previous_state.get("all_trigger_periods") or []) if previous_state else []
        ),
        "source_projection_run_id": projection_row.get("projection_run_id") if projection_row else None,
        "projection_lineage_json": projection.get("projection_lineage_json") or {},
        "blocked_reason": None,
        "pending_reasons": [],
        "quality_reasons": [],
    }

    if condition_family == "full":
        base_plan.update(
            {
                "trigger_mark_candidate": "normal",
                "projection_30m_flag": False,
                "projection_30m_type": "none",
                "projection_30m_volume_up_flag": False,
                "projection_30m_shrink_down_flag": False,
                "projection_period": None,
                "previous_all_trigger_periods": [],
            }
        )
        return _evaluate_full(base_plan, direction, period_baselines, projection, context_row)

    if condition_family == "hint":
        return _evaluate_hint(base_plan, direction, projection)

    return _evaluate_ordinary(
        base_plan,
        direction,
        periods,
        period_baselines,
        projection,
        for_trade_date=for_trade_date,
        projection_for_trade_date=projection_for_trade_date,
    )


def build_v4_dry_run_report(
    plans: list[Mapping[str, Any]],
    *,
    v3_summary: Mapping[str, Any] | None = None,
    traceability_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize v4 dry-run plans and compatibility proofs."""

    outcome_counts = Counter(str(plan.get("outcome_classification")) for plan in plans)
    event_counts = Counter(str(plan.get("output_event_type")) for plan in plans if plan.get("output_event_type"))
    signal_counts = Counter(str(plan.get("signal_type")) for plan in plans)
    kind_counts = Counter(str(plan.get("trigger_kind")) for plan in plans)
    marker_counts = Counter(str(plan.get("trigger_mark_candidate")) for plan in plans)
    deprecated_count = sum(
        count for signal, count in signal_counts.items() if signal in DEPRECATED_RUNTIME_SIGNAL_TYPES
    )
    n5_entry_count = sum(1 for plan in plans if plan.get("n5_entry_allowed") is True)
    n5_violations = [
        plan
        for plan in plans
        if plan.get("n5_entry_allowed") is True
        and not (
            plan.get("output_event_type") == "TriggerMatched"
            and plan.get("signal_type") in RUNTIME_SIGNAL_TYPES
            and plan.get("outcome_classification") == "matched"
            and plan.get("trigger_live") is True
        )
    ]
    full_blocked = [
        {
            "identity_key": plan.get("identity_key"),
            "condition_key": plan.get("condition_key"),
            "blocked_reason": plan.get("blocked_reason"),
        }
        for plan in plans
        if plan.get("condition_key") in {"BUY:FULL", "SELL:FULL"}
    ]

    return {
        "result": "DRY_RUN_PASS" if not n5_violations and deprecated_count == 0 else "DRY_RUN_BLOCKED",
        "trigger_rule_spec_version": TRIGGER_RULE_SPEC_VERSION,
        "trigger_rule_policy_hash": TRIGGER_RULE_POLICY_HASH,
        "plan_count": len(plans),
        "outcome_counts": dict(outcome_counts),
        "event_counts": dict(event_counts),
        "signal_type_distribution": dict(signal_counts),
        "trigger_kind_distribution": dict(kind_counts),
        "trigger_mark_candidate_distribution": dict(marker_counts),
        "deprecated_runtime_signal_type_count": deprecated_count,
        "n5_entry_guard": {
            "allowed_count": n5_entry_count,
            "violations": len(n5_violations),
            "rule": "TriggerMatched+B_BUY/S_SELL+matched+trigger_live=true+n5_entry_allowed=true",
        },
        "full_blocked_proof": {
            "blocked_count": len(full_blocked),
            "samples": full_blocked[:20],
        },
        "source_boundary_proof": {
            "uses_n2_context_enrichment": True,
            "uses_n3_projection_enrichment": True,
            "opens_database_connection": False,
            "fetches_external_market_data": False,
            "self_aggregates_upstream_history": False,
        },
        "v3_summary": dict(v3_summary or {}),
        "traceability_summary": dict(traceability_summary or {}),
        "sample_plans": [dict(plan) for plan in plans[:20]],
    }


def _evaluate_ordinary(
    base_plan: dict[str, Any],
    direction: str,
    periods: list[str],
    period_baselines: Mapping[str, Any],
    projection: Mapping[str, Any],
    *,
    for_trade_date: str | None,
    projection_for_trade_date: str | None,
) -> dict[str, Any]:
    if not projection:
        return _finalize_plan(
            base_plan,
            outcome="pending_market_data",
            triggered_periods=[],
            details=[
                _period_pending_detail(period, period_baselines, "missing_projection_enrichment")
                for period in periods
            ],
            pending_reasons=["missing_projection_enrichment"],
        )

    quality_reason = _projection_quality_reason(projection)
    if quality_reason:
        return _finalize_plan(
            base_plan,
            outcome="quality_blocked",
            triggered_periods=[],
            details=[
                _period_quality_detail(period, period_baselines, quality_reason)
                for period in periods
            ],
            blocked_reason=quality_reason,
            quality_reasons=[quality_reason],
        )

    triggered_periods: list[str] = []
    details: list[dict[str, Any]] = []
    pending_reasons: list[str] = []
    quality_reasons: list[str] = []
    target_transition = "volume_up" if direction == "buy" else "low_volume_down"

    for period in periods:
        detail = _evaluate_period(
            period,
            direction,
            target_transition,
            period_baselines,
            projection,
            for_trade_date=for_trade_date,
            projection_for_trade_date=projection_for_trade_date,
        )
        details.append(detail)
        if detail["classification"] == "triggered":
            triggered_periods.append(period)
        elif detail["classification"] == "pending":
            pending_reasons.append(detail["reason"])
        elif detail["classification"] == "quality_blocked":
            quality_reasons.append(detail["reason"])

    if triggered_periods:
        return _finalize_plan(
            base_plan,
            outcome="matched",
            triggered_periods=triggered_periods,
            details=details,
        )
    if pending_reasons:
        return _finalize_plan(
            base_plan,
            outcome="pending_market_data",
            triggered_periods=[],
            details=details,
            pending_reasons=sorted(set(pending_reasons)),
        )
    if quality_reasons:
        return _finalize_plan(
            base_plan,
            outcome="quality_blocked",
            triggered_periods=[],
            details=details,
            blocked_reason=sorted(set(quality_reasons))[0],
            quality_reasons=sorted(set(quality_reasons)),
        )
    return _finalize_plan(base_plan, outcome="no_op", triggered_periods=[], details=details)


def _evaluate_full(
    base_plan: dict[str, Any],
    direction: str,
    period_baselines: Mapping[str, Any],
    projection: Mapping[str, Any],
    context_row: Mapping[str, Any],
) -> dict[str, Any]:
    if not _has_explicit_full_context(context_row):
        return _finalize_plan(
            base_plan,
            outcome="quality_blocked",
            triggered_periods=[],
            details=[_period_quality_detail("D", period_baselines, "full_n2_context_missing")],
            blocked_reason="full_n2_context_missing",
            quality_reasons=["full_n2_context_missing"],
        )

    if not projection:
        return _finalize_plan(
            base_plan,
            outcome="pending_market_data",
            triggered_periods=[],
            details=[_period_pending_detail("D", period_baselines, "missing_projection_enrichment")],
            pending_reasons=["missing_projection_enrichment"],
        )

    quality_reason = _projection_quality_reason(projection)
    if quality_reason:
        return _finalize_plan(
            base_plan,
            outcome="quality_blocked",
            triggered_periods=[],
            details=[_period_quality_detail("D", period_baselines, quality_reason)],
            blocked_reason=quality_reason,
            quality_reasons=[quality_reason],
        )

    target_transition = "volume_up" if direction == "buy" else "low_volume_down"
    detail = _evaluate_full_period("D", direction, target_transition, period_baselines, projection)
    if detail["classification"] == "triggered":
        return _finalize_plan(
            base_plan,
            outcome="matched",
            triggered_periods=["D"],
            details=[detail],
        )
    if detail["classification"] == "pending":
        return _finalize_plan(
            base_plan,
            outcome="pending_market_data",
            triggered_periods=[],
            details=[detail],
            pending_reasons=[detail["reason"]],
        )
    if detail["classification"] == "quality_blocked":
        return _finalize_plan(
            base_plan,
            outcome="quality_blocked",
            triggered_periods=[],
            details=[detail],
            blocked_reason=detail["reason"],
            quality_reasons=[detail["reason"]],
        )
    return _finalize_plan(base_plan, outcome="no_op", triggered_periods=[], details=[detail])


def _evaluate_hint(base_plan: dict[str, Any], direction: str, projection: Mapping[str, Any]) -> dict[str, Any]:
    if not projection:
        return _finalize_plan(
            base_plan,
            outcome="pending_market_data",
            triggered_periods=[],
            details=[],
            pending_reasons=["missing_projection_enrichment"],
        )

    quality_reason = _projection_quality_reason(projection)
    if quality_reason:
        return _finalize_plan(
            base_plan,
            outcome="quality_blocked",
            triggered_periods=[],
            details=[],
            blocked_reason=quality_reason,
            quality_reasons=[quality_reason],
        )

    expected_type = "volume_up" if direction == "buy" else "shrink_down"
    has_flag = "projection_30m_flag" in projection
    has_type = "projection_30m_type" in projection
    if not has_flag or not has_type:
        return _finalize_plan(
            base_plan,
            outcome="pending_market_data",
            triggered_periods=[],
            details=[],
            pending_reasons=["missing_projection_30m_status"],
        )

    if projection.get("projection_30m_type") == "unknown":
        return _finalize_plan(
            base_plan,
            outcome="pending_market_data",
            triggered_periods=[],
            details=[],
            pending_reasons=["projection_30m_unknown"],
        )

    if bool(projection.get("projection_30m_flag")) and projection.get("projection_30m_type") == expected_type:
        return _finalize_plan(base_plan, outcome="matched", triggered_periods=[], details=[])
    return _finalize_plan(base_plan, outcome="no_op", triggered_periods=[], details=[])


def _evaluate_period(
    period: str,
    direction: str,
    target_transition: str,
    period_baselines: Mapping[str, Any],
    projection: Mapping[str, Any],
    *,
    for_trade_date: str | None = None,
    projection_for_trade_date: str | None = None,
) -> dict[str, Any]:
    baseline = _period_baseline(period_baselines, period)
    previous_transition = baseline.get("previous_transition")
    if baseline.get("period_baseline_ready") is False:
        return _period_quality_detail(period, period_baselines, "period_baseline_not_ready")
    rollover_block = _period_rollover_block_detail(
        period,
        baseline,
        period_baselines,
        for_trade_date=for_trade_date,
        projection_for_trade_date=projection_for_trade_date,
    )
    if rollover_block:
        return rollover_block

    price = _to_float(projection.get("current_price_or_close"))
    transition_amount_field = CURRENT_PERIOD_AVG_FIELD_BY_PERIOD.get(period, "current_period_avg_with_today")
    amount = _to_float(projection.get(transition_amount_field))
    entity_high = _to_float(baseline.get("trigger_previous_entity_high"))
    entity_low = _to_float(baseline.get("trigger_previous_entity_low"))
    amount_baseline = _to_float(_selected_previous_avg_amount(baseline))
    chain_pass = _chain_pass_for_period(projection, period)
    amount_unit_status = _amount_unit_status(baseline, projection)
    amount_source_status = _formal_amount_source_status(projection)

    missing_fields = [
        name
        for name, value in {
            "current_price_or_close": price,
            transition_amount_field: amount,
            "previous_avg_amount": amount_baseline,
            "previous_transition": previous_transition,
            "trigger_previous_entity_high": entity_high,
            "trigger_previous_entity_low": entity_low,
            "trigger_amount_chain_pass": chain_pass,
        }.items()
        if value is None
    ]
    if amount_unit_status["status"] == "mismatch":
        missing_fields.append("trigger_amount_unit_mismatch")
    elif amount_unit_status["status"] != "matched":
        missing_fields.append("trigger_amount_unit_not_proven")
    if amount_source_status["status"] == "not_allowed":
        missing_fields.append("formal_period_metric_source_not_allowed")
    elif amount_source_status["status"] != "matched":
        missing_fields.append("formal_period_metric_source_not_proven")
    if missing_fields:
        return {
            "period": period,
            "classification": "pending",
            "reason": "missing_" + ",".join(missing_fields),
            "current_transition": None,
            "previous_transition": previous_transition,
            "previous_entity_high": entity_high,
            "previous_entity_low": entity_low,
            "current_price_or_close": price,
            "current_amount_metric": amount,
            "transition_amount_field": transition_amount_field,
            "transition_amount_value": amount,
            "used_for_period": period,
            "compare_to": f"previous_avg_amount[{period}]",
            "previous_amount_baseline": amount_baseline,
            "trigger_previous_entity_high": entity_high,
            "trigger_previous_entity_low": entity_low,
            "trigger_previous_amount_baseline": amount_baseline,
            "transition_amount_pass": None,
            "trigger_amount_chain_pass": chain_pass,
            "amount_unit_status": amount_unit_status,
            "amount_source_status": amount_source_status,
            "amount_metric": transition_amount_field,
            "amount_rule": "price_break_plus_current_period_avg_with_today_vs_previous_avg_amount",
            "source_field_trace": _source_field_trace(period),
            **_period_rollover_trace(
                period,
                baseline,
                for_trade_date=for_trade_date,
                projection_for_trade_date=projection_for_trade_date,
            ),
        }

    if direction == "buy":
        price_pass = price > entity_high
        transition_amount_pass = amount > amount_baseline
        if price_pass and transition_amount_pass:
            current_transition = "volume_up"
        elif price_pass:
            current_transition = "low_volume_up"
        else:
            current_transition = "other"
    else:
        price_pass = price < entity_low
        transition_amount_pass = amount < amount_baseline
        if price_pass and transition_amount_pass:
            current_transition = "low_volume_down"
        elif price_pass:
            current_transition = "volume_down"
        else:
            current_transition = "other"

    triggered = (
        previous_transition != target_transition
        and current_transition == target_transition
        and _chain_satisfied(period, chain_pass)
    )
    return {
        "period": period,
        "classification": "triggered" if triggered else "no_op",
        "reason": None if triggered else "transition_or_chain_not_triggered",
        "current_transition": current_transition,
        "previous_transition": previous_transition,
        "previous_entity_high": entity_high,
        "previous_entity_low": entity_low,
        "current_price_or_close": price,
        "current_amount_metric": amount,
        "transition_amount_field": transition_amount_field,
        "transition_amount_value": amount,
        "used_for_period": period,
        "compare_to": f"previous_avg_amount[{period}]",
        "previous_amount_baseline": amount_baseline,
        "trigger_previous_entity_high": entity_high,
        "trigger_previous_entity_low": entity_low,
        "trigger_previous_amount_baseline": amount_baseline,
        "transition_amount_pass": transition_amount_pass,
        "trigger_amount_chain_pass": chain_pass,
        "amount_unit_status": amount_unit_status,
        "amount_source_status": amount_source_status,
        "amount_metric": transition_amount_field,
        "amount_rule": "price_break_plus_current_period_avg_with_today_vs_previous_avg_amount",
        "source_field_trace": _source_field_trace(period),
        **_period_rollover_trace(
            period,
            baseline,
            for_trade_date=for_trade_date,
            projection_for_trade_date=projection_for_trade_date,
        ),
    }


def _evaluate_full_period(
    period: str,
    direction: str,
    target_transition: str,
    period_baselines: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    detail = _evaluate_period(period, direction, target_transition, period_baselines, projection)
    if (
        detail["classification"] == "no_op"
        and detail.get("current_transition") == target_transition
        and detail.get("transition_amount_pass") is True
        and detail.get("trigger_amount_chain_pass") is True
    ):
        return {**detail, "classification": "triggered", "reason": None}
    return detail


def _finalize_plan(
    plan: dict[str, Any],
    *,
    outcome: str,
    triggered_periods: list[str],
    details: list[Mapping[str, Any]],
    blocked_reason: str | None = None,
    pending_reasons: list[str] | None = None,
    quality_reasons: list[str] | None = None,
) -> dict[str, Any]:
    ordered_triggered = [period for period in PERIOD_PRIORITY if period in set(triggered_periods)]
    previous_all = list(plan.get("previous_all_trigger_periods") or [])
    all_periods = [period for period in PERIOD_PRIORITY if period in set(previous_all + ordered_triggered)]
    event_type = OUTCOME_TO_EVENT_TYPE[outcome]
    trigger_live = outcome == "matched"
    current_status = "matched" if outcome == "matched" else outcome
    trigger_period = None
    if event_type == "TriggerMatched":
        trigger_period = "30m" if plan.get("trigger_kind") == "hint" else _primary_period(ordered_triggered)
    elif plan.get("trigger_kind") == "hint":
        trigger_period = "30m"

    plan.update(
        {
            "outcome_classification": outcome,
            "output_event_type": event_type,
            "trigger_live": trigger_live,
            "current_status": current_status,
            "trigger_period": trigger_period,
            "triggered_periods": ordered_triggered,
            "all_trigger_periods": all_periods,
            "primary_trigger_period": _primary_period(all_periods),
            "triggered_period_details": [
                dict(detail) for detail in details if detail.get("classification") == "triggered"
            ],
            "period_evaluation_details": [dict(detail) for detail in details],
            "blocked_reason": blocked_reason,
            "pending_reasons": list(pending_reasons or []),
            "quality_reasons": list(quality_reasons or []),
        }
    )
    plan["n5_entry_allowed"] = (
        event_type == "TriggerMatched"
        and plan.get("signal_type") in RUNTIME_SIGNAL_TYPES
        and outcome == "matched"
        and trigger_live is True
    )
    return plan


def condition_signal_type_for_condition_key(
    condition_key: str,
    *,
    direction: str | None = None,
    condition_family: str | None = None,
) -> str:
    """Return the six-family condition signal type carried by N4 payloads."""

    if condition_key in {"BUY_HINT", "SELL_HINT", "BUY:FULL", "SELL:FULL"}:
        return condition_key
    if condition_key.startswith("SELL"):
        return "SELL"
    if condition_key.startswith("BUY"):
        return "BUY"
    if condition_family == "hint":
        return "SELL_HINT" if direction == "sell" else "BUY_HINT"
    if condition_family == "full":
        return "SELL:FULL" if direction == "sell" else "BUY:FULL"
    return "SELL" if direction == "sell" else "BUY"


def projection_30m_flags(
    projection_30m_type: Any,
    *,
    projection_30m_flag: bool,
) -> tuple[bool, bool]:
    projection_type = str(projection_30m_type or "none")
    return (
        bool(projection_30m_flag and projection_type == "volume_up"),
        bool(projection_30m_flag and projection_type == "shrink_down"),
    )


def _parse_condition_key(
    condition_key: str,
    context_row: Mapping[str, Any],
) -> tuple[str, str, list[str]]:
    if condition_key == "BUY_HINT":
        return "buy", "hint", []
    if condition_key == "SELL_HINT":
        return "sell", "hint", []
    if condition_key == "BUY:FULL":
        return "buy", "full", ["D"]
    if condition_key == "SELL:FULL":
        return "sell", "full", ["D"]
    if condition_key.startswith("BUY"):
        return "buy", "ordinary", _parse_periods(condition_key, context_row)
    if condition_key.startswith("SELL"):
        return "sell", "ordinary", _parse_periods(condition_key, context_row)
    direction = str(context_row.get("direction") or "buy").lower()
    return ("sell" if direction == "sell" else "buy"), "ordinary", _parse_periods(condition_key, context_row)


def _parse_periods(condition_key: str, context_row: Mapping[str, Any]) -> list[str]:
    if ":" in condition_key:
        suffix = condition_key.split(":", 1)[1]
        periods = [part.strip() for part in suffix.split(",") if part.strip() in PERIOD_PRIORITY]
        if periods:
            return [period for period in PERIOD_PRIORITY if period in set(periods)]
    raw_period = context_row.get("trigger_period") or context_row.get("period")
    if raw_period in PERIOD_PRIORITY:
        return [str(raw_period)]
    return ["D"]


def _has_explicit_full_context(context_row: Mapping[str, Any]) -> bool:
    condition_key = str(context_row.get("condition_key") or "")
    original_condition_key = str(context_row.get("original_condition_key") or "")
    if condition_key not in {"BUY:FULL", "SELL:FULL"}:
        return False
    if original_condition_key != condition_key:
        return False
    expected_direction = "buy" if condition_key == "BUY:FULL" else "sell"
    direction = str(context_row.get("direction") or expected_direction).lower()
    return direction == expected_direction


def _extract_period_baselines(context_row: Mapping[str, Any]) -> Mapping[str, Any]:
    baseline_json = _json_object(context_row.get("period_trigger_baseline_json"))
    periods = baseline_json.get("periods")
    if isinstance(periods, Mapping):
        return periods
    return {}


def _extract_projection_enrichment(projection_row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not projection_row:
        return {}
    raw_json = _json_object(projection_row.get("raw_json"))
    enrichment = raw_json.get("enrichment_v1")
    if isinstance(enrichment, Mapping):
        result = dict(enrichment)
    else:
        result = {}
    for key in (
        "current_price_or_close",
        "current_amount_metric",
        "today_virt_amount",
        "weekly_avg_with_today",
        "monthly_avg_with_today",
        "quarterly_avg_with_today",
        "yearly_avg_with_today",
        "current_amount_metric_unit",
        "current_amount_metric_source_kind",
        "amount_unit",
        "current_metric_time",
        "current_metric_quality_status",
        "projection_period",
        "projection_30m_flag",
        "projection_30m_type",
        "trigger_amount_chain_pass",
        "current_30m_virtual_amount",
        "reference_30m_amount",
        "projection_lineage_json",
        "source_freshness_status",
        "metric_ready",
        "metric_quality_status",
        "quality_visible",
        "quality_reason",
        "for_trade_date",
        "trade_date",
    ):
        if key in projection_row and key not in result:
            result[key] = projection_row[key]
    return result


def _period_baseline(period_baselines: Mapping[str, Any], period: str) -> dict[str, Any]:
    value = period_baselines.get(period) or {}
    return dict(value) if isinstance(value, Mapping) else {}


def _period_value(period_baselines: Mapping[str, Any], period: str, key: str) -> Any:
    return _period_baseline(period_baselines, period).get(key)


def _chain_pass_for_period(projection: Mapping[str, Any], period: str) -> bool | str | None:
    chain = projection.get("trigger_amount_chain_pass")
    if not isinstance(chain, Mapping):
        return "not_applicable" if period == "Y" else None
    value = chain.get(period)
    if value is None and isinstance(chain.get("period_baseline_pass"), Mapping):
        value = chain["period_baseline_pass"].get(period)
    if isinstance(value, Mapping):
        value = value.get("pass")
    if value is None:
        return "not_applicable" if period == "Y" else None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "not_applicable":
            return "not_applicable"
        if normalized in {"true", "passed"}:
            return True
        if normalized in {"false", "failed"}:
            return False
    if period == "Y" and value is True:
        return "not_applicable"
    return bool(value)


def _chain_satisfied(period: str, chain_pass: bool | str | None) -> bool:
    if period == "Y":
        return chain_pass == "not_applicable"
    return chain_pass is True


def _selected_previous_avg_amount(baseline: Mapping[str, Any]) -> Any:
    for key in (
        "previous_avg_amount",
        "previous_amount",
        "previous_amount_baseline",
        "classification_previous_amount_baseline",
        "trigger_previous_amount_baseline",
    ):
        value = baseline.get(key)
        if value not in (None, ""):
            return value
    return None


def _amount_unit_status(baseline: Mapping[str, Any], projection: Mapping[str, Any]) -> dict[str, Any]:
    baseline_unit = str(
        baseline.get("trigger_previous_amount_baseline_unit")
        or baseline.get("amount_unit")
        or ""
    ).strip()
    projection_unit = str(
        projection.get("current_amount_metric_unit")
        or projection.get("amount_unit")
        or ""
    ).strip()
    if baseline_unit and projection_unit and baseline_unit != projection_unit:
        return {
            "status": "mismatch",
            "trigger_previous_amount_baseline_unit": baseline_unit,
            "current_amount_metric_unit": projection_unit,
        }
    return {
        "status": "matched" if baseline_unit and projection_unit else "not_declared",
        "trigger_previous_amount_baseline_unit": baseline_unit or None,
        "current_amount_metric_unit": projection_unit or None,
    }


def _formal_amount_source_status(projection: Mapping[str, Any]) -> dict[str, Any]:
    source_kind = str(projection.get("current_amount_metric_source_kind") or "").strip()
    if source_kind == FORMAL_AMOUNT_METRIC_SOURCE_KIND:
        return {"status": "matched", "current_amount_metric_source_kind": source_kind}
    if source_kind:
        return {"status": "not_allowed", "current_amount_metric_source_kind": source_kind}
    return {"status": "not_declared", "current_amount_metric_source_kind": None}


def _trigger_mark_candidate(direction: str, projection: Mapping[str, Any]) -> str:
    projection_type = projection.get("projection_30m_type")
    if direction == "buy" and projection_type == "volume_up":
        return "30m_volume"
    if direction == "sell" and projection_type == "shrink_down":
        return "30m_shrink"
    return "normal"


def _projection_quality_reason(projection: Mapping[str, Any]) -> str | None:
    quality = projection.get("current_metric_quality_status")
    metric_quality = projection.get("metric_quality_status")
    freshness = projection.get("source_freshness_status")
    quality_reason = projection.get("quality_reason")
    if projection.get("metric_ready") is False:
        return str(quality_reason or "projection_metric_not_ready")
    if metric_quality is not None and metric_quality != "passed":
        return str(quality_reason or "projection_metric_quality_not_passed")
    if quality is not None and quality != "passed":
        return str(quality_reason or "projection_quality_not_passed")
    if freshness is not None and freshness not in {"passed", "fresh", "ready", "fresh_complete_lineage"}:
        return str(quality_reason or "projection_source_not_fresh")
    return None


def _period_pending_detail(period: str, period_baselines: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "period": period,
        "classification": "pending",
        "reason": reason,
        "current_transition": None,
        "previous_transition": _period_value(period_baselines, period, "previous_transition"),
        "previous_entity_high": _period_value(period_baselines, period, "trigger_previous_entity_high"),
        "previous_entity_low": _period_value(period_baselines, period, "trigger_previous_entity_low"),
        "current_price_or_close": None,
        "current_amount_metric": None,
        "previous_amount_baseline": _period_value(
            period_baselines, period, "trigger_previous_amount_baseline"
        ),
        "trigger_previous_entity_high": _period_value(period_baselines, period, "trigger_previous_entity_high"),
        "trigger_previous_entity_low": _period_value(period_baselines, period, "trigger_previous_entity_low"),
        "trigger_previous_amount_baseline": _period_value(
            period_baselines, period, "trigger_previous_amount_baseline"
        ),
        "transition_amount_pass": None,
        "trigger_amount_chain_pass": None,
        "amount_unit_status": _amount_unit_status(_period_baseline(period_baselines, period), {}),
        "amount_metric": "current_amount_metric",
        "source_field_trace": _source_field_trace(period),
    }


def _period_quality_detail(period: str, period_baselines: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "period": period,
        "classification": "quality_blocked",
        "reason": reason,
        "current_transition": None,
        "previous_transition": _period_value(period_baselines, period, "previous_transition"),
        "previous_entity_high": _period_value(period_baselines, period, "trigger_previous_entity_high"),
        "previous_entity_low": _period_value(period_baselines, period, "trigger_previous_entity_low"),
        "current_price_or_close": None,
        "current_amount_metric": None,
        "previous_amount_baseline": _period_value(
            period_baselines, period, "trigger_previous_amount_baseline"
        ),
        "trigger_previous_entity_high": _period_value(period_baselines, period, "trigger_previous_entity_high"),
        "trigger_previous_entity_low": _period_value(period_baselines, period, "trigger_previous_entity_low"),
        "trigger_previous_amount_baseline": _period_value(
            period_baselines, period, "trigger_previous_amount_baseline"
        ),
        "transition_amount_pass": None,
        "trigger_amount_chain_pass": None,
        "amount_unit_status": _amount_unit_status(_period_baseline(period_baselines, period), {}),
        "amount_metric": "current_amount_metric",
        "source_field_trace": _source_field_trace(period),
    }


def _period_rollover_block_detail(
    period: str,
    baseline: Mapping[str, Any],
    period_baselines: Mapping[str, Any],
    *,
    for_trade_date: str | None,
    projection_for_trade_date: str | None,
) -> dict[str, Any] | None:
    trace = _period_rollover_trace(
        period,
        baseline,
        for_trade_date=for_trade_date,
        projection_for_trade_date=projection_for_trade_date,
    )
    if period not in ROLLOVER_GUARDED_PERIODS:
        return None
    reason = trace.get("stale_period_baseline_reason")
    if not reason:
        return None
    detail = _period_quality_detail(period, period_baselines, str(reason))
    detail.update(trace)
    return detail


def _period_rollover_trace(
    period: str,
    baseline: Mapping[str, Any],
    *,
    for_trade_date: str | None,
    projection_for_trade_date: str | None,
) -> dict[str, Any]:
    baseline_key = _normalize_period_key(baseline.get("period_key_current"))
    expected_key = expected_period_key_current(for_trade_date, period) if for_trade_date else None
    baseline_previous = _normalize_period_key(baseline.get("period_key_previous"))
    baseline_source_trade_date = _normalize_trade_date(
        baseline.get("baseline_source_trade_date")
        or baseline.get("source_trade_date")
        or baseline.get("prev_trade_date")
    )
    reason = None
    if period in ROLLOVER_GUARDED_PERIODS:
        if not for_trade_date or not expected_key:
            reason = "missing_for_trade_date_for_period_rollover"
        elif projection_for_trade_date and projection_for_trade_date != for_trade_date:
            reason = "for_trade_date_mismatch"
        elif not baseline_key or baseline_key != expected_key:
            reason = STALE_PERIOD_BASELINE_REASON
    return {
        "baseline_period_key_current": baseline_key,
        "expected_period_key_current": expected_key,
        "baseline_period_key_previous": baseline_previous,
        "baseline_source_trade_date": baseline_source_trade_date,
        "for_trade_date": for_trade_date,
        "projection_for_trade_date": projection_for_trade_date,
        "stale_period_baseline": bool(reason),
        "stale_period_baseline_reason": reason,
    }


def expected_period_key_current(for_trade_date: str | None, period: str) -> str | None:
    trade_date = _parse_trade_date(for_trade_date)
    if not trade_date:
        return None
    if period == "W":
        iso = trade_date.isocalendar()
        return f"{iso.year}W{iso.week:02d}"
    if period == "M":
        return f"{trade_date.year}{trade_date.month:02d}"
    if period == "Q":
        return f"{trade_date.year}Q{((trade_date.month - 1) // 3) + 1}"
    if period == "Y":
        return str(trade_date.year)
    return None


def _parse_trade_date(value: Any) -> date | None:
    text = _normalize_trade_date(value)
    if not text:
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def _normalize_trade_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("-", "")
    if len(normalized) == 8 and normalized.isdigit():
        return normalized
    return None


def _normalize_period_key(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _primary_period(periods: list[str]) -> str | None:
    for period in PERIOD_PRIORITY:
        if period in periods:
            return period
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _source_field_trace(period: str) -> dict[str, str]:
    transition_amount_field = CURRENT_PERIOD_AVG_FIELD_BY_PERIOD.get(period, "current_period_avg_with_today")
    return {
        "period": period,
        "previous_transition": "trigger_context_snapshot.period_trigger_baseline_json",
        "previous_entity_high": "trigger_context_snapshot.period_trigger_baseline_json.trigger_previous_entity_high",
        "previous_entity_low": "trigger_context_snapshot.period_trigger_baseline_json.trigger_previous_entity_low",
        "previous_amount_baseline": "trigger_context_snapshot.period_trigger_baseline_json.trigger_previous_amount_baseline",
        "trigger_previous_entity_high": "trigger_context_snapshot.period_trigger_baseline_json",
        "trigger_previous_entity_low": "trigger_context_snapshot.period_trigger_baseline_json",
        "trigger_previous_amount_baseline": "trigger_context_snapshot.period_trigger_baseline_json",
        "current_price_or_close": "n3_projection_enrichment.enrichment_v1",
        "transition_amount_field": transition_amount_field,
        "transition_amount_value": "n3_projection_enrichment.enrichment_v1",
        "current_period_avg_with_today": "n3_projection_enrichment.enrichment_v1",
        "trigger_amount_chain_pass": "n3_projection_enrichment.enrichment_v1",
    }
