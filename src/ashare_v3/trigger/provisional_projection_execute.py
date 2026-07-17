"""N4 provisional B2 TriggerMatched execute contract.

This module is intentionally isolated from the legacy projection matcher
execute route. It reads trigger context plus N3 B2 realtime projection facts,
builds provisional TriggerMatched rows, and writes only N4 trigger facts and
outbox when an explicitly confirmed runner calls the transaction function.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.events.ids import build_stable_event_id, join_dedup_parts
from ashare_v3.events.models import (
    DEFAULT_EVENT_SCHEMA_VERSION,
    EventEnvelope,
    N4_SOURCE_LAYER,
    utc_now,
    validate_event_envelope,
)
from ashare_v3.trigger.projection_matcher import (
    HINT_PROJECTION_TABLE_CONFIG,
    is_hint_1m_projection_run_id,
    normalize_context_row,
    normalize_hint_projection_row,
)
from ashare_v3.trigger.provisional_projection_matcher import (
    build_provisional_projection_matcher_plans,
    summarize_provisional_projection_matcher_plans,
)
from ashare_v3.trigger.provisional_trigger_lifecycle import (
    TRIGGER_MATCHED_EVENT_TYPE,
    TRIGGER_PENDING_MARKET_DATA_EVENT_TYPE,
    TRIGGER_STATE_CHANGED_EVENT_TYPE,
    build_lifecycle_output_plans,
    lifecycle_state_key,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect, audited_n4_trigger_connect


PROVISIONAL_ALLOWED_WRITE_TABLES = frozenset(
    {
        "common_trigger_run",
        "common_trigger_quality_item",
        "common_trigger_state",
        "common_trigger_match",
        "common_event_outbox",
    }
)
PROVISIONAL_FORBIDDEN_WRITE_TABLES = frozenset(
    {
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        "common_action_run",
        "common_action_event",
        "stock_action_fact",
        "index_action_fact",
        "board_action_fact",
        "user_card_projection",
        "user_voice_delivery",
        "user_device_ack",
        "sim_projection",
        "real_trade_order",
    }
)
PROVISIONAL_ROLLBACK_DOWNSTREAM_GUARD_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_action_run",
    "common_action_event",
    "common_action_quality_item",
    "common_action_tracking_state",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "user_signal_card_projection",
    "user_signal_projection_event",
    "user_notification_queue",
    "user_card_projection",
    "user_voice_delivery",
    "user_device_ack",
    "sim_projection",
    "sim_account",
    "sim_order",
    "sim_trade",
    "sim_position",
    "n6_virtual_account",
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_position",
    "real_trade_order",
    "voice_delivery",
    "mobile_push",
)
PROVISIONAL_TRIGGER_EVENT_TYPE = TRIGGER_MATCHED_EVENT_TYPE
PROVISIONAL_PENDING_EVENT_TYPE = TRIGGER_PENDING_MARKET_DATA_EVENT_TYPE
PROVISIONAL_STATE_CHANGED_EVENT_TYPE = TRIGGER_STATE_CHANGED_EVENT_TYPE
PROVISIONAL_SOURCE_EVENT_TYPE = "MarketSnapshotUpdated"
PROVISIONAL_TRIGGER_PERIOD = "30m"
DEFAULT_GENERATED_BY = "n4_provisional_b2_projection_execute_v1"
DEFAULT_SOURCE_VARIANT = "default"
LEGACY_V1_SOURCE_VARIANT = "legacy_v1"
LIVE_CURRENT_1M_SOURCE_VARIANT = "live_current_1m"
LIVE_CURRENT_1M_UNIFIED_PAYLOAD_V1_SOURCE_VARIANT = "live_current_1m_unified_payload_v1"
HINT_V2_ASSET_SCOPE = "asset_index_board"
HINT_V2_PROOF_KIND = "index_board_1m_hint_projection_v1"
HINT_V2_MIDDAY_BRIDGE_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"
BASELINE_MODE_NO_PREVIOUS = "no_previous_baseline"
BASELINE_MODE_EXACT_HINT_PREVIOUS = "exact_hint_previous_baseline"
BASELINE_FAMILY_NONE = "none"
BASELINE_FAMILY_HINT_PROJECTION = "hint_projection"
BASELINE_FAMILY_IMPLICIT_PROJECTION = "implicit_projection"
BLOCKED_PREVIOUS_BASELINE_POLICY_UNSAFE = "BLOCKED_PREVIOUS_BASELINE_POLICY_UNSAFE"
ALLOWED_HINT_V2_PROOF_KINDS = frozenset(
    {
        HINT_V2_PROOF_KIND,
        HINT_V2_MIDDAY_BRIDGE_PROOF_KIND,
    }
)
ALLOWED_SOURCE_VARIANTS = frozenset(
    {
        DEFAULT_SOURCE_VARIANT,
        LIVE_CURRENT_1M_SOURCE_VARIANT,
        LIVE_CURRENT_1M_UNIFIED_PAYLOAD_V1_SOURCE_VARIANT,
    }
)
ATOMIC_RULE_SUFFIX_RE = re.compile(r"^atomic_rule_v\d+$")
LEGACY_RUN_ID_RE = re.compile(
    r"^trigger_provisional_b2_"
    r"(?P<for_trade_date>\d{8})_until_(?P<until_hhmm>\d{4})"
    r"_v(?P<legacy_version>\d+)$"
)
RUN_ID_RE = re.compile(
    r"^trigger_provisional_b2_"
    r"(?P<for_trade_date>\d{8})_until_(?P<until_hhmm>\d{4})"
    r"__realtime_projection_metric_"
    r"(?P=for_trade_date)_until_(?P=until_hhmm)"
    r"(?P<source_variant_suffix>(?:__(?:live_current_1m|live_current_1m_unified_payload_v1))?)"
    r"(?:__(?P<rule_suffix>atomic_rule_v\d+))?$"
)
HINT_V2_RUN_ID_RE = re.compile(
    r"^trigger_provisional_b2_"
    r"(?P<for_trade_date>\d{8})_until_(?P<until_hhmm>\d{4})"
    r"__realtime_hint_projection_metric_"
    r"(?P=for_trade_date)_until_(?P=until_hhmm)"
    r"__(?P<asset_scope>asset_index_board)"
    r"__(?P<proof_kind>index_board_1m_hint_projection_v1(?:_midday_bridge_v1)?)"
    r"__(?P<rule_suffix>atomic_rule_v\d+)$"
)
HINT_V2_SOURCE_RUN_ID_RE = re.compile(
    r"^realtime_hint_projection_metric_"
    r"(?P<for_trade_date>\d{8})_until_(?P<until_hhmm>\d{4})"
    r"__(?P<asset_scope>asset_index_board)"
    r"__(?P<proof_kind>index_board_1m_hint_projection_v1(?:_midday_bridge_v1)?)"
    r"__market_data_subscription_.*$"
)


class ProvisionalProjectionExecuteBlocked(RuntimeError):
    """Raised when provisional B2 execute must fail closed."""


def build_provisional_projection_trigger_run_id(
    *,
    for_trade_date: str,
    until_hhmm: str,
    source_variant: str = DEFAULT_SOURCE_VARIANT,
    source_metric_run_id: str | None = None,
    rule_suffix: str | None = None,
) -> str:
    if source_metric_run_id:
        source_match = HINT_V2_SOURCE_RUN_ID_RE.match(source_metric_run_id)
        if not source_match:
            raise ProvisionalProjectionExecuteBlocked(f"unsupported N4 provisional source_metric_run_id: {source_metric_run_id}")
        parsed_source = source_match.groupdict()
        if parsed_source["for_trade_date"] != for_trade_date or parsed_source["until_hhmm"] != until_hhmm:
            raise ProvisionalProjectionExecuteBlocked(
                "N4 provisional HINT trigger_run_id source date/until mismatch: "
                f"{parsed_source['for_trade_date']} {parsed_source['until_hhmm']} != {for_trade_date} {until_hhmm}"
            )
        if rule_suffix != "atomic_rule_v1":
            raise ProvisionalProjectionExecuteBlocked("N4 provisional HINT v2 trigger_run_id requires atomic_rule_v1")
        run_id = (
            f"trigger_provisional_b2_{for_trade_date}_until_{until_hhmm}"
            f"__realtime_hint_projection_metric_{for_trade_date}_until_{until_hhmm}"
            f"__{HINT_V2_ASSET_SCOPE}__{parsed_source['proof_kind']}__{rule_suffix}"
        )
        parse_provisional_projection_trigger_run_id(run_id)
        return run_id

    if source_variant not in ALLOWED_SOURCE_VARIANTS:
        raise ProvisionalProjectionExecuteBlocked(f"unsupported B2 trigger source_variant: {source_variant}")
    if rule_suffix is not None and not ATOMIC_RULE_SUFFIX_RE.match(rule_suffix):
        raise ProvisionalProjectionExecuteBlocked(f"invalid B2 trigger rule_suffix: {rule_suffix}")

    run_id = (
        f"trigger_provisional_b2_{for_trade_date}_until_{until_hhmm}"
        f"__realtime_projection_metric_{for_trade_date}_until_{until_hhmm}"
    )
    if source_variant != DEFAULT_SOURCE_VARIANT:
        run_id += f"__{source_variant}"
        run_id += f"__{rule_suffix or 'atomic_rule_v1'}"
    elif rule_suffix:
        run_id += f"__{rule_suffix}"

    parse_provisional_projection_trigger_run_id(run_id)
    return run_id


def parse_provisional_projection_trigger_run_id(run_id: str) -> dict[str, str]:
    legacy_match = LEGACY_RUN_ID_RE.match(run_id)
    if legacy_match:
        parsed = legacy_match.groupdict()
        return {
            "run_id": run_id,
            "for_trade_date": parsed["for_trade_date"],
            "until_hhmm": parsed["until_hhmm"],
            "source_variant": LEGACY_V1_SOURCE_VARIANT,
            "legacy_version": f"v{parsed['legacy_version']}",
            "rule_suffix": "",
            "mode": "provisional_b2",
            "source_metric_kind": "legacy_projection_metric",
        }

    hint_match = HINT_V2_RUN_ID_RE.match(run_id)
    if hint_match:
        parsed = hint_match.groupdict()
        if parsed["asset_scope"] != HINT_V2_ASSET_SCOPE or parsed["proof_kind"] not in ALLOWED_HINT_V2_PROOF_KINDS:
            raise ProvisionalProjectionExecuteBlocked(f"unsupported N4 provisional HINT trigger_run_id: {run_id}")
        if parsed["rule_suffix"] != "atomic_rule_v1":
            raise ProvisionalProjectionExecuteBlocked(f"N4 provisional HINT trigger_run_id requires atomic_rule_v1: {run_id}")
        return {
            "run_id": run_id,
            "for_trade_date": parsed["for_trade_date"],
            "until_hhmm": parsed["until_hhmm"],
            "source_variant": parsed["proof_kind"],
            "asset_scope": parsed["asset_scope"],
            "proof_kind": parsed["proof_kind"],
            "rule_suffix": parsed["rule_suffix"],
            "mode": "provisional_hint_v2",
            "source_metric_kind": "realtime_hint_projection_metric",
        }

    match = RUN_ID_RE.match(run_id)
    if not match:
        raise ProvisionalProjectionExecuteBlocked(f"invalid N4 provisional B2 trigger_run_id: {run_id}")

    parsed = match.groupdict()
    variant_suffix = parsed.get("source_variant_suffix") or ""
    source_variant = variant_suffix.removeprefix("__") if variant_suffix else DEFAULT_SOURCE_VARIANT
    rule_suffix = parsed.get("rule_suffix") or ""
    if source_variant not in ALLOWED_SOURCE_VARIANTS:
        raise ProvisionalProjectionExecuteBlocked(f"unsupported B2 trigger source_variant: {source_variant}")
    if source_variant != DEFAULT_SOURCE_VARIANT and not rule_suffix:
        raise ProvisionalProjectionExecuteBlocked(
            f"N4 provisional B2 trigger_run_id requires atomic rule suffix for source_variant={source_variant}: {run_id}"
        )
    if rule_suffix and not ATOMIC_RULE_SUFFIX_RE.match(rule_suffix):
        raise ProvisionalProjectionExecuteBlocked(f"invalid B2 trigger rule_suffix: {rule_suffix}")
    return {
        "run_id": run_id,
        "for_trade_date": parsed["for_trade_date"],
        "until_hhmm": parsed["until_hhmm"],
        "source_variant": source_variant,
        "rule_suffix": rule_suffix,
        "mode": "provisional_b2",
        "source_metric_kind": "realtime_projection_metric",
    }


def canonical_provisional_trigger_type(plan: Mapping[str, Any]) -> str:
    trigger_type = str(plan.get("trigger_type") or "")
    if trigger_type in {"BUY", "SELL"}:
        return trigger_type
    signal_type = str(plan.get("signal_type") or "")
    condition_key = str(plan.get("condition_key") or plan.get("original_condition_key") or "")
    legacy_signal_type = str(plan.get("legacy_signal_type") or "")
    direction = str(plan.get("direction") or "")
    if signal_type == "S_SELL" or condition_key == "SELL_HINT" or legacy_signal_type == "SELL_HINT" or direction == "sell":
        return "SELL"
    if signal_type == "B_BUY" or condition_key == "BUY_HINT" or legacy_signal_type == "BUY_HINT" or direction == "buy":
        return "BUY"
    return trigger_type or condition_key


def assert_provisional_projection_execute_confirmed(*, execute: bool, user_confirmed: bool) -> None:
    missing: list[str] = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if missing:
        raise ProvisionalProjectionExecuteBlocked(
            "N4 provisional projection execute blocked: missing " + ", ".join(missing)
        )


def build_provisional_projection_execute_plan(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    projection_run: Mapping[str, Any],
    trigger_context_run_id: str,
    projection_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    source_projection_run_id: str,
    context_rows: Sequence[Mapping[str, Any]],
    projection_rows: Sequence[Mapping[str, Any]],
    target_counts: Mapping[str, int],
    previous_trigger_states: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build the write plan without mutating the database."""

    parsed_run_id = parse_provisional_projection_trigger_run_id(trigger_run_id)
    if parsed_run_id["for_trade_date"] != for_trade_date:
        raise ProvisionalProjectionExecuteBlocked(
            f"trigger_run_id trade date mismatch: {parsed_run_id['for_trade_date']} != {for_trade_date}"
        )
    _require_passed_run(
        trigger_context_run,
        expected_run_id=trigger_context_run_id,
        run_kind="trigger_context_run",
    )
    _require_passed_run(
        projection_run,
        expected_run_id=projection_run_id,
        run_kind="projection_run",
    )
    _assert_target_absent(target_counts)

    raw_dry_run_plans = build_provisional_projection_matcher_plans(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        context_rows=context_rows,
        projection_rows=projection_rows,
    )
    dry_run_plans = [
        {**dict(plan), "for_trade_date": for_trade_date, "trigger_type": canonical_provisional_trigger_type(plan)}
        for plan in raw_dry_run_plans
    ]
    lifecycle_plans = build_lifecycle_output_plans(dry_run_plans, previous_states=previous_trigger_states)
    matched_plans = [plan for plan in lifecycle_plans if plan.get("output_event_type") == PROVISIONAL_TRIGGER_EVENT_TYPE]
    pending_plans = [plan for plan in lifecycle_plans if plan.get("output_event_type") == PROVISIONAL_PENDING_EVENT_TYPE]
    state_changed_plans = [
        plan for plan in lifecycle_plans if plan.get("output_event_type") == PROVISIONAL_STATE_CHANGED_EVENT_TYPE
    ]
    context_lookup = _context_lookup(context_rows)
    now = utc_now()
    trigger_state_rows: list[dict[str, Any]] = []
    trigger_match_rows: list[dict[str, Any]] = []
    outbox_rows: list[dict[str, Any]] = []
    for plan in lifecycle_plans:
        enriched = enrich_provisional_plan(
            plan,
            context_lookup=context_lookup,
            trigger_run_id=trigger_run_id,
            trigger_context_run_id=trigger_context_run_id,
            projection_run_id=projection_run_id,
            source_condition_run_id=source_condition_run_id,
            source_projection_run_id=source_projection_run_id,
            for_trade_date=for_trade_date,
        )
        state_row = build_provisional_trigger_state_row(
            trigger_run_id=trigger_run_id,
            trigger_context_run=trigger_context_run,
            plan=enriched,
            created_at=now,
        )
        envelope = build_provisional_trigger_matched_envelope(
            trigger_run_id=trigger_run_id,
            trigger_context_run=trigger_context_run,
            plan=enriched,
            dedup_key=str(state_row["dedup_key"]),
            output_event_id=str(enriched["output_event_id"]),
            trigger_state_id=None,
            trigger_match_id=None,
            created_at=now,
        )
        trigger_state_rows.append(state_row)
        if enriched.get("output_event_type") == PROVISIONAL_TRIGGER_EVENT_TYPE:
            match_row = build_provisional_trigger_match_row(
                trigger_run_id=trigger_run_id,
                trigger_context_run=trigger_context_run,
                plan=enriched,
                dedup_key=str(state_row["dedup_key"]),
                output_event_id=str(enriched["output_event_id"]),
                created_at=now,
            )
            trigger_match_rows.append(match_row)
        outbox_rows.append(envelope.as_record())

    run_row = build_provisional_trigger_run_row(
        trigger_run_id=trigger_run_id,
        trigger_context_run=trigger_context_run,
        projection_run=projection_run,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        source_projection_run_id=source_projection_run_id,
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        context_row_count=len(context_rows),
        candidate_count=len(dry_run_plans),
        matched_count=len(matched_plans),
        state_count=len(trigger_state_rows),
        match_count=len(trigger_match_rows),
        outbox_count=len(outbox_rows),
        created_at=now,
    )
    writes = {
        "common_trigger_run": [run_row],
        "common_trigger_quality_item": build_provisional_quality_items(
            trigger_run_id=trigger_run_id,
            source_condition_run_id=source_condition_run_id,
            for_trade_date=for_trade_date,
            source_trade_date=str(trigger_context_run.get("source_trade_date") or ""),
            dry_run_plans=dry_run_plans,
            matched_count=len(matched_plans),
            created_at=now,
        ),
        "common_trigger_state": trigger_state_rows,
        "common_trigger_match": trigger_match_rows,
        "common_event_outbox": outbox_rows,
    }
    summary = summarize_provisional_projection_matcher_plans(dry_run_plans)
    summary["lifecycle_output_event_types"] = dict(
        sorted(Counter(str(plan.get("output_event_type") or "") for plan in lifecycle_plans).items())
    )
    summary["lifecycle_state_changed_count"] = len(state_changed_plans)
    return {
        "result": "EXECUTE_PLAN_READY",
        "status": "passed",
        "layer_role": "N4_trigger",
        "trigger_run_id": trigger_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_projection_run_id": source_projection_run_id,
        "for_trade_date": for_trade_date,
        "candidate_count": len(dry_run_plans),
        "matched_count": len(matched_plans),
        "state_changed_count": len(state_changed_plans),
        "noop_count": len(dry_run_plans) - len(lifecycle_plans),
        "summary": summary,
        "writes": writes,
        "write_counts": {table_name: len(rows) for table_name, rows in writes.items()},
        "allowed_write_tables": sorted(PROVISIONAL_ALLOWED_WRITE_TABLES),
        "forbidden_write_counts": {table_name: 0 for table_name in sorted(PROVISIONAL_FORBIDDEN_WRITE_TABLES)},
        "event_model": {
            "output_event_types": sorted({str(plan.get("output_event_type")) for plan in lifecycle_plans}),
            "writes_state_changed": bool(state_changed_plans),
            "writes_pending_market_data": bool(pending_plans),
            "consumes_source_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "enters_n5": bool(matched_plans),
        },
        "dry_run_plans": [to_jsonable(plan) for plan in dry_run_plans],
    }


def build_provisional_source_event_id(*, projection_run_id: str, projection_id: Any) -> str:
    projection_id_text = _required_text(projection_id, "projection_id")
    return f"B2:{projection_run_id}:{projection_id_text}"


def build_provisional_dedup_key(plan: Mapping[str, Any], *, event_type: str = PROVISIONAL_TRIGGER_EVENT_TYPE) -> str:
    return join_dedup_parts(
        N4_SOURCE_LAYER,
        event_type,
        "projection_run_id",
        plan.get("projection_run_id"),
        "projection_id",
        plan.get("projection_id"),
        "asset_kind",
        plan.get("asset_kind"),
        "identity_key",
        plan.get("identity_key"),
        "signal_type",
        plan.get("signal_type"),
        "condition_key",
        plan.get("condition_key"),
        "trigger_mark_candidate",
        plan.get("trigger_mark_candidate"),
        "trigger_period",
        PROVISIONAL_TRIGGER_PERIOD,
    )


def enrich_provisional_plan(
    plan: Mapping[str, Any],
    *,
    context_lookup: Mapping[tuple[str, str, str, str], Mapping[str, Any]],
    trigger_run_id: str,
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_projection_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    output_event_type = str(plan.get("output_event_type") or "")
    if output_event_type not in {
        PROVISIONAL_TRIGGER_EVENT_TYPE,
        PROVISIONAL_PENDING_EVENT_TYPE,
        PROVISIONAL_STATE_CHANGED_EVENT_TYPE,
    }:
        raise ProvisionalProjectionExecuteBlocked("provisional execute only writes lifecycle B2 plans")
    projection_id_value = plan.get("projection_id")
    projection_id = _required_text(projection_id_value, "projection_id")
    context_row = context_lookup.get(
        (
            str(plan.get("asset_kind") or ""),
            str(plan.get("identity_key") or ""),
            str(plan.get("condition_key") or ""),
            str(plan.get("direction") or ""),
        ),
        {},
    )
    dedup_key = build_provisional_dedup_key(plan, event_type=output_event_type)
    output_event_id = build_stable_event_id(
        source_layer=N4_SOURCE_LAYER,
        event_type=output_event_type,
        source_run_id=trigger_run_id,
        dedup_key=dedup_key,
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
    )
    projection_trace = dict(plan.get("projection_trace") or {})
    enriched = {
        **dict(plan),
        "run_id": trigger_run_id,
        "source_event_id": build_provisional_source_event_id(
            projection_run_id=projection_run_id,
            projection_id=projection_id,
        ),
        "source_event_type": PROVISIONAL_SOURCE_EVENT_TYPE,
        "source_projection_run_id": source_projection_run_id,
        "projection_run_id": projection_run_id,
        "projection_id": projection_id_value,
        "trigger_context_run_id": trigger_context_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_condition_pool_id": context_row.get("source_condition_pool_id"),
        "source_condition_basis_id": context_row.get("source_condition_basis_id"),
        "source_minute_target_scope_id": context_row.get("source_minute_target_scope_id"),
        "source_market_subscription_id": context_row.get("source_market_subscription_id"),
        "context_snapshot_id": context_row.get("trigger_context_id"),
        "context_hash": context_row.get("context_hash"),
        "for_trade_date": for_trade_date,
        "source_trade_date": context_row.get("source_trade_date"),
        "prev_trade_date": context_row.get("prev_trade_date"),
        "trigger_period": PROVISIONAL_TRIGGER_PERIOD,
        "trigger_bucket": plan.get("projection_window_id") or f"projection:{projection_id}",
        "source_outcome_event_type": output_event_type,
        "source_outcome_event_id": output_event_id,
        "output_event_id": output_event_id,
        "dedup_key": dedup_key,
        "data_quality_status": "passed",
        "match_basis": "intraday_projection",
        "trigger_live": bool(plan.get("trigger_live")),
        "current_status": plan.get("current_status") or "matched",
        "provisional": True,
        "projection_trace": projection_trace,
    }
    return enriched


def build_provisional_trigger_run_row(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    projection_run: Mapping[str, Any],
    for_trade_date: str,
    source_condition_run_id: str,
    source_projection_run_id: str,
    trigger_context_run_id: str,
    projection_run_id: str,
    context_row_count: int,
    candidate_count: int,
    matched_count: int,
    state_count: int,
    match_count: int,
    outbox_count: int,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": trigger_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_market_data_run_id": source_projection_run_id,
        "for_trade_date": for_trade_date,
        "source_trade_date": trigger_context_run.get("source_trade_date"),
        "prev_trade_date": trigger_context_run.get("prev_trade_date"),
        "mode": "execute",
        "status": "passed",
        "context_snapshot_row_count": context_row_count,
        "candidate_count": candidate_count,
        "matched_count": matched_count,
        "trigger_state_row_count": state_count,
        "trigger_match_row_count": match_count,
        "trigger_event_outbox_count": outbox_count,
        "generated_by": DEFAULT_GENERATED_BY,
        "market_data_pulled": False,
        "action_layer_touched": False,
        "user_layer_touched": False,
        "voice_touched": False,
        "sim_touched": False,
        "real_trade_touched": False,
        "worker_started": False,
        "raw_json": {
            "provisional": True,
            "mode_detail": "provisional_b2_projection_execute",
            "trigger_context_run_id": trigger_context_run_id,
            "projection_run_id": projection_run_id,
            "source_projection_run_id": source_projection_run_id,
            "source_b2_live_target_run_id": source_projection_run_id or projection_run_id,
            "projection_run_status": projection_run.get("status"),
            "source": DEFAULT_GENERATED_BY,
            "event_model": "TriggerMatched_or_TriggerStateChanged_lifecycle",
            "writes_inbox_or_checkpoint": False,
            "enters_n5": bool(matched_count),
        },
        "started_at": created_at,
        "finished_at": created_at,
    }


def build_provisional_quality_items(
    *,
    trigger_run_id: str,
    source_condition_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    dry_run_plans: Sequence[Mapping[str, Any]],
    matched_count: int,
    created_at: datetime,
) -> list[dict[str, Any]]:
    return [
        {
            "run_id": trigger_run_id,
            "source_condition_run_id": source_condition_run_id,
            "for_trade_date": for_trade_date,
            "source_trade_date": source_trade_date,
            "data_domain": "common",
            "layer_scope": "trigger_run",
            "table_name": "common_trigger_run/common_trigger_state/common_trigger_match/common_event_outbox",
            "gate_code": "n4_provisional_b2_matcher_execute_summary",
            "gate_name": "N4 provisional B2 matcher execute summary",
            "severity": "P2",
            "status": "passed",
            "expected_value": "TriggerMatched or TriggerStateChanged lifecycle provisional execute",
            "actual_value": f"matched={matched_count}",
            "identity_key": None,
            "details": {
                "provisional": True,
                "candidate_count": len(dry_run_plans),
                "matched_count": matched_count,
                "allowed_output_event_types": [PROVISIONAL_TRIGGER_EVENT_TYPE, PROVISIONAL_STATE_CHANGED_EVENT_TYPE],
                "writes_inbox_or_checkpoint": False,
                "enters_n5": bool(matched_count),
            },
            "created_at": created_at,
        }
    ]


def build_provisional_trigger_state_row(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": trigger_run_id,
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "for_trade_date": str(plan.get("for_trade_date") or trigger_context_run.get("for_trade_date") or ""),
        "asset_kind": plan.get("asset_kind"),
        "identity_key": plan.get("identity_key"),
        "direction": plan.get("direction"),
        "signal_type": plan.get("signal_type"),
        "condition_key": plan.get("condition_key"),
        "trigger_type": canonical_provisional_trigger_type(plan),
        "trigger_period": PROVISIONAL_TRIGGER_PERIOD,
        "triggered_periods": [PROVISIONAL_TRIGGER_PERIOD],
        "trigger_bucket": plan.get("trigger_bucket"),
        "current_status": plan.get("current_status") or "matched",
        "last_source_event_id": plan.get("source_event_id"),
        "data_quality_status": "passed",
        "context_hash": plan.get("context_hash"),
        "match_count": 1 if plan.get("current_status") != "inactive" else 0,
        "first_matched_at": parse_event_time(plan.get("event_time")) if plan.get("current_status") != "inactive" else None,
        "last_matched_at": parse_event_time(plan.get("event_time")) if plan.get("current_status") != "inactive" else None,
        "cleared_at": parse_event_time(plan.get("event_time")) if plan.get("current_status") == "inactive" else None,
        "dedup_key": plan.get("dedup_key"),
        "raw_json": build_provisional_raw_json(plan),
        "created_at": created_at,
        "updated_at": created_at,
    }


def build_provisional_trigger_match_row(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    dedup_key: str,
    output_event_id: str,
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "run_id": trigger_run_id,
        "source_event_id": plan.get("source_event_id"),
        "source_event_type": plan.get("source_event_type"),
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "asset_kind": plan.get("asset_kind"),
        "identity_key": plan.get("identity_key"),
        "for_trade_date": str(plan.get("for_trade_date") or trigger_context_run.get("for_trade_date") or ""),
        "direction": plan.get("direction"),
        "signal_type": plan.get("signal_type"),
        "condition_key": plan.get("condition_key"),
        "trigger_period": PROVISIONAL_TRIGGER_PERIOD,
        "trigger_bucket": plan.get("trigger_bucket"),
        "trigger_price": plan.get("trigger_price"),
        "trigger_time": parse_event_time(plan.get("event_time")),
        "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
        "output_event_id": output_event_id,
        "output_event_type": PROVISIONAL_TRIGGER_EVENT_TYPE,
        "dedup_key": dedup_key,
        "data_quality_status": "passed",
        "source_condition_pool_id": plan.get("source_condition_pool_id"),
        "source_condition_basis_id": plan.get("source_condition_basis_id"),
        "source_market_subscription_id": plan.get("source_market_subscription_id"),
        "context_hash": plan.get("context_hash"),
        "raw_json": build_provisional_raw_json(plan),
        "created_at": created_at,
    }


def build_provisional_trigger_matched_envelope(
    *,
    trigger_run_id: str,
    trigger_context_run: Mapping[str, Any],
    plan: Mapping[str, Any],
    dedup_key: str,
    output_event_id: str,
    trigger_state_id: int | None,
    trigger_match_id: int | None,
    created_at: datetime | None = None,
) -> EventEnvelope:
    event_type = str(plan.get("output_event_type") or PROVISIONAL_TRIGGER_EVENT_TYPE)
    enters_n5 = event_type == PROVISIONAL_TRIGGER_EVENT_TYPE
    trigger_live = True if event_type == PROVISIONAL_TRIGGER_EVENT_TYPE else bool(plan.get("trigger_live"))
    current_status = str(plan.get("current_status") or ("matched" if trigger_live else "inactive"))
    original_condition_key = plan.get("original_condition_key") or plan.get("condition_key")
    trigger_type = canonical_provisional_trigger_type(plan)
    payload = to_jsonable({
        "event_type": event_type,
        "run_id": trigger_run_id,
        "source_event_id": plan.get("source_event_id"),
        "source_event_type": plan.get("source_event_type"),
        "identity_key": plan.get("identity_key"),
        "asset_kind": plan.get("asset_kind"),
        "condition_projection_context": to_jsonable(
            plan.get("condition_projection_context")
            if plan.get("condition_projection_context") is not None
            else {}
        ),
        "condition_projection_context_status": plan.get("condition_projection_context_status") or "not_ready",
        "condition_projection_context_trace": to_jsonable(
            plan.get("condition_projection_context_trace") or {}
        ),
        "direction": plan.get("direction"),
        "condition_key": plan.get("condition_key"),
        "original_condition_key": original_condition_key,
        "legacy_signal_type": plan.get("legacy_signal_type"),
        "signal_type": plan.get("signal_type"),
        "trigger_type": trigger_type,
        "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
        "trigger_period": PROVISIONAL_TRIGGER_PERIOD,
        "triggered_periods": plan.get("triggered_periods") or [PROVISIONAL_TRIGGER_PERIOD],
        "trigger_bucket": plan.get("trigger_bucket"),
        "match_basis": "intraday_projection",
        "data_quality_status": "passed",
        "provisional": True,
        "projection_run_id": plan.get("projection_run_id"),
        "source_projection_run_id": plan.get("source_projection_run_id"),
        "source_b2_live_target_run_id": plan.get("source_projection_run_id") or plan.get("projection_run_id"),
        "projection_id": plan.get("projection_id"),
        "source_projection_proof_run_id": plan.get("source_projection_proof_run_id"),
        "source_projection_proof_metric_id": plan.get("source_projection_proof_metric_id"),
        "source_projection_proof_time": plan.get("source_projection_proof_time"),
        "not_n5_final_proof": plan.get("not_n5_final_proof"),
        "projection_proof_kind": plan.get("projection_proof_kind"),
        "projection_30m_flag": plan.get("projection_30m_flag"),
        "projection_30m_type": plan.get("projection_30m_type"),
        "projection_signal_status": plan.get("projection_signal_status"),
        "source_mode": plan.get("source_mode"),
        "source_live_minute_run_id": plan.get("source_live_minute_run_id"),
        "c1_dependency": plan.get("c1_dependency"),
        "trigger_price": plan.get("trigger_price"),
        "trigger_time": isoformat_or_none(plan.get("trigger_time")),
        "trigger_live": trigger_live,
        "current_status": current_status,
        "previous_status": plan.get("previous_status"),
        "primary_trigger_period": plan.get("primary_trigger_period"),
        "previous_primary_trigger_period": plan.get("previous_primary_trigger_period"),
        "all_trigger_periods": plan.get("all_trigger_periods") or [],
        "previous_all_trigger_periods": plan.get("previous_all_trigger_periods") or [],
        "previous_projection_30m_flag": plan.get("previous_projection_30m_flag"),
        "previous_projection_30m_type": plan.get("previous_projection_30m_type"),
        "previous_trigger_mark_candidate": plan.get("previous_trigger_mark_candidate"),
        "state_change_reason": plan.get("state_change_reason"),
        "source_outcome_event_type": plan.get("source_outcome_event_type"),
        "source_outcome_event_id": plan.get("source_outcome_event_id"),
        "lifecycle_state_key": plan.get("lifecycle_state_key"),
        "lifecycle_state_key_version": plan.get("lifecycle_state_key_version"),
        "lifecycle_output_reason": plan.get("lifecycle_output_reason"),
        "previous_current_status": plan.get("previous_current_status"),
        "previous_trigger_live": plan.get("previous_trigger_live"),
        "trigger_context_run_id": plan.get("trigger_context_run_id"),
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "source_condition_pool_id": plan.get("source_condition_pool_id"),
        "source_condition_basis_id": plan.get("source_condition_basis_id"),
        "source_minute_target_scope_id": plan.get("source_minute_target_scope_id"),
        "source_market_subscription_id": plan.get("source_market_subscription_id"),
        "context_snapshot_id": plan.get("context_snapshot_id"),
        "context_hash": plan.get("context_hash"),
        "trigger_state_id": trigger_state_id,
        "trigger_match_id": trigger_match_id,
        "n5_entry_allowed": enters_n5,
        "projection_trace": to_jsonable(plan.get("projection_trace") or {}),
        "n4_boundary": {
            "provisional_b2": True,
            "market_data_pulled": False,
            "source_outbox_consumed": False,
            "writes_inbox_or_checkpoint": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "enters_n5": enters_n5,
        },
    })
    envelope = EventEnvelope(
        event_id=output_event_id,
        event_type=event_type,
        event_schema_version=DEFAULT_EVENT_SCHEMA_VERSION,
        trade_date=str(plan.get("for_trade_date") or trigger_context_run.get("for_trade_date") or ""),
        asset_kind=str(plan.get("asset_kind") or ""),
        identity_key=str(plan.get("identity_key") or ""),
        event_time=parse_event_time(plan.get("event_time")),
        source_layer=N4_SOURCE_LAYER,
        source_run_id=trigger_run_id,
        dedup_key=dedup_key,
        partition_key=str(plan.get("identity_key") or ""),
        payload_json=payload,
        created_at=created_at or utc_now(),
    )
    validate_event_envelope(envelope)
    return envelope


def build_provisional_raw_json(plan: Mapping[str, Any]) -> dict[str, Any]:
    event_type = str(plan.get("output_event_type") or "")
    trigger_type = canonical_provisional_trigger_type(plan)
    return to_jsonable({
        "event_type": plan.get("output_event_type"),
        "provisional": True,
        "asset_kind": plan.get("asset_kind"),
        "identity_key": plan.get("identity_key"),
        "condition_projection_context": to_jsonable(
            plan.get("condition_projection_context")
            if plan.get("condition_projection_context") is not None
            else {}
        ),
        "condition_projection_context_status": plan.get("condition_projection_context_status") or "not_ready",
        "condition_projection_context_trace": to_jsonable(
            plan.get("condition_projection_context_trace") or {}
        ),
        "condition_key": plan.get("condition_key"),
        "original_condition_key": plan.get("original_condition_key") or plan.get("condition_key"),
        "signal_type": plan.get("signal_type"),
        "trigger_type": trigger_type,
        "projection_run_id": plan.get("projection_run_id"),
        "source_b2_live_target_run_id": plan.get("source_projection_run_id") or plan.get("projection_run_id"),
        "projection_id": plan.get("projection_id"),
        "source_projection_proof_run_id": plan.get("source_projection_proof_run_id"),
        "source_projection_proof_metric_id": plan.get("source_projection_proof_metric_id"),
        "source_projection_proof_time": plan.get("source_projection_proof_time"),
        "not_n5_final_proof": plan.get("not_n5_final_proof"),
        "projection_proof_kind": plan.get("projection_proof_kind"),
        "projection_30m_flag": plan.get("projection_30m_flag"),
        "projection_30m_type": plan.get("projection_30m_type"),
        "source_mode": plan.get("source_mode"),
        "source_live_minute_run_id": plan.get("source_live_minute_run_id"),
        "c1_dependency": plan.get("c1_dependency"),
        "trigger_period": PROVISIONAL_TRIGGER_PERIOD,
        "triggered_periods": plan.get("triggered_periods") or [PROVISIONAL_TRIGGER_PERIOD],
        "trigger_price": plan.get("trigger_price"),
        "trigger_time": isoformat_or_none(plan.get("trigger_time")),
        "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
        "source_condition_run_id": plan.get("source_condition_run_id"),
        "trigger_context_run_id": plan.get("trigger_context_run_id"),
        "source_event_id": plan.get("source_event_id"),
        "source_fact_kind": "realtime_projection_metric",
        "source_event_id_kind": "B2_projection_fact",
        "output_event_type": plan.get("output_event_type"),
        "source_outcome_event_id": plan.get("output_event_id"),
        "current_status": plan.get("current_status"),
        "trigger_live": plan.get("trigger_live"),
        "lifecycle_state_key": plan.get("lifecycle_state_key"),
        "lifecycle_state_key_version": plan.get("lifecycle_state_key_version"),
        "lifecycle_output_reason": plan.get("lifecycle_output_reason"),
        "n5_entry_allowed": event_type == PROVISIONAL_TRIGGER_EVENT_TYPE,
        "projection_trace": to_jsonable(plan.get("projection_trace") or {}),
        "plan": to_jsonable(dict(plan)),
    })


def execute_provisional_projection_transaction(*, dsn: str, execute_plan: Mapping[str, Any]) -> dict[str, int]:
    """Persist a previously built execute plan.

    The function performs plain inserts after target absence preflight. It does
    not upsert or overwrite existing rows.
    """

    trigger_run_id = str(execute_plan.get("trigger_run_id") or "")
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_provisional_projection_execute",
        source_run_id=trigger_run_id,
        readonly_expected=False,
        bypass_classification="explicit_bypass_n4_provisional_execute",
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("BEGIN")
            insert_provisional_trigger_run(cur, execute_plan["writes"]["common_trigger_run"][0])
            insert_provisional_quality_items(cur, execute_plan["writes"]["common_trigger_quality_item"])
            state_id_by_dedup_key: dict[str, int] = {}
            for row in execute_plan["writes"]["common_trigger_state"]:
                dedup_key = str(row["dedup_key"])
                state_id = insert_provisional_trigger_state(cur, row)
                state_id_by_dedup_key[dedup_key] = state_id
            match_count = 0
            outbox_count = 0
            matched_dedup_keys: set[str] = set()
            for match_row in execute_plan["writes"]["common_trigger_match"]:
                dedup_key = str(match_row["dedup_key"])
                matched_dedup_keys.add(dedup_key)
                state_id = state_id_by_dedup_key[dedup_key]
                match_id = insert_provisional_trigger_match(cur, match_row, trigger_state_id=state_id)
                update_provisional_state_last_match(cur, trigger_state_id=state_id, trigger_match_id=match_id)
                event_plan = _matched_plan_by_dedup_key(execute_plan, dedup_key)
                envelope = build_provisional_trigger_matched_envelope(
                    trigger_run_id=trigger_run_id,
                    trigger_context_run=execute_plan["writes"]["common_trigger_run"][0],
                    plan=event_plan,
                    dedup_key=dedup_key,
                    output_event_id=str(match_row["output_event_id"]),
                    trigger_state_id=state_id,
                    trigger_match_id=match_id,
                )
                insert_provisional_outbox_envelope(cur, envelope)
                match_count += 1
                outbox_count += 1
            for state_row in execute_plan["writes"]["common_trigger_state"]:
                dedup_key = str(state_row["dedup_key"])
                if dedup_key in matched_dedup_keys:
                    continue
                state_id = state_id_by_dedup_key[dedup_key]
                event_plan = _state_plan_by_dedup_key(execute_plan, dedup_key)
                envelope = build_provisional_trigger_matched_envelope(
                    trigger_run_id=trigger_run_id,
                    trigger_context_run=execute_plan["writes"]["common_trigger_run"][0],
                    plan=event_plan,
                    dedup_key=dedup_key,
                    output_event_id=str(event_plan["output_event_id"]),
                    trigger_state_id=state_id,
                    trigger_match_id=None,
                )
                insert_provisional_outbox_envelope(cur, envelope)
                outbox_count += 1
            conn.commit()
    return {
        "common_trigger_run": 1,
        "common_trigger_quality_item": len(execute_plan["writes"]["common_trigger_quality_item"]),
        "common_trigger_state": len(execute_plan["writes"]["common_trigger_state"]),
        "common_trigger_match": match_count,
        "common_event_outbox": outbox_count,
    }


def insert_provisional_trigger_run(cur: Any, row: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_trigger_run (
          run_id, source_condition_run_id, source_market_data_run_id,
          for_trade_date, source_trade_date, prev_trade_date, mode, status,
          context_snapshot_row_count, trigger_state_row_count,
          trigger_match_row_count, trigger_event_outbox_count, generated_by,
          market_data_pulled, action_layer_touched, user_layer_touched,
          voice_touched, sim_touched, real_trade_touched, worker_started,
          raw_json, started_at, finished_at
        )
        VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(source_market_data_run_id)s,
          %(for_trade_date)s, %(source_trade_date)s, %(prev_trade_date)s, %(mode)s, %(status)s,
          %(context_snapshot_row_count)s, %(trigger_state_row_count)s,
          %(trigger_match_row_count)s, %(trigger_event_outbox_count)s, %(generated_by)s,
          %(market_data_pulled)s, %(action_layer_touched)s, %(user_layer_touched)s,
          %(voice_touched)s, %(sim_touched)s, %(real_trade_touched)s, %(worker_started)s,
          %(raw_json)s, %(started_at)s, %(finished_at)s
        )
        """,
        {**dict(row), "raw_json": Jsonb(to_jsonable(row.get("raw_json") or {}))},
    )


def insert_provisional_quality_items(cur: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        cur.execute(
            """
            INSERT INTO common_trigger_quality_item (
              run_id, source_condition_run_id, for_trade_date, source_trade_date,
              data_domain, layer_scope, table_name, gate_code, gate_name, severity,
              status, expected_value, actual_value, identity_key, details, created_at
            )
            VALUES (
              %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s, %(source_trade_date)s,
              %(data_domain)s, %(layer_scope)s, %(table_name)s, %(gate_code)s, %(gate_name)s, %(severity)s,
              %(status)s, %(expected_value)s, %(actual_value)s, %(identity_key)s, %(details)s, %(created_at)s
            )
            """,
            {**dict(row), "details": Jsonb(to_jsonable(row.get("details") or {}))},
        )


def insert_provisional_trigger_state(cur: Any, row: Mapping[str, Any]) -> int:
    cur.execute(
        """
        INSERT INTO common_trigger_state (
          run_id, source_condition_run_id, for_trade_date,
          asset_kind, identity_key, direction, signal_type, condition_key,
          trigger_period, trigger_bucket, current_status, last_source_event_id,
          data_quality_status, context_hash, match_count, first_matched_at,
          last_matched_at, cleared_at, raw_json, created_at, updated_at
        )
        VALUES (
          %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s,
          %(asset_kind)s, %(identity_key)s, %(direction)s, %(signal_type)s, %(condition_key)s,
          %(trigger_period)s, %(trigger_bucket)s, %(current_status)s, %(last_source_event_id)s,
          %(data_quality_status)s, %(context_hash)s, %(match_count)s, %(first_matched_at)s,
          %(last_matched_at)s, %(cleared_at)s, %(raw_json)s, %(created_at)s, %(updated_at)s
        )
        RETURNING trigger_state_id
        """,
        {
            **dict(row),
            "raw_json": Jsonb(to_jsonable(row.get("raw_json") or {})),
        },
    )
    fetched = cur.fetchone()
    if isinstance(fetched, Mapping):
        return int(fetched["trigger_state_id"])
    return int(fetched[0])


def insert_provisional_trigger_match(cur: Any, row: Mapping[str, Any], *, trigger_state_id: int) -> int:
    cur.execute(
        """
        INSERT INTO common_trigger_match (
          run_id, trigger_state_id, source_event_id, source_event_type,
          source_condition_run_id, source_condition_pool_id, source_condition_basis_id,
          source_market_subscription_id, for_trade_date, asset_kind, identity_key,
          direction, signal_type, condition_key, trigger_price, trigger_mark_candidate,
          trigger_time, trigger_period, trigger_bucket,
          output_event_id, output_event_type, data_quality_status,
          dedup_key, context_hash, raw_json, created_at
        )
        VALUES (
          %(run_id)s, %(trigger_state_id)s, %(source_event_id)s, %(source_event_type)s,
          %(source_condition_run_id)s, %(source_condition_pool_id)s, %(source_condition_basis_id)s,
          %(source_market_subscription_id)s, %(for_trade_date)s, %(asset_kind)s, %(identity_key)s,
          %(direction)s, %(signal_type)s, %(condition_key)s, %(trigger_price)s, %(trigger_mark_candidate)s,
          %(trigger_time)s, %(trigger_period)s, %(trigger_bucket)s,
          %(output_event_id)s, %(output_event_type)s, %(data_quality_status)s,
          %(dedup_key)s, %(context_hash)s, %(raw_json)s, %(created_at)s
        )
        RETURNING trigger_match_id
        """,
        {
            **dict(row),
            "trigger_state_id": trigger_state_id,
            "raw_json": Jsonb(to_jsonable(row.get("raw_json") or {})),
        },
    )
    fetched = cur.fetchone()
    if isinstance(fetched, Mapping):
        return int(fetched["trigger_match_id"])
    return int(fetched[0])


def update_provisional_state_last_match(cur: Any, *, trigger_state_id: int, trigger_match_id: int) -> None:
    cur.execute(
        """
        UPDATE common_trigger_state
        SET last_trigger_match_id = %s, updated_at = now()
        WHERE trigger_state_id = %s
        """,
        (trigger_match_id, trigger_state_id),
    )


def insert_provisional_outbox_envelope(cur: Any, envelope: EventEnvelope) -> str:
    record = envelope.as_record()
    columns = (
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
    )
    placeholders = ", ".join(["%s"] * len(columns))
    cur.execute(
        f"""
        INSERT INTO common_event_outbox ({", ".join(columns)})
        VALUES ({placeholders})
        RETURNING event_id
        """,
        [Jsonb(to_jsonable(record[column])) if column == "payload_json" else record[column] for column in columns],
    )
    fetched = cur.fetchone()
    if isinstance(fetched, Mapping):
        return str(fetched["event_id"])
    return str(fetched[0])


def run_provisional_projection_once(
    *,
    dsn: str,
    trigger_context_run_id: str,
    projection_run_id: str,
    trigger_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    source_projection_run_id: str,
    execute: bool,
    user_confirmed: bool,
    json_report_path: str | Path | None = None,
    markdown_report_path: str | Path | None = None,
    rollback_sql_path: str | Path | None = None,
    no_previous_baseline: bool = False,
    previous_trigger_run_id: str | None = None,
) -> dict[str, Any]:
    if execute:
        assert_provisional_projection_execute_confirmed(execute=execute, user_confirmed=user_confirmed)
    previous_trigger_states, baseline_report = select_projection_previous_baseline(
        dsn=dsn,
        trigger_run_id=trigger_run_id,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        no_previous_baseline=no_previous_baseline,
        previous_trigger_run_id=previous_trigger_run_id,
    )
    context_rows, trigger_context_run = fetch_trigger_context_rows(dsn, trigger_context_run_id)
    projection_rows, projection_run = fetch_projection_rows(dsn, projection_run_id)
    target_counts = fetch_target_counts(dsn, trigger_run_id)
    execute_plan = build_provisional_projection_execute_plan(
        trigger_run_id=trigger_run_id,
        trigger_context_run=trigger_context_run,
        projection_run=projection_run,
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        source_projection_run_id=source_projection_run_id,
        context_rows=context_rows,
        projection_rows=projection_rows,
        target_counts=target_counts,
        previous_trigger_states=previous_trigger_states,
    )
    write_counts: dict[str, int] | None = None
    result = "PREFLIGHT_PASS"
    if execute:
        write_counts = execute_provisional_projection_transaction(dsn=dsn, execute_plan=execute_plan)
        result = "EXECUTED"
    report = {
        "result": result,
        "trigger_run_id": trigger_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "for_trade_date": for_trade_date,
        "execute": execute,
        "summary": execute_plan.get("summary"),
        "write_counts": write_counts or execute_plan.get("write_counts"),
        "side_effect_boundary": execute_plan.get("event_model"),
        "forbidden_write_counts": execute_plan.get("forbidden_write_counts"),
        **baseline_report,
    }
    if rollback_sql_path is not None:
        write_text(rollback_sql_path, build_provisional_rollback_sql(trigger_run_id))
        report["rollback_sql_path"] = str(rollback_sql_path)
    if json_report_path is not None:
        write_json(json_report_path, report)
    if markdown_report_path is not None:
        write_text(markdown_report_path, render_provisional_report_markdown(report))
    return report


def select_projection_previous_baseline(
    *,
    dsn: str,
    trigger_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    no_previous_baseline: bool = False,
    previous_trigger_run_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select previous state input for the projection/HINT execute path.

    HINT v2 targets must never inherit same-day ordinary states implicitly.
    """

    parsed = parse_provisional_projection_trigger_run_id(trigger_run_id)
    is_hint_v2_target = parsed.get("mode") == "provisional_hint_v2"
    if no_previous_baseline and previous_trigger_run_id:
        raise ProvisionalProjectionExecuteBlocked(
            "HINT previous baseline policy conflict: choose no_previous_baseline or previous_trigger_run_id"
        )
    if is_hint_v2_target:
        if no_previous_baseline:
            return [], build_previous_baseline_report(
                baseline_mode=BASELINE_MODE_NO_PREVIOUS,
                previous_trigger_run_id=None,
                previous_state_count=0,
                previous_baseline_family=BASELINE_FAMILY_NONE,
                previous_baseline_policy_safe=True,
            )
        if previous_trigger_run_id:
            previous_states = fetch_exact_previous_hint_trigger_states(
                dsn,
                previous_trigger_run_id=previous_trigger_run_id,
                for_trade_date=for_trade_date,
                source_condition_run_id=source_condition_run_id,
            )
            return previous_states, build_previous_baseline_report(
                baseline_mode=BASELINE_MODE_EXACT_HINT_PREVIOUS,
                previous_trigger_run_id=previous_trigger_run_id,
                previous_state_count=len(previous_states),
                previous_baseline_family=BASELINE_FAMILY_HINT_PROJECTION,
                previous_baseline_policy_safe=True,
            )
        raise ProvisionalProjectionExecuteBlocked(
            f"{BLOCKED_PREVIOUS_BASELINE_POLICY_UNSAFE}: HINT/projection execute requires "
            "explicit no_previous_baseline=true or previous_trigger_run_id=<exact HINT target>"
        )

    previous_states = fetch_previous_trigger_states(
        dsn,
        trigger_run_id=trigger_run_id,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
    )
    return previous_states, build_previous_baseline_report(
        baseline_mode="implicit_same_day_projection_baseline",
        previous_trigger_run_id=None,
        previous_state_count=len(previous_states),
        previous_baseline_family=BASELINE_FAMILY_IMPLICIT_PROJECTION,
        previous_baseline_policy_safe=True,
    )


def build_previous_baseline_report(
    *,
    baseline_mode: str,
    previous_trigger_run_id: str | None,
    previous_state_count: int,
    previous_baseline_family: str,
    previous_baseline_policy_safe: bool,
) -> dict[str, Any]:
    return {
        "baseline_mode": baseline_mode,
        "previous_trigger_run_id": previous_trigger_run_id,
        "previous_state_count": previous_state_count,
        "previous_baseline_family": previous_baseline_family,
        "previous_baseline_policy_safe": previous_baseline_policy_safe,
    }


def collapse_latest_lifecycle_states(states: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the latest row per lifecycle key from an already ordered state stream."""

    latest_by_key: dict[str, dict[str, Any]] = {}
    for state in states:
        latest_by_key[lifecycle_state_key(state)] = dict(state)
    return list(latest_by_key.values())


def require_hint_previous_trigger_run_id(previous_trigger_run_id: str) -> dict[str, str]:
    if previous_trigger_run_id.startswith("trigger_provisional_ordinary_"):
        raise ProvisionalProjectionExecuteBlocked(
            f"previous HINT baseline must be trigger_provisional_b2 realtime_hint_projection_metric: {previous_trigger_run_id}"
        )
    parsed = parse_provisional_projection_trigger_run_id(previous_trigger_run_id)
    if parsed.get("mode") != "provisional_hint_v2" or parsed.get("source_metric_kind") != "realtime_hint_projection_metric":
        raise ProvisionalProjectionExecuteBlocked(
            f"previous HINT baseline must be trigger_provisional_b2 realtime_hint_projection_metric: {previous_trigger_run_id}"
        )
    return parsed


def fetch_exact_previous_hint_trigger_states(
    dsn: str,
    *,
    previous_trigger_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
) -> list[dict[str, Any]]:
    require_hint_previous_trigger_run_id(previous_trigger_run_id)
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_provisional_projection_exact_previous_hint_state_fetch",
        source_run_id=previous_trigger_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM common_trigger_run WHERE run_id = %s", (previous_trigger_run_id,))
        previous_run = cur.fetchone()
        if not previous_run:
            raise ProvisionalProjectionExecuteBlocked(f"previous HINT baseline run missing: {previous_trigger_run_id}")
        if str(previous_run.get("status") or "") != "passed":
            raise ProvisionalProjectionExecuteBlocked(
                f"previous HINT baseline run must be passed: {previous_trigger_run_id}"
            )
        if str(previous_run.get("for_trade_date") or "") != for_trade_date:
            raise ProvisionalProjectionExecuteBlocked(
                "previous HINT baseline trade date mismatch: "
                f"{previous_run.get('for_trade_date')} != {for_trade_date}"
            )
        if str(previous_run.get("source_condition_run_id") or "") != source_condition_run_id:
            raise ProvisionalProjectionExecuteBlocked(
                "previous HINT baseline source_condition_run_id mismatch: "
                f"{previous_run.get('source_condition_run_id')} != {source_condition_run_id}"
            )
        cur.execute(
            """
            SELECT s.*
            FROM common_trigger_state AS s
            JOIN common_trigger_run AS r ON r.run_id = s.run_id
            WHERE r.for_trade_date = %s
              AND r.source_condition_run_id = %s
              AND r.status = 'passed'
              AND r.run_id LIKE %s
              AND r.run_id <= %s
            ORDER BY r.run_id, s.updated_at, s.identity_key
            """,
            (
                for_trade_date,
                source_condition_run_id,
                f"trigger_provisional_b2_{for_trade_date}_until_%__realtime_hint_projection_metric_%",
                previous_trigger_run_id,
            ),
        )
        return collapse_latest_lifecycle_states([dict(row) for row in cur.fetchall()])


def fetch_trigger_context_rows(dsn: str, trigger_context_run_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_provisional_projection_context_fetch",
        source_run_id=trigger_context_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM common_trigger_run WHERE run_id = %s", (trigger_context_run_id,))
        trigger_context_run = cur.fetchone()
        if not trigger_context_run:
            raise ProvisionalProjectionExecuteBlocked(f"trigger_context_run missing: {trigger_context_run_id}")
        rows: list[dict[str, Any]] = []
        for asset_kind, table_name in (
            ("stock", "stock_trigger_context_snapshot"),
            ("index", "index_trigger_context_snapshot"),
            ("board", "board_trigger_context_snapshot"),
        ):
            cur.execute(f"SELECT *, %s AS asset_kind FROM {table_name} WHERE run_id = %s", (asset_kind, trigger_context_run_id))
            rows.extend(dict(row) for row in cur.fetchall())
        return rows, dict(trigger_context_run)


def fetch_projection_rows(dsn: str, projection_run_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_provisional_projection_metric_fetch",
        source_run_id=projection_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM common_market_data_run WHERE run_id = %s", (projection_run_id,))
        projection_run = cur.fetchone()
        if not projection_run:
            raise ProvisionalProjectionExecuteBlocked(f"projection_run missing: {projection_run_id}")
        rows: list[dict[str, Any]] = []
        if is_hint_1m_projection_run_id(projection_run_id):
            for asset_kind, table_name in HINT_PROJECTION_TABLE_CONFIG.items():
                cur.execute(
                    f"""
                    SELECT metric_id AS projection_id,
                           projection_run_id,
                           trade_date,
                           metric_minute_label,
                           asset_kind,
                           identity_key,
                           code,
                           name,
                           direction,
                           condition_key,
                           original_condition_key,
                           source_condition_pool_id,
                           source_minute_target_scope_id,
                           source_subscription_run_id,
                           source_artifact_path,
                           source_artifact_sha256,
                           source_previous_day_minute_run_id,
                           source_context_run_id,
                           proof_kind,
                           source_mode,
                           metric_role,
                           proof_owner,
                           proof_consumer,
                           not_n5_final_proof,
                           current_window_start,
                           current_window_end,
                           previous_completed_window_start,
                           previous_completed_window_end,
                           current_window_elapsed_count,
                           full_window_count,
                           current_30m_price,
                           current_30m_elapsed_amount,
                           previous_day_same_elapsed_30m_amount,
                           previous_day_full_30m_amount,
                           current_30m_virtual_amount,
                           reference_30m_amount,
                           reference_30m_entity_high,
                           reference_30m_entity_low,
                           projection_30m_type,
                           projection_30m_flag,
                           metric_ready,
                           blocked_reasons,
                           raw_json,
                           trace_json,
                           created_at
                    FROM {table_name}
                    WHERE projection_run_id = %s
                    ORDER BY identity_key, metric_minute_label DESC, metric_id
                    """,
                    (projection_run_id,),
                )
                for row in cur.fetchall():
                    normalized = normalize_hint_projection_row(row)
                    normalized["asset_kind"] = asset_kind
                    rows.append(normalized)
            return rows, dict(projection_run)
        for asset_kind, table_name, identity_column in (
            ("stock", "stock_realtime_projection_metric", "stock_identity_key"),
            ("index", "index_realtime_projection_metric", "index_identity_key"),
            ("board", "board_realtime_projection_metric", "board_identity_key"),
        ):
            cur.execute(
                f"""
                SELECT *, {identity_column} AS identity_key, %s AS asset_kind
                FROM {table_name}
                WHERE projection_run_id = %s
                """,
                (asset_kind, projection_run_id),
            )
            rows.extend(normalize_provisional_projection_row(asset_kind, row) for row in cur.fetchall())
        return rows, dict(projection_run)


def normalize_provisional_projection_row(asset_kind: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize asset-specific B2 projection identity columns for the matcher."""

    output = dict(row)
    output["asset_kind"] = asset_kind
    if not output.get("identity_key"):
        output["identity_key"] = output.get(f"{asset_kind}_identity_key")
    source_fact_ids = output.get("source_fact_ids")
    if source_fact_ids is None:
        output["source_fact_ids"] = {}
    return output


def fetch_target_counts(dsn: str, trigger_run_id: str) -> dict[str, int]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_provisional_projection_target_absence",
        source_run_id=trigger_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        counts: dict[str, int] = {}
        for table_name, column_name in (
            ("common_trigger_run", "run_id"),
            ("common_trigger_state", "run_id"),
            ("common_trigger_match", "run_id"),
        ):
            cur.execute(f"SELECT count(*) AS row_count FROM {table_name} WHERE {column_name} = %s", (trigger_run_id,))
            counts[table_name] = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*) AS row_count
            FROM common_event_outbox
            WHERE source_layer = %s AND source_run_id = %s
            """,
            (N4_SOURCE_LAYER, trigger_run_id),
        )
        counts["common_event_outbox"] = int(cur.fetchone()["row_count"])
        return counts


def fetch_previous_trigger_states(
    dsn: str,
    *,
    trigger_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
) -> list[dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_provisional_projection_previous_state_fetch",
        source_run_id=trigger_run_id,
        connect_timeout=10,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM common_trigger_state
            WHERE for_trade_date = %s
              AND source_condition_run_id = %s
              AND run_id <> %s
            """,
            (for_trade_date, source_condition_run_id, trigger_run_id),
        )
        return [dict(row) for row in cur.fetchall()]


def build_provisional_rollback_sql(trigger_run_id: str) -> str:
    escaped = trigger_run_id.replace("'", "''")
    downstream_guard_tables = ",\n      ".join(
        f"'{table_name}'" for table_name in PROVISIONAL_ROLLBACK_DOWNSTREAM_GUARD_TABLES
    )
    return f"""-- N4 provisional B2 rollback for {escaped}
DO $$
DECLARE
  v_run_id text := '{escaped}';
  v_ref_table text;
  v_ref_count bigint;
BEGIN
  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    EXECUTE
      'SELECT count(*) FROM common_event_outbox AS t '
      || 'WHERE to_jsonb(t)::text LIKE $1 '
      || 'AND NOT (t.source_layer = ''N4_trigger'' AND t.source_run_id = $2)'
      INTO v_ref_count
      USING '%' || v_run_id || '%', v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: non-scoped common_event_outbox refs exist for %', v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.common_trigger_match') IS NOT NULL THEN
    EXECUTE
      'SELECT count(*) FROM common_trigger_match AS t '
      || 'WHERE to_jsonb(t)::text LIKE $1 AND t.run_id <> $2'
      INTO v_ref_count
      USING '%' || v_run_id || '%', v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: non-scoped common_trigger_match refs exist for %', v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.common_trigger_state') IS NOT NULL THEN
    EXECUTE
      'SELECT count(*) FROM common_trigger_state AS t '
      || 'WHERE to_jsonb(t)::text LIKE $1 AND t.run_id <> $2'
      INTO v_ref_count
      USING '%' || v_run_id || '%', v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: non-scoped common_trigger_state refs exist for %', v_run_id;
    END IF;
  END IF;

  FOR v_ref_table IN SELECT unnest(ARRAY[
      {downstream_guard_tables}
  ])
  LOOP
    IF to_regclass('public.' || v_ref_table) IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM %I AS t WHERE to_jsonb(t)::text LIKE $1',
        v_ref_table
      )
      INTO v_ref_count
      USING '%' || v_run_id || '%';
      IF v_ref_count > 0 THEN
        RAISE EXCEPTION 'rollback blocked: downstream refs exist in % for %', v_ref_table, v_run_id;
      END IF;
    END IF;
  END LOOP;

  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    SELECT count(*)
    INTO v_ref_count
    FROM common_event_outbox
    WHERE source_layer = 'N4_trigger'
      AND source_run_id = v_run_id
      AND status IN ('delivered', 'delivering');
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: scoped outbox already delivered/delivering for %', v_run_id;
    END IF;
  END IF;

  DELETE FROM common_event_outbox
  WHERE source_layer = 'N4_trigger' AND source_run_id = v_run_id;
  DELETE FROM common_trigger_match WHERE run_id = v_run_id;
  DELETE FROM common_trigger_state WHERE run_id = v_run_id;
  DELETE FROM common_trigger_quality_item WHERE run_id = v_run_id;
  DELETE FROM common_trigger_run WHERE run_id = v_run_id;
END $$;
"""


def render_provisional_report_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    return "\n".join(
        [
            "# N4 Provisional B2 Execute Report",
            "",
            f"- result: {report.get('result')}",
            f"- trigger_run_id: {report.get('trigger_run_id')}",
            f"- projection_run_id: {report.get('projection_run_id')}",
            f"- candidate_count: {summary.get('candidate_count')}",
            f"- matched_count: {summary.get('matched_count')}",
            f"- noop_count: {summary.get('noop_count')}",
            f"- writes_inbox_or_checkpoint: {(report.get('side_effect_boundary') or {}).get('writes_inbox_or_checkpoint')}",
            f"- enters_n5: {(report.get('side_effect_boundary') or {}).get('enters_n5')}",
            "",
        ]
    )


def _require_passed_run(run: Mapping[str, Any], *, expected_run_id: str, run_kind: str) -> None:
    run_id = str(run.get("run_id") or run.get("projection_run_id") or "")
    status = str(run.get("status") or "")
    if run_id != expected_run_id:
        raise ProvisionalProjectionExecuteBlocked(f"{run_kind} lineage mismatch: {run_id} != {expected_run_id}")
    if status != "passed":
        raise ProvisionalProjectionExecuteBlocked(f"{run_kind} status must be passed: {status}")


def _assert_target_absent(target_counts: Mapping[str, int]) -> None:
    existing = {name: int(count) for name, count in target_counts.items() if int(count) > 0}
    if existing:
        raise ProvisionalProjectionExecuteBlocked(f"target exists for trigger_run_id: {existing}")


def _context_lookup(context_rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str, str], Mapping[str, Any]]:
    lookup: dict[tuple[str, str, str, str], Mapping[str, Any]] = {}
    for raw_row in context_rows:
        row = normalize_context_row(raw_row)
        key = (
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or ""),
            str(row.get("condition_key") or ""),
            str(row.get("direction") or ""),
        )
        lookup.setdefault(key, row)
    return lookup


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProvisionalProjectionExecuteBlocked(f"{field_name} is required")
    return text


def parse_event_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value or "").strip()
    if not text:
        return utc_now()
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def isoformat_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _matched_plan_by_dedup_key(execute_plan: Mapping[str, Any], dedup_key: str) -> Mapping[str, Any]:
    for row in execute_plan["writes"]["common_trigger_match"]:
        if str(row.get("dedup_key") or "") == dedup_key:
            raw_json = dict(row.get("raw_json") or {})
            original_plan = dict(raw_json.get("plan") or {})
            return {
                **original_plan,
                **raw_json,
                **dict(row),
                "dedup_key": dedup_key,
                "output_event_id": row.get("output_event_id"),
            }
    raise KeyError(dedup_key)


def _state_plan_by_dedup_key(execute_plan: Mapping[str, Any], dedup_key: str) -> Mapping[str, Any]:
    for row in execute_plan["writes"]["common_trigger_state"]:
        if str(row.get("dedup_key") or "") == dedup_key:
            raw_json = dict(row.get("raw_json") or {})
            original_plan = dict(raw_json.get("plan") or {})
            return {
                **original_plan,
                **raw_json,
                **dict(row),
                "dedup_key": dedup_key,
                "output_event_id": raw_json.get("source_outcome_event_id")
                or original_plan.get("output_event_id")
                or row.get("source_outcome_event_id"),
            }
    raise KeyError(dedup_key)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def summarize_event_rows(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))
