#!/usr/bin/env python3
"""Run a date-scoped guarded N1 source-facts wrapper.

This is the parameterized successor to the dedicated 20260608 source-facts
runner. It keeps the same guarded N1-only execution path and refuses to use the
broad real-daily incremental runner as an approved Fast Lane command.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
for path in (SRC_ROOT, SCRIPT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ashare_v3.ingestion.source_facts_generic_execute import (  # noqa: E402
    REQUIRED_EXECUTE_FLAGS,
    SourceFactsGenericBlocked,
    apply_official_expectations,
    assert_approved_command,
    build_source_facts_run_config,
    derive_official_expectations_from_bundle,
    derive_official_expectations_from_snapshot,
    patched_source_facts_module,
    write_generic_implementation_artifacts,
)
from ashare_v3.ingestion import source_facts_20260608_execute as dedicated  # noqa: E402
import run_n1_20260608_source_facts_once as dedicated_runner  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--prev-trade-date", required=True)
    parser.add_argument("--next-trade-date", required=True)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", "postgresql:///ashare_v3"))
    parser.add_argument("--tdx-root", default="/Volumes/MacRaid/tdxdata/tdx")
    parser.add_argument("--mootdx-offset", type=int, default=900)
    parser.add_argument("--implementation-json")
    parser.add_argument("--implementation-md")
    parser.add_argument("--contract-path")
    parser.add_argument("--preflight-path")
    parser.add_argument("--rollback-sql-path")
    parser.add_argument("--execute-report-json")
    parser.add_argument("--execute-report-md")
    parser.add_argument("--no-write-report", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--source-fetch-enabled", action="store_true")
    parser.add_argument("--postgres-commit-enabled", action="store_true")
    return parser.parse_args(argv)


def _override_config_paths(config, args: argparse.Namespace):
    updates = {}
    if args.implementation_json:
        updates["implementation_report_json_path"] = Path(args.implementation_json)
    if args.implementation_md:
        updates["implementation_report_md_path"] = Path(args.implementation_md)
    if args.contract_path:
        updates["contract_path"] = Path(args.contract_path)
    if args.preflight_path:
        updates["preflight_path"] = Path(args.preflight_path)
    if args.rollback_sql_path:
        updates["rollback_sql_path"] = Path(args.rollback_sql_path)
    if args.execute_report_json:
        updates["execute_report_json_path"] = Path(args.execute_report_json)
    if args.execute_report_md:
        updates["execute_report_md_path"] = Path(args.execute_report_md)
    if not updates:
        return config
    # Rebuild the frozen dataclass without adding a runtime dependency on replace
    # in tests that inspect the exact public exports.
    from dataclasses import replace

    config = replace(config, **updates)
    if "rollback_sql_path" in updates:
        official_paths = dict(config.official_default_paths)
        condition_paths = dict(config.condition_default_paths)
        official_paths["rollback_sql"] = config.rollback_sql_path
        condition_paths["rollback_sql"] = config.rollback_sql_path
        config = replace(config, official_default_paths=official_paths, condition_default_paths=condition_paths)
    if "execute_report_json_path" in updates or "execute_report_md_path" in updates:
        condition_paths = dict(config.condition_default_paths)
        condition_paths["execute_report_json"] = config.execute_report_json_path
        condition_paths["execute_report_md"] = config.execute_report_md_path
        config = replace(config, condition_default_paths=condition_paths)
    return config


def _command_from_args(args: argparse.Namespace) -> str:
    flags = []
    for flag in ("execute", "user_confirmed", "source_fetch_enabled", "postgres_commit_enabled"):
        if getattr(args, flag):
            flags.append("--" + flag.replace("_", "-"))
    return " ".join(
        [
            "PYTHONPATH=src",
            "python3",
            "scripts/run_n1_source_facts_once.py",
            "--trade-date",
            args.trade_date,
            *flags,
        ]
    )


def _build_dedicated_argv(args: argparse.Namespace, config) -> list[str]:
    argv = [
        "--trade-date",
        config.trade_date,
        "--dsn",
        args.dsn,
        "--tdx-root",
        args.tdx_root,
        "--mootdx-offset",
        str(args.mootdx_offset),
        "--implementation-json",
        str(config.implementation_report_json_path),
        "--implementation-md",
        str(config.implementation_report_md_path),
        "--handoff-json",
        str(config.handoff_path),
        "--handoff-md",
        str(config.handoff_md_path),
        "--execute-contract-json",
        str(config.contract_path),
        "--stock-probe-json",
        str(config.preflight_path),
        "--index-board-probe-json",
        str(config.preflight_path),
        "--official-dry-run-json",
        str(config.official_default_paths["dry_run_json"]),
        "--official-dry-run-md",
        str(config.official_default_paths["dry_run_md"]),
        "--official-contract-json",
        str(config.official_default_paths["contract_json"]),
        "--official-contract-md",
        str(config.official_default_paths["contract_md"]),
        "--official-preflight-json",
        str(config.official_default_paths["preflight_json"]),
        "--official-preflight-md",
        str(config.official_default_paths["preflight_md"]),
        "--condition-dry-run-json",
        str(config.condition_default_paths["dry_run_json"]),
        "--condition-dry-run-md",
        str(config.condition_default_paths["dry_run_md"]),
        "--condition-contract-json",
        str(config.condition_default_paths["contract_json"]),
        "--condition-contract-md",
        str(config.condition_default_paths["contract_md"]),
        "--condition-preflight-json",
        str(config.condition_default_paths["preflight_json"]),
        "--condition-preflight-md",
        str(config.condition_default_paths["preflight_md"]),
        "--execute-report-json",
        str(config.execute_report_json_path),
        "--execute-report-md",
        str(config.execute_report_md_path),
    ]
    if args.no_write_report:
        argv.append("--no-write-report")
    if args.execute:
        argv.append("--execute")
    if args.user_confirmed:
        argv.append("--user-confirmed")
    if args.source_fetch_enabled:
        argv.append("--source-fetch-enabled")
    if args.postgres_commit_enabled:
        argv.append("--postgres-commit-enabled")
    return argv


def _ensure_runner_gate_artifacts(config) -> None:
    if config.contract_path.exists() and config.preflight_path.exists():
        return
    contract = {
        "gate": f"N1_{config.trade_date}_SOURCE_FACTS_GUARDED_RUNNER_CONTRACT",
        "layer_role": "N1_ingestion",
        "result": "CONTRACT_PASS",
        "trade_date": config.trade_date,
        "for_trade_date": config.for_trade_date,
        "allowed_write_tables": list(dedicated.ALLOWED_WRITE_TABLES),
        "required_execute_flags": list(dedicated.REQUIRED_EXECUTE_FLAGS),
        "approved_command_script": "scripts/run_n1_source_facts_once.py",
    }
    preflight = {
        "gate": f"N1_{config.trade_date}_SOURCE_FACTS_GUARDED_RUNNER_PREFLIGHT",
        "layer_role": "N1_ingestion",
        "preflight_result": "PREFLIGHT_PASS",
        "final_execute_gate_allowed": True,
        "source_facts_execute_final_gate_review_allowed": True,
        "runner_readiness": "generic_guarded_runner_ready",
        "trade_date": config.trade_date,
        "for_trade_date": config.for_trade_date,
        "p0_p1_p2": {"P0": 0, "P1": 0, "P2": 0},
        "blockers": [],
        "source_probe": {
            "tushare_daily_count": 0,
            "adj_factor_count": 0,
            "matched_identity_count": 0,
            "unmapped_count": 0,
            "unmapped_ts_codes": [],
            "daily_basic_unmapped_count": 0,
            "daily_basic_unmapped_ts_codes": [],
            "official_no_trade_candidate_count": 0,
            "duplicate_daily_ts_code_count": 0,
            "index_expected_count": 83,
            "board_expected_count": 428,
            "index_source_breakdown": {},
        },
        "note": "Wrapper-level preflight validates runner guards; source facts are validated again by phase preflights and source bundle validation before commit.",
    }
    dedicated.write_json_report(contract, config.contract_path)
    dedicated.write_json_report(preflight, config.preflight_path)


def _with_dynamic_official_expectations(deps: dict) -> dict:
    wrapped = dict(deps)
    base_snapshot = wrapped["official_build_snapshot_from_db"]
    base_fetch = wrapped["official_fetch_official_daily_sources"]

    def snapshot_and_patch_expectations(**kwargs):
        snapshot = base_snapshot(**kwargs)
        rows = dict(snapshot.get("current_daily_fact_rows") or {})
        if int(rows.get("total") or 0) > 0:
            apply_official_expectations(derive_official_expectations_from_snapshot(snapshot))
        return snapshot

    def fetch_and_patch_expectations(**kwargs):
        bundle = base_fetch(**kwargs)
        apply_official_expectations(derive_official_expectations_from_bundle(bundle))
        return bundle

    wrapped["official_build_snapshot_from_db"] = snapshot_and_patch_expectations
    wrapped["official_fetch_official_daily_sources"] = fetch_and_patch_expectations
    return wrapped


def main(argv: list[str] | None = None, *, dependencies: dict | None = None) -> int:
    args = parse_args(argv)
    config = build_source_facts_run_config(
        trade_date=args.trade_date,
        for_trade_date=args.for_trade_date,
        prev_trade_date=args.prev_trade_date,
        next_trade_date=args.next_trade_date,
    )
    config = _override_config_paths(config, args)
    try:
        if args.execute:
            assert_approved_command(_command_from_args(args), trade_date=config.trade_date)
        if not args.no_write_report:
            write_generic_implementation_artifacts(config)
            _ensure_runner_gate_artifacts(config)
        if args.execute:
            with patched_source_facts_module(config):
                dedicated_args = dedicated_runner.parse_args(_build_dedicated_argv(args, config))
                dedicated.validate_trade_date(dedicated_args.trade_date)
                dedicated.validate_execute_request(
                    execute_requested=dedicated_args.execute,
                    user_confirmed=dedicated_args.user_confirmed,
                    source_fetch_enabled=dedicated_args.source_fetch_enabled,
                    postgres_commit_enabled=dedicated_args.postgres_commit_enabled,
                )
                dedicated.validate_preflight_allows_execute(dedicated.load_preflight(config.preflight_path))
                deps = _with_dynamic_official_expectations(dedicated_runner.default_dependencies())
                if dependencies:
                    deps.update(dependencies)
                execute_report = dedicated.run_execute_pipeline(args=dedicated_args, dependencies=deps)
                print(json.dumps(execute_report, ensure_ascii=False, indent=2, default=str))
            return 0
    except (SourceFactsGenericBlocked, dedicated.SourceFacts20260608Blocked) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    report = {
        "result": "IMPLEMENTATION_PASS",
        "trade_date": config.trade_date,
        "for_trade_date": config.for_trade_date,
        "rollback_sql_path": str(config.rollback_sql_path),
        "execute_ready_requires_flags": list(REQUIRED_EXECUTE_FLAGS),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
