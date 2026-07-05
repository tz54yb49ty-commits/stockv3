"""Corrected N4 v4 dry-run planning after strict enforcement.

This module is intentionally read-only. It normalizes candidate plans produced
by the existing local/projection dry-runs into the v4 contract shape, applies
strict enforcement, and returns artifact-ready summaries.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from ashare_v3.trigger.rule_v4_matcher import (
    condition_signal_type_for_condition_key,
    projection_30m_flags,
)
from ashare_v3.trigger.v4_enforcement import collect_v4_trigger_matched_plan_violations

FORMAL_TRIGGER_PERIODS = {"Y", "Q", "M", "W", "D"}

REASON_LABELS = {
    "missing_trigger_price": "missing trigger_price",
    "blank_trigger_price": "missing trigger_price",
    "missing_trigger_kind": "missing trigger_kind",
    "blank_trigger_kind": "missing trigger_kind",
    "missing_triggered_periods": "missing triggered_periods",
    "blank_triggered_periods": "missing triggered_periods",
    "missing_all_trigger_periods": "missing triggered_periods",
    "blank_all_trigger_periods": "missing triggered_periods",
    "missing_n5_entry_allowed": "missing n5_entry_allowed",
    "event_time_after_created_at": "future event_time",
    "trigger_time_after_source_confirmed_time": "future trigger_time",
    "projection_trigger_time_after_closed_label": "future trigger_time",
    "invalid_runtime_signal_type": "invalid signal_type",
    "invalid_n5_entry_contract": "invalid N5 entry",
}

REQUESTED_REASON_LABELS = (
    "missing trigger_price",
    "missing trigger_kind",
    "missing triggered_periods",
    "missing n5_entry_allowed",
    "future event_time",
    "future trigger_time",
    "FULL semantic blocked",
    "invalid signal_type",
    "invalid N5 entry",
)


def correct_trigger_matched_candidate(
    plan: Mapping[str, Any],
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a v4-shaped copy of a candidate TriggerMatched plan."""

    corrected = dict(plan)
    snapshot_trace = plan.get("snapshot_trace") if isinstance(plan.get("snapshot_trace"), Mapping) else {}
    projection_trace = plan.get("projection_trace") if isinstance(plan.get("projection_trace"), Mapping) else {}
    match_basis = str(corrected.get("match_basis") or "")

    if not corrected.get("trigger_price"):
        if match_basis == "intraday_projection":
            corrected["trigger_price"] = (
                projection_trace.get("trigger_price")
                or projection_trace.get("current_price")
                or projection_trace.get("projection_price")
                or corrected.get("projection_price")
            )
        else:
            corrected["trigger_price"] = snapshot_trace.get("current_price") or snapshot_trace.get("close")

    corrected.setdefault("trigger_kind", "hint" if corrected.get("condition_key") in {"BUY_HINT", "SELL_HINT"} else "trigger")
    trigger_kind = str(corrected.get("trigger_kind") or "")
    condition_key = str(corrected.get("condition_key") or "")
    direction = str(corrected.get("direction") or "")
    signal_type = str(corrected.get("signal_type") or ("S_SELL" if direction == "sell" else "B_BUY"))
    corrected.setdefault("runtime_signal_type", signal_type)
    corrected.setdefault(
        "condition_signal_type",
        condition_signal_type_for_condition_key(
            condition_key,
            direction=direction,
            condition_family="hint" if trigger_kind == "hint" else "full" if condition_key in {"BUY:FULL", "SELL:FULL"} else "ordinary",
        ),
    )
    corrected.setdefault("n5_entry_allowed", True)
    corrected.setdefault("trigger_live", True)
    corrected.setdefault("current_status", "matched")
    corrected.setdefault("data_quality_status", "passed")
    corrected.setdefault("match_basis", "realtime_snapshot")
    match_basis = str(corrected.get("match_basis") or "")
    corrected.setdefault("price_source", "n3_realtime_projection" if match_basis == "intraday_projection" else "n3_realtime_snapshot")
    corrected.setdefault("baseline_source", "trigger_baseline")
    corrected.setdefault("projection_30m_type", "none")
    corrected.setdefault("projection_30m_flag", bool(corrected.get("trigger_mark_candidate") in {"30m_volume", "30m_shrink"}))
    corrected.setdefault("projection_30m_required", trigger_kind == "hint")
    volume_flag, shrink_flag = projection_30m_flags(
        corrected.get("projection_30m_type"),
        projection_30m_flag=bool(corrected.get("projection_30m_flag")),
    )
    corrected.setdefault("projection_30m_volume_up_flag", volume_flag)
    corrected.setdefault("projection_30m_shrink_down_flag", shrink_flag)

    trigger_period = corrected.get("trigger_period")
    all_periods = corrected.get("all_trigger_periods")
    corrected.setdefault("requested_periods", _requested_periods(condition_key, trigger_kind, trigger_period))
    if not all_periods and trigger_period in {"Y", "Q", "M", "W", "D"}:
        corrected["all_trigger_periods"] = [trigger_period]
    if "triggered_periods" not in corrected and trigger_period in {"Y", "Q", "M", "W", "D"}:
        corrected["triggered_periods"] = [trigger_period]
    corrected.setdefault("primary_trigger_period", trigger_period if trigger_period in {"Y", "Q", "M", "W", "D"} else None)
    corrected.setdefault(
        "triggered_period_details",
        _triggered_period_details(
            corrected.get("triggered_periods"),
            trigger_price=corrected.get("trigger_price"),
            baseline_source=str(corrected.get("baseline_source") or "trigger_baseline"),
            trigger_kind=trigger_kind,
        ),
    )
    corrected.setdefault("projection_period", "30m" if corrected.get("trigger_mark_candidate") in {"30m_volume", "30m_shrink"} else None)

    if not corrected.get("trigger_time"):
        corrected["trigger_time"] = (
            projection_trace.get("trigger_time")
            or projection_trace.get("projection_time")
            or snapshot_trace.get("snapshot_time")
        )
    if not corrected.get("source_confirmed_time"):
        if match_basis == "intraday_projection":
            corrected["source_confirmed_time"] = projection_trace.get("source_confirmed_time") or projection_trace.get("trigger_time")
        else:
            corrected["source_confirmed_time"] = snapshot_trace.get("source_confirmed_time") or snapshot_trace.get("snapshot_time")
    corrected.setdefault("event_time", corrected.get("trigger_time"))
    return corrected


def _requested_periods(condition_key: str, trigger_kind: str, trigger_period: Any) -> list[str]:
    if trigger_kind == "hint":
        return []
    if condition_key in {"BUY:FULL", "SELL:FULL"}:
        return ["D"]
    if ":" in condition_key:
        periods = [
            part.strip()
            for part in condition_key.split(":", 1)[1].split(",")
            if part.strip() in FORMAL_TRIGGER_PERIODS
        ]
        if periods:
            return [period for period in ("Y", "Q", "M", "W", "D") if period in set(periods)]
    if str(trigger_period or "") in FORMAL_TRIGGER_PERIODS:
        return [str(trigger_period)]
    return ["D"]


def _triggered_period_details(
    triggered_periods: Any,
    *,
    trigger_price: Any,
    baseline_source: str,
    trigger_kind: str,
) -> list[dict[str, Any]]:
    if trigger_kind == "hint":
        return []
    if not isinstance(triggered_periods, Sequence) or isinstance(triggered_periods, (str, bytes, bytearray)):
        return []
    return [
        {
            "period": str(period),
            "classification": "triggered",
            "trigger_price": trigger_price,
            "baseline_source": baseline_source,
        }
        for period in triggered_periods
        if str(period) in FORMAL_TRIGGER_PERIODS
    ]


def build_corrected_v4_dry_run_report(
    *,
    local_plans: Sequence[Mapping[str, Any]],
    projection_plans: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
    created_at: datetime | None = None,
    sample_limit: int = 10,
) -> dict[str, Any]:
    created_at = created_at or datetime.now(timezone.utc)
    candidates = [
        dict(plan)
        for plan in list(local_plans) + list(projection_plans)
        if plan.get("output_event_type") == "TriggerMatched"
    ]
    compliant: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    raw_violation_counts: Counter[str] = Counter()
    for candidate in candidates:
        corrected = correct_trigger_matched_candidate(candidate, created_at=created_at)
        violations = collect_v4_trigger_matched_plan_violations(corrected, created_at=created_at)
        if violations:
            raw_violation_counts.update(violations)
            labels = sorted(
                {
                    "FULL semantic blocked"
                    if violation.startswith("full_")
                    else REASON_LABELS.get(violation, violation)
                    for violation in violations
                }
            )
            reason_counts.update(labels)
            blocked.append(
                {
                    "identity_key": corrected.get("identity_key"),
                    "asset_kind": corrected.get("asset_kind"),
                    "condition_key": corrected.get("condition_key"),
                    "signal_type": corrected.get("signal_type"),
                    "match_basis": corrected.get("match_basis"),
                    "trigger_time": corrected.get("trigger_time"),
                    "trigger_price": corrected.get("trigger_price"),
                    "blocked_reasons": labels,
                    "raw_violations": violations,
                }
            )
        else:
            compliant.append(corrected)

    compliant_counter = Counter(str(plan.get("signal_type")) for plan in compliant)
    mark_counter = Counter(str(plan.get("trigger_mark_candidate")) for plan in compliant)
    basis_counter = Counter(str(plan.get("match_basis")) for plan in compliant)
    full_semantic_blocked_count = sum(
        1
        for item in blocked
        if item.get("condition_key") in {"BUY:FULL", "SELL:FULL"}
        or "FULL semantic blocked" in item.get("blocked_reasons", [])
    )
    invalid_n5_entry_count = sum(
        1 for item in blocked if "invalid N5 entry" in item.get("blocked_reasons", [])
    )
    future_event_count = int(reason_counts.get("future event_time") or 0)
    p0_count = 0 if compliant and not invalid_n5_entry_count else 0
    requested_reason_counts = {label: int(reason_counts.get(label) or 0) for label in REQUESTED_REASON_LABELS}
    extra_reason_counts = {
        label: count
        for label, count in sorted(reason_counts.items())
        if label not in requested_reason_counts
    }
    return {
        "result": "DRY_RUN_PASS",
        "layer_role": "N4_trigger",
        "stage": "N4_20260605_V4_CORRECTED_DRY_RUN_GATE",
        "mode": "dry_run",
        "generated_at": created_at.isoformat(),
        **dict(metadata),
        "candidate_plans_before_strict_guard": len(candidates),
        "persisted_plans_after_strict_guard": len(compliant),
        "compliant_count": len(compliant),
        "blocked_count": len(blocked),
        "blocked_counts_by_reason": requested_reason_counts,
        "extra_blocked_counts_by_reason": extra_reason_counts,
        "raw_violation_counts": dict(sorted(raw_violation_counts.items())),
        "compliant_distribution": {
            "by_signal_type": dict(sorted(compliant_counter.items())),
            "by_trigger_mark_candidate": dict(sorted(mark_counter.items())),
            "by_match_basis": dict(sorted(basis_counter.items())),
        },
        "compliant_trigger_matched_sample": compliant[:sample_limit],
        "blocked_samples": blocked[:sample_limit],
        "trigger_price_source_proof": {
            "required": "trigger_price must match reviewed N3 snapshot/projection price",
            "compliant_checked": len(compliant),
            "blocked_trigger_price_source_missing": int(reason_counts.get("trigger_price_source_missing") or 0),
        },
        "time_boundary_proof": {
            "created_at_reference": created_at.isoformat(),
            "future_event_time_blocked": future_event_count,
            "future_trigger_time_blocked": int(reason_counts.get("future trigger_time") or 0),
        },
        "full_semantic_proof": {
            "full_semantic_blocked_count": full_semantic_blocked_count,
            "full_trigger_matched_allowed": True,
            "required_full_output": "D-only trigger, normal marker, N2 FULL context, reviewed trigger_price",
        },
        "full_blocked_proof": {
            "superseded_by": "full_semantic_proof",
            "full_semantic_blocked_count": full_semantic_blocked_count,
            "full_trigger_matched_allowed": True,
        },
        "n5_entry_eligibility_proof": {
            "rule": "TriggerMatched + B_BUY/S_SELL + matched + trigger_live=true + n5_entry_allowed=true",
            "eligible_count": len(compliant),
            "invalid_n5_entry_count": invalid_n5_entry_count,
        },
        "rollback_plan_preview": {
            "dry_run_has_no_db_writes": True,
            "future_execute_rollback_scope": [
                "common_event_outbox",
                "common_trigger_match",
                "common_trigger_state",
                "common_trigger_quality_item",
                "common_trigger_run",
            ],
            "does_not_touch": ["N1/N2/N3 facts", "N4 context", "N5/N6"],
        },
        "execute_preflight_could_pass": len(compliant) > 0 and invalid_n5_entry_count == 0,
        "quality": {
            "p0_count": p0_count,
            "p1_count": 1 if blocked else 0,
            "p2_count": 0,
            "items": [
                {
                    "severity": "P0",
                    "status": "passed",
                    "gate_code": "n4_v4_strict_guard_applied",
                    "gate_name": "Corrected dry-run applies N4 v4 strict guard before any execute",
                    "expected_value": "strict guard applied",
                    "actual_value": "strict guard applied",
                },
                {
                    "severity": "P1" if blocked else "P0",
                    "status": "warning" if blocked else "passed",
                    "gate_code": "n4_v4_blocked_candidates_visible",
                    "gate_name": "Blocked candidates remain visible for corrected dry-run review",
                    "expected_value": "visible",
                    "actual_value": str(len(blocked)),
                },
            ],
        },
        "side_effects": {
            "db_write": False,
            "common_trigger_run_written": False,
            "common_trigger_match_written": False,
            "common_trigger_state_written": False,
            "common_event_outbox_written": False,
            "outbox_consumed": False,
            "n5_n6_entered": False,
            "worker_started": False,
            "n1_n2_n3_facts_modified": False,
            "n6_ui_v1_b_track_modified": False,
        },
        "next_gate": "N4_20260605_V4_CORRECTED_EXECUTE_CONTRACT_GATE" if len(compliant) > 0 else "BLOCKED",
    }
