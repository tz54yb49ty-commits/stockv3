"""N6 delivery notification no-op materialization runner.

This runner implements only the local preview materialization path for N6
notifications. It never contacts a provider, starts a worker, consumes N5
outbox rows, writes N5 inbox/checkpoints, creates sim/position rows, or places
trades. The only future execute write is append-only rows in
user_notification_queue.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.user.projection_plan import normalize_jsonable, utc_now_iso


DEFAULT_SOURCE_PROJECTION_RUN_ID = (
    "user_projection_shadow_20260603_v1__"
    "action_consumer_market_action_confirmation_v1_20260603_"
    "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1"
)
DEFAULT_DELIVERY_MATERIALIZATION_RUN_ID = "n6_delivery_notification_materialization_20260603_v1__user_projection_shadow_20260603_v1"
DEFAULT_SOURCE_ACTION_RUN_ID = (
    "action_consumer_market_action_confirmation_v1_20260603_"
    "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1"
)
CONTRACT_JSON_PATH = "docs/N6_20260603_delivery_notification_contract.json"
PREFLIGHT_JSON_PATH = "docs/N6_20260603_delivery_notification_preflight.json"
ROLLBACK_SQL_PATH = "sql/N6_20260603_delivery_notification_rollback.sql"

SOURCE_NOTIFICATION_SOURCE = "n5_action_blocked"
SOURCE_QUEUE_STATUS = "queued_only"
SOURCE_CHANNEL = "broadcast_queue"
TARGET_NOTIFICATION_SOURCE = "n6_delivery_materialized_noop"
TARGET_QUEUE_STATUS = "ready_for_future_push"
TARGET_CHANNEL = "in_app_notification_preview"
NOOP_PROVIDER = "noop_local_provider_v1"
USER_POLICY = "admin_default_notification_preview_v1"
DEFAULT_EXPECTED_SOURCE_COUNT = 863
ALLOWED_WRITE_TABLES = ("user_notification_queue",)
PROJECTION_POLICY = "noop_local_preview_materialized_no_delivery"

ALLOWED_PROVIDER_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "delivery_materialization_run_id",
        "dedup_key",
        "provider",
        "channel",
        "policy",
        "asset_kind",
        "identity_key",
        "action_state",
        "display_state",
        "retry",
        "failure",
    }
)
FORBIDDEN_PROVIDER_PAYLOAD_KEYS = frozenset(
    {
        "trace_json",
        "source_payload_json",
        "card_payload_json",
        "display_payload_json",
        "raw_n5_payload",
        "source_outbox_id",
        "source_event_id",
        "source_action_event_id",
        "source_action_run_id",
        "source_event_dedup_key",
        "payload_json",
        "raw_payload",
        "outbox_payload_json",
        "action_run_internal_payload",
    }
)
ALLOWED_CONTRACT_STATUSES = frozenset({"CONTRACT_MATERIALIZATION_PASS", "DELIVERY_EXECUTE_CONTRACT_PASS"})
ALLOWED_PREFLIGHT_STATUSES = frozenset({"EXECUTE_FINAL_PREFLIGHT_PASS", "DELIVERY_EXECUTE_PREFLIGHT_PASS"})


@dataclass
class SourceNotificationRow:
    user_notification_queue_id: int
    user_id: int
    user_projection_run_id: str
    user_signal_projection_id: int | None
    user_signal_card_id: int | None
    notification_source: str
    queue_status: str
    channel: str
    title: str
    message: str
    priority: int | None
    source_event_id: str | None
    source_action_run_id: str | None
    source_action_event_id: str | None
    source_action_event_type: str | None
    action_state: str | None
    action_mark: str | None
    condition_key: str | None
    original_condition_key: str | None
    trace_json: dict[str, Any] | None
    projection_policy: str | None
    asset_kind: str | None
    identity_key: str | None
    notification_payload_json: dict[str, Any]


@dataclass
class DeliveryExecuteSnapshot:
    source_projection_run_id: str
    delivery_materialization_run_id: str
    source_rows: list[SourceNotificationRow]
    existing_materialized_count: int
    forbidden_ref_counts: dict[str, int]
    n5_outbox_counts: dict[str, int]


@dataclass
class DeliveryWritePlan:
    source_projection_run_id: str
    delivery_materialization_run_id: str
    write_tables: tuple[str, ...]
    write_counts: dict[str, int]
    notification_rows: list[dict[str, Any]]


class DeliveryExecuteRepository(Protocol):
    def fetch_delivery_snapshot(
        self,
        *,
        source_projection_run_id: str,
        delivery_materialization_run_id: str,
    ) -> DeliveryExecuteSnapshot:
        ...

    def commit_delivery_materialization(self, plan: DeliveryWritePlan) -> dict[str, Any]:
        ...


class PostgresDeliveryExecuteRepository:
    def __init__(self, dsn: str, *, source_action_run_id: str = DEFAULT_SOURCE_ACTION_RUN_ID) -> None:
        self.dsn = dsn
        self.source_action_run_id = source_action_run_id

    def fetch_delivery_snapshot(
        self,
        *,
        source_projection_run_id: str,
        delivery_materialization_run_id: str,
    ) -> DeliveryExecuteSnapshot:
        with psycopg.connect(
            self.dsn,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
            row_factory=dict_row,
        ) as conn, conn.cursor() as cur:
            source_rows = fetch_source_notification_rows(cur, source_projection_run_id)
            existing_materialized_count = count_existing_materialized_rows(cur, source_projection_run_id, delivery_materialization_run_id)
            forbidden_ref_counts = fetch_forbidden_ref_counts(cur, delivery_materialization_run_id)
            n5_outbox_counts = fetch_n5_outbox_counts(cur, self.source_action_run_id)
        return DeliveryExecuteSnapshot(
            source_projection_run_id=source_projection_run_id,
            delivery_materialization_run_id=delivery_materialization_run_id,
            source_rows=source_rows,
            existing_materialized_count=existing_materialized_count,
            forbidden_ref_counts=forbidden_ref_counts,
            n5_outbox_counts=n5_outbox_counts,
        )

    def commit_delivery_materialization(self, plan: DeliveryWritePlan) -> dict[str, Any]:
        with psycopg.connect(self.dsn, connect_timeout=10, row_factory=dict_row) as conn:
            with conn.transaction(), conn.cursor() as cur:
                for row in plan.notification_rows:
                    insert_notification_preview(cur, row)
        return {
            "committed": True,
            "write_tables": list(plan.write_tables),
            "write_counts": dict(plan.write_counts),
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run N6 no-op delivery notification materialization once.")
    parser.add_argument("--dsn", help="PostgreSQL DSN. Defaults to ASHARE_V3_POSTGRES_DSN or project default in wrapper.")
    parser.add_argument("--source-projection-run-id", default=DEFAULT_SOURCE_PROJECTION_RUN_ID)
    parser.add_argument("--delivery-materialization-run-id", default=DEFAULT_DELIVERY_MATERIALIZATION_RUN_ID)
    parser.add_argument("--source-action-run-id", default=DEFAULT_SOURCE_ACTION_RUN_ID)
    parser.add_argument("--expected-source-count", type=int, default=DEFAULT_EXPECTED_SOURCE_COUNT)
    parser.add_argument("--contract-json-path", default=CONTRACT_JSON_PATH)
    parser.add_argument("--preflight-json-path", default=PREFLIGHT_JSON_PATH)
    parser.add_argument("--rollback-sql-path", default=ROLLBACK_SQL_PATH)
    parser.add_argument("--execute", action="store_true", help="Required for materialization.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required with --execute.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def run_delivery_materialization_execute(
    *,
    repository: DeliveryExecuteRepository | None = None,
    dsn: str | None = None,
    source_projection_run_id: str = DEFAULT_SOURCE_PROJECTION_RUN_ID,
    delivery_materialization_run_id: str = DEFAULT_DELIVERY_MATERIALIZATION_RUN_ID,
    source_action_run_id: str = DEFAULT_SOURCE_ACTION_RUN_ID,
    expected_source_count: int = DEFAULT_EXPECTED_SOURCE_COUNT,
    execute: bool = False,
    user_confirmed: bool = False,
    contract_json_path: str = CONTRACT_JSON_PATH,
    preflight_json_path: str = PREFLIGHT_JSON_PATH,
    rollback_sql_path: str = ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    if not execute:
        return build_gate_blocked_report(
            "missing_execute_flag",
            started_at=started_at,
            source_projection_run_id=source_projection_run_id,
            delivery_materialization_run_id=delivery_materialization_run_id,
            rollback_sql_path=rollback_sql_path,
        )
    if not user_confirmed:
        return build_gate_blocked_report(
            "missing_user_confirmed",
            started_at=started_at,
            source_projection_run_id=source_projection_run_id,
            delivery_materialization_run_id=delivery_materialization_run_id,
            rollback_sql_path=rollback_sql_path,
        )

    artifact_errors = validate_delivery_artifacts(contract_json_path, preflight_json_path, rollback_sql_path)
    if artifact_errors:
        return build_artifact_blocked_report(
            artifact_errors,
            started_at=started_at,
            source_projection_run_id=source_projection_run_id,
            delivery_materialization_run_id=delivery_materialization_run_id,
            rollback_sql_path=rollback_sql_path,
        )
    if repository is None:
        if not dsn:
            return build_gate_blocked_report(
                "missing_dsn",
                started_at=started_at,
                source_projection_run_id=source_projection_run_id,
                delivery_materialization_run_id=delivery_materialization_run_id,
                rollback_sql_path=rollback_sql_path,
            )
        repository = PostgresDeliveryExecuteRepository(dsn, source_action_run_id=source_action_run_id)

    snapshot = repository.fetch_delivery_snapshot(
        source_projection_run_id=source_projection_run_id,
        delivery_materialization_run_id=delivery_materialization_run_id,
    )
    preflight_report = build_delivery_preflight_report(
        snapshot,
        started_at=started_at,
        expected_source_count=expected_source_count,
        rollback_sql_path=rollback_sql_path,
    )
    if preflight_report["quality"]["p0_count"] > 0:
        return preflight_report

    plan = build_delivery_write_plan(snapshot)
    try:
        commit_result = repository.commit_delivery_materialization(plan)
    except Exception as exc:  # pragma: no cover - defensive DB reporting
        report = dict(preflight_report)
        report["result"] = "FAILED"
        report["failure"] = {"error_type": type(exc).__name__, "message": str(exc)}
        report["finished_at"] = utc_now_iso()
        return normalize_jsonable(report)

    report = dict(preflight_report)
    report["result"] = "EXECUTED"
    report["finished_at"] = utc_now_iso()
    report["write_summary"] = {
        "committed": bool(commit_result.get("committed")),
        "write_tables": list(commit_result.get("write_tables") or []),
        "write_counts": dict(commit_result.get("write_counts") or {}),
        "allowed_write_tables_only": set(commit_result.get("write_tables") or []) <= set(ALLOWED_WRITE_TABLES),
    }
    report["side_effects"] = delivery_side_effects(database_write=True, writes_user_notification_queue=True)
    report["allowed_next_gate"] = "N6 delivery materialization post-review"
    return normalize_jsonable(report)


def build_delivery_preflight_report(
    snapshot: DeliveryExecuteSnapshot,
    *,
    started_at: str,
    expected_source_count: int,
    rollback_sql_path: str,
) -> dict[str, Any]:
    quality_items = build_delivery_quality_items(snapshot, expected_source_count=expected_source_count)
    quality_counts = count_quality_severities(quality_items)
    blockers = sorted(
        str(item["gate_code"])
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    )
    warnings = sorted(
        str(item["gate_code"])
        for item in quality_items
        if item.get("severity") == "P1" and item.get("status") == "warning"
    )
    notes = sorted(
        str(item["gate_code"])
        for item in quality_items
        if item.get("severity") == "P2" and item.get("status") == "warning"
    )
    source_count = len(snapshot.source_rows)
    return normalize_jsonable(
        {
            "result": "BLOCKED" if quality_counts["P0"] else "PREFLIGHT_PASS",
            "preflight_result": "PREFLIGHT_BLOCKED" if quality_counts["P0"] else "PREFLIGHT_PASS",
            "stage": "N6-delivery-notification-materialization-execute",
            "mode": "noop_local_preview_materialization",
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "source_projection_run_id": snapshot.source_projection_run_id,
            "delivery_materialization_run_id": snapshot.delivery_materialization_run_id,
            "source_queue": {
                "expected_rows": expected_source_count,
                "actual_rows": source_count,
                "notification_source": SOURCE_NOTIFICATION_SOURCE,
                "queue_status": SOURCE_QUEUE_STATUS,
                "channel": SOURCE_CHANNEL,
                "existing_materialized_rows": snapshot.existing_materialized_count,
            },
            "planned_write_summary": {
                "write_tables": list(ALLOWED_WRITE_TABLES),
                "write_counts": {"user_notification_queue": source_count},
                "notification_source": TARGET_NOTIFICATION_SOURCE,
                "queue_status": TARGET_QUEUE_STATUS,
                "channel": TARGET_CHANNEL,
                "append_only": True,
            },
            "quality": {
                "p0_count": quality_counts["P0"],
                "p1_count": quality_counts["P1"],
                "p2_count": quality_counts["P2"],
                "items": quality_items,
            },
            "blockers": blockers,
            "warnings": warnings,
            "notes": notes,
            "write_summary": {
                "committed": False,
                "write_tables": [],
                "write_counts": {},
                "allowed_write_tables_only": True,
            },
            "side_effects": delivery_side_effects(database_write=False, writes_user_notification_queue=False),
            "n5_outbox_counts": dict(snapshot.n5_outbox_counts),
            "rollback_sql_path": rollback_sql_path,
            "rollback_safe": not quality_counts["P0"],
            "allowed_next_gate": "runtime_control delivery execute final gate review" if not quality_counts["P0"] else "resolve P0 blockers",
        }
    )


def build_delivery_quality_items(snapshot: DeliveryExecuteSnapshot, *, expected_source_count: int) -> list[dict[str, Any]]:
    source_count = len(snapshot.source_rows)
    items = [
        quality_item(
            "P0",
            "passed" if source_count == expected_source_count else "failed",
            "source_queue_count_mismatch",
            "Source queued_only rows must match the reviewed delivery contract baseline",
            expected=str(expected_source_count),
            actual=str(source_count),
        ),
        quality_item(
            "P0",
            "passed" if snapshot.existing_materialized_count == 0 else "failed",
            "delivery_materialization_baseline_not_zero",
            "Same delivery_materialization_run_id must have no existing target rows",
            expected="0",
            actual=str(snapshot.existing_materialized_count),
        ),
        quality_item(
            "P0",
            "passed" if all(row.notification_source == SOURCE_NOTIFICATION_SOURCE for row in snapshot.source_rows) else "failed",
            "source_notification_source_mismatch",
            "Source rows must remain n5_action_blocked",
            expected=SOURCE_NOTIFICATION_SOURCE,
            actual=source_distribution(snapshot.source_rows, "notification_source"),
        ),
        quality_item(
            "P0",
            "passed" if all(row.queue_status == SOURCE_QUEUE_STATUS for row in snapshot.source_rows) else "failed",
            "source_queue_status_mismatch",
            "Source rows must remain queued_only",
            expected=SOURCE_QUEUE_STATUS,
            actual=source_distribution(snapshot.source_rows, "queue_status"),
        ),
        quality_item(
            "P0",
            "passed" if all(row.channel == SOURCE_CHANNEL for row in snapshot.source_rows) else "failed",
            "source_channel_mismatch",
            "Source rows must remain broadcast_queue before no-op preview materialization",
            expected=SOURCE_CHANNEL,
            actual=source_distribution(snapshot.source_rows, "channel"),
        ),
        quality_item(
            "P0",
            "passed" if all(row.title and row.message for row in snapshot.source_rows) else "failed",
            "source_title_or_message_missing",
            "Provider-visible preview rows may only use source title/message after sanitization",
            expected="title and message present",
            actual=str(sum(1 for row in snapshot.source_rows if not row.title or not row.message)),
        ),
        quality_item(
            "P0",
            "passed" if not linked_ref_total(snapshot.forbidden_ref_counts) else "failed",
            "linked_delivery_or_runtime_refs_not_zero",
            "No provider delivery, push, voice, mobile, sim, position, or trade refs may exist before materialization",
            expected="0",
            actual=str(linked_ref_total(snapshot.forbidden_ref_counts)),
        ),
        quality_item(
            "P0",
            "passed" if sanitized_rows_are_clean(snapshot.source_rows, snapshot.delivery_materialization_run_id) else "failed",
            "sanitized_payload_contains_forbidden_keys",
            "Provider-visible payload must exclude trace, source payload, N5 outbox, and action-run internals",
            expected="no forbidden keys",
            actual="clean" if sanitized_rows_are_clean(snapshot.source_rows, snapshot.delivery_materialization_run_id) else "forbidden keys found",
        ),
        quality_item(
            "P0",
            "passed",
            "allowed_write_scope_only",
            "Write plan is limited to append-only user_notification_queue preview rows",
            expected="user_notification_queue",
            actual="user_notification_queue",
        ),
        quality_item(
            "P0",
            "passed",
            "forbidden_side_effect_plan_all_false",
            "No provider delivery, push, voice, mobile, sim, position, trade, worker, or N5 outbox mutation is planned",
            expected="all false",
            actual="all false",
        ),
    ]
    source_trace_count = sum(1 for row in snapshot.source_rows if row.trace_json)
    source_internal_payload_count = sum(1 for row in snapshot.source_rows if provider_payload_contains_forbidden_keys(row.notification_payload_json))
    items.extend(
        [
            quality_item(
                "P1",
                "warning" if source_trace_count else "passed",
                "source_queue_trace_json_present",
                "Source queue rows contain internal trace_json; execute sanitizes it out of provider-visible payload",
                expected="sanitized target payload",
                actual=str(source_trace_count),
            ),
            quality_item(
                "P1",
                "warning" if source_internal_payload_count else "passed",
                "source_payload_internal_source_outbox_id_present",
                "Source queue payload contains internal N5/source fields; execute sanitizes target payload",
                expected="sanitized target payload",
                actual=str(source_internal_payload_count),
            ),
            quality_item(
                "P2",
                "warning",
                "noop_provider_only",
                "Delivery provider is a local no-op preview; no external send occurs",
                expected=NOOP_PROVIDER,
                actual=NOOP_PROVIDER,
            ),
            quality_item(
                "P2",
                "warning",
                "retry_disabled_until_real_provider_contract",
                "Retry and failure state are encoded as no-op preview metadata only",
                expected="max_attempts=0",
                actual="max_attempts=0",
            ),
            quality_item(
                "P2",
                "warning",
                "delivery_schema_uses_existing_user_notification_queue",
                "MVP materializes preview rows in existing user_notification_queue",
                expected="user_notification_queue",
                actual="user_notification_queue",
            ),
        ]
    )
    return items


def build_delivery_write_plan(snapshot: DeliveryExecuteSnapshot) -> DeliveryWritePlan:
    notification_rows = [build_materialized_notification_row(row, snapshot.delivery_materialization_run_id) for row in snapshot.source_rows]
    return DeliveryWritePlan(
        source_projection_run_id=snapshot.source_projection_run_id,
        delivery_materialization_run_id=snapshot.delivery_materialization_run_id,
        write_tables=ALLOWED_WRITE_TABLES,
        write_counts={"user_notification_queue": len(notification_rows)},
        notification_rows=notification_rows,
    )


def build_materialized_notification_row(row: SourceNotificationRow, delivery_materialization_run_id: str) -> dict[str, Any]:
    return {
        "user_id": row.user_id,
        "user_projection_run_id": row.user_projection_run_id,
        "user_signal_projection_id": row.user_signal_projection_id,
        "user_signal_card_id": row.user_signal_card_id,
        "notification_source": TARGET_NOTIFICATION_SOURCE,
        "queue_status": TARGET_QUEUE_STATUS,
        "channel": TARGET_CHANNEL,
        "title": row.title,
        "message": row.message,
        "priority": row.priority,
        "source_event_id": row.source_event_id,
        "source_action_run_id": row.source_action_run_id,
        "source_action_event_id": row.source_action_event_id,
        "source_action_event_type": row.source_action_event_type,
        "action_state": row.action_state,
        "action_mark": row.action_mark,
        "condition_key": row.condition_key,
        "original_condition_key": row.original_condition_key,
        "trace_json": None,
        "projection_policy": PROJECTION_POLICY,
        "asset_kind": row.asset_kind,
        "identity_key": row.identity_key,
        "notification_payload_json": build_sanitized_payload(row, delivery_materialization_run_id),
    }


def build_sanitized_payload(row: SourceNotificationRow, delivery_materialization_run_id: str) -> dict[str, Any]:
    payload = {
        "schema_version": "n6_delivery_noop_preview_v1",
        "delivery_materialization_run_id": delivery_materialization_run_id,
        "dedup_key": delivery_dedup_key(delivery_materialization_run_id, row),
        "provider": NOOP_PROVIDER,
        "channel": TARGET_CHANNEL,
        "policy": USER_POLICY,
        "asset_kind": row.asset_kind,
        "identity_key": row.identity_key,
        "action_state": row.action_state,
        "display_state": display_state_for_action_state(row.action_state),
        "retry": {
            "policy": "noop_provider_no_retry",
            "max_attempts": 0,
            "attempt_count": 0,
            "next_retry_at": None,
        },
        "failure": {
            "status": "not_attempted",
            "reason": None,
        },
    }
    return {key: payload[key] for key in payload if key in ALLOWED_PROVIDER_PAYLOAD_KEYS}


def delivery_dedup_key(delivery_materialization_run_id: str, row: SourceNotificationRow) -> str:
    raw = json.dumps(
        [delivery_materialization_run_id, row.user_id, row.user_notification_queue_id, NOOP_PROVIDER],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def display_state_for_action_state(action_state: str | None) -> str:
    if action_state == "blocked":
        return "blocked_unconfirmed"
    if action_state == "executed":
        return "action_confirmed"
    if action_state == "eligible":
        return "candidate"
    if action_state == "skipped":
        return "skipped"
    return "informational"


def validate_delivery_artifacts(contract_json_path: str, preflight_json_path: str, rollback_sql_path: str) -> list[str]:
    errors: list[str] = []
    for path, code, valid_statuses in (
        (contract_json_path, "missing_or_invalid_contract_json", ALLOWED_CONTRACT_STATUSES),
        (preflight_json_path, "missing_or_invalid_preflight_json", ALLOWED_PREFLIGHT_STATUSES),
    ):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            status = payload.get("status") or payload.get("result")
            if status not in valid_statuses:
                errors.append(f"{code}:status_not_allowed")
        except Exception:
            errors.append(code)
    rollback_path = Path(rollback_sql_path)
    if not rollback_path.exists():
        errors.append("missing_rollback_sql")
    else:
        rollback_sql = rollback_path.read_text(encoding="utf-8")
        upper_sql = rollback_sql.upper()
        first_raise = upper_sql.find("RAISE EXCEPTION")
        first_delete = upper_sql.find("DELETE FROM")
        if first_raise < 0 or first_delete < 0 or first_raise > first_delete:
            errors.append("rollback_missing_hard_fail_before_delete")
    return errors


def build_gate_blocked_report(
    blocker: str,
    *,
    started_at: str,
    source_projection_run_id: str,
    delivery_materialization_run_id: str,
    rollback_sql_path: str,
) -> dict[str, Any]:
    item = quality_item(
        "P0",
        "failed",
        blocker,
        "N6 delivery materialization execute gate was not satisfied",
        expected="--execute --user-confirmed and valid artifacts",
        actual=blocker,
    )
    return normalize_jsonable(
        {
            "result": "BLOCKED",
            "preflight_result": "NOT_RUN",
            "stage": "N6-delivery-notification-materialization-execute",
            "mode": "noop_local_preview_materialization",
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "source_projection_run_id": source_projection_run_id,
            "delivery_materialization_run_id": delivery_materialization_run_id,
            "quality": {"p0_count": 1, "p1_count": 0, "p2_count": 0, "items": [item]},
            "blockers": [blocker],
            "warnings": [],
            "notes": [],
            "write_summary": {
                "committed": False,
                "write_tables": [],
                "write_counts": {},
                "allowed_write_tables_only": True,
            },
            "side_effects": delivery_side_effects(database_write=False, writes_user_notification_queue=False),
            "rollback_sql_path": rollback_sql_path,
        }
    )


def build_artifact_blocked_report(
    errors: Sequence[str],
    *,
    started_at: str,
    source_projection_run_id: str,
    delivery_materialization_run_id: str,
    rollback_sql_path: str,
) -> dict[str, Any]:
    report = build_gate_blocked_report(
        "artifact_validation_failed",
        started_at=started_at,
        source_projection_run_id=source_projection_run_id,
        delivery_materialization_run_id=delivery_materialization_run_id,
        rollback_sql_path=rollback_sql_path,
    )
    report["blockers"] = list(errors)
    report["quality"] = {
        "p0_count": len(errors),
        "p1_count": 0,
        "p2_count": 0,
        "items": [
            quality_item(
                "P0",
                "failed",
                error,
                "Required delivery contract/preflight/rollback artifact is missing or invalid",
                expected="valid artifact",
                actual=error,
            )
            for error in errors
        ],
    }
    return report


def delivery_side_effects(*, database_write: bool, writes_user_notification_queue: bool) -> dict[str, bool]:
    return {
        "database_write": database_write,
        "writes_user_notification_queue": writes_user_notification_queue,
        "n5_outbox_consumed": False,
        "n5_outbox_status_updated": False,
        "n5_inbox_checkpoint_written": False,
        "worker_started": False,
        "provider_delivery": False,
        "push": False,
        "voice": False,
        "mobile": False,
        "sim": False,
        "position": False,
        "real_trade": False,
        "write_n1_to_n5": False,
    }


def fetch_source_notification_rows(cur: psycopg.Cursor[dict[str, Any]], source_projection_run_id: str) -> list[SourceNotificationRow]:
    columns = (
        "user_notification_queue_id",
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
        f"""
        SELECT {', '.join(columns)}
          FROM user_notification_queue
         WHERE user_projection_run_id = %s
           AND notification_source = %s
           AND queue_status = %s
         ORDER BY priority NULLS LAST, queued_at, user_notification_queue_id
        """,
        (source_projection_run_id, SOURCE_NOTIFICATION_SOURCE, SOURCE_QUEUE_STATUS),
    )
    return [
        SourceNotificationRow(
            **{
                **dict(row),
                "trace_json": row.get("trace_json") if isinstance(row.get("trace_json"), dict) else None,
                "notification_payload_json": row.get("notification_payload_json") if isinstance(row.get("notification_payload_json"), dict) else {},
            }
        )
        for row in cur.fetchall()
    ]


def count_existing_materialized_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    source_projection_run_id: str,
    delivery_materialization_run_id: str,
) -> int:
    cur.execute(
        """
        SELECT count(*)::int AS count
          FROM user_notification_queue
         WHERE user_projection_run_id = %s
           AND notification_source = %s
           AND notification_payload_json->>'delivery_materialization_run_id' = %s
        """,
        (source_projection_run_id, TARGET_NOTIFICATION_SOURCE, delivery_materialization_run_id),
    )
    return int(cur.fetchone()["count"])


def fetch_n5_outbox_counts(cur: psycopg.Cursor[dict[str, Any]], source_action_run_id: str) -> dict[str, int]:
    cur.execute(
        """
        SELECT event_type, status, count(*)::int AS count
          FROM common_event_outbox
         WHERE source_layer = 'N5_action'
           AND source_run_id = %s
           AND event_type IN ('ActionBlocked', 'ActionEligible', 'ActionExecuted', 'ActionSkipped')
         GROUP BY event_type, status
        """,
        (source_action_run_id,),
    )
    return {f"{row['event_type']}:{row['status']}": int(row["count"]) for row in cur.fetchall()}


def fetch_forbidden_ref_counts(cur: psycopg.Cursor[dict[str, Any]], delivery_materialization_run_id: str) -> dict[str, int]:
    guards = {
        "provider_delivery_attempt": ("common_event_delivery_attempt",),
        "notification_delivery": ("user_notification_delivery",),
        "voice": ("user_voice_delivery", "user_voice_queue", "user_voice_delivery_log"),
        "mobile": ("user_mobile_delivery", "user_mobile_queue", "user_device_ack", "user_notification_delivery"),
        "position": ("user_position_projection", "user_position_state"),
        "sim": ("user_sim_order", "user_sim_trade", "user_sim_position"),
    }
    counts: dict[str, int] = {}
    for category, tables in guards.items():
        counts[category] = sum(optional_link_count(cur, table, delivery_materialization_run_id) for table in tables)
    counts["real_trade"] = 0
    return counts


def optional_link_count(cur: psycopg.Cursor[dict[str, Any]], table_name: str, delivery_materialization_run_id: str) -> int:
    cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
    if cur.fetchone()["regclass"] is None:
        return 0
    predicates: list[str] = []
    for column in ("delivery_materialization_run_id", "delivery_run_id"):
        if column_exists(cur, table_name, column):
            predicates.append(f"{column} = %s")
    if column_exists(cur, table_name, "raw_json"):
        predicates.append("raw_json::text LIKE %s")
    if not predicates:
        return 0
    params = [delivery_materialization_run_id for predicate in predicates if "LIKE" not in predicate]
    params += [f"%{delivery_materialization_run_id}%" for predicate in predicates if "LIKE" in predicate]
    cur.execute(f"SELECT count(*)::int AS count FROM {table_name} WHERE {' OR '.join(predicates)}", params)
    return int(cur.fetchone()["count"])


def column_exists(cur: psycopg.Cursor[dict[str, Any]], table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = %s
           AND column_name = %s
         LIMIT 1
        """,
        (table_name, column_name),
    )
    return cur.fetchone() is not None


def insert_notification_preview(cur: psycopg.Cursor[dict[str, Any]], row: Mapping[str, Any]) -> None:
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
    if value is None:
        return None
    if column.endswith("_json"):
        return Jsonb(normalize_jsonable(value))
    return value


def linked_ref_total(counts: Mapping[str, int]) -> int:
    return sum(int(value or 0) for value in counts.values())


def source_distribution(rows: Sequence[SourceNotificationRow], attr: str) -> str:
    values: dict[str, int] = {}
    for row in rows:
        value = str(getattr(row, attr))
        values[value] = values.get(value, 0) + 1
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def provider_payload_contains_forbidden_keys(payload: Mapping[str, Any]) -> bool:
    return bool(set(payload.keys()) & FORBIDDEN_PROVIDER_PAYLOAD_KEYS)


def sanitized_rows_are_clean(rows: Sequence[SourceNotificationRow], delivery_materialization_run_id: str) -> bool:
    for row in rows:
        payload = build_sanitized_payload(row, delivery_materialization_run_id)
        if set(payload.keys()) - ALLOWED_PROVIDER_PAYLOAD_KEYS:
            return False
        if set(payload.keys()) & FORBIDDEN_PROVIDER_PAYLOAD_KEYS:
            return False
    return True


def format_summary(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    write_summary = report.get("write_summary") or {}
    source_queue = report.get("source_queue") or {}
    return "\n".join(
        [
            "N6 delivery notification materialization execute",
            f"  result={report.get('result')}",
            f"  preflight_result={report.get('preflight_result')}",
            f"  source_projection_run_id={report.get('source_projection_run_id')}",
            f"  delivery_materialization_run_id={report.get('delivery_materialization_run_id')}",
            f"  source_rows={source_queue.get('actual_rows')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
            f"  blockers={report.get('blockers') or []}",
            f"  committed={str(write_summary.get('committed')).lower()} write_tables={write_summary.get('write_tables') or []}",
            f"  provider_delivery={str((report.get('side_effects') or {}).get('provider_delivery')).lower()} push={str((report.get('side_effects') or {}).get('push')).lower()}",
        ]
    )
