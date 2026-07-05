"""N6 shadow projection execute runner.

The runner implements the future execute path for N6 MVP user projection, but
it is gated by explicit --execute and --user-confirmed flags. The execute is a
shadow projection only: it writes N6 projection/card/queue rows and never
consumes N5 outbox rows, creates sessions, writes decisions or sim rows,
starts workers, pushes notifications, or places trades.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.user.projection_plan import (
    ALLOWED_EVENT_TYPES,
    DEFAULT_MARKDOWN_REPORT_PATH,
    DEFAULT_SOURCE_ACTION_RUN_ID,
    PostgresProjectionPlanRepository,
    ProjectionEvent,
    ProjectionInputSnapshot,
    action_mark_for_event,
    action_state_for_event,
    build_base_report,
    build_card_summary,
    build_planned_row_counts,
    build_projection_report,
    events_for_user_message_filter,
    card_type_for_event,
    card_status_for_event,
    display_priority_for_event,
    normalize_user_message_event_filter,
    normalize_jsonable,
    notification_source_for_event,
    parse_expected_n5_outbox_counts,
    projection_policy_for_event,
    utc_now_iso,
)


DEFAULT_PROJECTION_RUN_ID = (
    "user_projection_shadow_20260529__"
    "action_consumer_canonical_20260529_trigger_execute_20260529_"
    "condition_layer_20260528_source_20260528_v1"
)
CONTRACT_JSON_PATH = "docs/N6_canonical_projection_execute_contract.json"
PREFLIGHT_JSON_PATH = "docs/N6_canonical_projection_execute_preflight.json"
ROLLBACK_SQL_PATH = "sql/N6_projection_business_rollback.sql"
ALLOWED_CONTRACT_ARTIFACT_STATUSES = frozenset(
    {
        "DRAFT_PASS",
        "DESIGN_PASS",
        "ROLLBACK_ALIGNMENT_PASS",
        "CONTRACT_PASS",
        "EXECUTE_CONTRACT_PASS",
    }
)
ALLOWED_PREFLIGHT_ARTIFACT_STATUSES = frozenset(
    {
        "PREFLIGHT_DRAFT_PASS",
        "DESIGN_PASS",
        "EXECUTE_FINAL_PREFLIGHT_PASS",
        "EXECUTE_PREFLIGHT_PASS",
        "PREFLIGHT_PASS",
    }
)
ALLOWED_WRITE_TABLES = (
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "user_notification_queue",
)
DEFERRED_NOTIFICATION_WRITE_TABLES = (
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
)
NOTIFICATION_QUEUE_POLICY_IMMEDIATE = "immediate"
NOTIFICATION_QUEUE_POLICY_LEGACY = "legacy"
NOTIFICATION_QUEUE_POLICY_DEFERRED = "deferred"
NOTIFICATION_QUEUE_POLICY_DEFERRED_NO_QUEUE_WRITE = "deferred_no_queue_write"
SUPPORTED_NOTIFICATION_QUEUE_POLICIES = frozenset(
    {
        NOTIFICATION_QUEUE_POLICY_IMMEDIATE,
        NOTIFICATION_QUEUE_POLICY_LEGACY,
        NOTIFICATION_QUEUE_POLICY_DEFERRED,
        NOTIFICATION_QUEUE_POLICY_DEFERRED_NO_QUEUE_WRITE,
    }
)
DEFERRED_NOTIFICATION_QUEUE_POLICIES = frozenset(
    {
        NOTIFICATION_QUEUE_POLICY_DEFERRED,
        NOTIFICATION_QUEUE_POLICY_DEFERRED_NO_QUEUE_WRITE,
    }
)
SCOPED_GUARD_TABLES = ALLOWED_WRITE_TABLES
LINKED_GUARD_TABLES = (
    "user_signal_decision",
    "user_sim_order",
    "user_sim_trade",
    "user_sim_position",
)
FORBIDDEN_ZERO_TABLES = (
    "user_signal_decision",
    "user_watchlist",
    "user_watchlist_item",
    "user_sim_order",
    "user_sim_trade",
    "user_sim_position",
)


@dataclass
class ProjectionExecuteSnapshot:
    input_snapshot: ProjectionInputSnapshot
    projection_run_id: str
    scoped_counts: dict[str, int]
    linked_counts: dict[str, int]


@dataclass
class ProjectionWritePlan:
    projection_run_id: str
    source_action_run_id: str
    write_tables: tuple[str, ...]
    write_counts: dict[str, int]
    projection_run_row: dict[str, Any]
    projection_rows: list[dict[str, Any]]
    card_rows: list[dict[str, Any]]
    notification_rows: list[dict[str, Any]]
    n5_outbox_before: dict[str, int]
    quality_summary: dict[str, Any]


@dataclass(frozen=True)
class ProjectionExecuteContractSettings:
    notification_queue_policy: str = NOTIFICATION_QUEUE_POLICY_IMMEDIATE
    planned_writes: Mapping[str, Any] | None = None
    user_message_event_filter: tuple[str, ...] | None = None


class ProjectionExecuteRepository(Protocol):
    def fetch_execute_snapshot(self, projection_run_id: str) -> ProjectionExecuteSnapshot:
        ...

    def commit_shadow_projection(self, plan: ProjectionWritePlan) -> dict[str, Any]:
        ...


class PostgresProjectionExecuteRepository:
    def __init__(self, dsn: str, *, source_action_run_id: str = DEFAULT_SOURCE_ACTION_RUN_ID) -> None:
        self.dsn = dsn
        self.source_action_run_id = source_action_run_id

    def fetch_execute_snapshot(self, projection_run_id: str) -> ProjectionExecuteSnapshot:
        input_snapshot = PostgresProjectionPlanRepository(
            self.dsn,
            source_action_run_id=self.source_action_run_id,
        ).fetch_input_snapshot()
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            scoped_counts = {
                "user_projection_run": count_where(cur, "user_projection_run", "user_projection_run_id = %s", projection_run_id),
                "user_signal_projection": count_where(cur, "user_signal_projection", "user_projection_run_id = %s", projection_run_id),
                "user_signal_card": count_where(cur, "user_signal_card", "user_projection_run_id = %s", projection_run_id),
                "user_notification_queue": count_where(cur, "user_notification_queue", "user_projection_run_id = %s", projection_run_id),
            }
            linked_counts = {
                "user_signal_decision": count_linked_decisions(cur, projection_run_id),
                "user_sim_order": count_linked_sim_orders(cur, projection_run_id),
                "user_sim_trade": count_where(cur, "user_sim_trade", "sim_run_id = %s", projection_run_id),
                "user_sim_position": count_where(cur, "user_sim_position", "sim_run_id = %s", projection_run_id),
            }
        return ProjectionExecuteSnapshot(
            input_snapshot=input_snapshot,
            projection_run_id=projection_run_id,
            scoped_counts=scoped_counts,
            linked_counts=linked_counts,
        )

    def commit_shadow_projection(self, plan: ProjectionWritePlan) -> dict[str, Any]:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                insert_projection_run(cur, plan.projection_run_row)
                projection_id_by_event: dict[str, int] = {}
                for row in plan.projection_rows:
                    projection_id_by_event[row["source_event_id"]] = insert_signal_projection(cur, row)
                card_id_by_event: dict[str, int] = {}
                for row in plan.card_rows:
                    source_event_id = row["source_event_id"]
                    row["user_signal_projection_id"] = projection_id_by_event[source_event_id]
                    card_id_by_event[source_event_id] = insert_signal_card(cur, row)
                for row in plan.notification_rows:
                    source_event_id = row["source_event_id"]
                    row["user_signal_projection_id"] = projection_id_by_event[source_event_id]
                    row["user_signal_card_id"] = card_id_by_event[source_event_id]
                    insert_notification(cur, row)
                n5_outbox_after = fetch_n5_outbox_counts(cur, plan.source_action_run_id)
        return {
            "committed": True,
            "write_tables": list(plan.write_tables),
            "write_counts": dict(plan.write_counts),
            "n5_outbox_after": n5_outbox_after,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run N6 MVP shadow projection once after explicit final gate.")
    parser.add_argument("--dsn", help="PostgreSQL DSN. Defaults to caller-provided project default.")
    parser.add_argument("--projection-run-id", default=DEFAULT_PROJECTION_RUN_ID)
    parser.add_argument("--source-action-run-id", default=DEFAULT_SOURCE_ACTION_RUN_ID)
    parser.add_argument(
        "--expected-n5-outbox-count",
        action="append",
        default=[],
        metavar="EVENT:STATUS=COUNT",
        help="Explicit N5 outbox baseline for this execute gate, for example ActionExecuted:pending=4.",
    )
    parser.add_argument("--contract-json-path", default=CONTRACT_JSON_PATH)
    parser.add_argument("--preflight-json-path", default=PREFLIGHT_JSON_PATH)
    parser.add_argument("--rollback-sql-path", default=ROLLBACK_SQL_PATH)
    parser.add_argument("--execute", action="store_true", help="Required for the future write path.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required with --execute.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def run_projection_shadow_execute(
    *,
    repository: ProjectionExecuteRepository | None = None,
    dsn: str | None = None,
    projection_run_id: str = DEFAULT_PROJECTION_RUN_ID,
    source_action_run_id: str = DEFAULT_SOURCE_ACTION_RUN_ID,
    expected_n5_outbox_counts: Mapping[str, int] | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    contract_json_path: str = CONTRACT_JSON_PATH,
    preflight_json_path: str = PREFLIGHT_JSON_PATH,
    rollback_sql_path: str = ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    if not execute:
        return build_gate_blocked_report(
            gate_code="missing_execute_flag",
            gate_name="N6 projection shadow execute requires --execute",
            expected="--execute",
            actual="missing",
            started_at=started_at,
            projection_run_id=projection_run_id,
            source_action_run_id=source_action_run_id,
            rollback_sql_path=rollback_sql_path,
        )
    if not user_confirmed:
        return build_gate_blocked_report(
            gate_code="missing_user_confirmed",
            gate_name="N6 projection shadow execute requires --user-confirmed",
            expected="--user-confirmed",
            actual="missing",
            started_at=started_at,
            projection_run_id=projection_run_id,
            source_action_run_id=source_action_run_id,
            rollback_sql_path=rollback_sql_path,
        )

    artifact_errors = validate_design_artifacts(contract_json_path, preflight_json_path, rollback_sql_path)
    if artifact_errors:
        return build_artifact_blocked_report(
            artifact_errors,
            started_at=started_at,
            projection_run_id=projection_run_id,
            source_action_run_id=source_action_run_id,
            rollback_sql_path=rollback_sql_path,
        )
    contract_settings = load_execute_contract_settings(contract_json_path)
    if repository is None:
        if not dsn:
            return build_gate_blocked_report(
                gate_code="missing_dsn",
                gate_name="N6 projection shadow execute requires a PostgreSQL DSN when no repository is injected",
                expected="dsn",
                actual="missing",
                started_at=started_at,
                projection_run_id=projection_run_id,
                source_action_run_id=source_action_run_id,
                rollback_sql_path=rollback_sql_path,
            )
        repository = PostgresProjectionExecuteRepository(dsn, source_action_run_id=source_action_run_id)

    snapshot = repository.fetch_execute_snapshot(projection_run_id)
    preflight_report = build_execute_preflight_report(
        snapshot,
        started_at=started_at,
        projection_run_id=projection_run_id,
        source_action_run_id=source_action_run_id,
        expected_n5_outbox_counts=expected_n5_outbox_counts,
        preflight_json_path=preflight_json_path,
        rollback_sql_path=rollback_sql_path,
        notification_queue_policy=contract_settings.notification_queue_policy,
        user_message_event_filter=contract_settings.user_message_event_filter,
    )
    if preflight_report["quality"]["p0_count"] > 0:
        return preflight_report

    plan = build_write_plan(
        snapshot,
        preflight_report,
        projection_run_id=projection_run_id,
        source_action_run_id=source_action_run_id,
        notification_queue_policy=contract_settings.notification_queue_policy,
        user_message_event_filter=contract_settings.user_message_event_filter,
    )
    write_plan_alignment_items = build_write_plan_alignment_quality_items(plan, contract_settings)
    if any(item.get("severity") == "P0" and item.get("status") == "failed" for item in write_plan_alignment_items):
        return build_write_plan_alignment_blocked_report(preflight_report, write_plan_alignment_items)
    try:
        commit_result = repository.commit_shadow_projection(plan)
    except Exception as exc:  # pragma: no cover - defensive DB failure reporting
        return build_failed_report(preflight_report, exc)

    report = dict(preflight_report)
    zero_user_messages = (
        plan.write_counts.get("user_projection_run") == 1
        and plan.write_counts.get("user_signal_projection") == 0
        and plan.write_counts.get("user_signal_card") == 0
        and plan.write_counts.get("user_notification_queue") == 0
    )
    report["result"] = "PROJECTION_PASS_ZERO_USER_MESSAGES" if zero_user_messages else "EXECUTED"
    report["finished_at"] = utc_now_iso()
    report["write_summary"] = {
        "committed": bool(commit_result.get("committed")),
        "write_tables": list(commit_result.get("write_tables") or []),
        "write_counts": dict(commit_result.get("write_counts") or {}),
        "allowed_write_tables_only": set(commit_result.get("write_tables") or []) <= set(ALLOWED_WRITE_TABLES),
    }
    report["n5_outbox_after"] = dict(commit_result.get("n5_outbox_after") or plan.n5_outbox_before)
    report["n5_outbox_unchanged"] = report["n5_outbox_after"] == plan.n5_outbox_before
    report["allowed_next_gate"] = "N6 projection shadow execute post-review"
    return normalize_jsonable(report)


def build_execute_preflight_report(
    snapshot: ProjectionExecuteSnapshot,
    *,
    started_at: str,
    projection_run_id: str,
    source_action_run_id: str,
    expected_n5_outbox_counts: Mapping[str, int] | None = None,
    preflight_json_path: str = PREFLIGHT_JSON_PATH,
    rollback_sql_path: str,
    notification_queue_policy: str = NOTIFICATION_QUEUE_POLICY_IMMEDIATE,
    user_message_event_filter: Sequence[str] | None = None,
) -> dict[str, Any]:
    base = build_projection_report(
        snapshot=snapshot.input_snapshot,
        started_at=started_at,
        finished_at=utc_now_iso(),
        source_action_run_id=source_action_run_id,
        user_projection_run_id=projection_run_id,
        expected_n5_outbox_counts=expected_n5_outbox_counts,
        json_report_path=preflight_json_path,
        markdown_report_path=DEFAULT_MARKDOWN_REPORT_PATH,
        sample_limit=20,
        user_message_event_filter=user_message_event_filter,
    )
    execute_items = build_execute_quality_items(snapshot)
    quality_items = list(base["quality"]["items"]) + execute_items
    quality_counts = count_quality_severities(quality_items)
    blockers = sorted(
        {
            str(item["gate_code"])
            for item in quality_items
            if item.get("severity") == "P0" and item.get("status") == "failed"
        }
    )
    warnings = sorted(
        {
            str(item["gate_code"])
            for item in quality_items
            if item.get("severity") == "P1" and item.get("status") == "warning"
        }
    )
    notes = sorted(
        {
            str(item["gate_code"])
            for item in quality_items
            if item.get("severity") == "P2" and item.get("status") == "warning"
        }
    )
    base.update(
        {
            "stage": "N6-projection-shadow-execute",
            "mode": "projection_shadow_execute",
            "result": "BLOCKED" if quality_counts["P0"] else "PREFLIGHT_PASS",
            "preflight_result": "PREFLIGHT_BLOCKED" if quality_counts["P0"] else "PREFLIGHT_PASS",
            "projection_run_id": projection_run_id,
            "blockers": blockers,
            "warnings": warnings,
            "notes": notes,
            "quality": {
                "p0_count": quality_counts["P0"],
                "p1_count": quality_counts["P1"],
                "p2_count": quality_counts["P2"],
                "items": quality_items,
            },
            "baseline_guard": {
                "scoped_counts": dict(snapshot.scoped_counts),
                "linked_counts": dict(snapshot.linked_counts),
                "forbidden_zero_counts": forbidden_zero_counts(snapshot.input_snapshot),
            },
            "rollback_sql_path": rollback_sql_path,
            "notification_queue_policy": notification_queue_policy,
            "write_summary": {
                "committed": False,
                "write_tables": [],
                "write_counts": {},
                "allowed_write_tables_only": True,
            },
            "allow_projection_execute": False,
            "allow_n5_outbox_consumption": False,
            "allowed_next_gate": "N6 projection final execute gate" if not quality_counts["P0"] else "resolve P0 blockers before execute gate",
        }
    )
    if is_deferred_notification_queue_policy(notification_queue_policy):
        planned = dict(base.get("planned_row_counts") or {})
        planned["user_notification_queue"] = 0
        base["planned_row_counts"] = planned
        base["notification_plan_summary"] = {
            "planned_notification_count": 0,
            "queue_status_counts": {},
            "notification_source_counts": {},
            "queued_only_passed": True,
            "actual_push": False,
            "voice_mobile_push": False,
            "provider_delivery_attempt": False,
            "deferred": True,
        }
    return normalize_jsonable(base)


def build_execute_quality_items(snapshot: ProjectionExecuteSnapshot) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    admin = snapshot.input_snapshot.admin
    admin_id_ok = admin is not None and admin.user_id == 1
    items.append(
        quality_item(
            "P0",
            "passed" if admin_id_ok else "failed",
            "admin_user_id_not_1",
            "N6 MVP shadow projection execute is restricted to admin user_id=1",
            expected="1",
            actual=str(admin.user_id) if admin else "missing",
        )
    )
    for table in SCOPED_GUARD_TABLES:
        count = snapshot.scoped_counts.get(table, 0)
        items.append(
            quality_item(
                "P0",
                "passed" if count == 0 else "failed",
                f"projection_run_scoped_rows_not_zero:{table}",
                "Projection run scoped N6 rows must be zero before first insert",
                expected="0",
                actual=str(count),
            )
        )
    for table in LINKED_GUARD_TABLES:
        count = snapshot.linked_counts.get(table, 0)
        items.append(
            quality_item(
                "P0",
                "passed" if count == 0 else "failed",
                f"linked_rows_not_zero:{table}",
                "Linked decision or sim rows block projection rollback safety",
                expected="0",
                actual=str(count),
            )
        )
    forbidden_counts = forbidden_zero_counts(snapshot.input_snapshot)
    for table, count in forbidden_counts.items():
        items.append(
            quality_item(
                "P0",
                "passed" if count == 0 else "failed",
                f"forbidden_n6_table_not_zero:{table}",
                "Forbidden N6 MVP table must remain empty before shadow projection execute",
                expected="0",
                actual=str(count),
            )
        )
    duplicate_count = duplicate_source_event_count(snapshot.input_snapshot.events)
    items.append(
        quality_item(
            "P0",
            "passed" if duplicate_count == 0 else "failed",
            "duplicate_source_event_within_run",
            "Projection source_event_id must be unique within the planned run",
            expected="0",
            actual=str(duplicate_count),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed",
            "allowed_write_scope_only",
            "Shadow execute write plan is limited to N6 projection run/projection/card/notification tables",
            expected=",".join(ALLOWED_WRITE_TABLES),
            actual=",".join(ALLOWED_WRITE_TABLES),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed",
            "forbidden_side_effect_plan_all_false",
            "Shadow execute plan excludes N5 outbox mutation, sessions, decisions, sim, worker, push, and real trade",
            expected="all false",
            actual="all false",
        )
    )
    return items


def build_write_plan(
    snapshot: ProjectionExecuteSnapshot,
    preflight_report: Mapping[str, Any],
    *,
    projection_run_id: str,
    source_action_run_id: str,
    notification_queue_policy: str = NOTIFICATION_QUEUE_POLICY_IMMEDIATE,
    user_message_event_filter: Sequence[str] | None = None,
) -> ProjectionWritePlan:
    source_events = list(snapshot.input_snapshot.events)
    filter_result = normalize_user_message_event_filter(user_message_event_filter)
    events = events_for_user_message_filter(source_events, filter_result["event_types"])
    quality_summary = {
        "p0_count": preflight_report["quality"]["p0_count"],
        "p1_count": preflight_report["quality"]["p1_count"],
        "p2_count": preflight_report["quality"]["p2_count"],
        "warnings": preflight_report.get("warnings") or [],
        "notes": preflight_report.get("notes") or [],
        "missing_fields_summary": preflight_report.get("missing_fields_summary") or {},
        "shadow_projection": True,
        "n5_outbox_consumed": False,
        "n5_outbox_status_updated": False,
        "notification_queue_policy": notification_queue_policy,
        "user_message_event_filter": {
            "explicit": filter_result["explicit"],
            "event_types": list(filter_result["event_types"]),
        },
        "source_event_count": len(source_events),
        "user_message_event_count": len(events),
    }
    projection_rows = [build_projection_row(event, projection_run_id, snapshot) for event in events]
    card_rows = [build_card_row(event, projection_run_id, snapshot) for event in events]
    notification_rows = (
        []
        if is_deferred_notification_queue_policy(notification_queue_policy)
        else [build_notification_row(event, projection_run_id, snapshot) for event in events]
    )
    projection_run_row = build_projection_run_row(
        events,
        preflight_report,
        projection_run_id=projection_run_id,
        source_action_run_id=source_action_run_id,
        quality_summary=quality_summary,
        source_events=source_events,
    )
    write_counts = {
        "user_projection_run": 1 if source_events else 0,
        "user_signal_projection": len(projection_rows),
        "user_signal_card": len(card_rows),
        "user_notification_queue": len(notification_rows),
    }
    return ProjectionWritePlan(
        projection_run_id=projection_run_id,
        source_action_run_id=source_action_run_id,
        write_tables=write_tables_for_write_counts(write_counts, notification_queue_policy),
        write_counts=write_counts,
        projection_run_row=projection_run_row,
        projection_rows=projection_rows,
        card_rows=card_rows,
        notification_rows=notification_rows,
        n5_outbox_before=dict(snapshot.input_snapshot.n5_outbox_counts),
        quality_summary=quality_summary,
    )


def build_projection_run_row(
    events: Sequence[ProjectionEvent],
    preflight_report: Mapping[str, Any],
    *,
    projection_run_id: str,
    source_action_run_id: str,
    quality_summary: Mapping[str, Any],
    source_events: Sequence[ProjectionEvent] | None = None,
) -> dict[str, Any]:
    input_events = list(source_events) if source_events is not None else list(events)
    event_ids = [event.event_id for event in input_events]
    return {
        "user_projection_run_id": projection_run_id,
        "projection_contract_version": "N6-canonical-user-projection-shadow-execute-v1",
        "source_layer": "N5_action",
        "source_action_run_id": source_action_run_id,
        "source_n5_outbox_range": {
            "event_status": "pending",
            "event_type_counts": (preflight_report.get("event_summary") or {}).get("by_event_type") or {},
            "min_outbox_id": min((event.outbox_id for event in input_events), default=None),
            "max_outbox_id": max((event.outbox_id for event in input_events), default=None),
            "first_event_time": str(min((event.event_time for event in input_events), default="")),
            "last_event_time": str(max((event.event_time for event in input_events), default="")),
            "event_id_sha256": stable_hash(event_ids),
            "outbox_consumed": False,
            "outbox_status_updated": False,
        },
        "source_event_types": source_event_types_for_events(input_events),
        "source_display_condition_run_id": first_non_empty(event.display_run_id for event in input_events),
        "input_event_count": len(input_events),
        "output_projection_count": len(events),
        "p0_count": int((preflight_report.get("quality") or {}).get("p0_count") or 0),
        "p1_count": int((preflight_report.get("quality") or {}).get("p1_count") or 0),
        "p2_count": int((preflight_report.get("quality") or {}).get("p2_count") or 0),
        "quality_summary_json": dict(quality_summary),
        "status": "passed",
        "started_at": utc_now_iso(),
        "finished_at": utc_now_iso(),
    }


def build_projection_row(event: ProjectionEvent, projection_run_id: str, snapshot: ProjectionExecuteSnapshot) -> dict[str, Any]:
    payload = event.payload_json or {}
    missing = row_missing_fields(event)
    trace = canonical_trace_fields(event)
    return {
        "user_projection_run_id": projection_run_id,
        "user_id": snapshot.input_snapshot.admin.user_id if snapshot.input_snapshot.admin else None,
        "user_filter_profile_id": snapshot.input_snapshot.default_profile.user_filter_profile_id if snapshot.input_snapshot.default_profile else None,
        "user_watchlist_id": None,
        "permission_scope": "self",
        "source_layer": event.source_layer,
        "source_event_id": event.event_id,
        "source_outbox_id": event.outbox_id,
        "source_event_type": event.event_type,
        "source_event_schema_version": event.event_schema_version,
        "source_event_dedup_key": event.dedup_key,
        "source_action_event_id": event.event_id,
        "source_action_event_type": event.event_type,
        "source_action_run_id": event.source_run_id,
        "action_state": trace["action_state"],
        "action_mark": trace["action_mark"],
        "condition_key": trace["condition_key"],
        "original_condition_key": trace["original_condition_key"],
        "trace_json": trace["trace_json"],
        "projection_policy": trace["projection_policy"],
        "asset_kind": event.asset_kind,
        "identity_key": event.identity_key,
        "code": event.code or event.identity_key,
        "name": event.name or event.identity_key,
        "direction": str(payload.get("direction") or ""),
        "signal_type": str(payload.get("signal_type") or ""),
        "target_price": decimal_or_none(event.target_price),
        "current_price": decimal_or_none(event.current_price),
        "expected_return_pct": decimal_or_none(event.expected_return_pct),
        "board_identity_key": None,
        "board_code": event.board_code,
        "board_name": event.board_name,
        "source_display_table": event.source_display_table,
        "source_condition_display_basis_id": event.display_basis_id,
        "source_condition_display_run_id": event.display_run_id,
        "projection_status": "visible",
        "source_payload_json": {
            "event_id": event.event_id,
            "outbox_id": event.outbox_id,
            "event_type": event.event_type,
            "event_schema_version": event.event_schema_version,
            "trade_date": event.trade_date,
            "event_time": str(event.event_time),
            "dedup_key": event.dedup_key,
            "payload_json": payload,
        },
        "display_payload_json": {
            "source_display_table": event.source_display_table,
            "source_condition_display_basis_id": event.display_basis_id,
            "source_condition_display_run_id": event.display_run_id,
            "missing_fields": missing,
            "shadow_projection": True,
        },
    }


def build_card_row(event: ProjectionEvent, projection_run_id: str, snapshot: ProjectionExecuteSnapshot) -> dict[str, Any]:
    payload = event.payload_json or {}
    trace = canonical_trace_fields(event)
    title = f"{event.name or event.identity_key} {payload.get('signal_type') or ''}".strip()
    return {
        "user_projection_run_id": projection_run_id,
        "user_id": snapshot.input_snapshot.admin.user_id if snapshot.input_snapshot.admin else None,
        "card_type": card_type_for_event(event),
        "card_status": card_status_for_event(event),
        "display_priority": display_priority_for_event(event),
        "title": title,
        "summary": build_card_summary(event),
        "asset_kind": event.asset_kind,
        "identity_key": event.identity_key,
        "code": event.code or event.identity_key,
        "name": event.name or event.identity_key,
        "direction": str(payload.get("direction") or ""),
        "signal_type": str(payload.get("signal_type") or ""),
        "target_price": decimal_or_none(event.target_price),
        "current_price": decimal_or_none(event.current_price),
        "expected_return_pct": decimal_or_none(event.expected_return_pct),
        "board_code": event.board_code,
        "board_name": event.board_name,
        "source_action_run_id": event.source_run_id,
        "source_event_id": event.event_id,
        "source_action_event_id": event.event_id,
        "source_action_event_type": event.event_type,
        "action_state": trace["action_state"],
        "action_mark": trace["action_mark"],
        "condition_key": trace["condition_key"],
        "original_condition_key": trace["original_condition_key"],
        "trace_json": trace["trace_json"],
        "projection_policy": trace["projection_policy"],
        "card_payload_json": {
            "source_outbox_id": event.outbox_id,
            "source_event_type": event.event_type,
            "lane": payload.get("lane"),
            "action_type": payload.get("action_type"),
            "condition_key": payload.get("condition_key"),
            "original_condition_key": payload.get("original_condition_key"),
            "action_state": trace["action_state"],
            "action_mark": trace["action_mark"],
            "projection_policy": trace["projection_policy"],
            "decision_buttons": False,
            "sim_allowed": False,
            "real_trade_allowed": False,
            "trigger_period": payload.get("trigger_period"),
            "missing_fields": row_missing_fields(event),
        },
    }


def build_notification_row(event: ProjectionEvent, projection_run_id: str, snapshot: ProjectionExecuteSnapshot) -> dict[str, Any]:
    payload = event.payload_json or {}
    trace = canonical_trace_fields(event)
    title = f"{event.name or event.identity_key} {payload.get('signal_type') or ''}".strip()
    return {
        "user_id": snapshot.input_snapshot.admin.user_id if snapshot.input_snapshot.admin else None,
        "user_projection_run_id": projection_run_id,
        "notification_source": notification_source_for_event(event),
        "queue_status": "queued_only",
        "channel": "broadcast_queue",
        "title": title,
        "message": build_card_summary(event),
        "priority": display_priority_for_event(event),
        "source_event_id": event.event_id,
        "source_action_run_id": event.source_run_id,
        "source_action_event_id": event.event_id,
        "source_action_event_type": event.event_type,
        "action_state": trace["action_state"],
        "action_mark": trace["action_mark"],
        "condition_key": trace["condition_key"],
        "original_condition_key": trace["original_condition_key"],
        "trace_json": trace["trace_json"],
        "projection_policy": trace["projection_policy"],
        "asset_kind": event.asset_kind,
        "identity_key": event.identity_key,
        "notification_payload_json": {
            "queue_only": True,
            "provider_payload": False,
            "delivery_attempt": False,
            "actual_push": False,
            "voice_mobile_push": False,
            "source_event_type": event.event_type,
            "source_outbox_id": event.outbox_id,
            "action_state": trace["action_state"],
            "action_mark": trace["action_mark"],
            "condition_key": trace["condition_key"],
            "original_condition_key": trace["original_condition_key"],
            "projection_policy": trace["projection_policy"],
            "missing_fields": row_missing_fields(event),
        },
    }


def source_event_types_for_events(events: Sequence[ProjectionEvent]) -> list[str]:
    present = {event.event_type for event in events}
    ordered = [event_type for event_type in ALLOWED_EVENT_TYPES if event_type in present]
    return ordered or list(ALLOWED_EVENT_TYPES)


def canonical_trace_fields(event: ProjectionEvent) -> dict[str, Any]:
    payload = event.payload_json or {}
    trace_json = payload.get("trace_json")
    if not isinstance(trace_json, Mapping):
        trace_json = None
    return {
        "source_action_event_type": event.event_type,
        "action_state": action_state_for_event(event),
        "action_mark": action_mark_for_event(event),
        "condition_key": payload.get("condition_key") or None,
        "original_condition_key": payload.get("original_condition_key") or None,
        "trace_json": trace_json,
        "projection_policy": projection_policy_for_event(event),
    }


def build_gate_blocked_report(
    *,
    gate_code: str,
    gate_name: str,
    expected: str,
    actual: str,
    started_at: str,
    projection_run_id: str,
    source_action_run_id: str,
    rollback_sql_path: str,
) -> dict[str, Any]:
    item = quality_item("P0", "failed", gate_code, gate_name, expected=expected, actual=actual)
    report = build_base_report(
        result="BLOCKED",
        blockers=[gate_code],
        warnings=[],
        notes=[],
        quality_items=[item],
        started_at=started_at,
        finished_at=utc_now_iso(),
        source_action_run_id=source_action_run_id,
        user_projection_run_id=projection_run_id,
        json_report_path=PREFLIGHT_JSON_PATH,
        markdown_report_path=DEFAULT_MARKDOWN_REPORT_PATH,
        planned_row_counts=build_planned_row_counts(0),
        missing_fields_summary={
            "display_basis_missing": 0,
            "code_name_missing": 0,
            "current_price_missing": 0,
            "target_price_missing": 0,
            "expected_return_pct_missing": 0,
            "board_context_missing": 0,
        },
        event_summary={
            "input_event_count": 0,
            "by_event_type": {},
            "by_direction": {},
            "by_signal_type": {},
            "distribution": [],
        },
        notification_plan_summary={
            "planned_notification_count": 0,
            "queue_status_counts": {},
            "notification_source_counts": {},
            "queued_only_passed": True,
            "actual_push": False,
        },
        input_state=None,
        sample_plans=[],
    )
    report.update(
        {
            "stage": "N6-projection-shadow-execute",
            "mode": "projection_shadow_execute",
            "preflight_result": "NOT_RUN",
            "projection_run_id": projection_run_id,
            "rollback_sql_path": rollback_sql_path,
            "write_summary": {"committed": False, "write_tables": [], "write_counts": {}, "allowed_write_tables_only": True},
        }
    )
    report["side_effects"]["read_only_database_checks"] = False
    return report


def build_artifact_blocked_report(
    errors: list[str],
    *,
    started_at: str,
    projection_run_id: str,
    source_action_run_id: str,
    rollback_sql_path: str,
) -> dict[str, Any]:
    items = [
        quality_item(
            "P0",
            "failed",
            error,
            "Required execute contract/preflight/rollback artifact is missing or invalid",
            expected="valid artifact",
            actual=error,
        )
        for error in errors
    ]
    report = build_gate_blocked_report(
        gate_code="artifact_validation_failed",
        gate_name="Required N6 projection execute artifacts must be readable",
        expected="valid artifacts",
        actual=";".join(errors),
        started_at=started_at,
        projection_run_id=projection_run_id,
        source_action_run_id=source_action_run_id,
        rollback_sql_path=rollback_sql_path,
    )
    report["quality"]["items"] = items
    report["quality"] = {"p0_count": len(items), "p1_count": 0, "p2_count": 0, "items": items}
    report["blockers"] = errors
    return report


def build_failed_report(preflight_report: Mapping[str, Any], exc: Exception) -> dict[str, Any]:
    report = dict(preflight_report)
    report["result"] = "FAILED"
    report["preflight_result"] = preflight_report.get("preflight_result")
    report["finished_at"] = utc_now_iso()
    report["failure"] = {
        "error_type": type(exc).__name__,
        "message": str(exc),
    }
    report["write_summary"] = {
        "committed": False,
        "write_tables": list(ALLOWED_WRITE_TABLES),
        "write_counts": {},
        "allowed_write_tables_only": True,
    }
    return normalize_jsonable(report)


def validate_design_artifacts(contract_json_path: str, preflight_json_path: str, rollback_sql_path: str) -> list[str]:
    errors: list[str] = []
    for path, code, valid_statuses in (
        (contract_json_path, "missing_or_invalid_contract_json", ALLOWED_CONTRACT_ARTIFACT_STATUSES),
        (preflight_json_path, "missing_or_invalid_preflight_json", ALLOWED_PREFLIGHT_ARTIFACT_STATUSES),
    ):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            result_or_status = payload.get("status") or payload.get("result")
            if result_or_status not in valid_statuses:
                errors.append(f"{code}:status_not_allowed")
            if code == "missing_or_invalid_contract_json":
                errors.extend(validate_notification_queue_policy_payload(payload))
                errors.extend(validate_user_message_event_filter_payload(payload))
        except Exception:
            errors.append(code)
    if not Path(rollback_sql_path).exists():
        errors.append("missing_rollback_sql")
    return errors


def load_execute_contract_settings(contract_json_path: str) -> ProjectionExecuteContractSettings:
    try:
        payload = json.loads(Path(contract_json_path).read_text(encoding="utf-8"))
    except Exception:
        return ProjectionExecuteContractSettings()
    return ProjectionExecuteContractSettings(
        notification_queue_policy=extract_notification_queue_policy(payload),
        planned_writes=extract_planned_writes(payload),
        user_message_event_filter=extract_user_message_event_filter(payload),
    )


def validate_notification_queue_policy_payload(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    policy = extract_notification_queue_policy(payload)
    if policy not in SUPPORTED_NOTIFICATION_QUEUE_POLICIES:
        return ["notification_queue_policy_not_allowed"]
    planned_writes = extract_planned_writes(payload)
    planned_queue = planned_writes.get("user_notification_queue")
    if is_deferred_notification_queue_policy(policy) and planned_queue not in (0, "0", None):
        errors.append("notification_queue_deferred_contract_plans_queue_rows")
    return errors


def validate_user_message_event_filter_payload(payload: Mapping[str, Any]) -> list[str]:
    if "user_message_event_filter" not in payload:
        return ["missing_user_message_event_filter"]
    filter_result = normalize_user_message_event_filter(extract_user_message_event_filter(payload))
    if not filter_result["valid"]:
        return [str(filter_result["gate_code"])]
    return []


def extract_notification_queue_policy(payload: Mapping[str, Any]) -> str:
    raw = payload.get("notification_queue_policy")
    if raw is None:
        raw = payload.get("notification_policy")
    if isinstance(raw, Mapping):
        raw = raw.get("status") or raw.get("policy") or raw.get("mode")
    if raw in (None, ""):
        return NOTIFICATION_QUEUE_POLICY_IMMEDIATE
    return str(raw)


def extract_planned_writes(payload: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("planned_writes", "planned_row_counts"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    planned_outputs = payload.get("planned_outputs")
    if isinstance(planned_outputs, Mapping):
        dry_run_plan = planned_outputs.get("dry_run_would_plan")
        if isinstance(dry_run_plan, Mapping):
            return dict(dry_run_plan)
        return dict(planned_outputs)
    return {}


def extract_user_message_event_filter(payload: Mapping[str, Any]) -> tuple[str, ...] | None:
    raw = payload.get("user_message_event_filter")
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        raw = raw.get("include_event_types") or raw.get("included_event_types") or raw.get("event_types")
    if raw is None:
        return tuple()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        return tuple(str(value) for value in raw)
    return tuple()


def write_tables_for_notification_policy(notification_queue_policy: str) -> tuple[str, ...]:
    if is_deferred_notification_queue_policy(notification_queue_policy):
        return DEFERRED_NOTIFICATION_WRITE_TABLES
    return ALLOWED_WRITE_TABLES


def write_tables_for_write_counts(write_counts: Mapping[str, int], notification_queue_policy: str) -> tuple[str, ...]:
    if is_deferred_notification_queue_policy(notification_queue_policy):
        ordered = DEFERRED_NOTIFICATION_WRITE_TABLES
    else:
        ordered = ALLOWED_WRITE_TABLES
    return tuple(table for table in ordered if int(write_counts.get(table) or 0) > 0)


def build_write_plan_alignment_quality_items(
    plan: ProjectionWritePlan,
    contract_settings: ProjectionExecuteContractSettings,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    policy = contract_settings.notification_queue_policy
    if is_deferred_notification_queue_policy(policy):
        queue_count = int(plan.write_counts.get("user_notification_queue") or 0)
        queue_table_in_scope = "user_notification_queue" in plan.write_tables
        items.append(
            quality_item(
                "P0",
                "passed" if queue_count == 0 else "failed",
                "notification_queue_deferred_write_plan_not_zero",
                "Deferred notification policy requires zero user_notification_queue rows",
                expected="0",
                actual=str(queue_count),
            )
        )
        items.append(
            quality_item(
                "P0",
                "passed" if not queue_table_in_scope else "failed",
                "notification_queue_deferred_write_table_in_scope",
                "Deferred notification policy must not include user_notification_queue in write tables",
                expected="absent",
                actual="present" if queue_table_in_scope else "absent",
            )
        )
    planned_writes = dict(contract_settings.planned_writes or {})
    for table in ("user_projection_run", "user_signal_projection", "user_signal_card", "user_notification_queue"):
        if table not in planned_writes:
            continue
        expected = int(planned_writes.get(table) or 0)
        actual = int(plan.write_counts.get(table) or 0)
        items.append(
            quality_item(
                "P0",
                "passed" if actual == expected else "failed",
                f"contract_planned_write_mismatch:{table}",
                "N6 projection write plan must match reviewed contract planned writes",
                expected=str(expected),
                actual=str(actual),
            )
        )
    return items


def is_deferred_notification_queue_policy(notification_queue_policy: str) -> bool:
    return notification_queue_policy in DEFERRED_NOTIFICATION_QUEUE_POLICIES


def build_write_plan_alignment_blocked_report(
    preflight_report: Mapping[str, Any],
    quality_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    report = dict(preflight_report)
    existing_items = list((preflight_report.get("quality") or {}).get("items") or [])
    all_items = existing_items + [dict(item) for item in quality_items]
    quality_counts = count_quality_severities(all_items)
    blockers = sorted(
        {
            str(item["gate_code"])
            for item in all_items
            if item.get("severity") == "P0" and item.get("status") == "failed"
        }
    )
    report["result"] = "BLOCKED"
    report["preflight_result"] = "PREFLIGHT_BLOCKED"
    report["blockers"] = blockers
    report["quality"] = {
        "p0_count": quality_counts["P0"],
        "p1_count": quality_counts["P1"],
        "p2_count": quality_counts["P2"],
        "items": all_items,
    }
    report["write_summary"] = {
        "committed": False,
        "write_tables": [],
        "write_counts": {},
        "allowed_write_tables_only": True,
    }
    report["allowed_next_gate"] = "resolve N6 projection write-plan alignment blockers before execute gate"
    return normalize_jsonable(report)


def forbidden_zero_counts(snapshot: ProjectionInputSnapshot) -> dict[str, int]:
    return {table: int(snapshot.table_counts.get(table) or 0) for table in FORBIDDEN_ZERO_TABLES}


def duplicate_source_event_count(events: Sequence[ProjectionEvent]) -> int:
    seen: set[str] = set()
    duplicates = 0
    for event in events:
        if event.event_id in seen:
            duplicates += 1
        seen.add(event.event_id)
    return duplicates


def row_missing_fields(event: ProjectionEvent) -> list[str]:
    missing: list[str] = []
    if event.display_basis_id is None:
        missing.append("display_basis")
    if not event.code or not event.name:
        missing.append("code_or_name")
    if event.current_price is None:
        missing.append("current_price")
    if event.target_price is None:
        missing.append("target_price")
    if event.expected_return_pct is None:
        missing.append("expected_return_pct")
    if not event.board_code or not event.board_name:
        missing.append("board_context")
    return missing


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def first_non_empty(values: Sequence[Any] | Any) -> Any | None:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def stable_hash(values: Sequence[Any]) -> str:
    import hashlib

    raw = json.dumps(list(values), ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def count_where(cur: psycopg.Cursor[dict[str, Any]], table: str, predicate: str, value: Any) -> int:
    cur.execute(f"SELECT count(*)::int AS count FROM {table} WHERE {predicate}", (value,))
    return int(cur.fetchone()["count"])


def count_linked_decisions(cur: psycopg.Cursor[dict[str, Any]], projection_run_id: str) -> int:
    cur.execute(
        """
        SELECT count(*)::int AS count
          FROM user_signal_decision d
          JOIN user_signal_projection p
            ON p.user_signal_projection_id = d.user_signal_projection_id
         WHERE p.user_projection_run_id = %s
        """,
        (projection_run_id,),
    )
    return int(cur.fetchone()["count"])


def count_linked_sim_orders(cur: psycopg.Cursor[dict[str, Any]], projection_run_id: str) -> int:
    cur.execute(
        """
        SELECT count(*)::int AS count
          FROM user_sim_order o
         WHERE o.sim_run_id = %s
            OR o.user_signal_projection_id IN (
                 SELECT user_signal_projection_id
                   FROM user_signal_projection
                  WHERE user_projection_run_id = %s
               )
        """,
        (projection_run_id, projection_run_id),
    )
    return int(cur.fetchone()["count"])


def fetch_n5_outbox_counts(cur: psycopg.Cursor[dict[str, Any]], source_action_run_id: str) -> dict[str, int]:
    cur.execute(
        """
        SELECT event_type, status, count(*)::int AS count
          FROM common_event_outbox
         WHERE source_layer = 'N5_action'
           AND source_run_id = %s
           AND event_type = ANY(%s)
         GROUP BY event_type, status
        """,
        (source_action_run_id, list(ALLOWED_EVENT_TYPES)),
    )
    return {f"{row['event_type']}:{row['status']}": int(row["count"]) for row in cur.fetchall()}


def insert_projection_run(cur: psycopg.Cursor[dict[str, Any]], row: Mapping[str, Any]) -> None:
    columns = (
        "user_projection_run_id",
        "projection_contract_version",
        "source_layer",
        "source_action_run_id",
        "source_n5_outbox_range",
        "source_event_types",
        "source_display_condition_run_id",
        "input_event_count",
        "output_projection_count",
        "p0_count",
        "p1_count",
        "p2_count",
        "quality_summary_json",
        "status",
        "started_at",
        "finished_at",
    )
    cur.execute(
        f"INSERT INTO user_projection_run ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
        [jsonb_if_needed(column, row[column]) for column in columns],
    )


def insert_signal_projection(cur: psycopg.Cursor[dict[str, Any]], row: Mapping[str, Any]) -> int:
    columns = (
        "user_projection_run_id",
        "user_id",
        "user_filter_profile_id",
        "user_watchlist_id",
        "permission_scope",
        "source_layer",
        "source_event_id",
        "source_outbox_id",
        "source_event_type",
        "source_event_schema_version",
        "source_event_dedup_key",
        "source_action_event_id",
        "source_action_event_type",
        "source_action_run_id",
        "action_state",
        "action_mark",
        "condition_key",
        "original_condition_key",
        "trace_json",
        "projection_policy",
        "asset_kind",
        "identity_key",
        "code",
        "name",
        "direction",
        "signal_type",
        "target_price",
        "current_price",
        "expected_return_pct",
        "board_identity_key",
        "board_code",
        "board_name",
        "source_display_table",
        "source_condition_display_basis_id",
        "source_condition_display_run_id",
        "projection_status",
        "source_payload_json",
        "display_payload_json",
    )
    cur.execute(
        f"""
        INSERT INTO user_signal_projection ({', '.join(columns)})
        VALUES ({', '.join(['%s'] * len(columns))})
        RETURNING user_signal_projection_id
        """,
        [jsonb_if_needed(column, row[column]) for column in columns],
    )
    return int(cur.fetchone()["user_signal_projection_id"])


def insert_signal_card(cur: psycopg.Cursor[dict[str, Any]], row: Mapping[str, Any]) -> int:
    columns = (
        "user_signal_projection_id",
        "user_projection_run_id",
        "user_id",
        "card_type",
        "card_status",
        "display_priority",
        "title",
        "summary",
        "asset_kind",
        "identity_key",
        "code",
        "name",
        "direction",
        "signal_type",
        "target_price",
        "current_price",
        "expected_return_pct",
        "board_code",
        "board_name",
        "source_action_run_id",
        "source_event_id",
        "source_action_event_id",
        "source_action_event_type",
        "action_state",
        "action_mark",
        "condition_key",
        "original_condition_key",
        "trace_json",
        "projection_policy",
        "card_payload_json",
    )
    cur.execute(
        f"""
        INSERT INTO user_signal_card ({', '.join(columns)})
        VALUES ({', '.join(['%s'] * len(columns))})
        RETURNING user_signal_card_id
        """,
        [jsonb_if_needed(column, row[column]) for column in columns],
    )
    return int(cur.fetchone()["user_signal_card_id"])


def insert_notification(cur: psycopg.Cursor[dict[str, Any]], row: Mapping[str, Any]) -> None:
    columns = (
        "user_id",
        "user_projection_run_id",
        "user_signal_projection_id",
        "user_signal_card_id",
        "notification_source",
        "queue_status",
        "channel",
        "title",
        "message",
        "priority",
        "source_event_id",
        "source_action_run_id",
        "source_action_event_id",
        "source_action_event_type",
        "action_state",
        "action_mark",
        "condition_key",
        "original_condition_key",
        "trace_json",
        "projection_policy",
        "asset_kind",
        "identity_key",
        "notification_payload_json",
    )
    cur.execute(
        f"INSERT INTO user_notification_queue ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
        [jsonb_if_needed(column, row[column]) for column in columns],
    )


def jsonb_if_needed(column: str, value: Any) -> Any:
    if column.endswith("_json") or column in {"source_n5_outbox_range", "quality_summary_json"}:
        return Jsonb(normalize_jsonable(value))
    return value


def format_summary(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    planned = report.get("planned_row_counts") or {}
    write_summary = report.get("write_summary") or {}
    return "\n".join(
        [
            "N6 projection shadow execute",
            f"  result={report.get('result')}",
            f"  preflight_result={report.get('preflight_result')}",
            f"  projection_run_id={report.get('projection_run_id')}",
            f"  planned_projection_run={planned.get('user_projection_run')}",
            f"  planned_signal_projection={planned.get('user_signal_projection')}",
            f"  planned_signal_card={planned.get('user_signal_card')}",
            f"  planned_notification_queue={planned.get('user_notification_queue')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
            f"  blockers={report.get('blockers') or []}",
            f"  committed={str(write_summary.get('committed')).lower()} write_tables={write_summary.get('write_tables') or []}",
            f"  n5_outbox_consumed={str((report.get('side_effects') or {}).get('n5_outbox_consumed')).lower()} updates_n5_outbox_status={str((report.get('side_effects') or {}).get('updates_n5_outbox_status')).lower()}",
        ]
    )
