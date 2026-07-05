"""N5-5 action consumer run-once dry-run planner.

This module reads N4 standard outbox rows and builds the write plan N5 would
use in a future execute step. It never writes inbox/checkpoint rows, action
facts, common_action_event rows, N5 outbox rows, user projections, voice, sim,
mobile, true trading rows, or worker state.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.action.query_audit_phase2 import audited_n5_readonly_plan_connect
from ashare_v3.action.consumer_dry_run import (
    CONSUMER_ORDERING,
    DEFAULT_N5_1_CONSUMER_NAME,
    build_consumer_contract,
    build_consumer_plan,
    compact_event_plans,
    empty_inbox_keys,
    fetch_existing_checkpoints,
    fetch_existing_inbox_keys,
    summarize_consumer_plan,
)
from ashare_v3.action.dry_run import (
    ALLOWED_N4_INPUT_EVENT_TYPES,
    N5_OUTPUT_EVENT_TYPES,
    build_action_tracking_state_plan,
    build_action_candidates_from_outbox_rows,
    infer_source_action_confirmation_metric_id,
    summarize_action_candidates,
    summarize_action_tracking_state_plan,
)
from ashare_v3.action.preflight import (
    DEFAULT_TRIGGER_RUN_ID,
    ROW_COUNT_GUARD_TABLES,
    fetch_n4_outbox_rows,
    fetch_row_counts,
    fetch_trigger_run,
    normalize_outbox_row,
    summarize_outbox_rows,
)
from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item


DEFAULT_N5_5_JSON_REPORT_PATH = "docs/N5_5_action_consumer_run_once_dry_run_report.json"
DEFAULT_N5_5_MD_REPORT_PATH = "docs/N5_5_ACTION_CONSUMER_RUN_ONCE_DRY_RUN_REPORT.md"
DEFAULT_N5_5_BASELINE_REPORT_PATH = "docs/N5_1_action_consumer_dry_run_report.json"
DEFAULT_N5_5_ACTION_RUN_ID = (
    "action_consumer_run_once_dry_run_20260525_"
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029"
)
DEFAULT_N5_R4_TRIGGER_RUN_ID = (
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute"
)
DEFAULT_N5_R4_ACTION_RUN_ID = (
    "action_consumer_run_once_dry_run_20260525_"
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855"
)
DEFAULT_N5_R4_BASELINE_REPORT_PATH = "docs/N4_R4_synthetic_trigger_execute_report.json"
DEFAULT_N5_R4_JSON_REPORT_PATH = "docs/N5_R4_action_consumer_run_once_dry_run_report.json"
DEFAULT_N5_R4_MD_REPORT_PATH = "docs/N5_R4_ACTION_CONSUMER_RUN_ONCE_DRY_RUN_REPORT.md"
CURRENT_REAL_N4_SOURCE_RUN_ID = (
    "trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249"
)
CURRENT_REAL_N4_SOURCE_RUN_ALLOWLIST = (CURRENT_REAL_N4_SOURCE_RUN_ID,)
SYNTHETIC_N4_SOURCE_RUN_DENYLIST = (
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute",
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute",
)
DEFAULT_N5_CURRENT_REAL_ACTION_RUN_ID = (
    "action_consumer_current_real_dry_run_20260525_"
    "trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249"
)
DEFAULT_N5_CURRENT_REAL_BASELINE_REPORT_PATH = "docs/N4_PROJECTION_MATCHER_EXECUTE_PREFLIGHT_REPORT.json"
DEFAULT_N5_CURRENT_REAL_JSON_REPORT_PATH = "docs/N5_current_real_action_consumer_dry_run_report.json"
DEFAULT_N5_CURRENT_REAL_MD_REPORT_PATH = "docs/N5_CURRENT_REAL_ACTION_CONSUMER_DRY_RUN_REPORT.md"
DEFAULT_N5_CURRENT_REAL_ROLLBACK_SQL_PATH = "sql/N5_current_real_action_execute_rollback.sql"
ACTION_FACT_TABLE_BY_ASSET_KIND = {
    "stock": "stock_action_fact",
    "index": "index_action_fact",
    "board": "board_action_fact",
}
ACTION_FACT_TABLES = tuple(ACTION_FACT_TABLE_BY_ASSET_KIND.values())
ACTION_EVENT_GUARD_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "stock_action_fact",
    "index_action_fact",
    "board_action_fact",
    "common_action_event",
    "common_position_state",
    "common_position_event",
)
ACTION_CONFIRMATION_METRIC_TABLE_BY_ASSET_KIND = {
    "stock": "stock_action_confirmation_projection_metric",
    "index": "index_action_confirmation_projection_metric",
    "board": "board_action_confirmation_projection_metric",
}


def coerce_action_metric_run_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            output.extend(coerce_action_metric_run_ids(item))
        return output
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def fetch_action_confirmation_metric_facts(
    cur: Any,
    outbox_rows: Sequence[Mapping[str, Any]],
    *,
    metric_run_id: Any = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    metric_run_ids = coerce_action_metric_run_ids(metric_run_id)
    ids_by_asset_kind: dict[str, set[int]] = defaultdict(set)
    for row in outbox_rows:
        payload = row.get("payload_json") or {}
        if not isinstance(payload, Mapping):
            continue
        asset_kind = str(payload.get("asset_kind") or row.get("asset_kind") or "")
        metric_id = infer_source_action_confirmation_metric_id(payload)
        if asset_kind in ACTION_CONFIRMATION_METRIC_TABLE_BY_ASSET_KIND and metric_id:
            ids_by_asset_kind[asset_kind].add(int(metric_id))

    output: dict[tuple[str, str], dict[str, Any]] = {}
    for asset_kind, metric_ids in sorted(ids_by_asset_kind.items()):
        if not metric_ids:
            continue
        table_name = ACTION_CONFIRMATION_METRIC_TABLE_BY_ASSET_KIND[asset_kind]
        if metric_run_ids:
            cur.execute(
                f"""
                SELECT *
                FROM {table_name}
                WHERE action_confirmation_metric_id = ANY(%s)
                  AND projection_run_id = ANY(%s)
                """,
                (list(sorted(metric_ids)), metric_run_ids),
            )
        else:
            cur.execute(
                f"""
                SELECT *
                FROM {table_name}
                WHERE action_confirmation_metric_id = ANY(%s)
                """,
                (list(sorted(metric_ids)),),
            )
        for row in cur.fetchall():
            normalized = normalize_mapping(row)
            metric_id = str(normalized.get("action_confirmation_metric_id") or "")
            if metric_id:
                output[(asset_kind, metric_id)] = normalized
    return output


def run_action_consumer_run_once_dry_run(
    *,
    dsn: str,
    trigger_run_id: str = DEFAULT_TRIGGER_RUN_ID,
    action_run_id: str = DEFAULT_N5_5_ACTION_RUN_ID,
    consumer_name: str = DEFAULT_N5_1_CONSUMER_NAME,
    baseline_report_path: str = DEFAULT_N5_5_BASELINE_REPORT_PATH,
    json_report_path: str = DEFAULT_N5_5_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_5_MD_REPORT_PATH,
    stage: str = "N5-5",
    expected_read_event_count: int | None = None,
    require_period_trigger_baseline_trace: bool = False,
    allowed_source_run_ids: Sequence[str] | None = None,
    denied_source_run_ids: Sequence[str] | None = None,
    rollback_sql_path: str | None = None,
    sample_limit: int = 80,
) -> dict[str, Any]:
    started_at = utc_now_iso()
    with audited_n5_readonly_plan_connect(
        dsn,
        stage_id="n5_run_once_dry_run",
        source_run_id=action_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        before_counts = fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES)
        trigger_run = fetch_trigger_run(cur, trigger_run_id)
        outbox_rows = fetch_n4_outbox_rows(cur, trigger_run_id)
        action_confirmation_metric_facts = fetch_action_confirmation_metric_facts(cur, outbox_rows)
        existing_inbox_keys = fetch_existing_inbox_keys(cur, consumer_name)
        existing_checkpoints = fetch_existing_checkpoints(cur, consumer_name)
        after_counts = fetch_row_counts(cur, ROW_COUNT_GUARD_TABLES)

    report = build_action_consumer_run_once_dry_run_report_from_rows(
        trigger_run_id=trigger_run_id,
        action_run_id=action_run_id,
        consumer_name=consumer_name,
        trigger_run=trigger_run,
        outbox_rows=outbox_rows,
        existing_inbox_keys=existing_inbox_keys,
        existing_checkpoints=existing_checkpoints,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
        action_confirmation_metric_facts=action_confirmation_metric_facts,
        baseline_report=load_baseline_report(baseline_report_path),
        baseline_report_path=baseline_report_path,
        stage=stage,
        expected_read_event_count=expected_read_event_count,
        require_period_trigger_baseline_trace=require_period_trigger_baseline_trace,
        allowed_source_run_ids=allowed_source_run_ids,
        denied_source_run_ids=denied_source_run_ids,
        rollback_sql_path=rollback_sql_path,
        started_at=started_at,
        finished_at=utc_now_iso(),
        json_report_path=json_report_path,
        markdown_report_path=markdown_report_path,
        sample_limit=sample_limit,
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_action_consumer_run_once_dry_run_report(report))
    return report


def build_action_consumer_run_once_dry_run_report_from_rows(
    *,
    trigger_run_id: str,
    action_run_id: str,
    consumer_name: str,
    trigger_run: Mapping[str, Any] | None,
    outbox_rows: Sequence[Mapping[str, Any]],
    existing_inbox_keys: Mapping[str, set[str]] | None = None,
    existing_checkpoints: Mapping[str, Mapping[str, Any]] | None = None,
    before_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    action_confirmation_metric_facts: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None = None,
    action_confirmation_metric_facts_by_identity: Mapping[Any, Sequence[Mapping[str, Any]]] | None = None,
    baseline_report: Mapping[str, Any] | None = None,
    baseline_report_path: str = DEFAULT_N5_5_BASELINE_REPORT_PATH,
    stage: str = "N5-5",
    expected_read_event_count: int | None = None,
    require_period_trigger_baseline_trace: bool = False,
    allowed_source_run_ids: Sequence[str] | None = None,
    denied_source_run_ids: Sequence[str] | None = None,
    rollback_sql_path: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    json_report_path: str = DEFAULT_N5_5_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N5_5_MD_REPORT_PATH,
    sample_limit: int = 80,
) -> dict[str, Any]:
    normalized_rows = [normalize_outbox_row(row) for row in outbox_rows]
    consumer_plan = build_consumer_plan(
        rows=normalized_rows,
        consumer_name=consumer_name,
        existing_inbox_keys=existing_inbox_keys or empty_inbox_keys(),
        existing_checkpoints=existing_checkpoints or {},
    )
    accepted_rows = [
        item["source_outbox_row"]
        for item in consumer_plan["event_plans"]
        if item["consumer_status"] == "planned_receive"
    ]
    candidates = build_action_candidates_from_outbox_rows(
        accepted_rows,
        action_run_id=action_run_id,
        action_confirmation_metric_facts=action_confirmation_metric_facts,
        action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
    )
    candidate_key_recheck = build_candidate_key_stability_recheck(
        accepted_rows[:sample_limit],
        candidates[:sample_limit],
        action_run_id,
        action_confirmation_metric_facts=action_confirmation_metric_facts,
        action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
        full_candidate_count=len(candidates),
    )
    action_tracking_state_plan = build_action_tracking_state_plan(candidates)
    action_write_plan = build_action_write_plan(candidates, action_tracking_state_plan=action_tracking_state_plan)
    output_event_plan = build_output_event_plan(action_write_plan)
    outbox_summary = summarize_outbox_rows(normalized_rows)
    source_run_id_summary = summarize_source_run_ids(normalized_rows, expected_source_run_id=trigger_run_id)
    source_run_guard = build_source_run_guard(
        trigger_run_id=trigger_run_id,
        source_run_id_summary=source_run_id_summary,
        allowed_source_run_ids=allowed_source_run_ids,
        denied_source_run_ids=denied_source_run_ids,
    )
    period_trigger_baseline_trace_summary = summarize_period_trigger_baseline_trace(normalized_rows)
    consumer_summary = summarize_consumer_plan(consumer_plan)
    candidate_summary = summarize_action_candidates(candidates)
    action_write_plan_summary = summarize_action_write_plan(action_write_plan)
    action_tracking_state_plan_summary = summarize_action_tracking_state_plan(action_tracking_state_plan)
    output_event_plan_summary = summarize_output_event_plan(output_event_plan)
    baseline_comparison = compare_baseline_report(
        current_consumer_summary=consumer_summary,
        current_outbox_summary=outbox_summary,
        trigger_run_id=trigger_run_id,
        baseline_report=baseline_report,
        baseline_report_path=baseline_report_path,
    )
    consumer_guard = build_consumer_guard(
        consumer_name=consumer_name,
        trigger_run_id=trigger_run_id,
        baseline_report=baseline_report,
        existing_inbox_keys=existing_inbox_keys or empty_inbox_keys(),
        existing_checkpoints=existing_checkpoints or {},
    )
    quality_items = build_quality_items(
        trigger_run_id=trigger_run_id,
        consumer_name=consumer_name,
        trigger_run=trigger_run or {},
        outbox_summary=outbox_summary,
        source_run_id_summary=source_run_id_summary,
        period_trigger_baseline_trace_summary=period_trigger_baseline_trace_summary,
        consumer_summary=consumer_summary,
        candidate_summary=candidate_summary,
        action_write_plan_summary=action_write_plan_summary,
        output_event_plan_summary=output_event_plan_summary,
        baseline_comparison=baseline_comparison,
        consumer_guard=consumer_guard,
        candidate_key_recheck=candidate_key_recheck,
        source_run_guard=source_run_guard,
        expected_read_event_count=expected_read_event_count,
        require_period_trigger_baseline_trace=require_period_trigger_baseline_trace,
        before_row_counts=before_row_counts or {},
        after_row_counts=after_row_counts or {},
    )
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": stage,
        "layer_role": "N5_action",
        "mode": "action_consumer_run_once_dry_run",
        "execution_mode": "read_only_n4_outbox_action_write_plan",
        "action_run_id": action_run_id,
        "consumer_name": consumer_name,
        "source_trigger_run_id": trigger_run_id,
        "source_trigger_run": normalize_mapping(trigger_run or {}),
        "for_trade_date": (trigger_run or {}).get("for_trade_date") or infer_trade_date(normalized_rows),
        "started_at": started_at or utc_now_iso(),
        "finished_at": finished_at or utc_now_iso(),
        "json_report_path": json_report_path,
        "markdown_report_path": markdown_report_path,
        "rollback_sql_path": rollback_sql_path,
        "expected_read_event_count": expected_read_event_count,
        "baseline_report_path": baseline_report_path,
        "consumer_contract": build_consumer_contract(consumer_name),
        "consumer_guard": consumer_guard,
        "run_once_contract": build_run_once_contract(),
        "baseline_comparison": baseline_comparison,
        "outbox_summary": outbox_summary,
        "source_run_id_summary": source_run_id_summary,
        "source_run_guard": source_run_guard,
        "period_trigger_baseline_trace_summary": period_trigger_baseline_trace_summary,
        "consumer_plan_summary": consumer_summary,
        "action_candidate_summary": candidate_summary,
        "action_write_plan_summary": action_write_plan_summary,
        "action_tracking_state_plan_summary": action_tracking_state_plan_summary,
        "output_event_plan_summary": output_event_plan_summary,
        "candidate_key_stability_recheck": candidate_key_recheck,
        "action_confirmation_metric_readiness": summarize_action_confirmation_metric_readiness(candidates),
        "checkpoint_write_plan": consumer_plan["checkpoint_write_plan"],
        "sample_event_plans": compact_event_plans(consumer_plan["event_plans"], sample_limit),
        "sample_action_candidates": candidates[:sample_limit],
        "sample_action_tracking_state_plan": action_tracking_state_plan[:sample_limit],
        "sample_action_write_plan": action_write_plan[:sample_limit],
        "output_event_write_plan": output_event_plan,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "before_row_counts": before_row_counts or {},
        "after_row_counts": after_row_counts or {},
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "writes_performed": False,
            "common_event_inbox_updated": False,
            "consumer_checkpoint_updated": False,
            "action_run_written": False,
            "action_quality_written": False,
            "action_fact_written": False,
            "action_event_written": False,
            "position_state_written": False,
            "position_event_written": False,
            "common_event_outbox_written": False,
            "n5_outbox_written": False,
            "n4_outbox_status_updated": False,
            "n4_outbox_consumed": False,
            "market_data_pulled": False,
            "n1_n2_n3_n4_modified": False,
            "n6_user_layer_touched": False,
            "user_layer_touched": False,
            "voice_touched": False,
            "sim_touched": False,
            "mobile_touched": False,
            "real_trade_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "passed": severity_counts["P0"] == 0,
    }


def build_run_once_contract() -> dict[str, Any]:
    return {
        "input_event_types": list(ALLOWED_N4_INPUT_EVENT_TYPES),
        "consumer_name": DEFAULT_N5_1_CONSUMER_NAME,
        "ordering": list(CONSUMER_ORDERING),
        "action_fact_tables": dict(ACTION_FACT_TABLE_BY_ASSET_KIND),
        "output_event_types": list(N5_OUTPUT_EVENT_TYPES),
        "pending_market_data_policy": "TriggerPendingMarketData creates only a quality plan and no action fact",
        "tracking_state_policy": (
            "TriggerMatched creates/updates N5 tracking in dry-run; "
            "TriggerStateChanged updates existing tracking or expires unfinished tracking; "
            "TriggerStateChanged never starts action confirmation"
        ),
        "source_trigger_match_id_policy": (
            "ordinary TriggerMatched rows plan at most one action fact per source_trigger_match_id; "
            "live-window multi-action rows use selected_metric_id action grain"
        ),
        "execute_boundary": {
            "common_event_inbox_updated": False,
            "consumer_checkpoint_updated": False,
            "action_fact_written": False,
            "action_event_written": False,
            "common_event_outbox_written": False,
        },
    }


def build_consumer_guard(
    *,
    consumer_name: str,
    trigger_run_id: str,
    baseline_report: Mapping[str, Any] | None,
    existing_inbox_keys: Mapping[str, set[str]],
    existing_checkpoints: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate whether the requested consumer is legal for this run-once plan.

    The default N5 consumer remains the normal online path. A dedicated
    reprocess consumer is allowed only when the baseline explicitly declares it
    and its live inbox/checkpoint state is empty, so replay cannot silently skip
    historical events or collide with another consumer lineage.
    """

    inbox_ref_count = sum(len(values or set()) for values in existing_inbox_keys.values())
    checkpoint_ref_count = len(existing_checkpoints)
    if consumer_name == DEFAULT_N5_1_CONSUMER_NAME:
        return {
            "passed": True,
            "strategy": "default",
            "consumer_name": consumer_name,
            "expected_consumer_name": DEFAULT_N5_1_CONSUMER_NAME,
            "blockers": [],
            "uses_dedicated_consumer": False,
            "dedicated_consumer_name": None,
            "source_trigger_run_id_match": True,
            "metric_run_id_bound": False,
            "inbox_ref_count": inbox_ref_count,
            "checkpoint_ref_count": checkpoint_ref_count,
        }

    baseline = baseline_report or {}
    strategy = baseline.get("consumer_strategy") or {}
    dedicated_name = str(
        strategy.get("dedicated_consumer_name")
        or baseline.get("dedicated_consumer_name")
        or baseline.get("consumer_name")
        or ""
    )
    metric_run_id = str(
        baseline.get("metric_run_id")
        or baseline.get("n3_action_metric_run_id")
        or baseline.get("action_metric_run_id")
        or ""
    )
    metric_inputs = baseline.get("metric_inputs")
    if not metric_run_id and isinstance(metric_inputs, Mapping):
        metric_run_id = ",".join(
            str(value)
            for value in (
                metric_inputs.get("original_metric_run_id"),
                metric_inputs.get("repair_metric_run_id"),
            )
            if value
        )
    baseline_source_run_id = str(
        baseline.get("source_trigger_run_id")
        or baseline.get("source_run_id")
        or baseline.get("trigger_run_id")
        or ""
    )
    blockers: list[str] = []
    if strategy.get("uses_dedicated_consumer") is not True:
        blockers.append("baseline_dedicated_consumer_not_declared")
    if dedicated_name != consumer_name:
        blockers.append("dedicated_consumer_name_mismatch")
    if baseline_source_run_id != trigger_run_id:
        blockers.append("dedicated_consumer_source_trigger_run_id_mismatch")
    if not metric_run_id:
        blockers.append("dedicated_consumer_metric_run_id_missing")
    if inbox_ref_count or checkpoint_ref_count:
        blockers.append("dedicated_consumer_inbox_or_checkpoint_not_empty")
    return {
        "passed": not blockers,
        "strategy": "dedicated_reprocess",
        "consumer_name": consumer_name,
        "expected_consumer_name": dedicated_name or DEFAULT_N5_1_CONSUMER_NAME,
        "blockers": blockers,
        "uses_dedicated_consumer": strategy.get("uses_dedicated_consumer") is True,
        "dedicated_consumer_name": dedicated_name or None,
        "source_trigger_run_id_match": baseline_source_run_id == trigger_run_id,
        "metric_run_id_bound": bool(metric_run_id),
        "metric_run_id": metric_run_id or None,
        "baseline_source_trigger_run_id": baseline_source_run_id or None,
        "inbox_ref_count": inbox_ref_count,
        "checkpoint_ref_count": checkpoint_ref_count,
    }


def build_action_write_plan(
    candidates: Sequence[Mapping[str, Any]],
    *,
    action_tracking_state_plan: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    seen_match_ids: set[str] = set()
    seen_action_grains: dict[str, dict[str, Any]] = {}
    tracking_plan = action_tracking_state_plan or build_action_tracking_state_plan(candidates)
    plans: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        candidate_kind = str(candidate.get("candidate_kind") or "")
        source_event_type = str(candidate.get("source_trigger_event_type") or "")
        source_trigger_match_id = normalize_match_id(candidate.get("source_trigger_match_id"))
        asset_kind = str(candidate.get("asset_kind") or "")
        target_action_fact_table = ACTION_FACT_TABLE_BY_ASSET_KIND.get(asset_kind)
        action_confirmation_grain_key = str(candidate.get("action_confirmation_grain_key") or "")
        action_confirmation_merge_key = str(candidate.get("action_confirmation_merge_key") or action_confirmation_grain_key)
        allow_multi_action_same_match = bool(candidate.get("multi_action_window_candidate"))
        skip_reasons: list[str] = []
        tracking_row = tracking_plan[index] if index < len(tracking_plan) else {}
        if candidate_kind == "quality_plan":
            plan_status = "quality_plan_only"
        elif candidate_kind == "state_gate":
            plan_status = (
                "state_gate_expire"
                if tracking_row.get("operation") == "expire_unfinished_tracking"
                else "state_gate_only"
            )
        else:
            if not target_action_fact_table:
                skip_reasons.append("unsupported_asset_kind_for_action_fact_table")
            if source_event_type == "TriggerMatched":
                if not source_trigger_match_id:
                    skip_reasons.append("missing_source_trigger_match_id")
                elif source_trigger_match_id in seen_match_ids and not allow_multi_action_same_match:
                    skip_reasons.append("duplicate_source_trigger_match_id")
                elif action_confirmation_merge_key and action_confirmation_merge_key in seen_action_grains:
                    skip_reasons.append("duplicate_action_confirmation_grain")
                    merge_condition_provenance(seen_action_grains[action_confirmation_merge_key], candidate)
                else:
                    if not allow_multi_action_same_match:
                        seen_match_ids.add(source_trigger_match_id)
            plan_status = "planned_action_fact" if not skip_reasons else "skipped"

        would_insert_action_fact = plan_status == "planned_action_fact"
        would_update_existing_action_fact = plan_status == "state_gate_expire"
        planned_output_event_type = (
            "ActionSkipped"
            if would_update_existing_action_fact
            else candidate.get("planned_output_event_type") if would_insert_action_fact else None
        )
        action_key = action_confirmation_grain_key if would_insert_action_fact and action_confirmation_grain_key else candidate.get("action_key")
        plan = {
            "plan_status": plan_status,
            "skip_reasons": skip_reasons,
            "candidate_kind": candidate_kind,
            "source_trigger_event_id": candidate.get("source_trigger_event_id"),
            "source_trigger_event_type": source_event_type,
            "source_trigger_match_id": candidate.get("source_trigger_match_id"),
            "trigger_state_id": candidate.get("trigger_state_id"),
            "source_condition_run_id": candidate.get("source_condition_run_id"),
            "source_market_data_run_id": candidate.get("source_market_data_run_id"),
            "identity_key": candidate.get("identity_key"),
            "asset_kind": asset_kind,
            "direction": candidate.get("direction"),
            "signal_type": candidate.get("signal_type"),
            "condition_key": candidate.get("condition_key"),
            "original_condition_key": candidate.get("original_condition_key"),
            "trigger_kind": candidate.get("trigger_kind"),
            "trigger_period": candidate.get("trigger_period"),
            "primary_trigger_period": candidate.get("primary_trigger_period"),
            "trigger_time": candidate.get("trigger_time"),
            "trigger_price": candidate.get("trigger_price"),
            "trigger_live": candidate.get("trigger_live"),
            "current_status": candidate.get("current_status"),
            "action_eligible": candidate.get("action_eligible"),
            "trigger_mark_candidate": candidate.get("trigger_mark_candidate"),
            "action_mark_candidate": candidate.get("action_mark_candidate"),
            "final_action_mark": candidate.get("final_action_mark"),
            "action_state": candidate.get("action_state"),
            "confirmation_status": candidate.get("confirmation_status"),
            "blocked_reason": candidate.get("blocked_reason"),
            "minute_boundary_status": candidate.get("minute_boundary_status"),
            "action_event_type": candidate.get("action_event_type"),
            "starts_action_confirmation": candidate.get("starts_action_confirmation"),
            "runtime_signal_status": candidate.get("runtime_signal_status"),
            "action_type": candidate.get("action_type"),
            "lane": candidate.get("lane"),
            "decision_status": candidate.get("decision_status"),
            "data_quality_status": candidate.get("data_quality_status"),
            "closed_minute_required": candidate.get("closed_minute_required"),
            "closed_minute_verified": candidate.get("closed_minute_verified"),
            "minute_context_status": candidate.get("minute_context_status"),
            "source_market_trace": candidate.get("source_market_trace") or {},
            "trace_json": candidate.get("trace_json") or {},
            "action_bucket": candidate.get("action_bucket"),
            "source_action_confirmation_metric_id": candidate.get("source_action_confirmation_metric_id"),
            "source_projection_run_id": candidate.get("source_projection_run_id"),
            "action_confirmation_grain_key": action_confirmation_grain_key or None,
            "action_confirmation_merge_key": action_confirmation_merge_key or None,
            "multi_action_window_candidate": allow_multi_action_same_match,
            "action_event_time": candidate.get("action_event_time"),
            "target_action_fact_table": target_action_fact_table if would_insert_action_fact else None,
            "target_quality_table": "common_action_quality_item" if candidate_kind == "quality_plan" else None,
            "planned_output_event_type": planned_output_event_type,
            "tracking_state_key": candidate.get("tracking_state_key"),
            "tracking_state_operation": tracking_row.get("operation"),
            "tracking_state_match_strategy": tracking_row.get("match_strategy"),
            "tracking_state_plan": tracking_row,
            "action_key": action_key,
            "dedup_key": action_key,
            "event_schema_version": candidate.get("event_schema_version"),
            "source_payload_json": candidate.get("source_payload_json") or {},
            "would_insert_action_fact": would_insert_action_fact,
            "would_update_existing_action_fact": would_update_existing_action_fact,
            "would_create_action_tracking_state": bool(tracking_row.get("would_create_tracking_state")),
            "would_update_action_tracking_state": bool(tracking_row.get("would_update_tracking_state")),
            "would_expire_action_tracking_state": bool(tracking_row.get("would_expire_tracking_state")),
            "would_insert_common_action_quality_item": candidate_kind == "quality_plan",
            "would_insert_common_action_event": (would_insert_action_fact or would_update_existing_action_fact) and bool(planned_output_event_type),
            "would_insert_common_event_outbox": (would_insert_action_fact or would_update_existing_action_fact) and bool(planned_output_event_type),
            "would_update_position_state": False,
            "would_insert_common_position_event": False,
            "would_update_common_event_inbox": False,
            "would_update_consumer_checkpoint": False,
            "executed": False,
        }
        if would_insert_action_fact and action_confirmation_merge_key:
            seen_action_grains[action_confirmation_merge_key] = plan
        plans.append(plan)
    return plans


def merge_condition_provenance(plan: dict[str, Any], candidate: Mapping[str, Any]) -> None:
    trace = dict(plan.get("trace_json") or {})
    provenance = dict(trace.get("condition_provenance") or {})
    condition_keys = list(provenance.get("condition_keys") or [])
    original_condition_keys = list(provenance.get("original_condition_keys") or [])
    source_event_ids = list(provenance.get("source_trigger_event_ids") or [])
    source_match_ids = list(provenance.get("source_trigger_match_ids") or [])
    append_unique(condition_keys, candidate.get("condition_key"))
    append_unique(original_condition_keys, candidate.get("original_condition_key"))
    append_unique(source_event_ids, candidate.get("source_trigger_event_id"))
    append_unique(source_match_ids, candidate.get("source_trigger_match_id"))
    provenance["condition_keys"] = condition_keys
    provenance["original_condition_keys"] = original_condition_keys
    provenance["source_trigger_event_ids"] = source_event_ids
    provenance["source_trigger_match_ids"] = source_match_ids
    trace["condition_provenance"] = provenance
    plan["trace_json"] = trace


def append_unique(values: list[Any], value: Any) -> None:
    if value is None:
        return
    if value not in values:
        values.append(value)


def build_output_event_plan(action_write_plan: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(
        str(row.get("planned_output_event_type") or "")
        for row in action_write_plan
        if row.get("planned_output_event_type")
        and row.get("plan_status") in {"planned_action_fact", "state_gate_expire"}
    )
    return [
        {
            "event_type": event_type,
            "planned_event_count": int(counts.get(event_type, 0)),
            "would_insert_common_action_event": int(counts.get(event_type, 0)) > 0,
            "would_insert_common_event_outbox": int(counts.get(event_type, 0)) > 0,
            "common_event_outbox_written": False,
            "executed": False,
        }
        for event_type in N5_OUTPUT_EVENT_TYPES
    ]


def summarize_action_write_plan(action_write_plan: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    planned = [row for row in action_write_plan if row.get("plan_status") == "planned_action_fact"]
    quality_only = [row for row in action_write_plan if row.get("plan_status") == "quality_plan_only"]
    state_gate_only = [row for row in action_write_plan if row.get("plan_status") == "state_gate_only"]
    state_gate_expire = [row for row in action_write_plan if row.get("plan_status") == "state_gate_expire"]
    skipped = [row for row in action_write_plan if row.get("plan_status") == "skipped"]
    pending_action_fact_plan_count = sum(
        1
        for row in action_write_plan
        if row.get("source_trigger_event_type") == "TriggerPendingMarketData"
        and row.get("would_insert_action_fact")
    )
    planned_match_ids = [
        normalize_match_id(row.get("source_trigger_match_id"))
        for row in planned
        if row.get("source_trigger_event_type") == "TriggerMatched"
        and normalize_match_id(row.get("source_trigger_match_id"))
        and not row.get("multi_action_window_candidate")
    ]
    duplicate_planned_match_ids = sorted(
        match_id for match_id, count in Counter(planned_match_ids).items() if count > 1
    )
    multi_action_groups = Counter(
        str(row.get("source_trigger_event_id") or "")
        for row in planned
        if row.get("multi_action_window_candidate")
    )
    multi_action_groups = Counter({key: count for key, count in multi_action_groups.items() if key})
    return {
        "plan_row_count": len(action_write_plan),
        "planned_action_fact_count": len(planned),
        "quality_plan_only_count": len(quality_only),
        "state_gate_only_count": len(state_gate_only),
        "state_gate_expire_count": len(state_gate_expire),
        "skipped_count": len(skipped),
        "by_plan_status": count_by(action_write_plan, "plan_status"),
        "skip_reasons": count_skip_reasons(skipped),
        "by_target_action_fact_table": count_by(planned, "target_action_fact_table"),
        "by_asset_kind": count_by(action_write_plan, "asset_kind"),
        "planned_action_fact_by_asset_kind": count_by(planned, "asset_kind"),
        "planned_action_fact_by_signal_type": count_by(planned, "signal_type"),
        "planned_action_fact_by_direction": count_by(planned, "direction"),
        "planned_action_fact_by_output_event_type": count_by(planned, "planned_output_event_type"),
        "planned_action_fact_by_action_state": count_by(planned, "action_state"),
        "planned_action_fact_by_confirmation_status": count_by(planned, "confirmation_status"),
        "state_gate_expire_by_output_event_type": count_by(state_gate_expire, "planned_output_event_type"),
        "buy_hint_planned_action_fact_count": sum(
            1
            for row in planned
            if row.get("condition_key") == "BUY_HINT" or row.get("original_condition_key") == "BUY_HINT"
        ),
        "sell_hint_planned_action_fact_count": sum(
            1
            for row in planned
            if row.get("condition_key") == "SELL_HINT" or row.get("original_condition_key") == "SELL_HINT"
        ),
        "deprecated_runtime_signal_type_action_fact_count": sum(
            1 for row in planned if row.get("runtime_signal_status") == "deprecated_runtime_signal_type"
        ),
        "pending_action_fact_plan_count": pending_action_fact_plan_count,
        "duplicate_source_trigger_match_id_skipped_count": sum(
            1 for row in skipped if "duplicate_source_trigger_match_id" in (row.get("skip_reasons") or [])
        ),
        "missing_source_trigger_match_id_skipped_count": sum(
            1 for row in skipped if "missing_source_trigger_match_id" in (row.get("skip_reasons") or [])
        ),
        "duplicate_source_trigger_match_id_planned_count": len(duplicate_planned_match_ids),
        "duplicate_source_trigger_match_ids_planned_sample": duplicate_planned_match_ids[:20],
        "multi_action_trigger_count": sum(1 for count in multi_action_groups.values() if count > 1),
        "executed_metric_count": sum(1 for row in planned if row.get("multi_action_window_candidate")),
        "max_actions_per_trigger": max(multi_action_groups.values(), default=0),
        "physical_split_error_count": count_physical_split_errors(planned),
        "would_insert_common_action_event_count": sum(
            1 for row in action_write_plan if row.get("would_insert_common_action_event")
        ),
        "would_insert_common_event_outbox_count": sum(
            1 for row in action_write_plan if row.get("would_insert_common_event_outbox")
        ),
        "would_update_existing_action_fact_count": sum(
            1 for row in action_write_plan if row.get("would_update_existing_action_fact")
        ),
        "would_create_action_tracking_state_count": sum(
            1 for row in action_write_plan if row.get("would_create_action_tracking_state")
        ),
        "would_update_action_tracking_state_count": sum(
            1 for row in action_write_plan if row.get("would_update_action_tracking_state")
        ),
        "would_expire_action_tracking_state_count": sum(
            1 for row in action_write_plan if row.get("would_expire_action_tracking_state")
        ),
        "executed_count": sum(1 for row in action_write_plan if row.get("executed")),
    }


def summarize_output_event_plan(output_event_plan: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    event_types = [str(row.get("event_type") or "") for row in output_event_plan]
    missing = sorted(set(N5_OUTPUT_EVENT_TYPES) - set(event_types))
    return {
        "event_type_contract": list(N5_OUTPUT_EVENT_TYPES),
        "event_types_in_plan": event_types,
        "missing_event_types": missing,
        "by_event_type": {
            str(row.get("event_type") or ""): int(row.get("planned_event_count") or 0)
            for row in output_event_plan
        },
        "planned_event_count": sum(int(row.get("planned_event_count") or 0) for row in output_event_plan),
        "common_event_outbox_written": any(bool(row.get("common_event_outbox_written")) for row in output_event_plan),
        "executed_count": sum(1 for row in output_event_plan if row.get("executed")),
    }


def summarize_source_run_ids(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_source_run_id: str,
) -> dict[str, Any]:
    by_source_run_id = count_by(rows, "source_run_id")
    unexpected = {
        source_run_id: count
        for source_run_id, count in by_source_run_id.items()
        if source_run_id != expected_source_run_id
    }
    return {
        "expected_source_run_id": expected_source_run_id,
        "by_source_run_id": by_source_run_id,
        "only_expected_source_run_id": not unexpected and bool(rows),
        "unexpected_source_run_id_count": sum(unexpected.values()),
        "unexpected_source_run_ids": unexpected,
    }


def build_source_run_guard(
    *,
    trigger_run_id: str,
    source_run_id_summary: Mapping[str, Any],
    allowed_source_run_ids: Sequence[str] | None,
    denied_source_run_ids: Sequence[str] | None,
) -> dict[str, Any]:
    allowed = tuple(allowed_source_run_ids or ())
    denied = tuple(denied_source_run_ids or ())
    by_source_run_id = dict(source_run_id_summary.get("by_source_run_id") or {})
    observed = set(by_source_run_id)
    denied_observed = sorted(source_run_id for source_run_id in observed if source_run_id in denied)
    outside_allowlist = sorted(
        source_run_id for source_run_id in observed if allowed and source_run_id not in allowed
    )
    trigger_run_denied = trigger_run_id in denied
    trigger_run_not_allowed = bool(allowed) and trigger_run_id not in allowed
    passed = not (denied_observed or outside_allowlist or trigger_run_denied or trigger_run_not_allowed)
    return {
        "configured": bool(allowed or denied),
        "allowed_source_run_ids": list(allowed),
        "denied_source_run_ids": list(denied),
        "trigger_run_id": trigger_run_id,
        "trigger_run_denied": trigger_run_denied,
        "trigger_run_not_allowed": trigger_run_not_allowed,
        "observed_source_run_ids": by_source_run_id,
        "denied_observed_source_run_ids": denied_observed,
        "outside_allowlist_source_run_ids": outside_allowlist,
        "passed": passed,
    }


def summarize_period_trigger_baseline_trace(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    present_rows: list[Mapping[str, Any]] = []
    missing_rows: list[Mapping[str, Any]] = []
    null_count = 0
    empty_count = 0
    present_flag_true_count = 0
    present_flag_false_count = 0
    required_period_not_ready_count = 0
    baseline_versions: Counter[str] = Counter()
    by_trigger_period: Counter[str] = Counter()
    present_by_trigger_period: Counter[str] = Counter()
    missing_by_trigger_period: Counter[str] = Counter()
    for row in rows:
        payload = row.get("payload_json") or {}
        if not isinstance(payload, Mapping):
            payload = {}
        trigger_period = str(payload.get("trigger_period") or "")
        by_trigger_period[trigger_period] += 1
        trace = payload.get("period_trigger_baseline_trace")
        trace_is_present = isinstance(trace, Mapping) and bool(trace)
        if trace_is_present:
            present_rows.append(row)
            present_by_trigger_period[trigger_period] += 1
            if trace.get("present") is True:
                present_flag_true_count += 1
            if trace.get("present") is False:
                present_flag_false_count += 1
            version = str(trace.get("baseline_version") or "")
            if version:
                baseline_versions[version] += 1
            not_ready = trace.get("required_period_not_ready") or []
            if isinstance(not_ready, (list, tuple)):
                required_period_not_ready_count += len(not_ready)
        else:
            missing_rows.append(row)
            missing_by_trigger_period[trigger_period] += 1
            if trace is None:
                null_count += 1
            if trace == {}:
                empty_count += 1

    return {
        "row_count": len(rows),
        "present_count": len(present_rows),
        "missing_count": len(missing_rows),
        "null_count": null_count,
        "empty_object_count": empty_count,
        "present_flag_true_count": present_flag_true_count,
        "present_flag_false_count": present_flag_false_count,
        "required_period_not_ready_count": required_period_not_ready_count,
        "by_trigger_period": dict(sorted(by_trigger_period.items())),
        "present_by_trigger_period": dict(sorted(present_by_trigger_period.items())),
        "missing_by_trigger_period": dict(sorted(missing_by_trigger_period.items())),
        "baseline_versions": dict(sorted(baseline_versions.items())),
    }


def build_candidate_key_stability_recheck(
    accepted_rows: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    action_run_id: str,
    action_confirmation_metric_facts: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]] | None = None,
    action_confirmation_metric_facts_by_identity: Mapping[Any, Sequence[Mapping[str, Any]]] | None = None,
    full_candidate_count: int | None = None,
) -> dict[str, Any]:
    repeated = build_action_candidates_from_outbox_rows(
        accepted_rows,
        action_run_id=action_run_id,
        action_confirmation_metric_facts=action_confirmation_metric_facts,
        action_confirmation_metric_facts_by_identity=action_confirmation_metric_facts_by_identity,
    )
    original_pairs = [
        (
            str(row.get("source_trigger_event_id") or ""),
            str(row.get("action_key") or ""),
            str(row.get("dedup_key") or ""),
        )
        for row in candidates
    ]
    repeated_pairs = [
        (
            str(row.get("source_trigger_event_id") or ""),
            str(row.get("action_key") or ""),
            str(row.get("dedup_key") or ""),
        )
        for row in repeated
    ]
    action_keys = [pair[1] for pair in original_pairs]
    dedup_keys = [pair[2] for pair in original_pairs]
    return {
        "stable_on_recompute": original_pairs == repeated_pairs,
        "sampled_recheck": full_candidate_count is not None and full_candidate_count > len(original_pairs),
        "full_candidate_count": int(full_candidate_count if full_candidate_count is not None else len(original_pairs)),
        "action_key_equals_dedup_key_count": sum(1 for _, action_key, dedup_key in original_pairs if action_key == dedup_key),
        "candidate_count": len(original_pairs),
        "unique_action_key_count": len(set(action_keys)),
        "unique_dedup_key_count": len(set(dedup_keys)),
        "duplicate_action_key_count": len(action_keys) - len(set(action_keys)),
        "duplicate_dedup_key_count": len(dedup_keys) - len(set(dedup_keys)),
    }


def summarize_action_confirmation_metric_readiness(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    action_candidates = [row for row in candidates if row.get("candidate_kind") == "action_confirmation"]
    source_metric_rows = [row for row in action_candidates if row.get("source_action_confirmation_metric_id")]
    metric_fact_available = [row for row in source_metric_rows if row.get("action_confirmation_metric_fact_available")]
    return {
        "action_confirmation_candidate_count": len(action_candidates),
        "source_action_confirmation_metric_id_count": len(source_metric_rows),
        "metric_fact_available_count": len(metric_fact_available),
        "metric_fact_missing_count": len(source_metric_rows) - len(metric_fact_available),
        "by_metric_status": count_by(source_metric_rows, "action_confirmation_metric_status"),
        "by_metric_quality_status": count_by(source_metric_rows, "action_confirmation_metric_quality_status"),
        "all_period_confirmation_pass_count": sum(
            1 for row in source_metric_rows if row.get("action_confirmation_metric_all_period_pass")
        ),
        "all_period_confirmation_failed_count": sum(
            1
            for row in source_metric_rows
            if row.get("action_confirmation_metric_fact_available")
            and not row.get("action_confirmation_metric_all_period_pass")
        ),
    }


def compare_baseline_report(
    *,
    current_consumer_summary: Mapping[str, Any],
    current_outbox_summary: Mapping[str, Any],
    trigger_run_id: str,
    baseline_report: Mapping[str, Any] | None,
    baseline_report_path: str,
) -> dict[str, Any]:
    if not baseline_report:
        return {
            "baseline_report_path": baseline_report_path,
            "baseline_available": False,
            "explainable": False,
            "explanation": "baseline report is not available",
        }
    if "output_summary" in baseline_report and "run_id" in baseline_report:
        return compare_n4_execute_baseline(
            current_consumer_summary=current_consumer_summary,
            current_outbox_summary=current_outbox_summary,
            trigger_run_id=trigger_run_id,
            baseline_report=baseline_report,
            baseline_report_path=baseline_report_path,
        )
    if "execute_plan_summary" in baseline_report and "execute_run_id" in baseline_report:
        return compare_n4_projection_execute_preflight_baseline(
            current_consumer_summary=current_consumer_summary,
            current_outbox_summary=current_outbox_summary,
            trigger_run_id=trigger_run_id,
            baseline_report=baseline_report,
            baseline_report_path=baseline_report_path,
        )
    if "expected_writes" in baseline_report and "execute_run_id" in baseline_report:
        return compare_n4_action_confirmation_metric_baseline(
            current_consumer_summary=current_consumer_summary,
            current_outbox_summary=current_outbox_summary,
            trigger_run_id=trigger_run_id,
            baseline_report=baseline_report,
            baseline_report_path=baseline_report_path,
        )
    if (
        baseline_report.get("stage") == "N5_ACTION_PIPELINE_EXECUTE_CONTRACT_GATE"
        and "input_universe" in baseline_report
        and "dry_run_expectation" in baseline_report
    ):
        return compare_n5_action_pipeline_execute_contract_baseline(
            current_consumer_summary=current_consumer_summary,
            current_outbox_summary=current_outbox_summary,
            trigger_run_id=trigger_run_id,
            baseline_report=baseline_report,
            baseline_report_path=baseline_report_path,
        )
    if "summary" in baseline_report and "trigger_context_run_id" in baseline_report:
        return compare_n4_projection_matcher_baseline(
            current_consumer_summary=current_consumer_summary,
            current_outbox_summary=current_outbox_summary,
            trigger_run_id=trigger_run_id,
            baseline_report=baseline_report,
            baseline_report_path=baseline_report_path,
        )
    baseline_consumer = baseline_report.get("consumer_plan_summary") or {}
    baseline_outbox = baseline_report.get("outbox_summary") or {}
    current_read_count = int(current_consumer_summary.get("read_event_count") or 0)
    baseline_read_count = int(baseline_consumer.get("read_event_count") or 0)
    same_trigger_run = baseline_report.get("source_trigger_run_id") == trigger_run_id
    same_event_distribution = dict(current_outbox_summary.get("by_event_type") or {}) == dict(
        baseline_outbox.get("by_event_type") or {}
    )
    same_signal_distribution = dict(current_outbox_summary.get("by_signal_type") or {}) == dict(
        baseline_outbox.get("by_signal_type") or {}
    )
    explainable = same_trigger_run and current_read_count == baseline_read_count and same_event_distribution
    if explainable and same_signal_distribution:
        explanation = "N5-5 read_event_count and distributions match the N5-1 baseline for the same N4 run"
    elif explainable:
        explanation = "N5-5 read_event_count matches N5-1; signal distribution differs and is reported for review"
    else:
        explanation = "N5-5 read_event_count differs from N5-1 or uses a different trigger run"
    return {
        "baseline_report_path": baseline_report_path,
        "baseline_available": True,
        "baseline_stage": baseline_report.get("stage"),
        "same_trigger_run": same_trigger_run,
        "current_read_event_count": current_read_count,
        "baseline_read_event_count": baseline_read_count,
        "read_event_count_delta": current_read_count - baseline_read_count,
        "same_event_distribution": same_event_distribution,
        "same_signal_distribution": same_signal_distribution,
        "current_by_event_type": current_outbox_summary.get("by_event_type") or {},
        "baseline_by_event_type": baseline_outbox.get("by_event_type") or {},
        "current_by_signal_type": current_outbox_summary.get("by_signal_type") or {},
        "baseline_by_signal_type": baseline_outbox.get("by_signal_type") or {},
        "explainable": explainable,
        "explanation": explanation,
    }


def compare_n5_action_pipeline_execute_contract_baseline(
    *,
    current_consumer_summary: Mapping[str, Any],
    current_outbox_summary: Mapping[str, Any],
    trigger_run_id: str,
    baseline_report: Mapping[str, Any],
    baseline_report_path: str,
) -> dict[str, Any]:
    input_universe = baseline_report.get("input_universe") or {}
    expectation = baseline_report.get("dry_run_expectation") or {}
    expected_read_count = int(
        input_universe.get("n4_eligible_trigger_matched")
        or expectation.get("input_universe")
        or 0
    )
    expected_by_event_type = {"TriggerMatched": expected_read_count} if expected_read_count else {}
    expected_by_signal_type = dict(expectation.get("signal_type_distribution") or {})
    current_read_count = int(current_consumer_summary.get("read_event_count") or 0)
    same_trigger_run = baseline_report.get("source_trigger_run_id") == trigger_run_id
    same_event_distribution = dict(current_outbox_summary.get("by_event_type") or {}) == expected_by_event_type
    same_signal_distribution = dict(current_outbox_summary.get("by_signal_type") or {}) == expected_by_signal_type
    explainable = same_trigger_run and current_read_count == expected_read_count and same_event_distribution
    if explainable and same_signal_distribution:
        explanation = "N5 action pipeline read_event_count and distributions match the reviewed execute contract"
    elif explainable:
        explanation = "N5 action pipeline read_event_count matches the reviewed execute contract; signal distribution differs and is reported for review"
    else:
        explanation = "N5 action pipeline read_event_count differs from the reviewed execute contract or uses a different trigger run"
    return {
        "baseline_report_path": baseline_report_path,
        "baseline_available": True,
        "baseline_stage": baseline_report.get("stage"),
        "baseline_kind": "N5_action_pipeline_execute_contract",
        "same_trigger_run": same_trigger_run,
        "current_read_event_count": current_read_count,
        "baseline_read_event_count": expected_read_count,
        "read_event_count_delta": current_read_count - expected_read_count,
        "same_event_distribution": same_event_distribution,
        "same_signal_distribution": same_signal_distribution,
        "current_by_event_type": current_outbox_summary.get("by_event_type") or {},
        "baseline_by_event_type": expected_by_event_type,
        "current_by_signal_type": current_outbox_summary.get("by_signal_type") or {},
        "baseline_by_signal_type": expected_by_signal_type,
        "explainable": explainable,
        "explanation": explanation,
    }


def compare_n4_execute_baseline(
    *,
    current_consumer_summary: Mapping[str, Any],
    current_outbox_summary: Mapping[str, Any],
    trigger_run_id: str,
    baseline_report: Mapping[str, Any],
    baseline_report_path: str,
) -> dict[str, Any]:
    output_summary = baseline_report.get("output_summary") or {}
    expected_by_event_type = dict(output_summary.get("outbox_by_event_type") or {})
    expected_by_signal_type = dict(output_summary.get("match_by_signal_type") or {})
    expected_read_count = int(
        output_summary.get("outbox_count")
        or sum(int(value or 0) for value in expected_by_event_type.values())
        or 0
    )
    current_read_count = int(current_consumer_summary.get("read_event_count") or 0)
    same_trigger_run = baseline_report.get("run_id") == trigger_run_id
    same_event_distribution = dict(current_outbox_summary.get("by_event_type") or {}) == expected_by_event_type
    same_signal_distribution = dict(current_outbox_summary.get("by_signal_type") or {}) == expected_by_signal_type
    explainable = same_trigger_run and current_read_count == expected_read_count and same_event_distribution
    if explainable and same_signal_distribution:
        explanation = "N5 dry-run read_event_count and distributions match the N4 execute report for the same run"
    elif explainable:
        explanation = "N5 dry-run read_event_count matches N4 execute report; signal distribution differs and is reported for review"
    else:
        explanation = "N5 dry-run read_event_count differs from N4 execute report or uses a different trigger run"
    return {
        "baseline_report_path": baseline_report_path,
        "baseline_available": True,
        "baseline_stage": baseline_report.get("stage"),
        "baseline_kind": "N4_execute_report",
        "same_trigger_run": same_trigger_run,
        "current_read_event_count": current_read_count,
        "baseline_read_event_count": expected_read_count,
        "read_event_count_delta": current_read_count - expected_read_count,
        "same_event_distribution": same_event_distribution,
        "same_signal_distribution": same_signal_distribution,
        "current_by_event_type": current_outbox_summary.get("by_event_type") or {},
        "baseline_by_event_type": expected_by_event_type,
        "current_by_signal_type": current_outbox_summary.get("by_signal_type") or {},
        "baseline_by_signal_type": expected_by_signal_type,
        "explainable": explainable,
        "explanation": explanation,
    }


def compare_n4_projection_matcher_baseline(
    *,
    current_consumer_summary: Mapping[str, Any],
    current_outbox_summary: Mapping[str, Any],
    trigger_run_id: str,
    baseline_report: Mapping[str, Any],
    baseline_report_path: str,
) -> dict[str, Any]:
    summary = baseline_report.get("summary") or {}
    expected_by_event_type = {
        "TriggerMatched": int(summary.get("matched_count") or 0),
        "TriggerPendingMarketData": int(summary.get("pending_count") or 0),
    }
    expected_by_signal_type: dict[str, int] = {}
    for signal_type, count in dict(summary.get("matched_by_signal_type") or {}).items():
        expected_by_signal_type[str(signal_type)] = expected_by_signal_type.get(str(signal_type), 0) + int(count or 0)
    for signal_type, count in dict(summary.get("pending_by_signal_type") or {}).items():
        expected_by_signal_type[str(signal_type)] = expected_by_signal_type.get(str(signal_type), 0) + int(count or 0)
    expected_read_count = sum(expected_by_event_type.values())
    current_read_count = int(current_consumer_summary.get("read_event_count") or 0)
    same_trigger_run = (
        baseline_report.get("execute_run_id") == trigger_run_id
        or baseline_report.get("run_id") == trigger_run_id
    )
    same_event_distribution = dict(current_outbox_summary.get("by_event_type") or {}) == expected_by_event_type
    same_signal_distribution = dict(current_outbox_summary.get("by_signal_type") or {}) == expected_by_signal_type
    explainable = same_trigger_run and current_read_count == expected_read_count and same_event_distribution
    if explainable and same_signal_distribution:
        explanation = "N5 current-real dry-run read_event_count and distributions match the N4 projection matcher report"
    elif explainable:
        explanation = "N5 current-real dry-run read_event_count matches N4 projection matcher report; signal distribution differs and is reported for review"
    else:
        explanation = "N5 current-real dry-run read_event_count differs from N4 projection matcher report or uses a different trigger run"
    return {
        "baseline_report_path": baseline_report_path,
        "baseline_available": True,
        "baseline_stage": baseline_report.get("stage"),
        "baseline_kind": "N4_projection_matcher_report",
        "same_trigger_run": same_trigger_run,
        "current_read_event_count": current_read_count,
        "baseline_read_event_count": expected_read_count,
        "read_event_count_delta": current_read_count - expected_read_count,
        "same_event_distribution": same_event_distribution,
        "same_signal_distribution": same_signal_distribution,
        "current_by_event_type": current_outbox_summary.get("by_event_type") or {},
        "baseline_by_event_type": expected_by_event_type,
        "current_by_signal_type": current_outbox_summary.get("by_signal_type") or {},
        "baseline_by_signal_type": dict(sorted(expected_by_signal_type.items())),
        "explainable": explainable,
        "explanation": explanation,
    }


def compare_n4_projection_execute_preflight_baseline(
    *,
    current_consumer_summary: Mapping[str, Any],
    current_outbox_summary: Mapping[str, Any],
    trigger_run_id: str,
    baseline_report: Mapping[str, Any],
    baseline_report_path: str,
) -> dict[str, Any]:
    summary = baseline_report.get("execute_plan_summary") or {}
    expected_by_event_type = {
        "TriggerMatched": int(summary.get("matched_output_count") or 0),
        "TriggerPendingMarketData": int(summary.get("pending_output_count") or 0),
    }
    expected_by_signal_type: dict[str, int] = {}
    for signal_type, count in dict(summary.get("matched_by_signal_type") or {}).items():
        expected_by_signal_type[str(signal_type)] = expected_by_signal_type.get(str(signal_type), 0) + int(count or 0)
    for signal_type, count in dict(summary.get("pending_by_signal_type") or {}).items():
        expected_by_signal_type[str(signal_type)] = expected_by_signal_type.get(str(signal_type), 0) + int(count or 0)
    expected_read_count = int(summary.get("trigger_output_plan_count") or sum(expected_by_event_type.values()))
    current_read_count = int(current_consumer_summary.get("read_event_count") or 0)
    same_trigger_run = baseline_report.get("execute_run_id") == trigger_run_id
    same_event_distribution = dict(current_outbox_summary.get("by_event_type") or {}) == expected_by_event_type
    same_signal_distribution = dict(current_outbox_summary.get("by_signal_type") or {}) == expected_by_signal_type
    explainable = same_trigger_run and current_read_count == expected_read_count and same_event_distribution
    if explainable and same_signal_distribution:
        explanation = "N5 current-real dry-run read_event_count and distributions match the N4 projection matcher execute preflight"
    elif explainable:
        explanation = "N5 current-real dry-run read_event_count matches N4 projection matcher execute preflight; signal distribution differs and is reported for review"
    else:
        explanation = "N5 current-real dry-run read_event_count differs from N4 projection matcher execute preflight or uses a different trigger run"
    return {
        "baseline_report_path": baseline_report_path,
        "baseline_available": True,
        "baseline_stage": baseline_report.get("stage"),
        "baseline_kind": "N4_projection_matcher_execute_preflight",
        "same_trigger_run": same_trigger_run,
        "current_read_event_count": current_read_count,
        "baseline_read_event_count": expected_read_count,
        "read_event_count_delta": current_read_count - expected_read_count,
        "same_event_distribution": same_event_distribution,
        "same_signal_distribution": same_signal_distribution,
        "current_by_event_type": current_outbox_summary.get("by_event_type") or {},
        "baseline_by_event_type": expected_by_event_type,
        "current_by_signal_type": current_outbox_summary.get("by_signal_type") or {},
        "baseline_by_signal_type": dict(sorted(expected_by_signal_type.items())),
        "explainable": explainable,
        "explanation": explanation,
    }


def compare_n4_action_confirmation_metric_baseline(
    *,
    current_consumer_summary: Mapping[str, Any],
    current_outbox_summary: Mapping[str, Any],
    trigger_run_id: str,
    baseline_report: Mapping[str, Any],
    baseline_report_path: str,
) -> dict[str, Any]:
    expected_writes = dict(baseline_report.get("expected_writes") or {})
    expected_by_event_type = {
        "TriggerMatched": int(expected_writes.get("TriggerMatched") or 0),
        "TriggerPendingMarketData": int(expected_writes.get("TriggerPendingMarketData") or 0),
    }
    state_changed_count = int(expected_writes.get("TriggerStateChanged") or 0)
    if state_changed_count:
        expected_by_event_type["TriggerStateChanged"] = state_changed_count
    expected_read_count = int(
        expected_writes.get("common_event_outbox")
        or sum(expected_by_event_type.values())
        or 0
    )
    current_read_count = int(current_consumer_summary.get("read_event_count") or 0)
    same_trigger_run = baseline_report.get("execute_run_id") == trigger_run_id
    same_event_distribution = dict(current_outbox_summary.get("by_event_type") or {}) == expected_by_event_type
    explainable = same_trigger_run and current_read_count == expected_read_count and same_event_distribution
    explanation = (
        "N5 action-confirmation metric dry-run read_event_count and distributions match the N4 metric execute contract"
        if explainable
        else "N5 action-confirmation metric dry-run read_event_count differs from N4 metric execute contract or uses a different run"
    )
    return {
        "baseline_report_path": baseline_report_path,
        "baseline_available": True,
        "baseline_kind": "N4_action_confirmation_metric_contract",
        "same_trigger_run": same_trigger_run,
        "current_read_event_count": current_read_count,
        "baseline_read_event_count": expected_read_count,
        "read_event_count_delta": current_read_count - expected_read_count,
        "same_event_distribution": same_event_distribution,
        "same_signal_distribution": True,
        "current_by_event_type": current_outbox_summary.get("by_event_type") or {},
        "baseline_by_event_type": expected_by_event_type,
        "current_by_signal_type": current_outbox_summary.get("by_signal_type") or {},
        "baseline_by_signal_type": current_outbox_summary.get("by_signal_type") or {},
        "explainable": explainable,
        "explanation": explanation,
    }

def build_quality_items(
    *,
    trigger_run_id: str,
    consumer_name: str,
    trigger_run: Mapping[str, Any],
    outbox_summary: Mapping[str, Any],
    source_run_id_summary: Mapping[str, Any],
    period_trigger_baseline_trace_summary: Mapping[str, Any],
    consumer_summary: Mapping[str, Any],
    candidate_summary: Mapping[str, Any],
    action_write_plan_summary: Mapping[str, Any],
    output_event_plan_summary: Mapping[str, Any],
    baseline_comparison: Mapping[str, Any],
    consumer_guard: Mapping[str, Any],
    candidate_key_recheck: Mapping[str, Any],
    source_run_guard: Mapping[str, Any],
    expected_read_event_count: int | None,
    require_period_trigger_baseline_trace: bool,
    before_row_counts: Mapping[str, Mapping[str, Any]],
    after_row_counts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    row_counts_unchanged = before_row_counts == after_row_counts
    guarded_action_counts_unchanged = counts_equal(before_row_counts, after_row_counts, ACTION_EVENT_GUARD_TABLES)
    n5_tables_exist = all(
        (before_row_counts.get(table_name) or {}).get("exists") is True
        for table_name in ACTION_EVENT_GUARD_TABLES
    )
    items = [
        quality_item(
            "P0",
            "passed" if consumer_guard.get("passed") else "failed",
            "n5_5_consumer_name_contract",
            "N5-5 must use the default consumer or an explicitly declared empty dedicated reprocess consumer",
            expected=str(consumer_guard.get("expected_consumer_name") or DEFAULT_N5_1_CONSUMER_NAME),
            actual=json.dumps(
                {
                    "consumer_name": consumer_name,
                    "strategy": consumer_guard.get("strategy"),
                    "blockers": consumer_guard.get("blockers") or [],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        quality_item(
            "P0",
            "passed" if trigger_run.get("run_id") == trigger_run_id else "failed",
            "n5_5_source_trigger_run_found",
            "N5-5 must read the requested N4 trigger run as upstream metadata",
            expected=trigger_run_id,
            actual=str(trigger_run.get("run_id") or ""),
        ),
        quality_item(
            "P0",
            "passed" if int(outbox_summary.get("outbox_row_count") or 0) > 0 else "failed",
            "n5_5_n4_outbox_available",
            "N5-5 must read N4 standard outbox rows",
            expected=">0",
            actual=str(outbox_summary.get("outbox_row_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if source_run_id_summary.get("only_expected_source_run_id") else "failed",
            "n5_run_once_only_requested_source_run_id",
            "N5 run-once dry-run must read only the requested N4 source_run_id",
            expected=trigger_run_id,
            actual=json.dumps(source_run_id_summary.get("by_source_run_id") or {}, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed"
            if expected_read_event_count is None
            or int(consumer_summary.get("read_event_count") or 0) == expected_read_event_count
            else "failed",
            "n5_run_once_expected_read_event_count",
            "N5 run-once dry-run read_event_count must match the requested expected count when provided",
            expected=str(expected_read_event_count) if expected_read_event_count is not None else "not enforced",
            actual=str(consumer_summary.get("read_event_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if not outbox_summary.get("disallowed_event_types") else "failed",
            "n5_5_only_standard_n4_events",
            "N5-5 input must be TriggerMatched, TriggerPendingMarketData, or TriggerStateChanged",
            expected=",".join(ALLOWED_N4_INPUT_EVENT_TYPES),
            actual=",".join(outbox_summary.get("by_event_type", {}).keys()),
        ),
        quality_item(
            "P0" if require_period_trigger_baseline_trace else "P2",
            "passed"
            if not require_period_trigger_baseline_trace
            or int(period_trigger_baseline_trace_summary.get("missing_count") or 0) == 0
            else "failed",
            "n5_run_once_period_trigger_baseline_trace_present",
            "N5 run-once dry-run must preserve period_trigger_baseline_trace statistics from N4 payload",
            expected="missing_count=0" if require_period_trigger_baseline_trace else "reported",
            actual=(
                f"present={period_trigger_baseline_trace_summary.get('present_count') or 0} "
                f"missing={period_trigger_baseline_trace_summary.get('missing_count') or 0}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if baseline_comparison.get("explainable") else "failed",
            "n5_5_read_event_count_matches_n5_1_baseline",
            "N5-5 read_event_count must be explainable against the N5-1 baseline",
            expected="explainable",
            actual=str(baseline_comparison.get("explanation") or ""),
        ),
        quality_item(
            "P0",
            "passed"
            if int(consumer_summary.get("planned_receive_count") or 0)
            + int(consumer_summary.get("skipped_count") or 0)
            == int(consumer_summary.get("read_event_count") or 0)
            else "failed",
            "n5_5_consumer_plan_accounts_for_all_events",
            "N5-5 consumer plan must account for every read event",
            expected=str(consumer_summary.get("read_event_count") or 0),
            actual=str(int(consumer_summary.get("planned_receive_count") or 0) + int(consumer_summary.get("skipped_count") or 0)),
        ),
        quality_item(
            "P0",
            "passed"
            if int(consumer_summary.get("planned_receive_count") or 0)
            == int(candidate_summary.get("candidate_count") or 0)
            else "failed",
            "n5_5_accepted_events_map_to_candidates",
            "Every accepted N4 event must map to an N5 dry-run candidate or quality plan",
            expected=str(consumer_summary.get("planned_receive_count") or 0),
            actual=str(candidate_summary.get("candidate_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if int(candidate_summary.get("trigger_matched_action_candidate_count") or 0) > 0 else "failed",
            "n5_5_trigger_matched_generates_action_candidate",
            "TriggerMatched must generate action candidates",
            expected=">0",
            actual=str(candidate_summary.get("trigger_matched_action_candidate_count") or 0),
        ),
        quality_item(
            "P0",
            "passed"
            if int(action_write_plan_summary.get("pending_action_fact_plan_count") or 0) == 0
            else "failed",
            "n5_5_pending_market_data_no_action_fact",
            "TriggerPendingMarketData must not generate action fact write plans",
            expected="0",
            actual=str(action_write_plan_summary.get("pending_action_fact_plan_count") or 0),
        ),
        quality_item(
            "P0",
            "passed"
            if int(candidate_summary.get("deprecated_runtime_signal_type_count") or 0) == 0
            and int(action_write_plan_summary.get("deprecated_runtime_signal_type_action_fact_count") or 0) == 0
            else "failed",
            "n5_5_runtime_signal_type_canonical",
            "N5 runtime signal_type must be B_BUY or S_SELL; BUY_HINT/SELL_HINT stay in condition trace only",
            expected="deprecated runtime signal count=0",
            actual=(
                f"candidate={candidate_summary.get('deprecated_runtime_signal_type_count') or 0} "
                f"planned_fact={action_write_plan_summary.get('deprecated_runtime_signal_type_action_fact_count') or 0}"
            ),
        ),
        quality_item(
            "P0",
            "passed"
            if int(candidate_summary.get("deprecated_hint_event_plan_count") or 0) == 0
            else "failed",
            "n5_5_buy_sell_hint_trace_only_no_hint_event",
            "BUY_HINT and SELL_HINT must remain condition trace only and must not plan legacy hint events",
            expected="deprecated_hint_event_plan_count=0",
            actual=(
                f"BUY_HINT_trace={candidate_summary.get('buy_hint_trace_count') or 0} "
                f"SELL_HINT_trace={candidate_summary.get('sell_hint_trace_count') or 0} "
                f"legacy_hint_event_plan={candidate_summary.get('deprecated_hint_event_plan_count') or 0}"
            ),
        ),
        quality_item(
            "P0",
            "passed"
            if candidate_key_recheck.get("stable_on_recompute")
            and int(candidate_key_recheck.get("duplicate_action_key_count") or 0) == 0
            and int(candidate_key_recheck.get("duplicate_dedup_key_count") or 0) == 0
            else "failed",
            "n5_5_action_key_dedup_key_stable",
            "N5-5 action_key and dedup_key must be stable and unique in the dry-run plan",
            expected="stable unique keys",
            actual=json.dumps(candidate_key_recheck, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed"
            if int(action_write_plan_summary.get("duplicate_source_trigger_match_id_planned_count") or 0) == 0
            and int(action_write_plan_summary.get("missing_source_trigger_match_id_skipped_count") or 0) == 0
            else "failed",
            "n5_5_source_trigger_match_id_idempotent",
            "N5-5 must not plan duplicate ordinary action facts for the same source_trigger_match_id",
            expected="0 duplicate ordinary planned match ids and 0 missing match-id skips",
            actual=(
                f"duplicate_planned={action_write_plan_summary.get('duplicate_source_trigger_match_id_planned_count') or 0} "
                f"missing_skipped={action_write_plan_summary.get('missing_source_trigger_match_id_skipped_count') or 0} "
                f"multi_action_trigger_count={action_write_plan_summary.get('multi_action_trigger_count') or 0} "
                f"executed_metric_count={action_write_plan_summary.get('executed_metric_count') or 0}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if int(action_write_plan_summary.get("physical_split_error_count") or 0) == 0 else "failed",
            "n5_5_physical_action_fact_split_plan",
            "N5-5 action fact plan must target stock/index/board physical tables by asset_kind",
            expected="0 physical split errors",
            actual=str(action_write_plan_summary.get("physical_split_error_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if not output_event_plan_summary.get("missing_event_types") else "failed",
            "n5_5_output_event_plan_contract_complete",
            "N5-5 output event plan must include ActionEligible, ActionBlocked, ActionExecuted, and ActionSkipped",
            expected=",".join(N5_OUTPUT_EVENT_TYPES),
            actual=",".join(output_event_plan_summary.get("event_types_in_plan") or []),
        ),
        quality_item(
            "P0",
            "passed" if not output_event_plan_summary.get("common_event_outbox_written") else "failed",
            "n5_5_output_event_plan_not_written",
            "N5-5 may plan N5 output events but must not write N5 outbox rows",
            expected="common_event_outbox_written=false",
            actual=str(output_event_plan_summary.get("common_event_outbox_written")),
        ),
        quality_item(
            "P0",
            "passed" if n5_tables_exist else "failed",
            "n5_5_n5_target_tables_exist_for_dry_run_guard",
            "N5-5 must guard the migrated N5 tables before and after dry-run",
            expected="all N5 action/event/position tables exist",
            actual=json.dumps({table: before_row_counts.get(table) for table in ACTION_EVENT_GUARD_TABLES}, ensure_ascii=False, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n5_5_database_row_counts_unchanged",
            "N5-5 run-once dry-run must keep guarded table row counts unchanged",
            expected="before row counts equal after row counts",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item(
            "P0",
            "passed" if guarded_action_counts_unchanged else "failed",
            "n5_5_no_inbox_checkpoint_action_event_fact_update",
            "N5-5 must not update inbox, checkpoint, action facts, action events, or position tables",
            expected="unchanged",
            actual="unchanged" if guarded_action_counts_unchanged else "changed",
        ),
        quality_item(
            "P0",
            "passed" if int(action_write_plan_summary.get("executed_count") or 0) == 0 else "failed",
            "n5_5_action_write_plan_not_executed",
            "N5-5 must not execute the action write plan",
            expected="0",
            actual=str(action_write_plan_summary.get("executed_count") or 0),
        ),
        quality_item("P0", "passed", "n5_5_no_n4_mutation", "N5-5 does not consume or mutate N4 outbox"),
        quality_item("P0", "passed", "n5_5_no_market_data_pull", "N5-5 does not pull market data"),
        quality_item("P0", "passed", "n5_5_no_user_voice_sim_mobile_trade", "N5-5 does not enter N6, voice, sim, mobile, or true trade"),
        quality_item("P0", "passed", "n5_5_no_worker", "N5-5 does not start workers"),
        quality_item("P0", "passed", "n5_5_no_old_system_touch", "N5-5 does not touch old system"),
        quality_item(
            "P2",
            "warning" if int(outbox_summary.get("synthetic_sample_event_count") or 0) > 0 else "passed",
            "n5_5_source_outbox_is_synthetic_sample",
            "Current N4 outbox is synthetic/sample run-once material for N5 development only",
            expected="development sample noted",
            actual=str(outbox_summary.get("synthetic_sample_event_count") or 0),
        ),
    ]
    if source_run_guard.get("configured"):
        items.insert(
            4,
            quality_item(
                "P0",
                "passed" if source_run_guard.get("passed") else "failed",
                "n5_current_real_source_run_allowlist_denylist",
                "N5 current-real dry-run must accept only the current real N4 source_run_id and reject synthetic denylist runs",
                expected=json.dumps(
                    {
                        "allowed": source_run_guard.get("allowed_source_run_ids") or [],
                        "denied": source_run_guard.get("denied_source_run_ids") or [],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                actual=json.dumps(
                    {
                        "trigger_run_id": source_run_guard.get("trigger_run_id"),
                        "observed": source_run_guard.get("observed_source_run_ids") or {},
                        "denied_observed": source_run_guard.get("denied_observed_source_run_ids") or [],
                        "outside_allowlist": source_run_guard.get("outside_allowlist_source_run_ids") or [],
                        "trigger_run_denied": source_run_guard.get("trigger_run_denied"),
                        "trigger_run_not_allowed": source_run_guard.get("trigger_run_not_allowed"),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )
    return items


def count_physical_split_errors(planned_rows: Sequence[Mapping[str, Any]]) -> int:
    errors = 0
    for row in planned_rows:
        asset_kind = str(row.get("asset_kind") or "")
        if row.get("target_action_fact_table") != ACTION_FACT_TABLE_BY_ASSET_KIND.get(asset_kind):
            errors += 1
    return errors


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def count_skip_reasons(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for reason in row.get("skip_reasons") or []:
            counter[str(reason)] += 1
    return dict(sorted(counter.items()))


def counts_equal(
    before_counts: Mapping[str, Mapping[str, Any]],
    after_counts: Mapping[str, Mapping[str, Any]],
    table_names: Sequence[str],
) -> bool:
    return all(before_counts.get(table_name) == after_counts.get(table_name) for table_name in table_names)


def normalize_match_id(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def infer_trade_date(rows: Sequence[Mapping[str, Any]]) -> str | None:
    for row in rows:
        trade_date = row.get("trade_date")
        if trade_date:
            return str(trade_date)
    return None


def load_baseline_report(path: str) -> dict[str, Any] | None:
    target = Path(path)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def format_action_consumer_run_once_dry_run_report(report: Mapping[str, Any]) -> str:
    outbox = report["outbox_summary"]
    source_run = report["source_run_id_summary"]
    trace = report["period_trigger_baseline_trace_summary"]
    consumer = report["consumer_plan_summary"]
    candidates = report["action_candidate_summary"]
    action_plan = report["action_write_plan_summary"]
    output_plan = report["output_event_plan_summary"]
    baseline = report["baseline_comparison"]
    source_guard = report.get("source_run_guard") or {}
    quality = report["quality"]
    side_effects = report["side_effects"]
    return "\n".join(
        [
            f"# {report['stage']} Action Consumer Run-Once Dry-Run Report",
            "",
            "## Summary",
            "",
            f"- stage: {report['stage']}",
            f"- layer_role: {report['layer_role']}",
            f"- consumer_name: {report['consumer_name']}",
            f"- source_trigger_run_id: {report['source_trigger_run_id']}",
            f"- action_run_id: {report['action_run_id']}",
            f"- for_trade_date: {report.get('for_trade_date')}",
            f"- rollback_sql_path: {report.get('rollback_sql_path')}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            f"- passed: {report['passed']}",
            "",
            "## Source Run Guard",
            "",
            f"- configured: {source_guard.get('configured')}",
            f"- passed: {source_guard.get('passed')}",
            f"- allowed_source_run_ids: {source_guard.get('allowed_source_run_ids')}",
            f"- denied_source_run_ids: {source_guard.get('denied_source_run_ids')}",
            f"- denied_observed_source_run_ids: {source_guard.get('denied_observed_source_run_ids')}",
            f"- outside_allowlist_source_run_ids: {source_guard.get('outside_allowlist_source_run_ids')}",
            "",
            "## Baseline Check",
            "",
            f"- baseline_report_path: {baseline['baseline_report_path']}",
            f"- baseline_available: {baseline['baseline_available']}",
            f"- explainable: {baseline['explainable']}",
            f"- current_read_event_count: {baseline.get('current_read_event_count')}",
            f"- baseline_read_event_count: {baseline.get('baseline_read_event_count')}",
            f"- read_event_count_delta: {baseline.get('read_event_count_delta')}",
            f"- explanation: {baseline['explanation']}",
            "",
            "## N4 Outbox Statistics",
            "",
            f"- outbox_row_count: {outbox['outbox_row_count']}",
            f"- source_run_id: {source_run['by_source_run_id']}",
            f"- only_expected_source_run_id: {source_run['only_expected_source_run_id']}",
            f"- unexpected_source_run_id_count: {source_run['unexpected_source_run_id_count']}",
            f"- by_event_type: {outbox['by_event_type']}",
            f"- by_signal_type: {outbox['by_signal_type']}",
            f"- by_asset_kind: {outbox['by_asset_kind']}",
            f"- by_direction: {outbox['by_direction']}",
            f"- TriggerMatched: {outbox['matched_count']}",
            f"- TriggerPendingMarketData: {outbox['pending_count']}",
            f"- TriggerStateChanged: {outbox['state_changed_count']}",
            f"- BUY_HINT runtime signal matched/pending/total: {outbox['buy_hint_matched_count']}/{outbox['buy_hint_pending_count']}/{outbox['buy_hint_count']}",
            f"- SELL_HINT runtime signal matched/pending/total: {outbox['sell_hint_matched_count']}/{outbox['sell_hint_pending_count']}/{outbox['sell_hint_count']}",
            f"- BUY_HINT trace matched/pending/total: {outbox.get('buy_hint_trace_matched_count')}/{outbox.get('buy_hint_trace_pending_count')}/{outbox.get('buy_hint_trace_count')}",
            f"- SELL_HINT trace matched/pending/total: {outbox.get('sell_hint_trace_matched_count')}/{outbox.get('sell_hint_trace_pending_count')}/{outbox.get('sell_hint_trace_count')}",
            "",
            "## Period Trigger Baseline Trace",
            "",
            f"- present_count: {trace['present_count']}",
            f"- missing_count: {trace['missing_count']}",
            f"- null_count: {trace['null_count']}",
            f"- empty_object_count: {trace['empty_object_count']}",
            f"- present_flag_true_count: {trace['present_flag_true_count']}",
            f"- present_flag_false_count: {trace['present_flag_false_count']}",
            f"- required_period_not_ready_count: {trace['required_period_not_ready_count']}",
            f"- by_trigger_period: {trace['by_trigger_period']}",
            f"- present_by_trigger_period: {trace['present_by_trigger_period']}",
            f"- missing_by_trigger_period: {trace['missing_by_trigger_period']}",
            f"- baseline_versions: {trace['baseline_versions']}",
            "",
            "## Consumer Plan",
            "",
            f"- read_event_count: {consumer['read_event_count']}",
            f"- planned_receive_count: {consumer['planned_receive_count']}",
            f"- skipped_count: {consumer['skipped_count']}",
            f"- ordering: {consumer['ordering']}",
            f"- partition_count: {consumer['partition_count']}",
            f"- checkpoint_write_plan_count: {consumer['checkpoint_write_plan_count']}",
            f"- would_insert_inbox_count: {consumer['would_insert_inbox_count']}",
            f"- would_update_checkpoint_count: {consumer['would_update_checkpoint_count']}",
            f"- would_consume_outbox_count: {consumer['would_consume_outbox_count']}",
            "",
            "## Action Write Plan",
            "",
            f"- candidate_count: {candidates['candidate_count']}",
            f"- action_candidate_count: {candidates['action_candidate_count']}",
            f"- quality_plan_count: {candidates['quality_plan_count']}",
            f"- planned_action_fact_count: {action_plan['planned_action_fact_count']}",
            f"- quality_plan_only_count: {action_plan['quality_plan_only_count']}",
            f"- by_target_action_fact_table: {action_plan['by_target_action_fact_table']}",
            f"- planned_action_fact_by_signal_type: {action_plan['planned_action_fact_by_signal_type']}",
            f"- planned_action_fact_by_direction: {action_plan['planned_action_fact_by_direction']}",
            f"- action_state: {candidates.get('by_action_state')}",
            f"- confirmation_status: {candidates.get('by_confirmation_status')}",
            f"- BUY_HINT planned action fact count: {action_plan['buy_hint_planned_action_fact_count']}",
            f"- SELL_HINT planned action fact count: {action_plan['sell_hint_planned_action_fact_count']}",
            f"- BUY_HINT trace count: {candidates.get('buy_hint_trace_count')}",
            f"- SELL_HINT trace count: {candidates.get('sell_hint_trace_count')}",
            f"- deprecated_runtime_signal_type_count: {candidates.get('deprecated_runtime_signal_type_count')}",
            f"- deprecated_hint_event_plan_count: {candidates.get('deprecated_hint_event_plan_count')}",
            f"- pending_action_fact_plan_count: {action_plan['pending_action_fact_plan_count']}",
            f"- duplicate_source_trigger_match_id_skipped_count: {action_plan['duplicate_source_trigger_match_id_skipped_count']}",
            f"- duplicate_source_trigger_match_id_planned_count: {action_plan['duplicate_source_trigger_match_id_planned_count']}",
            f"- physical_split_error_count: {action_plan['physical_split_error_count']}",
            "",
            "## N5 Output Event Plan",
            "",
            f"- event_type_contract: {output_plan['event_type_contract']}",
            f"- by_event_type: {output_plan['by_event_type']}",
            f"- planned_event_count: {output_plan['planned_event_count']}",
            f"- common_event_outbox_written: {output_plan['common_event_outbox_written']}",
            f"- executed_count: {output_plan['executed_count']}",
            "",
            "## Row Count Guards",
            "",
            f"- before_row_counts: {report['before_row_counts']}",
            f"- after_row_counts: {report['after_row_counts']}",
            "",
            "## Boundary Confirmation",
            "",
            f"- writes_performed: {side_effects['writes_performed']}",
            f"- common_event_inbox_updated: {side_effects['common_event_inbox_updated']}",
            f"- consumer_checkpoint_updated: {side_effects['consumer_checkpoint_updated']}",
            f"- action_fact_written: {side_effects['action_fact_written']}",
            f"- action_event_written: {side_effects['action_event_written']}",
            f"- common_event_outbox_written: {side_effects['common_event_outbox_written']}",
            f"- n5_outbox_written: {side_effects['n5_outbox_written']}",
            f"- n4_outbox_consumed: {side_effects['n4_outbox_consumed']}",
            f"- market_data_pulled: {side_effects['market_data_pulled']}",
            f"- n1_n2_n3_n4_modified: {side_effects['n1_n2_n3_n4_modified']}",
            f"- n6_user_layer_touched: {side_effects['n6_user_layer_touched']}",
            f"- voice_touched: {side_effects['voice_touched']}",
            f"- sim_touched: {side_effects['sim_touched']}",
            f"- mobile_touched: {side_effects['mobile_touched']}",
            f"- real_trade_touched: {side_effects['real_trade_touched']}",
            f"- worker_started: {side_effects['worker_started']}",
            f"- old_system_touched: {side_effects['old_system_touched']}",
            "",
            "## Notes",
            "",
            "- This report is a run-once dry-run only. It plans action writes but executes none of them.",
            "- Canonical mode accepts only B_BUY / S_SELL as runtime signal_type.",
            "- BUY_HINT / SELL_HINT are condition trace only and do not map to legacy hint events in N5 canonical runtime.",
            "- Source-run allowlist and historical synthetic/current-real denylist are enforced by this gate.",
        ]
    )
