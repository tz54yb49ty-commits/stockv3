"""N3-C2B closed signal enrichment dry-run planner.

This module reads C2 closed 30m summaries and previous-day minute facts to
plan standardized closed signal enrichment rows. It never writes enrichment
facts, quality rows, outbox/inbox/checkpoint rows, downstream runtime state, or
starts workers.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import json
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.closed_30m_replay_plan import ASSET_KINDS, BUCKET_SPECS


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_DRY_RUN_PLAN_PATH = "docs/N3_C2B_closed_signal_enrichment_dry_run_plan.json"
DEFAULT_EXECUTE_CONTRACT_PATH = "docs/N3_C2B_closed_signal_enrichment_execute_contract.json"
DEFAULT_C2_REPORT_PATH = "docs/N3_C2_closed_30m_replay_execute_report.json"
DEFAULT_N4_C3_REPLAY_REPORT_PATH = "docs/N4_C3_replay_dry_run_report.json"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N3_C2B_closed_signal_enrichment_business_rollback.sql"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/N3_C2B_CLOSED_SIGNAL_ENRICHMENT_DRY_RUN_REPORT.md"
DEFAULT_JSON_REPORT_PATH = "docs/N3_C2B_closed_signal_enrichment_dry_run_report.json"

IDENTITY_COLUMNS = {
    "stock": "stock_identity_key",
    "index": "index_identity_key",
    "board": "board_identity_key",
}
MINUTE_TABLES = {
    "stock": "stock_minute_bar_1m",
    "index": "index_minute_bar_1m",
    "board": "board_minute_bar_1m",
}
SUMMARY_TABLES = {
    "stock": "stock_closed_30m_summary",
    "index": "index_closed_30m_summary",
    "board": "board_closed_30m_summary",
}
ENRICHMENT_TABLES = {
    "stock": "stock_closed_30m_signal_enrichment",
    "index": "index_closed_30m_signal_enrichment",
    "board": "board_closed_30m_signal_enrichment",
}

SCHEMA_VERSION = "n3.closed_signal_enrichment.v1"
PRICE_FLAT_ABS_THRESHOLD = Decimal("0.0010")
AMOUNT_EXPANDING_THRESHOLD = Decimal("1.20")
AMOUNT_SHRINKING_THRESHOLD = Decimal("0.80")
CALCULATION_CONFIG_HASH_SOURCE = (
    "n3.closed_signal_enrichment.v1|price_flat_abs_threshold=0.0010|"
    "amount_expanding_threshold=1.20|amount_shrinking_threshold=0.80|bucket_schema=8x30m"
)
CALCULATION_CONFIG_HASH = hashlib.sha256(CALCULATION_CONFIG_HASH_SOURCE.encode("utf-8")).hexdigest()

ALLOWED_FUTURE_EXECUTE_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_closed_30m_signal_enrichment",
    "index_closed_30m_signal_enrichment",
    "board_closed_30m_signal_enrichment",
]
FORBIDDEN_WRITE_TABLES = [
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "N4/N5/N6",
    "worker",
    "old system",
]


def bucket_id_for_label(label: str) -> str | None:
    normalized = str(label or "").strip()
    for bucket_id, start, end in BUCKET_SPECS:
        if start.strftime("%H:%M") <= normalized <= end.strftime("%H:%M"):
            return bucket_id
    return None


def build_baseline_buckets(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        identity_key = str(row.get("identity_key") or "")
        label = str(row.get("bar_time_label") or label_from_bar_time(row.get("bar_time")) or "")
        bucket_id = bucket_id_for_label(label)
        if not identity_key or not bucket_id:
            continue
        grouped.setdefault((identity_key, bucket_id), []).append(row)

    baseline: dict[tuple[str, str], dict[str, Any]] = {}
    for key, bucket_rows in grouped.items():
        amount = sum((decimal_or_none(row.get("amount")) or Decimal("0")) for row in bucket_rows)
        baseline[key] = {
            "identity_key": key[0],
            "bucket_id": key[1],
            "baseline_window_amount": amount,
            "baseline_minute_count": len(bucket_rows),
            "baseline_window_open": decimal_or_none(bucket_rows[0].get("open")),
            "baseline_window_close": decimal_or_none(bucket_rows[-1].get("close")),
            "baseline_minute_bar_ids": [
                int(row["bar_id"]) for row in bucket_rows if row.get("bar_id") is not None
            ],
        }
    return baseline


def calculate_enrichment_candidate(
    summary: Mapping[str, Any],
    baseline: Mapping[str, Any] | None,
    *,
    c2b_run_id: str,
    source_previous_day_minute_run_id: str,
    previous_day_minute_date: str,
) -> dict[str, Any]:
    asset_kind = str(summary.get("asset_kind") or "")
    identity_key = str(summary.get("identity_key") or summary.get(f"{asset_kind}_identity_key") or "")
    current_amount = decimal_or_none(summary.get("amount"))
    current_open = decimal_or_none(summary.get("open"))
    current_close = decimal_or_none(summary.get("close"))
    closed_status = str(summary.get("closed_status") or "")
    baseline_amount = decimal_or_none((baseline or {}).get("baseline_window_amount"))
    baseline_count = int((baseline or {}).get("baseline_minute_count") or 0)

    price_change_pct = None
    price_direction = "unknown"
    if current_open is not None and current_close is not None and current_open != 0:
        price_change_pct = (current_close / current_open) - Decimal("1")
        price_direction = classify_price_direction(price_change_pct)

    amount_ratio = None
    amount_shape = "unknown"
    if current_amount is not None and baseline_amount is not None and baseline_amount > 0:
        amount_ratio = current_amount / baseline_amount
        amount_shape = classify_amount_shape(amount_ratio)

    if closed_status == "missing":
        quality_status = "missing"
        signal_status = "unknown"
    elif closed_status == "partial":
        quality_status = "warning"
        signal_status = "unknown"
    elif closed_status == "failed":
        quality_status = "failed"
        signal_status = "unknown"
    elif amount_shape == "unknown" or price_direction == "unknown":
        quality_status = "warning"
        signal_status = "unknown"
    else:
        quality_status = "passed"
        signal_status = map_signal_status(price_direction, amount_shape)

    baseline_status = "passed" if baseline_amount is not None and baseline_amount > 0 and baseline_count > 0 else "missing"
    if closed_status == "closed" and baseline_status != "passed":
        quality_status = "warning"
        signal_status = "unknown"

    basis_json = {
        "schema_version": SCHEMA_VERSION,
        "price_flat_abs_threshold": str(PRICE_FLAT_ABS_THRESHOLD),
        "amount_expanding_threshold": str(AMOUNT_EXPANDING_THRESHOLD),
        "amount_shrinking_threshold": str(AMOUNT_SHRINKING_THRESHOLD),
        "current_open": decimal_to_json(current_open),
        "current_close": decimal_to_json(current_close),
        "current_amount": decimal_to_json(current_amount),
        "baseline_amount": decimal_to_json(baseline_amount),
        "baseline_minute_count": baseline_count,
        "current_summary_status": closed_status,
        "baseline_status": baseline_status,
    }
    baseline_trace_json = {
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "previous_day_minute_date": previous_day_minute_date,
        "baseline_bucket_id": summary.get("bucket_id"),
        "baseline_bucket_start": None,
        "baseline_bucket_end": None,
        "baseline_minute_bar_ids": list((baseline or {}).get("baseline_minute_bar_ids") or []),
        "baseline_minute_count": baseline_count,
        "baseline_amount": decimal_to_json(baseline_amount),
    }

    return {
        "c2b_run_id": c2b_run_id,
        "c2_run_id": summary.get("run_id"),
        "current_summary_id": summary.get("summary_id"),
        "source_condition_run_id": summary.get("source_condition_run_id"),
        "source_subscription_run_id": summary.get("source_subscription_run_id"),
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "for_trade_date": summary.get("for_trade_date"),
        "trade_date": summary.get("trade_date"),
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "exchange": summary.get("exchange"),
        "code": summary.get("code"),
        "display_code": summary.get("display_code"),
        "name": summary.get("name"),
        "bucket_id": summary.get("bucket_id"),
        "bucket_start": stringify_value(summary.get("bucket_start")),
        "bucket_end": stringify_value(summary.get("bucket_end")),
        "current_window_amount": current_amount,
        "baseline_window_amount": baseline_amount,
        "closed_amount_ratio": amount_ratio,
        "closed_price_change_pct": price_change_pct,
        "closed_price_direction_status": price_direction,
        "closed_market_shape_status": signal_status,
        "closed_signal_status": signal_status,
        "closed_signal_quality_status": quality_status,
        "closed_signal_basis_json": basis_json,
        "baseline_trace_json": baseline_trace_json,
        "calculation_config_hash": CALCULATION_CONFIG_HASH,
        "raw_json": {
            "source_summary_closed_status": closed_status,
            "source_summary_quality_status": summary.get("quality_status"),
            "do_not_fabricate_signal": True,
        },
    }


def classify_price_direction(price_change_pct: Decimal | None) -> str:
    if price_change_pct is None:
        return "unknown"
    if abs(price_change_pct) <= PRICE_FLAT_ABS_THRESHOLD:
        return "flat"
    if price_change_pct > 0:
        return "up"
    return "down"


def classify_amount_shape(amount_ratio: Decimal | None) -> str:
    if amount_ratio is None:
        return "unknown"
    if amount_ratio >= AMOUNT_EXPANDING_THRESHOLD:
        return "volume_expanding"
    if amount_ratio <= AMOUNT_SHRINKING_THRESHOLD:
        return "volume_shrinking"
    return "volume_flat"


def map_signal_status(price_direction: str, amount_shape: str) -> str:
    if price_direction == "flat":
        return "flat"
    if price_direction in {"up", "down"} and amount_shape in {"volume_expanding", "volume_flat", "volume_shrinking"}:
        return f"{price_direction}_{amount_shape}"
    return "unknown"


def build_write_scope_contract() -> dict[str, Any]:
    return {
        "allowed_future_execute_write_tables": list(ALLOWED_FUTURE_EXECUTE_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "updates_closed_30m_summary": False,
        "updates_minute_bar_1m": False,
        "updates_realtime_projection_metric": False,
        "updates_realtime_daily_snapshot": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }


def build_closed_signal_dry_run_report(
    *,
    c2b_run_id: str,
    c2_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_previous_day_minute_run_id: str,
    for_trade_date: str,
    previous_day_minute_date: str,
    expected_rows: Mapping[str, int],
    candidates_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    target_audit: Mapping[str, Any],
    n4_replay_source: Mapping[str, Any],
    source_evidence: Mapping[str, Any] | None = None,
    source_run_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row_counts = {asset_kind: len(candidates_by_asset.get(asset_kind) or []) for asset_kind in ASSET_KINDS}
    row_counts["total"] = sum(row_counts.values())
    expected = {asset_kind: int(expected_rows.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}
    expected["total"] = int(expected_rows.get("total") or sum(expected.values()))
    flat_candidates = [candidate for asset_kind in ASSET_KINDS for candidate in candidates_by_asset.get(asset_kind, [])]
    signal_distribution = dict(Counter(str(candidate.get("closed_signal_status") or "") for candidate in flat_candidates))
    price_direction_distribution = dict(
        Counter(str(candidate.get("closed_price_direction_status") or "") for candidate in flat_candidates)
    )
    quality_distribution = dict(
        Counter(str(candidate.get("closed_signal_quality_status") or "") for candidate in flat_candidates)
    )
    computable_rows = sum(
        1
        for candidate in flat_candidates
        if str(candidate.get("closed_signal_status") or "") != "unknown"
        and str(candidate.get("closed_signal_quality_status") or "") == "passed"
    )
    unknown_rows = sum(1 for candidate in flat_candidates if str(candidate.get("closed_signal_status") or "") == "unknown")
    missing_rows = sum(1 for candidate in flat_candidates if str(candidate.get("closed_signal_quality_status") or "") == "missing")
    baseline_missing_rows = sum(
        1
        for candidate in flat_candidates
        if (candidate.get("closed_signal_basis_json") or {}).get("baseline_status") != "passed"
    )
    quality_items = build_quality_items(
        c2b_run_id=c2b_run_id,
        expected_rows=expected,
        actual_rows=row_counts,
        unknown_rows=unknown_rows,
        missing_rows=missing_rows,
        baseline_missing_rows=baseline_missing_rows,
        target_audit=target_audit,
        source_evidence=source_evidence or {},
        source_run_status=source_run_status or {},
    )
    severity_counts = count_quality_severities(quality_items)
    blocked = severity_counts["P0"] > 0
    write_scope = build_write_scope_contract()
    c3_event_missing = int(n4_replay_source.get("c3_event_missing") or n4_replay_source.get("missing") or 0)
    status_missing_before = int(n4_replay_source.get("closed_signal_status_missing") or 0)
    return {
        "stage": "N3-C2B",
        "layer_role": "N3_market_data",
        "execution_mode": "closed_signal_enrichment_dry_run",
        "result": "DRY_RUN_BLOCKED" if blocked else "DRY_RUN_PASS",
        "blocked": blocked,
        "c2b_run_id": c2b_run_id,
        "c2_run_id": c2_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "for_trade_date": for_trade_date,
        "previous_day_minute_date": previous_day_minute_date,
        "expected_rows": expected,
        "current_summary_rows": row_counts,
        "baseline_bucket_rows": {
            "total": computable_rows + baseline_missing_rows,
            "baseline_missing_rows": baseline_missing_rows,
        },
        "computable_rows": computable_rows,
        "unknown_rows": unknown_rows,
        "missing_rows": missing_rows,
        "baseline_missing_rows": baseline_missing_rows,
        "signal_distribution": signal_distribution,
        "price_direction_distribution": price_direction_distribution,
        "quality_distribution": quality_distribution,
        "candidate_preview": [json_safe(candidate) for candidate in flat_candidates[:20]],
        "write_scope_contract": write_scope,
        "target_audit": dict(target_audit),
        "source_evidence": dict(source_evidence or {}),
        "source_run_status": dict(source_run_status or {}),
        "n4_replay_unblock_estimate": {
            "closed_signal_status_missing_before_c2b": status_missing_before,
            "closed_signal_status_missing_after_c2b": 0 if not blocked else status_missing_before,
            "c3_event_missing_remains": c3_event_missing,
            "n4_replay_execute_authorized": False,
            "note": "C2B only writes N3 enrichment facts in a future execute; it does not replay N4 or consume C3 outbox.",
        },
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
            "enrichment_rows_written": False,
            "quality_written": False,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "inbox_or_checkpoint_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "next_allowed_step": "N3-C2B dry-run review" if not blocked else "fix P0 blockers before C2B review",
    }


def build_quality_items(
    *,
    c2b_run_id: str,
    expected_rows: Mapping[str, int],
    actual_rows: Mapping[str, int],
    unknown_rows: int,
    missing_rows: int,
    baseline_missing_rows: int,
    target_audit: Mapping[str, Any],
    source_evidence: Mapping[str, Any],
    source_run_status: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not c2b_run_id:
        items.append(quality_item("P0", "failed", "n3_c2b_run_id_present", "C2B run id is present"))
    for run_name, status in source_run_status.items():
        if status != "passed":
            items.append(
                quality_item(
                    "P0",
                    "failed",
                    f"n3_c2b_source_run_{run_name}_passed",
                    f"source run {run_name} must be passed",
                    expected="passed",
                    actual=str(status),
                )
            )
    if actual_rows.get("total") != expected_rows.get("total"):
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c2b_expected_rows_match_c2_summary",
                "enrichment candidate count must match C2 summary rows",
                expected=str(expected_rows.get("total")),
                actual=str(actual_rows.get("total")),
            )
        )
    if int(target_audit.get("run_exists") or 0):
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c2b_run_id_not_reused",
                "C2B run id must not already exist",
                expected="absent",
                actual="present",
            )
        )
    counts = target_audit.get("enrichment_rows_for_c2b_run") or {}
    if sum(int(counts.get(asset_kind) or 0) for asset_kind in ASSET_KINDS):
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c2b_enrichment_rows_zero",
                "C2B enrichment target rows must be zero before execute",
                expected="0",
                actual=str(counts),
            )
        )
    for name in ("quality_rows_for_c2b_run", "outbox_rows_for_c2b_run", "inbox_rows_for_c2b_run", "checkpoint_rows_for_c2b_run"):
        if int(target_audit.get(name) or 0):
            items.append(
                quality_item(
                    "P0",
                    "failed",
                    f"n3_c2b_{name}_zero",
                    f"{name} must be zero before execute",
                    expected="0",
                    actual=str(target_audit.get(name)),
                )
            )
    if not source_evidence.get("rollback_sql_exists", True):
        items.append(
            quality_item(
                "P0",
                "failed",
                "n3_c2b_rollback_sql_exists",
                "C2B business rollback SQL exists",
                expected="true",
                actual="false",
            )
        )
    if unknown_rows:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_c2b_unknown_signal_rows_visible",
                "unknown closed signal rows remain explicit",
                expected="0 unknown rows",
                actual=str(unknown_rows),
            )
        )
    if missing_rows:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_c2b_missing_current_rows_visible",
                "missing current summary rows remain explicit",
                expected="0 missing rows",
                actual=str(missing_rows),
            )
        )
    if baseline_missing_rows:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_c2b_baseline_missing_rows_visible",
                "baseline missing/zero rows are unknown and must not be inferred by N4",
                expected="0 baseline missing rows",
                actual=str(baseline_missing_rows),
            )
        )
    if not items:
        items.append(
            quality_item(
                "P2",
                "passed",
                "n3_c2b_dry_run_ready",
                "C2B dry-run plan is ready for review",
                expected="ready",
                actual="ready",
            )
        )
    return items


def build_closed_signal_enrichment_dry_run(
    *,
    dsn: str,
    dry_run_plan_path: str = DEFAULT_DRY_RUN_PLAN_PATH,
    execute_contract_path: str = DEFAULT_EXECUTE_CONTRACT_PATH,
    c2_report_path: str = DEFAULT_C2_REPORT_PATH,
    n4_replay_report_path: str = DEFAULT_N4_C3_REPLAY_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    dry_run_plan = load_json_file(dry_run_plan_path)
    execute_contract = load_json_file(execute_contract_path)
    c2_report = load_json_file(c2_report_path)
    n4_replay_report = load_json_file(n4_replay_report_path)
    rollback_sql_exists = Path(rollback_sql_path).exists()

    c2b_run_id = str(execute_contract.get("c2b_run_id") or dry_run_plan.get("c2b_run_id") or "")
    lineage = execute_contract.get("lineage") or dry_run_plan.get("lineage") or {}
    expected_rows = execute_contract.get("expected_enrichment_rows") or dry_run_plan.get("expected_enrichment_rows") or {}
    runtime = fetch_runtime_context(
        dsn=dsn,
        c2b_run_id=c2b_run_id,
        c2_run_id=str(lineage.get("c2_run_id") or ""),
        source_previous_day_minute_run_id=str(lineage.get("source_previous_day_minute_run_id") or ""),
        previous_day_minute_date=str(lineage.get("previous_day_minute_date") or dry_run_plan.get("previous_day_minute_date") or ""),
    )
    candidates_by_asset: dict[str, list[dict[str, Any]]] = {asset_kind: [] for asset_kind in ASSET_KINDS}
    for asset_kind in ASSET_KINDS:
        baselines = runtime["baseline_buckets_by_asset"].get(asset_kind, {})
        for summary in runtime["summary_rows_by_asset"].get(asset_kind, []):
            identity_key = str(summary.get("identity_key") or "")
            bucket_id = str(summary.get("bucket_id") or "")
            candidate = calculate_enrichment_candidate(
                summary,
                baselines.get((identity_key, bucket_id)),
                c2b_run_id=c2b_run_id,
                source_previous_day_minute_run_id=str(lineage.get("source_previous_day_minute_run_id") or ""),
                previous_day_minute_date=str(lineage.get("previous_day_minute_date") or dry_run_plan.get("previous_day_minute_date") or ""),
            )
            candidates_by_asset[asset_kind].append(candidate)

    reason_summary = n4_replay_report.get("reason_summary") or {}
    n4_source = {
        "closed_signal_status_missing": int(reason_summary.get("closed_signal_status_missing") or 0),
        "c3_event_missing": int(reason_summary.get("c3_event_missing") or n4_replay_report.get("classification_summary", {}).get("by_classification", {}).get("missing") or 0),
    }
    return build_closed_signal_dry_run_report(
        c2b_run_id=c2b_run_id,
        c2_run_id=str(lineage.get("c2_run_id") or c2_report.get("c2_run_id") or ""),
        source_condition_run_id=str(lineage.get("source_condition_run_id") or c2_report.get("source_condition_run_id") or ""),
        source_subscription_run_id=str(lineage.get("source_subscription_run_id") or c2_report.get("source_subscription_run_id") or ""),
        source_previous_day_minute_run_id=str(lineage.get("source_previous_day_minute_run_id") or ""),
        for_trade_date=str(execute_contract.get("for_trade_date") or dry_run_plan.get("for_trade_date") or ""),
        previous_day_minute_date=str(lineage.get("previous_day_minute_date") or dry_run_plan.get("previous_day_minute_date") or ""),
        expected_rows=expected_rows,
        candidates_by_asset=candidates_by_asset,
        target_audit=runtime["target_audit"],
        n4_replay_source=n4_source,
        source_evidence={
            "dry_run_plan_path": dry_run_plan_path,
            "execute_contract_path": execute_contract_path,
            "c2_report_path": c2_report_path,
            "n4_replay_report_path": n4_replay_report_path,
            "rollback_sql_path": rollback_sql_path,
            "rollback_sql_exists": rollback_sql_exists,
            "schema_017_tables_exist": runtime["schema_017_tables_exist"],
        },
        source_run_status=runtime["source_run_status"],
    )


def fetch_runtime_context(
    *,
    dsn: str,
    c2b_run_id: str,
    c2_run_id: str,
    source_previous_day_minute_run_id: str,
    previous_day_minute_date: str,
) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        summary_rows_by_asset = {
            asset_kind: fetch_summary_rows(cur, asset_kind, c2_run_id) for asset_kind in ASSET_KINDS
        }
        baseline_buckets_by_asset = {
            asset_kind: fetch_baseline_buckets(cur, asset_kind, source_previous_day_minute_run_id, previous_day_minute_date)
            for asset_kind in ASSET_KINDS
        }
        target_audit = fetch_target_audit(cur, c2b_run_id)
        source_run_status = fetch_source_run_status(
            cur,
            {
                "c2_run": c2_run_id,
                "previous_day_minute_run": source_previous_day_minute_run_id,
            },
        )
        schema_017_tables_exist = {
            asset_kind: table_exists(cur, ENRICHMENT_TABLES[asset_kind]) for asset_kind in ASSET_KINDS
        }
    return {
        "summary_rows_by_asset": summary_rows_by_asset,
        "baseline_buckets_by_asset": baseline_buckets_by_asset,
        "target_audit": target_audit,
        "source_run_status": source_run_status,
        "schema_017_tables_exist": schema_017_tables_exist,
    }


def fetch_summary_rows(cur: Any, asset_kind: str, c2_run_id: str) -> list[dict[str, Any]]:
    table = SUMMARY_TABLES[asset_kind]
    identity_column = IDENTITY_COLUMNS[asset_kind]
    cur.execute(
        f"""
        SELECT summary_id, run_id, source_condition_run_id, source_subscription_run_id,
               source_today_minute_run_ids, for_trade_date, trade_date, asset_kind,
               {identity_column} AS identity_key, exchange, code, display_code, name,
               bucket_id, bucket_start, bucket_end, open, high, low, close, volume,
               amount, closed_status, quality_status, source_minute_bar_ids,
               replay_diff_json, raw_json
        FROM {table}
        WHERE run_id = %s
        ORDER BY {identity_column}, bucket_id
        """,
        (c2_run_id,),
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_baseline_buckets(cur: Any, asset_kind: str, run_id: str, trade_date: str) -> dict[tuple[str, str], dict[str, Any]]:
    table = MINUTE_TABLES[asset_kind]
    identity_column = IDENTITY_COLUMNS[asset_kind]
    case_sql = bucket_case_sql()
    cur.execute(
        f"""
        WITH labeled AS (
          SELECT bar_id, {identity_column} AS identity_key, bar_time, open, close, amount,
                 to_char(bar_time AT TIME ZONE 'Asia/Shanghai', 'HH24:MI') AS label
          FROM {table}
          WHERE run_id = %s
            AND trade_date = %s
            AND is_previous_day_preload = true
        ),
        bucketed AS (
          SELECT *, {case_sql} AS bucket_id
          FROM labeled
        )
        SELECT identity_key, bucket_id,
               count(*)::int AS baseline_minute_count,
               sum(amount) AS baseline_window_amount,
               (array_agg(open ORDER BY bar_time))[1] AS baseline_window_open,
               (array_agg(close ORDER BY bar_time DESC))[1] AS baseline_window_close,
               array_agg(bar_id ORDER BY bar_time) AS baseline_minute_bar_ids
        FROM bucketed
        WHERE bucket_id IS NOT NULL
        GROUP BY identity_key, bucket_id
        """,
        (run_id, trade_date),
    )
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for row in cur.fetchall():
        item = dict(row)
        output[(str(item["identity_key"]), str(item["bucket_id"]))] = item
    return output


def bucket_case_sql() -> str:
    parts = ["CASE"]
    for bucket_id, start, end in BUCKET_SPECS:
        parts.append(f"WHEN label BETWEEN '{start:%H:%M}' AND '{end:%H:%M}' THEN '{bucket_id}'")
    parts.append("ELSE NULL END")
    return " ".join(parts)


def fetch_target_audit(cur: Any, c2b_run_id: str) -> dict[str, Any]:
    enrichment_counts = {}
    for asset_kind in ASSET_KINDS:
        table = ENRICHMENT_TABLES[asset_kind]
        if table_exists(cur, table):
            cur.execute(f"SELECT count(*) AS n FROM {table} WHERE c2b_run_id = %s", (c2b_run_id,))
            enrichment_counts[asset_kind] = int(cur.fetchone()["n"])
        else:
            enrichment_counts[asset_kind] = -1
    cur.execute("SELECT count(*) AS n FROM common_market_data_run WHERE run_id = %s", (c2b_run_id,))
    run_exists = int(cur.fetchone()["n"]) > 0
    cur.execute("SELECT count(*) AS n FROM common_market_data_quality_item WHERE run_id = %s", (c2b_run_id,))
    quality_rows = int(cur.fetchone()["n"])
    cur.execute("SELECT count(*) AS n FROM common_event_outbox WHERE source_run_id = %s", (c2b_run_id,))
    outbox_rows = int(cur.fetchone()["n"])
    cur.execute("SELECT count(*) AS n FROM common_event_inbox WHERE source_run_id = %s", (c2b_run_id,))
    inbox_rows = int(cur.fetchone()["n"])
    cur.execute(
        "SELECT count(*) AS n FROM common_event_consumer_checkpoint WHERE position(%s in checkpoint_payload::TEXT) > 0",
        (c2b_run_id,),
    )
    checkpoint_rows = int(cur.fetchone()["n"])
    return {
        "run_exists": run_exists,
        "enrichment_rows_for_c2b_run": enrichment_counts,
        "quality_rows_for_c2b_run": quality_rows,
        "outbox_rows_for_c2b_run": outbox_rows,
        "inbox_rows_for_c2b_run": inbox_rows,
        "checkpoint_rows_for_c2b_run": checkpoint_rows,
    }


def fetch_source_run_status(cur: Any, named_runs: Mapping[str, str]) -> dict[str, str]:
    output: dict[str, str] = {}
    for name, run_id in named_runs.items():
        if not run_id:
            output[name] = "missing"
            continue
        cur.execute("SELECT status FROM common_market_data_run WHERE run_id = %s", (run_id,))
        row = cur.fetchone()
        output[name] = str(row["status"]) if row else "missing"
    return output


def table_exists(cur: Any, table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS rel", (f"public.{table_name}",))
    return cur.fetchone()["rel"] is not None


def load_json_file(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def write_report_files(report: Mapping[str, Any], *, markdown_path: str, json_path: str) -> None:
    Path(json_path).write_text(json.dumps(json_safe(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    Path(markdown_path).write_text(format_markdown_report(report))


def format_markdown_report(report: Mapping[str, Any]) -> str:
    quality = report.get("quality") or {}
    return "\n".join(
        [
            "# N3-C2B Closed Signal Enrichment Dry-Run Report",
            "",
            f"- result: `{report.get('result')}`",
            f"- layer_role: `{report.get('layer_role')}`",
            f"- c2b_run_id: `{report.get('c2b_run_id')}`",
            f"- c2_run_id: `{report.get('c2_run_id')}`",
            f"- expected_rows: `{report.get('expected_rows')}`",
            f"- current_summary_rows: `{report.get('current_summary_rows')}`",
            f"- computable_rows: `{report.get('computable_rows')}`",
            f"- unknown_rows: `{report.get('unknown_rows')}`",
            f"- missing_rows: `{report.get('missing_rows')}`",
            f"- baseline_missing_rows: `{report.get('baseline_missing_rows')}`",
            f"- signal_distribution: `{report.get('signal_distribution')}`",
            f"- price_direction_distribution: `{report.get('price_direction_distribution')}`",
            f"- quality_distribution: `{report.get('quality_distribution')}`",
            f"- P0/P1/P2: `{quality.get('p0_count')}/{quality.get('p1_count')}/{quality.get('p2_count')}`",
            "",
            "## N4 Replay Unblock Estimate",
            "",
            f"- before: `{(report.get('n4_replay_unblock_estimate') or {}).get('closed_signal_status_missing_before_c2b')}`",
            f"- after: `{(report.get('n4_replay_unblock_estimate') or {}).get('closed_signal_status_missing_after_c2b')}`",
            f"- c3_event_missing_remains: `{(report.get('n4_replay_unblock_estimate') or {}).get('c3_event_missing_remains')}`",
            "",
            "## Boundary",
            "",
            f"- side_effects: `{report.get('side_effects')}`",
            f"- write_scope_contract: `{report.get('write_scope_contract')}`",
            "",
            "## Decision",
            "",
            f"`{report.get('result')}`.",
            "",
        ]
    )


def format_summary(report: Mapping[str, Any]) -> str:
    return (
        f"{report.get('result')} c2b_run_id={report.get('c2b_run_id')} "
        f"rows={report.get('current_summary_rows')} "
        f"signal_distribution={report.get('signal_distribution')} "
        f"P0/P1/P2={report.get('quality', {}).get('p0_count')}/"
        f"{report.get('quality', {}).get('p1_count')}/{report.get('quality', {}).get('p2_count')}"
    )


def label_from_bar_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value.astimezone(ASIA_SHANGHAI) if value.tzinfo else value
        return dt.strftime("%H:%M")
    text = str(value)
    if len(text) >= 5 and text[-5:-3].isdigit() and text[-2:].isdigit():
        return text[-5:]
    return None


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_to_json(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.normalize())


def stringify_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value
