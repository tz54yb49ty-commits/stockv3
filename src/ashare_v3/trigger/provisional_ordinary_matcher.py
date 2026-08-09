"""N4P ordinary realtime-action metric matcher dry-run.

This module is plan-only. It adapts N3P realtime action-confirmation metric
rows into the existing N4 rule v4 matcher input shape, then emits provisional
TriggerMatched plans for ordinary BUY/SELL/FULL conditions without writing DB
rows or touching downstream layers.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from typing import Any, Mapping, Sequence

from ashare_v3.events.ids import stable_hash
from ashare_v3.trigger.action_confirmation_metric_matcher import (
    FORMAL_AMOUNT_SOURCE_KIND,
    FORMAL_AMOUNT_UNIT,
    decimal_json,
    evaluate_formal_amount_chain,
    formal_transition_previous_amount_value,
    trigger_amount_chain_pass_for_period,
)
from ashare_v3.trigger.projection_matcher import normalize_context_row
from ashare_v3.trigger.rule_v4_matcher import (
    CURRENT_PERIOD_AVG_FIELD_BY_PERIOD,
    LEGACY_PERIOD_ESCALATION_REPLAY_CONTEXT_RUN_IDS,
    OUTCOME_TO_EVENT_TYPE,
    ORDINARY_PERIOD_ESCALATION_POLICY_HASH,
    ORDINARY_PERIOD_ESCALATION_POLICY_VERSION,
    PERIOD_ESCALATION_CONTEXT_VERSION,
    PERIOD_ESCALATION_DIRECTION_TRANSITIONS,
    PERIOD_ESCALATION_INCREMENTAL_GENERATION_MODE,
    PERIOD_ESCALATION_REQUIREMENTS,
    TRIGGER_RULE_POLICY_HASH,
    TRIGGER_RULE_SPEC_VERSION,
    condition_signal_type_for_condition_key,
    evaluate_v4_plan,
)


SOURCE_METRIC_KIND = "realtime_action_confirmation_metric"
ORDINARY_CONDITION_SIGNAL_TYPES = {"BUY", "SELL", "BUY:FULL", "SELL:FULL"}
HINT_CONDITION_KEYS = {"BUY_HINT", "SELL_HINT"}
PERIOD_PRIORITY = ("Y", "Q", "M", "W", "D")
SAME_DAY_FORMAL_EVIDENCE_SOURCE = "current_same_day_formal_pass"
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
        canonical_value, _, normalization_trace = formal_transition_previous_amount_value(
            baseline_dict,
            str(period),
            asset_kind=str(output.get("asset_kind") or ""),
        )
        source_field = normalization_trace.get("source_field")
        baseline_dict["transition_previous_amount_normalization_trace"] = {
            **normalization_trace,
            "period": str(period),
            "canonical_value": decimal_json(canonical_value),
            "canonical_unit": FORMAL_AMOUNT_UNIT if canonical_value is not None else None,
        }
        if canonical_value is not None and source_field:
            baseline_dict[str(source_field)] = decimal_json(canonical_value)
            baseline_dict[f"{source_field}_unit"] = FORMAL_AMOUNT_UNIT
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
    assert_same_day_period_escalation_output_contract(
        rule_plan,
        contract_scope="raw_rule_plan",
    )
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
        "condition_projection_context": (
            context.get("condition_projection_context")
            if context.get("condition_projection_context") is not None
            else {}
        ),
        "condition_projection_context_status": context.get("condition_projection_context_status") or "not_ready",
        "condition_projection_context_trace": dict(context.get("condition_projection_context_trace") or {}),
        "condition_key": condition_key,
        "direction": rule_plan.get("direction"),
        "signal_type": signal_type,
        "trigger_type": trigger_type,
        "trigger_mark_candidate": rule_plan.get("trigger_mark_candidate") or "normal",
        "trigger_period": rule_plan.get("trigger_period") if matched else None,
        "triggered_periods": list(rule_plan.get("triggered_periods") or []),
        "all_trigger_periods": list(rule_plan.get("all_trigger_periods") or []),
        "primary_trigger_period": rule_plan.get("primary_trigger_period"),
        "prerequisite_periods": list(rule_plan.get("prerequisite_periods") or []),
        "period_escalation_trace": dict(rule_plan.get("period_escalation_trace") or {}),
        "ordinary_period_escalation_policy_version": rule_plan.get(
            "ordinary_period_escalation_policy_version"
        ),
        "ordinary_period_escalation_policy_hash": rule_plan.get(
            "ordinary_period_escalation_policy_hash"
        ),
        "candidate_trigger_identity_key": candidate_key,
        "rule_eval_result": {
            "trigger_rule_spec_version": rule_plan.get("trigger_rule_spec_version"),
            "trigger_rule_policy_hash": rule_plan.get("trigger_rule_policy_hash"),
            "outcome_classification": rule_plan.get("outcome_classification"),
            "output_event_type": rule_plan.get("output_event_type"),
            "trigger_live": bool(rule_plan.get("trigger_live")),
            "triggered_periods": list(rule_plan.get("triggered_periods") or []),
            "all_trigger_periods": list(rule_plan.get("all_trigger_periods") or []),
            "primary_trigger_period": rule_plan.get("primary_trigger_period"),
            "prerequisite_periods": list(rule_plan.get("prerequisite_periods") or []),
            "period_escalation_trace": dict(rule_plan.get("period_escalation_trace") or {}),
            "ordinary_period_escalation_policy_version": rule_plan.get(
                "ordinary_period_escalation_policy_version"
            ),
            "ordinary_period_escalation_policy_hash": rule_plan.get(
                "ordinary_period_escalation_policy_hash"
            ),
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
            "period_escalation_trace": dict(rule_plan.get("period_escalation_trace") or {}),
            "ordinary_period_escalation_policy_version": rule_plan.get(
                "ordinary_period_escalation_policy_version"
            ),
            "ordinary_period_escalation_policy_hash": rule_plan.get(
                "ordinary_period_escalation_policy_hash"
            ),
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


def assert_same_day_period_escalation_output_contract(
    rule_plan: Mapping[str, Any],
    *,
    contract_scope: str = "production_provisional",
) -> None:
    def fail(reason: str) -> None:
        raise ValueError(f"same-day period escalation output contract blocked: {reason}")

    def canonical_formal_detail_passes(
        candidate_direction: str,
        period: str,
        detail: Mapping[str, Any],
        *,
        require_effective_trigger: bool = True,
    ) -> bool:
        if candidate_direction not in PERIOD_ESCALATION_DIRECTION_TRANSITIONS:
            return False
        if period not in CURRENT_PERIOD_AVG_FIELD_BY_PERIOD:
            return False
        expected_transition = PERIOD_ESCALATION_DIRECTION_TRANSITIONS[candidate_direction]
        expected_amount_field = CURRENT_PERIOD_AVG_FIELD_BY_PERIOD[period]
        expected_chain_pass: bool | str = "not_applicable" if period == "Y" else True
        amount_unit_status = detail.get("amount_unit_status")
        amount_source_status = detail.get("amount_source_status")
        if (
            detail.get("period") != period
            or detail.get("current_transition") != expected_transition
            or detail.get("previous_transition") in {None, expected_transition}
            or detail.get("transition_amount_pass") is not True
            or detail.get("trigger_amount_chain_pass") != expected_chain_pass
            or detail.get("transition_amount_field") != expected_amount_field
            or detail.get("amount_metric") != expected_amount_field
            or detail.get("used_for_period") != period
            or detail.get("compare_to") != f"previous_avg_amount[{period}]"
            or detail.get("current_price_or_close") is None
            or detail.get("current_amount_metric") is None
            or detail.get("transition_amount_value") != detail.get("current_amount_metric")
            or detail.get("previous_amount_baseline") is None
            or detail.get("trigger_previous_entity_high") is None
            or detail.get("trigger_previous_entity_low") is None
            or not isinstance(amount_unit_status, Mapping)
            or amount_unit_status.get("status") != "matched"
            or not isinstance(amount_source_status, Mapping)
            or amount_source_status.get("status") != "matched"
        ):
            return False
        has_existing_formal_state = (
            "existing_formal_classification" in detail or "existing_formal_pass" in detail
        )
        if require_effective_trigger:
            if detail.get("classification") != "triggered" or detail.get("reason") is not None:
                return False
            if has_existing_formal_state and (
                detail.get("existing_formal_classification") != "triggered"
                or detail.get("existing_formal_pass") is not True
            ):
                return False
            if (
                "period_escalation_gate_pass" in detail
                and detail.get("period_escalation_gate_pass") is not True
            ):
                return False
        elif has_existing_formal_state:
            if (
                detail.get("existing_formal_classification") != "triggered"
                or detail.get("existing_formal_pass") is not True
            ):
                return False
        elif detail.get("classification") != "triggered" or detail.get("reason") is not None:
            return False
        return True

    if contract_scope not in {"raw_rule_plan", "production_provisional"}:
        fail("contract_scope_invalid")

    top_level_required_fields = {
        "condition_key",
        "direction",
        "signal_type",
        "output_event_type",
        "triggered_periods",
        "all_trigger_periods",
        "primary_trigger_period",
        "prerequisite_periods",
        "period_escalation_trace",
        "ordinary_period_escalation_policy_version",
        "ordinary_period_escalation_policy_hash",
    }
    rule_proof_required_fields = {
        "rule_reused",
        "trigger_rule_spec_version",
        "trigger_rule_policy_hash",
        "selected_metric",
        "period_evaluation_details",
        "triggered_period_details",
        "period_escalation_trace",
        "ordinary_period_escalation_policy_version",
        "ordinary_period_escalation_policy_hash",
    }
    rule_eval_required_fields = {
        "trigger_rule_spec_version",
        "trigger_rule_policy_hash",
        "outcome_classification",
        "output_event_type",
        "trigger_live",
        "triggered_periods",
        "all_trigger_periods",
        "primary_trigger_period",
        "prerequisite_periods",
        "period_escalation_trace",
        "ordinary_period_escalation_policy_version",
        "ordinary_period_escalation_policy_hash",
        "pending_reasons",
        "quality_reasons",
        "blocked_reason",
    }
    top_level_trace_fields = {
        "policy_version",
        "policy_hash",
        "context_contract_version",
        "context_hash",
        "direction",
        "legacy_replay",
        "same_day_formal_evidence",
        "periods",
    }

    def require_fields(source_name: str, source: Mapping[str, Any], manifest: set[str]) -> None:
        missing = sorted(manifest - set(source))
        if missing:
            fail(f"source_required_fields_missing:{source_name}:{','.join(missing)}")

    raw_rule_proof = rule_plan.get("rule_proof")
    raw_rule_eval_result = rule_plan.get("rule_eval_result")
    if contract_scope == "production_provisional":
        require_fields("top_level", rule_plan, top_level_required_fields)
        if not isinstance(raw_rule_proof, Mapping) or not raw_rule_proof:
            fail("rule_proof_missing_empty_or_not_mapping")
        if not isinstance(raw_rule_eval_result, Mapping) or not raw_rule_eval_result:
            fail("rule_eval_result_missing_empty_or_not_mapping")
        require_fields("rule_proof", raw_rule_proof, rule_proof_required_fields)
        require_fields("rule_eval_result", raw_rule_eval_result, rule_eval_required_fields)
    else:
        if "rule_proof" in rule_plan:
            if not isinstance(raw_rule_proof, Mapping) or not raw_rule_proof:
                fail("rule_proof_missing_empty_or_not_mapping")
            require_fields("rule_proof", raw_rule_proof, rule_proof_required_fields)
        if "rule_eval_result" in rule_plan:
            if not isinstance(raw_rule_eval_result, Mapping) or not raw_rule_eval_result:
                fail("rule_eval_result_missing_empty_or_not_mapping")
            require_fields("rule_eval_result", raw_rule_eval_result, rule_eval_required_fields)

    rule_proof = raw_rule_proof if isinstance(raw_rule_proof, Mapping) else {}
    rule_eval_result = raw_rule_eval_result if isinstance(raw_rule_eval_result, Mapping) else {}
    sources = (
        ("top_level", rule_plan),
        ("rule_proof", rule_proof),
        ("rule_eval_result", rule_eval_result),
    )

    def source_has_same_day_marker(value: Any) -> bool:
        if not isinstance(value, Mapping):
            return False
        candidate_trace = value.get("period_escalation_trace")
        if isinstance(candidate_trace, Mapping):
            if candidate_trace.get("same_day_formal_evidence") is True:
                return True
            candidate_periods = candidate_trace.get("periods")
            if isinstance(candidate_periods, Mapping) and any(
                isinstance(period_trace, Mapping)
                and period_trace.get("evidence_source") == SAME_DAY_FORMAL_EVIDENCE_SOURCE
                for period_trace in candidate_periods.values()
            ):
                return True
        for detail_field in ("triggered_period_details", "period_evaluation_details"):
            details = value.get(detail_field)
            if isinstance(details, list) and any(
                isinstance(detail, Mapping)
                and isinstance(detail.get("period_escalation_trace"), Mapping)
                and detail["period_escalation_trace"].get("evidence_source")
                == SAME_DAY_FORMAL_EVIDENCE_SOURCE
                for detail in details
            ):
                return True
        return False

    def source_has_same_day_candidate_shape(value: Any) -> bool:
        if not isinstance(value, Mapping):
            return False
        all_trigger_periods = value.get("all_trigger_periods")
        if isinstance(all_trigger_periods, list):
            all_period_set = {str(period or "") for period in all_trigger_periods}
            if any(
                target_period in all_period_set
                and requirement["prerequisite_period"] in all_period_set
                for target_period, requirement in PERIOD_ESCALATION_REQUIREMENTS.items()
            ):
                return True
        candidate_trace = value.get("period_escalation_trace")
        if isinstance(candidate_trace, Mapping):
            if candidate_trace.get("legacy_replay") is True:
                return True
            trace_periods = candidate_trace.get("periods")
            if isinstance(trace_periods, Mapping) and any(
                isinstance(period_trace, Mapping)
                and "current_formal_pass_periods" in period_trace
                for period_trace in trace_periods.values()
            ):
                return True
        return False

    source_candidates = tuple(value for _, value in sources)
    candidate_identified = any(
        source_has_same_day_marker(value) or source_has_same_day_candidate_shape(value)
        for value in source_candidates
    )

    def is_exact_raw_legacy_input() -> bool:
        if contract_scope != "raw_rule_plan" or rule_proof or rule_eval_result:
            return False
        context_run_id = str(rule_plan.get("context_run_id") or "")
        if context_run_id not in LEGACY_PERIOD_ESCALATION_REPLAY_CONTEXT_RUN_IDS:
            return False
        raw_trace = rule_plan.get("period_escalation_trace")
        if not isinstance(raw_trace, Mapping) or set(raw_trace) != top_level_trace_fields:
            return False
        if (
            raw_trace.get("policy_version") != ORDINARY_PERIOD_ESCALATION_POLICY_VERSION
            or raw_trace.get("policy_hash") != ORDINARY_PERIOD_ESCALATION_POLICY_HASH
            or raw_trace.get("context_contract_version") is not None
            or raw_trace.get("context_hash") is not None
            or raw_trace.get("direction") != rule_plan.get("direction")
            or raw_trace.get("legacy_replay") is not True
            or raw_trace.get("same_day_formal_evidence") is not False
        ):
            return False
        legacy_trace_fields = {
            "policy_version",
            "policy_hash",
            "target_period",
            "prerequisite_period",
            "direction",
            "expected_window_kind",
            "expected_window_key",
            "expected_required_transition",
            "context_contract_version",
            "context_generation_mode",
            "context_hash",
            "evidence_source",
            "gate_pass",
            "evidence_ready",
            "gate_status",
            "legacy_context_run_id",
            "reason",
        }
        raw_periods = raw_trace.get("periods")
        if not isinstance(raw_periods, Mapping) or not raw_periods:
            return False
        for period, period_trace in raw_periods.items():
            if period not in PERIOD_ESCALATION_REQUIREMENTS or not isinstance(period_trace, Mapping):
                return False
            requirement = PERIOD_ESCALATION_REQUIREMENTS[period]
            if set(period_trace) != legacy_trace_fields or (
                period_trace.get("policy_version") != ORDINARY_PERIOD_ESCALATION_POLICY_VERSION
                or period_trace.get("policy_hash") != ORDINARY_PERIOD_ESCALATION_POLICY_HASH
                or period_trace.get("target_period") != period
                or period_trace.get("prerequisite_period") != requirement["prerequisite_period"]
                or period_trace.get("direction") != rule_plan.get("direction")
                or period_trace.get("expected_window_kind") != requirement["window_kind"]
                or period_trace.get("expected_required_transition")
                != PERIOD_ESCALATION_DIRECTION_TRANSITIONS.get(str(rule_plan.get("direction") or ""))
                or period_trace.get("context_contract_version") is not None
                or period_trace.get("context_generation_mode") is not None
                or period_trace.get("context_hash") is not None
                or period_trace.get("evidence_source") != "n2_period_escalation_context"
                or period_trace.get("gate_status") != "legacy_replay"
                or period_trace.get("gate_pass") is not True
                or period_trace.get("evidence_ready") is not True
                or period_trace.get("legacy_context_run_id") != context_run_id
                or period_trace.get("reason") != "frozen_legacy_period_rule_replay"
            ):
                return False
        return True

    if candidate_identified and is_exact_raw_legacy_input():
        return

    if "output_event_type" in rule_proof:
        fail("rule_proof_output_event_type_forbidden")

    raw_event_source = rule_eval_result if rule_eval_result else rule_plan
    raw_outcome = raw_event_source.get("outcome_classification")
    if raw_outcome not in OUTCOME_TO_EVENT_TYPE:
        fail("raw_outcome_classification_invalid")
    raw_output_event_type = raw_event_source.get("output_event_type")
    if raw_output_event_type != OUTCOME_TO_EVENT_TYPE[raw_outcome]:
        fail("rule_eval_result_output_event_type_conflicting_with_raw_outcome")

    lifecycle_required_fields = {
        "lifecycle_state_key",
        "lifecycle_state_key_version",
        "previous_current_status",
        "previous_status",
        "current_status",
        "lifecycle_output_reason",
        "state_change_reason",
        "writes_trigger_match",
        "n5_entry_allowed",
        "is_n5_action_entry",
        "trigger_live",
    }
    lifecycle_annotated = any(
        field in rule_plan
        for field in {
            "lifecycle_state_key",
            "lifecycle_state_key_version",
            "lifecycle_output_reason",
        }
    )
    if lifecycle_annotated:
        missing_lifecycle_fields = sorted(lifecycle_required_fields - set(rule_plan))
        if missing_lifecycle_fields:
            fail(f"lifecycle_fields_missing:{','.join(missing_lifecycle_fields)}")
        if (
            rule_plan.get("lifecycle_state_key_version")
            != "n4p_provisional_trigger_lifecycle_v1"
            or not isinstance(rule_plan.get("lifecycle_state_key"), str)
            or not rule_plan.get("lifecycle_state_key")
            or rule_plan.get("previous_current_status") != rule_plan.get("previous_status")
        ):
            fail("lifecycle_identity_or_previous_status_invalid")

        final_event_type = rule_plan.get("output_event_type")
        current_status = rule_plan.get("current_status")
        previous_status_value = rule_plan.get("previous_status")
        lifecycle_reason = rule_plan.get("lifecycle_output_reason")
        if lifecycle_reason == "inactive_to_matched":
            lifecycle_event_valid = (
                final_event_type == "TriggerMatched"
                and current_status == "matched"
                and previous_status_value in {"inactive", "pending_market_data"}
            )
        elif lifecycle_reason == "matched_changed":
            lifecycle_event_valid = (
                final_event_type == "TriggerStateChanged"
                and current_status == "matched"
                and previous_status_value == "matched"
            )
        elif lifecycle_reason == "matched_to_inactive":
            lifecycle_event_valid = (
                final_event_type == "TriggerStateChanged"
                and current_status == "inactive"
                and previous_status_value == "matched"
            )
        elif lifecycle_reason == "pending_market_data":
            lifecycle_event_valid = (
                final_event_type == "TriggerPendingMarketData"
                and current_status == "pending_market_data"
            )
        else:
            lifecycle_event_valid = False
        expected_state_change_reason = (
            "deactivated" if lifecycle_reason == "matched_to_inactive" else lifecycle_reason
        )
        final_enters_n5 = final_event_type == "TriggerMatched"
        if (
            not lifecycle_event_valid
            or rule_plan.get("state_change_reason") != expected_state_change_reason
            or rule_plan.get("trigger_live") is not (current_status == "matched")
            or rule_plan.get("writes_trigger_match") is not final_enters_n5
            or rule_plan.get("n5_entry_allowed") is not final_enters_n5
            or rule_plan.get("is_n5_action_entry") is not final_enters_n5
        ):
            fail("top_level_output_event_type_conflicting_with_lifecycle")

    if not candidate_identified:
        return

    require_fields("top_level", rule_plan, top_level_required_fields)
    if contract_scope == "raw_rule_plan":
        require_fields(
            "top_level",
            rule_plan,
            {"period_evaluation_details", "triggered_period_details"},
        )

    for source_index, (source_name, source) in enumerate(sources):
        for other_name, other_source in sources[source_index + 1 :]:
            for field in set(source) & set(other_source):
                if lifecycle_annotated and field == "output_event_type":
                    continue
                if source[field] != other_source[field]:
                    fail(f"source_field_conflicting:{source_name}:{other_name}:{field}")

    top_level_trace = rule_plan.get("period_escalation_trace")
    if not isinstance(top_level_trace, Mapping):
        fail("period_escalation_trace_missing")
    trace = top_level_trace
    raw_rule_plan_audit_compatibility = (
        contract_scope == "raw_rule_plan"
        and not rule_proof
        and not rule_eval_result
        and trace.get("audit_note") == "dedup_must_ignore_optional_trace"
    )
    accepted_top_level_trace_fields = set(top_level_trace_fields)
    if raw_rule_plan_audit_compatibility:
        accepted_top_level_trace_fields.add("audit_note")
    if set(trace) != accepted_top_level_trace_fields:
        fail("top_level_trace_fields_conflicting")
    if trace.get("legacy_replay") is not False:
        fail("top_level_trace_legacy_replay_conflicting")
    raw_period_traces = trace.get("periods")
    if not isinstance(raw_period_traces, Mapping):
        fail("period_escalation_trace_periods_not_mapping")
    period_traces: dict[str, Mapping[str, Any]] = {}
    for raw_period, period_trace in raw_period_traces.items():
        if not isinstance(raw_period, str) or raw_period not in PERIOD_ESCALATION_REQUIREMENTS:
            fail("period_escalation_trace_period_invalid")
        if not isinstance(period_trace, Mapping):
            fail("period_escalation_trace_entry_not_mapping")
        period_traces[raw_period] = period_trace
    same_day_targets = {
        period
        for period, period_trace in period_traces.items()
        if period_trace.get("evidence_source") == SAME_DAY_FORMAL_EVIDENCE_SOURCE
    }
    if trace.get("same_day_formal_evidence") is not True or not same_day_targets:
        fail("same_day_trace_entries_missing")
    if rule_plan.get("ordinary_period_escalation_policy_version") != ORDINARY_PERIOD_ESCALATION_POLICY_VERSION:
        fail("policy_version_missing_or_conflicting")
    if rule_plan.get("ordinary_period_escalation_policy_hash") != ORDINARY_PERIOD_ESCALATION_POLICY_HASH:
        fail("policy_hash_missing_or_conflicting")
    if trace.get("policy_version") != ORDINARY_PERIOD_ESCALATION_POLICY_VERSION:
        fail("trace_policy_version_missing_or_conflicting")
    if trace.get("policy_hash") != ORDINARY_PERIOD_ESCALATION_POLICY_HASH:
        fail("trace_policy_hash_missing_or_conflicting")

    required_lists: dict[str, list[str]] = {}
    for field in ("triggered_periods", "all_trigger_periods", "prerequisite_periods"):
        value = rule_plan.get(field)
        if not isinstance(value, list) or not value:
            fail(f"{field}_missing")
        periods = [str(period) for period in value]
        if periods != [period for period in PERIOD_PRIORITY if period in set(periods)]:
            fail(f"{field}_order_or_value_invalid")
        required_lists[field] = periods

    triggered_periods = required_lists["triggered_periods"]
    all_trigger_periods = required_lists["all_trigger_periods"]
    prerequisite_periods = required_lists["prerequisite_periods"]
    primary_trigger_period = str(rule_plan.get("primary_trigger_period") or "")
    if primary_trigger_period != triggered_periods[0]:
        fail("primary_trigger_period_conflicting")

    direction = str(rule_plan.get("direction") or "")
    if direction not in {"buy", "sell"} or trace.get("direction") != direction:
        fail("direction_missing_or_conflicting")

    def source_value(field: str) -> Any:
        for _, source in sources:
            if field in source:
                return source[field]
        fail(f"{field}_missing")

    triggered_details = source_value("triggered_period_details")
    period_evaluation_details = source_value("period_evaluation_details")
    if not isinstance(triggered_details, list):
        fail("triggered_period_details_not_list")
    if not isinstance(period_evaluation_details, list):
        fail("period_evaluation_details_not_list")

    def index_details(
        details: list[Any],
        *,
        invalid_reason: str,
        duplicate_reason: str,
    ) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
        ordered_periods: list[str] = []
        indexed: dict[str, Mapping[str, Any]] = {}
        for detail in details:
            if not isinstance(detail, Mapping):
                fail(invalid_reason)
            period = detail.get("period")
            if not isinstance(period, str) or period not in PERIOD_PRIORITY:
                fail(invalid_reason)
            if period in indexed:
                fail(duplicate_reason)
            ordered_periods.append(period)
            indexed[period] = detail
        return ordered_periods, indexed

    triggered_detail_periods, triggered_details_by_period = index_details(
        triggered_details,
        invalid_reason="triggered_period_detail_invalid",
        duplicate_reason="triggered_period_details_duplicate",
    )
    evaluation_detail_periods, evaluation_details_by_period = index_details(
        period_evaluation_details,
        invalid_reason="period_evaluation_detail_invalid",
        duplicate_reason="period_evaluation_details_duplicate",
    )
    if triggered_detail_periods != triggered_periods:
        fail("triggered_period_details_order_or_scope_conflicting")
    for period, detail in triggered_details_by_period.items():
        if detail.get("classification") != "triggered":
            fail("triggered_period_detail_classification_conflicting")
        if dict(detail) != dict(evaluation_details_by_period.get(period) or {}):
            fail("triggered_period_detail_evaluation_conflicting")

    condition_key = str(rule_plan.get("condition_key") or "")
    expected_prefix = "BUY" if direction == "buy" else "SELL"
    if not condition_key.startswith(f"{expected_prefix}:"):
        fail("condition_key_direction_or_periods_invalid")
    raw_condition_periods = [period.strip() for period in condition_key.split(":", 1)[1].split(",")]
    if (
        not raw_condition_periods
        or any(period not in PERIOD_PRIORITY for period in raw_condition_periods)
        or len(raw_condition_periods) != len(set(raw_condition_periods))
        or raw_condition_periods
        != [period for period in PERIOD_PRIORITY if period in set(raw_condition_periods)]
    ):
        fail("condition_key_direction_or_periods_invalid")
    if evaluation_detail_periods != raw_condition_periods:
        fail("period_evaluation_details_order_or_scope_conflicting")

    canonical_formal_periods = [
        period
        for period in evaluation_detail_periods
        if canonical_formal_detail_passes(
            direction,
            period,
            evaluation_details_by_period[period],
            require_effective_trigger=False,
        )
    ]

    evaluation_trace_periods: dict[str, Mapping[str, Any]] = {}
    for period, detail in evaluation_details_by_period.items():
        if "period_escalation_trace" not in detail:
            continue
        detail_trace = detail.get("period_escalation_trace")
        if not isinstance(detail_trace, Mapping):
            fail("period_evaluation_trace_not_mapping")
        evaluation_trace_periods[period] = detail_trace
    if set(period_traces) != set(evaluation_trace_periods):
        fail("period_escalation_trace_scope_conflicting")
    for period, period_trace in period_traces.items():
        if dict(period_trace) != dict(evaluation_trace_periods[period]):
            fail("period_escalation_trace_evaluation_conflicting")

    same_day_prerequisite_by_target: dict[str, str] = {}
    formal_pass_period_sets: set[tuple[str, ...]] = set()
    same_day_trace_fields = {
        "policy_version",
        "policy_hash",
        "target_period",
        "prerequisite_period",
        "direction",
        "expected_window_kind",
        "expected_required_transition",
        "context_contract_version",
        "context_hash",
        "evidence_source",
        "current_formal_pass_periods",
        "gate_status",
        "gate_pass",
        "evidence_ready",
        "reason",
    }
    n2_context_trace_fields = {
        "policy_version",
        "policy_hash",
        "target_period",
        "prerequisite_period",
        "direction",
        "expected_window_kind",
        "expected_window_key",
        "expected_required_transition",
        "context_contract_version",
        "context_generation_mode",
        "context_hash",
        "evidence_source",
        "gate_pass",
        "evidence_ready",
        "source_entry",
        "status",
        "coverage_status",
        "seen",
        "gate_status",
        "reason",
    }
    n2_source_entry_fields = {
        "target_period",
        "prerequisite_period",
        "window_kind",
        "window_key",
        "window_start",
        "required_transition",
        "reset_for_trade_date",
        "state_epoch_trade_date",
        "observation_end",
        "expected_source_trade_date_count",
        "observed_source_trade_date_count",
        "missing_source_trade_dates",
        "observation_count",
        "previous_incremental_state_used",
        "first_source_trade_date",
        "last_source_trade_date",
        "status",
        "coverage_status",
        "seen",
        "latest_source_basis_ref",
        "latest_source_condition_run_id",
        "entry_hash",
    }

    def n2_context_trace_is_valid(period: str, period_trace: Mapping[str, Any]) -> bool:
        requirement = PERIOD_ESCALATION_REQUIREMENTS[period]
        source_entry = period_trace.get("source_entry")
        if set(period_trace) != n2_context_trace_fields or not isinstance(source_entry, Mapping):
            return False
        if set(source_entry) != n2_source_entry_fields:
            return False
        generation_mode = period_trace.get("context_generation_mode")
        if generation_mode not in {None, PERIOD_ESCALATION_INCREMENTAL_GENERATION_MODE}:
            return False
        if (
            period_trace.get("policy_version") != ORDINARY_PERIOD_ESCALATION_POLICY_VERSION
            or period_trace.get("policy_hash") != ORDINARY_PERIOD_ESCALATION_POLICY_HASH
            or period_trace.get("target_period") != period
            or period_trace.get("prerequisite_period") != requirement["prerequisite_period"]
            or period_trace.get("direction") != direction
            or period_trace.get("expected_window_kind") != requirement["window_kind"]
            or period_trace.get("expected_required_transition")
            != PERIOD_ESCALATION_DIRECTION_TRANSITIONS[direction]
            or period_trace.get("context_contract_version") != PERIOD_ESCALATION_CONTEXT_VERSION
            or not isinstance(period_trace.get("context_hash"), str)
            or not period_trace.get("context_hash")
            or trace.get("context_contract_version") != period_trace.get("context_contract_version")
            or trace.get("context_hash") != period_trace.get("context_hash")
            or period_trace.get("evidence_source") != "n2_period_escalation_context"
        ):
            return False
        if (
            source_entry.get("target_period") != period
            or source_entry.get("prerequisite_period") != requirement["prerequisite_period"]
            or source_entry.get("window_kind") != requirement["window_kind"]
            or source_entry.get("window_key") != period_trace.get("expected_window_key")
            or source_entry.get("required_transition") != PERIOD_ESCALATION_DIRECTION_TRANSITIONS[direction]
            or period_trace.get("status") != source_entry.get("status")
            or source_entry.get("coverage_status") != period_trace.get("coverage_status")
            or period_trace.get("seen") is not source_entry.get("seen")
            or not isinstance(source_entry.get("reset_for_trade_date"), bool)
        ):
            return False
        expected_count = source_entry.get("expected_source_trade_date_count")
        observed_count = source_entry.get("observed_source_trade_date_count")
        observation_count = source_entry.get("observation_count")
        previous_incremental_state_used = source_entry.get("previous_incremental_state_used")
        missing_dates = source_entry.get("missing_source_trade_dates")
        if (
            not isinstance(expected_count, int)
            or isinstance(expected_count, bool)
            or not isinstance(observed_count, int)
            or isinstance(observed_count, bool)
            or not isinstance(observation_count, int)
            or isinstance(observation_count, bool)
            or type(previous_incremental_state_used) is not bool
            or not isinstance(missing_dates, list)
            or expected_count < 0
            or observed_count < 0
            or observation_count < 0
            or observation_count > observed_count
            or observed_count + len(missing_dates) != expected_count
            or previous_incremental_state_used != (observed_count > 1)
            or any(
                not isinstance(value, str) or len(value) != 8 or not value.isdigit()
                for value in missing_dates
            )
        ):
            return False
        expected_entry_hash = str(source_entry.get("entry_hash") or "")
        entry_payload = dict(source_entry)
        entry_payload.pop("entry_hash", None)
        actual_entry_hash = stable_hash(
            json.dumps(
                entry_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ),
            length=64,
        )
        if expected_entry_hash != actual_entry_hash:
            return False

        status = source_entry.get("status")
        coverage_status = source_entry.get("coverage_status")
        seen = source_entry.get("seen")
        reset_for_trade_date = source_entry.get("reset_for_trade_date")
        first_source_trade_date = source_entry.get("first_source_trade_date")
        last_source_trade_date = source_entry.get("last_source_trade_date")

        def is_trade_date(value: Any) -> bool:
            return isinstance(value, str) and len(value) == 8 and value.isdigit()

        def parse_trade_date(value: Any) -> date | None:
            if not is_trade_date(value):
                return None
            try:
                return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
            except ValueError:
                return None

        def period_key_for_day(candidate_period: str, value: date) -> str:
            if candidate_period == "Y":
                return f"{value.year:04d}"
            if candidate_period == "Q":
                return f"{value.year:04d}Q{((value.month - 1) // 3) + 1}"
            if candidate_period == "M":
                return f"{value.year:04d}{value.month:02d}"
            iso_year, iso_week, _ = value.isocalendar()
            return f"{iso_year:04d}W{iso_week:02d}"

        window_start = parse_trade_date(source_entry.get("window_start"))
        observation_end = parse_trade_date(source_entry.get("observation_end"))
        state_epoch_trade_date = parse_trade_date(source_entry.get("state_epoch_trade_date"))
        parsed_missing_dates = [parse_trade_date(value) for value in missing_dates]
        if window_start is None or observation_end is None:
            return False
        if (
            (period == "Y" and (window_start.month, window_start.day) != (1, 1))
            or (period == "Q" and (window_start.month not in {1, 4, 7, 10} or window_start.day != 1))
            or (period == "M" and window_start.day != 1)
            or (period == "W" and window_start.isoweekday() != 1)
            or period_key_for_day(period, window_start) != period_trace.get("expected_window_key")
            or (not reset_for_trade_date and period_key_for_day(period, observation_end) != period_trace.get("expected_window_key"))
            or (reset_for_trade_date and observation_end >= window_start)
            or (not reset_for_trade_date and observation_end < window_start)
            or any(value is None for value in parsed_missing_dates)
            or missing_dates != sorted(set(missing_dates))
            or any(
                value is not None and not (window_start <= value <= observation_end)
                for value in parsed_missing_dates
            )
        ):
            return False
        if observed_count == 0:
            if source_entry.get("state_epoch_trade_date") is not None:
                return False
        elif (
            state_epoch_trade_date is None
            or not (window_start <= state_epoch_trade_date <= observation_end)
            or source_entry.get("state_epoch_trade_date") in missing_dates
            or (
                previous_incremental_state_used is False
                and state_epoch_trade_date != observation_end
            )
        ):
            return False

        if status == "ready":
            coverage_valid = (
                coverage_status == "passed"
                and not missing_dates
                and observed_count == expected_count
            ) or (
                generation_mode == PERIOD_ESCALATION_INCREMENTAL_GENERATION_MODE
                and coverage_status == "incomplete"
                and bool(missing_dates)
                and observed_count < expected_count
                and len(set(missing_dates)) == len(missing_dates)
                and len(missing_dates) == expected_count - observed_count
            )
            first_source_date = parse_trade_date(first_source_trade_date)
            last_source_date = parse_trade_date(last_source_trade_date)
            latest_source_basis_ref = source_entry.get("latest_source_basis_ref")
            return (
                coverage_valid
                and seen is True
                and observation_count >= 1
                and first_source_date is not None
                and last_source_date is not None
                and state_epoch_trade_date is not None
                and state_epoch_trade_date <= first_source_date <= last_source_date <= observation_end
                and first_source_trade_date not in missing_dates
                and last_source_trade_date not in missing_dates
                and isinstance(latest_source_basis_ref, str)
                and latest_source_basis_ref.endswith(f":{last_source_trade_date}")
                and (
                    source_entry.get("latest_source_condition_run_id") is None
                    or isinstance(source_entry.get("latest_source_condition_run_id"), str)
                )
                and period_trace.get("gate_status") == "passed"
                and period_trace.get("gate_pass") is True
                and period_trace.get("evidence_ready") is True
                and period_trace.get("reason") is None
            )

        if status == "not_seen":
            expected_coverage = "not_applicable" if reset_for_trade_date else "passed"
            return (
                coverage_status == expected_coverage
                and seen is False
                and not missing_dates
                and observed_count == expected_count
                and observation_count == 0
                and first_source_trade_date is None
                and last_source_trade_date is None
                and (
                    not reset_for_trade_date
                    or (expected_count == 0 and observed_count == 0)
                )
                and period_trace.get("gate_status") == "not_seen"
                and period_trace.get("gate_pass") is False
                and period_trace.get("evidence_ready") is True
                and period_trace.get("reason")
                == f"period_escalation_prerequisite_not_seen:{period}"
            )

        if status == "not_ready":
            return (
                coverage_status == "incomplete"
                and seen is False
                and bool(missing_dates)
                and observed_count < expected_count
                and len(set(missing_dates)) == len(missing_dates)
                and len(missing_dates) == expected_count - observed_count
                and observation_count == 0
                and first_source_trade_date is None
                and last_source_trade_date is None
                and source_entry.get("latest_source_basis_ref") is None
                and source_entry.get("latest_source_condition_run_id") is None
                and period_trace.get("gate_status") == "not_ready"
                and period_trace.get("gate_pass") is False
                and period_trace.get("evidence_ready") is False
                and period_trace.get("reason")
                == f"period_escalation_prerequisite_not_ready:{period}"
            )

        return False

    def n2_context_trace_is_complete(period: str, period_trace: Mapping[str, Any]) -> bool:
        return (
            n2_context_trace_is_valid(period, period_trace)
            and period_trace.get("status") == "ready"
        )

    n2_context_identities: set[tuple[str, str]] = set()
    for period, period_trace in period_traces.items():
        evidence_source = period_trace.get("evidence_source")
        if evidence_source == SAME_DAY_FORMAL_EVIDENCE_SOURCE:
            continue
        # A valid negative trace on an untriggered higher period is audit data;
        # it must not suppress a lower period that already satisfied its rule.
        if evidence_source != "n2_period_escalation_context" or not n2_context_trace_is_valid(
            period,
            period_trace,
        ):
            fail("non_same_day_period_trace_proof_invalid")
        n2_context_identities.add(
            (
                str(period_trace.get("context_contract_version") or ""),
                str(period_trace.get("context_hash") or ""),
            )
        )
    if len(n2_context_identities) > 1:
        fail("top_level_trace_context_conflicting")
    expected_top_context = next(iter(n2_context_identities), ("", ""))
    actual_top_context = (
        str(trace.get("context_contract_version") or ""),
        str(trace.get("context_hash") or ""),
    )
    if actual_top_context != expected_top_context:
        fail("top_level_trace_context_conflicting")

    for target_period in same_day_targets:
        if target_period not in PERIOD_ESCALATION_REQUIREMENTS:
            fail("same_day_target_invalid")
        requirement = PERIOD_ESCALATION_REQUIREMENTS[target_period]
        expected_prerequisite = requirement["prerequisite_period"]
        same_day_prerequisite_by_target[target_period] = expected_prerequisite
        period_trace = period_traces[target_period]
        if set(period_trace) != same_day_trace_fields:
            fail("same_day_trace_fields_conflicting")
        if period_trace.get("policy_version") != ORDINARY_PERIOD_ESCALATION_POLICY_VERSION:
            fail("same_day_trace_policy_version_conflicting")
        if period_trace.get("policy_hash") != ORDINARY_PERIOD_ESCALATION_POLICY_HASH:
            fail("same_day_trace_policy_hash_conflicting")
        if period_trace.get("direction") != direction:
            fail("same_day_trace_direction_conflicting")
        if period_trace.get("target_period") != target_period:
            fail("same_day_trace_target_conflicting")
        if period_trace.get("prerequisite_period") != expected_prerequisite:
            fail("same_day_prerequisite_conflicting")
        if period_trace.get("expected_window_kind") != requirement["window_kind"]:
            fail("same_day_trace_window_conflicting")
        if period_trace.get("expected_required_transition") != PERIOD_ESCALATION_DIRECTION_TRANSITIONS[direction]:
            fail("same_day_trace_transition_conflicting")
        if period_trace.get("context_contract_version") is not None or period_trace.get("context_hash") is not None:
            fail("same_day_trace_context_not_null")
        if period_trace.get("evidence_source") != SAME_DAY_FORMAL_EVIDENCE_SOURCE:
            fail("same_day_trace_evidence_conflicting")
        if (
            period_trace.get("gate_status") != "passed"
            or period_trace.get("gate_pass") is not True
            or period_trace.get("evidence_ready") is not True
            or period_trace.get("reason") is not None
        ):
            fail("same_day_trace_gate_conflicting")
        current_formal_pass_value = period_trace.get("current_formal_pass_periods")
        if not isinstance(current_formal_pass_value, list) or not current_formal_pass_value:
            fail("same_day_formal_pass_periods_missing")
        current_formal_pass_periods = [str(period) for period in current_formal_pass_value]
        if current_formal_pass_periods != [
            period for period in PERIOD_PRIORITY if period in set(current_formal_pass_periods)
        ]:
            fail("same_day_formal_pass_periods_order_or_value_invalid")
        formal_pass_period_sets.add(tuple(current_formal_pass_periods))
        if target_period not in current_formal_pass_periods or expected_prerequisite not in current_formal_pass_periods:
            fail("same_day_formal_pass_pair_missing")
        evaluation_detail = evaluation_details_by_period.get(target_period)
        if (
            not isinstance(evaluation_detail, Mapping)
            or evaluation_detail.get("classification") != "triggered"
            or evaluation_detail.get("existing_formal_classification") != "triggered"
            or evaluation_detail.get("existing_formal_pass") is not True
            or evaluation_detail.get("period_escalation_gate_pass") is not True
        ):
            fail("period_evaluation_same_day_formal_state_conflicting")
        if list(evaluation_detail.get("prerequisite_periods") or []) != [expected_prerequisite]:
            fail("period_evaluation_prerequisite_missing_or_conflicting")

    if len(formal_pass_period_sets) != 1:
        fail("same_day_formal_pass_periods_conflicting")
    ordered_formal_pass_periods = list(next(iter(formal_pass_period_sets)))
    formal_pass_periods = set(ordered_formal_pass_periods)
    if ordered_formal_pass_periods != canonical_formal_periods:
        fail("current_formal_pass_periods_not_proven_by_canonical_evaluation")
    expected_same_day_targets = {
        target_period
        for target_period, requirement in PERIOD_ESCALATION_REQUIREMENTS.items()
        if target_period in formal_pass_periods
        and requirement["prerequisite_period"] in formal_pass_periods
    }
    if same_day_targets != expected_same_day_targets:
        fail("same_day_trace_target_set_conflicting")

    compressed_same_day_targets = same_day_targets & set(same_day_prerequisite_by_target.values())
    final_same_day_targets = same_day_targets - compressed_same_day_targets
    if not final_same_day_targets:
        fail("same_day_final_target_missing")
    if set(triggered_periods) & same_day_targets != final_same_day_targets:
        fail("same_day_target_compression_conflicting")
    compressed_by_same_day_targets = set(same_day_prerequisite_by_target.values())
    if set(triggered_periods) & compressed_by_same_day_targets:
        fail("compressed_prerequisite_reintroduced")

    independent_triggered_periods = set(triggered_periods) - same_day_targets
    for period in independent_triggered_periods:
        detail = evaluation_details_by_period.get(period)
        if not isinstance(detail, Mapping) or not canonical_formal_detail_passes(
            direction,
            period,
            detail,
        ):
            fail("independent_triggered_period_n2_proof_invalid")
        # D is an ordinary same-day formal trigger and has no N2 escalation
        # source_entry. Higher independent targets still require complete,
        # positive ready/seen N2 proof.
        if period == "D":
            continue
        detail_trace = detail.get("period_escalation_trace")
        if (
            period not in PERIOD_ESCALATION_REQUIREMENTS
            or not isinstance(detail_trace, Mapping)
            or not n2_context_trace_is_complete(period, detail_trace)
        ):
            fail("independent_triggered_period_n2_proof_invalid")

    final_same_day_prerequisites = {
        same_day_prerequisite_by_target[target_period]
        for target_period in final_same_day_targets
    }
    for target_period in final_same_day_targets:
        expected_prerequisite = same_day_prerequisite_by_target[target_period]
        detail = triggered_details_by_period[target_period]
        detail_trace = detail.get("period_escalation_trace")
        if not isinstance(detail_trace, Mapping) or dict(detail_trace) != dict(period_traces[target_period]):
            fail("triggered_detail_same_day_trace_missing_or_conflicting")
        if list(detail.get("prerequisite_periods") or []) != [expected_prerequisite]:
            fail("triggered_detail_prerequisite_missing_or_conflicting")

    expected_all = [
        period
        for period in PERIOD_PRIORITY
        if period in set(triggered_periods) | final_same_day_prerequisites
    ]
    if all_trigger_periods != expected_all:
        fail("all_trigger_periods_missing_or_conflicting")

    expected_prerequisite_periods_set: set[str] = set()
    for detail in triggered_details:
        if not isinstance(detail, Mapping):
            continue
        detail_prerequisites = detail.get("prerequisite_periods") or []
        if not isinstance(detail_prerequisites, list):
            fail("triggered_detail_prerequisite_value_invalid")
        detail_prerequisite_periods = [str(period) for period in detail_prerequisites]
        if detail_prerequisite_periods != [
            period for period in PERIOD_PRIORITY if period in set(detail_prerequisite_periods)
        ]:
            fail("triggered_detail_prerequisite_order_or_value_invalid")
        expected_prerequisite_periods_set.update(detail_prerequisite_periods)
    expected_prerequisite_periods = [
        period for period in PERIOD_PRIORITY if period in expected_prerequisite_periods_set
    ]
    if prerequisite_periods != expected_prerequisite_periods:
        fail("prerequisite_periods_missing_or_conflicting")


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
