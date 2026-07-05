"""N5 provisional eligibility-only action path.

This module is isolated from the formal action-confirmation metric consumer.
It turns N4 provisional TriggerMatched events into ActionEligible rows only.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.action.event_factory import build_n5_action_event
from ashare_v3.action.query_audit_phase2 import audited_n5_action_connect, audited_n5_readonly_plan_connect
from ashare_v3.events.ids import join_dedup_parts
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    FORMAL_TRIGGER_PERIODS as EVENT_FORMAL_TRIGGER_PERIODS,
    N5_SOURCE_LAYER,
    utc_now,
)


PROVISIONAL_ACTIONELIGIBLE_EVENT_TYPE = "ActionEligible"
PROVISIONAL_ACTION_CONFIRMATION_MODE = "eligibility_only"
PROVISIONAL_ACTION_POLICY = "n5_provisional_eligibility_only"
PROVISIONAL_GENERATED_BY = "n5_provisional_actioneligible_v1"
N3P_SOURCE_METRIC_KIND = "realtime_action_confirmation_metric"
HINT_CONDITION_KEYS = frozenset({"BUY_HINT", "SELL_HINT"})
ORDINARY_TRIGGER_TYPES = frozenset({"BUY", "SELL", "BUY:FULL", "SELL:FULL"})
FORMAL_TRIGGER_PERIODS = tuple(EVENT_FORMAL_TRIGGER_PERIODS)

PROVISIONAL_ACTIONELIGIBLE_ALLOWED_WRITE_TABLES = frozenset(
    {
        "common_action_run",
        "common_action_quality_item",
        "stock_action_fact",
        "index_action_fact",
        "board_action_fact",
        "common_action_event",
        "common_event_outbox",
    }
)
PROVISIONAL_ACTIONELIGIBLE_FORBIDDEN_WRITE_TABLES = frozenset(
    {
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        "common_action_tracking_state",
    }
)
ACTION_FACT_TABLE_BY_ASSET_KIND = {
    "stock": "stock_action_fact",
    "index": "index_action_fact",
    "board": "board_action_fact",
}
IDENTITY_COLUMN_BY_ACTION_FACT_TABLE = {
    "stock_action_fact": "stock_identity_key",
    "index_action_fact": "index_identity_key",
    "board_action_fact": "board_identity_key",
}


class ProvisionalActionEligibleBlocked(RuntimeError):
    """Raised when provisional ActionEligible execution must fail closed."""


def assert_provisional_actioneligible_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise ProvisionalActionEligibleBlocked(
            "N5 provisional ActionEligible execute blocked: missing " + ", ".join(missing)
        )


def build_provisional_actioneligible_plan(
    *,
    source_trigger_run: Mapping[str, Any],
    source_trigger_run_id: str,
    action_run_id: str,
    for_trade_date: str,
    consumer_name: str,
    outbox_rows: Sequence[Mapping[str, Any]],
    target_counts: Mapping[str, int],
    allowed_source_trigger_run_ids: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    """Build the provisional ActionEligible write plan without mutating state."""

    _require_passed_source_trigger_run(source_trigger_run, source_trigger_run_id=source_trigger_run_id)
    _assert_target_absent(target_counts)

    now = utc_now()
    normalized_rows = [normalize_source_outbox_row(row) for row in outbox_rows]
    candidate_rows: list[dict[str, Any]] = []
    noop_reasons: list[str] = []
    for row in normalized_rows:
        reason = validate_provisional_source_row(row)
        if reason:
            noop_reasons.append(reason)
            continue
        candidate_rows.append(
            build_action_candidate(
                row,
                source_trigger_run=source_trigger_run,
                source_trigger_run_id=source_trigger_run_id,
                action_run_id=action_run_id,
                for_trade_date=for_trade_date,
                allowed_source_trigger_run_ids=allowed_source_trigger_run_ids,
            )
        )

    action_fact_rows = {
        "stock_action_fact": [],
        "index_action_fact": [],
        "board_action_fact": [],
    }
    common_action_event_rows: list[dict[str, Any]] = []
    outbox_rows_plan: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        table_name = str(candidate["target_action_fact_table"])
        action_fact_rows[table_name].append(build_action_fact_row(candidate, created_at=now))
        common_action_event_rows.append(build_common_action_event_row(candidate, source_action_fact_id=None, created_at=now))
        outbox_rows_plan.append(build_action_outbox_record(candidate, source_action_fact_id=None, created_at=now))

    writes = {
        "common_action_run": [
            build_action_run_row(
                source_trigger_run=source_trigger_run,
                source_trigger_run_id=source_trigger_run_id,
                action_run_id=action_run_id,
                for_trade_date=for_trade_date,
                consumer_name=consumer_name,
                trigger_outbox_row_count=len(normalized_rows),
                action_count=len(candidate_rows),
                created_at=now,
            )
        ],
        "common_action_quality_item": [
            build_quality_item(
                source_trigger_run=source_trigger_run,
                source_trigger_run_id=source_trigger_run_id,
                action_run_id=action_run_id,
                for_trade_date=for_trade_date,
                trigger_outbox_row_count=len(normalized_rows),
                eligible_count=len(candidate_rows),
                noop_reason_counts=Counter(noop_reasons),
                created_at=now,
            )
        ],
        **action_fact_rows,
        "common_action_event": common_action_event_rows,
        "common_event_outbox": outbox_rows_plan,
    }
    event_counts = dict(Counter(row["event_type"] for row in outbox_rows_plan))
    return {
        "result": "EXECUTE_PLAN_READY",
        "status": "passed",
        "layer_role": "N5_action",
        "mode": "provisional_actioneligible",
        "source_trigger_run_id": source_trigger_run_id,
        "action_run_id": action_run_id,
        "for_trade_date": for_trade_date,
        "consumer_name": consumer_name,
        "trigger_outbox_row_count": len(normalized_rows),
        "candidate_count": len(candidate_rows),
        "eligible_count": len(candidate_rows),
        "noop_count": len(noop_reasons),
        "noop_reason_counts": dict(Counter(noop_reasons)),
        "event_counts": event_counts,
        "writes": writes,
        "write_counts": {table_name: len(rows) for table_name, rows in writes.items()},
        "allowed_write_tables": sorted(PROVISIONAL_ACTIONELIGIBLE_ALLOWED_WRITE_TABLES),
        "forbidden_write_counts": {table_name: 0 for table_name in sorted(PROVISIONAL_ACTIONELIGIBLE_FORBIDDEN_WRITE_TABLES)},
        "event_model": {
            "output_event_type": PROVISIONAL_ACTIONELIGIBLE_EVENT_TYPE,
            "action_confirmation_mode": PROVISIONAL_ACTION_CONFIRMATION_MODE,
            "uses_formal_action_confirmation_metric": False,
            "writes_inbox_or_checkpoint": False,
            "consumes_source_outbox": False,
            "enters_user_layer": False,
            "inbox_written": False,
            "checkpoint_written": False,
            "n6_written": False,
            "sim_trade_virtual_written": False,
            "worker_started": False,
            "action_executed_generated": False,
            "action_blocked_generated": False,
            "action_skipped_generated": False,
        },
    }


def normalize_source_outbox_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    if not isinstance(payload, Mapping):
        payload = {}
    output = dict(row)
    output["payload_json"] = dict(payload)
    output["event_type"] = str(output.get("event_type") or payload.get("event_type") or "")
    output["event_id"] = str(output.get("event_id") or payload.get("source_trigger_event_id") or "")
    output["asset_kind"] = str(payload.get("asset_kind") or output.get("asset_kind") or "")
    output["identity_key"] = str(payload.get("identity_key") or output.get("identity_key") or "")
    output["trade_date"] = str(payload.get("trade_date") or output.get("trade_date") or "")
    output["event_time"] = output.get("event_time") or payload.get("trigger_time")
    return output


def classify_source_payload(payload: Mapping[str, Any]) -> str:
    if is_ordinary_payload(payload):
        return "ordinary"
    return "hint"


def classify_candidate_source(candidate: Mapping[str, Any], source_payload: Mapping[str, Any]) -> str:
    source_kind = str(candidate.get("source_kind") or "")
    if source_kind in {"ordinary", "hint"}:
        return source_kind
    return classify_source_payload(source_payload)


def is_hint_payload(payload: Mapping[str, Any]) -> bool:
    return str(payload.get("condition_key") or "") in HINT_CONDITION_KEYS


def is_ordinary_payload(payload: Mapping[str, Any]) -> bool:
    condition_key = str(payload.get("condition_key") or "")
    trigger_type = str(payload.get("trigger_type") or "")
    return (
        str(payload.get("source_metric_kind") or "") == N3P_SOURCE_METRIC_KIND
        and condition_key not in HINT_CONDITION_KEYS
        and trigger_type in ORDINARY_TRIGGER_TYPES
        and (condition_key.startswith("BUY") or condition_key.startswith("SELL"))
    )


def action_side_from_condition(payload: Mapping[str, Any]) -> str:
    condition_key = str(payload.get("condition_key") or "")
    trigger_type = str(payload.get("trigger_type") or "")
    if condition_key.startswith("BUY") or trigger_type.startswith("BUY"):
        return "buy"
    if condition_key.startswith("SELL") or trigger_type.startswith("SELL"):
        return "sell"
    return ""


def validate_provisional_source_row(row: Mapping[str, Any]) -> str | None:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
    if str(row.get("event_type") or "") != "TriggerMatched":
        return "unsupported_event_type"
    if not bool_value(payload.get("provisional")):
        return "not_provisional"
    condition_key = str(payload.get("condition_key") or "")
    signal_type = str(payload.get("signal_type") or "")
    if is_hint_payload(payload):
        if not str(payload.get("projection_run_id") or ""):
            return "missing_projection_run_id"
        if not str(payload.get("projection_id") or ""):
            return "missing_projection_id"
    elif is_ordinary_payload(payload):
        if not str(payload.get("source_metric_run_id") or ""):
            return "missing_source_metric_run_id"
        if not str(payload.get("selected_metric_id") or ""):
            return "missing_selected_metric_id"
        if not str(payload.get("selected_metric_time") or ""):
            return "missing_selected_metric_time"
    else:
        return "unsupported_condition_key"
    if signal_type not in {"B_BUY", "S_SELL"}:
        return "unsupported_signal_type"
    if action_side_from_condition(payload) == "buy" and signal_type != "B_BUY":
        return "condition_signal_mismatch"
    if action_side_from_condition(payload) == "sell" and signal_type != "S_SELL":
        return "condition_signal_mismatch"
    if str(row.get("asset_kind") or "") not in ACTION_FACT_TABLE_BY_ASSET_KIND:
        return "unsupported_asset_kind"
    if not str(row.get("identity_key") or ""):
        return "missing_identity_key"
    return None


def build_canonical_action_identity_key(
    *,
    for_trade_date: str,
    asset_kind: str,
    identity_key: str,
    signal_type: str,
    condition_key: str,
    action_type: str,
    selected_metric_time: str,
    action_mark: str | None,
) -> str:
    return join_dedup_parts(
        "N5_canonical_action_identity_v1",
        "for_trade_date",
        for_trade_date,
        "asset_kind",
        asset_kind,
        "identity_key",
        identity_key,
        "signal_type",
        signal_type,
        "condition_key",
        condition_key,
        "action_type",
        action_type,
        "selected_metric_time",
        selected_metric_time,
        "action_mark",
        action_mark or "none",
    )


def selected_metric_time_for_canonical_key(payload: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    return str(
        payload.get("selected_metric_time")
        or payload.get("trigger_time")
        or row.get("event_time")
        or payload.get("projection_id")
        or ""
    )


def build_action_bucket(payload: Mapping[str, Any], *, source_kind: str) -> str:
    if source_kind == "ordinary":
        return join_dedup_parts(
            "provisional",
            N3P_SOURCE_METRIC_KIND,
            payload.get("source_metric_run_id"),
            payload.get("selected_metric_id"),
        )
    return f"provisional:{payload.get('projection_run_id')}:{payload.get('projection_id')}"


def build_action_candidate(
    row: Mapping[str, Any],
    *,
    source_trigger_run: Mapping[str, Any],
    source_trigger_run_id: str,
    action_run_id: str,
    for_trade_date: str,
    allowed_source_trigger_run_ids: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
    candidate_source_trigger_run_id = resolve_candidate_source_trigger_run_id(
        row,
        payload,
        fallback_source_trigger_run_id=source_trigger_run_id,
        allowed_source_trigger_run_ids=allowed_source_trigger_run_ids,
    )
    signal_type = str(payload.get("signal_type") or "")
    business_action_type = "buy" if signal_type == "B_BUY" else "sell"
    fact_action_type = "buy_candidate" if business_action_type == "buy" else "sell_candidate"
    source_kind = classify_source_payload(payload)
    if source_kind == "ordinary":
        action_key = build_ordinary_action_key(
            action_run_id=action_run_id,
            source_trigger_event_id=str(row["event_id"]),
            source_metric_run_id=str(payload.get("source_metric_run_id") or ""),
            selected_metric_id=str(payload.get("selected_metric_id") or ""),
            selected_metric_time=str(payload.get("selected_metric_time") or ""),
            action_type=business_action_type,
            identity_key=str(row["identity_key"]),
            condition_key=str(payload.get("condition_key") or ""),
        )
    else:
        action_key = build_provisional_action_key(
            action_run_id=action_run_id,
            source_trigger_event_id=str(row["event_id"]),
            projection_run_id=str(payload.get("projection_run_id") or ""),
            projection_id=str(payload.get("projection_id") or ""),
            action_type=business_action_type,
            identity_key=str(row["identity_key"]),
            condition_key=str(payload.get("condition_key") or ""),
        )
    dedup_key = build_provisional_action_dedup_key(action_key=action_key)
    canonical_action_identity_key = build_canonical_action_identity_key(
        for_trade_date=for_trade_date,
        asset_kind=str(row["asset_kind"]),
        identity_key=str(row["identity_key"]),
        signal_type=signal_type,
        condition_key=str(payload.get("condition_key") or ""),
        action_type=business_action_type,
        selected_metric_time=selected_metric_time_for_canonical_key(payload, row),
        action_mark=None,
    )
    source_market_trace = build_source_market_trace(payload)
    trigger_period = str(payload.get("trigger_period") or "30m")
    candidate = {
        "action_run_id": action_run_id,
        "source_trigger_run_id": candidate_source_trigger_run_id,
        "source_trigger_event_id": str(row["event_id"]),
        "source_trigger_event_type": "TriggerMatched",
        "event_schema_version": str(row.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION),
        "source_trigger_match_id": payload.get("trigger_match_id") or payload.get("source_trigger_match_id"),
        "source_trigger_state_id": payload.get("trigger_state_id") or payload.get("source_trigger_state_id"),
        "source_condition_run_id": str(payload.get("source_condition_run_id") or source_trigger_run.get("source_condition_run_id") or ""),
        "source_market_data_run_id": payload.get("source_metric_run_id") or payload.get("projection_run_id"),
        "source_market_trace": source_market_trace,
        "for_trade_date": for_trade_date,
        "asset_kind": str(row["asset_kind"]),
        "identity_key": str(row["identity_key"]),
        "direction": str(payload.get("direction") or business_action_type),
        "signal_type": signal_type,
        "condition_key": str(payload.get("condition_key") or ""),
        "original_condition_key": str(payload.get("original_condition_key") or payload.get("condition_key") or ""),
        "trigger_period": trigger_period,
        "trigger_time": payload.get("trigger_time") or row.get("event_time"),
        "trigger_price": payload.get("trigger_price"),
        "trigger_mark_candidate": payload.get("trigger_mark_candidate"),
        "action_mark": None,
        "action_state": "eligible",
        "confirmation_status": "pending",
        "tracking_until": None,
        "last_checked_minute_label": None,
        "trace_json": build_trace_json(payload, canonical_action_identity_key=canonical_action_identity_key),
        "action_policy": PROVISIONAL_ACTION_POLICY,
        "business_action_type": business_action_type,
        "fact_action_type": fact_action_type,
        "source_kind": source_kind,
        "lane": "policy_pending" if source_kind == "ordinary" else "hint",
        "decision_status": "candidate",
        "data_quality_status": str(payload.get("data_quality_status") or "passed"),
        "closed_minute_required": False,
        "closed_minute_verified": False,
        "minute_context_status": "not_required",
        "action_bucket": build_action_bucket(payload, source_kind=source_kind),
        "canonical_action_identity_key": canonical_action_identity_key,
        "action_key": action_key,
        "dedup_key": dedup_key,
        "target_action_fact_table": ACTION_FACT_TABLE_BY_ASSET_KIND[str(row["asset_kind"])],
        "source_payload_json": build_source_payload_json(
            row,
            payload,
            business_action_type,
            fact_action_type,
            canonical_action_identity_key=canonical_action_identity_key,
        ),
        "event_time": row.get("event_time") or payload.get("trigger_time"),
    }
    return candidate


def resolve_candidate_source_trigger_run_id(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    fallback_source_trigger_run_id: str,
    allowed_source_trigger_run_ids: set[str] | frozenset[str] | None = None,
) -> str:
    candidate_source_trigger_run_id = str(
        row.get("source_run_id")
        or payload.get("run_id")
        or payload.get("source_trigger_run_id")
        or ""
    ).strip()
    if not candidate_source_trigger_run_id:
        raise ProvisionalActionEligibleBlocked("missing_candidate_source_trigger_run_id")
    if allowed_source_trigger_run_ids is not None and candidate_source_trigger_run_id not in allowed_source_trigger_run_ids:
        raise ProvisionalActionEligibleBlocked(
            "candidate_source_trigger_run_id_not_allowed:"
            f"{candidate_source_trigger_run_id}"
        )
    return candidate_source_trigger_run_id or fallback_source_trigger_run_id


def build_provisional_action_key(
    *,
    action_run_id: str,
    source_trigger_event_id: str,
    projection_run_id: str,
    projection_id: str,
    action_type: str,
    identity_key: str,
    condition_key: str,
) -> str:
    return join_dedup_parts(
        "N5_action",
        "provisional_actioneligible",
        "action_run_id",
        action_run_id,
        "source_trigger_event_id",
        source_trigger_event_id,
        "projection_run_id",
        projection_run_id,
        "projection_id",
        projection_id,
        "action_type",
        action_type,
        "identity_key",
        identity_key,
        "condition_key",
        condition_key,
    )


def build_ordinary_action_key(
    *,
    action_run_id: str,
    source_trigger_event_id: str,
    source_metric_run_id: str,
    selected_metric_id: str,
    selected_metric_time: str,
    action_type: str,
    identity_key: str,
    condition_key: str,
) -> str:
    return join_dedup_parts(
        "N5_action",
        "provisional_actioneligible",
        "action_run_id",
        action_run_id,
        "source_trigger_event_id",
        source_trigger_event_id,
        "source_metric_run_id",
        source_metric_run_id,
        "selected_metric_id",
        selected_metric_id,
        "selected_metric_time",
        selected_metric_time,
        "action_type",
        action_type,
        "identity_key",
        identity_key,
        "condition_key",
        condition_key,
    )


def build_provisional_action_dedup_key(*, action_key: str) -> str:
    return join_dedup_parts("N5_action", PROVISIONAL_ACTIONELIGIBLE_EVENT_TYPE, "action_key", action_key)


def build_source_market_trace(payload: Mapping[str, Any]) -> dict[str, Any]:
    if classify_source_payload(payload) == "ordinary":
        return {
            "source": "N4_provisional_ordinary_trigger_payload",
            "source_metric_kind": payload.get("source_metric_kind"),
            "source_metric_run_id": payload.get("source_metric_run_id"),
            "selected_metric_id": payload.get("selected_metric_id"),
            "selected_metric_time": payload.get("selected_metric_time"),
            "metric_time_label": payload.get("metric_time_label"),
            "metric_minute_label": payload.get("metric_minute_label"),
            "is_closed_1m": bool_value(payload.get("is_closed_1m")),
            "rule_proof": json_safe_value(payload.get("rule_proof") or {}),
            "trace": json_safe_value(payload.get("trace") or {}),
        }
    projection_trace = payload.get("projection_trace") if isinstance(payload.get("projection_trace"), Mapping) else {}
    return {
        "source": "N4_provisional_trigger_payload",
        "projection_run_id": payload.get("projection_run_id"),
        "projection_id": payload.get("projection_id"),
        "projection_30m_type": payload.get("projection_30m_type"),
        "trigger_mark_candidate": payload.get("trigger_mark_candidate"),
        "projection_trace": json_safe_value(dict(projection_trace)),
    }


def build_trace_json(payload: Mapping[str, Any], *, canonical_action_identity_key: str) -> dict[str, Any]:
    if classify_source_payload(payload) == "ordinary":
        return {
            "provisional": True,
            "action_confirmation_mode": PROVISIONAL_ACTION_CONFIRMATION_MODE,
            "eligibility_only": True,
            "source_fact_kind": N3P_SOURCE_METRIC_KIND,
            "source_metric_kind": payload.get("source_metric_kind"),
            "source_metric_run_id": payload.get("source_metric_run_id"),
            "selected_metric_id": payload.get("selected_metric_id"),
            "selected_metric_time": payload.get("selected_metric_time"),
            "metric_role": payload.get("metric_role"),
            "proof_owner": payload.get("proof_owner"),
            "proof_consumer": payload.get("proof_consumer"),
            "not_n5_final_proof": bool_value(payload.get("not_n5_final_proof")),
            "source_trigger_proof_kind": payload.get("source_trigger_proof_kind"),
            "source_trigger_proof_run_id": payload.get("source_trigger_proof_run_id"),
            "source_trigger_proof_metric_id": payload.get("source_trigger_proof_metric_id"),
            "source_trigger_proof_time": payload.get("source_trigger_proof_time"),
            "metric_time_label": payload.get("metric_time_label"),
            "metric_minute_label": payload.get("metric_minute_label"),
            "trigger_type": payload.get("trigger_type"),
            "trigger_mark_candidate": payload.get("trigger_mark_candidate"),
            "candidate_trigger_identity_key": payload.get("candidate_trigger_identity_key"),
            "rule_proof": json_safe_value(payload.get("rule_proof") or {}),
            "trace": json_safe_value(payload.get("trace") or {}),
            "closed_minute_proof": {
                "selected_metric_time": payload.get("selected_metric_time"),
                "metric_minute_label": payload.get("metric_minute_label"),
                "is_closed_1m": bool_value(payload.get("is_closed_1m")),
            },
            "canonical_action_identity_key": canonical_action_identity_key,
            "source_action_confirmation_metric_id": None,
        }
    return {
        "provisional": True,
        "action_confirmation_mode": PROVISIONAL_ACTION_CONFIRMATION_MODE,
        "eligibility_only": True,
        "source_fact_kind": "realtime_projection_metric",
        "projection_run_id": payload.get("projection_run_id"),
        "projection_id": payload.get("projection_id"),
        "projection_30m_flag": payload.get("projection_30m_flag"),
        "projection_30m_type": payload.get("projection_30m_type"),
        "trigger_mark_candidate": payload.get("trigger_mark_candidate"),
        "canonical_action_identity_key": canonical_action_identity_key,
        "source_action_confirmation_metric_id": None,
    }


def build_source_payload_json(
    row: Mapping[str, Any],
    payload: Mapping[str, Any],
    business_action_type: str,
    fact_action_type: str,
    *,
    canonical_action_identity_key: str,
) -> dict[str, Any]:
    source_payload = dict(payload)
    if is_hint_payload(source_payload) and not str(source_payload.get("trigger_type") or ""):
        source_payload["trigger_type"] = source_payload.get("condition_key")
    return json_safe_value(
        {
            **source_payload,
            "event_type": PROVISIONAL_ACTIONELIGIBLE_EVENT_TYPE,
            "provisional": True,
            "action_confirmation_mode": PROVISIONAL_ACTION_CONFIRMATION_MODE,
            "eligibility_only": True,
            "source_trigger_event_id": row.get("event_id"),
            "source_trigger_run_id": row.get("source_run_id"),
            "source_action_confirmation_metric_id": None,
            "action_state": "eligible",
            "confirmation_status": "pending",
            "action_type": business_action_type,
            "fact_action_type": fact_action_type,
            "canonical_action_identity_key": canonical_action_identity_key,
        }
    )


def build_action_run_row(
    *,
    source_trigger_run: Mapping[str, Any],
    source_trigger_run_id: str,
    action_run_id: str,
    for_trade_date: str,
    consumer_name: str,
    trigger_outbox_row_count: int,
    action_count: int,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "source_condition_run_id": source_trigger_run.get("source_condition_run_id"),
        "for_trade_date": for_trade_date,
        "mode": "execute",
        "status": "passed",
        "p0_count": 0,
        "p1_count": 0,
        "p2_count": 0,
        "trigger_outbox_row_count": trigger_outbox_row_count,
        "action_candidate_row_count": action_count,
        "action_fact_row_count": action_count,
        "action_event_outbox_count": action_count,
        "position_event_row_count": 0,
        "generated_by": PROVISIONAL_GENERATED_BY,
        "market_data_pulled": False,
        "trigger_layer_mutated": False,
        "user_layer_touched": False,
        "voice_touched": False,
        "sim_touched": False,
        "real_trade_touched": False,
        "worker_started": False,
        "consumer_checkpoint_updated": False,
        "common_event_inbox_updated": False,
        "raw_json": {
            "provisional": True,
            "mode_detail": "provisional_actioneligible_only",
            "consumer_name": consumer_name,
            "source_trigger_run_id": source_trigger_run_id,
            "action_confirmation_mode": PROVISIONAL_ACTION_CONFIRMATION_MODE,
            "writes_inbox_or_checkpoint": False,
            "uses_formal_action_confirmation_metric": False,
        },
        "started_at": created_at,
        "finished_at": created_at,
    }


def build_quality_item(
    *,
    source_trigger_run: Mapping[str, Any],
    source_trigger_run_id: str,
    action_run_id: str,
    for_trade_date: str,
    trigger_outbox_row_count: int,
    eligible_count: int,
    noop_reason_counts: Mapping[str, int],
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "for_trade_date": for_trade_date,
        "data_domain": "common",
        "layer_scope": "action_fact",
        "table_name": "common_event_outbox",
        "gate_code": "n5_provisional_actioneligible_summary",
        "gate_name": "N5 provisional ActionEligible summary",
        "severity": "P2",
        "status": "passed",
        "expected_value": "provisional TriggerMatched creates ActionEligible only",
        "actual_value": f"eligible={eligible_count}",
        "identity_key": None,
        "details": {
            "provisional": True,
            "source_trigger_status": source_trigger_run.get("status"),
            "trigger_outbox_row_count": trigger_outbox_row_count,
            "eligible_count": eligible_count,
            "noop_reason_counts": dict(noop_reason_counts),
            "action_confirmation_mode": PROVISIONAL_ACTION_CONFIRMATION_MODE,
        },
        "created_at": created_at,
    }


def build_action_fact_row(candidate: Mapping[str, Any], *, created_at: datetime) -> dict[str, Any]:
    return {
        "run_id": candidate["action_run_id"],
        "source_trigger_run_id": candidate["source_trigger_run_id"],
        "source_trigger_event_id": candidate["source_trigger_event_id"],
        "source_trigger_event_type": candidate["source_trigger_event_type"],
        "event_schema_version": candidate["event_schema_version"],
        "source_trigger_match_id": candidate.get("source_trigger_match_id"),
        "trigger_state_id": candidate.get("source_trigger_state_id"),
        "source_trigger_state_id": candidate.get("source_trigger_state_id"),
        "source_condition_run_id": candidate.get("source_condition_run_id"),
        "source_market_data_run_id": candidate.get("source_market_data_run_id"),
        "source_market_trace": candidate.get("source_market_trace") or {},
        "for_trade_date": candidate["for_trade_date"],
        "asset_kind": candidate["asset_kind"],
        "identity_key": candidate["identity_key"],
        "direction": candidate["direction"],
        "signal_type": candidate["signal_type"],
        "condition_key": candidate["condition_key"],
        "original_condition_key": candidate["original_condition_key"],
        "trigger_period": candidate["trigger_period"],
        "trigger_time": candidate.get("trigger_time"),
        "trigger_price": candidate.get("trigger_price"),
        "trigger_mark_candidate": candidate.get("trigger_mark_candidate"),
        "action_mark": None,
        "action_state": "eligible",
        "confirmation_status": "pending",
        "tracking_until": None,
        "last_checked_minute_label": None,
        "trace_json": candidate.get("trace_json") or {},
        "action_policy": PROVISIONAL_ACTION_POLICY,
        "action_type": candidate["fact_action_type"],
        "lane": candidate["lane"],
        "decision_status": candidate["decision_status"],
        "data_quality_status": candidate["data_quality_status"],
        "closed_minute_required": False,
        "closed_minute_verified": False,
        "minute_context_status": "not_required",
        "action_bucket": candidate["action_bucket"],
        "action_key": candidate["action_key"],
        "dedup_key": candidate["dedup_key"],
        "source_payload_json": candidate["source_payload_json"],
        "raw_json": {
            "provisional": True,
            "plan": json_safe_value(dict(candidate)),
        },
        "created_at": created_at,
        "updated_at": created_at,
        "target_action_fact_table": candidate["target_action_fact_table"],
    }


def build_action_event_payload(candidate: Mapping[str, Any], *, source_action_fact_id: int | None) -> dict[str, Any]:
    source_payload = candidate.get("source_payload_json") if isinstance(candidate.get("source_payload_json"), Mapping) else {}
    source_kind = classify_candidate_source(candidate, source_payload)
    period_passthrough = build_period_passthrough(candidate, source_payload, source_kind=source_kind)
    period_trace = source_payload.get("period_trigger_baseline_trace")
    if not isinstance(period_trace, Mapping) or not period_trace:
        period_trace = {
            "source": "provisional_actioneligible",
            "source_kind": source_kind,
            "primary_trigger_period": period_passthrough.get("primary_trigger_period"),
        }
    trigger_price = candidate.get("trigger_price")
    trigger_price_source = "n4_trigger_payload"
    if trigger_price in (None, ""):
        trigger_price = "0"
        trigger_price_source = "not_available_in_n4p_payload"
    return json_safe_value(
        {
            **dict(source_payload),
            "source_action_fact_table": candidate["target_action_fact_table"],
            "source_action_fact_id": source_action_fact_id,
            "action_key": candidate["action_key"],
            "dedup_key": candidate["dedup_key"],
            "n4_trigger_event_id": candidate["source_trigger_event_id"],
            "trigger_price": trigger_price,
            "trigger_price_source": trigger_price_source,
            "trigger_period": period_passthrough["trigger_period"],
            "triggered_periods": period_passthrough["triggered_periods"],
            "all_trigger_periods": period_passthrough["all_trigger_periods"],
            "primary_trigger_period": period_passthrough["primary_trigger_period"],
            "trigger_kind": period_passthrough["trigger_kind"],
            "period_trigger_baseline_trace": dict(period_trace),
            "baseline_source": (
                "provisional_n3p_realtime_action_confirmation_metric"
                if source_kind == "ordinary"
                else "provisional_b2_realtime_projection"
            ),
            "provisional": True,
            "action_confirmation_mode": PROVISIONAL_ACTION_CONFIRMATION_MODE,
            "eligibility_only": True,
            "source_action_confirmation_metric_id": None,
            "projection_run_id": source_payload.get("projection_run_id"),
            "projection_id": source_payload.get("projection_id"),
            "source_metric_kind": source_payload.get("source_metric_kind"),
            "source_metric_run_id": source_payload.get("source_metric_run_id"),
            "selected_metric_id": source_payload.get("selected_metric_id"),
            "selected_metric_time": source_payload.get("selected_metric_time"),
            "metric_time_label": source_payload.get("metric_time_label"),
            "metric_minute_label": source_payload.get("metric_minute_label"),
            "is_closed_1m": bool_value(source_payload.get("is_closed_1m")),
            "trigger_type": source_payload.get("trigger_type"),
            "rule_proof": source_payload.get("rule_proof"),
            "trace": source_payload.get("trace"),
            "candidate_trigger_identity_key": source_payload.get("candidate_trigger_identity_key"),
            "canonical_action_identity_key": candidate.get("canonical_action_identity_key"),
            "trigger_mark_candidate": candidate.get("trigger_mark_candidate"),
            "projection_30m_type": source_payload.get("projection_30m_type"),
            "event_type": PROVISIONAL_ACTIONELIGIBLE_EVENT_TYPE,
            "action_type": candidate["business_action_type"],
            "fact_action_type": candidate["fact_action_type"],
        }
    )


def build_period_passthrough(
    candidate: Mapping[str, Any],
    source_payload: Mapping[str, Any],
    *,
    source_kind: str,
) -> dict[str, Any]:
    if source_kind == "hint":
        return {
            "trigger_kind": "hint",
            "trigger_period": "30m",
            "triggered_periods": [],
            "all_trigger_periods": [],
            "primary_trigger_period": None,
        }

    triggered_periods = formal_period_values(source_payload.get("triggered_periods"))
    all_trigger_periods = formal_period_values(source_payload.get("all_trigger_periods"))
    primary = str(source_payload.get("primary_trigger_period") or "").strip()
    if primary not in FORMAL_TRIGGER_PERIODS:
        primary = infer_primary_formal_period(source_payload)
    if not triggered_periods:
        triggered_periods = infer_triggered_formal_periods(source_payload, primary=primary)
    if not all_trigger_periods:
        all_trigger_periods = list(triggered_periods)
    if primary not in FORMAL_TRIGGER_PERIODS:
        primary = triggered_periods[0] if triggered_periods else "D"
    return {
        "trigger_kind": "trigger",
        "trigger_period": primary,
        "triggered_periods": triggered_periods,
        "all_trigger_periods": all_trigger_periods,
        "primary_trigger_period": primary,
    }


def formal_period_values(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    output: list[str] = []
    for item in values:
        period = str(item or "").strip()
        if period in FORMAL_TRIGGER_PERIODS and period not in output:
            output.append(period)
    return output


def infer_primary_formal_period(payload: Mapping[str, Any]) -> str:
    for value in (
        payload.get("trigger_period"),
        payload.get("primary_trigger_period"),
        condition_key_period(payload),
    ):
        period = str(value or "").strip()
        if period in FORMAL_TRIGGER_PERIODS:
            return period
    return "D"


def infer_triggered_formal_periods(payload: Mapping[str, Any], *, primary: str) -> list[str]:
    trigger_type = str(payload.get("trigger_type") or "")
    condition_key = str(payload.get("condition_key") or "")
    if trigger_type.endswith(":FULL") or condition_key.endswith(":FULL"):
        return list(FORMAL_TRIGGER_PERIODS)
    return [primary if primary in FORMAL_TRIGGER_PERIODS else "D"]


def condition_key_period(payload: Mapping[str, Any]) -> str:
    condition_key = str(payload.get("condition_key") or "")
    for token in reversed(condition_key.split(":")):
        if token in FORMAL_TRIGGER_PERIODS:
            return token
    return ""


def build_action_envelope(candidate: Mapping[str, Any], *, source_action_fact_id: int | None, created_at: datetime):
    payload = build_action_event_payload(candidate, source_action_fact_id=source_action_fact_id)
    trigger_period = str(payload.get("trigger_period") or candidate["trigger_period"])
    return build_n5_action_event(
        event_type=PROVISIONAL_ACTIONELIGIBLE_EVENT_TYPE,
        asset_kind=str(candidate["asset_kind"]),
        identity_key=str(candidate["identity_key"]),
        trade_date=str(candidate["for_trade_date"]),
        event_time=parse_event_time(candidate.get("event_time") or candidate.get("trigger_time")),
        action_run_id=str(candidate["action_run_id"]),
        source_trigger_event_id=str(candidate["source_trigger_event_id"]),
        source_trigger_run_id=str(candidate["source_trigger_run_id"]),
        source_trigger_state_id=candidate.get("source_trigger_state_id"),
        source_trigger_match_id=candidate.get("source_trigger_match_id"),
        source_condition_run_id=str(candidate.get("source_condition_run_id") or ""),
        direction=str(candidate["direction"]),
        signal_type=str(candidate["signal_type"]),
        condition_key=str(candidate["condition_key"]),
        original_condition_key=str(candidate.get("original_condition_key") or candidate["condition_key"]),
        trigger_period=trigger_period,
        action_mark=None,
        action_state="eligible",
        confirmation_status="pending",
        action_policy=PROVISIONAL_ACTION_POLICY,
        eligibility_reason="provisional_trigger_matched",
        trace_json=candidate.get("trace_json") or {},
        action_type=str(candidate["business_action_type"]),
        lane=str(candidate["lane"]),
        data_quality_status=str(candidate["data_quality_status"]),
        source_market_data_run_id=str(candidate.get("source_market_data_run_id") or ""),
        source_market_trace=candidate.get("source_market_trace") or {},
        payload=payload,
        created_at=created_at,
    )


def build_common_action_event_row(
    candidate: Mapping[str, Any],
    *,
    source_action_fact_id: int | None,
    created_at: datetime,
) -> dict[str, Any]:
    envelope = build_action_envelope(candidate, source_action_fact_id=source_action_fact_id, created_at=created_at)
    payload_trigger_period = envelope.payload_json.get("trigger_period")
    return {
        "event_id": envelope.event_id,
        "event_schema_version": envelope.event_schema_version,
        "run_id": candidate["action_run_id"],
        "source_trigger_run_id": candidate["source_trigger_run_id"],
        "source_trigger_event_id": candidate["source_trigger_event_id"],
        "source_trigger_match_id": candidate.get("source_trigger_match_id"),
        "source_trigger_state_id": candidate.get("source_trigger_state_id"),
        "source_condition_run_id": candidate.get("source_condition_run_id"),
        "source_market_data_run_id": candidate.get("source_market_data_run_id"),
        "source_market_trace": candidate.get("source_market_trace") or {},
        "source_action_fact_table": candidate["target_action_fact_table"],
        "source_action_fact_id": source_action_fact_id,
        "for_trade_date": candidate["for_trade_date"],
        "asset_kind": candidate["asset_kind"],
        "identity_key": candidate["identity_key"],
        "direction": candidate["direction"],
        "signal_type": candidate["signal_type"],
        "condition_key": candidate["condition_key"],
        "original_condition_key": candidate["original_condition_key"],
        "trigger_period": payload_trigger_period or candidate["trigger_period"],
        "trigger_mark_candidate": candidate.get("trigger_mark_candidate"),
        "action_mark": None,
        "action_state": "eligible",
        "confirmation_status": "pending",
        "tracking_until": None,
        "last_checked_minute_label": None,
        "trace_json": candidate.get("trace_json") or {},
        "action_policy": PROVISIONAL_ACTION_POLICY,
        "event_type": PROVISIONAL_ACTIONELIGIBLE_EVENT_TYPE,
        "action_type": candidate["fact_action_type"],
        "lane": candidate["lane"],
        "data_quality_status": candidate["data_quality_status"],
        "action_key": candidate["action_key"],
        "dedup_key": candidate["dedup_key"],
        "partition_key": candidate["identity_key"],
        "payload_json": envelope.payload_json,
        "created_at": created_at,
    }


def build_action_outbox_record(
    candidate: Mapping[str, Any],
    *,
    source_action_fact_id: int | None,
    created_at: datetime,
) -> dict[str, Any]:
    envelope = build_action_envelope(candidate, source_action_fact_id=source_action_fact_id, created_at=created_at)
    return envelope.as_record()


def execute_provisional_actioneligible_transaction(*, dsn: str, execute_plan: Mapping[str, Any]) -> dict[str, int]:
    action_run_id = str(execute_plan.get("action_run_id") or "")
    with audited_n5_action_connect(
        dsn,
        stage_id="n5_provisional_actioneligible_execute",
        source_run_id=action_run_id,
        readonly_expected=False,
        bypass_classification="explicit_bypass_n5_provisional_actioneligible_execute",
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            insert_action_run(cur, execute_plan["writes"]["common_action_run"][0])
            insert_quality_items(cur, execute_plan["writes"]["common_action_quality_item"])
            fact_count = Counter()
            event_count = 0
            outbox_count = 0
            candidates = candidate_rows_from_plan(execute_plan)
            for candidate in candidates:
                fact_row = build_action_fact_row(candidate, created_at=utc_now())
                action_fact_id = insert_action_fact(cur, fact_row)
                event_row = build_common_action_event_row(candidate, source_action_fact_id=action_fact_id, created_at=utc_now())
                insert_common_action_event(cur, event_row)
                outbox_record = build_action_outbox_record(candidate, source_action_fact_id=action_fact_id, created_at=utc_now())
                insert_common_event_outbox(cur, outbox_record)
                fact_count[str(candidate["target_action_fact_table"])] += 1
                event_count += 1
                outbox_count += 1
            conn.commit()
    return {
        "common_action_run": 1,
        "common_action_quality_item": len(execute_plan["writes"]["common_action_quality_item"]),
        "stock_action_fact": fact_count["stock_action_fact"],
        "index_action_fact": fact_count["index_action_fact"],
        "board_action_fact": fact_count["board_action_fact"],
        "common_action_event": event_count,
        "common_event_outbox": outbox_count,
    }


def candidate_rows_from_plan(execute_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table_name in ("stock_action_fact", "index_action_fact", "board_action_fact"):
        for fact_row in execute_plan["writes"][table_name]:
            source_payload = fact_row.get("source_payload_json") if isinstance(fact_row.get("source_payload_json"), Mapping) else {}
            rows.append(
                {
                    **dict(fact_row),
                    "action_run_id": fact_row["run_id"],
                    "business_action_type": source_payload.get("action_type"),
                    "fact_action_type": fact_row["action_type"],
                    "target_action_fact_table": table_name,
                    "event_time": fact_row.get("trigger_time"),
                }
            )
    return rows


def insert_action_run(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_action_run (
          run_id, source_trigger_run_id, source_condition_run_id, for_trade_date,
          mode, status, p0_count, p1_count, p2_count, trigger_outbox_row_count,
          action_candidate_row_count, action_fact_row_count, action_event_outbox_count,
          position_event_row_count, generated_by, market_data_pulled,
          trigger_layer_mutated, user_layer_touched, voice_touched, sim_touched,
          real_trade_touched, worker_started, consumer_checkpoint_updated,
          common_event_inbox_updated, raw_json, started_at, finished_at
        )
        VALUES (
          %(run_id)s, %(source_trigger_run_id)s, %(source_condition_run_id)s, %(for_trade_date)s,
          %(mode)s, %(status)s, %(p0_count)s, %(p1_count)s, %(p2_count)s, %(trigger_outbox_row_count)s,
          %(action_candidate_row_count)s, %(action_fact_row_count)s, %(action_event_outbox_count)s,
          %(position_event_row_count)s, %(generated_by)s, %(market_data_pulled)s,
          %(trigger_layer_mutated)s, %(user_layer_touched)s, %(voice_touched)s, %(sim_touched)s,
          %(real_trade_touched)s, %(worker_started)s, %(consumer_checkpoint_updated)s,
          %(common_event_inbox_updated)s, %(raw_json)s, %(started_at)s, %(finished_at)s
        )
        """,
        {**dict(row), "raw_json": Jsonb(json_safe_value(row.get("raw_json") or {}))},
    )


def insert_quality_items(cur: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO common_action_quality_item (
              run_id, source_trigger_run_id, for_trade_date, data_domain, layer_scope,
              table_name, gate_code, gate_name, severity, status, expected_value,
              actual_value, identity_key, details, created_at
            )
            VALUES (
              %(run_id)s, %(source_trigger_run_id)s, %(for_trade_date)s, %(data_domain)s, %(layer_scope)s,
              %(table_name)s, %(gate_code)s, %(gate_name)s, %(severity)s, %(status)s, %(expected_value)s,
              %(actual_value)s, %(identity_key)s, %(details)s, %(created_at)s
            )
            """,
            {**dict(row), "details": Jsonb(json_safe_value(row.get("details") or {}))},
        )


def insert_action_fact(cur: Any, row: Mapping[str, Any]) -> int:
    table_name = str(row["target_action_fact_table"])
    identity_column = IDENTITY_COLUMN_BY_ACTION_FACT_TABLE[table_name]
    columns = [
        "run_id",
        "source_trigger_run_id",
        "source_trigger_event_id",
        "source_trigger_event_type",
        "event_schema_version",
        "source_trigger_match_id",
        "trigger_state_id",
        "source_trigger_state_id",
        "source_condition_run_id",
        "source_market_data_run_id",
        "source_market_trace",
        "for_trade_date",
        "asset_kind",
        "identity_key",
        identity_column,
        "direction",
        "signal_type",
        "condition_key",
        "original_condition_key",
        "trigger_period",
        "trigger_time",
        "trigger_price",
        "trigger_mark_candidate",
        "action_mark",
        "action_state",
        "confirmation_status",
        "tracking_until",
        "last_checked_minute_label",
        "trace_json",
        "action_policy",
        "action_type",
        "lane",
        "decision_status",
        "data_quality_status",
        "closed_minute_required",
        "closed_minute_verified",
        "minute_context_status",
        "action_bucket",
        "action_key",
        "dedup_key",
        "source_payload_json",
        "raw_json",
        "created_at",
        "updated_at",
    ]
    params = dict(row)
    params[identity_column] = row["identity_key"]
    params["source_market_trace"] = Jsonb(json_safe_value(row.get("source_market_trace") or {}))
    params["trace_json"] = Jsonb(json_safe_value(row.get("trace_json") or {}))
    params["source_payload_json"] = Jsonb(json_safe_value(row.get("source_payload_json") or {}))
    params["raw_json"] = Jsonb(json_safe_value(row.get("raw_json") or {}))
    placeholders = ", ".join([f"%({column})s" for column in columns])
    cur.execute(
        f"""
        INSERT INTO {table_name} ({", ".join(columns)})
        VALUES ({placeholders})
        RETURNING action_fact_id
        """,
        params,
    )
    fetched = cur.fetchone()
    if isinstance(fetched, Mapping):
        return int(fetched["action_fact_id"])
    return int(fetched[0])


def insert_common_action_event(cur: Any, row: Mapping[str, Any]) -> None:
    columns = [
        "event_id",
        "event_schema_version",
        "run_id",
        "source_trigger_run_id",
        "source_trigger_event_id",
        "source_trigger_match_id",
        "source_trigger_state_id",
        "source_condition_run_id",
        "source_market_data_run_id",
        "source_market_trace",
        "source_action_fact_table",
        "source_action_fact_id",
        "for_trade_date",
        "asset_kind",
        "identity_key",
        "direction",
        "signal_type",
        "condition_key",
        "original_condition_key",
        "trigger_period",
        "trigger_mark_candidate",
        "action_mark",
        "action_state",
        "confirmation_status",
        "tracking_until",
        "last_checked_minute_label",
        "trace_json",
        "action_policy",
        "event_type",
        "action_type",
        "lane",
        "data_quality_status",
        "action_key",
        "dedup_key",
        "partition_key",
        "payload_json",
        "created_at",
    ]
    params = dict(row)
    params["source_market_trace"] = Jsonb(json_safe_value(row.get("source_market_trace") or {}))
    params["trace_json"] = Jsonb(json_safe_value(row.get("trace_json") or {}))
    params["payload_json"] = Jsonb(json_safe_value(row.get("payload_json") or {}))
    placeholders = ", ".join([f"%({column})s" for column in columns])
    cur.execute(
        f"""
        INSERT INTO common_action_event ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        params,
    )


def insert_common_event_outbox(cur: Any, row: Mapping[str, Any]) -> None:
    columns = [
        "event_id",
        "event_type",
        "event_schema_version",
        "trade_date",
        "asset_kind",
        "identity_key",
        "event_time",
        "source_layer",
        "source_run_id",
        "dedup_key",
        "partition_key",
        "payload_json",
        "created_at",
    ]
    params = dict(row)
    params["payload_json"] = Jsonb(json_safe_value(row.get("payload_json") or {}))
    placeholders = ", ".join([f"%({column})s" for column in columns])
    cur.execute(
        f"""
        INSERT INTO common_event_outbox ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        params,
    )


def run_provisional_actioneligible_once(
    *,
    dsn: str,
    source_trigger_run_id: str,
    action_run_id: str,
    for_trade_date: str,
    consumer_name: str,
    execute: bool,
    user_confirmed: bool,
    json_report_path: str | Path | None = None,
    markdown_report_path: str | Path | None = None,
    rollback_sql_path: str | Path | None = None,
) -> dict[str, Any]:
    if execute:
        assert_provisional_actioneligible_execute_confirmed(execute=execute, user_confirmed=user_confirmed)
    outbox_rows, source_trigger_run = fetch_source_trigger_outbox_rows(dsn, source_trigger_run_id)
    target_counts = fetch_target_counts(dsn, action_run_id)
    plan = build_provisional_actioneligible_plan(
        source_trigger_run=source_trigger_run,
        source_trigger_run_id=source_trigger_run_id,
        action_run_id=action_run_id,
        for_trade_date=for_trade_date,
        consumer_name=consumer_name,
        outbox_rows=outbox_rows,
        target_counts=target_counts,
    )
    write_counts: dict[str, int] | None = None
    result = "PREFLIGHT_PASS"
    if execute:
        write_counts = execute_provisional_actioneligible_transaction(dsn=dsn, execute_plan=plan)
        result = "EXECUTED"
    report = {
        "result": result,
        "source_trigger_run_id": source_trigger_run_id,
        "action_run_id": action_run_id,
        "for_trade_date": for_trade_date,
        "execute": execute,
        "candidate_count": plan.get("candidate_count"),
        "eligible_count": plan.get("eligible_count"),
        "noop_count": plan.get("noop_count"),
        "noop_reason_counts": plan.get("noop_reason_counts"),
        "event_counts": plan.get("event_counts"),
        "write_counts": write_counts or plan.get("write_counts"),
        "side_effect_boundary": plan.get("event_model"),
        "forbidden_write_counts": plan.get("forbidden_write_counts"),
    }
    if rollback_sql_path is not None:
        write_text(rollback_sql_path, build_provisional_actioneligible_rollback_sql(action_run_id))
        report["rollback_sql_path"] = str(rollback_sql_path)
    if json_report_path is not None:
        write_json(json_report_path, report)
    if markdown_report_path is not None:
        write_text(markdown_report_path, render_report_markdown(report))
    return report


def fetch_source_trigger_outbox_rows(dsn: str, source_trigger_run_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_provisional_actioneligible_source_fetch",
        source_run_id=source_trigger_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM common_trigger_run WHERE run_id = %s", (source_trigger_run_id,))
        trigger_run = cur.fetchone()
        if not trigger_run:
            raise ProvisionalActionEligibleBlocked(f"source trigger run missing: {source_trigger_run_id}")
        cur.execute(
            """
            SELECT *
            FROM common_event_outbox
            WHERE source_layer = 'N4_trigger'
              AND source_run_id = %s
              AND event_type = 'TriggerMatched'
            ORDER BY event_time, event_id
            """,
            (source_trigger_run_id,),
        )
        return [dict(row) for row in cur.fetchall()], dict(trigger_run)


def fetch_target_counts(dsn: str, action_run_id: str) -> dict[str, int]:
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_provisional_actioneligible_target_absence",
        source_run_id=action_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        counts: dict[str, int] = {}
        for table_name in (
            "common_action_run",
            "common_action_quality_item",
            "stock_action_fact",
            "index_action_fact",
            "board_action_fact",
            "common_action_event",
        ):
            cur.execute(f"SELECT count(*) AS row_count FROM {table_name} WHERE run_id = %s", (action_run_id,))
            counts[table_name] = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*) AS row_count
            FROM common_event_outbox
            WHERE source_layer = %s AND source_run_id = %s
            """,
            (N5_SOURCE_LAYER, action_run_id),
        )
        counts["common_event_outbox"] = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*) AS row_count
            FROM common_event_inbox
            WHERE payload_json->>'run_id' = %s
               OR payload_json->>'action_run_id' = %s
               OR raw_json->>'run_id' = %s
               OR raw_json->>'action_run_id' = %s
            """,
            (action_run_id, action_run_id, action_run_id, action_run_id),
        )
        counts["common_event_inbox"] = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*) AS row_count
            FROM common_event_consumer_checkpoint
            WHERE checkpoint_payload->>'run_id' = %s
               OR checkpoint_payload->>'action_run_id' = %s
            """,
            (action_run_id, action_run_id),
        )
        counts["common_event_consumer_checkpoint"] = int(cur.fetchone()["row_count"])
        return counts


def build_provisional_actioneligible_rollback_sql(action_run_id: str) -> str:
    escaped = action_run_id.replace("'", "''")
    return f"""-- N5 provisional ActionEligible rollback for {escaped}
DO $$
DECLARE
  v_run_id text := '{escaped}';
BEGIN
  DELETE FROM common_event_outbox WHERE source_layer = 'N5_action' AND source_run_id = v_run_id;
  DELETE FROM common_action_event WHERE run_id = v_run_id;
  DELETE FROM stock_action_fact WHERE run_id = v_run_id;
  DELETE FROM index_action_fact WHERE run_id = v_run_id;
  DELETE FROM board_action_fact WHERE run_id = v_run_id;
  DELETE FROM common_action_quality_item WHERE run_id = v_run_id;
  DELETE FROM common_action_run WHERE run_id = v_run_id;
END $$;
"""


def render_report_markdown(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N5 Provisional ActionEligible Report",
            "",
            f"- result: {report.get('result')}",
            f"- source_trigger_run_id: {report.get('source_trigger_run_id')}",
            f"- action_run_id: {report.get('action_run_id')}",
            f"- candidate_count: {report.get('candidate_count')}",
            f"- eligible_count: {report.get('eligible_count')}",
            f"- event_counts: {report.get('event_counts')}",
            f"- writes_inbox_or_checkpoint: {(report.get('side_effect_boundary') or {}).get('writes_inbox_or_checkpoint')}",
            "",
        ]
    )


def _require_passed_source_trigger_run(run: Mapping[str, Any], *, source_trigger_run_id: str) -> None:
    if str(run.get("run_id") or "") != source_trigger_run_id:
        raise ProvisionalActionEligibleBlocked("source trigger run lineage mismatch")
    if str(run.get("status") or "") != "passed":
        raise ProvisionalActionEligibleBlocked(f"source trigger run status must be passed: {run.get('status')}")


def _assert_target_absent(target_counts: Mapping[str, int]) -> None:
    existing = {name: int(count) for name, count in target_counts.items() if int(count) > 0}
    if existing:
        raise ProvisionalActionEligibleBlocked(f"BLOCKED_TARGET_NOT_EMPTY: target exists for action_run_id: {existing}")


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y"}
    return bool(value)


def parse_event_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return utc_now()
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe_value(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: str | Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
