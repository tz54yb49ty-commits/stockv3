"""N5 live tracking bounded poller planner.

The module is pure planning logic. It consumes normalized N4 event rows plus
N3 action-confirmation metric rows and returns the N5-only state/event effects
that a bounded one-shot runner can persist later.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping, Sequence

from ashare_v3.action.dry_run import (
    BUY_CONFIRMATION_FLAGS,
    CALIBRATED_METRIC_POLICY_VERSION,
    CANONICAL_RUNTIME_SIGNAL_TYPES,
    SELL_CONFIRMATION_FLAGS,
    build_action_tracking_state_key,
    datetime_or_none,
    evaluate_action_confirmation_metric,
)
from ashare_v3.condition.basis import normalize_mapping
from ashare_v3.events.ids import build_stable_event_id, join_dedup_parts
from ashare_v3.market.minute_label_normalization import canonical_ashare_1m_labels


N5_SOURCE_LAYER = "N5_action"
N5_LIVE_TRACKING_SCHEMA_VERSION = "v2"
N5_LIVE_TRACKING_INPUT_EVENTS = ("TriggerMatched", "TriggerStateChanged")
N5_LIVE_TRACKING_OUTPUT_EVENTS = ("ActionEligible", "ActionExecuted")
FINAL_ACTION_MARKS = ("normal", "30m_volume", "30m_shrink")
TERMINAL_TRACKING_STATES = ("blocked", "executed", "skipped", "expired")
REQUIRED_N3T_SOURCE_BASIS = "N3T_C1_CLOSED"
N3T_METRIC_REQUIRED_REASON = "BLOCKED_N3T_METRIC_REQUIRED"
N3P_NOT_ACTION_PROOF_REASON = "BLOCKED_N3P_NOT_ACTION_CONFIRMATION_PROOF"
N3T_POLICY_ALIGNMENT_TRACE_KEY = "n5_n3t_closed_c1_policy_alignment"
POST_CLOSE_NO_ACTION_EXPIRED_REASON = "post_close_no_action_final_minute_checked"
N5_TRIGGER_ACTION_PCT_CONTEXT_VERSION = "N5-trigger-action-pct-context-v1"
N2_CONDITION_PROJECTION_CONTEXT_VERSION = "N2-condition-projection-context-v1"
N4_CONDITION_PROJECTION_PASSTHROUGH_POLICY_VERSION = "N4-condition-projection-passthrough-v1"
N4_CONDITION_PROJECTION_PASSTHROUGH_POLICY_HASH = (
    "2cd95d3d427ec07ccd208bc7b939081d104415f6b9da3c4bf78e40b78a6d279e"
)
N5_N6_PROJECTION_MESSAGE_CONTRACT_VERSION = "N5-n6-projection-message-v1"
N5_N6_PROJECTION_MESSAGE_CONTRACT = {
    "action_policy": "n5_live_tracking_bounded_v2",
    "common_keys": [
        "asset_kind",
        "identity_key",
        "asset_code",
        "asset_name",
        "direction",
        "condition_key",
        "trigger_period",
        "trigger_price",
        "trigger_pct",
        "buy_expected_return_pct",
        "sell_expected_return_pct",
        "up_secondary_expected_return_pct",
        "up_reference_period",
        "down_reference_period",
        "primary_trigger_period",
        "all_trigger_periods",
        "action_state",
        "action_mark",
        "condition_projection_context",
    ],
    "condition_context_fields": [
        "name",
        "close",
        "up_reference_period",
        "buy_target_price",
        "buy_expected_return_pct",
        "down_reference_period",
        "sell_target_price",
        "sell_expected_return_pct",
        "clear_sell_ref_period",
        "up_secondary_target_price",
        "up_secondary_expected_return_pct",
        "score",
        "pe_core",
    ],
    "contract_version": N5_N6_PROJECTION_MESSAGE_CONTRACT_VERSION,
    "core_ready_values": [
        "asset_kind",
        "identity_key",
        "asset_code",
        "asset_name",
        "direction",
        "condition_key",
        "trigger_price",
        "trigger_pct",
        "action_state",
        "condition_projection_context.contract_version",
        "condition_projection_context.context_hash",
        "condition_projection_context.status",
    ],
    "event_schema_version": "v2",
    "event_shapes": {
        "ActionEligible": {"forbidden_fields": ["action_price", "action_pct", "action_pct_status"]},
        "ActionExecuted": {"required_ready_fields": ["action_price", "action_pct", "action_pct_status"]},
    },
    "event_types": ["ActionEligible", "ActionExecuted"],
    "field_sources": {
        "action_pct": "N5-trigger-action-pct-context-v1.entry_close_and_action_price",
        "action_price": "selected_passing_N3T_C1_CLOSED.current_price",
        "all_trigger_periods": "current_live_tracking_state",
        "asset_code": "validated_identity_key_last_segment",
        "asset_name": "action_entry_condition_projection_context.fields.name",
        "condition_fields": "action_entry_condition_projection_context.fields",
        "primary_trigger_period": "current_live_tracking_state",
        "trigger_pct": "N5-trigger-action-pct-context-v1.entry_snapshot",
        "trigger_price": "action_entry_trigger_matched_ref.source_n4_payload.trigger_price",
    },
    "formal_period_contract": "ordinary_YQMWD_or_hint_empty_with_trigger_period_30m",
    "invalid_effect": "projection_message_status_not_ready_without_n5_action_lifecycle_event_id_or_dedup_change",
    "marker_fields": [
        "projection_message_contract_version",
        "projection_message_contract_hash",
        "projection_message_status",
        "projection_message_not_ready_reasons",
    ],
    "optional_nullable_fields": [
        "buy_expected_return_pct",
        "sell_expected_return_pct",
        "up_secondary_expected_return_pct",
        "up_reference_period",
        "down_reference_period",
        "action_mark",
        "score",
        "pe_core",
    ],
    "pct_contract_version": N5_TRIGGER_ACTION_PCT_CONTEXT_VERSION,
    "source_layer": N5_SOURCE_LAYER,
    "stock_only_keys": ["score", "pe_core"],
    "upstream_context_version": N2_CONDITION_PROJECTION_CONTEXT_VERSION,
}
N5_N6_PROJECTION_MESSAGE_CONTRACT_JSON = json.dumps(
    N5_N6_PROJECTION_MESSAGE_CONTRACT,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
N5_N6_PROJECTION_MESSAGE_CONTRACT_HASH = hashlib.sha256(
    N5_N6_PROJECTION_MESSAGE_CONTRACT_JSON.encode("utf-8")
).hexdigest()
N5_N6_PROJECTION_MESSAGE_CONTRACT_BYTES = 2653
N5_N6_PROJECTION_MESSAGE_CONTRACT_HASH_EXPECTED = (
    "572078a71de8cf00963f718bc812fbe3a1ae09652a3faaa8bb3774f51b882025"
)
if (
    len(N5_N6_PROJECTION_MESSAGE_CONTRACT_JSON.encode("utf-8"))
    != N5_N6_PROJECTION_MESSAGE_CONTRACT_BYTES
    or N5_N6_PROJECTION_MESSAGE_CONTRACT_HASH
    != N5_N6_PROJECTION_MESSAGE_CONTRACT_HASH_EXPECTED
):
    raise RuntimeError("N5/N6 projection-message contract manifest mismatch")
N5_N6_PROJECTION_MESSAGE_NOT_READY_REASON_ORDER = (
    "action_entry_trigger_matched_ref_missing",
    "condition_projection_context_missing",
    "condition_projection_context_not_object",
    "condition_projection_contract_version_mismatch",
    "condition_projection_source_layer_mismatch",
    "condition_projection_asset_kind_mismatch",
    "condition_projection_identity_key_mismatch",
    "condition_projection_for_trade_date_mismatch",
    "condition_projection_context_status_not_ready",
    "condition_projection_source_status_not_ready",
    "condition_projection_fields_missing",
    "condition_projection_field_shape_mismatch",
    "condition_projection_close_invalid",
    "condition_projection_context_hash_missing",
    "condition_projection_context_hash_mismatch",
    "condition_projection_trace_policy_version_mismatch",
    "condition_projection_trace_policy_hash_invalid",
    "condition_projection_trace_status_not_ready",
    "condition_projection_trace_source_hash_mismatch",
    "asset_code_invalid",
    "asset_name_missing",
    "trigger_pct_status_not_ready",
    "action_price_invalid",
    "action_pct_status_not_ready",
)
PCT_DECIMAL_QUANTUM = Decimal("0.000001")


def build_live_tracking_plan(
    *,
    n4_event_rows: Sequence[Mapping[str, Any]],
    repair_n4_event_rows: Sequence[Mapping[str, Any]] = (),
    active_tracking_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
    action_run_id: str,
    source_trigger_run_id: str,
    source_metric_run_id: str,
    consumer_name: str,
    existing_action_event_keys: set[str] | Sequence[str] | None = None,
    active_scope_tracking_rows: Sequence[Mapping[str, Any]] | None = None,
    for_trade_date: str | None = None,
) -> dict[str, Any]:
    """Plan one bounded N5 live-tracking invocation.

    N4 event rows are treated as immutable inputs. The returned plan contains
    N5 tracking updates, N5 action events, and N5 inbox/checkpoint intent only.
    """

    existing_event_keys = {str(key) for key in (existing_action_event_keys or set())}
    metric_index = _index_metric_rows(metric_rows, source_metric_run_id=source_metric_run_id)
    active_by_key: dict[str, dict[str, Any]] = {}
    latest_planned_by_key: dict[str, dict[str, Any]] = {}
    planned_update_keys: set[str] = set()
    action_events: list[dict[str, Any]] = []
    tracking_updates: list[dict[str, Any]] = []
    consumed_n4_event_ids: list[str] = []
    consumed_n4_events: list[dict[str, Any]] = []
    attention_scope_events: list[dict[str, Any]] = []
    active_scope_new_state_keys: set[str] = set()
    input_counter: Counter[str] = Counter()

    def append_consumed_n4_event(row: Mapping[str, Any]) -> None:
        event_id = str(row.get("event_id") or "")
        if event_id:
            consumed_n4_event_ids.append(event_id)
            consumed_n4_events.append(normalize_mapping(row))

    def latest_tracking_state(state_key: str) -> dict[str, Any] | None:
        return (
            latest_planned_by_key.get(state_key)
            or active_by_key.get(state_key)
            or _find_tracking_row(active_tracking_rows, state_key)
        )

    source_trigger_filter = str(source_trigger_run_id or "")
    for row in _sort_event_rows(n4_event_rows):
        event_type = str(row.get("event_type") or "")
        if event_type not in N5_LIVE_TRACKING_INPUT_EVENTS:
            continue
        input_counter[event_type] += 1
        if source_trigger_filter and str(row.get("source_run_id") or "") != source_trigger_filter:
            continue
        if not _is_pending_n4_event(row):
            continue

        if _is_valid_trigger_matched_entry(row):
            append_consumed_n4_event(row)
            state = _tracking_state_from_trigger_match(
                row,
                action_run_id=action_run_id,
                source_trigger_run_id=source_trigger_run_id,
            )
            state_key = state["state_key"]
            prior = latest_tracking_state(state_key)
            terminal_ref_reopened = False
            if _is_terminal_tracking(prior):
                if not _can_reopen_terminal_tracking_from_latest_match(prior, state):
                    continue
                state = _reopen_terminal_tracking_from_latest_match(prior, state)
                terminal_ref_reopened = True
            action_eligible_required = (
                terminal_ref_reopened
                or not prior
                or str(prior.get("planned_output_event_type") or "") != "ActionEligible"
            )
            if action_eligible_required:
                _replace_tracking_update(tracking_updates, planned_update_keys, state)
                active_scope_new_state_keys.add(state_key)
                eligible_event = _build_action_event(
                    "ActionEligible",
                    state,
                    action_run_id=action_run_id,
                    source_trigger_run_id=source_trigger_run_id,
                    source_metric_run_id=source_metric_run_id,
                    consumer_name=consumer_name,
                )
                if eligible_event["event_key"] not in existing_event_keys:
                    action_events.append(eligible_event)
                    existing_event_keys.add(eligible_event["event_key"])
                active_by_key[state_key] = state
                latest_planned_by_key[state_key] = state
            else:
                merged = _merge_tracking_from_latest_match(prior, state)
                active_by_key[state_key] = merged
                latest_planned_by_key[state_key] = merged
            continue

        if _is_trigger_state_changed_inactive(row):
            append_consumed_n4_event(row)
            state_key = _tracking_state_key_from_event(row)
            prior = latest_tracking_state(state_key)
            if prior and not _is_terminal_tracking(prior):
                expired = _expire_tracking_state(prior, row)
                _replace_tracking_update(tracking_updates, planned_update_keys, expired)
                latest_planned_by_key[state_key] = expired
                active_by_key.pop(expired["state_key"], None)
            elif prior and str(prior.get("action_state") or "") == "executed":
                boundary = _record_executed_inactive_episode_boundary(prior, row)
                if boundary is not None:
                    _replace_tracking_update(tracking_updates, planned_update_keys, boundary)
                    latest_planned_by_key[state_key] = boundary
            continue

        if _is_trigger_state_changed_active(row):
            append_consumed_n4_event(row)
            state = _tracking_state_from_trigger_state_changed_active(
                row,
                action_run_id=action_run_id,
                source_trigger_run_id=source_trigger_run_id,
            )
            state_key = state["state_key"]
            prior = latest_tracking_state(state_key)
            if _is_terminal_tracking(prior):
                continue
            if prior and not _event_is_newer_or_equal(state.get("latest_n4_event_time"), prior.get("latest_n4_event_time")):
                active_by_key[state_key] = _normalize_tracking_row(prior)
                continue
            if prior:
                state = _refresh_tracking_state_from_trigger_state_changed(prior, state)
            active_by_key[state_key] = state
            latest_planned_by_key[state_key] = state
            _replace_tracking_update(tracking_updates, planned_update_keys, state)
            active_scope_new_state_keys.add(state_key)

    for row in _sort_event_rows(repair_n4_event_rows):
        if not _is_matched_trigger_state_changed_active(row):
            continue
        state = _tracking_state_from_trigger_state_changed_active(
            row,
            action_run_id=action_run_id,
            source_trigger_run_id=source_trigger_run_id,
        )
        state_key = state["state_key"]
        prior = latest_tracking_state(state_key)
        if _is_terminal_tracking(prior):
            continue
        if (
            prior
            and _is_active_tracking(prior)
            and str(prior.get("source_trigger_event_id") or "") == str(state.get("source_trigger_event_id") or "")
        ):
            active_by_key[state_key] = _normalize_tracking_row(prior)
            continue
        if prior and not _event_is_newer_or_equal(state.get("latest_n4_event_time"), prior.get("latest_n4_event_time")):
            active_by_key[state_key] = _normalize_tracking_row(prior)
            continue
        if prior:
            state = _refresh_tracking_state_from_trigger_state_changed(prior, state)
        active_by_key[state_key] = state
        latest_planned_by_key[state_key] = state
        _replace_tracking_update(tracking_updates, planned_update_keys, state)
        active_scope_new_state_keys.add(state_key)

    for row in active_tracking_rows:
        normalized = _normalize_tracking_row(row)
        state_key = normalized["state_key"]
        if state_key in latest_planned_by_key:
            if _is_active_tracking(latest_planned_by_key[state_key]):
                active_by_key[state_key] = latest_planned_by_key[state_key]
            else:
                active_by_key.pop(state_key, None)
            continue
        if _is_active_tracking(normalized):
            active_by_key.setdefault(state_key, normalized)

    active_states = [state for state in active_by_key.values() if _is_active_tracking(state)]
    action_confirmation_states = [
        state for state in active_states if _has_verified_trigger_matched_action_entry(state)
    ]
    primary_state_keys = _primary_action_state_keys_by_group(action_confirmation_states)
    for state in action_confirmation_states:
        if not _is_active_tracking(state):
            continue
        result = _select_confirming_metric(state, metric_index)
        primary_key = primary_state_keys.get(_action_ref_group_key(state))
        if primary_key and primary_key != str(state.get("state_key") or ""):
            primary_state = active_by_key.get(primary_key) or {}
            primary_result = _select_confirming_metric(primary_state, metric_index) if primary_state else {}
            if _primary_ref_has_metric_evaluation(primary_result):
                evidence_update = _superseded_tracking_evidence(state, primary_state=primary_state, result=result)
                if _pending_tracking_evidence_unchanged(state, evidence_update):
                    continue
                _replace_tracking_update(tracking_updates, planned_update_keys, evidence_update)
                continue
            if result.get("reason") == "metric_missing":
                if str(state.get("state_key") or "") in planned_update_keys:
                    continue
                evidence_update = _pending_tracking_evidence(state, result)
                if _pending_tracking_evidence_unchanged(state, evidence_update):
                    continue
                _replace_tracking_update(tracking_updates, planned_update_keys, evidence_update)
                continue
        if result["status"] == "passed":
            executed = _execute_tracking_state(state, result)
            tracking_updates.append(executed)
            planned_update_keys.add(executed["state_key"])
            executed_event = _build_action_event(
                "ActionExecuted",
                executed,
                action_run_id=action_run_id,
                source_trigger_run_id=source_trigger_run_id,
                source_metric_run_id=source_metric_run_id,
                consumer_name=consumer_name,
            )
            if executed_event["event_key"] not in existing_event_keys:
                action_events.append(executed_event)
                existing_event_keys.add(executed_event["event_key"])
            continue
        if result.get("reason") == "metric_missing" and str(state.get("state_key") or "") in planned_update_keys:
            continue
        if result.get("reason") == "metric_missing" and _should_terminalize_unconfirmable_cursor(state):
            result = _unconfirmable_cursor_no_action_result(state)
            terminalize_no_action = True
        else:
            terminalize_no_action = _should_terminalize_no_action_tracking(state, result)
        evidence_update = (
            _terminal_no_action_tracking_evidence(state, result)
            if terminalize_no_action
            else _pending_tracking_evidence(state, result)
        )
        if not terminalize_no_action and _pending_tracking_evidence_unchanged(state, evidence_update):
            continue
        _replace_tracking_update(tracking_updates, planned_update_keys, evidence_update)

    output_counter = Counter(event["event_type"] for event in action_events)
    active_scope_snapshot_artifact = _build_active_scope_snapshot_artifact(
        for_trade_date=for_trade_date or _derive_for_trade_date(active_tracking_rows, tracking_updates, n4_event_rows),
        action_run_id=action_run_id,
        source_trigger_run_id=source_trigger_run_id,
        consumer_name=consumer_name,
        active_tracking_rows=active_scope_tracking_rows if active_scope_tracking_rows is not None else active_tracking_rows,
        tracking_updates=tracking_updates,
        tracking_update_state_keys_allowed_to_enter_scope=active_scope_new_state_keys,
        active_tracking_rows_authoritative=active_scope_tracking_rows is not None,
        attention_n4_event_rows=attention_scope_events,
    )
    return {
        "action_run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "source_metric_run_id": source_metric_run_id,
        "consumer_name": consumer_name,
        "active_tracking_rows": [normalize_mapping(row) for row in active_tracking_rows],
        "action_events": action_events,
        "tracking_updates": tracking_updates,
        "consumed_n4_event_ids": consumed_n4_event_ids,
        "consumed_n4_events": consumed_n4_events,
        "active_scope_snapshot_artifact": active_scope_snapshot_artifact,
        "inbox_checkpoint_intent": {
            "consumer_name": consumer_name,
            "source_layer": "N4_trigger",
            "source_event_ids": consumed_n4_event_ids,
            "updates_n4_outbox": False,
        },
        "summary": {
            "input_event_count": sum(input_counter.values()),
            "input_event_type_counts": dict(sorted(input_counter.items())),
            "tracking_upsert_count": len(tracking_updates),
            "action_eligible_count": output_counter.get("ActionEligible", 0),
            "action_executed_count": output_counter.get("ActionExecuted", 0),
            "active_scope_snapshot_count": active_scope_snapshot_artifact["scope_count"],
            "active_scope_snapshot_empty_noop": active_scope_snapshot_artifact["empty_scope_noop"],
            "n6_output_event_types": list(N5_LIVE_TRACKING_OUTPUT_EVENTS),
        },
    }


def build_active_set_a_rebuild_from_n4_day_events(
    *,
    n4_event_rows: Sequence[Mapping[str, Any]],
    action_executed_event_rows: Sequence[Mapping[str, Any]],
    for_trade_date: str,
    action_run_id: str,
    consumer_name: str,
    current_exchange_time: str = "",
) -> dict[str, Any]:
    """Replay one trade day's N4 events into a post-close final A artifact.

    This is an artifact-only rebuild path. It does not consume N4 events and
    does not create inbox/checkpoint intent.
    """

    active_by_key: dict[str, dict[str, Any]] = {}
    input_counter: Counter[str] = Counter()
    ignored_other_trade_date_count = 0
    removed_by_tsc_false_count = 0
    action_executed_removed_ref_count = 0

    replay_rows = [
        ("n4", row)
        for row in n4_event_rows
    ] + [
        ("n5_action_executed", row)
        for row in action_executed_event_rows
    ]
    for source, row in _sort_day_replay_rows(replay_rows):
        if source == "n5_action_executed":
            for state_key, state in list(active_by_key.items()):
                if _action_executed_event_matches_state(row, state, for_trade_date):
                    active_by_key.pop(state_key, None)
                    action_executed_removed_ref_count += 1
            continue

        event_type = str(row.get("event_type") or "")
        if event_type not in N5_LIVE_TRACKING_INPUT_EVENTS:
            continue
        grain = _tracking_grain_from_event(row)
        if str(grain.get("trade_date") or "") != str(for_trade_date):
            ignored_other_trade_date_count += 1
            continue
        input_counter[event_type] += 1

        if _is_valid_trigger_matched_entry(row):
            state = _tracking_state_from_trigger_match(
                row,
                action_run_id=action_run_id,
                source_trigger_run_id=str(row.get("source_run_id") or ""),
            )
            active_by_key[state["state_key"]] = state
            continue

        if _is_trigger_state_changed_inactive(row):
            state_key = _tracking_state_key_from_event(row)
            if state_key in active_by_key:
                removed_by_tsc_false_count += 1
            active_by_key.pop(state_key, None)
            continue

        if _is_matched_trigger_state_changed_active(row):
            state = _tracking_state_from_trigger_state_changed_active(
                row,
                action_run_id=action_run_id,
                source_trigger_run_id=str(row.get("source_run_id") or ""),
            )
            prior = active_by_key.get(state["state_key"])
            if prior and not _event_is_newer_or_equal(state.get("latest_n4_event_time"), prior.get("latest_n4_event_time")):
                continue
            active_by_key[state["state_key"]] = state

    artifact = _build_active_scope_snapshot_artifact(
        for_trade_date=for_trade_date,
        action_run_id=action_run_id,
        source_trigger_run_id="post_close_final_a_rebuild_from_n4_day_events",
        consumer_name=consumer_name,
        active_tracking_rows=[],
        tracking_updates=list(active_by_key.values()),
    )
    artifact["rebuild_mode"] = "post_close_final_a_rebuild_from_n4_day_events"
    artifact["current_exchange_time"] = str(current_exchange_time or "")
    artifact["boundary"] = {
        **normalize_mapping(artifact.get("boundary") or {}),
        "n4_outbox_updated": False,
        "inbox_checkpoint_written": False,
        "db_written": False,
        "n6_touched": False,
    }
    artifact["n4_outbox_updated"] = False
    artifact["inbox_checkpoint_written"] = False
    artifact["db_written"] = False
    artifact["n6_touched"] = False
    return {
        "action_run_id": action_run_id,
        "source_trigger_run_id": "post_close_final_a_rebuild_from_n4_day_events",
        "source_metric_run_id": "",
        "consumer_name": consumer_name,
        "action_events": [],
        "tracking_updates": [],
        "consumed_n4_event_ids": [],
        "consumed_n4_events": [],
        "active_scope_snapshot_artifact": artifact,
        "inbox_checkpoint_intent": {
            "consumer_name": consumer_name,
            "source_layer": "N4_trigger",
            "source_event_ids": [],
            "updates_n4_outbox": False,
        },
        "summary": {
            "input_event_count": sum(input_counter.values()),
            "input_event_type_counts": dict(sorted(input_counter.items())),
            "active_ref_count": artifact["active_tracking_ref_count"],
            "scope_count": artifact["scope_count"],
            "removed_by_tsc_false_count": removed_by_tsc_false_count,
            "action_executed_removed_ref_count": action_executed_removed_ref_count,
            "ignored_other_trade_date_count": ignored_other_trade_date_count,
        },
    }


def _sort_event_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _dt_sort_key(row.get("event_time")),
            int(row.get("outbox_id") or 0),
            str(row.get("event_id") or ""),
        ),
    )


def _sort_day_replay_event_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _dt_sort_key(row.get("event_time")),
            str(row.get("source_run_id") or ""),
            str(row.get("event_id") or ""),
        ),
    )


def _sort_day_replay_rows(rows: Sequence[tuple[str, Mapping[str, Any]]]) -> list[tuple[str, Mapping[str, Any]]]:
    source_order = {"n4": 0, "n5_action_executed": 1}
    return sorted(
        rows,
        key=lambda item: (
            _dt_sort_key(item[1].get("event_time")),
            source_order.get(item[0], 9),
            str(item[1].get("source_run_id") or ""),
            str(item[1].get("event_id") or ""),
        ),
    )


def _dt_sort_key(value: Any) -> datetime:
    parsed = datetime_or_none(value)
    if parsed is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return normalize_mapping(row.get("payload_json") or {})


def _value(row: Mapping[str, Any], payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _bool_value(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "1", "yes", "y"}:
        return True
    if text in {"false", "f", "0", "no", "n"}:
        return False
    return default


def _tracking_grain_from_event(row: Mapping[str, Any]) -> dict[str, str]:
    payload = _payload(row)
    signal_type = str(_value(row, payload, "signal_type") or "")
    direction = str(_value(row, payload, "direction") or "")
    if not direction:
        direction = "buy" if signal_type == "B_BUY" else "sell" if signal_type == "S_SELL" else ""
    return {
        "trade_date": str(_value(row, payload, "trade_date", "for_trade_date") or ""),
        "asset_kind": str(_value(row, payload, "asset_kind") or ""),
        "identity_key": str(_value(row, payload, "identity_key") or ""),
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": str(_value(row, payload, "condition_key", "original_condition_key") or ""),
    }


def _tracking_state_key_from_event(row: Mapping[str, Any]) -> str:
    grain = _tracking_grain_from_event(row)
    return build_action_tracking_state_key(**grain)


def _is_valid_trigger_matched_entry(row: Mapping[str, Any]) -> bool:
    if str(row.get("event_type") or "") != "TriggerMatched":
        return False
    payload = _payload(row)
    trigger_live = _bool_value(_value(row, payload, "trigger_live"), default=True)
    current_status = str(_value(row, payload, "current_status") or "matched")
    grain = _tracking_grain_from_event(row)
    return (
        trigger_live
        and current_status == "matched"
        and grain["signal_type"] in CANONICAL_RUNTIME_SIGNAL_TYPES
        and all(grain[key] for key in ("trade_date", "asset_kind", "identity_key", "direction", "condition_key"))
    )


def _is_trigger_state_changed_inactive(row: Mapping[str, Any]) -> bool:
    if str(row.get("event_type") or "") != "TriggerStateChanged":
        return False
    payload = _payload(row)
    return not _bool_value(_value(row, payload, "trigger_live"), default=True)


def _is_trigger_state_changed_active(row: Mapping[str, Any]) -> bool:
    if str(row.get("event_type") or "") != "TriggerStateChanged":
        return False
    payload = _payload(row)
    grain = _tracking_grain_from_event(row)
    return (
        _bool_value(_value(row, payload, "trigger_live"), default=True)
        and grain["signal_type"] in CANONICAL_RUNTIME_SIGNAL_TYPES
        and all(grain[key] for key in ("trade_date", "asset_kind", "identity_key", "direction", "condition_key"))
    )


def _is_matched_trigger_state_changed_active(row: Mapping[str, Any]) -> bool:
    if not _is_trigger_state_changed_active(row):
        return False
    payload = _payload(row)
    return str(_value(row, payload, "current_status") or "matched") == "matched"


def _action_executed_event_matches_state(
    row: Mapping[str, Any],
    state: Mapping[str, Any],
    for_trade_date: str,
) -> bool:
    if str(row.get("source_layer") or "") != N5_SOURCE_LAYER:
        return False
    if str(row.get("event_type") or "") != "ActionExecuted":
        return False
    payload = _payload(row)
    grain = _tracking_grain_from_event(row)
    if str(grain.get("trade_date") or "") != str(for_trade_date):
        return False
    for key in ("asset_kind", "identity_key", "direction", "signal_type", "condition_key"):
        if str(grain.get(key) or "") != str(state.get(key) or ""):
            return False
    executed_dt = datetime_or_none(row.get("event_time"))
    trigger_dt = datetime_or_none(state.get("latest_n4_event_time"))
    if executed_dt is not None and trigger_dt is not None and executed_dt < trigger_dt:
        return False
    return True


def _is_pending_n4_event(row: Mapping[str, Any]) -> bool:
    return str(row.get("status") or "") == "pending"


def _tracking_state_from_trigger_match(
    row: Mapping[str, Any],
    *,
    action_run_id: str,
    source_trigger_run_id: str,
) -> dict[str, Any]:
    payload = _payload(row)
    grain = _tracking_grain_from_event(row)
    state_key = build_action_tracking_state_key(**grain)
    trigger_period, primary_trigger_period, trigger_periods = _canonical_trigger_period_payload_fields(
        grain,
        payload,
    )
    raw_json = {
        "action_run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "source_n4_payload": payload,
        "action_entry_trigger_price": _value(row, payload, "trigger_price"),
        "n4_trigger_mark_candidate_ignored": _value(row, payload, "trigger_mark_candidate"),
        "action_eligible_entry_allowed": True,
        "action_confirmation_entry_verified": True,
        "action_entry_trigger_matched_ref": _trigger_event_ref(
            row,
            payload,
            event_type="TriggerMatched",
        ),
    }
    return {
        "run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "source_trigger_state_id": _value(row, payload, "trigger_state_id", "source_trigger_state_id"),
        "source_trigger_event_id": str(row.get("event_id") or ""),
        "source_trigger_event_type": "TriggerMatched",
        "source_trigger_match_id": _value(row, payload, "trigger_match_id", "source_trigger_match_id"),
        "trade_date": grain["trade_date"],
        "state_key": state_key,
        "asset_kind": grain["asset_kind"],
        "identity_key": grain["identity_key"],
        "direction": grain["direction"],
        "signal_type": grain["signal_type"],
        "condition_key": grain["condition_key"],
        "trigger_live": True,
        "current_status": "matched",
        "trigger_period": trigger_period,
        "primary_trigger_period": primary_trigger_period,
        "all_trigger_periods": trigger_periods,
        "triggered_periods": ["30m"] if _is_hint_condition_key(grain["condition_key"]) else trigger_periods,
        "trigger_price": _value(row, payload, "trigger_price"),
        "projection_30m_flag": _bool_value(_value(row, payload, "projection_30m_flag"), default=False),
        "projection_30m_type": _value(row, payload, "projection_30m_type"),
        "trigger_mark_candidate": _value(row, payload, "trigger_mark_candidate"),
        "latest_n4_event_id": str(row.get("event_id") or ""),
        "latest_n4_event_type": "TriggerMatched",
        "latest_n4_event_time": row.get("event_time"),
        "action_state": "eligible",
        "confirmation_status": "pending",
        "tracking_status": "tracking",
        "planned_output_event_type": "ActionEligible",
        "expired_reason": None,
        "expired_at": None,
        "tracking_until": None,
        "last_checked_minute_label": None,
        "raw_json": raw_json,
    }


def _tracking_state_from_trigger_state_changed_active(
    row: Mapping[str, Any],
    *,
    action_run_id: str,
    source_trigger_run_id: str,
) -> dict[str, Any]:
    payload = _payload(row)
    grain = _tracking_grain_from_event(row)
    state_key = build_action_tracking_state_key(**grain)
    trigger_period, primary_trigger_period, trigger_periods = _canonical_trigger_period_payload_fields(
        grain,
        payload,
    )
    raw_json = {
        "action_run_id": action_run_id,
        "source_trigger_run_id": str(row.get("source_run_id") or source_trigger_run_id),
        "source_n4_payload": payload,
        "n4_trigger_mark_candidate_ignored": _value(row, payload, "trigger_mark_candidate"),
        "action_eligible_entry_allowed": False,
        "action_confirmation_entry_verified": False,
        "latest_trigger_state_changed_ref": _trigger_event_ref(
            row,
            payload,
            event_type="TriggerStateChanged",
        ),
    }
    return {
        "run_id": action_run_id,
        "source_trigger_run_id": str(row.get("source_run_id") or source_trigger_run_id),
        "source_trigger_state_id": _value(row, payload, "trigger_state_id", "source_trigger_state_id"),
        "source_trigger_event_id": str(row.get("event_id") or ""),
        "source_trigger_event_type": "TriggerStateChanged",
        "source_trigger_match_id": _value(row, payload, "trigger_match_id", "source_trigger_match_id"),
        "trade_date": grain["trade_date"],
        "state_key": state_key,
        "asset_kind": grain["asset_kind"],
        "identity_key": grain["identity_key"],
        "direction": grain["direction"],
        "signal_type": grain["signal_type"],
        "condition_key": grain["condition_key"],
        "trigger_live": True,
        "current_status": str(_value(row, payload, "current_status") or "matched"),
        "trigger_period": trigger_period,
        "primary_trigger_period": primary_trigger_period,
        "all_trigger_periods": trigger_periods,
        "triggered_periods": ["30m"] if _is_hint_condition_key(grain["condition_key"]) else trigger_periods,
        "trigger_price": _value(row, payload, "trigger_price"),
        "projection_30m_flag": _bool_value(_value(row, payload, "projection_30m_flag"), default=False),
        "projection_30m_type": _value(row, payload, "projection_30m_type"),
        "trigger_mark_candidate": _value(row, payload, "trigger_mark_candidate"),
        "latest_n4_event_id": str(row.get("event_id") or ""),
        "latest_n4_event_type": "TriggerStateChanged",
        "latest_n4_event_time": row.get("event_time"),
        "action_state": "eligible",
        "confirmation_status": "pending",
        "tracking_status": "tracking",
        "planned_output_event_type": None,
        "expired_reason": None,
        "expired_at": None,
        "tracking_until": None,
        "last_checked_minute_label": None,
        "raw_json": raw_json,
    }


def _trigger_event_ref(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    event_type: str,
) -> dict[str, Any]:
    return {
        "source_trigger_event_id": str(row.get("event_id") or ""),
        "source_trigger_event_type": event_type,
        "source_trigger_event_time": row.get("event_time"),
        "source_trigger_run_id": str(row.get("source_run_id") or ""),
        "source_trigger_state_id": _value(row, payload, "trigger_state_id", "source_trigger_state_id"),
        "source_trigger_match_id": _value(row, payload, "trigger_match_id", "source_trigger_match_id"),
        "source_n4_payload": dict(payload),
    }


def _action_entry_trigger_matched_ref(state: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_tracking_row(state)
    raw_json = normalize_mapping(normalized.get("raw_json") or {})
    stored_ref = normalize_mapping(raw_json.get("action_entry_trigger_matched_ref") or {})
    if (
        stored_ref.get("source_trigger_event_type") == "TriggerMatched"
        and str(stored_ref.get("source_trigger_event_id") or "")
    ):
        return stored_ref
    if (
        str(normalized.get("source_trigger_event_type") or normalized.get("latest_n4_event_type") or "")
        == "TriggerMatched"
        and str(normalized.get("source_trigger_event_id") or normalized.get("latest_n4_event_id") or "")
    ):
        source_payload = normalize_mapping(raw_json.get("source_n4_payload") or {})
        return {
            "source_trigger_event_id": str(
                normalized.get("source_trigger_event_id") or normalized.get("latest_n4_event_id") or ""
            ),
            "source_trigger_event_type": "TriggerMatched",
            "source_trigger_event_time": normalized.get("latest_n4_event_time"),
            "source_trigger_run_id": str(normalized.get("source_trigger_run_id") or ""),
            "source_trigger_state_id": normalized.get("source_trigger_state_id"),
            "source_trigger_match_id": normalized.get("source_trigger_match_id"),
            "source_n4_payload": source_payload,
        }
    return {}


def _has_verified_trigger_matched_action_entry(state: Mapping[str, Any]) -> bool:
    return bool(_action_entry_trigger_matched_ref(state))


def _refresh_tracking_state_from_trigger_state_changed(
    prior: Mapping[str, Any],
    latest: Mapping[str, Any],
) -> dict[str, Any]:
    refreshed = dict(_normalize_tracking_row(prior))
    normalized_latest = _normalize_tracking_row(latest)
    for key in (
        "run_id",
        "source_trigger_run_id",
        "source_trigger_state_id",
        "source_trigger_event_id",
        "source_trigger_event_type",
        "source_trigger_match_id",
        "trigger_live",
        "current_status",
        "primary_trigger_period",
        "all_trigger_periods",
        "trigger_price",
        "projection_30m_flag",
        "projection_30m_type",
        "trigger_mark_candidate",
        "latest_n4_event_id",
        "latest_n4_event_type",
        "latest_n4_event_time",
    ):
        refreshed[key] = normalized_latest.get(key)

    prior_raw_json = normalize_mapping(refreshed.get("raw_json") or {})
    latest_raw_json = normalize_mapping(normalized_latest.get("raw_json") or {})
    entry_ref = _action_entry_trigger_matched_ref(prior)
    raw_json = {**prior_raw_json, **latest_raw_json}
    raw_json["action_eligible_entry_allowed"] = False
    raw_json["action_confirmation_entry_verified"] = bool(entry_ref)
    if entry_ref:
        raw_json["action_entry_trigger_matched_ref"] = entry_ref
    refreshed["raw_json"] = raw_json
    return refreshed


def _triggered_periods(payload: Mapping[str, Any]) -> list[Any]:
    periods = payload.get("all_trigger_periods")
    if not periods:
        periods = payload.get("triggered_periods")
    if not periods:
        return []
    if isinstance(periods, list):
        return list(periods)
    if isinstance(periods, tuple):
        return list(periods)
    return [periods]


def _canonical_trigger_period_fields(
    state: Mapping[str, Any],
    source_n4_payload: Mapping[str, Any] | None = None,
) -> tuple[str | None, list[Any]]:
    source_payload = normalize_mapping(source_n4_payload or {})
    condition_key = str(state.get("condition_key") or source_payload.get("condition_key") or "")
    if _is_hint_condition_key(condition_key):
        return None, []
    periods = _triggered_periods(state) or _triggered_periods(source_payload)
    primary = str(
        state.get("primary_trigger_period")
        or state.get("trigger_period")
        or source_payload.get("primary_trigger_period")
        or source_payload.get("trigger_period")
        or ""
    ).strip()
    if not primary and periods:
        primary = str(periods[0] or "").strip()
    if not periods and primary:
        periods = [primary]
    return primary or None, periods


def _canonical_trigger_period_payload_fields(
    state: Mapping[str, Any],
    source_n4_payload: Mapping[str, Any] | None = None,
) -> tuple[str | None, str | None, list[Any]]:
    source_payload = normalize_mapping(source_n4_payload or {})
    condition_key = str(state.get("condition_key") or source_payload.get("condition_key") or "")
    if _is_hint_condition_key(condition_key):
        return "30m", None, []
    primary_trigger_period, trigger_periods = _canonical_trigger_period_fields(state, source_payload)
    return primary_trigger_period, primary_trigger_period, trigger_periods


def _event_is_newer_or_equal(candidate_time: Any, prior_time: Any) -> bool:
    candidate_dt = datetime_or_none(candidate_time)
    prior_dt = datetime_or_none(prior_time)
    if candidate_dt is None or prior_dt is None:
        return True
    return candidate_dt >= prior_dt


def _normalize_tracking_row(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_mapping(row)
    raw_json = normalize_mapping(normalized.get("raw_json") or {})
    for key in (
        "source_n4_payload",
        "action_entry_trigger_matched_ref",
        "latest_trigger_state_changed_ref",
    ):
        top_level_value = normalized.get(key)
        if key not in raw_json and isinstance(top_level_value, Mapping):
            raw_json[key] = normalize_mapping(top_level_value)
    source_n4_payload = normalize_mapping(raw_json.get("source_n4_payload") or {})
    trigger_period, primary_trigger_period, trigger_periods = _canonical_trigger_period_payload_fields(
        normalized,
        source_n4_payload,
    )
    if _is_hint_condition_key(normalized.get("condition_key")):
        normalized["trigger_period"] = trigger_period
        normalized["primary_trigger_period"] = None
        normalized["all_trigger_periods"] = []
        normalized["triggered_periods"] = ["30m"]
    elif primary_trigger_period:
        normalized["primary_trigger_period"] = primary_trigger_period
        normalized["trigger_period"] = primary_trigger_period
    if trigger_periods:
        normalized["all_trigger_periods"] = trigger_periods
        normalized["triggered_periods"] = trigger_periods
    if not normalized.get("state_key"):
        normalized["state_key"] = build_action_tracking_state_key(
            trade_date=str(normalized.get("trade_date") or ""),
            asset_kind=str(normalized.get("asset_kind") or ""),
            identity_key=str(normalized.get("identity_key") or ""),
            direction=str(normalized.get("direction") or ""),
            signal_type=str(normalized.get("signal_type") or ""),
            condition_key=str(normalized.get("condition_key") or ""),
        )
    normalized.setdefault("trigger_live", True)
    normalized.setdefault("action_state", "eligible")
    normalized.setdefault("confirmation_status", "pending")
    normalized.setdefault("tracking_status", "tracking")
    normalized["raw_json"] = raw_json
    return normalized


def _find_tracking_row(rows: Sequence[Mapping[str, Any]], state_key: str) -> dict[str, Any] | None:
    for row in rows:
        normalized = _normalize_tracking_row(row)
        if normalized.get("state_key") == state_key:
            return normalized
    return None


def _is_terminal_tracking(row: Mapping[str, Any] | None) -> bool:
    return bool(row) and str(row.get("action_state") or "") in TERMINAL_TRACKING_STATES


def _can_reopen_terminal_tracking_from_latest_match(
    prior: Mapping[str, Any] | None,
    latest: Mapping[str, Any],
) -> bool:
    prior_action_state = str((prior or {}).get("action_state") or "")
    if not prior or prior_action_state not in {"expired", "executed"}:
        return False
    if str(latest.get("source_trigger_event_type") or "") != "TriggerMatched":
        return False
    if not _bool_value(latest.get("trigger_live"), default=False):
        return False
    if str(latest.get("current_status") or "") != "matched":
        return False
    latest_event_id = str(latest.get("source_trigger_event_id") or "")
    prior_event_id = str(prior.get("source_trigger_event_id") or prior.get("latest_n4_event_id") or "")
    if not latest_event_id or latest_event_id == prior_event_id:
        return False
    latest_event_time = datetime_or_none(latest.get("latest_n4_event_time"))
    prior_event_time = datetime_or_none(prior.get("latest_n4_event_time"))
    if latest_event_time is None:
        return False
    if prior_event_time is not None and latest_event_time < prior_event_time:
        return False
    if prior_action_state == "expired":
        return True
    boundary = normalize_mapping(
        normalize_mapping(prior.get("raw_json") or {}).get("terminal_episode_inactive_boundary")
        or {}
    )
    if str(boundary.get("source_trigger_event_type") or "") != "TriggerStateChanged":
        return False
    if _bool_value(boundary.get("trigger_live"), default=True):
        return False
    boundary_event_id = str(boundary.get("source_trigger_event_id") or "")
    closed_source_trigger_event_id = str(
        boundary.get("closed_source_trigger_event_id") or ""
    )
    boundary_event_time = datetime_or_none(boundary.get("source_trigger_event_time"))
    if (
        not boundary_event_id
        or closed_source_trigger_event_id != prior_event_id
        or boundary_event_time is None
    ):
        return False
    return latest_event_time >= boundary_event_time


def _reopen_terminal_tracking_from_latest_match(
    prior: Mapping[str, Any],
    latest: Mapping[str, Any],
) -> dict[str, Any]:
    reopened = dict(_normalize_tracking_row(latest))
    raw_json = normalize_mapping(reopened.get("raw_json") or {})
    prior_raw_json = normalize_mapping(prior.get("raw_json") or {})
    inactive_boundary = normalize_mapping(
        prior_raw_json.get("terminal_episode_inactive_boundary") or {}
    )
    raw_json["terminal_ref_reopen_allowed"] = True
    if inactive_boundary:
        raw_json["terminal_episode_inactive_boundary"] = inactive_boundary
    raw_json["terminal_ref_reopen_trace"] = {
        "prior_action_state": str(prior.get("action_state") or ""),
        "prior_source_trigger_event_id": str(
            prior.get("source_trigger_event_id") or prior.get("latest_n4_event_id") or ""
        ),
        "prior_latest_n4_event_time": prior.get("latest_n4_event_time"),
        "inactive_boundary_event_id": str(
            inactive_boundary.get("source_trigger_event_id") or ""
        ),
        "inactive_boundary_event_time": inactive_boundary.get("source_trigger_event_time"),
        "reopened_by_source_trigger_event_id": str(reopened.get("source_trigger_event_id") or ""),
        "reopened_by_latest_n4_event_time": reopened.get("latest_n4_event_time"),
    }
    reopened.update(
        {
            "action_state": "eligible",
            "confirmation_status": "pending",
            "tracking_status": "tracking",
            "planned_output_event_type": "ActionEligible",
            "expired_reason": None,
            "expired_at": None,
            "tracking_until": None,
            "last_checked_minute_label": None,
            "raw_json": raw_json,
        }
    )
    return reopened


def _record_executed_inactive_episode_boundary(
    prior: Mapping[str, Any],
    event_row: Mapping[str, Any],
) -> dict[str, Any] | None:
    event_time = datetime_or_none(event_row.get("event_time"))
    prior_event_time = datetime_or_none(prior.get("latest_n4_event_time"))
    if event_time is None or (prior_event_time is not None and event_time < prior_event_time):
        return None
    payload = _payload(event_row)
    boundary = dict(_normalize_tracking_row(prior))
    boundary.update(
        {
            "trigger_live": False,
            "current_status": str(_value(event_row, payload, "current_status") or "inactive"),
            "latest_n4_event_id": str(event_row.get("event_id") or ""),
            "latest_n4_event_type": "TriggerStateChanged",
            "latest_n4_event_time": event_row.get("event_time"),
        }
    )
    raw_json = normalize_mapping(boundary.get("raw_json") or {})
    raw_json["terminal_episode_inactive_boundary"] = {
        "source_trigger_event_id": str(event_row.get("event_id") or ""),
        "source_trigger_event_type": "TriggerStateChanged",
        "source_trigger_event_time": event_row.get("event_time"),
        "closed_source_trigger_event_id": str(
            prior.get("source_trigger_event_id") or prior.get("latest_n4_event_id") or ""
        ),
        "trigger_live": False,
        "current_status": str(_value(event_row, payload, "current_status") or "inactive"),
    }
    raw_json["trigger_state_changed_payload"] = payload
    boundary["raw_json"] = raw_json
    return boundary


def _is_active_tracking(row: Mapping[str, Any]) -> bool:
    return (
        str(row.get("action_state") or "") == "eligible"
        and str(row.get("tracking_status") or "") == "tracking"
        and _bool_value(row.get("trigger_live"), default=False)
    )


def _merge_tracking_from_latest_match(prior: Mapping[str, Any], latest: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(prior)
    for key in (
        "source_trigger_event_id",
        "source_trigger_event_type",
        "source_trigger_match_id",
        "trigger_live",
        "current_status",
        "primary_trigger_period",
        "all_trigger_periods",
        "trigger_mark_candidate",
        "latest_n4_event_id",
        "latest_n4_event_type",
        "latest_n4_event_time",
    ):
        merged[key] = latest.get(key)
    merged["raw_json"] = {**normalize_mapping(prior.get("raw_json") or {}), **normalize_mapping(latest.get("raw_json") or {})}
    return merged


def _append_tracking_update(updates: list[dict[str, Any]], update_keys: set[str], row: Mapping[str, Any]) -> None:
    normalized = _normalize_tracking_row(row)
    updates.append(normalized)
    update_keys.add(normalized["state_key"])


def _replace_tracking_update(updates: list[dict[str, Any]], update_keys: set[str], row: Mapping[str, Any]) -> None:
    normalized = _normalize_tracking_row(row)
    for index, existing in enumerate(updates):
        if str(existing.get("state_key") or "") == normalized["state_key"]:
            updates[index] = normalized
            update_keys.add(normalized["state_key"])
            return
    updates.append(normalized)
    update_keys.add(normalized["state_key"])


def _expire_tracking_state(prior: Mapping[str, Any], event_row: Mapping[str, Any]) -> dict[str, Any]:
    payload = _payload(event_row)
    rollback_before = normalize_mapping(_normalize_tracking_row(prior))
    expired = dict(_normalize_tracking_row(prior))
    expired.update(
        {
            "trigger_live": False,
            "current_status": str(_value(event_row, payload, "current_status") or "inactive"),
            "latest_n4_event_id": str(event_row.get("event_id") or ""),
            "latest_n4_event_type": "TriggerStateChanged",
            "latest_n4_event_time": event_row.get("event_time"),
            "action_state": "expired",
            "confirmation_status": "expired",
            "tracking_status": "expired",
            "planned_output_event_type": None,
            "expired_reason": "trigger_live_false",
            "expired_at": event_row.get("event_time"),
        }
    )
    raw_json = normalize_mapping(expired.get("raw_json") or {})
    raw_json["rollback_before_tracking_state"] = rollback_before
    raw_json["trigger_state_changed_payload"] = payload
    expired["raw_json"] = raw_json
    return expired


def _index_metric_rows(
    metric_rows: Sequence[Mapping[str, Any]],
    *,
    source_metric_run_id: str,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    allowed_run_ids = {
        part.strip()
        for part in str(source_metric_run_id or "").split(",")
        if part.strip()
    }
    indexed: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in metric_rows:
        normalized = _normalize_metric_row_for_live_tracking(row)
        projection_run_id = str(normalized.get("projection_run_id") or normalized.get("source_metric_run_id") or "")
        if allowed_run_ids and projection_run_id not in allowed_run_ids:
            continue
        asset_kind = str(normalized.get("asset_kind") or "")
        identity_key = str(normalized.get("identity_key") or "")
        if not asset_kind or not identity_key:
            continue
        indexed.setdefault((asset_kind, identity_key), []).append(normalized)
    for key, rows in indexed.items():
        indexed[key] = sorted(rows, key=lambda row: _dt_sort_key(row.get("metric_time")))
    return indexed


def _select_confirming_metric(
    state: Mapping[str, Any],
    metric_index: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    rows = metric_index.get((str(state.get("asset_kind") or ""), str(state.get("identity_key") or "")), [])
    if not rows:
        return {"status": "pending", "reason": "metric_missing"}
    trigger_dt = datetime_or_none(state.get("latest_n4_event_time"))
    latest_evaluation: dict[str, Any] | None = None
    latest_fact: dict[str, Any] | None = None
    cursor_state = _normalize_tracking_row(state)
    for row in rows:
        fact = normalize_mapping(row)
        if not _metric_matches_state(fact, cursor_state):
            continue
        metric_dt = datetime_or_none(fact.get("metric_time"))
        if trigger_dt is not None and metric_dt is not None and metric_dt < trigger_dt:
            metric_id = str(fact.get("action_confirmation_metric_id") or fact.get("metric_id") or "")
            latest_evaluation = _blocked_metric_guard_evaluation(fact, metric_id, "metric_before_trigger_time")
            latest_fact = fact
            continue
        metric_id = str(fact.get("action_confirmation_metric_id") or fact.get("metric_id") or "")
        guard = _n3t_action_execution_metric_guard(fact)
        if guard["status"] != "valid":
            latest_evaluation = _blocked_metric_guard_evaluation(fact, metric_id, guard["reason"])
            latest_fact = fact
            cursor_state = _pending_tracking_evidence(
                cursor_state,
                _pending_result_from_metric_evaluation(latest_evaluation, latest_fact),
            )
            continue
        cursor_guard_reason = _metric_cursor_guard_reason(fact, cursor_state)
        if cursor_guard_reason:
            latest_evaluation = _blocked_metric_guard_evaluation(fact, metric_id, cursor_guard_reason)
            latest_fact = fact
            if cursor_guard_reason == "metric_after_next_unchecked_minute_label":
                break
            continue
        evaluation_fact = _n3t_closed_c1_metric_for_evaluation(fact)
        evaluation = evaluate_action_confirmation_metric(
            signal_type=str(cursor_state.get("signal_type") or ""),
            source_action_confirmation_metric_id=metric_id,
            metric_fact=evaluation_fact,
            trigger_time=evaluation_fact.get("metric_time"),
            metric_required=True,
        )
        evaluation["metric_evaluation_minute_label"] = _metric_evaluation_minute_label(evaluation_fact)
        latest_evaluation = evaluation
        latest_fact = evaluation_fact
        if _final_confirmation_passed(str(cursor_state.get("signal_type") or ""), evaluation):
            action_mark = derive_final_action_mark(signal_type=str(cursor_state.get("signal_type") or ""), evaluation=evaluation)
            return {
                "status": "passed",
                "metric_fact": evaluation_fact,
                "metric_evaluation": evaluation,
                "action_mark": action_mark["action_mark"],
                "action_mark_reason": action_mark["action_mark_reason"],
            }
        cursor_state = _pending_tracking_evidence(
            cursor_state,
            _pending_result_from_metric_evaluation(latest_evaluation, latest_fact),
        )
    if latest_evaluation is not None:
        return {
            "status": "pending",
            "reason": latest_evaluation.get("blocked_reason") or latest_evaluation.get("metric_context_status") or "metric_not_passed",
            "metric_fact": latest_fact,
            "metric_evaluation": latest_evaluation,
        }
    return {"status": "pending", "reason": "metric_not_in_scope"}


def _pending_result_from_metric_evaluation(
    evaluation: Mapping[str, Any],
    metric_fact: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "status": "pending",
        "reason": evaluation.get("blocked_reason") or evaluation.get("metric_context_status") or "metric_not_passed",
        "metric_fact": metric_fact or {},
        "metric_evaluation": evaluation,
    }


def _metric_evaluation_minute_label(metric: Mapping[str, Any]) -> str:
    return (
        _metric_minute_label_from_projection_run_id(
            metric.get("projection_run_id") or metric.get("source_metric_run_id")
        )
        or _minute_label_text(metric.get("metric_minute_label"))
        or _minute_label_text(metric.get("metric_evaluation_minute_label"))
        or _minute_label_text(metric.get("metric_time"))
    )


def _metric_minute_label_from_projection_run_id(projection_run_id: Any) -> str:
    match = re.search(r"(?:^|_)until_([0-2][0-9][0-5][0-9])(?:_|$)", str(projection_run_id or ""))
    return _minute_label_text(match.group(1)) if match else ""


def _metric_cursor_guard_reason(metric: Mapping[str, Any], state: Mapping[str, Any]) -> str:
    metric_label = _metric_evaluation_minute_label(metric)
    expected_label = _expected_next_unchecked_minute_label(state)
    if not metric_label or not expected_label:
        return ""
    comparison = _compare_canonical_minute_label(
        for_trade_date=state.get("trade_date"),
        left=metric_label,
        right=expected_label,
    )
    if comparison < 0:
        if _metric_matches_latest_metric_status(metric, state, metric_label=metric_label):
            return ""
        return "metric_before_next_unchecked_minute_label"
    if comparison > 0:
        return "metric_after_next_unchecked_minute_label"
    return ""


def _metric_matches_latest_metric_status(
    metric: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    metric_label: str,
) -> bool:
    raw_json = normalize_mapping(state.get("raw_json") or {})
    latest = normalize_mapping(raw_json.get("latest_metric_status") or {})
    latest_metric_id = str(latest.get("source_action_confirmation_metric_id") or "")
    metric_id = str(metric.get("action_confirmation_metric_id") or metric.get("metric_id") or "")
    if latest_metric_id and metric_id and latest_metric_id != metric_id:
        return False
    latest_label = _minute_label_text(latest.get("metric_evaluation_minute_label")) or _minute_label_text(
        latest.get("metric_minute_label")
    )
    return bool(latest_label and metric_label and latest_label == metric_label)


def _expected_next_unchecked_minute_label(state: Mapping[str, Any]) -> str:
    raw_json = normalize_mapping(state.get("raw_json") or {})
    explicit_label = _minute_label_text(raw_json.get("next_unchecked_minute_label"))
    if explicit_label:
        return explicit_label
    return _next_unchecked_minute_label(
        for_trade_date=str(state.get("trade_date") or ""),
        first_confirmation_minute_label=_first_confirmation_minute_label(
            state.get("latest_n4_event_time") or state.get("trigger_time")
        ),
        last_checked_minute_label=_minute_label_text(state.get("last_checked_minute_label")),
    )


def _compare_canonical_minute_label(*, for_trade_date: Any, left: Any, right: Any) -> int:
    left_label = _minute_label_text(left)
    right_label = _minute_label_text(right)
    if not left_label or not right_label:
        return 0
    trade_date = str(for_trade_date or "")
    labels = canonical_ashare_1m_labels(trade_date) if re.fullmatch(r"\d{8}", trade_date) else []
    if left_label in labels and right_label in labels:
        return (labels.index(left_label) > labels.index(right_label)) - (
            labels.index(left_label) < labels.index(right_label)
        )
    return (left_label > right_label) - (left_label < right_label)


def _n3t_action_execution_metric_guard(metric: Mapping[str, Any]) -> dict[str, str]:
    source_basis = _metric_lineage_value(metric, "source_basis")
    if _looks_like_non_n5_final_proof(metric):
        return {"status": "blocked", "reason": N3P_NOT_ACTION_PROOF_REASON}
    if source_basis != REQUIRED_N3T_SOURCE_BASIS:
        return {"status": "blocked", "reason": N3T_METRIC_REQUIRED_REASON}
    return {"status": "valid", "reason": ""}


def _looks_like_non_n5_final_proof(metric: Mapping[str, Any]) -> bool:
    if _bool_value(_metric_lineage_value(metric, "not_n5_final_proof"), default=False):
        return True
    metric_role = str(_metric_lineage_value(metric, "metric_role") or "")
    if metric_role in {"trigger_proof", "projection_trigger_proof", "hint_trigger_proof"}:
        return True
    proof_consumer = str(_metric_lineage_value(metric, "proof_consumer") or "")
    if proof_consumer and proof_consumer != "N5":
        return True
    source_mode = str(_metric_lineage_value(metric, "source_mode") or "")
    if source_mode.startswith("b1_") or source_mode.startswith("n3p_"):
        return True
    projection_run_id = str(metric.get("projection_run_id") or metric.get("source_metric_run_id") or "")
    return projection_run_id.startswith("realtime_action_confirmation_metric_")


def _metric_lineage_value(metric: Mapping[str, Any], key: str) -> Any:
    for source in (
        metric,
        normalize_mapping(metric.get("raw_json") or {}),
        normalize_mapping(metric.get("trace_json") or {}),
    ):
        value = source.get(key)
        if value is not None and value != "":
            return value
    return None


def _normalize_metric_row_for_live_tracking(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_mapping(row)
    n3t_metric_id = normalized.get("n3t_action_confirmation_metric_id")
    if not normalized.get("action_confirmation_metric_id") and n3t_metric_id:
        normalized["action_confirmation_metric_id"] = n3t_metric_id
    return normalized


def _n3t_closed_c1_metric_for_evaluation(metric: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_metric_row_for_live_tracking(metric)
    normalized["metric_evaluation_minute_label"] = _metric_evaluation_minute_label(normalized)
    if _metric_lineage_value(normalized, "source_basis") != REQUIRED_N3T_SOURCE_BASIS:
        return normalized
    if _metric_lineage_value(normalized, "virtual_amount_policy_version"):
        return normalized

    raw_json = normalize_mapping(normalized.get("raw_json") or {})
    trace_json = normalize_mapping(normalized.get("trace_json") or {})
    raw_json["virtual_amount_policy_version"] = CALIBRATED_METRIC_POLICY_VERSION
    trace_json[N3T_POLICY_ALIGNMENT_TRACE_KEY] = {
        "status": "valid",
        "source_basis": REQUIRED_N3T_SOURCE_BASIS,
        "metric_role": _metric_lineage_value(normalized, "metric_role"),
        "proof_consumer": _metric_lineage_value(normalized, "proof_consumer"),
        "reason": "N3T closed C1 metric is the N5 action-confirmation policy",
    }
    normalized["raw_json"] = raw_json
    normalized["trace_json"] = trace_json
    return normalized


def _blocked_metric_guard_evaluation(metric: Mapping[str, Any], metric_id: str, reason: str) -> dict[str, Any]:
    return {
        "source_action_confirmation_metric_id": metric_id or None,
        "metric_required": True,
        "metric_fact_available": bool(metric),
        "metric_context_status": "policy_invalid",
        "metric_ready": _bool_value(metric.get("metric_ready"), default=False),
        "metric_quality_status": metric.get("metric_quality_status"),
        "metric_time": metric.get("metric_time"),
        "metric_minute_label": metric.get("metric_minute_label"),
        "metric_evaluation_minute_label": _metric_evaluation_minute_label(metric),
        "current_price": metric.get("current_price"),
        "current_30m_virtual_amount": metric.get("current_30m_virtual_amount"),
        "previous_day_same_window_amount": metric.get("previous_day_same_window_amount"),
        "metric_policy_status": "invalid",
        "selected_flags": {},
        "action_execution_required_flags": {},
        "all_period_confirmation_pass": False,
        "blocked_reason": reason,
        "metric_lineage_status": "metric_guard_failed",
        "projection_run_id": metric.get("projection_run_id"),
        "source_basis": _metric_lineage_value(metric, "source_basis"),
        "metric_role": _metric_lineage_value(metric, "metric_role"),
        "proof_consumer": _metric_lineage_value(metric, "proof_consumer"),
        "not_n5_final_proof": _metric_lineage_value(metric, "not_n5_final_proof"),
    }


def _metric_matches_state(metric: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    if str(metric.get("for_trade_date") or metric.get("trade_date") or "") not in {"", str(state.get("trade_date") or "")}:
        return False
    if str(metric.get("signal_type") or state.get("signal_type") or "") != str(state.get("signal_type") or ""):
        return False
    if str(metric.get("direction") or state.get("direction") or "") != str(state.get("direction") or ""):
        return False
    metric_condition_key = str(metric.get("condition_key") or "")
    if metric_condition_key and metric_condition_key != str(state.get("condition_key") or ""):
        return False
    return True


def _final_confirmation_passed(signal_type: str, evaluation: Mapping[str, Any]) -> bool:
    if evaluation.get("metric_context_status") != "ready":
        return False
    if evaluation.get("blocked_reason"):
        return False
    if "all_period_confirmation_pass" in evaluation:
        return _bool_value(evaluation.get("all_period_confirmation_pass"), default=False)
    flags = normalize_mapping(evaluation.get("selected_flags") or {})
    required = BUY_CONFIRMATION_FLAGS if signal_type == "B_BUY" else SELL_CONFIRMATION_FLAGS if signal_type == "S_SELL" else ()
    return bool(required) and all(_bool_value(flags.get(flag), default=False) for flag in required)


def derive_final_action_mark(*, signal_type: str, evaluation: Mapping[str, Any]) -> dict[str, str]:
    current_amount = _decimal_or_none(evaluation.get("current_30m_virtual_amount"))
    previous_amount = _decimal_or_none(evaluation.get("previous_day_same_window_amount"))
    if previous_amount is None:
        return {
            "action_mark": "normal",
            "action_mark_reason": "previous_day_same_window_amount_missing",
        }
    flags = normalize_mapping(evaluation.get("selected_flags") or {})
    if (
        signal_type == "B_BUY"
        and current_amount is not None
        and current_amount > previous_amount
        and _bool_value(flags.get("buy_30m_price_pass"), default=False)
    ):
        return {"action_mark": "30m_volume", "action_mark_reason": "buy_30m_virtual_amount_expanded"}
    if (
        signal_type == "S_SELL"
        and current_amount is not None
        and current_amount < previous_amount
        and _bool_value(flags.get("sell_30m_price_pass"), default=False)
    ):
        return {"action_mark": "30m_shrink", "action_mark_reason": "sell_30m_virtual_amount_shrank"}
    return {"action_mark": "normal", "action_mark_reason": "final_confirmation_passed"}


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _positive_finite_decimal_or_none(value: Any) -> Decimal | None:
    numeric = _decimal_or_none(value)
    if numeric is None or not numeric.is_finite() or numeric <= 0:
        return None
    return numeric


def _condition_projection_context_hash(context: Mapping[str, Any]) -> str:
    payload = {str(key): value for key, value in context.items() if key != "context_hash"}
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _condition_projection_expected_fields(asset_kind: str) -> tuple[str, ...]:
    fields = tuple(N5_N6_PROJECTION_MESSAGE_CONTRACT["condition_context_fields"])
    return fields if asset_kind == "stock" else fields[:-2]


def _ordered_projection_message_reasons(reasons: Sequence[str]) -> list[str]:
    present = set(reasons)
    return [reason for reason in N5_N6_PROJECTION_MESSAGE_NOT_READY_REASON_ORDER if reason in present]


def _entry_projection_context_reasons(
    state: Mapping[str, Any],
    *,
    entry_ref: Mapping[str, Any],
    entry_payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    context_value = entry_payload.get("condition_projection_context")
    context = dict(context_value) if isinstance(context_value, Mapping) else {}
    trace_value = entry_payload.get("condition_projection_context_trace")
    trace = dict(trace_value) if isinstance(trace_value, Mapping) else {}
    reasons: list[str] = []
    if not entry_ref:
        reasons.append("action_entry_trigger_matched_ref_missing")
    if "condition_projection_context" not in entry_payload:
        reasons.append("condition_projection_context_missing")
    elif not isinstance(context_value, Mapping):
        reasons.append("condition_projection_context_not_object")

    asset_kind = str(state.get("asset_kind") or "")
    identity_key = str(state.get("identity_key") or "")
    trade_date = str(state.get("trade_date") or "")
    if isinstance(context_value, Mapping):
        if str(context.get("contract_version") or "") != N2_CONDITION_PROJECTION_CONTEXT_VERSION:
            reasons.append("condition_projection_contract_version_mismatch")
        if str(context.get("source_layer") or "") != "N2_condition":
            reasons.append("condition_projection_source_layer_mismatch")
        if str(context.get("asset_kind") or "") != asset_kind:
            reasons.append("condition_projection_asset_kind_mismatch")
        if str(context.get("identity_key") or "") != identity_key:
            reasons.append("condition_projection_identity_key_mismatch")
        if str(context.get("for_trade_date") or "") != trade_date:
            reasons.append("condition_projection_for_trade_date_mismatch")
        if str(entry_payload.get("condition_projection_context_status") or "") != "ready":
            reasons.append("condition_projection_context_status_not_ready")
        if str(context.get("status") or "") != "ready":
            reasons.append("condition_projection_source_status_not_ready")
        fields = context.get("fields")
        if not isinstance(fields, Mapping):
            reasons.append("condition_projection_fields_missing")
            fields = {}
        if set(fields) != set(_condition_projection_expected_fields(asset_kind)):
            reasons.append("condition_projection_field_shape_mismatch")
        if _positive_finite_decimal_or_none(fields.get("close")) is None:
            reasons.append("condition_projection_close_invalid")
        context_hash = str(context.get("context_hash") or "")
        if not context_hash:
            reasons.append("condition_projection_context_hash_missing")
        elif context_hash != _condition_projection_context_hash(context):
            reasons.append("condition_projection_context_hash_mismatch")
    else:
        context_hash = ""

    if str(trace.get("policy_version") or "") != N4_CONDITION_PROJECTION_PASSTHROUGH_POLICY_VERSION:
        reasons.append("condition_projection_trace_policy_version_mismatch")
    if str(trace.get("policy_hash") or "") != N4_CONDITION_PROJECTION_PASSTHROUGH_POLICY_HASH:
        reasons.append("condition_projection_trace_policy_hash_invalid")
    if str(trace.get("status") or "") != "ready":
        reasons.append("condition_projection_trace_status_not_ready")
    if str(trace.get("source_context_hash") or "") != context_hash:
        reasons.append("condition_projection_trace_source_hash_mismatch")
    return context, trace, _ordered_projection_message_reasons(reasons)


def _entry_condition_projection_snapshot(state: Mapping[str, Any]) -> dict[str, Any]:
    entry_ref = _action_entry_trigger_matched_ref(state)
    entry_payload = normalize_mapping(entry_ref.get("source_n4_payload") or {})
    context_value = entry_payload.get("condition_projection_context", {})
    context, trace, reasons = _entry_projection_context_reasons(
        state,
        entry_ref=entry_ref,
        entry_payload=entry_payload,
    )
    fields = context.get("fields") if isinstance(context, Mapping) else None
    if not isinstance(fields, Mapping):
        fields = {}
    return {
        "entry_ref": entry_ref,
        "entry_payload": entry_payload,
        "context": context_value,
        "context_status": str(entry_payload.get("condition_projection_context_status") or "not_ready"),
        "context_trace": trace,
        "close": _positive_finite_decimal_or_none(fields.get("close")),
        "not_ready_reasons": reasons,
    }


def _action_entry_trigger_price(state: Mapping[str, Any], snapshot: Mapping[str, Any]) -> Any:
    raw_json = normalize_mapping(state.get("raw_json") or {})
    if "action_entry_trigger_price" in raw_json:
        return raw_json.get("action_entry_trigger_price")
    entry_payload = normalize_mapping(snapshot.get("entry_payload") or {})
    return entry_payload.get("trigger_price")


def _percentage_from_price(
    price_value: Any,
    *,
    close: Decimal | None,
    inherited_reasons: Sequence[str],
    invalid_price_reason: str,
) -> dict[str, Any]:
    reasons = list(inherited_reasons)
    price = _positive_finite_decimal_or_none(price_value)
    if price is None:
        reasons.append(invalid_price_reason)
    if reasons or close is None or price is None:
        return {"value": None, "status": "not_ready", "not_ready_reasons": reasons}
    value = ((price / close) - Decimal("1")) * Decimal("100")
    quantized = value.quantize(PCT_DECIMAL_QUANTUM, rounding=ROUND_HALF_UP)
    if quantized == 0:
        quantized = abs(quantized)
    return {
        "value": format(quantized, ".6f"),
        "status": "ready",
        "not_ready_reasons": [],
    }


def _projection_message_contract_fields(
    event_type: str,
    state: Mapping[str, Any],
    *,
    entry_projection: Mapping[str, Any],
    trigger_pct: Mapping[str, Any],
    action_price: Any,
    action_pct_status: Any,
) -> dict[str, Any]:
    context_value = entry_projection.get("context")
    context = context_value if isinstance(context_value, Mapping) else {}
    fields_value = context.get("fields") if isinstance(context, Mapping) else None
    fields = fields_value if isinstance(fields_value, Mapping) else {}
    asset_kind = str(state.get("asset_kind") or "")
    identity_key = str(state.get("identity_key") or "")
    identity_parts = identity_key.split(":")
    asset_code = (
        identity_parts[2]
        if len(identity_parts) == 3 and identity_parts[0] == asset_kind and identity_parts[2]
        else None
    )
    asset_name = fields.get("name")
    reasons = list(entry_projection.get("not_ready_reasons") or [])
    if asset_code is None:
        reasons.append("asset_code_invalid")
    if not isinstance(asset_name, str) or not asset_name.strip():
        reasons.append("asset_name_missing")
        asset_name = None
    if str(trigger_pct.get("status") or "") != "ready":
        reasons.append("trigger_pct_status_not_ready")
    if event_type == "ActionExecuted":
        if _positive_finite_decimal_or_none(action_price) is None:
            reasons.append("action_price_invalid")
        if str(action_pct_status or "") != "ready":
            reasons.append("action_pct_status_not_ready")
    ordered_reasons = _ordered_projection_message_reasons(reasons)
    output = {
        "projection_message_contract_version": N5_N6_PROJECTION_MESSAGE_CONTRACT_VERSION,
        "projection_message_contract_hash": N5_N6_PROJECTION_MESSAGE_CONTRACT_HASH,
        "projection_message_status": "ready" if not ordered_reasons else "not_ready",
        "projection_message_not_ready_reasons": ordered_reasons,
        "asset_code": asset_code,
        "asset_name": asset_name,
        "buy_expected_return_pct": fields.get("buy_expected_return_pct"),
        "sell_expected_return_pct": fields.get("sell_expected_return_pct"),
        "up_secondary_expected_return_pct": fields.get("up_secondary_expected_return_pct"),
        "up_reference_period": fields.get("up_reference_period"),
        "down_reference_period": fields.get("down_reference_period"),
    }
    if asset_kind == "stock":
        output["score"] = fields.get("score")
        output["pe_core"] = fields.get("pe_core")
    return output


def _execute_tracking_state(state: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    executed = dict(_normalize_tracking_row(state))
    evaluation = normalize_mapping(result.get("metric_evaluation") or {})
    evaluation_minute_label = _metric_evaluation_minute_label(evaluation)
    raw_json = normalize_mapping(executed.get("raw_json") or {})
    raw_json.update(
        {
            "source_action_confirmation_metric_id": evaluation.get("source_action_confirmation_metric_id"),
            "source_metric_run_id": evaluation.get("projection_run_id"),
            "selected_metric_time": evaluation.get("metric_time"),
            "selected_metric_minute_label": evaluation.get("metric_minute_label"),
            "selected_metric_evaluation_minute_label": evaluation_minute_label,
            "selected_action_price": evaluation.get("current_price"),
            "action_mark": result.get("action_mark"),
            "action_mark_reason": result.get("action_mark_reason"),
            "confirmation_trace": evaluation,
        }
    )
    executed.update(
        {
            "action_state": "executed",
            "confirmation_status": "passed",
            "tracking_status": "executed",
            "planned_output_event_type": "ActionExecuted",
            "last_checked_minute_label": evaluation_minute_label or evaluation.get("metric_minute_label"),
            "raw_json": raw_json,
        }
    )
    return executed


def _pending_tracking_evidence(state: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    pending = dict(_normalize_tracking_row(state))
    evaluation = normalize_mapping(result.get("metric_evaluation") or {})
    evaluation_minute_label = _metric_evaluation_minute_label(evaluation)
    raw_json = normalize_mapping(pending.get("raw_json") or {})
    metric_status = {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "source_action_confirmation_metric_id": evaluation.get("source_action_confirmation_metric_id"),
        "projection_run_id": evaluation.get("projection_run_id"),
        "metric_context_status": evaluation.get("metric_context_status"),
        "metric_minute_label": evaluation.get("metric_minute_label"),
        "metric_evaluation_minute_label": evaluation_minute_label,
    }
    metric_status["metric_evaluation_key"] = _pending_metric_evaluation_key(metric_status)
    raw_json["latest_metric_status"] = metric_status
    prior_last_checked = _minute_label_text(pending.get("last_checked_minute_label"))
    if _metric_cursor_guard_is_non_advancing(metric_status.get("reason")):
        last_checked_minute_label = prior_last_checked or pending.get("last_checked_minute_label")
        next_unchecked_minute_label = _minute_label_text(raw_json.get("next_unchecked_minute_label"))
    else:
        last_checked_minute_label = (
            evaluation_minute_label
            or prior_last_checked
            or pending.get("last_checked_minute_label")
        )
        next_unchecked_minute_label = _next_unchecked_minute_label(
            for_trade_date=str(pending.get("trade_date") or ""),
            first_confirmation_minute_label=(
                _minute_label_text(raw_json.get("first_confirmation_minute_label"))
                or _first_confirmation_minute_label(pending.get("latest_n4_event_time") or pending.get("trigger_time"))
            ),
            last_checked_minute_label=_minute_label_text(last_checked_minute_label),
        )
    raw_json["last_checked_minute_label"] = _minute_label_text(last_checked_minute_label)
    raw_json["next_unchecked_minute_label"] = next_unchecked_minute_label
    pending.update(
        {
            "action_state": "eligible",
            "confirmation_status": "pending",
            "tracking_status": "tracking",
            "planned_output_event_type": pending.get("planned_output_event_type"),
            "last_checked_minute_label": last_checked_minute_label,
            "raw_json": raw_json,
        }
    )
    return pending


def _terminal_no_action_tracking_evidence(state: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    terminal = _pending_tracking_evidence(state, result)
    evaluation = normalize_mapping(result.get("metric_evaluation") or {})
    raw_json = normalize_mapping(terminal.get("raw_json") or {})
    raw_json["terminal_no_action_trace"] = {
        "reason": POST_CLOSE_NO_ACTION_EXPIRED_REASON,
        "latest_metric_status": normalize_mapping(raw_json.get("latest_metric_status") or {}),
    }
    terminal.update(
        {
            "action_state": "expired",
            "confirmation_status": "expired",
            "tracking_status": "expired",
            "planned_output_event_type": None,
            "expired_reason": POST_CLOSE_NO_ACTION_EXPIRED_REASON,
            "expired_at": evaluation.get("metric_time") or state.get("latest_n4_event_time"),
            "raw_json": raw_json,
        }
    )
    return terminal


def _should_terminalize_no_action_tracking(state: Mapping[str, Any], result: Mapping[str, Any]) -> bool:
    if result.get("status") == "passed":
        return False
    if _metric_cursor_guard_is_non_advancing(result.get("reason")):
        return False
    evaluation = normalize_mapping(result.get("metric_evaluation") or {})
    if _metric_cursor_guard_is_non_advancing(evaluation.get("blocked_reason")):
        return False
    metric_minute_label = _metric_evaluation_minute_label(evaluation)
    if not metric_minute_label:
        metric_minute_label = _minute_label_text(state.get("last_checked_minute_label"))
    if not metric_minute_label:
        return False
    return _is_final_canonical_minute_label(state.get("trade_date"), metric_minute_label)


def _should_terminalize_unconfirmable_cursor(state: Mapping[str, Any]) -> bool:
    trade_date = str(state.get("trade_date") or "")
    if not re.fullmatch(r"\d{8}", trade_date):
        return False
    labels = canonical_ashare_1m_labels(trade_date)
    if not labels:
        return False
    expected_label = _expected_next_unchecked_minute_label(state)
    if not expected_label or expected_label in labels:
        return False
    return _compare_canonical_minute_label(for_trade_date=trade_date, left=expected_label, right=labels[-1]) > 0


def _unconfirmable_cursor_no_action_result(state: Mapping[str, Any]) -> dict[str, Any]:
    expected_label = _expected_next_unchecked_minute_label(state)
    return {
        "status": "pending",
        "reason": "post_close_no_confirmable_minute",
        "metric_fact": {},
        "metric_evaluation": {
            "blocked_reason": "post_close_no_confirmable_minute",
            "metric_context_status": "post_close_no_confirmable_minute",
            "metric_minute_label": expected_label,
            "metric_evaluation_minute_label": expected_label,
            "metric_time": state.get("latest_n4_event_time") or state.get("trigger_time"),
            "projection_run_id": "",
            "source_action_confirmation_metric_id": "",
        },
    }


def _is_final_canonical_minute_label(for_trade_date: Any, minute_label: Any) -> bool:
    trade_date = str(for_trade_date or "")
    label = _minute_label_text(minute_label)
    if not re.fullmatch(r"\d{8}", trade_date) or not label:
        return False
    labels = canonical_ashare_1m_labels(trade_date)
    return bool(labels) and label == labels[-1]


def _metric_cursor_guard_is_non_advancing(reason: Any) -> bool:
    return str(reason or "") in {
        "metric_before_next_unchecked_minute_label",
        "metric_after_next_unchecked_minute_label",
    }


def _superseded_tracking_evidence(
    state: Mapping[str, Any],
    *,
    primary_state: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    pending = dict(_normalize_tracking_row(state))
    evaluation = normalize_mapping(result.get("metric_evaluation") or {})
    evaluation_minute_label = _metric_evaluation_minute_label(evaluation)
    raw_json = normalize_mapping(pending.get("raw_json") or {})
    metric_status = {
        "status": "pending",
        "reason": "superseded_by_primary_action_ref",
        "source_action_confirmation_metric_id": evaluation.get("source_action_confirmation_metric_id"),
        "projection_run_id": evaluation.get("projection_run_id"),
        "metric_context_status": evaluation.get("metric_context_status"),
        "metric_minute_label": evaluation.get("metric_minute_label"),
        "metric_evaluation_minute_label": evaluation_minute_label,
        "primary_action_state_key": primary_state.get("state_key"),
        "primary_condition_key": primary_state.get("condition_key"),
    }
    metric_status["metric_evaluation_key"] = _pending_metric_evaluation_key(metric_status)
    raw_json["latest_metric_status"] = metric_status
    raw_json["superseded_by_primary_action_ref"] = {
        "primary_action_state_key": primary_state.get("state_key"),
        "primary_condition_key": primary_state.get("condition_key"),
        "primary_source_trigger_event_id": primary_state.get("source_trigger_event_id"),
    }
    pending.update(
        {
            "action_state": "eligible",
            "confirmation_status": "pending",
            "tracking_status": "tracking",
            "planned_output_event_type": pending.get("planned_output_event_type"),
            "last_checked_minute_label": evaluation_minute_label or evaluation.get("metric_minute_label") or pending.get("last_checked_minute_label"),
            "raw_json": raw_json,
        }
    )
    return pending


def _pending_metric_evaluation_key(metric_status: Mapping[str, Any]) -> str:
    return "|".join(
        str(metric_status.get(key) or "")
        for key in (
            "status",
            "reason",
            "source_action_confirmation_metric_id",
            "projection_run_id",
            "metric_context_status",
            "metric_minute_label",
            "metric_evaluation_minute_label",
        )
    )


def _primary_action_state_keys_by_group(states: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str, str, str], str]:
    grouped: dict[tuple[str, str, str, str, str], list[Mapping[str, Any]]] = {}
    for state in states:
        grouped.setdefault(_action_ref_group_key(state), []).append(state)
    output: dict[tuple[str, str, str, str, str], str] = {}
    for group_key, group_states in grouped.items():
        primary = sorted(group_states, key=_action_ref_primary_sort_key)[0]
        output[group_key] = str(primary.get("state_key") or "")
    return output


def _primary_ref_has_metric_evaluation(result: Mapping[str, Any]) -> bool:
    if result.get("status") == "passed":
        return True
    if result.get("metric_evaluation"):
        return str(result.get("reason") or "") not in {"metric_missing", "metric_not_in_scope"}
    return False


def _action_ref_group_key(state: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(state.get("trade_date") or ""),
        str(state.get("asset_kind") or ""),
        str(state.get("identity_key") or ""),
        str(state.get("direction") or ""),
        str(state.get("signal_type") or ""),
    )


def _action_ref_primary_sort_key(state: Mapping[str, Any]) -> tuple[int, float, str, str]:
    trigger_dt = datetime_or_none(state.get("latest_n4_event_time"))
    trigger_ts = trigger_dt.timestamp() if trigger_dt is not None else 0.0
    return (
        1 if _is_hint_condition_key(state.get("condition_key")) else 0,
        -trigger_ts,
        str(state.get("condition_key") or ""),
        str(state.get("state_key") or ""),
    )


def _is_hint_condition_key(condition_key: Any) -> bool:
    text = str(condition_key or "").strip().upper()
    return text.startswith("BUY_HINT") or text.startswith("SELL_HINT")


def _pending_tracking_evidence_unchanged(state: Mapping[str, Any], update: Mapping[str, Any]) -> bool:
    current_status = normalize_mapping(normalize_mapping(state.get("raw_json") or {}).get("latest_metric_status") or {})
    new_status = normalize_mapping(normalize_mapping(update.get("raw_json") or {}).get("latest_metric_status") or {})
    new_key = str(new_status.get("metric_evaluation_key") or "")
    if new_key and new_key == str(current_status.get("metric_evaluation_key") or ""):
        return True
    comparable_keys = (
        "status",
        "reason",
        "source_action_confirmation_metric_id",
        "projection_run_id",
        "metric_context_status",
        "metric_minute_label",
    )
    return bool(current_status) and all(
        str(current_status.get(key) or "") == str(new_status.get(key) or "") for key in comparable_keys
    )


def _build_action_event(
    event_type: str,
    state: Mapping[str, Any],
    *,
    action_run_id: str,
    source_trigger_run_id: str,
    source_metric_run_id: str,
    consumer_name: str,
) -> dict[str, Any]:
    state_key = str(state.get("state_key") or "")
    raw_json = normalize_mapping(state.get("raw_json") or {})
    dedup_parts = ["N5_live_tracking_v2", event_type, action_run_id, state_key]
    if event_type == "ActionExecuted" or (
        event_type == "ActionEligible"
        and _bool_value(raw_json.get("terminal_ref_reopen_allowed"), default=False)
    ):
        dedup_parts.append(str(state.get("source_trigger_event_id") or state.get("latest_n4_event_id") or ""))
    dedup_key = join_dedup_parts(*dedup_parts)
    event_id = build_stable_event_id(
        source_layer=N5_SOURCE_LAYER,
        event_type=event_type,
        source_run_id=action_run_id,
        dedup_key=dedup_key,
        event_schema_version=N5_LIVE_TRACKING_SCHEMA_VERSION,
    )
    source_n4_payload = normalize_mapping(raw_json.get("source_n4_payload") or {})
    action_entry_trigger_matched_ref = normalize_mapping(
        raw_json.get("action_entry_trigger_matched_ref") or {}
    )
    latest_trigger_state_changed_ref = normalize_mapping(
        raw_json.get("latest_trigger_state_changed_ref") or {}
    )
    entry_projection = _entry_condition_projection_snapshot(state)
    entry_trigger_price = _action_entry_trigger_price(state, entry_projection)
    trigger_pct = _percentage_from_price(
        entry_trigger_price,
        close=entry_projection.get("close"),
        inherited_reasons=entry_projection.get("not_ready_reasons") or [],
        invalid_price_reason="entry_trigger_price_invalid",
    )
    trigger_period, primary_trigger_period, trigger_periods = _canonical_trigger_period_payload_fields(
        state,
        source_n4_payload,
    )
    source_trigger_event_time = _scope_time_text(state.get("latest_n4_event_time"))
    selected_source_metric_run_id = str(raw_json.get("source_metric_run_id") or source_metric_run_id)
    payload = {
        "run_id": action_run_id,
        "source_trigger_event_id": state.get("source_trigger_event_id"),
        "source_trigger_event_type": state.get("source_trigger_event_type") or state.get("latest_n4_event_type"),
        "source_trigger_event_time": source_trigger_event_time,
        "source_trigger_run_id": state.get("source_trigger_run_id") or source_trigger_run_id,
        "source_trigger_state_id": state.get("source_trigger_state_id"),
        "source_trigger_match_id": state.get("source_trigger_match_id"),
        "source_metric_run_id": selected_source_metric_run_id,
        "action_key": state_key,
        "dedup_key": dedup_key,
        "identity_key": state.get("identity_key"),
        "asset_kind": state.get("asset_kind"),
        "direction": state.get("direction"),
        "signal_type": state.get("signal_type"),
        "condition_key": state.get("condition_key"),
        "original_condition_key": state.get("condition_key"),
        "trigger_period": trigger_period,
        "primary_trigger_period": primary_trigger_period,
        "all_trigger_periods": trigger_periods,
        "trigger_time": source_trigger_event_time,
        "trigger_price": entry_trigger_price,
        "pct_contract_version": N5_TRIGGER_ACTION_PCT_CONTEXT_VERSION,
        "condition_projection_context": entry_projection.get("context"),
        "condition_projection_context_status": entry_projection.get("context_status"),
        "condition_projection_context_trace": entry_projection.get("context_trace"),
        "trigger_pct": trigger_pct["value"],
        "trigger_pct_status": trigger_pct["status"],
        "trigger_pct_not_ready_reasons": trigger_pct["not_ready_reasons"],
        "triggered_periods": trigger_periods,
        "projection_30m_flag": state.get("projection_30m_flag"),
        "projection_30m_type": state.get("projection_30m_type"),
        "trigger_mark_candidate": state.get("trigger_mark_candidate"),
        "source_n4_payload": source_n4_payload,
        "action_entry_trigger_matched_ref": action_entry_trigger_matched_ref,
        "latest_trigger_state_changed_ref": latest_trigger_state_changed_ref,
        "action_state": state.get("action_state"),
        "confirmation_status": state.get("confirmation_status"),
        "action_mark": raw_json.get("action_mark"),
        "action_mark_reason": raw_json.get("action_mark_reason"),
        "action_policy": "n5_live_tracking_bounded_v2",
        "trace_json": {
            "consumer_name": consumer_name,
            "tracking_state_key": state_key,
            "trigger_mark_candidate_ignored": raw_json.get("n4_trigger_mark_candidate_ignored"),
            "source_action_confirmation_metric_id": raw_json.get("source_action_confirmation_metric_id"),
            "selected_metric_time": raw_json.get("selected_metric_time"),
            "selected_metric_minute_label": raw_json.get("selected_metric_minute_label"),
            "source_trigger_event_id": state.get("source_trigger_event_id"),
            "source_trigger_event_type": state.get("source_trigger_event_type") or state.get("latest_n4_event_type"),
            "source_trigger_event_time": source_trigger_event_time,
            "source_n4_payload": source_n4_payload,
            "action_entry_trigger_matched_ref": action_entry_trigger_matched_ref,
            "latest_trigger_state_changed_ref": latest_trigger_state_changed_ref,
            "pct_contract_version": N5_TRIGGER_ACTION_PCT_CONTEXT_VERSION,
            "trigger_pct_status": trigger_pct["status"],
            "trigger_pct_not_ready_reasons": trigger_pct["not_ready_reasons"],
        },
        "data_quality_status": "passed",
        "event_schema_version": N5_LIVE_TRACKING_SCHEMA_VERSION,
    }
    if event_type == "ActionExecuted":
        confirmation_trace = normalize_mapping(raw_json.get("confirmation_trace") or {})
        action_price = (
            raw_json.get("selected_action_price")
            if "selected_action_price" in raw_json
            else confirmation_trace.get("current_price")
        )
        action_pct = _percentage_from_price(
            action_price,
            close=entry_projection.get("close"),
            inherited_reasons=entry_projection.get("not_ready_reasons") or [],
            invalid_price_reason="selected_n3t_current_price_invalid",
        )
        payload.update(
            {
                "action_price": action_price,
                "action_pct": action_pct["value"],
                "action_pct_status": action_pct["status"],
                "action_pct_not_ready_reasons": action_pct["not_ready_reasons"],
            }
        )
        payload["trace_json"].update(
            {
                "action_price_source": "selected_passing_N3T_C1_CLOSED.current_price",
                "action_pct_status": action_pct["status"],
                "action_pct_not_ready_reasons": action_pct["not_ready_reasons"],
            }
        )
    payload.update(
        _projection_message_contract_fields(
            event_type,
            state,
            entry_projection=entry_projection,
            trigger_pct=trigger_pct,
            action_price=payload.get("action_price"),
            action_pct_status=payload.get("action_pct_status"),
        )
    )
    return {
        "event_id": event_id,
        "event_key": dedup_key,
        "event_type": event_type,
        "event_schema_version": N5_LIVE_TRACKING_SCHEMA_VERSION,
        "trade_date": state.get("trade_date"),
        "asset_kind": state.get("asset_kind"),
        "identity_key": state.get("identity_key"),
        "event_time": _event_time_for_action(event_type, state, raw_json),
        "source_layer": N5_SOURCE_LAYER,
        "source_run_id": action_run_id,
        "dedup_key": dedup_key,
        "partition_key": state.get("identity_key"),
        "payload_json": payload,
    }


def _event_time_for_action(event_type: str, state: Mapping[str, Any], raw_json: Mapping[str, Any]) -> Any:
    if event_type == "ActionExecuted":
        return raw_json.get("selected_metric_time") or state.get("latest_n4_event_time")
    return state.get("latest_n4_event_time")


def _derive_for_trade_date(
    active_tracking_rows: Sequence[Mapping[str, Any]],
    tracking_updates: Sequence[Mapping[str, Any]],
    n4_event_rows: Sequence[Mapping[str, Any]],
) -> str:
    for row in (*tracking_updates, *active_tracking_rows):
        value = row.get("trade_date") or row.get("for_trade_date")
        if value:
            return str(value)
    for row in n4_event_rows:
        payload = _payload(row)
        value = _value(row, payload, "trade_date", "for_trade_date")
        if value:
            return str(value)
    return ""


def _build_active_scope_snapshot_artifact(
    *,
    for_trade_date: str,
    action_run_id: str,
    source_trigger_run_id: str,
    consumer_name: str,
    active_tracking_rows: Sequence[Mapping[str, Any]],
    tracking_updates: Sequence[Mapping[str, Any]],
    tracking_update_state_keys_allowed_to_enter_scope: set[str] | Sequence[str] | None = None,
    active_tracking_rows_authoritative: bool = False,
    attention_n4_event_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    final_states: dict[str, dict[str, Any]] = {}
    allowed_new_state_keys = {str(key) for key in (tracking_update_state_keys_allowed_to_enter_scope or set()) if str(key)}
    for row in active_tracking_rows:
        normalized = _normalize_tracking_row(row)
        if _state_in_trade_date(normalized, for_trade_date):
            final_states[normalized["state_key"]] = normalized
    for row in tracking_updates:
        normalized = _normalize_tracking_row(row)
        if _state_in_trade_date(normalized, for_trade_date):
            state_key = str(normalized.get("state_key") or "")
            if (
                not active_tracking_rows_authoritative
                or state_key in final_states
                or state_key in allowed_new_state_keys
            ):
                final_states[state_key] = normalized

    object_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for state in final_states.values():
        if not _is_active_tracking(state):
            continue
        ref = _active_scope_ref(state)
        key = _object_scope_key(ref)
        object_row = object_rows.setdefault(key, _object_scope_row(ref))
        object_row["active_tracking_refs"].append(ref)
    for event_row in attention_n4_event_rows:
        ref = _attention_scope_ref(event_row, for_trade_date=for_trade_date)
        if not ref:
            continue
        key = _object_scope_key(ref)
        object_row = object_rows.setdefault(key, _object_scope_row(ref))
        object_row["attention_event_refs"].append(ref)

    scope_rows = sorted(
        (_finalize_object_scope_row(row) for row in object_rows.values()),
        key=lambda row: (row["asset_kind"], row["identity_key"]),
    )
    removed_scope_rows = sorted(
        (_removed_scope_row(row) for row in final_states.values() if _scope_exit_reason(row)),
        key=lambda row: (
            row["asset_kind"],
            row["identity_key"],
            row["direction"],
            row["signal_type"],
            row["condition_key"],
        ),
    )
    return {
        "artifact_type": "n5_active_scope_snapshot_v1",
        "artifact_schema_version": "v2",
        "producer_layer": N5_SOURCE_LAYER,
        "for_trade_date": str(for_trade_date or ""),
        "action_run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "consumer_name": consumer_name,
        "scope_granularity": "object",
        "scope_status": "active" if scope_rows else "empty",
        "empty_scope_noop": not scope_rows,
        "scope_count": len(scope_rows),
        "active_tracking_ref_count": sum(len(row["active_tracking_refs"]) for row in scope_rows),
        "attention_event_ref_count": sum(len(row["attention_event_refs"]) for row in scope_rows),
        "active_sets": _active_sets_by_family(scope_rows),
        "scope_rows": scope_rows,
        "removed_scope_rows": removed_scope_rows,
        "full_market_fallback_allowed": False,
        "n3_scans_n5_internals": False,
        "db_write_allowed": False,
        "n4_outbox_status_update_allowed": False,
        "updates_n4_outbox": False,
        "artifact_output_only": True,
        "boundary": {
            "n5_owned_scope": True,
            "source_is_read_only_n4_pending_events": True,
            "n3_direct_n5_table_scan_allowed": False,
            "full_market_fallback_allowed": False,
            "db_write_allowed": False,
            "n4_outbox_status_update_allowed": False,
        },
    }


def _state_in_trade_date(state: Mapping[str, Any], for_trade_date: str) -> bool:
    return not for_trade_date or str(state.get("trade_date") or "") == str(for_trade_date)


def _object_scope_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("for_trade_date") or ""),
        str(row.get("asset_kind") or ""),
        str(row.get("identity_key") or ""),
    )


def _object_scope_row(ref: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "for_trade_date": str(ref.get("for_trade_date") or ""),
        "asset_kind": str(ref.get("asset_kind") or ""),
        "identity_key": str(ref.get("identity_key") or ""),
        "scope_status": "active",
        "active_tracking_refs": [],
        "attention_event_refs": [],
    }


def _finalize_object_scope_row(row: Mapping[str, Any]) -> dict[str, Any]:
    active_refs = sorted(
        (normalize_mapping(ref) for ref in row.get("active_tracking_refs") or []),
        key=lambda ref: (
            str(ref.get("direction") or ""),
            str(ref.get("signal_type") or ""),
            str(ref.get("condition_key") or ""),
            str(ref.get("source_trigger_event_id") or ""),
        ),
    )
    attention_refs = sorted(
        (normalize_mapping(ref) for ref in row.get("attention_event_refs") or []),
        key=lambda ref: (
            str(ref.get("event_time") or ""),
            str(ref.get("source_trigger_event_id") or ""),
        ),
    )
    return {
        "for_trade_date": str(row.get("for_trade_date") or ""),
        "asset_kind": str(row.get("asset_kind") or ""),
        "identity_key": str(row.get("identity_key") or ""),
        "scope_status": "active",
        "active_families": sorted(
            {
                _source_run_family(ref.get("source_trigger_run_id"))
                for ref in (*active_refs, *attention_refs)
                if _source_run_family(ref.get("source_trigger_run_id"))
            }
        ),
        "active_tracking_refs": active_refs,
        "attention_event_refs": attention_refs,
    }


def _active_scope_ref(state: Mapping[str, Any]) -> dict[str, Any]:
    raw_json = normalize_mapping(state.get("raw_json") or {})
    source_n4_payload = normalize_mapping(raw_json.get("source_n4_payload") or {})
    action_entry_trigger_matched_ref = normalize_mapping(
        raw_json.get("action_entry_trigger_matched_ref") or {}
    )
    latest_trigger_state_changed_ref = normalize_mapping(
        raw_json.get("latest_trigger_state_changed_ref") or {}
    )
    primary_trigger_period, trigger_periods = _canonical_trigger_period_fields(
        state,
        source_n4_payload,
    )
    latest_metric_status = raw_json.get("latest_metric_status")
    if isinstance(latest_metric_status, Mapping):
        latest_metric_status = normalize_mapping(latest_metric_status)
    trigger_time = _scope_time_text(state.get("latest_n4_event_time"))
    source_trigger_event_type = str(state.get("source_trigger_event_type") or state.get("latest_n4_event_type") or "")
    first_confirmation_minute_label = _first_confirmation_minute_label(trigger_time)
    last_checked_minute_label = _minute_label_text(state.get("last_checked_minute_label"))
    next_unchecked_minute_label = _next_unchecked_minute_label(
        for_trade_date=str(state.get("trade_date") or ""),
        first_confirmation_minute_label=first_confirmation_minute_label,
        last_checked_minute_label=last_checked_minute_label,
    )
    return {
        "for_trade_date": str(state.get("trade_date") or ""),
        "state_key": str(state.get("state_key") or ""),
        "asset_kind": str(state.get("asset_kind") or ""),
        "identity_key": str(state.get("identity_key") or ""),
        "direction": str(state.get("direction") or ""),
        "signal_type": str(state.get("signal_type") or ""),
        "condition_key": str(state.get("condition_key") or ""),
        "action_run_id": str(state.get("run_id") or raw_json.get("action_run_id") or ""),
        "source_trigger_event_id": str(state.get("source_trigger_event_id") or ""),
        "source_trigger_event_type": source_trigger_event_type,
        "source_trigger_run_id": str(state.get("source_trigger_run_id") or ""),
        "source_run_family": _source_run_family(state.get("source_trigger_run_id")),
        "source_run_hash": _state_source_run_hash(state),
        "ref_hash": _active_ref_hash(state),
        "trigger_time": trigger_time,
        "source_trigger_event_time": trigger_time,
        "latest_n4_event_time": trigger_time,
        "latest_n4_event_id": str(state.get("latest_n4_event_id") or state.get("source_trigger_event_id") or ""),
        "latest_n4_event_type": str(state.get("latest_n4_event_type") or source_trigger_event_type),
        "trigger_price": state.get("trigger_price") if state.get("trigger_price") is not None else source_n4_payload.get("trigger_price"),
        "primary_trigger_period": primary_trigger_period,
        "all_trigger_periods": trigger_periods,
        "triggered_periods": trigger_periods,
        "projection_30m_flag": state.get("projection_30m_flag"),
        "projection_30m_type": state.get("projection_30m_type"),
        "trigger_mark_candidate": state.get("trigger_mark_candidate"),
        "source_n4_payload": source_n4_payload,
        "action_eligible_entry_allowed": source_trigger_event_type != "TriggerStateChanged",
        "action_confirmation_entry_verified": bool(action_entry_trigger_matched_ref),
        "action_entry_trigger_matched_ref": action_entry_trigger_matched_ref,
        "latest_trigger_state_changed_ref": latest_trigger_state_changed_ref,
        "planned_output_event_type": state.get("planned_output_event_type"),
        "first_confirmation_minute_label": first_confirmation_minute_label,
        "last_checked_minute_label": last_checked_minute_label or None,
        "next_unchecked_minute_label": next_unchecked_minute_label,
        "latest_metric_status": latest_metric_status,
        "metric_evaluation_key": str(
            raw_json.get("metric_evaluation_key")
            or (latest_metric_status.get("metric_evaluation_key") if isinstance(latest_metric_status, Mapping) else "")
            or ""
        ),
        "last_seen_metric_key": str(raw_json.get("last_seen_metric_key") or ""),
        "action_state": str(state.get("action_state") or ""),
        "confirmation_status": str(state.get("confirmation_status") or ""),
        "tracking_status": str(state.get("tracking_status") or ""),
        "scope_status": "active",
    }


def _state_source_run_hash(state: Mapping[str, Any]) -> str:
    raw_json = normalize_mapping(state.get("raw_json") or {})
    existing = str(state.get("source_run_hash") or raw_json.get("source_run_hash") or "")
    if existing:
        return existing
    return _short_scope_hash(str(state.get("source_trigger_run_id") or state.get("source_trigger_event_id") or ""))


def _active_ref_hash(state: Mapping[str, Any]) -> str:
    return _short_scope_hash(
        str(state.get("state_key") or ""),
        str(state.get("source_trigger_event_id") or ""),
        str(state.get("latest_n4_event_time") or ""),
    )


def _short_scope_hash(*parts: str) -> str:
    text = join_dedup_parts(*(part for part in parts if part))
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _active_scope_row(state: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in _active_scope_ref(state).items() if key != "action_run_id"}


def _attention_scope_ref(row: Mapping[str, Any], *, for_trade_date: str) -> dict[str, Any]:
    payload = _payload(row)
    grain = _tracking_grain_from_event(row)
    if for_trade_date and grain["trade_date"] != str(for_trade_date):
        return {}
    if grain["asset_kind"] not in {"stock", "index", "board"} or not grain["identity_key"]:
        return {}
    trigger_time = _scope_time_text(row.get("event_time"))
    return {
        "for_trade_date": grain["trade_date"],
        "asset_kind": grain["asset_kind"],
        "identity_key": grain["identity_key"],
        "direction": grain["direction"],
        "signal_type": grain["signal_type"],
        "condition_key": grain["condition_key"],
        "source_trigger_event_id": str(row.get("event_id") or ""),
        "source_trigger_event_type": "TriggerStateChanged",
        "source_trigger_run_id": str(row.get("source_run_id") or ""),
        "source_run_family": _source_run_family(row.get("source_run_id")),
        "trigger_time": trigger_time,
        "source_trigger_event_time": trigger_time,
        "latest_n4_event_time": trigger_time,
        "first_confirmation_minute_label": _first_confirmation_minute_label(trigger_time),
        "trigger_live": True,
        "current_status": str(_value(row, payload, "current_status") or "matched"),
        "action_eligible_entry_allowed": False,
        "scope_status": "active",
    }


def _scope_time_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _first_confirmation_minute_label(trigger_time: Any) -> str:
    parsed = datetime_or_none(trigger_time)
    if parsed is None:
        return ""
    return parsed.strftime("%H:%M")


def _minute_label_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    match = re.search(r"([0-2][0-9]):([0-5][0-9])", text)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    if re.fullmatch(r"[0-2][0-9][0-5][0-9]", text):
        return f"{text[:2]}:{text[2:]}"
    parsed = datetime_or_none(value)
    if parsed is None:
        return ""
    return parsed.strftime("%H:%M")


def _next_unchecked_minute_label(
    *,
    for_trade_date: str,
    first_confirmation_minute_label: str,
    last_checked_minute_label: str,
) -> str:
    first_label = _minute_label_text(first_confirmation_minute_label)
    last_label = _minute_label_text(last_checked_minute_label)
    if not first_label:
        return ""
    labels = canonical_ashare_1m_labels(for_trade_date) if re.fullmatch(r"\d{8}", str(for_trade_date or "")) else []
    if first_label not in labels:
        return first_label
    if not last_label or last_label not in labels:
        return first_label
    first_index = labels.index(first_label)
    last_index = labels.index(last_label)
    if last_index < first_index:
        return first_label
    next_index = last_index + 1
    return labels[next_index] if next_index < len(labels) else ""


def _active_sets_by_family(scope_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, str]]]:
    output = {"ordinary_active": [], "b2_active": []}
    for row in scope_rows:
        object_ref = {
            "for_trade_date": str(row.get("for_trade_date") or ""),
            "asset_kind": str(row.get("asset_kind") or ""),
            "identity_key": str(row.get("identity_key") or ""),
        }
        families = set(row.get("active_families") or [])
        if "ordinary" in families:
            output["ordinary_active"].append(object_ref)
        if "b2_active" in families:
            output["b2_active"].append(object_ref)
    return output


def _source_run_family(source_trigger_run_id: Any) -> str:
    text = str(source_trigger_run_id or "").lower()
    if "b2" in text or "hint_projection" in text:
        return "b2_active"
    return "ordinary"


def _removed_scope_row(state: Mapping[str, Any]) -> dict[str, Any]:
    row = _active_scope_row(state)
    row["scope_status"] = "removed"
    row["scope_exit_reason"] = _scope_exit_reason(state)
    row["latest_n4_event_id"] = state.get("latest_n4_event_id")
    row["latest_n4_event_type"] = state.get("latest_n4_event_type")
    return row


def _scope_exit_reason(state: Mapping[str, Any]) -> str:
    action_state = str(state.get("action_state") or "")
    if action_state == "executed":
        return "ActionExecuted"
    if action_state == "expired" and str(state.get("expired_reason") or "") == "trigger_live_false":
        return "TriggerStateChanged(trigger_live=false)"
    if action_state in {"blocked", "skipped", "expired"}:
        return action_state
    return ""
