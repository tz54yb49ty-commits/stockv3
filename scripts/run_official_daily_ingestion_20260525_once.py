#!/usr/bin/env python3
"""Run the N1 official daily 20260525 execute preflight.

This runner performs the final preflight for the execute-capable implementation.
By default it remains read-only: it does not call external sources, write
PostgreSQL, write Parquet, update active source versions, or enter downstream
layers.
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

from ashare_v3.ingestion.tushare_env import load_tushare_token  # noqa: E402

from ashare_v3.ingestion.official_daily_ingestion_execute import (  # noqa: E402
    DEFAULT_EXECUTE_CONTRACT_JSON_PATH,
    DEFAULT_DRY_RUN_REPORT_PATH,
    DEFAULT_PREFLIGHT_JSON_PATH,
    DEFAULT_PREFLIGHT_MARKDOWN_PATH,
    DEFAULT_ROLLBACK_SQL_PATH,
    DefaultOfficialDailySourceAdapter,
    OfficialDailyExecuteBlocked,
    build_commit_plan,
    build_baseline_snapshot_from_db,
    build_execute_preflight_report,
    build_expected_scope_from_db,
    execute_commit_transaction,
    fetch_official_daily_sources,
    load_execute_contract,
    load_dry_run_report,
    validate_commit_preconditions,
    validate_execute_contract,
    validate_execute_request,
    validate_source_bundle,
    write_preflight_files,
)
from ashare_v3.ingestion.official_daily_ingestion_plan import DEFAULT_EOD_REPORT_JSON  # noqa: E402


def default_dependencies() -> dict:
    return {
        "load_execute_contract": load_execute_contract,
        "load_dry_run_report": load_dry_run_report,
        "build_baseline_snapshot_from_db": build_baseline_snapshot_from_db,
        "build_expected_scope_from_db": build_expected_scope_from_db,
        "source_adapter_factory": build_default_source_adapter,
        "connect": lambda dsn: psycopg.connect(dsn, connect_timeout=10),
        "fetch_official_daily_sources": fetch_official_daily_sources,
        "validate_source_bundle": validate_source_bundle,
        "validate_commit_preconditions": validate_commit_preconditions,
        "build_commit_plan": build_commit_plan,
        "execute_commit_transaction": execute_commit_transaction,
        "write_preflight_files": write_preflight_files,
    }


def build_default_source_adapter(**kwargs) -> DefaultOfficialDailySourceAdapter:
    args = kwargs.get("args")
    return DefaultOfficialDailySourceAdapter(
        tushare_token=load_tushare_token(),
        mootdx_offset=int(getattr(args, "mootdx_offset", 800)),
    )


def main(argv: list[str] | None = None, *, dependencies: dict | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", default="20260525")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql:///ashare_v3"))
    parser.add_argument("--dry-run-report-json", default=DEFAULT_DRY_RUN_REPORT_PATH)
    parser.add_argument("--execute-contract-json", default=DEFAULT_EXECUTE_CONTRACT_JSON_PATH)
    parser.add_argument("--eod-report-json", default=DEFAULT_EOD_REPORT_JSON)
    parser.add_argument("--json-report-path", default=DEFAULT_PREFLIGHT_JSON_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_PREFLIGHT_MARKDOWN_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--mootdx-offset", type=int, default=800)
    parser.add_argument("--no-write-report", action="store_true", help="Print JSON only; do not write preflight artifacts.")
    parser.add_argument("--execute", action="store_true", help="Requires --user-confirmed and later final-gate flags.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required with --execute.")
    parser.add_argument("--source-fetch-enabled", action="store_true", help="Final-gate flag; disabled by default and not used in this preflight run.")
    parser.add_argument("--postgres-commit-enabled", action="store_true", help="Final-gate flag; disabled by default and not used in this preflight run.")
    args = parser.parse_args(argv)
    deps = default_dependencies()
    if dependencies:
        deps.update(dependencies)

    if args.execute:
        try:
            validate_execute_request(execute_requested=args.execute, user_confirmed=args.user_confirmed)
        except OfficialDailyExecuteBlocked as exc:
            print(f"BLOCKED: {exc}", file=sys.stderr)
            return 2

    try:
        contract = deps["load_execute_contract"](args.execute_contract_json)
        validate_execute_contract(contract)
    except OfficialDailyExecuteBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    dry_run_report = deps["load_dry_run_report"](args.dry_run_report_json)
    baseline = deps["build_baseline_snapshot_from_db"](
        dsn=args.dsn,
        for_trade_date=args.trade_date,
        eod_report_path=args.eod_report_json,
    )
    report = build_execute_preflight_report(
        dry_run_report=dry_run_report,
        baseline=baseline,
        execute_requested=args.execute,
        user_confirmed=args.user_confirmed,
        source_fetch_enabled=args.source_fetch_enabled,
        postgres_commit_enabled=args.postgres_commit_enabled,
        rollback_sql_path=args.rollback_sql_path,
    )
    if not args.no_write_report:
        deps["write_preflight_files"](report, json_path=args.json_report_path, markdown_path=args.markdown_report_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["result"] != "PREFLIGHT_PASS":
        if args.execute:
            print(f"BLOCKED: {', '.join(report['blockers'])}", file=sys.stderr)
            return 2
        return 1

    if not args.execute:
        return 0

    try:
        expected_scope = deps["build_expected_scope_from_db"](
            dsn=args.dsn,
            for_trade_date=args.trade_date,
            eod_report_path=args.eod_report_json,
        )
        adapter = deps["source_adapter_factory"](args=args, contract=contract)
        source_bundle = deps["fetch_official_daily_sources"](
            adapter=adapter,
            for_trade_date=args.trade_date,
            expected_scope=expected_scope,
            source_fetch_enabled=args.source_fetch_enabled,
        )
        validation_report = deps["validate_source_bundle"](
            bundle=source_bundle,
            expected_scope=expected_scope,
            for_trade_date=args.trade_date,
        )
        deps["validate_commit_preconditions"](
            dry_run_report=dry_run_report,
            baseline=baseline,
            validation_report=validation_report,
            source_fetch_enabled=args.source_fetch_enabled,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
        commit_plan = deps["build_commit_plan"](
            bundle=source_bundle,
            validation_report=validation_report,
            baseline=baseline,
            for_trade_date=args.trade_date,
        )
        conn = deps["connect"](args.dsn)
        commit_result = deps["execute_commit_transaction"](
            conn,
            commit_plan=commit_plan,
            execute_requested=args.execute,
            user_confirmed=args.user_confirmed,
            source_fetch_enabled=args.source_fetch_enabled,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
    except OfficialDailyExecuteBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "stage": "N1 official daily fact ingestion execute",
                "layer_role": "N1_ingestion",
                "result": "EXECUTE_PASS",
                "execute_authorized": True,
                "preflight_result": report["result"],
                "source_validation": validation_report,
                "commit_result": commit_result,
                "side_effects": {
                    "writes_postgres": True,
                    "writes_parquet": False,
                    "writes_outbox": False,
                    "writes_inbox_or_checkpoint": False,
                    "enters_n3_n4_n5_n6": False,
                    "worker_started": False,
                    "old_system_touched": False,
                    "real_trading": False,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
