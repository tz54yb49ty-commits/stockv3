"""N5P active-monitor v2 ActionExecuted dry-run planner."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from ashare_v3.action.dry_run import evaluate_action_confirmation_metric


ACTION_EXECUTED_PLAN = "ACTION_EXECUTED_PLAN"
SKIPPED_ADAPTER_BLOCKED = "SKIPPED_ADAPTER_BLOCKED"
SKIPPED_DUPLICATE_ACTION_EXECUTED = "SKIPPED_DUPLICATE_ACTION_EXECUTED"
SKIPPED_EXPIRED_WINDOW = "SKIPPED_EXPIRED_WINDOW"
SKIPPED_FAILED_METRIC = "SKIPPED_FAILED_METRIC"
SKIPPED_NO_MATCH = "SKIPPED_NO_MATCH"
SKIPPED_AMBIGUOUS_JOIN = "SKIPPED_AMBIGUOUS_JOIN"

N3P_SOURCE_METRIC_KIND = "realtime_action_confirmation_metric"

SIDE_EFFECT_GUARD = {
    "db_written": False,
    "action_fact_written": False,
    "action_event_written": False,
    "outbox_written": False,
    "inbox_written": False,
    "checkpoint_written": False,
    "worker_started": False,
    "n6_written": False,
    "sim_trade_virtual_written": False,
}


def build_monitor_action_executed_dry_run_report(
    *,
    active_tracking_states: Sequence[Mapping[str, Any]],
    confirmation_metric_rows: Sequence[Mapping[str, Any]],
    existing_actionexecuted_keys: set[str] | frozenset[str],
    for_trade_date: str,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    seen_keys = set(existing_actionexecuted_keys)
    adapter_counts: Counter[str] = Counter()
    accepted_metric_ids: list[Any] = []

    for raw_metric in confirmation_metric_rows:
        metric = adapt_confirmation_metric_row(raw_metric)
        adapter_trace = metric.get("adapter_trace") if isinstance(metric.get("adapter_trace"), Mapping) else {}
        normalization_status = str(adapter_trace.get("normalization_status") or "already_normalized")
        adapter_counts[normalization_status] += 1
        if normalization_status == "blocked_missing_required_fields":
            decisions.append(
                {
                    "decision": SKIPPED_ADAPTER_BLOCKED,
                    "confirmation_metric_id": confirmation_metric_id(metric),
                    "metric_key": build_structured_metric_key(metric),
                    "reason": "confirmation_metric_adapter_blocked",
                    "adapter_trace": dict(adapter_trace),
                }
            )
            continue
        join_result = resolve_matching_states_for_metric(metric=metric, tracking_states=active_tracking_states)
        metric_key = build_structured_metric_key(metric)
        join_trace = build_confirmation_metric_join_trace(metric=metric, join_result=join_result)
        active_matches = [item for item in join_result["matches"] if is_active_tracking_state(item["state"])]

        if len(active_matches) > 1:
            decisions.append(
                {
                    "decision": SKIPPED_AMBIGUOUS_JOIN,
                    "metric_key": metric_key,
                    "reason": "ambiguous_confirmation_metric_join",
                    "join_trace": join_trace,
                    "monitor_window_ids": [
                        item["state"].get("monitor_window_id")
                        for item in active_matches
                    ],
                    "confirmation_metric_id": confirmation_metric_id(metric),
                }
            )
            continue

        if active_matches:
            state = active_matches[0]["state"]
            passing_rule = evaluate_metric_passing_rule(metric=metric, state=state)
            if not passing_rule["passed"]:
                decisions.append(
                    {
                        "decision": SKIPPED_FAILED_METRIC,
                        "monitor_window_id": state.get("monitor_window_id"),
                        "metric_key": metric_key,
                        "reason": "confirmation_metric_not_passing",
                        "join_trace": join_trace,
                        "passing_rule_trace": passing_rule["trace"],
                    }
                )
                continue

            idempotency_key = build_actionexecuted_idempotency_key(
                state=state,
                metric=metric,
                for_trade_date=for_trade_date,
            )
            if idempotency_key in seen_keys:
                decisions.append(
                    {
                        "decision": SKIPPED_DUPLICATE_ACTION_EXECUTED,
                        "monitor_window_id": state.get("monitor_window_id"),
                        "idempotency_key": idempotency_key,
                        "metric_key": metric_key,
                        "reason": "duplicate_confirmation_metric",
                        "join_trace": join_trace,
                    }
                )
                continue

            seen_keys.add(idempotency_key)
            plan = build_actionexecuted_plan(
                state=state,
                metric=metric,
                for_trade_date=for_trade_date,
                idempotency_key=idempotency_key,
                metric_key=metric_key,
                join_trace=join_trace,
                passing_rule_trace=passing_rule["trace"],
            )
            plans.append(plan)
            accepted_metric_ids.append(confirmation_metric_id(metric))
            decisions.append(
                {
                    "decision": ACTION_EXECUTED_PLAN,
                    "monitor_window_id": state.get("monitor_window_id"),
                    "idempotency_key": idempotency_key,
                    "metric_key": metric_key,
                    "confirmation_metric_id": confirmation_metric_id(metric),
                    "join_trace": join_trace,
                    "passing_rule_trace": passing_rule["trace"],
                }
            )
            continue

        if join_result["matches"]:
            for item in join_result["matches"]:
                decisions.append(
                    {
                        "decision": SKIPPED_EXPIRED_WINDOW,
                        "monitor_window_id": item["state"].get("monitor_window_id"),
                        "confirmation_metric_id": confirmation_metric_id(metric),
                        "reason": "tracking_window_not_active",
                        "join_trace": join_trace,
                    }
                )
            continue

        decisions.append(
            {
                "decision": SKIPPED_NO_MATCH,
                "confirmation_metric_id": confirmation_metric_id(metric),
                "metric_key": metric_key,
                "reason": "confirmation_metric_no_matching_window",
                "join_trace": join_trace,
            }
        )

    return {
        "status": "DRY_RUN_PASS",
        "mode": "n5p_active_monitor_v2_actionexecuted",
        "for_trade_date": for_trade_date,
        "tracking_state_count": len(active_tracking_states),
        "confirmation_metric_row_count": len(confirmation_metric_rows),
        "action_executed_plan_count": len(plans),
        "decision_counts": dict(Counter(str(row["decision"]) for row in decisions)),
        "adapter_counts": {
            "adapted_from_raw_json": adapter_counts.get("adapted_from_raw_json", 0),
            "already_normalized": adapter_counts.get("already_normalized", 0),
            "blocked_missing_required_fields": adapter_counts.get("blocked_missing_required_fields", 0),
        },
        "accepted_metric_ids": accepted_metric_ids,
        "decisions": decisions,
        "action_executed_plans": plans,
        "side_effect_guard": dict(SIDE_EFFECT_GUARD),
    }


def adapt_confirmation_metric_row(metric: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(metric)
    raw_json = metric.get("raw_json")
    raw_json = raw_json if isinstance(raw_json, Mapping) else {}
    adapted_fields: list[str] = []

    def top_or_raw(field: str, *, raw_field: str | None = None, default: Any = None) -> Any:
        value = output.get(field)
        if value not in (None, ""):
            return value
        candidate = raw_json.get(raw_field or field)
        if candidate not in (None, ""):
            adapted_fields.append(field)
            return candidate
        if default not in (None, ""):
            adapted_fields.append(field)
            return default
        return value

    output["signal_type"] = top_or_raw("signal_type")
    output["condition_key"] = top_or_raw("condition_key")
    output["original_condition_key"] = top_or_raw("original_condition_key")
    output["condition_keys"] = top_or_raw("condition_keys", default=list_value(raw_json.get("condition_keys")))
    output["source_metric_kind"] = top_or_raw("source_metric_kind", default=N3P_SOURCE_METRIC_KIND)
    output["metric_ready"] = bool_value(top_or_raw("metric_ready"))
    output["is_closed_1m"] = bool_value(
        top_or_raw("is_closed_1m", default=raw_json.get("closed_minute_proof", {}).get("is_closed_1m"))
    )
    output["metric_quality_status"] = top_or_raw("metric_quality_status")
    output["action_mark"] = top_or_raw("action_mark")
    output["source_metric_run_id"] = top_or_raw("source_metric_run_id")
    output["confirmation_metric_run_id"] = top_or_raw(
        "confirmation_metric_run_id",
        default=output.get("source_metric_run_id") or output.get("projection_run_id") or output.get("run_id"),
    )
    output["action_confirmation_metric_id"] = top_or_raw("action_confirmation_metric_id")
    output["confirmation_metric_id"] = top_or_raw(
        "confirmation_metric_id",
        default=output.get("action_confirmation_metric_id") or output.get("metric_id"),
    )

    missing_required_fields: list[str] = []
    for field, value in (
        ("asset_kind", output.get("asset_kind")),
        ("identity_key", output.get("identity_key")),
        ("confirmation_metric_id", confirmation_metric_id(output)),
        ("confirmation_metric_run_id", confirmation_metric_run_id(output)),
    ):
        if value in (None, ""):
            missing_required_fields.append(field)

    normalization_status = "already_normalized"
    if missing_required_fields:
        normalization_status = "blocked_missing_required_fields"
    elif adapted_fields:
        normalization_status = "adapted_from_raw_json"

    output["adapter_trace"] = {
        "normalization_status": normalization_status,
        "adapted_fields": adapted_fields,
        "missing_required_fields": missing_required_fields,
    }
    return output


def metric_matches_state(metric: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    fields = ("asset_kind", "identity_key", "signal_type", "condition_key")
    return all(str(metric.get(field) or "") == str(state.get(field) or "") for field in fields)


def resolve_matching_states_for_metric(
    *,
    metric: Mapping[str, Any],
    tracking_states: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for state in tracking_states:
        strategy = resolve_join_strategy(metric=metric, state=state)
        diagnostics.append(
            {
                "monitor_window_id": state.get("monitor_window_id"),
                "strategy": strategy,
            }
        )
        if strategy == "no_match":
            continue
        matches.append({"state": state, "strategy": strategy})
    return {"matches": matches, "diagnostics": diagnostics}


def resolve_join_strategy(metric: Mapping[str, Any], state: Mapping[str, Any]) -> str:
    if not same_metric_lifecycle_identity(metric=metric, state=state):
        return "no_match"
    if metric_matches_state(metric, state):
        return "exact_condition_key"

    state_condition_key = str(state.get("condition_key") or "")
    raw_json = metric.get("raw_json")
    raw_json = raw_json if isinstance(raw_json, Mapping) else {}
    if state_condition_key and state_condition_key == str(raw_json.get("original_condition_key") or ""):
        return "raw_original_condition_key"

    condition_keys = raw_json.get("condition_keys")
    normalized_keys = {
        str(item or "")
        for item in condition_keys
        if isinstance(condition_keys, list) and str(item or "")
    }
    if state_condition_key and state_condition_key in normalized_keys:
        return "raw_condition_keys"
    return "no_match"


def same_metric_lifecycle_identity(metric: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    fields = ("asset_kind", "identity_key", "signal_type")
    return all(str(metric.get(field) or "") == str(state.get(field) or "") for field in fields)


def build_confirmation_metric_join_trace(
    *,
    metric: Mapping[str, Any],
    join_result: Mapping[str, Any],
) -> dict[str, Any]:
    matches = list(join_result.get("matches") or [])
    diagnostics = list(join_result.get("diagnostics") or [])
    if len(matches) > 1:
        join_strategy = "ambiguous"
    elif len(matches) == 1:
        join_strategy = str(matches[0].get("strategy") or "no_match")
    else:
        join_strategy = "no_match"
    return {
        "join_strategy": join_strategy,
        "metric_condition_key": metric.get("condition_key"),
        "metric_original_condition_key": metric_original_condition_key(metric),
        "metric_condition_keys": metric_condition_keys(metric),
        "matched_monitor_window_ids": [
            item["state"].get("monitor_window_id")
            for item in matches
        ],
        "candidate_state_diagnostics": diagnostics,
    }


def is_active_tracking_state(state: Mapping[str, Any]) -> bool:
    return (
        str(state.get("tracking_status") or "") == "tracking"
        and bool(state.get("trigger_live"))
        and str(state.get("current_status") or "") == "matched"
    )


def metric_is_passing(metric: Mapping[str, Any]) -> bool:
    return (
        str(metric.get("source_metric_kind") or "") == N3P_SOURCE_METRIC_KIND
        and bool(metric.get("metric_ready"))
        and bool(metric.get("is_closed_1m"))
        and bool(metric.get("all_period_confirmation_pass"))
        and str(metric.get("metric_quality_status") or "") == "passed"
    )


def evaluate_metric_passing_rule(
    *,
    metric: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    legacy_gates = {
        "source_metric_kind_ok": str(metric.get("source_metric_kind") or "") == N3P_SOURCE_METRIC_KIND,
        "metric_ready_ok": bool(metric.get("metric_ready")),
        "is_closed_1m_ok": bool(metric.get("is_closed_1m")),
        "metric_quality_status_ok": str(metric.get("metric_quality_status") or "") == "passed",
    }
    legacy_gates_ok = all(legacy_gates.values())
    top_level_pass = metric.get("all_period_confirmation_pass")

    trace: dict[str, Any] = {
        "passing_rule_strategy": "failed_legacy_gate",
        "legacy_gates": legacy_gates,
        "top_level_all_period_confirmation_pass": top_level_pass,
        "evaluator_all_period_confirmation_pass": None,
        "evaluator_blocked_reason": None,
        "evaluator_metric_context_status": None,
    }
    if not legacy_gates_ok:
        return {"passed": False, "trace": trace}

    if bool(top_level_pass):
        trace["passing_rule_strategy"] = "legacy_top_level"
        return {"passed": True, "trace": trace}

    if top_level_pass is not None:
        return {"passed": False, "trace": trace}

    evaluator_result = evaluate_action_confirmation_metric(
        signal_type=str(metric.get("signal_type") or ""),
        source_action_confirmation_metric_id=str(confirmation_metric_id(metric) or ""),
        metric_fact=metric,
        trigger_time=state.get("latest_n4_event_time"),
        metric_required=True,
    )
    trace["evaluator_all_period_confirmation_pass"] = evaluator_result.get("all_period_confirmation_pass")
    trace["evaluator_blocked_reason"] = evaluator_result.get("blocked_reason")
    trace["evaluator_metric_context_status"] = evaluator_result.get("metric_context_status")
    if evaluator_result.get("all_period_confirmation_pass"):
        trace["passing_rule_strategy"] = "shared_evaluator_fallback"
        return {"passed": True, "trace": trace}
    trace["passing_rule_strategy"] = "evaluator_failed"
    return {"passed": False, "trace": trace}


def build_actionexecuted_idempotency_key(
    *,
    state: Mapping[str, Any],
    metric: Mapping[str, Any],
    for_trade_date: str,
) -> str:
    return "|".join(
        [
            str(for_trade_date),
            str(state.get("asset_kind") or ""),
            str(state.get("identity_key") or ""),
            str(state.get("signal_type") or ""),
            str(state.get("condition_key") or ""),
            str(state.get("monitor_window_id") or ""),
            str(confirmation_metric_run_id(metric)),
            str(confirmation_metric_id(metric)),
        ]
    )


def build_actionexecuted_plan(
    *,
    state: Mapping[str, Any],
    metric: Mapping[str, Any],
    for_trade_date: str,
    idempotency_key: str,
    metric_key: dict[str, Any],
    join_trace: Mapping[str, Any],
    passing_rule_trace: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "event_type": "ActionExecuted",
        "action_state": "executed",
        "confirmation_status": "passed",
        "monitor_window_id": state.get("monitor_window_id"),
        "trade_date": for_trade_date,
        "asset_kind": state.get("asset_kind"),
        "identity_key": state.get("identity_key"),
        "signal_type": state.get("signal_type"),
        "condition_key": state.get("condition_key"),
        "trigger_type": state.get("trigger_type"),
        "action_mark": metric.get("action_mark"),
        "latest_n4_event_id": state.get("latest_n4_event_id"),
        "latest_n4_event_type": state.get("latest_n4_event_type"),
        "latest_n4_event_time": state.get("latest_n4_event_time"),
        "trigger_period": state.get("trigger_period"),
        "triggered_periods": list_value(state.get("triggered_periods")),
        "trigger_price": state.get("trigger_price"),
        "trigger_mark_candidate": state.get("trigger_mark_candidate"),
        "trigger_context_version": state.get("trigger_context_version"),
        "confirmation_metric_run_id": confirmation_metric_run_id(metric),
        "confirmation_metric_id": confirmation_metric_id(metric),
        "confirmation_metric_key": metric_key,
        "confirmation_metric_join_trace": dict(join_trace),
        "confirmation_metric_passing_rule_trace": dict(passing_rule_trace),
    }
    return {
        "event_type": "ActionExecuted",
        "monitor_window_id": state.get("monitor_window_id"),
        "idempotency_key": idempotency_key,
        "metric_key": metric_key,
        "last_seen_metric_key": metric_key,
        "last_final_evaluated_metric_key": metric_key,
        "payload": payload,
    }


def metric_original_condition_key(metric: Mapping[str, Any]) -> Any:
    raw_json = metric.get("raw_json")
    raw_json = raw_json if isinstance(raw_json, Mapping) else {}
    return raw_json.get("original_condition_key")


def metric_condition_keys(metric: Mapping[str, Any]) -> list[Any]:
    raw_json = metric.get("raw_json")
    raw_json = raw_json if isinstance(raw_json, Mapping) else {}
    value = raw_json.get("condition_keys")
    return list_value(value)


def build_structured_metric_key(metric: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metric_time": metric.get("metric_time"),
        "metric_run_id": confirmation_metric_run_id(metric),
        "metric_id": confirmation_metric_id(metric),
        "metric_version": metric.get("metric_version"),
        "quality_status": metric.get("metric_quality_status"),
    }


def confirmation_metric_run_id(metric: Mapping[str, Any]) -> Any:
    return metric.get("confirmation_metric_run_id") or metric.get("projection_run_id") or metric.get("run_id")


def confirmation_metric_id(metric: Mapping[str, Any]) -> Any:
    return metric.get("confirmation_metric_id") or metric.get("action_confirmation_metric_id") or metric.get("metric_id")


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def list_value(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]
