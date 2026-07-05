#!/usr/bin/env python3
"""Build an N3-C3 MinuteBarClosed outbox dry-run report.

This script reads C2 closed summary facts and N3 control rows only. It does
not write run rows, quality rows, outbox rows, inbox/checkpoint rows, downstream
runtime, or worker state.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.minute_bar_closed_outbox_plan import (
    DEFAULT_C2_EXECUTE_REPORT_PATH,
    DEFAULT_DESIGN_PATH,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MARKDOWN_REPORT_PATH,
    DEFAULT_V2_CONTRACT_PATH,
    build_minute_bar_closed_outbox_dry_run,
    format_summary,
    write_report_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3-C3 MinuteBarClosed outbox dry-run report.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected. C3 execute requires a later explicit gate.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--design-path", default=DEFAULT_DESIGN_PATH)
    parser.add_argument("--v2-contract-path", default=DEFAULT_V2_CONTRACT_PATH)
    parser.add_argument("--c2-execute-report-path", default=DEFAULT_C2_EXECUTE_REPORT_PATH)
    parser.add_argument("--report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-C3 dry-run runner rejects --execute. Outbox execute requires a later explicit gate.")

    report = build_minute_bar_closed_outbox_dry_run(
        dsn=args.dsn,
        design_path=args.design_path,
        v2_contract_path=args.v2_contract_path,
        c2_execute_report_path=args.c2_execute_report_path,
    )
    write_report_files(report, markdown_path=args.report_path, json_path=args.json_report_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if not report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
