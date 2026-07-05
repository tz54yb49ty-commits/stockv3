#!/usr/bin/env python3
"""Build an N3-C2 closed minute / closed 30m replay dry-run report.

This script reads existing runtime facts and control rows only. It does not
pull market data, write minute delta rows, write closed summary rows, write
quality rows, write or consume outbox/inbox/checkpoint rows, enter downstream
layers, or start workers.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.closed_30m_replay_plan import (
    DEFAULT_B2_REPORT_PATH,
    DEFAULT_C1_REPORT_PATH,
    DEFAULT_DRY_RUN_PLAN_PATH,
    DEFAULT_EXECUTE_CONTRACT_PATH,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MARKDOWN_REPORT_PATH,
    DEFAULT_ROLLBACK_SQL_PATH,
    build_closed_30m_replay_dry_run,
    format_summary,
    write_report_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3-C2 closed 30m replay dry-run report.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected. C2 execute is not implemented here.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--dry-run-plan-path", default=DEFAULT_DRY_RUN_PLAN_PATH)
    parser.add_argument("--execute-contract-path", default=DEFAULT_EXECUTE_CONTRACT_PATH)
    parser.add_argument("--c1-report-path", default=DEFAULT_C1_REPORT_PATH)
    parser.add_argument("--b2-report-path", default=DEFAULT_B2_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--no-include-rows", action="store_true", help="Include only row samples from DB reads.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-C2 dry-run runner rejects --execute. Business execute requires a later explicit gate.")

    report = build_closed_30m_replay_dry_run(
        dsn=args.dsn,
        dry_run_plan_path=args.dry_run_plan_path,
        execute_contract_path=args.execute_contract_path,
        c1_report_path=args.c1_report_path,
        b2_report_path=args.b2_report_path,
        rollback_sql_path=args.rollback_sql_path,
        include_rows=not args.no_include_rows,
    )
    write_report_files(report, markdown_path=args.report_path, json_path=args.json_report_path)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if not report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
