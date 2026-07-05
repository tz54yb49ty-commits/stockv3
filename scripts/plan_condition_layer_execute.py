#!/usr/bin/env python3
"""Build the N2-E0 condition-layer execute readiness plan.

This script runs read-only dry-runs for condition_basis, condition_pool, and
minute_target_scope, then combines them into a future-write plan. It does not
write condition tables, run migrations, pull minute bars, start workers, or
touch the old system.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.basis import build_condition_basis_dry_run
from ashare_v3.condition.pool import build_condition_pool_dry_run
from ashare_v3.condition.readiness_plan import build_condition_layer_execute_readiness_plan
from ashare_v3.condition.scope import build_minute_target_scope_dry_run
from ashare_v3.condition.scope_policy import load_scope_policy
from check_condition_source_ready import DEFAULT_DSN, run_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v3 condition-layer execute readiness plan.")
    parser.add_argument("--source-trade-date", required=True, help="Finalized ingestion trade date, e.g. 20260522.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only N2-E0 mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected in N2-E0. This script never executes SQL.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--policy", default="", help="Optional scope selection policy JSON path.")
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-E0 only builds an execute readiness plan. It never supports --execute.")

    ready = run_check(args.dsn, args.source_trade_date)
    scope_policy = load_scope_policy(args.policy) if args.policy else None
    basis_report = build_condition_basis_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
    )
    pool_report = build_condition_pool_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
    )
    scope_report = build_minute_target_scope_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
        scope_policy=scope_policy,
    )
    report = build_condition_layer_execute_readiness_plan(
        basis_report=basis_report,
        pool_report=pool_report,
        scope_report=scope_report,
    )

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["execute_preconditions_passed"] else 2


def format_summary(report: dict[str, Any]) -> str:
    counts = report["stage_counts"]
    quality = report["quality_summary"]
    would_write = report["would_write"]
    row_count_summary = ", ".join(f"{table}: {spec['row_count']}" for table, spec in would_write.items())
    return "\n".join(
        [
            "condition-layer execute readiness plan",
            f"  source_trade_date={report['source_trade_date']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  prev_trade_date={report['prev_trade_date']}",
            f"  planned_run_id={report['planned_run_id']}",
            f"  policy={report['policy_name']} policy_hash={report['policy_hash']}",
            f"  basis_rows stock={counts['condition_basis']['stock']} index={counts['condition_basis']['index']} board={counts['condition_basis']['board']}",
            f"  pool_rows stock={counts['condition_pool']['stock']} index={counts['condition_pool']['index']} board={counts['condition_pool']['board']}",
            f"  scope_rows stock={counts['minute_target_scope']['stock']} index={counts['minute_target_scope']['index']} board={counts['minute_target_scope']['board']}",
            f"  would_write={{{row_count_summary}}}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']} quality_items={quality['quality_item_count']}",
            f"  execute_preconditions_passed={report['execute_preconditions_passed']} requires_user_confirmation={report['requires_user_confirmation']}",
            f"  blocked_reasons={report['blocked_reasons']}",
            f"  not_ready_reasons={report['not_ready_reasons']}",
            f"  rollback_strategy={report['rollback_plan']['strategy']} rollback_run_id={report['rollback_plan']['run_id']}",
            "  writes_performed=false will_execute_sql=false minute_kline_pulled=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
