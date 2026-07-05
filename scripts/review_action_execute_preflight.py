#!/usr/bin/env python3
"""Run N5-R4 execute preflight / contract review.

The script is read-only against PostgreSQL and writes report files only. It
does not consume N4 outbox, update inbox/checkpoint, write action facts, write
N5 outbox rows, enter N6, start workers, or touch the old system.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.action.consumer_dry_run import DEFAULT_N5_1_CONSUMER_NAME
from ashare_v3.action.execute_preflight import (
    DEFAULT_N5_R4_EXECUTE_PREFLIGHT_JSON_REPORT_PATH,
    DEFAULT_N5_R4_EXECUTE_PREFLIGHT_MD_REPORT_PATH,
    run_action_execute_preflight,
)
from ashare_v3.action.run_once_dry_run import (
    DEFAULT_N5_R4_ACTION_RUN_ID,
    DEFAULT_N5_R4_BASELINE_REPORT_PATH,
    DEFAULT_N5_R4_JSON_REPORT_PATH,
    DEFAULT_N5_R4_TRIGGER_RUN_ID,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Run N5-R4 action execute preflight contract review.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-run-id", default=DEFAULT_N5_R4_TRIGGER_RUN_ID)
    parser.add_argument("--action-run-id", default=DEFAULT_N5_R4_ACTION_RUN_ID)
    parser.add_argument("--consumer-name", default=DEFAULT_N5_1_CONSUMER_NAME)
    parser.add_argument("--n4-execute-report-path", default=DEFAULT_N5_R4_BASELINE_REPORT_PATH)
    parser.add_argument("--n5-dry-run-report-path", default=DEFAULT_N5_R4_JSON_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N5_R4_EXECUTE_PREFLIGHT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N5_R4_EXECUTE_PREFLIGHT_MD_REPORT_PATH)
    parser.add_argument("--expected-read-event-count", type=int, default=26652)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_action_execute_preflight(
        dsn=args.dsn,
        trigger_run_id=args.trigger_run_id,
        action_run_id=args.action_run_id,
        consumer_name=args.consumer_name,
        n4_execute_report_path=args.n4_execute_report_path,
        n5_dry_run_report_path=args.n5_dry_run_report_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        expected_read_event_count=args.expected_read_event_count,
        sample_limit=args.sample_limit,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    fresh = report["fresh_plan_summary"]
    event_mapping = report["event_type_mapping"]
    trace_mapping = report["trace_mapping"]
    quality = report["quality"]
    return "\n".join(
        [
            "action execute preflight",
            f"  stage={report['stage']}",
            f"  source_trigger_run_id={report['source_trigger_run_id']}",
            f"  read_event_count={fresh['consumer_plan_summary']['read_event_count']}",
            f"  event_mapping={event_mapping['by_signal_type_and_output_event_type']}",
            f"  mapping_violation_count={event_mapping['mapping_violation_count']}",
            f"  trace_present_in_action_fact_plan_count={trace_mapping['trace_present_in_action_fact_plan_count']}",
            f"  trace_missing_in_action_fact_plan_count={trace_mapping['trace_missing_in_action_fact_plan_count']}",
            f"  dedicated_period_trace_column_count={trace_mapping['dedicated_period_trace_column_count']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            f"  allow_execute={report['allow_execute']}",
            "  writes_performed=false n4_outbox_consumed=false action_fact_written=false n5_outbox_written=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
