"""N4 C3 replay audit-only preflight and run-once executor.

This module materializes reviewed C3 replay diffs as N4 audit facts only. The
preflight path is read-only; the execute path is gated by two explicit flags and
does not consume C3 outbox rows or emit standard N4 outbox events.
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

from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item
from ashare_v3.trigger.c3_replay_plan import (
    DEFAULT_ALLOWED_C3_RUN_ID,
    DEFAULT_C2B_RUN_ID,
    DEFAULT_CONTEXT_RUN_ID,
    DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
    DEFAULT_N5_ACTION_EXECUTE_RUN_ID,
    DEFAULT_REPLAY_RUN_ID,
    REPLAY_CLASSIFICATIONS,
    build_c3_replay_dry_run_report_from_rows,
    build_replay_context_candidates,
    build_replay_evaluations,
    fetch_c3_outbox_rows,
    fetch_closed_signal_enrichment_rows,
    fetch_closed_summary_rows,
    fetch_projection_match_rows,
    fetch_projection_trace_only_counts,
    fetch_trigger_run,
)
from ashare_v3.trigger.projection_matcher import DEFAULT_PROJECTION_RUN_ID, fetch_context_rows
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect, audited_n4_trigger_connect


DEFAULT_CONSUMER_NAME = "n4_c3_replay_audit_execute_v1"
DEFAULT_JSON_REPORT_PATH = "docs/N4_C3_replay_audit_execute_preflight.json"
DEFAULT_MD_REPORT_PATH = "docs/N4_C3_REPLAY_AUDIT_EXECUTE_PREFLIGHT.md"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N4_C3_replay_audit_business_rollback.sql"

AUDIT_TABLES = (
    "stock_trigger_replay_audit",
    "index_trigger_replay_audit",
    "board_trigger_replay_audit",
)
ALLOWED_WRITE_TABLES = (
    "common_trigger_run",
    "common_trigger_quality_item",
    *AUDIT_TABLES,
)
FORBIDDEN_WRITE_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_trigger_match",
    "common_trigger_state",
    "N3 facts/outbox",
    "N5 action facts/events/outbox",
    "N6 user projection",
    "action/user/voice/mobile/sim/position/real_trade",
    "long_running_service_state",
)
GUARD_TABLES = (
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_trigger_match",
    "common_trigger_state",
)
STANDARD_N4_OUTBOX_EVENT_TYPES = ("TriggerMatched", "TriggerPendingMarketData", "TriggerCleared")
EXPECTED_CLASSIFICATION_COUNTS = {
    "would_match": 4734,
    "would_clear": 245,
    "would_change": 243,
    "unchanged": 30730,
    "missing": 18,
    "not_ready": 0,
}
EXPECTED_TOTAL_AUDIT_ROWS = 35970
EXPECTED_C3_PENDING_ROWS = 17432


class C3ReplayAuditExecuteError(RuntimeError):
    """Raised when the N4 C3 replay audit execute gate is blocked."""


def assert_execute_confirmed(*, execute: bool, user_confirmed: bool, replay_run_id: str) -> None:
    missing = []
    if not execute:
        missing.append("--execute")
    if not user_confirmed:
        missing.append("--user-confirmed")
    if replay_run_id != DEFAULT_REPLAY_RUN_ID:
        missing.append("expected replay_run_id")
    if missing:
        raise C3ReplayAuditExecuteError(
            "N4 C3 replay audit execute blocked: missing explicit confirmation/input "
            f"{', '.join(missing)}"
        )


def build_execute_contract() -> dict[str, Any]:
    return {
        "stage": "N4 C3 replay audit run-once execute",
        "layer_role": "N4_trigger",
        "execution_shape": "audit_only_run_once",
        "requires_execute_flag": True,
        "requires_user_confirmed_flag": True,
        "replay_run_id": DEFAULT_REPLAY_RUN_ID,
        "allowed_c3_run_id": DEFAULT_ALLOWED_C3_RUN_ID,
        "c2b_run_id": DEFAULT_C2B_RUN_ID,
        "trigger_context_run_id": DEFAULT_CONTEXT_RUN_ID,
        "source_n4_projection_run_id": DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
        "source_n5_action_run_id": DEFAULT_N5_ACTION_EXECUTE_RUN_ID,
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "outbox_policy": {
            "emit_n4_outbox": False,
            "forbidden_standard_event_types": list(STANDARD_N4_OUTBOX_EVENT_TYPES),
        },
        "planned_standard_n4_outbox_counts": {event_type: 0 for event_type in STANDARD_N4_OUTBOX_EVENT_TYPES},
        "expected_audit_counts": {
            "total": EXPECTED_TOTAL_AUDIT_ROWS,
            "by_classification": dict(EXPECTED_CLASSIFICATION_COUNTS),
        },
        "side_effects": {
            "c3_outbox_consumed": False,
            "common_event_outbox_written": False,
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "trigger_match_written": False,
            "trigger_state_written": False,
            "downstream_layers_touched": False,
            "long_running_service_started": False,
        },
        "rollback_sql_path": DEFAULT_ROLLBACK_SQL_PATH,
    }


def run_c3_replay_audit_execute_preflight(
    *,
    dsn: str,
    replay_run_id: str = DEFAULT_REPLAY_RUN_ID,
    allowed_c3_run_id: str = DEFAULT_ALLOWED_C3_RUN_ID,
    c2b_run_id: str = DEFAULT_C2B_RUN_ID,
    trigger_context_run_id: str = DEFAULT_CONTEXT_RUN_ID,
    projection_execute_run_id: str = DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
    source_n5_action_run_id: str = DEFAULT_N5_ACTION_EXECUTE_RUN_ID,
    json_report_path: str = DEFAULT_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
    sample_limit: int = 80,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    before_counts = capture_guard_row_counts(dsn)
    plan = build_replay_audit_plan_from_database(
        dsn=dsn,
        replay_run_id=replay_run_id,
        allowed_c3_run_id=allowed_c3_run_id,
        c2b_run_id=c2b_run_id,
        trigger_context_run_id=trigger_context_run_id,
        projection_execute_run_id=projection_execute_run_id,
        source_n5_action_run_id=source_n5_action_run_id,
        sample_limit=sample_limit,
    )
    schema_status = fetch_schema_status(dsn)
    baseline_guard = fetch_baseline_guard(dsn, replay_run_id=replay_run_id)
    c3_outbox_status = fetch_c3_outbox_status(dsn, allowed_c3_run_id=allowed_c3_run_id)
    after_counts = capture_guard_row_counts(dsn)
    report = build_preflight_report_from_inputs(
        dry_run_report=plan["dry_run_report"],
        audit_rows=plan["audit_rows"],
        schema_status=schema_status,
        baseline_guard=baseline_guard,
        c3_outbox_status=c3_outbox_status,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
        rollback_sql_exists=Path(rollback_sql_path).exists(),
        started_at=started_at,
        sample_limit=sample_limit,
    )
    report["rollback_sql_path"] = rollback_sql_path
    report["sample_audit_rows"] = plan["audit_rows"][:sample_limit]
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_preflight_report(report))
    return report


def run_c3_replay_audit_once(
    *,
    dsn: str,
    execute: bool,
    user_confirmed: bool,
    replay_run_id: str = DEFAULT_REPLAY_RUN_ID,
    allowed_c3_run_id: str = DEFAULT_ALLOWED_C3_RUN_ID,
    c2b_run_id: str = DEFAULT_C2B_RUN_ID,
    trigger_context_run_id: str = DEFAULT_CONTEXT_RUN_ID,
    projection_execute_run_id: str = DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
    source_n5_action_run_id: str = DEFAULT_N5_ACTION_EXECUTE_RUN_ID,
    json_report_path: str = DEFAULT_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
    sample_limit: int = 80,
) -> dict[str, Any]:
    assert_execute_confirmed(execute=execute, user_confirmed=user_confirmed, replay_run_id=replay_run_id)
    preflight = run_c3_replay_audit_execute_preflight(
        dsn=dsn,
        replay_run_id=replay_run_id,
        allowed_c3_run_id=allowed_c3_run_id,
        c2b_run_id=c2b_run_id,
        trigger_context_run_id=trigger_context_run_id,
        projection_execute_run_id=projection_execute_run_id,
        source_n5_action_run_id=source_n5_action_run_id,
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        rollback_sql_path=rollback_sql_path,
        sample_limit=sample_limit,
    )
    if int(preflight["quality"]["p0_count"]) > 0:
        raise C3ReplayAuditExecuteError("N4 C3 replay audit execute blocked: preflight has P0 findings")
    full_plan = build_replay_audit_plan_from_database(
        dsn=dsn,
        replay_run_id=replay_run_id,
        allowed_c3_run_id=allowed_c3_run_id,
        c2b_run_id=c2b_run_id,
        trigger_context_run_id=trigger_context_run_id,
        projection_execute_run_id=projection_execute_run_id,
        source_n5_action_run_id=source_n5_action_run_id,
        sample_limit=sample_limit,
    )
    inserted_counts = execute_replay_audit_transaction(
        dsn=dsn,
        preflight=preflight,
        audit_rows=full_plan["audit_rows"],
    )
    preflight["result"] = "EXECUTED"
    preflight["inserted_counts"] = inserted_counts
    preflight["side_effects"].update(
        {
            "will_execute_sql": True,
            "writes_performed": True,
            "common_trigger_run_written": True,
            "common_trigger_quality_item_written": inserted_counts.get("common_trigger_quality_item", 0) > 0,
            "replay_audit_rows_written": sum(inserted_counts.get(table, 0) for table in AUDIT_TABLES) > 0,
        }
    )
    write_json(json_report_path, preflight)
    write_text(markdown_report_path, format_preflight_report(preflight))
    return preflight


def build_replay_audit_plan_from_database(
    *,
    dsn: str,
    replay_run_id: str,
    allowed_c3_run_id: str,
    c2b_run_id: str,
    trigger_context_run_id: str,
    projection_execute_run_id: str,
    source_n5_action_run_id: str,
    sample_limit: int,
) -> dict[str, Any]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_c3_replay_audit_build_plan",
        source_run_id=replay_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        context_rows, trigger_context_run = fetch_context_rows(dsn, trigger_context_run_id)
        projection_trigger_run = fetch_trigger_run(cur, projection_execute_run_id)
        c3_outbox_rows = fetch_c3_outbox_rows(cur, allowed_c3_run_id)
        closed_summary_rows = fetch_closed_summary_rows(cur, c3_outbox_rows)
        closed_signal_enrichment_rows = fetch_closed_signal_enrichment_rows(cur, c2b_run_id, c3_outbox_rows)
        projection_match_rows = fetch_projection_match_rows(cur, projection_execute_run_id)
        trace_only_projection_counts = fetch_projection_trace_only_counts(cur, DEFAULT_PROJECTION_RUN_ID)

    context_candidates = build_replay_context_candidates(
        context_rows=context_rows,
        trigger_context_run_id=trigger_context_run_id,
    )
    evaluations = build_replay_evaluations(
        context_candidates=context_candidates,
        c3_outbox_rows=c3_outbox_rows,
        closed_summary_rows=closed_summary_rows,
        closed_signal_enrichment_rows=closed_signal_enrichment_rows,
        projection_match_rows=projection_match_rows,
        projection_trigger_run_id=projection_execute_run_id,
    )
    dry_run_report = build_c3_replay_dry_run_report_from_rows(
        allowed_c3_run_id=allowed_c3_run_id,
        c2b_run_id=c2b_run_id,
        replay_run_id=replay_run_id,
        trigger_context_run=trigger_context_run,
        projection_trigger_run=projection_trigger_run,
        context_rows=context_rows,
        c3_outbox_rows=c3_outbox_rows,
        closed_summary_rows=closed_summary_rows,
        closed_signal_enrichment_rows=closed_signal_enrichment_rows,
        projection_match_rows=projection_match_rows,
        before_row_counts=None,
        after_row_counts=None,
        sample_limit=sample_limit,
        trace_only_projection_summary=trace_only_projection_counts,
    )
    dry_run_report["original_n5_action_execute_run_id"] = source_n5_action_run_id
    audit_rows = build_audit_rows_from_evaluations(
        replay_run_id=replay_run_id,
        source_c3_run_id=allowed_c3_run_id,
        source_c2b_run_id=c2b_run_id,
        source_n4_projection_run_id=projection_execute_run_id,
        source_trigger_context_run_id=trigger_context_run_id,
        source_n5_action_run_id=source_n5_action_run_id,
        evaluations=evaluations,
    )
    return {"dry_run_report": dry_run_report, "audit_rows": audit_rows}


def build_audit_rows_from_evaluations(
    *,
    replay_run_id: str,
    source_c3_run_id: str,
    source_c2b_run_id: str,
    source_n4_projection_run_id: str,
    source_trigger_context_run_id: str,
    source_n5_action_run_id: str | None,
    evaluations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        build_audit_row_from_evaluation(
            replay_run_id=replay_run_id,
            source_c3_run_id=source_c3_run_id,
            source_c2b_run_id=source_c2b_run_id,
            source_n4_projection_run_id=source_n4_projection_run_id,
            source_trigger_context_run_id=source_trigger_context_run_id,
            source_n5_action_run_id=source_n5_action_run_id,
            evaluation=evaluation,
        )
        for evaluation in evaluations
    ]


def build_audit_row_from_evaluation(
    *,
    replay_run_id: str,
    source_c3_run_id: str,
    source_c2b_run_id: str,
    source_n4_projection_run_id: str,
    source_trigger_context_run_id: str,
    source_n5_action_run_id: str | None,
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    asset_kind = str(evaluation.get("asset_kind") or "")
    identity_key = str(evaluation.get("identity_key") or "")
    exchange, code = parse_identity_key(identity_key)
    classification = str(evaluation.get("classification") or "")
    row = {
        "target_table": f"{asset_kind}_trigger_replay_audit",
        "replay_run_id": replay_run_id,
        "source_c3_run_id": source_c3_run_id,
        "source_c2b_run_id": source_c2b_run_id,
        "source_n4_projection_run_id": source_n4_projection_run_id,
        "source_trigger_context_run_id": source_trigger_context_run_id,
        "source_condition_run_id": str(evaluation.get("source_condition_run_id") or ""),
        "source_n5_action_run_id": source_n5_action_run_id,
        "for_trade_date": "20260525",
        "trade_date": "20260525",
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "identity_column_value": identity_key,
        "exchange": exchange,
        "code": code,
        "name": str(evaluation.get("name") or identity_key),
        "condition_key": str(evaluation.get("condition_key") or ""),
        "signal_type": str(evaluation.get("signal_type") or ""),
        "direction": str(evaluation.get("direction") or ""),
        "trigger_period": str(evaluation.get("trigger_period") or "30m"),
        "trigger_bucket": str(evaluation.get("trigger_bucket") or "bucket_missing"),
        "replay_classification": classification,
        "replay_diff_type": str(evaluation.get("diff_case") or "replay_blocked"),
        "original_trigger_status": original_trigger_status(evaluation),
        "closed_signal_status": str(evaluation.get("closed_signal_status") or "missing"),
        "closed_signal_quality_status": str(evaluation.get("closed_quality_status") or "unknown"),
        "projection_signal_status": str(evaluation.get("projection_signal_status") or "missing"),
        "original_match_id": evaluation.get("projection_trigger_match_id"),
        "c3_event_id": evaluation.get("source_c3_event_id"),
        "c2b_enrichment_id": evaluation.get("closed_signal_enrichment_id"),
        "comparison_key": build_comparison_key(evaluation),
        "diff_json": {
            "classification": classification,
            "diff_case": evaluation.get("diff_case"),
            "reason": evaluation.get("reason"),
            "projection_matched": bool(evaluation.get("projection_matched")),
            "closed_matched": bool(evaluation.get("closed_matched")),
            "value_trace": evaluation.get("value_trace") or {},
        },
        "trace_json": {
            "plan_id": evaluation.get("plan_id"),
            "context_snapshot_id": evaluation.get("context_snapshot_id"),
            "context_hash": evaluation.get("context_hash"),
            "source_c3_outbox_id": evaluation.get("source_c3_outbox_id"),
            "closed_30m_summary_id": evaluation.get("closed_30m_summary_id"),
            "closed_bucket_id": evaluation.get("closed_bucket_id"),
            "projection_source_event_id": evaluation.get("projection_source_event_id"),
            "projection_output_event_type": evaluation.get("projection_output_event_type"),
            "period_trigger_baseline_trace_present": evaluation.get("period_trigger_baseline_trace_present"),
        },
        "quality_status": quality_status_for_classification(classification),
    }
    return row


def parse_identity_key(identity_key: str) -> tuple[str, str]:
    parts = identity_key.split(":")
    if len(parts) >= 3:
        return parts[1], parts[2]
    return "UNKNOWN", identity_key


def build_comparison_key(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("asset_kind") or ""),
            str(row.get("identity_key") or ""),
            str(row.get("direction") or ""),
            str(row.get("signal_type") or ""),
            str(row.get("condition_key") or ""),
            str(row.get("trigger_period") or "30m"),
            str(row.get("trigger_bucket") or "bucket_missing"),
        ]
    )


def original_trigger_status(row: Mapping[str, Any]) -> str:
    if row.get("projection_matched"):
        return "matched"
    output_type = str(row.get("projection_output_event_type") or "")
    if output_type == "TriggerPendingMarketData":
        return "pending_market_data"
    if output_type == "TriggerCleared":
        return "cleared"
    return "missing"


def quality_status_for_classification(classification: str) -> str:
    if classification == "missing":
        return "missing"
    if classification == "not_ready":
        return "not_ready"
    if classification == "would_change":
        return "warning"
    return "passed"


def summarize_audit_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(rows),
        "by_classification": count_by(rows, "replay_classification"),
        "by_diff_type": count_by(rows, "replay_diff_type"),
        "by_target_table": count_by(rows, "target_table"),
        "by_signal_type": count_by(rows, "signal_type"),
    }


def build_preflight_report_from_inputs(
    *,
    dry_run_report: Mapping[str, Any],
    audit_rows: Sequence[Mapping[str, Any]],
    schema_status: Mapping[str, Mapping[str, Any]],
    baseline_guard: Mapping[str, int],
    c3_outbox_status: Mapping[str, int],
    before_row_counts: Mapping[str, Mapping[str, Any]],
    after_row_counts: Mapping[str, Mapping[str, Any]],
    rollback_sql_exists: bool,
    started_at: str | None = None,
    sample_limit: int = 80,
) -> dict[str, Any]:
    audit_summary = summarize_audit_rows(audit_rows)
    audit_summary["by_classification"] = normalize_classification_counts(audit_summary["by_classification"])
    quality_items = build_preflight_quality_items(
        dry_run_report=dry_run_report,
        audit_summary=audit_summary,
        schema_status=schema_status,
        baseline_guard=baseline_guard,
        c3_outbox_status=c3_outbox_status,
        before_row_counts=before_row_counts,
        after_row_counts=after_row_counts,
        rollback_sql_exists=rollback_sql_exists,
    )
    quality_counts = count_quality_severities(quality_items)
    return {
        "stage": "N4-C3-replay-audit-execute-preflight",
        "result": "PREFLIGHT_PASS" if quality_counts["P0"] == 0 else "PREFLIGHT_BLOCKED",
        "layer_role": "N4_trigger",
        "mode": "audit_only_execute_preflight",
        "replay_run_id": dry_run_report.get("replay_run_id") or DEFAULT_REPLAY_RUN_ID,
        "allowed_c3_run_id": dry_run_report.get("allowed_c3_run_id") or DEFAULT_ALLOWED_C3_RUN_ID,
        "c2b_run_id": dry_run_report.get("c2b_run_id") or DEFAULT_C2B_RUN_ID,
        "trigger_context_run_id": dry_run_report.get("trigger_context_run_id") or DEFAULT_CONTEXT_RUN_ID,
        "source_n4_projection_run_id": dry_run_report.get("original_n4_projection_execute_run_id")
        or DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
        "source_n5_action_run_id": dry_run_report.get("original_n5_action_execute_run_id")
        or DEFAULT_N5_ACTION_EXECUTE_RUN_ID,
        "started_at": started_at or utc_now_iso(),
        "finished_at": utc_now_iso(),
        "execute_contract": build_execute_contract(),
        "schema_status": dict(schema_status),
        "baseline_guard": dict(baseline_guard),
        "c3_outbox_status": dict(c3_outbox_status),
        "dry_run_summary": {
            "result": dry_run_report.get("result"),
            "source_condition_run_id": dry_run_report.get("source_condition_run_id"),
            "candidate_count": (dry_run_report.get("classification_summary") or {}).get("candidate_count"),
            "by_classification": normalize_classification_counts(
                (dry_run_report.get("classification_summary") or {}).get("by_classification") or {}
            ),
            "P0/P1/P2": dry_run_report.get("P0/P1/P2")
            or f"{(dry_run_report.get('quality') or {}).get('p0_count')}/{(dry_run_report.get('quality') or {}).get('p1_count')}/{(dry_run_report.get('quality') or {}).get('p2_count')}",
        },
        "audit_plan_summary": audit_summary,
        "planned_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "planned_standard_n4_outbox_counts": {event_type: 0 for event_type in STANDARD_N4_OUTBOX_EVENT_TYPES},
        "before_row_counts": dict(before_row_counts),
        "after_row_counts": dict(after_row_counts),
        "row_count_guard_unchanged": before_row_counts == after_row_counts,
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "writes_performed": False,
            "common_trigger_run_written": False,
            "common_trigger_quality_item_written": False,
            "replay_audit_rows_written": False,
            "common_event_outbox_written": False,
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "trigger_match_written": False,
            "trigger_state_written": False,
            "c3_outbox_consumed": False,
            "n5_n6_touched": False,
            "market_data_pulled": False,
            "long_running_service_started": False,
        },
        "rollback_sql_path": DEFAULT_ROLLBACK_SQL_PATH,
        "sample_audit_rows": list(audit_rows[:sample_limit]),
        "next_gate": {
            "allow_execute_final_gate": quality_counts["P0"] == 0,
            "allow_business_execute_now": False,
            "execute_requires": ["--execute", "--user-confirmed"],
        },
    }


def build_preflight_quality_items(
    *,
    dry_run_report: Mapping[str, Any],
    audit_summary: Mapping[str, Any],
    schema_status: Mapping[str, Mapping[str, Any]],
    baseline_guard: Mapping[str, int],
    c3_outbox_status: Mapping[str, int],
    before_row_counts: Mapping[str, Mapping[str, Any]],
    after_row_counts: Mapping[str, Mapping[str, Any]],
    rollback_sql_exists: bool,
) -> list[dict[str, Any]]:
    dry_run_classification = normalize_classification_counts(
        (dry_run_report.get("classification_summary") or {}).get("by_classification") or {}
    )
    dry_run_p0 = int((dry_run_report.get("quality") or {}).get("p0_count") or 0)
    schema_ready = all(
        (schema_status.get(table) or {}).get("exists") and int((schema_status.get(table) or {}).get("row_count") or 0) == 0
        for table in AUDIT_TABLES
    )
    index_ready = all(int((schema_status.get(table) or {}).get("index_count") or 0) >= 9 for table in AUDIT_TABLES)
    baseline_zero = all(int(value or 0) == 0 for value in baseline_guard.values())
    c3_pending = int(c3_outbox_status.get("pending") or 0)
    c3_delivered = int(c3_outbox_status.get("delivered") or 0)
    c3_delivering = int(c3_outbox_status.get("delivering") or 0)
    audit_classification = normalize_classification_counts(audit_summary.get("by_classification") or {})
    return [
        quality_item(
            "P0",
            "passed" if dry_run_report.get("result") == "DRY_RUN_PASS" and dry_run_p0 == 0 else "failed",
            "n4_c3_replay_audit_dry_run_passed",
            "Replay audit execute preflight requires a passed C3 replay dry-run",
            expected="DRY_RUN_PASS and P0=0",
            actual=f"{dry_run_report.get('result')} P0={dry_run_p0}",
        ),
        quality_item(
            "P0",
            "passed" if schema_ready and index_ready else "failed",
            "n4_c3_replay_audit_schema_ready",
            "Replay audit tables must exist, be empty, and have expected indexes before business execute",
            expected="three empty audit tables with indexes",
            actual=json.dumps(schema_status, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if baseline_zero else "failed",
            "n4_c3_replay_audit_baseline_zero",
            "Replay run scoped rows must be zero before execute",
            expected="all replay_run_id scoped counts are 0",
            actual=json.dumps(dict(baseline_guard), ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if c3_pending == EXPECTED_C3_PENDING_ROWS and c3_delivered == 0 and c3_delivering == 0 else "failed",
            "n4_c3_replay_audit_c3_outbox_not_consumed",
            "C3 MinuteBarClosed outbox must remain pending and unconsumed",
            expected=f"pending={EXPECTED_C3_PENDING_ROWS}, delivered=0, delivering=0",
            actual=json.dumps(dict(c3_outbox_status), ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if audit_summary.get("total") == EXPECTED_TOTAL_AUDIT_ROWS else "failed",
            "n4_c3_replay_audit_total_matches_dry_run",
            "Replay audit planned row count must match dry-run comparison candidates",
            expected=str(EXPECTED_TOTAL_AUDIT_ROWS),
            actual=str(audit_summary.get("total")),
        ),
        quality_item(
            "P0",
            "passed" if audit_classification == EXPECTED_CLASSIFICATION_COUNTS == dry_run_classification else "failed",
            "n4_c3_replay_audit_classification_matches_dry_run",
            "Replay audit classification counts must match reviewed dry-run",
            expected=json.dumps(EXPECTED_CLASSIFICATION_COUNTS, sort_keys=True),
            actual=json.dumps(audit_classification, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if before_row_counts == after_row_counts else "failed",
            "n4_c3_replay_audit_preflight_read_only",
            "Execute preflight must not change guarded row counts",
            expected="before row counts equal after row counts",
            actual="unchanged" if before_row_counts == after_row_counts else "changed",
        ),
        quality_item(
            "P0",
            "passed" if rollback_sql_exists else "failed",
            "n4_c3_replay_audit_business_rollback_exists",
            "Replay audit business rollback SQL must exist before execute",
            expected=DEFAULT_ROLLBACK_SQL_PATH,
            actual="present" if rollback_sql_exists else "missing",
        ),
        quality_item("P0", "passed", "n4_c3_replay_audit_no_standard_outbox", "Replay audit v1 emits no standard N4 outbox"),
        quality_item("P0", "passed", "n4_c3_replay_audit_no_inbox_checkpoint", "Replay audit v1 does not consume C3 outbox"),
        quality_item("P0", "passed", "n4_c3_replay_audit_no_trigger_match_state", "Replay audit v1 does not write live trigger facts"),
        quality_item("P0", "passed", "n4_c3_replay_audit_no_downstream_layers", "Replay audit v1 does not enter downstream layers"),
        quality_item(
            "P1",
            "warning" if EXPECTED_CLASSIFICATION_COUNTS["missing"] else "passed",
            "n4_c3_replay_audit_missing_rows_visible",
            "Replay audit keeps missing comparison rows visible for review",
            expected="visible",
            actual=str(EXPECTED_CLASSIFICATION_COUNTS["missing"]),
        ),
    ]


def normalize_classification_counts(counts: Mapping[str, Any]) -> dict[str, int]:
    return {classification: int(counts.get(classification) or 0) for classification in REPLAY_CLASSIFICATIONS}


def fetch_schema_status(dsn: str) -> dict[str, dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_c3_replay_audit_schema_status",
        source_run_id=DEFAULT_REPLAY_RUN_ID,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        status: dict[str, dict[str, Any]] = {}
        for table_name in AUDIT_TABLES:
            exists = table_exists(cur, table_name)
            row_count = table_count(cur, table_name) if exists else None
            status[table_name] = {
                "exists": exists,
                "row_count": row_count,
                "index_count": index_count(cur, table_name) if exists else None,
            }
        return status


def fetch_baseline_guard(dsn: str, *, replay_run_id: str) -> dict[str, int]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_c3_replay_audit_baseline_guard",
        source_run_id=replay_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        return {
            "common_trigger_run": count_where(cur, "common_trigger_run", "run_id = %s", (replay_run_id,)),
            "common_trigger_quality_item": count_where(cur, "common_trigger_quality_item", "run_id = %s", (replay_run_id,)),
            "stock_trigger_replay_audit": count_where(cur, "stock_trigger_replay_audit", "replay_run_id = %s", (replay_run_id,)),
            "index_trigger_replay_audit": count_where(cur, "index_trigger_replay_audit", "replay_run_id = %s", (replay_run_id,)),
            "board_trigger_replay_audit": count_where(cur, "board_trigger_replay_audit", "replay_run_id = %s", (replay_run_id,)),
            "common_event_outbox": count_where(cur, "common_event_outbox", "source_layer = 'N4_trigger' AND source_run_id = %s", (replay_run_id,)),
            "common_event_inbox": count_where(cur, "common_event_inbox", "raw_json ->> 'replay_run_id' = %s", (replay_run_id,)),
            "common_event_consumer_checkpoint": count_where(cur, "common_event_consumer_checkpoint", "checkpoint_payload ->> 'replay_run_id' = %s", (replay_run_id,)),
            "common_trigger_match": count_where(cur, "common_trigger_match", "run_id = %s", (replay_run_id,)),
            "common_trigger_state": count_where(cur, "common_trigger_state", "run_id = %s", (replay_run_id,)),
        }


def fetch_c3_outbox_status(dsn: str, *, allowed_c3_run_id: str) -> dict[str, int]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_c3_replay_audit_c3_outbox_status",
        source_run_id=allowed_c3_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, count(*)::bigint AS row_count
            FROM common_event_outbox
            WHERE source_layer = 'N3_market_data'
              AND event_type = 'MinuteBarClosed'
              AND source_run_id = %s
            GROUP BY status
            ORDER BY status
            """,
            (allowed_c3_run_id,),
        )
        return {str(row["status"]): int(row["row_count"]) for row in cur.fetchall()}


def capture_guard_row_counts(dsn: str) -> dict[str, dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_c3_replay_audit_capture_guard_counts",
        source_run_id="c3_replay_audit_guard_counts",
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        output: dict[str, dict[str, Any]] = {}
        for table_name in GUARD_TABLES:
            exists = table_exists(cur, table_name)
            output[table_name] = {
                "exists": exists,
                "row_count": table_count(cur, table_name) if exists else None,
            }
        return output


def table_exists(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
    return cur.fetchone()["regclass"] is not None


def table_count(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> int:
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
    return int(cur.fetchone()["row_count"])


def index_count(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> int:
    cur.execute(
        """
        SELECT count(*)::bigint AS index_count
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = %s
        """,
        (table_name,),
    )
    return int(cur.fetchone()["index_count"])


def count_where(cur: psycopg.Cursor[dict[str, Any]], table_name: str, where_sql: str, params: Sequence[Any]) -> int:
    if not table_exists(cur, table_name):
        return 0
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE {where_sql}", params)
    return int(cur.fetchone()["row_count"])


def execute_replay_audit_transaction(
    *,
    dsn: str,
    preflight: Mapping[str, Any],
    audit_rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    replay_run_id = str(preflight["replay_run_id"])
    source_condition_run_id = str((preflight.get("dry_run_summary") or {}).get("source_condition_run_id") or "condition_layer_20260522_to_20260525_20260525102249_execute")
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_c3_replay_audit_execute_transaction",
        source_run_id=replay_run_id,
        readonly_expected=False,
        connect_timeout=10,
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            insert_trigger_run(cur, preflight=preflight, source_condition_run_id=source_condition_run_id)
            quality_count = insert_quality_items(cur, preflight=preflight, source_condition_run_id=source_condition_run_id)
            audit_counts = insert_audit_rows(cur, rows=audit_rows)
        conn.commit()
    return {"common_trigger_run": 1, "common_trigger_quality_item": quality_count, **audit_counts, "replay_run_id": replay_run_id}


def insert_trigger_run(cur: psycopg.Cursor[dict[str, Any]], *, preflight: Mapping[str, Any], source_condition_run_id: str) -> None:
    cur.execute(
        """
        INSERT INTO common_trigger_run (
          run_id, source_condition_run_id, source_market_data_run_id,
          for_trade_date, source_trade_date, prev_trade_date,
          mode, status, p0_count, p1_count, p2_count,
          source_condition_row_count, context_snapshot_row_count,
          trigger_state_row_count, trigger_match_row_count, trigger_event_outbox_count,
          generated_by, raw_json, finished_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'execute', 'passed', %s, %s, %s, 0, 0, 0, 0, 0, %s, %s, now())
        """,
        (
            preflight["replay_run_id"],
            source_condition_run_id,
            preflight["allowed_c3_run_id"],
            "20260525",
            "20260522",
            "20260522",
            int((preflight.get("quality") or {}).get("p0_count") or 0),
            int((preflight.get("quality") or {}).get("p1_count") or 0),
            int((preflight.get("quality") or {}).get("p2_count") or 0),
            "c3_replay_audit_execute",
            Jsonb(to_jsonable({"audit_plan_summary": preflight.get("audit_plan_summary"), "lineage": lineage_from_preflight(preflight)})),
        ),
    )


def insert_quality_items(cur: psycopg.Cursor[dict[str, Any]], *, preflight: Mapping[str, Any], source_condition_run_id: str) -> int:
    items = list((preflight.get("quality") or {}).get("items") or [])
    if not items:
        return 0
    rows = []
    for item in items:
        rows.append(
            (
                preflight["replay_run_id"],
                source_condition_run_id,
                "20260525",
                "20260522",
                "common",
                "trigger_run",
                None,
                item.get("gate_code"),
                item.get("gate_name"),
                item.get("severity"),
                item.get("status"),
                item.get("expected_value"),
                item.get("actual_value"),
                Jsonb({"metric_scope": "c3_replay_audit", "details": item.get("details") or {}}),
            )
        )
    cur.executemany(
        """
        INSERT INTO common_trigger_quality_item (
          run_id, source_condition_run_id, for_trade_date, source_trade_date,
          data_domain, layer_scope, table_name, gate_code, gate_name,
          severity, status, expected_value, actual_value, details
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    return len(rows)


def insert_audit_rows(cur: psycopg.Cursor[dict[str, Any]], *, rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {table: 0 for table in AUDIT_TABLES}
    for table_name in AUDIT_TABLES:
        table_rows = [row for row in rows if row.get("target_table") == table_name]
        if not table_rows:
            continue
        identity_column = table_name.split("_", 1)[0] + "_identity_key"
        columns = [
            "replay_run_id",
            "source_c3_run_id",
            "source_c2b_run_id",
            "source_n4_projection_run_id",
            "source_trigger_context_run_id",
            "source_condition_run_id",
            "source_n5_action_run_id",
            "for_trade_date",
            "trade_date",
            "asset_kind",
            "identity_key",
            identity_column,
            "exchange",
            "code",
            "name",
            "condition_key",
            "signal_type",
            "direction",
            "trigger_period",
            "trigger_bucket",
            "replay_classification",
            "replay_diff_type",
            "original_trigger_status",
            "closed_signal_status",
            "closed_signal_quality_status",
            "projection_signal_status",
            "original_match_id",
            "c3_event_id",
            "c2b_enrichment_id",
            "comparison_key",
            "diff_json",
            "trace_json",
            "quality_status",
        ]
        values = [
            tuple(Jsonb(row[column]) if column in {"diff_json", "trace_json"} else row.get(column if column != identity_column else "identity_column_value") for column in columns)
            for row in table_rows
        ]
        placeholders = ", ".join(["%s"] * len(columns))
        column_sql = ", ".join(columns)
        cur.executemany(
            f"""
            INSERT INTO {table_name} ({column_sql})
            VALUES ({placeholders})
            ON CONFLICT (replay_run_id, comparison_key) DO NOTHING
            """,
            values,
        )
        counts[table_name] = len(table_rows)
    return counts


def lineage_from_preflight(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "allowed_c3_run_id": preflight.get("allowed_c3_run_id"),
        "c2b_run_id": preflight.get("c2b_run_id"),
        "trigger_context_run_id": preflight.get("trigger_context_run_id"),
        "source_n4_projection_run_id": preflight.get("source_n4_projection_run_id"),
        "source_n5_action_run_id": preflight.get("source_n5_action_run_id"),
    }


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def format_preflight_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    audit_summary = report.get("audit_plan_summary") or {}
    return "\n".join(
        [
            "# N4 C3 Replay Audit Execute Preflight",
            "",
            f"- result: `{report.get('result')}`",
            f"- layer_role: `{report.get('layer_role')}`",
            f"- replay_run_id: `{report.get('replay_run_id')}`",
            f"- allowed_c3_run_id: `{report.get('allowed_c3_run_id')}`",
            f"- c2b_run_id: `{report.get('c2b_run_id')}`",
            f"- source_n4_projection_run_id: `{report.get('source_n4_projection_run_id')}`",
            f"- source_n5_action_run_id: `{report.get('source_n5_action_run_id')}`",
            f"- rollback_sql_path: `{report.get('rollback_sql_path')}`",
            "",
            "## Audit Plan",
            "",
            f"- total: `{audit_summary.get('total')}`",
            f"- by_classification: `{audit_summary.get('by_classification')}`",
            f"- by_target_table: `{audit_summary.get('by_target_table')}`",
            "",
            "## Boundary",
            "",
            f"- planned_write_tables: `{report.get('planned_write_tables')}`",
            f"- planned_standard_n4_outbox_counts: `{report.get('planned_standard_n4_outbox_counts')}`",
            f"- writes_performed: `{(report.get('side_effects') or {}).get('writes_performed')}`",
            f"- common_event_outbox_written: `{(report.get('side_effects') or {}).get('common_event_outbox_written')}`",
            f"- common_event_inbox_written: `{(report.get('side_effects') or {}).get('common_event_inbox_written')}`",
            f"- checkpoint_written: `{(report.get('side_effects') or {}).get('checkpoint_written')}`",
            f"- trigger_match_written: `{(report.get('side_effects') or {}).get('trigger_match_written')}`",
            f"- trigger_state_written: `{(report.get('side_effects') or {}).get('trigger_state_written')}`",
            f"- n5_n6_touched: `{(report.get('side_effects') or {}).get('n5_n6_touched')}`",
            "",
            "## Quality",
            "",
            f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
            f"- quality_items: `{len(quality.get('items') or [])}`",
            "",
            "## Next Gate",
            "",
            f"- allow_execute_final_gate: `{(report.get('next_gate') or {}).get('allow_execute_final_gate')}`",
            "- execute still requires explicit final gate and both `--execute` / `--user-confirmed`.",
        ]
    )


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: str, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
