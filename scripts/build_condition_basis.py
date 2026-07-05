#!/usr/bin/env python3
"""Build a read-only condition_basis dry-run report.

N2-B boundary: this script reads v3 ingestion facts and the condition source
ready interface only. It does not write condition tables, build condition_pool,
pull minute bars, start workers, or touch the old system.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.basis import build_condition_basis_dry_run
from check_condition_source_ready import DEFAULT_DSN, run_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v3 condition_basis dry-run report.")
    parser.add_argument("--source-trade-date", required=True, help="Finalized ingestion trade date, e.g. 20260522.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only allowed N2-B mode.")
    parser.add_argument("--execute", action="store_true", help="Reserved for later stages; rejected in N2-B.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-B only supports --dry-run. Execute requires explicit later-stage confirmation.")

    ready = run_check(args.dsn, args.source_trade_date)
    report = build_condition_basis_dry_run(
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
    basis = report["basis_preview"]
    quality = report["quality"]
    source_versions = report["source_versions"]
    lines = [
        "condition_basis dry-run",
        f"  source_trade_date={report['source_trade_date']}",
        f"  source_prev_trade_date={report.get('source_prev_trade_date')}",
        f"  for_trade_date={report['for_trade_date']}",
        f"  prev_trade_date={report['prev_trade_date']}",
        f"  source_ready_passed={report['source_ready_passed']}",
        f"  stock_rows={basis['stock']['row_count']} stock_daily={source_versions['stock_daily']} stock_daily_basic={source_versions['stock_daily_basic']} stock_financial={source_versions['stock_financial']}",
        f"  index_rows={basis['index']['row_count']} index_daily={source_versions['index_daily']}",
        f"  board_rows={basis['board']['row_count']} board_daily={source_versions['board_daily']}",
        f"  stock_necessary={basis['stock'].get('necessary_counts', {})}",
        f"  index_necessary={basis['index'].get('necessary_counts', {})}",
        f"  board_necessary={basis['board'].get('necessary_counts', {})}",
        f"  stock_static_coverage={basis['stock'].get('static_structure_coverage', {})}",
        f"  index_static_coverage={basis['index'].get('static_structure_coverage', {})}",
        f"  board_static_coverage={basis['board'].get('static_structure_coverage', {})}",
        f"  amount_baseline_warnings stock={basis['stock'].get('amount_baseline_warning_count')} index={basis['index'].get('amount_baseline_warning_count')} board={basis['board'].get('amount_baseline_warning_count')}",
        f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
        "  writes_performed=false condition_pool_written=false minute_kline_pulled=false",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
