#!/usr/bin/env python3
"""Build a read-only condition_pool dry-run report.

N2-C boundary: this script reads the v3 condition source interface and reuses
the N2-B condition_basis dry-run preview. It does not write condition tables,
pull market data, start workers, or touch the old system.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.pool import build_condition_pool_dry_run
from check_condition_source_ready import DEFAULT_DSN, run_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v3 condition_pool dry-run report.")
    parser.add_argument("--source-trade-date", required=True, help="Finalized ingestion trade date, e.g. 20260522.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed N2-C mode.")
    parser.add_argument("--execute", action="store_true", help="Reserved for later stages; rejected in N2-C.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-C only supports --dry-run. Execute requires explicit later-stage confirmation.")

    ready = run_check(args.dsn, args.source_trade_date)
    report = build_condition_pool_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
    )

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["passed"] else 2


def format_summary(report: dict[str, Any]) -> str:
    pool = report["pool_preview"]
    quality = report["quality"]
    calendar = report["calendar_detail"]
    lines = [
        "condition_pool dry-run",
        f"  source_trade_date={report['source_trade_date']}",
        f"  for_trade_date={report['for_trade_date']}",
        f"  prev_trade_date={report['prev_trade_date']}",
        f"  source_ready_passed={report['source_ready_passed']}",
        f"  for_trade_calendar_row_exists={calendar['row_exists']}",
        (
            f"  stock_basis_preview_rows={pool['stock']['basis_preview_row_count']} "
            f"stock_candidate_rows={pool['stock']['candidate_pool_row_count']} "
            f"stock_selected_rows={pool['stock']['policy_selected_count']} "
            f"stock_excluded_rows={pool['stock']['policy_excluded_count']} "
            f"stock_pool_rows={pool['stock']['pool_row_count']}"
        ),
        (
            f"  index_basis_preview_rows={pool['index']['basis_preview_row_count']} "
            f"index_candidate_rows={pool['index']['candidate_pool_row_count']} "
            f"index_selected_rows={pool['index']['policy_selected_count']} "
            f"index_excluded_rows={pool['index']['policy_excluded_count']} "
            f"index_pool_rows={pool['index']['pool_row_count']}"
        ),
        (
            f"  board_basis_preview_rows={pool['board']['basis_preview_row_count']} "
            f"board_candidate_rows={pool['board']['candidate_pool_row_count']} "
            f"board_selected_rows={pool['board']['policy_selected_count']} "
            f"board_excluded_rows={pool['board']['policy_excluded_count']} "
            f"board_pool_rows={pool['board']['pool_row_count']}"
        ),
        f"  stock_policy_hash={pool['stock']['condition_pool_selection_policy_hash']}",
        f"  index_policy_hash={pool['index']['condition_pool_selection_policy_hash']}",
        f"  board_policy_hash={pool['board']['condition_pool_selection_policy_hash']}",
        f"  stock_excluded_reasons={pool['stock']['policy_excluded_reason_counts']}",
        f"  index_excluded_reasons={pool['index']['policy_excluded_reason_counts']}",
        f"  board_excluded_reasons={pool['board']['policy_excluded_reason_counts']}",
        f"  stock_condition_keys={pool['stock']['condition_key_counts']}",
        f"  index_condition_keys={pool['index']['condition_key_counts']}",
        f"  board_condition_keys={pool['board']['condition_key_counts']}",
        f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
        "  writes_performed=false condition_pool_written=false minute_kline_pulled=false",
    ]
    if not calendar["row_exists"]:
        lines.append(f"  calendar_repair_suggestion={calendar['repair_suggestion']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
