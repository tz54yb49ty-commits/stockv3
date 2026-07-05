#!/usr/bin/env python3
"""Run the guarded N1 20260608 source-facts implementation/preflight wrapper."""

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

from ashare_v3.ingestion.source_facts_20260608_execute import (  # noqa: E402
    CONDITION_DEFAULT_PATHS,
    CONTRACT_PATH,
    EXECUTE_REPORT_JSON_PATH,
    EXECUTE_REPORT_MD_PATH,
    IMPLEMENTATION_REPORT_JSON_PATH,
    IMPLEMENTATION_REPORT_MD_PATH,
    IDENTITY_REPAIR_HANDOFF_MD_PATH,
    IDENTITY_REPAIR_HANDOFF_PATH,
    OFFICIAL_DEFAULT_PATHS,
    PREFLIGHT_PATH,
    TRADE_DATE,
    SourceFacts20260608Blocked,
    DefaultConditionSourceActivation20260608SourceBuilder,
    DefaultOfficialDaily20260608SourceAdapter,
    build_handoff_report,
    build_implementation_report,
    condition_build_commit_plan,
    condition_build_dry_run_report,
    condition_build_execute_contract,
    condition_build_execute_preflight_report,
    condition_build_snapshot_from_db,
    condition_execute_commit_transaction,
    condition_validate_commit_preconditions,
    condition_validate_source_bundle,
    official_build_commit_plan,
    official_build_dry_run_report,
    official_build_execute_contract,
    official_build_execute_preflight_report,
    official_build_expected_scope_from_db,
    official_build_snapshot_from_db,
    official_execute_commit_transaction,
    official_fetch_official_daily_sources,
    official_load_execute_contract,
    official_validate_commit_preconditions,
    official_validate_execute_contract,
    official_validate_source_bundle,
    render_handoff_markdown,
    render_implementation_markdown,
    run_execute_pipeline,
    validate_execute_request,
    validate_preflight_allows_execute,
    validate_trade_date,
    load_source_facts_index_board_probe,
    load_source_facts_stock_source_probe,
    load_preflight,
    write_execute_report_files,
    write_json_report,
    write_text_report,
)
from ashare_v3.ingestion.tushare_env import load_tushare_token  # noqa: E402


def build_default_official_source_adapter(**kwargs) -> DefaultOfficialDaily20260608SourceAdapter:
    args = kwargs.get("args")
    return DefaultOfficialDaily20260608SourceAdapter(
        tushare_token=load_tushare_token(),
        mootdx_offset=int(getattr(args, "mootdx_offset", 900)),
    )


def build_default_condition_source_builder(**kwargs) -> DefaultConditionSourceActivation20260608SourceBuilder:
    args = kwargs.get("args")
    return DefaultConditionSourceActivation20260608SourceBuilder(
        tdx_root=getattr(args, "tdx_root", "/Volumes/MacRaid/tdxdata/tdx"),
        tushare_token=load_tushare_token(),
    )


def default_dependencies() -> dict:
    return {
        "connect": lambda dsn: psycopg.connect(dsn, connect_timeout=10),
        "official_load_execute_contract": official_load_execute_contract,
        "official_validate_execute_contract": official_validate_execute_contract,
        "official_build_snapshot_from_db": official_build_snapshot_from_db,
        "official_build_dry_run_report": official_build_dry_run_report,
        "official_build_execute_contract": official_build_execute_contract,
        "official_build_execute_preflight_report": official_build_execute_preflight_report,
        "official_build_expected_scope_from_db": official_build_expected_scope_from_db,
        "official_source_adapter_factory": build_default_official_source_adapter,
        "official_fetch_official_daily_sources": official_fetch_official_daily_sources,
        "official_validate_source_bundle": official_validate_source_bundle,
        "official_validate_commit_preconditions": official_validate_commit_preconditions,
        "official_build_commit_plan": official_build_commit_plan,
        "official_execute_commit_transaction": official_execute_commit_transaction,
        "official_load_stock_source_probe": load_source_facts_stock_source_probe,
        "official_load_index_board_source_probe": load_source_facts_index_board_probe,
        "condition_build_snapshot_from_db": condition_build_snapshot_from_db,
        "condition_build_dry_run_report": condition_build_dry_run_report,
        "condition_build_execute_contract": condition_build_execute_contract,
        "condition_build_execute_preflight_report": condition_build_execute_preflight_report,
        "condition_source_builder_factory": build_default_condition_source_builder,
        "condition_validate_source_bundle": condition_validate_source_bundle,
        "condition_validate_commit_preconditions": condition_validate_commit_preconditions,
        "condition_build_commit_plan": condition_build_commit_plan,
        "condition_execute_commit_transaction": condition_execute_commit_transaction,
        "write_dry_run_files": lambda report, *, json_path, markdown_path: (
            write_json_report(report, json_path),
            write_text_report(json.dumps(report, ensure_ascii=False, indent=2) + "\n", markdown_path),
        ),
        "write_contract_files": lambda report, *, json_path, markdown_path: (
            write_json_report(report, json_path),
            write_text_report(json.dumps(report, ensure_ascii=False, indent=2) + "\n", markdown_path),
        ),
        "write_preflight_files": lambda report, *, json_path, markdown_path: (
            write_json_report(report, json_path),
            write_text_report(json.dumps(report, ensure_ascii=False, indent=2) + "\n", markdown_path),
        ),
        "write_execute_report_files": write_execute_report_files,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", default=TRADE_DATE)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql:///ashare_v3"))
    parser.add_argument("--tdx-root", default="/Volumes/MacRaid/tdxdata/tdx")
    parser.add_argument("--mootdx-offset", type=int, default=900)
    parser.add_argument("--implementation-json", default=str(IMPLEMENTATION_REPORT_JSON_PATH))
    parser.add_argument("--implementation-md", default=str(IMPLEMENTATION_REPORT_MD_PATH))
    parser.add_argument("--handoff-json", default=str(IDENTITY_REPAIR_HANDOFF_PATH))
    parser.add_argument("--handoff-md", default=str(IDENTITY_REPAIR_HANDOFF_MD_PATH))
    parser.add_argument("--execute-contract-json", default=str(CONTRACT_PATH))
    parser.add_argument("--stock-probe-json", default=str(PREFLIGHT_PATH))
    parser.add_argument("--index-board-probe-json", default=str(PREFLIGHT_PATH))
    parser.add_argument("--official-dry-run-json", default=str(OFFICIAL_DEFAULT_PATHS["dry_run_json"]))
    parser.add_argument("--official-dry-run-md", default=str(OFFICIAL_DEFAULT_PATHS["dry_run_md"]))
    parser.add_argument("--official-contract-json", default=str(OFFICIAL_DEFAULT_PATHS["contract_json"]))
    parser.add_argument("--official-contract-md", default=str(OFFICIAL_DEFAULT_PATHS["contract_md"]))
    parser.add_argument("--official-preflight-json", default=str(OFFICIAL_DEFAULT_PATHS["preflight_json"]))
    parser.add_argument("--official-preflight-md", default=str(OFFICIAL_DEFAULT_PATHS["preflight_md"]))
    parser.add_argument("--condition-dry-run-json", default=str(CONDITION_DEFAULT_PATHS["dry_run_json"]))
    parser.add_argument("--condition-dry-run-md", default=str(CONDITION_DEFAULT_PATHS["dry_run_md"]))
    parser.add_argument("--condition-contract-json", default=str(CONDITION_DEFAULT_PATHS["contract_json"]))
    parser.add_argument("--condition-contract-md", default=str(CONDITION_DEFAULT_PATHS["contract_md"]))
    parser.add_argument("--condition-preflight-json", default=str(CONDITION_DEFAULT_PATHS["preflight_json"]))
    parser.add_argument("--condition-preflight-md", default=str(CONDITION_DEFAULT_PATHS["preflight_md"]))
    parser.add_argument("--execute-report-json", default=str(EXECUTE_REPORT_JSON_PATH))
    parser.add_argument("--execute-report-md", default=str(EXECUTE_REPORT_MD_PATH))
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--source-fetch-enabled", action="store_true")
    parser.add_argument("--postgres-commit-enabled", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, dependencies: dict | None = None) -> int:
    args = parse_args(argv)
    deps = default_dependencies()
    if dependencies:
        deps.update(dependencies)
    try:
        validate_trade_date(args.trade_date)
        if args.execute:
            validate_execute_request(
                execute_requested=args.execute,
                user_confirmed=args.user_confirmed,
                source_fetch_enabled=args.source_fetch_enabled,
                postgres_commit_enabled=args.postgres_commit_enabled,
            )

        implementation = build_implementation_report()
        handoff = build_handoff_report()
        if not args.no_write_report:
            write_json_report(implementation, args.implementation_json)
            write_text_report(render_implementation_markdown(implementation), args.implementation_md)
            write_json_report(handoff, args.handoff_json)
            write_text_report(render_handoff_markdown(handoff), args.handoff_md)

        if args.execute:
            validate_preflight_allows_execute(load_preflight())
            execute_report = run_execute_pipeline(args=args, dependencies=deps)
            print(json.dumps(execute_report, ensure_ascii=False, indent=2, default=str))
            return 0

    except SourceFacts20260608Blocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(implementation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
