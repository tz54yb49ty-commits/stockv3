#!/usr/bin/env python3
"""Run N5-1 N4 event consumer dry-run.

This script reads N4 outbox rows in a read-only transaction and writes report
files only. It does not consume outbox rows, update inbox/checkpoint, write
action facts, pull market data, start workers, or enter the user layer.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.action.consumer_dry_run import (
    DEFAULT_N5_1_ACTION_RUN_ID,
    DEFAULT_N5_1_CONSUMER_NAME,
    DEFAULT_N5_1_JSON_REPORT_PATH,
    DEFAULT_N5_1_MD_REPORT_PATH,
    DEFAULT_TRIGGER_RUN_ID,
    run_action_consumer_dry_run,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Run N5-1 action consumer dry-run from N4 outbox.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-run-id", default=DEFAULT_TRIGGER_RUN_ID)
    parser.add_argument("--action-run-id", default=DEFAULT_N5_1_ACTION_RUN_ID)
    parser.add_argument("--consumer-name", default=DEFAULT_N5_1_CONSUMER_NAME)
    parser.add_argument("--json-report-path", default=DEFAULT_N5_1_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N5_1_MD_REPORT_PATH)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    report = run_action_consumer_dry_run(
        dsn=args.dsn,
        trigger_run_id=args.trigger_run_id,
        action_run_id=args.action_run_id,
        consumer_name=args.consumer_name,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        sample_limit=args.sample_limit,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    consumer = report["consumer_plan_summary"]
    candidates = report["action_candidate_summary"]
    quality = report["quality"]
    return "\n".join(
        [
            "action consumer dry-run",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  consumer_name={report['consumer_name']}",
            f"  source_trigger_run_id={report['source_trigger_run_id']}",
            f"  read_event_count={consumer['read_event_count']}",
            f"  planned_receive_count={consumer['planned_receive_count']}",
            f"  skipped_count={consumer['skipped_count']}",
            f"  checkpoint_write_plan_count={consumer['checkpoint_write_plan_count']}",
            f"  would_insert_inbox_count={consumer['would_insert_inbox_count']}",
            f"  would_update_checkpoint_count={consumer['would_update_checkpoint_count']}",
            f"  action_candidate_count={candidates['action_candidate_count']}",
            f"  quality_plan_count={candidates['quality_plan_count']}",
            f"  pending_generates_action_event_count={candidates['pending_generates_action_event_count']}",
            f"  buy_hint_candidate_count={candidates['buy_hint_candidate_count']}",
            f"  sell_hint_candidate_count={candidates['sell_hint_candidate_count']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  writes_performed=false common_event_inbox_updated=false consumer_checkpoint_updated=false",
            "  n4_outbox_status_updated=false action_fact_written=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
