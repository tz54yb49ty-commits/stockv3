#!/usr/bin/env python3
"""Build an N3-C0 today minute_bar_1m run-once dry-run report.

This script reads persisted N3 subscription/pull-plan control rows and plans
today's closed 1m fact catch-up. It does not pull market data, write minute
facts, write common_event_outbox, consume events, or start workers.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.today_minute_plan import (
    DEFAULT_N3_C0_JSON_REPORT_PATH,
    DEFAULT_N3_C0_MARKDOWN_REPORT_PATH,
    build_today_minute_bar_plan_dry_run,
    format_today_minute_summary,
    parse_as_of,
    write_report_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3-C0 today minute_bar_1m dry-run report.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed N3-C0 mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected in N3-C0.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", required=True, help="N3 market_data_subscription run_id.")
    parser.add_argument("--for-trade-date", default="", help="Optional for_trade_date guard, e.g. 20260525.")
    parser.add_argument("--as-of", default="", help="Optional ISO timestamp used to compute latest_closed_minute.")
    parser.add_argument("--report-path", default=DEFAULT_N3_C0_MARKDOWN_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N3_C0_JSON_REPORT_PATH)
    parser.add_argument("--no-include-rows", action="store_true", help="Omit detailed row samples from JSON report.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-C0 only supports --dry-run. Execute requires later explicit N3-C1 confirmation.")

    report = build_today_minute_bar_plan_dry_run(
        dsn=args.dsn,
        market_data_run_id=args.run_id,
        for_trade_date=args.for_trade_date or None,
        as_of=parse_as_of(args.as_of),
        include_rows=not args.no_include_rows,
    )
    write_report_files(report, markdown_path=args.report_path, json_path=args.json_report_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_today_minute_summary(report))
    return 0 if not report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
