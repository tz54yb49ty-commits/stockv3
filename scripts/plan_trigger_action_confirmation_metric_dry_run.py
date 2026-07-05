#!/usr/bin/env python3
"""Build N4 action-confirmation metric dry-run/preflight reports.

This runner is read-only. It consumes N3 standard action-confirmation metric
facts and local N4 context to produce would-trigger / would-pending plans. It
rejects --execute and never writes trigger facts, outbox, inbox, checkpoint
rows, starts workers, or pulls market data.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.trigger.action_confirmation_metric_matcher import (
    DEFAULT_FOR_TRADE_DATE,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MARKDOWN_REPORT_PATH,
    DEFAULT_PREFLIGHT_JSON_PATH,
    DEFAULT_PREFLIGHT_MARKDOWN_PATH,
    DEFAULT_PROJECTION_RUN_ID,
    DEFAULT_SOURCE_CONDITION_RUN_ID,
    DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
    DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
    DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    run_action_confirmation_metric_dry_run,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N4 action-confirmation metric dry-run/preflight artifacts.")
    parser.add_argument("--execute", action="store_true", help="Rejected. This runner is read-only.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_TRIGGER_CONTEXT_RUN_ID)
    parser.add_argument("--projection-run-id", default=DEFAULT_PROJECTION_RUN_ID)
    parser.add_argument("--source-condition-run-id", default=DEFAULT_SOURCE_CONDITION_RUN_ID)
    parser.add_argument("--source-subscription-run-id", default=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID)
    parser.add_argument("--source-snapshot-run-id", default=DEFAULT_SOURCE_SNAPSHOT_RUN_ID)
    parser.add_argument("--for-trade-date", default=DEFAULT_FOR_TRADE_DATE)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--preflight-json-path", default=DEFAULT_PREFLIGHT_JSON_PATH)
    parser.add_argument("--preflight-markdown-path", default=DEFAULT_PREFLIGHT_MARKDOWN_PATH)
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--json", action="store_true", help="Print full report/preflight JSON.")
    args = parser.parse_args()

    if args.execute:
        blocked = {
            "result": "BLOCKED",
            "stage": "N4 action-confirmation metric dry-run",
            "layer_role": "N4_trigger",
            "reason": "This runner is read-only and rejects --execute.",
            "writes_database": False,
            "writes_outbox": False,
            "consumes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "worker_started": False,
        }
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return 2

    report, preflight = run_action_confirmation_metric_dry_run(
        dsn=args.dsn,
        trigger_context_run_id=args.trigger_context_run_id,
        projection_run_id=args.projection_run_id,
        source_condition_run_id=args.source_condition_run_id,
        source_subscription_run_id=args.source_subscription_run_id,
        source_snapshot_run_id=args.source_snapshot_run_id,
        for_trade_date=args.for_trade_date,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        preflight_json_path=args.preflight_json_path,
        preflight_markdown_path=args.preflight_markdown_path,
        sample_limit=args.sample_limit,
    )
    if args.json:
        print(json.dumps({"dry_run": report, "preflight": preflight}, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report, preflight))
    return 0 if report.get("result") == "DRY_RUN_PASS" and preflight.get("result") == "PREFLIGHT_PASS" else 2


def format_summary(report: dict, preflight: dict) -> str:
    summary = report.get("summary") or {}
    quality = report.get("quality") or {}
    planned = preflight.get("planned_counts") or {}
    return "\n".join(
        [
            f"dry_run={report.get('result')}",
            f"preflight={preflight.get('result')}",
            f"projection_run_id={report.get('projection_run_id')}",
            f"trigger_context_run_id={report.get('trigger_context_run_id')}",
            f"candidate_count={summary.get('candidate_count', 0)}",
            f"would_trigger={summary.get('would_trigger_count', 0)}",
            f"would_pending={summary.get('would_pending_count', 0)}",
            f"quality_only={summary.get('quality_only_count', 0)}",
            f"TriggerMatched={planned.get('TriggerMatched', 0)}",
            f"TriggerPendingMarketData={planned.get('TriggerPendingMarketData', 0)}",
            f"P0/P1/P2={quality.get('p0_count', 0)}/{quality.get('p1_count', 0)}/{quality.get('p2_count', 0)}",
            "writes_database=false",
            "business_execute_allowed=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
