"""Shared N4P provisional trigger lifecycle planner.

The module is intentionally pure: it does not read or write the database. Hint
and ordinary execute paths use it to decide whether a current dry-run candidate
should write TriggerMatched, TriggerStateChanged, or nothing.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


TRIGGER_MATCHED_EVENT_TYPE = "TriggerMatched"
TRIGGER_PENDING_MARKET_DATA_EVENT_TYPE = "TriggerPendingMarketData"
TRIGGER_STATE_CHANGED_EVENT_TYPE = "TriggerStateChanged"
LIFECYCLE_STATE_KEY_VERSION = "n4p_provisional_trigger_lifecycle_v1"


def build_lifecycle_output_plans(
    current_plans: Sequence[Mapping[str, Any]],
    *,
    previous_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    previous_by_key = {lifecycle_state_key(state): dict(state) for state in previous_states}
    previous_by_revalidation_key: dict[str, list[dict[str, Any]]] = {}
    for state in previous_states:
        previous_by_revalidation_key.setdefault(lifecycle_revalidation_key(state), []).append(dict(state))
    outputs: list[dict[str, Any]] = []
    for raw_plan in current_plans:
        plan = dict(raw_plan)
        key = lifecycle_state_key(plan)
        previous = previous_by_key.get(key)
        if previous is None:
            revalidation_candidates = previous_by_revalidation_key.get(lifecycle_revalidation_key(plan), [])
            if len(revalidation_candidates) == 1:
                previous = revalidation_candidates[0]
        was_matched = previous_state_is_matched(previous)
        is_matched = current_plan_is_matched(plan)
        has_ready_evidence = current_plan_has_ready_evidence(plan)

        if str(plan.get("output_event_type") or "") == TRIGGER_PENDING_MARKET_DATA_EVENT_TYPE:
            pending = dict(plan)
            pending["trigger_live"] = False
            pending["current_status"] = "pending_market_data"
            outputs.append(
                annotate_lifecycle_plan(
                    pending,
                    event_type=TRIGGER_PENDING_MARKET_DATA_EVENT_TYPE,
                    previous_state=previous,
                )
            )
            continue
        if is_matched and not was_matched:
            outputs.append(annotate_lifecycle_plan(plan, event_type=TRIGGER_MATCHED_EVENT_TYPE, previous_state=previous))
            continue
        if is_matched and was_matched:
            if lifecycle_state_materially_changed(previous or {}, plan):
                outputs.append(
                    annotate_lifecycle_plan(plan, event_type=TRIGGER_STATE_CHANGED_EVENT_TYPE, previous_state=previous)
                )
            continue
        if not is_matched and was_matched and has_ready_evidence:
            inactive = dict(plan)
            inactive["trigger_live"] = False
            inactive["current_status"] = "inactive"
            inactive["trigger_mark_candidate"] = "none"
            inactive["projection_30m_flag"] = False
            outputs.append(
                annotate_lifecycle_plan(inactive, event_type=TRIGGER_STATE_CHANGED_EVENT_TYPE, previous_state=previous)
            )
            continue
    return outputs


def annotate_lifecycle_plan(
    plan: Mapping[str, Any],
    *,
    event_type: str,
    previous_state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    output = dict(plan)
    output["output_event_type"] = event_type
    output["lifecycle_state_key"] = lifecycle_state_key(plan)
    output["lifecycle_state_key_version"] = LIFECYCLE_STATE_KEY_VERSION
    output["previous_current_status"] = previous_status(previous_state)
    output["previous_status"] = previous_status(previous_state)
    output["previous_trigger_live"] = previous_state_is_matched(previous_state)
    output["primary_trigger_period"] = plan.get("primary_trigger_period") or plan.get("trigger_period")
    output["triggered_periods"] = _list_value(plan.get("triggered_periods") or plan.get("all_trigger_periods") or plan.get("trigger_period"))
    output["all_trigger_periods"] = _list_value(plan.get("all_trigger_periods") or plan.get("triggered_periods") or plan.get("trigger_period"))
    output["previous_primary_trigger_period"] = raw_json_value(previous_state or {}, "primary_trigger_period", default=(previous_state or {}).get("trigger_period"))
    output["previous_triggered_periods"] = _list_value(raw_json_value(previous_state or {}, "triggered_periods", default=[]))
    output["previous_all_trigger_periods"] = _list_value(raw_json_value(previous_state or {}, "all_trigger_periods", default=[]))
    output["previous_projection_30m_flag"] = bool(raw_json_value(previous_state or {}, "projection_30m_flag", default=False))
    output["previous_projection_30m_type"] = _text(raw_json_value(previous_state or {}, "projection_30m_type"))
    output["previous_trigger_mark_candidate"] = _text(raw_json_value(previous_state or {}, "trigger_mark_candidate"))
    output["writes_trigger_match"] = event_type == TRIGGER_MATCHED_EVENT_TYPE
    output["n5_entry_allowed"] = event_type == TRIGGER_MATCHED_EVENT_TYPE
    output["is_n5_action_entry"] = event_type == TRIGGER_MATCHED_EVENT_TYPE
    if event_type == TRIGGER_MATCHED_EVENT_TYPE:
        output["current_status"] = "matched"
        output["trigger_live"] = True
    elif event_type == TRIGGER_PENDING_MARKET_DATA_EVENT_TYPE:
        output["current_status"] = "pending_market_data"
        output["trigger_live"] = False
    elif event_type == TRIGGER_STATE_CHANGED_EVENT_TYPE:
        current_status = canonical_current_status(output)
        if current_status == "inactive":
            output["current_status"] = "inactive"
            output["trigger_live"] = False
        elif current_status == "pending_market_data":
            output["current_status"] = "pending_market_data"
            output["trigger_live"] = False
        else:
            output["current_status"] = "matched"
            output["trigger_live"] = True
    output["lifecycle_output_reason"] = lifecycle_output_reason(output, previous_state=previous_state)
    output["state_change_reason"] = (
        "deactivated"
        if event_type == TRIGGER_STATE_CHANGED_EVENT_TYPE and output.get("current_status") == "inactive"
        else output["lifecycle_output_reason"]
    )
    return output


def lifecycle_output_reason(plan: Mapping[str, Any], *, previous_state: Mapping[str, Any] | None) -> str:
    event_type = str(plan.get("output_event_type") or "")
    if event_type == TRIGGER_MATCHED_EVENT_TYPE:
        return "inactive_to_matched"
    if event_type == TRIGGER_PENDING_MARKET_DATA_EVENT_TYPE:
        return "pending_market_data"
    if event_type == TRIGGER_STATE_CHANGED_EVENT_TYPE and str(plan.get("current_status") or "") == "inactive":
        return "matched_to_inactive"
    if event_type == TRIGGER_STATE_CHANGED_EVENT_TYPE and previous_state:
        return "matched_changed"
    return "dropped"


def lifecycle_state_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            _text(row.get("for_trade_date")),
            _text(row.get("asset_kind")),
            _text(row.get("identity_key")),
            _text(row.get("signal_type")),
            _text(row.get("condition_key")),
            canonical_trigger_type_for_lifecycle(row),
        ]
    )


def lifecycle_revalidation_key(row: Mapping[str, Any]) -> str:
    """Match current evidence to legacy live state without changing persisted keys."""

    return "|".join(
        [
            _text(row.get("for_trade_date")),
            _text(row.get("asset_kind")),
            _text(row.get("identity_key")),
            _text(row.get("direction")),
            normalized_signal_type_for_revalidation(row),
            _text(row.get("condition_key")),
        ]
    )


def normalized_signal_type_for_revalidation(row: Mapping[str, Any]) -> str:
    signal_type = _text(row.get("signal_type") or raw_json_value(row, "signal_type"))
    if signal_type in {"B_BUY", "BUY"}:
        return "BUY"
    if signal_type in {"S_SELL", "SELL"}:
        return "SELL"
    return signal_type


def current_plan_is_matched(plan: Mapping[str, Any]) -> bool:
    return (
        str(plan.get("plan_status") or "") == "matched"
        or str(plan.get("output_event_type") or "") == TRIGGER_MATCHED_EVENT_TYPE
        or str(plan.get("current_status") or "") == "matched"
    )


def previous_state_is_matched(state: Mapping[str, Any] | None) -> bool:
    if not state:
        return False
    return canonical_current_status(state) == "matched"


def current_plan_has_ready_evidence(plan: Mapping[str, Any]) -> bool:
    if current_plan_is_matched(plan):
        return True
    explicit_projection_ready = (
        str(plan.get("projection_status") or "") == "ready"
        and str(plan.get("projection_quality_status") or "") == "passed"
        and str(plan.get("trace_status") or "") == "passed"
    )
    selected_metric = plan.get("rule_proof", {})
    selected_metric = selected_metric if isinstance(selected_metric, Mapping) else {}
    selected_metric = selected_metric.get("selected_metric", {})
    selected_metric = selected_metric if isinstance(selected_metric, Mapping) else {}
    metric_ready = plan.get("metric_ready") is True or selected_metric.get("metric_ready") is True
    if not metric_ready:
        return explicit_projection_ready
    for quality_key in (
        "data_quality_status",
        "metric_quality_status",
        "current_metric_quality_status",
        "projection_quality_status",
        "trace_status",
    ):
        quality = plan.get(quality_key)
        if quality is not None and str(quality).strip().lower() not in {"", "passed", "pass", "ready", "ok"}:
            return False
    rule_eval = plan.get("rule_eval_result")
    rule_eval = rule_eval if isinstance(rule_eval, Mapping) else {}
    if rule_eval.get("pending_reasons") or rule_eval.get("quality_reasons") or rule_eval.get("blocked_reason"):
        return False
    return explicit_projection_ready or plan.get("metric_ready") is True or (
        str(rule_eval.get("outcome_classification") or "") == "no_op"
    )


def lifecycle_state_materially_changed(previous: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    return canonical_lifecycle_state(previous) != canonical_lifecycle_state(current)


def trigger_type_for_lifecycle(row: Mapping[str, Any]) -> str:
    return _text(row.get("trigger_type") or raw_json_value(row, "trigger_type") or row.get("condition_key"))


def canonical_trigger_type_for_lifecycle(row: Mapping[str, Any]) -> str:
    raw_trigger_type = trigger_type_for_lifecycle(row)
    if raw_trigger_type in {"BUY_HINT", "SELL_HINT", "BUY:FULL", "SELL:FULL"}:
        return raw_trigger_type
    if raw_trigger_type == "BUY" or raw_trigger_type.startswith("BUY:"):
        return "BUY"
    if raw_trigger_type == "SELL" or raw_trigger_type.startswith("SELL:"):
        return "SELL"
    return raw_trigger_type


def canonical_lifecycle_state(row: Mapping[str, Any]) -> dict[str, Any]:
    current_status = canonical_current_status(row)
    primary_period = raw_json_value(
        row,
        "primary_trigger_period",
        default=row.get("primary_trigger_period") or raw_json_value(row, "trigger_period", default=row.get("trigger_period")),
    )
    all_periods = raw_json_value(
        row,
        "all_trigger_periods",
        default=row.get("all_trigger_periods")
        or raw_json_value(row, "triggered_periods", default=row.get("triggered_periods"))
        or primary_period,
    )
    triggered_periods = raw_json_value(
        row,
        "triggered_periods",
        default=row.get("triggered_periods") or all_periods or primary_period,
    )
    return {
        "current_status": current_status,
        "trigger_live": canonical_trigger_live(row, current_status=current_status),
        "primary_trigger_period": _text(primary_period),
        "triggered_periods": tuple(_text(period) for period in _list_value(triggered_periods)),
        "all_trigger_periods": tuple(_text(period) for period in _list_value(all_periods)),
        "projection_30m_flag": bool_value(raw_json_value(row, "projection_30m_flag", default=row.get("projection_30m_flag"))),
        "projection_30m_type": _text(raw_json_value(row, "projection_30m_type", default=row.get("projection_30m_type") or "none") or "none"),
        "trigger_mark_candidate": _text(raw_json_value(row, "trigger_mark_candidate", default=row.get("trigger_mark_candidate") or "none") or "none"),
    }


def canonical_current_status(row: Mapping[str, Any]) -> str:
    event_type = _text(row.get("output_event_type") or raw_json_value(row, "event_type") or raw_json_value(row, "output_event_type"))
    explicit_status = _text(row.get("current_status") or raw_json_value(row, "current_status"))
    if event_type == TRIGGER_PENDING_MARKET_DATA_EVENT_TYPE:
        return "pending_market_data"
    if event_type == TRIGGER_MATCHED_EVENT_TYPE or explicit_status == "matched" or _text(row.get("plan_status")) == "matched":
        return "matched"
    if explicit_status in {"inactive", "pending_market_data"}:
        return explicit_status
    if _text(row.get("plan_status")) in {"inactive", "no_op"}:
        return "inactive"
    return explicit_status or "inactive"


def canonical_trigger_live(row: Mapping[str, Any], *, current_status: str) -> bool:
    if current_status == "matched":
        return True
    if current_status in {"inactive", "pending_market_data"}:
        return False
    return bool_value(raw_json_value(row, "trigger_live", default=row.get("trigger_live")))


def raw_json_value(row: Mapping[str, Any], key: str, *, default: Any = "") -> Any:
    raw_json = row.get("raw_json")
    raw_json = raw_json if isinstance(raw_json, Mapping) else {}
    if key in raw_json:
        return raw_json.get(key)
    plan = raw_json.get("plan")
    if isinstance(plan, Mapping) and key in plan:
        return plan.get(key)
    return default


def comparable_current_value(row: Mapping[str, Any], field: str) -> Any:
    if field == "projection_30m_flag":
        return bool(row.get(field)) if field in row else False
    if field == "projection_30m_type":
        return row.get(field) if row.get(field) not in (None, "") else "none"
    if field == "primary_trigger_period":
        return row.get(field) or row.get("trigger_period")
    return row.get(field)


def raw_json_has_value(row: Mapping[str, Any], key: str) -> bool:
    if key in row and row.get(key) not in (None, ""):
        return True
    raw_json = row.get("raw_json")
    raw_json = raw_json if isinstance(raw_json, Mapping) else {}
    if key in raw_json and raw_json.get(key) not in (None, ""):
        return True
    plan = raw_json.get("plan")
    return bool(isinstance(plan, Mapping) and key in plan and plan.get(key) not in (None, ""))


def previous_status(state: Mapping[str, Any] | None) -> str:
    if not state:
        return "inactive"
    return str(state.get("current_status") or "inactive")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    if text in {"true", "t", "1", "yes"}:
        return True
    if text in {"false", "f", "0", "no", ""}:
        return False
    return bool(value)


def comparable_scalar(value: Any) -> Any:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return value
    try:
        return Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError):
        return _text(value)


def _list_value(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                return [value]
            if isinstance(decoded, list):
                return decoded
    return [value]
