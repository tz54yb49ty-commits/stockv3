#!/usr/bin/env python3
"""Build N3 after N2-R2 subscription / pull_plan refresh dry-run report."""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.subscription_refresh import (
    DEFAULT_REFRESH_JSON_PATH,
    DEFAULT_REFRESH_MD_PATH,
    build_subscription_refresh_dry_run,
    format_subscription_refresh_summary,
    write_subscription_refresh_reports,
)
from check_condition_source_ready import DEFAULT_DSN


DEFAULT_NEW_CONDITION_RUN_ID = "condition_layer_20260522_to_20260525_20260524181321_execute"
DEFAULT_OLD_MARKET_DATA_RUN_ID = (
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260524014029_execute"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3 subscription refresh dry-run after N2-R2.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--new-condition-run-id", default=DEFAULT_NEW_CONDITION_RUN_ID)
    parser.add_argument("--old-market-data-run-id", default=DEFAULT_OLD_MARKET_DATA_RUN_ID)
    parser.add_argument("--markdown-report-path", default=DEFAULT_REFRESH_MD_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_REFRESH_JSON_PATH)
    parser.add_argument("--include-rows", action="store_true", help="Include all candidate/subscription/pull_plan rows in JSON.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--execute", action="store_true", help="Rejected. This stage is dry-run only.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3 after N2-R2 refresh only supports dry-run. Execute requires a separate N3-6 confirmation.")

    report = build_subscription_refresh_dry_run(
        dsn=args.dsn,
        new_condition_run_id=args.new_condition_run_id,
        old_market_data_run_id=args.old_market_data_run_id or None,
        include_rows=args.include_rows,
    )
    write_subscription_refresh_reports(
        report,
        markdown_path=args.markdown_report_path,
        json_path=args.json_report_path,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_subscription_refresh_summary(report))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
