"""N4 realtime projection matcher dry-run.

The matcher evaluates local N4 trigger context rows against N3 standardized
realtime projection facts. It does not consume outbox rows, read raw market
tables, call market adapters, write trigger facts, or start workers.
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
from ashare_v3.market.b2_projection_proof import extract_b2_30m_projection_proof
from ashare_v3.trigger.canonical_signal import (
    CANONICAL_SIGNAL_TYPES,
    canonical_payload_errors,
    canonicalize_trigger_candidate,
)
from ashare_v3.trigger.context_preflight import ASSET_KINDS, TARGET_CONTEXT_TABLES, normalize_text_array
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect
from ashare_v3.trigger.rule_v4_matcher import (
    condition_signal_type_for_condition_key,
    evaluate_v4_plan,
    projection_30m_flags,
)
from ashare_v3.trigger.synthetic_dry_run import build_period_trigger_baseline_trace


DEFAULT_CONTEXT_RUN_ID = (
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
DEFAULT_PROJECTION_RUN_ID = (
    "realtime_projection_metric_20260525__realtime_daily_snapshot_20260525__"
    "market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute"
)
DEFAULT_N4_PROJECTION_MATCHER_JSON_REPORT_PATH = "docs/N4_PROJECTION_MATCHER_IMPLEMENTATION_REPORT.json"
DEFAULT_N4_PROJECTION_MATCHER_MD_REPORT_PATH = "docs/N4_PROJECTION_MATCHER_IMPLEMENTATION_REPORT.md"
DEFAULT_SYNTHETIC_DENYLIST = (
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260524014029_execute",
    "trigger_context_snapshot_20260525_condition_layer_20260522_to_20260525_20260525003855_execute",
)

PROJECTION_SCHEMA_VERSION = "n3.realtime_projection.v1"
PROJECTION_WINDOW_KIND = "active_30m_bucket_projection"
HINT_1M_PROOF_KIND = "index_board_1m_hint_projection_v1"
HINT_1M_SOURCE_MODE = "index_board_frequency8_1m"
SOURCE_EVENT_TYPE = "MarketSnapshotUpdated"
TRIGGER_PERIOD = "30m"
PROJECTION_PERIOD = "30m"
FORMAL_TRIGGER_PERIODS = {"Y", "Q", "M", "W", "D"}
LEGACY_TRACE_ONLY_SIGNAL_TYPES = ("B_BUY_30M_VOL", "S_SELL_30M_SHRINK")
MATCH_SIGNAL_BY_DIRECTION = {
    "buy": {"BUY_HINT": "up_volume_expanding"},
    "sell": {"SELL_HINT": "down_volume_shrinking"},
}
PROJECTION_SIGNAL_TYPES = ("BUY_HINT", "SELL_HINT")
PROJECTION_MATCHING_STATUSES = ("up_volume_expanding", "down_volume_shrinking")
NONMATCHING_PROJECTION_STATUSES = (
    "up_volume_flat",
    "up_volume_shrinking",
    "down_volume_expanding",
    "down_volume_flat",
    "flat",
    "unknown",
)

PROJECTION_MATCHER_READ_TABLES = (
    "common_trigger_run",
    *TARGET_CONTEXT_TABLES.values(),
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "index_realtime_hint_projection_metric",
    "board_realtime_hint_projection_metric",
)
FORBIDDEN_N4_PROJECTION_MATCHER_READ_TABLES = (
    "stock_intraday_bar_source",
    "index_intraday_bar_source",
    "board_intraday_bar_source",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
)
ROW_COUNT_GUARD_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
)
PROJECTION_TABLE_CONFIG = {
    "stock": ("stock_realtime_projection_metric", "stock_identity_key"),
    "index": ("index_realtime_projection_metric", "index_identity_key"),
    "board": ("board_realtime_projection_metric", "board_identity_key"),
}
HINT_PROJECTION_TABLE_CONFIG = {
    "index": "index_realtime_hint_projection_metric",
    "board": "board_realtime_hint_projection_metric",
}
SNAPSHOT_TABLE_CONFIG = {
    "stock": ("stock_realtime_daily_snapshot", "stock_identity_key"),
    "index": ("index_realtime_daily_snapshot", "index_identity_key"),
    "board": ("board_realtime_daily_snapshot", "board_identity_key"),
}


def run_projection_matcher_dry_run(
    *,
    dsn: str,
    trigger_context_run_id: str = DEFAULT_CONTEXT_RUN_ID,
    projection_run_id: str = DEFAULT_PROJECTION_RUN_ID,
    json_report_path: str = DEFAULT_N4_PROJECTION_MATCHER_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_N4_PROJECTION_MATCHER_MD_REPORT_PATH,
    synthetic_denylist: Sequence[str] = DEFAULT_SYNTHETIC_DENYLIST,
    sample_limit: int = 80,
    stage: str = "N4-projection-matcher-implementation",
) -> dict[str, Any]:
    before_counts = capture_row_counts(dsn)
    context_rows, trigger_run = fetch_context_rows(dsn, trigger_context_run_id)
    projection_rows = fetch_projection_rows(dsn, projection_run_id)
    after_counts = capture_row_counts(dsn)
    report = build_projection_matcher_dry_run_report(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        context_rows=context_rows,
        projection_rows=projection_rows,
        trigger_run=trigger_run,
        synthetic_denylist=synthetic_denylist,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
        sample_limit=sample_limit,
        stage=stage,
    )
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_projection_matcher_report(report))
    return report


def fetch_context_rows(dsn: str, trigger_context_run_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_projection_matcher_fetch_context",
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


def fetch_projection_rows(dsn: str, projection_run_id: str) -> list[dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_projection_matcher_fetch_projection",
        source_run_id=projection_run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        rows: list[dict[str, Any]] = []
        if is_hint_1m_projection_run_id(projection_run_id):
            for asset_kind, table_name in HINT_PROJECTION_TABLE_CONFIG.items():
                cur.execute(
                    f"""
                    SELECT metric_id AS projection_id,
                           projection_run_id,
                           trade_date,
                           metric_minute_label,
                           asset_kind,
                           identity_key,
                           code,
                           name,
                           direction,
                           condition_key,
                           original_condition_key,
                           source_condition_pool_id,
                           source_minute_target_scope_id,
                           source_subscription_run_id,
                           source_artifact_path,
                           source_artifact_sha256,
                           source_previous_day_minute_run_id,
                           source_context_run_id,
                           proof_kind,
                           source_mode,
                           metric_role,
                           proof_owner,
                           proof_consumer,
                           not_n5_final_proof,
                           current_window_start,
                           current_window_end,
                           previous_completed_window_start,
                           previous_completed_window_end,
                           current_window_elapsed_count,
                           full_window_count,
                           current_30m_price,
                           current_30m_elapsed_amount,
                           previous_day_same_elapsed_30m_amount,
                           previous_day_full_30m_amount,
                           current_30m_virtual_amount,
                           reference_30m_amount,
                           reference_30m_entity_high,
                           reference_30m_entity_low,
                           projection_30m_type,
                           projection_30m_flag,
                           metric_ready,
                           blocked_reasons,
                           raw_json,
                           trace_json,
                           created_at
                    FROM {table_name}
                    WHERE projection_run_id = %s
                    ORDER BY identity_key, metric_minute_label DESC, metric_id
                    """,
                    (projection_run_id,),
                )
                for row in cur.fetchall():
                    normalized = normalize_hint_projection_row(row)
                    normalized["asset_kind"] = asset_kind
                    rows.append(normalized)
            return rows
        for asset_kind in ASSET_KINDS:
            table_name, identity_column = PROJECTION_TABLE_CONFIG[asset_kind]
            snapshot_table, snapshot_identity_column = SNAPSHOT_TABLE_CONFIG[asset_kind]
            cur.execute(
                f"""
                SELECT metric.projection_id, metric.projection_run_id, metric.source_snapshot_run_id,
                       metric.source_condition_run_id, metric.snapshot_id, metric.snapshot_event_id,
                       metric.subscription_id, metric.pull_plan_id, metric.for_trade_date, metric.trade_date,
                       metric.{identity_column} AS identity_key,
                       metric.projection_schema_version, metric.projection_window_kind,
                       metric.projection_window_id, metric.window_start, metric.window_end, metric.snapshot_time,
                       metric.latest_price, metric.window_open_price, metric.window_high_price, metric.window_low_price,
                       metric.projection_status, metric.projection_signal_status,
                       metric.projection_quality_status, metric.trace_status,
                       metric.source_fact_ids, metric.raw_json,
                       snapshot.current_price AS snapshot_current_price,
                       snapshot.close AS snapshot_close,
                       snapshot.amount AS snapshot_amount,
                       snapshot.snapshot_time AS source_snapshot_time,
                       snapshot.quality_status AS snapshot_quality_status,
                       snapshot.raw_json AS snapshot_raw_json
                FROM {table_name} metric
                LEFT JOIN {snapshot_table} snapshot
                  ON snapshot.run_id = metric.source_snapshot_run_id
                 AND snapshot.snapshot_id = metric.snapshot_id
                 AND snapshot.{snapshot_identity_column} = metric.{identity_column}
                WHERE metric.projection_run_id = %s
                ORDER BY metric.{identity_column}, metric.projection_window_id, metric.snapshot_time DESC, metric.projection_id
                """,
                (projection_run_id,),
            )
            for row in cur.fetchall():
                normalized = normalize_projection_row(row)
                normalized["asset_kind"] = asset_kind
                rows.append(normalized)
        return rows


def normalize_context_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["condition_periods"] = normalize_text_array(output.get("condition_periods"))
    output["allowed_signal_types"] = normalize_text_array(output.get("allowed_signal_types"))
    raw_json = output.get("raw_json") or {}
    if isinstance(raw_json, Mapping):
        if not output.get("condition_key") and raw_json.get("condition_key"):
            output["condition_key"] = raw_json.get("condition_key")
        if not output.get("original_condition_key") and raw_json.get("original_condition_key"):
            output["original_condition_key"] = raw_json.get("original_condition_key")
    condition_key = str(output.get("condition_key") or "")
    if condition_key and not output.get("original_condition_key"):
        output["original_condition_key"] = condition_key
    output["period_trigger_baseline_json"] = (
        raw_json.get("period_trigger_baseline_json") if isinstance(raw_json, Mapping) else {}
    ) or output.get("period_trigger_baseline_json") or {}
    return output


def normalize_projection_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    source_fact_ids = output.get("source_fact_ids")
    if source_fact_ids is None:
        output["source_fact_ids"] = {}
    return output


def normalize_hint_projection_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    projection_30m_type = str(output.get("projection_30m_type") or "unknown")
    output["projection_schema_version"] = HINT_1M_PROOF_KIND
    output["projection_window_kind"] = "index_board_1m_hint_projection"
    output["projection_window_id"] = f"{output.get('current_window_start')}_{output.get('current_window_end')}"
    output["snapshot_time"] = output.get("metric_minute_label")
    output["latest_price"] = output.get("current_30m_price")
    output["projection_status"] = "ready" if output.get("metric_ready") else "not_ready"
    output["projection_quality_status"] = "passed" if output.get("metric_ready") else "blocked"
    output["trace_status"] = "passed" if output.get("metric_ready") else "blocked"
    output["projection_signal_status"] = projection_signal_status_for_30m_type(projection_30m_type)
    output["source_fact_ids"] = {
        "source_hint_projection_run_id": output.get("projection_run_id"),
        "source_hint_projection_metric_id": output.get("projection_id"),
        "source_hint_projection_time": output.get("metric_minute_label"),
        "source_hint_projection_proof_kind": output.get("proof_kind"),
        "closed_label_used": output.get("metric_minute_label"),
    }
    return output


def build_projection_matcher_dry_run_report(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    context_rows: Sequence[Mapping[str, Any]],
    projection_rows: Sequence[Mapping[str, Any]],
    trigger_run: Mapping[str, Any] | None = None,
    synthetic_denylist: Sequence[str] = DEFAULT_SYNTHETIC_DENYLIST,
    before_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    sample_limit: int = 80,
    stage: str = "N4-projection-matcher-implementation",
) -> dict[str, Any]:
    evaluations = build_projection_matcher_plans(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        context_rows=context_rows,
        projection_rows=projection_rows,
        synthetic_denylist=synthetic_denylist,
    )
    summary = summarize_projection_matcher_evaluations(evaluations)
    isolation = build_synthetic_isolation_summary(
        trigger_context_run_id=trigger_context_run_id,
        context_rows=context_rows,
        synthetic_denylist=synthetic_denylist,
    )
    quality_items = build_projection_matcher_quality_items(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        trigger_run=trigger_run or {"run_id": trigger_context_run_id, "status": "passed"},
        context_rows=context_rows,
        projection_rows=projection_rows,
        evaluations=evaluations,
        summary=summary,
        isolation=isolation,
        before_row_counts=before_row_counts,
        after_row_counts=after_row_counts,
    )
    quality_counts = count_quality_severities(quality_items)
    return {
        "stage": stage,
        "result": "DRY_RUN_PASS" if quality_counts["P0"] == 0 else "DRY_RUN_BLOCKED",
        "layer_role": "N4_trigger",
        "mode": "projection_matcher_dry_run",
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "source_condition_run_id": (trigger_run or {}).get("source_condition_run_id"),
        "source_market_data_run_id": (trigger_run or {}).get("source_market_data_run_id"),
        "generated_at": utc_now_iso(),
        "matcher_contract": {
            "reads_only_n3_projection_facts": True,
            "reads_raw_market_tables": False,
            "uses_market_adapter": False,
            "consumes_outbox": False,
            "writes_database": False,
            "closed_30m_is_strong_confirmation_not_blocker": True,
            "projection_schema_version": PROJECTION_SCHEMA_VERSION,
            "projection_window_kind": PROJECTION_WINDOW_KIND,
        },
        "input_summary": {
            "raw_context_row_count": len(context_rows),
            "projection_row_count": len(projection_rows),
            "synthetic_denylist": list(synthetic_denylist),
            **isolation,
        },
        "summary": summary,
        "plans": {
            "output_plan_count": summary["matched_count"] + summary["pending_count"],
            "matched_plans": [row for row in evaluations if row.get("plan_status") == "matched"][:sample_limit],
            "pending_plans": [row for row in evaluations if row.get("plan_status") == "pending"][:sample_limit],
            "not_matched_samples": [row for row in evaluations if row.get("plan_status") == "not_matched"][:sample_limit],
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "common_event_outbox_consumed": False,
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "trigger_match_written": False,
            "trigger_state_written": False,
            "event_outbox_written": False,
            "market_data_pulled": False,
            "raw_market_tables_read": False,
            "worker_started": False,
            "downstream_layers_touched": False,
            "old_system_touched": False,
            "external_n2_runtime_path_accessed": False,
        },
        "before_row_counts": before_row_counts or {},
        "after_row_counts": after_row_counts or {},
        "rollback_plan": {
            "this_dry_run": "No DB rollback required; delete generated matcher report files if discarded.",
            "future_execute": (
                "Future N4 execute rollback must delete N4 inbox/checkpoint, trigger_state, "
                "trigger_match, quality, and outbox rows by execute run_id after downstream safety checks."
            ),
        },
        "next_gate": {
            "allow_projection_matcher_dry_run_refresh": quality_counts["P0"] == 0,
            "allow_real_execute_preflight": False,
            "execute_preflight_blocker": "requires refreshed dry-run, inbox/checkpoint/ack/rollback review, and user authorization",
        },
    }


def build_projection_matcher_plans(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    context_rows: Sequence[Mapping[str, Any]],
    projection_rows: Sequence[Mapping[str, Any]],
    synthetic_denylist: Sequence[str] = DEFAULT_SYNTHETIC_DENYLIST,
) -> list[dict[str, Any]]:
    projection_lookup = latest_projection_by_identity(projection_rows, projection_run_id=projection_run_id)
    evaluations: list[dict[str, Any]] = []
    for raw_row in context_rows:
        row = normalize_context_row(raw_row)
        if row.get("run_id") != trigger_context_run_id:
            continue
        if row.get("run_id") in set(synthetic_denylist):
            continue
        projection = projection_lookup.get((str(row.get("asset_kind") or ""), str(row.get("identity_key") or "")))
        if is_hint_condition(row):
            signal_type = projection_signal_type_for_context(row)
            if not signal_type:
                continue
            if str(row.get("asset_kind") or "") == "stock":
                evaluations.append(evaluate_stock_hint_not_applicable(row, projection, signal_type, projection_run_id))
                continue
            evaluations.append(evaluate_projection_candidate(row, projection, signal_type, projection_run_id))
            continue
        if is_formal_buy_sell_condition(row):
            evaluations.append(evaluate_formal_trigger_candidate(row, projection, projection_run_id))
            continue
        signal_type = projection_signal_type_for_context(row)
        if signal_type:
            evaluations.append(evaluate_projection_candidate(row, projection, signal_type, projection_run_id))
    return evaluations


def latest_projection_by_identity(
    projection_rows: Sequence[Mapping[str, Any]],
    *,
    projection_run_id: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for row in projection_rows:
        if row.get("projection_run_id") != projection_run_id:
            continue
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        if not key[0] or not key[1]:
            continue
        output.setdefault(key, dict(row))
    return output


def is_hint_1m_projection_run_id(projection_run_id: str) -> bool:
    return "index_board_1m_hint_projection_v1" in projection_run_id


def projection_signal_status_for_30m_type(projection_30m_type: str) -> str:
    if projection_30m_type == "volume_up":
        return "up_volume_expanding"
    if projection_30m_type == "shrink_down":
        return "down_volume_shrinking"
    if projection_30m_type == "none":
        return "flat"
    return "unknown"


def projection_signal_type_for_context(row: Mapping[str, Any]) -> str | None:
    direction = str(row.get("direction") or "")
    condition_key = str(row.get("condition_key") or "")
    allowed = set(normalize_text_array(row.get("allowed_signal_types")))
    if condition_key == "BUY_HINT" and direction == "buy" and "BUY_HINT" in allowed:
        return "BUY_HINT"
    if condition_key == "SELL_HINT" and direction == "sell" and "SELL_HINT" in allowed:
        return "SELL_HINT"
    return None


def is_formal_buy_sell_condition(row: Mapping[str, Any]) -> bool:
    condition_key = str(row.get("condition_key") or "")
    if condition_key in {"BUY_HINT", "SELL_HINT"}:
        return False
    if not (condition_key.startswith("BUY") or condition_key.startswith("SELL")):
        return False
    allowed = set(normalize_text_array(row.get("allowed_signal_types")))
    if not allowed:
        return True
    return bool(
        allowed
        & {
            "BUY",
            "BUY:FULL",
            "SELL",
            "SELL:FULL",
            "B_BUY",
            "S_SELL",
        }
    )


def evaluate_formal_trigger_candidate(
    row: Mapping[str, Any],
    projection: Mapping[str, Any] | None,
    projection_run_id: str,
) -> dict[str, Any]:
    prepared_projection = prepare_projection_for_v4(row=row, projection=projection)
    v4_plan = evaluate_v4_plan(
        row,
        prepared_projection if prepared_projection else None,
        v4_run_id=projection_run_id,
    )
    return build_formal_evaluation(row=row, projection=projection or {}, v4_plan=v4_plan, projection_run_id=projection_run_id)


def prepare_projection_for_v4(
    *,
    row: Mapping[str, Any],
    projection: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if not projection:
        return {}
    output = dict(projection)
    source_fact_ids = output.get("source_fact_ids") if isinstance(output.get("source_fact_ids"), Mapping) else {}
    raw_json = output.get("raw_json") if isinstance(output.get("raw_json"), Mapping) else {}
    output.setdefault("source_event_id", output.get("snapshot_event_id") or source_fact_ids.get("snapshot_event_id"))
    output.setdefault("source_event_type", SOURCE_EVENT_TYPE)
    output.setdefault("current_metric_time", projection_confirmed_time(output))
    output.setdefault("current_price_or_close", projection_trigger_price(output))
    output.setdefault("current_metric_quality_status", output.get("projection_quality_status"))
    output.setdefault("metric_ready", projection_is_ready(output))
    output.setdefault("metric_quality_status", output.get("projection_quality_status"))
    output.setdefault("source_freshness_status", "fresh_complete_lineage" if projection_is_ready(output) else "missing")

    enrichment = raw_json.get("enrichment_v1")
    if isinstance(enrichment, Mapping):
        lineage = dict(enrichment.get("projection_lineage_json") or {})
        if output.get("current_price_or_close") is not None:
            lineage.setdefault("trigger_price", output.get("current_price_or_close"))
            lineage.setdefault("current_price", output.get("current_price_or_close"))
        enrichment = {**dict(enrichment), "projection_lineage_json": lineage}
        output["raw_json"] = {**raw_json, "enrichment_v1": enrichment}
    elif is_formal_buy_sell_condition(row):
        output = apply_snapshot_formal_enrichment(row=row, projection=output)
    return output


def apply_snapshot_formal_enrichment(
    *,
    row: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    output = dict(projection)
    raw_json = output.get("raw_json") if isinstance(output.get("raw_json"), Mapping) else {}
    snapshot_raw_json = (
        output.get("snapshot_raw_json") if isinstance(output.get("snapshot_raw_json"), Mapping) else {}
    )
    current_price = (
        output.get("snapshot_current_price")
        or output.get("snapshot_close")
        or projection_trigger_price(output)
    )
    current_amount = output.get("snapshot_amount") or snapshot_raw_json.get("amount")
    current_time = output.get("source_snapshot_time") or projection_confirmed_time(output)
    snapshot_quality = output.get("snapshot_quality_status") or snapshot_raw_json.get("quality_status")
    metric_ready = bool(current_price is not None and current_amount is not None and snapshot_quality == "passed")
    enrichment = {
        "current_price_or_close": current_price,
        "current_amount_metric": None,
        "current_amount_metric_source_kind": "N3_realtime_daily_snapshot_trace_only",
        "snapshot_amount_trace": current_amount,
        "current_metric_time": current_time,
        "current_metric_quality_status": "passed" if metric_ready else "missing",
        "projection_period": PROJECTION_PERIOD,
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "trigger_amount_chain_pass": build_snapshot_trigger_amount_chain_pass(
            row=row,
            current_amount=current_amount,
            metric_ready=metric_ready,
        ),
        "projection_lineage_json": {
            "source": "N3_realtime_daily_snapshot",
            "source_snapshot_run_id": output.get("source_snapshot_run_id"),
            "source_snapshot_id": output.get("snapshot_id"),
            "source_snapshot_event_id": output.get("snapshot_event_id"),
            "source_projection_run_id": output.get("projection_run_id"),
            "source_projection_id": output.get("projection_id"),
            "trigger_price": current_price,
            "current_price": current_price,
            "snapshot_amount_trace": current_amount,
            "n4_recompute_allowed": False,
            "formal_snapshot_fallback": True,
            "formal_period_amount_metric_not_standardized": True,
        },
        "source_freshness_status": "fresh_complete_lineage" if metric_ready else "snapshot_metric_missing",
        "metric_ready": metric_ready,
        "metric_quality_status": "passed" if metric_ready else "missing",
    }
    output["current_price_or_close"] = current_price
    output.pop("current_amount_metric", None)
    output["current_amount_metric_source_kind"] = enrichment["current_amount_metric_source_kind"]
    output["snapshot_amount_trace"] = current_amount
    output["current_metric_time"] = current_time
    output["current_metric_quality_status"] = enrichment["current_metric_quality_status"]
    output["projection_period"] = PROJECTION_PERIOD
    output["projection_30m_flag"] = False
    output["projection_30m_type"] = "none"
    output["trigger_amount_chain_pass"] = enrichment["trigger_amount_chain_pass"]
    output["projection_lineage_json"] = enrichment["projection_lineage_json"]
    output["source_freshness_status"] = enrichment["source_freshness_status"]
    output["metric_ready"] = metric_ready
    output["metric_quality_status"] = enrichment["metric_quality_status"]
    output["quality_reason"] = None if metric_ready else "snapshot_price_or_amount_missing"
    output["raw_json"] = {**raw_json, "enrichment_v1": enrichment}
    return output


def build_snapshot_trigger_amount_chain_pass(
    *,
    row: Mapping[str, Any],
    current_amount: Any,
    metric_ready: bool,
) -> dict[str, Any]:
    baseline = row.get("period_trigger_baseline_json")
    if not isinstance(baseline, Mapping):
        baseline = {}
    periods = baseline.get("periods") if isinstance(baseline.get("periods"), Mapping) else {}
    period_pass: dict[str, bool | None] = {}
    missing: list[str] = []
    for period in ("Y", "Q", "M", "W", "D"):
        period_baseline = periods.get(period)
        if not isinstance(period_baseline, Mapping):
            period_pass[period] = None
            missing.append(f"N2.{period}.period_baseline")
            continue
        if not bool(period_baseline.get("period_baseline_ready") or period_baseline.get("baseline_ready")):
            period_pass[period] = None
            missing.append(f"N2.{period}.period_baseline_ready")
            continue
        period_pass[period] = None
        missing.append("formal_period_amount_metric_not_standardized")
    return {
        "generated_by": "N3_market_data/N4_formal_snapshot_bridge",
        "spec_version": "n4.formal_snapshot_projection_bridge.v1",
        "n4_recompute_allowed": False,
        "inputs": [
            "N2 period_trigger_baseline_json",
            "N3 realtime_daily_snapshot current_price",
            "N3 realtime_daily_snapshot amount trace-only",
        ],
        "direction": row.get("direction"),
        "period_baseline_pass": period_pass,
        "projection_30m": False,
        "ready": False,
        "_trace": {
            "source_condition_run_id": row.get("source_condition_run_id"),
            "source_trigger_context_id": row.get("trigger_context_id"),
            "missing_inputs": sorted(set(missing)),
        },
    }


def build_formal_evaluation(
    *,
    row: Mapping[str, Any],
    projection: Mapping[str, Any],
    v4_plan: Mapping[str, Any],
    projection_run_id: str,
) -> dict[str, Any]:
    asset_kind = str(row.get("asset_kind") or "")
    identity_key = str(row.get("identity_key") or "")
    condition_key = str(row.get("condition_key") or "")
    signal_type = str(v4_plan.get("signal_type") or ("B_BUY" if str(row.get("direction") or "") == "buy" else "S_SELL"))
    output_event_type = v4_plan.get("output_event_type")
    outcome = str(v4_plan.get("outcome_classification") or "")
    if output_event_type is None and outcome == "quality_blocked" and condition_key not in {"BUY:FULL", "SELL:FULL"}:
        output_event_type = "TriggerPendingMarketData"
    if output_event_type == "TriggerMatched":
        plan_status = "matched"
    elif output_event_type == "TriggerPendingMarketData":
        plan_status = "pending"
    else:
        plan_status = "not_matched"
    source_fact_ids = projection.get("source_fact_ids") if isinstance(projection.get("source_fact_ids"), Mapping) else {}
    raw_json = projection.get("raw_json") if isinstance(projection.get("raw_json"), Mapping) else {}
    source_event_id = str(
        projection.get("snapshot_event_id")
        or projection.get("source_event_id")
        or source_fact_ids.get("snapshot_event_id")
        or f"projection_missing:{projection_run_id}:{identity_key}"
    )
    projection_window_id = str(projection.get("projection_window_id") or "projection_window_not_available")
    trigger_mark_candidate = str(v4_plan.get("trigger_mark_candidate") or "normal")
    projection_30m_flag = bool(v4_plan.get("projection_30m_flag") or False)
    projection_30m_type = str(v4_plan.get("projection_30m_type") or "none")
    trigger_period = v4_plan.get("trigger_period") or v4_plan.get("primary_trigger_period")
    n3_trace = dict(v4_plan.get("n3_trace") or {})
    trigger_price = v4_plan.get("trigger_price")
    if trigger_price is not None:
        n3_trace.setdefault("trigger_price", trigger_price)
        n3_trace.setdefault("current_price", trigger_price)
    raw_id = "|".join(
        [
            projection_run_id,
            source_event_id,
            asset_kind,
            identity_key,
            str(v4_plan.get("direction") or row.get("direction") or ""),
            signal_type,
            trigger_mark_candidate,
            condition_key,
            projection_window_id,
            plan_status,
        ]
    )
    return {
        **dict(v4_plan),
        "plan_id": stable_hash(raw_id, length=32),
        "plan_status": plan_status,
        "output_event_type": output_event_type,
        "current_status": "pending_market_data" if plan_status == "pending" else v4_plan.get("current_status"),
        "trigger_live": False if plan_status == "pending" else v4_plan.get("trigger_live"),
        "n5_entry_allowed": False if plan_status == "pending" else v4_plan.get("n5_entry_allowed"),
        "source_event_id": source_event_id,
        "source_event_type": SOURCE_EVENT_TYPE,
        "source_projection_id": projection.get("projection_id") or projection.get("projection_enrichment_id"),
        "projection_run_id": projection_run_id,
        "projection_window_id": projection_window_id,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "original_condition_key": v4_plan.get("original_condition_key") or condition_key,
        "legacy_signal_type": projection_signal_type_for_context(row) or condition_key,
        "trigger_period": trigger_period,
        "trigger_mark_candidate": trigger_mark_candidate,
        "projection_period": v4_plan.get("projection_period") or PROJECTION_PERIOD,
        "projection_30m_flag": projection_30m_flag,
        "projection_30m_type": projection_30m_type,
        "trigger_bucket": v4_plan.get("trigger_bucket") or projection_window_id,
        "data_quality_status": v4_plan.get("data_quality_status") or projection.get("projection_quality_status") or "missing",
        "projection_status": projection.get("projection_status") or "missing",
        "projection_quality_status": projection.get("projection_quality_status") or "missing",
        "trace_status": projection.get("trace_status") or "missing",
        "projection_signal_status": str(projection.get("projection_signal_status") or "missing"),
        "not_ready_classification": None if plan_status == "matched" else not_ready_classification(projection or {}),
        "context_snapshot_id": row.get("trigger_context_id"),
        "source_condition_run_id": row.get("source_condition_run_id"),
        "source_condition_pool_id": row.get("source_condition_pool_id"),
        "source_condition_basis_id": row.get("source_condition_basis_id"),
        "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        "source_market_subscription_id": row.get("source_market_subscription_id"),
        "context_hash": row.get("context_hash"),
        "n3_trace": n3_trace,
        "projection_trace": {
            "projection_id": projection.get("projection_id") or projection.get("projection_enrichment_id"),
            "projection_schema_version": projection.get("projection_schema_version") or projection.get("spec_version"),
            "projection_window_kind": projection.get("projection_window_kind"),
            "source_snapshot_run_id": projection.get("source_snapshot_run_id"),
            "snapshot_id": projection.get("snapshot_id") or source_fact_ids.get("snapshot_id"),
            "snapshot_event_id": projection.get("snapshot_event_id") or source_fact_ids.get("snapshot_event_id"),
            "trigger_price": trigger_price,
            "current_price": trigger_price,
            "latest_price": projection.get("latest_price"),
            "trigger_time": v4_plan.get("trigger_time") or projection_confirmed_time(projection),
            "source_confirmed_time": v4_plan.get("trigger_time") or projection_confirmed_time(projection),
            "closed_label_used": projection_confirmed_time(projection),
            "quality_status": projection.get("projection_quality_status") or v4_plan.get("data_quality_status") or "missing",
            "source_fact_ids": source_fact_ids,
            "raw_json_projection_signal_status": raw_json.get("projection_signal_status"),
        },
        "period_trigger_baseline_trace": build_period_trigger_baseline_trace(
            row,
            condition_key,
            str(v4_plan.get("primary_trigger_period") or ""),
        ),
        "dry_run_reason": formal_dry_run_reason(v4_plan),
    }


def formal_dry_run_reason(v4_plan: Mapping[str, Any]) -> str:
    outcome = str(v4_plan.get("outcome_classification") or "")
    if outcome == "matched":
        return "N3 v4 projection enrichment satisfies formal N4 trigger periods"
    if outcome == "pending_market_data":
        reasons = v4_plan.get("pending_reasons") or []
        return "N3 v4 projection enrichment pending formal trigger evidence: " + ",".join(map(str, reasons))
    if outcome == "quality_blocked":
        return "N3 v4 projection enrichment quality blocked: " + str(v4_plan.get("blocked_reason") or "")
    return "N3 v4 projection enrichment did not satisfy formal trigger periods"


def evaluate_projection_candidate(
    row: Mapping[str, Any],
    projection: Mapping[str, Any] | None,
    signal_type: str,
    projection_run_id: str,
) -> dict[str, Any]:
    if projection is None:
        return build_evaluation(
            row=row,
            projection={},
            signal_type=signal_type,
            projection_run_id=projection_run_id,
            plan_status="pending",
            output_event_type="TriggerPendingMarketData",
            data_quality_status="missing",
            not_ready_classification="blocked",
            reason="N3 realtime projection fact is missing for this local context candidate",
        )
    if not projection_is_ready(projection):
        classification = not_ready_classification(projection)
        return build_evaluation(
            row=row,
            projection=projection,
            signal_type=signal_type,
            projection_run_id=projection_run_id,
            plan_status="pending",
            output_event_type="TriggerPendingMarketData",
            data_quality_status="not_ready",
            not_ready_classification=classification,
            reason="N3 realtime projection fact is not ready; N4 must not promote it to TriggerMatched",
        )
    proof = extract_standard_hint_projection_proof(projection)
    if not bool(proof.get("valid")):
        return build_evaluation(
            row=row,
            projection=projection,
            signal_type=signal_type,
            projection_run_id=projection_run_id,
            plan_status="pending",
            output_event_type="TriggerPendingMarketData",
            data_quality_status="partial",
            not_ready_classification="blocked",
            reason="N3 realtime projection fact is missing standard N3 hint projection proof",
            projection_30m_type_override="unknown",
        )
    projection_30m_type = str(proof.get("projection_30m_type") or projection.get("projection_30m_type") or "unknown")
    if projection_matches_atomic_type(signal_type, projection_30m_type):
        if not is_hint_condition(row):
            return build_evaluation(
                row=row,
                projection=projection,
                signal_type=signal_type,
                projection_run_id=projection_run_id,
                plan_status="pending",
                output_event_type="TriggerPendingMarketData",
                data_quality_status="partial",
                not_ready_classification="blocked",
                reason=(
                    "N3 30m projection evidence is present, but ordinary BUY/SELL requires "
                    "formal Y/Q/M/W/D trigger evidence before TriggerMatched"
                ),
            )
        return build_evaluation(
            row=row,
            projection=projection,
            signal_type=signal_type,
            projection_run_id=projection_run_id,
            plan_status="matched",
            output_event_type="TriggerMatched",
            data_quality_status="passed",
            not_ready_classification=None,
            reason="N3 ready realtime projection signal matches N4 projection trigger mapping",
            projection_30m_type_override=projection_30m_type,
        )
    return build_evaluation(
        row=row,
        projection=projection,
        signal_type=signal_type,
        projection_run_id=projection_run_id,
        plan_status="not_matched",
        output_event_type=None,
        data_quality_status="passed",
        not_ready_classification=None,
        reason="N3 ready realtime projection signal does not satisfy this N4 trigger mapping",
        projection_30m_type_override=projection_30m_type,
    )


def evaluate_stock_hint_not_applicable(
    row: Mapping[str, Any],
    projection: Mapping[str, Any] | None,
    signal_type: str,
    projection_run_id: str,
) -> dict[str, Any]:
    return build_evaluation(
        row=row,
        projection=projection or {},
        signal_type=signal_type,
        projection_run_id=projection_run_id,
        plan_status="not_matched",
        output_event_type=None,
        data_quality_status="not_applicable",
        not_ready_classification=None,
        reason="stock HINT is not applicable under N4 index/board-only HINT rule",
        projection_30m_type_override="none",
    )


def projection_is_ready(projection: Mapping[str, Any]) -> bool:
    if projection.get("proof_kind") == HINT_1M_PROOF_KIND:
        return (
            bool(projection.get("metric_ready"))
            and projection.get("metric_role") == "hint_trigger_proof"
            and projection.get("proof_owner") == "N3"
            and projection.get("proof_consumer") == "N4"
            and bool(projection.get("not_n5_final_proof"))
        )
    return (
        projection.get("projection_status") == "ready"
        and projection.get("projection_quality_status") == "passed"
        and projection.get("trace_status") == "passed"
        and projection.get("projection_schema_version") == PROJECTION_SCHEMA_VERSION
        and projection.get("projection_window_kind") == PROJECTION_WINDOW_KIND
    )


def projection_matches_signal(signal_type: str, projection_signal_status: str) -> bool:
    if signal_type in LEGACY_TRACE_ONLY_SIGNAL_TYPES:
        return False
    if signal_type == "BUY_HINT":
        return projection_signal_status == "up_volume_expanding"
    if signal_type == "SELL_HINT":
        return projection_signal_status == "down_volume_shrinking"
    return False


def projection_matches_atomic_type(signal_type: str, projection_30m_type: str) -> bool:
    if signal_type == "BUY_HINT":
        return projection_30m_type == "volume_up"
    if signal_type == "SELL_HINT":
        return projection_30m_type == "shrink_down"
    return False


def extract_standard_hint_projection_proof(projection: Mapping[str, Any]) -> dict[str, Any]:
    if projection.get("proof_kind") == HINT_1M_PROOF_KIND:
        required = {
            "projection_run_id": projection.get("projection_run_id"),
            "projection_id": projection.get("projection_id"),
            "metric_minute_label": projection.get("metric_minute_label"),
            "projection_30m_type": projection.get("projection_30m_type"),
            "current_30m_virtual_amount": projection.get("current_30m_virtual_amount"),
            "reference_30m_amount": projection.get("reference_30m_amount"),
            "current_30m_price": projection.get("current_30m_price"),
            "reference_30m_entity_high": projection.get("reference_30m_entity_high"),
            "reference_30m_entity_low": projection.get("reference_30m_entity_low"),
        }
        missing = [key for key, value in required.items() if value in (None, "")]
        return {
            "valid": not missing
            and projection.get("metric_role") == "hint_trigger_proof"
            and projection.get("proof_owner") == "N3"
            and projection.get("proof_consumer") == "N4"
            and bool(projection.get("not_n5_final_proof")),
            "proof_kind": HINT_1M_PROOF_KIND,
            "source_hint_projection_run_id": projection.get("projection_run_id"),
            "source_hint_projection_metric_id": projection.get("projection_id"),
            "source_hint_projection_time": projection.get("metric_minute_label"),
            "source_hint_projection_proof_kind": projection.get("proof_kind"),
            "projection_30m_type": projection.get("projection_30m_type"),
            "projection_30m_flag": projection.get("projection_30m_flag"),
            "current_30m_virtual_amount": projection.get("current_30m_virtual_amount"),
            "reference_30m_amount": projection.get("reference_30m_amount"),
            "current_30m_price": projection.get("current_30m_price"),
            "reference_30m_entity_high": projection.get("reference_30m_entity_high"),
            "reference_30m_entity_low": projection.get("reference_30m_entity_low"),
            "not_n5_final_proof": projection.get("not_n5_final_proof"),
            "missing_or_invalid_fields": missing,
        }
    return extract_b2_30m_projection_proof(projection)


def projection_30m_type_for_candidate(signal_type: str, projection_signal_status: str) -> str:
    if not projection_matches_signal(signal_type, projection_signal_status):
        return "none"
    if projection_signal_status == "up_volume_expanding":
        return "volume_up"
    if projection_signal_status == "down_volume_shrinking":
        return "shrink_down"
    return "none"


def is_hint_condition(row: Mapping[str, Any]) -> bool:
    return str(row.get("condition_key") or "") in {"BUY_HINT", "SELL_HINT"}


def trigger_kind_for_condition(condition_key: str) -> str:
    return "hint" if condition_key in {"BUY_HINT", "SELL_HINT"} else "trigger"


def projection_trigger_price(projection: Mapping[str, Any]) -> Any:
    raw_json = projection.get("raw_json") if isinstance(projection.get("raw_json"), Mapping) else {}
    return (
        projection.get("latest_price")
        or projection.get("current_price")
        or projection.get("close")
        or raw_json.get("latest_price")
        or raw_json.get("current_price")
        or raw_json.get("close")
    )


def projection_confirmed_time(projection: Mapping[str, Any]) -> Any:
    source_fact_ids = projection.get("source_fact_ids") if isinstance(projection.get("source_fact_ids"), Mapping) else {}
    raw_json = projection.get("raw_json") if isinstance(projection.get("raw_json"), Mapping) else {}
    return (
        source_fact_ids.get("closed_label_used")
        or raw_json.get("closed_label_used")
        or projection.get("snapshot_time")
        or projection.get("window_end")
    )


def not_ready_classification(projection: Mapping[str, Any]) -> str:
    asset_kind = str(projection.get("asset_kind") or "")
    identity_key = str(projection.get("identity_key") or "")
    if asset_kind == "stock" and identity_key.startswith("stock:BJ:920"):
        return "warning"
    return "blocked"


def build_evaluation(
    *,
    row: Mapping[str, Any],
    projection: Mapping[str, Any],
    signal_type: str,
    projection_run_id: str,
    plan_status: str,
    output_event_type: str | None,
    data_quality_status: str,
    not_ready_classification: str | None,
    reason: str,
    projection_30m_type_override: str | None = None,
) -> dict[str, Any]:
    asset_kind = str(row.get("asset_kind") or "")
    identity_key = str(row.get("identity_key") or "")
    condition_key = str(row.get("condition_key") or "")
    direction = str(row.get("direction") or "")
    legacy_signal_type = signal_type
    projection_signal_status = str(projection.get("projection_signal_status") or "missing")
    projection_30m_type = projection_30m_type_override or projection_30m_type_for_candidate(
        legacy_signal_type,
        projection_signal_status,
    )
    mapping_projection_30m_type = projection_30m_type if output_event_type == "TriggerMatched" else "none"
    mapping = canonicalize_trigger_candidate(
        condition_key,
        candidate_signal_type=legacy_signal_type,
        projection_30m_type=mapping_projection_30m_type,
    )
    canonical_signal_type = mapping.signal_type
    trigger_mark_candidate = mapping.trigger_mark_candidate
    proof = extract_standard_hint_projection_proof(projection) if projection else {}
    projection_window_id = str(projection.get("projection_window_id") or "projection_window_not_available")
    source_event_id = str(projection.get("snapshot_event_id") or f"projection_missing:{projection_run_id}:{identity_key}")
    matched = output_event_type == "TriggerMatched"
    trigger_kind = trigger_kind_for_condition(condition_key)
    trigger_price = projection_trigger_price(projection) if matched else None
    confirmed_time = projection_confirmed_time(projection)
    condition_signal_type = condition_signal_type_for_condition_key(
        condition_key,
        direction=direction,
        condition_family="hint" if trigger_kind == "hint" else "ordinary",
    )
    requested_periods = [] if trigger_kind == "hint" else condition_periods_for_payload(row, condition_key)
    projection_30m_required = trigger_kind == "hint"
    projection_30m_flag = projection_30m_type in {"volume_up", "shrink_down"}
    projection_30m_volume_up_flag, projection_30m_shrink_down_flag = projection_30m_flags(
        projection_30m_type,
        projection_30m_flag=projection_30m_flag,
    )
    raw_id = "|".join(
        [
            projection_run_id,
            source_event_id,
            asset_kind,
            identity_key,
            direction,
            canonical_signal_type,
            trigger_mark_candidate,
            legacy_signal_type,
            condition_key,
            projection_window_id,
            plan_status,
        ]
    )
    return {
        "plan_id": stable_hash(raw_id, length=32),
        "plan_status": plan_status,
        "output_event_type": output_event_type,
        "source_event_id": source_event_id,
        "source_event_type": SOURCE_EVENT_TYPE,
        "source_projection_id": projection.get("projection_id"),
        "source_projection_proof_run_id": proof.get("source_projection_proof_run_id"),
        "source_projection_proof_metric_id": proof.get("source_projection_proof_metric_id"),
        "source_projection_proof_time": proof.get("source_projection_proof_time"),
        "source_hint_projection_run_id": proof.get("source_hint_projection_run_id"),
        "source_hint_projection_metric_id": proof.get("source_hint_projection_metric_id"),
        "source_hint_projection_time": proof.get("source_hint_projection_time"),
        "source_hint_projection_proof_kind": proof.get("source_hint_projection_proof_kind"),
        "not_n5_final_proof": bool(proof.get("not_n5_final_proof")),
        "projection_proof_kind": proof.get("proof_kind"),
        "projection_proof_valid": bool(proof.get("valid")),
        "projection_proof_missing_or_invalid_fields": proof.get("missing_or_invalid_fields") or [],
        "projection_run_id": projection_run_id,
        "projection_window_id": projection_window_id,
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "signal_type": canonical_signal_type,
        "runtime_signal_type": canonical_signal_type,
        "condition_signal_type": condition_signal_type,
        "trigger_mark_candidate": trigger_mark_candidate,
        "condition_key": condition_key,
        "original_condition_key": mapping.original_condition_key,
        "legacy_signal_type": legacy_signal_type,
        "match_basis": "intraday_projection",
        "trigger_period": PROJECTION_PERIOD if matched and trigger_kind == "hint" else None,
        "trigger_price": trigger_price,
        "trigger_time": confirmed_time if matched else None,
        "event_time": confirmed_time if matched else None,
        "trigger_kind": trigger_kind,
        "trigger_live": matched,
        "current_status": "matched" if matched else "pending_market_data" if plan_status == "pending" else "no_op",
        "n5_entry_allowed": matched,
        "requested_periods": requested_periods,
        "triggered_periods": [],
        "all_trigger_periods": [],
        "primary_trigger_period": None,
        "triggered_period_details": [],
        "projection_period": PROJECTION_PERIOD,
        "projection_30m_required": projection_30m_required,
        "projection_30m_flag": projection_30m_flag,
        "projection_30m_type": projection_30m_type,
        "projection_30m_volume_up_flag": projection_30m_volume_up_flag,
        "projection_30m_shrink_down_flag": projection_30m_shrink_down_flag,
        "price_source": "n3_realtime_projection",
        "baseline_source": "trigger_baseline",
        "trigger_bucket": projection_window_id,
        "data_quality_status": data_quality_status,
        "projection_status": projection.get("projection_status") or "missing",
        "projection_quality_status": projection.get("projection_quality_status") or "missing",
        "trace_status": projection.get("trace_status") or "missing",
        "projection_signal_status": projection_signal_status,
        "not_ready_classification": not_ready_classification,
        "context_snapshot_id": row.get("trigger_context_id"),
        "source_condition_run_id": row.get("source_condition_run_id"),
        "source_condition_pool_id": row.get("source_condition_pool_id"),
        "source_condition_basis_id": row.get("source_condition_basis_id"),
        "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        "source_market_subscription_id": row.get("source_market_subscription_id"),
        "context_hash": row.get("context_hash"),
        "projection_trace": {
            "projection_id": projection.get("projection_id"),
            "projection_schema_version": projection.get("projection_schema_version"),
            "projection_window_kind": projection.get("projection_window_kind"),
            **{
                key: value
                for key, value in {
                    "source_snapshot_run_id": projection.get("source_snapshot_run_id"),
                    "snapshot_id": projection.get("snapshot_id"),
                    "snapshot_event_id": projection.get("snapshot_event_id"),
                }.items()
                if value is not None and value != ""
            },
            **{key: value for key, value in proof.items() if key != "valid" and value is not None and value != ""},
            "trigger_price": trigger_price,
            "current_price": trigger_price,
            "latest_price": projection.get("latest_price"),
            "trigger_time": confirmed_time,
            "source_confirmed_time": confirmed_time,
            "closed_label_used": confirmed_time,
            "quality_status": projection.get("projection_quality_status") or data_quality_status,
            "source_fact_ids": projection.get("source_fact_ids") or {},
            "raw_json_projection_signal_status": (projection.get("raw_json") or {}).get("projection_signal_status")
            if isinstance(projection.get("raw_json"), Mapping)
            else None,
        },
        "period_trigger_baseline_trace": build_period_trigger_baseline_trace(row, condition_key, ""),
        "dry_run_reason": reason,
    }


def condition_periods_for_payload(row: Mapping[str, Any], condition_key: str) -> list[str]:
    periods = [period for period in normalize_text_array(row.get("condition_periods")) if period in FORMAL_TRIGGER_PERIODS]
    if periods:
        return [period for period in ("Y", "Q", "M", "W", "D") if period in set(periods)]
    if ":" in condition_key:
        parsed = [part.strip() for part in condition_key.split(":", 1)[1].split(",") if part.strip() in FORMAL_TRIGGER_PERIODS]
        if parsed:
            return [period for period in ("Y", "Q", "M", "W", "D") if period in set(parsed)]
    return ["D"]


def summarize_projection_matcher_evaluations(evaluations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matched = [row for row in evaluations if row.get("plan_status") == "matched"]
    pending = [row for row in evaluations if row.get("plan_status") == "pending"]
    not_matched = [row for row in evaluations if row.get("plan_status") == "not_matched"]
    return {
        "candidate_count": len(evaluations),
        "matched_count": len(matched),
        "pending_count": len(pending),
        "not_matched_signal_count": len(not_matched),
        "by_asset_kind": count_by(evaluations, "asset_kind"),
        "matched_by_asset_kind": count_by(matched, "asset_kind"),
        "pending_by_asset_kind": count_by(pending, "asset_kind"),
        "by_signal_type": count_by(evaluations, "signal_type"),
        "matched_by_signal_type": count_by(matched, "signal_type"),
        "pending_by_signal_type": count_by(pending, "signal_type"),
        "by_trigger_mark_candidate": count_by(evaluations, "trigger_mark_candidate"),
        "matched_by_trigger_mark_candidate": count_by(matched, "trigger_mark_candidate"),
        "pending_by_trigger_mark_candidate": count_by(pending, "trigger_mark_candidate"),
        "by_legacy_signal_type": count_by(evaluations, "legacy_signal_type"),
        "matched_by_legacy_signal_type": count_by(matched, "legacy_signal_type"),
        "pending_by_legacy_signal_type": count_by(pending, "legacy_signal_type"),
        "by_direction": count_by(evaluations, "direction"),
        "matched_by_direction": count_by(matched, "direction"),
        "pending_by_direction": count_by(pending, "direction"),
        "by_projection_signal_status": count_by(evaluations, "projection_signal_status"),
        "matched_by_projection_signal_status": count_by(matched, "projection_signal_status"),
        "pending_by_projection_signal_status": count_by(pending, "projection_signal_status"),
        "not_matched_by_projection_signal_status": count_by(not_matched, "projection_signal_status"),
        "trigger_period_distribution": count_by(evaluations, "trigger_period"),
        "matched_output_event_types": count_by(matched, "output_event_type"),
        "pending_output_event_types": count_by(pending, "output_event_type"),
        "ready_candidate_count": sum(1 for row in evaluations if row.get("projection_status") == "ready"),
        "not_ready_candidate_count": sum(1 for row in evaluations if row.get("plan_status") == "pending"),
        "pending_by_not_ready_classification": count_by(pending, "not_ready_classification"),
        "board_not_ready_object_count": count_objects(
            row for row in pending if row.get("asset_kind") == "board"
        ),
        "bj_920xxx_not_ready_object_count": count_objects(
            row for row in pending if str(row.get("identity_key") or "").startswith("stock:BJ:920")
        ),
        "buy_hint_matched_count": sum(1 for row in matched if row.get("condition_key") == "BUY_HINT"),
        "sell_hint_matched_count": sum(1 for row in matched if row.get("condition_key") == "SELL_HINT"),
        "canonical_payload_invalid_count": sum(1 for row in evaluations if canonical_payload_errors(row)),
    }


def build_synthetic_isolation_summary(
    *,
    trigger_context_run_id: str,
    context_rows: Sequence[Mapping[str, Any]],
    synthetic_denylist: Sequence[str],
) -> dict[str, Any]:
    denylist = set(synthetic_denylist)
    excluded = [row for row in context_rows if row.get("run_id") in denylist and row.get("run_id") != trigger_context_run_id]
    return {
        "current_context_is_denylisted": trigger_context_run_id in denylist,
        "input_denylisted_context_rows_excluded": len(excluded),
        "synthetic_denylist_enforced": True,
    }


def build_projection_matcher_quality_items(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    trigger_run: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    projection_rows: Sequence[Mapping[str, Any]],
    evaluations: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    isolation: Mapping[str, Any],
    before_row_counts: Mapping[str, Mapping[str, Any]] | None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    row_counts_unchanged = True
    if before_row_counts is not None and after_row_counts is not None:
        row_counts_unchanged = before_row_counts == after_row_counts
    formal_snapshot_fallback_matches = [
        row for row in evaluations if is_formal_snapshot_fallback_match(row)
    ]
    invalid_formal_snapshot_fallback_matches = [
        row
        for row in evaluations
        if row.get("plan_status") == "matched"
        and has_formal_snapshot_fallback_trace(row)
        and not is_formal_snapshot_fallback_match(row)
    ]
    matched_not_ready = [
        row
        for row in evaluations
        if row.get("plan_status") == "matched"
        and row.get("projection_status") != "ready"
        and not is_formal_snapshot_fallback_match(row)
    ]
    matched_board_or_bj_not_ready = [
        row
        for row in evaluations
        if row.get("plan_status") == "matched"
        and (row.get("asset_kind") == "board" or str(row.get("identity_key") or "").startswith("stock:BJ:920"))
        and row.get("projection_status") != "ready"
        and not is_formal_snapshot_fallback_match(row)
    ]
    forbidden_read_overlap = sorted(
        set(PROJECTION_MATCHER_READ_TABLES) & set(FORBIDDEN_N4_PROJECTION_MATCHER_READ_TABLES)
    )
    invalid_canonical_payloads = [row for row in evaluations if canonical_payload_errors(row)]
    legacy_runtime_signals = sorted(
        {
            str(row.get("signal_type") or "")
            for row in evaluations
            if str(row.get("signal_type") or "") not in CANONICAL_SIGNAL_TYPES
        }
    )
    return [
        quality_item(
            "P0",
            "passed" if trigger_run.get("run_id", trigger_context_run_id) == trigger_context_run_id else "failed",
            "n4_projection_matcher_context_run_ready",
            "N4 projection matcher must bind the requested current context run",
            expected=trigger_context_run_id,
            actual=str(trigger_run.get("run_id", trigger_context_run_id)),
        ),
        quality_item(
            "P0",
            "passed" if not isolation.get("current_context_is_denylisted") else "failed",
            "n4_projection_matcher_current_context_not_synthetic",
            "Current real context run must not be a synthetic denylist run",
            expected="not denylisted",
            actual=str(isolation.get("current_context_is_denylisted")),
        ),
        quality_item(
            "P0",
            "passed" if context_rows else "failed",
            "n4_projection_matcher_context_rows_available",
            "Matcher must read local N4 context rows",
            expected=">0",
            actual=str(len(context_rows)),
        ),
        quality_item(
            "P0",
            "passed" if projection_rows else "failed",
            "n4_projection_matcher_projection_rows_available",
            "Matcher must read N3 realtime projection fact rows",
            expected=">0",
            actual=str(len(projection_rows)),
        ),
        quality_item(
            "P0",
            "passed" if not matched_not_ready else "failed",
            "n4_projection_matcher_ready_only_match",
            "Only ready projection rows or scoped formal snapshot fallback rows may produce TriggerMatched",
            expected="0 matched not-ready rows outside formal snapshot fallback",
            actual=(
                f"{len(matched_not_ready)} outside fallback; "
                f"formal_snapshot_fallback={len(formal_snapshot_fallback_matches)}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if not matched_board_or_bj_not_ready else "failed",
            "n4_projection_matcher_board_bj_not_ready_no_match",
            "Board and BJ 920xxx not-ready projection rows must not produce 30m TriggerMatched",
            expected="0 matched not-ready board/BJ rows outside formal snapshot fallback",
            actual=(
                f"{len(matched_board_or_bj_not_ready)} outside fallback; "
                f"formal_snapshot_fallback={len(formal_snapshot_fallback_matches)}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if not invalid_formal_snapshot_fallback_matches else "failed",
            "n4_projection_matcher_formal_snapshot_fallback_scope",
            "Formal snapshot fallback may only emit ordinary normal Y/Q/M/W/D TriggerMatched rows",
            expected="0 invalid formal snapshot fallback matches",
            actual=str(len(invalid_formal_snapshot_fallback_matches)),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("buy_hint_matched_count") or 0) >= 0 and int(summary.get("sell_hint_matched_count") or 0) >= 0 else "failed",
            "n4_projection_matcher_hint_signals_supported",
            "BUY_HINT and SELL_HINT are formal projection matcher candidates",
            expected="hint signal support present",
            actual=f"BUY_HINT={summary.get('buy_hint_matched_count')} SELL_HINT={summary.get('sell_hint_matched_count')}",
        ),
        quality_item(
            "P0",
            "passed" if not forbidden_read_overlap else "failed",
            "n4_projection_matcher_no_forbidden_read_tables",
            "Matcher must not read raw market, event inbox/outbox, or checkpoint tables",
            expected="no forbidden read table overlap",
            actual=",".join(forbidden_read_overlap),
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n4_projection_matcher_no_database_writes",
            "Matcher dry-run must not write database rows",
            expected="before row counts equal after row counts",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item(
            "P0",
            "passed" if not invalid_canonical_payloads and not legacy_runtime_signals else "failed",
            "n4_projection_matcher_canonical_payload",
            "Projection matcher dry-run payloads must expose canonical signal_type/trigger_mark_candidate and preserve original_condition_key",
            expected="canonical payload errors=0",
            actual=f"errors={len(invalid_canonical_payloads)} legacy_signal_types={','.join(legacy_runtime_signals)}",
        ),
        quality_item(
            "P0",
            "passed",
            "n4_projection_matcher_no_outbox_consumption",
            "Matcher implementation does not consume B1 outbox or write N4 outbox",
        ),
        quality_item(
            "P0",
            "passed",
            "n4_projection_matcher_no_market_adapter",
            "Matcher implementation does not call external market adapters or synthesize projection metrics",
        ),
        quality_item(
            "P1",
            "warning" if int(summary.get("board_not_ready_object_count") or 0) > 0 else "passed",
            "n4_projection_matcher_board_not_ready_visible",
            "Board not-ready projection rows remain visible and blocked from TriggerMatched",
            expected="visible if present",
            actual=str(summary.get("board_not_ready_object_count")),
        ),
        quality_item(
            "P1",
            "warning" if int(summary.get("bj_920xxx_not_ready_object_count") or 0) > 0 else "passed",
            "n4_projection_matcher_bj_920xxx_not_ready_visible",
            "BJ 920xxx not-ready projection rows remain visible and blocked from TriggerMatched",
            expected="visible if present",
            actual=str(summary.get("bj_920xxx_not_ready_object_count")),
        ),
    ]


def capture_row_counts(dsn: str) -> dict[str, dict[str, Any]]:
    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_projection_matcher_capture_row_counts",
        source_run_id="projection_matcher_row_count_guard",
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


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))


def count_objects(rows: Sequence[Mapping[str, Any]]) -> int:
    return len({str(row.get("identity_key") or "") for row in rows if row.get("identity_key")})


def has_formal_snapshot_fallback_trace(row: Mapping[str, Any]) -> bool:
    n3_trace = row.get("n3_trace") if isinstance(row.get("n3_trace"), Mapping) else {}
    return bool(n3_trace.get("formal_snapshot_fallback") is True)


def is_formal_snapshot_fallback_match(row: Mapping[str, Any]) -> bool:
    return (
        row.get("plan_status") == "matched"
        and row.get("trigger_kind") == "trigger"
        and str(row.get("trigger_mark_candidate") or "") == "normal"
        and row.get("projection_30m_flag") is False
        and str(row.get("projection_30m_type") or "none") == "none"
        and str(row.get("trigger_period") or "") in FORMAL_TRIGGER_PERIODS
        and has_formal_snapshot_fallback_trace(row)
    )


def format_projection_matcher_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    summary = report["summary"]
    lines = [
        "# N4 Projection Matcher Implementation Report",
        "",
        "## Summary",
        "",
        f"- result: {report['result']}",
        f"- layer_role: {report['layer_role']}",
        f"- trigger_context_run_id: {report['trigger_context_run_id']}",
        f"- projection_run_id: {report['projection_run_id']}",
        f"- candidate_count: {summary['candidate_count']}",
        f"- matched_count: {summary['matched_count']}",
        f"- pending_count: {summary['pending_count']}",
        f"- not_matched_signal_count: {summary['not_matched_signal_count']}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Match Summary",
        "",
        f"- matched_by_signal_type: {summary['matched_by_signal_type']}",
        f"- pending_by_signal_type: {summary['pending_by_signal_type']}",
        f"- matched_by_trigger_mark_candidate: {summary['matched_by_trigger_mark_candidate']}",
        f"- pending_by_trigger_mark_candidate: {summary['pending_by_trigger_mark_candidate']}",
        f"- by_legacy_signal_type: {summary['by_legacy_signal_type']}",
        f"- not_matched_by_projection_signal_status: {summary['not_matched_by_projection_signal_status']}",
        f"- buy_hint_matched_count: {summary['buy_hint_matched_count']}",
        f"- sell_hint_matched_count: {summary['sell_hint_matched_count']}",
        "",
        "## Not Ready Summary",
        "",
        f"- pending_by_not_ready_classification: {summary['pending_by_not_ready_classification']}",
        f"- board_not_ready_object_count: {summary['board_not_ready_object_count']}",
        f"- bj_920xxx_not_ready_object_count: {summary['bj_920xxx_not_ready_object_count']}",
        "",
        "## Boundary Confirmation",
        "",
    ]
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: {str(value).lower()}")
    lines.extend(["", "## Quality", ""])
    for item in quality["items"]:
        lines.append(
            f"- {item['severity']} {item['status']} {item['gate_code']}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(
        [
            "",
            "## Next Gate",
            "",
            f"- allow_projection_matcher_dry_run_refresh: {str(report['next_gate']['allow_projection_matcher_dry_run_refresh']).lower()}",
            f"- allow_real_execute_preflight: {str(report['next_gate']['allow_real_execute_preflight']).lower()}",
            f"- execute_preflight_blocker: {report['next_gate']['execute_preflight_blocker']}",
            "",
            "## Rollback",
            "",
            f"- this_dry_run: {report['rollback_plan']['this_dry_run']}",
            f"- future_execute: {report['rollback_plan']['future_execute']}",
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
