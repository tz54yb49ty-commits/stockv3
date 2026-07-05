#!/usr/bin/env python3
"""Plan V3-only 20260612 full-day N3/N4/N5 replay readiness.

This script is read-only against the V3 runtime DB.  It does not execute
backfill, N4, N5, rollback, scheduler, or any downstream path.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from ashare_v3.market import v3_full_day_replay_plan as plan


try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


DEFAULT_AUDIT_JSON = "docs/V3_20260612_N3_FULL_DAY_1M_COVERAGE_AUDIT.json"
DEFAULT_AUDIT_MD = "docs/V3_20260612_N3_FULL_DAY_1M_COVERAGE_AUDIT.md"
DEFAULT_BACKFILL_CONTRACT_JSON = "docs/V3_20260612_N3_FULL_DAY_1M_BACKFILL_CONTRACT.json"
DEFAULT_BACKFILL_CONTRACT_MD = "docs/V3_20260612_N3_FULL_DAY_1M_BACKFILL_CONTRACT.md"
DEFAULT_BACKFILL_PREFLIGHT_JSON = "docs/V3_20260612_N3_FULL_DAY_1M_BACKFILL_PREFLIGHT.json"
DEFAULT_BACKFILL_PREFLIGHT_MD = "docs/V3_20260612_N3_FULL_DAY_1M_BACKFILL_PREFLIGHT.md"
DEFAULT_BACKFILL_ROLLBACK_SQL = "sql/V3_20260612_n3_full_day_1m_backfill_rollback.sql"


def format_contract_markdown(contract: dict) -> str:
    source_scope = contract.get("source_scope") or {}
    lines = [
        "# V3 20260612 N3 Full-Day 1m Backfill Contract",
        "",
        f"- result: `{contract.get('result')}`",
        f"- backfill_run_id: `{contract.get('backfill_run_id')}`",
        f"- for_trade_date: `{contract.get('for_trade_date')}`",
        f"- source_condition_run_id: `{contract.get('source_condition_run_id')}`",
        f"- missing context objects: `{source_scope.get('missing_context_objects_total')}`",
        f"- missing by asset: `{source_scope.get('missing_context_objects_by_asset')}`",
        f"- missing sample: `{source_scope.get('missing_context_identity_sample')}`",
        "",
        "## Boundary",
        "",
        "- execute authorized: `false`",
        "- target machine reference: `forbidden`",
        "- N4/N5/N6 execute: `false`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def format_preflight_markdown(preflight: dict) -> str:
    lines = [
        "# V3 20260612 N3 Full-Day 1m Backfill Preflight",
        "",
        f"- result: `{preflight.get('result')}`",
        f"- P0/P1/P2: `{preflight.get('P0_P1_P2')}`",
        f"- execute_authorized: `{preflight.get('execute_authorized')}`",
        f"- next_gate: `{preflight.get('next_gate')}`",
        "",
        "## Forbidden Scope",
        "",
    ]
    for key, value in (preflight.get("forbidden_scope_proof") or {}).items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--for-trade-date", default=plan.FOR_TRADE_DATE)
    parser.add_argument("--source-condition-run-id", default=plan.SOURCE_CONDITION_RUN_ID)
    parser.add_argument("--trigger-context-run-id", default=plan.TRIGGER_CONTEXT_RUN_ID)
    parser.add_argument("--existing-metric-run-id", default=plan.LIMITED_METRIC_RUN_ID)
    parser.add_argument("--focus-identity-key", default="stock:SH:603259")
    parser.add_argument("--focus-minute-label", default="10:56")
    parser.add_argument("--audit-json-path", default=DEFAULT_AUDIT_JSON)
    parser.add_argument("--audit-md-path", default=DEFAULT_AUDIT_MD)
    parser.add_argument("--backfill-contract-json-path", default=DEFAULT_BACKFILL_CONTRACT_JSON)
    parser.add_argument("--backfill-contract-md-path", default=DEFAULT_BACKFILL_CONTRACT_MD)
    parser.add_argument("--backfill-preflight-json-path", default=DEFAULT_BACKFILL_PREFLIGHT_JSON)
    parser.add_argument("--backfill-preflight-md-path", default=DEFAULT_BACKFILL_PREFLIGHT_MD)
    parser.add_argument("--backfill-rollback-sql-path", default=DEFAULT_BACKFILL_ROLLBACK_SQL)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = plan.fetch_full_day_coverage_inputs(
        dsn=args.dsn,
        for_trade_date=args.for_trade_date,
        source_condition_run_id=args.source_condition_run_id,
        trigger_context_run_id=args.trigger_context_run_id,
        projection_run_id=args.existing_metric_run_id,
        focus_minute_label=args.focus_minute_label,
    )
    audit = plan.build_full_day_coverage_audit_report(
        for_trade_date=args.for_trade_date,
        source_condition_run_id=args.source_condition_run_id,
        trigger_context_run_id=args.trigger_context_run_id,
        existing_metric_run_id=args.existing_metric_run_id,
        scope_rows=inputs["scope_rows"],
        context_rows=inputs["context_rows"],
        minute_coverage_rows=inputs["minute_coverage_rows"],
        metric_coverage_rows=inputs["metric_coverage_rows"],
        focus_identity_key=args.focus_identity_key,
        focus_minute_label=args.focus_minute_label,
    )
    contract, preflight, rollback_sql = plan.build_n3_full_day_backfill_contract_preflight(audit)
    plan.write_json(args.audit_json_path, audit)
    plan.write_text(args.audit_md_path, plan.format_coverage_audit_markdown(audit))
    plan.write_json(args.backfill_contract_json_path, contract)
    plan.write_text(args.backfill_contract_md_path, format_contract_markdown(contract))
    plan.write_json(args.backfill_preflight_json_path, preflight)
    plan.write_text(args.backfill_preflight_md_path, format_preflight_markdown(preflight))
    Path(args.backfill_rollback_sql_path).parent.mkdir(parents=True, exist_ok=True)
    Path(args.backfill_rollback_sql_path).write_text(rollback_sql, encoding="utf-8")
    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "V3 20260612 full-day replay readiness "
            f"result={audit.get('result')} blockers={','.join(audit.get('blockers') or [])}"
        )
    return 0 if audit.get("result") in {"AUDIT_PASS", "BLOCKED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
