"""N4 local trigger dry-run from trigger context and B1 snapshot facts.

This planner is scoped to the fact-only 20260528 gate: it reads local N4
context and N3 realtime snapshot facts, creates plan artifacts, and writes no
database rows or outbox/inbox/checkpoint state.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item
from ashare_v3.events.ids import stable_hash
from ashare_v3.trigger.canonical_signal import canonical_payload_errors, canonicalize_trigger_candidate
from ashare_v3.trigger.context_preflight import (
    ASSET_KINDS,
    TARGET_CONTEXT_TABLES,
    normalize_text_array,
    period_trigger_baseline_json_missing_count,
    required_period_not_ready_rows_count,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect
from ashare_v3.trigger.synthetic_dry_run import (
    HINT_SIGNAL_TYPES,
    ORDINARY_SIGNAL_BY_DIRECTION,
    THIRTY_MINUTE_SIGNAL_BY_DIRECTION,
    THIRTY_MINUTE_SIGNAL_TYPES,
    build_period_trigger_baseline_trace,
    derive_trigger_period,
    write_json,
    write_text,
)


DEFAULT_20260528_CONTEXT_RUN_ID = "trigger_context_snapshot_20260528_condition_layer_20260527_source_20260527_v1"
DEFAULT_20260528_SNAPSHOT_RUN_ID = (
    "realtime_snapshot_20260528_retry1_market_data_subscription_20260528_condition_layer_20260527_source_20260527_v1"
)
DEFAULT_20260528_JSON_REPORT_PATH = "docs/N4_20260528_local_trigger_dry_run_report.json"
DEFAULT_20260528_MD_REPORT_PATH = "docs/N4_20260528_LOCAL_TRIGGER_DRY_RUN_REPORT.md"
DEFAULT_20260528_ROLLBACK_SQL_PATH = "sql/N4_20260528_local_trigger_dry_run_rollback.sql"

SOURCE_EVENT_TYPE = "MarketSnapshotUpdated"
LOCAL_DRY_RUN_STAGE = "N4-20260528-local-trigger-dry-run"
DEPRECATED_RUNTIME_SIGNAL_TYPES = (
    "B_BUY_30M_VOL",
    "S_SELL_30M_SHRINK",
    "BUY_HINT",
    "SELL_HINT",
)
SNAPSHOT_TABLE_CONFIG = {
    "stock": ("stock_realtime_daily_snapshot", "stock_identity_key"),
    "index": ("index_realtime_daily_snapshot", "index_identity_key"),
    "board": ("board_realtime_daily_snapshot", "board_identity_key"),
}
ROW_COUNT_GUARD_TABLES = (
    "common_trigger_run",
    "common_trigger_quality_item",
    "stock_trigger_context_snapshot",
    "index_trigger_context_snapshot",
    "board_trigger_context_snapshot",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
)


def run_local_trigger_dry_run(
    *,
    dsn: str,
    trigger_context_run_id: str = DEFAULT_20260528_CONTEXT_RUN_ID,
    snapshot_run_id: str = DEFAULT_20260528_SNAPSHOT_RUN_ID,
    json_report_path: str = DEFAULT_20260528_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_20260528_MD_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_20260528_ROLLBACK_SQL_PATH,
    sample_limit: int = 80,
    stage: str = LOCAL_DRY_RUN_STAGE,
) -> dict[str, Any]:
    before_counts = capture_row_counts(dsn)
    trigger_run, context_rows = fetch_context_rows(dsn, trigger_context_run_id)
    snapshot_run, snapshot_rows = fetch_snapshot_rows(dsn, snapshot_run_id)
    scoped_event_refs = capture_scoped_event_refs(
        dsn,
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
    )
    after_counts = capture_row_counts(dsn)
    report = build_local_trigger_dry_run_report(
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
        trigger_run=trigger_run,
        snapshot_run=snapshot_run,
        context_rows=context_rows,
        snapshot_rows=snapshot_rows,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
        scoped_event_refs=scoped_event_refs,
        sample_limit=sample_limit,
        stage=stage,
    )
    rollback_sql = build_local_trigger_dry_run_rollback_sql(
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
    )
    report["rollback_sql_path"] = rollback_sql_path
    report["rollback_sql"] = rollback_sql
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_local_trigger_dry_run_report(report))
    write_text(rollback_sql_path, rollback_sql)
    return report


def fetch_context_rows(dsn: str, trigger_context_run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_local_trigger_dry_run_fetch_context",
        source_run_id=trigger_context_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, source_condition_run_id, source_market_data_run_id,
                   for_trade_date, source_trade_date, prev_trade_date,
                   mode, status, p0_count, p1_count, p2_count,
                   context_snapshot_row_count, trigger_state_row_count,
                   trigger_match_row_count, trigger_event_outbox_count, raw_json
            FROM common_trigger_run
            WHERE run_id = %s
            """,
            (trigger_context_run_id,),
        )
        trigger_run = normalize_mapping(cur.fetchone() or {})
        context_rows: list[dict[str, Any]] = []
        for asset_kind in ASSET_KINDS:
            table_name = TARGET_CONTEXT_TABLES[asset_kind]
            cur.execute(
                f"""
                SELECT trigger_context_id, run_id, source_condition_run_id,
                       source_condition_pool_id, source_condition_basis_id,
                       source_minute_target_scope_id, source_market_subscription_id,
                       for_trade_date, source_trade_date, prev_trade_date,
                       asset_kind, identity_key, exchange, code, name,
                       direction, condition_key, condition_periods,
                       allowed_signal_types, is_hint_scope, context_hash,
                       quality_status, raw_json
                FROM {table_name}
                WHERE run_id = %s
                ORDER BY identity_key, direction, condition_key, trigger_context_id
                """,
                (trigger_context_run_id,),
            )
            context_rows.extend(normalize_context_row(row) for row in cur.fetchall())
        return trigger_run, context_rows


def fetch_snapshot_rows(dsn: str, snapshot_run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_local_trigger_dry_run_fetch_snapshot",
        source_run_id=snapshot_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, source_condition_run_id, for_trade_date, source_trade_date,
                   prev_trade_date, mode, status, p0_count, p1_count, p2_count,
                   source_scope_row_count, candidate_row_count, subscription_row_count,
                   subscription_object_count, market_data_pulled, market_data_fact_written,
                   downstream_layers_touched, worker_started, raw_json
            FROM common_market_data_run
            WHERE run_id = %s
            """,
            (snapshot_run_id,),
        )
        snapshot_run = normalize_mapping(cur.fetchone() or {})
        snapshot_rows: list[dict[str, Any]] = []
        for asset_kind in ASSET_KINDS:
            table_name, identity_column = SNAPSHOT_TABLE_CONFIG[asset_kind]
            cur.execute(
                f"""
                SELECT snapshot_id, run_id AS snapshot_run_id, subscription_id,
                       source_condition_run_id, for_trade_date, trade_date,
                       snapshot_time, {identity_column} AS identity_key,
                       exchange, code, display_code, name, open, high, low,
                       close, current_price, pre_close, volume, amount,
                       source_adapter, source_version, quality_status,
                       source_scope_ids, source_condition_pool_ids, raw_json
                FROM {table_name}
                WHERE run_id = %s
                ORDER BY {identity_column}, snapshot_time DESC, snapshot_id DESC
                """,
                (snapshot_run_id,),
            )
            for row in cur.fetchall():
                normalized = normalize_mapping(row)
                normalized["asset_kind"] = asset_kind
                snapshot_rows.append(normalized)
        return snapshot_run, snapshot_rows


def normalize_context_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["condition_periods"] = normalize_text_array(output.get("condition_periods"))
    output["allowed_signal_types"] = normalize_text_array(output.get("allowed_signal_types"))
    raw_json = output.get("raw_json") or {}
    output["period_trigger_baseline_json"] = (
        raw_json.get("period_trigger_baseline_json") if isinstance(raw_json, Mapping) else {}
    ) or {}
    return output


def build_local_trigger_dry_run_report(
    *,
    trigger_context_run_id: str,
    snapshot_run_id: str,
    trigger_run: Mapping[str, Any],
    snapshot_run: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    snapshot_rows: Sequence[Mapping[str, Any]],
    before_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    scoped_event_refs: Mapping[str, int] | None = None,
    sample_limit: int = 80,
    stage: str = LOCAL_DRY_RUN_STAGE,
) -> dict[str, Any]:
    plans = build_local_trigger_plans(
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
        context_rows=context_rows,
        snapshot_rows=snapshot_rows,
    )
    state_change_plans = build_trigger_state_change_plans(plans)
    summary = summarize_local_trigger_plans(plans)
    baseline_missing_count = period_trigger_baseline_json_missing_count(context_rows)
    required_not_ready_count = required_period_not_ready_rows_count(context_rows)
    baseline_trace_count = sum(1 for plan in plans if plan.get("period_trigger_baseline_trace", {}).get("present"))
    snapshot_summary = summarize_snapshots(snapshot_rows)
    scoped_refs = dict(scoped_event_refs or {})
    upstream_input_refs = {
        key: int(scoped_refs.get(key) or 0)
        for key in (
            "upstream_input_outbox_allowed",
            "upstream_input_outbox_disallowed",
            "upstream_input_inbox_refs",
            "upstream_input_checkpoint_refs",
        )
    }
    target_output_refs = {
        key: int(scoped_refs.get(key) or 0)
        for key in (
            "target_output_outbox_refs",
            "target_inbox_refs",
            "target_checkpoint_refs",
            "target_trigger_match_refs",
            "target_trigger_state_refs",
        )
    }
    quality_items = build_quality_items(
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
        trigger_run=trigger_run,
        snapshot_run=snapshot_run,
        context_rows=context_rows,
        snapshot_rows=snapshot_rows,
        plans=plans,
        summary=summary,
        baseline_missing_count=baseline_missing_count,
        required_not_ready_count=required_not_ready_count,
        baseline_trace_count=baseline_trace_count,
        before_row_counts=before_row_counts,
        after_row_counts=after_row_counts,
        scoped_event_refs=scoped_refs,
    )
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": stage,
        "result": "DRY_RUN_PASS" if severity_counts["P0"] == 0 else "DRY_RUN_BLOCKED",
        "layer_role": "N4_trigger",
        "mode": "local_snapshot_trigger_dry_run",
        "trigger_context_run_id": trigger_context_run_id,
        "snapshot_run_id": snapshot_run_id,
        "source_condition_run_id": trigger_run.get("source_condition_run_id"),
        "source_market_data_run_id": trigger_run.get("source_market_data_run_id"),
        "for_trade_date": trigger_run.get("for_trade_date") or snapshot_run.get("for_trade_date"),
        "generated_at": utc_now_iso(),
        "context_source": {
            "read_local_trigger_context_snapshot": True,
            "external_n2_runtime_path_accessed": False,
            "context_row_count": len(context_rows),
            "context_row_count_by_asset_kind": count_context_by_asset(context_rows),
            "period_trigger_baseline_json_raw_json_path": "trigger_context_snapshot.raw_json.period_trigger_baseline_json",
            "period_trigger_baseline_json_missing": baseline_missing_count,
            "required_period_not_ready_rows": required_not_ready_count,
        },
        "snapshot_source": {
            "read_n3_realtime_daily_snapshot_facts": True,
            "snapshot_run_status": snapshot_run.get("status"),
            "snapshot_row_count": len(snapshot_rows),
            "snapshot_row_count_by_asset_kind": snapshot_summary["row_count_by_asset_kind"],
            "snapshot_object_count_by_asset_kind": snapshot_summary["object_count_by_asset_kind"],
            "snapshot_quality_status_distribution": snapshot_summary["quality_status_distribution"],
            "market_snapshot_outbox_consumed": False,
        },
        "period_trigger_baseline_json_missing": baseline_missing_count,
        "required_period_not_ready_rows": required_not_ready_count,
        "period_trigger_baseline_trace_count": baseline_trace_count,
        "context_candidate_count": len(context_rows),
        "candidate_count": summary["candidate_count"],
        "matched_plan_count": summary["matched_plan_count"],
        "pending_plan_count": summary["pending_plan_count"],
        "state_change_plan_count": summary["state_change_plan_count"],
        "abnormal_rows": {
            "missing_snapshot_context_rows": summary["missing_snapshot_context_rows"],
            "snapshot_quality_not_passed_plan_count": summary["snapshot_quality_not_passed_plan_count"],
            "period_trigger_baseline_json_missing": baseline_missing_count,
            "required_period_not_ready_rows": required_not_ready_count,
            "projection_not_available_pending_plan_count": summary["projection_not_available_pending_plan_count"],
        },
        "summary": summary,
        "scoped_event_refs": scoped_refs,
        "upstream_input_refs": upstream_input_refs,
        "target_output_refs": target_output_refs,
        "sample_plans": plans[:sample_limit],
        "sample_state_change_plans": state_change_plans[:sample_limit],
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "writes_performed": False,
            "common_event_outbox_consumed": False,
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "trigger_state_written": False,
            "trigger_match_written": False,
            "event_outbox_written": False,
            "market_data_pulled": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
            "external_n2_runtime_path_accessed": False,
        },
        "before_row_counts": before_row_counts or {},
        "after_row_counts": after_row_counts or {},
        "next_gate": {
            "allow_local_trigger_dry_run_review": severity_counts["P0"] == 0,
            "allow_n5_action": False,
            "allow_trigger_execute": False,
            "note": "This is a local fact-only dry-run artifact; N5 remains blocked until a separately authorized N4 execute writes standard outbox.",
        },
    }


def build_local_trigger_plans(
    *,
    trigger_context_run_id: str,
    snapshot_run_id: str,
    context_rows: Sequence[Mapping[str, Any]],
    snapshot_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    snapshot_lookup = latest_snapshot_by_identity(snapshot_rows, snapshot_run_id=snapshot_run_id)
    plans: list[dict[str, Any]] = []
    for row in context_rows:
        if row.get("run_id") != trigger_context_run_id:
            continue
        snapshot = snapshot_lookup.get((str(row.get("asset_kind") or ""), str(row.get("identity_key") or "")))
        plans.extend(build_ordinary_snapshot_plans(row, snapshot, snapshot_run_id))
        plans.extend(build_projection_pending_plans(row, snapshot, snapshot_run_id))
    return plans


def latest_snapshot_by_identity(
    snapshot_rows: Sequence[Mapping[str, Any]],
    *,
    snapshot_run_id: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for row in snapshot_rows:
        if row.get("snapshot_run_id") != snapshot_run_id:
            continue
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        if not key[0] or not key[1]:
            continue
        output.setdefault(key, dict(row))
    return output


def build_ordinary_snapshot_plans(
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None,
    snapshot_run_id: str,
) -> list[dict[str, Any]]:
    signal_type = ORDINARY_SIGNAL_BY_DIRECTION.get(str(row.get("direction") or ""))
    if not signal_type or signal_type not in normalize_text_array(row.get("allowed_signal_types")):
        return []
    if row.get("condition_key") in HINT_SIGNAL_TYPES:
        return []
    trigger_period = derive_trigger_period(row, signal_type)
    if snapshot is None:
        return [
            build_plan(
                row=row,
                snapshot={},
                snapshot_run_id=snapshot_run_id,
                signal_type=signal_type,
                output_event_type="TriggerPendingMarketData",
                plan_status="pending",
                trigger_period=trigger_period,
                data_quality_status="missing",
                pending_reason="snapshot_fact_missing",
                reason="N3 B1 snapshot fact is missing for this ordinary trigger candidate",
            )
        ]
    if snapshot.get("quality_status") != "passed":
        return [
            build_plan(
                row=row,
                snapshot=snapshot,
                snapshot_run_id=snapshot_run_id,
                signal_type=signal_type,
                output_event_type="TriggerPendingMarketData",
                plan_status="pending",
                trigger_period=trigger_period,
                data_quality_status=str(snapshot.get("quality_status") or "not_ready"),
                pending_reason="snapshot_quality_not_passed",
                reason="N3 B1 snapshot fact is present but not quality_status=passed",
            )
        ]
    match_result = evaluate_ordinary_snapshot_match(
        row=row,
        snapshot=snapshot,
        signal_type=signal_type,
        trigger_period=trigger_period,
    )
    if not match_result["matched"]:
        return [
            build_plan(
                row=row,
                snapshot=snapshot,
                snapshot_run_id=snapshot_run_id,
                signal_type=signal_type,
                output_event_type="TriggerPendingMarketData",
                plan_status="pending",
                trigger_period=trigger_period,
                data_quality_status=str(match_result["data_quality_status"]),
                pending_reason=str(match_result["pending_reason"]),
                reason=str(match_result["reason"]),
            )
        ]
    return [
        build_plan(
            row=row,
            snapshot=snapshot,
            snapshot_run_id=snapshot_run_id,
            signal_type=signal_type,
            output_event_type="TriggerMatched",
            plan_status="matched",
            trigger_period=trigger_period,
            data_quality_status="passed",
            pending_reason=None,
            reason=str(match_result["reason"]),
        )
    ]


def evaluate_ordinary_snapshot_match(
    *,
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    signal_type: str,
    trigger_period: str,
) -> dict[str, object]:
    period_baseline = period_baseline_for(row, trigger_period)
    if period_baseline is None:
        return pending_match_result(
            "period_trigger_baseline_missing",
            "missing",
            f"N2 localized period_trigger_baseline_json is missing for trigger_period={trigger_period}",
        )
    if period_baseline.get("baseline_ready") is not True:
        return pending_match_result(
            "period_trigger_baseline_not_ready",
            "not_ready",
            f"N2 localized period_trigger_baseline_json is not ready for trigger_period={trigger_period}",
        )
    price = decimal_or_none(snapshot.get("current_price")) or decimal_or_none(snapshot.get("close"))
    open_price = decimal_or_none(snapshot.get("open"))
    if price is None or open_price is None:
        return pending_match_result(
            "snapshot_price_direction_missing",
            "missing",
            "N3 B1 snapshot current_price/close/open is missing for ordinary BUY/SELL direction check",
        )
    amount = decimal_or_none(snapshot.get("amount"))
    baseline_amount = ordinary_amount_baseline(period_baseline)
    price_baseline = ordinary_price_baseline(period_baseline, signal_type)
    if amount is None or baseline_amount is None:
        return pending_match_result(
            "period_amount_baseline_missing",
            "missing",
            "N3 B1 snapshot amount or N2 localized previous amount baseline is missing",
        )
    if price_baseline is None:
        return pending_match_result(
            "period_entity_baseline_missing",
            "missing",
            "N2 localized trigger previous entity high/low baseline is missing",
        )
    direction = str(row.get("direction") or "")
    if signal_type == "B_BUY" and direction == "buy":
        if price <= open_price:
            return pending_match_result(
                "ordinary_snapshot_trigger_condition_not_met",
                "not_ready",
                "BUY ordinary trigger requires current_price/close > open; snapshot body is not rising",
            )
        if price <= price_baseline:
            return pending_match_result(
                "ordinary_snapshot_trigger_condition_not_met",
                "not_ready",
                "BUY ordinary trigger requires current_price/close > trigger_previous_entity_high",
            )
        if amount < baseline_amount:
            return pending_match_result(
                "ordinary_snapshot_trigger_condition_not_met",
                "not_ready",
                "BUY ordinary trigger requires snapshot amount >= trigger_previous_amount_baseline",
            )
        return {
            "matched": True,
            "data_quality_status": "passed",
            "pending_reason": None,
            "reason": "BUY ordinary trigger matched: snapshot body rising, price > trigger_previous_entity_high, and amount >= trigger_previous_amount_baseline",
        }
    if signal_type == "S_SELL" and direction == "sell":
        if price >= open_price:
            return pending_match_result(
                "ordinary_snapshot_trigger_condition_not_met",
                "not_ready",
                "SELL ordinary trigger requires current_price/close < open; snapshot body is not falling",
            )
        if price >= price_baseline:
            return pending_match_result(
                "ordinary_snapshot_trigger_condition_not_met",
                "not_ready",
                "SELL ordinary trigger requires current_price/close < trigger_previous_entity_low",
            )
        if amount > baseline_amount:
            return pending_match_result(
                "ordinary_snapshot_trigger_condition_not_met",
                "not_ready",
                "SELL ordinary trigger requires snapshot amount <= trigger_previous_amount_baseline",
            )
        return {
            "matched": True,
            "data_quality_status": "passed",
            "pending_reason": None,
            "reason": "SELL ordinary trigger matched: snapshot body falling, price < trigger_previous_entity_low, and amount <= trigger_previous_amount_baseline",
        }
    return pending_match_result(
        "ordinary_snapshot_signal_direction_mismatch",
        "not_ready",
        "Ordinary trigger signal_type does not match context direction",
    )


def period_baseline_for(row: Mapping[str, Any], trigger_period: str) -> Mapping[str, Any] | None:
    baseline = row.get("period_trigger_baseline_json")
    if not isinstance(baseline, Mapping):
        return None
    periods = baseline.get("periods")
    if not isinstance(periods, Mapping):
        return None
    period_baseline = periods.get(trigger_period)
    if not isinstance(period_baseline, Mapping):
        return None
    return period_baseline


def ordinary_amount_baseline(period_baseline: Mapping[str, Any]) -> Decimal | None:
    trigger_value = decimal_or_none(period_baseline.get("trigger_previous_amount_baseline"))
    if trigger_value is not None:
        return trigger_value
    amount_metric = str(period_baseline.get("amount_metric") or "amount")
    preferred_keys = (
        ("previous_avg_amount", "previous_amount", "previous_amount_baseline")
        if amount_metric in {"avg_amount", "average_amount", "previous_avg_amount"}
        else ("previous_amount", "previous_avg_amount", "previous_amount_baseline")
    )
    for key in preferred_keys:
        value = decimal_or_none(period_baseline.get(key))
        if value is not None:
            return value
    return None


def ordinary_price_baseline(period_baseline: Mapping[str, Any], signal_type: str) -> Decimal | None:
    if signal_type == "B_BUY":
        preferred_keys = ("trigger_previous_entity_high", "previous_entity_high")
    elif signal_type == "S_SELL":
        preferred_keys = ("trigger_previous_entity_low", "previous_entity_low")
    else:
        return None
    for key in preferred_keys:
        value = decimal_or_none(period_baseline.get(key))
        if value is not None:
            return value
    return None


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def pending_match_result(pending_reason: str, data_quality_status: str, reason: str) -> dict[str, object]:
    return {
        "matched": False,
        "data_quality_status": data_quality_status,
        "pending_reason": pending_reason,
        "reason": reason,
    }


def build_projection_pending_plans(
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None,
    snapshot_run_id: str,
) -> list[dict[str, Any]]:
    signal_type = projection_signal_type_for_context(row)
    if not signal_type:
        return []
    return [
        build_plan(
            row=row,
            snapshot=snapshot or {},
            snapshot_run_id=snapshot_run_id,
            signal_type=signal_type,
            output_event_type="TriggerPendingMarketData",
            plan_status="pending",
            trigger_period="30m",
            data_quality_status="not_ready",
            pending_reason="projection_fact_not_available_in_local_snapshot_dry_run",
            reason="B_BUY_30M_VOL / S_SELL_30M_SHRINK / BUY_HINT / SELL_HINT require N3 standardized realtime projection or closed confirmation; local B1 fact-only snapshot is trace input only",
        )
    ]


def projection_signal_type_for_context(row: Mapping[str, Any]) -> str | None:
    direction = str(row.get("direction") or "")
    condition_key = str(row.get("condition_key") or "")
    allowed = set(normalize_text_array(row.get("allowed_signal_types")))
    if condition_key == "BUY_HINT" and direction == "buy" and "BUY_HINT" in allowed:
        return "BUY_HINT"
    if condition_key == "SELL_HINT" and direction == "sell" and "SELL_HINT" in allowed:
        return "SELL_HINT"
    signal_type = THIRTY_MINUTE_SIGNAL_BY_DIRECTION.get(direction)
    if signal_type in allowed:
        return signal_type
    return None


def build_plan(
    *,
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    snapshot_run_id: str,
    signal_type: str,
    output_event_type: str,
    plan_status: str,
    trigger_period: str,
    data_quality_status: str,
    pending_reason: str | None,
    reason: str,
) -> dict[str, Any]:
    asset_kind = str(row.get("asset_kind") or "")
    identity_key = str(row.get("identity_key") or "")
    condition_key = str(row.get("condition_key") or "")
    legacy_signal_type = signal_type
    mapping = canonicalize_trigger_candidate(condition_key, candidate_signal_type=legacy_signal_type)
    canonical_signal_type = mapping.signal_type
    trigger_mark_candidate = mapping.trigger_mark_candidate
    direction = str(row.get("direction") or "")
    source_event_id = (
        str(snapshot.get("snapshot_event_id"))
        if snapshot.get("snapshot_event_id")
        else f"fact_only:{snapshot_run_id}:{asset_kind}:{identity_key}:{canonical_signal_type}:{trigger_mark_candidate}"
    )
    current_status = "matched" if output_event_type == "TriggerMatched" else "pending_market_data"
    trigger_live = output_event_type == "TriggerMatched"
    raw_id = "|".join(
        [
            snapshot_run_id,
            source_event_id,
            asset_kind,
            identity_key,
            direction,
            canonical_signal_type,
            trigger_mark_candidate,
            legacy_signal_type,
            condition_key,
            trigger_period,
            plan_status,
        ]
    )
    return {
        "plan_id": stable_hash(raw_id, length=32),
        "plan_status": plan_status,
        "output_event_type": output_event_type,
        "source_event_id": source_event_id,
        "source_event_type": SOURCE_EVENT_TYPE,
        "source_snapshot_run_id": snapshot_run_id,
        "snapshot_id": snapshot.get("snapshot_id"),
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "signal_type": canonical_signal_type,
        "trigger_mark_candidate": trigger_mark_candidate,
        "condition_key": condition_key,
        "original_condition_key": mapping.original_condition_key,
        "legacy_signal_type": legacy_signal_type,
        "match_basis": "realtime_snapshot" if output_event_type == "TriggerMatched" else "pending_market_data",
        "trigger_period": trigger_period,
        "trigger_bucket": "active_30m_projection_required" if trigger_period == "30m" else "trading_day",
        "trigger_live": trigger_live,
        "previous_trigger_live": False,
        "current_status": current_status,
        "previous_status": "inactive",
        "primary_trigger_period": trigger_period,
        "previous_primary_trigger_period": None,
        "all_trigger_periods": [trigger_period],
        "previous_all_trigger_periods": [],
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "previous_projection_30m_flag": False,
        "previous_projection_30m_type": "none",
        "previous_trigger_mark_candidate": None,
        "state_change_reason": "activated" if trigger_live else "status_changed",
        "data_quality_status": data_quality_status,
        "pending_reason": pending_reason,
        "context_snapshot_id": row.get("trigger_context_id"),
        "source_condition_run_id": row.get("source_condition_run_id"),
        "source_condition_pool_id": row.get("source_condition_pool_id"),
        "source_condition_basis_id": row.get("source_condition_basis_id"),
        "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        "source_market_subscription_id": row.get("source_market_subscription_id"),
        "context_hash": row.get("context_hash"),
        "snapshot_trace": {
            "snapshot_run_id": snapshot_run_id,
            "snapshot_id": snapshot.get("snapshot_id"),
            "snapshot_time": snapshot.get("snapshot_time"),
            "quality_status": snapshot.get("quality_status") or "missing",
            "current_price": snapshot.get("current_price"),
            "open": snapshot.get("open"),
            "close": snapshot.get("close"),
            "amount": snapshot.get("amount"),
            "source_adapter": snapshot.get("source_adapter"),
        },
        "period_trigger_baseline_trace": build_period_trigger_baseline_trace(row, condition_key, trigger_period),
        "dry_run_reason": reason,
    }


def build_trigger_state_change_plans(plans: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [build_trigger_state_change_plan(plan) for plan in plans]


def build_trigger_state_change_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    source_outcome_plan_id = str(plan.get("plan_id") or "")
    raw_id = "|".join(
        [
            "TriggerStateChanged",
            source_outcome_plan_id,
            str(plan.get("asset_kind") or ""),
            str(plan.get("identity_key") or ""),
            str(plan.get("direction") or ""),
            str(plan.get("signal_type") or ""),
            str(plan.get("condition_key") or ""),
            str(plan.get("trigger_bucket") or ""),
            str(plan.get("previous_status") or ""),
            str(plan.get("current_status") or ""),
            str(plan.get("state_change_reason") or ""),
        ]
    )
    return {
        **dict(plan),
        "plan_id": stable_hash(raw_id, length=32),
        "plan_status": "state_changed",
        "output_event_type": "TriggerStateChanged",
        "source_outcome_plan_id": source_outcome_plan_id,
        "source_outcome_event_type": plan.get("output_event_type"),
        "source_outcome_event_id": None,
        "writes_common_trigger_match": False,
        "dry_run_reason": "Material trigger state creation/change derived from the outcome dry-run plan",
    }


def summarize_local_trigger_plans(plans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matched = [plan for plan in plans if plan.get("plan_status") == "matched"]
    pending = [plan for plan in plans if plan.get("plan_status") == "pending"]
    state_change_plans = build_trigger_state_change_plans(plans)
    planned_output_event_types = count_by(plans, "output_event_type")
    planned_output_event_types["TriggerStateChanged"] = len(state_change_plans)
    return {
        "candidate_count": len(plans),
        "matched_plan_count": len(matched),
        "pending_plan_count": len(pending),
        "state_change_plan_count": len(state_change_plans),
        "by_asset_kind": count_by(plans, "asset_kind"),
        "matched_by_asset_kind": count_by(matched, "asset_kind"),
        "pending_by_asset_kind": count_by(pending, "asset_kind"),
        "by_direction": count_by(plans, "direction"),
        "matched_by_direction": count_by(matched, "direction"),
        "pending_by_direction": count_by(pending, "direction"),
        "by_signal_type": count_by(plans, "signal_type"),
        "matched_by_signal_type": count_by(matched, "signal_type"),
        "pending_by_signal_type": count_by(pending, "signal_type"),
        "by_trigger_mark_candidate": count_by(plans, "trigger_mark_candidate"),
        "matched_by_trigger_mark_candidate": count_by(matched, "trigger_mark_candidate"),
        "pending_by_trigger_mark_candidate": count_by(pending, "trigger_mark_candidate"),
        "by_legacy_signal_type": count_by(plans, "legacy_signal_type"),
        "matched_by_legacy_signal_type": count_by(matched, "legacy_signal_type"),
        "pending_by_legacy_signal_type": count_by(pending, "legacy_signal_type"),
        "trigger_period_distribution": count_by(plans, "trigger_period"),
        "matched_trigger_period_distribution": count_by(matched, "trigger_period"),
        "pending_trigger_period_distribution": count_by(pending, "trigger_period"),
        "planned_output_event_types": planned_output_event_types,
        "outcome_output_event_types": count_by(plans, "output_event_type"),
        "state_change_output_event_types": count_by(state_change_plans, "output_event_type"),
        "matched_output_event_types": count_by(matched, "output_event_type"),
        "pending_output_event_types": count_by(pending, "output_event_type"),
        "missing_snapshot_context_rows": count_objects(
            plan for plan in pending if plan.get("pending_reason") == "snapshot_fact_missing"
        ),
        "snapshot_quality_not_passed_plan_count": sum(
            1 for plan in pending if plan.get("pending_reason") == "snapshot_quality_not_passed"
        ),
        "projection_not_available_pending_plan_count": sum(
            1 for plan in pending if plan.get("pending_reason") == "projection_fact_not_available_in_local_snapshot_dry_run"
        ),
        "buy_hint_pending_count": sum(1 for plan in pending if plan.get("condition_key") == "BUY_HINT"),
        "sell_hint_pending_count": sum(1 for plan in pending if plan.get("condition_key") == "SELL_HINT"),
        "buy_hint_condition_key_trace_count": sum(1 for plan in plans if plan.get("condition_key") == "BUY_HINT"),
        "sell_hint_condition_key_trace_count": sum(1 for plan in plans if plan.get("condition_key") == "SELL_HINT"),
        "deprecated_runtime_signal_type_count": sum(
            1 for plan in plans if plan.get("signal_type") in DEPRECATED_RUNTIME_SIGNAL_TYPES
        ),
        "pending_market_data_trigger_live_false_count": sum(
            1
            for plan in pending
            if plan.get("current_status") == "pending_market_data" and plan.get("trigger_live") is False
        ),
        "ordinary_snapshot_matched_count": sum(
            1 for plan in matched if plan.get("signal_type") in {"B_BUY", "S_SELL"}
        ),
        "projection_signal_types_pending_count": sum(
            1 for plan in pending if plan.get("legacy_signal_type") in THIRTY_MINUTE_SIGNAL_TYPES
        ),
        "canonical_payload_invalid_count": sum(1 for plan in plans if canonical_payload_errors(plan)),
    }


def summarize_snapshots(snapshot_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "row_count_by_asset_kind": count_by(snapshot_rows, "asset_kind"),
        "object_count_by_asset_kind": {
            asset_kind: count_objects(row for row in snapshot_rows if row.get("asset_kind") == asset_kind)
            for asset_kind in ASSET_KINDS
        },
        "quality_status_distribution": count_by(snapshot_rows, "quality_status"),
    }


def build_quality_items(
    *,
    trigger_context_run_id: str,
    snapshot_run_id: str,
    trigger_run: Mapping[str, Any],
    snapshot_run: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    snapshot_rows: Sequence[Mapping[str, Any]],
    plans: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    baseline_missing_count: int,
    required_not_ready_count: int,
    baseline_trace_count: int,
    before_row_counts: Mapping[str, Mapping[str, Any]] | None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None,
    scoped_event_refs: Mapping[str, int],
) -> list[dict[str, Any]]:
    row_counts_unchanged = True
    if before_row_counts is not None and after_row_counts is not None:
        row_counts_unchanged = before_row_counts == after_row_counts
    new_scoped_ref_shape = any(
        key in scoped_event_refs
        for key in (
            "upstream_input_outbox_allowed",
            "upstream_input_outbox_disallowed",
            "upstream_input_inbox_refs",
            "upstream_input_checkpoint_refs",
            "target_output_outbox_refs",
            "target_inbox_refs",
            "target_checkpoint_refs",
            "target_trigger_match_refs",
            "target_trigger_state_refs",
        )
    )
    upstream_refs = {
        key: int(scoped_event_refs.get(key) or 0)
        for key in (
            "upstream_input_outbox_disallowed",
            "upstream_input_inbox_refs",
            "upstream_input_checkpoint_refs",
        )
    }
    target_refs = {
        key: int(scoped_event_refs.get(key) or 0)
        for key in (
            "target_output_outbox_refs",
            "target_inbox_refs",
            "target_checkpoint_refs",
            "target_trigger_match_refs",
            "target_trigger_state_refs",
        )
    }
    if not new_scoped_ref_shape:
        target_refs = {key: int(value or 0) for key, value in scoped_event_refs.items()}
    upstream_refs_clean = all(value == 0 for value in upstream_refs.values())
    target_refs_clean = all(value == 0 for value in target_refs.values())
    upstream_allowed_count = int(scoped_event_refs.get("upstream_input_outbox_allowed") or 0)
    invalid_canonical_payload_count = sum(1 for plan in plans if canonical_payload_errors(plan))
    return [
        quality_item(
            "P0",
            "passed" if trigger_run.get("run_id") == trigger_context_run_id and trigger_run.get("status") == "passed" else "failed",
            "n4_20260528_context_run_ready",
            "N4 local dry-run must bind a passed 20260528 trigger context run",
            expected=trigger_context_run_id,
            actual=str(trigger_run.get("run_id")),
        ),
        quality_item(
            "P0",
            "passed" if snapshot_run.get("run_id") == snapshot_run_id and snapshot_run.get("status") == "passed" else "failed",
            "n4_20260528_snapshot_run_ready",
            "N4 local dry-run must read the passed B1 retry1 snapshot run",
            expected=snapshot_run_id,
            actual=str(snapshot_run.get("run_id")),
        ),
        quality_item(
            "P0",
            "passed" if context_rows else "failed",
            "n4_20260528_context_rows_available",
            "N4 local dry-run must read local context candidates",
            expected=">0",
            actual=str(len(context_rows)),
        ),
        quality_item(
            "P0",
            "passed" if snapshot_rows else "failed",
            "n4_20260528_snapshot_rows_available",
            "N4 local dry-run must read B1 snapshot facts",
            expected=">0",
            actual=str(len(snapshot_rows)),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("missing_snapshot_context_rows") or 0) == 0 else "failed",
            "n4_20260528_context_snapshot_coverage",
            "Every local context object must be traceable to a B1 snapshot fact",
            expected="0 missing context objects",
            actual=str(summary.get("missing_snapshot_context_rows")),
        ),
        quality_item(
            "P0",
            "passed" if baseline_missing_count == 0 else "failed",
            "n4_20260528_period_trigger_baseline_json_present",
            "N4 local dry-run must use local period_trigger_baseline_json copies",
            expected="missing=0",
            actual=str(baseline_missing_count),
        ),
        quality_item(
            "P0",
            "passed" if required_not_ready_count == 0 else "failed",
            "n4_20260528_required_period_baseline_ready",
            "N4 local dry-run must not use rows whose required periods are not ready",
            expected="required_period_not_ready_rows=0",
            actual=str(required_not_ready_count),
        ),
        quality_item(
            "P0",
            "passed" if len(plans) == 0 or baseline_trace_count == len(plans) else "failed",
            "n4_20260528_plan_payload_traces_period_baseline",
            "All local dry-run plans must trace period_trigger_baseline_json",
            expected=str(len(plans)),
            actual=str(baseline_trace_count),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("ordinary_snapshot_matched_count") or 0) > 0 else "failed",
            "n4_20260528_snapshot_ordinary_candidate_plans",
            "B1 snapshot facts must generate ordinary B_BUY/S_SELL dry-run matched plans",
            expected=">0",
            actual=str(summary.get("ordinary_snapshot_matched_count")),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("projection_signal_types_pending_count") or 0) > 0 else "failed",
            "n4_20260528_projection_signal_candidates_visible",
            "B_BUY_30M_VOL/S_SELL_30M_SHRINK/BUY_HINT/SELL_HINT remain visible as formal candidates",
            expected=">0",
            actual=str(summary.get("projection_signal_types_pending_count")),
        ),
        quality_item(
            "P0",
            "passed" if invalid_canonical_payload_count == 0 else "failed",
            "n4_20260528_canonical_payload_alignment",
            "Local dry-run plans must expose canonical signal_type/trigger_mark_candidate and preserve original_condition_key",
            expected="canonical_payload_invalid_count=0",
            actual=str(invalid_canonical_payload_count),
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n4_20260528_no_database_rows_written",
            "N4 local dry-run must not write database rows",
            expected="before row counts equal after row counts",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item(
            "P0",
            "passed" if upstream_refs_clean else "failed",
            "n4_local_dry_run_upstream_input_refs_compatible",
            "N4 local dry-run may see allowlisted N3 MarketSnapshotUpdated pending input, but must not see consumed/acked or non-allowlisted upstream refs",
            expected="upstream disallowed/inbox/checkpoint refs=0",
            actual=json.dumps(upstream_refs, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed",
            "n4_local_dry_run_upstream_input_outbox_allowlisted",
            "Allowlisted N3 MarketSnapshotUpdated pending outbox is input evidence and does not count as N4 output pollution",
            expected="allowed upstream input outbox >= 0",
            actual=str(upstream_allowed_count),
        ),
        quality_item(
            "P0",
            "passed" if target_refs_clean else "failed",
            "n4_local_dry_run_target_refs_zero",
            "N4 local dry-run must leave target N4 output/inbox/checkpoint/state/match refs at zero",
            expected="target output/state/match/inbox/checkpoint refs=0",
            actual=json.dumps(target_refs, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P1",
            "warning" if int(snapshot_run.get("p1_count") or 0) > 0 else "passed",
            "n4_20260528_b1_p1_carried",
            "B1 retry1 non-blocking P1 is carried into the local dry-run report",
            expected="visible if present",
            actual=str(snapshot_run.get("p1_count") or 0),
        ),
        quality_item(
            "P1",
            "warning" if int(summary.get("projection_not_available_pending_plan_count") or 0) > 0 else "passed",
            "n4_20260528_projection_candidates_pending",
            "Projection/HINT candidates are held pending until N3 standardized projection or closed confirmation exists for this 20260528 lineage",
            expected="pending candidates visible, no TriggerMatched write",
            actual=str(summary.get("projection_not_available_pending_plan_count")),
        ),
        quality_item("P0", "passed", "n4_20260528_no_outbox_consumption", "N4 local dry-run does not consume N3 or N5 outbox"),
        quality_item("P0", "passed", "n4_20260528_no_trigger_fact_write", "N4 local dry-run does not write trigger_match or trigger_state"),
        quality_item("P0", "passed", "n4_20260528_no_standard_outbox_write", "N4 local dry-run does not write TriggerMatched or TriggerPendingMarketData outbox"),
        quality_item("P0", "passed", "n4_20260528_no_worker", "N4 local dry-run does not start worker or service"),
    ]


def capture_row_counts(dsn: str) -> dict[str, dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_local_trigger_dry_run_capture_row_counts",
        source_run_id="local_trigger_row_count_guard",
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        output: dict[str, dict[str, Any]] = {}
        for table_name in ROW_COUNT_GUARD_TABLES:
            cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
            exists = cur.fetchone()["regclass"] is not None
            if not exists:
                output[table_name] = {"exists": False, "row_count": None, "status": "missing"}
                continue
            cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name}")
            output[table_name] = {
                "exists": True,
                "row_count": int(cur.fetchone()["row_count"]),
                "status": "present",
            }
        return output


def capture_scoped_event_refs(
    dsn: str,
    *,
    trigger_context_run_id: str,
    snapshot_run_id: str,
) -> dict[str, int]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_local_trigger_dry_run_capture_scoped_refs",
        source_run_id=trigger_context_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_outbox
            WHERE source_layer = 'N3_market_data'
              AND source_run_id = %s
              AND event_type = %s
              AND status = 'pending'
            """,
            (snapshot_run_id, SOURCE_EVENT_TYPE),
        )
        upstream_allowed_outbox = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_outbox
            WHERE source_run_id = %s
              AND NOT (
                source_layer = 'N3_market_data'
                AND event_type = %s
                AND status = 'pending'
              )
            """,
            (snapshot_run_id, SOURCE_EVENT_TYPE),
        )
        upstream_disallowed_outbox = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_inbox
            WHERE source_run_id = %s
            """,
            (snapshot_run_id,),
        )
        upstream_inbox = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_consumer_checkpoint
            WHERE source_layer = 'N3_market_data'
              AND checkpoint_payload::text LIKE %s
            """,
            (f"%{snapshot_run_id}%",),
        )
        upstream_checkpoint = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_outbox
            WHERE source_layer = 'N4_trigger'
              AND source_run_id = %s
            """,
            (trigger_context_run_id,),
        )
        target_outbox = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_inbox
            WHERE source_run_id = %s
            """,
            (trigger_context_run_id,),
        )
        target_inbox = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_consumer_checkpoint
            WHERE source_layer = 'N4_trigger'
              AND checkpoint_payload::text LIKE %s
            """,
            (f"%{trigger_context_run_id}%",),
        )
        target_checkpoint = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_trigger_match
            WHERE run_id = %s
            """,
            (trigger_context_run_id,),
        )
        target_trigger_match = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_trigger_state
            WHERE run_id = %s
            """,
            (trigger_context_run_id,),
        )
        target_trigger_state = int(cur.fetchone()["row_count"])
    return {
        "upstream_input_outbox_allowed": upstream_allowed_outbox,
        "upstream_input_outbox_disallowed": upstream_disallowed_outbox,
        "upstream_input_inbox_refs": upstream_inbox,
        "upstream_input_checkpoint_refs": upstream_checkpoint,
        "target_output_outbox_refs": target_outbox,
        "target_inbox_refs": target_inbox,
        "target_checkpoint_refs": target_checkpoint,
        "target_trigger_match_refs": target_trigger_match,
        "target_trigger_state_refs": target_trigger_state,
    }


def build_local_trigger_dry_run_rollback_sql(*, trigger_context_run_id: str, snapshot_run_id: str) -> str:
    return f"""-- N4 20260528 local trigger dry-run rollback guard.
-- Dry-run writes no database rows. No DELETE is required for N4 facts or events.
-- Report artifacts may be discarded from docs/sql if this dry-run is superseded.

BEGIN;

DO $$
DECLARE
  v_context_run_id TEXT := '{trigger_context_run_id}';
  v_snapshot_run_id TEXT := '{snapshot_run_id}';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_context_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: N4 output outbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_snapshot_run_id
    AND NOT (
      source_layer = 'N3_market_data'
      AND event_type = 'MarketSnapshotUpdated'
      AND status = 'pending'
    );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: non-allowlisted upstream input outbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id IN (v_context_run_id, v_snapshot_run_id);
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: scoped inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_context_run_id || '%'
     OR checkpoint_payload::text LIKE '%' || v_snapshot_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: checkpoint refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_trigger_match WHERE run_id = v_context_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: trigger_match refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_trigger_state WHERE run_id = v_context_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 local dry-run rollback guard blocked: trigger_state refs = %', v_count;
  END IF;
END $$;

COMMIT;
"""


def format_local_trigger_dry_run_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    summary = report["summary"]
    abnormal = report["abnormal_rows"]
    lines = [
        "# N4 20260528 Local Trigger Dry-Run Report",
        "",
        "## Summary",
        "",
        f"- result: {report['result']}",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- trigger_context_run_id: {report['trigger_context_run_id']}",
        f"- snapshot_run_id: {report['snapshot_run_id']}",
        f"- source_condition_run_id: {report.get('source_condition_run_id')}",
        f"- for_trade_date: {report.get('for_trade_date')}",
        f"- context_candidate_count: {report['context_candidate_count']}",
        f"- candidate_count: {report['candidate_count']}",
        f"- matched_plan_count: {report['matched_plan_count']}",
        f"- pending_plan_count: {report['pending_plan_count']}",
        f"- state_change_plan_count: {report['state_change_plan_count']}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Distribution",
        "",
        f"- by_asset_kind: {summary['by_asset_kind']}",
        f"- matched_by_asset_kind: {summary['matched_by_asset_kind']}",
        f"- pending_by_asset_kind: {summary['pending_by_asset_kind']}",
        f"- by_direction: {summary['by_direction']}",
        f"- by_signal_type: {summary['by_signal_type']}",
        f"- matched_by_signal_type: {summary['matched_by_signal_type']}",
        f"- pending_by_signal_type: {summary['pending_by_signal_type']}",
        f"- by_trigger_mark_candidate: {summary['by_trigger_mark_candidate']}",
        f"- matched_by_trigger_mark_candidate: {summary['matched_by_trigger_mark_candidate']}",
        f"- pending_by_trigger_mark_candidate: {summary['pending_by_trigger_mark_candidate']}",
        f"- by_legacy_signal_type: {summary['by_legacy_signal_type']}",
        f"- deprecated_runtime_signal_type_count: {summary['deprecated_runtime_signal_type_count']}",
        f"- buy_hint_condition_key_trace_count: {summary['buy_hint_condition_key_trace_count']}",
        f"- sell_hint_condition_key_trace_count: {summary['sell_hint_condition_key_trace_count']}",
        f"- pending_market_data_trigger_live_false_count: {summary['pending_market_data_trigger_live_false_count']}",
        f"- trigger_period_distribution: {summary['trigger_period_distribution']}",
        f"- planned_output_event_types: {summary['planned_output_event_types']}",
        "",
        "## Input / Target Refs",
        "",
        f"- upstream_input_refs: {report.get('upstream_input_refs')}",
        f"- target_output_refs: {report.get('target_output_refs')}",
        f"- scoped_event_refs: {report.get('scoped_event_refs')}",
        "",
        "## Abnormal Rows",
        "",
        f"- missing_snapshot_context_rows: {abnormal['missing_snapshot_context_rows']}",
        f"- snapshot_quality_not_passed_plan_count: {abnormal['snapshot_quality_not_passed_plan_count']}",
        f"- period_trigger_baseline_json_missing: {abnormal['period_trigger_baseline_json_missing']}",
        f"- required_period_not_ready_rows: {abnormal['required_period_not_ready_rows']}",
        f"- projection_not_available_pending_plan_count: {abnormal['projection_not_available_pending_plan_count']}",
        "",
        "## Scoped Event Refs",
        "",
        f"- scoped_event_refs: {report['scoped_event_refs']}",
        "",
        "## Quality",
        "",
    ]
    for item in quality["items"]:
        lines.append(
            f"- {item['severity']} {item['status']} {item['gate_code']}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(["", "## Boundary Confirmation", ""])
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines.extend(
        [
            "",
            "## Rollback",
            "",
            f"- rollback_sql_path: {report.get('rollback_sql_path')}",
            "- Dry-run writes no DB rows; rollback SQL is a scoped guard/no-op for DB state.",
            "",
            "## Next Gate",
            "",
            f"- allow_local_trigger_dry_run_review: {str(report['next_gate']['allow_local_trigger_dry_run_review']).lower()}",
            f"- allow_trigger_execute: {str(report['next_gate']['allow_trigger_execute']).lower()}",
            f"- allow_n5_action: {str(report['next_gate']['allow_n5_action']).lower()}",
            f"- note: {report['next_gate']['note']}",
            "",
        ]
    )
    return "\n".join(lines)


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def count_objects(rows: Sequence[Mapping[str, Any]]) -> int:
    return len({str(row.get("identity_key") or "") for row in rows if row.get("identity_key")})


def count_context_by_asset(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        asset_kind: sum(1 for row in rows if row.get("asset_kind") == asset_kind)
        for asset_kind in ASSET_KINDS
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
