"""N6 user projection dry-run planner.

The planner reads pending N5 action outbox rows and builds an in-memory N6
projection plan for the MVP admin user. The canonical path accepts
ActionEligible / ActionBlocked / ActionExecuted / ActionSkipped; historical
ActionEvent / HintEvent remain as replay compatibility only.

It never writes N6 projection tables, consumes N5 outbox rows, creates
sessions, starts workers, sends push notifications, writes sim rows, or places
trades.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.user.stale_active_lineage import is_stale_source_action_run_id


DEFAULT_JSON_REPORT_PATH = "docs/N6_projection_dry_run_report.json"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/N6_PROJECTION_DRY_RUN_REPORT.md"
LEGACY_SOURCE_ACTION_RUN_ID = (
    "action_consumer_current_real_execute_20260525_"
    "trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249"
)
CANONICAL_SOURCE_ACTION_RUN_ID = (
    "action_consumer_canonical_20260529_trigger_execute_20260529_"
    "condition_layer_20260528_source_20260528_v1"
)
DEFAULT_SOURCE_ACTION_RUN_ID = CANONICAL_SOURCE_ACTION_RUN_ID
LEGACY_USER_PROJECTION_RUN_ID = (
    "user_projection_dry_run_20260525__"
    "action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_"
    "condition_layer_20260522_to_20260525102249"
)
CANONICAL_USER_PROJECTION_RUN_ID = (
    "user_projection_dry_run_20260529__"
    "action_consumer_canonical_20260529_trigger_execute_20260529_"
    "condition_layer_20260528_source_20260528_v1"
)
DEFAULT_USER_PROJECTION_RUN_ID = CANONICAL_USER_PROJECTION_RUN_ID
EXPECTED_N5_OUTBOX_COUNTS = {
    "ActionBlocked:pending": 4309,
}
LEGACY_EXPECTED_N5_OUTBOX_COUNTS = {
    "ActionEvent:pending": 479,
    "HintEvent:pending": 9,
}
CANONICAL_EVENT_TYPES = ("ActionEligible", "ActionBlocked", "ActionExecuted", "ActionSkipped")
LEGACY_EVENT_TYPES = ("ActionEvent", "HintEvent")
ALLOWED_EVENT_TYPES = CANONICAL_EVENT_TYPES + LEGACY_EVENT_TYPES
USER_MESSAGE_EVENT_TYPES = ("ActionEligible", "ActionExecuted")
NON_INPUT_N5_EVENT_TYPES = ("RiskEvent", "PositionEvent")
NOTIFICATION_SOURCE_BY_EVENT_TYPE = {
    "ActionEligible": "n5_action_eligible",
    "ActionBlocked": "n5_action_blocked",
    "ActionExecuted": "n5_action_executed",
    "ActionSkipped": "n5_action_skipped",
    "ActionEvent": "n5_action_event",
    "HintEvent": "n5_hint_event",
}
ACTION_STATE_BY_EVENT_TYPE = {
    "ActionEligible": "eligible",
    "ActionBlocked": "blocked",
    "ActionExecuted": "executed",
    "ActionSkipped": "skipped",
}
PROJECTION_POLICY_BY_EVENT_TYPE = {
    "ActionBlocked": "blocked_unconfirmed_no_push_no_decision_no_sim_no_trade",
    "ActionEligible": "candidate_visible_queued_only_no_push_no_trade",
    "ActionExecuted": "action_confirmed_display_only_no_real_trade",
    "ActionSkipped": "skipped_informational_no_push_no_trade",
    "ActionEvent": "legacy_action_event_compat_queued_only",
    "HintEvent": "legacy_hint_event_compat_queued_only",
}
REQUIRED_ENVELOPE_FIELDS = (
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
    "status",
)
COMMON_REQUIRED_PAYLOAD_FIELDS = (
    "run_id",
    "asset_kind",
    "identity_key",
    "direction",
    "signal_type",
)
CANONICAL_REQUIRED_PAYLOAD_FIELDS = COMMON_REQUIRED_PAYLOAD_FIELDS + (
    "action_state",
    "condition_key",
    "original_condition_key",
    "trace_json",
)
LEGACY_REQUIRED_PAYLOAD_FIELDS = COMMON_REQUIRED_PAYLOAD_FIELDS + (
    "action_type",
    "lane",
    "condition_key",
    "trigger_period",
    "action_key",
    "dedup_key",
    "source_condition_run_id",
    "source_market_trace",
)
N6_TABLES = (
    "user_account",
    "user_session",
    "user_filter_profile",
    "user_watchlist",
    "user_watchlist_item",
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "user_signal_decision",
    "user_notification_queue",
    "user_sim_account",
    "user_sim_order",
    "user_sim_trade",
    "user_sim_position",
)
DISPLAY_BASIS_TABLES = (
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
)


@dataclass
class AdminUser:
    user_id: int
    login_name: str
    role: str
    status: str


@dataclass
class FilterProfile:
    user_filter_profile_id: int
    user_id: int
    profile_name: str
    is_default: bool
    status: str


@dataclass
class ProjectionEvent:
    outbox_id: int
    event_id: str
    event_type: str
    event_schema_version: str
    trade_date: str
    asset_kind: str
    identity_key: str
    event_time: Any
    source_layer: str
    source_run_id: str
    dedup_key: str
    partition_key: str
    status: str
    payload_json: dict[str, Any]
    source_display_table: str | None
    display_basis_id: int | None
    display_run_id: str | None
    code: str | None
    name: str | None
    target_price: Any | None
    expected_return_pct: Any | None
    board_code: str | None
    board_name: str | None
    current_price: Any | None = None


@dataclass
class ProjectionInputSnapshot:
    table_counts: dict[str, int | None]
    admin: AdminUser | None
    default_profile: FilterProfile | None
    n5_outbox_counts: dict[str, int]
    display_basis_counts: dict[str, int | None]
    events: list[ProjectionEvent]


class ProjectionPlanRepository(Protocol):
    def fetch_input_snapshot(self) -> ProjectionInputSnapshot:
        ...


class PostgresProjectionPlanRepository:
    def __init__(self, dsn: str, *, source_action_run_id: str = DEFAULT_SOURCE_ACTION_RUN_ID) -> None:
        self.dsn = dsn
        self.source_action_run_id = source_action_run_id

    def fetch_input_snapshot(self) -> ProjectionInputSnapshot:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            table_counts = {table: self._count_table(cur, table) for table in N6_TABLES}
            admin = self._fetch_admin(cur)
            default_profile = self._fetch_default_profile(cur, admin.user_id if admin else None)
            n5_outbox_counts = self._fetch_n5_outbox_counts(cur)
            events = self._fetch_projection_events(cur)
        return ProjectionInputSnapshot(
            table_counts=table_counts,
            admin=admin,
            default_profile=default_profile,
            n5_outbox_counts=n5_outbox_counts,
            display_basis_counts={},
            events=events,
        )

    def _table_exists(self, cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> bool:
        cur.execute("SELECT to_regclass(%s) AS reg", (f"public.{table_name}",))
        return cur.fetchone()["reg"] is not None

    def _count_table(self, cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> int | None:
        if not self._table_exists(cur, table_name):
            return None
        cur.execute(f"SELECT count(*)::int AS count FROM {table_name}")
        return cur.fetchone()["count"]

    def _fetch_admin(self, cur: psycopg.Cursor[dict[str, Any]]) -> AdminUser | None:
        if not self._table_exists(cur, "user_account"):
            return None
        cur.execute(
            """
            SELECT user_id, login_name, role, status
            FROM user_account
            WHERE login_name = 'admin'
            ORDER BY user_id
            LIMIT 1
            """
        )
        row = cur.fetchone()
        return AdminUser(**dict(row)) if row else None

    def _fetch_default_profile(
        self,
        cur: psycopg.Cursor[dict[str, Any]],
        admin_user_id: int | None,
    ) -> FilterProfile | None:
        if admin_user_id is None or not self._table_exists(cur, "user_filter_profile"):
            return None
        cur.execute(
            """
            SELECT user_filter_profile_id, user_id, profile_name, is_default, status
            FROM user_filter_profile
            WHERE user_id = %s
              AND is_default = true
              AND status = 'active'
            ORDER BY user_filter_profile_id
            LIMIT 1
            """,
            (admin_user_id,),
        )
        row = cur.fetchone()
        return FilterProfile(**dict(row)) if row else None

    def _fetch_n5_outbox_counts(self, cur: psycopg.Cursor[dict[str, Any]]) -> dict[str, int]:
        if not self._table_exists(cur, "common_event_outbox"):
            return {}
        cur.execute(
            """
            SELECT event_type, status, count(*)::int AS count
            FROM common_event_outbox
            WHERE source_layer = 'N5_action'
              AND source_run_id = %s
            GROUP BY event_type, status
            ORDER BY event_type, status
            """,
            (self.source_action_run_id,),
        )
        return {f"{row['event_type']}:{row['status']}": row["count"] for row in cur.fetchall()}

    def _fetch_projection_events(self, cur: psycopg.Cursor[dict[str, Any]]) -> list[ProjectionEvent]:
        if not self._table_exists(cur, "common_event_outbox"):
            return []
        cur.execute(
            """
            SELECT outbox_id,
                   event_id,
                   event_type,
                   event_schema_version,
                   trade_date,
                   asset_kind,
                   identity_key,
                   event_time,
                   source_layer,
                   source_run_id,
                   dedup_key,
                   partition_key,
                   status,
                   payload_json,
                   NULL::text AS source_display_table,
                   NULL::integer AS display_basis_id,
                   payload_json->>'source_condition_run_id' AS display_run_id,
                   COALESCE(payload_json->>'code', split_part(identity_key, ':', 3)) AS code,
                   payload_json->>'name' AS name,
                   COALESCE(payload_json->>'target_price', payload_json->>'action_target_price') AS target_price,
                   COALESCE(payload_json->>'expected_return_pct', payload_json->>'action_expected_return_pct') AS expected_return_pct,
                   COALESCE(payload_json->>'board_code', payload_json->'trace_json'->>'board_code') AS board_code,
                   COALESCE(payload_json->>'board_name', payload_json->'trace_json'->>'board_name') AS board_name,
                   payload_json->>'current_price' AS current_price
              FROM common_event_outbox
             WHERE source_layer = 'N5_action'
               AND source_run_id = %s
               AND event_type = ANY(%s)
               AND status = 'pending'
             ORDER BY partition_key, event_time, outbox_id, event_id
            """,
            (self.source_action_run_id, list(ALLOWED_EVENT_TYPES)),
        )
        return [ProjectionEvent(**dict(row)) for row in cur.fetchall()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan N6 projection dry-run from pending N5 action outbox.")
    parser.add_argument("--dsn", help="PostgreSQL DSN. Defaults to caller-provided project default.")
    parser.add_argument("--execute", action="store_true", help="Rejected. N6 projection execute requires a later gate.")
    parser.add_argument("--source-action-run-id", default=DEFAULT_SOURCE_ACTION_RUN_ID)
    parser.add_argument("--user-projection-run-id", default=DEFAULT_USER_PROJECTION_RUN_ID)
    parser.add_argument(
        "--expected-n5-outbox-count",
        action="append",
        default=[],
        metavar="EVENT:STATUS=COUNT",
        help="Explicit N5 outbox baseline for this gate, for example ActionExecuted:pending=4.",
    )
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def run_projection_dry_run(
    *,
    repository: ProjectionPlanRepository | None = None,
    dsn: str | None = None,
    execute: bool = False,
    source_action_run_id: str = DEFAULT_SOURCE_ACTION_RUN_ID,
    user_projection_run_id: str = DEFAULT_USER_PROJECTION_RUN_ID,
    expected_n5_outbox_counts: Mapping[str, int] | None = None,
    json_report_path: str = DEFAULT_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_MARKDOWN_REPORT_PATH,
    sample_limit: int = 20,
    write_reports: bool = False,
    user_message_event_filter: Sequence[str] | None = None,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    if execute:
        report = build_execute_blocked_report(
            started_at=started_at,
            finished_at=utc_now_iso(),
            source_action_run_id=source_action_run_id,
            user_projection_run_id=user_projection_run_id,
            json_report_path=json_report_path,
            markdown_report_path=markdown_report_path,
        )
        if write_reports:
            write_report_files(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)
        return report

    if repository is None:
        if not dsn:
            report = build_missing_dsn_report(
                started_at=started_at,
                finished_at=utc_now_iso(),
                source_action_run_id=source_action_run_id,
                user_projection_run_id=user_projection_run_id,
                json_report_path=json_report_path,
                markdown_report_path=markdown_report_path,
            )
            if write_reports:
                write_report_files(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)
            return report
        repository = PostgresProjectionPlanRepository(dsn, source_action_run_id=source_action_run_id)

    snapshot = repository.fetch_input_snapshot()
    report = build_projection_report(
        snapshot=snapshot,
        started_at=started_at,
        finished_at=utc_now_iso(),
        source_action_run_id=source_action_run_id,
        user_projection_run_id=user_projection_run_id,
        expected_n5_outbox_counts=expected_n5_outbox_counts,
        user_message_event_filter=user_message_event_filter,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        sample_limit=sample_limit,
    )
    if write_reports:
        write_report_files(report, json_report_path=json_report_path, markdown_report_path=markdown_report_path)
    return report


def build_execute_blocked_report(
    *,
    started_at: str,
    finished_at: str,
    source_action_run_id: str,
    user_projection_run_id: str,
    json_report_path: str,
    markdown_report_path: str,
) -> dict[str, Any]:
    item = quality_item(
        "P0",
        "failed",
        "execute_flag_not_allowed",
        "N6 projection dry-run runner rejects --execute",
        expected="execute=false",
        actual="execute=true",
    )
    return build_base_report(
        result="BLOCKED",
        blockers=["execute_flag_not_allowed"],
        warnings=[],
        notes=[],
        quality_items=[item],
        started_at=started_at,
        finished_at=finished_at,
        source_action_run_id=source_action_run_id,
        user_projection_run_id=user_projection_run_id,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        planned_row_counts=empty_planned_row_counts(),
        missing_fields_summary=empty_missing_fields_summary(),
        event_summary=empty_event_summary(),
        notification_plan_summary=empty_notification_summary(),
        input_state=None,
        sample_plans=[],
    )


def build_missing_dsn_report(
    *,
    started_at: str,
    finished_at: str,
    source_action_run_id: str,
    user_projection_run_id: str,
    json_report_path: str,
    markdown_report_path: str,
) -> dict[str, Any]:
    item = quality_item(
        "P0",
        "failed",
        "missing_dsn",
        "N6 projection dry-run requires a PostgreSQL DSN when no repository is injected",
        expected="dsn provided",
        actual="missing",
    )
    return build_base_report(
        result="BLOCKED",
        blockers=["missing_dsn"],
        warnings=[],
        notes=[],
        quality_items=[item],
        started_at=started_at,
        finished_at=finished_at,
        source_action_run_id=source_action_run_id,
        user_projection_run_id=user_projection_run_id,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        planned_row_counts=empty_planned_row_counts(),
        missing_fields_summary=empty_missing_fields_summary(),
        event_summary=empty_event_summary(),
        notification_plan_summary=empty_notification_summary(),
        input_state=None,
        sample_plans=[],
    )


def build_projection_report(
    *,
    snapshot: ProjectionInputSnapshot,
    started_at: str,
    finished_at: str,
    source_action_run_id: str,
    user_projection_run_id: str,
    expected_n5_outbox_counts: Mapping[str, int] | None,
    json_report_path: str,
    markdown_report_path: str,
    sample_limit: int,
    user_message_event_filter: Sequence[str] | None = None,
) -> dict[str, Any]:
    source_events = list(snapshot.events)
    filter_result = normalize_user_message_event_filter(user_message_event_filter)
    user_message_events = events_for_user_message_filter(source_events, filter_result["event_types"])
    missing = summarize_missing_fields(source_events)
    event_summary = summarize_events(source_events)
    user_message_summary = build_user_message_summary(source_events, user_message_events, filter_result)
    notification_summary = build_notification_summary(user_message_events)
    planned_row_counts = build_planned_row_counts(
        len(user_message_events),
        projection_run_count=1 if source_events else 0,
    )
    sample_plans = build_sample_plans(
        user_message_events,
        user_projection_run_id=user_projection_run_id,
        admin=snapshot.admin,
        default_profile=snapshot.default_profile,
        sample_limit=sample_limit,
    )
    quality_items = build_quality_items(
        snapshot,
        missing,
        event_summary,
        notification_summary,
        source_action_run_id=source_action_run_id,
        expected_n5_outbox_counts=expected_n5_outbox_counts,
        user_message_filter_result=filter_result,
    )
    severity_counts = count_quality_severities(quality_items)
    blockers = [
        str(item["gate_code"])
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    ]
    warnings = [
        str(item["gate_code"])
        for item in quality_items
        if item.get("severity") == "P1" and item.get("status") == "warning"
    ]
    notes = [
        str(item["gate_code"])
        for item in quality_items
        if item.get("severity") == "P2" and item.get("status") == "warning"
    ]
    result = "BLOCKED" if severity_counts["P0"] > 0 else "DRY_RUN_PASS"
    if result == "DRY_RUN_PASS" and source_events and not user_message_events:
        result = "PROJECTION_PASS_ZERO_USER_MESSAGES"
    report = build_base_report(
        result=result,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
        notes=sorted(set(notes)),
        quality_items=quality_items,
        started_at=started_at,
        finished_at=finished_at,
        source_action_run_id=source_action_run_id,
        user_projection_run_id=user_projection_run_id,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        planned_row_counts=planned_row_counts,
        missing_fields_summary=missing,
        event_summary=event_summary,
        notification_plan_summary=notification_summary,
        input_state=build_input_state(snapshot, expected_n5_outbox_counts=expected_n5_outbox_counts),
        sample_plans=sample_plans,
    )
    report["user_message_event_filter"] = {
        "explicit": filter_result["explicit"],
        "event_types": list(filter_result["event_types"]),
    }
    report["user_message_summary"] = user_message_summary
    return report


def build_quality_items(
    snapshot: ProjectionInputSnapshot,
    missing: Mapping[str, int],
    event_summary: Mapping[str, Any],
    notification_summary: Mapping[str, Any],
    *,
    source_action_run_id: str,
    expected_n5_outbox_counts: Mapping[str, int] | None = None,
    user_message_filter_result: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    admin_ok = snapshot.admin is not None and snapshot.admin.login_name == "admin" and snapshot.admin.role == "admin" and snapshot.admin.status == "active"
    items.append(
        quality_item(
            "P0",
            "passed" if admin_ok else "failed",
            "missing_active_admin",
            "N6 projection dry-run requires active admin user",
            expected="admin active",
            actual=admin_status(snapshot.admin),
        )
    )

    profile_ok = snapshot.default_profile is not None and snapshot.default_profile.is_default and snapshot.default_profile.status == "active"
    items.append(
        quality_item(
            "P0",
            "passed" if profile_ok else "failed",
            "missing_default_admin_filter_profile",
            "N6 projection dry-run requires active default admin filter profile",
            expected="one active default profile",
            actual=profile_status(snapshot.default_profile),
        )
    )

    stale_source_ok = not is_stale_source_action_run_id(source_action_run_id)
    items.append(
        quality_item(
            "P0",
            "passed" if stale_source_ok else "failed",
            "stale_source_action_run_id",
            "N6 active projection must not read reviewed stale N5 source runs",
            expected="source_action_run_id not in stale active lineage registry",
            actual=source_action_run_id,
        )
    )

    missing_tables = sorted(table for table, count in snapshot.table_counts.items() if count is None)
    items.append(
        quality_item(
            "P0",
            "passed" if not missing_tables else "failed",
            "missing_n6_schema_table",
            "All N6 projection tables must exist",
            expected="no missing N6 table",
            actual=",".join(missing_tables) if missing_tables else "none",
            details={"missing_tables": missing_tables},
        )
    )

    filter_result = user_message_filter_result or normalize_user_message_event_filter(None)
    items.append(
        quality_item(
            "P0",
            "passed" if filter_result["valid"] else "failed",
            str(filter_result["gate_code"]),
            "N6 user message event filter must be explicit when supplied and only contain supported canonical Action* event types",
            expected="non-empty subset of ActionEligible,ActionExecuted,ActionBlocked,ActionSkipped",
            actual=json.dumps(filter_result["raw_event_types"], sort_keys=True),
        )
    )

    expected_outbox_counts = resolve_expected_n5_outbox_counts(snapshot, expected_n5_outbox_counts)
    outbox_counts_ok = snapshot.n5_outbox_counts == expected_outbox_counts
    items.append(
        quality_item(
            "P0",
            "passed" if outbox_counts_ok else "failed",
            "n5_outbox_count_mismatch_without_new_gate",
            "N6 dry-run baseline expects the reviewed N5 outbox distribution for this compatibility path",
            expected=json.dumps(expected_outbox_counts, sort_keys=True),
            actual=json.dumps(snapshot.n5_outbox_counts, sort_keys=True),
        )
    )

    bad_event_types = sorted(
        {
            event.event_type
            for event in snapshot.events
            if event.event_type not in ALLOWED_EVENT_TYPES
        }
    )
    items.append(
        quality_item(
            "P0",
            "passed" if not bad_event_types else "failed",
            "input_event_type_not_supported_n5_action_event",
            "N6 dry-run may only read canonical N5 Action* events or legacy ActionEvent / HintEvent replay events",
            expected=",".join(ALLOWED_EVENT_TYPES),
            actual=",".join(bad_event_types) if bad_event_types else ",".join(ALLOWED_EVENT_TYPES),
        )
    )

    bad_source_layer_count = sum(1 for event in snapshot.events if event.source_layer != "N5_action")
    items.append(
        quality_item(
            "P0",
            "passed" if bad_source_layer_count == 0 else "failed",
            "source_layer_not_n5_action",
            "N6 dry-run may only read N5_action events",
            expected="0",
            actual=str(bad_source_layer_count),
        )
    )

    envelope_missing = find_missing_envelope_fields(snapshot.events)
    for field, count in sorted(envelope_missing.items()):
        items.append(
            quality_item(
                "P0",
                "failed",
                f"required_event_envelope_missing:{field}",
                "N5 event envelope field is required for N6 projection",
                expected="0",
                actual=str(count),
            )
        )
    if not envelope_missing:
        items.append(
            quality_item(
                "P0",
                "passed",
                "required_event_envelope_missing",
                "N5 event envelope required fields are present",
                expected="0",
                actual="0",
            )
        )

    payload_missing = find_missing_payload_fields(snapshot.events)
    for field, count in sorted(payload_missing.items()):
        items.append(
            quality_item(
                "P0",
                "failed",
                f"required_payload_field_missing:{field}",
                "N5 event payload field is required for N6 projection",
                expected="0",
                actual=str(count),
            )
        )
    if not payload_missing:
        items.append(
            quality_item(
                "P0",
                "passed",
                "required_payload_field_missing",
                "N5 event payload required fields are present",
                expected="0",
                actual="0",
            )
        )

    items.append(
        quality_item(
            "P1",
            "warning" if missing["display_basis_missing"] else "passed",
            "display_basis_missing",
            "Display enrichment is absent; N6 dry-run must not backfill by scanning N4/N3/N2 naked facts",
            expected="0",
            actual=str(missing["display_basis_missing"]),
        )
    )
    items.append(
        quality_item(
            "P1",
            "warning" if missing["current_price_missing"] else "passed",
            "current_price_missing",
            "Current price is not available in MVP projection inputs",
            expected="0",
            actual=str(missing["current_price_missing"]),
        )
    )
    items.append(
        quality_item(
            "P1",
            "warning" if missing["target_price_missing"] else "passed",
            "target_price_missing",
            "Target price is optional but must be reported when missing",
            expected="0",
            actual=str(missing["target_price_missing"]),
        )
    )
    items.append(
        quality_item(
            "P1",
            "warning" if missing["expected_return_pct_missing"] else "passed",
            "expected_return_pct_missing",
            "Expected return percentage is optional but must be reported when missing",
            expected="0",
            actual=str(missing["expected_return_pct_missing"]),
        )
    )
    items.append(
        quality_item(
            "P1",
            "warning" if missing["board_context_missing"] else "passed",
            "board_context_missing",
            "Board context is optional but must be reported when missing",
            expected="0",
            actual=str(missing["board_context_missing"]),
        )
    )

    items.append(
        quality_item(
            "P0",
            "passed" if notification_summary["queued_only_passed"] else "failed",
            "notification_only_queued_only",
            "N6 dry-run notification candidates must be queued_only and not pushed",
            expected="all queued_only",
            actual=json.dumps(notification_summary["queue_status_counts"], sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P2",
            "warning",
            "canonical_dry_run_uses_n5_outbox_only",
            "N6 canonical dry-run reads N5 outbox events only and does not substitute N4/N3/N2 naked facts",
            expected="N5 outbox only",
            actual=json.dumps(snapshot.display_basis_counts, sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P2",
            "warning",
            "n5_outbox_status_remains_pending_in_dry_run",
            "N6 dry-run does not consume or update N5 outbox status",
            expected="pending unchanged",
            actual=json.dumps(event_summary["by_event_type"], sort_keys=True),
        )
    )
    return items


def summarize_missing_fields(events: Sequence[ProjectionEvent]) -> dict[str, int]:
    return {
        "display_basis_missing": sum(1 for event in events if event.display_basis_id is None),
        "code_name_missing": sum(1 for event in events if not event.code or not event.name),
        "current_price_missing": sum(1 for event in events if event.current_price is None),
        "target_price_missing": sum(1 for event in events if event.target_price is None),
        "expected_return_pct_missing": sum(1 for event in events if event.expected_return_pct is None),
        "board_context_missing": sum(1 for event in events if not event.board_code or not event.board_name),
    }


def summarize_events(events: Sequence[ProjectionEvent]) -> dict[str, Any]:
    by_event_type = Counter(event.event_type for event in events)
    by_direction = Counter(str(event.payload_json.get("direction") or "") for event in events)
    by_signal_type = Counter(str(event.payload_json.get("signal_type") or "") for event in events)
    distribution = Counter(
        (
            event.event_type,
            str(event.payload_json.get("direction") or ""),
            str(event.payload_json.get("signal_type") or ""),
            str(event.payload_json.get("action_type") or ""),
            str(event.payload_json.get("lane") or ""),
        )
        for event in events
    )
    return {
        "input_event_count": len(events),
        "by_event_type": dict(sorted(by_event_type.items())),
        "by_direction": dict(sorted(by_direction.items())),
        "by_signal_type": dict(sorted(by_signal_type.items())),
        "distribution": [
            {
                "event_type": event_type,
                "direction": direction,
                "signal_type": signal_type,
                "action_type": action_type,
                "lane": lane,
                "count": count,
            }
            for (event_type, direction, signal_type, action_type, lane), count in sorted(distribution.items())
        ],
    }


def build_notification_summary(events: Sequence[ProjectionEvent]) -> dict[str, Any]:
    statuses = Counter("queued_only" for _ in events)
    sources = Counter(notification_source_for_event(event) for event in events)
    return {
        "planned_notification_count": len(events),
        "queue_status_counts": dict(sorted(statuses.items())),
        "notification_source_counts": dict(sorted(sources.items())),
        "queued_only_passed": set(statuses) <= {"queued_only"},
        "actual_push": False,
        "voice_mobile_push": False,
        "provider_delivery_attempt": False,
    }


def build_planned_row_counts(event_count: int, *, projection_run_count: int | None = None) -> dict[str, int]:
    return {
        "user_projection_run": 1 if event_count > 0 else 0 if projection_run_count is None else projection_run_count,
        "user_signal_projection": event_count,
        "user_signal_card": event_count,
        "user_notification_queue": event_count,
        "user_signal_decision": 0,
        "user_sim_account": 0,
        "user_sim_order": 0,
        "user_sim_trade": 0,
        "user_sim_position": 0,
        "user_sim_rows": 0,
        "user_session": 0,
        "n5_outbox_status_updates": 0,
    }


def normalize_user_message_event_filter(values: Sequence[str] | None) -> dict[str, Any]:
    if values is None:
        return {
            "explicit": False,
            "valid": True,
            "gate_code": "user_message_event_filter_legacy_all_events",
            "raw_event_types": list(ALLOWED_EVENT_TYPES),
            "event_types": tuple(ALLOWED_EVENT_TYPES),
        }
    raw = [str(value).strip() for value in values if str(value).strip()]
    if not raw:
        return {
            "explicit": True,
            "valid": False,
            "gate_code": "missing_user_message_event_filter",
            "raw_event_types": [],
            "event_types": tuple(),
        }
    unsupported = sorted(set(raw) - set(CANONICAL_EVENT_TYPES))
    if unsupported:
        return {
            "explicit": True,
            "valid": False,
            "gate_code": "unsupported_user_message_event_filter",
            "raw_event_types": raw,
            "event_types": tuple(raw),
            "unsupported": unsupported,
        }
    return {
        "explicit": True,
        "valid": True,
        "gate_code": "user_message_event_filter_valid",
        "raw_event_types": raw,
        "event_types": tuple(raw),
    }


def events_for_user_message_filter(events: Sequence[ProjectionEvent], event_types: Sequence[str]) -> list[ProjectionEvent]:
    allowed = set(event_types)
    return [event for event in events if event.event_type in allowed]


def build_user_message_summary(
    source_events: Sequence[ProjectionEvent],
    user_message_events: Sequence[ProjectionEvent],
    filter_result: Mapping[str, Any],
) -> dict[str, Any]:
    eligible_types = Counter(event.event_type for event in user_message_events)
    source_types = Counter(event.event_type for event in source_events)
    return {
        "filter_explicit": bool(filter_result["explicit"]),
        "filter_event_types": list(filter_result["event_types"]),
        "source_event_count": len(source_events),
        "eligible_user_message_count": len(user_message_events),
        "diagnosis_only_count": len(source_events) - len(user_message_events),
        "source_by_event_type": dict(sorted(source_types.items())),
        "eligible_by_event_type": dict(sorted(eligible_types.items())),
    }


def build_sample_plans(
    events: Sequence[ProjectionEvent],
    *,
    user_projection_run_id: str,
    admin: AdminUser | None,
    default_profile: FilterProfile | None,
    sample_limit: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    user_id = admin.user_id if admin else None
    user_filter_profile_id = default_profile.user_filter_profile_id if default_profile else None
    for event in list(events)[: max(0, sample_limit)]:
        direction = str(event.payload_json.get("direction") or "")
        signal_type = str(event.payload_json.get("signal_type") or "")
        code = event.code or event.identity_key
        name = event.name or event.identity_key
        card_type = card_type_for_event(event)
        card_status = card_status_for_event(event)
        action_state = action_state_for_event(event)
        action_mark = action_mark_for_event(event)
        projection_policy = projection_policy_for_event(event)
        title = f"{name} {signal_type}".strip()
        output.append(
            {
                "source_event_id": event.event_id,
                "source_outbox_id": event.outbox_id,
                "user_projection_run_id": user_projection_run_id,
                "projection": {
                    "user_id": user_id,
                    "user_filter_profile_id": user_filter_profile_id,
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
                    "action_state": action_state,
                    "action_mark": action_mark,
                    "condition_key": event.payload_json.get("condition_key"),
                    "original_condition_key": event.payload_json.get("original_condition_key"),
                    "trace_json": event.payload_json.get("trace_json"),
                    "projection_policy": projection_policy,
                    "asset_kind": event.asset_kind,
                    "identity_key": event.identity_key,
                    "code": code,
                    "name": name,
                    "direction": direction,
                    "signal_type": signal_type,
                    "target_price": json_safe(event.target_price),
                    "current_price": json_safe(event.current_price),
                    "expected_return_pct": json_safe(event.expected_return_pct),
                    "board_code": event.board_code,
                    "board_name": event.board_name,
                    "source_display_table": event.source_display_table,
                    "source_condition_display_basis_id": event.display_basis_id,
                    "source_condition_display_run_id": event.display_run_id,
                    "projection_status": "visible",
                },
                "card": {
                    "user_id": user_id,
                    "card_type": card_type,
                    "card_status": card_status,
                    "display_priority": display_priority_for_event(event),
                    "title": title,
                    "summary": build_card_summary(event),
                    "asset_kind": event.asset_kind,
                    "identity_key": event.identity_key,
                    "code": code,
                    "name": name,
                    "direction": direction,
                    "signal_type": signal_type,
                    "target_price": json_safe(event.target_price),
                    "current_price": json_safe(event.current_price),
                    "expected_return_pct": json_safe(event.expected_return_pct),
                    "board_code": event.board_code,
                    "board_name": event.board_name,
                    "source_action_run_id": event.source_run_id,
                    "source_event_id": event.event_id,
                    "source_action_event_id": event.event_id,
                    "source_action_event_type": event.event_type,
                    "action_state": action_state,
                    "action_mark": action_mark,
                    "condition_key": event.payload_json.get("condition_key"),
                    "original_condition_key": event.payload_json.get("original_condition_key"),
                    "trace_json": event.payload_json.get("trace_json"),
                    "projection_policy": projection_policy,
                    "decision_buttons": False if event.event_type == "ActionBlocked" else None,
                    "sim_allowed": False,
                    "real_trade_allowed": False,
                },
                "notification": {
                    "user_id": user_id,
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
                    "action_state": action_state,
                    "action_mark": action_mark,
                    "condition_key": event.payload_json.get("condition_key"),
                    "original_condition_key": event.payload_json.get("original_condition_key"),
                    "trace_json": event.payload_json.get("trace_json"),
                    "projection_policy": projection_policy,
                    "actual_push": False,
                    "voice_mobile_push": False,
                },
            }
        )
    return output


def build_input_state(
    snapshot: ProjectionInputSnapshot,
    *,
    expected_n5_outbox_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "admin": asdict(snapshot.admin) if snapshot.admin else None,
        "default_filter_profile": asdict(snapshot.default_profile) if snapshot.default_profile else None,
        "table_counts": dict(snapshot.table_counts),
        "n5_outbox_counts": dict(snapshot.n5_outbox_counts),
        "n5_outbox_expected": dict(resolve_expected_n5_outbox_counts(snapshot, expected_n5_outbox_counts)),
        "n5_outbox_expected_source": "explicit_gate" if expected_n5_outbox_counts is not None else "compat_default",
        "display_basis_counts": dict(snapshot.display_basis_counts),
    }


def resolve_expected_n5_outbox_counts(
    snapshot: ProjectionInputSnapshot,
    expected_n5_outbox_counts: Mapping[str, int] | None = None,
) -> dict[str, int]:
    if expected_n5_outbox_counts is not None:
        return dict(expected_n5_outbox_counts)
    event_types = {key.split(":", 1)[0] for key in snapshot.n5_outbox_counts}
    if event_types and event_types <= set(LEGACY_EVENT_TYPES):
        return dict(LEGACY_EXPECTED_N5_OUTBOX_COUNTS)
    return dict(EXPECTED_N5_OUTBOX_COUNTS)


def parse_expected_n5_outbox_counts(values: Sequence[str] | None) -> dict[str, int] | None:
    if not values:
        return None
    parsed: dict[str, int] = {}
    for value in values:
        key, separator, count_text = value.partition("=")
        if separator != "=" or ":" not in key:
            raise ValueError(f"invalid expected count {value!r}; expected EVENT:STATUS=COUNT")
        event_type, status = key.split(":", 1)
        event_type = event_type.strip()
        status = status.strip()
        if event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"unsupported expected event_type {event_type!r}")
        if status not in {"pending", "delivering", "delivered", "failed", "dead_letter"}:
            raise ValueError(f"unsupported expected outbox status {status!r}")
        try:
            count = int(count_text)
        except ValueError as exc:
            raise ValueError(f"invalid expected count value {count_text!r}") from exc
        if count < 0:
            raise ValueError(f"expected count must be non-negative for {key!r}")
        parsed[f"{event_type}:{status}"] = count
    return parsed


def build_base_report(
    *,
    result: str,
    blockers: list[str],
    warnings: list[str],
    notes: list[str],
    quality_items: list[dict[str, Any]],
    started_at: str,
    finished_at: str,
    source_action_run_id: str,
    user_projection_run_id: str,
    json_report_path: str,
    markdown_report_path: str,
    planned_row_counts: Mapping[str, int],
    missing_fields_summary: Mapping[str, int],
    event_summary: Mapping[str, Any],
    notification_plan_summary: Mapping[str, Any],
    input_state: Mapping[str, Any] | None,
    sample_plans: list[dict[str, Any]],
) -> dict[str, Any]:
    quality_counts = count_quality_severities(quality_items)
    return normalize_jsonable(
        {
            "stage": "N6-projection-dry-run",
            "layer_role": "N6_user",
            "mode": "projection_dry_run",
            "result": result,
            "blockers": blockers,
            "warnings": warnings,
            "notes": notes,
            "source_action_run_id": source_action_run_id,
            "user_projection_run_id": user_projection_run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "json_report_path": json_report_path,
            "markdown_report_path": markdown_report_path,
            "input_boundary": {
                "n5_outbox": {
                    "source_layer": "N5_action",
                    "status": "pending",
                    "event_types": list(ALLOWED_EVENT_TYPES),
                    "canonical_event_types": list(CANONICAL_EVENT_TYPES),
                    "legacy_compat_event_types": list(LEGACY_EVENT_TYPES),
                    "source_run_id": source_action_run_id,
                },
                "n4_n3_n2_naked_fact_substitution": False,
                "n2_display_basis": {
                    "read_as_event_substitute": False,
                    "tables": [],
                },
                "n6_user_scope": ["user_account", "user_filter_profile"],
            },
            "forbidden_scope": forbidden_scope(),
            "input_state": input_state,
            "event_summary": event_summary,
            "planned_row_counts": dict(planned_row_counts),
            "missing_fields_summary": dict(missing_fields_summary),
            "notification_plan_summary": notification_plan_summary,
            "sample_plans": sample_plans,
            "quality": {
                "p0_count": quality_counts["P0"],
                "p1_count": quality_counts["P1"],
                "p2_count": quality_counts["P2"],
                "items": quality_items,
            },
            "side_effects": side_effects(),
            "n5_outbox_before": (input_state or {}).get("n5_outbox_counts") if input_state else None,
            "n5_outbox_after": (input_state or {}).get("n5_outbox_counts") if input_state else None,
            "n5_outbox_unchanged": True if input_state else None,
            "allow_projection_execute": False,
            "allow_n5_outbox_consumption": False,
            "allowed_next_gate": "N6 projection dry-run review" if result == "DRY_RUN_PASS" else "resolve P0 blockers before dry-run review",
        }
    )


def find_missing_envelope_fields(events: Sequence[ProjectionEvent]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in events:
        data = asdict(event)
        for field in REQUIRED_ENVELOPE_FIELDS:
            if data.get(field) in (None, ""):
                counts[field] += 1
    return dict(counts)


def find_missing_payload_fields(events: Sequence[ProjectionEvent]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in events:
        payload = event.payload_json or {}
        for field in required_payload_fields_for_event(event):
            if payload.get(field) in (None, "", {}):
                counts[field] += 1
    return dict(counts)


def required_payload_fields_for_event(event: ProjectionEvent) -> tuple[str, ...]:
    if event.event_type in CANONICAL_EVENT_TYPES:
        return CANONICAL_REQUIRED_PAYLOAD_FIELDS
    return LEGACY_REQUIRED_PAYLOAD_FIELDS


def card_type_for_event(event: ProjectionEvent) -> str:
    direction = str(event.payload_json.get("direction") or "")
    if event.event_type == "ActionBlocked":
        return "blocked"
    if event.event_type == "ActionExecuted":
        return "action_confirmed"
    if event.event_type == "ActionSkipped":
        return "skipped"
    if event.event_type == "ActionEligible":
        return "buy_candidate" if direction == "buy" else "sell_candidate"
    if event.event_type == "HintEvent":
        return "hint"
    return "buy_candidate" if direction == "buy" else "sell_candidate"


def card_status_for_event(event: ProjectionEvent) -> str:
    action_state = action_state_for_event(event)
    if event.event_type == "ActionEligible":
        return "candidate"
    if event.event_type == "ActionBlocked":
        return "blocked"
    if event.event_type == "ActionExecuted":
        return "action_confirmed"
    if event.event_type == "ActionSkipped":
        return "expired" if action_state == "expired" else "skipped"
    return "active"


def notification_source_for_event(event: ProjectionEvent) -> str:
    return NOTIFICATION_SOURCE_BY_EVENT_TYPE.get(event.event_type, "n5_action_event")


def display_priority_for_event(event: ProjectionEvent) -> int:
    if event.event_type == "ActionEligible":
        base = 10
    elif event.event_type == "ActionExecuted":
        base = 20
    elif event.event_type == "ActionBlocked":
        base = 40
    elif event.event_type == "ActionSkipped":
        base = 80
    elif event.event_type == "HintEvent":
        base = 30
    else:
        base = 15
    direction_offset = 1 if event.payload_json.get("direction") == "sell" else 0
    return base + direction_offset


def action_state_for_event(event: ProjectionEvent) -> str | None:
    payload_state = event.payload_json.get("action_state")
    if payload_state:
        return str(payload_state)
    return ACTION_STATE_BY_EVENT_TYPE.get(event.event_type)


def action_mark_for_event(event: ProjectionEvent) -> str | None:
    value = event.payload_json.get("action_mark")
    if isinstance(value, str) and value.lower() in {"", "none", "null"}:
        return None
    return str(value) if value else None


def projection_policy_for_event(event: ProjectionEvent) -> str:
    return PROJECTION_POLICY_BY_EVENT_TYPE.get(event.event_type, "n5_action_event_queued_only")


def build_card_summary(event: ProjectionEvent) -> str:
    direction = str(event.payload_json.get("direction") or "unknown")
    signal_type = str(event.payload_json.get("signal_type") or "unknown")
    parts = [direction, signal_type]
    action_state = action_state_for_event(event)
    if action_state:
        parts.append(f"state={action_state}")
    condition_key = event.payload_json.get("condition_key")
    if condition_key:
        parts.append(f"condition={condition_key}")
    original_condition_key = event.payload_json.get("original_condition_key")
    if original_condition_key and original_condition_key != condition_key:
        parts.append(f"original_condition={original_condition_key}")
    if event.event_type == "ActionBlocked":
        parts.append("user_card_state=blocked/未确认")
    if event.target_price is not None:
        parts.append(f"target={event.target_price}")
    if event.expected_return_pct is not None:
        parts.append(f"expected_return_pct={event.expected_return_pct}")
    if event.board_name:
        parts.append(f"board={event.board_name}")
    return " | ".join(parts)


def admin_status(admin: AdminUser | None) -> str:
    if admin is None:
        return "missing"
    return f"{admin.login_name}:{admin.role}:{admin.status}"


def profile_status(profile: FilterProfile | None) -> str:
    if profile is None:
        return "missing"
    return f"{profile.profile_name}:default={str(profile.is_default).lower()}:{profile.status}"


def side_effects() -> dict[str, bool]:
    return {
        "read_only_database_checks": True,
        "writes_database": False,
        "writes_user_projection_run": False,
        "writes_user_signal_projection": False,
        "writes_user_signal_card": False,
        "writes_user_notification_queue": False,
        "writes_user_signal_decision": False,
        "writes_user_session": False,
        "writes_user_sim_tables": False,
        "writes_user_watchlist": False,
        "n5_outbox_consumed": False,
        "updates_n5_outbox_status": False,
        "writes_n5_inbox_or_checkpoint": False,
        "writes_n1_to_n5": False,
        "starts_worker": False,
        "actual_push": False,
        "voice_mobile_push": False,
        "writes_voice_mobile_delivery": False,
        "writes_position": False,
        "real_trade": False,
        "old_system_touched": False,
    }


def forbidden_scope() -> dict[str, bool]:
    return {
        "read_n4_n5_naked_facts_as_input": False,
        "consume_n5_outbox": False,
        "update_n5_outbox_status": False,
        "write_user_projection_run": False,
        "write_user_signal_projection": False,
        "write_user_signal_card": False,
        "write_user_notification_queue": False,
        "write_user_signal_decision": False,
        "write_user_session": False,
        "write_user_sim_tables": False,
        "write_user_watchlist": False,
        "write_voice_mobile_delivery": False,
        "write_position": False,
        "start_worker": False,
        "actual_push": False,
        "voice_mobile_push": False,
        "real_trade": False,
    }


def empty_planned_row_counts() -> dict[str, int]:
    return build_planned_row_counts(0)


def empty_missing_fields_summary() -> dict[str, int]:
    return {
        "display_basis_missing": 0,
        "code_name_missing": 0,
        "current_price_missing": 0,
        "target_price_missing": 0,
        "expected_return_pct_missing": 0,
        "board_context_missing": 0,
    }


def empty_event_summary() -> dict[str, Any]:
    return {
        "input_event_count": 0,
        "by_event_type": {},
        "by_direction": {},
        "by_signal_type": {},
        "distribution": [],
    }


def empty_notification_summary() -> dict[str, Any]:
    return {
        "planned_notification_count": 0,
        "queue_status_counts": {},
        "notification_source_counts": {},
        "queued_only_passed": True,
        "actual_push": False,
        "voice_mobile_push": False,
        "provider_delivery_attempt": False,
    }


def write_report_files(report: Mapping[str, Any], *, json_report_path: str, markdown_report_path: str) -> None:
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_markdown_report(report))


def write_json(path: str, report: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def format_markdown_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    planned = report.get("planned_row_counts") or {}
    missing = report.get("missing_fields_summary") or {}
    event_summary = report.get("event_summary") or {}
    side = report.get("side_effects") or {}
    lines = [
        "# N6 Projection Dry-Run Report",
        "",
        "## Summary",
        "",
        f"- result: {report.get('result')}",
        f"- layer_role: {report.get('layer_role')}",
        f"- source_action_run_id: {report.get('source_action_run_id')}",
        f"- user_projection_run_id: {report.get('user_projection_run_id')}",
        f"- blockers: {report.get('blockers') or []}",
        f"- warnings: {report.get('warnings') or []}",
        f"- P0/P1/P2: {quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
        "",
        "## Input Events",
        "",
        f"- input_event_count: {event_summary.get('input_event_count')}",
        f"- by_event_type: {event_summary.get('by_event_type')}",
        "",
        "## Planned Rows",
        "",
        f"- user_projection_run: {planned.get('user_projection_run')}",
        f"- user_signal_projection: {planned.get('user_signal_projection')}",
        f"- user_signal_card: {planned.get('user_signal_card')}",
        f"- user_notification_queue: {planned.get('user_notification_queue')}",
        f"- user_signal_decision: {planned.get('user_signal_decision')}",
        f"- user_sim_rows: {planned.get('user_sim_rows')}",
        "",
        "## Missing Fields",
        "",
        f"- current_price_missing: {missing.get('current_price_missing')}",
        f"- target_price_missing: {missing.get('target_price_missing')}",
        f"- expected_return_pct_missing: {missing.get('expected_return_pct_missing')}",
        f"- display_basis_missing: {missing.get('display_basis_missing')}",
        f"- board_context_missing: {missing.get('board_context_missing')}",
        "",
        "## Boundary",
        "",
        f"- writes_database: {str(side.get('writes_database')).lower()}",
        f"- n5_outbox_consumed: {str(side.get('n5_outbox_consumed')).lower()}",
        f"- updates_n5_outbox_status: {str(side.get('updates_n5_outbox_status')).lower()}",
        f"- writes_user_projection_run: {str(side.get('writes_user_projection_run')).lower()}",
        f"- writes_user_signal_projection: {str(side.get('writes_user_signal_projection')).lower()}",
        f"- writes_user_signal_card: {str(side.get('writes_user_signal_card')).lower()}",
        f"- writes_user_notification_queue: {str(side.get('writes_user_notification_queue')).lower()}",
        f"- writes_user_session: {str(side.get('writes_user_session')).lower()}",
        f"- writes_user_sim_tables: {str(side.get('writes_user_sim_tables')).lower()}",
        f"- starts_worker: {str(side.get('starts_worker')).lower()}",
        f"- actual_push: {str(side.get('actual_push')).lower()}",
        f"- real_trade: {str(side.get('real_trade')).lower()}",
        "",
        "## Next Gate",
        "",
        str(report.get("allowed_next_gate")),
        "",
    ]
    return "\n".join(lines)


def format_summary(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    planned = report.get("planned_row_counts") or {}
    missing = report.get("missing_fields_summary") or {}
    event_summary = report.get("event_summary") or {}
    side = report.get("side_effects") or {}
    return "\n".join(
        [
            "N6 projection dry-run",
            f"  result={report.get('result')}",
            f"  input_events={event_summary.get('input_event_count')}",
            f"  by_event_type={event_summary.get('by_event_type')}",
            f"  planned_projection_run={planned.get('user_projection_run')}",
            f"  planned_signal_projection={planned.get('user_signal_projection')}",
            f"  planned_signal_card={planned.get('user_signal_card')}",
            f"  planned_notification_queue={planned.get('user_notification_queue')}",
            f"  planned_decision={planned.get('user_signal_decision')} planned_sim_rows={planned.get('user_sim_rows')}",
            f"  current_price_missing={missing.get('current_price_missing')}",
            f"  target_price_missing={missing.get('target_price_missing')} expected_return_pct_missing={missing.get('expected_return_pct_missing')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
            f"  blockers={report.get('blockers') or []}",
            f"  warnings={report.get('warnings') or []}",
            f"  writes_database={str(side.get('writes_database')).lower()} n5_outbox_consumed={str(side.get('n5_outbox_consumed')).lower()} updates_n5_outbox_status={str(side.get('updates_n5_outbox_status')).lower()}",
            f"  worker_started={str(side.get('starts_worker')).lower()} actual_push={str(side.get('actual_push')).lower()} real_trade={str(side.get('real_trade')).lower()}",
        ]
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): normalize_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_jsonable(item) for item in value]
    return value


def json_safe(value: Any) -> Any:
    return normalize_jsonable(value)
