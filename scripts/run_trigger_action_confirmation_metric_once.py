#!/usr/bin/env python3
"""Run-once N4 action-confirmation metric business execute runner.

Default mode refreshes the business execute contract/final preflight only. The
business write path requires both --execute and --user-confirmed.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.trigger.action_confirmation_metric_execute import (
    DEFAULT_EXECUTE_REPORT_JSON_PATH,
    DEFAULT_EXECUTE_REPORT_MARKDOWN_PATH,
    ActionConfirmationMetricExecuteError,
    run_action_confirmation_metric_once,
)
from ashare_v3.trigger.action_confirmation_metric_matcher import (
    DEFAULT_EXECUTE_CONTRACT_JSON_PATH,
    DEFAULT_EXECUTE_CONTRACT_MARKDOWN_PATH,
    DEFAULT_EXECUTE_FINAL_PREFLIGHT_JSON_PATH,
    DEFAULT_EXECUTE_FINAL_PREFLIGHT_MARKDOWN_PATH,
    DEFAULT_EXECUTE_ROLLBACK_SQL_PATH,
    DEFAULT_EXECUTE_RUN_ID,
    DEFAULT_FOR_TRADE_DATE,
    DEFAULT_JSON_REPORT_PATH,
    DEFAULT_PREFLIGHT_JSON_PATH,
    DEFAULT_PROJECTION_RUN_ID,
    DEFAULT_SOURCE_CONDITION_RUN_ID,
    DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
    DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
    DEFAULT_TRIGGER_CONTEXT_RUN_ID,
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
    parser = argparse.ArgumentParser(description="N4 action-confirmation metric run-once preflight/execute.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--execute-run-id", default=DEFAULT_EXECUTE_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_TRIGGER_CONTEXT_RUN_ID)
    parser.add_argument("--projection-run-id", default=DEFAULT_PROJECTION_RUN_ID)
    parser.add_argument("--source-condition-run-id", default=DEFAULT_SOURCE_CONDITION_RUN_ID)
    parser.add_argument("--source-subscription-run-id", default=DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID)
    parser.add_argument("--source-snapshot-run-id", default=DEFAULT_SOURCE_SNAPSHOT_RUN_ID)
    parser.add_argument("--for-trade-date", default=DEFAULT_FOR_TRADE_DATE)
    parser.add_argument("--dry-run-json-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--dry-run-preflight-json-path", default=DEFAULT_PREFLIGHT_JSON_PATH)
    parser.add_argument("--contract-json-path", default=DEFAULT_EXECUTE_CONTRACT_JSON_PATH)
    parser.add_argument("--contract-markdown-path", default=DEFAULT_EXECUTE_CONTRACT_MARKDOWN_PATH)
    parser.add_argument("--final-preflight-json-path", default=DEFAULT_EXECUTE_FINAL_PREFLIGHT_JSON_PATH)
    parser.add_argument("--final-preflight-markdown-path", default=DEFAULT_EXECUTE_FINAL_PREFLIGHT_MARKDOWN_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_EXECUTE_ROLLBACK_SQL_PATH)
    parser.add_argument("--execute-report-json-path", default=DEFAULT_EXECUTE_REPORT_JSON_PATH)
    parser.add_argument("--execute-report-markdown-path", default=DEFAULT_EXECUTE_REPORT_MARKDOWN_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        if args.execute:
            report = run_action_confirmation_metric_once(
                dsn=args.dsn,
                execute=args.execute,
                user_confirmed=args.user_confirmed,
                execute_run_id=args.execute_run_id,
                trigger_context_run_id=args.trigger_context_run_id,
                projection_run_id=args.projection_run_id,
                source_condition_run_id=args.source_condition_run_id,
                source_subscription_run_id=args.source_subscription_run_id,
                source_snapshot_run_id=args.source_snapshot_run_id,
                for_trade_date=args.for_trade_date,
                dry_run_json_path=args.dry_run_json_path,
                dry_run_preflight_json_path=args.dry_run_preflight_json_path,
                contract_json_path=args.contract_json_path,
                final_preflight_json_path=args.final_preflight_json_path,
                rollback_sql_path=args.rollback_sql_path,
                execute_report_json_path=args.execute_report_json_path,
                execute_report_markdown_path=args.execute_report_markdown_path,
            )
        else:
            report = refresh_preflight(args)
    except ActionConfirmationMetricExecuteError as exc:
        print(f"BLOCKED: {exc}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    result = str(report.get("result") or "")
    return 0 if result in {"PREFLIGHT_PASS", "EXECUTED"} else 2


def refresh_preflight(args: argparse.Namespace) -> dict:
    dry_run_report = read_json(args.dry_run_json_path)
    dry_run_preflight = read_json(args.dry_run_preflight_json_path)
    write_text(args.rollback_sql_path, build_action_confirmation_metric_execute_rollback_sql(args.execute_run_id))
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
        rollback_sql_exists=True,
    )
    write_json(args.contract_json_path, contract)
    write_text(args.contract_markdown_path, format_action_confirmation_metric_business_execute_contract(contract))
    write_json(args.final_preflight_json_path, final_preflight)
    write_text(args.final_preflight_markdown_path, format_action_confirmation_metric_execute_final_preflight(final_preflight))
    return final_preflight


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def format_summary(report: dict) -> str:
    planned = report.get("planned_writes") or report.get("write_counts") or {}
    quality = report.get("quality") or {}
    return "\n".join(
        [
            "N4 action-confirmation metric runner",
            f"  result={report.get('result')}",
            f"  execute_run_id={report.get('execute_run_id')}",
            f"  TriggerMatched={planned.get('TriggerMatched')}",
            f"  TriggerPendingMarketData={planned.get('TriggerPendingMarketData')}",
            f"  common_trigger_state={planned.get('common_trigger_state')}",
            f"  common_trigger_match={planned.get('common_trigger_match')}",
            f"  common_event_outbox={planned.get('common_event_outbox')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
