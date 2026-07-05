#!/usr/bin/env python3
"""Run-once N4 20260605 matched-only combined execute runner."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ashare_v3.trigger.local_trigger_dry_run import (
    build_local_trigger_plans,
    fetch_context_rows,
    fetch_snapshot_rows,
)
from ashare_v3.trigger.matched_only_combined_execute import (
    CombinedExecuteBlocked,
    assert_combined_execute_confirmed,
    build_combined_matched_only_write_plan,
    build_combined_quality_items,
)
from ashare_v3.trigger.projection_matcher import (
    build_projection_matcher_plans,
    fetch_projection_rows,
)
from ashare_v3.trigger.rule_v4_execute import execute_v4_matched_only_transaction
from ashare_v3.trigger.synthetic_dry_run import write_json
from ashare_v3.trigger.v4_enforcement import V4EnforcementBlocked, assert_v4_write_plan_enforceable
from check_condition_source_ready import DEFAULT_DSN


DEFAULT_EXECUTE_RUN_ID = "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
DEFAULT_CONTEXT_RUN_ID = "trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1"
DEFAULT_SNAPSHOT_RUN_ID = (
    "realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1"
)
DEFAULT_PROJECTION_RUN_ID = (
    "realtime_projection_metric_20260605_live2_compat__"
    "realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1"
)
DEFAULT_CONTRACT_PATH = "docs/N4_20260605_execute_contract.json"
DEFAULT_PREFLIGHT_PATH = "docs/N4_20260605_execute_preflight.json"
DEFAULT_LOCAL_DRY_RUN_PATH = "docs/N4_20260605_local_trigger_dry_run_report.json"
DEFAULT_PROJECTION_DRY_RUN_PATH = "docs/N4_20260605_projection_matcher_dry_run_report.json"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N4_20260605_execute_rollback.sql"
DEFAULT_REPORT_PATH = "docs/N4_20260605_execute_report.json"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="N4 20260605 matched-only combined execute runner.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute-run-id", default=DEFAULT_EXECUTE_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_CONTEXT_RUN_ID)
    parser.add_argument("--snapshot-run-id", default=DEFAULT_SNAPSHOT_RUN_ID)
    parser.add_argument("--projection-run-id", default=DEFAULT_PROJECTION_RUN_ID)
    parser.add_argument("--contract-path", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--readiness-path", "--preflight-path", dest="readiness_path", default=DEFAULT_PREFLIGHT_PATH)
    parser.add_argument("--local-dry-run-json-path", default=DEFAULT_LOCAL_DRY_RUN_PATH)
    parser.add_argument("--projection-dry-run-json-path", default=DEFAULT_PROJECTION_DRY_RUN_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL_PATH)
    parser.add_argument("--report-json-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        assert_combined_execute_confirmed(execute=args.execute, user_confirmed=args.user_confirmed)
        report = run_execute(args)
    except CombinedExecuteBlocked as exc:
        report = {
            "result": "BLOCKED",
            "layer_role": "N4_trigger",
            "execute_run_id": args.execute_run_id,
            "writes_performed": False,
            "blocked_reason": str(exc),
            "boundary_proof": {
                "db_write": False,
                "n3_outbox_consumed": False,
                "inbox_checkpoint_written": False,
                "n5_n6_entered": False,
                "worker_started": False,
                "real_trade_touched": False,
            },
        }
        if args.report_json_path:
            write_json(Path(args.report_json_path), report)
        print_report(report, as_json=args.json)
        return 2
    if args.report_json_path:
        write_json(Path(args.report_json_path), report)
    print_report(report, as_json=args.json)
    return 0 if report.get("result") == "EXECUTE_PASS" else 2


def run_execute(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_json(args.contract_path)
    preflight = load_json(args.readiness_path)
    assert_artifacts_ready(contract=contract, preflight=preflight, args=args)
    trigger_run, context_rows = fetch_context_rows(args.dsn, args.trigger_context_run_id)
    snapshot_run, snapshot_rows = fetch_snapshot_rows(args.dsn, args.snapshot_run_id)
    local_plans = build_local_trigger_plans(
        trigger_context_run_id=args.trigger_context_run_id,
        snapshot_run_id=args.snapshot_run_id,
        context_rows=context_rows,
        snapshot_rows=snapshot_rows,
    )
    projection_rows = fetch_projection_rows(args.dsn, args.projection_run_id)
    projection_plans = build_projection_matcher_plans(
        trigger_context_run_id=args.trigger_context_run_id,
        projection_run_id=args.projection_run_id,
        context_rows=context_rows,
        projection_rows=projection_rows,
    )
    write_plan = build_combined_matched_only_write_plan(
        local_plans=local_plans,
        projection_plans=projection_plans,
        execute_run_id=args.execute_run_id,
        trigger_context_run_id=args.trigger_context_run_id,
        snapshot_run_id=args.snapshot_run_id,
        projection_run_id=args.projection_run_id,
    )
    assert_write_plan_matches_artifacts(write_plan=write_plan, contract=contract, preflight=preflight)
    try:
        assert_v4_write_plan_enforceable(write_plan, created_at=datetime.now(timezone.utc))
    except V4EnforcementBlocked as exc:
        raise CombinedExecuteBlocked(str(exc)) from exc
    quality_items = build_combined_quality_items(write_plan)
    if any(item.get("severity") == "P0" and item.get("status") == "failed" for item in quality_items):
        raise CombinedExecuteBlocked("N4 20260605 execute blocked by combined quality items before writes")
    write_counts = execute_v4_matched_only_transaction(
        dsn=args.dsn,
        execute_run_id=args.execute_run_id,
        trigger_context_run=trigger_run,
        snapshot_run=snapshot_run,
        write_plan=write_plan,
        quality_items=quality_items,
    )
    return {
        "result": "EXECUTE_PASS",
        "layer_role": "N4_trigger",
        "execute_run_id": args.execute_run_id,
        "trigger_context_run_id": args.trigger_context_run_id,
        "snapshot_run_id": args.snapshot_run_id,
        "projection_run_id": args.projection_run_id,
        "write_counts": write_counts,
        "invalid_n5_entry_count": write_plan["invalid_n5_entry_count"],
        "matched_by_basis": write_plan["matched_by_basis"],
        "rollback_sql_path": args.rollback_sql_path,
        "boundary_proof": {
            "n3_outbox_consumed": False,
            "inbox_checkpoint_written": False,
            "n5_n6_entered": False,
            "worker_started": False,
            "market_data_pulled": False,
            "real_trade_touched": False,
            "old_outbox_consuming_projection_execute_route_used": False,
        },
    }


def assert_artifacts_ready(*, contract: Mapping[str, Any], preflight: Mapping[str, Any], args: argparse.Namespace) -> None:
    blockers: list[str] = []
    if contract.get("result") != "CONTRACT_PASS":
        blockers.append(f"contract result={contract.get('result')}")
    if preflight.get("result") != "PREFLIGHT_PASS":
        blockers.append(f"preflight result={preflight.get('result')}")
    if contract.get("execute_run_id") != args.execute_run_id:
        blockers.append("contract execute_run_id mismatch")
    if preflight.get("execute_run_id") != args.execute_run_id:
        blockers.append("preflight execute_run_id mismatch")
    if contract.get("trigger_context_run_id") != args.trigger_context_run_id:
        blockers.append("contract trigger_context_run_id mismatch")
    if contract.get("snapshot_run_id") != args.snapshot_run_id:
        blockers.append("contract snapshot_run_id mismatch")
    if contract.get("projection_run_id") != args.projection_run_id:
        blockers.append("contract projection_run_id mismatch")
    if int((preflight.get("quality") or {}).get("p0_count") or 0) != 0:
        blockers.append("preflight P0 is not zero")
    if not (preflight.get("runner_readiness") or {}).get("ready"):
        blockers.append("runner_readiness.ready is not true")
    if blockers:
        raise CombinedExecuteBlocked("N4 20260605 matched-only execute blocked by artifacts: " + "; ".join(blockers))


def assert_write_plan_matches_artifacts(
    *,
    write_plan: Mapping[str, Any],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> None:
    expected = (
        contract.get("expected_writes_after_final_confirmation")
        or contract.get("expected_writes")
        or preflight.get("expected_future_writes")
        or {}
    )
    actual = write_plan.get("write_counts") or {}
    blockers: list[str] = []
    for key in ("TriggerMatched", "TriggerPendingMarketData", "TriggerStateChanged"):
        if int(actual.get(key) or 0) != int(expected.get(key) or 0):
            blockers.append(f"{key} expected write count mismatch")
    if int(write_plan.get("invalid_n5_entry_count") or 0) != 0:
        blockers.append("invalid N5 entry count is not zero")
    if blockers:
        raise CombinedExecuteBlocked("N4 20260605 matched-only execute blocked by write-plan mismatch: " + "; ".join(blockers))


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def print_report(report: Mapping[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return
    print(
        "\n".join(
            [
                "N4 20260605 matched-only combined execute runner",
                f"  result={report.get('result')}",
                f"  execute_run_id={report.get('execute_run_id')}",
                f"  write_counts={report.get('write_counts')}",
                f"  blocked_reason={report.get('blocked_reason')}",
            ]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
