"""Execute V3 20260615 C1 action-confirmation scoped subscription rows.

This runner persists only N3 subscription control rows from a reviewed dry-run
artifact. It does not pull market data, write minute facts, emit outbox events,
or enter downstream layers.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ashare_v3.condition.basis import count_quality_severities
from ashare_v3.market.subscription_execute import (
    build_post_quality_items,
    build_post_subscription_execute_checks,
    capture_subscription_execution_backup,
    persist_subscription_plan,
)


EXPECTED_STAGE = "V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_CONTROL_ROW_DRY_RUN"
EXPECTED_RUN_ID = (
    "market_data_subscription_20260615_action_confirmation_c1_1005_scope__"
    "n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1"
)
DEFAULT_DRY_RUN_PATH = "docs/V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_CONTROL_ROW_DRY_RUN.json"
DEFAULT_JSON_REPORT_PATH = (
    "docs/V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_CONTROL_ROW_EXECUTE_REPORT.json"
)
DEFAULT_MARKDOWN_REPORT_PATH = (
    "docs/V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_CONTROL_ROW_EXECUTE_REPORT.md"
)
DEFAULT_ROLLBACK_SQL_PATH = "sql/V3_20260615_c1_action_confirmation_scope_subscription_control_rollback.sql"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")


def write_text(path: str | Path, text: str) -> None:
    Path(path).write_text(text)


def validate_scoped_subscription_dry_run(report: Mapping[str, Any]) -> None:
    if report.get("stage") != EXPECTED_STAGE:
        raise RuntimeError("V3 20260615 scoped subscription execute blocked: dry-run stage mismatch")
    if report.get("market_data_run_id") != EXPECTED_RUN_ID:
        raise RuntimeError("V3 20260615 scoped subscription execute blocked: run_id mismatch")
    if report.get("mode") != "dry_run":
        raise RuntimeError("V3 20260615 scoped subscription execute blocked: dry-run mode mismatch")
    if bool(report.get("blocked")) or not bool(report.get("passed")):
        raise RuntimeError("V3 20260615 scoped subscription execute blocked: dry-run did not pass")
    if int(((report.get("quality") or {}).get("p0_count")) or 0) != 0:
        raise RuntimeError("V3 20260615 scoped subscription execute blocked: dry-run has P0")
    for section_name in (
        "market_data_subscription_candidate",
        "market_data_subscription_dedup",
        "market_data_pull_plan",
    ):
        section = report.get(section_name) or {}
        rows = section.get("rows") or []
        if not section.get("rows_included"):
            raise RuntimeError(f"V3 20260615 scoped subscription execute blocked: {section_name} rows missing")
        if len(rows) != int(section.get("row_count") or 0):
            raise RuntimeError(f"V3 20260615 scoped subscription execute blocked: {section_name} row_count mismatch")


def run_scoped_subscription_execute(
    *,
    dsn: str,
    dry_run_path: str = DEFAULT_DRY_RUN_PATH,
    json_report_path: str = DEFAULT_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_MARKDOWN_REPORT_PATH,
    execute: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    if not execute:
        raise RuntimeError("V3 20260615 scoped subscription execute blocked: missing --execute")
    if not user_confirmed:
        raise RuntimeError("V3 20260615 scoped subscription execute blocked: missing --user-confirmed")

    dry_run = read_json(dry_run_path)
    validate_scoped_subscription_dry_run(dry_run)
    run_id = str(dry_run["market_data_run_id"])
    started_at = utc_now_iso()
    pre_backup = capture_subscription_execution_backup(
        dsn,
        phase="before_v3_20260615_c1_action_scope_subscription",
        execute_run_id=run_id,
    )
    if pre_backup.get("target_run_exists"):
        raise RuntimeError(f"V3 20260615 scoped subscription execute blocked: run already exists: {run_id}")

    write_result = persist_subscription_plan(dsn=dsn, dry_run_report=dry_run, execute_run_id=run_id)
    post_backup = capture_subscription_execution_backup(
        dsn,
        phase="after_v3_20260615_c1_action_scope_subscription",
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
    severity_counts = count_quality_severities(quality_items)
    result = "EXECUTE_PASS" if severity_counts["P0"] == 0 else "BLOCKED"
    report = {
        "result": result,
        "stage": "V3_20260615_C1_ACTION_CONFIRMATION_SCOPE_SUBSCRIPTION_CONTROL_ROW_EXECUTE",
        "layer_role": "N3_market_data",
        "market_data_run_id": run_id,
        "source_condition_run_id": dry_run.get("source_condition_run_id"),
        "source_n4_trigger_run_id": dry_run.get("source_n4_trigger_run_id"),
        "for_trade_date": dry_run.get("for_trade_date"),
        "source_trade_date": dry_run.get("source_trade_date"),
        "prev_trade_date": dry_run.get("prev_trade_date"),
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "dry_run_path": dry_run_path,
        "write_result": write_result,
        "post_checks": post_checks,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "pre_execute": {
            "target_run_exists": pre_backup.get("target_run_exists"),
            "n3_fact_and_event_row_counts": pre_backup.get("n3_fact_and_event_row_counts"),
        },
        "post_execute": {
            "target_run_row_counts": post_backup.get("target_run_row_counts"),
            "n3_fact_and_event_row_counts": post_backup.get("n3_fact_and_event_row_counts"),
            "market_data_run_row": post_backup.get("market_data_run_row"),
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
            "real_trade_touched": False,
        },
        "rollback": {
            "rollback_safe": result == "EXECUTE_PASS",
            "rollback_sql_path": DEFAULT_ROLLBACK_SQL_PATH,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_execute_report(report))
    return report


def format_execute_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    write_result = report.get("write_result") or {}
    return "\n".join(
        [
            "# V3 20260615 C1 Action-Confirmation Scoped Subscription Execute Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- market_data_run_id: `{report.get('market_data_run_id')}`",
            f"- candidate rows written: `{write_result.get('candidate_rows_written')}`",
            f"- subscription rows written: `{write_result.get('subscription_rows_written')}`",
            f"- pull_plan rows written: `{write_result.get('pull_plan_rows_written')}`",
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
