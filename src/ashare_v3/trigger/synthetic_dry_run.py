"""N4-4 synthetic N3 event trigger dry-run planner.

The planner reads only the local N4 trigger_context_snapshot tables and builds
candidate TriggerMatched / TriggerPendingMarketData plans for synthetic N3
events. It never consumes real common_event_outbox rows and never writes DB
trigger facts, outbox events, action/user/voice/sim rows, or market data.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
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
    missing_required_period_trigger_baseline_periods,
    normalize_text_array,
    period_trigger_baseline_json_missing_count,
    required_period_not_ready_rows_count,
    required_periods_for_condition_key,
)
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect


DEFAULT_N4_4_JSON_REPORT_PATH = "docs/N4_4_synthetic_trigger_dry_run_report.json"
DEFAULT_N4_4_MD_REPORT_PATH = "docs/N4_4_SYNTHETIC_TRIGGER_DRY_RUN_REPORT.md"
DEFAULT_TRIGGER_CONTEXT_RUN_ID = (
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute"
)

SYNTHETIC_EVENT_TYPES = (
    "MarketSnapshotUpdated",
    "MinuteBarClosed",
    "MarketDataDelayed",
    "MarketDataMissing",
)
OUTPUT_PLAN_TYPES = ("TriggerMatched", "TriggerPendingMarketData")
ORDINARY_SIGNAL_BY_DIRECTION = {"buy": "B_BUY", "sell": "S_SELL"}
THIRTY_MINUTE_SIGNAL_BY_DIRECTION = {"buy": "B_BUY_30M_VOL", "sell": "S_SELL_30M_SHRINK"}
HINT_SIGNAL_TYPES = ("BUY_HINT", "SELL_HINT")
THIRTY_MINUTE_SIGNAL_TYPES = ("B_BUY_30M_VOL", "S_SELL_30M_SHRINK", "BUY_HINT", "SELL_HINT")
PERIOD_PRIORITY = ("D", "W", "M", "Q", "Y")

ROW_COUNT_GUARD_TABLES = (
    "common_trigger_run",
    "common_trigger_quality_item",
    "stock_trigger_context_snapshot",
    "index_trigger_context_snapshot",
    "board_trigger_context_snapshot",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
)


def run_synthetic_trigger_dry_run(
    *,
    dsn: str,
    trigger_context_run_id: str = DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    json_report_path: str = DEFAULT_N4_4_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N4_4_MD_REPORT_PATH,
    sample_limit: int = 80,
    stage: str = "N4-4",
) -> dict[str, Any]:
    before_counts = capture_row_counts(dsn)
    before_outbox_lineage = capture_outbox_lineage(dsn, trigger_context_run_id=trigger_context_run_id)
    context_rows, trigger_run = fetch_local_context_rows(dsn, trigger_context_run_id)
    synthetic_events = build_synthetic_events(str(trigger_run.get("for_trade_date") or "20260525"))
    report = build_synthetic_trigger_dry_run_report(
        stage=stage,
        trigger_context_run_id=trigger_context_run_id,
        trigger_run=trigger_run,
        context_rows=context_rows,
        synthetic_events=synthetic_events,
        before_row_counts=before_counts,
        after_row_counts=capture_row_counts(dsn),
        outbox_lineage=before_outbox_lineage,
        sample_limit=sample_limit,
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_synthetic_trigger_dry_run_report(report))
    return report


def fetch_local_context_rows(dsn: str, trigger_context_run_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_synthetic_dry_run_fetch_context",
        source_run_id=trigger_context_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, source_condition_run_id, source_market_data_run_id,
                   for_trade_date, source_trade_date, prev_trade_date,
                   mode, status, context_snapshot_row_count,
                   trigger_state_row_count, trigger_match_row_count, trigger_event_outbox_count
            FROM common_trigger_run
            WHERE run_id = %s
            """,
            (trigger_context_run_id,),
        )
        trigger_run = normalize_mapping(cur.fetchone() or {})
        rows: list[dict[str, Any]] = []
        for asset_kind in ASSET_KINDS:
            table_name = TARGET_CONTEXT_TABLES[asset_kind]
            cur.execute(
                f"""
                SELECT trigger_context_id, run_id, source_condition_run_id,
                       source_condition_pool_id, source_condition_basis_id,
                       source_minute_target_scope_id, source_market_subscription_id,
                       for_trade_date, source_trade_date, prev_trade_date,
                       asset_kind, identity_key, direction, condition_key,
                       condition_periods, allowed_signal_types, is_hint_scope,
                       context_hash, quality_status, raw_json
                FROM {table_name}
                WHERE run_id = %s
                ORDER BY identity_key, direction, condition_key, trigger_context_id
                """,
                (trigger_context_run_id,),
            )
            rows.extend(normalize_context_row(row) for row in cur.fetchall())
        return rows, trigger_run


def normalize_context_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["condition_periods"] = normalize_text_array(output.get("condition_periods"))
    output["allowed_signal_types"] = normalize_text_array(output.get("allowed_signal_types"))
    raw_json = output.get("raw_json") or {}
    output["period_trigger_baseline_json"] = (
        raw_json.get("period_trigger_baseline_json") if isinstance(raw_json, Mapping) else {}
    ) or {}
    return output


def build_synthetic_events(for_trade_date: str) -> list[dict[str, Any]]:
    return [
        {
            "event_id": f"synthetic_n3_market_snapshot_{for_trade_date}",
            "event_type": "MarketSnapshotUpdated",
            "event_time": f"{for_trade_date}T10:00:00+08:00",
            "data_quality_status": "passed",
            "dry_run_summary": "synthetic realtime daily snapshot update",
        },
        {
            "event_id": f"synthetic_n3_minute_bar_closed_30m_{for_trade_date}_103000",
            "event_type": "MinuteBarClosed",
            "event_time": f"{for_trade_date}T10:30:00+08:00",
            "data_quality_status": "passed",
            "minute_window": {"window_start": "10:00", "window_end": "10:30", "closed": True},
            "synthetic_30m_summary": {
                "buy_confirmation": "volume_up_price_up",
                "sell_confirmation": "volume_shrink_price_down",
            },
        },
        {
            "event_id": f"synthetic_n3_market_data_delayed_{for_trade_date}",
            "event_type": "MarketDataDelayed",
            "event_time": f"{for_trade_date}T10:31:00+08:00",
            "data_quality_status": "delayed",
            "dry_run_summary": "synthetic market data delay quality event",
        },
        {
            "event_id": f"synthetic_n3_market_data_missing_{for_trade_date}",
            "event_type": "MarketDataMissing",
            "event_time": f"{for_trade_date}T10:32:00+08:00",
            "data_quality_status": "missing",
            "dry_run_summary": "synthetic market data missing quality event",
        },
    ]


def build_synthetic_trigger_dry_run_report(
    *,
    stage: str = "N4-4",
    trigger_context_run_id: str,
    trigger_run: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    synthetic_events: Sequence[Mapping[str, Any]],
    before_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    outbox_lineage: Mapping[str, Any] | None = None,
    sample_limit: int = 80,
) -> dict[str, Any]:
    plans = build_dry_run_plans(context_rows=context_rows, synthetic_events=synthetic_events)
    summary = summarize_plans(plans)
    baseline_missing_count = period_trigger_baseline_json_missing_count(context_rows)
    required_not_ready_count = required_period_not_ready_rows_count(context_rows)
    baseline_trace_count = sum(1 for plan in plans if plan.get("period_trigger_baseline_trace", {}).get("present"))
    effective_outbox_lineage = dict(outbox_lineage or build_empty_outbox_lineage(trigger_context_run_id))
    quality_items = build_quality_items(
        trigger_context_run_id=trigger_context_run_id,
        trigger_run=trigger_run,
        context_rows=context_rows,
        synthetic_events=synthetic_events,
        plans=plans,
        baseline_missing_count=baseline_missing_count,
        required_not_ready_count=required_not_ready_count,
        baseline_trace_count=baseline_trace_count,
        before_row_counts=before_row_counts,
        after_row_counts=after_row_counts,
        outbox_lineage=effective_outbox_lineage,
    )
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": stage,
        "result": "DRY_RUN_PASS" if severity_counts["P0"] == 0 else "DRY_RUN_BLOCKED",
        "layer_role": "N4_trigger",
        "mode": "synthetic_sample_n3_event_trigger_dry_run",
        "trigger_context_run_id": trigger_context_run_id,
        "source_condition_run_id": trigger_run.get("source_condition_run_id"),
        "source_market_data_run_id": trigger_run.get("source_market_data_run_id"),
        "for_trade_date": trigger_run.get("for_trade_date"),
        "generated_at": utc_now_iso(),
        "synthetic_events": list(synthetic_events),
        "context_source": {
            "read_local_trigger_context_snapshot": True,
            "external_n2_runtime_path_accessed": False,
            "real_common_event_outbox_consumed": False,
            "context_row_count": len(context_rows),
            "context_row_count_by_asset_kind": count_context_by_asset(context_rows),
            "period_trigger_baseline_json_raw_json_path": "trigger_context_snapshot.raw_json.period_trigger_baseline_json",
            "period_trigger_baseline_json_missing": baseline_missing_count,
            "required_period_not_ready_rows": required_not_ready_count,
        },
        "period_trigger_baseline_json_missing": baseline_missing_count,
        "required_period_not_ready_rows": required_not_ready_count,
        "period_trigger_baseline_trace_count": baseline_trace_count,
        "candidate_count": len(plans),
        "context_candidate_count": len(context_rows),
        "matched_count": summary["matched_count"],
        "pending_count": summary["pending_count"],
        "summary": summary,
        "outbox_lineage": effective_outbox_lineage,
        "sample_plans": plans[:sample_limit],
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "writes_performed": False,
            "trigger_state_written": False,
            "trigger_match_written": False,
            "event_outbox_written": False,
            "market_data_pulled": False,
            "real_n3_event_consumed": False,
            "real_common_event_outbox_consumed": False,
            "downstream_layers_touched": False,
            "action_user_voice_sim_written": False,
            "worker_started": False,
            "old_system_touched": False,
            "external_n2_runtime_path_accessed": False,
        },
        "before_row_counts": before_row_counts or {},
        "after_row_counts": after_row_counts or {},
    }


def build_dry_run_plans(
    *,
    context_rows: Sequence[Mapping[str, Any]],
    synthetic_events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for event in synthetic_events:
        event_type = str(event["event_type"])
        for row in context_rows:
            if event_type == "MarketSnapshotUpdated":
                plans.extend(build_snapshot_match_plans(row, event))
            elif event_type == "MinuteBarClosed":
                plans.extend(build_minute_match_plans(row, event))
            elif event_type in {"MarketDataDelayed", "MarketDataMissing"}:
                plans.extend(build_pending_plans(row, event))
            else:
                continue
    return plans


def build_snapshot_match_plans(row: Mapping[str, Any], event: Mapping[str, Any]) -> list[dict[str, Any]]:
    signal_type = ORDINARY_SIGNAL_BY_DIRECTION.get(str(row.get("direction") or ""))
    if not signal_type or signal_type not in normalize_text_array(row.get("allowed_signal_types")):
        return []
    if row.get("condition_key") in HINT_SIGNAL_TYPES:
        return []
    return [
        build_plan(
            row=row,
            event=event,
            signal_type=signal_type,
            output_event_type="TriggerMatched",
            plan_status="matched",
            trigger_period=derive_trigger_period(row, signal_type),
            data_quality_status="passed",
            reason="synthetic MarketSnapshotUpdated validates ordinary BUY/SELL/FULL trigger candidate",
        )
    ]


def build_minute_match_plans(row: Mapping[str, Any], event: Mapping[str, Any]) -> list[dict[str, Any]]:
    signal_type = minute_signal_type_for_row(row)
    if not signal_type:
        return []
    return [
        build_plan(
            row=row,
            event=event,
            signal_type=signal_type,
            output_event_type="TriggerMatched",
            plan_status="matched",
            trigger_period="30m",
            data_quality_status="passed",
            reason="synthetic MinuteBarClosed / 30m summary validates 30m trigger candidate",
        )
    ]


def minute_signal_type_for_row(row: Mapping[str, Any]) -> str | None:
    condition_key = str(row.get("condition_key") or "")
    allowed = normalize_text_array(row.get("allowed_signal_types"))
    if condition_key == "BUY_HINT" and "BUY_HINT" in allowed:
        return "BUY_HINT"
    if condition_key == "SELL_HINT" and "SELL_HINT" in allowed:
        return "SELL_HINT"
    signal_type = THIRTY_MINUTE_SIGNAL_BY_DIRECTION.get(str(row.get("direction") or ""))
    if signal_type in allowed:
        return signal_type
    return None


def build_pending_plans(row: Mapping[str, Any], event: Mapping[str, Any]) -> list[dict[str, Any]]:
    event_type = str(event["event_type"])
    data_quality_status = "delayed" if event_type == "MarketDataDelayed" else "missing"
    plans = []
    for signal_type in normalize_text_array(row.get("allowed_signal_types")):
        plans.append(
            build_plan(
                row=row,
                event=event,
                signal_type=signal_type,
                output_event_type="TriggerPendingMarketData",
                plan_status="pending",
                trigger_period=derive_trigger_period(row, signal_type),
                data_quality_status=data_quality_status,
                reason=f"synthetic {event_type} creates pending market-data quality plan only",
            )
        )
    return plans


def build_plan(
    *,
    row: Mapping[str, Any],
    event: Mapping[str, Any],
    signal_type: str,
    output_event_type: str,
    plan_status: str,
    trigger_period: str,
    data_quality_status: str,
    reason: str,
) -> dict[str, Any]:
    asset_kind = str(row.get("asset_kind") or "")
    identity_key = str(row.get("identity_key") or "")
    direction = str(row.get("direction") or "")
    condition_key = str(row.get("condition_key") or "")
    legacy_signal_type = signal_type
    mapping = canonicalize_trigger_candidate(
        condition_key,
        candidate_signal_type=legacy_signal_type,
        projection_30m_type=projection_30m_type_for_synthetic_event(legacy_signal_type, event, output_event_type),
    )
    canonical_signal_type = mapping.signal_type
    trigger_mark_candidate = mapping.trigger_mark_candidate
    source_event_id = (
        f"{event['event_id']}:{identity_key}:{canonical_signal_type}:"
        f"{trigger_mark_candidate}:{legacy_signal_type}"
    )
    return {
        "plan_id": stable_hash(f"{source_event_id}:{condition_key}:{trigger_period}:{output_event_type}", length=32),
        "plan_status": plan_status,
        "output_event_type": output_event_type,
        "source_event_id": source_event_id,
        "source_event_type": event["event_type"],
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "signal_type": canonical_signal_type,
        "trigger_mark_candidate": trigger_mark_candidate,
        "condition_key": condition_key,
        "original_condition_key": mapping.original_condition_key,
        "legacy_signal_type": legacy_signal_type,
        "match_basis": "closed_30m_summary" if event["event_type"] == "MinuteBarClosed" else "synthetic_market_event",
        "trigger_period": trigger_period,
        "trigger_bucket": "30m_1000_1030" if trigger_period == "30m" else "trading_day",
        "data_quality_status": data_quality_status,
        "context_snapshot_id": row.get("trigger_context_id"),
        "source_condition_run_id": row.get("source_condition_run_id"),
        "source_condition_pool_id": row.get("source_condition_pool_id"),
        "source_condition_basis_id": row.get("source_condition_basis_id"),
        "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        "source_market_subscription_id": row.get("source_market_subscription_id"),
        "context_hash": row.get("context_hash"),
        "period_trigger_baseline_trace": build_period_trigger_baseline_trace(row, condition_key, trigger_period),
        "dry_run_reason": reason,
    }


def projection_30m_type_for_synthetic_event(
    signal_type: str,
    event: Mapping[str, Any],
    output_event_type: str,
) -> str:
    if event.get("event_type") != "MinuteBarClosed" or output_event_type != "TriggerMatched":
        return "none"
    if signal_type in {"B_BUY_30M_VOL", "BUY_HINT"}:
        return "volume_up"
    if signal_type in {"S_SELL_30M_SHRINK", "SELL_HINT"}:
        return "shrink_down"
    return "none"


def build_period_trigger_baseline_trace(
    row: Mapping[str, Any],
    condition_key: str,
    trigger_period: str,
) -> dict[str, Any]:
    baseline = row.get("period_trigger_baseline_json") or {}
    periods = baseline.get("periods") if isinstance(baseline, Mapping) else {}
    required_periods = required_periods_for_condition_key(condition_key)
    not_ready_periods = missing_required_period_trigger_baseline_periods(row)
    traced_periods = sorted(set(required_periods + ([trigger_period] if trigger_period in PERIOD_PRIORITY else [])))
    period_trace = {}
    if isinstance(periods, Mapping):
        for period in traced_periods:
            entry = periods.get(period)
            if not isinstance(entry, Mapping):
                continue
            has_trigger_baseline = any(
                entry.get(key) not in (None, "")
                for key in (
                    "trigger_previous_entity_high",
                    "trigger_previous_entity_low",
                    "trigger_previous_amount_baseline",
                )
            )
            period_trace[period] = {
                "baseline_ready": bool(entry.get("baseline_ready")),
                "baseline_source": "trigger_baseline" if has_trigger_baseline else "legacy_previous_fallback",
                "period_key_current": entry.get("period_key_current"),
                "period_key_previous": entry.get("period_key_previous"),
                "previous_entity_high": entry.get("previous_entity_high"),
                "previous_entity_low": entry.get("previous_entity_low"),
                "previous_amount": entry.get("previous_amount"),
                "previous_avg_amount": entry.get("previous_avg_amount"),
                "previous_amount_baseline": entry.get("previous_amount_baseline"),
                "classification_previous_entity_high": entry.get("classification_previous_entity_high"),
                "classification_previous_entity_low": entry.get("classification_previous_entity_low"),
                "classification_previous_amount_baseline": entry.get("classification_previous_amount_baseline"),
                "trigger_previous_entity_high": entry.get("trigger_previous_entity_high"),
                "trigger_previous_entity_low": entry.get("trigger_previous_entity_low"),
                "trigger_previous_amount_baseline": entry.get("trigger_previous_amount_baseline"),
                "baseline_source_trade_date": entry.get("baseline_source_trade_date"),
                "amount_metric": entry.get("amount_metric"),
            }
    return {
        "present": bool(baseline),
        "raw_json_path": "trigger_context_snapshot.raw_json.period_trigger_baseline_json",
        "baseline_version": baseline.get("baseline_version") if isinstance(baseline, Mapping) else None,
        "baseline_source": baseline.get("baseline_source") if isinstance(baseline, Mapping) else None,
        "required_periods": required_periods,
        "required_period_not_ready": not_ready_periods,
        "traced_periods": period_trace,
    }


def derive_trigger_period(row: Mapping[str, Any], signal_type: str) -> str:
    if signal_type in THIRTY_MINUTE_SIGNAL_TYPES:
        return "30m"
    condition_key = str(row.get("condition_key") or "")
    if condition_key.endswith(":FULL"):
        return "D"
    periods = normalize_text_array(row.get("condition_periods"))
    for period in PERIOD_PRIORITY:
        if period in periods:
            return period
    return "D"


def summarize_plans(plans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matched = [plan for plan in plans if plan.get("plan_status") == "matched"]
    pending = [plan for plan in plans if plan.get("plan_status") == "pending"]
    return {
        "candidate_count": len(plans),
        "matched_count": len(matched),
        "pending_count": len(pending),
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
        "by_event_type": count_by(plans, "source_event_type"),
        "matched_by_event_type": count_by(matched, "source_event_type"),
        "pending_by_event_type": count_by(pending, "source_event_type"),
        "trigger_period_distribution": count_by(plans, "trigger_period"),
        "matched_trigger_period_distribution": count_by(matched, "trigger_period"),
        "pending_trigger_period_distribution": count_by(pending, "trigger_period"),
        "buy_hint_matched_count": sum(
            1 for plan in matched if plan.get("condition_key") == "BUY_HINT"
        ),
        "sell_hint_matched_count": sum(
            1 for plan in matched if plan.get("condition_key") == "SELL_HINT"
        ),
        "pending_output_event_types": count_by(pending, "output_event_type"),
        "matched_output_event_types": count_by(matched, "output_event_type"),
        "canonical_payload_invalid_count": sum(1 for plan in plans if canonical_payload_errors(plan)),
    }


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def count_context_by_asset(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        asset_kind: sum(1 for row in rows if row.get("asset_kind") == asset_kind)
        for asset_kind in ASSET_KINDS
    }


def build_quality_items(
    *,
    trigger_context_run_id: str,
    trigger_run: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    synthetic_events: Sequence[Mapping[str, Any]],
    plans: Sequence[Mapping[str, Any]],
    before_row_counts: Mapping[str, Mapping[str, Any]] | None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None,
    baseline_missing_count: int = 0,
    required_not_ready_count: int = 0,
    baseline_trace_count: int = 0,
    outbox_lineage: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    summary = summarize_plans(plans)
    matched_by_event = summary["matched_by_event_type"]
    pending_by_event = summary["pending_by_event_type"]
    buy_hint_matched_count = int(summary.get("buy_hint_matched_count") or 0)
    sell_hint_matched_count = int(summary.get("sell_hint_matched_count") or 0)
    event_types = {event.get("event_type") for event in synthetic_events}
    lineage = outbox_lineage or build_empty_outbox_lineage(trigger_context_run_id)
    row_counts_unchanged = True
    if before_row_counts is not None and after_row_counts is not None:
        row_counts_unchanged = before_row_counts == after_row_counts
    return [
        quality_item(
            "P0",
            "passed" if trigger_run.get("run_id") == trigger_context_run_id and trigger_run.get("status") == "passed" else "failed",
            "n4_4_trigger_context_run_ready",
            "N4-4 must read a passed local trigger_context_snapshot run",
            expected=trigger_context_run_id,
            actual=str(trigger_run.get("run_id")),
        ),
        quality_item(
            "P0",
            "passed" if context_rows else "failed",
            "n4_4_local_context_rows_available",
            "N4-4 must read candidates from local trigger_context_snapshot",
            expected=">0",
            actual=str(len(context_rows)),
        ),
        quality_item(
            "P0",
            "passed" if baseline_missing_count == 0 else "failed",
            "n4_4_period_trigger_baseline_json_present",
            "N4-R4 synthetic dry-run must read period_trigger_baseline_json from local context raw_json",
            expected="missing=0",
            actual=str(baseline_missing_count),
        ),
        quality_item(
            "P0",
            "passed" if required_not_ready_count == 0 else "failed",
            "n4_4_required_period_baseline_ready",
            "N4-R4 synthetic dry-run must not use context rows whose required period baselines are not ready",
            expected="required_period_not_ready_rows=0",
            actual=str(required_not_ready_count),
        ),
        quality_item(
            "P0",
            "passed" if len(plans) == 0 or baseline_trace_count == len(plans) else "failed",
            "n4_4_plan_payload_traces_period_baseline",
            "TriggerMatched / TriggerPendingMarketData dry-run plans must trace period_trigger_baseline_json lineage",
            expected=str(len(plans)),
            actual=str(baseline_trace_count),
        ),
        quality_item(
            "P0",
            "passed" if event_types == set(SYNTHETIC_EVENT_TYPES) else "failed",
            "n4_4_uses_synthetic_event_types",
            "N4-4 must use the requested synthetic/sample event types",
            expected=",".join(SYNTHETIC_EVENT_TYPES),
            actual=",".join(sorted(str(item) for item in event_types)),
        ),
        quality_item(
            "P0",
            "passed" if int(matched_by_event.get("MarketSnapshotUpdated", 0)) > 0 else "failed",
            "n4_4_snapshot_matches_ordinary_buy_sell",
            "synthetic MarketSnapshotUpdated must match ordinary BUY/SELL candidates",
            expected="matched ordinary B_BUY/S_SELL > 0",
            actual=str(matched_by_event.get("MarketSnapshotUpdated", 0)),
        ),
        quality_item(
            "P0",
            "passed" if buy_hint_matched_count > 0 and sell_hint_matched_count > 0 else "failed",
            "n4_4_minute_matches_buy_sell_hint",
            "synthetic MinuteBarClosed must match BUY_HINT/SELL_HINT condition_key traces as formal buy/sell candidates",
            expected="BUY_HINT and SELL_HINT condition_key matched > 0",
            actual=f"BUY_HINT={buy_hint_matched_count} SELL_HINT={sell_hint_matched_count}",
        ),
        quality_item(
            "P0",
            "passed" if int(pending_by_event.get("MarketDataMissing", 0)) > 0 and int(matched_by_event.get("MarketDataMissing", 0)) == 0 else "failed",
            "n4_4_market_data_missing_pending_only",
            "MarketDataMissing must produce pending plans only",
            expected="pending>0 matched=0",
            actual=f"pending={pending_by_event.get('MarketDataMissing', 0)} matched={matched_by_event.get('MarketDataMissing', 0)}",
        ),
        quality_item(
            "P0",
            "passed" if int(pending_by_event.get("MarketDataDelayed", 0)) > 0 and int(matched_by_event.get("MarketDataDelayed", 0)) == 0 else "failed",
            "n4_4_market_data_delayed_pending_only",
            "MarketDataDelayed must produce pending plans only",
            expected="pending>0 matched=0",
            actual=f"pending={pending_by_event.get('MarketDataDelayed', 0)} matched={matched_by_event.get('MarketDataDelayed', 0)}",
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n4_4_no_database_rows_written",
            "N4-4 dry-run must not write DB rows",
            expected="before row counts equal after row counts",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("canonical_payload_invalid_count") or 0) == 0 else "failed",
            "n4_4_canonical_payload_alignment",
            "Synthetic dry-run payloads must expose canonical signal_type/trigger_mark_candidate and preserve original_condition_key",
            expected="canonical_payload_invalid_count=0",
            actual=str(summary.get("canonical_payload_invalid_count")),
        ),
        quality_item(
            "P0",
            "passed" if int(lineage.get("current_context_run_outbox_count") or 0) == 0 else "failed",
            "n4_4_no_current_context_outbox_available",
            "synthetic dry-run must not create current context run outbox rows",
            expected="0",
            actual=str(lineage.get("current_context_run_outbox_count")),
        ),
        quality_item(
            "P0",
            "passed",
            "n4_4_existing_outbox_is_prior_run_only",
            "Existing N4 outbox baseline is lineage-only and must not be handed to N5 for this context run",
            expected="current context run outbox is absent",
            actual=(
                f"old_n4_outbox_count={lineage.get('stale_n4_outbox_count')} "
                f"current_context_run_outbox_count={lineage.get('current_context_run_outbox_count')}"
            ),
        ),
        quality_item("P0", "passed", "n4_4_no_real_outbox_consumption", "N4-4 does not consume real common_event_outbox"),
        quality_item("P0", "passed", "n4_4_no_market_data_pull", "N4-4 does not pull market data"),
        quality_item("P0", "passed", "n4_4_no_trigger_fact_write", "N4-4 does not write trigger_state or trigger_match"),
        quality_item("P0", "passed", "n4_4_no_downstream_write", "N4-4 does not write action/user/voice/sim"),
        quality_item("P0", "passed", "n4_4_no_external_n2_runtime_path", "N4-4 does not access external N2 runtime path"),
    ]


def capture_row_counts(dsn: str) -> dict[str, dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_synthetic_dry_run_capture_row_counts",
        source_run_id="synthetic_row_count_guard",
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


def capture_outbox_lineage(dsn: str, *, trigger_context_run_id: str) -> dict[str, Any]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_synthetic_dry_run_capture_outbox_lineage",
        source_run_id=trigger_context_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.common_event_outbox') AS regclass")
        if cur.fetchone()["regclass"] is None:
            return build_empty_outbox_lineage(trigger_context_run_id)

        cur.execute("SELECT count(*)::bigint AS row_count FROM common_event_outbox")
        total_count = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT source_layer, source_run_id, event_type, count(*)::bigint AS row_count
            FROM common_event_outbox
            GROUP BY source_layer, source_run_id, event_type
            ORDER BY source_layer, source_run_id, event_type
            """
        )
        by_source_run = rows_to_json(cur.fetchall())
        cur.execute(
            """
            SELECT count(*)::bigint AS row_count
            FROM common_event_outbox
            WHERE source_layer = 'N4_trigger'
              AND source_run_id = %s
            """,
            (trigger_context_run_id,),
        )
        current_context_run_outbox_count = int(cur.fetchone()["row_count"])
        cur.execute(
            """
            SELECT source_run_id, event_type, count(*)::bigint AS row_count
            FROM common_event_outbox
            WHERE source_layer = 'N4_trigger'
              AND source_run_id <> %s
            GROUP BY source_run_id, event_type
            ORDER BY source_run_id, event_type
            """,
            (trigger_context_run_id,),
        )
        stale_by_run = rows_to_json(cur.fetchall())

    stale_count = sum(int(row["row_count"]) for row in stale_by_run)
    return {
        "common_event_outbox_baseline_count": total_count,
        "current_context_run_id": trigger_context_run_id,
        "current_context_run_outbox_count": current_context_run_outbox_count,
        "stale_n4_outbox_count": stale_count,
        "stale_n4_outbox_by_source_run": stale_by_run,
        "outbox_by_source_run": by_source_run,
        "current_run_has_n5_usable_outbox": False,
        "n5_use_guidance": (
            "Existing N4 outbox rows belong to prior trigger context runs. "
            "This dry-run creates no current-run outbox, so N5 must not consume the stale baseline."
        ),
    }


def build_empty_outbox_lineage(trigger_context_run_id: str) -> dict[str, Any]:
    return {
        "common_event_outbox_baseline_count": 0,
        "current_context_run_id": trigger_context_run_id,
        "current_context_run_outbox_count": 0,
        "stale_n4_outbox_count": 0,
        "stale_n4_outbox_by_source_run": [],
        "outbox_by_source_run": [],
        "current_run_has_n5_usable_outbox": False,
        "n5_use_guidance": "No current-run N4 outbox exists from this dry-run.",
    }


def rows_to_json(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_mapping(row) for row in rows]


def format_synthetic_trigger_dry_run_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    summary = report["summary"]
    outbox_lineage = report.get("outbox_lineage") or {}
    lines = [
        f"# {report['stage']} Synthetic Trigger Dry-Run Report",
        "",
        "## Summary",
        "",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- trigger_context_run_id: {report['trigger_context_run_id']}",
        f"- source_condition_run_id: {report['source_condition_run_id']}",
        f"- source_market_data_run_id: {report.get('source_market_data_run_id')}",
        f"- for_trade_date: {report['for_trade_date']}",
        f"- context_candidate_count: {report['context_candidate_count']}",
        f"- period_trigger_baseline_json_missing: {report.get('period_trigger_baseline_json_missing')}",
        f"- required_period_not_ready_rows: {report.get('required_period_not_ready_rows')}",
        f"- period_trigger_baseline_trace_count: {report.get('period_trigger_baseline_trace_count')}",
        f"- candidate_count: {report['candidate_count']}",
        f"- matched_count: {report['matched_count']}",
        f"- pending_count: {report['pending_count']}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Distribution",
        "",
        f"- by_asset_kind: {summary['by_asset_kind']}",
        f"- by_direction: {summary['by_direction']}",
        f"- by_signal_type: {summary['by_signal_type']}",
        f"- by_trigger_mark_candidate: {summary['by_trigger_mark_candidate']}",
        f"- by_legacy_signal_type: {summary['by_legacy_signal_type']}",
        f"- by_event_type: {summary['by_event_type']}",
        f"- trigger_period_distribution: {summary['trigger_period_distribution']}",
        f"- matched_by_signal_type: {summary['matched_by_signal_type']}",
        f"- matched_by_trigger_mark_candidate: {summary['matched_by_trigger_mark_candidate']}",
        f"- pending_by_signal_type: {summary['pending_by_signal_type']}",
        f"- pending_by_trigger_mark_candidate: {summary['pending_by_trigger_mark_candidate']}",
        f"- pending_by_event_type: {summary['pending_by_event_type']}",
        f"- buy_hint_matched_count: {summary['buy_hint_matched_count']}",
        f"- sell_hint_matched_count: {summary['sell_hint_matched_count']}",
        "",
        "## Planned Output Events",
        "",
        f"- matched_output_event_types: {summary['matched_output_event_types']}",
        f"- pending_output_event_types: {summary['pending_output_event_types']}",
        "",
        "## Outbox Lineage",
        "",
        f"- common_event_outbox_baseline_count: {outbox_lineage.get('common_event_outbox_baseline_count')}",
        f"- current_context_run_outbox_count: {outbox_lineage.get('current_context_run_outbox_count')}",
        f"- stale_n4_outbox_count: {outbox_lineage.get('stale_n4_outbox_count')}",
        f"- stale_n4_outbox_by_source_run: {outbox_lineage.get('stale_n4_outbox_by_source_run')}",
        f"- current_run_has_n5_usable_outbox: {str(outbox_lineage.get('current_run_has_n5_usable_outbox')).lower()}",
        f"- n5_use_guidance: {outbox_lineage.get('n5_use_guidance')}",
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
            "No DB rows are written in N4-4. Rollback is deleting this dry-run report if needed.",
            "",
        ]
    )
    return "\n".join(lines)


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
