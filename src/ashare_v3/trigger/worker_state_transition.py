"""Pure N4 worker state transition and idempotency helpers.

These helpers intentionally do not perform database I/O.  They describe the
bounded worker smoke semantics that later execute gates can persist safely.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ashare_v3.events.ids import join_dedup_parts


CANONICAL_TRIGGER_STATES = ("inactive", "pending_market_data", "matched")
FORMAL_PERIOD_PRIORITY = ("Y", "Q", "M", "W", "D")


class N4WorkerStateTransitionError(ValueError):
    """Raised when a worker state transition request is malformed."""


def source_event_consume_key(consumer_name: str, source_event_id: str) -> str:
    return join_dedup_parts(consumer_name, source_event_id)


def trigger_state_key(
    *,
    trade_date: str,
    asset_kind: str,
    identity_key: str,
    direction: str,
    signal_type: str,
    condition_key: str,
) -> str:
    return join_dedup_parts(trade_date, asset_kind, identity_key, direction, signal_type, condition_key)


def trigger_match_dedup_key(
    *,
    trade_date: str,
    asset_kind: str,
    identity_key: str,
    direction: str,
    signal_type: str,
    condition_key: str,
    primary_trigger_period: str | None,
    trigger_mark_candidate: str,
    match_basis: str,
    source_market_event_or_projection_id: str,
) -> str:
    return join_dedup_parts(
        "TriggerMatched",
        trade_date,
        asset_kind,
        identity_key,
        direction,
        signal_type,
        condition_key,
        _optional(primary_trigger_period),
        trigger_mark_candidate,
        match_basis,
        source_market_event_or_projection_id,
    )


def trigger_pending_dedup_key(
    *,
    trade_date: str,
    asset_kind: str,
    identity_key: str,
    direction: str,
    signal_type: str,
    condition_key: str,
    expected_primary_trigger_period: str | None,
    trigger_mark_candidate: str,
    missing_evidence_kind: str,
    source_market_event_or_projection_id: str,
) -> str:
    return join_dedup_parts(
        "TriggerPendingMarketData",
        trade_date,
        asset_kind,
        identity_key,
        direction,
        signal_type,
        condition_key,
        _optional(expected_primary_trigger_period),
        trigger_mark_candidate,
        missing_evidence_kind,
        source_market_event_or_projection_id,
    )


def trigger_state_changed_dedup_key(
    *,
    state_key: str,
    previous_status: str | None,
    current_status: str,
    previous_trigger_live: bool,
    trigger_live: bool,
    previous_primary_trigger_period: str | None,
    primary_trigger_period: str | None,
    previous_projection_30m_type: str | None,
    projection_30m_type: str | None,
    state_change_reason: str,
    source_event_id: str,
) -> str:
    return join_dedup_parts(
        "TriggerStateChanged",
        state_key,
        "previous_status",
        _optional(previous_status),
        "current_status",
        current_status,
        "previous_trigger_live",
        str(bool(previous_trigger_live)).lower(),
        "trigger_live",
        str(bool(trigger_live)).lower(),
        "previous_primary_trigger_period",
        _optional(previous_primary_trigger_period),
        "primary_trigger_period",
        _optional(primary_trigger_period),
        "previous_projection_30m_type",
        _optional(previous_projection_30m_type),
        "projection_30m_type",
        _optional(projection_30m_type),
        "state_change_reason",
        state_change_reason,
        "source_event_id",
        source_event_id,
    )


def build_transition_event_plans(
    *,
    previous_state: Mapping[str, Any] | None,
    current_evaluation: Mapping[str, Any],
    source_event_id: str,
    trade_date: str,
) -> list[dict[str, Any]]:
    """Return outcome/state-change event plans for a single state evaluation."""

    previous = _normalize_state(previous_state)
    current = _normalize_state(current_evaluation)
    state_key = trigger_state_key(
        trade_date=trade_date,
        asset_kind=str(current["asset_kind"]),
        identity_key=str(current["identity_key"]),
        direction=str(current["direction"]),
        signal_type=str(current["signal_type"]),
        condition_key=str(current["condition_key"]),
    )

    plans: list[dict[str, Any]] = []
    output_event_type = current_evaluation.get("output_event_type")
    new_trigger_fact = bool(current_evaluation.get("new_trigger_fact", output_event_type == "TriggerMatched"))

    if output_event_type == "TriggerMatched" and new_trigger_fact:
        plans.append(_build_matched_plan(current_evaluation, current=current, trade_date=trade_date, source_event_id=source_event_id))
    elif output_event_type == "TriggerPendingMarketData":
        plans.append(_build_pending_plan(current_evaluation, current=current, trade_date=trade_date, source_event_id=source_event_id))

    state_change_reason = classify_state_change(previous, current)
    if state_change_reason:
        plans.append(
            _build_state_changed_plan(
                current_evaluation,
                previous=previous,
                current=current,
                trade_date=trade_date,
                source_event_id=source_event_id,
                state_key=state_key,
                state_change_reason=state_change_reason,
                source_outcome_event_type=plans[0]["output_event_type"] if plans else None,
                source_outcome_event_id=plans[0]["dedup_key"] if plans else None,
            )
        )
    return plans


def classify_state_change(previous: Mapping[str, Any], current: Mapping[str, Any]) -> str | None:
    previous_status = str(previous["current_status"])
    current_status = str(current["current_status"])
    if previous_status != current_status:
        if current_status == "matched":
            return "activated"
        if current_status == "inactive":
            return "deactivated"
        return "status_changed"

    if bool(previous["trigger_live"]) != bool(current["trigger_live"]):
        return "trigger_live_changed"

    previous_period = previous.get("primary_trigger_period")
    current_period = current.get("primary_trigger_period")
    if previous_period != current_period or _periods(previous.get("all_trigger_periods")) != _periods(current.get("all_trigger_periods")):
        return _period_change_reason(previous_period, current_period)

    if (
        bool(previous.get("projection_30m_flag"))
        != bool(current.get("projection_30m_flag"))
        or str(previous.get("projection_30m_type") or "none") != str(current.get("projection_30m_type") or "none")
        or str(previous.get("trigger_mark_candidate") or "normal") != str(current.get("trigger_mark_candidate") or "normal")
    ):
        return "projection_state_changed"

    if str(previous.get("data_quality_status") or "") != str(current.get("data_quality_status") or ""):
        return "quality_changed"

    if _optional(previous.get("source_trace_hash")) != _optional(current.get("source_trace_hash")):
        return "source_trace_changed"

    return None


def _build_matched_plan(
    evaluation: Mapping[str, Any],
    *,
    current: Mapping[str, Any],
    trade_date: str,
    source_event_id: str,
) -> dict[str, Any]:
    dedup_key = trigger_match_dedup_key(
        trade_date=trade_date,
        asset_kind=str(current["asset_kind"]),
        identity_key=str(current["identity_key"]),
        direction=str(current["direction"]),
        signal_type=str(current["signal_type"]),
        condition_key=str(current["condition_key"]),
        primary_trigger_period=current.get("primary_trigger_period"),
        trigger_mark_candidate=str(current.get("trigger_mark_candidate") or "normal"),
        match_basis=str(evaluation.get("match_basis") or "unknown"),
        source_market_event_or_projection_id=str(evaluation.get("source_market_event_or_projection_id") or source_event_id),
    )
    return {
        **dict(evaluation),
        **dict(current),
        "output_event_type": "TriggerMatched",
        "dedup_key": dedup_key,
        "source_event_id": source_event_id,
        "writes_common_trigger_match": True,
        "is_n5_action_entry": True,
        "n5_entry_allowed": True,
        "trigger_live": True,
        "current_status": "matched",
    }


def _build_pending_plan(
    evaluation: Mapping[str, Any],
    *,
    current: Mapping[str, Any],
    trade_date: str,
    source_event_id: str,
) -> dict[str, Any]:
    dedup_key = trigger_pending_dedup_key(
        trade_date=trade_date,
        asset_kind=str(current["asset_kind"]),
        identity_key=str(current["identity_key"]),
        direction=str(current["direction"]),
        signal_type=str(current["signal_type"]),
        condition_key=str(current["condition_key"]),
        expected_primary_trigger_period=current.get("primary_trigger_period"),
        trigger_mark_candidate=str(current.get("trigger_mark_candidate") or "normal"),
        missing_evidence_kind=str(evaluation.get("missing_evidence_kind") or "market_data_missing"),
        source_market_event_or_projection_id=str(evaluation.get("source_market_event_or_projection_id") or source_event_id),
    )
    return {
        **dict(evaluation),
        **dict(current),
        "output_event_type": "TriggerPendingMarketData",
        "dedup_key": dedup_key,
        "source_event_id": source_event_id,
        "writes_common_trigger_match": False,
        "is_n5_action_entry": False,
        "n5_entry_allowed": False,
        "trigger_live": False,
        "current_status": "pending_market_data",
    }


def _build_state_changed_plan(
    evaluation: Mapping[str, Any],
    *,
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
    trade_date: str,
    source_event_id: str,
    state_key: str,
    state_change_reason: str,
    source_outcome_event_type: str | None,
    source_outcome_event_id: str | None,
) -> dict[str, Any]:
    dedup_key = trigger_state_changed_dedup_key(
        state_key=state_key,
        previous_status=previous.get("current_status"),
        current_status=str(current["current_status"]),
        previous_trigger_live=bool(previous.get("trigger_live")),
        trigger_live=bool(current.get("trigger_live")),
        previous_primary_trigger_period=previous.get("primary_trigger_period"),
        primary_trigger_period=current.get("primary_trigger_period"),
        previous_projection_30m_type=previous.get("projection_30m_type"),
        projection_30m_type=current.get("projection_30m_type"),
        state_change_reason=state_change_reason,
        source_event_id=source_event_id,
    )
    return {
        **dict(evaluation),
        **dict(current),
        "output_event_type": "TriggerStateChanged",
        "dedup_key": dedup_key,
        "source_event_id": source_event_id,
        "previous_status": previous.get("current_status"),
        "previous_trigger_live": bool(previous.get("trigger_live")),
        "previous_primary_trigger_period": previous.get("primary_trigger_period"),
        "previous_all_trigger_periods": _periods(previous.get("all_trigger_periods")),
        "previous_projection_30m_flag": bool(previous.get("projection_30m_flag")),
        "previous_projection_30m_type": previous.get("projection_30m_type") or "none",
        "previous_trigger_mark_candidate": previous.get("trigger_mark_candidate") or "normal",
        "state_change_reason": state_change_reason,
        "source_outcome_event_type": source_outcome_event_type,
        "source_outcome_event_id": source_outcome_event_id,
        "writes_common_trigger_match": False,
        "is_n5_action_entry": False,
        "n5_entry_allowed": False,
        "trade_date": trade_date,
    }


def _normalize_state(row: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(row or {})
    output_event_type = source.get("output_event_type")
    current_status = source.get("current_status")
    if not current_status:
        if output_event_type == "TriggerMatched":
            current_status = "matched"
        elif output_event_type == "TriggerPendingMarketData":
            current_status = "pending_market_data"
        else:
            current_status = "inactive"
    current_status = str(current_status)
    if current_status not in CANONICAL_TRIGGER_STATES:
        raise N4WorkerStateTransitionError(f"unsupported current_status: {current_status}")
    return {
        "trade_date": source.get("trade_date"),
        "asset_kind": source.get("asset_kind", ""),
        "identity_key": source.get("identity_key", ""),
        "direction": source.get("direction", ""),
        "signal_type": source.get("signal_type", ""),
        "condition_key": source.get("condition_key", ""),
        "current_status": current_status,
        "trigger_live": bool(source.get("trigger_live")) if "trigger_live" in source else current_status == "matched",
        "primary_trigger_period": source.get("primary_trigger_period"),
        "all_trigger_periods": _periods(source.get("all_trigger_periods")),
        "projection_30m_flag": bool(source.get("projection_30m_flag", False)),
        "projection_30m_type": source.get("projection_30m_type") or "none",
        "trigger_mark_candidate": source.get("trigger_mark_candidate") or "normal",
        "data_quality_status": source.get("data_quality_status") or "passed",
        "source_trace_hash": source.get("source_trace_hash"),
    }


def _period_change_reason(previous: object, current: object) -> str:
    if previous is None and current is not None:
        return "period_activated"
    if current is None:
        return "period_cleared"
    previous_rank = _period_rank(previous)
    current_rank = _period_rank(current)
    if current_rank < previous_rank:
        return "period_upgrade"
    if current_rank > previous_rank:
        return "period_downgrade"
    return "period_set_changed"


def _period_rank(value: object) -> int:
    text = str(value)
    if text not in FORMAL_PERIOD_PRIORITY:
        return len(FORMAL_PERIOD_PRIORITY)
    return FORMAL_PERIOD_PRIORITY.index(text)


def _periods(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Sequence):
        return [str(part) for part in value if str(part)]
    return [str(value)]


def _optional(value: object) -> str:
    if value is None:
        return "none"
    text = str(value).strip()
    return text or "none"
