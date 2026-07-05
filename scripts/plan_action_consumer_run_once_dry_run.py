#!/usr/bin/env python3
"""Run N5-5 action consumer run-once dry-run.

This script reads N4 outbox rows in a read-only transaction and writes report
files only. It does not update inbox/checkpoint rows, write action facts,
write common_action_event rows, write N5 outbox rows, pull market data, start
workers, or enter N6/user/voice/sim/mobile/true-trade flows.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.action.preflight import DEFAULT_TRIGGER_RUN_ID
from ashare_v3.action.run_once_dry_run import (
    CURRENT_REAL_N4_SOURCE_RUN_ALLOWLIST,
    CURRENT_REAL_N4_SOURCE_RUN_ID,
    DEFAULT_N5_CURRENT_REAL_ACTION_RUN_ID,
    DEFAULT_N5_CURRENT_REAL_BASELINE_REPORT_PATH,
    DEFAULT_N5_CURRENT_REAL_JSON_REPORT_PATH,
    DEFAULT_N5_CURRENT_REAL_MD_REPORT_PATH,
    DEFAULT_N5_CURRENT_REAL_ROLLBACK_SQL_PATH,
    DEFAULT_N5_5_ACTION_RUN_ID,
    DEFAULT_N5_5_BASELINE_REPORT_PATH,
    DEFAULT_N5_5_JSON_REPORT_PATH,
    DEFAULT_N5_5_MD_REPORT_PATH,
    DEFAULT_N5_1_CONSUMER_NAME,
    SYNTHETIC_N4_SOURCE_RUN_DENYLIST,
    run_action_consumer_run_once_dry_run,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Run N5-5 action consumer run-once dry-run from N4 outbox.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-run-id", default=DEFAULT_TRIGGER_RUN_ID)
    parser.add_argument("--action-run-id", default=DEFAULT_N5_5_ACTION_RUN_ID)
    parser.add_argument("--consumer-name", default=DEFAULT_N5_1_CONSUMER_NAME)
    parser.add_argument("--baseline-report-path", default=DEFAULT_N5_5_BASELINE_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N5_5_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_N5_5_MD_REPORT_PATH)
    parser.add_argument("--stage", default="N5-5")
    parser.add_argument("--expected-read-event-count", type=int)
    parser.add_argument("--require-period-trigger-baseline-trace", action="store_true")
    parser.add_argument("--current-real", action="store_true", help="Use the registered current real N4 projection matcher source_run_id with allowlist/denylist guards.")
    parser.add_argument("--rollback-sql-path")
    parser.add_argument("--sample-limit", type=int, default=80)
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    allowed_source_run_ids = None
    denied_source_run_ids = None
    rollback_sql_path = args.rollback_sql_path
    if args.current_real:
        args.trigger_run_id = CURRENT_REAL_N4_SOURCE_RUN_ID
        args.action_run_id = DEFAULT_N5_CURRENT_REAL_ACTION_RUN_ID
        args.baseline_report_path = DEFAULT_N5_CURRENT_REAL_BASELINE_REPORT_PATH
        args.json_report_path = DEFAULT_N5_CURRENT_REAL_JSON_REPORT_PATH
        args.markdown_report_path = DEFAULT_N5_CURRENT_REAL_MD_REPORT_PATH
        args.stage = "N5-current-real"
        args.expected_read_event_count = 764
        args.require_period_trigger_baseline_trace = True
        allowed_source_run_ids = CURRENT_REAL_N4_SOURCE_RUN_ALLOWLIST
        denied_source_run_ids = SYNTHETIC_N4_SOURCE_RUN_DENYLIST
        rollback_sql_path = rollback_sql_path or DEFAULT_N5_CURRENT_REAL_ROLLBACK_SQL_PATH

    report = run_action_consumer_run_once_dry_run(
        dsn=args.dsn,
        trigger_run_id=args.trigger_run_id,
        action_run_id=args.action_run_id,
        consumer_name=args.consumer_name,
        baseline_report_path=args.baseline_report_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        stage=args.stage,
        expected_read_event_count=args.expected_read_event_count,
        require_period_trigger_baseline_trace=args.require_period_trigger_baseline_trace,
        allowed_source_run_ids=allowed_source_run_ids,
        denied_source_run_ids=denied_source_run_ids,
        rollback_sql_path=rollback_sql_path,
        sample_limit=args.sample_limit,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    consumer = report["consumer_plan_summary"]
    outbox = report["outbox_summary"]
    action_plan = report["action_write_plan_summary"]
    output_plan = report["output_event_plan_summary"]
    trace = report["period_trigger_baseline_trace_summary"]
    source_run = report["source_run_id_summary"]
    quality = report["quality"]
    baseline = report["baseline_comparison"]
    return "\n".join(
        [
            "action consumer run-once dry-run",
            f"  stage={report['stage']}",
            f"  layer_role={report['layer_role']}",
            f"  consumer_name={report['consumer_name']}",
            f"  source_trigger_run_id={report['source_trigger_run_id']}",
            f"  only_expected_source_run_id={source_run['only_expected_source_run_id']}",
            f"  read_event_count={consumer['read_event_count']}",
            f"  baseline_read_event_count={baseline.get('baseline_read_event_count')}",
            f"  baseline_explainable={baseline['explainable']}",
            f"  TriggerMatched={outbox['matched_count']}",
            f"  TriggerPendingMarketData={outbox['pending_count']}",
            f"  TriggerStateChanged={outbox['state_changed_count']}",
            f"  planned_action_fact_count={action_plan['planned_action_fact_count']}",
            f"  quality_plan_only_count={action_plan['quality_plan_only_count']}",
            f"  pending_action_fact_plan_count={action_plan['pending_action_fact_plan_count']}",
            f"  buy_hint_planned_action_fact_count={action_plan['buy_hint_planned_action_fact_count']}",
            f"  sell_hint_planned_action_fact_count={action_plan['sell_hint_planned_action_fact_count']}",
            f"  period_trigger_baseline_trace_present={trace['present_count']}",
            f"  period_trigger_baseline_trace_missing={trace['missing_count']}",
            f"  by_target_action_fact_table={action_plan['by_target_action_fact_table']}",
            f"  output_event_plan={output_plan['by_event_type']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            "  writes_performed=false common_event_inbox_updated=false consumer_checkpoint_updated=false",
            "  action_fact_written=false action_event_written=false n5_outbox_written=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
