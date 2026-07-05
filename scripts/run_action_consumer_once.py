#!/usr/bin/env python3
"""Run N5 canonical action consumer once.

This entry point is guarded by a double confirmation. Without both --execute
and --user-confirmed it only emits a blocked contract and performs no database
writes. It never starts a worker and never enters N6, voice, sim, mobile, or
real-trade flows.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.action.consumer_dry_run import DEFAULT_N5_1_CONSUMER_NAME
from ashare_v3.action.execute import (
    LATEST_CANONICAL_DRY_RUN_JSON_REPORT_PATH,
    LATEST_CANONICAL_EXPECTED_PENDING_EVENT_COUNT,
    LATEST_CANONICAL_EXECUTE_REPORT_JSON_PATH,
    LATEST_CANONICAL_EXECUTE_REPORT_MD_PATH,
    LATEST_CANONICAL_N4_SOURCE_RUN_ID,
    LATEST_CANONICAL_N5_EXECUTE_ACTION_RUN_ID,
    LATEST_CANONICAL_ROLLBACK_SQL_PATH,
    run_consumption_only_smoke_once,
    run_semantic_action_smoke_once,
    run_action_consumer_once,
)
from check_condition_source_ready import DEFAULT_DSN


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run N5 canonical action consumer once.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--action-run-id", default=LATEST_CANONICAL_N5_EXECUTE_ACTION_RUN_ID)
    parser.add_argument(
        "--source-run-id",
        "--source-trigger-run-id",
        dest="source_run_id",
        default=LATEST_CANONICAL_N4_SOURCE_RUN_ID,
    )
    parser.add_argument("--consumer-name", default=DEFAULT_N5_1_CONSUMER_NAME)
    parser.add_argument(
        "--json-report-path",
        "--report-path",
        dest="json_report_path",
        default=LATEST_CANONICAL_EXECUTE_REPORT_JSON_PATH,
    )
    parser.add_argument("--markdown-report-path", default=LATEST_CANONICAL_EXECUTE_REPORT_MD_PATH)
    parser.add_argument("--rollback-sql-path", default=LATEST_CANONICAL_ROLLBACK_SQL_PATH)
    parser.add_argument("--baseline-report-path", default=LATEST_CANONICAL_DRY_RUN_JSON_REPORT_PATH)
    parser.add_argument("--expected-read-event-count", type=int, default=LATEST_CANONICAL_EXPECTED_PENDING_EVENT_COUNT)
    parser.add_argument("--allow-source-run-id", action="append", default=None)
    parser.add_argument("--deny-source-run-id", action="append", default=None)
    parser.add_argument(
        "--consumption-only-smoke",
        action="store_true",
        help="Run bounded N5 worker smoke that writes only run/quality/inbox/checkpoint.",
    )
    parser.add_argument(
        "--semantic-action-smoke",
        action="store_true",
        help="Run bounded N5 semantic action smoke with action confirmation writes.",
    )
    parser.add_argument("--smoke-run-id", default=None)
    parser.add_argument("--metric-run-id", default=None)
    parser.add_argument("--source-event-type", dest="source_event_types", action="append", default=None)
    parser.add_argument("--exclude-event-id", dest="excluded_event_ids", action="append", default=None)
    parser.add_argument(
        "--current-only-trigger-matched",
        action="store_true",
        help="For semantic action smoke, consume only TriggerMatched rows whose trigger state is still current matched.",
    )
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--max-runtime-seconds", type=int, default=None)
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=None)
    parser.add_argument("--status-json", default=None)
    parser.add_argument("--stop-file", default=None)
    parser.add_argument("--execute", action="store_true", help="Actually write N5 action facts/events/inbox/checkpoint.")
    parser.add_argument("--user-confirmed", action="store_true", help="Second human confirmation required for execute.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.semantic_action_smoke:
        report = run_semantic_action_smoke_once(
            dsn=args.dsn,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            smoke_run_id=args.smoke_run_id,
            source_trigger_run_id=args.source_run_id,
            consumer_name=args.consumer_name,
            source_event_types=args.source_event_types,
            excluded_event_ids=args.excluded_event_ids,
            current_only_trigger_matched=args.current_only_trigger_matched,
            metric_run_id=args.metric_run_id,
            max_events=args.max_events,
            max_runtime_seconds=args.max_runtime_seconds,
            heartbeat_interval_seconds=args.heartbeat_interval_seconds,
            rollback_sql_path=args.rollback_sql_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            status_json_path=args.status_json,
            stop_file_path=args.stop_file,
        )
    elif args.consumption_only_smoke:
        report = run_consumption_only_smoke_once(
            dsn=args.dsn,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            smoke_run_id=args.smoke_run_id,
            source_trigger_run_id=args.source_run_id,
            consumer_name=args.consumer_name,
            source_event_types=args.source_event_types,
            max_events=args.max_events,
            max_runtime_seconds=args.max_runtime_seconds,
            heartbeat_interval_seconds=args.heartbeat_interval_seconds,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            status_json_path=args.status_json,
            stop_file_path=args.stop_file,
        )
    else:
        report = run_action_consumer_once(
            dsn=args.dsn,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            action_run_id=args.action_run_id,
            source_trigger_run_id=args.source_run_id,
            consumer_name=args.consumer_name,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            rollback_sql_path=args.rollback_sql_path,
            allowed_source_run_ids=args.allow_source_run_id,
            denied_source_run_ids=args.deny_source_run_id,
            baseline_report_path=args.baseline_report_path,
            expected_read_event_count=args.expected_read_event_count,
            source_event_types=args.source_event_types,
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("allow_execute") and report.get("result") == "EXECUTED" else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    scope = report["planned_write_scope"]
    output = report["output_event_plan_summary"]
    return "\n".join(
        [
            "action consumer once",
            f"  stage={report['stage']}",
            f"  source_trigger_run_id={report['source_trigger_run_id']}",
            f"  action_run_id={report['action_run_id']}",
            f"  execute={report['execute']} user_confirmed={report['user_confirmed']}",
            f"  allow_execute={report['allow_execute']}",
            f"  blockers={report['blockers']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            f"  planned_write_scope={scope}",
            f"  output_event_plan={output['by_event_type']}",
            "  worker_started=false n6_user_layer_touched=false voice_touched=false sim_touched=false real_trade_touched=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
