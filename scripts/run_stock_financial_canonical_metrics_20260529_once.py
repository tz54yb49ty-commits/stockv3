#!/usr/bin/env python3
"""Run N1 stock_financial canonical metrics 20260529 preflight or execute."""

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

from ashare_v3.ingestion.stock_financial_canonical_metrics import (  # noqa: E402
    DEFAULT_PATHS,
    DEFAULT_SOURCE_BUNDLE_CACHE_PATH,
    TRADE_DATE,
    StockFinancialCanonicalBlocked,
    build_commit_plan,
    build_dry_run_report,
    build_execute_contract,
    build_execute_preflight_report,
    build_snapshot_from_cache,
    execute_commit_transaction,
    validate_commit_preconditions,
    validate_execute_request,
    write_artifacts,
)


def default_dependencies() -> dict:
    return {
        "build_snapshot_from_cache": build_snapshot_from_cache,
        "connect": lambda dsn: psycopg.connect(dsn, connect_timeout=10),
        "write_artifacts": write_artifacts,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-trade-date", "--trade-date", default=TRADE_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"))
    parser.add_argument("--source-bundle-cache-path", default=None)
    parser.add_argument("--dry-run-json", default=str(DEFAULT_PATHS["dry_run_json"]))
    parser.add_argument("--dry-run-md", default=str(DEFAULT_PATHS["dry_run_md"]))
    parser.add_argument("--contract-json", default=str(DEFAULT_PATHS["contract_json"]))
    parser.add_argument("--contract-md", default=str(DEFAULT_PATHS["contract_md"]))
    parser.add_argument("--json-report-path", default=str(DEFAULT_PATHS["preflight_json"]))
    parser.add_argument("--markdown-report-path", default=str(DEFAULT_PATHS["preflight_md"]))
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--postgres-commit-enabled", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, dependencies: dict | None = None) -> int:
    args = parse_args(argv)
    deps = default_dependencies()
    if dependencies:
        deps.update(dependencies)

    if args.source_trade_date != TRADE_DATE:
        print(f"BLOCKED: this runner is fixed to source_trade_date={TRADE_DATE}", file=sys.stderr)
        return 2

    if args.execute:
        try:
            validate_execute_request(
                execute_requested=args.execute,
                user_confirmed=args.user_confirmed,
                postgres_commit_enabled=args.postgres_commit_enabled,
            )
        except StockFinancialCanonicalBlocked as exc:
            print(f"BLOCKED: {exc}", file=sys.stderr)
            return 2

    cache_path = args.source_bundle_cache_path or str(DEFAULT_SOURCE_BUNDLE_CACHE_PATH)
    try:
        snapshot = deps["build_snapshot_from_cache"](
            dsn=args.dsn,
            source_trade_date=args.source_trade_date,
            source_bundle_cache_path=cache_path,
        )
        dry_run = build_dry_run_report(snapshot)
        contract = build_execute_contract(snapshot, dry_run)
        preflight = build_execute_preflight_report(snapshot, dry_run)
    except StockFinancialCanonicalBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    if not args.no_write_report:
        deps["write_artifacts"](dry_run, contract, preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2))

    if preflight["result"] != "PREFLIGHT_PASS":
        if args.execute:
            print(f"BLOCKED: {', '.join(preflight['blockers'])}", file=sys.stderr)
            return 2
        return 1
    if not args.execute:
        return 0

    try:
        validate_commit_preconditions(
            snapshot=snapshot,
            dry_run=dry_run,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
        commit_plan = build_commit_plan(snapshot=snapshot, dry_run=dry_run)
        conn = deps["connect"](args.dsn)
        commit_result = execute_commit_transaction(
            conn,
            commit_plan=commit_plan,
            execute_requested=args.execute,
            user_confirmed=args.user_confirmed,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
    except StockFinancialCanonicalBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "stage": "N1 stock_financial canonical metrics 20260529 execute",
                "layer_role": "N1_ingestion",
                "result": "EXECUTE_PASS",
                "execute_authorized": True,
                "source_batch_id": commit_plan.get("batch_id"),
                "source_version": commit_plan.get("source_version"),
                "previous_source_version": commit_plan.get("previous_source_version"),
                "commit_result": commit_result,
                "quality": dry_run.get("quality"),
                "side_effects": {
                    "writes_postgres": True,
                    "writes_stock_financial_metrics_fact": True,
                    "writes_condition_tables": False,
                    "writes_outbox": False,
                    "writes_inbox_or_checkpoint": False,
                    "writes_parquet": False,
                    "enters_n2_n3_n4_n5_n6": False,
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
