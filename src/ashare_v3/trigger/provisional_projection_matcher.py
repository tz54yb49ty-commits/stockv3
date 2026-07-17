"""N4 provisional B2 projection matcher dry-run.

This module is intentionally plan-only. It evaluates N4 localized context rows
against N3 realtime projection metric rows and never consumes events or writes
trigger facts.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Mapping, Sequence

from ashare_v3.events.ids import stable_hash
from ashare_v3.trigger.canonical_signal import canonicalize_trigger_candidate
from ashare_v3.trigger.projection_matcher import (
    HINT_1M_PROOF_KIND,
    PROJECTION_PERIOD,
    extract_standard_hint_projection_proof,
    latest_projection_by_identity,
    normalize_context_row,
    projection_confirmed_time,
    projection_is_ready,
    projection_signal_type_for_context,
    projection_trigger_price,
)
from ashare_v3.trigger.rule_v4_matcher import condition_signal_type_for_condition_key, projection_30m_flags


PROJECTION_AMOUNT_ALIAS_POLICY = "b2_live_current_legacy_amount_alias_v1"


def build_provisional_projection_matcher_plans(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    context_rows: Sequence[Mapping[str, Any]],
    projection_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    projection_lookup = latest_projection_by_identity(projection_rows, projection_run_id=projection_run_id)
    plans: list[dict[str, Any]] = []
    for raw_row in context_rows:
        row = normalize_context_row(raw_row)
        if row.get("run_id") != trigger_context_run_id:
            continue
        signal_type = projection_signal_type_for_context(row)
        if signal_type not in {"BUY_HINT", "SELL_HINT"}:
            continue
        if str(row.get("asset_kind") or "") == "stock":
            plans.append(
                build_provisional_projection_plan(
                    row=row,
                    projection={},
                    projection_run_id=projection_run_id,
                    legacy_signal_type=signal_type,
                    not_applicable_reason="stock HINT is not applicable under N4 index/board-only HINT rule",
                )
            )
            continue
        projection = projection_lookup.get((str(row.get("asset_kind") or ""), str(row.get("identity_key") or "")))
        plans.append(
            build_provisional_projection_plan(
                row=row,
                projection=projection or {},
                projection_run_id=projection_run_id,
                legacy_signal_type=signal_type,
            )
        )
    return plans


def build_provisional_projection_plan(
    *,
    row: Mapping[str, Any],
    projection: Mapping[str, Any],
    projection_run_id: str,
    legacy_signal_type: str,
    not_applicable_reason: str | None = None,
) -> dict[str, Any]:
    condition_projection_fields = {
        "condition_projection_context": (
            row.get("condition_projection_context")
            if row.get("condition_projection_context") is not None
            else {}
        ),
        "condition_projection_context_status": row.get("condition_projection_context_status") or "not_ready",
        "condition_projection_context_trace": dict(row.get("condition_projection_context_trace") or {}),
    }
    if not_applicable_reason:
        mapping = canonicalize_trigger_candidate(
            str(row.get("condition_key") or ""),
            candidate_signal_type=legacy_signal_type,
            projection_30m_type="none",
        )
        raw_plan_id = "|".join(
            [
                projection_run_id,
                "projection_not_applicable",
                str(row.get("asset_kind") or ""),
                str(row.get("identity_key") or ""),
                legacy_signal_type,
                mapping.signal_type,
                mapping.trigger_mark_candidate,
                str(row.get("condition_key") or ""),
                "no_op",
            ]
        )
        return {
            "plan_id": stable_hash(raw_plan_id, length=32),
            "plan_status": "no_op",
            "output_event_type": None,
            "trigger_context_run_id": row.get("run_id"),
            "projection_run_id": projection_run_id,
            "projection_id": None,
            "source_projection_id": None,
            "asset_kind": str(row.get("asset_kind") or ""),
            "identity_key": str(row.get("identity_key") or ""),
            **condition_projection_fields,
            "direction": str(row.get("direction") or ""),
            "signal_type": mapping.signal_type,
            "runtime_signal_type": mapping.signal_type,
            "condition_signal_type": condition_signal_type_for_condition_key(
                str(row.get("condition_key") or ""),
                direction=str(row.get("direction") or ""),
                condition_family="hint",
            ),
            "condition_key": str(row.get("condition_key") or ""),
            "original_condition_key": mapping.original_condition_key,
            "legacy_signal_type": legacy_signal_type,
            "match_basis": "intraday_projection",
            "trigger_mark_candidate": mapping.trigger_mark_candidate,
            "trigger_period": None,
            "trigger_price": None,
            "trigger_time": None,
            "event_time": None,
            "trigger_live": False,
            "current_status": "no_op",
            "n5_entry_allowed": False,
            "projection_period": PROJECTION_PERIOD,
            "projection_30m_flag": False,
            "projection_30m_type": "none",
            "projection_30m_amount_source": "not_applicable",
            "projection_30m_reference_source": "not_applicable",
            "projection_amount_alias_policy": PROJECTION_AMOUNT_ALIAS_POLICY,
            "projection_30m_volume_up_flag": False,
            "projection_30m_shrink_down_flag": False,
            "projection_signal_status": "not_applicable",
            "source_projection_proof_run_id": None,
            "source_projection_proof_metric_id": None,
            "source_projection_proof_time": None,
            "not_n5_final_proof": False,
            "projection_proof_kind": None,
            "projection_proof_valid": False,
            "projection_proof_missing_or_invalid_fields": [],
            "projection_status": "not_applicable",
            "projection_quality_status": "not_applicable",
            "trace_status": "not_applicable",
            "projection_window_id": None,
            "projection_trace": {"not_applicable_reason": not_applicable_reason},
            "dry_run_reason": not_applicable_reason,
        }
    projection_signal_status = str(projection.get("projection_signal_status") or "missing")
    proof = extract_standard_hint_projection_proof(projection) if projection else {}
    is_hint_v2_projection = projection.get("proof_kind") == HINT_1M_PROOF_KIND if projection else False
    hint_v2_event_time = hint_v2_projection_event_time(projection) if is_hint_v2_projection else None
    missing_hint_v2_iso_event_time = is_hint_v2_projection and not hint_v2_event_time
    if missing_hint_v2_iso_event_time:
        missing_fields = set(proof.get("missing_or_invalid_fields") or [])
        missing_fields.add("source_projection_proof_time")
        proof = {
            **proof,
            "valid": False,
            "missing_or_invalid_fields": sorted(missing_fields),
        }
    elif hint_v2_event_time:
        proof = {
            **proof,
            "source_projection_proof_time": hint_v2_event_time,
        }
    proof_valid = bool(proof.get("valid"))
    ready = bool(projection and projection_is_ready(projection) and proof_valid)
    amount_trace = (
        provisional_projection_30m_amount_trace(projection)
        if projection and proof_valid
        else missing_projection_amount_trace()
    )
    projection_30m_type = str(amount_trace["projection_30m_type"])
    matched = ready and projection_matches_atomic_type(legacy_signal_type, projection_30m_type)
    mapping = canonicalize_trigger_candidate(
        str(row.get("condition_key") or ""),
        candidate_signal_type=legacy_signal_type,
        projection_30m_type=projection_30m_type if matched else "none",
    )
    projection_30m_flag = projection_30m_type in {"volume_up", "shrink_down"}
    source_trace = projection_source_trace(projection)
    volume_up_flag, shrink_down_flag = projection_30m_flags(
        projection_30m_type,
        projection_30m_flag=projection_30m_flag,
    )
    pending = bool(projection) and not missing_hint_v2_iso_event_time and (not ready or projection_30m_type == "unknown")
    plan_status = "matched" if matched else "pending_market_data" if pending else "no_op"
    output_event_type = "TriggerMatched" if matched else "TriggerPendingMarketData" if pending else None
    confirmed_time = hint_v2_event_time if is_hint_v2_projection else projection_confirmed_time(projection)
    plan_event_time = confirmed_time if matched or (is_hint_v2_projection and confirmed_time) else None
    trigger_price = projection_trigger_price(projection) if matched else None
    source_projection_id = projection.get("projection_id")
    raw_plan_id = "|".join(
        [
            projection_run_id,
            str(source_projection_id or "projection_missing"),
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or ""),
            legacy_signal_type,
            mapping.signal_type,
            mapping.trigger_mark_candidate,
            str(row.get("condition_key") or ""),
            plan_status,
        ]
    )
    return {
        "plan_id": stable_hash(raw_plan_id, length=32),
        "plan_status": plan_status,
        "output_event_type": output_event_type,
        "trigger_context_run_id": row.get("run_id"),
        "projection_run_id": projection_run_id,
        "projection_id": source_projection_id,
        "source_projection_id": source_projection_id,
        "asset_kind": str(row.get("asset_kind") or ""),
        "identity_key": str(row.get("identity_key") or ""),
        **condition_projection_fields,
        "direction": str(row.get("direction") or ""),
        "signal_type": mapping.signal_type,
        "runtime_signal_type": mapping.signal_type,
        "condition_signal_type": condition_signal_type_for_condition_key(
            str(row.get("condition_key") or ""),
            direction=str(row.get("direction") or ""),
            condition_family="hint",
        ),
        "condition_key": str(row.get("condition_key") or ""),
        "original_condition_key": mapping.original_condition_key,
        "legacy_signal_type": legacy_signal_type,
        "match_basis": "intraday_projection",
        "trigger_mark_candidate": mapping.trigger_mark_candidate,
        "trigger_period": PROJECTION_PERIOD if matched else None,
        "trigger_price": trigger_price,
        "trigger_time": plan_event_time,
        "event_time": plan_event_time,
        "trigger_live": matched,
        "current_status": "matched" if matched else "pending_market_data" if pending else "no_op",
        "n5_entry_allowed": matched,
        "projection_period": PROJECTION_PERIOD,
        "projection_30m_flag": projection_30m_flag,
        "projection_30m_type": projection_30m_type,
        "projection_30m_amount_source": amount_trace["projection_30m_amount_source"],
        "projection_30m_reference_source": amount_trace["projection_30m_reference_source"],
        "projection_amount_alias_policy": amount_trace["projection_amount_alias_policy"],
        "projection_30m_volume_up_flag": volume_up_flag,
        "projection_30m_shrink_down_flag": shrink_down_flag,
        "projection_signal_status": projection_signal_status,
        "source_projection_proof_run_id": proof.get("source_projection_proof_run_id"),
        "source_projection_proof_metric_id": proof.get("source_projection_proof_metric_id"),
        "source_projection_proof_time": proof.get("source_projection_proof_time"),
        "source_hint_projection_run_id": proof.get("source_hint_projection_run_id"),
        "source_hint_projection_metric_id": proof.get("source_hint_projection_metric_id"),
        "source_hint_projection_time": proof.get("source_hint_projection_time"),
        "source_hint_projection_proof_kind": proof.get("source_hint_projection_proof_kind"),
        "not_n5_final_proof": bool(proof.get("not_n5_final_proof")),
        "projection_proof_kind": proof.get("proof_kind"),
        "projection_proof_valid": proof_valid,
        "projection_proof_missing_or_invalid_fields": proof.get("missing_or_invalid_fields") or [],
        **source_trace,
        "projection_status": projection.get("projection_status") or "missing",
        "projection_quality_status": projection.get("projection_quality_status") or "missing",
        "trace_status": projection.get("trace_status") or "missing",
        "projection_window_id": projection.get("projection_window_id"),
        "projection_trace": {
            "projection_id": source_projection_id,
            "projection_run_id": projection_run_id,
            "projection_schema_version": projection.get("projection_schema_version"),
            "projection_window_kind": projection.get("projection_window_kind"),
            **{
                key: value
                for key, value in {
                    "source_snapshot_run_id": projection.get("source_snapshot_run_id"),
                    "snapshot_id": projection.get("snapshot_id"),
                    "snapshot_event_id": projection.get("snapshot_event_id"),
                }.items()
                if value is not None and value != ""
            },
            "source_fact_ids": projection.get("source_fact_ids") or {},
            **{
                key: value
                for key, value in {
                    "metric_minute_label": projection.get("metric_minute_label"),
                }.items()
                if value is not None and value != ""
            },
            **{key: value for key, value in proof.items() if key != "valid" and value is not None and value != ""},
            **source_trace,
            "projection_30m_amount_source": amount_trace["projection_30m_amount_source"],
            "projection_30m_reference_source": amount_trace["projection_30m_reference_source"],
            "projection_amount_alias_policy": amount_trace["projection_amount_alias_policy"],
            "trigger_price": trigger_price,
            "trigger_time": confirmed_time,
        },
        "dry_run_reason": provisional_reason(
            projection=projection,
            ready=ready,
            matched=matched,
            projection_30m_type=projection_30m_type,
            legacy_signal_type=legacy_signal_type,
            projection_signal_status=projection_signal_status,
            proof_valid=proof_valid,
            missing_hint_v2_iso_event_time=missing_hint_v2_iso_event_time,
        ),
    }


def provisional_reason(
    *,
    projection: Mapping[str, Any],
    ready: bool,
    matched: bool,
    projection_30m_type: str,
    legacy_signal_type: str,
    projection_signal_status: str,
    proof_valid: bool,
    missing_hint_v2_iso_event_time: bool = False,
) -> str:
    if not projection:
        return "N3 hint projection row is missing for provisional matching"
    if missing_hint_v2_iso_event_time:
        return "N3 hint projection row is missing ISO proof time for event_time normalization"
    if not proof_valid:
        return "N3 hint projection row is missing standard N3 hint projection proof"
    if not ready:
        return "N3 hint projection row is not ready for provisional matching"
    if projection_30m_type == "unknown":
        return "N3 hint projection row is missing atomic 30m evidence"
    if matched:
        return "N3 ready hint projection signal matches provisional N4 hint mapping"
    return (
        "N3 ready hint projection signal does not match provisional "
        f"{legacy_signal_type} mapping: {projection_signal_status}"
    )


def provisional_projection_30m_type(projection: Mapping[str, Any]) -> str:
    return str(provisional_projection_30m_amount_trace(projection)["projection_30m_type"])


def provisional_projection_30m_amount_trace(projection: Mapping[str, Any]) -> dict[str, Any]:
    if projection.get("proof_kind") == "index_board_1m_hint_projection_v1":
        projection_30m_type = str(projection.get("projection_30m_type") or "unknown")
        return {
            "projection_30m_type": projection_30m_type,
            "projection_30m_amount_source": "current_30m_virtual_amount",
            "projection_30m_reference_source": "reference_30m_amount",
            "projection_amount_alias_policy": "index_board_1m_hint_projection_v1",
        }
    current_30m_virtual_amount, current_source = first_numeric_projection_amount(
        projection,
        (
            ("current_30m_virtual_amount", projection.get("current_30m_virtual_amount")),
            ("current_30m_virtual_amount", projection_source_value(projection, "current_30m_virtual_amount")),
            ("projected_30m_amount", projection.get("projected_30m_amount")),
            ("projected_30m_amount", projection_source_value(projection, "projected_30m_amount")),
        ),
    )
    reference_30m_amount, reference_source = first_numeric_projection_amount(
        projection,
        (
            ("reference_30m_amount", projection.get("reference_30m_amount")),
            ("reference_30m_amount", projection_source_value(projection, "reference_30m_amount")),
            ("previous_day_same_window_amount", projection.get("previous_day_same_window_amount")),
            ("previous_day_same_window_amount", projection_source_value(projection, "previous_day_same_window_amount")),
        ),
    )
    projection_30m_type = "unknown"
    if current_30m_virtual_amount is None or reference_30m_amount is None:
        projection_30m_type = "unknown"
    elif current_30m_virtual_amount > reference_30m_amount:
        projection_30m_type = "volume_up"
    elif current_30m_virtual_amount < reference_30m_amount:
        projection_30m_type = "shrink_down"
    else:
        projection_30m_type = "none"
    return {
        "projection_30m_type": projection_30m_type,
        "projection_30m_amount_source": current_source,
        "projection_30m_reference_source": reference_source,
        "projection_amount_alias_policy": PROJECTION_AMOUNT_ALIAS_POLICY,
    }


def missing_projection_amount_trace() -> dict[str, str]:
    return {
        "projection_30m_type": "unknown",
        "projection_30m_amount_source": "missing",
        "projection_30m_reference_source": "missing",
        "projection_amount_alias_policy": PROJECTION_AMOUNT_ALIAS_POLICY,
    }


def first_numeric_projection_amount(
    projection: Mapping[str, Any],
    candidates: Sequence[tuple[str, Any]],
) -> tuple[float | None, str]:
    for source_name, value in candidates:
        if value is None or value == "":
            continue
        return _to_float(value), source_name
    return None, "missing"


def projection_matches_atomic_type(signal_type: str, projection_30m_type: str) -> bool:
    if signal_type == "BUY_HINT":
        return projection_30m_type == "volume_up"
    if signal_type == "SELL_HINT":
        return projection_30m_type == "shrink_down"
    return False


def projection_source_value(projection: Mapping[str, Any], key: str) -> Any:
    raw_json = projection.get("raw_json") if isinstance(projection.get("raw_json"), Mapping) else {}
    return raw_json.get(key)


def hint_v2_projection_event_time(projection: Mapping[str, Any]) -> str | None:
    raw_json = projection.get("raw_json") if isinstance(projection.get("raw_json"), Mapping) else {}
    trace_json = projection.get("trace_json") if isinstance(projection.get("trace_json"), Mapping) else {}
    source_fact_ids = projection.get("source_fact_ids") if isinstance(projection.get("source_fact_ids"), Mapping) else {}
    raw_proof = raw_json.get("proof") if isinstance(raw_json.get("proof"), Mapping) else {}
    trace_proof = trace_json.get("proof") if isinstance(trace_json.get("proof"), Mapping) else {}
    candidates = (
        raw_proof.get("source_projection_proof_time"),
        raw_proof.get("proof_input_time"),
        trace_proof.get("source_projection_proof_time"),
        trace_proof.get("proof_input_time"),
        raw_json.get("source_projection_proof_time"),
        raw_json.get("proof_input_time"),
        trace_json.get("source_projection_proof_time"),
        trace_json.get("proof_input_time"),
        source_fact_ids.get("source_projection_proof_time"),
        source_fact_ids.get("proof_input_time"),
    )
    for value in candidates:
        text = str(value or "").strip()
        if is_iso_datetime_text(text):
            return text
    return None


def is_iso_datetime_text(value: str) -> bool:
    if not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def projection_source_trace(projection: Mapping[str, Any]) -> dict[str, Any]:
    raw_json = projection.get("raw_json") if isinstance(projection.get("raw_json"), Mapping) else {}
    trace_json = projection.get("trace_json") if isinstance(projection.get("trace_json"), Mapping) else {}
    lineage = projection.get("projection_lineage_json") if isinstance(projection.get("projection_lineage_json"), Mapping) else {}
    source_fact_ids = projection.get("source_fact_ids") if isinstance(projection.get("source_fact_ids"), Mapping) else {}
    source_mode = (
        projection.get("source_mode")
        or lineage.get("source_mode")
        or source_fact_ids.get("source_mode")
        or trace_json.get("source_mode")
        or raw_json.get("source_mode")
    )
    c1_dependency = first_present(
        projection.get("c1_dependency"),
        lineage.get("c1_dependency"),
        source_fact_ids.get("c1_dependency"),
        trace_json.get("c1_dependency"),
        raw_json.get("c1_dependency"),
    )
    source_live_minute_run_id = (
        projection.get("source_live_minute_run_id")
        or lineage.get("source_live_minute_run_id")
        or source_fact_ids.get("source_live_minute_run_id")
        or trace_json.get("source_live_minute_run_id")
        or raw_json.get("source_live_minute_run_id")
    )
    output: dict[str, Any] = {}
    if source_mode:
        output["source_mode"] = str(source_mode)
    if c1_dependency is not None:
        output["c1_dependency"] = bool(c1_dependency)
    if source_live_minute_run_id:
        output["source_live_minute_run_id"] = str(source_live_minute_run_id)
    return output


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def summarize_provisional_projection_matcher_plans(plans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matched = [plan for plan in plans if plan.get("plan_status") == "matched"]
    pending = [plan for plan in plans if plan.get("plan_status") == "pending_market_data"]
    noop = [plan for plan in plans if plan.get("plan_status") == "no_op"]
    return {
        "candidate_count": len(plans),
        "matched_count": len(matched),
        "pending_count": len(pending),
        "noop_count": len(noop),
        "output_event_types": count_by(plans, "output_event_type"),
        "matched_by_asset_kind": count_by(matched, "asset_kind"),
        "matched_by_signal_type": count_by(matched, "signal_type"),
        "matched_by_condition_signal_type": count_by(matched, "condition_signal_type"),
        "matched_by_trigger_mark_candidate": count_by(matched, "trigger_mark_candidate"),
        "pending_by_projection_signal_status": count_by(pending, "projection_signal_status"),
        "noop_by_projection_signal_status": count_by(noop, "projection_signal_status"),
    }


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))
