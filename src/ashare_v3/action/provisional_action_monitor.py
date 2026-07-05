"""N5P active-monitor v2 state planner.

The planner is intentionally pure. It does not write action facts, inbox rows,
checkpoints, or outbox rows; execute gates can consume this contract later.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


ACTIVE_MONITOR_MODE = "n5p_active_monitor_v2"
DIRECT_REPLAY_MODE = "direct_source_replay_no_inbox_checkpoint"
OUTBOX_CONSUMER_MODE = "outbox_consumer"

ACTION_ELIGIBLE = "ActionEligible"
ACTION_SKIPPED = "ActionSkipped"
TRIGGER_MATCHED = "TriggerMatched"
TRIGGER_STATE_CHANGED = "TriggerStateChanged"

SIDE_EFFECT_GUARD = {
    "db_written": False,
    "action_fact_written": False,
    "action_event_written": False,
    "outbox_written": False,
    "inbox_written": False,
    "checkpoint_written": False,
    "worker_started": False,
    "n6_written": False,
    "sim_trade_virtual_written": False,
}


def build_monitor_window_id(trigger_matched_event_id: str) -> str:
    return f"{ACTIVE_MONITOR_MODE}:{trigger_matched_event_id}"


def build_provisional_action_monitor_plan(
    *,
    n4_event_rows: Sequence[Mapping[str, Any]],
    existing_tracking_states: Sequence[Mapping[str, Any]],
    existing_action_event_keys: set[str] | frozenset[str],
    action_run_id: str,
    consumer_mode: str,
    for_trade_date: str | None = None,
) -> dict[str, Any]:
    states = [dict(row) for row in existing_tracking_states]
    states_by_window = {str(row.get("monitor_window_id") or ""): row for row in states}
    tracking_state_plans: list[dict[str, Any]] = []
    action_event_plans: list[dict[str, Any]] = []
    tracking_counts: Counter[str] = Counter()

    for raw_event in n4_event_rows:
        event = normalize_n4_event(raw_event)
        payload = event["payload_json"]
        event_type = str(event.get("event_type") or "")
        if event_type == TRIGGER_MATCHED:
            window_id = build_monitor_window_id(str(event.get("event_id") or ""))
            if window_id in states_by_window or window_id in existing_action_event_keys:
                tracking_counts["noop_existing_window"] += 1
                continue
            plan = build_window_plan(
                operation="create_window",
                event=event,
                payload=payload,
                monitor_window_id=window_id,
                action_run_id=action_run_id,
                for_trade_date=for_trade_date,
            )
            tracking_state_plans.append(plan)
            action_event_plans.append(build_action_eligible_plan(plan, event=event, payload=payload))
            tracking_counts["create_window"] += 1
            continue

        if event_type != TRIGGER_STATE_CHANGED:
            tracking_counts["noop_unsupported_event"] += 1
            continue

        active_state = find_active_state(states, payload)
        if active_state is None:
            tracking_counts["noop_missing_active_window"] += 1
            continue

        trigger_live = bool(payload.get("trigger_live"))
        current_status = str(payload.get("current_status") or "")
        if not trigger_live or current_status == "inactive":
            expire_plan = build_window_plan(
                operation="expire_window",
                event=event,
                payload=payload,
                monitor_window_id=str(active_state.get("monitor_window_id") or ""),
                action_run_id=action_run_id,
                for_trade_date=for_trade_date,
                previous_state=active_state,
            )
            tracking_state_plans.append(expire_plan)
            skipped_key = build_action_skipped_key(expire_plan)
            if skipped_key not in existing_action_event_keys:
                action_event_plans.append(build_action_skipped_plan(expire_plan, event=event, payload=payload))
            tracking_counts["expire_window"] += 1
            continue

        update_plan = build_window_plan(
            operation="update_context",
            event=event,
            payload=payload,
            monitor_window_id=str(active_state.get("monitor_window_id") or ""),
            action_run_id=action_run_id,
            for_trade_date=for_trade_date,
            previous_state=active_state,
        )
        tracking_state_plans.append(update_plan)
        tracking_counts["update_context"] += 1

    event_counts = Counter(str(row["event_type"]) for row in action_event_plans)
    return {
        "status": "PLAN_READY",
        "mode": ACTIVE_MONITOR_MODE,
        "action_run_id": action_run_id,
        "consumer_mode": consumer_mode,
        "for_trade_date": for_trade_date,
        "tracking_state_plans": tracking_state_plans,
        "action_event_plans": action_event_plans,
        "tracking_plan_counts": dict(tracking_counts),
        "event_counts": dict(event_counts),
        "side_effect_guard": side_effect_guard_for_mode(consumer_mode),
    }


def normalize_n4_event(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json")
    payload = payload if isinstance(payload, Mapping) else {}
    output = dict(row)
    output["payload_json"] = dict(payload)
    output["event_type"] = str(output.get("event_type") or payload.get("event_type") or "")
    output["asset_kind"] = str(output.get("asset_kind") or payload.get("asset_kind") or "")
    output["identity_key"] = str(output.get("identity_key") or payload.get("identity_key") or "")
    output["trade_date"] = str(output.get("trade_date") or payload.get("trade_date") or "")
    return output


def find_active_state(states: Sequence[Mapping[str, Any]], payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for state in states:
        if str(state.get("tracking_status") or "") != "tracking":
            continue
        if not bool(state.get("trigger_live")):
            continue
        if str(state.get("current_status") or "") != "matched":
            continue
        if lifecycle_identity_matches(state, payload):
            return state
    return None


def lifecycle_identity_matches(state: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    fields = ("asset_kind", "identity_key", "signal_type", "condition_key", "trigger_type")
    return all(str(state.get(field) or "") == str(payload.get(field) or "") for field in fields)


def build_window_plan(
    *,
    operation: str,
    event: Mapping[str, Any],
    payload: Mapping[str, Any],
    monitor_window_id: str,
    action_run_id: str,
    for_trade_date: str | None,
    previous_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    status = "expired" if operation == "expire_window" else "tracking"
    current_status = "inactive" if operation == "expire_window" else "matched"
    return {
        "operation": operation,
        "monitor_window_id": monitor_window_id,
        "action_run_id": action_run_id,
        "for_trade_date": for_trade_date or str(event.get("trade_date") or payload.get("trade_date") or ""),
        "asset_kind": str(payload.get("asset_kind") or event.get("asset_kind") or ""),
        "identity_key": str(payload.get("identity_key") or event.get("identity_key") or ""),
        "signal_type": str(payload.get("signal_type") or ""),
        "condition_key": str(payload.get("condition_key") or ""),
        "trigger_type": str(payload.get("trigger_type") or ""),
        "tracking_status": status,
        "action_state": "expired" if operation == "expire_window" else "eligible",
        "confirmation_status": "expired" if operation == "expire_window" else "pending",
        "trigger_live": operation != "expire_window",
        "current_status": current_status,
        "latest_n4_event_id": str(event.get("event_id") or ""),
        "latest_n4_event_type": str(event.get("event_type") or ""),
        "latest_n4_event_time": event.get("event_time"),
        "trigger_period": payload.get("trigger_period"),
        "triggered_periods": list_value(payload.get("triggered_periods") or payload.get("all_trigger_periods") or payload.get("trigger_period")),
        "trigger_price": payload.get("trigger_price"),
        "trigger_mark_candidate": payload.get("trigger_mark_candidate"),
        "trigger_context_version": str(event.get("event_id") or ""),
        "last_seen_metric_key": (previous_state or {}).get("last_seen_metric_key"),
        "last_final_evaluated_metric_key": (previous_state or {}).get("last_final_evaluated_metric_key"),
        "raw_json": {
            "mode": ACTIVE_MONITOR_MODE,
            "latest_trigger_context": dict(payload),
            "source_n4_event": {
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "source_run_id": event.get("source_run_id"),
            },
        },
    }


def build_action_eligible_plan(
    window_plan: Mapping[str, Any],
    *,
    event: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": ACTION_ELIGIBLE,
        "monitor_window_id": window_plan["monitor_window_id"],
        "action_run_id": window_plan["action_run_id"],
        "action_state": "eligible",
        "confirmation_status": "pending",
        "source_n4_event_id": event.get("event_id"),
        "source_n4_event_type": event.get("event_type"),
        "payload": {
            **context_payload(window_plan),
            "source_trigger_event_id": event.get("event_id"),
            "source_trigger_run_id": event.get("source_run_id") or payload.get("run_id"),
        },
    }


def build_action_skipped_plan(
    window_plan: Mapping[str, Any],
    *,
    event: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "event_type": ACTION_SKIPPED,
        "monitor_window_id": window_plan["monitor_window_id"],
        "action_run_id": window_plan["action_run_id"],
        "action_state": "expired",
        "confirmation_status": "expired",
        "reason": "trigger_live_false",
        "idempotency_key": build_action_skipped_key(window_plan),
        "source_n4_event_id": event.get("event_id"),
        "source_n4_event_type": event.get("event_type"),
        "payload": {
            **context_payload(window_plan),
            "action_state": "expired",
            "reason": "trigger_live_false",
            "source_trigger_event_id": event.get("event_id"),
            "source_trigger_run_id": event.get("source_run_id") or payload.get("run_id"),
        },
    }


def build_action_skipped_key(window_plan: Mapping[str, Any]) -> str:
    return "|".join([str(window_plan.get("monitor_window_id") or ""), "ActionSkipped", "trigger_live_false"])


def context_payload(window_plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "mode": ACTIVE_MONITOR_MODE,
        "monitor_window_id": window_plan.get("monitor_window_id"),
        "trade_date": window_plan.get("for_trade_date"),
        "asset_kind": window_plan.get("asset_kind"),
        "identity_key": window_plan.get("identity_key"),
        "signal_type": window_plan.get("signal_type"),
        "condition_key": window_plan.get("condition_key"),
        "trigger_type": window_plan.get("trigger_type"),
        "latest_n4_event_id": window_plan.get("latest_n4_event_id"),
        "latest_n4_event_type": window_plan.get("latest_n4_event_type"),
        "latest_n4_event_time": window_plan.get("latest_n4_event_time"),
        "trigger_period": window_plan.get("trigger_period"),
        "triggered_periods": list(window_plan.get("triggered_periods") or []),
        "trigger_price": window_plan.get("trigger_price"),
        "trigger_mark_candidate": window_plan.get("trigger_mark_candidate"),
        "trigger_context_version": window_plan.get("trigger_context_version"),
    }


def side_effect_guard_for_mode(consumer_mode: str) -> dict[str, bool]:
    guard = dict(SIDE_EFFECT_GUARD)
    if consumer_mode == DIRECT_REPLAY_MODE:
        guard["inbox_written"] = False
        guard["checkpoint_written"] = False
    return guard


def list_value(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]
