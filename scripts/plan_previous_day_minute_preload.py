#!/usr/bin/env python3
"""Build an N3-A0 previous-day minute preload dry-run report.

This script reads the persisted N3-6 market_data_subscription run, its
previous-day minute pull_plan rows, and matching subscriptions. It does not
pull market data, write market-data facts, write common_event_outbox, execute
migrations, or start workers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.market.preload_plan import (
    build_previous_day_minute_preload_plan_dry_run,
    format_previous_day_minute_preload_markdown,
    format_previous_day_minute_preload_summary,
)
from check_condition_source_ready import DEFAULT_DSN

DEFAULT_MARKDOWN_REPORT_PATH = "docs/N3_A0_PREVIOUS_DAY_MINUTE_PRELOAD_DRY_RUN_REPORT.md"
DEFAULT_JSON_REPORT_PATH = "docs/N3_A0_previous_day_minute_preload_dry_run.json"
DEFAULT_EXPECTED_PREVIOUS_DAY_MINUTE_DATE = "20260522"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3-A0 previous-day minute preload dry-run report.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed N3-A0 mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected in N3-A0.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", default="", help="N3-6 market_data_subscription run_id.")
    parser.add_argument("--market-data-run-id", default="", help="Alias for --run-id.")
    parser.add_argument("--source-trade-date", default="", help="Optional source_trade_date filter, e.g. 20260522.")
    parser.add_argument("--for-trade-date", default="", help="Optional for_trade_date filter, e.g. 20260525.")
    parser.add_argument(
        "--expected-previous-day-minute-date",
        default=DEFAULT_EXPECTED_PREVIOUS_DAY_MINUTE_DATE,
        help="Expected previous-day minute date for this N3-A0 check.",
    )
    parser.add_argument("--report-path", default=DEFAULT_MARKDOWN_REPORT_PATH, help="Markdown report path.")
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH, help="JSON report path.")
    parser.add_argument("--no-include-rows", action="store_true", help="Only include row samples in the JSON report.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-A0 only supports --dry-run. Execute requires later explicit N3-A1 confirmation.")

    market_data_run_id = args.market_data_run_id or args.run_id
    if not market_data_run_id:
        parser.error("--run-id or --market-data-run-id is required for N3-A0.")

    report = build_previous_day_minute_preload_plan_dry_run(
        dsn=args.dsn,
        market_data_run_id=market_data_run_id,
        source_trade_date=args.source_trade_date or None,
        for_trade_date=args.for_trade_date or None,
        expected_previous_day_minute_date=args.expected_previous_day_minute_date or None,
        include_rows=not args.no_include_rows,
    )

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(format_previous_day_minute_preload_markdown(report), encoding="utf-8")

    if args.json_report_path:
        path = Path(args.json_report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_previous_day_minute_preload_summary(report))
    return 0 if not report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
