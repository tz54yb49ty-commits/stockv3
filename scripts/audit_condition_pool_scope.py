#!/usr/bin/env python3
"""Audit condition_pool default object ranges for an active condition run."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.pool_scope_audit import (
    fetch_active_condition_run_id,
    fetch_condition_pool_scope_audit,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Run N2-E4 condition_pool default range audit without writes.")
    parser.add_argument("--run-id", default="", help="Condition run id to audit. Defaults to active run for date pair.")
    parser.add_argument("--source-trade-date", default="20260522")
    parser.add_argument("--for-trade-date", default="20260525")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--overwrite", action="store_true", help="Rejected. N2-E4 audit never overwrites.")
    parser.add_argument("--execute", action="store_true", help="Rejected. N2-E4 audit never writes.")
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args()

    if args.execute or args.overwrite:
        parser.error("N2-E4 is read-only. It does not support --execute or --overwrite.")

    run_id = args.run_id or fetch_active_condition_run_id(
        args.dsn,
        source_trade_date=args.source_trade_date,
        for_trade_date=args.for_trade_date,
    )
    report = fetch_condition_pool_scope_audit(args.dsn, run_id=run_id)

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["quality"]["p0_count"] == 0 else 1


def format_summary(report: dict[str, Any]) -> str:
    pool = report["pool_audit"]
    scope = report["scope_audit"]
    remediation = report["remediation_plan"]
    return "\n".join(
        [
            "condition_pool default range audit",
            f"  run_id={report['run_id']}",
            f"  source_trade_date={report['source_trade_date']} for_trade_date={report['for_trade_date']} prev_trade_date={report['prev_trade_date']}",
            f"  index_pool objects={pool['index']['object_count']} rows={pool['index']['row_count']} out_of_range_rows={pool['index']['out_of_range_row_count']}",
            f"  board_pool objects={pool['board']['object_count']} rows={pool['board']['row_count']} out_of_range_rows={pool['board']['out_of_range_row_count']}",
            f"  stock_pool objects={pool['stock']['object_count']} rows={pool['stock']['row_count']} out_of_range_rows={pool['stock']['out_of_range_row_count']}",
            f"  index_scope objects={scope['index']['object_count']} rows={scope['index']['row_count']} pool_link_violations={scope['index']['pool_link_violation_row_count']} explanation={scope['index']['object_count_row_count_explanation']}",
            f"  board_scope objects={scope['board']['object_count']} rows={scope['board']['row_count']} pool_link_violations={scope['board']['pool_link_violation_row_count']} explanation={scope['board']['object_count_row_count_explanation']}",
            f"  stock_scope objects={scope['stock']['object_count']} rows={scope['stock']['row_count']} pool_link_violations={scope['stock']['pool_link_violation_row_count']} market_value_violations={scope['stock']['market_value_violation_row_count']}",
            f"  p0_count={report['quality']['p0_count']} p1_count={report['quality']['p1_count']} p2_count={report['quality']['p2_count']}",
            f"  needs_remediation={report['needs_remediation']} remediation_required={remediation.get('required')}",
            "  writes_performed=false will_execute_sql=false overwrite_performed=false minute_kline_pulled=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
