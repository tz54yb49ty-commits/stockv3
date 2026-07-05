#!/usr/bin/env python3
"""Build an N3-B0 realtime daily snapshot run-once dry-run report."""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.realtime_snapshot_plan import (
    DEFAULT_N3_B0_JSON_REPORT_PATH,
    DEFAULT_N3_B0_MARKDOWN_REPORT_PATH,
    build_realtime_daily_snapshot_dry_run,
    format_realtime_daily_snapshot_summary,
    write_report_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3-B0 realtime daily snapshot dry-run report.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed N3-B0 mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected in N3-B0.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", required=True, help="N3-6 market_data_subscription run_id.")
    parser.add_argument("--preload-run-id", default="", help="N3-A1 previous_day_minute preload run_id.")
    parser.add_argument("--report-path", default=DEFAULT_N3_B0_MARKDOWN_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_N3_B0_JSON_REPORT_PATH)
    parser.add_argument("--no-include-rows", action="store_true", help="Only include row samples in the JSON report.")
    parser.add_argument(
        "--no-writes-outbox",
        action="store_true",
        help="Plan a snapshot fact-only B1 execute contract with writes_outbox=false.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-B0 only supports --dry-run. Execute requires later explicit N3-B1 confirmation.")

    report = build_realtime_daily_snapshot_dry_run(
        dsn=args.dsn,
        market_data_run_id=args.run_id,
        previous_day_preload_run_id=args.preload_run_id or None,
        include_rows=not args.no_include_rows,
        writes_outbox=not args.no_writes_outbox,
    )
    write_report_files(report, markdown_path=args.report_path, json_path=args.json_report_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_realtime_daily_snapshot_summary(report))
    return 0 if not report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
