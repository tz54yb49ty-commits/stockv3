"""N5 action candidate dry-run planner.

This module transforms N4 standard trigger events into in-memory N5 action
candidates. It never writes action facts, common_event_outbox, inbox,
checkpoint, user projection, voice, sim, or trading rows.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Mapping, Sequence

from ashare_v3.condition.basis import normalize_mapping
from ashare_v3.events.ids import join_dedup_parts


ALLOWED_N4_INPUT_EVENT_TYPES = (
    "TriggerMatched",
    "TriggerPendingMarketData",
    "TriggerStateChanged",
)
N5_OUTPUT_EVENT_TYPES = (
    "ActionEligible",
    "ActionBlocked",
    "ActionExecuted",
    "ActionSkipped",
)
TERMINAL_ACTION_STATES = ("blocked", "executed", "skipped", "expired")
UNFINISHED_ACTION_STATES = ("eligible",)
BUY_SIGNAL_TYPES = ("B_BUY",)
SELL_SIGNAL_TYPES = ("S_SELL",)
HINT_SIGNAL_TYPES = ("BUY_HINT", "SELL_HINT")
CANONICAL_RUNTIME_SIGNAL_TYPES = BUY_SIGNAL_TYPES + SELL_SIGNAL_TYPES
DEPRECATED_RUNTIME_SIGNAL_TYPES = (
    "B_BUY_30M_VOL",
    "S_SELL_30M_SHRINK",
    "BUY_HINT",
    "SELL_HINT",
)
CANONICAL_ACTION_MARKS = ("normal", "30m_volume", "30m_shrink")
ACTION_MARK_SOURCE_N5_METRIC = "n5_action_confirmation_metric"
ACTION_MARK_BASIS_PREVIOUS_DAY_SAME_WINDOW = "previous_day_same_window_amount"
CALIBRATED_METRIC_POLICY_VERSION = "previous_day_same_window_elapsed_ratio_v1"
ALLOWED_BLOCKED_REASONS = (
    "metric_missing",
    "metric_scope_excluded",
    "metric_quality_failed",
    "metric_policy_invalid",
    "trigger_not_live",
    "lineage_mismatch",
    "missing_previous_session_reference",
    "price_confirmation_failed",
    "amount_confirmation_failed",
    "duplicate_action_fact",
    "unsupported_signal_type",
    "n4_formal_trigger_period_missing",
)
USER_LAYER_BLOCKED_REASONS = (
    "no_position",
    "insufficient_cash",
    "t_plus_one_locked",
    "already_sold",
    "position_limit",
    "blacklist",
)
CONFIRMATION_PERIODS = ("120m", "30m", "5m", "1m")
BUY_CONFIRMATION_FLAGS = (
    "buy_120m_price_pass",
    "buy_30m_price_pass",
    "buy_5m_price_pass",
    "buy_5m_amount_pass",
    "buy_1m_price_pass",
    "buy_1m_amount_pass",
)
BUY_ACTION_EXECUTION_FLAGS = (
    "buy_120m_price_pass",
    "buy_5m_price_pass",
    "buy_5m_amount_pass",
    "buy_1m_price_pass",
    "buy_1m_amount_pass",
)
SELL_CONFIRMATION_FLAGS = (
    "sell_120m_price_pass",
    "sell_30m_price_pass",
    "sell_5m_price_pass",
    "sell_5m_amount_pass",
    "sell_1m_price_pass",
    "sell_1m_amount_pass",
)
SELL_ACTION_EXECUTION_FLAGS = (
    "sell_120m_price_pass",
    "sell_5m_price_pass",
    "sell_5m_amount_pass",
    "sell_1m_price_pass",
    "sell_1m_amount_pass",
)
CLOSED_MINUTE_SOURCE_EVENT_TYPES = ("MinuteBarClosed", "ClosedThirtyMinuteSummary")
REALTIME_PROJECTION_SOURCE_EVENT_TYPES = ("MarketSnapshotUpdated",)
NON_ACTION_EVENT_PREFIXES = ("User", "Voice", "Sim")
DEPRECATED_N5_OUTPUT_EVENT_TYPES = ("ActionEvent", "HintEvent", "RiskEvent", "PositionEvent")


def build_action_candidates_from_outbox_rows(
    outbox_rows: Sequence[Mapping[str, Any]],
    *,
    action_run_id: str = "n5_action_dry_run",
    action_confirmation_metric_facts: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None = None,
    action_confirmation_metric_facts_by_identity: Mapping[Any, Sequence[Mapping[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Convert N4 outbox rows to N5 in-memory candidates."""

    metric_lookup = normalize_action_confirmation_metric_facts(action_confirmation_metric_facts)
    metrics_by_identity = (
        normalize_action_confirmation_metric_facts_by_identity(action_confirmation_metric_facts_by_identity)
        if action_confirmation_metric_facts_by_identity is not None
        else None
    )
    candidates: list[dict[str, Any]] = []
    for row in outbox_rows:
        normalized = normalize_outbox_row(row)
        event_type = str(normalized.get("event_type") or "")
        if event_type not in ALLOWED_N4_INPUT_EVENT_TYPES:
            continue
        candidate = build_candidate_from_trigger_event(
            normalized,
            action_run_id=action_run_id,
            action_confirmation_metric_facts=metric_lookup,
            action_confirmation_metric_facts_by_identity=metrics_by_identity,
        )
        candidates.extend(expand_live_window_multi_action_candidates(candidate))
    return candidates


def expand_live_window_multi_action_candidates(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    details = list(candidate.get("_live_window_selected_metric_details") or [])
    if not details:
        return [strip_internal_candidate_fields(candidate)]
    return [
        materialize_live_window_metric_candidate(candidate, detail, index=index, total_count=len(details))
        for index, detail in enumerate(details)
    ]


def strip_internal_candidate_fields(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in dict(candidate).items() if not str(key).startswith("_live_window_")}


def normalize_action_confirmation_metric_facts(
    metric_facts: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if not metric_facts:
        return {}
    output: dict[tuple[str, str], dict[str, Any]] = {}
    if isinstance(metric_facts, Mapping):
        iterable = metric_facts.items()
        for raw_key, raw_value in iterable:
            value = normalize_mapping(raw_value or {})
            asset_kind, metric_id = normalize_metric_lookup_key(raw_key, value)
            if asset_kind and metric_id:
                output[(asset_kind, metric_id)] = value
        return output
    for raw_value in metric_facts:
        value = normalize_mapping(raw_value or {})
        asset_kind, metric_id = normalize_metric_lookup_key(None, value)
        if asset_kind and metric_id:
            output[(asset_kind, metric_id)] = value
    return output


def normalize_action_confirmation_metric_facts_by_identity(
    metric_facts_by_identity: Mapping[Any, Sequence[Mapping[str, Any]]] | None,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not metric_facts_by_identity:
        return {}
    output: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw_key, raw_values in metric_facts_by_identity.items():
        asset_kind = ""
        identity_key = ""
        if isinstance(raw_key, (tuple, list)) and len(raw_key) >= 2:
            asset_kind = str(raw_key[0] or "")
            identity_key = str(raw_key[1] or "")
        if not asset_kind or not identity_key:
            continue
        normalized_values = [normalize_mapping(value or {}) for value in raw_values or []]
        normalized_values.sort(
            key=lambda value: (
                datetime_or_none(value.get("metric_time")) or datetime.max.replace(tzinfo=timezone.utc),
                str(value.get("action_confirmation_metric_id") or value.get("metric_id") or ""),
            )
        )
        output[(asset_kind, identity_key)] = normalized_values
    return output


def normalize_metric_lookup_key(raw_key: Any, value: Mapping[str, Any]) -> tuple[str, str]:
    if isinstance(raw_key, (tuple, list)) and len(raw_key) >= 2:
        return str(raw_key[0] or ""), str(raw_key[1] or "")
    asset_kind = str(value.get("asset_kind") or "")
    metric_id = str(
        value.get("action_confirmation_metric_id")
        or value.get("source_action_confirmation_metric_id")
        or value.get("metric_id")
        or ""
    )
    return asset_kind, metric_id


def normalize_outbox_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    payload = output.get("payload_json") or {}
    if not isinstance(payload, Mapping):
        payload = {}
    output["payload_json"] = normalize_mapping(payload)
    return output


def build_candidate_from_trigger_event(
    row: Mapping[str, Any],
    *,
    action_run_id: str,
    action_confirmation_metric_facts: Mapping[tuple[str, str], Mapping[str, Any]] | None = None,
    action_confirmation_metric_facts_by_identity: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    payload = dict(row.get("payload_json") or {})
    source_trigger_event_type = str(row.get("event_type") or "")
    source_trigger_event_id = str(row.get("event_id") or payload.get("trigger_event_id") or "")
    asset_kind = str(payload.get("asset_kind") or row.get("asset_kind") or "")
    identity_key = str(payload.get("identity_key") or row.get("identity_key") or "")
    trade_date = str(payload.get("trade_date") or row.get("trade_date") or "")
    direction = str(payload.get("direction") or "")
    signal_type = str(payload.get("signal_type") or "")
    condition_key = str(payload.get("condition_key") or "")
    original_condition_key = str(payload.get("original_condition_key") or condition_key)
    trigger_period = str(payload.get("trigger_period") or "")
    trigger_time = payload.get("trigger_time") or row.get("event_time")
    trigger_kind = infer_trigger_kind(payload=payload, original_condition_key=original_condition_key)
    primary_trigger_period = resolve_primary_trigger_period(
        payload=payload,
        trigger_kind=trigger_kind,
        condition_key=condition_key,
        original_condition_key=original_condition_key,
        trigger_period=trigger_period,
    )
    formal_period_proof_status = evaluate_n4_formal_trigger_period_proof(
        source_trigger_event_type=source_trigger_event_type,
        trigger_kind=trigger_kind,
        signal_type=signal_type,
        payload=payload,
    )
    action_eligible = bool_value(payload.get("action_eligible", True))
    current_status = str(payload.get("current_status") or ("matched" if source_trigger_event_type == "TriggerMatched" else ""))
    trigger_live = infer_trigger_live(source_trigger_event_type=source_trigger_event_type, payload=payload)
    data_quality_status = str(payload.get("data_quality_status") or "pending")
    source_trigger_match_id = payload.get("source_trigger_match_id") or payload.get("trigger_match_id")
    source_condition_run_id = str(payload.get("source_condition_run_id") or "")
    source_market_data_run_id = payload.get("source_market_data_run_id")
    source_market_trace = build_source_market_trace(payload)
    source_action_confirmation_metric_id = infer_source_action_confirmation_metric_id(payload)
    action_confirmation_metric_fact = lookup_action_confirmation_metric_fact(
        asset_kind=asset_kind,
        metric_id=source_action_confirmation_metric_id,
        action_confirmation_metric_facts=action_confirmation_metric_facts or {},
    )
    action_confirmation_metric_required = requires_action_confirmation_metric(
        source_trigger_event_type=source_trigger_event_type,
        signal_type=signal_type,
        payload=payload,
    )
    metric_evaluation = evaluate_action_confirmation_metric(
        signal_type=signal_type,
        source_action_confirmation_metric_id=source_action_confirmation_metric_id,
        metric_fact=action_confirmation_metric_fact,
        trigger_time=resolve_metric_alignment_trigger_time(payload, fallback_trigger_time=trigger_time),
        metric_required=action_confirmation_metric_required,
    )
    if bool_value(payload.get("action_confirmation_metric_scope_excluded")):
        metric_evaluation = {
            **metric_evaluation,
            "metric_required": action_confirmation_metric_required,
            "metric_context_status": "scope_excluded",
            "blocked_reason": "metric_scope_excluded",
            "metric_scope_excluded": True,
            "metric_scope_excluded_reason": payload.get("action_confirmation_metric_scope_excluded_reason"),
        }
    live_window_confirmation = resolve_live_window_confirmation(
        source_trigger_event_type=source_trigger_event_type,
        trigger_live=trigger_live,
        current_status=str(payload.get("current_status") or ""),
        action_eligible=action_eligible,
        signal_type=signal_type,
        asset_kind=asset_kind,
        identity_key=identity_key,
        source_projection_run_id=payload.get("source_projection_run_id"),
        trigger_time=resolve_metric_alignment_trigger_time(payload, fallback_trigger_time=trigger_time),
        source_action_confirmation_metric_id=source_action_confirmation_metric_id,
        initial_metric_evaluation=metric_evaluation,
        action_confirmation_metric_facts=action_confirmation_metric_facts or {},
        action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
    )
    if live_window_confirmation["status"] == "executed":
        selected_metric = dict(live_window_confirmation.get("selected_metric_fact") or {})
        selected_metric_id = str(live_window_confirmation.get("selected_metric_id") or "")
        if selected_metric and selected_metric_id:
            action_confirmation_metric_fact = selected_metric
            source_action_confirmation_metric_id = selected_metric_id
            metric_evaluation = dict(live_window_confirmation.get("selected_metric_evaluation") or metric_evaluation)
    trigger_price, trigger_price_source = resolve_trigger_price(
        payload=payload,
        metric_evaluation=metric_evaluation,
    )
    action_type = infer_action_type(source_trigger_event_type, direction)
    lane = infer_lane(asset_kind=asset_kind, signal_type=signal_type, payload=payload)
    candidate_kind = infer_candidate_kind(source_trigger_event_type)
    runtime_signal_status = infer_runtime_signal_status(signal_type)
    closed_minute_required = source_trigger_event_type == "TriggerMatched"
    realtime_projection_confirmed = is_realtime_projection_confirmed(
        signal_type=signal_type,
        payload=payload,
    )
    minute_boundary_status = infer_minute_context_status(
        closed_minute_required=closed_minute_required,
        realtime_projection_confirmed=realtime_projection_confirmed,
        payload=payload,
        action_confirmation_metric_status=str(metric_evaluation.get("metric_context_status") or ""),
    )
    closed_minute_verified = minute_boundary_status == "closed"
    confirmation_source = infer_confirmation_source(
        source_trigger_event_type=source_trigger_event_type,
        minute_context_status=minute_boundary_status,
        realtime_projection_confirmed=realtime_projection_confirmed,
        metric_evaluation=metric_evaluation,
    )
    trigger_mark_candidate = infer_trigger_mark_candidate(signal_type=signal_type, payload=payload)
    confirmation_status = infer_confirmation_status(
        source_trigger_event_type=source_trigger_event_type,
        trigger_live=trigger_live,
        action_eligible=action_eligible,
        current_status=current_status,
        runtime_signal_status=runtime_signal_status,
        minute_boundary_status=minute_boundary_status,
        payload=payload,
        metric_evaluation=metric_evaluation,
    )
    if live_window_confirmation["status"] == "pending":
        confirmation_status = "pending"
    if formal_period_proof_status["blocked_reason"]:
        confirmation_status = "failed"
    action_mark_decision = derive_action_mark_decision_from_n5_metric(
        signal_type=signal_type,
        metric=metric_evaluation,
    )
    action_mark_candidate = str(action_mark_decision.get("action_mark") or "normal")
    action_state = infer_action_state(
        source_trigger_event_type=source_trigger_event_type,
        trigger_live=trigger_live,
        candidate_kind=candidate_kind,
        confirmation_status=confirmation_status,
    )
    action_event_type = infer_canonical_action_event_type(
        source_trigger_event_type=source_trigger_event_type,
        candidate_kind=candidate_kind,
        action_state=action_state,
    )
    blocked_reason = infer_blocked_reason(
        candidate_kind=candidate_kind,
        source_trigger_event_type=source_trigger_event_type,
        trigger_live=trigger_live,
        action_eligible=action_eligible,
        current_status=current_status,
        runtime_signal_status=runtime_signal_status,
        confirmation_status=confirmation_status,
        action_state=action_state,
        minute_boundary_status=minute_boundary_status,
        metric_evaluation=metric_evaluation,
        formal_period_proof_status=formal_period_proof_status,
    )
    decision_status = infer_decision_status_from_action_state(
        candidate_kind=candidate_kind,
        action_state=action_state,
        confirmation_status=confirmation_status,
        runtime_signal_status=runtime_signal_status,
        minute_boundary_status=minute_boundary_status,
    )
    final_action_mark = action_mark_candidate if action_state == "executed" and confirmation_status == "passed" else None
    starts_action_confirmation = (
        source_trigger_event_type == "TriggerMatched"
        and trigger_live
        and current_status == "matched"
        and action_eligible
        and signal_type in CANONICAL_RUNTIME_SIGNAL_TYPES
    )
    trace_json = build_action_trace_json(
        payload=payload,
        condition_key=condition_key,
        original_condition_key=original_condition_key,
        trigger_mark_candidate=trigger_mark_candidate,
        action_mark_candidate=action_mark_candidate,
        runtime_signal_status=runtime_signal_status,
        minute_boundary_status=minute_boundary_status,
        confirmation_status=confirmation_status,
        action_state=action_state,
        blocked_reason=blocked_reason,
        source_action_confirmation_metric_id=source_action_confirmation_metric_id,
        source_projection_run_id=payload.get("source_projection_run_id"),
        metric_evaluation=metric_evaluation,
        action_mark_decision=action_mark_decision,
    )
    if live_window_confirmation["status"] in {"executed", "pending"}:
        trace_json["live_window_confirmation"] = {
            key: value
            for key, value in live_window_confirmation.items()
            if key not in {"selected_metric_fact", "selected_metric_evaluation", "selected_metric_details"}
        }
    if formal_period_proof_status["blocked_reason"]:
        trace_json["n4_formal_trigger_period_proof"] = formal_period_proof_status
    if trigger_price_source:
        trace_json["trigger_price"] = trigger_price
        trace_json["trigger_price_source"] = trigger_price_source
    trace_json.setdefault("condition_provenance", {})
    trace_json["condition_provenance"].setdefault("source_trigger_event_ids", [])
    trace_json["condition_provenance"].setdefault("source_trigger_match_ids", [])
    if source_trigger_event_id not in trace_json["condition_provenance"]["source_trigger_event_ids"]:
        trace_json["condition_provenance"]["source_trigger_event_ids"].append(source_trigger_event_id)
    if source_trigger_match_id is not None and source_trigger_match_id not in trace_json["condition_provenance"]["source_trigger_match_ids"]:
        trace_json["condition_provenance"]["source_trigger_match_ids"].append(source_trigger_match_id)
    selected_metric_id_for_grain = str(live_window_confirmation.get("selected_metric_id") or "")
    selected_metric_time_for_grain = live_window_confirmation.get("executed_metric_time")
    live_window_multi_action = (
        live_window_confirmation.get("status") == "executed"
        and bool(live_window_confirmation.get("live_window_confirmation"))
        and bool(live_window_confirmation.get("executed_from_window"))
    )
    dedup_key = build_action_candidate_dedup_key(
        action_run_id=action_run_id,
        source_trigger_event_id=source_trigger_event_id,
        source_trigger_event_type=source_trigger_event_type,
        asset_kind=asset_kind,
        identity_key=identity_key,
        direction=direction,
        signal_type=signal_type,
        condition_key=condition_key,
        original_condition_key=original_condition_key,
        trigger_period=trigger_period,
        action_state=action_state,
        action_mark_candidate=action_mark_candidate,
        selected_metric_id=selected_metric_id_for_grain if live_window_multi_action else None,
        executed_metric_time=selected_metric_time_for_grain if live_window_multi_action else None,
    )
    action_confirmation_grain_key = build_action_confirmation_grain_key(
        identity_key=identity_key,
        signal_type=signal_type,
        trade_date=trade_date,
        trigger_kind=trigger_kind,
        original_condition_key=original_condition_key,
        primary_trigger_period=primary_trigger_period or "null",
        trigger_mark_candidate=trigger_mark_candidate,
        trigger_time=trigger_time,
        selected_metric_id=selected_metric_id_for_grain if live_window_multi_action else None,
        executed_metric_time=selected_metric_time_for_grain if live_window_multi_action else None,
    )
    action_confirmation_merge_key = build_action_confirmation_merge_key(
        identity_key=identity_key,
        signal_type=signal_type,
        trade_date=trade_date,
        primary_trigger_period=primary_trigger_period or trigger_period or "null",
        trigger_mark_candidate=trigger_mark_candidate,
        trigger_time=trigger_time,
    )
    if live_window_multi_action:
        action_confirmation_merge_key = action_confirmation_grain_key
    all_trigger_periods = normalize_trigger_period_list(payload.get("all_trigger_periods"))
    tracking_state_key = build_action_tracking_state_key(
        trade_date=trade_date,
        asset_kind=asset_kind,
        identity_key=identity_key,
        direction=direction,
        signal_type=signal_type,
        condition_key=condition_key,
    )
    return {
        "candidate_kind": candidate_kind,
        "action_run_id": action_run_id,
        "source_trigger_run_id": row.get("source_run_id") or payload.get("run_id"),
        "source_trigger_event_id": source_trigger_event_id,
        "source_trigger_event_time": row.get("event_time"),
        "source_trigger_event_type": source_trigger_event_type,
        "source_trigger_match_id": source_trigger_match_id,
        "trigger_match_id": source_trigger_match_id,
        "source_trigger_state_id": payload.get("source_trigger_state_id") or payload.get("trigger_state_id"),
        "trigger_state_id": payload.get("trigger_state_id"),
        "source_condition_run_id": source_condition_run_id,
        "source_market_data_run_id": source_market_data_run_id,
        "source_market_trace": source_market_trace,
        "source_projection_run_id": payload.get("source_projection_run_id"),
        "source_action_confirmation_metric_id": source_action_confirmation_metric_id or None,
        "action_confirmation_metric_required": action_confirmation_metric_required,
        "action_confirmation_metric_fact_available": bool(action_confirmation_metric_fact),
        "action_confirmation_metric_status": metric_evaluation.get("metric_context_status"),
        "action_confirmation_metric_quality_status": metric_evaluation.get("metric_quality_status"),
        "action_confirmation_metric_all_period_pass": metric_evaluation.get("all_period_confirmation_pass"),
        "identity_key": identity_key,
        "asset_kind": asset_kind,
        "trade_date": trade_date,
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": original_condition_key,
        "trigger_kind": trigger_kind,
        "trigger_period": trigger_period,
        "primary_trigger_period": primary_trigger_period,
        "all_trigger_periods": all_trigger_periods,
        "trigger_time": trigger_time,
        "action_event_time": live_window_confirmation.get("executed_metric_time") if live_window_multi_action else trigger_time,
        "trigger_price": trigger_price,
        "trigger_live": trigger_live,
        "current_status": current_status,
        "action_eligible": action_eligible,
        "trigger_mark_candidate": trigger_mark_candidate,
        "action_mark_candidate": action_mark_candidate,
        "action_mark_source": action_mark_decision.get("action_mark_source"),
        "action_mark_basis": action_mark_decision.get("action_mark_basis"),
        "action_mark_reason": action_mark_decision.get("action_mark_reason"),
        "final_action_mark": final_action_mark,
        "action_state": action_state,
        "confirmation_status": confirmation_status,
        "blocked_reason": blocked_reason,
        "tracking_until": live_window_confirmation.get("tracking_until"),
        "last_checked_minute_label": live_window_confirmation.get("last_checked_minute_label"),
        "minute_boundary_status": minute_boundary_status,
        "action_event_type": action_event_type,
        "starts_action_confirmation": starts_action_confirmation,
        "runtime_signal_status": runtime_signal_status,
        "deprecated_runtime_signal_type": signal_type in DEPRECATED_RUNTIME_SIGNAL_TYPES,
        "action_type": action_type,
        "lane": lane,
        "decision_status": decision_status,
        "planned_output_event_type": action_event_type,
        "data_quality_status": data_quality_status,
        "closed_minute_required": closed_minute_required,
        "closed_minute_verified": closed_minute_verified,
        "minute_context_status": minute_boundary_status,
        "confirmation_source": confirmation_source,
        "trace_json": trace_json,
        "action_bucket": build_action_bucket(payload),
        "action_confirmation_grain_key": action_confirmation_grain_key,
        "action_confirmation_merge_key": action_confirmation_merge_key,
        "tracking_state_key": tracking_state_key,
        "action_key": dedup_key,
        "dedup_key": dedup_key,
        "event_schema_version": row.get("event_schema_version") or "v1",
        "source_event_type": payload.get("source_event_type"),
        "source_payload_json": payload,
        "multi_action_window_candidate": live_window_multi_action,
        "_live_window_selected_metric_details": live_window_confirmation.get("selected_metric_details") or [],
        "would_write_db": False,
        "would_update_common_event_inbox": False,
        "would_update_consumer_checkpoint": False,
        "would_pull_market_data": False,
        "would_write_user_projection": False,
        "would_write_voice": False,
        "would_write_sim": False,
        "would_submit_real_trade": False,
    }


def materialize_live_window_metric_candidate(
    candidate: Mapping[str, Any],
    detail: Mapping[str, Any],
    *,
    index: int,
    total_count: int,
) -> dict[str, Any]:
    output = strip_internal_candidate_fields(candidate)
    metric_id = str(detail.get("selected_metric_id") or "")
    metric_fact = normalize_mapping(detail.get("selected_metric_fact") or {})
    metric_evaluation = normalize_mapping(detail.get("selected_metric_evaluation") or {})
    if not metric_id:
        return output

    payload = output.get("source_payload_json") if isinstance(output.get("source_payload_json"), Mapping) else {}
    trigger_price, trigger_price_source = resolve_trigger_price(
        payload=payload,
        metric_evaluation=metric_evaluation,
    )
    action_mark_decision = derive_action_mark_decision_from_n5_metric(
        signal_type=str(output.get("signal_type") or ""),
        metric=metric_evaluation,
    )
    action_mark_candidate = str(action_mark_decision.get("action_mark") or "normal")
    trace_json = dict(output.get("trace_json") or {})
    trace_json["source_action_confirmation_metric_id"] = metric_id
    trace_json["candidate_action_mark"] = action_mark_candidate
    trace_json["action_mark_source"] = action_mark_decision.get("action_mark_source")
    trace_json["action_mark_basis"] = action_mark_decision.get("action_mark_basis")
    trace_json["action_mark_reason"] = action_mark_decision.get("action_mark_reason")
    trace_json["current_30m_virtual_amount"] = action_mark_decision.get("current_30m_virtual_amount")
    trace_json["previous_day_same_window_amount"] = action_mark_decision.get("previous_day_same_window_amount")
    trace_json["action_confirmation_metric"] = {
        "source_action_confirmation_metric_id": metric_evaluation.get("source_action_confirmation_metric_id"),
        "projection_run_id": metric_evaluation.get("projection_run_id"),
        "projection_schema_version": metric_evaluation.get("projection_schema_version"),
        "metric_context_status": metric_evaluation.get("metric_context_status"),
        "metric_ready": metric_evaluation.get("metric_ready"),
        "metric_quality_status": metric_evaluation.get("metric_quality_status"),
        "metric_policy_status": metric_evaluation.get("metric_policy_status"),
        "virtual_amount_policy_version": metric_evaluation.get("virtual_amount_policy_version"),
        "metric_policy": metric_evaluation.get("metric_policy") or {},
        "metric_time": metric_evaluation.get("metric_time"),
        "metric_minute_label": metric_evaluation.get("metric_minute_label"),
        "current_price": metric_evaluation.get("current_price"),
        "current_30m_virtual_amount": metric_evaluation.get("current_30m_virtual_amount"),
        "previous_day_same_window_amount": metric_evaluation.get("previous_day_same_window_amount"),
        "previous_30m_full_amount": metric_evaluation.get("previous_30m_full_amount"),
        "metric_time_alignment_status": metric_evaluation.get("metric_time_alignment_status"),
        "metric_time_alignment": metric_evaluation.get("metric_time_alignment") or {},
        "selected_flags": metric_evaluation.get("selected_flags") or {},
        "all_period_confirmation_pass": metric_evaluation.get("all_period_confirmation_pass"),
        "source_fact_ids": metric_evaluation.get("source_fact_ids") or {},
        "metric_scope_excluded": metric_evaluation.get("metric_scope_excluded"),
        "metric_scope_excluded_reason": metric_evaluation.get("metric_scope_excluded_reason"),
    }
    live_trace = dict(trace_json.get("live_window_confirmation") or {})
    live_trace.update(
        {
            "selected_metric_id": metric_id,
            "executed_metric_time": detail.get("executed_metric_time"),
            "executed_metric_minute_label": detail.get("executed_metric_minute_label"),
            "last_checked_minute_label": detail.get("executed_metric_minute_label"),
            "multi_action_window": total_count > 1,
            "multi_action_window_index": index,
            "executed_metric_count": total_count,
            "action_grain": "source_trigger_event_id+action_type+selected_metric_id",
        }
    )
    trace_json["live_window_confirmation"] = live_trace
    if trigger_price_source:
        trace_json["trigger_price"] = trigger_price
        trace_json["trigger_price_source"] = trigger_price_source

    output.update(
        {
            "source_action_confirmation_metric_id": metric_id,
            "action_confirmation_metric_fact_available": bool(metric_fact),
            "action_confirmation_metric_status": metric_evaluation.get("metric_context_status"),
            "action_confirmation_metric_quality_status": metric_evaluation.get("metric_quality_status"),
            "action_confirmation_metric_all_period_pass": metric_evaluation.get("all_period_confirmation_pass"),
            "trigger_price": trigger_price,
            "action_mark_candidate": action_mark_candidate,
            "action_mark_source": action_mark_decision.get("action_mark_source"),
            "action_mark_basis": action_mark_decision.get("action_mark_basis"),
            "action_mark_reason": action_mark_decision.get("action_mark_reason"),
            "final_action_mark": action_mark_candidate,
            "action_state": "executed",
            "confirmation_status": "passed",
            "blocked_reason": None,
            "last_checked_minute_label": detail.get("executed_metric_minute_label"),
            "action_event_type": "ActionExecuted",
            "planned_output_event_type": "ActionExecuted",
            "decision_status": infer_decision_status_from_action_state(
                candidate_kind=str(output.get("candidate_kind") or ""),
                action_state="executed",
                confirmation_status="passed",
                runtime_signal_status=str(output.get("runtime_signal_status") or ""),
                minute_boundary_status=str(output.get("minute_boundary_status") or ""),
            ),
            "trace_json": trace_json,
            "action_event_time": detail.get("executed_metric_time"),
            "multi_action_window_candidate": True,
        }
    )
    dedup_key = build_action_candidate_dedup_key(
        action_run_id=str(output.get("action_run_id") or ""),
        source_trigger_event_id=str(output.get("source_trigger_event_id") or ""),
        source_trigger_event_type=str(output.get("source_trigger_event_type") or ""),
        asset_kind=str(output.get("asset_kind") or ""),
        identity_key=str(output.get("identity_key") or ""),
        direction=str(output.get("direction") or ""),
        signal_type=str(output.get("signal_type") or ""),
        condition_key=str(output.get("condition_key") or ""),
        original_condition_key=str(output.get("original_condition_key") or ""),
        trigger_period=str(output.get("trigger_period") or ""),
        action_state=str(output.get("action_state") or ""),
        action_mark_candidate=str(output.get("action_mark_candidate") or ""),
        selected_metric_id=metric_id,
        executed_metric_time=detail.get("executed_metric_time"),
    )
    grain_key = build_action_confirmation_grain_key(
        trade_date=str(output.get("trade_date") or ""),
        identity_key=str(output.get("identity_key") or ""),
        signal_type=str(output.get("signal_type") or ""),
        trigger_kind=str(output.get("trigger_kind") or ""),
        original_condition_key=str(output.get("original_condition_key") or ""),
        primary_trigger_period=str(output.get("primary_trigger_period") or "null"),
        trigger_mark_candidate=str(output.get("trigger_mark_candidate") or ""),
        trigger_time=output.get("trigger_time"),
        selected_metric_id=metric_id,
        executed_metric_time=detail.get("executed_metric_time"),
    )
    output["action_key"] = dedup_key
    output["dedup_key"] = dedup_key
    output["action_confirmation_grain_key"] = grain_key
    output["action_confirmation_merge_key"] = grain_key
    return output


FORMAL_N4_TRIGGER_PERIODS = ("Y", "Q", "M", "W", "D")


def evaluate_n4_formal_trigger_period_proof(
    *,
    source_trigger_event_type: str,
    trigger_kind: str,
    signal_type: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate that N5 only acts on formal periods proven by N4."""

    trigger_period = str(payload.get("trigger_period") or "").strip()
    triggered_periods = formal_period_values(payload.get("triggered_periods"))
    all_trigger_periods = formal_period_values(payload.get("all_trigger_periods"))
    primary_trigger_period = str(payload.get("primary_trigger_period") or "").strip()
    primary_is_formal = primary_trigger_period in FORMAL_N4_TRIGGER_PERIODS
    is_hint = trigger_kind == "hint" or str(payload.get("condition_key") or "") in HINT_SIGNAL_TYPES or str(payload.get("original_condition_key") or "") in HINT_SIGNAL_TYPES
    blocked_reason = None
    if (
        source_trigger_event_type == "TriggerMatched"
        and signal_type in CANONICAL_RUNTIME_SIGNAL_TYPES
        and not is_hint
        and trigger_period == "30m"
        and not triggered_periods
    ):
        blocked_reason = "n4_formal_trigger_period_missing"
    return {
        "status": "blocked" if blocked_reason else "passed",
        "blocked_reason": blocked_reason,
        "trigger_period": trigger_period or None,
        "triggered_periods": triggered_periods,
        "all_trigger_periods": all_trigger_periods,
        "primary_trigger_period": primary_trigger_period if primary_is_formal else None,
        "hint_exempt": is_hint,
    }


def formal_period_values(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                parsed = [text]
            return formal_period_values(parsed)
        raw_values = [part.strip() for part in text.split(",") if part.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw_values = [str(item).strip() for item in value if str(item).strip()]
    else:
        raw_values = [str(value).strip()]
    return [period for period in raw_values if period in FORMAL_N4_TRIGGER_PERIODS]


def resolve_trigger_price(
    *,
    payload: Mapping[str, Any],
    metric_evaluation: Mapping[str, Any],
) -> tuple[Any, str | None]:
    """Resolve N5 trigger_price without changing trigger/action semantics."""

    if payload.get("trigger_price") not in (None, ""):
        return payload.get("trigger_price"), "n4_trigger_payload.trigger_price"
    if metric_evaluation.get("current_price") not in (None, ""):
        return metric_evaluation.get("current_price"), "n3_action_confirmation_metric.current_price"
    return None, None


def build_source_market_trace(payload: Mapping[str, Any]) -> dict[str, Any]:
    trace = payload.get("source_market_trace")
    if isinstance(trace, Mapping) and trace:
        output = dict(trace)
    else:
        source_market_data_run_id = payload.get("source_market_data_run_id")
        source_event_id = payload.get("source_event_id")
        source_event_type = payload.get("source_event_type") or payload.get("synthetic_event_type")
        output = {
            "source_market_data_run_id": source_market_data_run_id,
            "source_event_id": source_event_id,
            "source_event_type": source_event_type,
            "trace_source": "N4_trigger_payload",
        }
    period_trace = payload.get("period_trigger_baseline_trace")
    if isinstance(period_trace, Mapping) and period_trace:
        output["period_trigger_baseline_trace"] = dict(period_trace)
    projection_trace = projection_trace_from_payload(payload)
    if projection_trace:
        output["projection_trace"] = projection_trace
    return output


def infer_candidate_kind(source_trigger_event_type: str) -> str:
    if source_trigger_event_type == "TriggerPendingMarketData":
        return "quality_plan"
    if source_trigger_event_type == "TriggerStateChanged":
        return "state_gate"
    return "action_confirmation"


def build_action_tracking_state_key(
    *,
    trade_date: str,
    asset_kind: str,
    identity_key: str,
    direction: str,
    signal_type: str,
    condition_key: str,
) -> str:
    return join_dedup_parts(
        "N5_action_tracking_state_v1",
        "trade_date",
        trade_date,
        "asset_kind",
        asset_kind,
        "identity_key",
        identity_key,
        "direction",
        direction,
        "signal_type",
        signal_type,
        "condition_key",
        condition_key,
    )


def build_action_tracking_state_plan(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Plan N5 tracking-state effects from N4 events without writing DB rows."""

    processed_event_ids: set[str] = set()
    tracking_by_state_key: dict[str, dict[str, Any]] = {}
    tracking_by_state_id: dict[str, dict[str, Any]] = {}
    plans: list[dict[str, Any]] = []
    for candidate in candidates:
        source_event_id = str(candidate.get("source_trigger_event_id") or "")
        source_event_type = str(candidate.get("source_trigger_event_type") or "")
        state_key = str(candidate.get("tracking_state_key") or "")
        state_id = normalize_tracking_state_id(candidate.get("source_trigger_state_id") or candidate.get("trigger_state_id"))
        plan = build_tracking_base_plan(candidate)
        if source_event_id and source_event_id in processed_event_ids:
            plan.update(
                {
                    "operation": "duplicate_n4_event_id_noop",
                    "idempotent_duplicate": True,
                    "would_create_tracking_state": False,
                    "would_update_tracking_state": False,
                }
            )
            plans.append(plan)
            continue
        if source_event_id:
            processed_event_ids.add(source_event_id)

        if source_event_type == "TriggerMatched":
            prior, match_strategy = find_prior_tracking_state(
                state_id=state_id,
                state_key=state_key,
                tracking_by_state_id=tracking_by_state_id,
                tracking_by_state_key=tracking_by_state_key,
            )
            if prior:
                updated = update_tracking_state_from_matched(prior, candidate)
                operation = (
                    "update_tracking_from_matched_terminal"
                    if is_terminal_action_state(updated.get("action_state"))
                    else "update_tracking_from_matched_unfinished"
                )
                plan.update(
                    {
                        "operation": operation,
                        "match_strategy": match_strategy,
                        "tracking_status": updated["tracking_status"],
                        "would_create_tracking_state": False,
                        "would_update_tracking_state": True,
                        "would_expire_tracking_state": False,
                        "terminal_action_state": prior.get("action_state")
                        if is_terminal_action_state(prior.get("action_state"))
                        else None,
                        "tracking_state": updated,
                    }
                )
                store_tracking_state(
                    tracking_by_state_key=tracking_by_state_key,
                    tracking_by_state_id=tracking_by_state_id,
                    state_key=state_key,
                    state_id=state_id,
                    tracking_state=updated,
                )
                plans.append(plan)
                continue

            tracking_state = build_tracking_state_from_candidate(candidate)
            operation = (
                "create_tracking_terminal"
                if is_terminal_action_state(candidate.get("action_state"))
                else "create_tracking_unfinished"
            )
            plan.update(
                {
                    "operation": operation,
                    "tracking_status": tracking_state["tracking_status"],
                    "would_create_tracking_state": True,
                    "would_update_tracking_state": False,
                    "would_expire_tracking_state": False,
                    "tracking_state": tracking_state,
                }
            )
            store_tracking_state(
                tracking_by_state_key=tracking_by_state_key,
                tracking_by_state_id=tracking_by_state_id,
                state_key=state_key,
                state_id=state_id,
                tracking_state=tracking_state,
            )
            plans.append(plan)
            continue

        if source_event_type == "TriggerPendingMarketData":
            plan.update(
                {
                    "operation": "quality_only_no_tracking",
                    "would_create_tracking_state": False,
                    "would_update_tracking_state": False,
                    "would_expire_tracking_state": False,
                }
            )
            plans.append(plan)
            continue

        if source_event_type != "TriggerStateChanged":
            plan.update(
                {
                    "operation": "unsupported_event_noop",
                    "would_create_tracking_state": False,
                    "would_update_tracking_state": False,
                    "would_expire_tracking_state": False,
                }
            )
            plans.append(plan)
            continue

        prior, match_strategy = find_prior_tracking_state(
            state_id=state_id,
            state_key=state_key,
            tracking_by_state_id=tracking_by_state_id,
            tracking_by_state_key=tracking_by_state_key,
        )
        if not prior:
            plan.update(
                {
                    "operation": "state_gate_trace_only_no_prior_tracking",
                    "match_strategy": "none",
                    "would_create_tracking_state": False,
                    "would_update_tracking_state": False,
                    "would_expire_tracking_state": False,
                }
            )
            plans.append(plan)
            continue

        trigger_live = bool(candidate.get("trigger_live"))
        updated = update_tracking_state_from_state_gate(prior, candidate)
        if trigger_live:
            plan.update(
                {
                    "operation": "state_gate_update_tracking_live",
                    "match_strategy": match_strategy,
                    "would_create_tracking_state": False,
                    "would_update_tracking_state": True,
                    "would_expire_tracking_state": False,
                    "tracking_state": updated,
                }
            )
        elif is_terminal_action_state(prior.get("action_state")):
            plan.update(
                {
                    "operation": "state_gate_terminal_noop",
                    "match_strategy": match_strategy,
                    "terminal_action_state": prior.get("action_state"),
                    "would_create_tracking_state": False,
                    "would_update_tracking_state": True,
                    "would_expire_tracking_state": False,
                    "tracking_state": updated,
                }
            )
        else:
            updated["tracking_status"] = "expired"
            updated["action_state"] = "expired"
            updated["confirmation_status"] = "expired"
            updated["expired_reason"] = "trigger_live_false"
            updated["expired_at"] = candidate.get("source_trigger_event_time")
            plan.update(
                {
                    "operation": "expire_unfinished_tracking",
                    "match_strategy": match_strategy,
                    "would_create_tracking_state": False,
                    "would_update_tracking_state": True,
                    "would_expire_tracking_state": True,
                    "would_update_existing_action_fact": True,
                    "planned_output_event_type": "ActionSkipped",
                    "expired_reason": "trigger_live_false",
                    "tracking_state": updated,
                }
            )
        store_tracking_state(
            tracking_by_state_key=tracking_by_state_key,
            tracking_by_state_id=tracking_by_state_id,
            state_key=state_key,
            state_id=state_id,
            tracking_state=updated,
        )
        plans.append(plan)
    return plans


def summarize_action_tracking_state_plan(tracking_plan: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expire_rows = [row for row in tracking_plan if row.get("operation") == "expire_unfinished_tracking"]
    return {
        "plan_row_count": len(tracking_plan),
        "by_operation": count_by(tracking_plan, "operation"),
        "by_source_trigger_event_type": count_by(tracking_plan, "source_trigger_event_type"),
        "tracking_create_count": sum(1 for row in tracking_plan if row.get("would_create_tracking_state")),
        "tracking_update_count": sum(1 for row in tracking_plan if row.get("would_update_tracking_state")),
        "tracking_expire_count": len(expire_rows),
        "action_skipped_plan_count": sum(1 for row in expire_rows if row.get("planned_output_event_type") == "ActionSkipped"),
        "no_prior_tracking_state_gate_count": sum(
            1 for row in tracking_plan if row.get("operation") == "state_gate_trace_only_no_prior_tracking"
        ),
        "terminal_not_reversed_count": sum(
            1 for row in tracking_plan if row.get("operation") == "state_gate_terminal_noop"
        ),
        "duplicate_n4_event_id_noop_count": sum(
            1 for row in tracking_plan if row.get("operation") == "duplicate_n4_event_id_noop"
        ),
        "matched_tracking_create_count": sum(
            1
            for row in tracking_plan
            if row.get("source_trigger_event_type") == "TriggerMatched"
            and row.get("would_create_tracking_state")
        ),
        "matched_tracking_update_count": sum(
            1
            for row in tracking_plan
            if row.get("source_trigger_event_type") == "TriggerMatched"
            and row.get("would_update_tracking_state")
        ),
    }


def build_tracking_base_plan(candidate: Mapping[str, Any]) -> dict[str, Any]:
    tracking_action_state = resolve_tracking_action_state(candidate)
    tracking_confirmation_status = resolve_tracking_confirmation_status(candidate, tracking_action_state)
    tracking_output_event_type = resolve_tracking_output_event_type(candidate, tracking_action_state)
    return {
        "run_id": candidate.get("action_run_id"),
        "source_trigger_run_id": candidate.get("source_trigger_run_id"),
        "state_key": candidate.get("tracking_state_key"),
        "source_trigger_state_id": candidate.get("source_trigger_state_id") or candidate.get("trigger_state_id"),
        "source_trigger_event_id": candidate.get("source_trigger_event_id"),
        "source_trigger_event_type": candidate.get("source_trigger_event_type"),
        "source_trigger_match_id": candidate.get("source_trigger_match_id"),
        "trade_date": candidate.get("trade_date"),
        "asset_kind": candidate.get("asset_kind"),
        "identity_key": candidate.get("identity_key"),
        "direction": candidate.get("direction"),
        "signal_type": candidate.get("signal_type"),
        "condition_key": candidate.get("condition_key"),
        "trigger_live": candidate.get("trigger_live"),
        "current_status": candidate.get("current_status"),
        "primary_trigger_period": candidate.get("primary_trigger_period"),
        "all_trigger_periods": candidate.get("all_trigger_periods") or [],
        "trigger_mark_candidate": candidate.get("trigger_mark_candidate"),
        "latest_n4_event_id": candidate.get("source_trigger_event_id"),
        "latest_n4_event_type": candidate.get("source_trigger_event_type"),
        "latest_n4_event_time": candidate.get("source_trigger_event_time"),
        "action_state": tracking_action_state,
        "confirmation_status": tracking_confirmation_status,
        "planned_output_event_type": tracking_output_event_type,
        "tracking_until": candidate.get("tracking_until"),
        "last_checked_minute_label": candidate.get("last_checked_minute_label"),
        "would_create_tracking_state": False,
        "would_update_tracking_state": False,
        "would_expire_tracking_state": False,
        "would_update_existing_action_fact": False,
    }


def build_tracking_state_from_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    base = build_tracking_base_plan(candidate)
    action_state = str(base.get("action_state") or "")
    return {
        **base,
        "tracking_status": action_state if is_terminal_action_state(action_state) else "tracking",
        "raw_json": candidate.get("source_payload_json") or {},
    }


def live_window_tracking_should_remain_open(candidate: Mapping[str, Any]) -> bool:
    return (
        bool(candidate.get("multi_action_window_candidate"))
        and bool(candidate.get("trigger_live"))
        and str(candidate.get("current_status") or "") == "matched"
    )


def resolve_tracking_action_state(candidate: Mapping[str, Any]) -> str:
    if live_window_tracking_should_remain_open(candidate):
        return "eligible"
    return str(candidate.get("action_state") or "")


def resolve_tracking_confirmation_status(candidate: Mapping[str, Any], tracking_action_state: str) -> str:
    if live_window_tracking_should_remain_open(candidate):
        return "pending"
    return str(candidate.get("confirmation_status") or "")


def resolve_tracking_output_event_type(candidate: Mapping[str, Any], tracking_action_state: str) -> str | None:
    if live_window_tracking_should_remain_open(candidate):
        return "ActionEligible"
    return candidate.get("planned_output_event_type")


def store_tracking_state(
    *,
    tracking_by_state_key: dict[str, dict[str, Any]],
    tracking_by_state_id: dict[str, dict[str, Any]],
    state_key: str,
    state_id: str,
    tracking_state: Mapping[str, Any],
) -> None:
    stored = dict(tracking_state)
    if state_key:
        tracking_by_state_key[state_key] = stored
        for existing_state_id, existing in list(tracking_by_state_id.items()):
            if existing.get("state_key") == state_key:
                tracking_by_state_id[existing_state_id] = stored
    if state_id:
        tracking_by_state_id[state_id] = stored


def update_tracking_state_from_matched(
    prior: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    updated = build_tracking_state_from_candidate(candidate)
    candidate_action_state = str(updated.get("action_state") or "")
    action_state = choose_tracking_action_state(prior.get("action_state"), candidate_action_state)
    if action_state == candidate_action_state:
        confirmation_status = updated.get("confirmation_status")
        planned_output_event_type = updated.get("planned_output_event_type")
    else:
        confirmation_status = prior.get("confirmation_status")
        planned_output_event_type = prior.get("planned_output_event_type")
    updated["action_state"] = action_state
    updated["confirmation_status"] = confirmation_status
    updated["tracking_status"] = action_state if is_terminal_action_state(action_state) else "tracking"
    updated["planned_output_event_type"] = planned_output_event_type
    if action_state != "expired":
        updated["expired_reason"] = prior.get("expired_reason")
        updated["expired_at"] = prior.get("expired_at")
    return updated


def choose_tracking_action_state(prior_state: Any, candidate_state: Any) -> str:
    prior = str(prior_state or "")
    candidate = str(candidate_state or "")
    if candidate == "executed":
        return "executed"
    if prior == "executed":
        return "executed"
    if prior in {"blocked", "skipped", "expired"}:
        return prior
    return candidate


def find_prior_tracking_state(
    *,
    state_id: str,
    state_key: str,
    tracking_by_state_id: Mapping[str, Mapping[str, Any]],
    tracking_by_state_key: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any] | None, str]:
    if state_id and state_id in tracking_by_state_id:
        return dict(tracking_by_state_id[state_id]), "source_trigger_state_id"
    if state_key and state_key in tracking_by_state_key:
        return dict(tracking_by_state_key[state_key]), "state_key"
    return None, "none"


def update_tracking_state_from_state_gate(
    prior: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    updated = dict(prior)
    for key in (
        "trigger_live",
        "current_status",
        "primary_trigger_period",
        "all_trigger_periods",
        "trigger_mark_candidate",
    ):
        updated[key] = candidate.get(key)
    updated["latest_n4_event_id"] = candidate.get("source_trigger_event_id")
    updated["latest_n4_event_type"] = candidate.get("source_trigger_event_type")
    updated["latest_n4_event_time"] = candidate.get("source_trigger_event_time")
    updated["raw_json"] = candidate.get("source_payload_json") or {}
    return updated


def normalize_tracking_state_id(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value)


def is_terminal_action_state(value: Any) -> bool:
    return str(value or "") in TERMINAL_ACTION_STATES


def normalize_trigger_period_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                return normalize_trigger_period_list(json.loads(text))
            except (TypeError, ValueError):
                return [text]
        return [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def infer_trigger_live(*, source_trigger_event_type: str, payload: Mapping[str, Any]) -> bool:
    if "trigger_live" in payload:
        return bool(payload.get("trigger_live"))
    return source_trigger_event_type == "TriggerMatched"


def infer_runtime_signal_status(signal_type: str) -> str:
    if signal_type in CANONICAL_RUNTIME_SIGNAL_TYPES:
        return "canonical"
    if signal_type in DEPRECATED_RUNTIME_SIGNAL_TYPES:
        return "deprecated_runtime_signal_type"
    return "unsupported_runtime_signal_type"


def infer_trigger_kind(*, payload: Mapping[str, Any], original_condition_key: str) -> str:
    raw = str(payload.get("trigger_kind") or "").strip()
    if raw in {"trigger", "hint"}:
        return raw
    if original_condition_key in HINT_SIGNAL_TYPES:
        return "hint"
    return "trigger"


def resolve_primary_trigger_period(
    *,
    payload: Mapping[str, Any],
    trigger_kind: str,
    condition_key: str,
    original_condition_key: str,
    trigger_period: str,
) -> str | None:
    raw_primary = payload.get("primary_trigger_period")
    if raw_primary is not None and str(raw_primary).strip():
        return str(raw_primary).strip()
    if (
        trigger_kind == "hint"
        and (condition_key in HINT_SIGNAL_TYPES or original_condition_key in HINT_SIGNAL_TYPES)
        and trigger_period == "30m"
    ):
        return None
    return trigger_period or None


def infer_trigger_mark_candidate(*, signal_type: str, payload: Mapping[str, Any]) -> str:
    raw_candidate = str(payload.get("trigger_mark_candidate") or "").strip()
    if raw_candidate in CANONICAL_ACTION_MARKS:
        return raw_candidate
    projection_type = str(payload.get("projection_30m_type") or "").strip()
    if projection_type in {"volume_up", "volume", "30m_volume"}:
        return "30m_volume"
    if projection_type in {"shrink_down", "shrink", "30m_shrink"}:
        return "30m_shrink"
    return "normal"


def derive_final_action_mark_from_n5_metric(signal_type: str, metric: Mapping[str, Any]) -> str:
    """Derive N5's final action_mark from N3 action-confirmation metric evidence."""

    return str(derive_action_mark_decision_from_n5_metric(signal_type=signal_type, metric=metric)["action_mark"])


def derive_action_mark_decision_from_n5_metric(*, signal_type: str, metric: Mapping[str, Any]) -> dict[str, Any]:
    current_30m_amount = decimal_or_none(metric.get("current_30m_virtual_amount"))
    previous_same_window_amount = decimal_or_none(metric.get("previous_day_same_window_amount"))
    selected_flags = metric.get("selected_flags") if isinstance(metric.get("selected_flags"), Mapping) else {}
    decision: dict[str, Any] = {
        "action_mark": "normal",
        "action_mark_source": ACTION_MARK_SOURCE_N5_METRIC,
        "action_mark_basis": ACTION_MARK_BASIS_PREVIOUS_DAY_SAME_WINDOW,
        "action_mark_reason": "normal",
        "current_30m_virtual_amount": metric.get("current_30m_virtual_amount"),
        "previous_day_same_window_amount": metric.get("previous_day_same_window_amount"),
    }
    if signal_type not in CANONICAL_RUNTIME_SIGNAL_TYPES:
        decision["action_mark_reason"] = "unsupported_signal_type"
        return decision
    if current_30m_amount is None:
        decision["action_mark_reason"] = "current_30m_virtual_amount_missing"
        return decision
    if previous_same_window_amount is None:
        decision["action_mark_reason"] = "previous_day_same_window_amount_missing"
        return decision
    if previous_same_window_amount <= 0:
        decision["action_mark_reason"] = "previous_day_same_window_amount_not_positive"
        return decision
    if signal_type == "B_BUY":
        buy_30m_price_pass = action_mark_30m_price_pass(
            signal_type=signal_type,
            metric=metric,
            selected_flags=selected_flags,
        )
        if not buy_30m_price_pass:
            decision["action_mark_reason"] = "buy_30m_price_not_confirmed"
            return decision
        if current_30m_amount > previous_same_window_amount:
            decision["action_mark"] = "30m_volume"
            decision["action_mark_reason"] = "n5_buy_30m_volume_confirmed"
        else:
            decision["action_mark_reason"] = "previous_day_same_window_amount_not_exceeded"
        return decision
    sell_30m_price_pass = action_mark_30m_price_pass(
        signal_type=signal_type,
        metric=metric,
        selected_flags=selected_flags,
    )
    if not sell_30m_price_pass:
        decision["action_mark_reason"] = "sell_30m_price_not_confirmed"
        return decision
    if current_30m_amount < previous_same_window_amount:
        decision["action_mark"] = "30m_shrink"
        decision["action_mark_reason"] = "n5_sell_30m_shrink_confirmed"
    else:
        decision["action_mark_reason"] = "previous_day_same_window_amount_not_shrunk"
    return decision


def action_mark_30m_price_pass(
    *,
    signal_type: str,
    metric: Mapping[str, Any],
    selected_flags: Mapping[str, Any],
) -> bool:
    flag_name = "buy_30m_price_pass" if signal_type == "B_BUY" else "sell_30m_price_pass"
    if flag_name in selected_flags:
        return bool_value(selected_flags.get(flag_name))
    if flag_name in metric:
        return bool_value(metric.get(flag_name))
    current_price = decimal_or_none(metric.get("current_price"))
    if current_price is None:
        return False
    if signal_type == "B_BUY":
        return compare_price(metric, "previous_30m_body_high", current_price, ">")
    return compare_price(metric, "previous_30m_body_low", current_price, "<")


def infer_source_action_confirmation_metric_id(payload: Mapping[str, Any]) -> str:
    metric_id = (
        payload.get("source_action_confirmation_metric_id")
        or payload.get("action_confirmation_metric_id")
    )
    metric_trace = payload.get("metric_trace")
    if not metric_id and isinstance(metric_trace, Mapping):
        metric_id = metric_trace.get("action_confirmation_metric_id")
    return str(metric_id or "")


def resolve_metric_alignment_trigger_time(payload: Mapping[str, Any], *, fallback_trigger_time: Any) -> Any:
    metric_trace = payload.get("metric_trace") if isinstance(payload.get("metric_trace"), Mapping) else {}
    join_key = metric_trace.get("join_key") if isinstance(metric_trace.get("join_key"), Mapping) else {}
    projection_trace = payload.get("projection_trace") if isinstance(payload.get("projection_trace"), Mapping) else {}
    source_fact_ids = (
        projection_trace.get("source_fact_ids")
        if isinstance(projection_trace.get("source_fact_ids"), Mapping)
        else {}
    )
    return (
        join_key.get("trigger_time")
        or payload.get("metric_join_time")
        or projection_trace.get("closed_label_used")
        or source_fact_ids.get("closed_label_used")
        or fallback_trigger_time
    )


def lookup_action_confirmation_metric_fact(
    *,
    asset_kind: str,
    metric_id: str,
    action_confirmation_metric_facts: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    if not asset_kind or not metric_id:
        return {}
    fact = action_confirmation_metric_facts.get((asset_kind, metric_id)) or {}
    return normalize_mapping(fact)


def resolve_live_window_confirmation(
    *,
    source_trigger_event_type: str,
    trigger_live: bool,
    current_status: str,
    action_eligible: bool,
    signal_type: str,
    asset_kind: str,
    identity_key: str,
    source_projection_run_id: Any,
    trigger_time: Any,
    source_action_confirmation_metric_id: str,
    initial_metric_evaluation: Mapping[str, Any],
    action_confirmation_metric_facts: Mapping[tuple[str, str], Mapping[str, Any]],
    action_confirmation_metric_facts_by_identity: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    if (
        source_trigger_event_type != "TriggerMatched"
        or not trigger_live
        or current_status != "matched"
        or not action_eligible
        or signal_type not in CANONICAL_RUNTIME_SIGNAL_TYPES
    ):
        return {"status": "not_applicable"}
    initial_reason = str(initial_metric_evaluation.get("blocked_reason") or "")
    if initial_metric_evaluation.get("all_period_confirmation_pass"):
        return {"status": "already_confirmed"}
    if initial_reason not in {"price_confirmation_failed", "amount_confirmation_failed"}:
        return {"status": "not_applicable", "reason": initial_reason or "non_window_failure"}
    if initial_metric_evaluation.get("metric_context_status") != "ready":
        return {"status": "not_applicable", "reason": "metric_not_ready"}

    trigger_dt = datetime_or_none(initial_metric_evaluation.get("metric_time")) or datetime_or_none(trigger_time)
    projection_run_id = str(initial_metric_evaluation.get("projection_run_id") or source_projection_run_id or "")
    last_checked_minute_label = str(initial_metric_evaluation.get("metric_minute_label") or "")
    if action_confirmation_metric_facts_by_identity is None:
        return {
            "status": "pending",
            "live_window_confirmation": True,
            "executed_from_window": False,
            "identity_metric_cache_required": True,
            "identity_metric_cache_present": False,
            "fallback_full_scan_disabled": True,
            "pending_reason": "live_window_identity_metric_cache_missing",
            "trigger_metric_id": str(source_action_confirmation_metric_id or ""),
            "trigger_metric_time": initial_metric_evaluation.get("metric_time"),
            "trigger_metric_minute_label": initial_metric_evaluation.get("metric_minute_label"),
            "trigger_metric_blocked_reason": initial_reason,
            "last_checked_minute_label": last_checked_minute_label or None,
            "tracking_until": None,
            "tracking_window_end_policy": "implicit_for_trade_date_close",
        }

    later_candidates: list[tuple[datetime, str, dict[str, Any], dict[str, Any]]] = []
    if action_confirmation_metric_facts_by_identity:
        raw_metrics = [
            (asset_kind, str(raw_fact.get("action_confirmation_metric_id") or raw_fact.get("metric_id") or ""), raw_fact)
            for raw_fact in action_confirmation_metric_facts_by_identity.get((asset_kind, identity_key), [])
        ]
    else:
        raw_metrics = []
    for fact_asset_kind, metric_id, raw_fact in raw_metrics:
        fact = normalize_mapping(raw_fact)
        if str(fact_asset_kind or "") != asset_kind:
            continue
        if str(metric_id or "") == str(source_action_confirmation_metric_id or ""):
            continue
        if str(fact.get("identity_key") or "") != identity_key:
            continue
        if projection_run_id and str(fact.get("projection_run_id") or "") != projection_run_id:
            continue
        metric_dt = datetime_or_none(fact.get("metric_time"))
        if metric_dt is None:
            continue
        if trigger_dt is not None and metric_dt <= trigger_dt:
            continue
        evaluation = evaluate_action_confirmation_metric(
            signal_type=signal_type,
            source_action_confirmation_metric_id=str(metric_id),
            metric_fact=fact,
            trigger_time=fact.get("metric_time"),
            metric_required=True,
        )
        if evaluation.get("metric_context_status") == "ready" and evaluation.get("all_period_confirmation_pass"):
            later_candidates.append((metric_dt, str(metric_id), fact, evaluation))

    if later_candidates:
        sorted_candidates = sorted(later_candidates, key=lambda item: item[0])
        selected_metric_details = [
            {
                "selected_metric_id": metric_id,
                "selected_metric_fact": fact,
                "selected_metric_evaluation": evaluation,
                "executed_metric_time": evaluation.get("metric_time"),
                "executed_metric_minute_label": evaluation.get("metric_minute_label"),
            }
            for _metric_dt, metric_id, fact, evaluation in sorted_candidates
        ]
        selected_metric_confirmations = [
            {
                "selected_metric_id": detail["selected_metric_id"],
                "executed_metric_time": detail["executed_metric_time"],
                "executed_metric_minute_label": detail["executed_metric_minute_label"],
            }
            for detail in selected_metric_details
        ]
        _, metric_id, fact, evaluation = sorted_candidates[0]
        return {
            "status": "executed",
            "live_window_confirmation": True,
            "executed_from_window": True,
            "multi_action_window": len(selected_metric_details) > 1,
            "executed_metric_count": len(selected_metric_details),
            "selected_metric_confirmations": selected_metric_confirmations,
            "selected_metric_details": selected_metric_details,
            "trigger_metric_id": str(source_action_confirmation_metric_id or ""),
            "trigger_metric_time": initial_metric_evaluation.get("metric_time"),
            "trigger_metric_minute_label": initial_metric_evaluation.get("metric_minute_label"),
            "trigger_metric_blocked_reason": initial_reason,
            "selected_metric_id": metric_id,
            "selected_metric_fact": fact,
            "selected_metric_evaluation": evaluation,
            "executed_metric_time": evaluation.get("metric_time"),
            "executed_metric_minute_label": evaluation.get("metric_minute_label"),
            "action_grain": "source_trigger_event_id+action_type+selected_metric_id",
            "last_checked_minute_label": evaluation.get("metric_minute_label"),
            "tracking_until": None,
            "tracking_window_end_policy": "implicit_for_trade_date_close",
        }

    return {
        "status": "pending",
        "live_window_confirmation": True,
        "executed_from_window": False,
        "trigger_metric_id": str(source_action_confirmation_metric_id or ""),
        "trigger_metric_time": initial_metric_evaluation.get("metric_time"),
        "trigger_metric_minute_label": initial_metric_evaluation.get("metric_minute_label"),
        "trigger_metric_blocked_reason": initial_reason,
        "last_checked_minute_label": last_checked_minute_label or None,
        "tracking_until": None,
        "tracking_window_end_policy": "implicit_for_trade_date_close",
        "pending_reason": "live_trigger_confirmation_not_yet_satisfied",
    }


def evaluate_action_confirmation_metric(
    *,
    signal_type: str,
    source_action_confirmation_metric_id: str,
    metric_fact: Mapping[str, Any],
    trigger_time: Any = None,
    metric_required: bool = False,
) -> dict[str, Any]:
    fact_available = bool(metric_fact)
    if signal_type == "B_BUY":
        selected_flags = BUY_CONFIRMATION_FLAGS
    elif signal_type == "S_SELL":
        selected_flags = SELL_CONFIRMATION_FLAGS
    else:
        selected_flags = ()
    numeric_evaluation = evaluate_numeric_action_confirmation_metric(
        signal_type=signal_type,
        metric_fact=metric_fact,
    )
    if numeric_evaluation.get("numeric_fields_present"):
        flag_status = dict(numeric_evaluation.get("selected_flags") or {})
    else:
        flag_status = {flag: bool_value(metric_fact.get(flag)) for flag in selected_flags}
    metric_ready = bool_value(metric_fact.get("metric_ready"))
    metric_quality_status = str(metric_fact.get("metric_quality_status") or "")
    time_alignment = evaluate_metric_time_alignment(trigger_time=trigger_time, metric_fact=metric_fact)
    metric_time_aligned = time_alignment["status"] in {"aligned", "not_checked"}
    metric_policy = evaluate_metric_policy(metric_fact)
    metric_ready_for_confirmation = (
        fact_available
        and metric_ready
        and metric_quality_status == "passed"
        and metric_time_aligned
        and metric_policy["status"] == "valid"
    )
    action_execution_flags = BUY_ACTION_EXECUTION_FLAGS if signal_type == "B_BUY" else SELL_ACTION_EXECUTION_FLAGS
    action_execution_flag_status = {
        flag: bool(flag_status.get(flag))
        for flag in action_execution_flags
    }
    all_period_confirmation_pass = metric_ready_for_confirmation and all(action_execution_flag_status.values())
    if not source_action_confirmation_metric_id and metric_required:
        metric_context_status = "missing"
    elif not source_action_confirmation_metric_id:
        metric_context_status = "not_required"
    elif not fact_available:
        metric_context_status = "missing"
    elif time_alignment["status"] == "time_mismatch":
        metric_context_status = "time_mismatch"
    elif fact_available and metric_policy["status"] != "valid":
        metric_context_status = "policy_invalid"
    elif not metric_ready_for_confirmation:
        metric_context_status = "not_ready"
    else:
        metric_context_status = "ready"
    blocked_reason = None
    if signal_type not in CANONICAL_RUNTIME_SIGNAL_TYPES:
        blocked_reason = "unsupported_signal_type"
    elif (source_action_confirmation_metric_id or metric_required) and not fact_available:
        blocked_reason = "metric_missing"
    elif fact_available and time_alignment["status"] == "time_mismatch":
        blocked_reason = "lineage_mismatch"
    elif fact_available and metric_policy["status"] != "valid":
        blocked_reason = "metric_policy_invalid"
    elif fact_available and not metric_ready_for_confirmation:
        blocked_reason = "metric_quality_failed"
    elif fact_available and metric_ready_for_confirmation and not all_period_confirmation_pass:
        blocked_reason = str(
            numeric_evaluation.get("blocked_reason")
            or infer_blocked_reason_from_flags(action_execution_flag_status)
        )
    return {
        "source_action_confirmation_metric_id": source_action_confirmation_metric_id or None,
        "metric_required": metric_required,
        "metric_fact_available": fact_available,
        "metric_context_status": metric_context_status,
        "metric_ready": metric_ready,
        "metric_quality_status": metric_quality_status,
        "metric_time": metric_fact.get("metric_time"),
        "metric_minute_label": metric_fact.get("metric_minute_label"),
        "current_price": metric_fact.get("current_price"),
        "current_30m_virtual_amount": metric_fact.get("current_30m_virtual_amount"),
        "previous_day_same_window_amount": metric_fact.get("previous_day_same_window_amount"),
        "previous_30m_full_amount": metric_fact.get("previous_30m_full_amount"),
        "metric_time_alignment_status": time_alignment["status"],
        "metric_time_alignment": time_alignment,
        "projection_run_id": metric_fact.get("projection_run_id"),
        "projection_schema_version": metric_fact.get("projection_schema_version"),
        "virtual_amount_policy_version": metric_policy["policy_version"],
        "metric_policy_status": metric_policy["status"],
        "metric_policy": metric_policy,
        "selected_flags": flag_status,
        "action_execution_required_flags": action_execution_flag_status,
        "all_period_confirmation_pass": all_period_confirmation_pass,
        "blocked_reason": blocked_reason,
        "numeric_fields_present": bool(numeric_evaluation.get("numeric_fields_present")),
        "metric_lineage_status": "metric_fact_joined" if fact_available else "metric_fact_missing",
        "source_fact_ids": metric_fact.get("source_fact_ids") or {},
    }


def evaluate_metric_policy(metric_fact: Mapping[str, Any]) -> dict[str, Any]:
    if not metric_fact:
        return {"status": "missing", "policy_version": None, "required_policy_version": CALIBRATED_METRIC_POLICY_VERSION}
    raw_json = normalize_mapping(metric_fact.get("raw_json") or {})
    trace_json = normalize_mapping(metric_fact.get("trace_json") or {})
    virtual_policy = normalize_mapping(trace_json.get("virtual_amount_policy") or {})
    policy_version = (
        metric_fact.get("virtual_amount_policy_version")
        or raw_json.get("virtual_amount_policy_version")
        or virtual_policy.get("policy_version")
    )
    status = "valid" if policy_version == CALIBRATED_METRIC_POLICY_VERSION else "invalid"
    return {
        "status": status,
        "policy_version": policy_version,
        "required_policy_version": CALIBRATED_METRIC_POLICY_VERSION,
    }


def evaluate_metric_time_alignment(*, trigger_time: Any, metric_fact: Mapping[str, Any]) -> dict[str, Any]:
    metric_time = metric_fact.get("metric_time")
    if not trigger_time or not metric_time:
        return {
            "status": "not_checked",
            "reason": "trigger_time_or_metric_time_missing",
            "trigger_time": trigger_time,
            "metric_time": metric_time,
        }
    trigger_minute = minute_key(trigger_time)
    metric_minute = minute_key(metric_time)
    if not trigger_minute or not metric_minute:
        return {
            "status": "not_checked",
            "reason": "trigger_time_or_metric_time_unparseable",
            "trigger_time": trigger_time,
            "metric_time": metric_time,
        }
    status = "aligned" if trigger_minute == metric_minute else "time_mismatch"
    return {
        "status": status,
        "reason": None if status == "aligned" else "metric_time_not_compatible_with_trigger_time",
        "trigger_time": trigger_time,
        "metric_time": metric_time,
        "trigger_minute": trigger_minute,
        "metric_minute": metric_minute,
    }


def minute_key(value: Any) -> str | None:
    dt = datetime_or_none(value)
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(second=0, microsecond=0).isoformat()


def datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None or value == "":
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def evaluate_numeric_action_confirmation_metric(
    *,
    signal_type: str,
    metric_fact: Mapping[str, Any],
) -> dict[str, Any]:
    if signal_type not in CANONICAL_RUNTIME_SIGNAL_TYPES or not metric_fact:
        return {"numeric_fields_present": False, "selected_flags": {}}
    current_price = decimal_or_none(metric_fact.get("current_price"))
    numeric_probe_fields = (
        "current_price",
        "previous_120m_body_high",
        "previous_120m_body_low",
        "previous_30m_body_high",
        "previous_30m_body_low",
        "previous_5m_body_high",
        "previous_5m_body_low",
        "previous_1m_body_high",
        "previous_1m_body_low",
        "current_1m_amount",
        "previous_1m_amount",
        "current_5m_virtual_amount",
        "previous_5m_full_amount",
    )
    numeric_fields_present = any(field in metric_fact for field in numeric_probe_fields)
    if not numeric_fields_present:
        return {"numeric_fields_present": False, "selected_flags": {}}
    if current_price is None:
        return {
            "numeric_fields_present": True,
            "selected_flags": {flag: False for flag in (BUY_CONFIRMATION_FLAGS if signal_type == "B_BUY" else SELL_CONFIRMATION_FLAGS)},
            "blocked_reason": "metric_quality_failed",
        }
    if signal_type == "B_BUY":
        selected_flags = {
            "buy_120m_price_pass": compare_price(metric_fact, "previous_120m_body_high", current_price, ">"),
            "buy_30m_price_pass": compare_price(metric_fact, "previous_30m_body_high", current_price, ">"),
            "buy_5m_price_pass": compare_price(metric_fact, "previous_5m_body_high", current_price, ">"),
            "buy_5m_amount_pass": compare_amount(
                metric_fact,
                current_field="current_5m_virtual_amount",
                previous_field="previous_5m_full_amount",
                operator=">",
                first_period_field="is_first_5m_of_day",
                default_pass_field="first_5m_amount_default_pass",
            ),
            "buy_1m_price_pass": compare_price(metric_fact, "previous_1m_body_high", current_price, ">"),
            "buy_1m_amount_pass": compare_amount(
                metric_fact,
                current_field="current_1m_amount",
                previous_field="previous_1m_amount",
                operator=">",
                first_period_field="is_first_1m_of_day",
                default_pass_field="first_1m_amount_default_pass",
            ),
        }
        price_flags = ("buy_120m_price_pass", "buy_5m_price_pass", "buy_1m_price_pass")
        amount_flags = ("buy_5m_amount_pass", "buy_1m_amount_pass")
    else:
        selected_flags = {
            "sell_120m_price_pass": compare_price(metric_fact, "previous_120m_body_low", current_price, "<"),
            "sell_30m_price_pass": compare_price(metric_fact, "previous_30m_body_low", current_price, "<"),
            "sell_5m_price_pass": compare_price(metric_fact, "previous_5m_body_low", current_price, "<"),
            "sell_5m_amount_pass": compare_amount(
                metric_fact,
                current_field="current_5m_virtual_amount",
                previous_field="previous_5m_full_amount",
                operator="<",
                first_period_field="is_first_5m_of_day",
                default_pass_field="first_5m_amount_default_pass",
            ),
            "sell_1m_price_pass": compare_price(metric_fact, "previous_1m_body_low", current_price, "<"),
            "sell_1m_amount_pass": compare_amount(
                metric_fact,
                current_field="current_1m_amount",
                previous_field="previous_1m_amount",
                operator="<",
                first_period_field="is_first_1m_of_day",
                default_pass_field="first_1m_amount_default_pass",
            ),
        }
        price_flags = ("sell_120m_price_pass", "sell_5m_price_pass", "sell_1m_price_pass")
        amount_flags = ("sell_5m_amount_pass", "sell_1m_amount_pass")
    if missing_previous_session_reference(metric_fact):
        blocked_reason = "missing_previous_session_reference"
    elif any(not selected_flags[flag] for flag in price_flags):
        blocked_reason = "price_confirmation_failed"
    elif any(not selected_flags[flag] for flag in amount_flags):
        blocked_reason = "amount_confirmation_failed"
    else:
        blocked_reason = None
    return {
        "numeric_fields_present": True,
        "selected_flags": selected_flags,
        "blocked_reason": blocked_reason,
    }


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def compare_price(metric_fact: Mapping[str, Any], previous_field: str, current_price: Decimal, operator: str) -> bool:
    previous_value = decimal_or_none(metric_fact.get(previous_field))
    if previous_value is None:
        return False
    return current_price > previous_value if operator == ">" else current_price < previous_value


def compare_amount(
    metric_fact: Mapping[str, Any],
    *,
    current_field: str,
    previous_field: str,
    operator: str,
    first_period_field: str,
    default_pass_field: str,
) -> bool:
    if bool_value(metric_fact.get(first_period_field)) and bool_value(metric_fact.get(default_pass_field)):
        return True
    current_value = decimal_or_none(metric_fact.get(current_field))
    previous_value = decimal_or_none(metric_fact.get(previous_field))
    if current_value is None or previous_value is None:
        return False
    return current_value > previous_value if operator == ">" else current_value < previous_value


def missing_previous_session_reference(metric_fact: Mapping[str, Any]) -> bool:
    source_by_period = {
        "1m": str(metric_fact.get("previous_1m_period_source") or ""),
        "5m": str(metric_fact.get("previous_5m_period_source") or ""),
        "120m": str(metric_fact.get("previous_120m_period_source") or ""),
    }
    first_by_period = {
        "1m": bool_value(metric_fact.get("is_first_1m_of_day")),
        "5m": bool_value(metric_fact.get("is_first_5m_of_day")),
        "120m": bool_value(metric_fact.get("is_first_120m_of_day")),
    }
    for period, is_first in first_by_period.items():
        if is_first and source_by_period[period] == "not_available":
            return True
    required_previous_fields = (
        "previous_120m_body_high",
        "previous_120m_body_low",
        "previous_5m_body_high",
        "previous_5m_body_low",
        "previous_1m_body_high",
        "previous_1m_body_low",
    )
    return any(field in metric_fact and metric_fact.get(field) in {None, ""} for field in required_previous_fields)


def infer_blocked_reason_from_flags(flag_status: Mapping[str, bool]) -> str:
    failed = {flag for flag, passed in flag_status.items() if not passed}
    if any("price" in flag for flag in failed):
        return "price_confirmation_failed"
    if any("amount" in flag for flag in failed):
        return "amount_confirmation_failed"
    return "metric_quality_failed"


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "1", "yes", "passed"}
    return bool(value)


def infer_confirmation_status(
    *,
    source_trigger_event_type: str,
    trigger_live: bool,
    action_eligible: bool,
    current_status: str,
    runtime_signal_status: str,
    minute_boundary_status: str,
    payload: Mapping[str, Any],
    metric_evaluation: Mapping[str, Any] | None = None,
) -> str:
    if source_trigger_event_type == "TriggerPendingMarketData":
        return "pending"
    if source_trigger_event_type == "TriggerStateChanged":
        return "pending" if trigger_live else "expired"
    if not trigger_live:
        return "expired"
    if current_status and current_status != "matched":
        return "failed"
    if not action_eligible:
        return "failed"
    if runtime_signal_status != "canonical":
        return "failed"
    metric = metric_evaluation or {}
    if metric.get("metric_required") and metric.get("metric_context_status") in {"missing", "not_ready", "time_mismatch", "scope_excluded"}:
        return "failed"
    if metric.get("source_action_confirmation_metric_id") or metric.get("metric_fact_available"):
        if not metric.get("metric_fact_available"):
            return "failed"
        if metric.get("metric_context_status") != "ready":
            return "failed"
        return "passed" if metric.get("all_period_confirmation_pass") else "failed"
    if minute_boundary_status in {"unclosed", "missing"}:
        return "failed"
    return "pending"


def infer_blocked_reason(
    *,
    candidate_kind: str,
    source_trigger_event_type: str,
    trigger_live: bool,
    action_eligible: bool,
    current_status: str,
    runtime_signal_status: str,
    confirmation_status: str,
    action_state: str,
    minute_boundary_status: str,
    metric_evaluation: Mapping[str, Any] | None,
    formal_period_proof_status: Mapping[str, Any] | None = None,
) -> str | None:
    if candidate_kind != "action_confirmation" or action_state != "blocked":
        return None
    if not trigger_live or confirmation_status == "expired":
        return validate_blocked_reason("trigger_not_live")
    if current_status and current_status != "matched":
        return validate_blocked_reason("trigger_not_live")
    if not action_eligible:
        return validate_blocked_reason("trigger_not_live")
    if runtime_signal_status != "canonical":
        return validate_blocked_reason("unsupported_signal_type")
    formal_reason = str((formal_period_proof_status or {}).get("blocked_reason") or "")
    if formal_reason:
        return validate_blocked_reason(formal_reason)
    metric_reason = str((metric_evaluation or {}).get("blocked_reason") or "")
    if metric_reason:
        return validate_blocked_reason(metric_reason)
    if minute_boundary_status in {"missing", "unclosed"}:
        return validate_blocked_reason("metric_missing")
    if confirmation_status == "failed":
        return validate_blocked_reason("metric_quality_failed")
    return None


def validate_blocked_reason(reason: str | None) -> str | None:
    if reason is None or reason == "":
        return None
    if reason in USER_LAYER_BLOCKED_REASONS:
        raise ValueError(f"user-layer blocked_reason is forbidden in N5: {reason}")
    if reason not in ALLOWED_BLOCKED_REASONS:
        raise ValueError(f"unsupported N5 blocked_reason: {reason}")
    return reason


def requires_action_confirmation_metric(
    *,
    source_trigger_event_type: str,
    signal_type: str,
    payload: Mapping[str, Any],
) -> bool:
    if source_trigger_event_type != "TriggerMatched":
        return False
    if signal_type not in CANONICAL_RUNTIME_SIGNAL_TYPES:
        return False
    if action_confirmation_is_intentionally_deferred(payload):
        return False
    return True


def action_confirmation_is_intentionally_deferred(payload: Mapping[str, Any]) -> bool:
    mode = str(
        payload.get("action_confirmation_mode")
        or payload.get("n5_action_confirmation_mode")
        or ""
    ).strip()
    if mode in {"deferred", "eligibility_only", "pending"}:
        return True
    return bool_value(payload.get("action_confirmation_deferred"))


def infer_action_state(
    *,
    source_trigger_event_type: str,
    trigger_live: bool,
    candidate_kind: str,
    confirmation_status: str,
) -> str:
    if candidate_kind == "quality_plan":
        return "blocked"
    if not trigger_live or confirmation_status == "expired":
        return "expired"
    if source_trigger_event_type == "TriggerStateChanged":
        return "eligible"
    if confirmation_status == "passed":
        return "executed"
    if confirmation_status == "failed":
        return "blocked"
    return "eligible"


def infer_canonical_action_event_type(
    *,
    source_trigger_event_type: str,
    candidate_kind: str,
    action_state: str,
) -> str | None:
    if source_trigger_event_type != "TriggerMatched":
        return None
    if candidate_kind == "quality_plan":
        return None
    if candidate_kind == "state_gate" and action_state != "expired":
        return None
    if action_state == "executed":
        return "ActionExecuted"
    if action_state == "blocked":
        return "ActionBlocked"
    if action_state in {"skipped", "expired"}:
        return "ActionSkipped"
    if source_trigger_event_type == "TriggerMatched":
        return "ActionEligible"
    return None


def infer_decision_status_from_action_state(
    *,
    candidate_kind: str,
    action_state: str,
    confirmation_status: str,
    runtime_signal_status: str,
    minute_boundary_status: str,
) -> str:
    if candidate_kind == "quality_plan":
        return "quality_only"
    if candidate_kind == "state_gate":
        return "state_gate"
    if runtime_signal_status != "canonical":
        return runtime_signal_status
    if minute_boundary_status in {"unclosed", "missing"}:
        return f"blocked_{minute_boundary_status}"
    if action_state == "executed":
        return "confirmation_passed"
    if action_state == "blocked":
        return "confirmation_failed"
    if confirmation_status == "pending":
        return "pending_confirmation"
    return action_state


def build_action_trace_json(
    *,
    payload: Mapping[str, Any],
    condition_key: str,
    original_condition_key: str,
    trigger_mark_candidate: str,
    action_mark_candidate: str,
    runtime_signal_status: str,
    minute_boundary_status: str,
    confirmation_status: str,
    action_state: str,
    blocked_reason: str | None,
    source_action_confirmation_metric_id: str,
    source_projection_run_id: Any,
    metric_evaluation: Mapping[str, Any],
    action_mark_decision: Mapping[str, Any],
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "condition_key": condition_key,
        "original_condition_key": original_condition_key,
        "trigger_mark_candidate": trigger_mark_candidate,
        "n4_trigger_mark_candidate": trigger_mark_candidate,
        "candidate_action_mark": action_mark_candidate,
        "action_mark_source": action_mark_decision.get("action_mark_source"),
        "action_mark_basis": action_mark_decision.get("action_mark_basis"),
        "action_mark_reason": action_mark_decision.get("action_mark_reason"),
        "current_30m_virtual_amount": action_mark_decision.get("current_30m_virtual_amount"),
        "previous_day_same_window_amount": action_mark_decision.get("previous_day_same_window_amount"),
        "runtime_signal_status": runtime_signal_status,
        "minute_boundary_status": minute_boundary_status,
        "confirmation_status": confirmation_status,
        "action_state": action_state,
        "blocked_reason": blocked_reason,
        "condition_provenance": {
            "condition_keys": [condition_key] if condition_key else [],
            "original_condition_keys": [original_condition_key] if original_condition_key else [],
        },
    }
    if source_action_confirmation_metric_id:
        trace["source_action_confirmation_metric_id"] = source_action_confirmation_metric_id
    if source_projection_run_id:
        trace["source_projection_run_id"] = source_projection_run_id
    if (
        metric_evaluation.get("metric_fact_available")
        or metric_evaluation.get("source_action_confirmation_metric_id")
        or metric_evaluation.get("metric_scope_excluded")
    ):
        trace["action_confirmation_metric"] = {
            "source_action_confirmation_metric_id": metric_evaluation.get("source_action_confirmation_metric_id"),
            "projection_run_id": metric_evaluation.get("projection_run_id"),
            "projection_schema_version": metric_evaluation.get("projection_schema_version"),
            "metric_context_status": metric_evaluation.get("metric_context_status"),
            "metric_ready": metric_evaluation.get("metric_ready"),
            "metric_quality_status": metric_evaluation.get("metric_quality_status"),
            "metric_policy_status": metric_evaluation.get("metric_policy_status"),
            "virtual_amount_policy_version": metric_evaluation.get("virtual_amount_policy_version"),
            "metric_policy": metric_evaluation.get("metric_policy") or {},
            "metric_time": metric_evaluation.get("metric_time"),
            "metric_minute_label": metric_evaluation.get("metric_minute_label"),
            "current_price": metric_evaluation.get("current_price"),
            "current_30m_virtual_amount": metric_evaluation.get("current_30m_virtual_amount"),
            "previous_day_same_window_amount": metric_evaluation.get("previous_day_same_window_amount"),
            "previous_30m_full_amount": metric_evaluation.get("previous_30m_full_amount"),
            "metric_time_alignment_status": metric_evaluation.get("metric_time_alignment_status"),
            "metric_time_alignment": metric_evaluation.get("metric_time_alignment") or {},
            "selected_flags": metric_evaluation.get("selected_flags") or {},
            "all_period_confirmation_pass": metric_evaluation.get("all_period_confirmation_pass"),
            "source_fact_ids": metric_evaluation.get("source_fact_ids") or {},
            "metric_scope_excluded": metric_evaluation.get("metric_scope_excluded"),
            "metric_scope_excluded_reason": metric_evaluation.get("metric_scope_excluded_reason"),
        }
    for key in (
        "projection_30m_flag",
        "projection_30m_type",
        "projection_trace",
        "period_trigger_baseline_trace",
        "source_market_trace",
        "minute_context",
    ):
        if key in payload:
            trace[key] = payload[key]
    if "action_confirmation" in payload:
        trace["opaque_action_confirmation_trace_only"] = payload["action_confirmation"]
    return trace


def infer_action_type(source_trigger_event_type: str, direction: str) -> str:
    if source_trigger_event_type == "TriggerPendingMarketData":
        return "pending_market_data"
    if source_trigger_event_type == "TriggerStateChanged":
        return "state_gate"
    if direction == "buy":
        return "buy_candidate"
    if direction == "sell":
        return "sell_candidate"
    return "risk_candidate"


def infer_lane(*, asset_kind: str, signal_type: str, payload: Mapping[str, Any]) -> str:
    payload_lane = str(payload.get("lane") or "")
    if payload_lane in {"stock_trade", "stock_alert", "market_alert", "hint", "policy_pending"}:
        return payload_lane
    if asset_kind == "stock":
        return "policy_pending"
    return "policy_pending"


def infer_minute_context_status(
    *,
    closed_minute_required: bool,
    realtime_projection_confirmed: bool,
    payload: Mapping[str, Any],
    action_confirmation_metric_status: str = "",
) -> str:
    if not closed_minute_required:
        return "not_required"
    if action_confirmation_metric_status == "ready":
        return "closed"
    if action_confirmation_metric_status == "not_ready":
        return "missing"
    minute_context = payload.get("minute_context")
    if isinstance(minute_context, Mapping) and minute_context.get("is_closed") is False:
        return "unclosed"
    if payload.get("minute_context_closed") is False:
        return "unclosed"
    if realtime_projection_confirmed:
        return "closed"
    source_event_type = str(payload.get("source_event_type") or payload.get("synthetic_event_type") or "")
    if source_event_type in CLOSED_MINUTE_SOURCE_EVENT_TYPES:
        return "closed"
    if source_event_type in {"MarketDataDelayed", "MarketDataMissing"}:
        return "missing"
    return "unclosed"


def projection_trace_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    projection_trace = payload.get("projection_trace")
    if isinstance(projection_trace, Mapping) and projection_trace:
        return dict(projection_trace)
    source_market_trace = payload.get("source_market_trace")
    if isinstance(source_market_trace, Mapping):
        nested_projection_trace = source_market_trace.get("projection_trace")
        if isinstance(nested_projection_trace, Mapping) and nested_projection_trace:
            return dict(nested_projection_trace)
    return {}


def is_realtime_projection_confirmed(*, signal_type: str, payload: Mapping[str, Any]) -> bool:
    source_event_type = str(payload.get("source_event_type") or payload.get("synthetic_event_type") or "")
    data_quality_status = str(payload.get("data_quality_status") or "")
    if signal_type not in CANONICAL_RUNTIME_SIGNAL_TYPES:
        return False
    if source_event_type not in REALTIME_PROJECTION_SOURCE_EVENT_TYPES:
        return False
    if data_quality_status in {"missing", "delayed", "failed"}:
        return False
    return bool(projection_trace_from_payload(payload))


def infer_confirmation_source(
    *,
    source_trigger_event_type: str,
    minute_context_status: str,
    realtime_projection_confirmed: bool,
    metric_evaluation: Mapping[str, Any] | None = None,
) -> str:
    if source_trigger_event_type == "TriggerPendingMarketData":
        return "pending_market_data"
    metric = metric_evaluation or {}
    if metric.get("metric_fact_available"):
        return "n3_action_confirmation_metric"
    if metric.get("source_action_confirmation_metric_id") or (
        metric.get("metric_required") and metric.get("metric_context_status") == "missing"
    ):
        return "n3_action_confirmation_metric_missing"
    if realtime_projection_confirmed:
        return "realtime_projection_trace"
    if minute_context_status == "closed":
        return "closed_minute"
    if minute_context_status == "missing":
        return "missing_market_data"
    if minute_context_status == "unclosed":
        return "unclosed_minute"
    return "not_required"


def build_action_bucket(payload: Mapping[str, Any]) -> str:
    trigger_bucket = str(payload.get("trigger_bucket") or "")
    trigger_period = str(payload.get("trigger_period") or "")
    if trigger_bucket:
        return trigger_bucket
    if trigger_period == "30m":
        return "30m"
    return "trading_day"


def build_action_candidate_dedup_key(
    *,
    action_run_id: str,
    source_trigger_event_id: str,
    source_trigger_event_type: str,
    asset_kind: str,
    identity_key: str,
    direction: str,
    signal_type: str,
    condition_key: str,
    original_condition_key: str,
    trigger_period: str,
    action_state: str,
    action_mark_candidate: str,
    selected_metric_id: str | None = None,
    executed_metric_time: Any = None,
) -> str:
    parts = [
        "N5_action",
        action_run_id,
        source_trigger_event_type,
        source_trigger_event_id,
        asset_kind,
        identity_key,
        "direction",
        direction,
        "signal_type",
        signal_type,
        "condition_key",
        condition_key,
        "original_condition_key",
        original_condition_key,
        "trigger_period",
        trigger_period,
        "action_state",
        action_state,
        "action_mark_candidate",
        action_mark_candidate,
    ]
    if selected_metric_id:
        parts.extend(["selected_metric_id", selected_metric_id])
    if executed_metric_time:
        parts.extend(["executed_metric_time", executed_metric_time])
    return join_dedup_parts(*parts)


def build_action_confirmation_grain_key(
    *,
    trade_date: str,
    identity_key: str,
    signal_type: str,
    trigger_kind: str,
    original_condition_key: str,
    primary_trigger_period: str,
    trigger_mark_candidate: str,
    trigger_time: Any,
    selected_metric_id: str | None = None,
    executed_metric_time: Any = None,
) -> str:
    parts = [
        "N5_action_confirmation_grain_v1",
        "trade_date",
        trade_date,
        "identity_key",
        identity_key,
        "signal_type",
        signal_type,
        "trigger_kind",
        trigger_kind,
        "original_condition_key",
        original_condition_key,
        "primary_trigger_period",
        primary_trigger_period,
        "trigger_mark_candidate",
        trigger_mark_candidate,
        "trigger_time",
        trigger_time,
    ]
    if selected_metric_id:
        parts.extend(["selected_metric_id", selected_metric_id])
    if executed_metric_time:
        parts.extend(["executed_metric_time", executed_metric_time])
    return join_dedup_parts(*parts)


def build_action_confirmation_merge_key(
    *,
    trade_date: str,
    identity_key: str,
    signal_type: str,
    primary_trigger_period: str,
    trigger_mark_candidate: str,
    trigger_time: Any,
) -> str:
    return join_dedup_parts(
        "N5_action_confirmation_merge_grain_v1",
        "trade_date",
        trade_date,
        "identity_key",
        identity_key,
        "signal_type",
        signal_type,
        "primary_trigger_period",
        primary_trigger_period,
        "trigger_mark_candidate",
        trigger_mark_candidate,
        "trigger_time",
        trigger_time,
    )


def summarize_action_candidates(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    action_candidates = [row for row in candidates if row.get("candidate_kind") == "action_confirmation"]
    quality_plans = [row for row in candidates if row.get("candidate_kind") == "quality_plan"]
    state_gates = [row for row in candidates if row.get("candidate_kind") == "state_gate"]
    trigger_matched_candidates = [
        row for row in candidates if row.get("source_trigger_event_type") == "TriggerMatched"
    ]
    pending_candidates = [
        row for row in candidates if row.get("source_trigger_event_type") == "TriggerPendingMarketData"
    ]
    blocked_unclosed = [
        row
        for row in candidates
        if row.get("closed_minute_required")
        and row.get("minute_boundary_status") == "unclosed"
        and row.get("action_state") == "blocked"
    ]
    buy_hint_trace = [
        row
        for row in candidates
        if row.get("condition_key") == "BUY_HINT" or row.get("original_condition_key") == "BUY_HINT"
    ]
    sell_hint_trace = [
        row
        for row in candidates
        if row.get("condition_key") == "SELL_HINT" or row.get("original_condition_key") == "SELL_HINT"
    ]
    tracking_state_plan = build_action_tracking_state_plan(candidates)
    return {
        "candidate_count": len(candidates),
        "action_candidate_count": len(action_candidates),
        "action_confirmation_count": len(action_candidates),
        "quality_plan_count": len(quality_plans),
        "state_gate_count": len(state_gates),
        "trigger_matched_action_candidate_count": len(trigger_matched_candidates),
        "pending_quality_plan_count": len(pending_candidates),
        "by_source_trigger_event_type": count_by(candidates, "source_trigger_event_type"),
        "by_planned_output_event_type": count_by(
            [row for row in candidates if row.get("planned_output_event_type")],
            "planned_output_event_type",
        ),
        "by_asset_kind": count_by(candidates, "asset_kind"),
        "by_direction": count_by(candidates, "direction"),
        "by_signal_type": count_by(candidates, "signal_type"),
        "by_action_type": count_by(candidates, "action_type"),
        "by_lane": count_by(candidates, "lane"),
        "by_decision_status": count_by(candidates, "decision_status"),
        "by_action_state": count_by(candidates, "action_state"),
        "by_confirmation_status": count_by(candidates, "confirmation_status"),
        "tracking_state_plan": summarize_action_tracking_state_plan(tracking_state_plan),
        "buy_hint_candidate_count": sum(1 for row in action_candidates if row in buy_hint_trace),
        "sell_hint_candidate_count": sum(1 for row in action_candidates if row in sell_hint_trace),
        "buy_hint_trace_count": len(buy_hint_trace),
        "sell_hint_trace_count": len(sell_hint_trace),
        "deprecated_runtime_signal_type_count": sum(
            1 for row in candidates if row.get("runtime_signal_status") == "deprecated_runtime_signal_type"
        ),
        "deprecated_hint_event_plan_count": sum(
            1 for row in candidates if row.get("planned_output_event_type") == "HintEvent"
        ),
        "pending_generates_action_event_count": sum(
            1 for row in pending_candidates if row.get("planned_output_event_type")
        ),
        "unclosed_minute_blocked_count": len(blocked_unclosed),
        "unclosed_minute_generates_action_event_count": sum(
            1 for row in blocked_unclosed if row.get("planned_output_event_type") == "ActionExecuted"
        ),
        "unclosed_minute_generates_action_executed_count": sum(
            1 for row in blocked_unclosed if row.get("planned_output_event_type") == "ActionExecuted"
        ),
        "would_write_db_count": sum(1 for row in candidates if row.get("would_write_db")),
        "would_update_checkpoint_count": sum(
            1 for row in candidates if row.get("would_update_consumer_checkpoint")
        ),
        "would_write_user_voice_sim_count": sum(
            1
            for row in candidates
            if row.get("would_write_user_projection") or row.get("would_write_voice") or row.get("would_write_sim")
        ),
        "would_submit_real_trade_count": sum(1 for row in candidates if row.get("would_submit_real_trade")),
    }


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def list_forbidden_candidate_outputs(candidates: Sequence[Mapping[str, Any]]) -> list[str]:
    forbidden: set[str] = set()
    for candidate in candidates:
        event_type = str(candidate.get("planned_output_event_type") or "")
        if event_type.startswith(NON_ACTION_EVENT_PREFIXES):
            forbidden.add(event_type)
    return sorted(forbidden)
