#!/usr/bin/env python3
"""Build N3-EOD snapshot refresh dry-run and execute preflight reports.

This script is read-only against PostgreSQL. It does not execute EOD business,
pull market data, write EOD facts, write run/quality rows, write or consume
outbox/inbox/checkpoint rows, enter N4/N5/N6, or start workers.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.eod_snapshot_plan import (
    DEFAULT_CONTRACT_PATH,
    DEFAULT_DRY_RUN_PLAN_PATH,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MARKDOWN_REPORT_PATH,
    DEFAULT_PREFLIGHT_JSON_PATH,
    DEFAULT_PREFLIGHT_MARKDOWN_PATH,
    DEFAULT_ROLLBACK_SQL_PATH,
    DEFAULT_SCHEMA_READINESS_PATH,
    build_eod_snapshot_refresh_dry_run,
    format_summary,
    write_report_files,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3-EOD snapshot refresh dry-run and preflight reports.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected. EOD business execute is not implemented here.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-path", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--dry-run-plan-path", default=DEFAULT_DRY_RUN_PLAN_PATH)
    parser.add_argument("--schema-readiness-path", default=DEFAULT_SCHEMA_READINESS_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--preflight-report-path", default=DEFAULT_PREFLIGHT_MARKDOWN_PATH)
    parser.add_argument("--preflight-json-path", default=DEFAULT_PREFLIGHT_JSON_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-EOD dry-run runner rejects --execute. Business execute requires a later explicit gate.")

    dry_run_report, preflight_report = build_eod_snapshot_refresh_dry_run(
        dsn=args.dsn,
        contract_path=args.contract_path,
        dry_run_plan_path=args.dry_run_plan_path,
        schema_readiness_path=args.schema_readiness_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    write_report_files(
        dry_run_report,
        preflight_report,
        markdown_path=args.report_path,
        json_path=args.json_report_path,
        preflight_markdown_path=args.preflight_report_path,
        preflight_json_path=args.preflight_json_path,
    )

    if args.json:
        print(json.dumps({"dry_run": dry_run_report, "preflight": preflight_report}, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(dry_run_report, preflight_report))
    return 0 if not dry_run_report.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
