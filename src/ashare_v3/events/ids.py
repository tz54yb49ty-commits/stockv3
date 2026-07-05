"""Stable event id and dedup key helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


EVENT_ID_PREFIX = "evt"


def canonical_json(value: Mapping[str, Any] | list[Any] | tuple[Any, ...] | str | int | float | bool | None) -> str:
    """Return a deterministic JSON string for hashing and comparisons."""

    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(value: str, *, length: int = 32) -> str:
    """Return a deterministic sha256 hex digest prefix."""

    if length <= 0 or length > 64:
        raise ValueError("length must be between 1 and 64")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def build_stable_event_id(
    *,
    source_layer: str,
    event_type: str,
    source_run_id: str,
    dedup_key: str,
    event_schema_version: str,
) -> str:
    """Build an idempotent event_id from the stable cross-layer identity."""

    raw = canonical_json(
        {
            "source_layer": source_layer,
            "event_type": event_type,
            "source_run_id": source_run_id,
            "dedup_key": dedup_key,
            "event_schema_version": event_schema_version,
        }
    )
    return f"{EVENT_ID_PREFIX}_{stable_hash(raw, length=40)}"


def join_dedup_parts(*parts: str | int | None) -> str:
    """Join already-normalized dedup parts into a stable text key."""

    normalized: list[str] = []
    for part in parts:
        if part is None:
            raise ValueError("dedup key parts cannot be None")
        text = str(part).strip()
        if not text:
            raise ValueError("dedup key parts cannot be empty")
        normalized.append(text)
    return "|".join(normalized)


def build_n3_dedup_key(
    *,
    event_type: str,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    source_adapter: str,
    event_schema_version: str = "v1",
    snapshot_time: str | None = None,
    minute_bar_time: str | None = None,
    required_data_kind: str | None = None,
    status_kind: str | None = None,
    display_time: str | None = None,
    c2_run_id: str | None = None,
    summary_id: str | int | None = None,
    bucket_id: str | None = None,
) -> str:
    """Build the N3 event dedup_key using the documented per-event rules."""

    prefix = ("N3_market_data", event_type, asset_kind, identity_key, trade_date)
    if event_type == "MarketSnapshotUpdated":
        return join_dedup_parts(*prefix, "snapshot_time", snapshot_time, "source_adapter", source_adapter)
    if event_type == "MinuteBarClosed" and event_schema_version == "v2":
        return join_dedup_parts(
            *prefix,
            "c2_run_id",
            c2_run_id,
            "summary_id",
            summary_id,
            "bucket_id",
            bucket_id,
            "event_schema_version",
            event_schema_version,
        )
    if event_type in {"MinuteBarClosed", "MinuteBarCorrected"}:
        return join_dedup_parts(*prefix, "minute_bar_time", minute_bar_time, "source_adapter", source_adapter)
    if event_type in {"MarketDataDelayed", "MarketDataMissing"}:
        return join_dedup_parts(
            *prefix,
            "required_data_kind",
            required_data_kind,
            "status_kind",
            status_kind,
            "source_adapter",
            source_adapter,
        )
    if event_type == "MarketDisplaySnapshotUpdated":
        return join_dedup_parts(*prefix, "display_time", display_time, "source_adapter", source_adapter)
    raise ValueError(f"unsupported N3 event_type: {event_type}")


def build_n4_trigger_dedup_key(
    *,
    event_type: str,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    direction: str,
    signal_type: str,
    condition_key: str,
    trigger_bucket: str,
) -> str:
    """Build the N4 trigger event dedup_key using the documented trigger grain."""

    return join_dedup_parts(
        "N4_trigger",
        event_type,
        asset_kind,
        identity_key,
        trade_date,
        "direction",
        direction,
        "signal_type",
        signal_type,
        "condition_key",
        condition_key,
        "trigger_bucket",
        trigger_bucket,
    )


def build_n4_trigger_state_changed_dedup_key(
    *,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    direction: str,
    signal_type: str,
    condition_key: str,
    trigger_bucket: str,
    trigger_mark_candidate: str,
    previous_status: str | None,
    current_status: str,
    previous_trigger_live: bool,
    trigger_live: bool,
    previous_primary_trigger_period: str | None,
    primary_trigger_period: str | None,
    previous_all_trigger_periods: object,
    all_trigger_periods: object,
    state_change_reason: str,
    source_outcome_event_id: str | None,
) -> str:
    """Build a state-transition dedup key distinct from outcome event keys."""

    return join_dedup_parts(
        "N4_trigger",
        "TriggerStateChanged",
        asset_kind,
        identity_key,
        trade_date,
        "direction",
        direction,
        "signal_type",
        signal_type,
        "condition_key",
        condition_key,
        "trigger_bucket",
        trigger_bucket,
        "trigger_mark_candidate",
        trigger_mark_candidate,
        "previous_status",
        _normalize_optional(previous_status),
        "current_status",
        current_status,
        "previous_trigger_live",
        str(bool(previous_trigger_live)).lower(),
        "trigger_live",
        str(bool(trigger_live)).lower(),
        "previous_primary_trigger_period",
        _normalize_optional(previous_primary_trigger_period),
        "primary_trigger_period",
        _normalize_optional(primary_trigger_period),
        "previous_all_trigger_periods",
        _normalize_period_collection(previous_all_trigger_periods),
        "all_trigger_periods",
        _normalize_period_collection(all_trigger_periods),
        "state_change_reason",
        state_change_reason,
        "source_outcome_event_id",
        _normalize_optional(source_outcome_event_id),
    )


def _normalize_period_collection(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, str):
        return value or "none"
    try:
        return ",".join(str(part) for part in value) or "none"  # type: ignore[operator]
    except TypeError:
        return str(value)


def _normalize_optional(value: object) -> str:
    if value is None:
        return "none"
    text = str(value).strip()
    return text or "none"
