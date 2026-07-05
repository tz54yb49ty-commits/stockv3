"""N4P ordinary realtime-action metric matcher dry-run.

This module is plan-only. It adapts N3P realtime action-confirmation metric
rows into the existing N4 rule v4 matcher input shape, then emits provisional
TriggerMatched plans for ordinary BUY/SELL/FULL conditions without writing DB
rows or touching downstream layers.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Mapping, Sequence

from ashare_v3.events.ids import stable_hash
from ashare_v3.trigger.action_confirmation_metric_matcher import (
    FORMAL_AMOUNT_SOURCE_KIND,
    FORMAL_AMOUNT_UNIT,
    evaluate_formal_amount_chain,
    trigger_amount_chain_pass_for_period,
)
from ashare_v3.trigger.projection_matcher import normalize_context_row
from ashare_v3.trigger.rule_v4_matcher import (
    TRIGGER_RULE_POLICY_HASH,
    TRIGGER_RULE_SPEC_VERSION,
    condition_signal_type_for_condition_key,
    evaluate_v4_plan,
)


SOURCE_METRIC_KIND = "realtime_action_confirmation_metric"
ORDINARY_CONDITION_SIGNAL_TYPES = {"BUY", "SELL", "BUY:FULL", "SELL:FULL"}
HINT_CONDITION_KEYS = {"BUY_HINT", "SELL_HINT"}
SIDE_EFFECT_GUARD = {
    "db_written": False,
    "outbox_written": False,
    "inbox_written": False,
    "checkpoint_written": False,
    "trigger_run_written": False,
    "trigger_state_written": False,
    "trigger_match_written": False,
    "n5_executed": False,
    "n6_written": False,
    "sim_trade_virtual_written": False,
    "worker_started": False,
}


def build_provisional_ordinary_matcher_plans(
    *,
    trigger_context_run_id: str,
    source_metric_run_id: str,
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    metric_lookup = latest_n3p_metric_lookup(metric_rows, source_metric_run_id=source_metric_run_id)
    plans: list[dict[str, Any]] = []
    for raw_context in context_rows:
        context = normalize_context_row(raw_context)
        if context.get("run_id") != trigger_context_run_id:
            continue
        condition_key = str(context.get("condition_key") or "")
        if condition_key in HINT_CONDITION_KEYS:
            continue
        trigger_type = ordinary_trigger_type(condition_key)
        if trigger_type not in ORDINARY_CONDITION_SIGNAL_TYPES:
            continue
        if metric_lookup["has_condition_grain"]:
            metric = metric_lookup["by_condition_grain"].get(n3p_context_condition_grain_key(context))
        else:
            metric = metric_lookup["by_identity"].get((str(context.get("asset_kind") or ""), str(context.get("identity_key") or "")))
        adapted_metric = adapt_n3p_metric_row_for_rule_v4(metric, context_row=context) if metric else None
        if adapted_metric:
            context = context_with_formal_amount_unit_compat(context, adapted_metric)
        rule_plan = evaluate_v4_plan(
            context,
            adapted_metric,
            v4_run_id=f"n4p_ordinary_dry_run:{source_metric_run_id}",
        )
        plans.append(
            build_provisional_ordinary_plan(
                context=context,
                metric=metric or {},
                source_metric_run_id=source_metric_run_id,
                trigger_type=trigger_type,
                rule_plan=rule_plan,
            )
        )
    return plans


def latest_n3p_metric_lookup(
    metric_rows: Sequence[Mapping[str, Any]],
    *,
    source_metric_run_id: str,
) -> dict[str, Any]:
    by_identity = latest_n3p_metric_by_identity(metric_rows, source_metric_run_id=source_metric_run_id)
    by_condition_grain: dict[tuple[str, str, str, str, str, str], Mapping[str, Any]] = {}
    for row in sorted(metric_rows, key=lambda item: str(item.get("metric_time") or item.get("metric_time_label") or "")):
        if str(row.get("projection_run_id") or "") != source_metric_run_id:
            continue
        key = n3p_metric_condition_grain_key(row)
        if key is not None:
            by_condition_grain[key] = row
    return {
        "by_identity": by_identity,
        "by_condition_grain": by_condition_grain,
        "has_condition_grain": bool(by_condition_grain),
    }


def latest_n3p_metric_by_identity(
    metric_rows: Sequence[Mapping[str, Any]],
    *,
    source_metric_run_id: str,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    lookup: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in sorted(metric_rows, key=lambda item: str(item.get("metric_time") or item.get("metric_time_label") or "")):
        if str(row.get("projection_run_id") or "") != source_metric_run_id:
            continue
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        if key[0] and key[1]:
            lookup[key] = row
    return lookup


def n3p_context_condition_grain_key(context_row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(context_row.get("asset_kind") or ""),
        str(context_row.get("identity_key") or ""),
        str(context_row.get("direction") or ""),
        str(context_row.get("condition_key") or ""),
        str(context_row.get("source_condition_pool_id") or ""),
        str(context_row.get("source_minute_target_scope_id") or ""),
    )


def n3p_metric_condition_grain_key(metric_row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str] | None:
    condition_key = str(n3p_metric_lineage_value(metric_row, "condition_key") or "")
    pool_id = str(n3p_metric_lineage_value(metric_row, "source_condition_pool_id") or "")
    scope_id = str(n3p_metric_lineage_value(metric_row, "source_minute_target_scope_id") or "")
    if not condition_key or not pool_id or not scope_id:
        return None
    return (
        str(metric_row.get("asset_kind") or ""),
        str(metric_row.get("identity_key") or ""),
        n3p_metric_direction(metric_row, condition_key=condition_key),
        condition_key,
        pool_id,
        scope_id,
    )


def n3p_metric_lineage_value(metric_row: Mapping[str, Any], key: str) -> Any:
    raw_json = json_object(metric_row.get("raw_json"))
    trace_json = json_object(metric_row.get("trace_json"))
    source_fact_ids = json_object(metric_row.get("source_fact_ids"))
    higher_period_context = json_object(raw_json.get("higher_period_context_source")) or json_object(
        trace_json.get("higher_period_context_source")
    )
    b1_selection = json_object(raw_json.get("b1_source_returned_payload_selection")) or json_object(
        trace_json.get("b1_source_returned_payload_selection")
    )
    for container in (metric_row, source_fact_ids, raw_json, trace_json, higher_period_context, b1_selection):
        value = container.get(key) if isinstance(container, Mapping) else None
        if value is not None and value != "":
            return value
    return None


def n3p_metric_direction(metric_row: Mapping[str, Any], *, condition_key: str) -> str:
    signal_type = str(n3p_metric_lineage_value(metric_row, "signal_type") or "")
    if signal_type == "S_SELL" or condition_key.startswith("SELL"):
        return "sell"
    return "buy"


def adapt_n3p_metric_row_for_rule_v4(
    metric_row: Mapping[str, Any],
    *,
    context_row: Mapping[str, Any],
) -> dict[str, Any]:
    raw_json = json_object(metric_row.get("raw_json"))
    trace_json = json_object(metric_row.get("trace_json"))
    enrichment = json_object(raw_json.get("enrichment_v1"))
    formal_amount_proof = formal_period_amount_proof(metric_row)
    formal_metrics = formal_amount_chain_metrics(metric_row)
    formal_amount_unit, formal_amount_source_kind = trusted_formal_amount_unit_and_source(formal_amount_proof)
    trigger_amount_chain_pass = (
        metric_row.get("trigger_amount_chain_pass")
        or raw_json.get("trigger_amount_chain_pass")
        or enrichment.get("trigger_amount_chain_pass")
        or trigger_amount_chain_pass_from_formal_proof(metric_row, context_row=context_row)
        or trigger_amount_chain_pass_from_flags(metric_row, context_row=context_row)
    )
    result = {
        **enrichment,
        "projection_run_id": metric_row.get("projection_run_id"),
        "projection_schema_version": metric_row.get("projection_schema_version"),
        "projection_id": selected_metric_id(metric_row),
        "source_metric_kind": SOURCE_METRIC_KIND,
        "asset_kind": metric_row.get("asset_kind"),
        "identity_key": metric_row.get("identity_key"),
        "current_price_or_close": first_present(
            enrichment.get("current_price_or_close"),
            metric_row.get("current_price"),
        ),
        "current_amount_metric": first_present(
            enrichment.get("current_amount_metric"),
            metric_row.get("current_d_virtual_amount"),
            metric_row.get("current_1m_amount"),
        ),
        "today_virt_amount": first_present(
            enrichment.get("today_virt_amount"),
            formal_metrics.get("today_virt_amount"),
            metric_row.get("current_d_virtual_amount"),
            metric_row.get("current_1m_amount"),
        ),
        "weekly_avg_with_today": first_present(
            enrichment.get("weekly_avg_with_today"),
            metric_row.get("weekly_avg_with_today"),
            formal_metrics.get("weekly_avg_with_today"),
        ),
        "monthly_avg_with_today": first_present(
            enrichment.get("monthly_avg_with_today"),
            metric_row.get("monthly_avg_with_today"),
            formal_metrics.get("monthly_avg_with_today"),
        ),
        "quarterly_avg_with_today": first_present(
            enrichment.get("quarterly_avg_with_today"),
            metric_row.get("quarterly_avg_with_today"),
            formal_metrics.get("quarterly_avg_with_today"),
        ),
        "yearly_avg_with_today": first_present(
            enrichment.get("yearly_avg_with_today"),
            metric_row.get("yearly_avg_with_today"),
            formal_metrics.get("yearly_avg_with_today"),
        ),
        "current_amount_metric_unit": first_present(
            enrichment.get("current_amount_metric_unit"),
            metric_row.get("current_amount_metric_unit"),
            metric_row.get("amount_unit"),
            formal_amount_unit,
        ),
        "amount_unit": first_present(
            enrichment.get("amount_unit"),
            metric_row.get("amount_unit"),
            formal_amount_unit,
        ),
        "current_amount_metric_source_kind": first_present(
            enrichment.get("current_amount_metric_source_kind"),
            metric_row.get("current_amount_metric_source_kind"),
            formal_amount_source_kind,
        ),
        "current_metric_time": first_present(
            enrichment.get("current_metric_time"),
            metric_row.get("metric_time"),
            metric_row.get("metric_time_label"),
        ),
        "current_metric_quality_status": first_present(
            enrichment.get("current_metric_quality_status"),
            metric_row.get("metric_quality_status"),
            "passed" if metric_row.get("metric_ready") is True else None,
        ),
        "projection_period": first_present(enrichment.get("projection_period"), "realtime_action_confirmation_metric"),
        "projection_30m_flag": bool(enrichment.get("projection_30m_flag") or False),
        "projection_30m_type": str(enrichment.get("projection_30m_type") or "none"),
        "trigger_amount_chain_pass": dict(trigger_amount_chain_pass or {}),
        "projection_lineage_json": first_present(
            enrichment.get("projection_lineage_json"),
            trace_json,
            raw_json,
            {},
        ),
        "source_freshness_status": first_present(enrichment.get("source_freshness_status"), "passed"),
        "metric_ready": bool(metric_row.get("metric_ready")),
        "metric_quality_status": metric_row.get("metric_quality_status"),
        "quality_reason": metric_row.get("quality_reason"),
    }
    return result


def formal_period_amount_proof(metric_row: Mapping[str, Any]) -> dict[str, Any]:
    raw_json = json_object(metric_row.get("raw_json"))
    trace_json = json_object(metric_row.get("trace_json"))
    proof = (
        metric_row.get("formal_period_amount_proof")
        or raw_json.get("formal_period_amount_proof")
        or trace_json.get("formal_period_amount_proof")
    )
    return json_object(proof)


def formal_amount_chain_metrics(metric_row: Mapping[str, Any]) -> dict[str, Any]:
    raw_json = json_object(metric_row.get("raw_json"))
    trace_json = json_object(metric_row.get("trace_json"))
    proof = formal_period_amount_proof(metric_row)
    return (
        json_object(proof.get("amount_chain_metrics"))
        or json_object(metric_row.get("formal_amount_chain_metrics"))
        or json_object(raw_json.get("formal_amount_chain_metrics"))
        or json_object(trace_json.get("formal_amount_chain_metrics"))
    )


def trusted_formal_amount_unit_and_source(proof: Mapping[str, Any]) -> tuple[str | None, str | None]:
    if not proof:
        return None, None
    top_source = str(proof.get("source_kind") or "")
    top_unit = str(proof.get("amount_unit") or "")
    if top_source == FORMAL_AMOUNT_SOURCE_KIND and top_unit == FORMAL_AMOUNT_UNIT:
        return FORMAL_AMOUNT_UNIT, FORMAL_AMOUNT_SOURCE_KIND
    periods = json_object(proof.get("periods"))
    for period_proof in periods.values():
        period_proof = json_object(period_proof)
        source_kind = str(period_proof.get("current_amount_source_kind") or period_proof.get("source_kind") or "")
        unit = str(period_proof.get("current_amount_unit") or period_proof.get("amount_unit") or "")
        if source_kind == FORMAL_AMOUNT_SOURCE_KIND and unit == FORMAL_AMOUNT_UNIT:
            return FORMAL_AMOUNT_UNIT, FORMAL_AMOUNT_SOURCE_KIND
    return None, None


def trigger_amount_chain_pass_from_formal_proof(
    metric_row: Mapping[str, Any],
    *,
    context_row: Mapping[str, Any],
) -> dict[str, Any]:
    proof = formal_period_amount_proof(metric_row)
    unit, source_kind = trusted_formal_amount_unit_and_source(proof)
    if unit != FORMAL_AMOUNT_UNIT or source_kind != FORMAL_AMOUNT_SOURCE_KIND:
        return {}
    periods = requested_periods_for_condition(str(context_row.get("condition_key") or ""))
    if not periods:
        return {}
    formal_metric = {
        **dict(metric_row),
        "formal_period_amount_proof": proof,
        "formal_amount_chain_metrics": formal_amount_chain_metrics(metric_row),
    }
    direction = "sell" if str(context_row.get("condition_key") or "").startswith("SELL") else "buy"
    period_proofs = json_object(proof.get("periods"))
    chain: dict[str, bool] = {}
    for period in periods:
        period_proof = json_object(period_proofs.get(period))
        explicit = period_proof.get("trigger_amount_chain_pass")
        if explicit is None:
            explicit = period_proof.get("amount_pass")
        if period == "Y":
            chain[period] = "not_applicable"
            continue
        if isinstance(explicit, bool):
            chain[period] = explicit
            continue
        evaluated = evaluate_formal_amount_chain(metric=formal_metric, period=period, direction=direction)
        if evaluated.get("status") == "passed":
            chain_pass = trigger_amount_chain_pass_for_period(period, evaluated)
            if chain_pass is not None:
                chain[period] = bool(chain_pass)
    return chain


def requested_periods_for_condition(condition_key: str) -> list[str]:
    if condition_key in {"BUY:FULL", "SELL:FULL"}:
        return ["D"]
    if ":" not in condition_key:
        return ["D"]
    _, raw_periods = condition_key.split(":", 1)
    periods = [period.strip().upper() for period in raw_periods.split(",") if period.strip()]
    return [period for period in periods if period in {"Y", "Q", "M", "W", "D"}]


def context_with_formal_amount_unit_compat(
    context: Mapping[str, Any],
    adapted_metric: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        adapted_metric.get("current_amount_metric_unit") != FORMAL_AMOUNT_UNIT
        or adapted_metric.get("current_amount_metric_source_kind") != FORMAL_AMOUNT_SOURCE_KIND
    ):
        return dict(context)
    output = dict(context)
    baseline_json = json_object(output.get("period_trigger_baseline_json"))
    periods = json_object(baseline_json.get("periods"))
    if not periods:
        return output
    patched_periods: dict[str, Any] = {}
    for period, baseline in periods.items():
        baseline_dict = json_object(baseline)
        if not baseline_dict:
            patched_periods[str(period)] = baseline
            continue
        if not baseline_dict.get("trigger_previous_amount_baseline_unit"):
            baseline_dict["trigger_previous_amount_baseline_unit"] = FORMAL_AMOUNT_UNIT
        if not baseline_dict.get("amount_unit"):
            baseline_dict["amount_unit"] = FORMAL_AMOUNT_UNIT
        patched_periods[str(period)] = baseline_dict
    output["period_trigger_baseline_json"] = {**baseline_json, "periods": patched_periods}
    return output


def trigger_amount_chain_pass_from_flags(
    metric_row: Mapping[str, Any],
    *,
    context_row: Mapping[str, Any],
) -> dict[str, bool]:
    explicit = json_object(metric_row.get("trigger_amount_chain_pass"))
    if explicit:
        return {str(key): bool(value) for key, value in explicit.items()}
    raw_flags = json_object(metric_row.get("deterministic_pass_flags"))
    raw_json = json_object(metric_row.get("raw_json"))
    raw_flags = raw_flags or json_object(raw_json.get("deterministic_pass_flags"))
    if not raw_flags:
        return {}
    condition_key = str(context_row.get("condition_key") or "")
    direction = "sell" if condition_key.startswith("SELL") else "buy"
    period = "D" if condition_key in {"BUY:FULL", "SELL:FULL"} else (condition_key.split(":", 1)[1].split(",", 1)[0] if ":" in condition_key else "D")
    family_flags = raw_flags.get("S_SELL" if direction == "sell" else "B_BUY")
    if not isinstance(family_flags, Mapping):
        return {}
    amount_key = "sell_1m_amount_pass" if direction == "sell" else "buy_1m_amount_pass"
    price_key = "sell_1m_price_pass" if direction == "sell" else "buy_1m_price_pass"
    if amount_key in family_flags and price_key in family_flags:
        return {period: bool(family_flags.get(amount_key)) and bool(family_flags.get(price_key))}
    return {}


def build_provisional_ordinary_plan(
    *,
    context: Mapping[str, Any],
    metric: Mapping[str, Any],
    source_metric_run_id: str,
    trigger_type: str,
    rule_plan: Mapping[str, Any],
) -> dict[str, Any]:
    matched = rule_plan.get("output_event_type") == "TriggerMatched"
    selected_time = str(metric.get("metric_time") or metric.get("metric_time_label") or "")
    source_mode, c1_dependency = source_mode_and_c1_dependency(metric)
    signal_type = str(rule_plan.get("signal_type") or "")
    condition_key = str(context.get("condition_key") or "")
    identity_key = str(context.get("identity_key") or "")
    asset_kind = str(context.get("asset_kind") or "")
    candidate_key = candidate_trigger_identity_key(
        for_trade_date=str(context.get("for_trade_date") or metric.get("for_trade_date") or ""),
        asset_kind=asset_kind,
        identity_key=identity_key,
        signal_type=signal_type,
        condition_key=condition_key,
        trigger_type=trigger_type,
        selected_metric_time=selected_time,
        source_metric_run_id=source_metric_run_id,
    )
    output_event_type = "TriggerMatched" if matched else None
    return {
        "plan_id": stable_hash(candidate_key + "|" + str(output_event_type or "no_op"), length=32),
        "plan_status": "matched" if matched else "no_op",
        "output_event_type": output_event_type,
        "provisional": True,
        "source_metric_kind": SOURCE_METRIC_KIND,
        "source_metric_run_id": source_metric_run_id,
        "selected_metric_id": selected_metric_id(metric),
        "selected_metric_time": selected_time,
        "metric_time_label": metric.get("metric_time_label"),
        "metric_minute_label": metric.get("metric_minute_label"),
        "is_closed_1m": bool(metric.get("is_closed_1m")),
        "source_mode": source_mode,
        "c1_dependency": c1_dependency,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "display_name": metric.get("name") or context.get("name") or identity_key,
        "condition_key": condition_key,
        "signal_type": signal_type,
        "trigger_type": trigger_type,
        "trigger_mark_candidate": rule_plan.get("trigger_mark_candidate") or "normal",
        "trigger_period": rule_plan.get("trigger_period") if matched else None,
        "triggered_periods": list(rule_plan.get("triggered_periods") or []) if matched else [],
        "candidate_trigger_identity_key": candidate_key,
        "rule_eval_result": {
            "trigger_rule_spec_version": rule_plan.get("trigger_rule_spec_version"),
            "trigger_rule_policy_hash": rule_plan.get("trigger_rule_policy_hash"),
            "outcome_classification": rule_plan.get("outcome_classification"),
            "output_event_type": rule_plan.get("output_event_type"),
            "trigger_live": bool(rule_plan.get("trigger_live")),
            "triggered_periods": list(rule_plan.get("triggered_periods") or []),
            "pending_reasons": list(rule_plan.get("pending_reasons") or []),
            "quality_reasons": list(rule_plan.get("quality_reasons") or []),
            "blocked_reason": rule_plan.get("blocked_reason"),
        },
        "rule_proof": {
            "rule_reused": "ashare_v3.trigger.rule_v4_matcher.evaluate_v4_plan",
            "trigger_rule_spec_version": TRIGGER_RULE_SPEC_VERSION,
            "trigger_rule_policy_hash": TRIGGER_RULE_POLICY_HASH,
            "selected_metric": {
                "projection_run_id": metric.get("projection_run_id"),
                "selected_metric_id": selected_metric_id(metric),
                "selected_metric_time": selected_time,
                "metric_time_label": metric.get("metric_time_label"),
                "metric_minute_label": metric.get("metric_minute_label"),
                "is_closed_1m": bool(metric.get("is_closed_1m")),
                "metric_ready": bool(metric.get("metric_ready")),
            },
            "period_evaluation_details": list(rule_plan.get("period_evaluation_details") or []),
            "triggered_period_details": list(rule_plan.get("triggered_period_details") or []),
        },
        "trace": {
            "trigger_context_run_id": context.get("run_id"),
            "source_condition_run_id": context.get("source_condition_run_id"),
            "source_today_minute_run_id": metric.get("source_today_minute_run_id"),
            "source_previous_day_minute_run_id": metric.get("source_previous_day_minute_run_id"),
            "source_snapshot_run_id": metric.get("source_snapshot_run_id"),
            "source_mode": source_mode,
            "c1_dependency": c1_dependency,
        },
    }


def build_provisional_ordinary_matcher_dry_run_report(
    *,
    trigger_context_run_id: str,
    source_metric_run_id: str,
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    plans = build_provisional_ordinary_matcher_plans(
        trigger_context_run_id=trigger_context_run_id,
        source_metric_run_id=source_metric_run_id,
        context_rows=context_rows,
        metric_rows=metric_rows,
    )
    summary = summarize_provisional_ordinary_matcher_plans(plans)
    return {
        "stage": "N4P ordinary realtime-action metric matcher dry-run",
        "result": "DRY_RUN_PASS",
        "layer_role": "N4_trigger",
        "mode": "n4p_ordinary_matcher_dry_run",
        "trigger_context_run_id": trigger_context_run_id,
        "source_metric_kind": SOURCE_METRIC_KIND,
        "source_metric_run_id": source_metric_run_id,
        "matcher_contract": {
            "reads_n3p_realtime_action_confirmation_metric": True,
            "reads_b2_realtime_projection_metric": False,
            "handles_condition_signal_types": sorted(ORDINARY_CONDITION_SIGNAL_TYPES),
            "skips_condition_signal_types": sorted(HINT_CONDITION_KEYS),
            "rule_reuse": "ashare_v3.trigger.rule_v4_matcher.evaluate_v4_plan",
            "writes_database": False,
        },
        "summary": summary,
        "plans": plans,
        "side_effect_guard": dict(SIDE_EFFECT_GUARD),
    }


def summarize_provisional_ordinary_matcher_plans(plans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matched = [plan for plan in plans if plan.get("output_event_type") == "TriggerMatched"]
    noop = [plan for plan in plans if plan.get("output_event_type") is None]
    return {
        "candidate_count": len(plans),
        "matched_count": len(matched),
        "noop_count": len(noop),
        "matched_by_asset_kind": count_by(matched, "asset_kind"),
        "matched_by_signal_type": count_by(matched, "signal_type"),
        "matched_by_trigger_type": count_by(matched, "trigger_type"),
        "matched_by_trigger_mark_candidate": count_by(matched, "trigger_mark_candidate"),
        "output_event_types": count_by(plans, "output_event_type"),
        "unclosed_metric_count": sum(1 for plan in plans if plan.get("is_closed_1m") is False),
    }


def ordinary_trigger_type(condition_key: str) -> str:
    if condition_key == "BUY:FULL":
        return "BUY:FULL"
    if condition_key == "SELL:FULL":
        return "SELL:FULL"
    condition_signal_type = condition_signal_type_for_condition_key(condition_key)
    if condition_signal_type == "SELL":
        return "SELL"
    if condition_signal_type == "BUY":
        return "BUY"
    return condition_signal_type


def candidate_trigger_identity_key(
    *,
    for_trade_date: str,
    asset_kind: str,
    identity_key: str,
    signal_type: str,
    condition_key: str,
    trigger_type: str,
    selected_metric_time: str,
    source_metric_run_id: str,
) -> str:
    return "|".join(
        [
            for_trade_date,
            asset_kind,
            identity_key,
            signal_type,
            condition_key,
            trigger_type,
            selected_metric_time,
            source_metric_run_id,
        ]
    )


def selected_metric_id(metric: Mapping[str, Any]) -> Any:
    return metric.get("action_confirmation_metric_id") or metric.get("metric_id") or metric.get("projection_id")


def source_mode_and_c1_dependency(metric: Mapping[str, Any]) -> tuple[str | None, bool | None]:
    raw_json = json_object(metric.get("raw_json"))
    trace_json = json_object(metric.get("trace_json"))
    source_fact_ids = json_object(metric.get("source_fact_ids"))
    closed_proof = json_object(raw_json.get("closed_minute_proof")) or json_object(trace_json.get("closed_minute_proof"))
    source_mode = first_present(
        metric.get("source_mode"),
        source_fact_ids.get("source_mode"),
        trace_json.get("source_mode"),
        raw_json.get("source_mode"),
        closed_proof.get("source_mode"),
    )
    c1_dependency = first_present(
        metric.get("c1_dependency"),
        source_fact_ids.get("c1_dependency"),
        trace_json.get("c1_dependency"),
        raw_json.get("c1_dependency"),
        closed_proof.get("c1_dependency"),
    )
    return (str(source_mode) if source_mode else None, bool(c1_dependency) if c1_dependency is not None else None)


def json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))
