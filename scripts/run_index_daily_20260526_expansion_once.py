#!/usr/bin/env python3
"""Run N1 index_daily 20260526 universe expansion preflight or final execute."""

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

from ashare_v3.ingestion.index_daily_20260526_expansion_execute import (  # noqa: E402
    DEFAULT_PATHS,
    TRADE_DATE,
    DefaultIndexDaily20260526ExpansionSourceAdapter,
    IndexDaily20260526ExpansionBlocked,
    build_commit_plan,
    build_execute_contract,
    build_execute_preflight_report,
    build_expected_scope_from_db,
    build_snapshot_from_db,
    build_source_bundle,
    execute_commit_transaction,
    validate_commit_preconditions,
    validate_execute_request,
    validate_source_bundle,
    write_contract_files,
    write_preflight_files,
)


def default_dependencies() -> dict:
    return {
        "build_snapshot_from_db": build_snapshot_from_db,
        "build_expected_scope_from_db": build_expected_scope_from_db,
        "source_adapter_factory": build_default_source_adapter,
        "connect": lambda dsn: psycopg.connect(dsn, connect_timeout=10),
        "write_preflight_files": write_preflight_files,
        "write_contract_files": write_contract_files,
    }


def build_default_source_adapter(**kwargs) -> DefaultIndexDaily20260526ExpansionSourceAdapter:
    args = kwargs.get("args")
    return DefaultIndexDaily20260526ExpansionSourceAdapter(
        tushare_token=load_tushare_token(),
        mootdx_offset=int(getattr(args, "mootdx_offset", 800)),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", default=TRADE_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql:///ashare_v3"))
    parser.add_argument("--execute-contract-json", default=str(DEFAULT_PATHS["contract_json"]))
    parser.add_argument("--execute-contract-md", default=str(DEFAULT_PATHS["contract_md"]))
    parser.add_argument("--json-report-path", default=str(DEFAULT_PATHS["preflight_json"]))
    parser.add_argument("--markdown-report-path", default=str(DEFAULT_PATHS["preflight_md"]))
    parser.add_argument("--mootdx-offset", type=int, default=800)
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

    if args.trade_date != TRADE_DATE:
        print(f"BLOCKED: this runner is fixed to trade_date={TRADE_DATE}", file=sys.stderr)
        return 2

    if args.execute:
        try:
            validate_execute_request(
                execute_requested=args.execute,
                user_confirmed=args.user_confirmed,
                postgres_commit_enabled=args.postgres_commit_enabled,
            )
        except IndexDaily20260526ExpansionBlocked as exc:
            print(f"BLOCKED: {exc}", file=sys.stderr)
            return 2

    snapshot = deps["build_snapshot_from_db"](dsn=args.dsn, trade_date=args.trade_date)
    contract = build_execute_contract(snapshot)
    preflight = build_execute_preflight_report(
        snapshot,
        execute_requested=args.execute,
        user_confirmed=args.user_confirmed,
        postgres_commit_enabled=args.postgres_commit_enabled,
    )
    if not args.no_write_report:
        deps["write_contract_files"](
            contract,
            json_path=args.execute_contract_json,
            markdown_path=args.execute_contract_md,
        )
        deps["write_preflight_files"](
            preflight,
            json_path=args.json_report_path,
            markdown_path=args.markdown_report_path,
        )
    print(json.dumps(preflight, ensure_ascii=False, indent=2))

    if preflight["result"] != "PREFLIGHT_PASS":
        if args.execute:
            print(f"BLOCKED: {', '.join(preflight['blockers'])}", file=sys.stderr)
            return 2
        return 1
    if not args.execute:
        return 0

    try:
        expected_scope = deps["build_expected_scope_from_db"](dsn=args.dsn, trade_date=args.trade_date)
        adapter = deps["source_adapter_factory"](args=args, contract=contract)
        source_bundle = build_source_bundle(
            adapter=adapter,
            trade_date=args.trade_date,
            expected_scope=expected_scope,
            source_fetch_enabled=args.execute,
        )
        validation_report = validate_source_bundle(bundle=source_bundle, expected_scope=expected_scope)
        validate_commit_preconditions(
            snapshot=snapshot,
            validation_report=validation_report,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
        commit_plan = build_commit_plan(bundle=source_bundle, validation_report=validation_report, baseline=snapshot)
        conn = deps["connect"](args.dsn)
        commit_result = execute_commit_transaction(
            conn,
            commit_plan=commit_plan,
            execute_requested=args.execute,
            user_confirmed=args.user_confirmed,
            postgres_commit_enabled=args.postgres_commit_enabled,
        )
    except IndexDaily20260526ExpansionBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "stage": "N1 index_daily 20260526 universe expansion execute",
                "layer_role": "N1_ingestion",
                "result": "EXECUTE_PASS",
                "execute_authorized": True,
                "source_validation": validation_report,
                "commit_result": commit_result,
                "side_effects": {
                    "writes_postgres": True,
                    "writes_parquet": False,
                    "writes_outbox": False,
                    "writes_inbox_or_checkpoint": False,
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
