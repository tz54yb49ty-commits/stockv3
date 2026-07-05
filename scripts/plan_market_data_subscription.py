#!/usr/bin/env python3
"""Build an N3-0 market_data_subscription dry-run report.

This script reads the active v3 condition run and stock/index/board
minute_target_scope tables in a read-only transaction. It does not pull market
data, write market data fact tables, execute migrations, or start workers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.market.subscription_plan import build_market_data_subscription_plan_dry_run
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N3-0 market data subscription dry-run report.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed N3-0 mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected in N3-0.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", default="", help="Optional explicit condition run id. Defaults to the single active passed run.")
    parser.add_argument("--source-trade-date", default="", help="Optional source_trade_date filter, e.g. 20260522.")
    parser.add_argument("--for-trade-date", default="", help="Optional for_trade_date filter, e.g. 20260525.")
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--no-include-rows", action="store_true", help="Only include row samples in the JSON report.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N3-0 only supports --dry-run. Execute requires explicit later-stage confirmation.")

    report = build_market_data_subscription_plan_dry_run(
        dsn=args.dsn,
        run_id=args.run_id or None,
        source_trade_date=args.source_trade_date or None,
        for_trade_date=args.for_trade_date or None,
        include_rows=not args.no_include_rows,
    )

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("passed") else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report["quality"]
    lines = [
        "market_data_subscription dry-run",
        f"  source_condition_run_id={report.get('source_condition_run_id')}",
        f"  source_trade_date={report.get('source_trade_date')}",
        f"  for_trade_date={report.get('for_trade_date')}",
        f"  prev_trade_date={report.get('prev_trade_date')}",
        f"  source_scope_row_count={report.get('source_scope_row_count')}",
        f"  source_scope_row_count_by_asset_kind={report.get('source_scope_row_count_by_asset_kind')}",
        f"  subscription_candidate_count={report.get('subscription_candidate_count', report.get('candidate_row_count'))}",
        f"  dedup_subscription_count={report.get('dedup_subscription_count', report.get('subscription_row_count'))}",
        f"  subscription_object_count={report.get('subscription_object_count')}",
        f"  object_count_by_asset_kind={report.get('object_count_by_asset_kind')}",
        f"  required_data_kind_counts={report.get('required_data_kind_counts')}",
        f"  previous_day_minute_required_count={report.get('previous_day_minute_required_count')}",
        f"  previous_day_minute_date_counts={report.get('previous_day_minute_date_counts')}",
        f"  trade_calendar_detail_check={calendar_summary(report.get('trade_calendar_detail_check'))}",
        f"  dedup_ratio={report.get('dedup_ratio')} dedup_reduction_ratio={report.get('dedup_reduction_ratio')}",
        f"  market_data_pull_plan_row_count={report.get('market_data_pull_plan_row_count')}",
        f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
        f"  blocked={report.get('blocked')} passed={report.get('passed')}",
        "  read_only_database_checks=true will_execute_sql=false migration_executed=false",
        "  market_data_pulled=false market_data_fact_written=false downstream_layers_touched=false worker_started=false",
    ]
    if report.get("blocked"):
        failed = [
            item
            for item in quality["items"]
            if item.get("status") in {"failed", "warning"}
        ][:10]
        lines.append(f"  blocking_quality_items={failed}")
    return "\n".join(lines)


def calendar_summary(detail: Any) -> dict[str, Any] | None:
    if not isinstance(detail, dict):
        return None
    row = detail.get("row") or {}
    return {
        "trade_date": detail.get("trade_date"),
        "table_exists": detail.get("table_exists"),
        "row_exists": detail.get("row_exists"),
        "is_open": row.get("is_open") if isinstance(row, dict) else None,
        "prev_trade_date": row.get("prev_trade_date") if isinstance(row, dict) else None,
        "next_trade_date": row.get("next_trade_date") if isinstance(row, dict) else None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
