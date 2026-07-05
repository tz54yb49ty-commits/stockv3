#!/usr/bin/env python3
"""Run N4 real projection matcher preflight or execute.

Default use is explicit preflight with --preflight-only. A real run-once
execute is blocked unless both --execute and --user-confirmed are supplied.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.projection_matcher import DEFAULT_CONTEXT_RUN_ID, DEFAULT_PROJECTION_RUN_ID
from ashare_v3.trigger.projection_matcher_execute import (
    DEFAULT_CONSUMER_NAME,
    DEFAULT_EXECUTE_RUN_ID,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MD_REPORT_PATH,
    DEFAULT_ROLLBACK_SQL_PATH,
    DEFAULT_SNAPSHOT_RUN_ID,
    ProjectionMatcherExecuteError,
    run_projection_matcher_execute_preflight,
    run_projection_matcher_once,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="N4 projection matcher run-once preflight/execute.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute-run-id", default=DEFAULT_EXECUTE_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_CONTEXT_RUN_ID)
    parser.add_argument("--projection-run-id", default=DEFAULT_PROJECTION_RUN_ID)
    parser.add_argument("--snapshot-run-id", default=DEFAULT_SNAPSHOT_RUN_ID)
    parser.add_argument("--consumer-name", default=DEFAULT_CONSUMER_NAME)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--dry-run-report-path", default=None)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--preflight-only", action="store_true", help="Build read-only execute preflight artifacts.")
    parser.add_argument("--execute", action="store_true", help="Actually write N4 inbox/checkpoint/facts/outbox.")
    parser.add_argument("--user-confirmed", action="store_true", help="Second explicit confirmation required for execute.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    try:
        if args.preflight_only:
            report = run_projection_matcher_execute_preflight(
                dsn=args.dsn,
                execute_run_id=args.execute_run_id,
                trigger_context_run_id=args.trigger_context_run_id,
                projection_run_id=args.projection_run_id,
                snapshot_run_id=args.snapshot_run_id,
                consumer_name=args.consumer_name,
                json_report_path=args.json_report_path,
                markdown_report_path=args.markdown_report_path,
                rollback_sql_path=args.rollback_sql_path,
                dry_run_report_path=args.dry_run_report_path,
                sample_limit=args.sample_limit,
            )
        else:
            report = run_projection_matcher_once(
                dsn=args.dsn,
                execute=args.execute,
                user_confirmed=args.user_confirmed,
                execute_run_id=args.execute_run_id,
                trigger_context_run_id=args.trigger_context_run_id,
                projection_run_id=args.projection_run_id,
                snapshot_run_id=args.snapshot_run_id,
                consumer_name=args.consumer_name,
                json_report_path=args.json_report_path,
                markdown_report_path=args.markdown_report_path,
                rollback_sql_path=args.rollback_sql_path,
                dry_run_report_path=args.dry_run_report_path,
                sample_limit=args.sample_limit,
            )
    except ProjectionMatcherExecuteError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    quality = report.get("quality") or {}
    return 0 if int(quality.get("p0_count") or 0) == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report.get("quality") or {}
    summary = report.get("execute_plan_summary") or {}
    return "\n".join(
        [
            "N4 projection matcher run-once",
            f"  result={report.get('result')}",
            f"  layer_role={report.get('layer_role')}",
            f"  execute_run_id={report.get('execute_run_id')}",
            f"  trigger_context_run_id={report.get('trigger_context_run_id')}",
            f"  projection_run_id={report.get('projection_run_id')}",
            f"  snapshot_run_id={report.get('snapshot_run_id')}",
            f"  accepted_source_event_count={summary.get('accepted_source_event_count')}",
            f"  matched_output_count={summary.get('matched_output_count')}",
            f"  pending_output_count={summary.get('pending_output_count')}",
            f"  inbox_write_plan_count={summary.get('inbox_write_plan_count')}",
            f"  checkpoint_write_plan_count={summary.get('checkpoint_write_plan_count')}",
            f"  rollback_sql_path={report.get('rollback_sql_path')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
