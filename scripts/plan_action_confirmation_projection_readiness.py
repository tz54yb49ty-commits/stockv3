#!/usr/bin/env python3
"""Build N3 action-confirmation projection writer readiness reports.

This planner is read-only. It validates source run readiness, trace coverage,
baseline cleanliness, rollback scope, and N4/N5 boundary alignment for a future
N3 action-confirmation projection metric writer. It never writes projection
rows, run rows, quality rows, outbox/inbox/checkpoint rows, or starts workers.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.action_confirmation_projection_plan import (
    DEFAULT_FOR_TRADE_DATE,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MARKDOWN_REPORT_PATH,
    DEFAULT_PREFLIGHT_JSON_PATH,
    DEFAULT_PREFLIGHT_MARKDOWN_PATH,
    DEFAULT_PROJECTION_RUN_ID,
    DEFAULT_ROLLBACK_SQL_PATH,
    DEFAULT_SOURCE_CONDITION_RUN_ID,
    DEFAULT_SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID,
    DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
    DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
    DEFAULT_SOURCE_TODAY_MINUTE_RUN_ID,
    build_action_confirmation_projection_readiness_from_db,
    build_preflight_report,
    format_summary,
    write_preflight_files,
    write_report_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build N3 action-confirmation projection writer readiness and preflight reports."
    )
    parser.add_argument("--execute", action="store_true", help="Rejected. This runner is read-only.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--projection-run-id", default=DEFAULT_PROJECTION_RUN_ID)
    parser.add_argument("--for-trade-date", default=DEFAULT_FOR_TRADE_DATE)
    parser.add_argument("--source-condition-run-id", default=DEFAULT_SOURCE_CONDITION_RUN_ID)
    parser.add_argument("--source-subscription-run-id", default=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID)
    parser.add_argument("--source-snapshot-run-id", default=DEFAULT_SOURCE_SNAPSHOT_RUN_ID)
    parser.add_argument("--source-today-minute-run-id", default=DEFAULT_SOURCE_TODAY_MINUTE_RUN_ID)
    parser.add_argument("--source-previous-day-minute-run-id", default=DEFAULT_SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--preflight-report-path", default=DEFAULT_PREFLIGHT_MARKDOWN_PATH)
    parser.add_argument("--preflight-json-path", default=DEFAULT_PREFLIGHT_JSON_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3 action-confirmation projection readiness rejects --execute. Business writes require a later explicit gate.")

    report = build_action_confirmation_projection_readiness_from_db(
        dsn=args.dsn,
        projection_run_id=args.projection_run_id,
        for_trade_date=args.for_trade_date,
        source_condition_run_id=args.source_condition_run_id,
        source_subscription_run_id=args.source_subscription_run_id,
        source_snapshot_run_id=args.source_snapshot_run_id,
        source_today_minute_run_id=args.source_today_minute_run_id,
        source_previous_day_minute_run_id=args.source_previous_day_minute_run_id,
        rollback_sql_path=args.rollback_sql_path,
    )
    preflight = build_preflight_report(report)

    write_report_files(report, json_path=args.json_report_path, markdown_path=args.report_path)
    write_preflight_files(report, json_path=args.preflight_json_path, markdown_path=args.preflight_report_path)

    if args.json:
        print(json.dumps({"readiness": report, "preflight": preflight}, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
        print(f"preflight={preflight['result']}")
    return 0 if not report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
