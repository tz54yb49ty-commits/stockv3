#!/usr/bin/env python3
"""Run N3-C2 closed minute / closed 30m replay once.

This runner is intentionally run-once only. It rejects execution unless both
``--execute`` and ``--user-confirmed`` are present. C2 writes no event outbox
and does not start workers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from ashare_v3.market.closed_30m_replay_execute import (
    DEFAULT_C2_DRY_RUN_PLAN_PATH,
    DEFAULT_C2_DRY_RUN_REPORT_PATH,
    DEFAULT_C2_EXECUTE_CONTRACT_PATH,
    DEFAULT_C2_JSON_REPORT_PATH,
    DEFAULT_C2_MD_REPORT_PATH,
    DEFAULT_C2_ROLLBACK_SQL_PATH,
    Closed30mReplayExecuteError,
    run_closed_30m_replay_execute,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run N3-C2 closed 30m replay once.")
    parser.add_argument("--dry-run-plan-path", default=DEFAULT_C2_DRY_RUN_PLAN_PATH)
    parser.add_argument("--execute-contract-path", default=DEFAULT_C2_EXECUTE_CONTRACT_PATH)
    parser.add_argument("--dry-run-report-path", default=DEFAULT_C2_DRY_RUN_REPORT_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_C2_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_C2_MD_REPORT_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_C2_ROLLBACK_SQL_PATH)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--c2-run-id", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN"))
    parser.add_argument("--progress-every", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.dsn:
        parser.error("ASHARE_V3_POSTGRES_DSN or --dsn is required")
    try:
        report = run_closed_30m_replay_execute(
            dsn=args.dsn,
            dry_run_plan_path=args.dry_run_plan_path,
            execute_contract_path=args.execute_contract_path,
            dry_run_report_path=args.dry_run_report_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            rollback_sql_path=args.rollback_sql_path,
            c2_run_id=args.c2_run_id,
            for_trade_date=args.for_trade_date,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
            progress_callback=lambda message: print(message, flush=True),
            progress_every=args.progress_every,
        )
    except Closed30mReplayExecuteError as exc:
        blocked = {
            "result": "BLOCKED",
            "stage": "N3-C2",
            "layer_role": "N3_market_data",
            "reason": str(exc),
            "writes_performed": False,
            "writes_outbox": False,
            "starts_worker": False,
        }
        print(json.dumps(blocked, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(compact_output(report), ensure_ascii=False, indent=2))
    return 0 if report.get("result") == "EXECUTED" else 1


def compact_output(report: dict[str, Any]) -> dict[str, Any]:
    write = report.get("write_result") or {}
    quality = report.get("quality") or {}
    return {
        "result": report.get("result"),
        "c2_run_id": report.get("c2_run_id"),
        "common_market_data_run_status": "passed" if report.get("result") == "EXECUTED" else "failed",
        "minute_delta_rows": write.get("minute_delta_rows"),
        "closed_30m_summary_rows": write.get("summary_rows"),
        "summary_status": write.get("summary_status"),
        "quality_rows": write.get("quality_rows"),
        "P0/P1/P2": f"{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}",
        "outbox_rows_for_c2_run": write.get("outbox_rows_for_c2_run"),
        "writes_outbox": (write.get("side_effects") or {}).get("writes_outbox"),
        "rollback_safe": (report.get("rollback") or {}).get("preserves_c1_b1_b2_n4_n5"),
        "rollback_sql_path": (report.get("paths") or {}).get("rollback_sql_path"),
        "report_path": str(Path(DEFAULT_C2_JSON_REPORT_PATH)),
        "next_allowed_step": report.get("next_allowed_step"),
    }


if __name__ == "__main__":
    sys.exit(main())
