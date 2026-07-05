#!/usr/bin/env python3
"""Run N4 C3 replay audit-only preflight or execute.

Default use is read-only preflight. Business execute is blocked unless both
--execute and --user-confirmed are supplied by a later final gate.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.c3_replay_audit_execute import (
    DEFAULT_ALLOWED_C3_RUN_ID,
    DEFAULT_C2B_RUN_ID,
    DEFAULT_CONTEXT_RUN_ID,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MD_REPORT_PATH,
    DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
    DEFAULT_N5_ACTION_EXECUTE_RUN_ID,
    DEFAULT_REPLAY_RUN_ID,
    DEFAULT_ROLLBACK_SQL_PATH,
    C3ReplayAuditExecuteError,
    run_c3_replay_audit_execute_preflight,
    run_c3_replay_audit_once,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="N4 C3 replay audit-only preflight/execute.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--replay-run-id", default=DEFAULT_REPLAY_RUN_ID)
    parser.add_argument("--allowed-c3-run-id", default=DEFAULT_ALLOWED_C3_RUN_ID)
    parser.add_argument("--c2b-run-id", default=DEFAULT_C2B_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_CONTEXT_RUN_ID)
    parser.add_argument("--projection-execute-run-id", default=DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID)
    parser.add_argument("--source-n5-action-run-id", default=DEFAULT_N5_ACTION_EXECUTE_RUN_ID)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--preflight-only", action="store_true", help="Build read-only execute preflight artifacts.")
    parser.add_argument("--execute", action="store_true", help="Actually write N4 replay audit rows.")
    parser.add_argument("--user-confirmed", action="store_true", help="Second explicit confirmation required for execute.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    try:
        if args.preflight_only:
            report = run_c3_replay_audit_execute_preflight(
                dsn=args.dsn,
                replay_run_id=args.replay_run_id,
                allowed_c3_run_id=args.allowed_c3_run_id,
                c2b_run_id=args.c2b_run_id,
                trigger_context_run_id=args.trigger_context_run_id,
                projection_execute_run_id=args.projection_execute_run_id,
                source_n5_action_run_id=args.source_n5_action_run_id,
                json_report_path=args.json_report_path,
                markdown_report_path=args.markdown_report_path,
                rollback_sql_path=args.rollback_sql_path,
                sample_limit=args.sample_limit,
            )
        else:
            report = run_c3_replay_audit_once(
                dsn=args.dsn,
                execute=args.execute,
                user_confirmed=args.user_confirmed,
                replay_run_id=args.replay_run_id,
                allowed_c3_run_id=args.allowed_c3_run_id,
                c2b_run_id=args.c2b_run_id,
                trigger_context_run_id=args.trigger_context_run_id,
                projection_execute_run_id=args.projection_execute_run_id,
                source_n5_action_run_id=args.source_n5_action_run_id,
                json_report_path=args.json_report_path,
                markdown_report_path=args.markdown_report_path,
                rollback_sql_path=args.rollback_sql_path,
                sample_limit=args.sample_limit,
            )
    except C3ReplayAuditExecuteError as exc:
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
    summary = report.get("audit_plan_summary") or {}
    return "\n".join(
        [
            "N4 C3 replay audit-only",
            f"  result={report.get('result')}",
            f"  layer_role={report.get('layer_role')}",
            f"  replay_run_id={report.get('replay_run_id')}",
            f"  allowed_c3_run_id={report.get('allowed_c3_run_id')}",
            f"  c2b_run_id={report.get('c2b_run_id')}",
            f"  source_n4_projection_run_id={report.get('source_n4_projection_run_id')}",
            f"  audit_total={summary.get('total')}",
            f"  by_classification={summary.get('by_classification')}",
            f"  rollback_sql_path={report.get('rollback_sql_path')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
