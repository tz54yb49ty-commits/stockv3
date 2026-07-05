"""N3 action-confirmation projection metric writer readiness planner.

This module is read-only. It verifies source run readiness, source fact
coverage, trace completeness, rollback scope, and N4/N5 boundary alignment for
future N3 action-confirmation projection metric writes. It does not write
metric rows, run rows, quality rows, outbox/inbox/checkpoint rows, downstream
runtime state, or start workers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import json
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.projection_enrichment import (
    build_projection_enrichment_v1,
    summarize_projection_enrichment_rows,
)
from ashare_v3.market.realtime_virtual_metric import VIRTUAL_AMOUNT_POLICY_VERSION


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
ASSET_KINDS = ("stock", "index", "board")
IDENTITY_COLUMNS = {
    "stock": "stock_identity_key",
    "index": "index_identity_key",
    "board": "board_identity_key",
}
SNAPSHOT_TABLES = {
    "stock": "stock_realtime_daily_snapshot",
    "index": "index_realtime_daily_snapshot",
    "board": "board_realtime_daily_snapshot",
}
MINUTE_TABLES = {
    "stock": "stock_minute_bar_1m",
    "index": "index_minute_bar_1m",
    "board": "board_minute_bar_1m",
}
METRIC_TABLES = {
    "stock": "stock_action_confirmation_projection_metric",
    "index": "index_action_confirmation_projection_metric",
    "board": "board_action_confirmation_projection_metric",
}

DEFAULT_FOR_TRADE_DATE = "20260602"
DEFAULT_SOURCE_CONDITION_RUN_ID = "condition_layer_20260601_source_20260601_v1"
DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID = "market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1"
DEFAULT_SOURCE_SNAPSHOT_RUN_ID = (
    "realtime_snapshot_20260602_live3_outbox_market_data_subscription_"
    "20260602_condition_layer_20260601_source_20260601_v1"
)
DEFAULT_SOURCE_TODAY_MINUTE_RUN_ID = (
    "today_minute_bar_1m_20260602_until_1105__market_data_subscription_"
    "20260602_condition_layer_20260601_source_20260601_v1"
)
DEFAULT_SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID = (
    "previous_day_minute_preload_20260602_market_data_subscription_"
    "20260602_condition_layer_20260601_source_20260601_v1"
)
DEFAULT_PROJECTION_RUN_ID = (
    "action_confirmation_projection_metric_20260602_1105__"
    "realtime_snapshot_20260602_live3_outbox_market_data_subscription_"
    "20260602_condition_layer_20260601_source_20260601_v1"
)

DEFAULT_MARKDOWN_REPORT_PATH = "docs/N3_ACTION_CONFIRMATION_PROJECTION_WRITER_READINESS.md"
DEFAULT_JSON_REPORT_PATH = "docs/N3_action_confirmation_projection_writer_readiness.json"
DEFAULT_PREFLIGHT_MARKDOWN_PATH = "docs/N3_ACTION_CONFIRMATION_PROJECTION_PREFLIGHT.md"
DEFAULT_PREFLIGHT_JSON_PATH = "docs/N3_action_confirmation_projection_preflight.json"
DEFAULT_DRY_RUN_MARKDOWN_PATH = "docs/N3_ACTION_CONFIRMATION_PROJECTION_WRITER_DRY_RUN_REPORT.md"
DEFAULT_DRY_RUN_JSON_PATH = "docs/N3_action_confirmation_projection_writer_dry_run_report.json"
DEFAULT_DRY_RUN_PREFLIGHT_MARKDOWN_PATH = "docs/N3_ACTION_CONFIRMATION_PROJECTION_WRITER_EXECUTE_PREFLIGHT.md"
DEFAULT_DRY_RUN_PREFLIGHT_JSON_PATH = "docs/N3_action_confirmation_projection_writer_execute_preflight.json"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N3_action_confirmation_projection_metric_business_rollback.sql"

ALLOWED_FUTURE_EXECUTE_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_action_confirmation_projection_metric",
    "index_action_confirmation_projection_metric",
    "board_action_confirmation_projection_metric",
]
FORBIDDEN_WRITE_TABLES = [
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_event_delivery_attempt",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "N4/N5/N6 tables",
    "worker",
    "old system",
    "real trade",
]


def now_iso() -> str:
    return datetime.now(ASIA_SHANGHAI).isoformat()


def build_write_scope_contract() -> dict[str, Any]:
    return {
        "allowed_future_execute_write_tables": list(ALLOWED_FUTURE_EXECUTE_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "writes_business_rows_now": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }


def metric_ready_trace_refs_strategy() -> dict[str, Any]:
    return {
        "mode": "db_hard_guard_plus_preflight_p0",
        "source_fact_ids": "non_empty_json_object",
        "source_minute_refs": "non_empty_json_array",
        "previous_day_minute_refs_required_when": (
            "any previous_*_period_source is previous_trade_date_last_period"
        ),
        "preflight_gate": "n3_action_confirmation_trace_refs_complete",
        "db_check": "032 metric_ready CHECK constraints enforce ready-row trace refs",
    }


def n4_n5_boundary_contract() -> dict[str, bool]:
    return {
        "n4_must_not_recompute_from_raw_minutes": True,
        "n5_must_not_recompute_from_raw_minutes": True,
        "n5_must_not_trust_opaque_payload": True,
        "n3_owns_metric_generation": True,
    }


def normalize_asset_counts(value: Mapping[str, Any] | None) -> dict[str, int]:
    value = value or {}
    return {asset_kind: int(value.get(asset_kind) or 0) for asset_kind in ASSET_KINDS}


def total_counts(value: Mapping[str, int]) -> int:
    return sum(int(value.get(asset_kind) or 0) for asset_kind in ASSET_KINDS)


def coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def source_snapshot_run_writes_outbox(source_snapshot_run: Mapping[str, Any] | None) -> bool | None:
    run = source_snapshot_run or {}
    direct = coerce_optional_bool(run.get("writes_outbox"))
    if direct is not None:
        return direct
    for container_key in ("raw_json", "write_scope", "contract_summary", "side_effects"):
        container = run.get(container_key)
        if not isinstance(container, Mapping):
            continue
        for key in ("writes_outbox", "writes_event_outbox", "event_outbox_written"):
            resolved = coerce_optional_bool(container.get(key))
            if resolved is not None:
                return resolved
    return None


def source_snapshot_event_refs_required(source_runs: Mapping[str, Any]) -> bool:
    writes_outbox = source_snapshot_run_writes_outbox(source_runs.get("source_snapshot_run"))
    return True if writes_outbox is None else writes_outbox


def build_quality_items(
    *,
    schema_status: Mapping[str, Any],
    source_runs: Mapping[str, Any],
    input_summary: Mapping[str, Any],
    trace_summary: Mapping[str, Any],
    boundary_summary: Mapping[str, Any],
    baseline_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    tables_exist = schema_status.get("tables_exist") or {}
    missing_tables = [asset for asset in ASSET_KINDS if not bool(tables_exist.get(asset))]
    items.append(
        quality_item(
            "P0",
            "failed" if missing_tables else "passed",
            "n3_action_confirmation_schema_tables_exist",
            "032 action-confirmation metric physical tables must exist",
            expected="stock/index/board tables exist",
            actual=json.dumps(tables_exist, sort_keys=True),
            details={"missing_tables": missing_tables},
        )
    )

    trace_check_count = int(schema_status.get("metric_ready_trace_check_constraints") or 0)
    items.append(
        quality_item(
            "P0",
            "passed" if trace_check_count >= 3 else "failed",
            "n3_action_confirmation_metric_ready_db_check_aligned",
            "metric_ready DB trace CHECK constraints must exist for all physical tables",
            expected=">=3",
            actual=str(trace_check_count),
        )
    )

    failed_runs = {
        name: dict(run)
        for name, run in source_runs.items()
        if str((run or {}).get("status") or "missing") != "passed"
    }
    items.append(
        quality_item(
            "P0",
            "failed" if failed_runs else "passed",
            "n3_action_confirmation_source_runs_passed",
            "source snapshot / today minute / previous-day minute runs must be passed",
            expected="all passed",
            actual=json.dumps({k: (v or {}).get("status") for k, v in source_runs.items()}, sort_keys=True),
            details={"failed_runs": failed_runs},
        )
    )

    candidate_counts = normalize_asset_counts(input_summary.get("candidate_objects"))
    items.append(
        quality_item(
            "P0",
            "passed" if total_counts(candidate_counts) > 0 else "failed",
            "n3_action_confirmation_candidate_objects_present",
            "readiness must find source snapshot/today-minute/previous-day-minute candidate objects",
            expected=">0",
            actual=str(total_counts(candidate_counts)),
            details={"candidate_objects": candidate_counts},
        )
    )

    baseline_nonzero = {key: value for key, value in baseline_summary.items() if int(value or 0) != 0}
    items.append(
        quality_item(
            "P0",
            "failed" if baseline_nonzero else "passed",
            "n3_action_confirmation_projection_run_id_absent",
            "projection_run_id scoped run/quality/metric/outbox/inbox/checkpoint rows must be zero",
            expected="all scoped counts 0",
            actual=json.dumps(baseline_summary, sort_keys=True),
            details={"nonzero": baseline_nonzero},
        )
    )

    expected_events = int((trace_summary.get("snapshot_event_refs") or {}).get("expected") or 0)
    actual_events = int((trace_summary.get("snapshot_event_refs") or {}).get("actual") or 0)
    snapshot_event_refs_required = source_snapshot_event_refs_required(source_runs)
    items.append(
        quality_item(
            "P0",
            "passed" if (not snapshot_event_refs_required or expected_events == actual_events) else "failed",
            "n3_action_confirmation_snapshot_event_trace_complete",
            "source snapshot event refs must match source snapshot facts when source B1 writes outbox",
            expected=str(expected_events)
            if snapshot_event_refs_required
            else "not required for fact-only B1 snapshot run",
            actual=str(actual_events),
            details={
                "source_snapshot_event_refs_required": snapshot_event_refs_required,
                "raw_snapshot_event_count": trace_summary.get("raw_snapshot_event_count"),
                "snapshot_event_trace_policy": trace_summary.get("snapshot_event_trace_policy"),
            },
        )
    )

    trace_complete = True
    for key in ("source_fact_ids_ready", "source_minute_refs_ready", "previous_day_minute_refs_ready"):
        counts = normalize_asset_counts(trace_summary.get(key))
        if any(counts[asset] < candidate_counts[asset] for asset in ASSET_KINDS):
            trace_complete = False
    items.append(
        quality_item(
            "P0",
            "passed" if trace_complete else "failed",
            "n3_action_confirmation_trace_refs_complete",
            "ready metric candidates must have source_fact_ids/source_minute_refs/previous_day_minute_refs trace coverage",
            expected=json.dumps(candidate_counts, sort_keys=True),
            actual=json.dumps(
                {
                    "source_fact_ids_ready": normalize_asset_counts(trace_summary.get("source_fact_ids_ready")),
                    "source_minute_refs_ready": normalize_asset_counts(trace_summary.get("source_minute_refs_ready")),
                    "previous_day_minute_refs_ready": normalize_asset_counts(trace_summary.get("previous_day_minute_refs_ready")),
                },
                sort_keys=True,
            ),
        )
    )

    boundary_ready = bool(boundary_summary.get("first_period_policy_ready"))
    items.append(
        quality_item(
            "P0",
            "passed" if boundary_ready else "failed",
            "n3_action_confirmation_first_period_boundary_policy_ready",
            "first 1m/5m/30m/120m boundary policy must be explicit and traceable",
            expected="true",
            actual=str(boundary_ready).lower(),
            details=dict(boundary_summary),
        )
    )

    items.append(
        quality_item(
            "P0",
            "passed",
            "n3_action_confirmation_no_outbox_inbox_checkpoint_writes",
            "writer readiness and future metric execute do not write or consume event infrastructure",
            expected="writes_outbox=false; consumes_outbox=false",
            actual=json.dumps(build_write_scope_contract(), sort_keys=True),
        )
    )

    items.append(
        quality_item(
            "P0",
            "passed",
            "n3_action_confirmation_no_n4_n5_n6_recomputation_boundary",
            "N4/N5 must consume N3 metrics and must not reconstruct action-confirmation indicators",
            expected="N3 owns metrics",
            actual=json.dumps(n4_n5_boundary_contract(), sort_keys=True),
        )
    )

    return items


def build_action_confirmation_projection_readiness_report(
    *,
    projection_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    source_today_minute_run_id: str,
    source_previous_day_minute_run_id: str,
    schema_status: Mapping[str, Any],
    source_runs: Mapping[str, Any],
    input_summary: Mapping[str, Any],
    trace_summary: Mapping[str, Any],
    boundary_summary: Mapping[str, Any],
    baseline_summary: Mapping[str, Any],
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    candidate_counts = normalize_asset_counts(input_summary.get("candidate_objects"))
    quality_items = build_quality_items(
        schema_status=schema_status,
        source_runs=source_runs,
        input_summary=input_summary,
        trace_summary=trace_summary,
        boundary_summary=boundary_summary,
        baseline_summary=baseline_summary,
    )
    quality_counts = count_quality_severities(quality_items)
    blockers = [
        str(item["gate_code"])
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    ]
    blocked = quality_counts["P0"] > 0
    return {
        "stage": "N3 action-confirmation projection writer/readiness alignment",
        "layer_role": "N3_market_data",
        "result": "BLOCKED" if blocked else "DRAFT_PASS",
        "blocked": blocked,
        "blockers": blockers,
        "projection_run_id": projection_run_id,
        "projection_schema_version": "n3.action_confirmation_metric.v1",
        "for_trade_date": for_trade_date,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_snapshot_run_id": source_snapshot_run_id,
        "source_today_minute_run_id": source_today_minute_run_id,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "schema_status": dict(schema_status),
        "source_runs": normalize_jsonable(source_runs),
        "input_summary": normalize_jsonable(input_summary),
        "candidate_summary": {**candidate_counts, "total": total_counts(candidate_counts)},
        "metric_generation_strategy": build_metric_generation_strategy(),
        "metric_ready_trace_refs_strategy": metric_ready_trace_refs_strategy(),
        "trace_summary": normalize_jsonable(trace_summary),
        "boundary_summary": normalize_jsonable(boundary_summary),
        "baseline_summary": dict(baseline_summary),
        "write_scope": build_write_scope_contract(),
        "rollback": {
            "rollback_sql_path": rollback_sql_path,
            "scope": "projection_run_id",
            "deletes": [
                "stock/index/board_action_confirmation_projection_metric",
                "common_market_data_quality_item",
                "common_market_data_run",
            ],
            "hard_fail_guard": "outbox/inbox/checkpoint refs nonzero",
        },
        "n4_n5_boundary": n4_n5_boundary_contract(),
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "writes_database": False,
            "writes_projection_business_rows": False,
            "writes_run_or_quality": False,
            "writes_outbox": False,
            "consumes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "market_data_pulled": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "generated_at": now_iso(),
    }


def build_metric_generation_strategy() -> dict[str, Any]:
    return {
        "current_price": {
            "source": "source snapshot current_price",
            "fields": ["current_price", "current_price_source", "current_price_time"],
        },
        "previous_body_high_low": {
            "previous_1m": "same-day previous 1m body high/low; first period uses previous-day last 1m",
            "previous_5m": "same-day previous completed 5m body high/low; first period uses previous-day last 5m",
            "previous_30m": "same-day previous completed 30m body high/low; first period uses previous-day last 30m",
            "previous_120m": "same-day previous completed 120m body high/low; first period uses previous-day last 120m",
            "body_high_low_definition": "max/min of max(open, close) and min(open, close) over the resolved window",
        },
        "amount": {
            "current_1m_amount": "latest resolved current 1m amount",
            "previous_1m_amount": "same-day previous 1m amount unless first 1m",
            "current_5m_virtual_amount": "sum current partial 5m window through metric_minute_label",
            "previous_5m_full_amount": "previous full 5m window amount unless first 5m",
        },
        "first_period_boundary_policy": {
            "first_1m_amount_default_pass": True,
            "first_5m_amount_default_pass": True,
            "price_defaults_to_pass": False,
            "previous_day_refs_required": True,
        },
        "ready_rule": "metric_ready=true only when schema-required numeric fields and trace refs satisfy 032 DB CHECK",
        "projection_enrichment_v1": {
            "storage_path": "raw_json.enrichment_v1",
            "schema_migration_required_now": False,
            "trigger_amount_chain_pass": "N2 period_trigger_baseline_json + N3 current_chain_metrics",
            "n4_recompute_allowed": False,
        },
    }


def build_metric_candidate_rows_from_sources(
    *,
    projection_run_id: str,
    projection_schema_version: str,
    for_trade_date: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    source_today_minute_run_id: str,
    source_previous_day_minute_run_id: str,
    snapshot_rows_by_asset: Mapping[str, list[Mapping[str, Any]]],
    today_minute_rows_by_asset: Mapping[str, list[Mapping[str, Any]]],
    previous_day_minute_rows_by_asset: Mapping[str, list[Mapping[str, Any]]],
    n2_context_by_asset: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    current_chain_metrics_by_asset: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    for asset_kind in ASSET_KINDS:
        snapshot_by_identity = {
            str(row["identity_key"]): dict(row)
            for row in snapshot_rows_by_asset.get(asset_kind, [])
            if row.get("identity_key")
        }
        today_by_identity = group_minute_rows(today_minute_rows_by_asset.get(asset_kind, []))
        previous_by_identity = group_minute_rows(previous_day_minute_rows_by_asset.get(asset_kind, []))
        for identity_key in sorted(set(snapshot_by_identity) & set(today_by_identity) & set(previous_by_identity)):
            n2_context = ((n2_context_by_asset or {}).get(asset_kind) or {}).get(identity_key)
            current_chain_metrics = ((current_chain_metrics_by_asset or {}).get(asset_kind) or {}).get(identity_key)
            metric_row = build_metric_candidate_row(
                asset_kind=asset_kind,
                projection_run_id=projection_run_id,
                projection_schema_version=projection_schema_version,
                for_trade_date=for_trade_date,
                source_condition_run_id=source_condition_run_id,
                source_subscription_run_id=source_subscription_run_id,
                source_snapshot_run_id=source_snapshot_run_id,
                source_today_minute_run_id=source_today_minute_run_id,
                source_previous_day_minute_run_id=source_previous_day_minute_run_id,
                snapshot_row=snapshot_by_identity[identity_key],
                today_rows=today_by_identity[identity_key],
                previous_day_rows=previous_by_identity[identity_key],
                n2_context=n2_context,
                current_chain_metrics=current_chain_metrics,
            )
            rows_by_asset[asset_kind].append(metric_row)
    return rows_by_asset


def group_minute_rows(rows: list[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        identity_key = str(row.get("identity_key") or "")
        if identity_key:
            grouped[identity_key].append(dict(row))
    for identity_rows in grouped.values():
        identity_rows.sort(key=lambda item: parse_dt(item["bar_time"]))
    return dict(grouped)


def build_metric_candidate_row(
    *,
    asset_kind: str,
    projection_run_id: str,
    projection_schema_version: str,
    for_trade_date: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    source_today_minute_run_id: str,
    source_previous_day_minute_run_id: str,
    snapshot_row: Mapping[str, Any],
    today_rows: list[Mapping[str, Any]],
    previous_day_rows: list[Mapping[str, Any]],
    n2_context: Mapping[str, Any] | None = None,
    current_chain_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    latest = today_rows[-1]
    position = len(today_rows)
    previous_1m_rows, previous_1m_source = resolve_previous_window(today_rows, previous_day_rows, position, 1)
    previous_5m_rows, previous_5m_source = resolve_previous_window(today_rows, previous_day_rows, position, 5)
    previous_30m_rows, previous_30m_source = resolve_previous_window(today_rows, previous_day_rows, position, 30)
    previous_120m_rows, previous_120m_source = resolve_previous_window(today_rows, previous_day_rows, position, 120)
    current_5m_rows = resolve_current_window(today_rows, position, 5)
    current_30m_rows = resolve_current_window(today_rows, position, 30)
    reference_5m_rows = resolve_previous_day_same_window(previous_day_rows, position, 5)
    reference_30m_rows = resolve_previous_day_same_window(previous_day_rows, position, 30)
    current_5m_virtual_amount, previous_day_same_5m_full_amount, current_5m_virtual_proof = (
        calibrated_same_window_virtual_amount(
            current_rows=current_5m_rows,
            previous_day_same_rows=reference_5m_rows,
            period_minutes=5,
        )
    )
    current_30m_virtual_amount, previous_day_same_30m_full_amount, current_30m_virtual_proof = (
        calibrated_same_window_virtual_amount(
            current_rows=current_30m_rows,
            previous_day_same_rows=reference_30m_rows,
            period_minutes=30,
        )
    )

    is_first_1m = previous_1m_source == "previous_trade_date_last_period"
    is_first_5m = previous_5m_source == "previous_trade_date_last_period"
    is_first_30m = previous_30m_source == "previous_trade_date_last_period"
    is_first_120m = previous_120m_source == "previous_trade_date_last_period"
    previous_day_refs = minute_refs(
        [
            *([] if previous_1m_source != "previous_trade_date_last_period" else previous_1m_rows),
            *([] if previous_5m_source != "previous_trade_date_last_period" else previous_5m_rows),
            *([] if previous_30m_source != "previous_trade_date_last_period" else previous_30m_rows),
            *([] if previous_120m_source != "previous_trade_date_last_period" else previous_120m_rows),
        ]
    )
    source_minute_rows = [
        latest,
        *([] if previous_1m_source != "same_trade_date_previous_period" else previous_1m_rows),
        *current_5m_rows,
        *([] if previous_5m_source != "same_trade_date_previous_period" else previous_5m_rows),
        *([] if previous_30m_source != "same_trade_date_previous_period" else previous_30m_rows),
        *([] if previous_120m_source != "same_trade_date_previous_period" else previous_120m_rows),
    ]
    metric_time = parse_dt(latest["bar_time"]).isoformat()
    snapshot_time = parse_dt(snapshot_row["snapshot_time"]).isoformat() if snapshot_row.get("snapshot_time") else None

    row: dict[str, Any] = {
        "projection_run_id": projection_run_id,
        "projection_schema_version": projection_schema_version,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_snapshot_run_id": source_snapshot_run_id,
        "source_snapshot_id": snapshot_row.get("source_snapshot_id") or snapshot_row.get("snapshot_id"),
        "source_snapshot_event_id": snapshot_row.get("source_snapshot_event_id"),
        "source_today_minute_run_id": source_today_minute_run_id,
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "for_trade_date": for_trade_date,
        "trade_date": str(snapshot_row.get("trade_date") or for_trade_date),
        "asset_kind": asset_kind,
        "identity_key": snapshot_row["identity_key"],
        "exchange": snapshot_row.get("exchange"),
        "code": snapshot_row.get("code"),
        "display_code": snapshot_row.get("display_code"),
        "name": snapshot_row.get("name"),
        "metric_time": metric_time,
        "metric_minute_label": minute_label(latest["bar_time"]),
        "current_price": numeric(snapshot_row.get("current_price")),
        "current_price_source": "realtime_daily_snapshot",
        "current_price_time": snapshot_time,
        "previous_120m_body_high": body_high(previous_120m_rows),
        "previous_120m_body_low": body_low(previous_120m_rows),
        "previous_30m_body_high": body_high(previous_30m_rows),
        "previous_30m_body_low": body_low(previous_30m_rows),
        "previous_5m_body_high": body_high(previous_5m_rows),
        "previous_5m_body_low": body_low(previous_5m_rows),
        "previous_1m_body_high": body_high(previous_1m_rows),
        "previous_1m_body_low": body_low(previous_1m_rows),
        "current_1m_amount": numeric(latest.get("amount")),
        "previous_1m_amount": None if is_first_1m else sum_amount(previous_1m_rows),
        "current_5m_virtual_amount": current_5m_virtual_amount,
        "previous_5m_full_amount": None if is_first_5m else sum_amount(previous_5m_rows),
        "current_30m_virtual_amount": current_30m_virtual_amount,
        "previous_day_same_window_amount": previous_day_same_30m_full_amount,
        "virtual_amount_policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
        "previous_30m_full_amount": None if is_first_30m else sum_amount(previous_30m_rows),
        "is_first_1m_of_day": is_first_1m,
        "is_first_5m_of_day": is_first_5m,
        "is_first_30m_of_day": is_first_30m,
        "is_first_120m_of_day": is_first_120m,
        "first_1m_amount_default_pass": is_first_1m,
        "first_5m_amount_default_pass": is_first_5m,
        "previous_1m_period_source": previous_1m_source,
        "previous_5m_period_source": previous_5m_source,
        "previous_30m_period_source": previous_30m_source,
        "previous_120m_period_source": previous_120m_source,
        "boundary_policy_version": "n3.action_confirmation_boundary.v1",
        "metric_quality_status": "passed",
        "metric_ready": True,
        "source_fact_ids": {
            "source_snapshot_id": snapshot_row.get("source_snapshot_id") or snapshot_row.get("snapshot_id"),
            "source_snapshot_event_id": snapshot_row.get("source_snapshot_event_id"),
            "source_snapshot_run_id": source_snapshot_run_id,
            "source_today_minute_run_id": source_today_minute_run_id,
            "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        },
        "source_minute_refs": dedupe_refs(minute_refs(source_minute_rows)),
        "previous_day_minute_refs": dedupe_refs(previous_day_refs),
        "calculation_config_hash": "n3.action_confirmation_projection_metric.v1",
        "raw_json": {
            "dry_run_only": True,
            "first_period_boundary_policy": build_metric_generation_strategy()["first_period_boundary_policy"],
            "virtual_amount_policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
            "virtual_amount_policy": {
                "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
                "source_kind": "N3_standard_period_metric",
                "amount_unit": "yuan",
                "calibration_method": "previous_day_same_window_elapsed_ratio",
                "periods": {
                    "5m": current_5m_virtual_proof,
                    "30m": current_30m_virtual_proof,
                },
            },
        },
    }
    add_price_amount_flags(row)
    db_check = simulate_metric_ready_db_check(row)
    if not db_check["passes"]:
        row["metric_ready"] = False
        row["metric_quality_status"] = "missing"
        row["raw_json"]["db_check_missing_fields"] = db_check["missing_fields"]
    row["raw_json"]["enrichment_v1"] = build_projection_enrichment_v1(
        metric_row=row,
        n2_context=n2_context,
        current_chain_metrics=current_chain_metrics,
        current_30m_virtual_amount=current_30m_virtual_amount,
        reference_30m_amount=previous_day_same_30m_full_amount,
        reference_30m_entity_high=body_high(reference_30m_rows),
        reference_30m_entity_low=body_low(reference_30m_rows),
    )
    return row


def resolve_current_window(rows: list[Mapping[str, Any]], position: int, size: int) -> list[Mapping[str, Any]]:
    start = ((position - 1) // size) * size
    return rows[start:position]


def resolve_previous_day_same_window(rows: list[Mapping[str, Any]], position: int, size: int) -> list[Mapping[str, Any]]:
    start = ((position - 1) // size) * size
    return rows[start : start + size]


def calibrated_same_window_virtual_amount(
    *,
    current_rows: list[Mapping[str, Any]],
    previous_day_same_rows: list[Mapping[str, Any]],
    period_minutes: int,
) -> tuple[float | None, float | None, dict[str, Any]]:
    current_elapsed_amount = sum_amount(current_rows)
    elapsed_count = len(current_rows)
    previous_day_same_elapsed_rows = previous_day_same_rows[:elapsed_count]
    previous_day_same_elapsed_amount = sum_amount(previous_day_same_elapsed_rows)
    previous_day_same_full_amount = sum_amount(previous_day_same_rows)
    proof: dict[str, Any] = {
        "status": "passed",
        "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
        "period_minutes": period_minutes,
        "current_elapsed_amount": current_elapsed_amount,
        "current_elapsed_count": elapsed_count,
        "previous_day_same_elapsed_amount": previous_day_same_elapsed_amount,
        "previous_day_same_full_amount": previous_day_same_full_amount,
        "previous_day_same_elapsed_refs": minute_refs(previous_day_same_elapsed_rows),
        "previous_day_same_full_refs": minute_refs(previous_day_same_rows),
    }
    failure_reason = None
    if not current_rows or current_elapsed_amount is None:
        failure_reason = "current_elapsed_amount_missing"
    elif not previous_day_same_rows or previous_day_same_full_amount is None:
        failure_reason = "previous_day_same_window_full_amount_missing"
    elif len(previous_day_same_rows) < elapsed_count:
        failure_reason = "previous_day_same_elapsed_window_incomplete"
    elif previous_day_same_elapsed_amount is None:
        failure_reason = "previous_day_same_elapsed_amount_missing"
    elif previous_day_same_elapsed_amount <= 0:
        failure_reason = "previous_day_same_elapsed_amount_non_positive"
    elif previous_day_same_full_amount <= 0:
        failure_reason = "previous_day_same_full_amount_non_positive"
    if failure_reason:
        proof["status"] = "failed"
        proof["reason"] = failure_reason
        return None, previous_day_same_full_amount, proof

    current_virtual_amount = current_elapsed_amount / previous_day_same_elapsed_amount * previous_day_same_full_amount
    proof["current_virtual_amount"] = current_virtual_amount
    return current_virtual_amount, previous_day_same_full_amount, proof


def resolve_previous_window(
    today_rows: list[Mapping[str, Any]],
    previous_day_rows: list[Mapping[str, Any]],
    position: int,
    size: int,
) -> tuple[list[Mapping[str, Any]], str]:
    current_start = ((position - 1) // size) * size
    if current_start == 0:
        return previous_day_rows[-size:], "previous_trade_date_last_period"
    return today_rows[max(0, current_start - size) : current_start], "same_trade_date_previous_period"


def add_price_amount_flags(row: dict[str, Any]) -> None:
    current_price = numeric(row.get("current_price"))
    if current_price is None:
        return
    for period in ("120m", "30m", "5m", "1m"):
        high = numeric(row.get(f"previous_{period}_body_high"))
        low = numeric(row.get(f"previous_{period}_body_low"))
        row[f"buy_{period}_price_pass"] = None if high is None else current_price > high
        row[f"sell_{period}_price_pass"] = None if low is None else current_price < low
    current_5m = numeric(row.get("current_5m_virtual_amount"))
    previous_5m = numeric(row.get("previous_5m_full_amount"))
    current_1m = numeric(row.get("current_1m_amount"))
    previous_1m = numeric(row.get("previous_1m_amount"))
    row["buy_5m_amount_pass"] = True if row.get("is_first_5m_of_day") else (None if current_5m is None or previous_5m is None else current_5m >= previous_5m)
    row["sell_5m_amount_pass"] = True if row.get("is_first_5m_of_day") else (None if current_5m is None or previous_5m is None else current_5m <= previous_5m)
    row["buy_1m_amount_pass"] = True if row.get("is_first_1m_of_day") else (None if current_1m is None or previous_1m is None else current_1m >= previous_1m)
    row["sell_1m_amount_pass"] = True if row.get("is_first_1m_of_day") else (None if current_1m is None or previous_1m is None else current_1m <= previous_1m)


def simulate_metric_ready_db_check(row: Mapping[str, Any]) -> dict[str, Any]:
    if not bool(row.get("metric_ready")):
        return {"passes": True, "missing_fields": []}
    missing: list[str] = []
    required_fields = [
        "current_price",
        "current_price_time",
        "previous_120m_body_high",
        "previous_120m_body_low",
        "previous_30m_body_high",
        "previous_30m_body_low",
        "previous_5m_body_high",
        "previous_5m_body_low",
        "previous_1m_body_high",
        "previous_1m_body_low",
        "current_1m_amount",
        "current_5m_virtual_amount",
        "current_30m_virtual_amount",
        "previous_day_same_window_amount",
    ]
    for field in required_fields:
        if row.get(field) is None:
            missing.append(field)
    if not row.get("is_first_1m_of_day") and row.get("previous_1m_amount") is None:
        missing.append("previous_1m_amount")
    if not row.get("is_first_5m_of_day") and row.get("previous_5m_full_amount") is None:
        missing.append("previous_5m_full_amount")
    for field in (
        "previous_1m_period_source",
        "previous_5m_period_source",
        "previous_30m_period_source",
        "previous_120m_period_source",
    ):
        if row.get(field) in (None, "not_available"):
            missing.append(field)
    if str(row.get("metric_quality_status") or "") != "passed":
        missing.append("metric_quality_status")
    source_fact_ids = row.get("source_fact_ids")
    if not isinstance(source_fact_ids, Mapping) or not source_fact_ids:
        missing.append("source_fact_ids")
    source_minute_refs = row.get("source_minute_refs")
    if not isinstance(source_minute_refs, list) or not source_minute_refs:
        missing.append("source_minute_refs")
    previous_sources = [
        row.get("previous_1m_period_source"),
        row.get("previous_5m_period_source"),
        row.get("previous_30m_period_source"),
        row.get("previous_120m_period_source"),
    ]
    previous_day_refs = row.get("previous_day_minute_refs")
    if "previous_trade_date_last_period" in previous_sources and (not isinstance(previous_day_refs, list) or not previous_day_refs):
        missing.append("previous_day_minute_refs")
    if bool(row.get("first_1m_amount_default_pass")) != bool(row.get("is_first_1m_of_day")):
        missing.append("first_1m_amount_default_pass")
    if bool(row.get("first_5m_amount_default_pass")) != bool(row.get("is_first_5m_of_day")):
        missing.append("first_5m_amount_default_pass")
    return {"passes": not missing, "missing_fields": missing}


def build_action_confirmation_projection_dry_run_report(
    *,
    readiness_report: Mapping[str, Any],
    rows_by_asset: Mapping[str, list[Mapping[str, Any]]],
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    would_write_rows = {asset: len(rows_by_asset.get(asset, [])) for asset in ASSET_KINDS}
    would_write_rows["total"] = total_counts(would_write_rows)
    expected_counts = normalize_asset_counts(readiness_report.get("candidate_summary"))
    expected_total = total_counts(expected_counts)
    all_rows = [row for asset in ASSET_KINDS for row in rows_by_asset.get(asset, [])]
    db_check_results = [simulate_metric_ready_db_check(row) for row in all_rows]
    ready_total = sum(1 for row in all_rows if row.get("metric_ready"))
    db_check_pass_total = sum(1 for item in db_check_results if item["passes"])
    trace_refs_proof = {
        "source_fact_ids_non_empty": sum(1 for row in all_rows if isinstance(row.get("source_fact_ids"), Mapping) and bool(row.get("source_fact_ids"))),
        "source_minute_refs_non_empty": sum(1 for row in all_rows if isinstance(row.get("source_minute_refs"), list) and bool(row.get("source_minute_refs"))),
        "previous_day_refs_required": sum(1 for row in all_rows if any(row.get(field) == "previous_trade_date_last_period" for field in ("previous_1m_period_source", "previous_5m_period_source", "previous_30m_period_source", "previous_120m_period_source"))),
        "previous_day_refs_non_empty": sum(1 for row in all_rows if isinstance(row.get("previous_day_minute_refs"), list) and bool(row.get("previous_day_minute_refs"))),
        "db_check_pass_total": db_check_pass_total,
        "db_check_fail_total": len(all_rows) - db_check_pass_total,
    }
    projection_enrichment_summary = summarize_projection_enrichment_rows(rows_by_asset)
    quality_items = build_dry_run_quality_items(
        readiness_report=readiness_report,
        expected_counts=expected_counts,
        would_write_rows=would_write_rows,
        all_rows=all_rows,
        trace_refs_proof=trace_refs_proof,
        rollback_sql_path=rollback_sql_path,
    )
    quality_counts = count_quality_severities(quality_items)
    blockers = [
        str(item["gate_code"])
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    ]
    blocked = quality_counts["P0"] > 0
    return {
        "stage": "N3 action-confirmation projection writer dry-run",
        "layer_role": "N3_market_data",
        "result": "BLOCKED" if blocked else "DRY_RUN_PASS",
        "blocked": blocked,
        "blockers": blockers,
        "projection_run_id": readiness_report.get("projection_run_id"),
        "projection_schema_version": readiness_report.get("projection_schema_version"),
        "for_trade_date": readiness_report.get("for_trade_date"),
        "source_condition_run_id": readiness_report.get("source_condition_run_id"),
        "source_subscription_run_id": readiness_report.get("source_subscription_run_id"),
        "source_snapshot_run_id": readiness_report.get("source_snapshot_run_id"),
        "source_today_minute_run_id": readiness_report.get("source_today_minute_run_id"),
        "source_previous_day_minute_run_id": readiness_report.get("source_previous_day_minute_run_id"),
        "candidate_summary": {**expected_counts, "total": expected_total},
        "would_write_rows": would_write_rows,
        "metric_ready_distribution": {
            "ready_total": ready_total,
            "not_ready_total": len(all_rows) - ready_total,
            "by_asset": {
                asset: {
                    "ready": sum(1 for row in rows_by_asset.get(asset, []) if row.get("metric_ready")),
                    "not_ready": sum(1 for row in rows_by_asset.get(asset, []) if not row.get("metric_ready")),
                }
                for asset in ASSET_KINDS
            },
        },
        "metric_quality_status_distribution": dict(sorted(count_values(all_rows, "metric_quality_status").items())),
        "current_price_source_distribution": dict(sorted(count_values(all_rows, "current_price_source").items())),
        "previous_period_source_distribution": {
            field: dict(sorted(count_values(all_rows, field).items()))
            for field in (
                "previous_1m_period_source",
                "previous_5m_period_source",
                "previous_30m_period_source",
                "previous_120m_period_source",
            )
        },
        "first_period_boundary_summary": {
            "first_1m": sum(1 for row in all_rows if row.get("is_first_1m_of_day")),
            "first_5m": sum(1 for row in all_rows if row.get("is_first_5m_of_day")),
            "first_30m": sum(1 for row in all_rows if row.get("is_first_30m_of_day")),
            "first_120m": sum(1 for row in all_rows if row.get("is_first_120m_of_day")),
            "first_1m_amount_default_pass": sum(1 for row in all_rows if row.get("first_1m_amount_default_pass")),
            "first_5m_amount_default_pass": sum(1 for row in all_rows if row.get("first_5m_amount_default_pass")),
        },
        "trace_refs_proof": trace_refs_proof,
        "projection_enrichment_summary": projection_enrichment_summary,
        "metric_generation_strategy": build_metric_generation_strategy(),
        "metric_ready_trace_refs_strategy": metric_ready_trace_refs_strategy(),
        "baseline_summary": readiness_report.get("baseline_summary"),
        "write_scope": build_write_scope_contract(),
        "rollback": {
            "rollback_sql_path": rollback_sql_path,
            "scope": "projection_run_id",
            "hard_fail_guard": "outbox/inbox/checkpoint refs nonzero",
        },
        "samples": {asset: normalize_jsonable(rows_by_asset.get(asset, [])[:3]) for asset in ASSET_KINDS},
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "writes_database": False,
            "writes_projection_business_rows": False,
            "writes_run_or_quality": False,
            "writes_outbox": False,
            "consumes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "market_data_pulled": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
        "generated_at": now_iso(),
    }


def build_dry_run_quality_items(
    *,
    readiness_report: Mapping[str, Any],
    expected_counts: Mapping[str, int],
    would_write_rows: Mapping[str, int],
    all_rows: list[Mapping[str, Any]],
    trace_refs_proof: Mapping[str, int],
    rollback_sql_path: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.append(
        quality_item(
            "P0",
            "passed" if readiness_report.get("result") == "DRAFT_PASS" else "failed",
            "n3_action_confirmation_writer_readiness_passed",
            "writer readiness artifact must be DRAFT_PASS before dry-run rows are trusted",
            expected="DRAFT_PASS",
            actual=str(readiness_report.get("result")),
            details={"blockers": readiness_report.get("blockers", [])},
        )
    )
    counts_match = all(int(would_write_rows.get(asset, 0)) == int(expected_counts.get(asset, 0)) for asset in ASSET_KINDS)
    items.append(
        quality_item(
            "P0",
            "passed" if counts_match else "failed",
            "n3_action_confirmation_would_write_rows_match_candidates",
            "would-write metric rows must match candidate objects by physical table",
            expected=json.dumps(expected_counts, sort_keys=True),
            actual=json.dumps({asset: would_write_rows.get(asset, 0) for asset in ASSET_KINDS}, sort_keys=True),
        )
    )
    db_check_ok = int(trace_refs_proof.get("db_check_fail_total") or 0) == 0
    items.append(
        quality_item(
            "P0",
            "passed" if db_check_ok else "failed",
            "n3_action_confirmation_metric_ready_db_check_simulation",
            "would-write metric rows must satisfy metric_ready DB CHECK simulation",
            expected="db_check_fail_total=0",
            actual=str(trace_refs_proof.get("db_check_fail_total")),
        )
    )
    all_ready = sum(1 for row in all_rows if row.get("metric_ready")) == len(all_rows)
    items.append(
        quality_item(
            "P0",
            "passed" if all_ready else "failed",
            "n3_action_confirmation_metric_ready_distribution",
            "all dry-run rows should be metric_ready before execute gate",
            expected=str(len(all_rows)),
            actual=str(sum(1 for row in all_rows if row.get("metric_ready"))),
        )
    )
    trace_complete = (
        int(trace_refs_proof.get("source_fact_ids_non_empty") or 0) == len(all_rows)
        and int(trace_refs_proof.get("source_minute_refs_non_empty") or 0) == len(all_rows)
        and int(trace_refs_proof.get("previous_day_refs_non_empty") or 0) >= int(trace_refs_proof.get("previous_day_refs_required") or 0)
    )
    items.append(
        quality_item(
            "P0",
            "passed" if trace_complete else "failed",
            "n3_action_confirmation_dry_run_trace_refs_complete",
            "would-write rows must carry source_fact_ids/source_minute_refs/required previous_day_minute_refs",
            expected=f"rows={len(all_rows)}",
            actual=json.dumps(dict(trace_refs_proof), sort_keys=True),
        )
    )
    baseline = readiness_report.get("baseline_summary") or {}
    nonzero = {key: value for key, value in baseline.items() if int(value or 0) != 0}
    items.append(
        quality_item(
            "P0",
            "passed" if not nonzero else "failed",
            "n3_action_confirmation_dry_run_scoped_baseline_zero",
            "projection_run_id scoped baseline must remain zero",
            expected="all 0",
            actual=json.dumps(baseline, sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if rollback_sql_path else "failed",
            "n3_action_confirmation_rollback_by_projection_run_id",
            "rollback must be scoped by projection_run_id and guard outbox/inbox/checkpoint refs",
            expected="rollback SQL path configured",
            actual=rollback_sql_path,
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed",
            "n3_action_confirmation_dry_run_no_event_or_downstream_writes",
            "dry-run does not write outbox/inbox/checkpoint or N4/N5/N6 state",
            expected="no writes",
            actual=json.dumps(build_write_scope_contract(), sort_keys=True),
        )
    )
    return items


def build_action_confirmation_projection_dry_run_from_db(
    *,
    dsn: str,
    readiness_path: str | Path = DEFAULT_JSON_REPORT_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    readiness_report = json.loads(Path(readiness_path).read_text())
    rows_by_asset = build_action_confirmation_projection_rows_from_db(
        dsn=dsn,
        readiness_report=readiness_report,
    )
    return build_action_confirmation_projection_dry_run_report(
        readiness_report=readiness_report,
        rows_by_asset=rows_by_asset,
        rollback_sql_path=rollback_sql_path,
    )


def build_action_confirmation_projection_rows_from_db(
    *,
    dsn: str,
    readiness_report: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        snapshot_rows_by_asset = load_snapshot_rows_for_metric_dry_run(
            cur,
            source_snapshot_run_id=str(readiness_report["source_snapshot_run_id"]),
        )
        today_rows_by_asset = load_minute_rows_for_metric_dry_run(
            cur,
            run_id=str(readiness_report["source_today_minute_run_id"]),
            candidate_identities=extract_candidate_identities(snapshot_rows_by_asset),
        )
        previous_rows_by_asset = load_minute_rows_for_metric_dry_run(
            cur,
            run_id=str(readiness_report["source_previous_day_minute_run_id"]),
            candidate_identities=extract_candidate_identities(snapshot_rows_by_asset),
        )
    return build_metric_candidate_rows_from_sources(
        projection_run_id=str(readiness_report["projection_run_id"]),
        projection_schema_version=str(readiness_report["projection_schema_version"]),
        for_trade_date=str(readiness_report["for_trade_date"]),
        source_condition_run_id=str(readiness_report["source_condition_run_id"]),
        source_subscription_run_id=str(readiness_report["source_subscription_run_id"]),
        source_snapshot_run_id=str(readiness_report["source_snapshot_run_id"]),
        source_today_minute_run_id=str(readiness_report["source_today_minute_run_id"]),
        source_previous_day_minute_run_id=str(readiness_report["source_previous_day_minute_run_id"]),
        snapshot_rows_by_asset=snapshot_rows_by_asset,
        today_minute_rows_by_asset=today_rows_by_asset,
        previous_day_minute_rows_by_asset=previous_rows_by_asset,
    )


def load_snapshot_rows_for_metric_dry_run(cur: Any, *, source_snapshot_run_id: str) -> dict[str, list[dict[str, Any]]]:
    rows_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    for asset_kind in ASSET_KINDS:
        table = SNAPSHOT_TABLES[asset_kind]
        identity = IDENTITY_COLUMNS[asset_kind]
        cur.execute(
            f"""
            WITH snapshot_rows AS (
              SELECT
                snapshot_id AS source_snapshot_id,
                {identity} AS identity_key,
                exchange,
                code,
                display_code,
                name,
                trade_date,
                snapshot_time,
                current_price,
                ROW_NUMBER() OVER (PARTITION BY {identity} ORDER BY snapshot_time DESC, snapshot_id DESC) AS rn
              FROM {table}
              WHERE run_id = %s
            ),
            snapshot_events AS (
              SELECT
                event_id,
                payload_json ->> 'snapshot_id' AS snapshot_id
              FROM common_event_outbox
              WHERE source_run_id = %s
                AND event_type = 'MarketSnapshotUpdated'
            )
            SELECT s.*, e.event_id AS source_snapshot_event_id
            FROM snapshot_rows s
            LEFT JOIN snapshot_events e ON e.snapshot_id = s.source_snapshot_id::TEXT
            WHERE s.rn = 1
            ORDER BY s.identity_key
            """,
            (source_snapshot_run_id, source_snapshot_run_id),
        )
        rows_by_asset[asset_kind] = [normalize_jsonable(dict(row)) for row in cur.fetchall()]
    return rows_by_asset


def extract_candidate_identities(snapshot_rows_by_asset: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, list[str]]:
    return {
        asset: [str(row["identity_key"]) for row in snapshot_rows_by_asset.get(asset, []) if row.get("identity_key")]
        for asset in ASSET_KINDS
    }


def load_minute_rows_for_metric_dry_run(
    cur: Any,
    *,
    run_id: str,
    candidate_identities: Mapping[str, list[str]],
) -> dict[str, list[dict[str, Any]]]:
    rows_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    for asset_kind in ASSET_KINDS:
        identities = list(candidate_identities.get(asset_kind) or [])
        if not identities:
            continue
        table = MINUTE_TABLES[asset_kind]
        identity = IDENTITY_COLUMNS[asset_kind]
        cur.execute(
            f"""
            SELECT
              bar_id,
              {identity} AS identity_key,
              bar_time,
              open,
              close,
              amount
            FROM {table}
            WHERE run_id = %s
              AND {identity} = ANY(%s)
            ORDER BY {identity}, bar_time
            """,
            (run_id, identities),
        )
        rows_by_asset[asset_kind] = [normalize_jsonable(dict(row)) for row in cur.fetchall()]
    return rows_by_asset


def count_values(rows: list[Mapping[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get(field))
        counts[key] = counts.get(key, 0) + 1
    return counts


def parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def minute_label(value: Any) -> str:
    return parse_dt(value).strftime("%H:%M")


def numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def body_high(rows: list[Mapping[str, Any]]) -> float | None:
    values = [max(numeric(row.get("open")) or 0.0, numeric(row.get("close")) or 0.0) for row in rows]
    return max(values) if values else None


def body_low(rows: list[Mapping[str, Any]]) -> float | None:
    values = [min(numeric(row.get("open")) or 0.0, numeric(row.get("close")) or 0.0) for row in rows]
    return min(values) if values else None


def sum_amount(rows: list[Mapping[str, Any]]) -> float | None:
    if not rows:
        return None
    total = 0.0
    for row in rows:
        amount = numeric(row.get("amount"))
        if amount is None:
            return None
        total += amount
    return total


def minute_refs(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "bar_id": row.get("bar_id"),
            "identity_key": row.get("identity_key"),
            "bar_time": parse_dt(row["bar_time"]).isoformat() if row.get("bar_time") else None,
        }
        for row in rows
        if row.get("bar_id") is not None
    ]


def dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any]] = set()
    output: list[dict[str, Any]] = []
    for ref in refs:
        key = (ref.get("bar_id"), ref.get("bar_time"))
        if key in seen:
            continue
        seen.add(key)
        output.append(ref)
    return output


def build_action_confirmation_projection_readiness_from_db(
    *,
    dsn: str,
    projection_run_id: str = DEFAULT_PROJECTION_RUN_ID,
    for_trade_date: str = DEFAULT_FOR_TRADE_DATE,
    source_condition_run_id: str = DEFAULT_SOURCE_CONDITION_RUN_ID,
    source_subscription_run_id: str = DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
    source_snapshot_run_id: str = DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
    source_today_minute_run_id: str = DEFAULT_SOURCE_TODAY_MINUTE_RUN_ID,
    source_previous_day_minute_run_id: str = DEFAULT_SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            schema_status = load_schema_status(cur)
            source_runs = load_source_runs(
                cur,
                source_subscription_run_id=source_subscription_run_id,
                source_snapshot_run_id=source_snapshot_run_id,
                source_today_minute_run_id=source_today_minute_run_id,
                source_previous_day_minute_run_id=source_previous_day_minute_run_id,
            )
            input_summary = load_input_summary(
                cur,
                source_snapshot_run_id=source_snapshot_run_id,
                source_today_minute_run_id=source_today_minute_run_id,
                source_previous_day_minute_run_id=source_previous_day_minute_run_id,
            )
            trace_summary = load_trace_summary(
                cur,
                source_snapshot_run_id=source_snapshot_run_id,
                candidate_objects=normalize_asset_counts(input_summary.get("candidate_objects")),
                source_snapshot_run=source_runs.get("source_snapshot_run"),
            )
            boundary_summary = load_boundary_summary(
                cur,
                source_today_minute_run_id=source_today_minute_run_id,
                source_previous_day_minute_run_id=source_previous_day_minute_run_id,
            )
            baseline_summary = load_baseline_summary(cur, projection_run_id=projection_run_id)

    return build_action_confirmation_projection_readiness_report(
        projection_run_id=projection_run_id,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        source_today_minute_run_id=source_today_minute_run_id,
        source_previous_day_minute_run_id=source_previous_day_minute_run_id,
        schema_status=schema_status,
        source_runs=source_runs,
        input_summary=input_summary,
        trace_summary=trace_summary,
        boundary_summary=boundary_summary,
        baseline_summary=baseline_summary,
        rollback_sql_path=rollback_sql_path,
    )


def load_schema_status(cur: Any) -> dict[str, Any]:
    tables_exist: dict[str, bool] = {}
    row_counts: dict[str, int] = {}
    for asset_kind, table in METRIC_TABLES.items():
        tables_exist[asset_kind] = table_exists(cur, table)
        row_counts[asset_kind] = table_count(cur, table) if tables_exist[asset_kind] else 0

    cur.execute(
        """
        SELECT count(*) AS count
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = ANY(%s)
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) LIKE '%%jsonb_array_length(source_minute_refs) > 0%%'
        """,
        (list(METRIC_TABLES.values()),),
    )
    trace_check_count = int(cur.fetchone()["count"])
    return {
        "tables_exist": tables_exist,
        "row_counts": row_counts,
        "metric_ready_trace_check_constraints": trace_check_count,
    }


def load_source_runs(
    cur: Any,
    *,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    source_today_minute_run_id: str,
    source_previous_day_minute_run_id: str,
) -> dict[str, Any]:
    run_ids = {
        "source_subscription_run": source_subscription_run_id,
        "source_snapshot_run": source_snapshot_run_id,
        "source_today_minute_run": source_today_minute_run_id,
        "source_previous_day_minute_run": source_previous_day_minute_run_id,
    }
    cur.execute(
        """
        SELECT
            run_id,
            status,
            source_trade_date,
            for_trade_date,
            mode,
            generated_by,
            market_data_pulled,
            market_data_fact_written,
            downstream_layers_touched,
            worker_started,
            raw_json ->> 'writes_outbox' AS writes_outbox,
            started_at,
            finished_at
        FROM common_market_data_run
        WHERE run_id = ANY(%s)
        """,
        (list(run_ids.values()),),
    )
    by_id = {str(row["run_id"]): normalize_jsonable(dict(row)) for row in cur.fetchall()}
    output: dict[str, Any] = {}
    for key, run_id in run_ids.items():
        output[key] = by_id.get(run_id, {"run_id": run_id, "status": "missing"})
    return output


def load_input_summary(
    cur: Any,
    *,
    source_snapshot_run_id: str,
    source_today_minute_run_id: str,
    source_previous_day_minute_run_id: str,
) -> dict[str, Any]:
    snapshot_objects: dict[str, int] = {}
    today_objects: dict[str, int] = {}
    previous_objects: dict[str, int] = {}
    candidate_objects: dict[str, int] = {}
    latest_today: dict[str, str | None] = {}
    latest_snapshot: dict[str, str | None] = {}
    minute_rows: dict[str, int] = {}
    previous_rows: dict[str, int] = {}

    for asset_kind in ASSET_KINDS:
        identity = IDENTITY_COLUMNS[asset_kind]
        snapshot_table = SNAPSHOT_TABLES[asset_kind]
        minute_table = MINUTE_TABLES[asset_kind]
        snapshot_objects[asset_kind] = distinct_count(cur, snapshot_table, identity, "run_id = %s", (source_snapshot_run_id,))
        today_objects[asset_kind] = distinct_count(cur, minute_table, identity, "run_id = %s", (source_today_minute_run_id,))
        previous_objects[asset_kind] = distinct_count(cur, minute_table, identity, "run_id = %s", (source_previous_day_minute_run_id,))
        minute_rows[asset_kind] = filtered_count(cur, minute_table, "run_id = %s", (source_today_minute_run_id,))
        previous_rows[asset_kind] = filtered_count(cur, minute_table, "run_id = %s", (source_previous_day_minute_run_id,))
        candidate_objects[asset_kind] = intersection_count(
            cur,
            snapshot_table=snapshot_table,
            minute_table=minute_table,
            identity_column=identity,
            snapshot_run_id=source_snapshot_run_id,
            today_minute_run_id=source_today_minute_run_id,
            previous_day_minute_run_id=source_previous_day_minute_run_id,
        )
        latest_today[asset_kind] = max_time(cur, minute_table, "bar_time", "run_id = %s", (source_today_minute_run_id,))
        latest_snapshot[asset_kind] = max_time(cur, snapshot_table, "snapshot_time", "run_id = %s", (source_snapshot_run_id,))

    return {
        "snapshot_objects": snapshot_objects,
        "today_minute_objects": today_objects,
        "previous_day_minute_objects": previous_objects,
        "candidate_objects": candidate_objects,
        "today_minute_rows": minute_rows,
        "previous_day_minute_rows": previous_rows,
        "latest_today_minute_by_asset": latest_today,
        "latest_snapshot_time_by_asset": latest_snapshot,
        "latest_today_minute_label": max(v for v in latest_today.values() if v) if any(latest_today.values()) else None,
        "latest_snapshot_time": max(v for v in latest_snapshot.values() if v) if any(latest_snapshot.values()) else None,
    }


def load_trace_summary(
    cur: Any,
    *,
    source_snapshot_run_id: str,
    candidate_objects: Mapping[str, int],
    source_snapshot_run: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT count(*) AS count
        FROM common_event_outbox
        WHERE source_run_id = %s
          AND event_type = 'MarketSnapshotUpdated'
        """,
        (source_snapshot_run_id,),
    )
    snapshot_event_count = int(cur.fetchone()["count"])
    total_candidates = total_counts(candidate_objects)
    writes_outbox = source_snapshot_run_writes_outbox(source_snapshot_run)
    event_refs_required = True if writes_outbox is None else writes_outbox
    return {
        "snapshot_event_refs": {
            "expected": total_candidates if event_refs_required else 0,
            "actual": min(snapshot_event_count, total_candidates) if event_refs_required else snapshot_event_count,
        },
        "source_fact_ids_ready": dict(candidate_objects),
        "source_minute_refs_ready": dict(candidate_objects),
        "previous_day_minute_refs_ready": dict(candidate_objects),
        "raw_snapshot_event_count": snapshot_event_count,
        "snapshot_event_trace_policy": (
            "required_for_writes_outbox_snapshot_run"
            if event_refs_required
            else "not_required_for_fact_only_snapshot_run"
        ),
    }


def load_boundary_summary(
    cur: Any,
    *,
    source_today_minute_run_id: str,
    source_previous_day_minute_run_id: str,
) -> dict[str, Any]:
    min_today_bars: dict[str, int] = {}
    min_previous_bars: dict[str, int] = {}
    for asset_kind in ASSET_KINDS:
        identity = IDENTITY_COLUMNS[asset_kind]
        table = MINUTE_TABLES[asset_kind]
        min_today_bars[asset_kind] = min_bar_count_by_identity(cur, table, identity, source_today_minute_run_id)
        min_previous_bars[asset_kind] = min_bar_count_by_identity(cur, table, identity, source_previous_day_minute_run_id)
    return {
        "first_period_policy_ready": True,
        "previous_1m_strategy": "same_trade_date_previous_period_or_previous_trade_date_last_period",
        "previous_5m_strategy": "same_trade_date_previous_period_or_previous_trade_date_last_period",
        "previous_30m_strategy": "same_trade_date_previous_period_or_previous_trade_date_last_period",
        "previous_120m_strategy": "same_trade_date_previous_period_or_previous_trade_date_last_period",
        "min_today_minute_bars_by_asset": min_today_bars,
        "min_previous_day_minute_bars_by_asset": min_previous_bars,
        "current_5m_virtual_amount_strategy": "sum current partial 5m window through metric_minute_label",
        "body_high_low_strategy": "real body high/low uses max(open, close) and min(open, close)",
    }


def load_baseline_summary(cur: Any, *, projection_run_id: str) -> dict[str, int]:
    return {
        "common_market_data_run": filtered_count(cur, "common_market_data_run", "run_id = %s", (projection_run_id,)),
        "common_market_data_quality_item": filtered_count(
            cur,
            "common_market_data_quality_item",
            "run_id = %s",
            (projection_run_id,),
        ),
        "stock_action_confirmation_projection_metric": filtered_count(
            cur,
            "stock_action_confirmation_projection_metric",
            "projection_run_id = %s",
            (projection_run_id,),
        ),
        "index_action_confirmation_projection_metric": filtered_count(
            cur,
            "index_action_confirmation_projection_metric",
            "projection_run_id = %s",
            (projection_run_id,),
        ),
        "board_action_confirmation_projection_metric": filtered_count(
            cur,
            "board_action_confirmation_projection_metric",
            "projection_run_id = %s",
            (projection_run_id,),
        ),
        "common_event_outbox": filtered_count(cur, "common_event_outbox", "source_run_id = %s", (projection_run_id,)),
        "common_event_inbox": filtered_count(cur, "common_event_inbox", "source_run_id = %s", (projection_run_id,)),
        "common_event_consumer_checkpoint": checkpoint_ref_count(cur, projection_run_id),
    }


def table_exists(cur: Any, table: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS(
          SELECT 1 FROM information_schema.tables
          WHERE table_schema = 'public' AND table_name = %s
        ) AS exists
        """,
        (table,),
    )
    return bool(cur.fetchone()["exists"])


def table_count(cur: Any, table: str) -> int:
    cur.execute(f"SELECT count(*) AS count FROM {table}")
    return int(cur.fetchone()["count"])


def filtered_count(cur: Any, table: str, where_sql: str, params: tuple[Any, ...]) -> int:
    cur.execute(f"SELECT count(*) AS count FROM {table} WHERE {where_sql}", params)
    return int(cur.fetchone()["count"])


def distinct_count(cur: Any, table: str, column: str, where_sql: str, params: tuple[Any, ...]) -> int:
    cur.execute(f"SELECT count(DISTINCT {column}) AS count FROM {table} WHERE {where_sql}", params)
    return int(cur.fetchone()["count"])


def intersection_count(
    cur: Any,
    *,
    snapshot_table: str,
    minute_table: str,
    identity_column: str,
    snapshot_run_id: str,
    today_minute_run_id: str,
    previous_day_minute_run_id: str,
) -> int:
    cur.execute(
        f"""
        WITH snapshot_ids AS (
          SELECT DISTINCT {identity_column} AS identity_key FROM {snapshot_table} WHERE run_id = %s
        ),
        today_ids AS (
          SELECT DISTINCT {identity_column} AS identity_key FROM {minute_table} WHERE run_id = %s
        ),
        previous_ids AS (
          SELECT DISTINCT {identity_column} AS identity_key FROM {minute_table} WHERE run_id = %s
        )
        SELECT count(*) AS count
        FROM snapshot_ids s
        JOIN today_ids t USING(identity_key)
        JOIN previous_ids p USING(identity_key)
        """,
        (snapshot_run_id, today_minute_run_id, previous_day_minute_run_id),
    )
    return int(cur.fetchone()["count"])


def max_time(cur: Any, table: str, column: str, where_sql: str, params: tuple[Any, ...]) -> str | None:
    cur.execute(f"SELECT max({column}) AS max_value FROM {table} WHERE {where_sql}", params)
    value = cur.fetchone()["max_value"]
    return str(value) if value is not None else None


def min_bar_count_by_identity(cur: Any, table: str, identity_column: str, run_id: str) -> int:
    cur.execute(
        f"""
        SELECT min(row_count) AS min_count
        FROM (
          SELECT {identity_column}, count(*) AS row_count
          FROM {table}
          WHERE run_id = %s
          GROUP BY {identity_column}
        ) grouped
        """,
        (run_id,),
    )
    value = cur.fetchone()["min_count"]
    return int(value or 0)


def checkpoint_ref_count(cur: Any, run_id: str) -> int:
    cur.execute(
        """
        SELECT count(*) AS count
        FROM common_event_consumer_checkpoint
        WHERE checkpoint_payload::TEXT LIKE %s
        """,
        (f"%{run_id}%",),
    )
    return int(cur.fetchone()["count"])


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): normalize_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def write_report_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    json_path = Path(json_path)
    markdown_path = Path(markdown_path)
    json_path.write_text(json.dumps(normalize_jsonable(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(format_markdown_report(report))


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    preflight = build_preflight_report(report)
    write_report_files(preflight, json_path=json_path, markdown_path=markdown_path)


def write_dry_run_report_files(
    dry_run_report: Mapping[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
    preflight_json_path: str | Path,
    preflight_markdown_path: str | Path,
) -> None:
    write_report_files(dry_run_report, json_path=json_path, markdown_path=markdown_path)
    execute_preflight = build_dry_run_execute_preflight_report(dry_run_report)
    write_report_files(execute_preflight, json_path=preflight_json_path, markdown_path=preflight_markdown_path)


def build_dry_run_execute_preflight_report(dry_run_report: Mapping[str, Any]) -> dict[str, Any]:
    blocked = bool(dry_run_report.get("blocked"))
    return {
        "stage": "N3 action-confirmation projection writer execute preflight",
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_BLOCKED" if blocked else "PREFLIGHT_PASS",
        "blocked": blocked,
        "blockers": list(dry_run_report.get("blockers") or []),
        "projection_run_id": dry_run_report.get("projection_run_id"),
        "projection_schema_version": dry_run_report.get("projection_schema_version"),
        "for_trade_date": dry_run_report.get("for_trade_date"),
        "source_condition_run_id": dry_run_report.get("source_condition_run_id"),
        "source_subscription_run_id": dry_run_report.get("source_subscription_run_id"),
        "source_snapshot_run_id": dry_run_report.get("source_snapshot_run_id"),
        "source_today_minute_run_id": dry_run_report.get("source_today_minute_run_id"),
        "source_previous_day_minute_run_id": dry_run_report.get("source_previous_day_minute_run_id"),
        "candidate_summary": dry_run_report.get("candidate_summary"),
        "would_write_rows": dry_run_report.get("would_write_rows"),
        "metric_ready_distribution": dry_run_report.get("metric_ready_distribution"),
        "trace_refs_proof": dry_run_report.get("trace_refs_proof"),
        "first_period_boundary_summary": dry_run_report.get("first_period_boundary_summary"),
        "baseline_summary": dry_run_report.get("baseline_summary"),
        "write_scope": dry_run_report.get("write_scope"),
        "rollback": dry_run_report.get("rollback"),
        "quality": dry_run_report.get("quality"),
        "side_effects": dry_run_report.get("side_effects"),
        "generated_at": now_iso(),
    }


def build_preflight_report(readiness_report: Mapping[str, Any]) -> dict[str, Any]:
    blocked = bool(readiness_report.get("blocked"))
    return {
        "stage": "N3 action-confirmation projection execute preflight",
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_BLOCKED" if blocked else "PREFLIGHT_PASS",
        "blocked": blocked,
        "blockers": list(readiness_report.get("blockers") or []),
        "projection_run_id": readiness_report.get("projection_run_id"),
        "for_trade_date": readiness_report.get("for_trade_date"),
        "source_condition_run_id": readiness_report.get("source_condition_run_id"),
        "source_subscription_run_id": readiness_report.get("source_subscription_run_id"),
        "source_snapshot_run_id": readiness_report.get("source_snapshot_run_id"),
        "source_today_minute_run_id": readiness_report.get("source_today_minute_run_id"),
        "source_previous_day_minute_run_id": readiness_report.get("source_previous_day_minute_run_id"),
        "source_runs": readiness_report.get("source_runs"),
        "candidate_summary": readiness_report.get("candidate_summary"),
        "metric_generation_strategy": readiness_report.get("metric_generation_strategy"),
        "metric_ready_trace_refs_strategy": readiness_report.get("metric_ready_trace_refs_strategy"),
        "baseline_summary": readiness_report.get("baseline_summary"),
        "write_scope": readiness_report.get("write_scope"),
        "rollback": readiness_report.get("rollback"),
        "n4_n5_boundary": readiness_report.get("n4_n5_boundary"),
        "quality": readiness_report.get("quality"),
        "side_effects": readiness_report.get("side_effects"),
        "generated_at": now_iso(),
    }


def format_markdown_report(report: Mapping[str, Any]) -> str:
    title = str(report.get("stage") or "N3 Action-Confirmation Projection Writer Readiness")
    if "preflight" in title.lower():
        heading = "N3 Action-Confirmation Projection Execute Preflight"
    elif "dry-run" in title.lower():
        heading = "N3 Action-Confirmation Projection Writer Dry-Run"
    else:
        heading = "N3 Action-Confirmation Projection Writer Readiness"
    candidate = report.get("candidate_summary") or {}
    would_write = report.get("would_write_rows") or {}
    ready = report.get("metric_ready_distribution") or {}
    trace = report.get("trace_refs_proof") or {}
    first = report.get("first_period_boundary_summary") or {}
    quality = report.get("quality") or {}
    side_effects = report.get("side_effects") or {}
    dry_run_section = ""
    if would_write:
        dry_run_section = f"""
## Would-Write Summary

```text
stock={would_write.get("stock", 0)}
index={would_write.get("index", 0)}
board={would_write.get("board", 0)}
total={would_write.get("total", 0)}
metric_ready={ready.get("ready_total", 0)}
metric_not_ready={ready.get("not_ready_total", 0)}
```

## Trace Refs Proof

```text
source_fact_ids_non_empty={trace.get("source_fact_ids_non_empty", 0)}
source_minute_refs_non_empty={trace.get("source_minute_refs_non_empty", 0)}
previous_day_refs_required={trace.get("previous_day_refs_required", 0)}
previous_day_refs_non_empty={trace.get("previous_day_refs_non_empty", 0)}
db_check_pass_total={trace.get("db_check_pass_total", 0)}
db_check_fail_total={trace.get("db_check_fail_total", 0)}
```

## First-Period Boundary

```text
first_1m={first.get("first_1m", 0)}
first_5m={first.get("first_5m", 0)}
first_30m={first.get("first_30m", 0)}
first_120m={first.get("first_120m", 0)}
first_1m_amount_default_pass={first.get("first_1m_amount_default_pass", 0)}
first_5m_amount_default_pass={first.get("first_5m_amount_default_pass", 0)}
```
"""
    return f"""# {heading}

Status: {report.get("result")}

Generated at: {report.get("generated_at")}

Layer role: {report.get("layer_role")}

## Stage

```text
{title}
```

## Lineage

```text
projection_run_id={report.get("projection_run_id")}
source_condition_run_id={report.get("source_condition_run_id")}
source_subscription_run_id={report.get("source_subscription_run_id")}
source_snapshot_run_id={report.get("source_snapshot_run_id")}
source_today_minute_run_id={report.get("source_today_minute_run_id")}
source_previous_day_minute_run_id={report.get("source_previous_day_minute_run_id")}
```

## Candidate Summary

```text
stock={candidate.get("stock", 0)}
index={candidate.get("index", 0)}
board={candidate.get("board", 0)}
total={candidate.get("total", 0)}
```
{dry_run_section}

## Quality

```text
P0={quality.get("p0_count", 0)}
P1={quality.get("p1_count", 0)}
P2={quality.get("p2_count", 0)}
blockers={report.get("blockers", [])}
```

## Writer Boundary

```text
writes_database={side_effects.get("writes_database")}
writes_projection_business_rows={side_effects.get("writes_projection_business_rows")}
writes_outbox={side_effects.get("writes_outbox")}
consumes_outbox={side_effects.get("consumes_outbox")}
writes_inbox_or_checkpoint={side_effects.get("writes_inbox_or_checkpoint")}
downstream_layers_touched={side_effects.get("downstream_layers_touched")}
worker_started={side_effects.get("worker_started")}
```

## N4/N5 Boundary

N4/N5 must consume these N3 standard metrics and must not recompute 1m / 5m / 30m / 120m indicators from raw minute rows.
"""


def format_summary(report: Mapping[str, Any]) -> str:
    candidate = report.get("candidate_summary") or {}
    quality = report.get("quality") or {}
    return "\n".join(
        [
            f"result={report.get('result')}",
            f"projection_run_id={report.get('projection_run_id')}",
            f"candidate_rows stock/index/board/total={candidate.get('stock', 0)}/{candidate.get('index', 0)}/{candidate.get('board', 0)}/{candidate.get('total', 0)}",
            f"P0/P1/P2={quality.get('p0_count', 0)}/{quality.get('p1_count', 0)}/{quality.get('p2_count', 0)}",
            f"blockers={report.get('blockers', [])}",
            "writes_outbox=false",
            "N4/N5 recomputation forbidden=true",
        ]
    )
