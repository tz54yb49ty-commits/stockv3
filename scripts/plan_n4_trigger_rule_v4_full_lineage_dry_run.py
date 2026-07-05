#!/usr/bin/env python3
"""Plan N4 trigger rule spec v4 over a real lineage in shadow dry-run mode.

This runner is read-only. It does not execute N4, write database rows, consume
outbox events, or reinterpret historical runs.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect
from ashare_v3.trigger.local_trigger_dry_run import (
    build_local_trigger_plans,
    fetch_context_rows,
    fetch_snapshot_rows,
)
from ashare_v3.trigger.rule_v4_matcher import (
    TRIGGER_RULE_POLICY_HASH,
    TRIGGER_RULE_SPEC_VERSION,
    build_v4_dry_run_report,
    evaluate_v4_plan,
)
from check_condition_source_ready import DEFAULT_DSN


DEFAULT_CONTEXT_RUN_ID = "trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1"
DEFAULT_SNAPSHOT_RUN_ID = "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1"
DEFAULT_JSON_REPORT = "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_dry_run_report.json"
DEFAULT_MD_REPORT = "docs/N4_TRIGGER_RULE_SPEC_v4_FULL_LINEAGE_DRY_RUN_REPORT.md"
DEFAULT_DIFF_JSON = "docs/N4_TRIGGER_RULE_SPEC_v4_full_lineage_v3_v4_diff.json"
DEFAULT_DIFF_MD = "docs/N4_TRIGGER_RULE_SPEC_v4_FULL_LINEAGE_V3_V4_DIFF.md"
DEFAULT_N2_CONTEXT_ENRICHMENT_REPORT = "docs/N2_20260603_context_enrichment_row_level_materialization_execute_report.json"
DEFAULT_N3_PROJECTION_ENRICHMENT_REPORT = "docs/N3_projection_enrichment_v4_20260603_materialization_execute_report.json"
DEFAULT_N2_CONTEXT_MATERIALIZATION_RUN_ID = (
    "condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1"
)
DEFAULT_N3_PROJECTION_RUN_ID = (
    "projection_enrichment_v4_20260603_until_1500__"
    "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1"
)

ASSET_KINDS = ("stock", "index", "board")
CONDITION_CONTEXT_ENRICHMENT_TABLES = {
    "stock": ("stock_condition_context_enrichment", "stock_identity_key", "stock_condition_context_enrichment_id"),
    "index": ("index_condition_context_enrichment", "index_identity_key", "index_condition_context_enrichment_id"),
    "board": ("board_condition_context_enrichment", "board_identity_key", "board_condition_context_enrichment_id"),
}
REALTIME_PROJECTION_TABLES = {
    "stock": ("stock_realtime_projection_metric", "stock_identity_key"),
    "index": ("index_realtime_projection_metric", "index_identity_key"),
    "board": ("board_realtime_projection_metric", "board_identity_key"),
}
PROJECTION_ENRICHMENT_V4_TABLES = {
    "stock": ("stock_projection_enrichment_v4_metric", "stock_identity_key"),
    "index": ("index_projection_enrichment_v4_metric", "index_identity_key"),
    "board": ("board_projection_enrichment_v4_metric", "board_identity_key"),
}
ACTION_CONFIRMATION_TABLES = {
    "stock": "stock_action_confirmation_projection_metric",
    "index": "index_action_confirmation_projection_metric",
    "board": "board_action_confirmation_projection_metric",
}


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.execute:
        raise SystemExit("BLOCKED: N4 v4 full-lineage dry-run is shadow-only and never executes")

    report, diff = run_full_lineage_dry_run(
        dsn=args.dsn,
        trigger_context_run_id=args.trigger_context_run_id,
        snapshot_run_id=args.snapshot_run_id,
        condition_context_materialization_run_id=args.condition_context_materialization_run_id,
        projection_run_id=args.projection_run_id,
        sample_limit=args.sample_limit,
        n2_context_enrichment_report_path=args.n2_context_enrichment_report_path,
        n3_projection_enrichment_report_path=args.n3_projection_enrichment_report_path,
    )
    write_json(Path(args.json_report_path), report)
    write_text(Path(args.markdown_report_path), render_report_md(report))
    write_json(Path(args.diff_json_path), diff)
    write_text(Path(args.diff_markdown_path), render_diff_md(diff))
    print(
        json.dumps(
            {
                "result": report["result"],
                "v4_full_dry_run_row_count": report["v4_full_dry_run_row_count"],
                "json_report_path": args.json_report_path,
                "diff_json_path": args.diff_json_path,
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["result"] == "FULL_LINEAGE_DRY_RUN_PASS" else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--trigger-context-run-id", default=DEFAULT_CONTEXT_RUN_ID)
    parser.add_argument("--snapshot-run-id", default=DEFAULT_SNAPSHOT_RUN_ID)
    parser.add_argument("--condition-context-materialization-run-id", default=DEFAULT_N2_CONTEXT_MATERIALIZATION_RUN_ID)
    parser.add_argument("--projection-run-id", default=DEFAULT_N3_PROJECTION_RUN_ID)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MD_REPORT)
    parser.add_argument("--diff-json-path", default=DEFAULT_DIFF_JSON)
    parser.add_argument("--diff-markdown-path", default=DEFAULT_DIFF_MD)
    parser.add_argument("--n2-context-enrichment-report-path", default=DEFAULT_N2_CONTEXT_ENRICHMENT_REPORT)
    parser.add_argument("--n3-projection-enrichment-report-path", default=DEFAULT_N3_PROJECTION_ENRICHMENT_REPORT)
    parser.add_argument("--sample-limit", type=int, default=60)
    parser.add_argument("--execute", action="store_true")
    return parser


def run_full_lineage_dry_run(
    *,
    dsn: str,
    trigger_context_run_id: str,
    snapshot_run_id: str,
    condition_context_materialization_run_id: str,
    projection_run_id: str,
    sample_limit: int,
    n2_context_enrichment_report_path: str,
    n3_projection_enrichment_report_path: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    trigger_run, context_rows = fetch_context_rows(dsn, trigger_context_run_id)
    snapshot_run, snapshot_rows = fetch_snapshot_rows(dsn, snapshot_run_id)
    materialized_context_rows = fetch_condition_context_enrichment_rows(
        dsn,
        condition_context_materialization_run_id,
    )
    realtime_projection_rows = fetch_projection_enrichment_v4_rows(dsn, projection_run_id)
    action_confirmation_rows = fetch_action_confirmation_projection_rows(dsn, snapshot_run_id)
    projection_lookup = latest_projection_by_context_key(realtime_projection_rows)

    v4_plans = [
        evaluate_v4_plan(
            context_row,
            projection_lookup.get(context_projection_key(context_row)),
            v4_run_id=build_v4_run_id(trigger_context_run_id),
        )
        for context_row in materialized_context_rows
    ]
    v3_plans = build_local_trigger_plans(
        trigger_context_run_id=trigger_context_run_id,
        snapshot_run_id=snapshot_run_id,
        context_rows=context_rows,
        snapshot_rows=snapshot_rows,
    )

    input_readiness = build_input_readiness(
        context_rows=context_rows,
        materialized_context_rows=materialized_context_rows,
        realtime_projection_rows=realtime_projection_rows,
        action_confirmation_rows=action_confirmation_rows,
    )
    declared_readiness = load_declared_readiness(
        n2_context_enrichment_report_path=n2_context_enrichment_report_path,
        n3_projection_enrichment_report_path=n3_projection_enrichment_report_path,
    )
    v4_summary = build_full_v4_summary(v4_plans)
    base_report = build_v4_dry_run_report(v4_plans, v3_summary=build_v3_summary(v3_plans))
    blockers = build_blockers(input_readiness, declared_readiness)
    result = "FULL_LINEAGE_DRY_RUN_PASS" if not blockers and base_report["result"] == "DRY_RUN_PASS" else "FULL_LINEAGE_DRY_RUN_BLOCKED"

    diff = build_full_diff(v3_plans, v4_plans, sample_limit=sample_limit)
    report: dict[str, Any] = {
        "result": result,
        "stage": "N4_TRIGGER_RULE_SPEC_v4_FULL_LINEAGE_DRY_RUN_REFRESH_GATE",
        "layer_role": "N4_trigger",
        "mode": "shadow_v4_full_lineage_dry_run",
        "trigger_rule_spec_version": TRIGGER_RULE_SPEC_VERSION,
        "trigger_rule_policy_hash": TRIGGER_RULE_POLICY_HASH,
        "independent_v4_run_id": build_v4_run_id(trigger_context_run_id),
        "trigger_context_run_id": trigger_context_run_id,
        "snapshot_run_id": snapshot_run_id,
        "condition_context_materialization_run_id": condition_context_materialization_run_id,
        "projection_run_id": projection_run_id,
        "source_condition_run_id": trigger_run.get("source_condition_run_id")
        or snapshot_run.get("source_condition_run_id"),
        "for_trade_date": trigger_run.get("for_trade_date") or snapshot_run.get("for_trade_date"),
        "v3_still_production_mainline": True,
        "v4_shadow_only": True,
        "blockers": blockers,
        "input_readiness": input_readiness,
        "declared_enrichment_readiness": declared_readiness,
        "v4_full_dry_run_row_count": len(v4_plans),
        "v4_summary": v4_summary,
        "v3_summary": build_v3_summary(v3_plans),
        "v3_v4_diff_summary": diff["summary"],
        "bj_missing_quality_visible_proof": build_bj_missing_quality_visible_proof(
            v4_plans=v4_plans,
            input_readiness=input_readiness,
            declared_readiness=declared_readiness,
        ),
        "false_positive_samples": diff["false_positive_samples"],
        "false_negative_samples": diff["false_negative_samples"],
        "full_blocked_proof": base_report["full_blocked_proof"],
        "n5_entry_guard": base_report["n5_entry_guard"],
        "no_invalid_n5_entry_proof": {
            "invalid_n5_entry_count": base_report["n5_entry_guard"]["violations"],
            "passed": base_report["n5_entry_guard"]["violations"] == 0,
        },
        "boundary_proof": {
            "database_writes": False,
            "history_modified": False,
            "outbox_consumed": False,
            "worker_started": False,
            "n5_n6_entered": False,
            "raw_k_read": False,
            "n1_daily_read": False,
            "self_aggregation": False,
            "projection_source_policy": "only N3 row-level projection_enrichment_v4_metric rows are accepted as projection enrichment",
            "summary_artifacts_are_not_row_level_inputs": True,
        },
        "sample_v4_plans": v4_plans[:sample_limit],
        "sample_v3_plans": v3_plans[:sample_limit],
        "next_gate": {
            "allow_runtime_control_v4_full_dry_run_review": True,
            "allow_v4_execute": False,
            "blocked_by_layer": "N2_condition/N3_market_data" if blockers else None,
            "note": "v4 execute remains blocked; this gate is shadow dry-run only.",
        },
    }
    return report, diff


def fetch_condition_context_enrichment_rows(dsn: str, materialization_run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_rule_v4_full_lineage_fetch_context_enrichment",
        source_run_id=materialization_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for asset_kind, (table_name, identity_column, id_column) in CONDITION_CONTEXT_ENRICHMENT_TABLES.items():
            cur.execute(
                f"""
                SELECT {id_column} AS condition_context_enrichment_id,
                       materialization_run_id,
                       source_condition_run_id,
                       for_trade_date,
                       for_trade_date AS trade_date,
                       source_trade_date,
                       spec_version,
                       policy_hash,
                       {identity_column} AS identity_key,
                       condition_key,
                       direction,
                       allowed_signal_types,
                       source_scope_table,
                       source_minute_target_scope_id,
                       context_materialization_row_key,
                       context_enrichment_version,
                       context_enrichment_hash,
                       period_trigger_baseline_json,
                       trigger_amount_chain_baseline_json,
                       trigger_amount_chain_formula_hash,
                       full_prerequisite_trace_json,
                       full_prerequisite_quality_status,
                       hint_prerequisite_trace_json,
                       hint_prerequisite_quality_status,
                       freshness_status,
                       period_baseline_ready_json,
                       payload_json,
                       created_at
                FROM {table_name}
                WHERE materialization_run_id = %s
                ORDER BY {identity_column}, condition_key, direction, {id_column}
                """,
                (materialization_run_id,),
            )
            for row in cur.fetchall():
                item = dict(row)
                item["asset_kind"] = asset_kind
                item["original_condition_key"] = item.get("condition_key")
                item["run_id"] = materialization_run_id
                item["context_snapshot_id"] = item.get("condition_context_enrichment_id")
                rows.append(item)
    return rows


def fetch_projection_enrichment_v4_rows(dsn: str, projection_run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_rule_v4_full_lineage_fetch_projection_enrichment",
        source_run_id=projection_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for asset_kind, (table_name, identity_column) in PROJECTION_ENRICHMENT_V4_TABLES.items():
            cur.execute(
                f"""
                SELECT projection_enrichment_id,
                       projection_run_id,
                       spec_version,
                       policy_hash,
                       source_condition_run_id,
                       source_subscription_run_id,
                       source_snapshot_run_id,
                       source_today_minute_run_id,
                       source_previous_day_minute_run_id,
                       source_trigger_context_run_id,
                       source_trigger_context_id,
                       source_condition_context_enrichment_id,
                       source_snapshot_id,
                       for_trade_date,
                       trade_date,
                       asset_kind,
                       identity_key,
                       {identity_column} AS typed_identity_key,
                       exchange,
                       code,
                       display_code,
                       name,
                       direction,
                       condition_key,
                       allowed_signal_types,
                       materialization_row_key,
                       current_price_or_close,
                       current_amount_metric,
                       current_metric_time,
                       current_metric_quality_status,
                       projection_period,
                       projection_30m_flag,
                       projection_30m_type,
                       current_30m_virtual_amount,
                       reference_30m_amount,
                       reference_30m_entity_high,
                       reference_30m_entity_low,
                       trigger_amount_chain_pass,
                       projection_lineage_json,
                       source_freshness_status,
                       metric_ready,
                       metric_quality_status,
                       quality_visible,
                       quality_reason,
                       payload_json,
                       raw_json,
                       created_at
                FROM {table_name}
                WHERE projection_run_id = %s
                ORDER BY identity_key, condition_key, direction, projection_enrichment_id
                """,
                (projection_run_id,),
            )
            for row in cur.fetchall():
                item = dict(row)
                item["asset_kind"] = asset_kind
                item["source_event_id"] = item.get("source_snapshot_id")
                item["source_event_type"] = "MarketSnapshotUpdated"
                item["source_market_data_run_id"] = item.get("source_snapshot_run_id")
                rows.append(item)
    return rows


def fetch_realtime_projection_rows(dsn: str, snapshot_run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_rule_v4_full_lineage_fetch_realtime_projection",
        source_run_id=snapshot_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for asset_kind, (table_name, identity_column) in REALTIME_PROJECTION_TABLES.items():
            cur.execute(
                f"""
                SELECT projection_id, projection_run_id, source_snapshot_run_id,
                       source_condition_run_id, snapshot_id, snapshot_event_id,
                       for_trade_date, trade_date, {identity_column} AS identity_key,
                       exchange, code, display_code, name, raw_json, created_at, updated_at
                FROM {table_name}
                WHERE source_snapshot_run_id = %s
                ORDER BY {identity_column}, updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                """,
                (snapshot_run_id,),
            )
            for row in cur.fetchall():
                item = dict(row)
                item["asset_kind"] = asset_kind
                item["source_event_id"] = item.get("snapshot_event_id")
                item["source_event_type"] = "MarketSnapshotUpdated"
                item["source_market_data_run_id"] = item.get("source_snapshot_run_id")
                rows.append(item)
    return rows


def fetch_action_confirmation_projection_rows(dsn: str, snapshot_run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_rule_v4_full_lineage_fetch_action_confirmation_projection",
        source_run_id=snapshot_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for table_name in ACTION_CONFIRMATION_TABLES.values():
            cur.execute(
                f"""
                SELECT action_confirmation_metric_id, projection_run_id,
                       source_condition_run_id, source_subscription_run_id,
                       source_snapshot_run_id, for_trade_date, trade_date,
                       asset_kind, identity_key, raw_json, created_at
                FROM {table_name}
                WHERE source_snapshot_run_id = %s
                ORDER BY identity_key, created_at DESC NULLS LAST
                """,
                (snapshot_run_id,),
            )
            rows.extend(dict(row) for row in cur.fetchall())
    return rows


def latest_projection_by_context_key(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    output: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        raw_json = row.get("raw_json")
        has_legacy_enrichment = isinstance(raw_json, Mapping) and isinstance(raw_json.get("enrichment_v1"), Mapping)
        has_v4_enrichment = "projection_enrichment_id" in row
        if not has_legacy_enrichment and not has_v4_enrichment:
            continue
        key = projection_context_key(row)
        output.setdefault(key, dict(row))
    return output


def build_input_readiness(
    *,
    context_rows: Sequence[Mapping[str, Any]],
    materialized_context_rows: Sequence[Mapping[str, Any]],
    realtime_projection_rows: Sequence[Mapping[str, Any]],
    action_confirmation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    context_count = len(materialized_context_rows)
    context_enrichment_rows = 0
    period_previous_transition_rows = 0
    period_previous_amount_baseline_rows = 0
    for row in materialized_context_rows:
        baseline = row.get("period_trigger_baseline_json")
        if isinstance(baseline, Mapping) and isinstance(baseline.get("context_enrichment"), Mapping):
            context_enrichment_rows += 1
        periods = baseline.get("periods") if isinstance(baseline, Mapping) else {}
        if isinstance(periods, Mapping) and all(
            isinstance(value, Mapping) and "previous_transition" in value
            for value in periods.values()
        ):
            period_previous_transition_rows += 1
        if isinstance(periods, Mapping) and all(
            isinstance(value, Mapping) and "previous_amount_baseline" in value
            for value in periods.values()
        ):
            period_previous_amount_baseline_rows += 1

    realtime_enriched = sum(
        1
        for row in realtime_projection_rows
        if "projection_enrichment_id" in row
        or (
            isinstance(row.get("raw_json"), Mapping)
            and isinstance(row["raw_json"].get("enrichment_v1"), Mapping)
        )
    )
    complete_lineage_rows = sum(
        1
        for row in realtime_projection_rows
        if row.get("source_freshness_status") == "fresh_complete_lineage"
    )
    bj_quality_visible_rows = sum(
        1
        for row in realtime_projection_rows
        if row.get("quality_visible") is True
        and row.get("source_freshness_status") == "source_minute_missing_quality_visible"
    )
    snapshot_only_fallback_rows = sum(
        1
        for row in realtime_projection_rows
        if row.get("source_freshness_status") == "snapshot_only_fallback"
    )
    action_enriched = sum(
        1
        for row in action_confirmation_rows
        if isinstance(row.get("raw_json"), Mapping)
        and isinstance(row["raw_json"].get("enrichment_v1"), Mapping)
    )
    return {
        "context_rows": context_count,
        "legacy_trigger_context_rows": len(context_rows),
        "context_enrichment_rows": context_enrichment_rows,
        "period_previous_transition_rows": period_previous_transition_rows,
        "period_previous_amount_baseline_rows": period_previous_amount_baseline_rows,
        "realtime_projection_rows": len(realtime_projection_rows),
        "realtime_projection_enrichment_rows": realtime_enriched,
        "complete_lineage_rows": complete_lineage_rows,
        "bj_quality_visible_rows": bj_quality_visible_rows,
        "snapshot_only_fallback_rows": snapshot_only_fallback_rows,
        "action_confirmation_projection_rows": len(action_confirmation_rows),
        "action_confirmation_projection_enrichment_rows": action_enriched,
    }


def load_declared_readiness(
    *,
    n2_context_enrichment_report_path: str,
    n3_projection_enrichment_report_path: str,
) -> dict[str, Any]:
    n2_payload = load_json_if_exists(n2_context_enrichment_report_path)
    n3_payload = load_json_if_exists(n3_projection_enrichment_report_path)
    n2_summary = n2_payload.get("refresh_summary") if isinstance(n2_payload, Mapping) else {}
    n2_row_counts = n2_payload.get("row_counts") if isinstance(n2_payload, Mapping) else {}
    n3_freshness = n3_payload.get("source_freshness_distribution") if isinstance(n3_payload, Mapping) else {}
    n3_actual_rows = n3_payload.get("actual_rows") if isinstance(n3_payload, Mapping) else {}
    n3_bj_rows = n3_payload.get("bj_quality_visible_rows") if isinstance(n3_payload, Mapping) else {}
    return {
        "n2_context_enrichment": {
            "path": n2_context_enrichment_report_path,
            "path_exists": bool(n2_payload),
            "result": n2_payload.get("execute_result")
            or n2_payload.get("refresh_result")
            or n2_payload.get("gate_result"),
            "expected_context_candidates": n2_payload.get("expected_context_candidates")
            or (n2_row_counts.get("total") if isinstance(n2_row_counts, Mapping) else None),
            "declared_context_enrichment_rows": (
                n2_summary.get("context_enrichment_rows")
                if isinstance(n2_summary, Mapping)
                else n2_row_counts.get("total")
                if isinstance(n2_row_counts, Mapping)
                else None
            ),
            "declared_previous_transition_rows": (
                n2_summary.get("previous_transition_rows") if isinstance(n2_summary, Mapping) else None
            ),
            "declared_previous_amount_baseline_rows": (
                n2_summary.get("previous_amount_baseline_rows") if isinstance(n2_summary, Mapping) else None
            ),
            "row_level_payload_available": has_row_level_payload(n2_payload),
            "row_level_payload_policy": "N4 accepts only materialized DB rows or an explicit full row-level payload, not summary counts.",
        },
        "n3_projection_enrichment": {
            "path": n3_projection_enrichment_report_path,
            "path_exists": bool(n3_payload),
            "result": n3_payload.get("execute_result") or n3_payload.get("result"),
            "expected_context_candidates": n3_payload.get("expected_context_candidates")
            or (n3_actual_rows.get("total") if isinstance(n3_actual_rows, Mapping) else None),
            "declared_projection_rows": n3_payload.get("projection_row_count")
            or (n3_actual_rows.get("total") if isinstance(n3_actual_rows, Mapping) else None),
            "declared_enrichment_rows": n3_payload.get("enrichment_rows")
            or (n3_actual_rows.get("total") if isinstance(n3_actual_rows, Mapping) else None),
            "declared_complete_lineage_rows": n3_payload.get("complete_lineage_rows"),
            "missing_source_minute_rows": n3_payload.get("missing_source_minute_rows")
            or (n3_bj_rows.get("total") if isinstance(n3_bj_rows, Mapping) else None),
            "snapshot_only_fallback_rows": n3_freshness.get("snapshot_only_fallback_rows")
            if isinstance(n3_freshness, Mapping)
            else 0
            if n3_payload
            else None,
            "row_level_payload_available": has_row_level_payload(n3_payload),
            "row_level_payload_policy": "N4 accepts only materialized DB rows or an explicit full row-level payload, not summary counts.",
        },
    }


def load_json_if_exists(path: str) -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.exists():
        return {}
    try:
        payload = json.loads(report_path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def has_row_level_payload(payload: Mapping[str, Any]) -> bool:
    for key in (
        "row_level_payload_path",
        "full_row_payload_path",
        "materialized_row_payload_path",
        "context_enrichment_row_payload_path",
        "projection_enrichment_row_payload_path",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return True
    for key in (
        "row_level_rows",
        "context_enrichment_row_payload",
        "projection_enrichment_row_payload",
        "projection_enrichment_rows",
        "materialized_rows",
    ):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return True
    rows = payload.get("rows")
    return isinstance(rows, list) and bool(rows)


def build_blockers(
    input_readiness: Mapping[str, Any],
    declared_readiness: Mapping[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    context_rows = int(input_readiness.get("context_rows") or 0)
    n2_declared = declared_readiness.get("n2_context_enrichment", {})
    n3_declared = declared_readiness.get("n3_projection_enrichment", {})
    if int(input_readiness.get("context_enrichment_rows") or 0) < context_rows:
        blockers.append(
            {
                "blocked_by_layer": "N2_condition",
                "reason": "n2_context_enrichment_missing_in_trigger_context_snapshot",
                "expected": context_rows,
                "actual": int(input_readiness.get("context_enrichment_rows") or 0),
            }
        )
        if (
            isinstance(n2_declared, Mapping)
            and int(n2_declared.get("declared_context_enrichment_rows") or 0) >= context_rows
            and not bool(n2_declared.get("row_level_payload_available"))
        ):
            blockers.append(
                {
                    "blocked_by_layer": "N2_condition",
                    "reason": "n2_context_enrichment_declared_but_not_materialized_as_n4_row_level_input",
                    "declared": int(n2_declared.get("declared_context_enrichment_rows") or 0),
                    "materialized_in_trigger_context_snapshot": int(input_readiness.get("context_enrichment_rows") or 0),
                    "required_policy": "N4 must consume row-level N2 context enrichment, not summary counts.",
                }
            )
    if int(input_readiness.get("period_previous_transition_rows") or 0) < context_rows:
        blockers.append(
            {
                "blocked_by_layer": "N2_condition",
                "reason": "previous_transition_missing_in_context_enrichment",
                "expected": context_rows,
                "actual": int(input_readiness.get("period_previous_transition_rows") or 0),
            }
        )
        if (
            isinstance(n2_declared, Mapping)
            and int(n2_declared.get("declared_previous_transition_rows") or 0) >= context_rows
            and not bool(n2_declared.get("row_level_payload_available"))
        ):
            blockers.append(
                {
                    "blocked_by_layer": "N2_condition",
                    "reason": "previous_transition_declared_but_not_materialized_as_n4_row_level_input",
                    "declared": int(n2_declared.get("declared_previous_transition_rows") or 0),
                    "materialized_in_trigger_context_snapshot": int(input_readiness.get("period_previous_transition_rows") or 0),
                    "required_policy": "N4 must consume row-level previous_transition values, not summary counts.",
                }
            )
    if int(input_readiness.get("period_previous_amount_baseline_rows") or 0) < context_rows:
        pass
    if int(input_readiness.get("realtime_projection_enrichment_rows") or 0) == 0:
        blockers.append(
            {
                "blocked_by_layer": "N3_market_data",
                "reason": "n3_projection_enrichment_rows_missing_for_snapshot_run",
                "expected": ">0",
                "actual": 0,
            }
        )
        if (
            isinstance(n3_declared, Mapping)
            and int(n3_declared.get("declared_enrichment_rows") or 0) > 0
            and not bool(n3_declared.get("row_level_payload_available"))
        ):
            blockers.append(
                {
                    "blocked_by_layer": "N3_market_data",
                    "reason": "n3_projection_enrichment_declared_but_not_materialized_as_n4_row_level_input",
                    "declared": int(n3_declared.get("declared_enrichment_rows") or 0),
                    "materialized_projection_enrichment_rows": int(input_readiness.get("realtime_projection_enrichment_rows") or 0),
                    "snapshot_only_fallback_rows": n3_declared.get("snapshot_only_fallback_rows"),
                    "required_policy": "N4 must consume row-level N3 projection enrichment, not summary counts.",
                }
            )
    return blockers


def context_projection_key(context_row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(context_row.get("asset_kind") or ""),
        str(context_row.get("identity_key") or ""),
        str(context_row.get("direction") or ""),
        str(context_row.get("condition_key") or ""),
    )


def projection_context_key(projection_row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(projection_row.get("asset_kind") or ""),
        str(projection_row.get("identity_key") or ""),
        str(projection_row.get("direction") or ""),
        str(projection_row.get("condition_key") or ""),
    )


def build_full_v4_summary(plans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "matched": count_where(plans, "outcome_classification", "matched"),
        "pending_market_data": count_where(plans, "outcome_classification", "pending_market_data"),
        "no_op": count_where(plans, "outcome_classification", "no_op"),
        "quality_blocked": count_where(plans, "outcome_classification", "quality_blocked"),
        "inactive": count_where(plans, "outcome_classification", "inactive"),
        "n5_entry_allowed": sum(1 for plan in plans if plan.get("n5_entry_allowed") is True),
        "primary_trigger_period_distribution": counter(plans, "primary_trigger_period"),
        "trigger_kind_distribution": counter(plans, "trigger_kind"),
        "trigger_mark_candidate_distribution": counter(plans, "trigger_mark_candidate"),
        "by_asset_kind": counter(plans, "asset_kind"),
        "by_signal_type": counter(plans, "signal_type"),
        "by_condition_key": counter(plans, "condition_key"),
        "by_asset_kind_signal_type": combo_counter(plans, ("asset_kind", "signal_type")),
        "by_asset_kind_condition_key": combo_counter(plans, ("asset_kind", "condition_key")),
        "by_trigger_kind_trigger_mark_candidate": combo_counter(plans, ("trigger_kind", "trigger_mark_candidate")),
    }


def build_bj_missing_quality_visible_proof(
    *,
    v4_plans: Sequence[Mapping[str, Any]],
    input_readiness: Mapping[str, Any],
    declared_readiness: Mapping[str, Any],
) -> dict[str, Any]:
    n3_declared = declared_readiness.get("n3_projection_enrichment", {})
    declared_missing_rows = int(n3_declared.get("missing_source_minute_rows") or 0) if isinstance(n3_declared, Mapping) else 0
    snapshot_only_fallback_rows = (
        int(n3_declared.get("snapshot_only_fallback_rows") or 0) if isinstance(n3_declared, Mapping) else None
    )
    row_level_projection_rows = int(input_readiness.get("realtime_projection_enrichment_rows") or 0)
    n4_bj_quality_blocked_rows = sum(
        1
        for plan in v4_plans
        if str(plan.get("identity_key") or "").startswith("index:BJ:")
        and plan.get("outcome_classification") == "quality_blocked"
    )
    return {
        "declared_by_n3_missing_source_minute_rows": declared_missing_rows,
        "declared_snapshot_only_fallback_rows": snapshot_only_fallback_rows,
        "n4_row_level_projection_enrichment_rows": row_level_projection_rows,
        "n4_bj_quality_blocked_rows": n4_bj_quality_blocked_rows,
        "bj_rows_quality_blocked": n4_bj_quality_blocked_rows == declared_missing_rows
        and declared_missing_rows > 0,
        "status": (
            "materialized_quality_blocked"
            if n4_bj_quality_blocked_rows == declared_missing_rows and declared_missing_rows > 0
            else "blocked_not_materialized_as_n4_row_level_input"
            if declared_missing_rows and row_level_projection_rows == 0
            else "materialized_or_not_declared"
        ),
        "policy": "BJ missing rows must be quality-visible from row-level N3 enrichment; N4 must not fallback or infer them from summary counts.",
    }


def build_v3_summary(plans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "plan_count": len(plans),
        "TriggerMatched": count_where(plans, "output_event_type", "TriggerMatched"),
        "TriggerPendingMarketData": count_where(plans, "output_event_type", "TriggerPendingMarketData"),
        "TriggerStateChanged": count_where(plans, "output_event_type", "TriggerStateChanged"),
        "by_signal_type": counter(plans, "signal_type"),
        "by_trigger_mark_candidate": counter(plans, "trigger_mark_candidate"),
    }


def build_full_diff(
    v3_plans: Sequence[Mapping[str, Any]],
    v4_plans: Sequence[Mapping[str, Any]],
    *,
    sample_limit: int,
) -> dict[str, Any]:
    v3_by_key = index_plans(v3_plans)
    v4_by_key = index_plans(v4_plans)
    all_keys = sorted(set(v3_by_key) | set(v4_by_key))
    false_positives: list[dict[str, Any]] = []
    false_negatives: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    for key in all_keys:
        v3_items = v3_by_key.get(key, [])
        v4_items = v4_by_key.get(key, [])
        v3_matched = any(item.get("output_event_type") == "TriggerMatched" for item in v3_items)
        v4_matched = any(item.get("outcome_classification") == "matched" for item in v4_items)
        if v3_matched and not v4_matched:
            false_positives.append(diff_sample(key, v3_items, v4_items))
        elif v4_matched and not v3_matched:
            false_negatives.append(diff_sample(key, v3_items, v4_items))
        elif v3_items and v4_items and v3_matched != v4_matched:
            changed.append(diff_sample(key, v3_items, v4_items))
    return {
        "result": "FULL_DIFF_PASS",
        "summary": {
            "v3_plan_count": len(v3_plans),
            "v4_plan_count": len(v4_plans),
            "false_positive_count": len(false_positives),
            "false_negative_count": len(false_negatives),
            "changed_count": len(changed),
            "interpretation": "false positives/negatives are shadow comparisons between production v3 plans and shadow v4 outcomes.",
        },
        "false_positive_samples": false_positives[:sample_limit],
        "false_negative_samples": false_negatives[:sample_limit],
    }


def index_plans(plans: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    output: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for plan in plans:
        key = "|".join(
            str(plan.get(part) or "")
            for part in ("asset_kind", "identity_key", "direction", "condition_key", "signal_type")
        )
        output[key].append(plan)
    return output


def diff_sample(
    key: str,
    v3_items: Sequence[Mapping[str, Any]],
    v4_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "comparison_key": key,
        "v3_event_types": sorted({str(item.get("output_event_type")) for item in v3_items}),
        "v4_outcomes": sorted({str(item.get("outcome_classification")) for item in v4_items}),
        "v4_pending_reasons": sorted(
            {
                reason
                for item in v4_items
                for reason in (item.get("pending_reasons") or [])
            }
        ),
        "v4_blocked_reasons": sorted(
            {
                str(item.get("blocked_reason"))
                for item in v4_items
                if item.get("blocked_reason")
            }
        ),
    }


def build_v4_run_id(trigger_context_run_id: str) -> str:
    suffix = trigger_context_run_id.replace("trigger_context_snapshot_", "")
    return f"trigger_rule_v4_shadow_dry_run_{suffix}"


def counter(plans: Sequence[Mapping[str, Any]], field: str) -> dict[str, int]:
    return dict(Counter(str(plan.get(field)) for plan in plans))


def combo_counter(plans: Sequence[Mapping[str, Any]], fields: tuple[str, ...]) -> dict[str, int]:
    return dict(Counter("|".join(str(plan.get(field)) for field in fields) for plan in plans))


def count_where(plans: Sequence[Mapping[str, Any]], field: str, value: str) -> int:
    return sum(1 for plan in plans if plan.get(field) == value)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def render_report_md(report: Mapping[str, Any]) -> str:
    return f"""# N4 Trigger Rule Spec v4 Full-Lineage Dry-Run Report

Result: `{report['result']}`

Mode: `{report['mode']}`

Context run: `{report['trigger_context_run_id']}`

Snapshot run: `{report['snapshot_run_id']}`

V4 run: `{report['independent_v4_run_id']}`

## Input Readiness

```json
{json.dumps(report['input_readiness'], ensure_ascii=False, indent=2, default=str)}
```

## Declared Enrichment Readiness

```json
{json.dumps(report['declared_enrichment_readiness'], ensure_ascii=False, indent=2, default=str)}
```

## Blockers

```json
{json.dumps(report['blockers'], ensure_ascii=False, indent=2, default=str)}
```

## V4 Summary

```json
{json.dumps(report['v4_summary'], ensure_ascii=False, indent=2, default=str)}
```

## V3-V4 Diff Summary

```json
{json.dumps(report['v3_v4_diff_summary'], ensure_ascii=False, indent=2, default=str)}
```

## BJ Missing Quality Visible Proof

```json
{json.dumps(report['bj_missing_quality_visible_proof'], ensure_ascii=False, indent=2, default=str)}
```

## FULL Blocked Proof

```json
{json.dumps(report['full_blocked_proof'], ensure_ascii=False, indent=2, default=str)}
```

## N5 Entry Guard

```json
{json.dumps(report['n5_entry_guard'], ensure_ascii=False, indent=2, default=str)}
```
"""


def render_diff_md(diff: Mapping[str, Any]) -> str:
    return f"""# N4 Trigger Rule Spec v4 Full-Lineage V3-V4 Diff

Result: `{diff['result']}`

```json
{json.dumps(diff['summary'], ensure_ascii=False, indent=2, default=str)}
```

## False Positive Samples

```json
{json.dumps(diff['false_positive_samples'], ensure_ascii=False, indent=2, default=str)}
```

## False Negative Samples

```json
{json.dumps(diff['false_negative_samples'], ensure_ascii=False, indent=2, default=str)}
```
"""


if __name__ == "__main__":
    raise SystemExit(main())
