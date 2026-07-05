#!/usr/bin/env python3
"""Generic guarded N1 trade-calendar patch runner.

Default mode is preflight only: it performs read-only PostgreSQL checks,
queries Tushare trade_cal for the target date when a token is available, writes
preflight artifacts, and does not patch the database. Execute mode requires
explicit final-gate flags.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import psycopg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.trade_calendar_patch_generic import (  # noqa: E402
    DEFAULT_DSN,
    CalendarPatchGenericBlocked,
    TradeCalendarPatchConfig,
    build_calendar_patch_preflight,
    build_snapshot_from_db,
    execute_patch_transaction,
    fetch_tushare_trade_calendar_source,
    write_preflight_files,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--expected-prev-trade-date", required=True)
    parser.add_argument("--fallback-next-trade-date", required=True)
    parser.add_argument("--exchange", default="SSE")
    parser.add_argument("--source-batch-id")
    parser.add_argument("--source-version")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--json-report-path")
    parser.add_argument("--markdown-report-path")
    parser.add_argument("--rollback-sql-path")
    parser.add_argument("--allow-minimal-fallback", action="store_true")
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--postgres-commit-enabled", action="store_true")
    args = parser.parse_args(argv)

    config = TradeCalendarPatchConfig(
        trade_date=args.trade_date,
        expected_prev_trade_date=args.expected_prev_trade_date,
        fallback_next_trade_date=args.fallback_next_trade_date,
        exchange=args.exchange,
        source_batch_id=args.source_batch_id,
        source_version=args.source_version,
        preflight_json_path=args.json_report_path,
        preflight_markdown_path=args.markdown_report_path,
        rollback_sql_path=args.rollback_sql_path,
    )

    snapshot = build_snapshot_from_db(config=config, dsn=args.dsn)
    source_result = fetch_tushare_trade_calendar_source(config=config)
    report = build_calendar_patch_preflight(
        config=config,
        snapshot=snapshot,
        source_result=source_result,
        allow_minimal_fallback=args.allow_minimal_fallback,
        execute_requested=args.execute,
        user_confirmed=args.user_confirmed,
        postgres_commit_enabled=args.postgres_commit_enabled,
    )
    if not args.no_write_report:
        write_preflight_files(
            report,
            json_path=config.resolved_preflight_json_path,
            markdown_path=config.resolved_preflight_markdown_path,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["result"] != "PREFLIGHT_PASS":
        if args.execute:
            print(f"BLOCKED: {', '.join(report['blockers'])}", file=sys.stderr)
            return 2
        return 1
    if not args.execute:
        return 0

    try:
        with psycopg.connect(args.dsn, connect_timeout=10) as conn:
            result = execute_patch_transaction(
                config=config,
                conn=conn,
                report=report,
                execute_requested=args.execute,
                user_confirmed=args.user_confirmed,
                postgres_commit_enabled=args.postgres_commit_enabled,
            )
    except CalendarPatchGenericBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
