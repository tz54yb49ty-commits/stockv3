#!/usr/bin/env python3
"""Build the N2-E1 condition-layer execute/rollback contract.

This script runs the read-only N2-E0 plan, then emits the contract required
before a real execute. It never executes SQL, writes condition tables, runs
migrations, pulls minute bars, starts workers, or touches the old system.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.basis import build_condition_basis_dry_run
from ashare_v3.condition.execute_contract import build_condition_execute_contract
from ashare_v3.condition.pool import build_condition_pool_dry_run
from ashare_v3.condition.readiness_plan import build_condition_layer_execute_readiness_plan
from ashare_v3.condition.scope import build_minute_target_scope_dry_run
try:
    from run_condition_layer_execute import condition_runner_report_metadata, resolve_condition_runner_policy
except ModuleNotFoundError:
    from scripts.run_condition_layer_execute import condition_runner_report_metadata, resolve_condition_runner_policy
from check_condition_source_ready import DEFAULT_DSN, run_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v3 condition-layer execute contract.")
    parser.add_argument("--source-trade-date", required=True, help="Finalized ingestion trade date, e.g. 20260522.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only N2-E1 mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected in N2-E1. This script never executes SQL.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--policy", default="", help="Optional scope selection policy JSON path.")
    parser.add_argument("--user-confirmed", action="store_true", help="Record user confirmation in the contract report only.")
    parser.add_argument("--overwrite", action="store_true", help="Plan overwrite contract; still does not execute SQL.")
    parser.add_argument("--operator", default="manual", help="Operator label recorded in the dry-run contract.")
    parser.add_argument("--confirmation-note", default="", help="Optional confirmation note presence marker.")
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-E1 only builds an execute contract. It never supports --execute.")

    ready = run_check(args.dsn, args.source_trade_date)
    policy_bundle = resolve_condition_runner_policy(args.policy)
    scope_policy = policy_bundle.scope_policy
    condition_pool_policy = policy_bundle.condition_pool_policy
    basis_report = build_condition_basis_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
    )
    pool_report = build_condition_pool_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
        condition_pool_policy=condition_pool_policy,
    )
    scope_report = build_minute_target_scope_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
        scope_policy=scope_policy,
        condition_pool_policy=condition_pool_policy,
    )
    readiness_plan = build_condition_layer_execute_readiness_plan(
        basis_report=basis_report,
        pool_report=pool_report,
        scope_report=scope_report,
    )
    report = build_condition_execute_contract(
        readiness_plan,
        user_confirmed=args.user_confirmed,
        overwrite=args.overwrite,
        operator=args.operator,
        confirmation_note=args.confirmation_note,
    )
    report["policy_runner_metadata"] = condition_runner_report_metadata(
        policy_bundle,
        scope_report,
        execute_requested=False,
    )

    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if not report["blocked_reasons"] else 2


def format_summary(report: dict[str, Any]) -> str:
    rows = report["row_count_contract"]["expected_rows_by_table"]
    row_count_summary = ", ".join(f"{table}: {count}" for table, count in rows.items())
    quality = report["quality_policy"]
    active = report["active_run_contract"]
    return "\n".join(
        [
            "condition-layer execute contract",
            f"  source_trade_date={report['source_trade_date']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  prev_trade_date={report['prev_trade_date']}",
            f"  policy={report['policy_name']} policy_hash={report['policy_hash']}",
            f"  execute_run_id_template={report['run_id_contract']['execute_run_id_template']}",
            f"  active_run_policy={active['active_run_policy']} overwrite={report['overwrite']}",
            f"  expected_rows={{{row_count_summary}}}",
            f"  expected_hash={report['row_count_contract']['pre_execute_expected_hash']}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            f"  user_confirmed={report['user_confirmed']} execute_request_allowed={report['execute_request_allowed']}",
            f"  blocked_reasons={report['blocked_reasons']}",
            f"  not_ready_reasons={report['not_ready_reasons']}",
            f"  rollback_strategy={report['rollback_contract']['strategy']}",
            "  writes_performed=false will_execute_sql=false migration_performed=false minute_kline_pulled=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
