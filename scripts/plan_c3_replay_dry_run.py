#!/usr/bin/env python3
"""Build N4 C3 MinuteBarClosed replay dry-run artifacts.

This script is read-only. It filters the explicitly allowlisted C3
MinuteBarClosed outbox stream, compares it with local N4 context and the
current N4 projection matcher result, and writes report files only.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.c3_replay_plan import (
    DEFAULT_ALLOWED_C3_RUN_ID,
    DEFAULT_C2B_RUN_ID,
    DEFAULT_CONTEXT_RUN_ID,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MD_REPORT_PATH,
    DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID,
    DEFAULT_REPLAY_RUN_ID,
    C3ReplayPlanError,
    run_c3_replay_dry_run,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="N4 C3 MinuteBarClosed replay dry-run planner.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--allowed-c3-run-id", default=DEFAULT_ALLOWED_C3_RUN_ID)
    parser.add_argument("--c2b-run-id", default=DEFAULT_C2B_RUN_ID)
    parser.add_argument("--replay-run-id", default=DEFAULT_REPLAY_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_CONTEXT_RUN_ID)
    parser.add_argument("--projection-execute-run-id", default=DEFAULT_N4_PROJECTION_EXECUTE_RUN_ID)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MD_REPORT_PATH)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    try:
        report = run_c3_replay_dry_run(
            dsn=args.dsn,
            allowed_c3_run_id=args.allowed_c3_run_id,
            c2b_run_id=args.c2b_run_id,
            replay_run_id=args.replay_run_id,
            trigger_context_run_id=args.trigger_context_run_id,
            projection_execute_run_id=args.projection_execute_run_id,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            sample_limit=args.sample_limit,
        )
    except C3ReplayPlanError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if int((report.get("quality") or {}).get("p0_count") or 0) == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report.get("quality") or {}
    classification = report.get("classification_summary") or {}
    diff = report.get("replay_diff_summary") or {}
    return "\n".join(
        [
            "N4 C3 MinuteBarClosed replay dry-run",
            f"  result={report.get('result')}",
            f"  layer_role={report.get('layer_role')}",
            f"  replay_run_id={report.get('replay_run_id')}",
            f"  allowed_c3_run_id={report.get('allowed_c3_run_id')}",
            f"  c2b_run_id={report.get('c2b_run_id')}",
            f"  trigger_context_run_id={report.get('trigger_context_run_id')}",
            f"  original_n4_projection_execute_run_id={report.get('original_n4_projection_execute_run_id')}",
            f"  candidate_count={classification.get('candidate_count')}",
            f"  by_classification={classification.get('by_classification')}",
            f"  replay_diff_summary={diff}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
