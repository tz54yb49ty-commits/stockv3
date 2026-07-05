"""Matched-only combined N4 execute helpers.

This module combines ordinary B1 snapshot trigger matches with B2 projection
matches, then exposes only valid TriggerMatched rows for N5 entry.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from ashare_v3.condition.basis import quality_item
from ashare_v3.trigger.canonical_signal import CANONICAL_SIGNAL_TYPES


class CombinedExecuteBlocked(RuntimeError):
    """Raised when combined matched-only execute must stop before DB writes."""


def assert_combined_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise CombinedExecuteBlocked(
            "N4 20260605 matched-only combined execute blocked before writes: missing "
            + ", ".join(missing)
        )


def build_combined_matched_only_write_plan(
    *,
    local_plans: Sequence[Mapping[str, Any]],
    projection_plans: Sequence[Mapping[str, Any]],
    execute_run_id: str,
    trigger_context_run_id: str,
    snapshot_run_id: str,
    projection_run_id: str,
) -> dict[str, Any]:
    """Build a write plan that persists only valid TriggerMatched rows."""

    local_candidates = [dict(plan) for plan in local_plans]
    projection_candidates = [dict(plan) for plan in projection_plans]
    all_candidates = local_candidates + projection_candidates
    matched_candidates = [
        dict(plan)
        for plan in all_candidates
        if plan.get("output_event_type") == "TriggerMatched"
    ]
    invalid_n5_entry_plans = [
        plan for plan in matched_candidates if not is_valid_combined_n5_entry(plan)
    ]
    matched_write_plans = [
        normalize_combined_matched_plan(
            plan,
            snapshot_run_id=snapshot_run_id,
            projection_run_id=projection_run_id,
        )
        for plan in matched_candidates
        if is_valid_combined_n5_entry(plan)
    ]
    event_counts = Counter(str(plan.get("output_event_type")) for plan in matched_write_plans)
    matched_by_basis = Counter(str(plan.get("match_basis") or "unknown") for plan in matched_write_plans)
    matched_by_signal = Counter(str(plan.get("signal_type") or "") for plan in matched_write_plans)
    matched_by_mark = Counter(str(plan.get("trigger_mark_candidate") or "") for plan in matched_write_plans)
    suppressed = Counter(
        str(plan.get("output_event_type") or plan.get("plan_status") or "not_matched")
        for plan in all_candidates
        if plan not in matched_candidates
    )
    return {
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "snapshot_run_id": snapshot_run_id,
        "projection_run_id": projection_run_id,
        "outcome_persistence_strategy": "v4_matched_only_combined_b1_b2",
        "input_plan_count": len(all_candidates),
        "local_input_plan_count": len(local_candidates),
        "projection_input_plan_count": len(projection_candidates),
        "matched_candidate_count": len(matched_candidates),
        "persisted_plan_count": len(matched_write_plans),
        "invalid_n5_entry_count": len(invalid_n5_entry_plans),
        "invalid_n5_entry_samples": invalid_n5_entry_plans[:10],
        "suppressed_counts": dict(suppressed),
        "matched_by_basis": dict(sorted(matched_by_basis.items())),
        "matched_by_signal_type": dict(sorted(matched_by_signal.items())),
        "matched_by_trigger_mark_candidate": dict(sorted(matched_by_mark.items())),
        "write_counts": {
            "common_trigger_run": 1,
            "common_trigger_quality_item": "quality rows only",
            "common_trigger_state": len(matched_write_plans),
            "common_trigger_match": len(matched_write_plans),
            "common_event_outbox": len(matched_write_plans),
            "TriggerMatched": int(event_counts.get("TriggerMatched") or 0),
            "TriggerPendingMarketData": 0,
            "TriggerStateChanged": 0,
        },
        "pending_market_data_enters_n5": False,
        "trigger_state_changed_enters_n5": False,
        "not_matched_enters_n5": False,
        "quality_visible_enters_n5": False,
        "old_outbox_consuming_projection_execute_route_used": False,
        "matched_write_plan_samples": matched_write_plans[:10],
        "matched_write_plans": matched_write_plans,
    }


def build_combined_quality_items(write_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    invalid_count = int(write_plan.get("invalid_n5_entry_count") or 0)
    pending_writes = int((write_plan.get("write_counts") or {}).get("TriggerPendingMarketData") or 0)
    state_change_writes = int((write_plan.get("write_counts") or {}).get("TriggerStateChanged") or 0)
    old_route_used = bool(write_plan.get("old_outbox_consuming_projection_execute_route_used"))
    return [
        quality_item(
            "P0",
            "passed" if invalid_count == 0 else "failed",
            "n4_20260605_invalid_n5_entry_zero",
            "Combined matched-only execute must expose zero invalid N5 entries",
            expected="0",
            actual=str(invalid_count),
        ),
        quality_item(
            "P0",
            "passed" if pending_writes == 0 else "failed",
            "n4_20260605_no_pending_market_data_writes",
            "Matched-only execute must not write TriggerPendingMarketData",
            expected="0",
            actual=str(pending_writes),
        ),
        quality_item(
            "P0",
            "passed" if state_change_writes == 0 else "failed",
            "n4_20260605_no_trigger_state_changed_writes",
            "Matched-only execute must not write TriggerStateChanged",
            expected="0",
            actual=str(state_change_writes),
        ),
        quality_item(
            "P0",
            "passed" if not old_route_used else "failed",
            "n4_20260605_no_old_projection_execute_route",
            "Combined execute must not use the old outbox-consuming projection matcher execute route",
            expected="false",
            actual=str(old_route_used).lower(),
        ),
    ]


def is_valid_combined_n5_entry(plan: Mapping[str, Any]) -> bool:
    return (
        plan.get("output_event_type") == "TriggerMatched"
        and plan.get("signal_type") in CANONICAL_SIGNAL_TYPES
        and plan.get("current_status") == "matched"
        and plan.get("trigger_live") is True
        and plan.get("n5_entry_allowed") is True
    )


def normalize_combined_matched_plan(
    plan: Mapping[str, Any],
    *,
    snapshot_run_id: str,
    projection_run_id: str,
) -> dict[str, Any]:
    normalized = dict(plan)
    match_basis = str(normalized.get("match_basis") or "")
    projection_trace = normalized.get("projection_trace") if isinstance(normalized.get("projection_trace"), Mapping) else {}
    source_snapshot_run_id = (
        normalized.get("source_snapshot_run_id")
        or projection_trace.get("source_snapshot_run_id")
        or snapshot_run_id
    )
    trigger_mark = str(normalized.get("trigger_mark_candidate") or "normal")
    if trigger_mark == "30m_volume":
        projection_30m_type = "volume_up"
    elif trigger_mark == "30m_shrink":
        projection_30m_type = "shrink_down"
    else:
        projection_30m_type = str(normalized.get("projection_30m_type") or "none")
    normalized.update(
        {
            "output_event_type": "TriggerMatched",
            "plan_status": "matched",
            "current_status": "matched",
            "trigger_live": True,
            "n5_entry_allowed": True,
            "source_snapshot_run_id": source_snapshot_run_id,
            "projection_run_id": normalized.get("projection_run_id") or (
                projection_run_id if match_basis == "intraday_projection" else None
            ),
            "projection_30m_flag": trigger_mark in {"30m_volume", "30m_shrink"},
            "projection_30m_type": projection_30m_type,
            "data_quality_status": str(normalized.get("data_quality_status") or "passed"),
            "match_basis": match_basis or "realtime_snapshot",
        }
    )
    if not normalized.get("source_event_id"):
        normalized["source_event_id"] = (
            f"fact_only:{source_snapshot_run_id}:{normalized.get('asset_kind')}:"
            f"{normalized.get('identity_key')}:{normalized.get('signal_type')}:"
            f"{trigger_mark}"
        )
    if not normalized.get("source_event_type"):
        normalized["source_event_type"] = "MarketSnapshotUpdated"
    if not normalized.get("trigger_period"):
        normalized["trigger_period"] = "30m" if trigger_mark in {"30m_volume", "30m_shrink"} else "D"
    if not normalized.get("trigger_bucket"):
        normalized["trigger_bucket"] = (
            str(normalized.get("projection_window_id") or "projection_window")
            if normalized["trigger_period"] == "30m"
            else "trading_day"
        )
    return normalized
