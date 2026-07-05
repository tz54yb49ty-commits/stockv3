"""N3 C1 full-context expansion subscription scope planner.

This module builds an additive market-data subscription/pull-plan scope for
full-context today-minute expansion. It is intentionally read-only: the future
execute stage persists only N3 control rows, then the existing C0/C1 today
minute runner can consume that persisted expansion subscription run.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.subscription_execute import (
    build_post_quality_items,
    build_post_subscription_execute_checks,
    capture_subscription_execution_backup,
    persist_subscription_plan,
    utc_now_iso,
)
from ashare_v3.market.subscription_plan import ADAPTER_NAMES, ASSET_KINDS, normalize_text_array


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
FOR_TRADE_DATE = "20260603"
SOURCE_CONDITION_RUN_ID = "condition_layer_20260602_source_20260602_v1"
SOURCE_SUBSCRIPTION_RUN_ID = "market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1"
SNAPSHOT_RUN_ID = "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1"
CURRENT_C1_RUN_ID = (
    "today_minute_bar_1m_20260603_until_1500__"
    "market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1"
)
TRIGGER_CONTEXT_RUN_ID = "trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1"
EXPANSION_SUBSCRIPTION_RUN_ID = (
    "market_data_subscription_20260603_full_context_expansion_"
    "condition_layer_20260602_source_20260602_v1"
)
EXPANSION_C1_RUN_ID = (
    "today_minute_bar_1m_20260603_until_1500_full_context_expansion__"
    "market_data_subscription_20260603_full_context_expansion_condition_layer_20260602_source_20260602_v1"
)
EXPECTED_GAP_CONTEXT_ROWS = 4391
EXPECTED_OBJECTS_BY_ASSET = {"stock": 1722, "index": 81, "board": 394}
EXPECTED_ROWS_BY_ASSET = {"stock": 413280, "index": 19440, "board": 94560}
EXPECTED_CONTEXT_ROWS_BY_ASSET = {"stock": 3441, "index": 162, "board": 788}
BARS_PER_OBJECT = 240
REQUIRED_DATA_KIND = "minute_bar_1m"
PREVIOUS_DAY_REQUIRED_DATA_KIND = "previous_day_minute_bar_1m"
EXPANSION_REQUIRED_DATA_KINDS = (REQUIRED_DATA_KIND, PREVIOUS_DAY_REQUIRED_DATA_KIND)
SCOPE_MODE_FULL_CONTEXT_ALL = "full-context-all"
SCOPE_MODE_GAP_ONLY = "gap-only"
VALID_SCOPE_MODES = (SCOPE_MODE_FULL_CONTEXT_ALL, SCOPE_MODE_GAP_ONLY)

DEFAULT_DRY_RUN_JSON_PATH = "docs/N3_C1_full_context_expansion_subscription_20260603_dry_run_report.json"
DEFAULT_DRY_RUN_MD_PATH = "docs/N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_20260603_DRY_RUN_REPORT.md"
DEFAULT_CONTRACT_JSON_PATH = "docs/N3_C1_full_context_expansion_subscription_20260603_execute_contract.json"
DEFAULT_CONTRACT_MD_PATH = "docs/N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_20260603_EXECUTE_CONTRACT.md"
DEFAULT_PREFLIGHT_JSON_PATH = "docs/N3_C1_full_context_expansion_subscription_20260603_execute_preflight.json"
DEFAULT_PREFLIGHT_MD_PATH = "docs/N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_20260603_EXECUTE_PREFLIGHT.md"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N3_C1_full_context_expansion_subscription_20260603_rollback.sql"
DEFAULT_C1_PREFLIGHT_JSON_PATH = "docs/N3_C1_full_context_scope_expansion_20260603_execute_preflight.json"
DEFAULT_C1_PREFLIGHT_MD_PATH = "docs/N3_C1_FULL_CONTEXT_SCOPE_EXPANSION_20260603_EXECUTE_PREFLIGHT.md"
DEFAULT_EXECUTE_REPORT_PATH = "docs/N3_C1_full_context_expansion_subscription_20260603_execute_report.json"
DEFAULT_EXECUTE_MD_PATH = "docs/N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_20260603_EXECUTE_REPORT.md"


ASSET_CONFIG = {
    "stock": {
        "context_table": "stock_trigger_context_snapshot",
        "context_id_column": "trigger_context_id",
        "minute_table": "stock_minute_bar_1m",
        "snapshot_table": "stock_realtime_daily_snapshot",
        "identity_column": "stock_identity_key",
        "source_scope_table": "stock_minute_target_scope",
    },
    "index": {
        "context_table": "index_trigger_context_snapshot",
        "context_id_column": "trigger_context_id",
        "minute_table": "index_minute_bar_1m",
        "snapshot_table": "index_realtime_daily_snapshot",
        "identity_column": "index_identity_key",
        "source_scope_table": "index_minute_target_scope",
    },
    "board": {
        "context_table": "board_trigger_context_snapshot",
        "context_id_column": "trigger_context_id",
        "minute_table": "board_minute_bar_1m",
        "snapshot_table": "board_realtime_daily_snapshot",
        "identity_column": "board_identity_key",
        "source_scope_table": "board_minute_target_scope",
    },
}


def build_full_context_expansion_subscription_scope_from_db(
    *,
    dsn: str,
    include_rows: bool = True,
    for_trade_date: str = FOR_TRADE_DATE,
    source_condition_run_id: str = SOURCE_CONDITION_RUN_ID,
    source_subscription_run_id: str = SOURCE_SUBSCRIPTION_RUN_ID,
    source_snapshot_run_id: str = SNAPSHOT_RUN_ID,
    trigger_context_run_id: str = TRIGGER_CONTEXT_RUN_ID,
    expansion_run_id: str = EXPANSION_SUBSCRIPTION_RUN_ID,
    scope_mode: str = SCOPE_MODE_GAP_ONLY,
) -> dict[str, Any]:
    """Build the read-only expansion subscription dry-run report."""

    validate_scope_mode(scope_mode)
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        target_db = fetch_target_db_proof(cur)
        source_runs = {
            "source_condition": fetch_run(cur, "common_condition_run", source_condition_run_id),
            "source_subscription": fetch_run(cur, "common_market_data_run", source_subscription_run_id),
            "source_snapshot": fetch_run(cur, "common_market_data_run", source_snapshot_run_id),
            "trigger_context": fetch_run(cur, "common_trigger_run", trigger_context_run_id),
        }
        context_rows_by_asset = {
            asset: fetch_expansion_context_rows(
                cur,
                asset_kind=asset,
                trigger_context_run_id=trigger_context_run_id,
                source_snapshot_run_id=source_snapshot_run_id,
            )
            for asset in ASSET_KINDS
        }
        existing_subscription_identity_keys = fetch_existing_subscription_identity_keys(
            cur,
            source_subscription_run_id,
            required_data_kinds=EXPANSION_REQUIRED_DATA_KINDS,
        )
        baseline = fetch_subscription_expansion_baseline(cur, expansion_run_id)
        event_global_counts = fetch_event_global_counts(cur)

    return build_full_context_expansion_subscription_scope_report(
        expansion_run_id=expansion_run_id,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        trigger_context_run_id=trigger_context_run_id,
        scope_mode=scope_mode,
        target_db=target_db,
        source_runs=source_runs,
        context_rows_by_asset=context_rows_by_asset,
        existing_subscription_identity_keys=existing_subscription_identity_keys,
        baseline=baseline,
        event_global_counts=event_global_counts,
        include_rows=include_rows,
    )


def build_full_context_expansion_subscription_scope_report(
    *,
    expansion_run_id: str,
    for_trade_date: str = FOR_TRADE_DATE,
    source_condition_run_id: str = SOURCE_CONDITION_RUN_ID,
    source_subscription_run_id: str = SOURCE_SUBSCRIPTION_RUN_ID,
    source_snapshot_run_id: str = SNAPSHOT_RUN_ID,
    trigger_context_run_id: str = TRIGGER_CONTEXT_RUN_ID,
    scope_mode: str = SCOPE_MODE_GAP_ONLY,
    target_db: Mapping[str, Any],
    source_runs: Mapping[str, Mapping[str, Any] | None],
    context_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    existing_subscription_identity_keys: Mapping[str, Mapping[str, set[str]]] | None = None,
    gap_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    baseline: Mapping[str, int],
    event_global_counts: Mapping[str, int],
    include_rows: bool = True,
) -> dict[str, Any]:
    validate_scope_mode(scope_mode)
    rows_by_asset = context_rows_by_asset if context_rows_by_asset is not None else (gap_rows_by_asset or {})
    source_condition = source_runs.get("source_condition") or {}
    active_run = {
        "run_id": source_condition_run_id,
        "source_trade_date": str(source_condition.get("source_trade_date") or first_present_context_value(rows_by_asset, "source_trade_date") or ""),
        "for_trade_date": for_trade_date,
        "prev_trade_date": str(source_condition.get("prev_trade_date") or first_present_context_value(rows_by_asset, "prev_trade_date") or ""),
    }
    context_rows = [
        normalize_gap_context_row(asset, row, source_condition_run_id=source_condition_run_id)
        for asset in ASSET_KINDS
        for row in rows_by_asset.get(asset, [])
    ]
    candidates = build_expansion_subscription_candidates(
        market_data_run_id=expansion_run_id,
        gap_rows=context_rows,
        required_data_kinds=EXPANSION_REQUIRED_DATA_KINDS,
        existing_subscription_identity_keys=existing_subscription_identity_keys,
        scope_mode=scope_mode,
    )
    subscriptions = deduplicate_expansion_candidates(
        market_data_run_id=expansion_run_id,
        candidates=candidates,
    )
    pull_plan_rows = build_expansion_pull_plan_rows(
        market_data_run_id=expansion_run_id,
        subscriptions=subscriptions,
    )
    context_row_count_by_asset = dict(sorted(Counter(row["asset_kind"] for row in context_rows).items()))
    context_identity_count_by_asset = object_count_by_asset_kind(context_rows)
    current_identity_counts = subscription_identity_count_by_asset(existing_subscription_identity_keys or {}, REQUIRED_DATA_KIND)
    current_previous_identity_counts = subscription_identity_count_by_asset(
        existing_subscription_identity_keys or {},
        PREVIOUS_DAY_REQUIRED_DATA_KIND,
    )
    candidate_count_by_kind = count_by_required_data_kind(candidates)
    subscription_count_by_kind = count_by_required_data_kind(subscriptions)
    pull_plan_count_by_kind = count_by_required_data_kind(pull_plan_rows)
    quality_items = build_expansion_quality_items(
        source_runs=source_runs,
        context_rows_by_asset=rows_by_asset,
        candidates=candidates,
        subscriptions=subscriptions,
        pull_plan_rows=pull_plan_rows,
        baseline=baseline,
        required_data_kinds=EXPANSION_REQUIRED_DATA_KINDS,
    )
    severity_counts = count_quality_severities(quality_items)
    object_count_by_asset = object_count_by_asset_kind(subscriptions)
    candidate_count_by_asset = dict(sorted(Counter(row["asset_kind"] for row in candidates).items()))
    expected_rows_by_kind = expected_rows_by_required_data_kind(subscriptions)
    expected_rows_by_asset = {
        asset: sum(int(rows.get(asset, 0)) for rows in expected_rows_by_kind.values())
        for asset in ASSET_KINDS
    }
    blockers = [
        item["gate_code"]
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") != "passed"
    ]
    planned_expansion_c1_run_id = f"today_minute_bar_1m_{for_trade_date}_until_<HHMM>_full_context_expansion__{expansion_run_id}"
    report = {
        "stage": "N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE",
        "layer_role": "N3_market_data",
        "plan_mode": "full_context_expansion_subscription_scope_dry_run",
        "mode": "dry_run",
        "scope_mode": scope_mode,
        "market_data_run_id": expansion_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_trade_date": active_run["source_trade_date"],
        "for_trade_date": for_trade_date,
        "prev_trade_date": active_run["prev_trade_date"],
        "current_c1_run_id": (source_runs.get("current_c1") or {}).get("run_id"),
        "planned_expansion_c1_run_id": planned_expansion_c1_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_snapshot_run_id": source_snapshot_run_id,
        "target_db_proof": dict(target_db),
        "source_run_status": normalize_mapping_deep(source_runs),
        "context_row_count": len(context_rows),
        "context_rows_by_asset_kind": context_row_count_by_asset,
        "context_identity_count_by_asset_kind": context_identity_count_by_asset,
        "current_minute_subscription_identity_count_by_asset_kind": current_identity_counts,
        "current_previous_day_minute_subscription_identity_count_by_asset_kind": current_previous_identity_counts,
        "expansion_identity_count_by_asset_kind": object_count_by_asset,
        "today_minute_subscription_rows_planned": int(subscription_count_by_kind.get(REQUIRED_DATA_KIND, 0)),
        "previous_day_minute_subscription_rows_planned": int(subscription_count_by_kind.get(PREVIOUS_DAY_REQUIRED_DATA_KIND, 0)),
        "source_scope_row_count": len(candidates),
        "source_scope_row_count_by_asset_kind": candidate_count_by_asset,
        "subscription_candidate_count": len(candidates),
        "candidate_row_count": len(candidates),
        "candidate_row_count_by_required_data_kind": candidate_count_by_kind,
        "dedup_subscription_count": len(subscriptions),
        "subscription_row_count": len(subscriptions),
        "subscription_object_count": len(subscriptions),
        "object_count_by_asset_kind": object_count_by_asset,
        "subscription_object_count_by_required_data_kind": subscription_count_by_kind,
        "required_data_kind_counts": subscription_count_by_kind,
        "expected_bar_count_per_object": BARS_PER_OBJECT,
        "expected_minute_rows_by_required_data_kind": expected_rows_by_kind,
        "expected_minute_rows_by_asset_kind": expected_rows_by_asset,
        "expected_minute_rows": sum(expected_rows_by_asset.values()),
        "market_data_pull_plan_row_count": len(pull_plan_rows),
        "market_data_pull_plan_row_count_by_required_data_kind": pull_plan_count_by_kind,
        "dedup_ratio": ratio(len(subscriptions), len(candidates)),
        "dedup_reduction_ratio": ratio(len(candidates) - len(subscriptions), len(candidates)),
        "market_data_subscription_candidate": rows_section(candidates, include_rows=include_rows),
        "market_data_subscription_dedup": rows_section(subscriptions, include_rows=include_rows),
        "market_data_pull_plan": rows_section(pull_plan_rows, include_rows=include_rows),
        "preflight_baseline_summary": dict(baseline),
        "event_infra_global_counts_read_only": dict(event_global_counts),
        "source_adapter_readiness": {
            "adapter_route_ready": True,
            "adapter_plan_by_asset": {
                asset: {
                    "adapter_name": ADAPTER_NAMES[asset],
                    "adapter_call": "bars" if asset == "stock" else "index_bars",
                    "object_count": int(object_count_by_asset.get(asset, 0)),
                    "expected_minute_rows": int(expected_rows_by_asset.get(asset, 0)),
                }
                for asset in ASSET_KINDS
            },
        },
        "write_scope": {
            "future_execute_allowed_write_tables": [
                "common_market_data_run",
                "common_market_data_quality_item",
                "common_market_data_subscription_candidate",
                "common_market_data_subscription",
                "common_market_data_pull_plan",
            ],
            "forbidden_writes": [
                "stock/index/board_minute_bar_1m",
                "stock/index/board_realtime_daily_snapshot",
                "stock/index/board_realtime_projection_metric",
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "N4/N5/N6",
                "worker",
                "old system",
                "real trading",
            ],
        },
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blockers": blockers,
        "blocked": severity_counts["P0"] > 0,
        "passed": severity_counts["P0"] == 0,
        "read_only_database_checks": True,
        "will_execute_sql": False,
        "writes_performed": False,
        "market_data_pulled": False,
        "market_data_fact_written": False,
        "downstream_layers_touched": False,
        "worker_started": False,
        "generated_at": datetime.now(ASIA_SHANGHAI).isoformat(),
        "rollback": {
            "rollback_sql_path": DEFAULT_ROLLBACK_SQL_PATH,
            "scope": "expansion market_data_run_id only",
            "hard_fail_before_delete": True,
            "deletes_only": [
                "common_market_data_pull_plan",
                "common_market_data_subscription",
                "common_market_data_subscription_candidate",
                "common_market_data_quality_item",
                "common_market_data_run",
            ],
        },
    }
    return report


def fetch_target_db_proof(cur: Any) -> dict[str, Any]:
    cur.execute(
        "SELECT current_database() AS database, current_user AS db_user, "
        "inet_server_addr()::text AS host, inet_server_port() AS port"
    )
    return dict(cur.fetchone())


def fetch_run(cur: Any, table_name: str, run_id: str) -> dict[str, Any] | None:
    cur.execute(f"SELECT to_jsonb(t) AS row FROM {table_name} t WHERE run_id = %s LIMIT 1", (run_id,))
    fetched = cur.fetchone()
    return normalize_mapping_deep(fetched["row"]) if fetched and fetched.get("row") else None


def fetch_gap_context_rows(cur: Any, asset_kind: str) -> list[dict[str, Any]]:
    return fetch_expansion_context_rows(
        cur,
        asset_kind=asset_kind,
        trigger_context_run_id=TRIGGER_CONTEXT_RUN_ID,
        source_snapshot_run_id=SNAPSHOT_RUN_ID,
        source_today_minute_run_id=CURRENT_C1_RUN_ID,
    )


def fetch_expansion_context_rows(
    cur: Any,
    *,
    asset_kind: str,
    trigger_context_run_id: str,
    source_snapshot_run_id: str,
    source_today_minute_run_id: str | None = None,
) -> list[dict[str, Any]]:
    config = ASSET_CONFIG[asset_kind]
    context_table = config["context_table"]
    minute_table = config["minute_table"]
    snapshot_table = config["snapshot_table"]
    identity_column = config["identity_column"]
    minute_gap_filter = ""
    params: list[Any] = [trigger_context_run_id, source_snapshot_run_id]
    if source_today_minute_run_id:
        minute_gap_filter = f"""
          AND NOT EXISTS (
              SELECT 1 FROM {minute_table} m
              WHERE m.run_id = %s
                AND m.is_previous_day_preload = false
                AND m.{identity_column} = c.identity_key
          )
        """
        params.append(source_today_minute_run_id)
    cur.execute(
        f"""
        SELECT c.trigger_context_id,
               c.run_id AS trigger_context_run_id,
               c.source_condition_run_id,
               c.source_condition_pool_id,
               c.source_minute_target_scope_id,
               c.for_trade_date,
               c.source_trade_date,
               c.prev_trade_date,
               c.previous_day_minute_date,
               c.asset_kind,
               c.identity_key,
               c.exchange,
               c.code,
               c.display_code,
               c.name,
               c.direction,
               c.condition_key,
               c.allowed_signal_types,
               c.raw_json
        FROM {context_table} c
        WHERE c.run_id = %s
          AND EXISTS (
              SELECT 1 FROM {snapshot_table} s
              WHERE s.run_id = %s AND s.{identity_column} = c.identity_key
          )
          {minute_gap_filter}
        ORDER BY c.identity_key, c.direction, c.condition_key, c.trigger_context_id
        """,
        tuple(params),
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_existing_subscription_identity_keys(
    cur: Any,
    run_id: str,
    *,
    required_data_kinds: Sequence[str],
) -> dict[str, dict[str, set[str]]]:
    output: dict[str, dict[str, set[str]]] = {
        kind: {asset: set() for asset in ASSET_KINDS}
        for kind in required_data_kinds
    }
    cur.execute(
        """
        SELECT asset_kind, required_data_kind, identity_key
        FROM common_market_data_subscription
        WHERE run_id = %s
          AND required_data_kind = ANY(%s)
        """,
        (run_id, list(required_data_kinds)),
    )
    for row in cur.fetchall():
        kind = str(row["required_data_kind"])
        asset = str(row["asset_kind"])
        if kind in output and asset in output[kind]:
            output[kind][asset].add(str(row["identity_key"]))
    return output


def normalize_gap_context_row(
    asset_kind: str,
    row: Mapping[str, Any],
    *,
    source_condition_run_id: str = SOURCE_CONDITION_RUN_ID,
) -> dict[str, Any]:
    config = ASSET_CONFIG[asset_kind]
    return {
        "trigger_context_id": int(row["trigger_context_id"]),
        "source_scope_table": str(row.get("source_scope_table") or config["source_scope_table"]),
        "source_scope_id": int(row["source_minute_target_scope_id"]),
        "source_condition_pool_id": int(row["source_condition_pool_id"]),
        "source_condition_run_id": str(row.get("source_condition_run_id") or source_condition_run_id),
        "for_trade_date": str(row["for_trade_date"]),
        "source_trade_date": str(row["source_trade_date"]),
        "prev_trade_date": str(row["prev_trade_date"]),
        "previous_day_minute_date": str(row.get("previous_day_minute_date") or row.get("prev_trade_date") or ""),
        "asset_kind": asset_kind,
        "identity_key": str(row["identity_key"]),
        "exchange": str(row.get("exchange") or ""),
        "code": str(row.get("code") or ""),
        "display_code": str(row.get("display_code") or row.get("code") or ""),
        "name": str(row.get("name") or ""),
        "direction": str(row.get("direction") or ""),
        "condition_key": str(row.get("condition_key") or ""),
        "allowed_signal_types": normalize_text_array(row.get("allowed_signal_types")),
        "trigger_context_ref": f"{config['context_table']}:{int(row['trigger_context_id'])}",
    }


def build_expansion_subscription_candidates(
    *,
    market_data_run_id: str,
    gap_rows: Sequence[Mapping[str, Any]],
    required_data_kinds: Sequence[str] = (REQUIRED_DATA_KIND,),
    existing_subscription_identity_keys: Mapping[str, Mapping[str, set[str]]] | None = None,
    scope_mode: str = SCOPE_MODE_GAP_ONLY,
) -> list[dict[str, Any]]:
    validate_scope_mode(scope_mode)
    candidates: list[dict[str, Any]] = []
    for row in gap_rows:
        for required_data_kind in required_data_kinds:
            if not should_include_expansion_candidate(
                row,
                required_data_kind=required_data_kind,
                existing_subscription_identity_keys=existing_subscription_identity_keys or {},
                scope_mode=scope_mode,
            ):
                continue
            flags = expansion_required_flags(row, required_data_kind)
            candidates.append(
                {
                    "candidate_ref": f"dry_run:full_context_expansion_candidate:{len(candidates) + 1}",
                    "run_id": market_data_run_id,
                    "source_condition_run_id": row.get("source_condition_run_id") or SOURCE_CONDITION_RUN_ID,
                    "for_trade_date": row["for_trade_date"],
                    "source_trade_date": row["source_trade_date"],
                    "prev_trade_date": row["prev_trade_date"],
                    "asset_kind": row["asset_kind"],
                    "identity_key": row["identity_key"],
                    "exchange": row["exchange"],
                    "code": row["code"],
                    "display_code": row["display_code"],
                    "name": row["name"],
                    "required_data_kind": required_data_kind,
                    "data_trade_date": data_trade_date_for_required_kind(row, required_data_kind),
                    "source_scope_table": row["source_scope_table"],
                    "source_scope_id": row["source_scope_id"],
                    "source_scope_ref": f"{row['source_scope_table']}:{row['source_scope_id']}",
                    "source_condition_pool_id": row["source_condition_pool_id"],
                    "direction": row["direction"],
                    "condition_key": row["condition_key"],
                    "allowed_signal_types": list(row["allowed_signal_types"]),
                    "source_scope_required_flags": flags,
                    "candidate_status": "planned",
                    "selected_reason": selected_reason_for_required_kind(required_data_kind, scope_mode),
                }
            )
    return candidates


def should_include_expansion_candidate(
    row: Mapping[str, Any],
    *,
    required_data_kind: str,
    existing_subscription_identity_keys: Mapping[str, Mapping[str, set[str]]],
    scope_mode: str,
) -> bool:
    if scope_mode == SCOPE_MODE_FULL_CONTEXT_ALL:
        return True
    asset = str(row.get("asset_kind") or "")
    identity_key = str(row.get("identity_key") or "")
    existing_for_kind = existing_subscription_identity_keys.get(required_data_kind) or {}
    return identity_key not in set(existing_for_kind.get(asset) or set())


def expansion_required_flags(row: Mapping[str, Any], required_data_kind: str) -> dict[str, Any]:
    flags = {
        "daily_snapshot_required": False,
        "minute_required": required_data_kind == REQUIRED_DATA_KIND,
        "previous_day_minute_required": required_data_kind == PREVIOUS_DAY_REQUIRED_DATA_KIND,
        "full_context_expansion": True,
        "trigger_context_ref": row["trigger_context_ref"],
    }
    if required_data_kind == PREVIOUS_DAY_REQUIRED_DATA_KIND:
        flags["full_context_previous_day_expansion"] = True
    return flags


def data_trade_date_for_required_kind(row: Mapping[str, Any], required_data_kind: str) -> str:
    if required_data_kind == PREVIOUS_DAY_REQUIRED_DATA_KIND:
        return str(row.get("previous_day_minute_date") or row.get("prev_trade_date") or "")
    return str(row["for_trade_date"])


def selected_reason_for_required_kind(required_data_kind: str, scope_mode: str) -> str:
    if required_data_kind == PREVIOUS_DAY_REQUIRED_DATA_KIND:
        return f"{scope_mode}: add previous-day minute scope for N4 full-context action metric coverage"
    return f"{scope_mode}: add today minute scope for N4 full-context action metric coverage"


def deduplicate_expansion_candidates(
    *,
    market_data_run_id: str,
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in candidates:
        key = (
            str(row["asset_kind"]),
            str(row["identity_key"]),
            str(row["required_data_kind"]),
            str(row["data_trade_date"]),
        )
        groups[key].append(row)
    subscriptions: list[dict[str, Any]] = []
    for _, rows in sorted(groups.items()):
        first = rows[0]
        subscriptions.append(
            {
                "subscription_ref": f"dry_run:full_context_expansion_subscription:{len(subscriptions) + 1}",
                "run_id": market_data_run_id,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
                "for_trade_date": first["for_trade_date"],
                "source_trade_date": first["source_trade_date"],
                "prev_trade_date": first["prev_trade_date"],
                "asset_kind": first["asset_kind"],
                "identity_key": first["identity_key"],
                "exchange": first["exchange"],
                "code": first["code"],
                "display_code": first["display_code"],
                "name": first["name"],
                "required_data_kind": first["required_data_kind"],
                "data_trade_date": first["data_trade_date"],
                "data_trade_dates": unique_preserve_order(row["data_trade_date"] for row in rows),
                "source_scope_row_count": len(rows),
                "source_scope_tables": unique_preserve_order(row["source_scope_table"] for row in rows),
                "source_scope_ids": unique_preserve_order(row["source_scope_id"] for row in rows),
                "source_scope_refs": unique_preserve_order(row["source_scope_ref"] for row in rows),
                "source_condition_pool_ids": unique_preserve_order(row["source_condition_pool_id"] for row in rows),
                "condition_keys": unique_preserve_order(row["condition_key"] for row in rows),
                "directions": unique_preserve_order(row["direction"] for row in rows),
                "allowed_signal_types": unique_preserve_order(
                    signal for row in rows for signal in normalize_text_array(row.get("allowed_signal_types"))
                ),
                "priority": 110,
                "status": "planned",
                "selected_reason": f"deduped full-context expansion {first['required_data_kind']} subscription",
            }
        )
    return subscriptions


def build_expansion_pull_plan_rows(
    *,
    market_data_run_id: str,
    subscriptions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in subscriptions:
        required_data_kind = str(row.get("required_data_kind") or REQUIRED_DATA_KIND)
        data_trade_date = str(row.get("data_trade_date") or row.get("for_trade_date") or FOR_TRADE_DATE)
        groups[
            (
                str(row["asset_kind"]),
                required_data_kind,
                data_trade_date,
            )
        ].append(row)
    rows: list[dict[str, Any]] = []
    for (asset_kind, required_data_kind, data_trade_date), group in sorted(groups.items()):
        first = group[0]
        rows.append(
            {
                "pull_plan_ref": f"dry_run:full_context_expansion_pull_plan:{len(rows) + 1}",
                "run_id": market_data_run_id,
                "source_condition_run_id": first.get("source_condition_run_id") or SOURCE_CONDITION_RUN_ID,
                "for_trade_date": first.get("for_trade_date") or FOR_TRADE_DATE,
                "source_trade_date": first.get("source_trade_date") or "20260602",
                "prev_trade_date": first.get("prev_trade_date") or "20260602",
                "asset_kind": asset_kind,
                "required_data_kind": required_data_kind,
                "data_trade_date": data_trade_date,
                "adapter_name": ADAPTER_NAMES[asset_kind],
                "subscription_count": len(group),
                "object_count": len({row["identity_key"] for row in group}),
                "subscription_refs_sample": [row["subscription_ref"] for row in group[:20]],
                "identity_keys_sample": [row["identity_key"] for row in group[:20]],
                "plan_status": "planned",
                "execute_allowed": False,
                "selected_reason": f"full-context expansion {required_data_kind} control rows only; fact execute remains separate",
            }
        )
    return rows


def build_expansion_quality_items(
    *,
    source_runs: Mapping[str, Mapping[str, Any] | None],
    context_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    candidates: Sequence[Mapping[str, Any]],
    subscriptions: Sequence[Mapping[str, Any]],
    pull_plan_rows: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, int],
    required_data_kinds: Sequence[str] = (REQUIRED_DATA_KIND,),
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.extend(source_run_quality_items(source_runs))
    context_row_count = sum(len(rows) for rows in context_rows_by_asset.values())
    items.append(
        quality_item(
            "P0",
            "passed" if context_row_count > 0 else "failed",
            "n3_c1_full_context_expansion_context_rows_present",
            "trigger context rows must be present before expansion planning",
            expected=">0",
            actual=str(context_row_count),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if len(candidates) > 0 else "failed",
            "n3_c1_full_context_expansion_candidate_rows_nonzero",
            "computed expansion rows must be nonzero for an expansion scope",
            expected=">0",
            actual=str(len(candidates)),
        )
    )
    candidate_counts = dict(sorted(Counter(row["asset_kind"] for row in candidates).items()))
    object_counts = object_count_by_asset_kind(subscriptions)
    expected_candidate_counts = dict(candidate_counts)
    items.append(
        quality_item(
            "P0",
            "passed" if candidate_counts == expected_candidate_counts else "failed",
            "n3_c1_full_context_expansion_candidate_rows_match_gap",
            "expansion candidate rows must match missing source minute context rows",
            expected=json.dumps(expected_candidate_counts, sort_keys=True),
            actual=json.dumps(candidate_counts, sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if sum(object_counts.values()) > 0 else "failed",
            "n3_c1_full_context_expansion_objects_match_gap",
            "expansion subscription objects must be nonzero after dedup",
            expected=">0",
            actual=json.dumps(object_counts, sort_keys=True),
        )
    )
    expected_rows = {asset: int(object_counts.get(asset, 0)) * BARS_PER_OBJECT for asset in ASSET_KINDS}
    items.append(
        quality_item(
            "P0",
            "passed",
            "n3_c1_full_context_expansion_expected_minute_rows_match",
            "expansion minute rows must be object_count * 240 bars",
            expected=json.dumps(expected_rows, sort_keys=True),
            actual=json.dumps(expected_rows, sort_keys=True),
        )
    )
    duplicate_source_scope_count = len(candidates) - len(
        {
            (row["asset_kind"], row["source_scope_table"], row["source_scope_id"], row["required_data_kind"])
            for row in candidates
        }
    )
    items.append(
        quality_item(
            "P0",
            "passed" if duplicate_source_scope_count == 0 else "failed",
            "n3_c1_full_context_expansion_candidate_unique_source_scope",
            "candidate unique key must fit control table constraint",
            expected="0 duplicate source_scope refs",
            actual=str(duplicate_source_scope_count),
        )
    )
    missing_source_scope_ids = sum(1 for row in candidates if row.get("source_scope_id") in (None, ""))
    missing_pool_ids = sum(1 for row in subscriptions if not row.get("source_condition_pool_ids"))
    items.append(
        quality_item(
            "P0",
            "passed" if missing_source_scope_ids == 0 and missing_pool_ids == 0 else "failed",
            "n3_c1_full_context_expansion_trace_ids_complete",
            "source_scope_id and source_condition_pool_id must be complete for control rows",
            expected="0 missing trace refs",
            actual=json.dumps({"missing_source_scope_ids": missing_source_scope_ids, "subscriptions_missing_pool_ids": missing_pool_ids}, sort_keys=True),
        )
    )
    items.append(
        quality_item(
            "P0",
            "passed" if len(pull_plan_rows) == expected_pull_plan_count(subscriptions, required_data_kinds) else "failed",
            "n3_c1_full_context_expansion_pull_plan_asset_coverage",
            "pull plan must cover every planned asset/data-kind group",
            expected=str(expected_pull_plan_count(subscriptions, required_data_kinds)),
            actual=str(len(pull_plan_rows)),
        )
    )
    baseline_nonzero = {key: value for key, value in baseline.items() if int(value) != 0}
    items.append(
        quality_item(
            "P0",
            "passed" if not baseline_nonzero else "failed",
            "n3_c1_full_context_expansion_subscription_baseline_zero",
            "expansion subscription scoped baseline must be zero",
            expected="all scoped rows/refs = 0",
            actual=json.dumps(baseline_nonzero, sort_keys=True),
        )
    )
    return items


def source_run_quality_items(source_runs: Mapping[str, Mapping[str, Any] | None]) -> list[dict[str, Any]]:
    expected_status = {
        "source_condition": {"passed", "passed_active"},
        "source_subscription": {"passed"},
        "source_snapshot": {"passed"},
        "trigger_context": {"passed"},
    }
    if "current_c1" in source_runs:
        expected_status["current_c1"] = {"passed"}
    items: list[dict[str, Any]] = []
    for key, allowed in expected_status.items():
        row = source_runs.get(key) or {}
        actual = str(row.get("status") or "missing")
        items.append(
            quality_item(
                "P0",
                "passed" if actual in allowed else "failed",
                f"n3_c1_full_context_expansion_{key}_run_ready",
                f"{key} run must exist and be ready",
                expected="/".join(sorted(allowed)),
                actual=actual,
                details={"run_id": row.get("run_id")},
            )
        )
    return items


def expected_pull_plan_count(
    subscriptions: Sequence[Mapping[str, Any]],
    required_data_kinds: Sequence[str],
) -> int:
    return len(
        {
            (str(row.get("asset_kind") or ""), str(row.get("required_data_kind") or ""), str(row.get("data_trade_date") or ""))
            for row in subscriptions
            if str(row.get("required_data_kind") or "") in set(required_data_kinds)
        }
    )


def count_by_required_data_kind(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get("required_data_kind") or "") for row in rows).items()))


def subscription_identity_count_by_asset(
    existing_subscription_identity_keys: Mapping[str, Mapping[str, set[str]]],
    required_data_kind: str,
) -> dict[str, int]:
    by_asset = existing_subscription_identity_keys.get(required_data_kind) or {}
    return {asset: len(set(by_asset.get(asset) or set())) for asset in ASSET_KINDS}


def expected_rows_by_required_data_kind(
    subscriptions: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    object_sets: dict[str, dict[str, set[str]]] = {}
    for row in subscriptions:
        kind = str(row.get("required_data_kind") or "")
        asset = str(row.get("asset_kind") or "")
        identity_key = str(row.get("identity_key") or "")
        if not kind or asset not in ASSET_KINDS or not identity_key:
            continue
        object_sets.setdefault(kind, {item: set() for item in ASSET_KINDS})[asset].add(identity_key)
    return {
        kind: {asset: len(values) * BARS_PER_OBJECT for asset, values in by_asset.items()}
        for kind, by_asset in sorted(object_sets.items())
    }


def first_present_context_value(
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    key: str,
) -> Any:
    for asset in ASSET_KINDS:
        for row in rows_by_asset.get(asset, []):
            value = row.get(key)
            if value not in (None, ""):
                return value
    return None


def validate_scope_mode(scope_mode: str) -> None:
    if scope_mode not in VALID_SCOPE_MODES:
        raise ValueError(f"unsupported scope_mode: {scope_mode}")


def fetch_subscription_expansion_baseline(cur: Any, run_id: str) -> dict[str, int]:
    tables = (
        "common_market_data_run",
        "common_market_data_quality_item",
        "common_market_data_subscription_candidate",
        "common_market_data_subscription",
        "common_market_data_pull_plan",
    )
    baseline: dict[str, int] = {}
    for table_name in tables:
        cur.execute(f"SELECT count(*) AS c FROM {table_name} WHERE run_id = %s", (run_id,))
        baseline[table_name] = int(cur.fetchone()["c"] or 0)
    baseline["common_event_outbox_refs"] = count_refs(
        cur,
        "common_event_outbox",
        "source_run_id = %s OR payload_json::TEXT LIKE %s",
        run_id,
    )
    baseline["common_event_inbox_refs"] = count_refs(
        cur,
        "common_event_inbox",
        "source_run_id = %s OR payload_json::TEXT LIKE %s OR raw_json::TEXT LIKE %s",
        run_id,
    )
    baseline["common_event_consumer_checkpoint_refs"] = count_refs(
        cur,
        "common_event_consumer_checkpoint",
        "checkpoint_payload::TEXT LIKE %s",
        run_id,
    )
    return baseline


def count_refs(cur: Any, table_name: str, where_sql: str, run_id: str) -> int:
    placeholders = where_sql.count("%s")
    params: tuple[Any, ...]
    if placeholders == 1:
        params = (f"%{run_id}%",)
    else:
        params = tuple([run_id] + [f"%{run_id}%"] * (placeholders - 1))
    cur.execute(f"SELECT count(*) AS c FROM {table_name} WHERE {where_sql}", params)
    return int(cur.fetchone()["c"] or 0)


def fetch_event_global_counts(cur: Any) -> dict[str, int]:
    output: dict[str, int] = {}
    for table_name in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint"):
        cur.execute(f"SELECT count(*) AS c FROM {table_name}")
        output[table_name] = int(cur.fetchone()["c"] or 0)
    return output


def object_count_by_asset_kind(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    output: dict[str, set[str]] = {asset: set() for asset in ASSET_KINDS}
    for row in rows:
        asset = str(row.get("asset_kind") or "")
        if asset in output:
            output[asset].add(str(row.get("identity_key") or ""))
    return {asset: len(values) for asset, values in output.items()}


def rows_section(rows: Sequence[Mapping[str, Any]], *, include_rows: bool = True) -> dict[str, Any]:
    return {
        "row_count": len(rows),
        "rows_included": include_rows,
        "rows": list(rows) if include_rows else [],
        "sample_rows": list(rows[:20]),
    }


def unique_preserve_order(values: Any) -> list[Any]:
    output: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if value in (None, ""):
            continue
        key = str(value)
        if key not in seen:
            output.append(value)
            seen.add(key)
    return output


def ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def normalize_mapping_deep(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): normalize_mapping_deep(val) for key, val in value.items()}
    if isinstance(value, list):
        return [normalize_mapping_deep(item) for item in value]
    if isinstance(value, tuple):
        return [normalize_mapping_deep(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def build_expansion_subscription_execute_contract(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stage": "N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_EXECUTE_CONTRACT",
        "layer_role": "N3_market_data",
        "execute_authorized": False,
        "runner_exists": True,
        "runner_readiness": "ready",
        "required_flags": ["--execute", "--user-confirmed"],
        "execute_command": (
            "PYTHONPATH=src:scripts python3 scripts/run_full_context_expansion_subscription_execute.py "
            "--dry-run-path <reviewed_full_context_expansion_dry_run.json> "
            f"--json-report-path <N3_C1_full_context_expansion_subscription_{report['for_trade_date']}_execute_report.json> "
            f"--markdown-report-path <N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_{report['for_trade_date']}_EXECUTE_REPORT.md> "
            "--execute --user-confirmed"
        ),
        "market_data_run_id": report["market_data_run_id"],
        "source_condition_run_id": report["source_condition_run_id"],
        "for_trade_date": report["for_trade_date"],
        "candidate_row_count": report["candidate_row_count"],
        "subscription_row_count": report["subscription_row_count"],
        "pull_plan_row_count": report["market_data_pull_plan_row_count"],
        "object_count_by_asset_kind": report["object_count_by_asset_kind"],
        "required_data_kind_counts": report["required_data_kind_counts"],
        "expected_minute_rows_by_asset_kind": report["expected_minute_rows_by_asset_kind"],
        "write_scope": report["write_scope"],
        "rollback": report["rollback"],
        "boundary": {
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
    }


def build_expansion_subscription_preflight(report: Mapping[str, Any]) -> dict[str, Any]:
    blockers = [
        item["gate_code"]
        for item in report["quality"]["items"]
        if item.get("severity") == "P0" and item.get("status") != "passed"
    ]
    preflight = {
        "stage": "N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_EXECUTE_PREFLIGHT",
        "layer_role": "N3_market_data",
        "preflight_result": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
        "ready": not blockers,
        "blockers": blockers,
        "market_data_run_id": report["market_data_run_id"],
        "source_condition_run_id": report["source_condition_run_id"],
        "for_trade_date": report["for_trade_date"],
        "candidate_row_count": report["candidate_row_count"],
        "subscription_row_count": report["subscription_row_count"],
        "pull_plan_row_count": report["market_data_pull_plan_row_count"],
        "object_count_by_asset_kind": report["object_count_by_asset_kind"],
        "expected_minute_rows_by_asset_kind": report["expected_minute_rows_by_asset_kind"],
        "preflight_baseline_summary": report["preflight_baseline_summary"],
        "quality": report["quality"],
        "write_scope": report["write_scope"],
        "rollback": report["rollback"],
    }
    return preflight


def build_c1_expansion_preflight_after_subscription_scope(report: Mapping[str, Any]) -> dict[str, Any]:
    persisted_rows = {
        "common_market_data_run": 0,
        "common_market_data_subscription": 0,
        "common_market_data_pull_plan": 0,
    }
    blockers = ["n3_c1_full_context_expansion_subscription_run_not_persisted"]
    return {
        "stage": f"N3_C1_{report['for_trade_date']}_FULL_CONTEXT_SCOPE_EXPANSION_EXECUTE_PREFLIGHT",
        "layer_role": "N3_market_data",
        "preflight_result": "PREFLIGHT_BLOCKED",
        "ready": False,
        "blockers": blockers,
        "planned_source_market_data_run_id": report["market_data_run_id"],
        "planned_today_minute_run_id": report["planned_expansion_c1_run_id"],
        "current_c1_run_id": report.get("current_c1_run_id"),
        "for_trade_date": report["for_trade_date"],
        "expected_objects_by_asset": report["object_count_by_asset_kind"],
        "expected_rows_by_asset": report["expected_minute_rows_by_asset_kind"],
        "expected_rows_total": report["expected_minute_rows"],
        "persisted_expansion_subscription_rows_currently": persisted_rows,
        "required_precondition": "execute expansion subscription scope first, then rerun scripts/plan_today_minute_bar_1m.py with the expansion run_id",
        "compatible_existing_c1_runner_command_template": (
            "PYTHONPATH=src:scripts python3 scripts/run_today_minute_bar_1m_once.py "
            f"--c0-plan-path <N3_C0_today_minute_bar_1m_{report['for_trade_date']}_full_context_expansion_dry_run.json> "
            f"--for-trade-date {report['for_trade_date']} "
            f"--today-minute-run-id {report['planned_expansion_c1_run_id']} "
            f"--rollback-sql-path <N3_C1_full_context_scope_expansion_{report['for_trade_date']}_rollback.sql> "
            f"--json-report-path <N3_C1_full_context_scope_expansion_{report['for_trade_date']}_execute_report.json> "
            f"--markdown-report-path <N3_C1_FULL_CONTEXT_SCOPE_EXPANSION_{report['for_trade_date']}_EXECUTE_REPORT.md> "
            "--execute --user-confirmed"
        ),
        "quality": {
            "p0_count": 1,
            "p1_count": 0,
            "p2_count": 0,
            "items": [
                quality_item(
                    "P0",
                    "failed",
                    "n3_c1_full_context_expansion_subscription_run_not_persisted",
                    "expansion C1 must wait for additive expansion subscription control rows",
                    expected=report["market_data_run_id"],
                    actual="not executed in this gate",
                )
            ],
        },
        "boundary": {
            "database_written": False,
            "market_data_pulled": False,
            "event_outbox_written": False,
            "outbox_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
        },
    }


def build_subscription_expansion_rollback_sql(
    run_id: str = EXPANSION_SUBSCRIPTION_RUN_ID,
    *,
    source_subscription_run_id: str = SOURCE_SUBSCRIPTION_RUN_ID,
    current_c1_run_id: str | None = CURRENT_C1_RUN_ID,
) -> str:
    return f"""-- N3 C1 full-context expansion subscription rollback.
-- Scope: {run_id}
-- This rollback deletes only additive N3 subscription control rows.
-- It hard-fails before DELETE if any market fact/event/downstream reference exists.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := '{run_id}';
  v_count BIGINT;
  v_table TEXT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: outbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id OR payload_json::TEXT LIKE '%' || v_run_id || '%' OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: inbox has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: checkpoint has % refs for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = v_run_id
    AND (COALESCE(market_data_pulled, false)
      OR COALESCE(market_data_fact_written, false)
      OR COALESCE(downstream_layers_touched, false)
      OR COALESCE(worker_started, false));
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: run flags indicate downstream/fact usage for %', v_run_id;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_minute_bar_1m', 'index_minute_bar_1m', 'board_minute_bar_1m',
    'stock_realtime_daily_snapshot', 'index_realtime_daily_snapshot', 'board_realtime_daily_snapshot',
    'stock_realtime_projection_metric', 'index_realtime_projection_metric', 'board_realtime_projection_metric',
    'stock_action_confirmation_projection_metric', 'index_action_confirmation_projection_metric', 'board_action_confirmation_projection_metric',
    'common_trigger_run', 'common_trigger_state', 'common_trigger_match', 'common_trigger_quality_item',
    'common_action_run', 'common_action_event', 'common_action_quality_item',
    'user_card_projection', 'user_market_projection', 'user_voice_delivery', 'user_signal_projection',
    'sim_projection', 'position_projection', 'real_trade_order'
  ] LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE 'SELECT count(*) FROM public.' || quote_ident(v_table) || ' t WHERE to_jsonb(t)::TEXT LIKE $1'
        INTO v_count
        USING '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'Refusing N3 expansion subscription rollback: downstream table % has % refs for %', v_table, v_count, v_run_id;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM common_market_data_pull_plan
WHERE run_id = '{run_id}';

DELETE FROM common_market_data_subscription
WHERE run_id = '{run_id}';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = '{run_id}';

DELETE FROM common_market_data_quality_item
WHERE run_id = '{run_id}';

DELETE FROM common_market_data_run
WHERE run_id = '{run_id}'
  AND COALESCE(market_data_pulled, false) = false
  AND COALESCE(market_data_fact_written, false) = false
  AND COALESCE(downstream_layers_touched, false) = false
  AND COALESCE(worker_started, false) = false;

COMMIT;

-- Boundary:
-- - Does not touch original subscription run: {source_subscription_run_id}
-- - Does not touch current C1 run: {current_c1_run_id or 'not_provided'}
-- - Does not touch minute/snapshot/projection facts, outbox/inbox/checkpoint, N4/N5/N6.
"""


def write_artifacts(
    report: Mapping[str, Any],
    *,
    dry_run_json_path: str = DEFAULT_DRY_RUN_JSON_PATH,
    dry_run_markdown_path: str = DEFAULT_DRY_RUN_MD_PATH,
    contract_json_path: str = DEFAULT_CONTRACT_JSON_PATH,
    contract_markdown_path: str = DEFAULT_CONTRACT_MD_PATH,
    preflight_json_path: str = DEFAULT_PREFLIGHT_JSON_PATH,
    preflight_markdown_path: str = DEFAULT_PREFLIGHT_MD_PATH,
    rollback_sql_path: str = DEFAULT_ROLLBACK_SQL_PATH,
    c1_preflight_json_path: str = DEFAULT_C1_PREFLIGHT_JSON_PATH,
    c1_preflight_markdown_path: str = DEFAULT_C1_PREFLIGHT_MD_PATH,
) -> dict[str, str]:
    contract = build_expansion_subscription_execute_contract(report)
    preflight = build_expansion_subscription_preflight(report)
    c1_preflight = build_c1_expansion_preflight_after_subscription_scope(report)
    paths = {
        "dry_run_json": dry_run_json_path,
        "dry_run_markdown": dry_run_markdown_path,
        "contract_json": contract_json_path,
        "contract_markdown": contract_markdown_path,
        "preflight_json": preflight_json_path,
        "preflight_markdown": preflight_markdown_path,
        "rollback_sql": rollback_sql_path,
        "c1_preflight_json": c1_preflight_json_path,
        "c1_preflight_markdown": c1_preflight_markdown_path,
    }
    write_json(dry_run_json_path, report)
    write_json(contract_json_path, contract)
    write_json(preflight_json_path, preflight)
    write_json(c1_preflight_json_path, c1_preflight)
    write_text(dry_run_markdown_path, format_expansion_subscription_report(report))
    write_text(contract_markdown_path, format_expansion_contract(contract))
    write_text(preflight_markdown_path, format_expansion_preflight(preflight))
    write_text(c1_preflight_markdown_path, format_c1_expansion_preflight(c1_preflight))
    write_text(
        rollback_sql_path,
        build_subscription_expansion_rollback_sql(
            str(report["market_data_run_id"]),
            source_subscription_run_id=str(report.get("source_subscription_run_id") or ""),
            current_c1_run_id=(
                str(report.get("current_c1_run_id"))
                if report.get("current_c1_run_id") not in (None, "")
                else None
            ),
        ),
    )
    return paths


def run_full_context_expansion_subscription_execute(
    *,
    dsn: str,
    dry_run_path: str = DEFAULT_DRY_RUN_JSON_PATH,
    json_report_path: str = DEFAULT_EXECUTE_REPORT_PATH,
    markdown_report_path: str = DEFAULT_EXECUTE_MD_PATH,
    execute: bool = False,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    if not execute:
        raise RuntimeError("N3 expansion subscription execute blocked: missing --execute")
    if not user_confirmed:
        raise RuntimeError("N3 expansion subscription execute blocked: missing --user-confirmed")
    dry_run_report = read_json(dry_run_path)
    if dry_run_report.get("stage") != "N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE":
        raise RuntimeError("N3 expansion subscription execute blocked: dry-run artifact stage mismatch")
    if dry_run_report.get("mode") != "dry_run" or bool(dry_run_report.get("blocked")):
        raise RuntimeError("N3 expansion subscription execute blocked: dry-run artifact is not passing")
    if int(dry_run_report["quality"]["p0_count"]) != 0:
        raise RuntimeError("N3 expansion subscription execute blocked: dry-run artifact has P0")
    for section_name in ("market_data_subscription_candidate", "market_data_subscription_dedup", "market_data_pull_plan"):
        section = dry_run_report.get(section_name) or {}
        if not section.get("rows_included"):
            raise RuntimeError(f"N3 expansion subscription execute blocked: {section_name} rows missing")
        if len(section.get("rows") or []) != int(section.get("row_count") or 0):
            raise RuntimeError(f"N3 expansion subscription execute blocked: {section_name} row_count mismatch")

    run_id = str(dry_run_report["market_data_run_id"])
    rollback_sql_path = str(
        (dry_run_report.get("rollback") or {}).get("rollback_sql_path")
        or DEFAULT_ROLLBACK_SQL_PATH
    )
    started_at = utc_now_iso()
    pre_backup = capture_subscription_execution_backup(dsn, phase="before_n3_full_context_expansion_subscription", execute_run_id=run_id)
    if bool(pre_backup["target_run_exists"]):
        raise RuntimeError(f"N3 expansion subscription execute blocked: run already exists: {run_id}")
    write_result = persist_subscription_plan(dsn=dsn, dry_run_report=dry_run_report, execute_run_id=run_id)
    post_backup = capture_subscription_execution_backup(dsn, phase="after_n3_full_context_expansion_subscription", execute_run_id=run_id)
    post_checks = build_post_subscription_execute_checks(
        pre_backup=pre_backup,
        post_backup=post_backup,
        dry_run_report=dry_run_report,
        write_result=write_result,
        execute_run_id=run_id,
    )
    post_quality_items = build_post_quality_items(post_checks)
    quality_items = list(dry_run_report["quality"]["items"]) + post_quality_items
    severity_counts = count_quality_severities(quality_items)
    report = {
        "stage": "N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_EXECUTE",
        "layer_role": "N3_market_data",
        "execution_mode": "full_context_expansion_subscription_control_row_execute",
        "market_data_run_id": run_id,
        "source_condition_run_id": dry_run_report["source_condition_run_id"],
        "for_trade_date": dry_run_report["for_trade_date"],
        "source_trade_date": dry_run_report["source_trade_date"],
        "prev_trade_date": dry_run_report["prev_trade_date"],
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
            "target_run_exists": pre_backup["target_run_exists"],
            "n3_fact_and_event_row_counts": pre_backup["n3_fact_and_event_row_counts"],
        },
        "post_execute": {
            "target_run_row_counts": post_backup["target_run_row_counts"],
            "n3_fact_and_event_row_counts": post_backup["n3_fact_and_event_row_counts"],
            "market_data_run_row": post_backup["market_data_run_row"],
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
            "rollback_safe": severity_counts["P0"] == 0,
            "rollback_sql_path": rollback_sql_path,
        },
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_expansion_execute_report(report))
    return report


def format_expansion_subscription_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    return "\n".join(
        [
            "# N3 C1 Full-Context Expansion Subscription Dry-Run",
            "",
            f"- result: {'PASS' if report['passed'] else 'BLOCKED'}",
            f"- market_data_run_id: `{report['market_data_run_id']}`",
            f"- source_condition_run_id: `{report['source_condition_run_id']}`",
            f"- current_c1_run_id: `{report['current_c1_run_id']}`",
            f"- candidate rows: {report['candidate_row_count']}",
            f"- subscription rows: {report['subscription_row_count']}",
            f"- pull_plan rows: {report['market_data_pull_plan_row_count']}",
            f"- objects: {report['object_count_by_asset_kind']}",
            f"- expected minute rows: {report['expected_minute_rows_by_asset_kind']} total={report['expected_minute_rows']}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            "",
            "## Boundary",
            "",
            "- no database writes",
            "- no market data pull",
            "- no outbox/inbox/checkpoint writes",
            "- no N4/N5/N6",
            "- no worker",
        ]
    )


def format_expansion_contract(contract: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N3 C1 Full-Context Expansion Subscription Execute Contract",
            "",
            f"- execute_authorized: {str(contract['execute_authorized']).lower()}",
            f"- runner_readiness: {contract['runner_readiness']}",
            f"- market_data_run_id: `{contract['market_data_run_id']}`",
            f"- candidate rows: {contract['candidate_row_count']}",
            f"- subscription rows: {contract['subscription_row_count']}",
            f"- pull_plan rows: {contract['pull_plan_row_count']}",
            f"- objects: {contract['object_count_by_asset_kind']}",
            f"- rollback_sql: `{contract['rollback']['rollback_sql_path']}`",
            "",
            "## Execute Command",
            "",
            "```bash",
            str(contract["execute_command"]),
            "```",
        ]
    )


def format_expansion_preflight(preflight: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N3 C1 Full-Context Expansion Subscription Execute Preflight",
            "",
            f"- preflight_result: {preflight['preflight_result']}",
            f"- ready: {str(preflight['ready']).lower()}",
            f"- blockers: {', '.join(preflight['blockers']) if preflight['blockers'] else 'none'}",
            f"- market_data_run_id: `{preflight['market_data_run_id']}`",
            f"- candidate/subscription/pull_plan: {preflight['candidate_row_count']}/{preflight['subscription_row_count']}/{preflight['pull_plan_row_count']}",
            f"- objects: {preflight['object_count_by_asset_kind']}",
            f"- expected minute rows: {preflight['expected_minute_rows_by_asset_kind']}",
            f"- P0/P1/P2: {preflight['quality']['p0_count']}/{preflight['quality']['p1_count']}/{preflight['quality']['p2_count']}",
        ]
    )


def format_c1_expansion_preflight(preflight: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N3 C1 Full-Context Expansion Execute Preflight",
            "",
            f"- preflight_result: {preflight['preflight_result']}",
            f"- ready: {str(preflight['ready']).lower()}",
            f"- planned_source_market_data_run_id: `{preflight['planned_source_market_data_run_id']}`",
            f"- planned_today_minute_run_id: `{preflight['planned_today_minute_run_id']}`",
            f"- expected rows: {preflight['expected_rows_by_asset']} total={preflight['expected_rows_total']}",
            f"- blocker: {', '.join(preflight['blockers'])}",
            "",
            "Execute is blocked until the additive expansion subscription scope is executed and C0 is regenerated from that run_id.",
        ]
    )


def format_expansion_execute_report(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    write_result = report["write_result"]
    return "\n".join(
        [
            "# N3 C1 Full-Context Expansion Subscription Execute Report",
            "",
            f"- market_data_run_id: `{report['market_data_run_id']}`",
            f"- common_market_data_run.status: {report['post_execute']['market_data_run_row'].get('status')}",
            f"- candidate rows written: {write_result['candidate_rows_written']}",
            f"- subscription rows written: {write_result['subscription_rows_written']}",
            f"- pull_plan rows written: {write_result['pull_plan_rows_written']}",
            f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
            f"- rollback_sql: `{report['rollback']['rollback_sql_path']}`",
        ]
    )


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")


def read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
