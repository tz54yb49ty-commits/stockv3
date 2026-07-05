"""N5 historical metadata repair runner.

This runner is scoped to metadata-only payload repair for an existing N5
action run. It never starts workers or enters N6. Database writes are gated by
``execute`` and ``user_confirmed`` and are limited to JSON metadata keys in
``common_action_event.payload_json`` and scoped N5 ``common_event_outbox``.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import normalize_mapping
from ashare_v3.action.query_audit_phase2 import audited_n5_metadata_repair_connect


DEFAULT_FULL_METRIC_UNION_REPAIR_CONTRACT_PATH = (
    "docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_CONTRACT.json"
)
DEFAULT_FULL_METRIC_UNION_REPAIR_PREFLIGHT_PATH = (
    "docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_PREFLIGHT.json"
)
DEFAULT_FULL_METRIC_UNION_REPAIR_DRY_RUN_PATH = (
    "docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_DRY_RUN.json"
)
DEFAULT_FULL_METRIC_UNION_REPAIR_PAYLOAD_PATH = (
    "docs/N5_full_metric_union_historical_metadata_repair_payload.json"
)
DEFAULT_FULL_METRIC_UNION_REPAIR_ROLLBACK_SQL_PATH = (
    "sql/N5_full_metric_union_historical_metadata_repair_20260605_rollback.sql"
)
DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_JSON_PATH = (
    "docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_REPORT.json"
)
DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_MD_PATH = (
    "docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_REPORT.md"
)
DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_CONTRACT_JSON_PATH = (
    "docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_CONTRACT.json"
)
DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_CONTRACT_MD_PATH = (
    "docs/N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_CONTRACT.md"
)

ALLOWED_METADATA_REPAIR_KEYS = (
    "blocked_reason",
    "action_confirmation_metric_run_refs",
    "metric_union_policy_version",
    "metric_union_source_runs",
    "metric_coverage_status",
    "metric_missing_resolved",
    "repair_trace",
)
FORBIDDEN_METADATA_REPAIR_KEYS = (
    "event_type",
    "action_state",
    "confirmation_status",
    "action_mark",
    "event_id",
    "source_trigger_event_id",
    "action_run_id",
    "source_run_id",
    "status",
    "delivery_status",
)
N5_SOURCE_LAYER = "N5_action"


class MetadataRepairError(RuntimeError):
    """Raised when the N5 metadata repair runner is blocked."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")


def write_text(path: str | Path, text: str) -> None:
    Path(path).write_text(text)


def merge_metadata_repair_payload(
    current_payload: Mapping[str, Any] | None,
    metadata_patch: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge only allowed metadata repair keys into an existing payload."""

    output = dict(current_payload or {})
    for key in ALLOWED_METADATA_REPAIR_KEYS:
        if key in metadata_patch:
            output[key] = metadata_patch[key]
    return output


def validate_metadata_repair_payload_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(payload.get("rows") or [])
    payload_scope = payload.get("payload_scope") or {}
    declared_rows = int(payload_scope.get("rows") or len(rows))
    if declared_rows != len(rows):
        raise ValueError(f"payload row count mismatch: declared={declared_rows} actual={len(rows)}")
    allowed = set(ALLOWED_METADATA_REPAIR_KEYS)
    for index, row in enumerate(rows):
        patch = row.get("metadata_patch")
        if not isinstance(patch, Mapping):
            raise ValueError(f"payload row {index} missing metadata_patch")
        forbidden = sorted(set(patch) - allowed)
        if forbidden:
            raise ValueError(f"payload row {index} contains forbidden metadata keys: {forbidden}")
        action_event = row.get("common_action_event") or {}
        if action_event.get("current_event_type") != action_event.get("planned_event_type"):
            raise ValueError(f"payload row {index} would change event_type")
        if action_event.get("current_action_state") != action_event.get("planned_action_state"):
            raise ValueError(f"payload row {index} would change action_state")
        if action_event.get("current_confirmation_status") != action_event.get("planned_confirmation_status"):
            raise ValueError(f"payload row {index} would change confirmation_status")
        if action_event.get("current_action_mark") != action_event.get("planned_action_mark"):
            raise ValueError(f"payload row {index} would change action_mark")
    return {
        "row_count": len(rows),
        "allowed_metadata_keys_only": True,
        "status_invariant": True,
    }


def validate_metadata_repair_artifacts(
    *,
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    payload_validation = validate_metadata_repair_payload_artifact(payload)
    action_run_id = str(contract.get("action_run_id") or "")
    source_trigger_run_id = str(contract.get("source_trigger_run_id") or "")
    for name, artifact in (
        ("preflight", preflight),
        ("dry_run", dry_run),
        ("payload", payload),
    ):
        if str(artifact.get("action_run_id") or "") != action_run_id:
            raise ValueError(f"{name} action_run_id does not match contract")
        if str(artifact.get("source_trigger_run_id") or "") != source_trigger_run_id:
            raise ValueError(f"{name} source_trigger_run_id does not match contract")
    if contract.get("result") != "CONTRACT_PASS":
        raise ValueError("contract is not CONTRACT_PASS")
    if preflight.get("preflight_result") != "PREFLIGHT_PASS":
        raise ValueError("preflight is not PREFLIGHT_PASS")
    dry_run_quality = dry_run.get("quality") or {}
    if int(dry_run_quality.get("p0_count") or 0) != 0:
        raise ValueError("dry-run has P0 blockers")
    comparison = contract.get("expected_old_new_comparison") or {}
    status_change_fields = (
        "event_type_changes",
        "action_state_changes",
        "confirmation_status_changes",
        "action_mark_changes",
    )
    for field in status_change_fields:
        if int(comparison.get(field) or 0) != 0:
            raise ValueError(f"contract would change immutable status field: {field}")
    return {
        "artifact_consistency": "passed",
        "action_run_id": action_run_id,
        "source_trigger_run_id": source_trigger_run_id,
        "payload_validation": payload_validation,
    }


def build_full_metric_union_metadata_repair_command(
    *,
    dsn: str,
    contract_path: str,
    preflight_path: str,
    dry_run_path: str,
    payload_path: str,
    rollback_sql_path: str,
    json_report_path: str,
    markdown_report_path: str,
) -> list[str]:
    return [
        "PYTHONPATH=src:scripts",
        "python3",
        "scripts/run_n5_full_metric_union_metadata_repair.py",
        "--dsn",
        dsn,
        "--contract-path",
        contract_path,
        "--preflight-path",
        preflight_path,
        "--dry-run-path",
        dry_run_path,
        "--payload-path",
        payload_path,
        "--rollback-sql-path",
        rollback_sql_path,
        "--json-report-path",
        json_report_path,
        "--markdown-report-path",
        markdown_report_path,
        "--execute",
        "--user-confirmed",
    ]


def build_execute_command_contract(*, dsn: str) -> dict[str, Any]:
    command = build_full_metric_union_metadata_repair_command(
        dsn=dsn,
        contract_path=DEFAULT_FULL_METRIC_UNION_REPAIR_CONTRACT_PATH,
        preflight_path=DEFAULT_FULL_METRIC_UNION_REPAIR_PREFLIGHT_PATH,
        dry_run_path=DEFAULT_FULL_METRIC_UNION_REPAIR_DRY_RUN_PATH,
        payload_path=DEFAULT_FULL_METRIC_UNION_REPAIR_PAYLOAD_PATH,
        rollback_sql_path=DEFAULT_FULL_METRIC_UNION_REPAIR_ROLLBACK_SQL_PATH,
        json_report_path=DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_JSON_PATH,
        markdown_report_path=DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_MD_PATH,
    )
    return {
        "result": "CONTRACT_PASS",
        "layer_role": "N5_action",
        "stage": "N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE_COMMAND_CONTRACT",
        "execute_authorized_now": False,
        "execute_command": " ".join(command),
        "execute_command_argv": command,
        "requires": ["--execute", "--user-confirmed"],
        "artifact_inputs": {
            "contract": DEFAULT_FULL_METRIC_UNION_REPAIR_CONTRACT_PATH,
            "preflight": DEFAULT_FULL_METRIC_UNION_REPAIR_PREFLIGHT_PATH,
            "dry_run": DEFAULT_FULL_METRIC_UNION_REPAIR_DRY_RUN_PATH,
            "payload": DEFAULT_FULL_METRIC_UNION_REPAIR_PAYLOAD_PATH,
            "rollback_sql": DEFAULT_FULL_METRIC_UNION_REPAIR_ROLLBACK_SQL_PATH,
        },
        "report_outputs": {
            "json": DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_JSON_PATH,
            "markdown": DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_MD_PATH,
        },
        "write_scope": {
            "allowed_tables": ["common_action_event", "common_event_outbox"],
            "allowed_payload_keys": list(ALLOWED_METADATA_REPAIR_KEYS),
            "forbidden_fields": list(FORBIDDEN_METADATA_REPAIR_KEYS),
        },
        "forbidden_scope": forbidden_scope(),
    }


def forbidden_scope() -> dict[str, bool]:
    return {
        "consume_outbox": False,
        "update_outbox_status": False,
        "write_inbox_checkpoint": False,
        "modify_n4": False,
        "modify_n3": False,
        "enter_n6": False,
        "delivery_push_voice_mobile": False,
        "sim_position_pnl_real_trade": False,
        "proposal_order_trade": False,
        "worker_started": False,
    }


def run_full_metric_union_metadata_repair_from_paths(
    *,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
    contract_path: str = DEFAULT_FULL_METRIC_UNION_REPAIR_CONTRACT_PATH,
    preflight_path: str = DEFAULT_FULL_METRIC_UNION_REPAIR_PREFLIGHT_PATH,
    dry_run_path: str = DEFAULT_FULL_METRIC_UNION_REPAIR_DRY_RUN_PATH,
    payload_path: str = DEFAULT_FULL_METRIC_UNION_REPAIR_PAYLOAD_PATH,
    rollback_sql_path: str = DEFAULT_FULL_METRIC_UNION_REPAIR_ROLLBACK_SQL_PATH,
    json_report_path: str = DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_JSON_PATH,
    markdown_report_path: str = DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_MD_PATH,
) -> dict[str, Any]:
    report = run_full_metric_union_metadata_repair_from_artifacts(
        dsn=dsn,
        execute=execute,
        user_confirmed=user_confirmed,
        contract=load_json(contract_path),
        preflight=load_json(preflight_path),
        dry_run=load_json(dry_run_path),
        payload=load_json(payload_path),
        rollback_sql_path=rollback_sql_path,
        artifact_paths={
            "contract": contract_path,
            "preflight": preflight_path,
            "dry_run": dry_run_path,
            "payload": payload_path,
        },
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_metadata_repair_report(report))
    return report


def run_full_metric_union_metadata_repair_from_artifacts(
    *,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    payload: Mapping[str, Any],
    rollback_sql_path: str,
    artifact_paths: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    blockers: list[str] = []
    artifact_validation: dict[str, Any] | None = None
    try:
        artifact_validation = validate_metadata_repair_artifacts(
            contract=contract,
            preflight=preflight,
            dry_run=dry_run,
            payload=payload,
        )
    except ValueError as exc:
        blockers.append(f"artifact_validation_failed:{exc}")
    if not execute or not user_confirmed:
        blockers.append("n5_metadata_repair_double_confirmation")
    if not Path(rollback_sql_path).exists():
        blockers.append("rollback_sql_missing")

    allow_execute = not blockers
    updated_rows = {
        "common_action_event": 0,
        "common_event_outbox": 0,
    }
    boundary_scan: dict[str, Any] = {}
    dsn_safety: dict[str, Any] = {}
    if allow_execute:
        execution = execute_metadata_repair_transaction(
            dsn=dsn,
            contract=contract,
            payload=payload,
        )
        updated_rows = execution["updated_rows"]
        boundary_scan = execution["boundary_scan"]
        dsn_safety = execution["dsn_safety"]

    quality = {
        "p0_count": len(blockers),
        "p1_count": 0,
        "p2_count": 0,
        "items": [
            {
                "severity": "P0",
                "status": "failed",
                "gate_code": blocker,
                "expected_value": "not present",
                "actual_value": blocker,
            }
            for blocker in blockers
        ],
    }
    report = {
        "result": "EXECUTED" if allow_execute else "BLOCKED",
        "layer_role": "N5_action",
        "stage": "N5_FULL_METRIC_UNION_HISTORICAL_METADATA_REPAIR_EXECUTE",
        "execute": execute,
        "user_confirmed": user_confirmed,
        "allow_execute": allow_execute,
        "blockers": blockers,
        "action_run_id": contract.get("action_run_id"),
        "source_trigger_run_id": contract.get("source_trigger_run_id"),
        "repair_run_id": contract.get("repair_run_id"),
        "metric_union_policy_version": contract.get("metric_union_policy_version"),
        "artifact_paths": dict(artifact_paths or {}),
        "rollback_sql_path": rollback_sql_path,
        "artifact_validation": artifact_validation or {},
        "planned_update_scope": {
            "target_tables": ["common_action_event", "common_event_outbox"],
            "payload_rows": int((payload.get("payload_scope") or {}).get("rows") or len(payload.get("rows") or [])),
            "allowed_metadata_keys": list(ALLOWED_METADATA_REPAIR_KEYS),
            "forbidden_fields": list(FORBIDDEN_METADATA_REPAIR_KEYS),
        },
        "updated_rows": updated_rows,
        "boundary_scan": boundary_scan,
        "dsn_safety": dsn_safety,
        "quality": quality,
        "side_effects": {
            "writes_performed": allow_execute,
            "common_action_event_updated": allow_execute,
            "common_event_outbox_updated": allow_execute,
            "outbox_status_updated": False,
            "outbox_consumed": False,
            "inbox_checkpoint_updated": False,
            "n4_facts_modified": False,
            "n3_metric_modified": False,
            "n6_projection_card_modified": False,
            "worker_started": False,
            "delivery_push_voice_mobile": False,
            "sim_position_pnl_real_trade": False,
            "proposal_order_trade": False,
        },
        "started_at": started_at,
        "finished_at": utc_now_iso(),
    }
    return report


def execute_metadata_repair_transaction(
    *,
    dsn: str,
    contract: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    action_run_id = str(contract.get("action_run_id") or "")
    policy_version = str(contract.get("metric_union_policy_version") or "")
    rows = list(payload.get("rows") or [])
    with audited_n5_metadata_repair_connect(
        dsn,
        stage_id="n5_full_metric_union_metadata_repair_transaction",
        source_run_id=action_run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            dsn_safety = fetch_dsn_safety(cur)
            run_hard_fail_guards(cur, action_run_id=action_run_id, policy_version=policy_version)
            updated = Counter()
            for row in rows:
                patch = row["metadata_patch"]
                event_row = row["common_action_event"]
                outbox_row = row["n5_common_event_outbox"]
                action_event_row_id = event_row["action_event_row_id"]
                outbox_id = outbox_row["outbox_id"]
                cur.execute(
                    """
                    SELECT payload_json
                    FROM common_action_event
                    WHERE run_id = %s
                      AND action_event_row_id = %s
                    FOR UPDATE
                    """,
                    (action_run_id, action_event_row_id),
                )
                current_event = cur.fetchone()
                if current_event is None:
                    raise MetadataRepairError(f"missing common_action_event row {action_event_row_id}")
                merged_event_payload = merge_metadata_repair_payload(current_event["payload_json"], patch)
                cur.execute(
                    """
                    UPDATE common_action_event
                    SET payload_json = %s
                    WHERE run_id = %s
                      AND action_event_row_id = %s
                    """,
                    (Jsonb(merged_event_payload), action_run_id, action_event_row_id),
                )
                updated["common_action_event"] += cur.rowcount

                cur.execute(
                    """
                    SELECT payload_json
                    FROM common_event_outbox
                    WHERE source_layer = %s
                      AND source_run_id = %s
                      AND outbox_id = %s
                    FOR UPDATE
                    """,
                    (N5_SOURCE_LAYER, action_run_id, outbox_id),
                )
                current_outbox = cur.fetchone()
                if current_outbox is None:
                    raise MetadataRepairError(f"missing common_event_outbox row {outbox_id}")
                merged_outbox_payload = merge_metadata_repair_payload(current_outbox["payload_json"], patch)
                cur.execute(
                    """
                    UPDATE common_event_outbox
                    SET payload_json = %s
                    WHERE source_layer = %s
                      AND source_run_id = %s
                      AND outbox_id = %s
                    """,
                    (Jsonb(merged_outbox_payload), N5_SOURCE_LAYER, action_run_id, outbox_id),
                )
                updated["common_event_outbox"] += cur.rowcount
            boundary = fetch_metadata_repair_boundary_scan(cur, action_run_id=action_run_id)
        conn.commit()
    return {
        "updated_rows": {
            "common_action_event": int(updated["common_action_event"]),
            "common_event_outbox": int(updated["common_event_outbox"]),
        },
        "boundary_scan": boundary,
        "dsn_safety": dsn_safety,
    }


def fetch_dsn_safety(cur: Any) -> dict[str, Any]:
    cur.execute(
        """
        SELECT current_database() AS dbname,
               current_user AS username,
               inet_server_addr()::text AS host,
               inet_server_port() AS port
        """
    )
    return normalize_mapping(cur.fetchone())


def run_hard_fail_guards(cur: Any, *, action_run_id: str, policy_version: str) -> None:
    guards = fetch_metadata_repair_boundary_scan(cur, action_run_id=action_run_id)
    outbox_status = guards.get("n5_outbox_status") or []
    delivered = sum(int(row.get("row_count") or 0) for row in outbox_status if row.get("status") in {"delivered", "delivering"})
    downstream = guards.get("n5_downstream_refs") or {}
    if delivered:
        raise MetadataRepairError(f"N5 outbox delivered/delivering rows exist: {delivered}")
    if any(int(value or 0) for value in downstream.values()):
        raise MetadataRepairError(f"N5 downstream refs exist: {downstream}")
    if policy_version:
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM user_signal_projection WHERE source_action_run_id = %s AND COALESCE(source_payload_json::text, '') LIKE '%%' || %s || '%%') AS user_signal_projection,
              (SELECT count(*) FROM user_signal_card WHERE source_action_run_id = %s AND COALESCE(card_payload_json::text, '') LIKE '%%' || %s || '%%') AS user_signal_card,
              (SELECT count(*) FROM user_notification_queue WHERE source_action_run_id = %s AND COALESCE(notification_payload_json::text, '') LIKE '%%' || %s || '%%') AS user_notification_queue
            """,
            (action_run_id, policy_version, action_run_id, policy_version, action_run_id, policy_version),
        )
        refs = normalize_mapping(cur.fetchone())
        if any(int(value or 0) for value in refs.values()):
            raise MetadataRepairError(f"N6 refs from this metadata repair already exist: {refs}")


def fetch_metadata_repair_boundary_scan(cur: Any, *, action_run_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT event_type, status, count(*) AS row_count
        FROM common_event_outbox
        WHERE source_layer = %s
          AND source_run_id = %s
        GROUP BY event_type, status
        ORDER BY event_type, status
        """,
        (N5_SOURCE_LAYER, action_run_id),
    )
    n5_outbox_status = [normalize_mapping(row) for row in cur.fetchall()]
    cur.execute(
        """
        WITH scoped AS (
          SELECT event_id, partition_key
          FROM common_event_outbox
          WHERE source_layer = %s
            AND source_run_id = %s
        )
        SELECT
          (SELECT count(*) FROM common_event_inbox WHERE source_layer = %s AND source_run_id = %s) AS inbox,
          (SELECT count(*) FROM common_event_consumer_checkpoint WHERE source_layer = %s AND partition_key IN (SELECT partition_key FROM scoped)) AS checkpoint,
          (SELECT count(*) FROM common_event_delivery_attempt WHERE event_id IN (SELECT event_id FROM scoped)) AS delivery_attempt
        """,
        (N5_SOURCE_LAYER, action_run_id, N5_SOURCE_LAYER, action_run_id, N5_SOURCE_LAYER),
    )
    downstream = normalize_mapping(cur.fetchone())
    return {
        "n5_outbox_status": n5_outbox_status,
        "n5_downstream_refs": downstream,
    }


def format_metadata_repair_report(report: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N5 Full Metric Union Historical Metadata Repair Execute Report",
            "",
            f"Status: {report.get('result')}",
            "",
            "```text",
            f"action_run_id={report.get('action_run_id')}",
            f"source_trigger_run_id={report.get('source_trigger_run_id')}",
            f"execute={report.get('execute')} user_confirmed={report.get('user_confirmed')}",
            f"allow_execute={report.get('allow_execute')}",
            f"blockers={report.get('blockers')}",
            f"updated_rows={report.get('updated_rows')}",
            f"P0/P1/P2={report.get('quality', {}).get('p0_count')}/{report.get('quality', {}).get('p1_count')}/{report.get('quality', {}).get('p2_count')}",
            "forbidden_scope: N4/N3/N6 untouched, outbox status not updated, worker not started",
            "```",
        ]
    )
