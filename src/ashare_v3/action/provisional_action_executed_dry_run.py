"""N5 provisional ActionExecuted dry-run.

This module is intentionally read-only. It evaluates whether existing
provisional ActionEligible rows can become ActionExecuted after a closed N3P
action-confirmation metric exists, but it never builds database write rows.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from ashare_v3.action.dry_run import (
    derive_action_mark_decision_from_n5_metric,
    evaluate_action_confirmation_metric,
)
from ashare_v3.action.provisional_action_eligible import build_canonical_action_identity_key
from ashare_v3.events.ids import join_dedup_parts


ACTION_EXECUTED_PLAN = "ACTION_EXECUTED_PLAN"
PENDING_NO_CLOSED_METRIC = "PENDING_NO_CLOSED_METRIC"
NOT_EXECUTED_RULE_FAILED = "NOT_EXECUTED_RULE_FAILED"
SKIPPED_INVALID_PAYLOAD = "SKIPPED_INVALID_PAYLOAD"
SKIPPED_DUPLICATE_ACTION_EXECUTED = "SKIPPED_DUPLICATE_ACTION_EXECUTED"
BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF = "BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF"

PROVISIONAL_EXECUTED_MODE = "intraday_closed_minute"
SOURCE_METRIC_KIND = "realtime_action_confirmation_metric"
N5_ACTION_CONFIRMATION_METRIC_V2_KIND = "n5_action_confirmation_metric_v2"
SUPPORTED_ORDINARY_TRIGGER_TYPES = frozenset({"BUY", "SELL", "BUY:FULL", "SELL:FULL"})
SUPPORTED_HINT_CONDITIONS = frozenset({"BUY_HINT", "SELL_HINT"})
SUPPORTED_TRIGGER_TYPES = SUPPORTED_ORDINARY_TRIGGER_TYPES | SUPPORTED_HINT_CONDITIONS
SUPPORTED_SIGNAL_TYPES = frozenset({"B_BUY", "S_SELL"})

SIDE_EFFECT_GUARD = {
    "db_written": False,
    "action_run_written": False,
    "action_event_written": False,
    "action_fact_written": False,
    "outbox_written": False,
    "inbox_written": False,
    "checkpoint_written": False,
    "n6_written": False,
    "sim_trade_virtual_written": False,
    "worker_started": False,
}


def build_provisional_action_executed_plans(
    *,
    actioneligible_rows: Sequence[Mapping[str, Any]],
    confirmation_metric_rows: Sequence[Mapping[str, Any]],
    confirmation_projection_rows: Sequence[Mapping[str, Any]] | None = None,
    for_trade_date: str,
    confirmation_metric_run_id: str | None = None,
    confirmation_projection_run_id: str | None = None,
    latest_closed_minute: Any = None,
) -> list[dict[str, Any]]:
    """Return only in-memory ActionExecuted plans."""

    return list(
        build_provisional_action_executed_dry_run_report(
            actioneligible_rows=actioneligible_rows,
            confirmation_metric_rows=confirmation_metric_rows,
            confirmation_projection_rows=confirmation_projection_rows or [],
            for_trade_date=for_trade_date,
            confirmation_metric_run_id=confirmation_metric_run_id,
            confirmation_projection_run_id=confirmation_projection_run_id,
            latest_closed_minute=latest_closed_minute,
        )["action_executed_plans"]
    )


def build_provisional_action_executed_dry_run_report(
    *,
    actioneligible_rows: Sequence[Mapping[str, Any]],
    confirmation_metric_rows: Sequence[Mapping[str, Any]],
    confirmation_projection_rows: Sequence[Mapping[str, Any]] | None = None,
    for_trade_date: str,
    confirmation_metric_run_id: str | None = None,
    confirmation_projection_run_id: str | None = None,
    latest_closed_minute: Any = None,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    seen_canonical_keys: set[str] = set()

    normalized_metrics = [normalize_metric_row(row) for row in confirmation_metric_rows]
    confirmation_projection_row_count = len(confirmation_projection_rows or [])
    for raw_row in actioneligible_rows:
        row = normalize_eligible_row(raw_row)
        validation_error = validate_eligible_row(row)
        if validation_error:
            decisions.append(
                {
                    "decision": validation_error,
                    "source_eligible_event_id": row.get("event_id"),
                    "reason": validation_error.lower(),
                }
            )
            continue

        n3p_blocker = n3p_final_proof_blocker(row)
        if n3p_blocker:
            decisions.append(
                {
                    "decision": BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF,
                    "source_eligible_event_id": row.get("event_id"),
                    "reason": n3p_blocker,
                }
            )
            continue

        selected_metric_time = source_trigger_time_from_eligible(row)
        selected_minute_label = selected_minute_label_from_payload(row["payload_json"])
        metric = resolve_closed_confirmation_metric(
            eligible_row=row,
            confirmation_metric_rows=normalized_metrics,
            confirmation_metric_run_id=confirmation_metric_run_id,
        )
        if metric is None:
            decisions.append(
                {
                    "decision": PENDING_NO_CLOSED_METRIC,
                    "source_eligible_event_id": row.get("event_id"),
                    "selected_metric_time": selected_metric_time,
                    "selected_metric_minute_label": selected_minute_label,
                    "reason": "closed_confirmation_metric_not_found",
                }
            )
            continue

        payload = row["payload_json"]
        signal_type = str(payload.get("signal_type") or "")
        metric_id = str(metric.get("action_confirmation_metric_id") or metric.get("metric_id") or "")
        evaluation = evaluate_action_confirmation_metric(
            signal_type=signal_type,
            source_action_confirmation_metric_id=metric_id,
            metric_fact=metric,
            trigger_time=selected_metric_time,
            metric_required=True,
        )
        if not (evaluation.get("metric_context_status") == "ready" and evaluation.get("all_period_confirmation_pass")):
            decisions.append(
                {
                    "decision": NOT_EXECUTED_RULE_FAILED,
                    "source_eligible_event_id": row.get("event_id"),
                    "selected_metric_time": selected_metric_time,
                    "confirmation_metric_id": metric_id,
                    "confirmation_metric_run_id": metric.get("projection_run_id"),
                    "reason": f"confirmation_failed:{evaluation.get('blocked_reason') or evaluation.get('metric_context_status')}",
                    "rule_evaluation": json_safe_value(evaluation),
                }
            )
            continue

        plan = build_action_executed_plan(
            eligible_row=row,
            confirmation_metric=metric,
            evaluation=evaluation,
            for_trade_date=for_trade_date,
            latest_closed_minute=latest_closed_minute,
            action_confirmation_mode=PROVISIONAL_EXECUTED_MODE,
        )
        canonical_key = str(plan["payload"]["canonical_action_identity_key"])
        if canonical_key in seen_canonical_keys:
            decisions.append(
                {
                    "decision": SKIPPED_DUPLICATE_ACTION_EXECUTED,
                    "source_eligible_event_id": row.get("event_id"),
                    "canonical_action_identity_key": canonical_key,
                    "reason": "duplicate_canonical_action_identity_key",
                }
            )
            continue
        seen_canonical_keys.add(canonical_key)
        plans.append(plan)
        decisions.append(
            {
                "decision": ACTION_EXECUTED_PLAN,
                "source_eligible_event_id": row.get("event_id"),
                "canonical_action_identity_key": canonical_key,
                "confirmation_metric_id": plan["payload"]["confirmation_metric_id"],
                "confirmation_metric_run_id": plan["payload"]["confirmation_metric_run_id"],
            }
        )

    decision_counts = Counter(str(item["decision"]) for item in decisions)
    return {
        "status": "DRY_RUN_PASS",
        "for_trade_date": for_trade_date,
        "confirmation_metric_run_id": confirmation_metric_run_id,
        "latest_closed_minute": iso_string_or_none(latest_closed_minute),
        "eligible_row_count": len(actioneligible_rows),
        "confirmation_metric_row_count": len(confirmation_metric_rows),
        "confirmation_projection_row_count": confirmation_projection_row_count,
        "action_executed_plan_count": len(plans),
        "decision_counts": dict(decision_counts),
        "decisions": decisions,
        "action_executed_plans": plans,
        "side_effect_guard": dict(SIDE_EFFECT_GUARD),
    }


def normalize_eligible_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
    normalized_payload = dict(payload)
    condition_key = str(normalized_payload.get("condition_key") or "")
    if condition_key in SUPPORTED_HINT_CONDITIONS and not str(normalized_payload.get("trigger_type") or ""):
        normalized_payload["trigger_type"] = condition_key
    return {
        **dict(row),
        "event_type": row.get("event_type") or normalized_payload.get("event_type"),
        "asset_kind": row.get("asset_kind") or normalized_payload.get("asset_kind"),
        "identity_key": row.get("identity_key") or normalized_payload.get("identity_key"),
        "payload_json": normalized_payload,
    }


def normalize_metric_row(row: Mapping[str, Any]) -> dict[str, Any]:
    metric = dict(row)
    metric.setdefault("asset_kind", row.get("asset_kind"))
    metric.setdefault("projection_run_id", row.get("projection_run_id") or row.get("run_id"))
    return metric


def validate_eligible_row(row: Mapping[str, Any]) -> str | None:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
    if str(row.get("event_type") or payload.get("event_type") or "") != "ActionEligible":
        return SKIPPED_INVALID_PAYLOAD
    if not bool_value(payload.get("provisional")):
        return SKIPPED_INVALID_PAYLOAD
    if str(payload.get("action_confirmation_mode") or "") != "eligibility_only":
        return SKIPPED_INVALID_PAYLOAD
    condition_key = str(payload.get("condition_key") or "")
    trigger_type = str(payload.get("trigger_type") or "")
    signal_type = str(payload.get("signal_type") or "")
    if trigger_type not in SUPPORTED_TRIGGER_TYPES:
        return SKIPPED_INVALID_PAYLOAD
    if signal_type not in SUPPORTED_SIGNAL_TYPES:
        return SKIPPED_INVALID_PAYLOAD
    if condition_key in SUPPORTED_HINT_CONDITIONS or trigger_type in SUPPORTED_HINT_CONDITIONS:
        if condition_key not in SUPPORTED_HINT_CONDITIONS or trigger_type not in SUPPORTED_HINT_CONDITIONS:
            return SKIPPED_INVALID_PAYLOAD
        if condition_key == "BUY_HINT" and signal_type != "B_BUY":
            return SKIPPED_INVALID_PAYLOAD
        if condition_key == "SELL_HINT" and signal_type != "S_SELL":
            return SKIPPED_INVALID_PAYLOAD
        required_hint_fields = (
            "source_trigger_event_id",
            "source_trigger_run_id",
            "projection_run_id",
            "projection_id",
            "condition_key",
            "signal_type",
            "action_type",
        )
        if any(not str(payload.get(field) or "") for field in required_hint_fields):
            return SKIPPED_INVALID_PAYLOAD
        if not str(row.get("asset_kind") or "") or not str(row.get("identity_key") or ""):
            return SKIPPED_INVALID_PAYLOAD
        return None
    if trigger_type not in SUPPORTED_ORDINARY_TRIGGER_TYPES:
        return SKIPPED_INVALID_PAYLOAD
    required_fields = (
        "source_trigger_event_id",
        "source_trigger_run_id",
        "source_metric_run_id",
        "selected_metric_id",
        "selected_metric_time",
        "condition_key",
        "signal_type",
        "action_type",
    )
    if any(not str(payload.get(field) or "") for field in required_fields):
        return SKIPPED_INVALID_PAYLOAD
    if not str(row.get("asset_kind") or "") or not str(row.get("identity_key") or ""):
        return SKIPPED_INVALID_PAYLOAD
    return None


def n3p_final_proof_blocker(row: Mapping[str, Any]) -> str | None:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
    if str(payload.get("metric_role") or "") == "trigger_proof":
        return "metric_role=trigger_proof"
    if bool_value(payload.get("not_n5_final_proof")):
        return "not_n5_final_proof=true"
    if str(payload.get("source_trigger_proof_kind") or ""):
        return "source_trigger_proof_kind_present"
    if str(payload.get("source_metric_kind") or "") == SOURCE_METRIC_KIND:
        return "source_metric_kind=realtime_action_confirmation_metric"
    return None


def resolve_closed_confirmation_metric(
    *,
    eligible_row: Mapping[str, Any],
    confirmation_metric_rows: Sequence[Mapping[str, Any]],
    confirmation_metric_run_id: str | None = None,
) -> dict[str, Any] | None:
    payload = eligible_row.get("payload_json") if isinstance(eligible_row.get("payload_json"), Mapping) else {}
    selected_label = selected_minute_label_from_payload(payload)
    selected_dt = datetime_or_none(source_trigger_time_from_eligible(eligible_row))
    candidates = [
        metric
        for metric in confirmation_metric_rows
        if metric_matches_eligible(
            metric=metric,
            eligible_row=eligible_row,
            selected_minute_label=selected_label,
            confirmation_metric_run_id=confirmation_metric_run_id,
        )
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda metric: confirmation_metric_sort_key(metric=metric, selected_dt=selected_dt),
    )[0]


def metric_matches_eligible(
    *,
    metric: Mapping[str, Any],
    eligible_row: Mapping[str, Any],
    selected_minute_label: str,
    confirmation_metric_run_id: str | None,
) -> bool:
    payload = eligible_row.get("payload_json") if isinstance(eligible_row.get("payload_json"), Mapping) else {}
    if confirmation_metric_run_id and str(metric.get("projection_run_id") or "") != confirmation_metric_run_id:
        return False
    if str(metric.get("asset_kind") or "") != str(eligible_row.get("asset_kind") or ""):
        return False
    if str(metric.get("identity_key") or "") != str(eligible_row.get("identity_key") or ""):
        return False
    if str(metric.get("signal_type") or "") != str(payload.get("signal_type") or ""):
        return False
    if not bool_value(metric.get("is_closed_1m")):
        return False
    if not bool_value(metric.get("metric_ready")):
        return False
    metric_label = minute_label_from_metric(metric)
    return bool(selected_minute_label and metric_label == selected_minute_label)


def confirmation_metric_sort_key(*, metric: Mapping[str, Any], selected_dt: datetime | None) -> tuple[Any, ...]:
    metric_dt = datetime_or_none(metric.get("metric_time"))
    if selected_dt is not None and metric_dt is not None:
        distance = abs((metric_dt - selected_dt).total_seconds())
    else:
        distance = 0
    metric_ts = metric_dt.timestamp() if metric_dt is not None else float("-inf")
    metric_id = int_or_zero(metric.get("action_confirmation_metric_id") or metric.get("metric_id"))
    return (distance, -metric_ts, -metric_id, str(metric.get("projection_run_id") or ""))


def build_action_executed_plan(
    *,
    eligible_row: Mapping[str, Any],
    confirmation_metric: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    for_trade_date: str,
    latest_closed_minute: Any,
    action_confirmation_mode: str = PROVISIONAL_EXECUTED_MODE,
) -> dict[str, Any]:
    source_payload = eligible_row.get("payload_json") if isinstance(eligible_row.get("payload_json"), Mapping) else {}
    signal_type = str(source_payload.get("signal_type") or "")
    action_mark_decision = derive_action_mark_decision_from_n5_metric(
        signal_type=signal_type,
        metric=evaluation,
    )
    action_mark = str(action_mark_decision.get("action_mark") or "normal")
    action_type = str(source_payload.get("action_type") or action_type_from_signal(signal_type))
    confirmation_metric_id = str(
        confirmation_metric.get("action_confirmation_metric_id") or confirmation_metric.get("metric_id") or ""
    )
    confirmation_metric_run_id = str(confirmation_metric.get("projection_run_id") or "")
    selected_metric_time = str(
        source_payload.get("selected_metric_time")
        or source_trigger_time_from_eligible(eligible_row)
        or confirmation_metric.get("metric_time")
        or ""
    )
    selected_metric_id = source_payload.get("selected_metric_id") or int_or_original(confirmation_metric_id)
    source_metric_run_id = str(source_payload.get("source_metric_run_id") or confirmation_metric_run_id)
    canonical_key = build_canonical_action_identity_key(
        for_trade_date=for_trade_date,
        asset_kind=str(eligible_row.get("asset_kind") or ""),
        identity_key=str(eligible_row.get("identity_key") or ""),
        signal_type=signal_type,
        condition_key=str(source_payload.get("condition_key") or ""),
        action_type=action_type,
        selected_metric_time=selected_metric_time,
        action_mark=action_mark,
    )
    source_mode = source_mode_from_payload(source_payload) or source_mode_from_payload(confirmation_metric)
    c1_dependency = c1_dependency_from_payload(source_payload, confirmation_metric)
    is_closed_1m = bool_value(confirmation_metric.get("is_closed_1m"))
    source_metric_kind = str(
        source_payload.get("source_metric_kind")
        or confirmation_metric.get("source_metric_kind")
        or SOURCE_METRIC_KIND
    )
    dedup_key = join_dedup_parts(
        "N5P",
        "ActionExecuted",
        "canonical_action_identity_key",
        canonical_key,
        "confirmation_metric_run_id",
        confirmation_metric_run_id,
        "confirmation_metric_id",
        confirmation_metric_id,
        "source_eligible_event_id",
        str(eligible_row.get("event_id") or ""),
        "source_trigger_event_id",
        str(source_payload.get("source_trigger_event_id") or ""),
    )
    payload = {
        "event_type": "ActionExecuted",
        "provisional": True,
        "action_confirmation_mode": action_confirmation_mode,
        "action_state": "executed",
        "confirmation_status": "passed",
        "source_eligible_event_id": eligible_row.get("event_id"),
        "source_eligible_run_id": eligible_row.get("source_run_id"),
        "source_trigger_event_id": source_payload.get("source_trigger_event_id"),
        "source_trigger_run_id": source_payload.get("source_trigger_run_id"),
        "source_metric_kind": source_metric_kind,
        "source_metric_run_id": source_metric_run_id,
        "confirmation_metric_run_id": confirmation_metric_run_id,
        "selected_metric_id": selected_metric_id,
        "selected_metric_time": selected_metric_time,
        "confirmation_metric_id": int_or_original(confirmation_metric_id),
        "confirmation_metric_time": iso_string_or_none(
            confirmation_metric.get("metric_time") or evaluation.get("metric_time")
        ),
        "metric_time_label": source_payload.get("metric_time_label") or confirmation_metric.get("metric_time_label"),
        "metric_minute_label": minute_label_from_metric(confirmation_metric),
        "is_closed_1m": is_closed_1m,
        "source_mode": source_mode,
        "c1_dependency": c1_dependency,
        "for_trade_date": for_trade_date,
        "asset_kind": eligible_row.get("asset_kind"),
        "identity_key": eligible_row.get("identity_key"),
        "display_name": source_payload.get("display_name") or eligible_row.get("identity_key"),
        "condition_key": source_payload.get("condition_key"),
        "signal_type": signal_type,
        "trigger_type": source_payload.get("trigger_type") or source_payload.get("condition_key"),
        "action_type": action_type,
        "action_mark": action_mark,
        "trigger_mark_candidate": source_payload.get("trigger_mark_candidate"),
        "canonical_action_identity_key": canonical_key,
        "dedup_key": dedup_key,
        "rule_proof": {
            "source": "formal_n5_metric_evaluation",
            "metric_context_status": evaluation.get("metric_context_status"),
            "all_period_confirmation_pass": evaluation.get("all_period_confirmation_pass"),
            "selected_flags": json_safe_value(evaluation.get("selected_flags") or {}),
            "action_execution_required_flags": json_safe_value(
                evaluation.get("action_execution_required_flags") or {}
            ),
        },
        "trace": {
            "source": "n5p_action_executed_dry_run",
            "source_actioneligible_payload": json_safe_value(source_payload),
            "confirmation_metric": {
                "confirmation_metric_id": int_or_original(confirmation_metric_id),
                "confirmation_metric_run_id": confirmation_metric_run_id,
                "metric_time": iso_string_or_none(confirmation_metric.get("metric_time")),
                "metric_minute_label": minute_label_from_metric(confirmation_metric),
                "is_closed_1m": is_closed_1m,
            },
            "latest_closed_minute": iso_string_or_none(latest_closed_minute),
            "source_mode": source_mode,
            "c1_dependency": c1_dependency,
            "action_mark_decision": json_safe_value(action_mark_decision),
            "dedup_trace": {
                "event_type": "ActionExecuted",
                "confirmation_metric_run_id": confirmation_metric_run_id,
                "confirmation_metric_id": int_or_original(confirmation_metric_id),
                "source_eligible_event_id": eligible_row.get("event_id"),
                "source_trigger_event_id": source_payload.get("source_trigger_event_id"),
            },
        },
    }
    return {
        "decision": ACTION_EXECUTED_PLAN,
        "payload": json_safe_value(payload),
        "canonical_action_identity_key": canonical_key,
        "dedup_key": dedup_key,
    }


def selected_minute_label_from_payload(payload: Mapping[str, Any]) -> str:
    return normalize_minute_label(payload.get("metric_minute_label")) or normalize_minute_label(
        payload.get("selected_metric_time")
    ) or normalize_minute_label(
        payload.get("trigger_time")
    )


def source_minute_label_from_eligible(row: Mapping[str, Any]) -> str:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
    return selected_minute_label_from_payload(payload) or normalize_minute_label(row.get("event_time"))


def source_trigger_time_from_eligible(row: Mapping[str, Any]) -> str:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
    return str(
        payload.get("selected_metric_time")
        or payload.get("trigger_time")
        or row.get("event_time")
        or ""
    )


def source_mode_from_payload(payload: Mapping[str, Any]) -> str:
    trace = payload.get("trace") if isinstance(payload.get("trace"), Mapping) else {}
    rule_proof = payload.get("rule_proof") if isinstance(payload.get("rule_proof"), Mapping) else {}
    return str(
        payload.get("source_mode")
        or trace.get("source_mode")
        or rule_proof.get("source_mode")
        or ""
    )


def c1_dependency_from_payload(*payloads: Mapping[str, Any]) -> bool | None:
    for payload in payloads:
        trace = payload.get("trace") if isinstance(payload.get("trace"), Mapping) else {}
        rule_proof = payload.get("rule_proof") if isinstance(payload.get("rule_proof"), Mapping) else {}
        for value in (payload.get("c1_dependency"), trace.get("c1_dependency"), rule_proof.get("c1_dependency")):
            if value is not None:
                return bool_value(value)
    return None


def minute_label_from_metric(metric: Mapping[str, Any]) -> str:
    return normalize_minute_label(metric.get("metric_minute_label")) or normalize_minute_label(metric.get("metric_time"))


def normalize_minute_label(value: Any) -> str:
    if value is None or value == "":
        return ""
    text = str(value).strip()
    if len(text) == 5 and text[2] == ":":
        return text
    dt = datetime_or_none(value)
    if dt is not None:
        return dt.strftime("%H:%M")
    if len(text) >= 16 and text[13] == ":":
        return text[11:16]
    return ""


def datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def iso_string_or_none(value: Any) -> str | None:
    dt = datetime_or_none(value)
    if dt is not None:
        return dt.isoformat()
    if value in (None, ""):
        return None
    return str(value)


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "passed"}
    return bool(value)


def action_type_from_signal(signal_type: str) -> str:
    return "sell" if signal_type == "S_SELL" else "buy"


def int_or_zero(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def int_or_original(value: Any) -> Any:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return value


def json_safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe_value(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
