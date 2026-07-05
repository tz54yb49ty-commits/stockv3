#!/usr/bin/env python3
"""Run N4 local trigger dry-run from B1 snapshot facts and N4 context."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.local_trigger_dry_run import (
    DEFAULT_20260528_CONTEXT_RUN_ID,
    DEFAULT_20260528_JSON_REPORT_PATH,
    DEFAULT_20260528_MD_REPORT_PATH,
    DEFAULT_20260528_ROLLBACK_SQL_PATH,
    DEFAULT_20260528_SNAPSHOT_RUN_ID,
    LOCAL_DRY_RUN_STAGE,
    run_local_trigger_dry_run,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    report = run_local_trigger_dry_run(
        dsn=args.dsn,
        trigger_context_run_id=args.trigger_context_run_id,
        snapshot_run_id=args.snapshot_run_id,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        rollback_sql_path=args.rollback_sql_path,
        sample_limit=args.sample_limit,
        stage=args.stage,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if int(report["quality"]["p0_count"]) == 0 else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan N4 local trigger outputs from N4 context and B1 snapshot facts.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_20260528_CONTEXT_RUN_ID)
    parser.add_argument("--snapshot-run-id", default=DEFAULT_20260528_SNAPSHOT_RUN_ID)
    parser.add_argument("--json-report-path", default=DEFAULT_20260528_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_20260528_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_20260528_ROLLBACK_SQL_PATH)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--stage", default=LOCAL_DRY_RUN_STAGE)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    summary = report["summary"]
    abnormal = report["abnormal_rows"]
    return "\n".join(
        [
            "local trigger dry-run",
            f"  result={report['result']}",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  trigger_context_run_id={report['trigger_context_run_id']}",
            f"  snapshot_run_id={report['snapshot_run_id']}",
            f"  context_candidate_count={report['context_candidate_count']}",
            f"  candidate_count={summary['candidate_count']}",
            f"  matched_plan_count={summary['matched_plan_count']}",
            f"  pending_plan_count={summary['pending_plan_count']}",
            f"  by_signal_type={summary['by_signal_type']}",
            f"  matched_by_signal_type={summary['matched_by_signal_type']}",
            f"  pending_by_signal_type={summary['pending_by_signal_type']}",
            f"  planned_output_event_types={summary['planned_output_event_types']}",
            f"  abnormal_rows={abnormal}",
            f"  scoped_event_refs={report['scoped_event_refs']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  writes_performed=false outbox_consumed=false inbox_written=false checkpoint_written=false",
            "  trigger_match_written=false event_outbox_written=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
