#!/usr/bin/env python3
"""Build the N1 official daily 20260525 ingestion dry-run report.

This script is plan-only. It may perform read-only PostgreSQL checks and write
report files, but it cannot execute ingestion, write facts, write Parquet,
update active source versions, enter downstream layers, or start workers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.official_daily_ingestion_plan import (  # noqa: E402
    DEFAULT_EOD_REPORT_JSON,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_MARKDOWN_REPORT_PATH,
    build_official_daily_ingestion_report,
    build_snapshot_from_db,
    write_report_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", default="20260525")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql:///ashare_v3"))
    parser.add_argument("--eod-report-json", default=DEFAULT_EOD_REPORT_JSON)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MARKDOWN_REPORT_PATH)
    parser.add_argument("--no-write-report", action="store_true", help="Print JSON only; do not write report files.")
    parser.add_argument("--execute", action="store_true", help="Rejected: this script is dry-run only.")
    parser.add_argument("--user-confirmed", action="store_true", help="Rejected with --execute; kept only to make misuse explicit.")
    args = parser.parse_args()

    if args.execute:
        print(
            "BLOCKED: scripts/plan_official_daily_ingestion_20260525.py is a dry-run planner only; "
            "it has no ingestion write path.",
            file=sys.stderr,
        )
        return 2

    snapshot = build_snapshot_from_db(
        dsn=args.dsn,
        for_trade_date=args.trade_date,
        eod_report_path=args.eod_report_json,
    )
    report = build_official_daily_ingestion_report(snapshot)
    if not args.no_write_report:
        write_report_files(report, json_path=args.json_report_path, markdown_path=args.markdown_report_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "DRY_RUN_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
