"""Strict N4 trigger rule v4 execute enforcement.

The checks in this module run before any v4 execute path is allowed to write
trigger facts or outbox rows. They intentionally fail closed: if a field is
missing or a time/lineage boundary cannot be proven, the caller must BLOCK
before opening a write transaction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


class V4EnforcementBlocked(RuntimeError):
    """Raised when N4 trigger rule v4 enforcement blocks execution."""


RUNTIME_SIGNAL_TYPES = {"B_BUY", "S_SELL"}
CONDITION_SIGNAL_TYPES = {"BUY", "SELL", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT"}
FULL_CONDITION_KEYS = {"BUY:FULL", "SELL:FULL"}
HINT_CONDITION_KEYS = {"BUY_HINT", "SELL_HINT"}
TRIGGER_KINDS = {"trigger", "hint"}
MATCH_BASIS_VALUES = {
    "realtime_snapshot",
    "intraday_projection",
    "v4_context_projection_enrichment",
    "action_confirmation_metric",
}
FORMAL_TRIGGER_PERIODS = {"Y", "Q", "M", "W", "D"}

REQUIRED_TRIGGER_MATCHED_FIELDS = (
    "runtime_signal_type",
    "condition_signal_type",
    "condition_key",
    "original_condition_key",
    "trigger_price",
    "event_time",
    "trigger_kind",
    "requested_periods",
    "triggered_periods",
    "all_trigger_periods",
    "primary_trigger_period",
    "triggered_period_details",
    "n5_entry_allowed",
    "trigger_live",
    "current_status",
    "data_quality_status",
    "match_basis",
    "price_source",
    "baseline_source",
    "projection_30m_required",
    "projection_30m_flag",
    "projection_30m_type",
    "projection_period",
    "projection_30m_volume_up_flag",
    "projection_30m_shrink_down_flag",
)


def assert_v4_write_plan_enforceable(
    write_plan: Mapping[str, Any],
    *,
    created_at: datetime | None = None,
) -> None:
    """Validate every persisted TriggerMatched plan in a write plan."""

    violations: list[str] = []
    for idx, plan in enumerate(write_plan.get("matched_write_plans") or []):
        for violation in collect_v4_trigger_matched_plan_violations(plan, created_at=created_at):
            violations.append(f"plan[{idx}]:{violation}")
    if violations:
        raise V4EnforcementBlocked("N4 v4 enforcement blocked before writes: " + "; ".join(violations[:20]))


def assert_v4_trigger_matched_plan(
    plan: Mapping[str, Any],
    *,
    created_at: datetime | None = None,
) -> None:
    violations = collect_v4_trigger_matched_plan_violations(plan, created_at=created_at)
    if violations:
        raise V4EnforcementBlocked("N4 v4 TriggerMatched plan blocked: " + "; ".join(violations))


def collect_v4_trigger_matched_plan_violations(
    plan: Mapping[str, Any],
    *,
    created_at: datetime | None = None,
) -> list[str]:
    """Return P0 violations for one planned TriggerMatched row."""

    violations: list[str] = []
    if plan.get("output_event_type") != "TriggerMatched":
        return violations

    condition_key = str(plan.get("condition_key") or "")
    original_condition_key = str(plan.get("original_condition_key") or "")
    hint_matched = plan.get("trigger_kind") == "hint" and condition_key in HINT_CONDITION_KEYS
    full_matched = condition_key in FULL_CONDITION_KEYS or original_condition_key in FULL_CONDITION_KEYS
    if "action_mark" in plan:
        violations.append("action_mark_forbidden_in_n4_payload")
    for field in REQUIRED_TRIGGER_MATCHED_FIELDS:
        if field not in plan:
            violations.append(f"missing_{field}")
        elif field == "projection_period":
            continue
        elif field in {"requested_periods", "triggered_periods", "all_trigger_periods", "triggered_period_details"} and hint_matched:
            continue
        elif field in {"triggered_periods", "all_trigger_periods"} and hint_matched:
            continue
        elif field == "primary_trigger_period" and hint_matched:
            continue
        elif field not in {"primary_trigger_period"} and _is_blank(plan.get(field)):
            violations.append(f"blank_{field}")
        elif field == "primary_trigger_period" and not hint_matched and _is_blank(plan.get(field)):
            violations.append(f"blank_{field}")

    if plan.get("signal_type") not in RUNTIME_SIGNAL_TYPES:
        violations.append("invalid_runtime_signal_type")
    if plan.get("runtime_signal_type") not in RUNTIME_SIGNAL_TYPES:
        violations.append("invalid_runtime_signal_type")
    elif plan.get("runtime_signal_type") != plan.get("signal_type"):
        violations.append("runtime_signal_type_mismatch")
    violations.extend(_condition_signal_type_violations(plan))
    if plan.get("trigger_kind") not in TRIGGER_KINDS:
        violations.append("invalid_trigger_kind")
    if plan.get("match_basis") not in MATCH_BASIS_VALUES:
        violations.append("invalid_match_basis")
    if not _valid_n5_entry_contract(plan):
        violations.append("invalid_n5_entry_contract")
    if not _has_reviewed_price_source(plan):
        violations.append("trigger_price_source_missing")
    violations.extend(_unified_period_payload_violations(plan, hint_matched=hint_matched))
    violations.extend(_projection_30m_flag_violations(plan, hint_matched=hint_matched))
    violations.extend(_formal_period_violations(plan, hint_matched=hint_matched))
    violations.extend(_hint_projection_violations(plan, hint_matched=hint_matched))
    violations.extend(_full_condition_violations(plan, full_matched=full_matched))

    event_time = _event_time(plan)
    created = _coerce_datetime(created_at) if created_at is not None else None
    if event_time is not None and created is not None and event_time > created:
        violations.append("event_time_after_created_at")

    trigger_time = _trigger_time(plan)
    source_confirmed_time = _source_confirmed_time(plan)
    if trigger_time is not None and source_confirmed_time is not None and trigger_time > source_confirmed_time:
        violations.append("trigger_time_after_source_confirmed_time")

    projection_closed_label = _projection_closed_label(plan)
    if (
        str(plan.get("match_basis") or "") == "intraday_projection"
        and trigger_time is not None
        and projection_closed_label is not None
        and trigger_time > projection_closed_label
    ):
        violations.append("projection_trigger_time_after_closed_label")

    return violations


def _condition_signal_type_violations(plan: Mapping[str, Any]) -> list[str]:
    violations: list[str] = []
    condition_signal_type = str(plan.get("condition_signal_type") or "")
    condition_key = str(plan.get("condition_key") or "")
    if condition_signal_type not in CONDITION_SIGNAL_TYPES:
        violations.append("invalid_condition_signal_type")
        return violations
    expected = _expected_condition_signal_type(condition_key)
    if expected and condition_signal_type != expected:
        violations.append("condition_signal_type_family_mismatch")
    if condition_signal_type == "BUY" and plan.get("signal_type") != "B_BUY":
        violations.append("condition_signal_type_signal_mismatch")
    if condition_signal_type == "SELL" and plan.get("signal_type") != "S_SELL":
        violations.append("condition_signal_type_signal_mismatch")
    if condition_signal_type in {"BUY:FULL", "BUY_HINT"} and plan.get("signal_type") != "B_BUY":
        violations.append("condition_signal_type_signal_mismatch")
    if condition_signal_type in {"SELL:FULL", "SELL_HINT"} and plan.get("signal_type") != "S_SELL":
        violations.append("condition_signal_type_signal_mismatch")
    return violations


def _expected_condition_signal_type(condition_key: str) -> str | None:
    if condition_key in FULL_CONDITION_KEYS or condition_key in HINT_CONDITION_KEYS:
        return condition_key
    if condition_key.startswith("BUY"):
        return "BUY"
    if condition_key.startswith("SELL"):
        return "SELL"
    return None


def _unified_period_payload_violations(plan: Mapping[str, Any], *, hint_matched: bool) -> list[str]:
    violations: list[str] = []
    requested_periods = _period_values(plan.get("requested_periods"))
    triggered_details = plan.get("triggered_period_details")
    details_empty = _is_blank(triggered_details)

    if hint_matched:
        if requested_periods:
            violations.append("hint_requested_periods_must_be_empty")
        if not details_empty:
            violations.append("hint_triggered_period_details_must_be_empty")
        return violations

    if not requested_periods:
        violations.append("blank_requested_periods")
    elif "30m" in requested_periods:
        violations.append("invalid_requested_periods_30m")
    elif any(period not in FORMAL_TRIGGER_PERIODS for period in requested_periods):
        violations.append("invalid_requested_periods")

    if details_empty:
        violations.append("blank_triggered_period_details")
    else:
        detail_periods = []
        if isinstance(triggered_details, Sequence) and not isinstance(triggered_details, (str, bytes, bytearray)):
            for detail in triggered_details:
                if isinstance(detail, Mapping):
                    period = str(detail.get("period") or "").strip()
                    if period:
                        detail_periods.append(period)
        if "30m" in detail_periods:
            violations.append("invalid_triggered_period_details_30m")
        if any(period and period not in FORMAL_TRIGGER_PERIODS for period in detail_periods):
            violations.append("invalid_triggered_period_details")
    return violations


def _projection_30m_flag_violations(plan: Mapping[str, Any], *, hint_matched: bool) -> list[str]:
    violations: list[str] = []
    projection_type = str(plan.get("projection_30m_type") or "none")
    volume_flag = plan.get("projection_30m_volume_up_flag") is True
    shrink_flag = plan.get("projection_30m_shrink_down_flag") is True
    if volume_flag and shrink_flag:
        violations.append("projection_30m_flags_both_true")
    if projection_type == "volume_up" and not (volume_flag and not shrink_flag):
        violations.append("projection_30m_flags_inconsistent_with_type")
    elif projection_type == "shrink_down" and not (shrink_flag and not volume_flag):
        violations.append("projection_30m_flags_inconsistent_with_type")
    elif projection_type == "none" and (volume_flag or shrink_flag):
        violations.append("projection_30m_flags_inconsistent_with_type")
    elif projection_type not in {"none", "volume_up", "shrink_down"}:
        violations.append("invalid_projection_30m_type")
    if hint_matched and plan.get("projection_30m_required") is not True:
        violations.append("hint_projection_30m_required_must_be_true")
    if not hint_matched and plan.get("projection_30m_required") is True:
        violations.append("formal_projection_30m_required_must_be_false")
    return violations


def _formal_period_violations(plan: Mapping[str, Any], *, hint_matched: bool) -> list[str]:
    violations: list[str] = []
    trigger_period = _period_text(plan.get("trigger_period"))
    primary_period = _period_text(plan.get("primary_trigger_period"))

    if hint_matched:
        if trigger_period != "30m":
            violations.append("hint_trigger_period_must_be_30m")
    elif trigger_period == "30m":
        violations.append("invalid_trigger_period_30m")
    elif trigger_period and trigger_period not in FORMAL_TRIGGER_PERIODS:
        violations.append("invalid_trigger_period")
    elif not trigger_period and not hint_matched:
        violations.append("blank_trigger_period")

    if primary_period == "30m":
        violations.append("invalid_primary_trigger_period_30m")
    elif primary_period and primary_period not in FORMAL_TRIGGER_PERIODS:
        violations.append("invalid_primary_trigger_period")
    elif not primary_period and not hint_matched:
        violations.append("blank_primary_trigger_period")

    for field in ("triggered_periods", "all_trigger_periods"):
        periods = _period_values(plan.get(field))
        if "30m" in periods:
            violations.append(f"invalid_{field}_30m")
        unknown = [period for period in periods if period not in FORMAL_TRIGGER_PERIODS]
        if unknown:
            violations.append(f"invalid_{field}")
        if not periods and not hint_matched:
            violations.append(f"blank_{field}")
    return violations


def _hint_projection_violations(plan: Mapping[str, Any], *, hint_matched: bool) -> list[str]:
    if not hint_matched:
        return []

    violations: list[str] = []
    condition_key = str(plan.get("condition_key") or "")
    projection_period = str(plan.get("projection_period") or "")
    projection_30m_type = str(plan.get("projection_30m_type") or "")
    trigger_mark_candidate = str(plan.get("trigger_mark_candidate") or "")
    if projection_period != "30m":
        violations.append("hint_projection_period_must_be_30m")
    if plan.get("projection_30m_flag") is not True:
        violations.append("hint_projection_30m_flag_must_be_true")
    if condition_key == "BUY_HINT":
        if projection_30m_type != "volume_up":
            violations.append("buy_hint_projection_30m_type_must_be_volume_up")
        if trigger_mark_candidate != "30m_volume":
            violations.append("buy_hint_trigger_mark_candidate_must_be_30m_volume")
    elif condition_key == "SELL_HINT":
        if projection_30m_type != "shrink_down":
            violations.append("sell_hint_projection_30m_type_must_be_shrink_down")
        if trigger_mark_candidate != "30m_shrink":
            violations.append("sell_hint_trigger_mark_candidate_must_be_30m_shrink")
    return violations


def _full_condition_violations(plan: Mapping[str, Any], *, full_matched: bool) -> list[str]:
    if not full_matched:
        return []

    violations: list[str] = []
    condition_key = str(plan.get("condition_key") or "")
    original_condition_key = str(plan.get("original_condition_key") or "")
    trigger_period = _period_text(plan.get("trigger_period"))
    primary_period = _period_text(plan.get("primary_trigger_period"))
    triggered_periods = _period_values(plan.get("triggered_periods"))
    all_trigger_periods = _period_values(plan.get("all_trigger_periods"))

    if condition_key not in FULL_CONDITION_KEYS or original_condition_key != condition_key:
        violations.append("full_condition_key_mismatch")
    if condition_key == "BUY:FULL" and plan.get("signal_type") != "B_BUY":
        violations.append("full_signal_type_mismatch")
    if condition_key == "SELL:FULL" and plan.get("signal_type") != "S_SELL":
        violations.append("full_signal_type_mismatch")
    if plan.get("trigger_kind") != "trigger":
        violations.append("full_trigger_kind_must_be_trigger")
    if trigger_period != "D":
        violations.append("full_trigger_period_must_be_D")
    if triggered_periods != ["D"]:
        violations.append("full_triggered_periods_must_be_D")
    if all_trigger_periods != ["D"]:
        violations.append("full_all_trigger_periods_must_be_D")
    if primary_period != "D":
        violations.append("full_primary_trigger_period_must_be_D")
    if str(plan.get("trigger_mark_candidate") or "") != "normal":
        violations.append("full_trigger_mark_candidate_must_be_normal")
    if plan.get("projection_30m_flag") is True:
        violations.append("full_projection_30m_flag_must_be_false")
    projection_30m_type = str(plan.get("projection_30m_type") or "none")
    if projection_30m_type != "none":
        violations.append("full_projection_30m_type_must_be_none")
    return violations


def _valid_n5_entry_contract(plan: Mapping[str, Any]) -> bool:
    return (
        plan.get("output_event_type") == "TriggerMatched"
        and plan.get("signal_type") in RUNTIME_SIGNAL_TYPES
        and plan.get("current_status") == "matched"
        and plan.get("trigger_live") is True
        and plan.get("n5_entry_allowed") is True
    )


def _has_reviewed_price_source(plan: Mapping[str, Any]) -> bool:
    trigger_price = _decimal_or_none(plan.get("trigger_price"))
    if trigger_price is None:
        return False

    match_basis = str(plan.get("match_basis") or "")
    if match_basis == "realtime_snapshot":
        trace = _mapping(plan.get("snapshot_trace"))
        source_price = _decimal_or_none(trace.get("current_price") or trace.get("close"))
        return (
            source_price is not None
            and source_price == trigger_price
            and not _is_blank(trace.get("snapshot_id"))
            and str(trace.get("quality_status") or "passed") == "passed"
        )

    if match_basis == "intraday_projection":
        trace = _mapping(plan.get("projection_trace"))
        source_price = _decimal_or_none(
            trace.get("trigger_price")
            or trace.get("current_price")
            or trace.get("projection_price")
            or plan.get("projection_price")
        )
        return (
            source_price is not None
            and source_price == trigger_price
            and not _is_blank(trace.get("projection_id") or plan.get("source_projection_id"))
            and str(trace.get("quality_status") or plan.get("data_quality_status") or "passed") == "passed"
        )

    trace = _mapping(plan.get("n3_trace")) or _mapping(plan.get("action_confirmation_metric_trace"))
    source_price = _decimal_or_none(trace.get("trigger_price") or trace.get("current_price"))
    return source_price is not None and source_price == trigger_price


def _event_time(plan: Mapping[str, Any]) -> datetime | None:
    return (
        _coerce_datetime(plan.get("event_time"))
        or _trigger_time(plan)
        or _coerce_datetime(_mapping(plan.get("snapshot_trace")).get("snapshot_time"))
        or _coerce_datetime(_mapping(plan.get("projection_trace")).get("trigger_time"))
    )


def _trigger_time(plan: Mapping[str, Any]) -> datetime | None:
    return (
        _coerce_datetime(plan.get("trigger_time"))
        or _coerce_datetime(_mapping(plan.get("snapshot_trace")).get("snapshot_time"))
        or _coerce_datetime(_mapping(plan.get("projection_trace")).get("trigger_time"))
    )


def _source_confirmed_time(plan: Mapping[str, Any]) -> datetime | None:
    snapshot_trace = _mapping(plan.get("snapshot_trace"))
    projection_trace = _mapping(plan.get("projection_trace"))
    return (
        _coerce_datetime(plan.get("source_confirmed_time"))
        or _coerce_datetime(snapshot_trace.get("source_confirmed_time"))
        or _coerce_datetime(projection_trace.get("source_confirmed_time"))
        or _coerce_datetime(snapshot_trace.get("snapshot_time"))
        or _coerce_datetime(projection_trace.get("trigger_time"))
    )


def _projection_closed_label(plan: Mapping[str, Any]) -> datetime | None:
    projection_trace = _mapping(plan.get("projection_trace"))
    return _coerce_datetime(
        projection_trace.get("approved_projection_closed_label_used")
        or projection_trace.get("closed_label_used")
        or plan.get("approved_projection_closed_label_used")
    )


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = str(value).replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _period_text(value: Any) -> str:
    return str(value or "").strip()


def _period_values(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                import json

                parsed = json.loads(text)
            except (TypeError, ValueError):
                return [text]
            return _period_values(parsed)
        return [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and len(value) == 0:
        return True
    return False


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
