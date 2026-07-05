#!/usr/bin/env python3
"""Refresh or execute the N4 20260528 v2 standard trigger runner gate."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.trigger.standard_trigger_execute import (
    DEFAULT_20260528_CONTRACT_JSON_PATH,
    DEFAULT_20260528_CONTRACT_MD_PATH,
    DEFAULT_20260528_DRY_RUN_JSON_PATH,
    DEFAULT_20260528_EXECUTE_RUN_ID,
    DEFAULT_20260528_PREFLIGHT_JSON_PATH,
    DEFAULT_20260528_PREFLIGHT_MD_PATH,
    DEFAULT_20260528_ROLLBACK_SQL_PATH,
    DEFAULT_20260528_SNAPSHOT_RUN_ID,
    DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID,
    StandardTriggerExecuteError,
    run_standard_trigger_execute_preflight,
    run_standard_trigger_once,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="N4 20260528 v2 standard trigger preflight/execute.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute-run-id", default=DEFAULT_20260528_EXECUTE_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_20260528_TRIGGER_CONTEXT_RUN_ID)
    parser.add_argument("--snapshot-run-id", default=DEFAULT_20260528_SNAPSHOT_RUN_ID)
    parser.add_argument("--market-subscription-run-id", default="")
    parser.add_argument("--for-trade-date", default="20260528")
    parser.add_argument("--contract-path", default=DEFAULT_20260528_CONTRACT_JSON_PATH)
    parser.add_argument("--readiness-path", default=DEFAULT_20260528_PREFLIGHT_JSON_PATH)
    parser.add_argument("--dry-run-json-path", default=DEFAULT_20260528_DRY_RUN_JSON_PATH)
    parser.add_argument("--contract-json-path", default=DEFAULT_20260528_CONTRACT_JSON_PATH)
    parser.add_argument("--contract-markdown-path", default=DEFAULT_20260528_CONTRACT_MD_PATH)
    parser.add_argument("--preflight-json-path", default=DEFAULT_20260528_PREFLIGHT_JSON_PATH)
    parser.add_argument("--preflight-markdown-path", default=DEFAULT_20260528_PREFLIGHT_MD_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_20260528_ROLLBACK_SQL_PATH)
    parser.add_argument("--preflight-only", action="store_true", help="Refresh read-only contract/preflight artifacts.")
    parser.add_argument("--execute", action="store_true", help="Write N4 trigger facts/outbox after final gate.")
    parser.add_argument("--user-confirmed", action="store_true", help="Second explicit confirmation required for execute.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    args = parser.parse_args()

    try:
        if args.execute:
            assert_final_gate_artifacts_ready(
                contract_path=args.contract_path,
                readiness_path=args.readiness_path,
                execute_run_id=args.execute_run_id,
                snapshot_run_id=args.snapshot_run_id,
                for_trade_date=args.for_trade_date,
            )
            report = run_standard_trigger_once(
                dsn=args.dsn,
                execute=args.execute,
                user_confirmed=args.user_confirmed,
                execute_run_id=args.execute_run_id,
                trigger_context_run_id=args.trigger_context_run_id,
                snapshot_run_id=args.snapshot_run_id,
                market_subscription_run_id=args.market_subscription_run_id or None,
                dry_run_json_path=args.dry_run_json_path,
                rollback_sql_path=args.rollback_sql_path,
            )
        else:
            report = run_standard_trigger_execute_preflight(
                dsn=args.dsn,
                execute_run_id=args.execute_run_id,
                trigger_context_run_id=args.trigger_context_run_id,
                snapshot_run_id=args.snapshot_run_id,
                market_subscription_run_id=args.market_subscription_run_id or None,
                dry_run_json_path=args.dry_run_json_path,
                contract_json_path=args.contract_json_path,
                contract_markdown_path=args.contract_markdown_path,
                preflight_json_path=args.preflight_json_path,
                preflight_markdown_path=args.preflight_markdown_path,
                rollback_sql_path=args.rollback_sql_path,
            )
    except StandardTriggerExecuteError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    if report.get("result") in {"PREFLIGHT_BLOCKED", "CONTRACT_BLOCKED", "BLOCKED"}:
        return 2
    quality = report.get("quality") or {}
    return 0 if int(quality.get("p0_count") or 0) == 0 else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report.get("quality") or {}
    expected = report.get("expected_future_writes") or report.get("write_counts") or {}
    trade_date = report.get("for_trade_date") or "unknown"
    return "\n".join(
        [
            f"N4 {trade_date} v2 standard trigger runner",
            f"  result={report.get('result')}",
            f"  execute_run_id={report.get('execute_run_id')}",
            f"  trigger_context_run_id={report.get('trigger_context_run_id')}",
            f"  snapshot_run_id={report.get('snapshot_run_id')}",
            f"  TriggerMatched={expected.get('TriggerMatched')}",
            f"  TriggerPendingMarketData={expected.get('TriggerPendingMarketData')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
        ]
    )


def assert_final_gate_artifacts_ready(
    *,
    contract_path: str,
    readiness_path: str,
    execute_run_id: str,
    snapshot_run_id: str,
    for_trade_date: str,
) -> None:
    contract = json.loads(open(contract_path, encoding="utf-8").read())
    readiness = json.loads(open(readiness_path, encoding="utf-8").read())
    blockers: list[str] = []
    if contract.get("result") != "CONTRACT_PASS":
        blockers.append(f"contract result={contract.get('result')}")
    if readiness.get("result") != "PREFLIGHT_PASS":
        blockers.append(f"readiness result={readiness.get('result')}")
    if contract.get("execute_run_id") != execute_run_id:
        blockers.append("contract execute_run_id mismatch")
    if readiness.get("execute_run_id") != execute_run_id:
        blockers.append("readiness execute_run_id mismatch")
    if contract.get("snapshot_run_id") != snapshot_run_id:
        blockers.append("contract snapshot_run_id mismatch")
    if readiness.get("snapshot_run_id") != snapshot_run_id:
        blockers.append("readiness snapshot_run_id mismatch")
    if str(contract.get("for_trade_date")) != str(for_trade_date):
        blockers.append("contract for_trade_date mismatch")
    if str(readiness.get("for_trade_date")) != str(for_trade_date):
        blockers.append("readiness for_trade_date mismatch")
    if int((readiness.get("quality") or {}).get("p0_count") or 0) != 0:
        blockers.append("readiness P0 is not zero")
    next_gate = readiness.get("next_gate") or {}
    if not next_gate.get("allow_enter_n4_v2_execute_final_gate"):
        blockers.append("readiness final gate not allowed")
    runner = contract.get("runner_readiness") or {}
    if not runner.get("ready") or not runner.get("execute_runner_guarded_by_double_confirmation"):
        blockers.append("runner readiness not ready")
    if blockers:
        raise StandardTriggerExecuteError("N4 v2 standard trigger execute blocked by final gate artifacts: " + "; ".join(blockers))


if __name__ == "__main__":
    raise SystemExit(main())
