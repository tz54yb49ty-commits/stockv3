#!/usr/bin/env python3
"""Run N2 scope-only policy repair once.

Default mode is read-only dry-run. Database writes require both --execute and
--user-confirmed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from ashare_v3.condition.scope_policy_repair import run_scope_policy_repair

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:
    from scripts.check_condition_source_ready import DEFAULT_DSN


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run N2 scope-only minute_target_scope policy repair.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--repair-run-id", required=True)
    parser.add_argument("--rollback-sql-path", default="")
    parser.add_argument("--json-report-path", default="")
    parser.add_argument("--report-path", default="", help="JSON report path alias.")
    parser.add_argument("--markdown-report-path", default="")
    parser.add_argument("--execute", action="store_true", help="Required to write repair rows.")
    parser.add_argument("--user-confirmed", action="store_true", help="Required with --execute before DB write.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args(argv)

    json_report_path = resolve_alias(
        primary_value=args.json_report_path,
        alias_value=args.report_path,
        primary_name="--json-report-path",
        alias_name="--report-path",
    )
    report = run_scope_policy_repair(
        dsn=args.dsn,
        source_run_id=args.source_run_id,
        repair_run_id=args.repair_run_id,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        rollback_sql_path=args.rollback_sql_path or None,
        json_report_path=json_report_path or None,
        markdown_report_path=args.markdown_report_path or None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_summary(report))
    return 0 if report.get("result") in {"PREFLIGHT_PASS", "EXECUTED"} else 2


def resolve_alias(*, primary_value: str, alias_value: str, primary_name: str, alias_name: str) -> str:
    primary = primary_value or ""
    alias = alias_value or ""
    if primary and alias and primary != alias:
        raise ValueError(f"{primary_name} and {alias_name} disagree")
    return alias or primary


def format_summary(report: dict[str, object]) -> str:
    return "\n".join(
        [
            "N2 scope-only policy repair",
            f"  result={report.get('result')}",
            f"  source_run_id={report.get('source_run_id')}",
            f"  repair_run_id={report.get('repair_run_id')}",
            f"  database_written={report.get('database_written')}",
            f"  write_tables={','.join(report.get('write_tables') or [])}",
            f"  blocked_reasons={','.join(report.get('blocked_reasons') or [])}",
            "  downstream_layers_touched=false worker_started=false",
        ]
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"N2 scope-only policy repair blocked before DB write: {exc}", file=sys.stderr)
        raise SystemExit(2)
