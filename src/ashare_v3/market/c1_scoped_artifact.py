"""N3-C1 scoped closed-minute artifact contract helpers.

This module is intentionally pure. It validates an explicit N5 active scope
snapshot artifact and returns an N3 scoped C1 plan/artifact without DB writes,
market pulls, outbox access, or runtime execution paths.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from ashare_v3.market.minute_label_normalization import (
    BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE,
    MinuteLabelNormalizationError,
    ashare_c1_minute_close_time,
    canonical_ashare_1m_labels,
    validate_ashare_c1_minute_label,
)
from ashare_v3.market.realtime_virtual_metric import VIRTUAL_AMOUNT_POLICY_VERSION


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")

INPUT_ARTIFACT_TYPE = "n5_active_scope_snapshot_v1"
OUTPUT_ARTIFACT_TYPE = "n3_c1_scoped_closed_1m_artifact_v1"
OUTPUT_ARTIFACT_SCHEMA_VERSION = "v1"
METRIC_CONTEXT_SOURCE_ARTIFACT_TYPE = "n3_c1_n3t_metric_context_source_v1"
CURRENT_DAY_PULL_PLAN_TYPE = "n3_c1_scoped_current_day_pull_plan_v1"
CURRENT_DAY_SOURCE_ROWS_TYPE = "n3_c1_scoped_current_day_source_rows_v1"
CURRENT_DAY_STAGING_ARTIFACT_TYPE = "n3_c1_scoped_current_day_staging_v1"
CURRENT_DAY_PULL_PLAN_SCHEMA_VERSION = "v1"
CURRENT_DAY_PULL_EXECUTE_GATE = "N3_C1_SCOPED_CURRENT_DAY_PULL_EXECUTE_GATE"
CANONICAL_C1_EXECUTE_GATE = "N3_C1_SCOPED_EXECUTE_GATE"

BLOCKED_C1_MINUTE_NOT_CLOSED = "BLOCKED_C1_MINUTE_NOT_CLOSED"
BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH = "BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH"
BLOCKED_FULL_MARKET_FALLBACK_RISK = "BLOCKED_FULL_MARKET_FALLBACK_RISK"
BLOCKED_N3_C1_SCOPED_CONTEXT_INSUFFICIENT = "BLOCKED_N3_C1_SCOPED_CONTEXT_INSUFFICIENT"
BLOCKED_PREVIOUS_DAY_RAW_C1_CONTEXT_INSUFFICIENT = "BLOCKED_PREVIOUS_DAY_RAW_C1_CONTEXT_INSUFFICIENT"
BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH = "BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH"
BLOCKED_SOURCE_CLOSE_LABEL_NOT_MAPPABLE = "BLOCKED_SOURCE_CLOSE_LABEL_NOT_MAPPABLE"
BLOCKED_N3T_FIXED_PERIOD_WINDOW_UNAVAILABLE = "BLOCKED_N3T_FIXED_PERIOD_WINDOW_UNAVAILABLE"
BLOCKED_N3T_CURRENT_5M_SAME_WINDOW_SOURCE_MISSING = (
    "BLOCKED_N3T_CURRENT_5M_SAME_WINDOW_SOURCE_MISSING"
)
BLOCKED_N3T_METRIC_CONTEXT_FIELDS_MISSING = "BLOCKED_N3T_METRIC_CONTEXT_FIELDS_MISSING"

SOURCE_CLOSE_LABEL_POLICY = "source_label_to_physical_with_close_boundaries_v4"
SOURCE_LABEL_SEMANTICS = "source_label"
PHYSICAL_LABEL_SEMANTICS = "start_label"
FORBIDDEN_SOURCE_CLOSE_LABELS = {"11:30"}
SOURCE_GAP_POLICY = "session_boundary_source_gap_excluded_v1"
OPEN_BOUNDARY_MISSING_SOURCE_REASON = "open_boundary_missing_source"
LUNCH_CLOSE_MISSING_SOURCE_REASON = "lunch_close_missing_source"
CLOSE_BOUNDARY_TARGET_POLICY = "session_close_boundary_latest_physical_label_v1"
BOUNDARY_POLICY_VERSION = "n3.action_confirmation_boundary.v1"
SAME_TRADE_DATE_PREVIOUS_PERIOD = "same_trade_date_previous_period"
PREVIOUS_TRADE_DATE_LAST_PERIOD = "previous_trade_date_last_period"
NOT_AVAILABLE_PERIOD_SOURCE = "not_available"
BLOCKED_N3T_PREVIOUS_PERIOD_SOURCE_UNAVAILABLE = "BLOCKED_N3T_PREVIOUS_PERIOD_SOURCE_UNAVAILABLE"
VALID_PREVIOUS_PERIOD_SOURCES = frozenset(
    {SAME_TRADE_DATE_PREVIOUS_PERIOD, PREVIOUS_TRADE_DATE_LAST_PERIOD}
)
PREVIOUS_PERIOD_SOURCE_FIELDS = tuple(
    f"previous_{period}_period_source" for period in ("1m", "5m", "30m", "120m")
)
FIXED_PERIOD_LAYOUT_INTRADAY = "intraday"
FIXED_PERIOD_LAYOUT_POST_CLOSE = "post_close"
FIXED_PERIOD_LAYOUT_PRELOAD_CLOSE_LABEL = "preload_close_label"
FIXED_PERIOD_MINUTE_AXIS_VERSION = "n3.fixed_period_minute_axis.v1"
FIXED_PERIOD_CALCULATION_LABELS = tuple(
    label
    for label in canonical_ashare_1m_labels("20000103")
    if label not in {"09:30", "11:30"}
)
FIXED_PERIOD_CALCULATION_ORDINALS = {
    label: index
    for index, label in enumerate(FIXED_PERIOD_CALCULATION_LABELS, start=1)
}

ASSET_KINDS = ("stock", "index", "board")
REQUIRED_SCOPE_GRAIN = (
    "for_trade_date",
    "asset_kind",
    "identity_key",
    "direction",
    "signal_type",
    "condition_key",
    "source_trigger_event_id",
    "source_trigger_run_id",
    "scope_status",
)
ACTIVE_REF_OPTIONAL_SCOPE_GRAIN = {"source_trigger_run_id"}
OBJECT_SCOPE_GRAIN = (
    "for_trade_date",
    "asset_kind",
    "identity_key",
    "scope_status",
)
SIDE_EFFECT_FLAGS = (
    "database_written",
    "market_data_pulled",
    "writes_canonical_minute_bar_1m",
    "writes_n3_outbox",
    "consumes_n4_outbox",
    "updates_n4_outbox",
    "full_market_fallback_used",
)
REQUIRED_METRIC_CONTEXT_FIELDS = (
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
    "current_5m_amount",
    "current_30m_closed_elapsed_amount",
    "is_first_1m_of_day",
    "is_first_5m_of_day",
    "is_first_30m_of_day",
    "is_first_120m_of_day",
    "first_1m_amount_default_pass",
    "first_5m_amount_default_pass",
    "previous_1m_period_source",
    "previous_5m_period_source",
    "previous_30m_period_source",
    "previous_120m_period_source",
    "boundary_policy_version",
)


def previous_period_sources_are_valid(metric_values: Mapping[str, Any]) -> bool:
    return all(
        str(metric_values.get(field) or "") in VALID_PREVIOUS_PERIOD_SOURCES
        for field in PREVIOUS_PERIOD_SOURCE_FIELDS
    )


def required_previous_day_metric_context_labels(
    *,
    labels: Sequence[str],
    current_labels: set[str],
) -> set[str]:
    """Return previous-day physical labels required by the shared fixed-period axis."""

    canonical_labels = tuple(str(label or "") for label in labels)
    calculation_labels = tuple(
        label for label in canonical_labels if label in FIXED_PERIOD_CALCULATION_ORDINALS
    )
    if calculation_labels != FIXED_PERIOD_CALCULATION_LABELS:
        return set()
    observed_labels = {
        str(label or "")
        for label in current_labels
        if str(label or "") in FIXED_PERIOD_CALCULATION_ORDINALS
    }
    if not observed_labels:
        return set()

    latest_label = max(
        observed_labels,
        key=lambda label: FIXED_PERIOD_CALCULATION_ORDINALS[label],
    )
    position = FIXED_PERIOD_CALCULATION_ORDINALS[latest_label]
    required: set[str] = set()
    for size in (1, 5, 30, 120):
        current_start = ((position - 1) // size) * size
        if current_start == 0:
            required.update(canonical_labels[-size:])
    for size in (5, 30):
        required.update(_fixed_period_same_window_labels(position=position, size=size))
    return required


def build_n3_c1_scoped_current_day_pull_plan(
    active_scope_artifact: Mapping[str, Any] | None,
    *,
    target_minute_label: str,
    observed_at: Any,
    source_artifact_path: str | None = None,
    source_artifact_hash: str | None = None,
) -> dict[str, Any]:
    """Build a current-day C1 pull/staging plan for an explicit N5 active scope."""

    scope = dict(active_scope_artifact or {})
    for_trade_date = str(scope.get("for_trade_date") or "")
    base = _base_current_day_pull_plan(
        for_trade_date=for_trade_date,
        target_minute_label=target_minute_label,
        source_artifact_path=source_artifact_path,
        source_artifact_hash=source_artifact_hash,
    )

    boundary_reason = _scope_boundary_block_reason(scope)
    if boundary_reason:
        return _blocked_current_day_pull_plan(base, boundary_reason)

    if not _valid_trade_date(for_trade_date):
        return _blocked_current_day_pull_plan(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)

    target_status = _normalize_current_day_pull_target_minute_label(target_minute_label)
    base.update(
        {
            "normalized_target_minute_label": target_status.get("normalized_target_minute_label"),
            "target_minute_boundary_policy": target_status.get("target_minute_boundary_policy"),
            "target_minute_boundary_reason": target_status.get("target_minute_boundary_reason"),
        }
    )
    if target_status["status"] == "blocked":
        return _blocked_current_day_pull_plan(base, target_status["reason"])
    effective_target_minute_label = str(target_status["normalized_target_minute_label"])

    scope_rows = list(scope.get("scope_rows") or [])
    if _empty_scope(scope, scope_rows):
        base.update(
            {
                "plan_status": "noop",
                "empty_scope_noop": True,
                "scope_count": 0,
                "plan_rows": [],
            }
        )
        return base

    normalized_rows = _normalize_c1_object_scope_rows(scope_rows, for_trade_date=for_trade_date)
    if normalized_rows is None:
        return _blocked_current_day_pull_plan(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)

    minute_status = is_c1_minute_closed_for_scoped_artifact(for_trade_date, effective_target_minute_label, observed_at)
    if minute_status["status"] == "blocked":
        return _blocked_current_day_pull_plan(base, minute_status["reason"])

    source_label_plan = build_source_close_label_plan_for_target_minute(
        for_trade_date=for_trade_date,
        target_minute_label=effective_target_minute_label,
    )
    if source_label_plan["status"] == "blocked":
        return _blocked_current_day_pull_plan(base, source_label_plan["reason"])

    normalized_rows.sort(
        key=lambda row: (
            row["asset_kind"],
            row["identity_key"],
        )
    )
    plan_rows = [
        _current_day_pull_plan_row(
            row,
            target_minute_label=target_minute_label,
            normalized_target_minute_label=effective_target_minute_label,
            minute_status=minute_status,
            source_label_plan=source_label_plan,
        )
        for row in normalized_rows
    ]
    base.update(
        {
            "plan_status": "planned",
            "blocked_reason": None,
            "empty_scope_noop": False,
            "scope_count": len(plan_rows),
            "plan_rows": plan_rows,
            "expected_closed_time": minute_status["usable_after"],
            "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
            "source_label_semantics": SOURCE_LABEL_SEMANTICS,
            "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
            "required_physical_labels": source_label_plan["required_physical_labels"],
            "required_raw_source_labels": source_label_plan["required_raw_source_labels"],
            "source_gap_policy": source_label_plan["source_gap_policy"],
            "source_gap_physical_labels": source_label_plan["source_gap_physical_labels"],
            "metric_context_dependencies": source_label_plan["metric_context_dependencies"],
            "expected_rows_after_pull": len(plan_rows) * len(source_label_plan["required_raw_source_labels"]),
            "closed_minute_contract": minute_status,
        }
    )
    return base


def build_source_close_label_plan_for_target_minute(
    *,
    for_trade_date: str,
    target_minute_label: str,
) -> dict[str, Any]:
    """Return physical labels and required raw source close labels through target."""

    try:
        target_status = _normalize_current_day_pull_target_minute_label(target_minute_label)
        if target_status["status"] == "blocked":
            raise ValueError(target_status["reason"])
        target = str(target_status["normalized_target_minute_label"])
        labels = canonical_ashare_1m_labels(for_trade_date)
        target_index = labels.index(target)
        requested_physical_labels = labels[: target_index + 1]
        physical_labels = []
        raw_labels = []
        source_gap_physical_labels = []
        metric_context_dependencies = []
        for physical_label in requested_physical_labels:
            if physical_label == "09:30":
                continue
            source_label = source_close_label_for_physical_start_label(for_trade_date, physical_label)
            if source_label["status"] == "blocked":
                if _is_lunch_close_missing_source(source_label):
                    source_gap = _lunch_close_source_gap(source_label)
                    source_gap_physical_labels.append(source_gap)
                    metric_context_dependencies.append(
                        {
                            "physical_c1_label": source_gap["physical_c1_label"],
                            "required_context": source_gap["metric_context_dependency"],
                            "reason": source_gap["reason"],
                        }
                    )
                    continue
                raise ValueError(source_label["reason"])
            physical_labels.append(physical_label)
            raw_labels.append(source_label["raw_source_label"])
    except (MinuteLabelNormalizationError, ValueError):
        return {
            "status": "blocked",
            "reason": BLOCKED_SOURCE_CLOSE_LABEL_NOT_MAPPABLE,
            "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
            "source_gap_policy": SOURCE_GAP_POLICY,
            "target_minute_label": str(target_minute_label or ""),
            "normalized_target_minute_label": None,
            "target_minute_boundary_policy": None,
            "target_minute_boundary_reason": None,
            "required_physical_labels": [],
            "required_raw_source_labels": [],
            "source_gap_physical_labels": [],
            "metric_context_dependencies": [],
        }
    return {
        "status": "planned",
        "reason": None,
        "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
        "source_gap_policy": SOURCE_GAP_POLICY,
        "target_minute_label": str(target_minute_label or ""),
        "normalized_target_minute_label": target,
        "target_minute_boundary_policy": target_status.get("target_minute_boundary_policy"),
        "target_minute_boundary_reason": target_status.get("target_minute_boundary_reason"),
        "source_label_semantics": SOURCE_LABEL_SEMANTICS,
        "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
        "required_physical_labels": physical_labels,
        "required_raw_source_labels": raw_labels,
        "source_gap_physical_labels": source_gap_physical_labels,
        "metric_context_dependencies": metric_context_dependencies,
    }


def source_close_label_for_physical_start_label(for_trade_date: str, physical_c1_label: str) -> dict[str, Any]:
    """Map one physical C1 start label to the raw source close label needed."""

    try:
        physical_label = validate_ashare_c1_minute_label(physical_c1_label)
    except (MinuteLabelNormalizationError, ValueError):
        return {
            "status": "blocked",
            "reason": BLOCKED_SOURCE_CLOSE_LABEL_NOT_MAPPABLE,
            "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
            "physical_c1_label": str(physical_c1_label or ""),
            "raw_source_label": None,
        }
    raw_label = _source_close_label_for_physical_label(physical_label)
    if not raw_label:
        return {
            "status": "blocked",
            "reason": BLOCKED_SOURCE_CLOSE_LABEL_NOT_MAPPABLE,
            "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
            "physical_c1_label": physical_label,
            "raw_source_label": raw_label,
        }
    return {
        "status": "mapped",
        "reason": None,
        "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
        "source_label_semantics": SOURCE_LABEL_SEMANTICS,
        "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
        "physical_c1_label": physical_label,
        "raw_source_label": raw_label,
    }


def source_close_label_to_physical_start_label(for_trade_date: str, raw_source_label: Any) -> dict[str, Any]:
    """Map a raw source close label to an N3-C1 physical start label."""

    raw_label = _hhmm_text(raw_source_label)
    physical_label = _physical_label_for_source_close_label(raw_label)
    if physical_label:
        return {
            "status": "mapped",
            "reason": None,
            "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
            "source_label_semantics": SOURCE_LABEL_SEMANTICS,
            "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
            "raw_source_label": raw_label,
            "physical_c1_label": physical_label,
        }
    return {
        "status": "blocked",
        "reason": BLOCKED_SOURCE_CLOSE_LABEL_NOT_MAPPABLE,
        "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
        "source_label_semantics": SOURCE_LABEL_SEMANTICS,
        "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
        "raw_source_label": raw_label,
        "physical_c1_label": None,
    }


def apply_source_close_label_policy_to_row(row: Mapping[str, Any], *, for_trade_date: str) -> dict[str, Any]:
    """Apply raw close-label trace to one provider row without creating synthetic rows."""

    source = dict(row or {})
    raw_key = _source_time_key(source)
    raw_dt = _coerce_shanghai(source[raw_key])
    mapped = source_close_label_to_physical_start_label(for_trade_date, raw_dt.strftime("%H:%M"))
    if mapped["status"] != "mapped":
        raise MinuteLabelNormalizationError(f"{mapped['reason']}: {mapped['raw_source_label']}")

    physical_dt = _with_hhmm(raw_dt, mapped["physical_c1_label"])
    raw_payload = dict(source.get("raw_payload") or {})
    raw_payload.update(
        {
            "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
            "source_label_semantics": SOURCE_LABEL_SEMANTICS,
            "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
            "raw_source_bar_time": raw_dt.isoformat(),
            "raw_source_label": mapped["raw_source_label"],
            "physical_c1_label": mapped["physical_c1_label"],
            "fake_or_synthetic_row": False,
        }
    )
    source[raw_key] = _format_like(source[raw_key], physical_dt)
    source.update(
        {
            "raw_source_bar_time": raw_dt.isoformat(),
            "raw_source_label": mapped["raw_source_label"],
            "physical_c1_label": mapped["physical_c1_label"],
            "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
            "source_label_semantics": SOURCE_LABEL_SEMANTICS,
            "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
            "fake_or_synthetic_row": False,
            "raw_payload": raw_payload,
        }
    )
    return source


def _source_close_label_for_physical_label(physical_label: str) -> str:
    if not validate_ashare_c1_minute_label(physical_label):
        return ""
    if physical_label == "14:59":
        return "15:00"
    return physical_label


def _physical_label_for_source_close_label(raw_label: str) -> str:
    if raw_label == "11:30":
        return "13:00"
    if raw_label == "15:00":
        return "14:59"
    if not re.fullmatch(r"\d{2}:\d{2}", raw_label or ""):
        return ""
    try:
        return validate_ashare_c1_minute_label(raw_label)
    except MinuteLabelNormalizationError:
        return ""


def build_n3_c1_scoped_artifact_plan(
    active_scope_artifact: Mapping[str, Any] | None,
    *,
    target_minute_label: str,
    observed_at: Any,
    source_artifact_path: str | None = None,
    source_artifact_hash: str | None = None,
    metric_context_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an artifact-first scoped C1 plan from an explicit N5 scope artifact."""

    scope = dict(active_scope_artifact or {})
    for_trade_date = str(scope.get("for_trade_date") or "")
    base = _base_artifact(
        for_trade_date=for_trade_date,
        target_minute_label=target_minute_label,
        source_artifact_path=source_artifact_path,
        source_artifact_hash=source_artifact_hash,
    )

    boundary_reason = _scope_boundary_block_reason(scope)
    if boundary_reason:
        return _blocked_artifact(base, boundary_reason)

    if not _valid_trade_date(for_trade_date):
        return _blocked_artifact(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)

    scope_rows = list(scope.get("scope_rows") or [])
    if _empty_scope(scope, scope_rows):
        base.update(
            {
                "artifact_status": "noop",
                "empty_scope_noop": True,
                "scope_count": 0,
                "scope_rows": [],
                "metric_context_status": "noop",
                "metric_context_count": 0,
                "metric_context_rows": [],
            }
        )
        return base

    normalized_rows = _expand_scope_rows_for_metric_artifact(scope, scope_rows, for_trade_date=for_trade_date)
    if normalized_rows is None:
        return _blocked_artifact(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
    if not normalized_rows:
        base.update(
            {
                "artifact_status": "noop",
                "empty_scope_noop": True,
                "scope_count": 0,
                "scope_rows": [],
                "metric_context_status": "noop",
                "metric_context_count": 0,
                "metric_context_rows": [],
            }
        )
        return base

    metric_context = _normalize_metric_context_rows(metric_context_rows or [])
    if metric_context and not _metric_context_matches_scope(metric_context, normalized_rows, for_trade_date):
        return _blocked_artifact(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)

    minute_status = is_c1_minute_closed_for_scoped_artifact(for_trade_date, target_minute_label, observed_at)
    if minute_status["status"] == "blocked":
        return _blocked_artifact(base, minute_status["reason"])

    normalized_rows.sort(
        key=lambda row: (
            row["asset_kind"],
            row["identity_key"],
            row["direction"],
            row["signal_type"],
            row["condition_key"],
        )
    )
    base.update(
        {
            "artifact_status": "planned",
            "empty_scope_noop": False,
            "scope_count": len(normalized_rows),
            "scope_rows": normalized_rows,
            "metric_context_status": "ready" if metric_context else "missing",
            "metric_context_count": len(metric_context),
            "metric_context_rows": metric_context,
            "closed_minute_contract": minute_status,
        }
    )
    return base


def build_n3_c1_scoped_current_day_staging_artifact(
    active_scope_artifact: Mapping[str, Any] | None,
    *,
    pull_plan_artifact: Mapping[str, Any] | None,
    source_rows_artifact: Mapping[str, Any] | None,
    target_hhmm: str,
    observed_at: Any,
    source_pull_plan_path: str | None = None,
    source_pull_plan_hash: str | None = None,
    source_rows_artifact_path: str | None = None,
    source_rows_artifact_hash: str | None = None,
) -> dict[str, Any]:
    """Build local scoped current-day staging from explicit source rows."""

    scope = dict(active_scope_artifact or {})
    pull_plan = dict(pull_plan_artifact or {})
    source_rows = dict(source_rows_artifact or {})
    for_trade_date = str(scope.get("for_trade_date") or pull_plan.get("for_trade_date") or source_rows.get("for_trade_date") or "")
    hhmm = _hhmm_digits(target_hhmm)
    base = _base_current_day_staging_artifact(
        for_trade_date=for_trade_date,
        target_hhmm=hhmm,
        observed_at=observed_at,
        source_pull_plan_path=source_pull_plan_path,
        source_pull_plan_hash=source_pull_plan_hash,
        source_rows_artifact_path=source_rows_artifact_path,
        source_rows_artifact_hash=source_rows_artifact_hash,
    )

    boundary_reason = _scope_boundary_block_reason(scope)
    if boundary_reason:
        return _blocked_current_day_staging_artifact(base, boundary_reason)
    if not _valid_trade_date(for_trade_date):
        return _blocked_current_day_staging_artifact(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
    plan_reason = _pull_plan_boundary_block_reason(pull_plan, for_trade_date)
    if plan_reason:
        return _blocked_current_day_staging_artifact(base, plan_reason)
    source_reason = _current_day_source_rows_boundary_block_reason(source_rows, for_trade_date)
    if source_reason:
        return _blocked_current_day_staging_artifact(base, source_reason)

    plan_rows = list(pull_plan.get("plan_rows") or [])
    if not plan_rows:
        return _blocked_current_day_staging_artifact(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)

    source_gap_labels = {
        _hhmm_label(gap.get("physical_c1_label"))
        for gap in pull_plan.get("source_gap_physical_labels") or []
        if isinstance(gap, Mapping)
    }
    indexed_source_rows: dict[tuple[tuple[str, ...], str], dict[str, Any]] = {}
    for row in source_rows.get("closed_minute_rows") or source_rows.get("source_rows") or []:
        normalized_row = _normalize_current_day_source_row(row, for_trade_date=for_trade_date)
        if normalized_row is None:
            return _blocked_current_day_staging_artifact(base, BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH)
        if str(normalized_row["physical_c1_label"]) in source_gap_labels:
            continue
        key = (_object_scope_key(_normalize_object_scope_row(normalized_row)), str(normalized_row["physical_c1_label"]))
        if key in indexed_source_rows:
            return _blocked_current_day_staging_artifact(base, BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH)
        indexed_source_rows[key] = normalized_row

    expected_rows: list[dict[str, Any]] = []
    for plan_row in plan_rows:
        scope_row = _normalize_object_scope_row(plan_row)
        if not _valid_object_scope_row(scope_row, for_trade_date):
            return _blocked_current_day_staging_artifact(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
        for physical_label in plan_row.get("required_physical_labels") or []:
            label = _hhmm_label(physical_label)
            source_row = indexed_source_rows.get((_object_scope_key(scope_row), label))
            if not source_row:
                return _blocked_current_day_staging_artifact(base, BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH)
            expected_rows.append(source_row)
    if len(indexed_source_rows) != len(expected_rows):
        return _blocked_current_day_staging_artifact(base, BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH)

    expected_rows.sort(
        key=lambda row: (
            row["asset_kind"],
            row["identity_key"],
            _minute_sort_key(row),
        )
    )
    base.update(
        {
            "artifact_status": "passed",
            "blocked_reason": None,
            "scope_count": int(pull_plan.get("scope_count") or len(plan_rows)),
            "closed_minute_row_count": len(expected_rows),
            "expected_closed_minute_row_count": int(pull_plan.get("expected_rows_after_pull") or len(expected_rows)),
            "closed_minute_rows": [_compact_current_day_staging_row(row) for row in expected_rows],
            "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
            "source_gap_policy": str(pull_plan.get("source_gap_policy") or SOURCE_GAP_POLICY),
            "required_physical_labels": list(pull_plan.get("required_physical_labels") or []),
            "required_raw_source_labels": list(pull_plan.get("required_raw_source_labels") or []),
            "source_gap_physical_labels": list(pull_plan.get("source_gap_physical_labels") or []),
        }
    )
    if base["expected_closed_minute_row_count"] != base["closed_minute_row_count"]:
        return _blocked_current_day_staging_artifact(base, BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH)
    return base


def build_n3_c1_n3t_metric_context_source_artifact(
    active_scope_artifact: Mapping[str, Any] | None,
    *,
    staging_artifact: Mapping[str, Any] | None,
    previous_day_minute_rows: Sequence[Mapping[str, Any]] | None,
    target_hhmm: str,
    observed_at: Any,
    source_staging_artifact_path: str | None = None,
    source_staging_artifact_hash: str | None = None,
) -> dict[str, Any]:
    """Build N3T metric-context source rows from explicit scoped C1 artifacts."""

    scope = dict(active_scope_artifact or {})
    staging = dict(staging_artifact or {})
    for_trade_date = str(scope.get("for_trade_date") or staging.get("for_trade_date") or "")
    hhmm = _hhmm_digits(target_hhmm)
    base = _base_metric_context_source_artifact(
        for_trade_date=for_trade_date,
        target_hhmm=hhmm,
        observed_at=observed_at,
        source_staging_artifact_path=source_staging_artifact_path,
        source_staging_artifact_hash=source_staging_artifact_hash,
    )

    boundary_reason = _scope_boundary_block_reason(scope)
    if boundary_reason:
        return _blocked_metric_context_source_artifact(base, boundary_reason)
    if not _valid_trade_date(for_trade_date):
        return _blocked_metric_context_source_artifact(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
    staging_reason = _staging_boundary_block_reason(staging, for_trade_date)
    if staging_reason:
        return _blocked_metric_context_source_artifact(base, staging_reason)

    scope_rows = list(scope.get("scope_rows") or [])
    if _empty_scope(scope, scope_rows):
        base.update(
            {
                "artifact_status": "noop",
                "metric_context_status": "noop",
                "scope_count": 0,
                "metric_context_count": 0,
                "metric_context_rows": [],
            }
        )
        return base

    object_scope_rows = _normalize_c1_object_scope_rows(scope_rows, for_trade_date=for_trade_date)
    normalized_scope_rows = _expand_scope_rows_for_metric_artifact(scope, scope_rows, for_trade_date=for_trade_date)
    if object_scope_rows is None or normalized_scope_rows is None:
        return _blocked_metric_context_source_artifact(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
    if not normalized_scope_rows:
        base.update(
            {
                "artifact_status": "noop",
                "metric_context_status": "noop",
                "scope_count": 0,
                "metric_context_count": 0,
                "metric_context_rows": [],
            }
        )
        return base

    refs_by_object: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for scope_row in normalized_scope_rows:
        refs_by_object.setdefault(_object_scope_key(scope_row), []).append(scope_row)
    current_rows_by_scope = _index_current_day_closed_rows(staging.get("closed_minute_rows") or [])
    previous_rows_by_identity = _index_previous_day_minute_rows(previous_day_minute_rows or [])
    target_label = _hhmm_label(target_hhmm)
    metric_context_rows: list[dict[str, Any]] = []
    for object_row in object_scope_rows:
        object_key = _object_scope_key(object_row)
        current_rows = _current_rows_through_target(
            current_rows_by_scope.get(object_key) or [],
            labels=canonical_ashare_1m_labels(for_trade_date),
            target_label=target_label,
        )
        previous_rows = previous_rows_by_identity.get((object_row["asset_kind"], object_row["identity_key"])) or []
        if not current_rows:
            return _blocked_metric_context_source_artifact(base, BLOCKED_N3_C1_SCOPED_CONTEXT_INSUFFICIENT)
        if not previous_rows:
            return _blocked_metric_context_source_artifact(base, BLOCKED_PREVIOUS_DAY_RAW_C1_CONTEXT_INSUFFICIENT)
        metric_values = _derive_metric_values(current_rows=current_rows, previous_rows=previous_rows)
        missing_metric_fields = [
            field
            for field in REQUIRED_METRIC_CONTEXT_FIELDS
            if metric_values.get(field) is None
        ]
        if missing_metric_fields:
            reason = _missing_metric_context_block_reason(
                metric_values=metric_values,
                missing_fields=missing_metric_fields,
            )
            blocked = _blocked_metric_context_source_artifact(base, reason)
            blocked.update(
                {
                    "blocked_stage": _metric_context_blocked_stage(reason),
                    "missing_metric_fields": missing_metric_fields,
                }
            )
            return blocked
        for scope_row in refs_by_object.get(object_key, []):
            metric_context_rows.append(
                {
                    **scope_row,
                    "source_closed_minute_bar_ids": [_minute_row_ref(row) for row in current_rows],
                    "closed_minute_rows": [_compact_minute_row(row) for row in current_rows],
                    "previous_day_minute_refs": [_minute_row_ref(row) for row in previous_rows],
                    "metric_values": metric_values,
                    "deterministic_derivation_inputs": {
                        "current_day_source": "scoped_current_day_c1_staging",
                        "previous_day_same_window_amount_source": "scoped_previous_day_raw_c1_sum",
                        "boundary_policy_version": BOUNDARY_POLICY_VERSION,
                        "previous_period_sources": {
                            "1m": metric_values.get("previous_1m_period_source"),
                            "5m": metric_values.get("previous_5m_period_source"),
                            "30m": metric_values.get("previous_30m_period_source"),
                            "120m": metric_values.get("previous_120m_period_source"),
                        },
                        "source_staging_artifact_path": source_staging_artifact_path,
                        "source_staging_artifact_hash": source_staging_artifact_hash,
                    },
                }
            )

    if not _metric_context_matches_scope(metric_context_rows, normalized_scope_rows, for_trade_date):
        return _blocked_metric_context_source_artifact(base, BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH)
    metric_context_rows.sort(
        key=lambda row: (
            row["asset_kind"],
            row["identity_key"],
            row["direction"],
            row["signal_type"],
            row["condition_key"],
        )
    )
    base.update(
        {
            "artifact_status": "planned",
            "blocked_reason": None,
            "scope_count": len(normalized_scope_rows),
            "metric_context_status": "ready",
            "metric_context_count": len(metric_context_rows),
            "metric_context_rows": metric_context_rows,
            "previous_day_context": {
                "source": "scoped_previous_day_raw_c1_sum",
                "row_count": sum(len(rows) for rows in previous_rows_by_identity.values()),
                "identity_count": len(previous_rows_by_identity),
            },
        }
    )
    return base


def is_c1_minute_closed_for_scoped_artifact(
    for_trade_date: str,
    minute_label: str,
    observed_at: Any,
) -> dict[str, Any]:
    """Return closed-minute eligibility for an N3 scoped C1 artifact plan."""

    try:
        close_time = _minute_close_time(for_trade_date=for_trade_date, minute_label=minute_label)
        observed = _coerce_shanghai(observed_at)
    except MinuteLabelNormalizationError as exc:
        return {
            "status": "blocked",
            "reason": BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE if BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE in str(exc) else BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH,
            "minute_label": str(minute_label or ""),
        }
    except (TypeError, ValueError):
        return {
            "status": "blocked",
            "reason": BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH,
            "minute_label": str(minute_label or ""),
        }
    if observed < close_time:
        return {
            "status": "blocked",
            "reason": BLOCKED_C1_MINUTE_NOT_CLOSED,
            "minute_label": str(minute_label),
            "usable_after": close_time.isoformat(),
            "observed_at": observed.isoformat(),
        }
    return {
        "status": "closed",
        "reason": None,
        "minute_label": str(minute_label),
        "usable_after": close_time.isoformat(),
        "observed_at": observed.isoformat(),
    }


def _base_artifact(
    *,
    for_trade_date: str,
    target_minute_label: str,
    source_artifact_path: str | None,
    source_artifact_hash: str | None,
) -> dict[str, Any]:
    side_effects = _false_side_effects()
    return {
        "artifact_type": OUTPUT_ARTIFACT_TYPE,
        "artifact_schema_version": OUTPUT_ARTIFACT_SCHEMA_VERSION,
        "producer_layer": "N3_market_data",
        "input_artifact_type": INPUT_ARTIFACT_TYPE,
        "for_trade_date": str(for_trade_date or ""),
        "target_minute_label": str(target_minute_label or ""),
        "artifact_status": "blocked",
        "blocked_reason": None,
        "scope_count": 0,
        "scope_rows": [],
        "metric_context_status": "missing",
        "metric_context_count": 0,
        "metric_context_rows": [],
        "empty_scope_noop": False,
        "full_market_fallback_allowed": False,
        "n3_scans_n5_internals": False,
        "canonical_c1_write_gate_required": "N3_C1_SCOPED_EXECUTE_GATE",
        "source_scope_artifact": {
            "path": source_artifact_path,
            "hash": source_artifact_hash,
            "artifact_type": INPUT_ARTIFACT_TYPE,
        },
        "side_effects": side_effects,
        "boundary": {
            **side_effects,
            "input_must_be_explicit_n5_active_scope_snapshot": True,
            "n3_direct_n5_table_scan_allowed": False,
            "canonical_c1_write_allowed_in_artifact_first_gate": False,
            "n3_outbox_write_allowed": False,
            "runtime_execute": False,
        },
        **side_effects,
    }


def _base_current_day_pull_plan(
    *,
    for_trade_date: str,
    target_minute_label: str,
    source_artifact_path: str | None,
    source_artifact_hash: str | None,
) -> dict[str, Any]:
    side_effects = _false_side_effects()
    return {
        "artifact_type": CURRENT_DAY_PULL_PLAN_TYPE,
        "artifact_schema_version": CURRENT_DAY_PULL_PLAN_SCHEMA_VERSION,
        "producer_layer": "N3_market_data",
        "input_artifact_type": INPUT_ARTIFACT_TYPE,
        "for_trade_date": str(for_trade_date or ""),
        "target_minute_label": str(target_minute_label or ""),
        "normalized_target_minute_label": str(target_minute_label or ""),
        "target_minute_boundary_policy": None,
        "target_minute_boundary_reason": None,
        "expected_closed_time": None,
        "plan_status": "blocked",
        "blocked_reason": None,
        "scope_count": 0,
        "plan_rows": [],
        "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
        "source_gap_policy": SOURCE_GAP_POLICY,
        "source_label_semantics": SOURCE_LABEL_SEMANTICS,
        "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
        "required_physical_labels": [],
        "required_raw_source_labels": [],
        "source_gap_physical_labels": [],
        "metric_context_dependencies": [],
        "expected_rows_after_pull": 0,
        "empty_scope_noop": False,
        "full_market_fallback_allowed": False,
        "n3_scans_n5_internals": False,
        "future_pull_execute_gate_required": CURRENT_DAY_PULL_EXECUTE_GATE,
        "canonical_c1_write_gate_required": CANONICAL_C1_EXECUTE_GATE,
        "n3t_remains_blocked_until_metric_context_ready": True,
        "source_scope_artifact": {
            "path": source_artifact_path,
            "hash": source_artifact_hash,
            "artifact_type": INPUT_ARTIFACT_TYPE,
        },
        "side_effects": side_effects,
        "boundary": {
            **side_effects,
            "input_must_be_explicit_n5_active_scope_snapshot": True,
            "n3_direct_n5_table_scan_allowed": False,
            "full_market_fallback_allowed": False,
            "artifact_staging_only": True,
            "market_pull_allowed_in_this_gate": False,
            "future_pull_execute_requires_explicit_gate": True,
            "canonical_c1_write_allowed_in_artifact_first_gate": False,
            "n3_outbox_write_allowed": False,
            "runtime_execute": False,
        },
        **side_effects,
    }


def _base_current_day_staging_artifact(
    *,
    for_trade_date: str,
    target_hhmm: str,
    observed_at: Any,
    source_pull_plan_path: str | None,
    source_pull_plan_hash: str | None,
    source_rows_artifact_path: str | None,
    source_rows_artifact_hash: str | None,
) -> dict[str, Any]:
    side_effects = _false_side_effects()
    return {
        "artifact_type": CURRENT_DAY_STAGING_ARTIFACT_TYPE,
        "artifact_schema_version": CURRENT_DAY_PULL_PLAN_SCHEMA_VERSION,
        "producer_layer": "N3_market_data",
        "input_artifact_type": CURRENT_DAY_SOURCE_ROWS_TYPE,
        "for_trade_date": str(for_trade_date or ""),
        "target_hhmm": str(target_hhmm or ""),
        "target_minute_label": _hhmm_label(target_hhmm),
        "observed_at": str(observed_at or ""),
        "artifact_status": "blocked",
        "blocked_reason": None,
        "scope_count": 0,
        "closed_minute_row_count": 0,
        "expected_closed_minute_row_count": 0,
        "closed_minute_rows": [],
        "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
        "source_gap_policy": SOURCE_GAP_POLICY,
        "source_label_semantics": SOURCE_LABEL_SEMANTICS,
        "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
        "required_physical_labels": [],
        "required_raw_source_labels": [],
        "source_gap_physical_labels": [],
        "source_pull_plan_artifact": {
            "path": source_pull_plan_path,
            "hash": source_pull_plan_hash,
            "artifact_type": CURRENT_DAY_PULL_PLAN_TYPE,
        },
        "source_rows_artifact": {
            "path": source_rows_artifact_path,
            "hash": source_rows_artifact_hash,
            "artifact_type": CURRENT_DAY_SOURCE_ROWS_TYPE,
        },
        "full_market_fallback_allowed": False,
        "n3_scans_n5_internals": False,
        "side_effects": side_effects,
        "boundary": {
            **side_effects,
            "input_must_be_explicit_n5_active_scope_snapshot": True,
            "input_must_be_explicit_current_day_source_rows": True,
            "n3_direct_n5_table_scan_allowed": False,
            "full_market_fallback_allowed": False,
            "canonical_c1_write_allowed": False,
            "n3_outbox_write_allowed": False,
            "runtime_execute": False,
        },
        **side_effects,
    }


def _base_metric_context_source_artifact(
    *,
    for_trade_date: str,
    target_hhmm: str,
    observed_at: Any,
    source_staging_artifact_path: str | None,
    source_staging_artifact_hash: str | None,
) -> dict[str, Any]:
    side_effects = _false_side_effects()
    return {
        "artifact_type": METRIC_CONTEXT_SOURCE_ARTIFACT_TYPE,
        "artifact_schema_version": OUTPUT_ARTIFACT_SCHEMA_VERSION,
        "producer_layer": "N3_market_data",
        "input_artifact_type": "n3_c1_scoped_current_day_staging_v1",
        "for_trade_date": str(for_trade_date or ""),
        "target_hhmm": str(target_hhmm or ""),
        "target_minute_label": _hhmm_label(target_hhmm),
        "observed_at": str(observed_at or ""),
        "artifact_status": "blocked",
        "blocked_reason": None,
        "scope_count": 0,
        "metric_context_status": "blocked",
        "metric_context_count": 0,
        "metric_context_rows": [],
        "previous_day_context": {
            "source": "scoped_previous_day_raw_c1_sum",
            "row_count": 0,
            "identity_count": 0,
        },
        "source_staging_artifact": {
            "path": source_staging_artifact_path,
            "hash": source_staging_artifact_hash,
            "artifact_type": "n3_c1_scoped_current_day_staging_v1",
        },
        "full_market_fallback_allowed": False,
        "n3_scans_n5_internals": False,
        "side_effects": side_effects,
        "boundary": {
            **side_effects,
            "input_must_be_explicit_current_day_staging_artifact": True,
            "previous_day_context_must_be_explicit": True,
            "n3_direct_n5_table_scan_allowed": False,
            "full_market_fallback_allowed": False,
            "canonical_c1_write_allowed": False,
            "n3_outbox_write_allowed": False,
            "runtime_execute": False,
        },
        **side_effects,
    }


def _blocked_metric_context_source_artifact(base: Mapping[str, Any], reason: str) -> dict[str, Any]:
    artifact = dict(base)
    artifact.update(
        {
            "artifact_status": "blocked",
            "blocked_reason": reason,
            "scope_count": 0,
            "metric_context_status": "blocked",
            "metric_context_count": 0,
            "metric_context_rows": [],
            "full_market_fallback_allowed": False,
            "n3_scans_n5_internals": False,
        }
    )
    return artifact


def _missing_metric_context_block_reason(
    *,
    metric_values: Mapping[str, Any],
    missing_fields: Sequence[str],
) -> str:
    if not metric_values:
        return BLOCKED_N3T_FIXED_PERIOD_WINDOW_UNAVAILABLE
    if (
        "current_5m_amount" in missing_fields
        and previous_period_sources_are_valid(metric_values)
    ):
        return BLOCKED_N3T_CURRENT_5M_SAME_WINDOW_SOURCE_MISSING
    return BLOCKED_N3T_METRIC_CONTEXT_FIELDS_MISSING


def _metric_context_blocked_stage(reason: str) -> str:
    if reason == BLOCKED_N3T_CURRENT_5M_SAME_WINDOW_SOURCE_MISSING:
        return "current_5m_same_window_source_missing"
    if reason == BLOCKED_N3T_FIXED_PERIOD_WINDOW_UNAVAILABLE:
        return "fixed_period_window_unavailable"
    return "metric_context_fields_missing"


def _blocked_current_day_staging_artifact(base: Mapping[str, Any], reason: str) -> dict[str, Any]:
    artifact = dict(base)
    artifact.update(
        {
            "artifact_status": "blocked",
            "blocked_reason": reason,
            "scope_count": 0,
            "closed_minute_row_count": 0,
            "closed_minute_rows": [],
            "full_market_fallback_allowed": False,
            "n3_scans_n5_internals": False,
        }
    )
    return artifact


def _blocked_current_day_pull_plan(base: Mapping[str, Any], reason: str) -> dict[str, Any]:
    artifact = dict(base)
    artifact.update(
        {
            "plan_status": "blocked",
            "blocked_reason": reason,
            "scope_count": 0,
            "plan_rows": [],
            "empty_scope_noop": False,
            "full_market_fallback_allowed": False,
            "n3_scans_n5_internals": False,
        }
    )
    return artifact


def _normalize_current_day_pull_target_minute_label(target_minute_label: Any) -> dict[str, Any]:
    label = _hhmm_text(target_minute_label)
    try:
        normalized = validate_ashare_c1_minute_label(label)
    except MinuteLabelNormalizationError:
        if label == "15:00":
            return {
                "status": "normalized",
                "reason": None,
                "target_minute_label": label,
                "normalized_target_minute_label": "14:59",
                "target_minute_boundary_policy": CLOSE_BOUNDARY_TARGET_POLICY,
                "target_minute_boundary_reason": "close_boundary_not_physical_c1_label",
            }
        return {
            "status": "blocked",
            "reason": BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE,
            "target_minute_label": label,
            "normalized_target_minute_label": None,
            "target_minute_boundary_policy": None,
            "target_minute_boundary_reason": None,
        }
    return {
        "status": "valid",
        "reason": None,
        "target_minute_label": label,
        "normalized_target_minute_label": normalized,
        "target_minute_boundary_policy": None,
        "target_minute_boundary_reason": None,
    }


def _is_lunch_close_missing_source(source_label: Mapping[str, Any]) -> bool:
    return (
        source_label.get("physical_c1_label") == "11:29"
        and source_label.get("raw_source_label") == "11:30"
        and source_label.get("reason") == BLOCKED_SOURCE_CLOSE_LABEL_NOT_MAPPABLE
    )


def _lunch_close_source_gap(source_label: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "physical_c1_label": str(source_label.get("physical_c1_label") or "11:29"),
        "missing_raw_source_label": str(source_label.get("raw_source_label") or "11:30"),
        "reason": LUNCH_CLOSE_MISSING_SOURCE_REASON,
        "metric_context_dependency": "session_boundary_previous_raw_c1_context_required",
        "fake_or_synthetic_row": False,
    }


def _open_boundary_source_gap() -> dict[str, Any]:
    return {
        "physical_c1_label": "09:30",
        "missing_raw_source_label": "09:30",
        "reason": OPEN_BOUNDARY_MISSING_SOURCE_REASON,
        "metric_context_dependency": "session_open_first_available_raw_c1_context_required",
        "fake_or_synthetic_row": False,
    }


def _current_day_pull_plan_row(
    row: Mapping[str, str],
    *,
    target_minute_label: str,
    normalized_target_minute_label: str,
    minute_status: Mapping[str, Any],
    source_label_plan: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **dict(row),
        "required_data_kind": "minute_bar_1m",
        "target_minute_label": str(target_minute_label or ""),
        "normalized_target_minute_label": str(normalized_target_minute_label or ""),
        "expected_closed_time": minute_status.get("usable_after"),
        "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
        "source_gap_policy": source_label_plan.get("source_gap_policy"),
        "source_label_semantics": SOURCE_LABEL_SEMANTICS,
        "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
        "required_physical_labels": list(source_label_plan.get("required_physical_labels") or []),
        "required_raw_source_labels": list(source_label_plan.get("required_raw_source_labels") or []),
        "source_gap_physical_labels": list(source_label_plan.get("source_gap_physical_labels") or []),
        "metric_context_dependencies": list(source_label_plan.get("metric_context_dependencies") or []),
        "artifact_staging_only": True,
        "future_pull_execute_required": True,
        "future_pull_execute_gate_required": CURRENT_DAY_PULL_EXECUTE_GATE,
        "writes_canonical_minute_bar_1m": False,
        "writes_n3_outbox": False,
        "consumes_n4_outbox": False,
        "updates_n4_outbox": False,
    }


def _blocked_artifact(base: Mapping[str, Any], reason: str) -> dict[str, Any]:
    artifact = dict(base)
    artifact.update(
        {
            "artifact_status": "blocked",
            "blocked_reason": reason,
            "scope_count": 0,
            "scope_rows": [],
            "metric_context_status": "blocked",
            "metric_context_count": 0,
            "metric_context_rows": [],
            "empty_scope_noop": False,
            "full_market_fallback_allowed": False,
            "n3_scans_n5_internals": False,
        }
    )
    return artifact


def _scope_boundary_block_reason(scope: Mapping[str, Any]) -> str | None:
    if scope.get("artifact_type") != INPUT_ARTIFACT_TYPE:
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    if scope.get("full_market_fallback_allowed") is True:
        return BLOCKED_FULL_MARKET_FALLBACK_RISK
    if scope.get("n3_scans_n5_internals") is True:
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    if scope.get("db_write_allowed") is True:
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    if scope.get("n4_outbox_status_update_allowed") is True:
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    if scope.get("updates_n4_outbox") is True:
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    return None


def _pull_plan_boundary_block_reason(pull_plan: Mapping[str, Any], for_trade_date: str) -> str | None:
    if pull_plan.get("artifact_type") != CURRENT_DAY_PULL_PLAN_TYPE:
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    if pull_plan.get("plan_status") != "planned":
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    if str(pull_plan.get("for_trade_date") or "") not in {"", for_trade_date}:
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    if pull_plan.get("full_market_fallback_allowed") is True or pull_plan.get("full_market_fallback_used") is True:
        return BLOCKED_FULL_MARKET_FALLBACK_RISK
    for flag in SIDE_EFFECT_FLAGS:
        if pull_plan.get(flag) is True:
            return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    return None


def _current_day_source_rows_boundary_block_reason(source_rows: Mapping[str, Any], for_trade_date: str) -> str | None:
    if source_rows.get("artifact_type") != CURRENT_DAY_SOURCE_ROWS_TYPE:
        return BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH
    if str(source_rows.get("for_trade_date") or "") not in {"", for_trade_date}:
        return BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH
    if source_rows.get("full_market_fallback_allowed") is True or source_rows.get("full_market_fallback_used") is True:
        return BLOCKED_FULL_MARKET_FALLBACK_RISK
    for flag in SIDE_EFFECT_FLAGS:
        if flag == "market_data_pulled":
            continue
        if source_rows.get(flag) is True:
            return BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH
    if source_rows.get("touches_n4_n5_n6_outbox") is True:
        return BLOCKED_C1_SOURCE_ROWS_CONTRACT_MISMATCH
    return None


def _staging_boundary_block_reason(staging: Mapping[str, Any], for_trade_date: str) -> str | None:
    if staging.get("artifact_type") != CURRENT_DAY_STAGING_ARTIFACT_TYPE:
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    if staging.get("artifact_status") != "passed":
        return BLOCKED_N3_C1_SCOPED_CONTEXT_INSUFFICIENT
    if str(staging.get("for_trade_date") or "") not in {"", for_trade_date}:
        return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    if staging.get("full_market_fallback_allowed") is True or staging.get("full_market_fallback_used") is True:
        return BLOCKED_FULL_MARKET_FALLBACK_RISK
    for flag in SIDE_EFFECT_FLAGS:
        if flag == "market_data_pulled":
            continue
        if staging.get(flag) is True:
            return BLOCKED_N3_C1_SCOPE_CONTRACT_MISMATCH
    return None


def _empty_scope(scope: Mapping[str, Any], scope_rows: list[Any]) -> bool:
    return bool(scope.get("empty_scope_noop")) or not scope_rows or scope.get("scope_status") == "empty"


def _normalize_scope_row(row: Any) -> dict[str, str]:
    source = dict(row or {})
    return {field: str(source.get(field) or "") for field in REQUIRED_SCOPE_GRAIN}


def _normalize_object_scope_row(row: Any) -> dict[str, Any]:
    source = dict(row or {})
    output: dict[str, Any] = {field: str(source.get(field) or "") for field in OBJECT_SCOPE_GRAIN}
    if "active_tracking_refs" in source:
        output["active_tracking_refs"] = list(source.get("active_tracking_refs") or [])
    if "attention_event_refs" in source:
        output["attention_event_refs"] = list(source.get("attention_event_refs") or [])
    return output


def _valid_scope_row(
    row: Mapping[str, str],
    for_trade_date: str,
    *,
    source_trigger_run_id_required: bool = True,
) -> bool:
    required_fields = REQUIRED_SCOPE_GRAIN
    if not source_trigger_run_id_required:
        required_fields = tuple(field for field in REQUIRED_SCOPE_GRAIN if field not in ACTIVE_REF_OPTIONAL_SCOPE_GRAIN)
    if any(not row.get(field) for field in required_fields):
        return False
    if row["for_trade_date"] != for_trade_date:
        return False
    if row["asset_kind"] not in ASSET_KINDS:
        return False
    if not row["identity_key"].startswith(f"{row['asset_kind']}:"):
        return False
    if row["scope_status"] != "active":
        return False
    return True


def _valid_object_scope_row(row: Mapping[str, Any], for_trade_date: str) -> bool:
    if any(not row.get(field) for field in OBJECT_SCOPE_GRAIN):
        return False
    if row["for_trade_date"] != for_trade_date:
        return False
    if row["asset_kind"] not in ASSET_KINDS:
        return False
    if not row["identity_key"].startswith(f"{row['asset_kind']}:"):
        return False
    if row["scope_status"] != "active":
        return False
    return True


def _normalize_c1_object_scope_rows(scope_rows: Sequence[Any], *, for_trade_date: str) -> list[dict[str, Any]] | None:
    by_object: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in scope_rows:
        source = dict(row or {})
        refs = list(source.get("active_tracking_refs") or [])
        attention_refs = list(source.get("attention_event_refs") or [])
        if refs or attention_refs or source.get("scope_granularity") == "object":
            object_row = _normalize_object_scope_row(source)
            if not _valid_object_scope_row(object_row, for_trade_date):
                return None
            key = _object_scope_key(object_row)
            merged = by_object.setdefault(
                key,
                {
                    **{field: object_row[field] for field in OBJECT_SCOPE_GRAIN},
                    "active_tracking_refs": [],
                    "attention_event_refs": [],
                },
            )
            merged["active_tracking_refs"].extend(refs)
            merged["attention_event_refs"].extend(attention_refs)
            continue
        scope_row = _normalize_scope_row(source)
        if not _valid_scope_row(scope_row, for_trade_date):
            return None
        key = _object_scope_key(scope_row)
        merged = by_object.setdefault(
            key,
            {
                **{field: scope_row[field] for field in OBJECT_SCOPE_GRAIN},
                "active_tracking_refs": [],
                "attention_event_refs": [],
            },
        )
        merged["active_tracking_refs"].append(scope_row)
    return list(by_object.values())


def _expand_active_scope_rows(scope_rows: Sequence[Any], *, for_trade_date: str) -> list[dict[str, str]] | None:
    expanded: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in scope_rows:
        source = dict(row or {})
        refs = list(source.get("active_tracking_refs") or [])
        if refs:
            for ref in refs:
                normalized = _normalize_scope_row(ref)
                if not _valid_scope_row(normalized, for_trade_date, source_trigger_run_id_required=False):
                    return None
                key = _scope_key(normalized)
                if key not in seen:
                    expanded.append(normalized)
                    seen.add(key)
            continue
        if source.get("attention_event_refs") is not None or source.get("scope_granularity") == "object":
            continue
        normalized = _normalize_scope_row(source)
        if not _valid_scope_row(normalized, for_trade_date):
            return None
        key = _scope_key(normalized)
        if key not in seen:
            expanded.append(normalized)
            seen.add(key)
    return expanded


def _expand_scope_rows_for_metric_artifact(
    scope: Mapping[str, Any],
    scope_rows: Sequence[Any],
    *,
    for_trade_date: str,
) -> list[dict[str, Any]] | None:
    if scope.get("object_minute_scope") is True:
        return _expand_object_minute_scope_rows(scope_rows, for_trade_date=for_trade_date)
    return _expand_active_scope_rows(scope_rows, for_trade_date=for_trade_date)


def _expand_object_minute_scope_rows(scope_rows: Sequence[Any], *, for_trade_date: str) -> list[dict[str, Any]] | None:
    expanded: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in scope_rows:
        source = dict(row or {})
        refs = list(source.get("active_tracking_refs") or [])
        if not refs:
            normalized = _normalize_scope_row(source)
            if not _valid_scope_row(normalized, for_trade_date):
                return None
            key = _object_minute_scope_key(normalized)
            if key not in seen:
                expanded.append(normalized)
                seen.add(key)
            continue
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for ref_source in refs:
            ref = dict(ref_source or {})
            enriched = {
                "for_trade_date": source.get("for_trade_date"),
                "asset_kind": source.get("asset_kind"),
                "identity_key": source.get("identity_key"),
                "scope_status": source.get("scope_status"),
                **ref,
            }
            normalized = _normalize_scope_row(enriched)
            if not _valid_scope_row(normalized, for_trade_date, source_trigger_run_id_required=False):
                return None
            grouped.setdefault(_object_minute_scope_key(normalized), []).append(enriched)
        for key, group_refs in grouped.items():
            if key in seen:
                continue
            primary = sorted(group_refs, key=_object_minute_primary_ref_sort_key)[0]
            normalized = _normalize_scope_row(primary)
            normalized.update(
                {
                    "object_minute_scope": True,
                    "object_minute_ref_count": len(group_refs),
                    "object_minute_ref_trace": _compact_object_minute_ref_trace(group_refs),
                }
            )
            expanded.append(normalized)
            seen.add(key)
    return expanded


def _object_minute_scope_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("for_trade_date") or ""),
        str(row.get("asset_kind") or ""),
        str(row.get("identity_key") or ""),
        str(row.get("direction") or ""),
        str(row.get("signal_type") or ""),
    )


def _object_minute_primary_ref_sort_key(ref: Mapping[str, Any]) -> tuple[int, str, str, str]:
    event_time = str(ref.get("source_trigger_event_time") or ref.get("latest_n4_event_time") or ref.get("trigger_time") or "")
    return (
        1 if _is_hint_condition_key(ref.get("condition_key")) else 0,
        _reverse_text_sort_key(event_time),
        str(ref.get("condition_key") or ""),
        str(ref.get("state_key") or ""),
    )


def _reverse_text_sort_key(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(ch)) for ch in str(value or ""))


def _is_hint_condition_key(condition_key: Any) -> bool:
    text = str(condition_key or "").strip().upper()
    return text.startswith("BUY_HINT") or text.startswith("SELL_HINT")


def _compact_object_minute_ref_trace(refs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for ref in refs:
        output.append(
            {
                "state_key": ref.get("state_key"),
                "condition_key": ref.get("condition_key"),
                "source_trigger_event_id": ref.get("source_trigger_event_id"),
                "source_trigger_event_type": ref.get("source_trigger_event_type"),
                "source_trigger_event_time": ref.get("source_trigger_event_time")
                or ref.get("latest_n4_event_time")
                or ref.get("trigger_time"),
            }
        )
    return output


def _normalize_metric_context_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        source = dict(row or {})
        normalized_rows.append(
            {
                **_normalize_scope_row(source),
                "source_closed_minute_bar_ids": list(source.get("source_closed_minute_bar_ids") or []),
                "closed_minute_rows": list(source.get("closed_minute_rows") or []),
                "previous_day_minute_refs": list(source.get("previous_day_minute_refs") or []),
                "metric_values": dict(source.get("metric_values") or {}),
                "deterministic_derivation_inputs": dict(source.get("deterministic_derivation_inputs") or {}),
                "object_minute_scope": bool(source.get("object_minute_scope")),
                "object_minute_ref_count": int(source.get("object_minute_ref_count") or 0),
                "object_minute_ref_trace": list(source.get("object_minute_ref_trace") or []),
            }
        )
    return normalized_rows


def _normalize_current_day_source_row(row: Any, *, for_trade_date: str) -> dict[str, Any] | None:
    source = dict(row or {})
    if source.get("fake_or_synthetic_row") is True:
        return None
    object_scope = _normalize_object_scope_row(source)
    if not _valid_object_scope_row(object_scope, for_trade_date):
        scope = _normalize_scope_row(source)
        if not _valid_scope_row(scope, for_trade_date):
            return None
        object_scope = _normalize_object_scope_row(scope)
    if not _valid_object_scope_row(object_scope, for_trade_date):
        return None
    physical_label = _hhmm_label(source.get("physical_c1_label") or source.get("minute_label") or "")
    raw_label = _hhmm_label(source.get("raw_source_label") or "")
    if not physical_label or not raw_label:
        return None
    mapped = source_close_label_to_physical_start_label(for_trade_date, raw_label)
    if mapped.get("status") != "mapped" or mapped.get("physical_c1_label") != physical_label:
        return None
    if raw_label == "13:00" and physical_label == "11:30":
        return None
    normalized = {
        **object_scope,
        "physical_c1_label": physical_label,
        "raw_source_label": raw_label,
        "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
        "source_label_semantics": SOURCE_LABEL_SEMANTICS,
        "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
        "fake_or_synthetic_row": False,
    }
    if "active_tracking_refs" in source:
        normalized["active_tracking_refs"] = list(source.get("active_tracking_refs") or [])
    if "attention_event_refs" in source:
        normalized["attention_event_refs"] = list(source.get("attention_event_refs") or [])
    for key in ("open", "high", "low", "close", "volume", "amount", "source_row_ref"):
        if key in source:
            normalized[key] = source.get(key)
    return normalized


def _metric_context_matches_scope(
    context_rows: Sequence[Mapping[str, Any]],
    scope_rows: Sequence[Mapping[str, str]],
    for_trade_date: str,
) -> bool:
    object_minute_scope = any(row.get("object_minute_scope") is True for row in scope_rows)
    key_fn = _object_minute_scope_key if object_minute_scope else _scope_key
    scope_keys = {key_fn(row) for row in scope_rows}
    context_keys: set[tuple[str, ...]] = set()
    for row in context_rows:
        context_scope = {field: str(row.get(field) or "") for field in REQUIRED_SCOPE_GRAIN}
        if not _valid_scope_row(context_scope, for_trade_date, source_trigger_run_id_required=False):
            return False
        context_key = key_fn(row if object_minute_scope else context_scope)
        if context_key not in scope_keys or context_key in context_keys:
            return False
        context_keys.add(context_key)
        if not (row.get("source_closed_minute_bar_ids") or row.get("closed_minute_rows")):
            return False
        if not row.get("previous_day_minute_refs"):
            return False
        metric_values = dict(row.get("metric_values") or {})
        if any(metric_values.get(field) is None for field in REQUIRED_METRIC_CONTEXT_FIELDS):
            return False
    return context_keys == scope_keys


def _index_current_day_closed_rows(rows: Sequence[Any]) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    indexed: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        source = dict(row or {})
        if source.get("fake_or_synthetic_row") is True:
            continue
        scope = _normalize_object_scope_row(source)
        if any(not scope.get(field) for field in OBJECT_SCOPE_GRAIN):
            continue
        indexed.setdefault(_object_scope_key(scope), []).append(source)
    for key in indexed:
        indexed[key].sort(key=_minute_sort_key)
    return indexed


def _index_previous_day_minute_rows(rows: Sequence[Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    indexed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        source = dict(row or {})
        if source.get("fake_or_synthetic_row") is True:
            continue
        asset_kind = str(source.get("asset_kind") or "")
        identity_key = str(source.get("identity_key") or "")
        if asset_kind not in ASSET_KINDS or not identity_key.startswith(f"{asset_kind}:"):
            continue
        indexed.setdefault((asset_kind, identity_key), []).append(source)
    for key in indexed:
        indexed[key].sort(key=_minute_sort_key)
    return indexed


def _current_rows_through_target(
    rows: Sequence[Mapping[str, Any]],
    *,
    labels: Sequence[str],
    target_label: str,
) -> list[Mapping[str, Any]]:
    if target_label not in labels:
        return []
    target_position = labels.index(target_label)
    output: list[Mapping[str, Any]] = []
    for row in rows:
        label = _hhmm_label(row.get("physical_c1_label") or row.get("minute_label") or row.get("raw_source_label") or "")
        if label not in labels:
            continue
        if labels.index(label) <= target_position:
            output.append(row)
    output.sort(key=_minute_sort_key)
    if not output:
        return []
    latest_label = _hhmm_label(output[-1].get("physical_c1_label") or output[-1].get("minute_label") or "")
    return output if latest_label == target_label else []


def resolve_fixed_period_windows(
    *,
    current_rows: Sequence[Mapping[str, Any]],
    previous_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve canonical fixed-period windows for N3 metric consumers."""

    unavailable = {
        "status": NOT_AVAILABLE_PERIOD_SOURCE,
        "position": 0,
        "latest_current_row": None,
        "previous_period_rows": {size: [] for size in (1, 5, 30, 120)},
        "previous_period_sources": {size: NOT_AVAILABLE_PERIOD_SOURCE for size in (1, 5, 30, 120)},
        "current_period_rows": {size: [] for size in (1, 5, 30, 120)},
        "previous_day_same_period_rows": {size: [] for size in (1, 5, 30, 120)},
        "boundary_policy_version": BOUNDARY_POLICY_VERSION,
    }
    try:
        current_index = fixed_period_calculation_row_index(current_rows)
        previous_index = _fixed_period_row_index(previous_rows)
        if not current_index:
            return unavailable
        current_ordinals = sorted(current_index)
        if current_ordinals != list(range(1, current_ordinals[-1] + 1)):
            return unavailable

        current = [current_index[ordinal] for ordinal in current_ordinals]
        previous = [previous_index[ordinal] for ordinal in sorted(previous_index)]
        latest_current = current[-1]
        position = current_ordinals[-1]
        previous_period_rows: dict[int, list[Mapping[str, Any]]] = {}
        previous_period_sources: dict[int, str] = {}
        current_period_rows: dict[int, list[Mapping[str, Any]]] = {}
        previous_day_same_period_rows: dict[int, list[Mapping[str, Any]]] = {}
        for size in (1, 5, 30, 120):
            period_rows, period_source = _resolve_previous_period_rows(
                current_rows=current,
                previous_rows=previous,
                labels=FIXED_PERIOD_CALCULATION_LABELS,
                position=position,
                size=size,
            )
            previous_period_rows[size] = period_rows
            previous_period_sources[size] = period_source
            current_period_rows[size] = _resolve_current_period_rows(
                current,
                labels=FIXED_PERIOD_CALCULATION_LABELS,
                position=position,
                size=size,
            )
            previous_day_same_period_rows[size] = _resolve_previous_day_same_period_rows(
                previous_rows,
                labels=FIXED_PERIOD_CALCULATION_LABELS,
                position=position,
                size=size,
            )
    except ValueError:
        return unavailable
    return {
        "status": "ready",
        "position": position,
        "latest_current_row": latest_current,
        "previous_period_rows": previous_period_rows,
        "previous_period_sources": previous_period_sources,
        "current_period_rows": current_period_rows,
        "previous_day_same_period_rows": previous_day_same_period_rows,
        "boundary_policy_version": BOUNDARY_POLICY_VERSION,
        "minute_axis_version": FIXED_PERIOD_MINUTE_AXIS_VERSION,
    }


def _derive_metric_values(
    *,
    current_rows: Sequence[Mapping[str, Any]],
    previous_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    windows = resolve_fixed_period_windows(current_rows=current_rows, previous_rows=previous_rows)
    if windows["status"] != "ready":
        return {}
    latest_current = windows["latest_current_row"]
    previous_period_rows = windows["previous_period_rows"]
    previous_period_sources = windows["previous_period_sources"]
    current_period_rows = windows["current_period_rows"]
    previous_day_same_period_rows = windows["previous_day_same_period_rows"]
    previous_1m_rows = previous_period_rows[1]
    previous_5m_rows = previous_period_rows[5]
    previous_30m_rows = previous_period_rows[30]
    previous_120m_rows = previous_period_rows[120]
    previous_1m_source = previous_period_sources[1]
    previous_5m_source = previous_period_sources[5]
    previous_30m_source = previous_period_sources[30]
    previous_120m_source = previous_period_sources[120]
    current_5m_rows = current_period_rows[5]
    current_30m_rows = current_period_rows[30]
    previous_day_same_5m_rows = previous_day_same_period_rows[5]
    previous_day_same_30m_rows = previous_day_same_period_rows[30]
    is_first_1m = previous_1m_source == PREVIOUS_TRADE_DATE_LAST_PERIOD
    is_first_5m = previous_5m_source == PREVIOUS_TRADE_DATE_LAST_PERIOD
    is_first_30m = previous_30m_source == PREVIOUS_TRADE_DATE_LAST_PERIOD
    is_first_120m = previous_120m_source == PREVIOUS_TRADE_DATE_LAST_PERIOD
    current_5m_virtual_amount = _same_window_virtual_amount(
        current_rows=current_5m_rows,
        previous_day_same_rows=previous_day_same_5m_rows,
    )
    current_30m_virtual_amount = _same_window_virtual_amount(
        current_rows=current_30m_rows,
        previous_day_same_rows=previous_day_same_30m_rows,
    )
    current_5m_elapsed_amount = _amount_sum_or_none(current_5m_rows)
    current_30m_elapsed_amount = _amount_sum_or_none(current_30m_rows)
    current_5m_amount = current_5m_elapsed_amount if len(current_5m_rows) >= 5 else current_5m_virtual_amount
    current_30m_amount = current_30m_elapsed_amount if len(current_30m_rows) >= 30 else current_30m_virtual_amount
    return {
        "current_price": _numeric(latest_current.get("close")),
        "previous_120m_body_high": _body_high(previous_120m_rows),
        "previous_120m_body_low": _body_low(previous_120m_rows),
        "previous_30m_body_high": _body_high(previous_30m_rows),
        "previous_30m_body_low": _body_low(previous_30m_rows),
        "previous_5m_body_high": _body_high(previous_5m_rows),
        "previous_5m_body_low": _body_low(previous_5m_rows),
        "previous_1m_body_high": _body_high(previous_1m_rows),
        "previous_1m_body_low": _body_low(previous_1m_rows),
        "current_1m_amount": _numeric(latest_current.get("amount")),
        "previous_1m_amount": None if is_first_1m else _amount_sum_or_none(previous_1m_rows),
        "current_5m_amount": current_5m_amount,
        "current_5m_elapsed_amount": current_5m_elapsed_amount,
        "previous_5m_amount": None if is_first_5m else _amount_sum_or_none(previous_5m_rows),
        "current_30m_closed_elapsed_amount": current_30m_elapsed_amount,
        "current_30m_virtual_amount": current_30m_amount,
        "previous_day_same_window_amount": _amount_sum_or_none(previous_day_same_30m_rows),
        "is_first_1m_of_day": is_first_1m,
        "is_first_5m_of_day": is_first_5m,
        "is_first_30m_of_day": is_first_30m,
        "is_first_120m_of_day": is_first_120m,
        "first_1m_amount_default_pass": is_first_1m,
        "first_5m_amount_default_pass": is_first_5m,
        "previous_1m_period_source": previous_1m_source,
        "previous_5m_period_source": previous_5m_source,
        "previous_30m_period_source": previous_30m_source,
        "previous_120m_period_source": previous_120m_source,
        "boundary_policy_version": BOUNDARY_POLICY_VERSION,
        "virtual_amount_policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
    }


def _resolve_previous_period_rows(
    *,
    current_rows: Sequence[Mapping[str, Any]],
    previous_rows: Sequence[Mapping[str, Any]],
    labels: Sequence[str],
    position: int,
    size: int,
) -> tuple[list[Mapping[str, Any]], str]:
    if position <= 0:
        return [], NOT_AVAILABLE_PERIOD_SOURCE
    current_start = ((position - 1) // size) * size
    if current_start == 0:
        previous_index = _fixed_period_row_index(previous_rows)
        if not previous_index:
            return [], NOT_AVAILABLE_PERIOD_SOURCE
        previous_end = max(previous_index) // size * size
        if previous_end < size:
            return [], NOT_AVAILABLE_PERIOD_SOURCE
        expected_ordinals = list(range(previous_end - size + 1, previous_end + 1))
        rows = [previous_index[ordinal] for ordinal in expected_ordinals if ordinal in previous_index]
        if len(rows) == size:
            return rows, PREVIOUS_TRADE_DATE_LAST_PERIOD
        return [], NOT_AVAILABLE_PERIOD_SOURCE
    expected_ordinals = list(range(current_start - size + 1, current_start + 1))
    current_index = fixed_period_calculation_row_index(current_rows)
    rows = [current_index[ordinal] for ordinal in expected_ordinals if ordinal in current_index]
    if len(rows) == size:
        return rows, SAME_TRADE_DATE_PREVIOUS_PERIOD
    return [], NOT_AVAILABLE_PERIOD_SOURCE


def _resolve_current_period_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    labels: Sequence[str],
    position: int,
    size: int,
) -> list[Mapping[str, Any]]:
    if position <= 0:
        return []
    current_start = ((position - 1) // size) * size
    expected_ordinals = list(range(current_start + 1, position + 1))
    row_index = fixed_period_calculation_row_index(rows)
    output = [row_index[ordinal] for ordinal in expected_ordinals if ordinal in row_index]
    return output if len(output) == len(expected_ordinals) else []


def _resolve_previous_day_same_period_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    labels: Sequence[str],
    position: int,
    size: int,
) -> list[Mapping[str, Any]]:
    if position <= 0:
        return []
    expected_labels = _fixed_period_same_window_labels(
        position=position,
        size=size,
        labels=labels,
    )
    return _rows_for_labels(rows, expected_labels)


def _fixed_period_same_window_labels(
    *,
    position: int,
    size: int,
    labels: Sequence[str] = FIXED_PERIOD_CALCULATION_LABELS,
) -> list[str]:
    if position <= 0 or size <= 0:
        return []
    current_start = ((position - 1) // size) * size
    return list(labels[current_start : min(current_start + size, len(labels))])


def _fixed_period_row_index(rows: Sequence[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    afternoon_layout = _fixed_period_afternoon_layout(rows)
    indexed: dict[int, Mapping[str, Any]] = {}
    for row in sorted(rows, key=_metric_period_sort_key):
        ordinal = _metric_period_ordinal(row, afternoon_layout)
        if ordinal <= 0:
            continue
        existing = indexed.get(ordinal)
        if existing is not None:
            if _is_contract_equivalent_close_boundary_duplicate(existing, row):
                indexed[ordinal] = _preferred_close_boundary_row(existing, row)
                continue
            existing_ref = str(existing.get("source_row_ref") or "")
            duplicate_ref = str(row.get("source_row_ref") or "")
            raise ValueError(
                "duplicate normalized fixed-period ordinal "
                f"{ordinal}: existing={existing_ref!r}, duplicate={duplicate_ref!r}"
            )
        indexed[ordinal] = row
    return indexed


def fixed_period_calculation_row_index(
    rows: Sequence[Mapping[str, Any]],
) -> dict[int, Mapping[str, Any]]:
    """Index current-day rows on the unique physical fixed-period axis."""

    _fixed_period_afternoon_layout(rows)
    rows_by_label = _rows_by_unique_physical_label(rows)
    indexed: dict[int, Mapping[str, Any]] = {}
    for label, row in rows_by_label.items():
        ordinal = FIXED_PERIOD_CALCULATION_ORDINALS.get(label, 0)
        if ordinal > 0:
            indexed[ordinal] = row
    return indexed


def _metric_period_ordinal(row: Mapping[str, Any], afternoon_layout: str) -> int:
    raw_label = _hhmm_label(row.get("raw_source_label") or "")
    physical_label = _hhmm_label(
        row.get("physical_c1_label") or row.get("minute_label") or row.get("bar_time") or ""
    )
    label = physical_label or raw_label
    if not label or physical_label == "09:30":
        return 0
    if afternoon_layout == FIXED_PERIOD_LAYOUT_POST_CLOSE and raw_label == "11:30":
        return 120
    ordinal = FIXED_PERIOD_CALCULATION_ORDINALS.get(physical_label or raw_label, 0)
    if ordinal >= 120:
        if afternoon_layout in {
            FIXED_PERIOD_LAYOUT_POST_CLOSE,
            FIXED_PERIOD_LAYOUT_PRELOAD_CLOSE_LABEL,
        }:
            ordinal += 1
        return ordinal
    return ordinal


def _fixed_period_afternoon_layout(rows: Sequence[Mapping[str, Any]]) -> str:
    has_raw_1130 = _has_post_close_raw_1130(rows)
    observed_styles: set[str] = set()
    for row in rows:
        raw_label = _hhmm_label(row.get("raw_source_label") or "")
        physical_label = _hhmm_label(
            row.get("physical_c1_label") or row.get("minute_label") or row.get("bar_time") or ""
        )
        physical_minutes = _hhmm_minutes(physical_label)
        if not (13 * 60 <= physical_minutes <= 14 * 60 + 59):
            continue
        if physical_label == "13:00" and raw_label == "11:30":
            continue
        if physical_label == "14:59" and raw_label == "15:00":
            continue
        if not raw_label:
            observed_styles.add(FIXED_PERIOD_LAYOUT_INTRADAY)
            continue
        if raw_label == physical_label:
            observed_styles.add(FIXED_PERIOD_LAYOUT_INTRADAY)
            continue
        if raw_label == _next_hhmm_label(physical_label):
            observed_styles.add(FIXED_PERIOD_LAYOUT_PRELOAD_CLOSE_LABEL)
            continue
        raise ValueError(
            "ambiguous fixed-period afternoon label layout: "
            f"physical={physical_label!r}, raw={raw_label!r}"
        )

    if has_raw_1130:
        if FIXED_PERIOD_LAYOUT_PRELOAD_CLOSE_LABEL in observed_styles:
            raise ValueError("ambiguous fixed-period post-close and preload label layout")
        return FIXED_PERIOD_LAYOUT_POST_CLOSE
    if observed_styles == {FIXED_PERIOD_LAYOUT_PRELOAD_CLOSE_LABEL}:
        return FIXED_PERIOD_LAYOUT_PRELOAD_CLOSE_LABEL
    if observed_styles in (set(), {FIXED_PERIOD_LAYOUT_INTRADAY}):
        return FIXED_PERIOD_LAYOUT_INTRADAY
    raise ValueError("ambiguous fixed-period intraday and preload label layout")


def _next_hhmm_label(label: str) -> str:
    minutes = _hhmm_minutes(label)
    if minutes < 0 or minutes >= 24 * 60 - 1:
        return ""
    minutes += 1
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _metric_period_sort_key(row: Mapping[str, Any]) -> tuple[int, str, str]:
    raw_label = _hhmm_label(row.get("raw_source_label") or "")
    physical_label = _hhmm_label(
        row.get("physical_c1_label") or row.get("minute_label") or row.get("bar_time") or ""
    )
    return (_hhmm_minutes(physical_label or raw_label), raw_label, str(row.get("source_row_ref") or ""))


def _is_contract_equivalent_close_boundary_duplicate(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> bool:
    physical_labels = {
        _hhmm_label(row.get("physical_c1_label") or row.get("minute_label") or "")
        for row in (first, second)
    }
    raw_labels = {
        _hhmm_label(row.get("raw_source_label") or "")
        for row in (first, second)
    }
    if physical_labels != {"14:59"} or raw_labels != {"14:59", "15:00"}:
        return False
    for field in ("asset_kind", "identity_key"):
        values = {str(row.get(field) or "") for row in (first, second)}
        if len(values - {""}) > 1:
            return False
    return True


def _preferred_close_boundary_row(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> Mapping[str, Any]:
    return second if _hhmm_label(second.get("raw_source_label") or "") == "15:00" else first


def _has_post_close_raw_1130(rows: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        _hhmm_label(
            row.get("physical_c1_label")
            or row.get("minute_label")
            or row.get("bar_time")
            or ""
        )
        == "13:00"
        and _hhmm_label(row.get("raw_source_label") or "") == "11:30"
        for row in rows
    )


def _hhmm_minutes(label: str) -> int:
    if not re.fullmatch(r"\d{2}:\d{2}", label or ""):
        return -1
    hour, minute = (int(part) for part in label.split(":", 1))
    return hour * 60 + minute


def _rows_for_labels(rows: Sequence[Mapping[str, Any]], labels: Sequence[str]) -> list[Mapping[str, Any]]:
    by_label = _rows_by_unique_physical_label(rows, accepted_labels=set(labels))
    output = [by_label[label] for label in labels if label in by_label]
    return output if len(output) == len(labels) else []


def _rows_by_unique_physical_label(
    rows: Sequence[Mapping[str, Any]],
    *,
    accepted_labels: set[str] | None = None,
) -> dict[str, Mapping[str, Any]]:
    by_label: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        label = _hhmm_label(
            row.get("physical_c1_label")
            or row.get("minute_label")
            or row.get("bar_time")
            or row.get("raw_source_label")
            or ""
        )
        if not label or (accepted_labels is not None and label not in accepted_labels):
            continue
        existing = by_label.get(label)
        if existing is None:
            by_label[label] = row
            continue
        raw_labels = {
            _hhmm_label(candidate.get("raw_source_label") or "")
            for candidate in (existing, row)
        }
        if label == "13:00" and raw_labels == {"11:30", "13:00"}:
            by_label[label] = (
                row
                if _hhmm_label(row.get("raw_source_label") or "") == "13:00"
                else existing
            )
            continue
        if _is_contract_equivalent_close_boundary_duplicate(existing, row):
            by_label[label] = _preferred_close_boundary_row(existing, row)
            continue
        raise ValueError(f"duplicate fixed-period physical label: {label}")
    return by_label


def _has_open_boundary_source_gap(rows: Sequence[Mapping[str, Any]]) -> bool:
    labels = {
        _hhmm_label(row.get("physical_c1_label") or row.get("minute_label") or row.get("raw_source_label") or "")
        for row in rows
    }
    return "09:30" not in labels and "09:31" in labels


def _amount_sum_or_none(rows: Sequence[Mapping[str, Any]]) -> float | None:
    if not rows:
        return None
    return _amount_sum(rows)


def _same_window_virtual_amount(
    *,
    current_rows: Sequence[Mapping[str, Any]],
    previous_day_same_rows: Sequence[Mapping[str, Any]],
) -> float | None:
    if not current_rows or not previous_day_same_rows:
        return None
    previous_day_elapsed_rows = list(previous_day_same_rows)[: len(current_rows)]
    current_amount = _amount_sum_or_none(current_rows)
    previous_day_elapsed_amount = _amount_sum_or_none(previous_day_elapsed_rows)
    previous_day_full_amount = _amount_sum_or_none(previous_day_same_rows)
    if (
        current_amount is None
        or previous_day_elapsed_amount is None
        or previous_day_full_amount is None
        or previous_day_elapsed_amount <= 0
        or previous_day_full_amount <= 0
    ):
        return None
    return current_amount / previous_day_elapsed_amount * previous_day_full_amount


def _compact_minute_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "for_trade_date",
            "asset_kind",
            "identity_key",
            "physical_c1_label",
            "raw_source_label",
            "open",
            "high",
            "low",
            "close",
            "amount",
            "source_row_ref",
            "fake_or_synthetic_row",
        )
        if key in row
    }


def _compact_current_day_staging_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = {
        **_normalize_object_scope_row(row),
        "physical_c1_label": row.get("physical_c1_label"),
        "raw_source_label": row.get("raw_source_label"),
        "source_label_policy": SOURCE_CLOSE_LABEL_POLICY,
        "source_label_semantics": SOURCE_LABEL_SEMANTICS,
        "physical_label_semantics": PHYSICAL_LABEL_SEMANTICS,
        "fake_or_synthetic_row": False,
    }
    for key in ("open", "high", "low", "close", "volume", "amount", "source_row_ref"):
        if key in row:
            output[key] = row.get(key)
    return output


def _minute_row_ref(row: Mapping[str, Any]) -> str:
    for key in ("source_row_ref", "minute_bar_id", "bar_id", "raw_source_row_id"):
        if row.get(key) is not None:
            return str(row.get(key))
    return "|".join(
        str(row.get(key) or "")
        for key in ("asset_kind", "identity_key", "physical_c1_label", "raw_source_label")
    )


def _minute_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (
        _hhmm_label(row.get("physical_c1_label") or row.get("minute_label") or row.get("raw_source_label") or ""),
        _minute_row_ref(row),
    )


def _amount_sum(rows: Sequence[Mapping[str, Any]]) -> float:
    return sum(_numeric(row.get("amount")) for row in rows)


def _body_high(rows: Sequence[Mapping[str, Any]]) -> float | None:
    if not rows:
        return None
    open_value = _optional_numeric(rows[0].get("open"))
    close_value = _optional_numeric(rows[-1].get("close"))
    if open_value is None or close_value is None:
        return None
    return max(open_value, close_value)


def _body_low(rows: Sequence[Mapping[str, Any]]) -> float | None:
    if not rows:
        return None
    open_value = _optional_numeric(rows[0].get("open"))
    close_value = _optional_numeric(rows[-1].get("close"))
    if open_value is None or close_value is None:
        return None
    return min(open_value, close_value)


def _body_high_for_row(row: Mapping[str, Any]) -> float | None:
    open_value = _optional_numeric(row.get("open"))
    close_value = _optional_numeric(row.get("close"))
    if open_value is None or close_value is None:
        return None
    return max(open_value, close_value)


def _body_low_for_row(row: Mapping[str, Any]) -> float | None:
    open_value = _optional_numeric(row.get("open"))
    close_value = _optional_numeric(row.get("close"))
    if open_value is None or close_value is None:
        return None
    return min(open_value, close_value)


def _numeric(value: Any) -> float:
    return float(value or 0)


def _optional_numeric(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _scope_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(field) or "") for field in REQUIRED_SCOPE_GRAIN)


def _object_scope_key(row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(row.get(field) or "") for field in OBJECT_SCOPE_GRAIN)


def _false_side_effects() -> dict[str, bool]:
    return {flag: False for flag in SIDE_EFFECT_FLAGS}


def _valid_trade_date(value: str) -> bool:
    return re.fullmatch(r"\d{8}", str(value or "")) is not None


def _minute_close_time(*, for_trade_date: str, minute_label: str) -> datetime:
    if not _valid_trade_date(for_trade_date):
        raise ValueError("for_trade_date must be YYYYMMDD")
    return ashare_c1_minute_close_time(for_trade_date, minute_label)


def _coerce_shanghai(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ASIA_SHANGHAI)
    return dt.astimezone(ASIA_SHANGHAI)


def _hhmm_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(ASIA_SHANGHAI).strftime("%H:%M") if value.tzinfo else value.strftime("%H:%M")
    text = str(value or "").strip()
    if re.fullmatch(r"\d{2}:\d{2}", text):
        return text
    match = re.search(r"(\d{2}:\d{2})(?::\d{2})?", text)
    if match:
        return match.group(1)
    return text


def _hhmm_digits(value: Any) -> str:
    label = _hhmm_label(value)
    return label.replace(":", "") if label else ""


def _hhmm_label(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}", text):
        return f"{text[:2]}:{text[2:]}"
    if re.fullmatch(r"\d{2}:\d{2}", text):
        return text
    return _hhmm_text(text)


def _source_time_key(row: Mapping[str, Any]) -> str:
    for key in ("bar_time", "datetime", "minute_label", "date_time", "time"):
        if key in row and row.get(key) is not None:
            return key
    raise MinuteLabelNormalizationError("missing minute time field")


def _with_hhmm(dt: datetime, label: str) -> datetime:
    hour, minute = (int(part) for part in label.split(":", 1))
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _format_like(original: Any, dt: datetime) -> Any:
    if isinstance(original, datetime):
        return dt
    text = str(original)
    if "T" in text:
        return dt.isoformat() if "+" in text or text.endswith("Z") else dt.strftime("%Y-%m-%dT%H:%M:%S")
    if len(text) == 16:
        return dt.strftime("%Y-%m-%d %H:%M")
    return dt.isoformat() if "+" in text else dt.strftime("%Y-%m-%d %H:%M:%S")
