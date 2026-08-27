#!/usr/bin/env python3
"""Windows N1 bootstrap entrypoint; plan is safe, execute is fail-closed."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ashare_v3.ingestion.windows_n1_bootstrap import (
    N1_BOOTSTRAP_STAGES,
    WindowsN1BootstrapConfig,
    execute_bootstrap,
    write_run_artifact,
)
from ashare_v3.ingestion.windows_n1_postgres import WindowsN1PostgresRepository
from ashare_v3.ingestion.windows_n1_production import WindowsN1ProductionHandlers
from ashare_v3.ingestion.windows_n1_sources import EltdxWindowsSource, TQHttpClient, TQWindowsSource
from ashare_v3.ingestion.windows_n1_db_setup import PASSWORDLESS_APP_DSN
from ashare_v3.ingestion.windows_n1_fastlane import (
    at_or_after_daily_cutoff,
    calendar_date_is_open,
    run_recent_stock_daily_gap_fill,
)
from ashare_v3.ingestion.windows_n1_sources import LocalTradeCalendarProvider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", default=r"C:\AshareV3\artifacts\n1")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--daily", action="store_true")
    args = parser.parse_args()
    if sum((args.plan, args.schema_only, args.execute)) != 1:
        parser.error("choose exactly one of --plan, --schema-only, or --execute")
    if args.daily and args.schema_only:
        parser.error("--daily cannot be combined with --schema-only")
    today = date.today()
    today_text = today.strftime("%Y%m%d")
    config = (
        WindowsN1BootstrapConfig(
            artifact_root=Path(args.artifact_root),
            start_date=today_text,
            end_date=today_text,
        )
        if args.daily
        else WindowsN1BootstrapConfig.for_today(
            artifact_root=Path(args.artifact_root), today=today
        )
    )
    if args.plan:
        print(json.dumps({
        "mode": "plan",
        "layer_role": "N1_ingestion",
        "start_date": config.start_date,
        "end_date": config.end_date,
        "tq_url": config.tq_url,
        "stages": list(N1_BOOTSTRAP_STAGES),
        "calendar_external": True,
        "writes_common_trade_calendar": False,
        "starts_scheduler": False,
        "touches_n2_n6": False,
        "daily": args.daily,
        "recent_stock_daily_gap_fill": args.daily,
        }, ensure_ascii=False, indent=2))
        return 0
    calendar = LocalTradeCalendarProvider()
    if args.daily:
        now = datetime.now()
        if not at_or_after_daily_cutoff(now):
            print(json.dumps({
                "result": "N1_DAILY_SKIPPED_BEFORE_1630",
                "trade_date": today_text,
                "database_written": False,
            }, ensure_ascii=False))
            return 0
        if not calendar_date_is_open(calendar, today_text):
            print(json.dumps({
                "result": "N1_DAILY_SKIPPED_CLOSED_DAY",
                "trade_date": today_text,
                "database_written": False,
            }, ensure_ascii=False))
            return 0
    import psycopg
    with psycopg.connect(PASSWORDLESS_APP_DSN, connect_timeout=8) as connection:
        repository = WindowsN1PostgresRepository(connection)
        if args.schema_only:
            repository.verify_authority()
            counts = repository.business_row_counts()
            if any(counts.values()):
                raise SystemExit(f"schema-only row-count invariant failed: {counts}")
            print(json.dumps({"result": "SCHEMA_READY", "business_row_counts": counts, "database_written": False, "business_rows_written": 0, "calendar_rows_written": 0, "downstream_rows_written": 0}, ensure_ascii=False))
            return 0
        from eltdx import TdxClient
        tq = TQWindowsSource(TQHttpClient(base_url=config.tq_url))
        gap_result = None
        today_counts_before = repository.daily_bar_counts(today_text) if args.daily else None
        with TdxClient(timeout=8) as eltdx_client:
            if args.daily:
                gap_run_id = "windows_n1_gap_" + datetime.now(timezone.utc).strftime(
                    "%Y%m%dT%H%M%S%fZ"
                )
                gap_result = run_recent_stock_daily_gap_fill(
                    today=today_text,
                    run_id=gap_run_id,
                    calendar=calendar,
                    tq=tq,
                    repository=repository,
                )
                print(json.dumps(gap_result.to_dict(), ensure_ascii=False))
                if gap_result.result == "NO_FASTLANE_COMPLETION_MARKER":
                    raise RuntimeError("Fastlane completion marker is missing")
            production = WindowsN1ProductionHandlers(
                config=config,
                tq=tq,
                eltdx=EltdxWindowsSource(eltdx_client),
                repository=repository,
                daily_mode=args.daily,
            )
            result = execute_bootstrap(config=config, stage_handlers=production.handlers())
        if not result.n1_data_ready:
            raise SystemExit(2)
        if args.daily:
            today_counts_after = repository.daily_bar_counts(today_text)
            completion_details = {
                "today_counts_before": today_counts_before,
                "today_counts_after": today_counts_after,
                "gap_fill": gap_result.to_dict() if gap_result is not None else None,
                "daily_bar_batches": result.evidence.get("daily_bar_batches"),
                "finance_incremental": result.evidence.get("finance_incremental"),
                "daily_basic_incremental": result.evidence.get("daily_basic_incremental"),
            }
            repository.mark_fastlane_complete(
                trade_date=today_text,
                run_id=result.run_id,
                row_count=sum(int(value) for value in production.row_counts.values()),
                details=completion_details,
            )
            result.evidence["fastlane_completion"] = completion_details
            write_run_artifact(artifact_root=config.artifact_root, result=result)
        print(json.dumps({"result": "N1_DATA_READY", "run_id": result.run_id, "artifact": str(config.artifact_root / result.run_id / "windows_n1_run.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
