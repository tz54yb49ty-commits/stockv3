#!/usr/bin/env python3
"""Run or prepare N3 action-confirmation projection metric writer once.

Without ``--execute`` this runner only refreshes execute contract/preflight
artifacts from the reviewed dry-run report. With ``--execute`` it requires
``--user-confirmed`` and writes only the scoped N3 action-confirmation metric
facts plus common_market_data_run / quality rows.
"""

from __future__ import annotations

import argparse
import json
import os

from ashare_v3.market.action_confirmation_projection_execute import (
    DEFAULT_EXECUTE_CONTRACT_MARKDOWN_PATH,
    DEFAULT_EXECUTE_CONTRACT_PATH,
    DEFAULT_EXECUTE_PREFLIGHT_MARKDOWN_PATH,
    DEFAULT_EXECUTE_PREFLIGHT_PATH,
    DEFAULT_EXECUTE_REPORT_MARKDOWN_PATH,
    DEFAULT_EXECUTE_REPORT_PATH,
    ActionConfirmationProjectionExecuteError,
    build_action_confirmation_execute_contract,
    build_action_confirmation_execute_preflight,
    run_action_confirmation_projection_execute,
    write_action_confirmation_execute_contract_files,
)
from ashare_v3.market.action_confirmation_projection_plan import DEFAULT_DRY_RUN_JSON_PATH
from check_condition_source_ready import DEFAULT_DSN


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or execute N3 action-confirmation projection metric writer.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--dry-run-path", default=DEFAULT_DRY_RUN_JSON_PATH)
    parser.add_argument("--contract-path", default=DEFAULT_EXECUTE_CONTRACT_PATH)
    parser.add_argument("--contract-markdown-path", default=DEFAULT_EXECUTE_CONTRACT_MARKDOWN_PATH)
    parser.add_argument("--preflight-path", default=DEFAULT_EXECUTE_PREFLIGHT_PATH)
    parser.add_argument("--preflight-markdown-path", default=DEFAULT_EXECUTE_PREFLIGHT_MARKDOWN_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_EXECUTE_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_EXECUTE_REPORT_MARKDOWN_PATH)
    parser.add_argument("--execute", action="store_true", help="Execute the writer. Requires --user-confirmed.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required for --execute.")
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    args = parser.parse_args()

    if not args.execute:
        dry_run = json.loads(open(args.dry_run_path, encoding="utf-8").read())
        contract = build_action_confirmation_execute_contract(dry_run)
        preflight = build_action_confirmation_execute_preflight(contract, dry_run)
        write_action_confirmation_execute_contract_files(
            contract,
            preflight,
            contract_json_path=args.contract_path,
            contract_markdown_path=args.contract_markdown_path,
            preflight_json_path=args.preflight_path,
            preflight_markdown_path=args.preflight_markdown_path,
        )
        result = {
            "result": "READY",
            "stage": "N3 action-confirmation projection writer execute contract refresh",
            "contract_path": args.contract_path,
            "preflight_path": args.preflight_path,
            "projection_run_id": contract["projection_run_id"],
            "execute_authorized_now": False,
            "writes_database": False,
            "writes_outbox": False,
            "preflight_result": preflight["result"],
            "P0/P1/P2": [
                preflight["quality"]["p0_count"],
                preflight["quality"]["p1_count"],
                preflight["quality"]["p2_count"],
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else format_refresh_summary(result))
        return 0 if preflight["result"] == "PREFLIGHT_PASS" else 2

    try:
        report = run_action_confirmation_projection_execute(
            dsn=args.dsn,
            contract_path=args.contract_path,
            preflight_path=args.preflight_path,
            dry_run_path=args.dry_run_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
        )
    except ActionConfirmationProjectionExecuteError as exc:
        blocked = {
            "result": "BLOCKED",
            "stage": "N3 action-confirmation projection writer execute",
            "layer_role": "N3_market_data",
            "reason": str(exc),
            "writes_database": False,
            "writes_outbox": False,
            "consumes_outbox": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        }
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str) if args.json else format_execute_summary(report))
    return 0 if report.get("result") == "EXECUTED" else 1


def format_refresh_summary(result: dict) -> str:
    return "\n".join(
        [
            f"result={result['result']}",
            f"projection_run_id={result['projection_run_id']}",
            f"preflight={result['preflight_result']}",
            f"P0/P1/P2={result['P0/P1/P2'][0]}/{result['P0/P1/P2'][1]}/{result['P0/P1/P2'][2]}",
            f"contract_path={result['contract_path']}",
            f"preflight_path={result['preflight_path']}",
            "writes_database=false",
            "writes_outbox=false",
        ]
    )


def format_execute_summary(report: dict) -> str:
    rows = (report.get("write_result") or {}).get("rows_written") or {}
    quality = report.get("quality") or {}
    return "\n".join(
        [
            f"result={report.get('result')}",
            f"projection_run_id={report.get('projection_run_id')}",
            f"rows stock/index/board/total={rows.get('stock', 0)}/{rows.get('index', 0)}/{rows.get('board', 0)}/{rows.get('total', 0)}",
            f"P0/P1/P2={quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
            "writes_outbox=false",
            f"rollback_safe={(report.get('rollback') or {}).get('rollback_safe')}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
