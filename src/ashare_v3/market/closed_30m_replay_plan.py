"""N3-C2 closed minute / closed 30m replay dry-run planner.

This module plans C2 replay and closed 30m summary work from existing runtime
facts. It never pulls market data, writes minute facts, writes summary rows,
emits outbox events, consumes events, or starts workers.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, time
from pathlib import Path
import json
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.preload_plan import MINUTE_FACT_TABLES, normalize_db_row
from ashare_v3.market.subscription_plan import ASSET_KINDS
from ashare_v3.market.today_minute_plan import iter_minute_labels, parse_trade_date


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_DRY_RUN_PLAN_PATH = "docs/N3_C2_closed_30m_dry_run_plan.json"
DEFAULT_EXECUTE_CONTRACT_PATH = "docs/N3_C2_closed_30m_execute_contract.json"
DEFAULT_C1_REPORT_PATH = "docs/N3_C1_TODAY_MINUTE_BAR_1M_EXECUTE_REPORT.md"
DEFAULT_B2_REPORT_PATH = "docs/N3_B2_realtime_projection_execute_report.json"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N3_C2_closed_30m_business_rollback.sql"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/N3_C2_CLOSED_30M_REPLAY_DRY_RUN_REPORT.md"
DEFAULT_JSON_REPORT_PATH = "docs/N3_C2_closed_30m_replay_dry_run_report.json"

IDENTITY_COLUMNS = {
    "stock": "stock_identity_key",
    "index": "index_identity_key",
    "board": "board_identity_key",
}
SUMMARY_TABLES = {
    "stock": "stock_closed_30m_summary",
    "index": "index_closed_30m_summary",
    "board": "board_closed_30m_summary",
}
BUCKET_SPECS = (
    ("0931_1000", time(9, 31), time(10, 0)),
    ("1001_1030", time(10, 1), time(10, 30)),
    ("1031_1100", time(10, 31), time(11, 0)),
    ("1101_1130", time(11, 1), time(11, 30)),
    ("1301_1330", time(13, 1), time(13, 30)),
    ("1331_1400", time(13, 31), time(14, 0)),
    ("1401_1430", time(14, 1), time(14, 30)),
    ("1431_1500", time(14, 31), time(15, 0)),
)
ALLOWED_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_minute_bar_1m delta rows",
    "index_minute_bar_1m delta rows",
    "board_minute_bar_1m delta rows",
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
]
FORBIDDEN_WRITE_TABLES = [
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "B1/B2/N4/N5 existing runtime rows",
    "condition tables",
    "trigger/action/user/voice/mobile/sim/position tables",
    "worker",
]


def bucket_definitions() -> list[dict[str, Any]]:
    return [
        {
            "bucket_id": bucket_id,
            "start_label": start.strftime("%H:%M"),
            "end_label": end.strftime("%H:%M"),
            "labels": minute_labels_between(start, end),
            "expected_minute_count": 30,
        }
        for bucket_id, start, end in BUCKET_SPECS
    ]


def build_full_day_minute_labels() -> list[str]:
    labels: list[str] = []
    for bucket in bucket_definitions():
        labels.extend(bucket["labels"])
    return labels


def minute_labels_between(start: time, end: time) -> list[str]:
    trade_day = parse_trade_date("20260525")
    return [
        minute_time.strftime("%H:%M")
        for minute_time in iter_minute_labels(trade_day, start, end)
    ]


def labels_after(label: str) -> list[str]:
    labels = build_full_day_minute_labels()
    if label not in labels:
        return labels
    return labels[labels.index(label) + 1 :]


def labels_until(label: str) -> set[str]:
    labels = build_full_day_minute_labels()
    if label not in labels:
        return set()
    return set(labels[: labels.index(label) + 1])


def build_delta_plan(
    *,
    latest_closed_label: str,
    object_counts_by_asset: Mapping[str, int],
    bj_missing_count: int,
) -> dict[str, Any]:
    missing_labels = labels_after(latest_closed_label)
    total_objects = sum(int(object_counts_by_asset.get(asset_kind) or 0) for asset_kind in ASSET_KINDS)
    non_bj_objects = max(total_objects - int(bj_missing_count or 0), 0)
    return {
        "compare_key": ["asset_kind", "identity_key", "trade_date", "bar_time"],
        "delta_kinds": ["missing_bar", "changed_bar", "new_bj_bar", "source_missing", "source_error"],
        "main_gap": {
            "from_label": missing_labels[0] if missing_labels else None,
            "to_label": missing_labels[-1] if missing_labels else None,
            "label_count": len(missing_labels),
            "available_non_bj_objects": non_bj_objects,
            "estimated_rows": len(missing_labels) * non_bj_objects,
        },
        "delta_minute_rows_estimate": len(missing_labels) * non_bj_objects,
        "bj_retry_capacity": {
            "objects": int(bj_missing_count or 0),
            "labels_per_object": len(build_full_day_minute_labels()),
            "estimated_rows_if_available": int(bj_missing_count or 0) * len(build_full_day_minute_labels()),
        },
        "replay_diff_check_required": True,
        "does_not_update_c1_rows": True,
    }


def build_closed_summary_plan(
    *,
    latest_closed_label: str,
    object_counts_by_asset: Mapping[str, int],
    missing_candidate_counts_by_asset: Mapping[str, int],
) -> dict[str, Any]:
    closed_labels = labels_until(latest_closed_label)
    bucket_rows: list[dict[str, Any]] = []
    status_counts_by_asset: dict[str, dict[str, int]] = {
        asset_kind: {"closed": 0, "partial": 0, "missing": 0, "failed": 0}
        for asset_kind in ASSET_KINDS
    }
    for asset_kind in ASSET_KINDS:
        object_count = int(object_counts_by_asset.get(asset_kind) or 0)
        missing_candidate_count = int(missing_candidate_counts_by_asset.get(asset_kind) or 0)
        available_object_count = max(object_count - missing_candidate_count, 0)
        for bucket in bucket_definitions():
            actual_count_for_available = len([label for label in bucket["labels"] if label in closed_labels])
            available_status = closed_status_for_count(actual_count_for_available, bucket["expected_minute_count"])
            bucket_status_counts = {"closed": 0, "partial": 0, "missing": 0, "failed": 0}
            bucket_status_counts[available_status] += available_object_count
            bucket_status_counts["missing"] += missing_candidate_count
            for status, count in bucket_status_counts.items():
                status_counts_by_asset[asset_kind][status] += count
            bucket_rows.append(
                {
                    "asset_kind": asset_kind,
                    "bucket_id": bucket["bucket_id"],
                    "expected_minute_count": bucket["expected_minute_count"],
                    "actual_minute_count_for_available_objects": actual_count_for_available,
                    "available_object_count": available_object_count,
                    "missing_candidate_count": missing_candidate_count,
                    "status_counts": bucket_status_counts,
                }
            )
    status_counts = {"closed": 0, "partial": 0, "missing": 0, "failed": 0}
    for counts in status_counts_by_asset.values():
        for status, count in counts.items():
            status_counts[status] += count
    expected_rows_by_asset = {
        asset_kind: int(object_counts_by_asset.get(asset_kind) or 0) * len(BUCKET_SPECS)
        for asset_kind in ASSET_KINDS
    }
    expected_rows_by_asset["total"] = sum(expected_rows_by_asset.values())
    return {
        "bucket_ids": [bucket["bucket_id"] for bucket in bucket_definitions()],
        "expected_minute_count_per_bucket": 30,
        "expected_summary_rows": expected_rows_by_asset,
        "status_counts": status_counts,
        "status_counts_by_asset": status_counts_by_asset,
        "bucket_rows": bucket_rows,
    }


def closed_status_for_count(actual_count: int, expected_count: int) -> str:
    if actual_count == expected_count:
        return "closed"
    if actual_count == 0:
        return "missing"
    return "partial"


def identify_bj_missing_candidates(
    subscriptions: Sequence[Mapping[str, Any]],
    baseline_counts_by_identity: Mapping[str, int],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for subscription in subscriptions:
        if str(subscription.get("asset_kind") or "") != "stock":
            continue
        identity_key = str(subscription.get("identity_key") or "")
        exchange = str(subscription.get("exchange") or "")
        code = str(subscription.get("code") or "")
        if not (exchange == "BJ" or code.startswith("920") or identity_key.startswith("stock:BJ:920")):
            continue
        if int(baseline_counts_by_identity.get(identity_key) or 0) != 0:
            continue
        candidates.append(
            {
                "asset_kind": "stock",
                "identity_key": identity_key,
                "exchange": exchange,
                "code": code,
                "name": subscription.get("name"),
                "baseline_row_count": 0,
                "replay_status": "replay_required",
                "missing_reason": "BJ 920xxx object has no C1 baseline minute rows",
            }
        )
    return candidates


def build_write_scope_contract() -> dict[str, Any]:
    return {
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "minute_bar_closed_event_deferred_to": "N3-C3",
        "downstream_layers_touched": False,
        "worker_started": False,
    }


def build_closed_30m_replay_dry_run(
    *,
    dsn: str,
    dry_run_plan_path: str = DEFAULT_DRY_RUN_PLAN_PATH,
    execute_contract_path: str = DEFAULT_EXECUTE_CONTRACT_PATH,
    c1_report_path: str = DEFAULT_C1_REPORT_PATH,
    b2_report_path: str = DEFAULT_B2_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
    include_rows: bool = True,
) -> dict[str, Any]:
    dry_run_plan = load_json_file(dry_run_plan_path)
    execute_contract = load_json_file(execute_contract_path)
    c1_report_exists = Path(c1_report_path).exists()
    b2_report = load_json_file(b2_report_path)
    rollback_sql_exists = Path(rollback_sql_path).exists()
    c2_run_id = str(execute_contract.get("c2_run_id") or dry_run_plan.get("c2_run_id") or "")
    lineage = execute_contract.get("lineage") or dry_run_plan.get("lineage") or {}
    runtime = fetch_runtime_context(
        dsn=dsn,
        c2_run_id=c2_run_id,
        source_subscription_run_id=str(lineage.get("source_subscription_run_id") or ""),
        today_minute_run_id=str((lineage.get("source_today_minute_run_ids") or [""])[0]),
        for_trade_date=str(lineage.get("for_trade_date") or ""),
        include_rows=include_rows,
    )
    missing_counts_by_asset = {
        asset_kind: int(runtime.get("missing_candidate_counts_by_asset", {}).get(asset_kind) or 0)
        for asset_kind in ASSET_KINDS
    }
    planning_subscriptions = runtime.pop("subscription_rows_for_planning", [])
    bj_missing_candidates = identify_bj_missing_candidates(
        planning_subscriptions,
        runtime.get("baseline_counts_by_identity", {}),
    )
    missing_counts_by_asset["stock"] = max(missing_counts_by_asset.get("stock", 0), len(bj_missing_candidates))
    latest_label = str(runtime.get("latest_closed_label") or "14:11")
    return build_replay_dry_run_report(
        c2_run_id=c2_run_id,
        source_condition_run_id=str(lineage.get("source_condition_run_id") or ""),
        source_subscription_run_id=str(lineage.get("source_subscription_run_id") or ""),
        today_minute_run_id=str((lineage.get("source_today_minute_run_ids") or [""])[0]),
        projection_run_id=str(lineage.get("source_projection_run_id") or b2_report.get("projection_run_id") or ""),
        for_trade_date=str(lineage.get("for_trade_date") or ""),
        latest_closed_label=latest_label,
        object_counts_by_asset=runtime.get("object_counts_by_asset", {}),
        baseline_rows_by_asset=runtime.get("baseline_rows_by_asset", {}),
        missing_candidate_counts_by_asset=missing_counts_by_asset,
        bj_missing_candidates=bj_missing_candidates,
        target_audit=runtime.get("target_audit", {}),
        source_evidence={
            "dry_run_plan_path": dry_run_plan_path,
            "execute_contract_path": execute_contract_path,
            "c1_report_path": c1_report_path,
            "c1_report_exists": c1_report_exists,
            "b2_report_path": b2_report_path,
            "b2_projection_run_id": b2_report.get("projection_run_id"),
            "rollback_sql_path": rollback_sql_path,
            "rollback_sql_exists": rollback_sql_exists,
        },
        runtime_context=runtime,
    )


def build_replay_dry_run_report(
    *,
    c2_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    today_minute_run_id: str,
    projection_run_id: str,
    for_trade_date: str,
    latest_closed_label: str,
    object_counts_by_asset: Mapping[str, int],
    baseline_rows_by_asset: Mapping[str, int],
    missing_candidate_counts_by_asset: Mapping[str, int],
    bj_missing_candidates: Sequence[Mapping[str, Any]],
    target_audit: Mapping[str, Any],
    source_evidence: Mapping[str, Any] | None = None,
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    object_counts = {asset_kind: int(object_counts_by_asset.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}
    object_counts["total"] = sum(object_counts.values())
    baseline_rows = {asset_kind: int(baseline_rows_by_asset.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}
    baseline_rows["total"] = sum(baseline_rows.values())
    missing_counts = {asset_kind: int(missing_candidate_counts_by_asset.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}
    delta_plan = build_delta_plan(
        latest_closed_label=latest_closed_label,
        object_counts_by_asset=object_counts,
        bj_missing_count=len(bj_missing_candidates),
    )
    summary_plan = build_closed_summary_plan(
        latest_closed_label=latest_closed_label,
        object_counts_by_asset=object_counts,
        missing_candidate_counts_by_asset=missing_counts,
    )
    write_scope = build_write_scope_contract()
    quality_items = build_quality_items(
        c2_run_id=c2_run_id,
        object_counts=object_counts,
        baseline_rows=baseline_rows,
        summary_plan=summary_plan,
        delta_plan=delta_plan,
        bj_missing_candidates=bj_missing_candidates,
        target_audit=target_audit,
        source_evidence=source_evidence or {},
    )
    severity_counts = count_quality_severities(quality_items)
    blocked = severity_counts["P0"] > 0
    return {
        "stage": "N3-C2",
        "layer_role": "N3_market_data",
        "execution_mode": "closed_minute_30m_replay_dry_run",
        "result": "DRY_RUN_BLOCKED" if blocked else "DRY_RUN_PASS",
        "blocked": blocked,
        "c2_run_id": c2_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "today_minute_run_id": today_minute_run_id,
        "projection_run_id": projection_run_id,
        "for_trade_date": for_trade_date,
        "latest_closed_label": latest_closed_label,
        "object_counts_by_asset": object_counts,
        "baseline_rows_by_asset": baseline_rows,
        "missing_candidate_counts_by_asset": missing_counts,
        "bj_missing_candidates": list(bj_missing_candidates),
        "replay_plan": {
            "full_day_minute_labels_per_object": len(build_full_day_minute_labels()),
            "full_day_expected_rows_if_all_available": object_counts["total"] * len(build_full_day_minute_labels()),
            "expected_rows_if_bj_920xxx_still_missing": (
                object_counts["total"] - len(bj_missing_candidates)
            )
            * len(build_full_day_minute_labels()),
            "adapter_routing": {"stock": "bars()", "index": "index_bars()", "board": "index_bars()"},
            "pulls_market_data_in_dry_run": False,
        },
        "delta_plan": delta_plan,
        "closed_30m_summary_plan": summary_plan,
        "write_scope_contract": write_scope,
        "target_audit": dict(target_audit),
        "source_evidence": dict(source_evidence or {}),
        "runtime_context": dict(runtime_context or {}),
        "rollback_sql_path": DEFAULT_ROLLBACK_SQL_PATH,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "minute_delta_written": False,
            "closed_summary_written": False,
            "quality_written": False,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "inbox_or_checkpoint_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "next_allowed_step": "N3-C2 dry-run review" if not blocked else "fix P0 blockers before C2 review",
    }


def build_quality_items(
    *,
    c2_run_id: str,
    object_counts: Mapping[str, int],
    baseline_rows: Mapping[str, int],
    summary_plan: Mapping[str, Any],
    delta_plan: Mapping[str, Any],
    bj_missing_candidates: Sequence[Mapping[str, Any]],
    target_audit: Mapping[str, Any],
    source_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not c2_run_id:
        items.append(quality_item("P0", "failed", "n3_c2_c2_run_id_present", "C2 run id is present"))
    if int(target_audit.get("run_exists") or 0):
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c2_run_id_not_reused",
                "C2 run id must not already exist",
                expected="absent",
                actual="present",
            )
        )
    for scope_name in ("minute_rows_for_c2_run", "summary_rows_for_c2_run"):
        counts = target_audit.get(scope_name) or {}
        total = sum(int(counts.get(asset_kind) or 0) for asset_kind in ASSET_KINDS)
        if total:
            items.append(
                quality_item(
                    "P0",
                    "failed",
                    f"n3_c2_{scope_name}_zero",
                    f"{scope_name} must be zero before dry-run review",
                    expected="0",
                    actual=str(total),
                )
            )
    for name in ("quality_rows_for_c2_run", "outbox_rows_for_c2_run", "inbox_rows_for_c2_run", "checkpoint_rows_for_c2_run"):
        if int(target_audit.get(name) or 0):
            items.append(
                quality_item(
                    "P0",
                    "failed",
                    f"n3_c2_{name}_zero",
                    f"{name} must be zero before execute",
                    expected="0",
                    actual=str(target_audit.get(name)),
                )
            )
    expected_summary_rows = (summary_plan.get("expected_summary_rows") or {}).get("total")
    if expected_summary_rows != object_counts.get("total", 0) * len(BUCKET_SPECS):
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c2_expected_summary_rows_match_object_count",
                "expected summary rows equal object_count * 8 buckets",
                expected=str(object_counts.get("total", 0) * len(BUCKET_SPECS)),
                actual=str(expected_summary_rows),
            )
        )
    if not source_evidence.get("rollback_sql_exists", True):
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c2_rollback_sql_exists",
                "C2 business rollback SQL exists",
                expected="true",
                actual="false",
            )
        )
    if len(bj_missing_candidates) > 0:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_c2_bj_920xxx_replay_required",
                "BJ 920xxx missing candidates remain visible for replay",
                expected="0 missing candidates",
                actual=str(len(bj_missing_candidates)),
            )
        )
    status_counts = summary_plan.get("status_counts") or {}
    partial_or_missing = int(status_counts.get("partial") or 0) + int(status_counts.get("missing") or 0)
    if partial_or_missing:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_c2_partial_or_missing_summary_visible",
                "dry-run exposes current partial/missing summary buckets",
                expected="0 partial/missing before full replay",
                actual=str(partial_or_missing),
            )
        )
    if delta_plan.get("replay_diff_check_required"):
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_c2_replay_diff_check_required",
                "future execute must compare replay rows against C1 baseline",
                expected="diff check required",
                actual="required",
            )
        )
    if int(baseline_rows.get("total") or 0) == 0:
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c2_c1_baseline_rows_present",
                "C1 baseline minute rows are present",
                expected=">0",
                actual="0",
            )
        )
    if not items:
        items.append(
            quality_item(
                "P2",
                "passed",
                "n3_c2_dry_run_ready",
                "C2 dry-run plan is ready for review",
                expected="ready",
                actual="ready",
            )
        )
    return items


def fetch_runtime_context(
    *,
    dsn: str,
    c2_run_id: str,
    source_subscription_run_id: str,
    today_minute_run_id: str,
    for_trade_date: str,
    include_rows: bool,
) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        subscriptions = fetch_minute_subscriptions(cur, source_subscription_run_id)
        object_counts = count_objects_by_asset(subscriptions)
        baseline = fetch_baseline_summary(cur, today_minute_run_id, for_trade_date)
        baseline_counts = fetch_baseline_counts_by_identity(cur, today_minute_run_id, for_trade_date)
        target_audit = fetch_target_audit(cur, c2_run_id)
    latest_label = latest_label_from_baseline(baseline)
    missing_candidates_by_asset = count_missing_candidates_by_asset(subscriptions, baseline_counts)
    return {
        "subscriptions": {
            "row_count": len(subscriptions),
            "rows_included": include_rows,
            "rows": subscriptions if include_rows else subscriptions[:20],
        },
        "subscription_rows_for_planning": subscriptions,
        "object_counts_by_asset": object_counts,
        "baseline_rows_by_asset": {
            asset_kind: int((baseline.get(asset_kind) or {}).get("row_count") or 0)
            for asset_kind in ASSET_KINDS
        },
        "baseline_objects_by_asset": {
            asset_kind: int((baseline.get(asset_kind) or {}).get("object_count") or 0)
            for asset_kind in ASSET_KINDS
        },
        "baseline_min_max_by_asset": {
            asset_kind: {
                "min_bar_time": stringify_dt((baseline.get(asset_kind) or {}).get("min_bar_time")),
                "max_bar_time": stringify_dt((baseline.get(asset_kind) or {}).get("max_bar_time")),
            }
            for asset_kind in ASSET_KINDS
        },
        "latest_closed_label": latest_label,
        "baseline_counts_by_identity": baseline_counts,
        "missing_candidate_counts_by_asset": missing_candidates_by_asset,
        "target_audit": target_audit,
    }


def fetch_minute_subscriptions(cur: Any, run_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT subscription_id, asset_kind, identity_key, exchange, code,
               display_code, name, required_data_kind, data_trade_date
        FROM common_market_data_subscription
        WHERE run_id = %s
          AND required_data_kind = 'minute_bar_1m'
        ORDER BY asset_kind, identity_key
        """,
        (run_id,),
    )
    return [normalize_db_row(row) for row in cur.fetchall()]


def fetch_baseline_summary(cur: Any, run_id: str, trade_date: str) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for asset_kind in ASSET_KINDS:
        table_name = MINUTE_FACT_TABLES[asset_kind]
        identity_column = IDENTITY_COLUMNS[asset_kind]
        cur.execute(
            f"""
            SELECT count(*)::bigint AS row_count,
                   count(DISTINCT {identity_column})::bigint AS object_count,
                   min(bar_time) AS min_bar_time,
                   max(bar_time) AS max_bar_time
            FROM {table_name}
            WHERE run_id = %s
              AND trade_date = %s
              AND is_previous_day_preload = false
            """,
            (run_id, trade_date),
        )
        output[asset_kind] = normalize_db_row(cur.fetchone())
    return output


def fetch_baseline_counts_by_identity(cur: Any, run_id: str, trade_date: str) -> dict[str, int]:
    output: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        table_name = MINUTE_FACT_TABLES[asset_kind]
        identity_column = IDENTITY_COLUMNS[asset_kind]
        cur.execute(
            f"""
            SELECT {identity_column} AS identity_key, count(*)::bigint AS row_count
            FROM {table_name}
            WHERE run_id = %s
              AND trade_date = %s
              AND is_previous_day_preload = false
            GROUP BY {identity_column}
            """,
            (run_id, trade_date),
        )
        for row in cur.fetchall():
            normalized = normalize_db_row(row)
            output[str(normalized["identity_key"])] = int(normalized["row_count"])
    return output


def fetch_target_audit(cur: Any, c2_run_id: str) -> dict[str, Any]:
    return {
        "run_exists": market_data_run_exists(cur, c2_run_id),
        "minute_rows_for_c2_run": {
            asset_kind: count_rows_by_run(cur, MINUTE_FACT_TABLES[asset_kind], c2_run_id)
            for asset_kind in ASSET_KINDS
        },
        "summary_rows_for_c2_run": {
            asset_kind: count_rows_by_run(cur, SUMMARY_TABLES[asset_kind], c2_run_id)
            for asset_kind in ASSET_KINDS
        },
        "quality_rows_for_c2_run": count_rows_by_run(cur, "common_market_data_quality_item", c2_run_id),
        "outbox_rows_for_c2_run": count_outbox_rows(cur, c2_run_id),
        "inbox_rows_for_c2_run": count_inbox_rows(cur, c2_run_id),
        "checkpoint_rows_for_c2_run": count_checkpoint_rows(cur, c2_run_id),
    }


def market_data_run_exists(cur: Any, run_id: str) -> bool:
    cur.execute("SELECT 1 FROM common_market_data_run WHERE run_id = %s LIMIT 1", (run_id,))
    return cur.fetchone() is not None


def count_rows_by_run(cur: Any, table_name: str, run_id: str) -> int:
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def count_outbox_rows(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_outbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def count_inbox_rows(cur: Any, run_id: str) -> int:
    cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_inbox WHERE source_run_id = %s", (run_id,))
    return int(cur.fetchone()["row_count"])


def count_checkpoint_rows(cur: Any, run_id: str) -> int:
    cur.execute(
        "SELECT count(*)::bigint AS row_count FROM common_event_consumer_checkpoint WHERE checkpoint_payload::TEXT LIKE %s",
        (f"%{run_id}%",),
    )
    return int(cur.fetchone()["row_count"])


def count_objects_by_asset(subscriptions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    grouped: dict[str, set[str]] = {asset_kind: set() for asset_kind in ASSET_KINDS}
    for row in subscriptions:
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind in grouped:
            grouped[asset_kind].add(str(row.get("identity_key") or ""))
    return {asset_kind: len(grouped[asset_kind]) for asset_kind in ASSET_KINDS}


def count_missing_candidates_by_asset(
    subscriptions: Sequence[Mapping[str, Any]],
    baseline_counts_by_identity: Mapping[str, int],
) -> dict[str, int]:
    counts = {asset_kind: 0 for asset_kind in ASSET_KINDS}
    for row in subscriptions:
        identity_key = str(row.get("identity_key") or "")
        if int(baseline_counts_by_identity.get(identity_key) or 0) == 0:
            asset_kind = str(row.get("asset_kind") or "")
            if asset_kind in counts:
                counts[asset_kind] += 1
    return counts


def latest_label_from_baseline(baseline: Mapping[str, Mapping[str, Any]]) -> str:
    max_times = [
        row.get("max_bar_time")
        for row in baseline.values()
        if row.get("max_bar_time") is not None
    ]
    if not max_times:
        return ""
    latest = max(max_times)
    if isinstance(latest, datetime):
        return latest.astimezone(ASIA_SHANGHAI).strftime("%H:%M")
    return str(latest)[11:16]


def stringify_dt(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(ASIA_SHANGHAI).isoformat()
    return str(value)


def load_json_file(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_report_files(report: Mapping[str, Any], *, markdown_path: str, json_path: str) -> None:
    markdown = Path(markdown_path)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(format_markdown_report(report), encoding="utf-8")
    json_report = Path(json_path)
    json_report.parent.mkdir(parents=True, exist_ok=True)
    json_report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def format_summary(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    delta_plan = report.get("delta_plan") or {}
    summary_plan = report.get("closed_30m_summary_plan") or {}
    return "\n".join(
        [
            "closed 30m replay dry-run",
            f"  result={report.get('result')}",
            f"  c2_run_id={report.get('c2_run_id')}",
            f"  for_trade_date={report.get('for_trade_date')}",
            f"  object_counts={report.get('object_counts_by_asset')}",
            f"  baseline_rows={report.get('baseline_rows_by_asset')}",
            f"  delta_minute_rows_estimate={delta_plan.get('delta_minute_rows_estimate')}",
            f"  summary_status_counts={summary_plan.get('status_counts')}",
            f"  p0_count={quality.get('p0_count')} p1_count={quality.get('p1_count')} p2_count={quality.get('p2_count')}",
            "  writes_performed=false market_data_pulled=false event_outbox_written=false worker_started=false",
        ]
    )


def format_markdown_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    summary_plan = report.get("closed_30m_summary_plan") or {}
    delta_plan = report.get("delta_plan") or {}
    lines = [
        "# N3-C2 Closed 30m Replay Dry-Run Report",
        "",
        "## Summary",
        "",
        f"- result: `{report.get('result')}`",
        f"- layer_role: `{report.get('layer_role')}`",
        f"- c2_run_id: `{report.get('c2_run_id')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- latest_closed_label: `{report.get('latest_closed_label')}`",
        f"- object_counts: `{report.get('object_counts_by_asset')}`",
        f"- baseline_rows: `{report.get('baseline_rows_by_asset')}`",
        f"- delta_minute_rows_estimate: `{delta_plan.get('delta_minute_rows_estimate')}`",
        f"- expected_summary_rows: `{(summary_plan.get('expected_summary_rows') or {}).get('total')}`",
        f"- summary_status_counts: `{summary_plan.get('status_counts')}`",
        f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
        "",
        "## Boundary",
        "",
        "- market_data_pulled: `false`",
        "- minute_delta_written: `false`",
        "- closed_summary_written: `false`",
        "- quality_written: `false`",
        "- event_outbox_written: `false`",
        "- outbox_consumed: `false`",
        "- inbox_or_checkpoint_written: `false`",
        "- downstream_layers_touched: `false`",
        "- worker_started: `false`",
        "",
        "## Replay Plan",
        "",
        f"- full_day_minute_labels_per_object: `{(report.get('replay_plan') or {}).get('full_day_minute_labels_per_object')}`",
        f"- main_gap: `{delta_plan.get('main_gap')}`",
        f"- BJ retry capacity: `{delta_plan.get('bj_retry_capacity')}`",
        "- replay_diff_check_required: `true`",
        "",
        "## Write Scope",
        "",
        "Allowed future execute writes:",
        "",
        "```text",
        "\n".join((report.get("write_scope_contract") or {}).get("allowed_write_tables") or []),
        "```",
        "",
        "Forbidden:",
        "",
        "```text",
        "\n".join((report.get("write_scope_contract") or {}).get("forbidden_write_tables") or []),
        "```",
        "",
        "## Next Step",
        "",
        f"- next_allowed_step: `{report.get('next_allowed_step')}`",
        "- C2 execute remains forbidden until a separate execute runner, preflight, rollback review, and explicit user confirmation.",
        "",
    ]
    return "\n".join(lines)
