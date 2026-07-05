#!/usr/bin/env python3
"""Generate per-minute N3 intraday B1/C1/B2 child artifacts once."""

from __future__ import annotations

import argparse
import json
from typing import Any

from ashare_v3.market.intraday_child_artifacts import (
    IntradayChildArtifactConflictError,
    IntradayChildArtifactRequest,
    build_intraday_child_artifact_plan,
    write_intraday_child_artifact_report,
    write_intraday_child_artifacts,
)


DEFAULT_JSON_REPORT_PATH = "docs/N3_INTRADAY_B1_C1_B2_DYNAMIC_CHILD_ARTIFACT_GENERATION_REPORT.json"
DEFAULT_MD_REPORT_PATH = "docs/N3_INTRADAY_B1_C1_B2_DYNAMIC_CHILD_ARTIFACT_GENERATION_REPORT.md"


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    request = IntradayChildArtifactRequest(
        for_trade_date=args.for_trade_date,
        latest_closed_minute=args.latest_closed_minute or None,
        latest_closed_minute_hhmm=args.latest_closed_minute_hhmm,
        subscription_run_id=args.subscription_run_id,
        preload_run_id=args.preload_run_id,
        source_condition_run_id=args.source_condition_run_id,
        docs_root=args.docs_root,
        sql_root=args.sql_root,
    )
    plan = build_intraday_child_artifact_plan(request)
    report: dict[str, Any] = dict(plan)
    if args.write_artifacts:
        try:
            write_result = write_intraday_child_artifacts(plan, allow_overwrite=args.allow_overwrite)
            report["result"] = "ARTIFACT_WRITE_PASS"
            report["write_result"] = write_result
        except IntradayChildArtifactConflictError as exc:
            report["result"] = "BLOCKED"
            report["blocked_reason"] = str(exc)
    else:
        report["result"] = "PLAN_ONLY"
        report["write_result"] = {
            "status": "not_written",
            "reason": "missing_explicit_write_artifacts_flag",
        }

    report.pop("artifact_payloads", None)
    write_intraday_child_artifact_report(
        report,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report["result"] in {"PLAN_ONLY", "ARTIFACT_WRITE_PASS"} else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate one N3 intraday B1/C1/B2 child artifact bundle.")
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--latest-closed-minute", default="")
    parser.add_argument("--latest-closed-minute-hhmm", required=True)
    parser.add_argument("--subscription-run-id", required=True)
    parser.add_argument("--preload-run-id", required=True)
    parser.add_argument("--source-condition-run-id", required=True)
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MD_REPORT_PATH)
    parser.add_argument("--write-artifacts", action="store_true", help="Write generated child artifacts.")
    parser.add_argument("--allow-overwrite", action="store_true", help="Allow replacing conflicting artifacts.")
    parser.add_argument("--json", action="store_true")
    return parser


def format_summary(report: dict[str, Any]) -> str:
    write = report.get("write_result") or {}
    return "\n".join(
        [
            "n3 intraday child artifact generation",
            f"  result={report.get('result')}",
            f"  for_trade_date={report.get('for_trade_date')}",
            f"  latest_closed_minute_hhmm={report.get('latest_closed_minute_hhmm')}",
            f"  subscription_run_id={report.get('subscription_run_id')}",
            f"  artifact_write_status={write.get('status')}",
            "  database_connected=false subprocess_executed=false b1_c1_b2_executed=false",
            "  outbox_consumed_or_updated=false n4_n5_n6_entered=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
