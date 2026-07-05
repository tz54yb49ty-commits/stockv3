#!/usr/bin/env python3
"""Persist reviewed N3 market-data subscription control rows from a dry-run.

This runner writes only N3 control rows:
common_market_data_run, common_market_data_quality_item,
common_market_data_subscription_candidate, common_market_data_subscription,
and common_market_data_pull_plan.

It does not pull market data, write market facts, emit outbox events, start a
worker, or enter downstream layers.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping

from ashare_v3.condition.basis import count_quality_severities
from ashare_v3.market.subscription_execute import (
    build_post_quality_items,
    build_post_subscription_execute_checks,
    capture_subscription_execution_backup,
    persist_subscription_plan,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover
    from scripts.check_condition_source_ready import DEFAULT_DSN


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def validate_dry_run(report: Mapping[str, Any]) -> None:
    if report.get("mode") != "dry_run":
        raise RuntimeError("subscription control execute blocked: input mode is not dry_run")
    if report.get("layer_role") != "N3_market_data":
        raise RuntimeError("subscription control execute blocked: layer_role is not N3_market_data")
    if bool(report.get("blocked")) or not bool(report.get("passed")):
        raise RuntimeError("subscription control execute blocked: dry-run did not pass")
    if int(((report.get("quality") or {}).get("p0_count")) or 0) != 0:
        raise RuntimeError("subscription control execute blocked: dry-run has P0")
    if bool(((report.get("side_effects") or {}).get("market_data_pulled"))):
        raise RuntimeError("subscription control execute blocked: dry-run unexpectedly pulled market data")
    for section_name in (
        "market_data_subscription_candidate",
        "market_data_subscription_dedup",
        "market_data_pull_plan",
    ):
        section = report.get(section_name) or {}
        rows = section.get("rows") or []
        if not section.get("rows_included"):
            raise RuntimeError(f"subscription control execute blocked: {section_name} rows missing")
        if len(rows) != int(section.get("row_count") or 0):
            raise RuntimeError(f"subscription control execute blocked: {section_name} row_count mismatch")


def run_subscription_control_from_dry_run(
    *,
    dsn: str,
    dry_run_path: str,
    json_report_path: str,
    markdown_report_path: str,
    execute: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    if not execute:
        raise RuntimeError("subscription control execute blocked: missing --execute")
    if not user_confirmed:
        raise RuntimeError("subscription control execute blocked: missing --user-confirmed")
    dry_run = read_json(dry_run_path)
    validate_dry_run(dry_run)
    run_id = str(dry_run["market_data_run_id"])
    started_at = utc_now_iso()
    pre_backup = capture_subscription_execution_backup(
        dsn,
        phase="before_dynamic_subscription_control",
        execute_run_id=run_id,
    )
    if pre_backup.get("target_run_exists"):
        raise RuntimeError(f"subscription control execute blocked: run already exists: {run_id}")

    write_result = persist_subscription_plan(dsn=dsn, dry_run_report=dry_run, execute_run_id=run_id)
    post_backup = capture_subscription_execution_backup(
        dsn,
        phase="after_dynamic_subscription_control",
        execute_run_id=run_id,
    )
    post_checks = build_post_subscription_execute_checks(
        pre_backup=pre_backup,
        post_backup=post_backup,
        dry_run_report=dry_run,
        write_result=write_result,
        execute_run_id=run_id,
    )
    quality_items = list((dry_run.get("quality") or {}).get("items") or []) + build_post_quality_items(post_checks)
    quality_counts = count_quality_severities(quality_items)
    result = "EXECUTE_PASS" if quality_counts["P0"] == 0 else "BLOCKED"
    report = {
        "result": result,
        "stage": "N3_DYNAMIC_MARKET_DATA_SUBSCRIPTION_CONTROL_EXECUTE",
        "layer_role": "N3_market_data",
        "market_data_run_id": run_id,
        "source_condition_run_id": dry_run.get("source_condition_run_id"),
        "for_trade_date": dry_run.get("for_trade_date"),
        "source_trade_date": dry_run.get("source_trade_date"),
        "prev_trade_date": dry_run.get("prev_trade_date"),
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "dry_run_path": dry_run_path,
        "write_result": write_result,
        "post_checks": post_checks,
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "writes_performed": True,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
            "voice_mobile_sim_position_trade_touched": False,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_report(report))
    return report


def format_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    write = report.get("write_result") or {}
    return "\n".join(
        [
            "# N3 Dynamic Market-Data Subscription Control Execute Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- market_data_run_id: `{report.get('market_data_run_id')}`",
            f"- candidate rows written: `{write.get('candidate_rows_written')}`",
            f"- subscription rows written: `{write.get('subscription_rows_written')}`",
            f"- pull_plan rows written: `{write.get('pull_plan_rows_written')}`",
            f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
            "",
            "## Boundary",
            "",
            "- market_data_pulled=false",
            "- market_data_fact_written=false",
            "- event_outbox_written=false",
            "- downstream_layers_touched=false",
            "- worker_started=false",
        ]
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--dry-run-path", required=True)
    parser.add_argument("--json-report-path", required=True)
    parser.add_argument("--markdown-report-path", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    try:
        report = run_subscription_control_from_dry_run(
            dsn=args.dsn,
            dry_run_path=args.dry_run_path,
            json_report_path=args.json_report_path,
            markdown_report_path=args.markdown_report_path,
            execute=args.execute,
            user_confirmed=args.user_confirmed,
        )
    except RuntimeError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    write = report.get("write_result") or {}
    print(
        " ".join(
            [
                str(report.get("result")),
                f"run_id={report.get('market_data_run_id')}",
                f"subscriptions={write.get('subscription_rows_written')}",
                f"pull_plan={write.get('pull_plan_rows_written')}",
            ]
        )
    )
    return 0 if report.get("result") == "EXECUTE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
