#!/usr/bin/env python3
"""Run N5 full metric-union historical metadata repair once.

The command is double-confirmed. Without both ``--execute`` and
``--user-confirmed`` it writes only a blocked report artifact and performs no
database updates.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from ashare_v3.action.metadata_repair import (
    DEFAULT_FULL_METRIC_UNION_REPAIR_CONTRACT_PATH,
    DEFAULT_FULL_METRIC_UNION_REPAIR_DRY_RUN_PATH,
    DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_JSON_PATH,
    DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_MD_PATH,
    DEFAULT_FULL_METRIC_UNION_REPAIR_PAYLOAD_PATH,
    DEFAULT_FULL_METRIC_UNION_REPAIR_PREFLIGHT_PATH,
    DEFAULT_FULL_METRIC_UNION_REPAIR_ROLLBACK_SQL_PATH,
    run_full_metric_union_metadata_repair_from_paths,
)
from check_condition_source_ready import DEFAULT_DSN


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run N5 full metric-union metadata repair once.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--contract-path", default=DEFAULT_FULL_METRIC_UNION_REPAIR_CONTRACT_PATH)
    parser.add_argument("--preflight-path", default=DEFAULT_FULL_METRIC_UNION_REPAIR_PREFLIGHT_PATH)
    parser.add_argument("--dry-run-path", default=DEFAULT_FULL_METRIC_UNION_REPAIR_DRY_RUN_PATH)
    parser.add_argument("--payload-path", default=DEFAULT_FULL_METRIC_UNION_REPAIR_PAYLOAD_PATH)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_FULL_METRIC_UNION_REPAIR_ROLLBACK_SQL_PATH)
    parser.add_argument("--json-report-path", default=DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_JSON_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_FULL_METRIC_UNION_REPAIR_EXECUTE_REPORT_MD_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = run_full_metric_union_metadata_repair_from_paths(
        dsn=args.dsn,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        contract_path=args.contract_path,
        preflight_path=args.preflight_path,
        dry_run_path=args.dry_run_path,
        payload_path=args.payload_path,
        rollback_sql_path=args.rollback_sql_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("result") == "EXECUTED" else 2


def format_summary(report: dict[str, Any]) -> str:
    quality = report.get("quality") or {}
    side_effects = report.get("side_effects") or {}
    return "\n".join(
        [
            "n5 full metric-union metadata repair",
            f"  result={report.get('result')}",
            f"  action_run_id={report.get('action_run_id')}",
            f"  execute={report.get('execute')} user_confirmed={report.get('user_confirmed')}",
            f"  allow_execute={report.get('allow_execute')}",
            f"  blockers={report.get('blockers')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
            f"  updated_rows={report.get('updated_rows')}",
            "  "
            f"writes_performed={side_effects.get('writes_performed')} "
            f"n4_facts_modified={side_effects.get('n4_facts_modified')} "
            f"n6_projection_card_modified={side_effects.get('n6_projection_card_modified')} "
            f"worker_started={side_effects.get('worker_started')}",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
