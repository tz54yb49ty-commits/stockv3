"""Execute reviewed scoped N3 subscription control-row manifests.

This helper is intentionally manifest-driven: it persists only the reviewed
control rows already embedded in a dry-run artifact. It never replans from N2,
pulls market data, writes market facts, emits outbox events, or enters
downstream layers.
"""

from __future__ import annotations

from copy import deepcopy
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

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


CONTROL_TABLES = {
    "common_market_data_run",
    "common_market_data_quality_item",
    "common_market_data_subscription_candidate",
    "common_market_data_subscription",
    "common_market_data_pull_plan",
}
CANONICAL_DIRECTIONS = {"buy", "sell"}


class ScopedSubscriptionControlExecuteBlocked(RuntimeError):
    """Raised when a reviewed scoped control-row manifest is not executable."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")


def write_text(path: str | Path, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def require_execute_flags(*, execute: bool, user_confirmed: bool) -> None:
    if execute and not user_confirmed:
        raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: missing --user-confirmed")
    if user_confirmed and not execute:
        raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: missing --execute")


def _direction_from_condition_key(condition_key: str) -> str | None:
    if condition_key.startswith("BUY"):
        return "buy"
    if condition_key.startswith("SELL"):
        return "sell"
    return None


def _signal_type_from_condition_key(condition_key: str) -> str:
    if condition_key == "BUY_HINT":
        return "BUY_HINT"
    if condition_key == "SELL_HINT":
        return "SELL_HINT"
    if condition_key == "BUY:FULL":
        return "BUY:FULL"
    if condition_key == "SELL:FULL":
        return "SELL:FULL"
    if condition_key.startswith("BUY"):
        return "BUY"
    if condition_key.startswith("SELL"):
        return "SELL"
    return condition_key


def _split_mixed_candidate_row(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    direction = str(row.get("direction") or "")
    if direction in CANONICAL_DIRECTIONS:
        return [dict(row)]
    raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), Mapping) else {}
    condition_keys = list((raw_json or {}).get("source_trigger_context_condition_keys") or [])
    source_scope_ids = list((raw_json or {}).get("all_source_scope_ids") or [])
    pool_ids = list((raw_json or {}).get("all_source_condition_pool_ids") or [])
    expanded: list[dict[str, Any]] = []
    for index, condition_key_value in enumerate(condition_keys):
        condition_key = str(condition_key_value or "")
        resolved_direction = _direction_from_condition_key(condition_key)
        if resolved_direction not in CANONICAL_DIRECTIONS:
            continue
        item = dict(row)
        item["direction"] = resolved_direction
        item["condition_key"] = condition_key
        item["allowed_signal_types"] = [_signal_type_from_condition_key(condition_key)]
        if index < len(source_scope_ids):
            item["source_scope_id"] = source_scope_ids[index]
            item["source_scope_ref"] = f"{item.get('source_scope_table')}:{source_scope_ids[index]}"
        if index < len(pool_ids):
            item["source_condition_pool_id"] = pool_ids[index]
        item["candidate_ref"] = f"{row.get('candidate_ref')}:{resolved_direction}:{index + 1}"
        item["raw_json"] = {
            **dict(raw_json or {}),
            "expanded_from_mixed_direction": True,
            "original_direction": direction,
            "original_condition_key": row.get("condition_key"),
            "selected_source_trigger_context_condition_key": condition_key,
            "selected_allowed_signal_type": item["allowed_signal_types"][0],
            "selected_source_scope_id": item.get("source_scope_id"),
            "selected_source_condition_pool_id": item.get("source_condition_pool_id"),
        }
        expanded.append(item)
    if not expanded:
        raise ScopedSubscriptionControlExecuteBlocked(
            f"scoped subscription control execute blocked: unsupported candidate direction {direction}"
        )
    return expanded


def normalize_candidate_directions(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a manifest copy whose candidate rows use DB-legal directions.

    The reviewed ordinary/FULL expansion manifest can dedupe a buy and sell
    source-scope pair into one subscription candidate with direction=mixed.
    The runtime table deliberately accepts only canonical buy/sell values, so
    keep the deduped subscription row intact and expand only the candidate audit
    rows back to their original condition-key directions.
    """

    output = deepcopy(dict(report))
    candidate_section = output.get("market_data_subscription_candidate") or {}
    original_rows = list(candidate_section.get("rows") or [])
    normalized_rows: list[dict[str, Any]] = []
    mixed_rows = 0
    for row in original_rows:
        split_rows = _split_mixed_candidate_row(row)
        if str(row.get("direction") or "") not in CANONICAL_DIRECTIONS:
            mixed_rows += 1
        normalized_rows.extend(split_rows)
    candidate_section["rows"] = normalized_rows
    candidate_section["row_count"] = len(normalized_rows)
    output["market_data_subscription_candidate"] = candidate_section
    output["candidate_row_count"] = len(normalized_rows)
    output["subscription_candidate_count"] = len(normalized_rows)
    planned_rows = dict(output.get("planned_rows") or {})
    if planned_rows:
        planned_rows["candidate"] = len(normalized_rows)
        output["planned_rows"] = planned_rows
    subscription_count = int(output.get("subscription_row_count") or 0)
    if normalized_rows and subscription_count:
        dedup_ratio = subscription_count / len(normalized_rows)
        output["dedup_ratio"] = dedup_ratio
        output["dedup_reduction_ratio"] = 1 - dedup_ratio
    output["candidate_direction_normalization"] = {
        "applied": mixed_rows > 0,
        "source_mixed_candidate_rows": mixed_rows,
        "candidate_rows_before": len(original_rows),
        "candidate_rows_after": len(normalized_rows),
        "policy": "expand_mixed_candidate_rows_to_canonical_buy_sell_v1",
        "subscription_rows_preserved": subscription_count,
    }
    return output


def validate_scoped_control_manifest(report: Mapping[str, Any], *, expected_run_id: str | None = None) -> None:
    if report.get("mode") != "dry_run":
        raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: manifest is not dry_run")
    if bool(report.get("blocked")) or not bool(report.get("passed")):
        raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: manifest did not pass")
    run_id = str(report.get("market_data_run_id") or report.get("control_run_id") or "")
    if not run_id:
        raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: missing run_id")
    if expected_run_id and run_id != expected_run_id:
        raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: run_id mismatch")
    quality = report.get("quality") or {}
    if int(quality.get("p0_count") or 0) != 0:
        raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: manifest has P0")
    allowed_write_tables = set(report.get("allowed_write_tables") or [])
    if allowed_write_tables and not allowed_write_tables.issubset(CONTROL_TABLES):
        raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: write scope is not control-only")
    for section_name in (
        "market_data_subscription_candidate",
        "market_data_subscription_dedup",
        "market_data_pull_plan",
    ):
        section = report.get(section_name) or {}
        rows = section.get("rows") or []
        if not section.get("rows_included"):
            raise ScopedSubscriptionControlExecuteBlocked(f"scoped subscription control execute blocked: {section_name} rows missing")
        if len(rows) != int(section.get("row_count") or 0):
            raise ScopedSubscriptionControlExecuteBlocked(f"scoped subscription control execute blocked: {section_name} row_count mismatch")
    for row in (report.get("market_data_subscription_candidate") or {}).get("rows") or []:
        if str(row.get("direction") or "") not in CANONICAL_DIRECTIONS:
            raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: candidate direction must be buy/sell")
    for row in (report.get("market_data_pull_plan") or {}).get("rows") or []:
        if bool(row.get("execute_allowed")):
            raise ScopedSubscriptionControlExecuteBlocked("scoped subscription control execute blocked: pull_plan execute_allowed must be false")


def format_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    write_result = report.get("write_result") or {}
    return "\n".join(
        [
            "# Scoped N3 Subscription Control Execute Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- market_data_run_id: `{report.get('market_data_run_id')}`",
            f"- mode: `{report.get('mode')}`",
            f"- candidate rows written: `{write_result.get('candidate_rows_written', 0)}`",
            f"- subscription rows written: `{write_result.get('subscription_rows_written', 0)}`",
            f"- pull_plan rows written: `{write_result.get('pull_plan_rows_written', 0)}`",
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


def run_scoped_subscription_control_execute(
    *,
    dsn: str = DEFAULT_DSN,
    dry_run_path: str | Path,
    json_report_path: str | Path,
    markdown_report_path: str | Path,
    expected_run_id: str | None = None,
    rollback_sql_path: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    require_execute_flags(execute=execute, user_confirmed=user_confirmed)
    dry_run = normalize_candidate_directions(read_json(dry_run_path))
    validate_scoped_control_manifest(dry_run, expected_run_id=expected_run_id)
    run_id = str(dry_run.get("market_data_run_id") or dry_run.get("control_run_id"))
    if not execute:
        report = {
            "result": "PLAN_ONLY",
            "mode": "plan_only",
            "market_data_run_id": run_id,
            "dry_run_path": str(dry_run_path),
            "database_written": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "candidate_direction_normalization": dry_run.get("candidate_direction_normalization"),
        }
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_report(report))
        return report

    started_at = utc_now_iso()
    pre_backup = capture_subscription_execution_backup(
        dsn,
        phase="before_scoped_subscription_control_execute",
        execute_run_id=run_id,
    )
    if pre_backup.get("target_run_exists"):
        raise ScopedSubscriptionControlExecuteBlocked(f"scoped subscription control execute blocked: run already exists: {run_id}")
    write_result = persist_subscription_plan(dsn=dsn, dry_run_report=dry_run, execute_run_id=run_id)
    post_backup = capture_subscription_execution_backup(
        dsn,
        phase="after_scoped_subscription_control_execute",
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
        "mode": "execute",
        "market_data_run_id": run_id,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "dry_run_path": str(dry_run_path),
        "write_result": write_result,
        "candidate_direction_normalization": dry_run.get("candidate_direction_normalization"),
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
            "rollback_sql_path": rollback_sql_path,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_report(report))
    return report
