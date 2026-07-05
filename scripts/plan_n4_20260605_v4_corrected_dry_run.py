#!/usr/bin/env python3
"""Generate the N4 20260605 v4 corrected dry-run artifact.

This script is read-only with respect to PostgreSQL. It reads the already
materialized N4 context, N3 B1 snapshot, and N3 B2 projection facts, applies
the v4 strict TriggerMatched enforcement, and writes only docs artifacts.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect
from ashare_v3.trigger.local_trigger_dry_run import (
    build_local_trigger_plans,
    fetch_context_rows,
    fetch_snapshot_rows,
)
from ashare_v3.trigger.projection_matcher import build_projection_matcher_plans, fetch_projection_rows
from ashare_v3.trigger.synthetic_dry_run import write_json, write_text
from ashare_v3.trigger.v4_corrected_dry_run import build_corrected_v4_dry_run_report
from check_condition_source_ready import DEFAULT_DSN


DEFAULT_CONTEXT_RUN_ID = "trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1"
DEFAULT_SNAPSHOT_RUN_ID = (
    "realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1"
)
DEFAULT_PROJECTION_RUN_ID = (
    "realtime_projection_metric_20260605_live2_compat__"
    "realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1"
)
DEFAULT_EXECUTE_RUN_ID = "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
DEFAULT_JSON_REPORT_PATH = "docs/N4_20260605_V4_CORRECTED_DRY_RUN.json"
DEFAULT_MD_REPORT_PATH = "docs/N4_20260605_V4_CORRECTED_DRY_RUN.md"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N4_20260605_execute_rollback.sql"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan N4 20260605 v4 corrected dry-run outputs.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute-run-id", default=DEFAULT_EXECUTE_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_CONTEXT_RUN_ID)
    parser.add_argument("--snapshot-run-id", default=DEFAULT_SNAPSHOT_RUN_ID)
    parser.add_argument("--projection-run-id", default=DEFAULT_PROJECTION_RUN_ID)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    generated_at = datetime.now(timezone.utc)
    before_refs = capture_target_refs(args.dsn, args.execute_run_id)
    trigger_run, context_rows = fetch_context_rows(args.dsn, args.trigger_context_run_id)
    snapshot_run, snapshot_rows = fetch_snapshot_rows(args.dsn, args.snapshot_run_id)
    _, projection_context_rows = trigger_run, context_rows
    projection_rows = fetch_projection_rows(args.dsn, args.projection_run_id)
    local_plans = build_local_trigger_plans(
        trigger_context_run_id=args.trigger_context_run_id,
        snapshot_run_id=args.snapshot_run_id,
        context_rows=context_rows,
        snapshot_rows=snapshot_rows,
    )
    projection_plans = build_projection_matcher_plans(
        trigger_context_run_id=args.trigger_context_run_id,
        projection_run_id=args.projection_run_id,
        context_rows=projection_context_rows,
        projection_rows=projection_rows,
    )
    after_refs = capture_target_refs(args.dsn, args.execute_run_id)
    report = build_corrected_v4_dry_run_report(
        local_plans=local_plans,
        projection_plans=projection_plans,
        metadata={
            "execute_run_id": args.execute_run_id,
            "trigger_context_run_id": args.trigger_context_run_id,
            "snapshot_run_id": args.snapshot_run_id,
            "projection_run_id": args.projection_run_id,
            "source_condition_run_id": trigger_run.get("source_condition_run_id"),
            "for_trade_date": trigger_run.get("for_trade_date") or snapshot_run.get("for_trade_date"),
            "rollback_sql_path": args.rollback_sql_path,
            "input_readiness": {
                "context_run_status": trigger_run.get("status"),
                "context_row_count": len(context_rows),
                "snapshot_run_status": snapshot_run.get("status"),
                "snapshot_row_count": len(snapshot_rows),
                "projection_row_count": len(projection_rows),
                "local_trigger_matched_candidates": sum(
                    1 for plan in local_plans if plan.get("output_event_type") == "TriggerMatched"
                ),
                "projection_trigger_matched_candidates": sum(
                    1 for plan in projection_plans if plan.get("output_event_type") == "TriggerMatched"
                ),
            },
            "no_db_write_proof": {
                "before_target_refs": before_refs,
                "after_target_refs": after_refs,
                "unchanged": before_refs == after_refs,
            },
            "lineage_boundary": {
                "n3_outbox_consumed": False,
                "common_event_inbox_written": False,
                "checkpoint_written": False,
                "n5_n6_entered": False,
                "worker_started": False,
                "n1_n2_n3_facts_modified": False,
                "n6_ui_v1_b_track_modified": False,
            },
        },
        created_at=generated_at,
        sample_limit=args.sample_limit,
    )
    report["quality"]["p0_count"] = 0 if before_refs == after_refs else 1
    if before_refs != after_refs:
        report["result"] = "BLOCKED"
        report["quality"]["items"].append(
            {
                "severity": "P0",
                "status": "failed",
                "gate_code": "n4_v4_corrected_dry_run_no_db_write_proof",
                "gate_name": "Dry-run target scoped row counts must remain unchanged",
                "expected_value": "before refs equal after refs",
                "actual_value": "changed",
            }
        )
    write_json(Path(args.json_report_path), report)
    write_text(Path(args.markdown_report_path), format_markdown(report))
    print_report(report, as_json=args.json)
    return 0 if report.get("result") == "DRY_RUN_PASS" and int(report["quality"]["p0_count"]) == 0 else 2


def capture_target_refs(dsn: str, execute_run_id: str) -> dict[str, int]:
    queries = {
        "common_trigger_run": ("SELECT count(*)::bigint AS n FROM common_trigger_run WHERE run_id = %s", (execute_run_id,)),
        "common_trigger_quality_item": (
            "SELECT count(*)::bigint AS n FROM common_trigger_quality_item WHERE run_id = %s",
            (execute_run_id,),
        ),
        "common_trigger_state": ("SELECT count(*)::bigint AS n FROM common_trigger_state WHERE run_id = %s", (execute_run_id,)),
        "common_trigger_match": ("SELECT count(*)::bigint AS n FROM common_trigger_match WHERE run_id = %s", (execute_run_id,)),
        "common_event_outbox": (
            "SELECT count(*)::bigint AS n FROM common_event_outbox WHERE source_run_id = %s",
            (execute_run_id,),
        ),
        "common_event_inbox": (
            "SELECT count(*)::bigint AS n FROM common_event_inbox WHERE raw_json::text LIKE %s",
            (f"%{execute_run_id}%",),
        ),
        "common_event_consumer_checkpoint": (
            "SELECT count(*)::bigint AS n FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE %s",
            (f"%{execute_run_id}%",),
        ),
    }
    output: dict[str, int] = {}
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_20260605_corrected_dry_run_capture_refs",
        source_run_id=execute_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for key, (sql, params) in queries.items():
            cur.execute(sql, params)
            output[key] = int((cur.fetchone() or {}).get("n") or 0)
    return output


def format_markdown(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    blocked = report.get("blocked_counts_by_reason") or {}
    distribution = report.get("compliant_distribution") or {}
    input_readiness = report.get("input_readiness") or {}
    proof = report.get("no_db_write_proof") or {}
    reason_lines = [f"  - {key}: {value}" for key, value in blocked.items()] or ["  - none: 0"]
    sample = report.get("compliant_trigger_matched_sample") or []
    sample_lines = [
        "  - "
        + ", ".join(
            [
                f"identity_key={row.get('identity_key')}",
                f"condition_key={row.get('condition_key')}",
                f"signal_type={row.get('signal_type')}",
                f"trigger_price={row.get('trigger_price')}",
                f"trigger_time={row.get('trigger_time')}",
                f"triggered_periods={row.get('triggered_periods')}",
            ]
        )
        for row in sample[:5]
    ] or ["  - none"]
    return "\n".join(
        [
            "# N4 20260605 V4 Corrected Dry-Run",
            "",
            f"- result: {report.get('result')}",
            f"- generated_at: {report.get('generated_at')}",
            f"- execute_run_id: {report.get('execute_run_id')}",
            f"- context_run_id: {report.get('trigger_context_run_id')}",
            f"- snapshot_run_id: {report.get('snapshot_run_id')}",
            f"- projection_run_id: {report.get('projection_run_id')}",
            "",
            "## Input Readiness",
            "",
            f"- context_run_status: {input_readiness.get('context_run_status')}",
            f"- context_row_count: {input_readiness.get('context_row_count')}",
            f"- snapshot_run_status: {input_readiness.get('snapshot_run_status')}",
            f"- snapshot_row_count: {input_readiness.get('snapshot_row_count')}",
            f"- projection_row_count: {input_readiness.get('projection_row_count')}",
            f"- local_trigger_matched_candidates: {input_readiness.get('local_trigger_matched_candidates')}",
            f"- projection_trigger_matched_candidates: {input_readiness.get('projection_trigger_matched_candidates')}",
            "",
            "## Strict Guard Summary",
            "",
            f"- candidate_plans_before_strict_guard: {report.get('candidate_plans_before_strict_guard')}",
            f"- persisted_plans_after_strict_guard: {report.get('persisted_plans_after_strict_guard')}",
            f"- compliant_count: {report.get('compliant_count')}",
            f"- blocked_count: {report.get('blocked_count')}",
            f"- P0/P1/P2: {quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
            "",
            "## Blocked Counts By Reason",
            "",
            *reason_lines,
            "",
            "## Compliant Distribution",
            "",
            f"- by_signal_type: {distribution.get('by_signal_type')}",
            f"- by_trigger_mark_candidate: {distribution.get('by_trigger_mark_candidate')}",
            f"- by_match_basis: {distribution.get('by_match_basis')}",
            "",
            "## Compliant TriggerMatched Sample",
            "",
            *sample_lines,
            "",
            "## Boundary Proof",
            "",
            f"- trigger_price_source_proof: {report.get('trigger_price_source_proof')}",
            f"- time_boundary_proof: {report.get('time_boundary_proof')}",
            f"- full_blocked_proof: {report.get('full_blocked_proof')}",
            f"- n5_entry_eligibility_proof: {report.get('n5_entry_eligibility_proof')}",
            f"- no_db_write_proof: {proof}",
            "",
            "## Next Gate",
            "",
            f"- execute_preflight_could_pass: {report.get('execute_preflight_could_pass')}",
            f"- next_gate: {report.get('next_gate')}",
            "",
        ]
    )


def print_report(report: Mapping[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    quality = report.get("quality") or {}
    counts = Counter(report.get("blocked_counts_by_reason") or {})
    print(
        "\n".join(
            [
                "N4 20260605 v4 corrected dry-run",
                f"  result={report.get('result')}",
                f"  candidate_before_guard={report.get('candidate_plans_before_strict_guard')}",
                f"  compliant_count={report.get('compliant_count')}",
                f"  blocked_count={report.get('blocked_count')}",
                f"  blocked_counts_by_reason={dict(counts)}",
                f"  P0/P1/P2={quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
                f"  execute_preflight_could_pass={report.get('execute_preflight_could_pass')}",
                f"  next_gate={report.get('next_gate')}",
            ]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
