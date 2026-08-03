#!/usr/bin/env python3
"""Run one daily N1 stock_financial canonical metrics preflight or execute."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import ashare_v3.ingestion.stock_financial_canonical_metrics as metrics  # noqa: E402
import ashare_v3.ingestion.stock_financial_canonical_source_bundle as source_bundle  # noqa: E402
from ashare_v3.ingestion.common import require_yyyymmdd  # noqa: E402


def default_dependencies() -> dict[str, Any]:
    return {
        "build_snapshot_from_cache": metrics.build_snapshot_from_cache,
        "load_active_source_metadata": metrics.load_active_source_metadata,
        "connect": lambda dsn: psycopg.connect(dsn, connect_timeout=10),
        "write_artifacts": metrics.write_artifacts,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-trade-date", "--trade-date", required=True)
    parser.add_argument("--target-source-version", help="Optional guard; must equal stock_financial_${source_trade_date}_v2.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"))
    parser.add_argument("--source-bundle-cache-path")
    parser.add_argument("--dry-run-json")
    parser.add_argument("--dry-run-md")
    parser.add_argument("--contract-json")
    parser.add_argument("--contract-md")
    parser.add_argument("--preflight-json")
    parser.add_argument("--preflight-md")
    parser.add_argument("--json-report-path")
    parser.add_argument("--markdown-report-path")
    parser.add_argument("--rollback-sql-path")
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--postgres-commit-enabled", action="store_true")
    return parser.parse_args(argv)


def apply_context_and_paths(args: argparse.Namespace) -> str:
    source_trade_date = require_yyyymmdd(args.source_trade_date, "source_trade_date")
    metrics.apply_canonical_context(source_trade_date)
    source_bundle.apply_source_bundle_context(source_trade_date)
    expected_source_version = metrics.SOURCE_VERSION
    if args.target_source_version and args.target_source_version != expected_source_version:
        raise metrics.StockFinancialCanonicalBlocked(
            f"target_source_version_mismatch: expected={expected_source_version}, actual={args.target_source_version}"
        )
    paths = dict(metrics.DEFAULT_PATHS)
    overrides = {
        "dry_run_json": args.dry_run_json,
        "dry_run_md": args.dry_run_md,
        "contract_json": args.contract_json,
        "contract_md": args.contract_md,
        "preflight_json": args.preflight_json,
        "preflight_md": args.preflight_md,
        "rollback_sql": args.rollback_sql_path,
    }
    for key, raw_path in overrides.items():
        if raw_path:
            paths[key] = Path(raw_path)
    metrics.DEFAULT_PATHS = paths
    if args.source_bundle_cache_path:
        metrics.DEFAULT_SOURCE_BUNDLE_CACHE_PATH = Path(args.source_bundle_cache_path)
    return source_trade_date


def write_json(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(metrics.json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: str | None, payload: dict[str, Any], title: str) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "result": payload.get("result"),
        "source_trade_date": payload.get("source_trade_date"),
        "source_batch_id": payload.get("source_batch_id"),
        "source_version": payload.get("source_version"),
        "previous_source_version": payload.get("previous_source_version"),
        "commit_result": payload.get("commit_result"),
        "quality": payload.get("quality"),
        "side_effects": payload.get("side_effects"),
    }
    target.write_text(f"# {title}\n\n```json\n{json.dumps(metrics.json_safe(summary), ensure_ascii=False, indent=2)}\n```\n", encoding="utf-8")


def main(argv: list[str] | None = None, *, dependencies: dict[str, Any] | None = None) -> int:
    args = parse_args(argv)
    deps = default_dependencies()
    if dependencies:
        deps.update(dependencies)

    try:
        source_trade_date = apply_context_and_paths(args)
    except metrics.StockFinancialCanonicalBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    if args.execute:
        try:
            metrics.validate_execute_request(
                execute_requested=args.execute,
                user_confirmed=args.user_confirmed,
                postgres_commit_enabled=args.postgres_commit_enabled,
            )
        except metrics.StockFinancialCanonicalBlocked as exc:
            print(f"BLOCKED: {exc}", file=sys.stderr)
            return 2

    cache_path = args.source_bundle_cache_path or str(metrics.DEFAULT_SOURCE_BUNDLE_CACHE_PATH)
    try:
        snapshot = deps["build_snapshot_from_cache"](
            dsn=args.dsn,
            source_trade_date=source_trade_date,
            source_bundle_cache_path=cache_path,
        )
        dry_run = metrics.build_dry_run_report(snapshot)
        contract = metrics.build_execute_contract(snapshot, dry_run)
        preflight = metrics.build_execute_preflight_report(snapshot, dry_run)
    except metrics.StockFinancialCanonicalBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    if not args.no_write_report:
        deps["write_artifacts"](dry_run, contract, preflight)
    if args.preflight_json:
        write_json(args.preflight_json, preflight)
    if args.preflight_md:
        write_markdown(args.preflight_md, preflight, "N1 Stock Financial Canonical Metrics Execute Preflight")
    print(json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True))

    if preflight["result"] != "PREFLIGHT_PASS":
        if args.execute:
            print(f"BLOCKED: {', '.join(preflight['blockers'])}", file=sys.stderr)
            return 2
        return 1
    if not args.execute:
        return 0

    try:
        metrics.validate_commit_preconditions(
            snapshot=snapshot,
            dry_run=dry_run,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
        active_source_metadata = deps["load_active_source_metadata"](
            dsn=args.dsn,
            source_trade_date=source_trade_date,
        )
        snapshot = {**snapshot, "active_source_metadata": active_source_metadata}
        commit_plan = metrics.build_commit_plan(snapshot=snapshot, dry_run=dry_run)
        conn = deps["connect"](args.dsn)
        commit_result = metrics.execute_commit_transaction(
            conn,
            commit_plan=commit_plan,
            execute_requested=args.execute,
            user_confirmed=args.user_confirmed,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
    except metrics.StockFinancialCanonicalBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    execute_report = {
        "stage": f"N1 stock_financial canonical metrics {source_trade_date} execute",
        "layer_role": "N1_ingestion",
        "result": "EXECUTE_PASS",
        "execute_authorized": True,
        "source_trade_date": source_trade_date,
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
    }
    write_json(args.json_report_path, execute_report)
    write_markdown(args.markdown_report_path, execute_report, "N1 Stock Financial Canonical Metrics Execute Report")
    print(json.dumps(metrics.json_safe(execute_report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
