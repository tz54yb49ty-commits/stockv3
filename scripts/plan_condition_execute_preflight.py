#!/usr/bin/env python3
"""Build the N2-E2 condition-layer execute preflight report.

This script performs only read-only checks. It does not execute SQL writes,
run migrations, write condition tables, pull minute bars, start workers, or
touch the old system.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from ashare_v3.condition.basis import build_condition_basis_dry_run
from ashare_v3.condition.execute_contract import build_condition_execute_contract
from ashare_v3.condition.execute_preflight import (
    build_condition_execute_preflight,
    fetch_active_run_status,
    fetch_schema_status,
)
from ashare_v3.condition.pool import build_condition_pool_dry_run
from ashare_v3.condition.readiness_plan import build_condition_layer_execute_readiness_plan
from ashare_v3.condition.scope import build_minute_target_scope_dry_run
try:
    from run_condition_layer_execute import condition_runner_report_metadata, resolve_condition_runner_policy
except ModuleNotFoundError:
    from scripts.run_condition_layer_execute import condition_runner_report_metadata, resolve_condition_runner_policy
from check_condition_source_ready import DEFAULT_DSN, run_check


def main() -> int:
    parser = argparse.ArgumentParser(description="Build v3 condition-layer execute preflight report.")
    parser.add_argument("--source-trade-date", required=True, help="Finalized ingestion trade date, e.g. 20260522.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run mode. This is the only N2-E2 mode.")
    parser.add_argument("--execute", action="store_true", help="Rejected in N2-E2. This script never executes SQL.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--policy", default="", help="Optional scope selection policy JSON path.")
    parser.add_argument("--user-confirmed", action="store_true", help="Record user confirmation in the preflight contract only.")
    parser.add_argument("--overwrite", action="store_true", help="Plan overwrite preflight; still does not execute SQL.")
    parser.add_argument("--operator", default="manual", help="Operator label recorded in the dry-run contract.")
    parser.add_argument("--confirmation-note", default="", help="Optional confirmation note presence marker.")
    parser.add_argument("--report-path", default="", help="Optional JSON report path.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    args = parser.parse_args()

    if args.execute:
        parser.error("N2-E2 only builds an execute preflight report. It never supports --execute.")

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
    contract = build_condition_execute_contract(
        readiness_plan,
        user_confirmed=args.user_confirmed,
        overwrite=args.overwrite,
        operator=args.operator,
        confirmation_note=args.confirmation_note,
    )
    schema_status = fetch_schema_status(args.dsn)
    active_run_status = fetch_active_run_status(
        args.dsn,
        source_trade_date=str(readiness_plan["source_trade_date"]),
        for_trade_date=str(readiness_plan["for_trade_date"]),
        overwrite=args.overwrite,
    )
    report = build_condition_execute_preflight(
        readiness_plan=readiness_plan,
        execute_contract=contract,
        schema_status=schema_status,
        active_run_status=active_run_status,
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
    return 0


def format_summary(report: dict[str, Any]) -> str:
    rows = report["expected_row_counts"]
    row_count_summary = ", ".join(f"{table}: {count}" for table, count in rows.items())
    quality = report["quality_summary"]
    schema = report["schema_status"]
    active = report["active_run_status"]
    return "\n".join(
        [
            "condition-layer execute preflight",
            f"  source_trade_date={report['source_trade_date']}",
            f"  for_trade_date={report['for_trade_date']}",
            f"  prev_trade_date={report['prev_trade_date']}",
            f"  run_id_preview={report['run_id_preview']}",
            f"  policy={report['policy_name']} policy_hash={report['policy_hash']}",
            f"  expected_rows={{{row_count_summary}}}",
            f"  p0_count={quality['p0_count']} p1_count={quality['p1_count']} p2_count={quality['p2_count']}",
            f"  schema_ready={schema['schema_ready']} migration_required={schema['migration_required']} missing_tables={schema['missing_tables']}",
            f"  active_exists={active['active_exists']} blocked_by_active_run={active['blocked_by_active_run']} overwrite={report['overwrite']}",
            f"  user_confirmation_required={report['user_confirmation_required']} user_confirmed={report['user_confirmed']}",
            f"  rollback_sql_preview_count={len(report['rollback_sql_preview'])} rollback_strategy={report['rollback_strategy']}",
            f"  execute_allowed={report['execute_allowed']} blocked_reasons={report['blocked_reasons']}",
            "  writes_performed=false will_execute_sql=false migration_performed=false minute_kline_pulled=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
