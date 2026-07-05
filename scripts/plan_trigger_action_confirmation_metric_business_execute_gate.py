#!/usr/bin/env python3
"""Build N4 action-confirmation metric business execute contract/final preflight.

This gate is read-only with respect to runtime business state. It writes only
contract/report artifacts and rollback SQL text. It rejects execute flags
because the dedicated business execute runner is intentionally not implemented
in this gate.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ashare_v3.trigger.action_confirmation_metric_matcher import (
    DEFAULT_EXECUTE_CONTRACT_JSON_PATH,
    DEFAULT_EXECUTE_CONTRACT_MARKDOWN_PATH,
    DEFAULT_EXECUTE_FINAL_PREFLIGHT_JSON_PATH,
    DEFAULT_EXECUTE_FINAL_PREFLIGHT_MARKDOWN_PATH,
    DEFAULT_EXECUTE_ROLLBACK_SQL_PATH,
    DEFAULT_EXECUTE_RUN_ID,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_PREFLIGHT_JSON_PATH,
    build_action_confirmation_metric_business_execute_contract,
    build_action_confirmation_metric_execute_final_preflight,
    build_action_confirmation_metric_execute_rollback_sql,
    capture_action_confirmation_metric_execute_baseline,
    format_action_confirmation_metric_business_execute_contract,
    format_action_confirmation_metric_execute_final_preflight,
    write_json,
    write_text,
)
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build N4 action-confirmation metric business execute contract/final preflight artifacts."
    )
    parser.add_argument("--execute", action="store_true", help="Rejected. This gate does not execute business writes.")
    parser.add_argument("--user-confirmed", action="store_true", help="Rejected here; business runner is not implemented.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute-run-id", default=DEFAULT_EXECUTE_RUN_ID)
    parser.add_argument("--dry-run-json-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--dry-run-preflight-json-path", default=DEFAULT_PREFLIGHT_JSON_PATH)
    parser.add_argument("--contract-json-path", default=DEFAULT_EXECUTE_CONTRACT_JSON_PATH)
    parser.add_argument("--contract-markdown-path", default=DEFAULT_EXECUTE_CONTRACT_MARKDOWN_PATH)
    parser.add_argument("--final-preflight-json-path", default=DEFAULT_EXECUTE_FINAL_PREFLIGHT_JSON_PATH)
    parser.add_argument("--final-preflight-markdown-path", default=DEFAULT_EXECUTE_FINAL_PREFLIGHT_MARKDOWN_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_EXECUTE_ROLLBACK_SQL_PATH)
    parser.add_argument("--json", action="store_true", help="Print full contract/final preflight JSON.")
    args = parser.parse_args()

    if args.execute or args.user_confirmed:
        blocked = {
            "result": "BLOCKED",
            "stage": "N4 action-confirmation metric business execute gate",
            "layer_role": "N4_trigger",
            "reason": "This gate only builds contract/final-preflight artifacts; dedicated business execute runner is not implemented.",
            "writes_database": False,
            "writes_outbox": False,
            "consumes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "worker_started": False,
        }
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return 2

    dry_run_report = load_json(args.dry_run_json_path)
    dry_run_preflight = load_json(args.dry_run_preflight_json_path)
    rollback_sql = build_action_confirmation_metric_execute_rollback_sql(args.execute_run_id)
    write_text(args.rollback_sql_path, rollback_sql)
    contract = build_action_confirmation_metric_business_execute_contract(
        dry_run_report,
        dry_run_preflight,
        execute_run_id=args.execute_run_id,
        rollback_sql_path=args.rollback_sql_path,
        business_execute_runner_ready=True,
        business_execute_runner="scripts/run_trigger_action_confirmation_metric_once.py",
    )
    baseline = capture_action_confirmation_metric_execute_baseline(args.dsn, args.execute_run_id)
    final_preflight = build_action_confirmation_metric_execute_final_preflight(
        dry_run_report,
        dry_run_preflight,
        contract,
        baseline_summary=baseline,
        rollback_sql_exists=Path(args.rollback_sql_path).exists(),
    )
    write_json(args.contract_json_path, contract)
    write_text(args.contract_markdown_path, format_action_confirmation_metric_business_execute_contract(contract))
    write_json(args.final_preflight_json_path, final_preflight)
    write_text(args.final_preflight_markdown_path, format_action_confirmation_metric_execute_final_preflight(final_preflight))

    if args.json:
        print(json.dumps({"contract": contract, "final_preflight": final_preflight}, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(contract, final_preflight))
    return 0 if contract.get("result") == "CONTRACT_PASS" else 2


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def format_summary(contract: dict, preflight: dict) -> str:
    expected = contract.get("expected_writes") or {}
    quality = preflight.get("quality") or {}
    return "\n".join(
        [
            f"contract={contract.get('result')}",
            f"final_preflight={preflight.get('result')}",
            f"execute_run_id={contract.get('execute_run_id')}",
            f"TriggerMatched={expected.get('TriggerMatched', 0)}",
            f"TriggerPendingMarketData={expected.get('TriggerPendingMarketData', 0)}",
            f"P0/P1/P2={quality.get('p0_count', 0)}/{quality.get('p1_count', 0)}/{quality.get('p2_count', 0)}",
            f"allow_business_execute_user_confirmation={(preflight.get('next_gate') or {}).get('allow_business_execute_user_confirmation')}",
            "writes_database=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
