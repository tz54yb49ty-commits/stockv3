"""N5 canonical action consumer execute runner.

The runner is deliberately run-once only and requires both ``execute`` and
``user_confirmed`` gates before it can write. Its contract helpers are pure and
are used by tests/preflight without mutating N4 outbox, action facts, inbox,
checkpoint, N5 outbox, user projection, voice, sim, mobile, or real trading
state.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.action.consumer_dry_run import (
    DEFAULT_N5_1_CONSUMER_NAME,
    build_consumer_plan,
    empty_inbox_keys,
    fetch_existing_checkpoints,
    fetch_existing_inbox_keys,
)
from ashare_v3.action.dry_run import (
    build_action_candidates_from_outbox_rows,
    infer_source_action_confirmation_metric_id,
    minute_key,
    resolve_metric_alignment_trigger_time,
)
from ashare_v3.action.event_factory import build_n5_action_event
from ashare_v3.action.query_audit_phase2 import audited_n5_action_connect
from ashare_v3.action.preflight import (
    ROW_COUNT_GUARD_TABLES,
    fetch_row_counts,
    fetch_trigger_run,
    normalize_outbox_row,
)
from ashare_v3.action.run_once_dry_run import (
    ACTION_CONFIRMATION_METRIC_TABLE_BY_ASSET_KIND,
    ACTION_EVENT_GUARD_TABLES,
    ACTION_FACT_TABLE_BY_ASSET_KIND,
    CURRENT_REAL_N4_SOURCE_RUN_ID,
    CURRENT_REAL_N4_SOURCE_RUN_ALLOWLIST,
    DEFAULT_N5_CURRENT_REAL_BASELINE_REPORT_PATH,
    DEFAULT_N5_CURRENT_REAL_JSON_REPORT_PATH,
    SYNTHETIC_N4_SOURCE_RUN_DENYLIST,
    build_action_consumer_run_once_dry_run_report_from_rows,
    build_action_write_plan,
    build_output_event_plan,
    fetch_action_confirmation_metric_facts,
    load_baseline_report,
    write_json,
    write_text,
)
from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item
from ashare_v3.events.models import DEFAULT_EVENT_SCHEMA_VERSION
from ashare_v3.events.repository import EventRepository


CURRENT_REAL_N5_EXECUTE_ACTION_RUN_ID = (
    "action_consumer_current_real_execute_20260525_"
    "trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249"
)
CANONICAL_20260528_N4_SOURCE_RUN_ID = (
    "trigger_execute_20260528_condition_layer_20260527_source_20260527_v2"
)
CANONICAL_20260528_N4_SOURCE_RUN_ALLOWLIST = (CANONICAL_20260528_N4_SOURCE_RUN_ID,)
CANONICAL_20260528_N4_SOURCE_RUN_DENYLIST = (
    *SYNTHETIC_N4_SOURCE_RUN_DENYLIST,
    CURRENT_REAL_N4_SOURCE_RUN_ID,
)
CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID = (
    "action_consumer_canonical_20260528_"
    "trigger_execute_20260528_condition_layer_20260527_source_20260527_v2"
)
CANONICAL_20260529_N4_SOURCE_RUN_ID = (
    "trigger_execute_20260529_condition_layer_20260528_source_20260528_v1"
)
CANONICAL_20260529_N4_SOURCE_RUN_ALLOWLIST = (CANONICAL_20260529_N4_SOURCE_RUN_ID,)
CANONICAL_20260529_N4_SOURCE_RUN_DENYLIST = (
    *SYNTHETIC_N4_SOURCE_RUN_DENYLIST,
    CURRENT_REAL_N4_SOURCE_RUN_ID,
    CANONICAL_20260528_N4_SOURCE_RUN_ID,
)
CANONICAL_20260529_N5_EXECUTE_ACTION_RUN_ID = (
    "action_consumer_canonical_20260529_"
    "trigger_execute_20260529_condition_layer_20260528_source_20260528_v1"
)
ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID = (
    "trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1"
)
ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ALLOWLIST = (
    ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID,
)
ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_DENYLIST = (
    *SYNTHETIC_N4_SOURCE_RUN_DENYLIST,
    CURRENT_REAL_N4_SOURCE_RUN_ID,
    CANONICAL_20260528_N4_SOURCE_RUN_ID,
    CANONICAL_20260529_N4_SOURCE_RUN_ID,
)
ACTION_CONFIRMATION_METRIC_20260602_N5_EXECUTE_ACTION_RUN_ID = (
    "action_consumer_action_confirmation_metric_execute_20260602_1105__"
    "trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1"
)
DEFAULT_N5_CURRENT_REAL_EXECUTE_CONTRACT_JSON_PATH = "docs/N5_current_real_action_execute_contract.json"
DEFAULT_N5_CURRENT_REAL_EXECUTE_CONTRACT_MD_PATH = "docs/N5_CURRENT_REAL_ACTION_EXECUTE_CONTRACT.md"
DEFAULT_N5_CURRENT_REAL_EXECUTE_REPORT_JSON_PATH = "docs/N5_current_real_action_execute_report.json"
DEFAULT_N5_CURRENT_REAL_EXECUTE_REPORT_MD_PATH = "docs/N5_CURRENT_REAL_ACTION_EXECUTE_REPORT.md"
DEFAULT_N5_CURRENT_REAL_ROLLBACK_SQL_PATH = "sql/N5_current_real_action_execute_rollback.sql"
DEFAULT_N5_CANONICAL_20260528_EXECUTE_REPORT_JSON_PATH = (
    "docs/N5_20260528_canonical_action_execute_report.json"
)
DEFAULT_N5_CANONICAL_20260528_EXECUTE_REPORT_MD_PATH = (
    "docs/N5_20260528_CANONICAL_ACTION_EXECUTE_REPORT.md"
)
DEFAULT_N5_CANONICAL_20260528_EXECUTE_CONTRACT_JSON_PATH = (
    "docs/N5_20260528_canonical_action_execute_contract.json"
)
DEFAULT_N5_CANONICAL_20260528_EXECUTE_CONTRACT_MD_PATH = (
    "docs/N5_20260528_CANONICAL_ACTION_EXECUTE_CONTRACT.md"
)
DEFAULT_N5_CANONICAL_20260528_DRY_RUN_JSON_REPORT_PATH = (
    "docs/N5_20260528_canonical_action_dry_run_contract_gate_report.json"
)
DEFAULT_N5_CANONICAL_20260528_ROLLBACK_SQL_PATH = (
    "sql/N5_20260528_canonical_action_execute_rollback.sql"
)
DEFAULT_N5_CANONICAL_20260529_EXECUTE_REPORT_JSON_PATH = (
    "docs/N5_20260529_canonical_action_execute_report.json"
)
DEFAULT_N5_CANONICAL_20260529_EXECUTE_REPORT_MD_PATH = (
    "docs/N5_20260529_CANONICAL_ACTION_EXECUTE_REPORT.md"
)
DEFAULT_N5_CANONICAL_20260529_EXECUTE_CONTRACT_JSON_PATH = (
    "docs/N5_20260529_canonical_action_execute_contract.json"
)
DEFAULT_N5_CANONICAL_20260529_EXECUTE_CONTRACT_MD_PATH = (
    "docs/N5_20260529_CANONICAL_ACTION_EXECUTE_CONTRACT.md"
)
DEFAULT_N5_CANONICAL_20260529_DRY_RUN_JSON_REPORT_PATH = (
    "docs/N5_20260529_canonical_action_dry_run_contract_gate_report.json"
)
DEFAULT_N5_CANONICAL_20260529_ROLLBACK_SQL_PATH = (
    "sql/N5_20260529_canonical_action_execute_rollback.sql"
)
DEFAULT_N5_ACTION_CONFIRMATION_METRIC_20260602_DRY_RUN_JSON_REPORT_PATH = (
    "docs/N5_20260602_action_confirmation_metric_consumption_dry_run_report.json"
)
DEFAULT_N5_ACTION_CONFIRMATION_METRIC_20260602_EXECUTE_REPORT_JSON_PATH = (
    "docs/N5_20260602_action_confirmation_metric_execute_report.json"
)
DEFAULT_N5_ACTION_CONFIRMATION_METRIC_20260602_EXECUTE_REPORT_MD_PATH = (
    "docs/N5_20260602_ACTION_CONFIRMATION_METRIC_EXECUTE_REPORT.md"
)
DEFAULT_N5_ACTION_CONFIRMATION_METRIC_20260602_ROLLBACK_SQL_PATH = (
    "sql/N5_20260602_action_confirmation_metric_execute_rollback.sql"
)
EXPECTED_CURRENT_REAL_PENDING_EVENT_COUNT = 764
EXPECTED_CURRENT_REAL_ACTION_EVENT_COUNT = 479
EXPECTED_CURRENT_REAL_HINT_EVENT_COUNT = 9
EXPECTED_CANONICAL_20260528_PENDING_EVENT_COUNT = 17774
EXPECTED_CANONICAL_20260529_PENDING_EVENT_COUNT = 17722
EXPECTED_ACTION_CONFIRMATION_METRIC_20260602_PENDING_EVENT_COUNT = 5941
LATEST_CANONICAL_N4_SOURCE_RUN_ID = ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID
LATEST_CANONICAL_N5_EXECUTE_ACTION_RUN_ID = ACTION_CONFIRMATION_METRIC_20260602_N5_EXECUTE_ACTION_RUN_ID
LATEST_CANONICAL_DRY_RUN_JSON_REPORT_PATH = DEFAULT_N5_ACTION_CONFIRMATION_METRIC_20260602_DRY_RUN_JSON_REPORT_PATH
LATEST_CANONICAL_EXECUTE_REPORT_JSON_PATH = DEFAULT_N5_ACTION_CONFIRMATION_METRIC_20260602_EXECUTE_REPORT_JSON_PATH
LATEST_CANONICAL_EXECUTE_REPORT_MD_PATH = DEFAULT_N5_ACTION_CONFIRMATION_METRIC_20260602_EXECUTE_REPORT_MD_PATH
LATEST_CANONICAL_ROLLBACK_SQL_PATH = DEFAULT_N5_ACTION_CONFIRMATION_METRIC_20260602_ROLLBACK_SQL_PATH
LATEST_CANONICAL_EXPECTED_PENDING_EVENT_COUNT = EXPECTED_ACTION_CONFIRMATION_METRIC_20260602_PENDING_EVENT_COUNT
ALLOWED_OUTBOX_STATUSES = ("pending",)
RUNNER_MODE = "run_once"
SOURCE_LAYER = "N4_trigger"
ACTION_POLICY = "n5_confirmation_only"
CANONICAL_ACTION_MARKS = frozenset({"normal", "30m_volume", "30m_shrink"})
N3T_ACTION_CONFIRMATION_METRIC_RUN_ID_PREFIX = "n3t_action_confirmation_metric_"
N3T_ACTION_CONFIRMATION_METRIC_TABLE_BY_ASSET_KIND = {
    "stock": "stock_n3t_action_confirmation_metric",
    "index": "index_n3t_action_confirmation_metric",
    "board": "board_n3t_action_confirmation_metric",
}


class ActionExecuteError(RuntimeError):
    """Raised when the N5 action execute runner is blocked."""


def normalize_action_persistence_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed on invalid persistence shape and normalize ActionExecuted rows.

    Execute writers must not persist an ActionExecuted row with eligible-shape
    fields and then rely on a follow-up repair. The dry-run plan remains the
    source of truth for the event type; persistence normalizes only the fields
    that must be canonical for the chosen output event.
    """

    normalized = dict(row)
    event_type = str(normalized.get("planned_output_event_type") or "")
    if event_type != "ActionExecuted":
        return normalized

    final_action_mark = str(normalized.get("final_action_mark") or "")
    if final_action_mark not in CANONICAL_ACTION_MARKS:
        raise ActionExecuteError(
            "ActionExecuted persistence requires canonical final_action_mark"
        )
    if not str(normalized.get("source_market_data_run_id") or ""):
        raise ActionExecuteError(
            "ActionExecuted persistence requires source_market_data_run_id"
        )
    if not str(normalized.get("last_checked_minute_label") or ""):
        raise ActionExecuteError(
            "ActionExecuted persistence requires last_checked_minute_label"
        )

    normalized.update(
        {
            "action_state": "executed",
            "confirmation_status": "passed",
            "action_policy": ACTION_POLICY,
            "closed_minute_required": True,
            "closed_minute_verified": True,
            "minute_context_status": "closed",
        }
    )
    return normalized


def resolve_allowed_source_run_ids(
    source_trigger_run_id: str,
    allowed_source_run_ids: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Resolve the source allowlist from the explicit execute source run."""

    if allowed_source_run_ids is not None:
        return tuple(allowed_source_run_ids)
    if source_trigger_run_id == ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID:
        return ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ALLOWLIST
    if source_trigger_run_id == CANONICAL_20260529_N4_SOURCE_RUN_ID:
        return CANONICAL_20260529_N4_SOURCE_RUN_ALLOWLIST
    if source_trigger_run_id == CANONICAL_20260528_N4_SOURCE_RUN_ID:
        return CANONICAL_20260528_N4_SOURCE_RUN_ALLOWLIST
    if source_trigger_run_id == CURRENT_REAL_N4_SOURCE_RUN_ID:
        return CURRENT_REAL_N4_SOURCE_RUN_ALLOWLIST
    return (source_trigger_run_id,)


def resolve_denied_source_run_ids(
    source_trigger_run_id: str,
    denied_source_run_ids: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Resolve stale/synthetic denylist entries for the explicit execute source run."""

    if denied_source_run_ids is not None:
        return tuple(denied_source_run_ids)
    if source_trigger_run_id == ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID:
        return ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_DENYLIST
    if source_trigger_run_id == CANONICAL_20260529_N4_SOURCE_RUN_ID:
        return CANONICAL_20260529_N4_SOURCE_RUN_DENYLIST
    if source_trigger_run_id == CANONICAL_20260528_N4_SOURCE_RUN_ID:
        return CANONICAL_20260528_N4_SOURCE_RUN_DENYLIST
    return SYNTHETIC_N4_SOURCE_RUN_DENYLIST


def build_current_real_execute_contract_from_rows(
    *,
    execute: bool,
    user_confirmed: bool,
    outbox_rows: Sequence[Mapping[str, Any]],
    trigger_run: Mapping[str, Any] | None,
    action_run_id: str = CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID,
    source_trigger_run_id: str = CANONICAL_20260528_N4_SOURCE_RUN_ID,
    consumer_name: str = DEFAULT_N5_1_CONSUMER_NAME,
    baseline_report: Mapping[str, Any] | None = None,
    before_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    action_confirmation_metric_facts: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None = None,
    action_confirmation_metric_facts_by_identity: Mapping[Any, Sequence[Mapping[str, Any]]] | None = None,
    rollback_sql_path: str = DEFAULT_N5_CANONICAL_20260528_ROLLBACK_SQL_PATH,
    allowed_source_run_ids: Sequence[str] | None = None,
    denied_source_run_ids: Sequence[str] | None = None,
    baseline_report_path: str = DEFAULT_N5_CANONICAL_20260528_DRY_RUN_JSON_REPORT_PATH,
    json_report_path: str = DEFAULT_N5_CANONICAL_20260528_EXECUTE_CONTRACT_JSON_PATH,
    markdown_report_path: str = DEFAULT_N5_CANONICAL_20260528_EXECUTE_CONTRACT_MD_PATH,
    expected_read_event_count: int | None = None,
    stage: str = "N5-canonical-20260528-execute-contract",
) -> dict[str, Any]:
    """Build the execute contract without writing to the DB."""

    normalized_rows = [normalize_outbox_row(row) for row in outbox_rows]
    pending_rows = [row for row in normalized_rows if str(row.get("status") or "") == "pending"]
    pending_guard = build_pending_only_guard(normalized_rows)
    expected_count = expected_read_event_count if expected_read_event_count is not None else len(pending_rows)
    resolved_allowed_source_run_ids = resolve_allowed_source_run_ids(
        source_trigger_run_id,
        allowed_source_run_ids,
    )
    resolved_denied_source_run_ids = resolve_denied_source_run_ids(
        source_trigger_run_id,
        denied_source_run_ids,
    )
    dry_run_plan = build_action_consumer_run_once_dry_run_report_from_rows(
        trigger_run_id=source_trigger_run_id,
        action_run_id=action_run_id,
        consumer_name=consumer_name,
        trigger_run=trigger_run or {},
        outbox_rows=pending_rows,
        before_row_counts=before_row_counts or empty_guard_counts(),
        after_row_counts=after_row_counts or empty_guard_counts(),
        action_confirmation_metric_facts=action_confirmation_metric_facts,
        action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
        baseline_report=baseline_report or source_baseline_from_rows(
            pending_rows,
            source_trigger_run_id=source_trigger_run_id,
        ),
        baseline_report_path=baseline_report_path,
        stage=stage,
        expected_read_event_count=expected_count,
        require_period_trigger_baseline_trace=True,
        allowed_source_run_ids=resolved_allowed_source_run_ids,
        denied_source_run_ids=resolved_denied_source_run_ids,
        rollback_sql_path=rollback_sql_path,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        sample_limit=min(max(len(pending_rows), 1), 80),
    )
    quality_items = build_execute_quality_items(
        execute=execute,
        user_confirmed=user_confirmed,
        pending_guard=pending_guard,
        dry_run_plan=dry_run_plan,
    )
    severity_counts = count_quality_severities(quality_items)
    blockers = [
        str(item["gate_code"])
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    ]
    planned_write_scope = build_planned_write_scope(dry_run_plan)
    expected_row_counts = build_expected_row_counts(planned_write_scope)
    allow_execute = not blockers
    return {
        "stage": stage,
        "layer_role": "N5_action",
        "runner_mode": RUNNER_MODE,
        "mode": "execute_contract",
        "execute": execute,
        "user_confirmed": user_confirmed,
        "allow_execute": allow_execute,
        "blockers": blockers,
        "source_trigger_run_id": source_trigger_run_id,
        "action_run_id": action_run_id,
        "consumer_name": consumer_name,
        "expected_read_event_count": expected_count,
        "source_run_guard": dry_run_plan["source_run_guard"],
        "pending_only_guard": pending_guard,
        "consumer_plan_summary": dry_run_plan["consumer_plan_summary"],
        "outbox_summary": dry_run_plan["outbox_summary"],
        "action_write_plan_summary": dry_run_plan["action_write_plan_summary"],
        "output_event_plan_summary": dry_run_plan["output_event_plan_summary"],
        "period_trigger_baseline_trace_summary": dry_run_plan["period_trigger_baseline_trace_summary"],
        "planned_write_scope": planned_write_scope,
        "expected_row_counts": expected_row_counts,
        "idempotency_plan": build_idempotency_plan(dry_run_plan),
        "rollback_plan": {
            "rollback_sql_path": rollback_sql_path,
            "action_run_id": action_run_id,
            "source_trigger_run_id": source_trigger_run_id,
            "consumer_name": consumer_name,
            "touches_n4_or_n3": False,
        },
        "write_tables_allowed": [
            "common_action_run",
            "common_action_quality_item",
            "stock_action_fact",
            "index_action_fact",
            "board_action_fact",
            "common_action_event",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        ],
        "write_tables_forbidden": [
            "common_position_state",
            "common_position_event",
            "user projection",
            "voice/mobile",
            "sim",
            "real trade/order",
            "N2/N3/N4 facts",
            "old synthetic outbox",
        ],
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": build_execute_side_effects(executed=False),
        "dry_run_plan": dry_run_plan,
    }


def build_pending_only_guard(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_status = dict(sorted(Counter(str(row.get("status") or "") for row in rows).items()))
    non_pending = [
        {
            "event_id": row.get("event_id"),
            "event_type": row.get("event_type"),
            "source_run_id": row.get("source_run_id"),
            "status": row.get("status"),
        }
        for row in rows
        if str(row.get("status") or "") not in ALLOWED_OUTBOX_STATUSES
    ]
    return {
        "allowed_statuses": list(ALLOWED_OUTBOX_STATUSES),
        "by_status": by_status,
        "total_row_count": len(rows),
        "pending_count": int(by_status.get("pending", 0)),
        "non_pending_count": len(non_pending),
        "non_pending_sample": non_pending[:20],
        "passed": not non_pending and bool(rows),
    }


def build_execute_quality_items(
    *,
    execute: bool,
    user_confirmed: bool,
    pending_guard: Mapping[str, Any],
    dry_run_plan: Mapping[str, Any],
) -> list[dict[str, Any]]:
    output_summary = dry_run_plan.get("output_event_plan_summary") or {}
    action_summary = dry_run_plan.get("action_write_plan_summary") or {}
    source_guard = dry_run_plan.get("source_run_guard") or {}
    consumer_guard = dry_run_plan.get("consumer_guard") or {}
    consumer_summary = dry_run_plan.get("consumer_plan_summary") or {}
    by_output = output_summary.get("by_event_type") or {}
    deprecated_output_count = sum(
        int(by_output.get(event_type) or 0)
        for event_type in ("ActionEvent", "HintEvent", "RiskEvent", "PositionEvent")
    )
    return [
        quality_item(
            "P0",
            "passed" if execute and user_confirmed else "failed",
            "n5_execute_double_confirmation",
            "N5 current-real execute requires both --execute and --user-confirmed",
            expected="execute=true user_confirmed=true",
            actual=f"execute={execute} user_confirmed={user_confirmed}",
        ),
        quality_item(
            "P0",
            "passed" if source_guard.get("passed") else "failed",
            "n5_execute_source_run_guard",
            "N5 canonical execute accepts only explicitly allowlisted source_run_id values and rejects synthetic/stale runs",
            expected=json.dumps(source_guard, sort_keys=True, default=str),
            actual=json.dumps(source_guard, sort_keys=True, default=str),
        ),
        quality_item(
            "P0",
            "passed" if consumer_guard.get("passed") else "failed",
            "n5_execute_consumer_guard",
            "N5 execute must use the default consumer or an explicitly declared empty dedicated reprocess consumer",
            expected=json.dumps(consumer_guard, sort_keys=True, default=str),
            actual=json.dumps(consumer_guard, sort_keys=True, default=str),
        ),
        quality_item(
            "P0",
            "passed" if pending_guard.get("passed") else "failed",
            "n5_execute_pending_only_guard",
            "N5 current-real execute must consume only pending N4 outbox rows",
            expected="all rows status=pending",
            actual=json.dumps(pending_guard, sort_keys=True, default=str),
        ),
        quality_item(
            "P0",
            "passed"
            if int(action_summary.get("pending_action_fact_plan_count") or 0) == 0
            else "failed",
            "n5_execute_pending_market_data_quality_only",
            "TriggerPendingMarketData must remain quality only and generate no action fact",
            expected="0",
            actual=str(action_summary.get("pending_action_fact_plan_count") or 0),
        ),
        quality_item(
            "P0",
            "passed"
            if deprecated_output_count == 0
            else "failed",
            "n5_execute_no_deprecated_output_events",
            "Canonical N5 execute planning must not produce ActionEvent/HintEvent/RiskEvent/PositionEvent",
            expected="deprecated output event count=0",
            actual=str(deprecated_output_count),
        ),
        quality_item(
            "P0",
            "passed"
            if int(consumer_summary.get("read_event_count") or 0) == int(pending_guard.get("pending_count") or 0)
            else "failed",
            "n5_execute_read_count_is_pending_count",
            "Execute read_event_count must equal pending N4 outbox count after pending-only filter",
            expected=str(pending_guard.get("pending_count") or 0),
            actual=str(consumer_summary.get("read_event_count") or 0),
        ),
    ]


def build_planned_write_scope(plan: Mapping[str, Any]) -> dict[str, int]:
    action_summary = plan.get("action_write_plan_summary") or {}
    consumer_summary = plan.get("consumer_plan_summary") or {}
    output_summary = plan.get("output_event_plan_summary") or {}
    by_table = dict(action_summary.get("by_target_action_fact_table") or {})
    accepted_event_count = int(consumer_summary.get("planned_receive_count") or consumer_summary.get("read_event_count") or 0)
    checkpoint_plan_entry_count = int(consumer_summary.get("checkpoint_write_plan_count") or 0)
    checkpoint_watermark_rows = int(
        consumer_summary.get("checkpoint_physical_watermark_rows")
        or consumer_summary.get("accepted_partition_count")
        or checkpoint_plan_entry_count
    )
    return {
        "common_action_run": 1 if int(consumer_summary.get("read_event_count") or 0) else 0,
        "common_action_quality_item": int(action_summary.get("quality_plan_only_count") or 0),
        "stock_action_fact": int(by_table.get("stock_action_fact") or 0),
        "index_action_fact": int(by_table.get("index_action_fact") or 0),
        "board_action_fact": int(by_table.get("board_action_fact") or 0),
        "common_action_event": int(action_summary.get("would_insert_common_action_event_count") or 0),
        "common_event_outbox": int(output_summary.get("planned_event_count") or 0),
        "common_event_inbox": int(consumer_summary.get("would_insert_inbox_count") or 0),
        "common_event_consumer_checkpoint": checkpoint_watermark_rows,
        "accepted_event_count": accepted_event_count,
        "checkpoint_plan_entry_count": checkpoint_plan_entry_count,
        "checkpoint_physical_watermark_rows": checkpoint_watermark_rows,
        "common_position_state": 0,
        "common_position_event": 0,
    }


def build_expected_row_counts(planned_scope: Mapping[str, int]) -> dict[str, Any]:
    return {
        "before_execute_expected_current_real_rows": {
            "N4_current_pending_outbox": EXPECTED_CURRENT_REAL_PENDING_EVENT_COUNT,
            "N5_action_run_rows_for_action_run_id": 0,
            "N5_outbox_rows_for_action_run_id": 0,
            "N5_inbox_rows_for_current_source": 0,
        },
        "after_execute_expected_delta": dict(planned_scope),
    }


def build_idempotency_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    key_recheck = plan.get("candidate_key_stability_recheck") or {}
    consumer_summary = plan.get("consumer_plan_summary") or {}
    return {
        "event_id_in_inbox_skips_existing": True,
        "action_fact_dedup_key_unique": int(key_recheck.get("duplicate_dedup_key_count") or 0) == 0,
        "common_action_event_dedup_key_unique": True,
        "n5_outbox_dedup_key_unique": True,
        "checkpoint_only_moves_forward": True,
        "duplicate_action_key_count": int(key_recheck.get("duplicate_action_key_count") or 0),
        "duplicate_dedup_key_count": int(key_recheck.get("duplicate_dedup_key_count") or 0),
        "accepted_event_count": int(consumer_summary.get("planned_receive_count") or consumer_summary.get("read_event_count") or 0),
        "checkpoint_plan_entry_count": int(consumer_summary.get("checkpoint_write_plan_count") or 0),
        "checkpoint_physical_watermark_rows": int(
            consumer_summary.get("checkpoint_physical_watermark_rows")
            or consumer_summary.get("accepted_partition_count")
            or consumer_summary.get("checkpoint_write_plan_count")
            or 0
        ),
    }


def build_execute_side_effects(*, executed: bool) -> dict[str, bool]:
    return {
        "will_execute_sql": executed,
        "writes_performed": executed,
        "common_event_inbox_updated": executed,
        "consumer_checkpoint_updated": executed,
        "action_run_written": executed,
        "action_quality_written": executed,
        "action_fact_written": executed,
        "action_event_written": executed,
        "common_event_outbox_written": executed,
        "n5_outbox_written": executed,
        "n4_outbox_status_updated": False,
        "n4_outbox_consumed": False,
        "position_state_written": False,
        "position_event_written": False,
        "market_data_pulled": False,
        "n1_n2_n3_n4_modified": False,
        "n6_user_layer_touched": False,
        "user_layer_touched": False,
        "voice_touched": False,
        "sim_touched": False,
        "mobile_touched": False,
        "real_trade_touched": False,
        "worker_started": False,
        "old_system_touched": False,
    }


def empty_guard_counts() -> dict[str, dict[str, Any]]:
    counts = {"common_event_outbox": {"exists": True, "row_count": 0, "status": "present"}}
    for table_name in ACTION_EVENT_GUARD_TABLES:
        counts[table_name] = {"exists": True, "row_count": 0, "status": "present"}
    counts["common_action_run"] = {"exists": True, "row_count": 0, "status": "present"}
    counts["common_action_quality_item"] = {"exists": True, "row_count": 0, "status": "present"}
    return counts


def current_real_baseline_from_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return source_baseline_from_rows(rows, source_trigger_run_id=CURRENT_REAL_N4_SOURCE_RUN_ID)


def source_baseline_from_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_trigger_run_id: str,
) -> dict[str, Any]:
    by_event_type = Counter(str(row.get("event_type") or "") for row in rows)
    by_signal_type = Counter(
        str((row.get("payload_json") or {}).get("signal_type") or "")
        for row in rows
        if isinstance(row.get("payload_json") or {}, Mapping)
    )
    return {
        "stage": "N4-execute-contract-inline",
        "run_id": source_trigger_run_id,
        "output_summary": {
            "outbox_count": len(rows),
            "outbox_by_event_type": dict(sorted(by_event_type.items())),
            "match_by_signal_type": dict(sorted(by_signal_type.items())),
        },
    }


def infer_action_metric_run_ids_from_baseline(baseline_report: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Infer one or more N3 action-confirmation metric runs for deterministic joins."""

    if not isinstance(baseline_report, Mapping):
        return ()
    candidates: list[Any] = [
        baseline_report.get("n3_action_metric_run_id"),
        baseline_report.get("action_metric_run_id"),
        baseline_report.get("metric_run_id"),
    ]
    metric_inputs = baseline_report.get("metric_inputs")
    if isinstance(metric_inputs, Mapping):
        candidates.extend(
            [
                metric_inputs.get("original_metric_run_id"),
                metric_inputs.get("repair_metric_run_id"),
                metric_inputs.get("metric_run_id"),
                metric_inputs.get("n3_action_metric_run_id"),
                metric_inputs.get("action_metric_run_id"),
            ]
        )
        for list_key in ("metric_run_ids", "combined_metric_run_ids", "input_metric_run_ids"):
            value = metric_inputs.get(list_key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                candidates.extend(value)
    for list_key in ("metric_run_ids", "combined_metric_run_ids", "input_metric_run_ids"):
        value = baseline_report.get(list_key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            candidates.extend(value)
    for nested_key in (
        "n3_action_confirmation_metric_rows",
        "metric_join_coverage",
        "deterministic_action_metric_join",
    ):
        nested = baseline_report.get(nested_key)
        if isinstance(nested, Mapping):
            candidates.extend(
                [
                    nested.get("metric_run_id"),
                    nested.get("n3_action_metric_run_id"),
                    nested.get("action_metric_run_id"),
                ]
            )
            for list_key in ("metric_run_ids", "combined_metric_run_ids", "input_metric_run_ids"):
                value = nested.get(list_key)
                if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                    candidates.extend(value)
    output: list[str] = []
    for candidate in candidates:
        for value in coerce_metric_run_ids(candidate):
            if value and value not in output:
                output.append(value)
    return tuple(output)


def infer_action_metric_run_id_from_baseline(baseline_report: Mapping[str, Any] | None) -> str:
    """Backward-compatible single metric run inference."""

    run_ids = infer_action_metric_run_ids_from_baseline(baseline_report)
    return run_ids[0] if run_ids else ""


def coerce_metric_run_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            output.extend(coerce_metric_run_ids(item))
        return output
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def action_metric_join_key_from_outbox_row(row: Mapping[str, Any]) -> tuple[str, str, str]:
    normalized = normalize_outbox_row(row)
    payload = normalized.get("payload_json") or {}
    asset_kind = str(payload.get("asset_kind") or normalized.get("asset_kind") or "")
    identity_key = str(payload.get("identity_key") or normalized.get("identity_key") or "")
    trade_date = str(payload.get("trade_date") or normalized.get("trade_date") or "")
    return asset_kind, identity_key, trade_date


def action_metric_join_key_from_metric_fact(metric: Mapping[str, Any]) -> tuple[str, str, str]:
    normalized = normalize_mapping(metric)
    asset_kind = str(normalized.get("asset_kind") or "")
    identity_key = str(normalized.get("identity_key") or "")
    trade_date = str(normalized.get("for_trade_date") or normalized.get("trade_date") or "")
    return asset_kind, identity_key, trade_date


def action_metric_trigger_signature_from_outbox_row(row: Mapping[str, Any]) -> dict[str, str]:
    normalized = normalize_outbox_row(row)
    payload = normalized.get("payload_json") or {}
    projection_trace = payload.get("projection_trace") if isinstance(payload.get("projection_trace"), Mapping) else {}
    projection_fact_ids = projection_trace.get("source_fact_ids") if isinstance(projection_trace.get("source_fact_ids"), Mapping) else {}
    metric_join_time = (
        payload.get("metric_join_time")
        or projection_trace.get("closed_label_used")
        or projection_fact_ids.get("closed_label_used")
        or payload.get("trigger_time")
        or normalized.get("event_time")
        or ""
    )
    return {
        "asset_kind": str(payload.get("asset_kind") or normalized.get("asset_kind") or ""),
        "identity_key": str(payload.get("identity_key") or normalized.get("identity_key") or ""),
        "trade_date": str(payload.get("trade_date") or normalized.get("trade_date") or ""),
        "direction": str(payload.get("direction") or ""),
        "condition_key": str(payload.get("condition_key") or ""),
        "source_trigger_match_id": str(
            payload.get("source_trigger_match_id")
            or payload.get("trigger_match_id")
            or ""
        ),
        "source_trigger_event_id": str(normalized.get("event_id") or payload.get("trigger_event_id") or ""),
        "trigger_time": str(metric_join_time),
    }


def action_metric_trigger_signature_from_metric_fact(metric: Mapping[str, Any]) -> dict[str, str]:
    normalized = normalize_mapping(metric)
    refs = metric_trigger_refs(normalized)
    return {
        "asset_kind": str(normalized.get("asset_kind") or ""),
        "identity_key": str(normalized.get("identity_key") or ""),
        "trade_date": str(normalized.get("for_trade_date") or normalized.get("trade_date") or ""),
        "direction": str(normalized.get("direction") or ""),
        "condition_key": str(normalized.get("condition_key") or ""),
        "source_trigger_match_ids": refs["match_ids"],
        "source_trigger_event_ids": refs["event_ids"],
        "metric_time": str(normalized.get("metric_time") or ""),
    }


def metric_trigger_refs(metric: Mapping[str, Any]) -> dict[str, set[str]]:
    match_ids: set[str] = set()
    event_ids: set[str] = set()
    for key in ("source_trigger_match_id", "trigger_match_id", "source_trigger_match_ids", "trigger_match_ids"):
        append_ref_values(match_ids, metric.get(key))
    for key in ("source_trigger_event_id", "trigger_event_id", "source_trigger_event_ids", "trigger_event_ids"):
        append_ref_values(event_ids, metric.get(key))
    raw_json = metric.get("raw_json") if isinstance(metric.get("raw_json"), Mapping) else {}
    source_fact_ids = metric.get("source_fact_ids") if isinstance(metric.get("source_fact_ids"), Mapping) else {}
    for source in (raw_json, source_fact_ids):
        for key in ("source_trigger_match_id", "trigger_match_id", "source_trigger_match_ids", "trigger_match_ids"):
            append_ref_values(match_ids, source.get(key))
        for key in ("source_trigger_event_id", "trigger_event_id", "source_trigger_event_ids", "trigger_event_ids"):
            append_ref_values(event_ids, source.get(key))
    for key in ("n4_trigger_matched_events", "trigger_matched_events", "source_trigger_matched_events"):
        events = raw_json.get(key)
        if isinstance(events, Sequence) and not isinstance(events, (str, bytes, bytearray)):
            for event in events:
                if not isinstance(event, Mapping):
                    continue
                append_ref_values(match_ids, event.get("source_trigger_match_id") or event.get("trigger_match_id"))
                append_ref_values(event_ids, event.get("source_trigger_event_id") or event.get("event_id"))
    return {"match_ids": match_ids, "event_ids": event_ids}


def append_ref_values(target: set[str], value: Any) -> None:
    if value is None or value == "":
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            append_ref_values(target, item)
        return
    target.add(str(value))


def metric_matches_trigger_signature(trigger: Mapping[str, str], metric: Mapping[str, Any]) -> bool:
    metric_sig = action_metric_trigger_signature_from_metric_fact(metric)
    for key in ("asset_kind", "identity_key", "trade_date"):
        if trigger.get(key) and metric_sig.get(key) and trigger[key] != metric_sig[key]:
            return False
    for key in ("direction", "condition_key"):
        if metric_sig.get(key) and trigger.get(key) != metric_sig.get(key):
            return False
    trigger_minute = minute_key(trigger.get("trigger_time"))
    metric_minute = minute_key(metric_sig.get("metric_time"))
    if not trigger_minute or not metric_minute or trigger_minute != metric_minute:
        return False
    trigger_match_id = trigger.get("source_trigger_match_id") or ""
    trigger_event_id = trigger.get("source_trigger_event_id") or ""
    return bool(
        (trigger_match_id and trigger_match_id in metric_sig["source_trigger_match_ids"])
        or (trigger_event_id and trigger_event_id in metric_sig["source_trigger_event_ids"])
    )


def metric_join_missing_reason(trigger: Mapping[str, str], candidates: Sequence[Mapping[str, Any]]) -> str:
    if not candidates:
        return "metric_join_key_missing"
    trigger_minute = minute_key(trigger.get("trigger_time"))
    if trigger_minute:
        metric_minutes = [minute_key(metric.get("metric_time")) for metric in candidates if metric.get("metric_time")]
        if metric_minutes and all(metric_minute != trigger_minute for metric_minute in metric_minutes):
            return "metric_time_mismatch"
    if not any(metric_trigger_refs(metric)["match_ids"] or metric_trigger_refs(metric)["event_ids"] for metric in candidates):
        return "metric_trigger_ref_missing"
    return "metric_trigger_row_join_missing"


def normalize_action_confirmation_metric_rows(
    metric_rows: Sequence[Mapping[str, Any]],
    *,
    metric_run_id: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    allowed_metric_run_ids = set(coerce_metric_run_ids(metric_run_id))
    for raw_metric in metric_rows:
        metric = normalize_mapping(raw_metric)
        if allowed_metric_run_ids:
            row_run_id = str(metric.get("projection_run_id") or metric.get("run_id") or "")
            if row_run_id and row_run_id not in allowed_metric_run_ids:
                continue
            if not row_run_id and len(allowed_metric_run_ids) == 1:
                metric.setdefault("projection_run_id", next(iter(allowed_metric_run_ids)))
        output.append(metric)
    return output


def build_deterministic_action_metric_join(
    outbox_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
    *,
    metric_run_id: str = "",
) -> dict[str, Any]:
    """Attach N3 action-confirmation metric ids to N4 rows without trusting opaque payloads."""

    normalized_metrics = normalize_action_confirmation_metric_rows(metric_rows, metric_run_id=metric_run_id)
    metrics_by_id: dict[tuple[str, str], dict[str, Any]] = {}
    metrics_by_object_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for metric in normalized_metrics:
        asset_kind = str(metric.get("asset_kind") or "")
        metric_id = str(metric.get("action_confirmation_metric_id") or metric.get("source_action_confirmation_metric_id") or "")
        if asset_kind and metric_id:
            metrics_by_id[(asset_kind, metric_id)] = metric
        join_key = action_metric_join_key_from_metric_fact(metric)
        if all(join_key):
            metrics_by_object_key.setdefault(join_key, []).append(metric)

    enriched_rows: list[dict[str, Any]] = []
    matched_rows = 0
    joined_rows = 0
    payload_metric_id_rows = 0
    missing_rows = 0
    duplicate_join_key_rows = 0
    duplicate_join_keys: dict[str, int] = {}
    by_asset: dict[str, Counter[str]] = {}
    missing_sample: list[dict[str, Any]] = []
    for raw_row in outbox_rows:
        row = normalize_outbox_row(deepcopy(raw_row))
        payload = dict(row.get("payload_json") or {})
        row["payload_json"] = payload
        event_type = str(row.get("event_type") or "")
        if event_type != "TriggerMatched":
            enriched_rows.append(row)
            continue

        matched_rows += 1
        trigger_signature = action_metric_trigger_signature_from_outbox_row(row)
        asset_kind = trigger_signature["asset_kind"]
        identity_key = trigger_signature["identity_key"]
        trade_date = trigger_signature["trade_date"]
        by_asset.setdefault(asset_kind or "unknown", Counter())
        by_asset[asset_kind or "unknown"]["trigger_matched_rows"] += 1
        existing_metric_id = infer_source_action_confirmation_metric_id(payload)
        if existing_metric_id:
            payload_metric_id_rows += 1
            if (asset_kind, existing_metric_id) in metrics_by_id:
                joined_rows += 1
                by_asset[asset_kind or "unknown"]["joined_rows"] += 1
            enriched_rows.append(row)
            continue

        join_key = (asset_kind, identity_key, trade_date)
        candidate_metrics = metrics_by_object_key.get(join_key) or []
        metric_matches = [
            metric for metric in candidate_metrics
            if metric_matches_trigger_signature(trigger_signature, metric)
        ]
        if len(metric_matches) > 1:
            duplicate_join_key_rows += 1
            duplicate_join_keys["|".join([*join_key, trigger_signature["source_trigger_match_id"], trigger_signature["trigger_time"]])] = len(metric_matches)
            missing_rows += 1
            by_asset[asset_kind or "unknown"]["missing_rows"] += 1
            missing_sample.append(
                {
                    "event_id": row.get("event_id"),
                    "join_key": list(join_key),
                    "reason": "duplicate_metric_join_key",
                }
            )
            enriched_rows.append(row)
            continue
        if not metric_matches:
            missing_rows += 1
            by_asset[asset_kind or "unknown"]["missing_rows"] += 1
            reason = metric_join_missing_reason(trigger_signature, candidate_metrics)
            if ":BJ:" in identity_key:
                payload["action_confirmation_metric_scope_excluded"] = True
                payload["action_confirmation_metric_scope_excluded_reason"] = "bj_identity_not_in_action_confirmation_metric_scope"
                payload["metric_trace"] = {
                    "join_policy": "deterministic_v2_trigger_row_time_action_metric_run",
                    "join_status": "scope_excluded",
                    "scope_excluded_reason": "bj_identity_not_in_action_confirmation_metric_scope",
                    "join_key": {
                        "asset_kind": asset_kind,
                        "identity_key": identity_key,
                        "trade_date": trade_date,
                        "direction": trigger_signature["direction"],
                        "condition_key": trigger_signature["condition_key"],
                        "source_trigger_match_id": trigger_signature["source_trigger_match_id"],
                        "source_trigger_event_id": trigger_signature["source_trigger_event_id"],
                        "trigger_time": trigger_signature["trigger_time"],
                        "action_metric_run_id": metric_run_id,
                    },
                }
            missing_sample.append(
                {
                    "event_id": row.get("event_id"),
                    "join_key": list(join_key),
                    "trigger_time": trigger_signature["trigger_time"],
                    "source_trigger_match_id": trigger_signature["source_trigger_match_id"],
                    "reason": reason,
                }
            )
            enriched_rows.append(row)
            continue

        metric = metric_matches[0]
        metric_id = str(metric.get("action_confirmation_metric_id") or "")
        payload["source_action_confirmation_metric_id"] = metric_id
        payload["source_projection_run_id"] = str(metric.get("projection_run_id") or metric_run_id)
        payload["metric_trace"] = {
            "join_policy": "deterministic_v2_trigger_row_time_action_metric_run",
            "join_key": {
                "asset_kind": asset_kind,
                "identity_key": identity_key,
                "trade_date": trade_date,
                "direction": trigger_signature["direction"],
                "condition_key": trigger_signature["condition_key"],
                "source_trigger_match_id": trigger_signature["source_trigger_match_id"],
                "source_trigger_event_id": trigger_signature["source_trigger_event_id"],
                "trigger_time": trigger_signature["trigger_time"],
                "metric_time": str(metric.get("metric_time") or ""),
                "action_metric_run_id": str(metric.get("projection_run_id") or metric_run_id),
            },
            "action_confirmation_metric_id": metric_id,
            "projection_run_id": str(metric.get("projection_run_id") or metric_run_id),
            "metric_table": str(metric.get("_metric_table") or ""),
            "metric_time": metric.get("metric_time"),
            "metric_minute_label": metric.get("metric_minute_label"),
            "metric_ready": metric.get("metric_ready"),
            "metric_quality_status": metric.get("metric_quality_status"),
            "projection_schema_version": metric.get("projection_schema_version"),
        }
        joined_rows += 1
        by_asset[asset_kind or "unknown"]["joined_rows"] += 1
        enriched_rows.append(row)

    metric_rows_by_asset = Counter(str(metric.get("asset_kind") or "unknown") for metric in normalized_metrics)
    by_asset_summary = {}
    for asset_kind in sorted(set(by_asset) | set(metric_rows_by_asset)):
        counts = by_asset.get(asset_kind, Counter())
        by_asset_summary[asset_kind] = {
            "n4_trigger_matched_rows": int(counts.get("trigger_matched_rows") or 0),
            "joined_n4_rows": int(counts.get("joined_rows") or 0),
            "missing_n4_rows": int(counts.get("missing_rows") or 0),
            "metric_rows": int(metric_rows_by_asset.get(asset_kind) or 0),
        }
    summary = {
        "join_policy": "deterministic_v2_trigger_row_time_action_metric_run",
        "join_key": [
            "source_trigger_match_id/source_trigger_event_id",
            "asset_kind",
            "identity_key",
            "direction",
            "condition_key",
            "trigger_time/metric_time",
            "trade_date/for_trade_date",
            "action_metric_run_id",
        ],
        "metric_run_id": metric_run_id,
        "metric_rows": len(normalized_metrics),
        "n4_trigger_matched_rows": matched_rows,
        "joined_n4_rows": joined_rows,
        "payload_metric_id_rows": payload_metric_id_rows,
        "missing_n4_rows": missing_rows,
        "coverage": f"{joined_rows}/{matched_rows}",
        "duplicate_join_key_count": len(duplicate_join_keys),
        "duplicate_join_key_rows": duplicate_join_key_rows,
        "duplicate_join_keys_sample": dict(list(sorted(duplicate_join_keys.items()))[:20]),
        "missing_sample": missing_sample[:20],
        "by_asset_kind": by_asset_summary,
    }
    return {
        "outbox_rows": enriched_rows,
        "action_confirmation_metric_facts": metrics_by_id,
        "summary": summary,
    }


def fetch_action_confirmation_metric_rows_by_run_id(cur: Any, metric_run_id: str) -> list[dict[str, Any]]:
    metric_run_ids = coerce_metric_run_ids(metric_run_id)
    if not metric_run_ids:
        return []
    n3t_metric_run_ids = [
        run_id
        for run_id in metric_run_ids
        if str(run_id).startswith(N3T_ACTION_CONFIRMATION_METRIC_RUN_ID_PREFIX)
    ]
    legacy_metric_run_ids = [
        run_id
        for run_id in metric_run_ids
        if not str(run_id).startswith(N3T_ACTION_CONFIRMATION_METRIC_RUN_ID_PREFIX)
    ]
    output: list[dict[str, Any]] = []
    output.extend(
        _fetch_action_confirmation_metric_rows_from_tables(
            cur,
            metric_run_ids=n3t_metric_run_ids,
            table_by_asset_kind=N3T_ACTION_CONFIRMATION_METRIC_TABLE_BY_ASSET_KIND,
        )
    )
    output.extend(
        _fetch_action_confirmation_metric_rows_from_tables(
            cur,
            metric_run_ids=legacy_metric_run_ids,
            table_by_asset_kind=ACTION_CONFIRMATION_METRIC_TABLE_BY_ASSET_KIND,
        )
    )
    return output


def _fetch_action_confirmation_metric_rows_from_tables(
    cur: Any,
    *,
    metric_run_ids: Sequence[str],
    table_by_asset_kind: Mapping[str, str],
) -> list[dict[str, Any]]:
    if not metric_run_ids:
        return []
    output: list[dict[str, Any]] = []
    for asset_kind, table_name in table_by_asset_kind.items():
        cur.execute(
            f"""
            SELECT *
            FROM {table_name}
            WHERE projection_run_id = ANY(%s)
            """,
            (metric_run_ids,),
        )
        for row in cur.fetchall():
            metric = normalize_mapping(row)
            n3t_metric_id = metric.get("n3t_action_confirmation_metric_id")
            if not metric.get("action_confirmation_metric_id") and n3t_metric_id:
                metric["action_confirmation_metric_id"] = n3t_metric_id
            if n3t_metric_id and not metric.get("metric_evaluation_minute_label"):
                metric["metric_evaluation_minute_label"] = _n3t_bar_minute_label(metric)
            metric["asset_kind"] = asset_kind
            metric["_metric_table"] = table_name
            output.append(metric)
    return output


LIVE_WINDOW_METRIC_SELECT_COLUMNS = (
    "action_confirmation_metric_id",
    "projection_run_id",
    "projection_schema_version",
    "for_trade_date",
    "trade_date",
    "asset_kind",
    "identity_key",
    "exchange",
    "code",
    "display_code",
    "name",
    "metric_time",
    "metric_minute_label",
    "current_price",
    "current_price_source",
    "current_price_time",
    "previous_120m_body_high",
    "previous_120m_body_low",
    "previous_30m_body_high",
    "previous_30m_body_low",
    "previous_5m_body_high",
    "previous_5m_body_low",
    "previous_1m_body_high",
    "previous_1m_body_low",
    "current_1m_amount",
    "previous_1m_amount",
    "current_5m_virtual_amount",
    "previous_5m_full_amount",
    "current_30m_virtual_amount",
    "previous_day_same_window_amount",
    "previous_30m_full_amount",
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
    "buy_120m_price_pass",
    "buy_30m_price_pass",
    "buy_5m_price_pass",
    "buy_5m_amount_pass",
    "buy_1m_price_pass",
    "buy_1m_amount_pass",
    "sell_120m_price_pass",
    "sell_30m_price_pass",
    "sell_5m_price_pass",
    "sell_5m_amount_pass",
    "sell_1m_price_pass",
    "sell_1m_amount_pass",
    "metric_quality_status",
    "metric_ready",
    "source_fact_ids",
    "source_minute_refs",
    "previous_day_minute_refs",
    "raw_json->>'virtual_amount_policy_version' AS virtual_amount_policy_version",
)


def build_live_window_metric_lookup_requests(
    outbox_rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    requests: dict[str, dict[str, Any]] = {}
    for raw_row in outbox_rows:
        row = normalize_outbox_row(raw_row)
        if not row_has_explicit_live_confirmation_window(row):
            continue
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
        asset_kind = str(payload.get("asset_kind") or row.get("asset_kind") or "")
        identity_key = str(payload.get("identity_key") or row.get("identity_key") or "")
        if asset_kind not in ACTION_CONFIRMATION_METRIC_TABLE_BY_ASSET_KIND or not identity_key:
            continue
        trigger_time = resolve_metric_alignment_trigger_time(payload, fallback_trigger_time=row.get("event_time"))
        request_key = f"{asset_kind}\0{identity_key}"
        existing = requests.get(request_key)
        if existing is None:
            requests[request_key] = {
                "asset_kind": asset_kind,
                "identity_key": identity_key,
                "min_trigger_time": trigger_time,
                "trigger_metric_ids": {
                    str(infer_source_action_confirmation_metric_id(payload) or "")
                }
                - {""},
            }
            continue
        existing["trigger_metric_ids"].update(
            {
                str(infer_source_action_confirmation_metric_id(payload) or "")
            }
            - {""}
        )
        current_dt = _datetime_or_none(trigger_time)
        previous_dt = _datetime_or_none(existing.get("min_trigger_time"))
        if current_dt is not None and (previous_dt is None or current_dt < previous_dt):
            existing["min_trigger_time"] = trigger_time
    return requests


def fetch_live_window_action_confirmation_metric_rows(
    cur: Any,
    outbox_rows: Sequence[Mapping[str, Any]],
    *,
    metric_run_ids: Sequence[str],
) -> list[dict[str, Any]]:
    requests = build_live_window_metric_lookup_requests(outbox_rows)
    if not requests or not metric_run_ids:
        return []
    by_asset: dict[str, list[dict[str, Any]]] = {}
    for request in requests.values():
        by_asset.setdefault(str(request["asset_kind"]), []).append(request)
    output: list[dict[str, Any]] = []
    select_columns = ", ".join(LIVE_WINDOW_METRIC_SELECT_COLUMNS)
    for asset_kind, asset_requests in sorted(by_asset.items()):
        identities = sorted({str(request["identity_key"]) for request in asset_requests if request.get("identity_key")})
        trigger_times: list[datetime] = []
        missing_trigger_time = []
        for request in asset_requests:
            trigger_time = _datetime_or_none(request.get("min_trigger_time"))
            if trigger_time is None:
                missing_trigger_time.append(
                    {
                        "asset_kind": str(request.get("asset_kind") or ""),
                        "identity_key": str(request.get("identity_key") or ""),
                    }
                )
                continue
            trigger_times.append(trigger_time)
        if missing_trigger_time:
            raise ValueError(f"live_window_min_trigger_time_missing:{missing_trigger_time[:5]}")
        if not identities or not trigger_times:
            raise ValueError(f"live_window_lookup_scope_empty:{asset_kind}")
        min_trigger_time = min(trigger_times).isoformat()
        table_name = ACTION_CONFIRMATION_METRIC_TABLE_BY_ASSET_KIND[asset_kind]
        cur.execute(
            f"""
            SELECT {select_columns}
            FROM {table_name}
            WHERE projection_run_id = ANY(%s)
              AND identity_key = ANY(%s)
              AND metric_time >= %s::timestamptz
            ORDER BY identity_key, metric_time, action_confirmation_metric_id
            """,
            (list(metric_run_ids), identities, min_trigger_time),
        )
        for row in cur.fetchall():
            metric = normalize_mapping(row)
            metric["asset_kind"] = asset_kind
            metric["_metric_table"] = table_name
            output.append(metric)
    return output


def build_action_confirmation_metric_facts_by_identity(
    metric_facts: Mapping[tuple[str, str], Mapping[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    output: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for (asset_kind, _metric_id), raw_fact in metric_facts.items():
        fact = normalize_mapping(raw_fact)
        identity_key = str(fact.get("identity_key") or "")
        if not asset_kind or not identity_key:
            continue
        output.setdefault((str(asset_kind), identity_key), []).append(fact)
    for rows in output.values():
        rows.sort(
            key=lambda row: (
                _datetime_or_none(row.get("metric_time")) or datetime.max.replace(tzinfo=timezone.utc),
                str(row.get("action_confirmation_metric_id") or ""),
            )
        )
    return output


def _datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if value is None:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _n3t_bar_minute_label(metric: Mapping[str, Any]) -> str:
    projection_run_id = str(metric.get("projection_run_id") or metric.get("source_metric_run_id") or "")
    match = re.search(r"(?:^|_)until_([0-2][0-9][0-5][0-9])(?:_|$)", projection_run_id)
    if match:
        value = match.group(1)
        return f"{value[:2]}:{value[2:]}"
    label = str(metric.get("metric_minute_label") or "").strip()
    if re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", label):
        return label
    if re.fullmatch(r"[0-2][0-9][0-5][0-9]", label):
        return f"{label[:2]}:{label[2:]}"
    metric_dt = _datetime_or_none(metric.get("metric_time"))
    return metric_dt.strftime("%H:%M") if metric_dt is not None else ""


def resolve_action_confirmation_metrics_for_execute(
    cur: Any,
    outbox_rows: Sequence[Mapping[str, Any]],
    *,
    baseline_report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    baseline_metric_run_ids = infer_action_metric_run_ids_from_baseline(baseline_report)
    baseline_metric_run_id = ",".join(baseline_metric_run_ids)
    direct_facts = (
        fetch_action_confirmation_metric_facts(cur, outbox_rows, metric_run_id=baseline_metric_run_ids)
        if baseline_metric_run_ids
        else {}
    )
    live_window_metric_lookup_enabled = any(row_has_explicit_live_confirmation_window(row) for row in outbox_rows)
    direct_missing_rows: list[dict[str, str]] = []
    direct_ref_rows = 0
    direct_matched_rows = 0
    for raw_row in outbox_rows:
        row = normalize_outbox_row(raw_row)
        if str(row.get("event_type") or "") != "TriggerMatched":
            continue
        direct_matched_rows += 1
        payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
        asset_kind = str(payload.get("asset_kind") or row.get("asset_kind") or "")
        metric_id = infer_source_action_confirmation_metric_id(payload)
        if asset_kind and metric_id:
            direct_ref_rows += 1
        if not asset_kind or not metric_id or (asset_kind, str(metric_id)) not in direct_facts:
            direct_missing_rows.append(
                {
                    "event_id": str(row.get("event_id") or ""),
                    "asset_kind": asset_kind,
                    "metric_id": str(metric_id or ""),
                }
            )
    if baseline_metric_run_ids and direct_matched_rows and not direct_missing_rows and not live_window_metric_lookup_enabled:
        return {
            "outbox_rows": [normalize_outbox_row(row) for row in outbox_rows],
            "action_confirmation_metric_facts": direct_facts,
            "action_confirmation_metric_facts_by_identity": build_action_confirmation_metric_facts_by_identity(direct_facts),
            "summary": {
                "join_policy": "direct_payload_metric_id",
                "matched_rows": direct_matched_rows,
                "joined_rows": direct_matched_rows,
                "missing_rows": 0,
                "direct_metric_fact_rows": len(direct_facts),
                "metric_fact_lookup_rows": len(direct_facts),
                "metric_run_id": baseline_metric_run_id,
                "metric_run_ids": list(baseline_metric_run_ids),
                "source": "N3_action_confirmation_metric_facts",
                "opaque_action_confirmation_payload_trusted": False,
                "full_metric_run_join_skipped": True,
                "live_window_metric_lookup_enabled": False,
            },
        }
    if baseline_metric_run_ids and direct_matched_rows and direct_ref_rows == direct_matched_rows and direct_missing_rows:
        return {
            "outbox_rows": [normalize_outbox_row(row) for row in outbox_rows],
            "action_confirmation_metric_facts": direct_facts,
            "action_confirmation_metric_facts_by_identity": build_action_confirmation_metric_facts_by_identity(direct_facts),
            "summary": {
                "join_policy": "direct_payload_metric_id",
                "matched_rows": direct_matched_rows,
                "joined_rows": direct_matched_rows - len(direct_missing_rows),
                "missing_rows": len(direct_missing_rows),
                "direct_missing_rows_sample": direct_missing_rows[:20],
                "direct_metric_fact_rows": len(direct_facts),
                "metric_fact_lookup_rows": len(direct_facts),
                "metric_run_id": baseline_metric_run_id,
                "metric_run_ids": list(baseline_metric_run_ids),
                "source": "N3_action_confirmation_metric_facts",
                "opaque_action_confirmation_payload_trusted": False,
                "full_metric_run_join_skipped": True,
                "live_window_metric_lookup_enabled": False,
            },
        }

    if baseline_metric_run_ids and direct_matched_rows and not direct_missing_rows and live_window_metric_lookup_enabled:
        live_metric_rows = fetch_live_window_action_confirmation_metric_rows(
            cur,
            outbox_rows,
            metric_run_ids=baseline_metric_run_ids,
        )
        live_metric_facts = {}
        for metric in live_metric_rows:
            metric_id = str(metric.get("action_confirmation_metric_id") or "")
            asset_kind = str(metric.get("asset_kind") or "")
            if asset_kind and metric_id:
                live_metric_facts[(asset_kind, metric_id)] = metric
        metric_facts = {
            **live_metric_facts,
            **direct_facts,
        }
        metric_facts_by_identity = build_action_confirmation_metric_facts_by_identity(metric_facts)
        return {
            "outbox_rows": [normalize_outbox_row(row) for row in outbox_rows],
            "action_confirmation_metric_facts": metric_facts,
            "action_confirmation_metric_facts_by_identity": metric_facts_by_identity,
            "summary": {
                "join_policy": "direct_payload_metric_id_with_bounded_live_window",
                "matched_rows": direct_matched_rows,
                "joined_rows": direct_matched_rows,
                "missing_rows": 0,
                "direct_metric_fact_rows": len(direct_facts),
                "live_window_metric_rows": len(live_metric_rows),
                "live_window_identity_count": len(metric_facts_by_identity),
                "metric_fact_lookup_rows": len(metric_facts),
                "metric_run_id": baseline_metric_run_id,
                "metric_run_ids": list(baseline_metric_run_ids),
                "source": "N3_action_confirmation_metric_facts",
                "opaque_action_confirmation_payload_trusted": False,
                "full_metric_run_join_skipped": True,
                "live_window_metric_lookup_enabled": True,
                "live_window_metric_lookup_policy": "bounded_identity_window",
            },
        }

    metric_rows = fetch_action_confirmation_metric_rows_by_run_id(cur, baseline_metric_run_id)
    deterministic_join = build_deterministic_action_metric_join(
        outbox_rows,
        metric_rows,
        metric_run_id=baseline_metric_run_id,
    )
    metric_facts = {
        **deterministic_join["action_confirmation_metric_facts"],
        **direct_facts,
    }
    summary = {
        **deterministic_join["summary"],
        "direct_missing_rows_sample": direct_missing_rows[:20],
        "direct_metric_fact_rows": len(direct_facts),
        "metric_fact_lookup_rows": len(metric_facts),
        "source": "N3_action_confirmation_metric_facts",
        "opaque_action_confirmation_payload_trusted": False,
        "full_metric_run_join_skipped": False,
        "live_window_metric_lookup_enabled": live_window_metric_lookup_enabled,
    }
    return {
        "outbox_rows": deterministic_join["outbox_rows"],
        "action_confirmation_metric_facts": metric_facts,
        "action_confirmation_metric_facts_by_identity": build_action_confirmation_metric_facts_by_identity(metric_facts),
        "summary": summary,
    }


def row_has_explicit_live_confirmation_window(row: Mapping[str, Any]) -> bool:
    normalized = normalize_outbox_row(row)
    if str(normalized.get("event_type") or "") != "TriggerMatched":
        return False
    payload = normalized.get("payload_json") if isinstance(normalized.get("payload_json"), Mapping) else {}
    return truthy(payload.get("trigger_live")) and str(payload.get("current_status") or "") == "matched"


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "1", "yes", "passed"}
    return bool(value)


def run_action_consumer_once(
    *,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
    action_run_id: str = LATEST_CANONICAL_N5_EXECUTE_ACTION_RUN_ID,
    source_trigger_run_id: str = LATEST_CANONICAL_N4_SOURCE_RUN_ID,
    consumer_name: str = DEFAULT_N5_1_CONSUMER_NAME,
    json_report_path: str = LATEST_CANONICAL_EXECUTE_REPORT_JSON_PATH,
    markdown_report_path: str = LATEST_CANONICAL_EXECUTE_REPORT_MD_PATH,
    rollback_sql_path: str = LATEST_CANONICAL_ROLLBACK_SQL_PATH,
    allowed_source_run_ids: Sequence[str] | None = None,
    denied_source_run_ids: Sequence[str] | None = None,
    baseline_report_path: str = LATEST_CANONICAL_DRY_RUN_JSON_REPORT_PATH,
    expected_read_event_count: int | None = LATEST_CANONICAL_EXPECTED_PENDING_EVENT_COUNT,
    source_event_types: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Run N5 canonical consume once.

    This function writes only when both confirmation flags are true and the
    contract has no P0 blockers. Callers in this task do not invoke it with
    write flags.
    """

    resolved_allowed_source_run_ids = resolve_allowed_source_run_ids(
        source_trigger_run_id,
        allowed_source_run_ids,
    )
    resolved_denied_source_run_ids = resolve_denied_source_run_ids(
        source_trigger_run_id,
        denied_source_run_ids,
    )

    if not execute or not user_confirmed:
        report = build_current_real_execute_contract_from_rows(
            execute=execute,
            user_confirmed=user_confirmed,
            outbox_rows=[],
            trigger_run={"run_id": source_trigger_run_id, "for_trade_date": infer_trade_date_from_source_run_id(source_trigger_run_id)},
            action_run_id=action_run_id,
            source_trigger_run_id=source_trigger_run_id,
            consumer_name=consumer_name,
            rollback_sql_path=rollback_sql_path,
            allowed_source_run_ids=resolved_allowed_source_run_ids,
            denied_source_run_ids=resolved_denied_source_run_ids,
            baseline_report_path=baseline_report_path,
            json_report_path=json_report_path,
            markdown_report_path=markdown_report_path,
            expected_read_event_count=0,
            stage="N5-canonical-execute-contract-flags-blocked",
        )
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_execute_contract(report))
        return report

    with audited_n5_action_connect(
        dsn,
        stage_id="n5_action_execute_transaction",
        source_run_id=action_run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            baseline_report = load_baseline_report(baseline_report_path)
            before_counts = fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES)
            trigger_run = fetch_trigger_run(cur, source_trigger_run_id)
            outbox_rows = fetch_current_real_pending_outbox_rows(
                cur,
                source_trigger_run_id,
                source_event_types=source_event_types,
            )
            metric_resolution = resolve_action_confirmation_metrics_for_execute(
                cur,
                outbox_rows,
                baseline_report=baseline_report,
            )
            outbox_rows = metric_resolution["outbox_rows"]
            action_confirmation_metric_facts = metric_resolution["action_confirmation_metric_facts"]
            action_confirmation_metric_facts_by_identity = metric_resolution[
                "action_confirmation_metric_facts_by_identity"
            ]
            all_status_counts = fetch_current_real_outbox_status_counts(cur, source_trigger_run_id)
            existing_inbox_keys = fetch_existing_inbox_keys(cur, consumer_name)
            existing_checkpoints = fetch_existing_checkpoints(cur, consumer_name)
            contract = build_action_consumer_run_once_dry_run_report_from_rows(
                trigger_run_id=source_trigger_run_id,
                action_run_id=action_run_id,
                consumer_name=consumer_name,
                trigger_run=trigger_run,
                outbox_rows=outbox_rows,
                existing_inbox_keys=existing_inbox_keys,
                existing_checkpoints=existing_checkpoints,
                before_row_counts=before_counts,
                after_row_counts=before_counts,
                action_confirmation_metric_facts=action_confirmation_metric_facts,
                action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
                baseline_report=baseline_report,
                baseline_report_path=baseline_report_path,
                stage="N5-canonical-execute",
                expected_read_event_count=expected_read_event_count,
                require_period_trigger_baseline_trace=True,
                allowed_source_run_ids=resolved_allowed_source_run_ids,
                denied_source_run_ids=resolved_denied_source_run_ids,
                rollback_sql_path=rollback_sql_path,
                json_report_path=json_report_path,
                markdown_report_path=markdown_report_path,
                sample_limit=80,
            )
            execute_contract = build_current_real_execute_contract_from_rows(
                execute=True,
                user_confirmed=True,
                outbox_rows=outbox_rows,
                trigger_run=trigger_run,
                action_run_id=action_run_id,
                consumer_name=consumer_name,
                source_trigger_run_id=source_trigger_run_id,
                baseline_report=baseline_report,
                before_row_counts=before_counts,
                after_row_counts=before_counts,
                action_confirmation_metric_facts=action_confirmation_metric_facts,
                action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
                rollback_sql_path=rollback_sql_path,
                allowed_source_run_ids=resolved_allowed_source_run_ids,
                denied_source_run_ids=resolved_denied_source_run_ids,
                baseline_report_path=baseline_report_path,
                json_report_path=json_report_path,
                markdown_report_path=markdown_report_path,
                expected_read_event_count=expected_read_event_count,
                stage="N5-canonical-execute-contract",
            )
            contract["deterministic_action_metric_join_summary"] = metric_resolution["summary"]
            execute_contract["deterministic_action_metric_join_summary"] = metric_resolution["summary"]
            execute_contract["current_real_outbox_status_counts"] = all_status_counts
            if execute_contract["quality"]["p0_count"]:
                conn.rollback()
                write_json(json_report_path, execute_contract)
                write_text(markdown_report_path, format_execute_contract(execute_contract))
                raise ActionExecuteError("N5 current-real action execute blocked by P0 contract findings")
            executable_plan = {
                **contract,
                **build_executable_plan_from_rows(
                    outbox_rows=outbox_rows,
                    action_run_id=action_run_id,
                    consumer_name=consumer_name,
                    existing_inbox_keys=existing_inbox_keys,
                    existing_checkpoints=existing_checkpoints,
                    action_confirmation_metric_facts=action_confirmation_metric_facts,
                    action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
                ),
                "execute_quality": execute_contract["quality"],
            }
            inserted_counts = execute_action_transaction(cur, trigger_run=trigger_run, plan=executable_plan)
        conn.commit()

    execute_contract["result"] = "EXECUTED"
    execute_contract["inserted_counts"] = inserted_counts
    execute_contract["side_effects"] = build_execute_side_effects(executed=True)
    write_json(json_report_path, execute_contract)
    write_text(markdown_report_path, format_execute_contract(execute_contract))
    return execute_contract


N5_CONSUMPTION_ONLY_SMOKE_ALLOWED_EVENT_TYPES = ("TriggerMatched",)


def run_consumption_only_smoke_once(
    *,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
    smoke_run_id: str | None,
    source_trigger_run_id: str,
    consumer_name: str,
    source_event_types: Sequence[str] | None,
    max_events: int | None,
    max_runtime_seconds: int | None,
    heartbeat_interval_seconds: int | None,
    json_report_path: str,
    markdown_report_path: str | None = None,
    status_json_path: str | None = None,
    stop_file_path: str | None = None,
) -> dict[str, Any]:
    """Run the bounded N5 worker smoke in consumption-only mode.

    This path intentionally bypasses action candidate/fact/event/outbox
    generation. When confirmed, it writes only scoped run, quality, inbox, and
    checkpoint rows so runtime_control can prove consumption watermarks without
    producing downstream action messages.
    """

    def blocked_report() -> dict[str, Any]:
        return build_consumption_only_smoke_contract_from_rows(
            execute=execute,
            user_confirmed=user_confirmed,
            smoke_run_id=smoke_run_id,
            source_trigger_run_id=source_trigger_run_id,
            consumer_name=consumer_name,
            source_event_types=source_event_types,
            max_events=max_events,
            max_runtime_seconds=max_runtime_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            stop_file_path=stop_file_path,
            outbox_rows=[],
            trigger_run={
                "run_id": source_trigger_run_id,
                "for_trade_date": infer_trade_date_from_source_run_id(source_trigger_run_id),
            },
            json_report_path=json_report_path,
            markdown_report_path=markdown_report_path,
            status_json_path=status_json_path,
        )

    if not execute or not user_confirmed:
        report = blocked_report()
        write_json(json_report_path, report)
        if markdown_report_path:
            write_text(markdown_report_path, format_consumption_only_smoke_report(report))
        if status_json_path:
            write_json(status_json_path, build_consumption_only_smoke_status(report))
        return report

    with audited_n5_action_connect(
        dsn,
        stage_id="n5_consumption_only_smoke",
        source_run_id=smoke_run_id or source_trigger_run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            trigger_run = fetch_trigger_run(cur, source_trigger_run_id)
            existing_inbox_keys = fetch_existing_inbox_keys(cur, consumer_name)
            existing_checkpoints = fetch_existing_checkpoints(cur, consumer_name)
            outbox_rows = fetch_consumption_only_smoke_outbox_rows(
                cur,
                source_trigger_run_id=source_trigger_run_id,
                source_event_types=source_event_types or (),
                max_events=max_events or 0,
            )
            report = build_consumption_only_smoke_contract_from_rows(
                execute=execute,
                user_confirmed=user_confirmed,
                smoke_run_id=smoke_run_id,
                source_trigger_run_id=source_trigger_run_id,
                consumer_name=consumer_name,
                source_event_types=source_event_types,
                max_events=max_events,
                max_runtime_seconds=max_runtime_seconds,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                stop_file_path=stop_file_path,
                outbox_rows=outbox_rows,
                trigger_run=trigger_run,
                existing_inbox_keys=existing_inbox_keys,
                existing_checkpoints=existing_checkpoints,
                json_report_path=json_report_path,
                markdown_report_path=markdown_report_path,
                status_json_path=status_json_path,
            )
            if not report["allow_execute"]:
                conn.rollback()
                write_json(json_report_path, report)
                if markdown_report_path:
                    write_text(markdown_report_path, format_consumption_only_smoke_report(report))
                if status_json_path:
                    write_json(status_json_path, build_consumption_only_smoke_status(report))
                return report
            inserted_counts = execute_consumption_only_smoke_transaction(cur, trigger_run=trigger_run, plan=report)
        conn.commit()

    report["result"] = "EXECUTED"
    report["inserted_counts"] = inserted_counts
    report["side_effects"] = build_consumption_only_smoke_side_effects(executed=True)
    write_json(json_report_path, report)
    if markdown_report_path:
        write_text(markdown_report_path, format_consumption_only_smoke_report(report))
    if status_json_path:
        write_json(status_json_path, build_consumption_only_smoke_status(report))
    return report


def run_semantic_action_smoke_once(
    *,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
    smoke_run_id: str | None,
    source_trigger_run_id: str,
    consumer_name: str,
    source_event_types: Sequence[str] | None,
    metric_run_id: str | None,
    max_events: int | None,
    max_runtime_seconds: int | None,
    heartbeat_interval_seconds: int | None,
    json_report_path: str,
    markdown_report_path: str | None = None,
    status_json_path: str | None = None,
    stop_file_path: str | None = None,
    excluded_event_ids: Sequence[str] | None = None,
    current_only_trigger_matched: bool = False,
    rollback_sql_path: str = DEFAULT_N5_CANONICAL_20260528_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    """Run bounded semantic action smoke with normal N5 action confirmation semantics."""

    if not execute or not user_confirmed:
        report = build_semantic_action_smoke_contract_from_rows(
            execute=execute,
            user_confirmed=user_confirmed,
            smoke_run_id=smoke_run_id,
            source_trigger_run_id=source_trigger_run_id,
            consumer_name=consumer_name,
            source_event_types=source_event_types,
            excluded_event_ids=excluded_event_ids,
            metric_run_id=metric_run_id,
            max_events=max_events,
            max_runtime_seconds=max_runtime_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            outbox_rows=[],
            trigger_run={
                "run_id": source_trigger_run_id,
                "for_trade_date": infer_trade_date_from_source_run_id(source_trigger_run_id),
            },
            json_report_path=json_report_path,
            markdown_report_path=markdown_report_path,
            status_json_path=status_json_path,
            stop_file_path=stop_file_path,
            rollback_sql_path=rollback_sql_path,
            current_only_trigger_matched=current_only_trigger_matched,
        )
        write_json(json_report_path, report)
        if markdown_report_path:
            write_text(markdown_report_path, format_execute_contract(report))
        if status_json_path:
            write_json(status_json_path, build_semantic_action_smoke_status(report))
        return report

    with audited_n5_action_connect(
        dsn,
        stage_id="n5_semantic_action_smoke",
        source_run_id=smoke_run_id or source_trigger_run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            trigger_run = fetch_trigger_run(cur, source_trigger_run_id)
            outbox_rows = fetch_semantic_action_smoke_outbox_rows(
                cur,
                source_trigger_run_id=source_trigger_run_id,
                source_event_types=source_event_types or (),
                excluded_event_ids=excluded_event_ids or (),
                max_events=max_events or 0,
                current_only_trigger_matched=current_only_trigger_matched,
            )
            baseline_report = semantic_action_smoke_baseline_report(
                source_trigger_run_id=source_trigger_run_id,
                consumer_name=consumer_name,
                metric_run_id=metric_run_id,
            )
            metric_resolution = resolve_action_confirmation_metrics_for_execute(
                cur,
                outbox_rows,
                baseline_report=baseline_report,
            )
            outbox_rows = metric_resolution["outbox_rows"]
            action_confirmation_metric_facts = metric_resolution["action_confirmation_metric_facts"]
            action_confirmation_metric_facts_by_identity = metric_resolution[
                "action_confirmation_metric_facts_by_identity"
            ]
            existing_inbox_keys = fetch_existing_inbox_keys(cur, consumer_name)
            existing_checkpoints = fetch_existing_checkpoints(cur, consumer_name)
            report = build_semantic_action_smoke_contract_from_rows(
                execute=execute,
                user_confirmed=user_confirmed,
                smoke_run_id=smoke_run_id,
                source_trigger_run_id=source_trigger_run_id,
                consumer_name=consumer_name,
                source_event_types=source_event_types,
                excluded_event_ids=excluded_event_ids,
                metric_run_id=metric_run_id,
                max_events=max_events,
                max_runtime_seconds=max_runtime_seconds,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
                outbox_rows=outbox_rows,
                trigger_run=trigger_run,
                action_confirmation_metric_facts=action_confirmation_metric_facts,
                action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
                existing_inbox_keys=existing_inbox_keys,
                existing_checkpoints=existing_checkpoints,
                json_report_path=json_report_path,
                markdown_report_path=markdown_report_path,
                status_json_path=status_json_path,
                stop_file_path=stop_file_path,
                metric_join_summary=metric_resolution["summary"],
                rollback_sql_path=rollback_sql_path,
                current_only_trigger_matched=current_only_trigger_matched,
            )
            if report["quality"]["p0_count"]:
                conn.rollback()
                write_json(json_report_path, report)
                if markdown_report_path:
                    write_text(markdown_report_path, format_execute_contract(report))
                if status_json_path:
                    write_json(status_json_path, build_semantic_action_smoke_status(report))
                return report
            executable_plan = {
                **report,
                **build_executable_plan_from_rows(
                    outbox_rows=outbox_rows,
                    action_run_id=str(smoke_run_id),
                    consumer_name=consumer_name,
                    existing_inbox_keys=existing_inbox_keys,
                    existing_checkpoints=existing_checkpoints,
                    action_confirmation_metric_facts=action_confirmation_metric_facts,
                    action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
                ),
                "execute_quality": report["quality"],
            }
            inserted_counts = execute_action_transaction(cur, trigger_run=trigger_run, plan=executable_plan)
        conn.commit()

    report["result"] = "EXECUTED"
    report["inserted_counts"] = inserted_counts
    report["side_effects"] = build_execute_side_effects(executed=True)
    report["side_effects"]["n4_outbox_status_updated"] = False
    write_json(json_report_path, report)
    if markdown_report_path:
        write_text(markdown_report_path, format_execute_contract(report))
    if status_json_path:
        write_json(status_json_path, build_semantic_action_smoke_status(report))
    return report


def fetch_semantic_action_smoke_outbox_rows(
    cur: Any,
    *,
    source_trigger_run_id: str,
    source_event_types: Sequence[str],
    excluded_event_ids: Sequence[str] | None = None,
    max_events: int,
    current_only_trigger_matched: bool = False,
) -> list[dict[str, Any]]:
    excluded_ids = [str(item) for item in (excluded_event_ids or []) if str(item)]
    if current_only_trigger_matched:
        cur.execute(
            """
            SELECT o.outbox_id, o.event_id, o.event_type, o.event_schema_version, o.trade_date,
                   o.asset_kind, o.identity_key, o.event_time, o.source_layer, o.source_run_id,
                   o.dedup_key, o.partition_key, o.payload_json, o.status, o.created_at
            FROM common_event_outbox o
            JOIN common_trigger_state s
              ON s.trigger_state_id::text = o.payload_json->>'trigger_state_id'
            WHERE o.source_layer = 'N4_trigger'
              AND o.source_run_id = %s
              AND o.status = 'pending'
              AND o.event_type = ANY(%s)
              AND o.event_id <> ALL(%s)
              AND o.event_type = 'TriggerMatched'
              AND COALESCE(o.payload_json->>'source_trigger_match_id', o.payload_json->>'trigger_match_id') IS NOT NULL
              AND s.run_id = %s
              AND s.for_trade_date = o.trade_date
              AND s.current_status = 'matched'
              AND s.last_trigger_match_id::text = COALESCE(o.payload_json->>'source_trigger_match_id', o.payload_json->>'trigger_match_id')
            ORDER BY o.partition_key, o.event_time, o.outbox_id, o.event_id
            LIMIT %s
            """,
            (source_trigger_run_id, list(source_event_types), excluded_ids, source_trigger_run_id, max_events),
        )
        return [normalize_mapping(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT outbox_id, event_id, event_type, event_schema_version, trade_date,
               asset_kind, identity_key, event_time, source_layer, source_run_id,
               dedup_key, partition_key, payload_json, status, created_at
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = %s
          AND status = 'pending'
          AND event_type = ANY(%s)
          AND event_id <> ALL(%s)
        ORDER BY partition_key, event_time, outbox_id, event_id
        LIMIT %s
        """,
        (source_trigger_run_id, list(source_event_types), excluded_ids, max_events),
    )
    return [normalize_mapping(row) for row in cur.fetchall()]


def build_semantic_action_smoke_contract_from_rows(
    *,
    execute: bool,
    user_confirmed: bool,
    smoke_run_id: str | None,
    source_trigger_run_id: str,
    consumer_name: str,
    source_event_types: Sequence[str] | None,
    metric_run_id: str | None,
    max_events: int | None,
    max_runtime_seconds: int | None,
    heartbeat_interval_seconds: int | None,
    outbox_rows: Sequence[Mapping[str, Any]],
    trigger_run: Mapping[str, Any] | None,
    action_confirmation_metric_facts: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None = None,
    action_confirmation_metric_facts_by_identity: Mapping[Any, Sequence[Mapping[str, Any]]] | None = None,
    existing_inbox_keys: Mapping[str, set[str]] | None = None,
    existing_checkpoints: Mapping[str, Mapping[str, Any]] | None = None,
    json_report_path: str | None = None,
    markdown_report_path: str | None = None,
    status_json_path: str | None = None,
    stop_file_path: str | None = None,
    metric_join_summary: Mapping[str, Any] | None = None,
    excluded_event_ids: Sequence[str] | None = None,
    current_only_trigger_matched: bool = False,
    rollback_sql_path: str = DEFAULT_N5_CANONICAL_20260528_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    normalized_event_types = [str(item) for item in (source_event_types or []) if str(item)]
    normalized_excluded_event_ids = list(dict.fromkeys(str(item) for item in (excluded_event_ids or []) if str(item)))
    excluded_set = set(normalized_excluded_event_ids)
    filtered_rows = [
        row
        for row in outbox_rows
        if str(row.get("event_type") or "") in set(normalized_event_types)
        and str(row.get("source_run_id") or "") == source_trigger_run_id
        and str(row.get("status") or "pending") == "pending"
        and str(row.get("event_id") or "") not in excluded_set
    ]
    bounded_rows = filtered_rows[: max_events or 0]
    baseline_report = semantic_action_smoke_baseline_report(
        source_trigger_run_id=source_trigger_run_id,
        consumer_name=consumer_name,
        metric_run_id=metric_run_id,
    )
    contract = build_current_real_execute_contract_from_rows(
        execute=execute,
        user_confirmed=user_confirmed,
        outbox_rows=bounded_rows,
        trigger_run=trigger_run or {
            "run_id": source_trigger_run_id,
            "for_trade_date": infer_trade_date_from_source_run_id(source_trigger_run_id),
        },
        action_run_id=smoke_run_id or "",
        consumer_name=consumer_name,
        source_trigger_run_id=source_trigger_run_id,
        baseline_report=baseline_report,
        action_confirmation_metric_facts=action_confirmation_metric_facts,
        action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
        rollback_sql_path=rollback_sql_path,
        allowed_source_run_ids=[source_trigger_run_id],
        expected_read_event_count=len(bounded_rows),
        stage="N5-worker-semantic-action-smoke-contract",
    )
    smoke_items = build_semantic_action_smoke_quality_items(
        execute=execute,
        user_confirmed=user_confirmed,
        smoke_run_id=smoke_run_id,
        source_trigger_run_id=source_trigger_run_id,
        consumer_name=consumer_name,
        source_event_types=normalized_event_types,
        metric_run_id=metric_run_id,
        max_events=max_events,
        max_runtime_seconds=max_runtime_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        stop_file_path=stop_file_path,
    )
    quality_items = list(contract["quality"]["items"]) + smoke_items
    quality_counts = count_quality_severities(quality_items)
    smoke_blockers = [
        item["gate_code"]
        for item in smoke_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    ]
    contract["quality"] = {
        "p0_count": quality_counts["P0"],
        "p1_count": quality_counts["P1"],
        "p2_count": quality_counts["P2"],
        "items": quality_items,
    }
    contract["allow_execute"] = bool(contract.get("allow_execute")) and not smoke_blockers
    contract["blockers"] = list(dict.fromkeys([*(contract.get("blockers") or []), *smoke_blockers]))
    if smoke_blockers:
        contract["result"] = "BLOCKED"
    contract["stage"] = "N5-worker-semantic-action-smoke"
    contract["smoke_run_id"] = smoke_run_id
    contract["action_run_id"] = smoke_run_id
    contract["source_event_types"] = normalized_event_types
    contract["source_event_filter"] = {
        "excluded_event_ids": normalized_excluded_event_ids,
        "excluded_event_count": len(normalized_excluded_event_ids),
        "excluded_event_reason": "reviewed_unmaterializable_n3_action_metric_source_event"
        if normalized_excluded_event_ids
        else None,
        "filter_applied_before_action_plan": bool(normalized_excluded_event_ids or current_only_trigger_matched),
        "current_only_trigger_matched": bool(current_only_trigger_matched),
        "current_only_criteria": {
            "current_status": "matched",
            "last_trigger_match_id": "payload.source_trigger_match_id_or_trigger_match_id",
        }
        if current_only_trigger_matched
        else None,
    }
    contract["bounded_controls"] = {
        "max_events": max_events,
        "max_runtime_seconds": max_runtime_seconds,
        "heartbeat_interval_seconds": heartbeat_interval_seconds,
        "status_json_path": status_json_path,
        "stop_file_path": stop_file_path,
        "stop_file_present": bool(stop_file_path and os.path.exists(stop_file_path)),
    }
    contract["metric_binding"] = {
        "metric_run_id": metric_run_id,
        "required": True,
        "deterministic_join_required": True,
        "opaque_action_confirmation_payload_trusted": False,
        "metric_join_summary": dict(metric_join_summary or {}),
    }
    contract["report_paths"] = {
        "json_report_path": json_report_path,
        "markdown_report_path": markdown_report_path,
        "status_json_path": status_json_path,
    }
    contract.setdefault("side_effects", build_execute_side_effects(executed=False))
    contract["side_effects"]["n4_outbox_status_updated"] = False
    contract["side_effects"]["worker_started"] = False
    return contract


def semantic_action_smoke_baseline_report(
    *,
    source_trigger_run_id: str,
    consumer_name: str,
    metric_run_id: str | None,
) -> dict[str, Any]:
    return {
        "source_trigger_run_id": source_trigger_run_id,
        "n3_action_metric_run_id": metric_run_id or "",
        "metric_run_id": metric_run_id or "",
        "consumer_strategy": {
            "uses_dedicated_consumer": True,
            "dedicated_consumer_name": consumer_name,
        },
    }


def build_semantic_action_smoke_quality_items(
    *,
    execute: bool,
    user_confirmed: bool,
    smoke_run_id: str | None,
    source_trigger_run_id: str,
    consumer_name: str,
    source_event_types: Sequence[str],
    metric_run_id: str | None,
    max_events: int | None,
    max_runtime_seconds: int | None,
    heartbeat_interval_seconds: int | None,
    stop_file_path: str | None,
) -> list[dict[str, Any]]:
    def item(gate_code: str, gate_name: str, status: str, actual_value: Any, expected_value: str = "passed") -> dict[str, Any]:
        return quality_item(
            "P0",
            status,
            gate_code,
            gate_name,
            expected=expected_value,
            actual=json.dumps(to_jsonable(actual_value), ensure_ascii=False),
            details={
                "smoke_run_id": smoke_run_id,
                "source_trigger_run_id": source_trigger_run_id,
                "consumer_name": consumer_name,
                "metric_run_id": metric_run_id,
            },
        )

    return [
        item(
            "n5_semantic_action_smoke_double_confirmation",
            "semantic action smoke requires --execute and --user-confirmed",
            "passed" if execute and user_confirmed else "failed",
            {"execute": execute, "user_confirmed": user_confirmed},
        ),
        item("n5_semantic_action_smoke_run_id_present", "smoke_run_id is required", "passed" if smoke_run_id else "failed", smoke_run_id),
        item(
            "n5_semantic_action_smoke_metric_run_id_required",
            "metric_run_id is required for deterministic metric join",
            "passed" if metric_run_id else "failed",
            metric_run_id,
        ),
        item(
            "n5_semantic_action_smoke_source_event_type_guard",
            "semantic action smoke may only consume TriggerMatched",
            "passed" if source_event_types == ["TriggerMatched"] else "failed",
            list(source_event_types),
        ),
        item(
            "n5_semantic_action_smoke_bounded_controls",
            "bounded semantic action smoke controls are required",
            "passed"
            if (max_events or 0) > 0 and (max_runtime_seconds or 0) > 0 and (heartbeat_interval_seconds or 0) > 0
            else "failed",
            {
                "max_events": max_events,
                "max_runtime_seconds": max_runtime_seconds,
                "heartbeat_interval_seconds": heartbeat_interval_seconds,
            },
        ),
        item(
            "n5_semantic_action_smoke_stop_file_guard",
            "stop file must not exist before start",
            "passed" if not (stop_file_path and os.path.exists(stop_file_path)) else "failed",
            {"stop_file_path": stop_file_path, "exists": bool(stop_file_path and os.path.exists(stop_file_path))},
        ),
    ]


def build_semantic_action_smoke_status(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": report.get("stage"),
        "result": report.get("result"),
        "smoke_run_id": report.get("smoke_run_id"),
        "source_trigger_run_id": report.get("source_trigger_run_id"),
        "consumer_name": report.get("consumer_name"),
        "allow_execute": report.get("allow_execute"),
        "blockers": report.get("blockers"),
        "bounded_controls": report.get("bounded_controls"),
        "metric_binding": report.get("metric_binding"),
        "planned_write_scope": report.get("planned_write_scope"),
    }


def fetch_consumption_only_smoke_outbox_rows(
    cur: Any,
    *,
    source_trigger_run_id: str,
    source_event_types: Sequence[str],
    max_events: int,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT outbox_id, event_id, event_type, event_schema_version, trade_date,
               asset_kind, identity_key, event_time, source_layer, source_run_id,
               dedup_key, partition_key, payload_json, status, created_at
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = %s
          AND status = 'pending'
          AND event_type = ANY(%s)
        ORDER BY partition_key, event_time, outbox_id, event_id
        LIMIT %s
        """,
        (source_trigger_run_id, list(source_event_types), max_events),
    )
    return [normalize_mapping(row) for row in cur.fetchall()]


def build_consumption_only_smoke_contract_from_rows(
    *,
    execute: bool,
    user_confirmed: bool,
    smoke_run_id: str | None,
    source_trigger_run_id: str,
    consumer_name: str,
    source_event_types: Sequence[str] | None,
    max_events: int | None,
    max_runtime_seconds: int | None,
    heartbeat_interval_seconds: int | None,
    outbox_rows: Sequence[Mapping[str, Any]],
    trigger_run: Mapping[str, Any] | None,
    existing_inbox_keys: Mapping[str, set[str]] | None = None,
    existing_checkpoints: Mapping[str, Mapping[str, Any]] | None = None,
    stop_file_path: str | None = None,
    json_report_path: str | None = None,
    markdown_report_path: str | None = None,
    status_json_path: str | None = None,
) -> dict[str, Any]:
    normalized_event_types = [str(item) for item in (source_event_types or []) if str(item)]
    normalized_rows = [
        normalize_outbox_row(row)
        for row in outbox_rows
        if str(row.get("event_type") or "") in set(normalized_event_types)
    ]
    consumer_plan = build_consumer_plan(
        rows=normalized_rows,
        consumer_name=consumer_name,
        existing_inbox_keys=existing_inbox_keys or empty_inbox_keys(),
        existing_checkpoints=existing_checkpoints or {},
    )
    planned_inbox_count = sum(1 for row in consumer_plan["event_plans"] if row.get("consumer_status") == "planned_receive")
    checkpoint_count = len(consumer_plan["checkpoint_write_plan"])
    quality_items = build_consumption_only_smoke_quality_items(
        execute=execute,
        user_confirmed=user_confirmed,
        smoke_run_id=smoke_run_id,
        source_trigger_run_id=source_trigger_run_id,
        consumer_name=consumer_name,
        source_event_types=normalized_event_types,
        max_events=max_events,
        max_runtime_seconds=max_runtime_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        stop_file_path=stop_file_path,
    )
    quality_counts = count_quality_severities(quality_items)
    blockers = [
        item["gate_code"]
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    ]
    allow_execute = execute and user_confirmed and not blockers
    planned_write_scope = {
        "common_action_run": 1 if allow_execute else 0,
        "common_action_quality_item": len(quality_items) if allow_execute else 0,
        "stock_action_fact": 0,
        "index_action_fact": 0,
        "board_action_fact": 0,
        "common_action_event": 0,
        "common_event_outbox": 0,
        "common_event_inbox": planned_inbox_count if allow_execute else 0,
        "common_event_consumer_checkpoint": checkpoint_count if allow_execute else 0,
        "common_position_state": 0,
        "common_position_event": 0,
    }
    output_event_plan_summary = {
        "planned_event_count": 0,
        "by_event_type": {
            "ActionExecuted": 0,
            "ActionBlocked": 0,
            "ActionEligible": 0,
            "ActionSkipped": 0,
            "ActionEvent": 0,
            "HintEvent": 0,
            "RiskEvent": 0,
            "PositionEvent": 0,
        },
    }
    return {
        "gate": "N5_WORKER_SCOPED_CONSUMPTION_SMOKE_RUNNER",
        "stage": "N5-worker-scoped-consumption-only-smoke",
        "result": "READY" if allow_execute else "BLOCKED",
        "execute": execute,
        "user_confirmed": user_confirmed,
        "allow_execute": allow_execute,
        "blockers": blockers,
        "smoke_run_id": smoke_run_id,
        "action_run_id": smoke_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "consumer_name": consumer_name,
        "source_event_types": normalized_event_types,
        "trigger_run": dict(trigger_run or {}),
        "bounded_controls": {
            "max_events": max_events,
            "max_runtime_seconds": max_runtime_seconds,
            "heartbeat_interval_seconds": heartbeat_interval_seconds,
            "status_json_path": status_json_path,
            "stop_file_path": stop_file_path,
            "stop_file_present": bool(stop_file_path and os.path.exists(stop_file_path)),
        },
        "consumer_plan": consumer_plan,
        "consumer_plan_summary": {
            "read_event_count": len(normalized_rows),
            "planned_inbox_count": planned_inbox_count,
            "checkpoint_write_plan_count": checkpoint_count,
        },
        "action_write_plan": [],
        "action_write_plan_summary": {
            "plan_row_count": 0,
            "planned_action_fact_count": 0,
            "quality_plan_only_count": 0,
        },
        "output_event_plan": [],
        "output_event_plan_summary": output_event_plan_summary,
        "planned_write_scope": planned_write_scope,
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": build_consumption_only_smoke_side_effects(executed=False),
        "report_paths": {
            "json_report_path": json_report_path,
            "markdown_report_path": markdown_report_path,
            "status_json_path": status_json_path,
        },
        "forbidden_write_proof": {
            "action_fact_rows": 0,
            "common_action_event_rows": 0,
            "n5_outbox_rows": 0,
            "n4_outbox_status_update": 0,
            "n6_user_refs": 0,
            "delivery_push_voice_mobile": False,
            "sim_position_pnl_real_trade": False,
            "proposal_order_trade": False,
        },
    }


def build_consumption_only_smoke_quality_items(
    *,
    execute: bool,
    user_confirmed: bool,
    smoke_run_id: str | None,
    source_trigger_run_id: str,
    consumer_name: str,
    source_event_types: Sequence[str],
    max_events: int | None,
    max_runtime_seconds: int | None,
    heartbeat_interval_seconds: int | None,
    stop_file_path: str | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add(gate_code: str, gate_name: str, status: str, actual_value: Any, expected_value: str = "passed") -> None:
        items.append(
            quality_item(
                "P0",
                status,
                gate_code,
                gate_name,
                expected=expected_value,
                actual=json.dumps(to_jsonable(actual_value), ensure_ascii=False),
                details={
                    "smoke_run_id": smoke_run_id,
                    "source_trigger_run_id": source_trigger_run_id,
                    "consumer_name": consumer_name,
                },
            )
        )

    add(
        "n5_consumption_only_smoke_double_confirmation",
        "consumption-only smoke requires --execute and --user-confirmed",
        "passed" if execute and user_confirmed else "failed",
        {"execute": execute, "user_confirmed": user_confirmed},
    )
    add("n5_consumption_only_smoke_run_id_present", "smoke_run_id is required", "passed" if smoke_run_id else "failed", smoke_run_id)
    add(
        "n5_consumption_only_smoke_source_event_type_guard",
        "source_event_type must be TriggerMatched; N5 cannot execute from pending/state broadcasts",
        "passed"
        if source_event_types and all(item in N5_CONSUMPTION_ONLY_SMOKE_ALLOWED_EVENT_TYPES for item in source_event_types)
        else "failed",
        list(source_event_types),
    )
    add(
        "n5_consumption_only_smoke_bounded_controls",
        "bounded smoke controls are required",
        "passed"
        if (max_events or 0) > 0 and (max_runtime_seconds or 0) > 0 and (heartbeat_interval_seconds or 0) > 0
        else "failed",
        {
            "max_events": max_events,
            "max_runtime_seconds": max_runtime_seconds,
            "heartbeat_interval_seconds": heartbeat_interval_seconds,
        },
    )
    add(
        "n5_consumption_only_smoke_stop_file_guard",
        "stop file must not exist before start",
        "passed" if not (stop_file_path and os.path.exists(stop_file_path)) else "failed",
        {"stop_file_path": stop_file_path, "exists": bool(stop_file_path and os.path.exists(stop_file_path))},
    )
    add(
        "n5_consumption_only_smoke_forbidden_write_scope",
        "smoke path must not plan action facts/events/outbox or N4 outbox update",
        "passed",
        {
            "stock_index_board_action_fact": "0/0/0",
            "common_action_event": 0,
            "n5_common_event_outbox": 0,
            "n4_outbox_status_update": 0,
        },
    )
    return items


def execute_consumption_only_smoke_transaction(cur: Any, *, trigger_run: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, int]:
    smoke_run_id = str(plan["smoke_run_id"])
    consumer_name = str(plan["consumer_name"])
    source_trigger_run_id = str(plan["source_trigger_run_id"])
    insert_action_run(
        cur,
        action_run_id=smoke_run_id,
        source_trigger_run_id=source_trigger_run_id,
        trigger_run=trigger_run,
        plan=plan,
    )
    quality_count = insert_consumption_only_smoke_quality_items(
        cur,
        smoke_run_id=smoke_run_id,
        source_trigger_run_id=source_trigger_run_id,
        trigger_run=trigger_run,
        items=plan["quality"]["items"],
    )
    inbox_count = insert_inbox_records(cur, rows=plan["consumer_plan"]["event_plans"], consumer_name=consumer_name)
    checkpoint_count = upsert_checkpoints(
        cur,
        rows=plan["consumer_plan"]["checkpoint_write_plan"],
        consumer_name=consumer_name,
        action_run_id=smoke_run_id,
    )
    persisted_quality_counts = resolve_persisted_run_quality_counts(plan)
    update_action_run_finished(
        cur,
        action_run_id=smoke_run_id,
        p0_count=persisted_quality_counts["P0"],
        p1_count=persisted_quality_counts["P1"],
        p2_count=persisted_quality_counts["P2"],
    )
    return {
        "common_action_run": 1,
        "common_action_quality_item": quality_count,
        "stock_action_fact": 0,
        "index_action_fact": 0,
        "board_action_fact": 0,
        "common_action_event": 0,
        "common_event_outbox": 0,
        "common_event_inbox": inbox_count,
        "common_event_consumer_checkpoint": checkpoint_count,
    }


def insert_consumption_only_smoke_quality_items(
    cur: Any,
    *,
    smoke_run_id: str,
    source_trigger_run_id: str,
    trigger_run: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
) -> int:
    if not items:
        return 0
    values = [
        (
            smoke_run_id,
            source_trigger_run_id,
            trigger_run.get("for_trade_date") or infer_trade_date_from_source_run_id(source_trigger_run_id),
            "common",
            "event_contract",
            "common_event_inbox",
            item.get("gate_code"),
            item.get("gate_name"),
            item.get("severity"),
            item.get("status"),
            json.dumps(to_jsonable(item.get("expected_value")), ensure_ascii=False),
            json.dumps(to_jsonable(item.get("actual_value")), ensure_ascii=False),
            None,
            Jsonb(to_jsonable(item)),
        )
        for item in items
    ]
    cur.executemany(
        """
        INSERT INTO common_action_quality_item (
          run_id, source_trigger_run_id, for_trade_date, data_domain, layer_scope,
          table_name, gate_code, gate_name, severity, status, expected_value,
          actual_value, identity_key, details
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        values,
    )
    rowcount = getattr(cur, "rowcount", None)
    return int(rowcount) if isinstance(rowcount, int) and rowcount >= 0 else len(values)


def build_consumption_only_smoke_side_effects(*, executed: bool) -> dict[str, Any]:
    return {
        "writes_performed": executed,
        "common_action_run_written": executed,
        "common_action_quality_item_written": executed,
        "common_event_inbox_written": executed,
        "common_event_consumer_checkpoint_written": executed,
        "action_fact_written": False,
        "common_action_event_written": False,
        "n5_outbox_written": False,
        "n4_outbox_status_updated": False,
        "n5_outbox_consumed": False,
        "n6_user_layer_touched": False,
        "worker_started": False,
        "delivery_push_voice_mobile": False,
        "sim_position_pnl_real_trade": False,
        "proposal_order_trade": False,
        "old_system_touched": False,
    }


def build_consumption_only_smoke_status(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": report.get("stage"),
        "result": report.get("result"),
        "smoke_run_id": report.get("smoke_run_id"),
        "source_trigger_run_id": report.get("source_trigger_run_id"),
        "consumer_name": report.get("consumer_name"),
        "allow_execute": report.get("allow_execute"),
        "blockers": report.get("blockers"),
        "bounded_controls": report.get("bounded_controls"),
        "planned_write_scope": report.get("planned_write_scope"),
    }


def format_consumption_only_smoke_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    scope = report.get("planned_write_scope") or {}
    return "\n".join(
        [
            "# N5 Worker Scoped Consumption-Only Smoke Runner",
            "",
            f"Result: `{report.get('result')}`",
            "",
            "```text",
            f"smoke_run_id={report.get('smoke_run_id')}",
            f"source_trigger_run_id={report.get('source_trigger_run_id')}",
            f"consumer_name={report.get('consumer_name')}",
            f"source_event_types={report.get('source_event_types')}",
            f"allow_execute={report.get('allow_execute')}",
            f"blockers={report.get('blockers')}",
            f"P0/P1/P2={quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
            f"planned_write_scope={scope}",
            "ActionExecuted/ActionBlocked/ActionEligible/ActionSkipped=0/0/0/0",
            "N4 outbox status update=0",
            "N6/user/delivery/sim/trade refs=0",
            "worker_started=false",
            "```",
        ]
    )


def fetch_current_real_pending_outbox_rows(
    cur: Any,
    source_run_id: str,
    *,
    source_event_types: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_event_types = [str(item) for item in (source_event_types or []) if str(item)]
    event_type_filter = ""
    params: list[Any] = [source_run_id]
    if normalized_event_types:
        event_type_filter = "AND event_type = ANY(%s)"
        params.append(normalized_event_types)
    cur.execute(
        f"""
        SELECT outbox_id, event_id, event_type, event_schema_version, trade_date,
               asset_kind, identity_key, event_time, source_layer, source_run_id,
               dedup_key, partition_key, payload_json, status, created_at
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = %s
          AND status = 'pending'
          {event_type_filter}
        ORDER BY partition_key, event_time, outbox_id, event_id
        """,
        tuple(params),
    )
    return [normalize_mapping(row) for row in cur.fetchall()]


def fetch_current_real_outbox_status_counts(cur: Any, source_run_id: str) -> dict[str, int]:
    cur.execute(
        """
        SELECT status, count(*)::bigint AS row_count
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = %s
        GROUP BY status
        ORDER BY status
        """,
        (source_run_id,),
    )
    return {str(row["status"]): int(row["row_count"]) for row in cur.fetchall()}


def build_executable_plan_from_rows(
    *,
    outbox_rows: Sequence[Mapping[str, Any]],
    action_run_id: str,
    consumer_name: str,
    existing_inbox_keys: Mapping[str, set[str]] | None,
    existing_checkpoints: Mapping[str, Mapping[str, Any]] | None,
    action_confirmation_metric_facts: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None = None,
    action_confirmation_metric_facts_by_identity: Mapping[Any, Sequence[Mapping[str, Any]]] | None = None,
) -> dict[str, Any]:
    normalized_rows = [normalize_outbox_row(row) for row in outbox_rows]
    consumer_plan = build_consumer_plan(
        rows=normalized_rows,
        consumer_name=consumer_name,
        existing_inbox_keys=existing_inbox_keys or empty_inbox_keys(),
        existing_checkpoints=existing_checkpoints or {},
    )
    accepted_rows = [
        item["source_outbox_row"]
        for item in consumer_plan["event_plans"]
        if item["consumer_status"] == "planned_receive"
    ]
    candidates = build_action_candidates_from_outbox_rows(
        accepted_rows,
        action_run_id=action_run_id,
        action_confirmation_metric_facts=action_confirmation_metric_facts,
        action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
    )
    action_write_plan = build_action_write_plan(candidates)
    output_event_plan = build_output_event_plan(action_write_plan)
    return {
        "consumer_plan": consumer_plan,
        "action_candidates": candidates,
        "action_write_plan": action_write_plan,
        "output_event_plan": output_event_plan,
    }


def execute_action_transaction(cur: Any, *, trigger_run: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, int]:
    action_run_id = str(plan["action_run_id"])
    consumer_name = str(plan["consumer_name"])
    source_trigger_run_id = str(plan["source_trigger_run_id"])
    dry_run_plan = plan
    all_action_write_plan = [
        normalize_action_persistence_row(row)
        for row in dry_run_plan["action_write_plan"]
    ]
    action_write_plan = [row for row in all_action_write_plan if row.get("plan_status") == "planned_action_fact"]
    quality_plan = [row for row in dry_run_plan["action_write_plan"] if row.get("plan_status") == "quality_plan_only"]
    insert_action_run(
        cur,
        action_run_id=action_run_id,
        source_trigger_run_id=source_trigger_run_id,
        trigger_run=trigger_run,
        plan=dry_run_plan,
    )
    quality_count = insert_pending_quality_items(
        cur,
        action_run_id=action_run_id,
        source_trigger_run_id=source_trigger_run_id,
        trigger_run=trigger_run,
        rows=quality_plan,
    )
    fact_event_counts = insert_action_facts_and_events(
        cur,
        action_run_id=action_run_id,
        source_trigger_run_id=source_trigger_run_id,
        trigger_run=trigger_run,
        rows=action_write_plan,
    )
    tracking_state_count = upsert_action_tracking_states(
        cur,
        rows=all_action_write_plan,
        action_run_id=action_run_id,
        source_trigger_run_id=source_trigger_run_id,
    )
    inbox_count = insert_inbox_records(cur, rows=dry_run_plan["consumer_plan"]["event_plans"], consumer_name=consumer_name)
    checkpoint_count = upsert_checkpoints(
        cur,
        rows=dry_run_plan["consumer_plan"]["checkpoint_write_plan"],
        consumer_name=consumer_name,
        action_run_id=action_run_id,
    )
    persisted_quality_counts = resolve_persisted_run_quality_counts(dry_run_plan)
    update_action_run_finished(
        cur,
        action_run_id=action_run_id,
        p0_count=persisted_quality_counts["P0"],
        p1_count=persisted_quality_counts["P1"],
        p2_count=persisted_quality_counts["P2"],
    )
    return {
        "common_action_run": 1,
        "common_action_quality_item": quality_count,
        **fact_event_counts,
        "common_action_tracking_state": tracking_state_count,
        "common_event_inbox": inbox_count,
        "common_event_consumer_checkpoint": checkpoint_count,
    }


def upsert_action_tracking_states(
    cur: Any,
    *,
    rows: Sequence[Mapping[str, Any]],
    action_run_id: str,
    source_trigger_run_id: str,
) -> int:
    writable = [
        row
        for row in rows
        if row.get("would_create_action_tracking_state")
        or row.get("would_update_action_tracking_state")
        or row.get("would_expire_action_tracking_state")
    ]
    values = [build_action_tracking_state_upsert_values(row, action_run_id, source_trigger_run_id) for row in writable]
    values = [value for value in values if value is not None]
    if not values:
        return 0
    cur.executemany(
        """
        INSERT INTO common_action_tracking_state (
          run_id, source_trigger_run_id, source_trigger_state_id,
          source_trigger_event_id, source_trigger_event_type, source_trigger_match_id,
          trade_date, state_key, asset_kind, identity_key, direction, signal_type,
          condition_key, trigger_live, current_status, primary_trigger_period,
          all_trigger_periods, trigger_mark_candidate, latest_n4_event_id,
          latest_n4_event_type, latest_n4_event_time, action_state,
          confirmation_status, tracking_status, planned_output_event_type,
          expired_reason, expired_at, tracking_until, last_checked_minute_label,
          raw_json, updated_at
        )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()
        )
        ON CONFLICT (run_id, state_key)
        DO UPDATE SET
          source_trigger_run_id = EXCLUDED.source_trigger_run_id,
          source_trigger_state_id = COALESCE(EXCLUDED.source_trigger_state_id, common_action_tracking_state.source_trigger_state_id),
          source_trigger_event_id = EXCLUDED.source_trigger_event_id,
          source_trigger_event_type = EXCLUDED.source_trigger_event_type,
          source_trigger_match_id = COALESCE(EXCLUDED.source_trigger_match_id, common_action_tracking_state.source_trigger_match_id),
          trigger_live = EXCLUDED.trigger_live,
          current_status = EXCLUDED.current_status,
          primary_trigger_period = EXCLUDED.primary_trigger_period,
          all_trigger_periods = EXCLUDED.all_trigger_periods,
          trigger_mark_candidate = EXCLUDED.trigger_mark_candidate,
          latest_n4_event_id = EXCLUDED.latest_n4_event_id,
          latest_n4_event_type = EXCLUDED.latest_n4_event_type,
          latest_n4_event_time = EXCLUDED.latest_n4_event_time,
          action_state = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.action_state
            WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.action_state
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired') THEN common_action_tracking_state.action_state
            ELSE EXCLUDED.action_state
          END,
          confirmation_status = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.confirmation_status
            WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.confirmation_status
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired') THEN common_action_tracking_state.confirmation_status
            ELSE EXCLUDED.confirmation_status
          END,
          tracking_status = CASE
            WHEN EXCLUDED.action_state = 'executed' THEN EXCLUDED.tracking_status
            WHEN common_action_tracking_state.action_state = 'executed' THEN common_action_tracking_state.tracking_status
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired') THEN common_action_tracking_state.tracking_status
            ELSE EXCLUDED.tracking_status
          END,
          planned_output_event_type = COALESCE(EXCLUDED.planned_output_event_type, common_action_tracking_state.planned_output_event_type),
          expired_reason = CASE
            WHEN EXCLUDED.action_state = 'expired' THEN EXCLUDED.expired_reason
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired', 'executed') THEN common_action_tracking_state.expired_reason
            ELSE EXCLUDED.expired_reason
          END,
          expired_at = CASE
            WHEN EXCLUDED.action_state = 'expired' THEN EXCLUDED.expired_at
            WHEN common_action_tracking_state.action_state IN ('blocked', 'skipped', 'expired', 'executed') THEN common_action_tracking_state.expired_at
            ELSE EXCLUDED.expired_at
          END,
          tracking_until = EXCLUDED.tracking_until,
          last_checked_minute_label = EXCLUDED.last_checked_minute_label,
          raw_json = EXCLUDED.raw_json,
          updated_at = now()
        """,
        values,
    )
    return len({(value[0], value[7]) for value in values})


def build_action_tracking_state_upsert_values(
    row: Mapping[str, Any],
    action_run_id: str,
    source_trigger_run_id: str,
) -> tuple[Any, ...] | None:
    row = normalize_action_persistence_row(row)
    tracking_plan = row.get("tracking_state_plan") if isinstance(row.get("tracking_state_plan"), Mapping) else {}
    tracking_state = tracking_plan.get("tracking_state") if isinstance(tracking_plan.get("tracking_state"), Mapping) else {}
    if not tracking_state:
        return None
    state_key = tracking_state.get("state_key") or row.get("tracking_state_key")
    if not state_key:
        return None
    planned_output_event_type = tracking_state.get("planned_output_event_type") or row.get("planned_output_event_type")
    return (
        action_run_id,
        source_trigger_run_id,
        tracking_state.get("source_trigger_state_id") or row.get("trigger_state_id"),
        tracking_state.get("source_trigger_event_id") or row.get("source_trigger_event_id"),
        tracking_state.get("source_trigger_event_type") or row.get("source_trigger_event_type"),
        tracking_state.get("source_trigger_match_id") or row.get("source_trigger_match_id"),
        tracking_state.get("trade_date"),
        state_key,
        tracking_state.get("asset_kind") or row.get("asset_kind"),
        tracking_state.get("identity_key") or row.get("identity_key"),
        tracking_state.get("direction") or row.get("direction"),
        tracking_state.get("signal_type") or row.get("signal_type"),
        tracking_state.get("condition_key") or row.get("condition_key"),
        bool(tracking_state.get("trigger_live")),
        tracking_state.get("current_status") or row.get("current_status"),
        tracking_state.get("primary_trigger_period") or row.get("primary_trigger_period"),
        Jsonb(to_jsonable(tracking_state.get("all_trigger_periods") or [])),
        tracking_state.get("trigger_mark_candidate") or row.get("trigger_mark_candidate"),
        tracking_state.get("latest_n4_event_id") or row.get("source_trigger_event_id"),
        tracking_state.get("latest_n4_event_type") or row.get("source_trigger_event_type"),
        parse_event_time(tracking_state.get("latest_n4_event_time")),
        tracking_state.get("action_state") or row.get("action_state"),
        tracking_state.get("confirmation_status") or row.get("confirmation_status"),
        tracking_state.get("tracking_status") or row.get("action_state"),
        planned_output_event_type,
        tracking_state.get("expired_reason"),
        parse_event_time(tracking_state.get("expired_at")) if tracking_state.get("expired_at") else None,
        parse_event_time(tracking_state.get("tracking_until")) if tracking_state.get("tracking_until") else None,
        tracking_state.get("last_checked_minute_label"),
        Jsonb(to_jsonable(tracking_state.get("raw_json") or row.get("source_payload_json") or {})),
    )


def resolve_persisted_run_quality_counts(plan: Mapping[str, Any]) -> dict[str, int]:
    """Choose run-level quality counts from the execute gate, not stale dry-run diagnostics."""

    quality = plan.get("execute_quality") or plan.get("quality") or {}
    items = quality.get("items") if isinstance(quality, Mapping) else None
    if isinstance(items, list):
        return count_quality_severities(items)
    return {
        "P0": int((quality or {}).get("p0_count") or 0),
        "P1": int((quality or {}).get("p1_count") or 0),
        "P2": int((quality or {}).get("p2_count") or 0),
    }


def insert_action_run(
    cur: Any,
    *,
    action_run_id: str,
    source_trigger_run_id: str,
    trigger_run: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> None:
    action_summary = plan["action_write_plan_summary"]
    output_summary = plan["output_event_plan_summary"]
    consumer_summary = plan["consumer_plan_summary"]
    cur.execute(
        """
        INSERT INTO common_action_run (
          run_id, source_trigger_run_id, source_condition_run_id, for_trade_date,
          mode, status, p0_count, p1_count, p2_count, trigger_outbox_row_count,
          action_candidate_row_count, action_fact_row_count, action_event_outbox_count,
          position_event_row_count, consumer_checkpoint_updated,
          common_event_inbox_updated, raw_json, started_at
        )
        VALUES (%s, %s, %s, %s, 'execute', 'running', 0, 0, 0, %s, %s, %s, %s, 0, true, true, %s, now())
        ON CONFLICT (run_id) DO UPDATE SET
          status = 'running',
          raw_json = EXCLUDED.raw_json,
          updated_at = now()
        """,
        (
            action_run_id,
            source_trigger_run_id,
            trigger_run.get("source_condition_run_id"),
            trigger_run.get("for_trade_date") or infer_trade_date_from_plan(plan),
            int(consumer_summary.get("read_event_count") or 0),
            int(action_summary.get("plan_row_count") or 0),
            int(action_summary.get("planned_action_fact_count") or 0),
            int(output_summary.get("planned_event_count") or 0),
            Jsonb(to_jsonable({"stage": "N5-canonical-execute", "plan_summary": plan_summary_for_raw_json(plan)})),
        ),
    )


def insert_pending_quality_items(
    cur: Any,
    *,
    action_run_id: str,
    source_trigger_run_id: str,
    trigger_run: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> int:
    if not rows:
        return 0
    values = []
    for row in rows:
        values.append(
            (
                action_run_id,
                source_trigger_run_id,
                trigger_run.get("for_trade_date") or infer_trade_date_from_source_run_id(source_trigger_run_id),
                str(row.get("asset_kind") or "common"),
                "trigger_outbox_preflight",
                "common_event_outbox",
                "n5_execute_pending_market_data_quality_only",
                "TriggerPendingMarketData is quality only and did not generate action fact",
                "P0",
                "passed",
                "quality only",
                str(row.get("data_quality_status") or ""),
                row.get("identity_key"),
                Jsonb(to_jsonable(row)),
            )
        )
    cur.executemany(
        """
        INSERT INTO common_action_quality_item (
          run_id, source_trigger_run_id, for_trade_date, data_domain, layer_scope,
          table_name, gate_code, gate_name, severity, status, expected_value,
          actual_value, identity_key, details
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        values,
    )
    rowcount = getattr(cur, "rowcount", None)
    return int(rowcount) if isinstance(rowcount, int) and rowcount >= 0 else len(rows)


def insert_action_facts_and_events(
    cur: Any,
    *,
    action_run_id: str,
    source_trigger_run_id: str,
    trigger_run: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    repository = EventRepository(cur)
    for row in rows:
        row = normalize_action_persistence_row(row)
        table_name = str(row["target_action_fact_table"])
        action_fact_id = insert_action_fact(
            cur,
            action_run_id=action_run_id,
            source_trigger_run_id=source_trigger_run_id,
            trigger_run=trigger_run,
            row=row,
            table_name=table_name,
        )
        payload = build_action_event_passthrough_payload(
            row=row,
            table_name=table_name,
            action_fact_id=action_fact_id,
        )
        envelope = build_n5_action_event(
            event_type=str(row["planned_output_event_type"]),
            asset_kind=str(row["asset_kind"]),
            identity_key=str(row["identity_key"]),
            trade_date=str(trigger_run.get("for_trade_date") or infer_trade_date_from_source_run_id(source_trigger_run_id)),
            event_time=parse_event_time(row.get("action_event_time") or row.get("trigger_time") or row.get("event_time")),
            action_run_id=action_run_id,
            source_trigger_event_id=str(row["source_trigger_event_id"]),
            source_trigger_run_id=source_trigger_run_id,
            source_trigger_state_id=row.get("trigger_state_id"),
            source_trigger_match_id=row.get("source_trigger_match_id") or "",
            source_condition_run_id=str(row.get("source_condition_run_id") or trigger_run.get("source_condition_run_id") or ""),
            direction=str(row["direction"]),
            signal_type=str(row["signal_type"]),
            condition_key=str(row["condition_key"]),
            original_condition_key=str(row.get("original_condition_key") or row["condition_key"]),
            trigger_period=str(payload.get("trigger_period") or row["trigger_period"]),
            action_mark=row.get("final_action_mark"),
            action_state=str(row.get("action_state") or "eligible"),
            confirmation_status=str(row.get("confirmation_status") or "pending"),
            action_policy="n5_confirmation_only",
            eligibility_reason=row.get("decision_status"),
            blocked_reason=row.get("blocked_reason"),
            trace_json=row.get("trace_json") or {},
            action_type=str(row["action_type"]),
            lane=str(row["lane"]),
            data_quality_status=str(row["data_quality_status"]),
            source_market_data_run_id=row.get("source_market_data_run_id"),
            source_market_trace=row.get("source_market_trace") or {},
            payload=payload,
        )
        insert_common_action_event(
            cur,
            action_run_id=action_run_id,
            source_trigger_run_id=source_trigger_run_id,
            trigger_run=trigger_run,
            row=row,
            action_fact_id=action_fact_id,
            event_id=envelope.event_id,
            payload=envelope.payload_json,
        )
        repository.insert_outbox(envelope)
        counts[table_name] += 1
        counts["common_action_event"] += 1
        counts["common_event_outbox"] += 1
    return {
        "stock_action_fact": counts["stock_action_fact"],
        "index_action_fact": counts["index_action_fact"],
        "board_action_fact": counts["board_action_fact"],
        "common_action_event": counts["common_action_event"],
        "common_event_outbox": counts["common_event_outbox"],
    }


def build_action_event_passthrough_payload(*, row: Mapping[str, Any], table_name: str, action_fact_id: int) -> dict[str, Any]:
    """Build the N5 action event payload from N5 fact/N4 TriggerMatched facts."""

    source_payload = row.get("source_payload_json") if isinstance(row.get("source_payload_json"), Mapping) else {}
    source_market_trace = row.get("source_market_trace") if isinstance(row.get("source_market_trace"), Mapping) else {}
    period_trace = source_market_trace.get("period_trigger_baseline_trace")
    if not isinstance(period_trace, Mapping):
        period_trace = source_payload.get("period_trigger_baseline_trace") if isinstance(source_payload, Mapping) else None
    if not isinstance(period_trace, Mapping):
        period_trace = {}
    period_passthrough = canonicalize_n5_trigger_period_passthrough(
        row=row,
        source_payload=source_payload,
        period_trace=period_trace,
    )
    return {
        "source_action_fact_table": table_name,
        "source_action_fact_id": action_fact_id,
        "action_key": row["action_key"],
        "blocked_reason": row.get("blocked_reason"),
        "n4_trigger_event_id": row.get("source_trigger_event_id"),
        "trigger_price": row.get("trigger_price") or source_payload.get("trigger_price"),
        "trigger_period": period_passthrough["trigger_period"],
        "triggered_periods": period_passthrough["triggered_periods"],
        "all_trigger_periods": period_passthrough["all_trigger_periods"],
        "primary_trigger_period": period_passthrough["primary_trigger_period"],
        "trigger_kind": period_passthrough["trigger_kind"],
        "period_trigger_baseline_trace": dict(period_trace),
        "baseline_source": resolve_baseline_source_for_period(period_trace, period_passthrough["primary_trigger_period"]),
    }


FORMAL_N5_TRIGGER_PERIODS = ("Y", "Q", "M", "W", "D")


def canonicalize_n5_trigger_period_passthrough(
    *,
    row: Mapping[str, Any],
    source_payload: Mapping[str, Any],
    period_trace: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep 30m as marker evidence, not a formal N5 trigger period."""

    trigger_kind = str(row.get("trigger_kind") or source_payload.get("trigger_kind") or "")
    condition_key = str(row.get("condition_key") or source_payload.get("condition_key") or "")
    original_condition_key = str(row.get("original_condition_key") or source_payload.get("original_condition_key") or condition_key)
    if trigger_kind == "hint" and condition_key in {"BUY_HINT", "SELL_HINT"} and original_condition_key in {"BUY_HINT", "SELL_HINT"}:
        return {
            "trigger_kind": "hint",
            "trigger_period": "30m",
            "triggered_periods": [],
            "all_trigger_periods": [],
            "primary_trigger_period": None,
        }

    raw_triggered = formal_period_values(source_payload.get("triggered_periods"))
    raw_all = formal_period_values(source_payload.get("all_trigger_periods"))
    all_periods = raw_all or raw_triggered
    triggered_periods = raw_triggered
    raw_primary = str(row.get("primary_trigger_period") or source_payload.get("primary_trigger_period") or "").strip()
    primary = raw_primary if raw_primary in FORMAL_N5_TRIGGER_PERIODS else (all_periods[0] if all_periods else None)
    trigger_period = str(row.get("trigger_period") or source_payload.get("trigger_period") or "").strip()
    if trigger_period not in FORMAL_N5_TRIGGER_PERIODS:
        trigger_period = primary or trigger_period
    return {
        "trigger_kind": trigger_kind or "trigger",
        "trigger_period": trigger_period,
        "triggered_periods": triggered_periods,
        "all_trigger_periods": all_periods,
        "primary_trigger_period": primary,
    }


def formal_period_values(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError):
                parsed = [text]
            return formal_period_values(parsed)
        raw_values = [part.strip() for part in text.split(",") if part.strip()]
    elif isinstance(value, (list, tuple, set)):
        raw_values = [str(item).strip() for item in value if str(item).strip()]
    else:
        raw_values = [str(value).strip()]
    return [period for period in raw_values if period in FORMAL_N5_TRIGGER_PERIODS]


def formal_periods_from_condition_key(condition_key: str) -> list[str]:
    if ":" not in condition_key:
        return []
    raw_periods = condition_key.split(":", 1)[1]
    return formal_period_values(raw_periods)


def formal_periods_from_trace(period_trace: Mapping[str, Any]) -> list[str]:
    required_periods = formal_period_values(period_trace.get("required_periods"))
    if required_periods:
        return required_periods
    traced_periods = period_trace.get("traced_periods")
    if isinstance(traced_periods, Mapping):
        return formal_period_values(list(traced_periods.keys()))
    return []


def resolve_baseline_source_for_period(period_trace: Mapping[str, Any], primary_trigger_period: Any) -> str | None:
    """Resolve baseline_source for the actual triggered period without condition_key inference."""

    period_key = str(primary_trigger_period or "")
    traced_periods = period_trace.get("traced_periods")
    if isinstance(traced_periods, Mapping) and period_key:
        period_entry = traced_periods.get(period_key)
        if isinstance(period_entry, Mapping) and period_entry.get("baseline_source"):
            return str(period_entry["baseline_source"])
    if period_trace.get("baseline_source"):
        return str(period_trace["baseline_source"])
    return None


def insert_action_fact(
    cur: Any,
    *,
    action_run_id: str,
    source_trigger_run_id: str,
    trigger_run: Mapping[str, Any],
    row: Mapping[str, Any],
    table_name: str,
) -> int:
    row = normalize_action_persistence_row(row)
    identity_column = {
        "stock_action_fact": "stock_identity_key",
        "index_action_fact": "index_identity_key",
        "board_action_fact": "board_identity_key",
    }[table_name]
    columns = (
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
    )
    source_payload = row.get("source_payload_json") or {}
    values = [
        action_run_id,
        source_trigger_run_id,
        row.get("source_trigger_event_id"),
        row.get("source_trigger_event_type"),
        row.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION,
        row.get("source_trigger_match_id"),
        row.get("trigger_state_id"),
        row.get("trigger_state_id"),
        row.get("source_condition_run_id") or trigger_run.get("source_condition_run_id"),
        row.get("source_market_data_run_id"),
        Jsonb(to_jsonable(row.get("source_market_trace") or {})),
        trigger_run.get("for_trade_date") or infer_trade_date_from_source_run_id(source_trigger_run_id),
        row.get("asset_kind"),
        row.get("identity_key"),
        row.get("identity_key"),
        row.get("direction"),
        row.get("signal_type"),
        row.get("condition_key"),
        row.get("original_condition_key") or row.get("condition_key"),
        row.get("trigger_period"),
        parse_event_time(row.get("trigger_time")),
        row.get("trigger_price"),
        row.get("trigger_mark_candidate"),
        row.get("final_action_mark"),
        row.get("action_state"),
        row.get("confirmation_status"),
        row.get("tracking_until"),
        row.get("last_checked_minute_label"),
        Jsonb(to_jsonable(row.get("trace_json") or {})),
        row.get("action_policy") or ACTION_POLICY,
        row.get("action_type"),
        row.get("lane"),
        row.get("decision_status"),
        row.get("data_quality_status"),
        bool(row.get("closed_minute_required")),
        bool(row.get("closed_minute_verified")),
        row.get("minute_context_status"),
        row.get("action_bucket"),
        row.get("action_key"),
        row.get("dedup_key"),
        Jsonb(to_jsonable(source_payload)),
        Jsonb(to_jsonable({"stage": "N5-canonical-execute", "plan": dict(row)})),
    ]
    placeholders = ", ".join(["%s"] * len(columns))
    cur.execute(
        f"""
        INSERT INTO {table_name} ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT (run_id, action_key) DO NOTHING
        RETURNING action_fact_id
        """,
        values,
    )
    fetched = cur.fetchone()
    if isinstance(fetched, Mapping) and fetched.get("action_fact_id") is not None:
        return int(fetched["action_fact_id"])
    cur.execute(
        f"""
        SELECT action_fact_id
        FROM {table_name}
        WHERE run_id = %s
          AND action_key = %s
        """,
        (action_run_id, row.get("action_key")),
    )
    return int(cur.fetchone()["action_fact_id"])


def insert_common_action_event(
    cur: Any,
    *,
    action_run_id: str,
    source_trigger_run_id: str,
    trigger_run: Mapping[str, Any],
    row: Mapping[str, Any],
    action_fact_id: int,
    event_id: str,
    payload: Mapping[str, Any],
) -> None:
    row = normalize_action_persistence_row(row)
    cur.execute(
        """
        INSERT INTO common_action_event (
          event_id, event_schema_version, run_id, source_trigger_run_id,
          source_trigger_event_id, source_trigger_match_id, source_trigger_state_id,
          source_condition_run_id,
          source_market_data_run_id, source_market_trace, source_action_fact_table,
          source_action_fact_id, for_trade_date, asset_kind, identity_key, direction,
          signal_type, condition_key, original_condition_key, trigger_period,
          trigger_mark_candidate, action_mark, action_state, confirmation_status,
          tracking_until, last_checked_minute_label, trace_json, action_policy,
          event_type, action_type, lane,
          data_quality_status, action_key, dedup_key, partition_key, payload_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_id) DO NOTHING
        """,
        (
            event_id,
            row.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION,
            action_run_id,
            source_trigger_run_id,
            row.get("source_trigger_event_id"),
            row.get("source_trigger_match_id"),
            row.get("trigger_state_id"),
            row.get("source_condition_run_id") or trigger_run.get("source_condition_run_id"),
            row.get("source_market_data_run_id"),
            Jsonb(to_jsonable(row.get("source_market_trace") or {})),
            row.get("target_action_fact_table"),
            action_fact_id,
            trigger_run.get("for_trade_date") or infer_trade_date_from_source_run_id(source_trigger_run_id),
            row.get("asset_kind"),
            row.get("identity_key"),
            row.get("direction"),
            row.get("signal_type"),
            row.get("condition_key"),
            row.get("original_condition_key") or row.get("condition_key"),
            row.get("trigger_period"),
            row.get("trigger_mark_candidate"),
            row.get("final_action_mark"),
            row.get("action_state"),
            row.get("confirmation_status"),
            row.get("tracking_until"),
            row.get("last_checked_minute_label"),
            Jsonb(to_jsonable(row.get("trace_json") or {})),
            row.get("action_policy") or ACTION_POLICY,
            row.get("planned_output_event_type"),
            row.get("action_type"),
            row.get("lane"),
            row.get("data_quality_status"),
            row.get("action_key"),
            row.get("dedup_key"),
            row.get("identity_key"),
            Jsonb(to_jsonable(payload)),
        ),
    )


def insert_inbox_records(cur: Any, *, rows: Sequence[Mapping[str, Any]], consumer_name: str) -> int:
    writable = [row for row in rows if row.get("consumer_status") == "planned_receive"]
    if not writable:
        return 0
    values = [
        (
            consumer_name,
            row["event_id"],
            row["event_type"],
            row.get("event_schema_version") or DEFAULT_EVENT_SCHEMA_VERSION,
            row["source_layer"],
            row["source_run_id"],
            row["dedup_key"],
            row["partition_key"],
            Jsonb(to_jsonable(row.get("payload_json") or {})),
            "processed",
            1,
            Jsonb(to_jsonable(row.get("source_outbox_row") or {})),
        )
        for row in writable
    ]
    cur.executemany(
        """
        INSERT INTO common_event_inbox (
          consumer_name, event_id, event_type, event_schema_version,
          source_layer, source_run_id, dedup_key, partition_key,
          payload_json, status, attempt_count, processed_at, raw_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
        ON CONFLICT (consumer_name, event_id) DO NOTHING
        """,
        values,
    )
    return len(writable)


def upsert_checkpoints(
    cur: Any,
    *,
    rows: Sequence[Mapping[str, Any]],
    consumer_name: str,
    action_run_id: str,
) -> int:
    if not rows:
        return 0
    values = [
        (
            consumer_name,
            row["partition_key"],
            SOURCE_LAYER,
            row.get("last_event_id"),
            parse_event_time(row.get("last_event_time")),
            row.get("last_outbox_id"),
            Jsonb(to_jsonable({**(row.get("checkpoint_payload") or {}), "action_run_id": action_run_id})),
        )
        for row in rows
    ]
    cur.executemany(
        """
        INSERT INTO common_event_consumer_checkpoint (
          consumer_name, partition_key, source_layer, last_event_id,
          last_event_time, last_outbox_id, checkpoint_payload, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (consumer_name, partition_key, source_layer)
        DO UPDATE SET
          last_event_id = EXCLUDED.last_event_id,
          last_event_time = EXCLUDED.last_event_time,
          last_outbox_id = EXCLUDED.last_outbox_id,
          checkpoint_payload = EXCLUDED.checkpoint_payload,
          updated_at = now()
        WHERE common_event_consumer_checkpoint.last_outbox_id IS NULL
           OR EXCLUDED.last_outbox_id > common_event_consumer_checkpoint.last_outbox_id
        """,
        values,
    )
    rowcount = getattr(cur, "rowcount", None)
    return int(rowcount) if isinstance(rowcount, int) and rowcount >= 0 else len(rows)


def update_action_run_finished(cur: Any, *, action_run_id: str, p0_count: int, p1_count: int, p2_count: int) -> None:
    status = "passed" if p0_count == 0 else "failed"
    cur.execute(
        """
        UPDATE common_action_run
        SET status = %s,
            p0_count = %s,
            p1_count = %s,
            p2_count = %s,
            finished_at = now(),
            updated_at = now()
        WHERE run_id = %s
        """,
        (status, p0_count, p1_count, p2_count, action_run_id),
    )


def build_current_real_rollback_sql(*, action_run_id: str, source_trigger_run_id: str, consumer_name: str) -> str:
    return f"""-- N5 current-real action execute rollback.
-- Execute only after an explicitly approved N5 execute run needs rollback.
-- Scope:
--   action_run_id: {action_run_id}
--   source_trigger_run_id: {source_trigger_run_id}
--   consumer_name: {consumer_name}
-- Boundary:
--   Deletes only N5 action-layer rows and this N5 consumer's inbox/checkpoint
--   rows for the scoped N4 source run. It does not mutate N4 trigger facts,
--   N4 outbox status, N3 facts, user projection, voice, sim, mobile, or
--   true-trade tables.

BEGIN;

\\set action_run_id '{action_run_id}'
\\set source_trigger_run_id '{source_trigger_run_id}'
\\set consumer_name '{consumer_name}'

SET LOCAL n5.rollback_action_run_id = :'action_run_id';
SET LOCAL n5.rollback_source_trigger_run_id = :'source_trigger_run_id';
SET LOCAL n5.rollback_consumer_name = :'consumer_name';

-- Hard-fail guard: every check below runs before the first DELETE.
DO $$
DECLARE
  v_action_run_id text := current_setting('n5.rollback_action_run_id');
  v_source_trigger_run_id text := current_setting('n5.rollback_source_trigger_run_id');
  v_consumer_name text := current_setting('n5.rollback_consumer_name');
  v_count bigint := 0;
  v_table_name text;
  v_table_regclass regclass;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has delivered/delivering rows (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has downstream inbox refs (%)', v_count;
  END IF;

  WITH scoped_n5_partitions AS (
    SELECT DISTINCT partition_key
    FROM common_event_outbox
    WHERE source_layer = 'N5_action'
      AND source_run_id = v_action_run_id
    UNION
    SELECT DISTINCT partition_key
    FROM common_event_ledger
    WHERE source_layer = 'N5_action'
      AND source_run_id = v_action_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N5_action'
    AND partition_key IN (SELECT partition_key FROM scoped_n5_partitions);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: scoped N5 outbox has downstream checkpoint refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_source_trigger_run_id
    AND consumer_name <> v_consumer_name;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: non-scoped consumer inbox refs exist for source_trigger_run_id (%)', v_count;
  END IF;

  WITH scoped_partitions AS (
    SELECT DISTINCT partition_key
    FROM common_event_inbox
    WHERE consumer_name = v_consumer_name
      AND source_layer = 'N4_trigger'
      AND source_run_id = v_source_trigger_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND consumer_name <> v_consumer_name
    AND partition_key IN (SELECT partition_key FROM scoped_partitions);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 rollback blocked: non-scoped consumer checkpoint refs exist for source_trigger_run_id (%)', v_count;
  END IF;

  FOREACH v_table_name IN ARRAY ARRAY[
    'user_projection_run',
    'user_card_projection',
    'user_signal_projection',
    'user_signal_decision',
    'user_notification_queue',
    'user_notification_projection',
    'user_voice_delivery',
    'user_device_ack',
    'user_market_projection',
    'voice_delivery_queue',
    'mobile_projection',
    'mobile_notification_queue',
    'sim_projection',
    'sim_order',
    'sim_trade',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'common_position_state',
    'common_position_event'
  ]
  LOOP
    v_table_regclass := to_regclass('public.' || v_table_name);
    IF v_table_regclass IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM %s t WHERE to_jsonb(t)::text LIKE $1 OR to_jsonb(t)::text LIKE $2',
        v_table_regclass
      )
      INTO v_count
      USING '%' || v_action_run_id || '%', '%' || v_source_trigger_run_id || '%';
      IF v_count > 0 THEN
        RAISE EXCEPTION 'N5 rollback blocked: downstream table % has scoped refs (%)', v_table_name, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

SELECT 'common_action_run' AS table_name, count(*) AS row_count
FROM common_action_run
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'stock_action_fact', count(*)
FROM stock_action_fact
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'index_action_fact', count(*)
FROM index_action_fact
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'board_action_fact', count(*)
FROM board_action_fact
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_action_event', count(*)
FROM common_action_event
WHERE run_id = :'action_run_id'
UNION ALL
SELECT 'common_event_outbox_n5', count(*)
FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id'
UNION ALL
SELECT 'common_event_inbox_n5_consumer', count(*)
FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id';

WITH scoped_n5_event_ids AS (
  SELECT event_id
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = :'action_run_id'
  UNION
  SELECT event_id
  FROM common_event_ledger
  WHERE source_layer = 'N5_action'
    AND source_run_id = :'action_run_id'
)
DELETE FROM common_event_delivery_attempt
WHERE event_id IN (SELECT event_id FROM scoped_n5_event_ids);

WITH scoped_partitions AS (
  SELECT DISTINCT partition_key
  FROM common_event_inbox
  WHERE consumer_name = :'consumer_name'
    AND source_layer = 'N4_trigger'
    AND source_run_id = :'source_trigger_run_id'
)
DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND partition_key IN (SELECT partition_key FROM scoped_partitions);

DELETE FROM common_event_inbox
WHERE consumer_name = :'consumer_name'
  AND source_layer = 'N4_trigger'
  AND source_run_id = :'source_trigger_run_id';

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

DELETE FROM common_event_ledger
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

DELETE FROM common_action_event
WHERE run_id = :'action_run_id';

DELETE FROM board_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM index_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM stock_action_fact
WHERE run_id = :'action_run_id';

DELETE FROM common_action_quality_item
WHERE run_id = :'action_run_id';

DELETE FROM common_action_run
WHERE run_id = :'action_run_id';

COMMIT;
"""


def format_execute_contract(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    scope = report["planned_write_scope"]
    output = report["output_event_plan_summary"]
    return "\n".join(
        [
            "# N5 Canonical Action Execute Contract",
            "",
            "## Summary",
            "",
            f"- stage: {report['stage']}",
            f"- layer_role: {report['layer_role']}",
            f"- runner_mode: {report['runner_mode']}",
            f"- source_trigger_run_id: {report['source_trigger_run_id']}",
            f"- action_run_id: {report['action_run_id']}",
            f"- consumer_name: {report['consumer_name']}",
            f"- execute: {report['execute']}",
            f"- user_confirmed: {report['user_confirmed']}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            f"- allow_execute: {report['allow_execute']}",
            "",
            "## Guards",
            "",
            f"- source_run_guard: {report['source_run_guard']}",
            f"- pending_only_guard: {report['pending_only_guard']}",
            f"- blockers: {report['blockers']}",
            "",
            "## Planned Write Scope",
            "",
            f"- common_action_run: {scope['common_action_run']}",
            f"- common_action_quality_item: {scope['common_action_quality_item']}",
            f"- stock_action_fact: {scope['stock_action_fact']}",
            f"- index_action_fact: {scope['index_action_fact']}",
            f"- board_action_fact: {scope['board_action_fact']}",
            f"- common_action_event: {scope['common_action_event']}",
            f"- common_event_outbox: {scope['common_event_outbox']}",
            f"- common_event_inbox: {scope['common_event_inbox']}",
            f"- common_event_consumer_checkpoint: {scope['common_event_consumer_checkpoint']}",
            f"- common_position_state: {scope['common_position_state']}",
            f"- common_position_event: {scope['common_position_event']}",
            "",
            "## Event Mapping",
            "",
            f"- output_event_plan: {output['by_event_type']}",
            "- BUY_HINT / SELL_HINT remain condition trace only; they do not emit HintEvent.",
            "- B_BUY / S_SELL are the only runtime signal_type values accepted by canonical N5 planning.",
            "- final action_mark is normal / 30m_volume / 30m_shrink only after N5 confirmation passes.",
            "- ActionBlocked means market action not confirmed / 市场动作未确认; it is not a user trade failure.",
            "- TriggerPendingMarketData writes quality only.",
            "- Execute is still gated by --execute, --user-confirmed, and a separate final gate.",
            "",
            "## Boundary",
            "",
            f"- side_effects: {report['side_effects']}",
        ]
    )


def write_current_real_rollback_sql(path: str = DEFAULT_N5_CURRENT_REAL_ROLLBACK_SQL_PATH) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        build_current_real_rollback_sql(
            action_run_id=CURRENT_REAL_N5_EXECUTE_ACTION_RUN_ID,
            source_trigger_run_id=CURRENT_REAL_N4_SOURCE_RUN_ID,
            consumer_name=DEFAULT_N5_1_CONSUMER_NAME,
        ),
        encoding="utf-8",
    )


def plan_summary_for_raw_json(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "consumer_plan_summary": plan.get("consumer_plan_summary"),
        "action_write_plan_summary": plan.get("action_write_plan_summary"),
        "output_event_plan_summary": plan.get("output_event_plan_summary"),
    }


def infer_trade_date_from_plan(plan: Mapping[str, Any]) -> str:
    for row in plan.get("action_write_plan") or []:
        payload = row.get("source_payload_json") or {}
        if isinstance(payload, Mapping) and payload.get("trade_date"):
            return str(payload["trade_date"])
    source_trigger_run_id = str(plan.get("source_trigger_run_id") or "")
    return infer_trade_date_from_source_run_id(source_trigger_run_id)


def infer_trade_date_from_source_run_id(source_trigger_run_id: str) -> str:
    if "20260602" in source_trigger_run_id:
        return "20260602"
    if "20260529" in source_trigger_run_id:
        return "20260529"
    if "20260528" in source_trigger_run_id:
        return "20260528"
    if "20260525" in source_trigger_run_id:
        return "20260525"
    return "20260525"


def parse_event_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "")
    if text:
        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


__all__ = [
    "ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ID",
    "ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_ALLOWLIST",
    "ACTION_CONFIRMATION_METRIC_20260602_N4_SOURCE_RUN_DENYLIST",
    "ACTION_CONFIRMATION_METRIC_20260602_N5_EXECUTE_ACTION_RUN_ID",
    "ActionExecuteError",
    "CANONICAL_20260528_N4_SOURCE_RUN_ID",
    "CANONICAL_20260528_N4_SOURCE_RUN_ALLOWLIST",
    "CANONICAL_20260528_N4_SOURCE_RUN_DENYLIST",
    "CANONICAL_20260528_N5_EXECUTE_ACTION_RUN_ID",
    "CANONICAL_20260529_N4_SOURCE_RUN_ID",
    "CANONICAL_20260529_N4_SOURCE_RUN_ALLOWLIST",
    "CANONICAL_20260529_N4_SOURCE_RUN_DENYLIST",
    "CANONICAL_20260529_N5_EXECUTE_ACTION_RUN_ID",
    "CURRENT_REAL_N4_SOURCE_RUN_ID",
    "CURRENT_REAL_N5_EXECUTE_ACTION_RUN_ID",
    "EXPECTED_CANONICAL_20260529_PENDING_EVENT_COUNT",
    "EXPECTED_ACTION_CONFIRMATION_METRIC_20260602_PENDING_EVENT_COUNT",
    "LATEST_CANONICAL_N4_SOURCE_RUN_ID",
    "LATEST_CANONICAL_N5_EXECUTE_ACTION_RUN_ID",
    "SYNTHETIC_N4_SOURCE_RUN_DENYLIST",
    "build_current_real_execute_contract_from_rows",
    "build_executable_plan_from_rows",
    "build_current_real_rollback_sql",
    "resolve_allowed_source_run_ids",
    "resolve_denied_source_run_ids",
    "run_action_consumer_once",
    "upsert_action_tracking_states",
    "write_current_real_rollback_sql",
]
