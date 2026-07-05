"""N4-0 local trigger context preflight.

This module reads the active N2 condition context in a read-only transaction
and builds the plan for local N4 trigger_context_snapshot rows. It does not
write PostgreSQL rows, read market data, consume N3 events, or start workers.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import (
    PERIODS,
    count_quality_severities,
    normalize_mapping,
    period_trigger_baseline_has_required_shape,
    period_trigger_baseline_not_ready_periods,
    quality_item,
)
from ashare_v3.events.ids import canonical_json, stable_hash
from ashare_v3.events.models import N4_COMMON_PAYLOAD_KEYS, N4_EVENT_TYPES
from ashare_v3.ingestion.common import require_yyyymmdd
from ashare_v3.market.subscription_plan import STANDARD_SIGNAL_TYPES, flag_is_true, rows_section
from ashare_v3.trigger.query_audit_phase1 import audited_n4_readonly_plan_connect


ASSET_KINDS = ("stock", "index", "board")
CONDITION_RUN_READY_STATUSES = ("passed", "passed_active")
INPUT_EVENT_TYPES = (
    "MarketSnapshotUpdated",
    "MinuteBarClosed",
    "MarketDataDelayed",
    "MarketDataMissing",
)
OUTPUT_EVENT_TYPES = N4_EVENT_TYPES
TARGET_CONTEXT_TABLES = {
    "stock": "stock_trigger_context_snapshot",
    "index": "index_trigger_context_snapshot",
    "board": "board_trigger_context_snapshot",
}
TRIGGER_FACT_TABLES = (
    "common_trigger_run",
    "common_trigger_state",
    "common_trigger_match",
    "common_trigger_quality_item",
)
CONTEXT_SOURCE_TABLES = {
    "stock": {
        "basis": "stock_condition_basis",
        "pool": "stock_condition_pool",
        "scope": "stock_minute_target_scope",
        "enrichment": "stock_condition_context_enrichment",
    },
    "index": {
        "basis": "index_condition_basis",
        "pool": "index_condition_pool",
        "scope": "index_minute_target_scope",
        "enrichment": "index_condition_context_enrichment",
    },
    "board": {
        "basis": "board_condition_basis",
        "pool": "board_condition_pool",
        "scope": "board_minute_target_scope",
        "enrichment": "board_condition_context_enrichment",
    },
}
DEFAULT_N4_CONTEXT_PREFLIGHT_JSON_PATH = "docs/N4_0_trigger_context_preflight.json"
ATOMIC_RULE_VERSION = "atomic_rule_v1"
ATOMIC_RULE_SPEC_PATH = "docs/N4_TRIGGER_RULE_SPEC_ATOMIC_REVISED.md"
CONTEXT_CONTRACT_VERSION = "n4_trigger_context_snapshot.atomic_rule_v1"
HINT_CONDITION_KEYS = {"BUY_HINT", "SELL_HINT"}
FULL_CONDITION_KEYS = {"BUY:FULL", "SELL:FULL"}


def build_trigger_context_preflight_dry_run(
    *,
    dsn: str,
    run_id: str | None = None,
    source_trade_date: str | None = None,
    for_trade_date: str | None = None,
    include_rows: bool = True,
) -> dict[str, Any]:
    """Read active N2 rows and build the N4 local context dry-run report."""

    if source_trade_date:
        source_trade_date = require_yyyymmdd(source_trade_date, "source_trade_date")
    if for_trade_date:
        for_trade_date = require_yyyymmdd(for_trade_date, "for_trade_date")

    with audited_n4_readonly_plan_connect(
        dsn,
        stage_id="n4_context_preflight",
        source_run_id=run_id,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        active_runs = fetch_condition_run_candidates(
            cur,
            run_id=run_id,
            source_trade_date=source_trade_date,
            for_trade_date=for_trade_date,
        )
        active_run, active_quality = select_active_condition_run(active_runs, requested_run_id=run_id)
        if active_run is None:
            return build_blocked_report(active_quality, active_runs, include_rows=include_rows)

        table_status = fetch_context_table_status(cur)
        materialization_run_id = build_context_materialization_run_id(active_run)
        context_rows_by_asset = {
            asset_kind: fetch_context_rows(
                cur,
                asset_kind,
                str(active_run["run_id"]),
                materialization_run_id=materialization_run_id,
                for_trade_date=str(active_run.get("for_trade_date") or ""),
            )
            for asset_kind in ASSET_KINDS
        }

    return build_trigger_context_preflight_plan(
        active_run=active_run,
        context_rows_by_asset=context_rows_by_asset,
        preflight_quality_items=active_quality,
        table_status=table_status,
        include_rows=include_rows,
    )


def fetch_condition_run_candidates(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    run_id: str | None,
    source_trade_date: str | None,
    for_trade_date: str | None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if run_id:
        where.append("run_id = %s")
        params.append(run_id)
    else:
        where.append("status = ANY(%s)")
        params.append(list(CONDITION_RUN_READY_STATUSES))
    if source_trade_date:
        where.append("source_trade_date = %s")
        params.append(source_trade_date)
    if for_trade_date:
        where.append("for_trade_date = %s")
        params.append(for_trade_date)

    cur.execute(
        f"""
        SELECT run_id, source_trade_date, for_trade_date, prev_trade_date,
               status, p0_count, p1_count, p2_count, source_versions,
               raw_json, started_at, finished_at, created_at
        FROM common_condition_run
        WHERE {' AND '.join(where)}
        ORDER BY finished_at DESC NULLS LAST, created_at DESC, run_id DESC
        """,
        params,
    )
    return [normalize_mapping(row) for row in cur.fetchall()]


def select_active_condition_run(
    active_runs: Sequence[Mapping[str, Any]],
    *,
    requested_run_id: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    quality_items: list[dict[str, Any]] = []
    expected = "exactly one passed active condition run"
    if requested_run_id:
        expected = f"condition run {requested_run_id} exists and is passed"

    quality_items.append(
        quality_item(
            "P0",
            "passed" if len(active_runs) == 1 else "failed",
            "active_condition_run_unique",
            "N4-0 must start from exactly one active condition run",
            expected=expected,
            actual=str(len(active_runs)),
            details={"run_ids": [row.get("run_id") for row in active_runs[:10]]},
        )
    )
    if len(active_runs) != 1:
        return None, quality_items

    active_run = normalize_mapping(active_runs[0])
    status = str(active_run.get("status") or "")
    p0_count = int(active_run.get("p0_count") or 0)
    source_trade_date = str(active_run.get("source_trade_date") or "")
    prev_trade_date = str(active_run.get("prev_trade_date") or "")
    quality_items.extend(
        [
            quality_item(
                "P0",
                "passed" if status in CONDITION_RUN_READY_STATUSES else "failed",
                "active_condition_run_status_passed",
                "active condition run must be passed before N4 localization",
                expected="/".join(CONDITION_RUN_READY_STATUSES),
                actual=status,
            ),
            quality_item(
                "P0",
                "passed" if p0_count == 0 else "failed",
                "active_condition_run_p0_clean",
                "active condition run P0 count must be zero before N4 localization",
                expected="0",
                actual=str(p0_count),
            ),
            quality_item(
                "P0",
                "passed" if source_trade_date == prev_trade_date else "failed",
                "active_condition_run_prev_trade_date_contract",
                "source_trade_date must equal prev_trade_date for N2/N4 handoff",
                expected=source_trade_date,
                actual=prev_trade_date,
            ),
        ]
    )
    if count_quality_severities(quality_items)["P0"] > 0:
        return None, quality_items
    return active_run, quality_items


def fetch_context_table_status(cur: psycopg.Cursor[dict[str, Any]]) -> dict[str, bool]:
    table_names = ["common_condition_run"]
    for tables in CONTEXT_SOURCE_TABLES.values():
        table_names.extend(tables.values())
    status: dict[str, bool] = {}
    for table_name in table_names:
        cur.execute("SELECT to_regclass(%s) AS regclass", (f"public.{table_name}",))
        status[table_name] = cur.fetchone()["regclass"] is not None
    return status


def fetch_context_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    asset_kind: str,
    condition_run_id: str,
    *,
    materialization_run_id: str | None = None,
    for_trade_date: str | None = None,
) -> list[dict[str, Any]]:
    materialization_run_id = materialization_run_id or ""
    for_trade_date = for_trade_date or ""
    if asset_kind == "stock":
        query = """
            SELECT s.stock_minute_target_scope_id AS source_minute_target_scope_id,
                   s.source_condition_pool_id AS source_condition_pool_id,
                   p.source_condition_basis_id AS source_condition_basis_id,
                   'stock_minute_target_scope' AS source_scope_table,
                   'stock_condition_pool' AS source_pool_table,
                   'stock_condition_basis' AS source_basis_table,
                   s.run_id AS source_condition_run_id,
                   s.for_trade_date, s.source_trade_date, s.prev_trade_date,
                   'stock' AS asset_kind,
                   s.stock_identity_key AS identity_key,
                   s.exchange, s.code, s.code AS display_code, s.name,
                   s.lane, p.monitor_type,
                   s.direction, s.condition_key, s.condition_periods,
                   s.allowed_signal_types, s.is_hint_scope, s.scope_source,
                   s.scope_status, p.active_target, p.quality_status AS pool_quality_status,
                   b.quality_status AS basis_quality_status,
                   b.amount_quality_status,
                   b.prev_up_str, b.prev_dn_str,
                   b.period_transition_y, b.period_transition_q,
                   b.period_transition_m, b.period_transition_w, b.period_transition_d,
                   b.amount_year AS amount_y, b.amount_quarter AS amount_q,
                   b.amount_month AS amount_m, b.amount_week AS amount_w,
                   b.amount_day AS amount_d,
                   b.amount_prev_year AS previous_amount_y,
                   b.amount_prev_quarter AS previous_amount_q,
                   b.amount_prev_month AS previous_amount_m,
                   b.amount_prev_week AS previous_amount_w,
                   b.amount_prev_day AS previous_amount_d,
                   b.main_up_anchor, b.up_reference_period, b.up_amplitude,
                   b.buy_target_price,
                   b.main_down_anchor, b.down_reference_period, b.down_amplitude,
                   b.sell_target_price, b.clear_sell_ref_period,
                   COALESCE(e.period_trigger_baseline_json, s.period_trigger_baseline_json, p.period_trigger_baseline_json, b.period_trigger_baseline_json)
                     AS period_trigger_baseline_json,
                   e.materialization_run_id AS context_enrichment_materialization_run_id,
                   e.context_enrichment_version,
                   e.context_enrichment_hash,
                   e.trigger_amount_chain_baseline_json,
                   e.trigger_amount_chain_formula_hash,
                   e.full_prerequisite_trace_json,
                   e.full_prerequisite_quality_status,
                   e.hint_prerequisite_trace_json,
                   e.hint_prerequisite_quality_status,
                   e.period_baseline_ready_json,
                   e.payload_json AS context_enrichment_payload_json,
                   s.daily_snapshot_required, s.minute_required,
                   s.previous_day_minute_required, s.previous_day_minute_date,
                   s.previous_day_minute_quality_required, s.minute_scope_reason,
                   p.policy_name, p.policy_hash, p.selected_reason,
                   NULL::BIGINT AS source_market_subscription_id
            FROM stock_minute_target_scope s
            LEFT JOIN stock_condition_pool p
              ON p.stock_condition_pool_id = s.source_condition_pool_id
            LEFT JOIN stock_condition_basis b
              ON b.stock_condition_basis_id = p.source_condition_basis_id
            LEFT JOIN stock_condition_context_enrichment e
              ON e.materialization_run_id = %s
             AND e.source_condition_run_id = s.run_id
             AND e.for_trade_date = s.for_trade_date
             AND e.source_minute_target_scope_id = s.stock_minute_target_scope_id
             AND e.stock_identity_key = s.stock_identity_key
             AND e.condition_key = s.condition_key
             AND e.direction = s.direction
            WHERE s.run_id = %s
              AND (%s = '' OR s.for_trade_date = %s)
            ORDER BY s.stock_identity_key, s.direction, s.condition_key, s.stock_minute_target_scope_id
        """
    elif asset_kind == "index":
        query = """
            SELECT s.index_minute_target_scope_id AS source_minute_target_scope_id,
                   s.source_condition_pool_id AS source_condition_pool_id,
                   p.source_condition_basis_id AS source_condition_basis_id,
                   'index_minute_target_scope' AS source_scope_table,
                   'index_condition_pool' AS source_pool_table,
                   'index_condition_basis' AS source_basis_table,
                   s.run_id AS source_condition_run_id,
                   s.for_trade_date, s.source_trade_date, s.prev_trade_date,
                   'index' AS asset_kind,
                   s.index_identity_key AS identity_key,
                   s.exchange, s.code, s.code AS display_code, s.name,
                   s.lane, p.monitor_type,
                   s.direction, s.condition_key, s.condition_periods,
                   s.allowed_signal_types, s.is_hint_scope, s.scope_source,
                   s.scope_status, p.active_target, p.quality_status AS pool_quality_status,
                   b.quality_status AS basis_quality_status,
                   b.amount_quality_status,
                   b.prev_up_str, b.prev_dn_str,
                   b.period_transition_y, b.period_transition_q,
                   b.period_transition_m, b.period_transition_w, b.period_transition_d,
                   b.amount_year AS amount_y, b.amount_quarter AS amount_q,
                   b.amount_month AS amount_m, b.amount_week AS amount_w,
                   b.amount_day AS amount_d,
                   b.amount_prev_year AS previous_amount_y,
                   b.amount_prev_quarter AS previous_amount_q,
                   b.amount_prev_month AS previous_amount_m,
                   b.amount_prev_week AS previous_amount_w,
                   b.amount_prev_day AS previous_amount_d,
                   b.main_up_anchor, b.up_reference_period, b.up_amplitude,
                   b.buy_target_price,
                   b.main_down_anchor, b.down_reference_period, b.down_amplitude,
                   b.sell_target_price, b.clear_sell_ref_period,
                   COALESCE(e.period_trigger_baseline_json, s.period_trigger_baseline_json, p.period_trigger_baseline_json, b.period_trigger_baseline_json)
                     AS period_trigger_baseline_json,
                   e.materialization_run_id AS context_enrichment_materialization_run_id,
                   e.context_enrichment_version,
                   e.context_enrichment_hash,
                   e.trigger_amount_chain_baseline_json,
                   e.trigger_amount_chain_formula_hash,
                   e.full_prerequisite_trace_json,
                   e.full_prerequisite_quality_status,
                   e.hint_prerequisite_trace_json,
                   e.hint_prerequisite_quality_status,
                   e.period_baseline_ready_json,
                   e.payload_json AS context_enrichment_payload_json,
                   s.daily_snapshot_required, s.minute_required,
                   s.previous_day_minute_required, s.previous_day_minute_date,
                   s.previous_day_minute_quality_required, s.minute_scope_reason,
                   p.policy_name, p.policy_hash, p.selected_reason,
                   NULL::BIGINT AS source_market_subscription_id
            FROM index_minute_target_scope s
            LEFT JOIN index_condition_pool p
              ON p.index_condition_pool_id = s.source_condition_pool_id
            LEFT JOIN index_condition_basis b
              ON b.index_condition_basis_id = p.source_condition_basis_id
            LEFT JOIN index_condition_context_enrichment e
              ON e.materialization_run_id = %s
             AND e.source_condition_run_id = s.run_id
             AND e.for_trade_date = s.for_trade_date
             AND e.source_minute_target_scope_id = s.index_minute_target_scope_id
             AND e.index_identity_key = s.index_identity_key
             AND e.condition_key = s.condition_key
             AND e.direction = s.direction
            WHERE s.run_id = %s
              AND (%s = '' OR s.for_trade_date = %s)
            ORDER BY s.index_identity_key, s.direction, s.condition_key, s.index_minute_target_scope_id
        """
    elif asset_kind == "board":
        query = """
            SELECT s.board_minute_target_scope_id AS source_minute_target_scope_id,
                   s.source_condition_pool_id AS source_condition_pool_id,
                   p.source_condition_basis_id AS source_condition_basis_id,
                   'board_minute_target_scope' AS source_scope_table,
                   'board_condition_pool' AS source_pool_table,
                   'board_condition_basis' AS source_basis_table,
                   s.run_id AS source_condition_run_id,
                   s.for_trade_date, s.source_trade_date, s.prev_trade_date,
                   'board' AS asset_kind,
                   s.board_identity_key AS identity_key,
                   'TDX' AS exchange, s.board_code AS code, s.board_code AS display_code, s.board_name AS name,
                   s.lane, p.monitor_type,
                   s.direction, s.condition_key, s.condition_periods,
                   s.allowed_signal_types, s.is_hint_scope, s.scope_source,
                   s.scope_status, p.active_target, p.quality_status AS pool_quality_status,
                   b.quality_status AS basis_quality_status,
                   b.amount_quality_status,
                   b.prev_up_str, b.prev_dn_str,
                   b.period_transition_y, b.period_transition_q,
                   b.period_transition_m, b.period_transition_w, b.period_transition_d,
                   b.amount_year AS amount_y, b.amount_quarter AS amount_q,
                   b.amount_month AS amount_m, b.amount_week AS amount_w,
                   b.amount_day AS amount_d,
                   b.amount_prev_year AS previous_amount_y,
                   b.amount_prev_quarter AS previous_amount_q,
                   b.amount_prev_month AS previous_amount_m,
                   b.amount_prev_week AS previous_amount_w,
                   b.amount_prev_day AS previous_amount_d,
                   b.main_up_anchor, b.up_reference_period, b.up_amplitude,
                   b.buy_target_price,
                   b.main_down_anchor, b.down_reference_period, b.down_amplitude,
                   b.sell_target_price, b.clear_sell_ref_period,
                   COALESCE(e.period_trigger_baseline_json, s.period_trigger_baseline_json, p.period_trigger_baseline_json, b.period_trigger_baseline_json)
                     AS period_trigger_baseline_json,
                   e.materialization_run_id AS context_enrichment_materialization_run_id,
                   e.context_enrichment_version,
                   e.context_enrichment_hash,
                   e.trigger_amount_chain_baseline_json,
                   e.trigger_amount_chain_formula_hash,
                   e.full_prerequisite_trace_json,
                   e.full_prerequisite_quality_status,
                   e.hint_prerequisite_trace_json,
                   e.hint_prerequisite_quality_status,
                   e.period_baseline_ready_json,
                   e.payload_json AS context_enrichment_payload_json,
                   s.daily_snapshot_required, s.minute_required,
                   s.previous_day_minute_required, s.previous_day_minute_date,
                   s.previous_day_minute_quality_required, s.minute_scope_reason,
                   p.policy_name, p.policy_hash, p.selected_reason,
                   NULL::BIGINT AS source_market_subscription_id
            FROM board_minute_target_scope s
            LEFT JOIN board_condition_pool p
              ON p.board_condition_pool_id = s.source_condition_pool_id
            LEFT JOIN board_condition_basis b
              ON b.board_condition_basis_id = p.source_condition_basis_id
            LEFT JOIN board_condition_context_enrichment e
              ON e.materialization_run_id = %s
             AND e.source_condition_run_id = s.run_id
             AND e.for_trade_date = s.for_trade_date
             AND e.source_minute_target_scope_id = s.board_minute_target_scope_id
             AND e.board_identity_key = s.board_identity_key
             AND e.condition_key = s.condition_key
             AND e.direction = s.direction
            WHERE s.run_id = %s
              AND (%s = '' OR s.for_trade_date = %s)
            ORDER BY s.board_identity_key, s.direction, s.condition_key, s.board_minute_target_scope_id
        """
    else:
        raise ValueError(f"unsupported asset_kind: {asset_kind}")

    cur.execute(query, (materialization_run_id, condition_run_id, for_trade_date, for_trade_date))
    return [normalize_context_row(row) for row in cur.fetchall()]


def normalize_context_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    enrichment_baseline = output.pop("enrichment_period_trigger_baseline_json", None)
    if enrichment_baseline not in (None, ""):
        output["period_trigger_baseline_json"] = enrichment_baseline
    for key in (
        "source_minute_target_scope_id",
        "source_condition_pool_id",
        "source_condition_basis_id",
        "source_market_subscription_id",
    ):
        output[key] = int(output[key]) if output.get(key) not in (None, "") else None
    output["condition_periods"] = normalize_text_array(output.get("condition_periods"))
    output["allowed_signal_types"] = normalize_text_array(output.get("allowed_signal_types"))
    output["selected_reason"] = normalize_text_array(output.get("selected_reason"))
    output["context_hash"] = build_context_hash(output)
    return output


def build_context_materialization_run_id(active_run: Mapping[str, Any]) -> str:
    return build_atomic_context_run_id(
        for_trade_date=str(active_run["for_trade_date"]),
        condition_run_id=str(active_run["run_id"]),
    )


def build_atomic_context_run_id(*, for_trade_date: str, condition_run_id: str) -> str:
    return f"trigger_context_snapshot_{for_trade_date}_{condition_run_id}__{ATOMIC_RULE_VERSION}"


def normalize_text_array(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item) for item in value]


def build_context_hash(row: Mapping[str, Any]) -> str:
    payload = {
        "source_condition_run_id": row.get("source_condition_run_id"),
        "source_condition_pool_id": row.get("source_condition_pool_id"),
        "source_condition_basis_id": row.get("source_condition_basis_id"),
        "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        "asset_kind": row.get("asset_kind"),
        "identity_key": row.get("identity_key"),
        "direction": row.get("direction"),
        "condition_key": row.get("condition_key"),
        "allowed_signal_types": row.get("allowed_signal_types") or [],
        "buy_target_price": row.get("buy_target_price"),
        "sell_target_price": row.get("sell_target_price"),
        "clear_sell_ref_period": row.get("clear_sell_ref_period"),
        "period_trigger_baseline_json": row.get("period_trigger_baseline_json") or {},
        "policy_hash": row.get("policy_hash"),
    }
    return stable_hash(canonical_json(payload), length=40)


def build_trigger_context_preflight_plan(
    *,
    active_run: Mapping[str, Any],
    context_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]],
    preflight_quality_items: Sequence[Mapping[str, Any]] | None = None,
    table_status: Mapping[str, bool] | None = None,
    include_rows: bool = True,
) -> dict[str, Any]:
    active_run = normalize_mapping(active_run)
    trigger_run_id = f"trigger_context_preflight_{active_run['for_trade_date']}_{active_run['run_id']}_dry_run"
    rows = flatten_context_rows(context_rows_by_asset)
    quality_items = list(preflight_quality_items or [])
    effective_table_status = table_status if table_status is not None else {
        table: True
        for tables in CONTEXT_SOURCE_TABLES.values()
        for table in tables.values()
    }
    if "common_condition_run" not in effective_table_status:
        effective_table_status = {"common_condition_run": True, **dict(effective_table_status)}
    quality_items.extend(build_table_status_quality(effective_table_status))
    quality_items.extend(build_context_quality_items(active_run=active_run, context_rows=rows))
    severity_counts = count_quality_severities(quality_items)
    object_keys = {(row.get("asset_kind"), row.get("identity_key")) for row in rows}
    report = {
        "stage": "N4-0",
        "layer_role": "N4_trigger",
        "plan_mode": "n2_to_n4_local_context_preflight",
        "mode": "dry_run",
        "trigger_run_id": trigger_run_id,
        "source_condition_run_id": active_run.get("run_id"),
        "source_trade_date": active_run.get("source_trade_date"),
        "for_trade_date": active_run.get("for_trade_date"),
        "prev_trade_date": active_run.get("prev_trade_date"),
        "active_condition_run": summarize_active_run(active_run),
        "target_context_tables": dict(TARGET_CONTEXT_TABLES),
        "target_trigger_fact_tables": list(TRIGGER_FACT_TABLES),
        "source_context_tables": CONTEXT_SOURCE_TABLES,
        "candidate_context_row_count": len(rows),
        "condition_row_count": len(rows),
        "condition_row_count_by_asset_kind": count_by_asset(rows),
        "object_count": len(object_keys),
        "object_count_by_asset_kind": object_count_by_asset_kind(rows),
        "direction_distribution": dict(sorted(Counter(str(row.get("direction") or "") for row in rows).items())),
        "condition_key_counts": dict(sorted(Counter(str(row.get("condition_key") or "") for row in rows).items())),
        "hint_condition_row_count": count_hint_rows(rows),
        "buy_hint_row_count": sum(1 for row in rows if row.get("condition_key") == "BUY_HINT"),
        "sell_hint_row_count": sum(1 for row in rows if row.get("condition_key") == "SELL_HINT"),
        "allowed_signal_type_counts": allowed_signal_type_counts(rows),
        "trigger_candidate_count_by_signal_type": trigger_candidate_count_by_signal_type(rows),
        "period_trigger_baseline_json_missing": period_trigger_baseline_json_missing_count(rows),
        "trigger_baseline_semantic_missing": trigger_baseline_semantic_missing_count(
            rows,
            expected_source_trade_date=str(active_run.get("source_trade_date") or ""),
        ),
        "trigger_baseline_source_trade_date_mismatch": trigger_baseline_source_trade_date_mismatch_count(
            rows,
            expected_source_trade_date=str(active_run.get("source_trade_date") or ""),
        ),
        "trigger_baseline_legacy_previous_usage_rows": trigger_baseline_legacy_previous_usage_count(
            rows,
            expected_source_trade_date=str(active_run.get("source_trade_date") or ""),
        ),
        "required_period_not_ready_rows": required_period_not_ready_rows_count(rows),
        "input_event_contract": build_input_event_contract(),
        "output_event_contract": build_output_event_contract(),
        "localization_contract": build_localization_contract(),
        "trigger_context_snapshot_dry_run_plan": rows_section(rows, include_rows=include_rows),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "blocked": severity_counts["P0"] > 0,
        "passed": severity_counts["P0"] == 0,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "trigger_context_snapshot_written": False,
            "trigger_state_written": False,
            "trigger_match_written": False,
            "event_outbox_written": False,
            "market_data_pulled": False,
            "n3_event_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
            "external_n2_runtime_path_accessed": False,
        },
    }
    return report


def flatten_context_rows(context_rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for asset_kind in ASSET_KINDS:
        rows.extend(normalize_context_row_like(row) for row in context_rows_by_asset.get(asset_kind, []))
    return rows


def normalize_context_row_like(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["condition_periods"] = normalize_text_array(output.get("condition_periods"))
    output["allowed_signal_types"] = normalize_text_array(output.get("allowed_signal_types"))
    output["selected_reason"] = normalize_text_array(output.get("selected_reason"))
    output["context_hash"] = str(output.get("context_hash") or build_context_hash(output))
    return output


def build_table_status_quality(table_status: Mapping[str, bool]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    required_tables = ["common_condition_run"]
    for asset_kind in ASSET_KINDS:
        required_tables.extend(CONTEXT_SOURCE_TABLES[asset_kind].values())
    for table_name in required_tables:
        exists = bool(table_status.get(table_name))
        items.append(
            quality_item(
                "P0",
                "passed" if exists else "failed",
                f"{table_name}_exists",
                f"{table_name} must exist for N4-0 local context preflight",
                expected="exists",
                actual="exists" if exists else "missing",
            )
        )
    return items


def build_context_quality_items(
    *,
    active_run: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.append(
        quality_item(
            "P0",
            "passed" if context_rows else "failed",
            "trigger_context_candidates_available",
            "N4-0 must localize non-empty condition context candidates",
            expected=">0 rows",
            actual=str(len(context_rows)),
        )
    )
    wrong_run_rows = [
        row for row in context_rows if row.get("source_condition_run_id") != active_run.get("run_id")
    ]
    missing_scope_links = [row for row in context_rows if row.get("source_minute_target_scope_id") in (None, "")]
    missing_pool_links = [row for row in context_rows if row.get("source_condition_pool_id") in (None, "")]
    missing_basis_links = [row for row in context_rows if row.get("source_condition_basis_id") in (None, "")]
    non_pool_scope_rows = [
        row for row in context_rows if str(row.get("scope_source") or "") != "condition_pool"
    ]
    invalid_signal_types = sorted(
        {
            signal_type
            for row in context_rows
            for signal_type in normalize_text_array(row.get("allowed_signal_types"))
            if signal_type not in STANDARD_SIGNAL_TYPES
        }
    )
    invalid_directions = [
        row for row in context_rows if row.get("direction") not in {"buy", "sell"}
    ]
    buy_hint_wrong_direction = [
        row for row in context_rows if row.get("condition_key") == "BUY_HINT" and row.get("direction") != "buy"
    ]
    sell_hint_wrong_direction = [
        row for row in context_rows if row.get("condition_key") == "SELL_HINT" and row.get("direction") != "sell"
    ]
    hint_rows = [row for row in context_rows if row.get("condition_key") in {"BUY_HINT", "SELL_HINT"}]
    hint_rows_without_signal = [
        row
        for row in hint_rows
        if row.get("condition_key") not in normalize_text_array(row.get("allowed_signal_types"))
    ]
    missing_period_trigger_baseline_rows = [
        row for row in context_rows if not period_trigger_baseline_has_required_shape(row.get("period_trigger_baseline_json"))
    ]
    trigger_baseline_semantic_missing_rows = [
        {
            "identity_key": str(row.get("identity_key") or ""),
            "condition_key": str(row.get("condition_key") or ""),
            "missing_periods": missing_n4_trigger_baseline_periods(
                row,
                expected_source_trade_date=str(active_run.get("source_trade_date") or ""),
            ),
        }
        for row in context_rows
        if missing_n4_trigger_baseline_periods(
            row,
            expected_source_trade_date=str(active_run.get("source_trade_date") or ""),
        )
    ]
    trigger_baseline_source_mismatch_rows = [
        {
            "identity_key": str(row.get("identity_key") or ""),
            "condition_key": str(row.get("condition_key") or ""),
            "mismatch_periods": trigger_baseline_source_trade_date_mismatch_periods(
                row,
                expected_source_trade_date=str(active_run.get("source_trade_date") or ""),
            ),
        }
        for row in context_rows
        if trigger_baseline_source_trade_date_mismatch_periods(
            row,
            expected_source_trade_date=str(active_run.get("source_trade_date") or ""),
        )
    ]
    trigger_baseline_legacy_usage_rows = [
        {
            "identity_key": str(row.get("identity_key") or ""),
            "condition_key": str(row.get("condition_key") or ""),
            "legacy_periods": trigger_baseline_legacy_previous_usage_periods(
                row,
                expected_source_trade_date=str(active_run.get("source_trade_date") or ""),
            ),
        }
        for row in context_rows
        if trigger_baseline_legacy_previous_usage_periods(
            row,
            expected_source_trade_date=str(active_run.get("source_trade_date") or ""),
        )
    ]
    required_period_not_ready_rows = [
        {
            "identity_key": str(row.get("identity_key") or ""),
            "condition_key": str(row.get("condition_key") or ""),
            "missing_periods": missing_required_period_trigger_baseline_periods(row),
        }
        for row in context_rows
        if missing_required_period_trigger_baseline_periods(row)
    ]
    items.extend(
        [
            quality_item(
                "P0",
                "passed" if not wrong_run_rows else "failed",
                "context_source_run_id_match",
                "all N4 context candidates must come from the active condition run",
                expected=str(active_run.get("run_id")),
                actual="matched" if not wrong_run_rows else sample_context_refs(wrong_run_rows),
            ),
            quality_item(
                "P0",
                "passed" if not missing_scope_links else "failed",
                "context_source_scope_link_present",
                "N4 context must preserve source minute_target_scope id",
                expected="source_minute_target_scope_id present",
                actual="present" if not missing_scope_links else sample_context_refs(missing_scope_links),
            ),
            quality_item(
                "P0",
                "passed" if not missing_pool_links else "failed",
                "context_source_condition_pool_link_present",
                "N4 context must preserve source condition_pool id",
                expected="source_condition_pool_id present",
                actual="present" if not missing_pool_links else sample_context_refs(missing_pool_links),
            ),
            quality_item(
                "P0",
                "passed" if not missing_basis_links else "failed",
                "context_source_condition_basis_link_present",
                "N4 context must preserve source condition_basis id",
                expected="source_condition_basis_id present",
                actual="present" if not missing_basis_links else sample_context_refs(missing_basis_links),
            ),
            quality_item(
                "P0",
                "passed" if not non_pool_scope_rows else "failed",
                "context_scope_source_condition_pool_only",
                "N4 context must be generated from condition_pool-backed scope rows",
                expected="condition_pool",
                actual="condition_pool" if not non_pool_scope_rows else sample_context_refs(non_pool_scope_rows),
            ),
            quality_item(
                "P0",
                "passed" if not invalid_signal_types else "failed",
                "context_allowed_signal_types_whitelist",
                "N4 context allowed_signal_types must stay in the v3 standard signal whitelist",
                expected=",".join(STANDARD_SIGNAL_TYPES),
                actual="whitelist_only" if not invalid_signal_types else ",".join(invalid_signal_types),
            ),
            quality_item(
                "P0",
                "passed" if not invalid_directions else "failed",
                "context_direction_buy_sell_only",
                "N4 direction can only be buy or sell",
                expected="buy,sell",
                actual="buy,sell" if not invalid_directions else sample_context_refs(invalid_directions),
            ),
            quality_item(
                "P0",
                "passed" if not buy_hint_wrong_direction else "failed",
                "buy_hint_direction_buy",
                "BUY_HINT must enter N4 as a buy trigger candidate",
                expected="direction=buy",
                actual="direction=buy" if not buy_hint_wrong_direction else sample_context_refs(buy_hint_wrong_direction),
            ),
            quality_item(
                "P0",
                "passed" if not sell_hint_wrong_direction else "failed",
                "sell_hint_direction_sell",
                "SELL_HINT must enter N4 as a sell trigger candidate",
                expected="direction=sell",
                actual="direction=sell" if not sell_hint_wrong_direction else sample_context_refs(sell_hint_wrong_direction),
            ),
            quality_item(
                "P0",
                "passed" if not hint_rows_without_signal else "failed",
                "hint_condition_keys_preserved_as_trigger_candidates",
                "BUY_HINT and SELL_HINT rows must remain N4 standard trigger candidates",
                expected="hint condition_key included in allowed_signal_types",
                actual="preserved" if not hint_rows_without_signal else sample_context_refs(hint_rows_without_signal),
            ),
            quality_item(
                "P0",
                "passed" if not missing_period_trigger_baseline_rows else "failed",
                "period_trigger_baseline_json_localization_input_present",
                "N4-R4 context candidates must carry N2 period_trigger_baseline_json for local trigger use",
                expected="missing=0",
                actual="0" if not missing_period_trigger_baseline_rows else str(len(missing_period_trigger_baseline_rows)),
                details={"missing_samples": sample_context_refs(missing_period_trigger_baseline_rows).split(",") if missing_period_trigger_baseline_rows else []},
            ),
            quality_item(
                "P0",
                "passed" if not trigger_baseline_semantic_missing_rows else "failed",
                "trigger_baseline_semantic_fields_present",
                "N4 context must use N2 trigger_previous_* fields rather than legacy previous_* fields",
                expected="trigger_previous_entity_high/low and trigger_previous_amount_baseline present",
                actual="present" if not trigger_baseline_semantic_missing_rows else str(len(trigger_baseline_semantic_missing_rows)),
                details={"missing_samples": trigger_baseline_semantic_missing_rows[:20]},
            ),
            quality_item(
                "P0",
                "passed" if not trigger_baseline_source_mismatch_rows else "failed",
                "trigger_baseline_source_trade_date_match",
                "N4 trigger baseline source date must equal the active N2 source_trade_date",
                expected=str(active_run.get("source_trade_date") or ""),
                actual="matched" if not trigger_baseline_source_mismatch_rows else str(len(trigger_baseline_source_mismatch_rows)),
                details={"mismatch_samples": trigger_baseline_source_mismatch_rows[:20]},
            ),
            quality_item(
                "P0",
                "passed" if not trigger_baseline_legacy_usage_rows else "failed",
                "trigger_baseline_not_from_current_seed",
                "N4 trigger baseline must use previous complete period entity high/low; current seed is trace only",
                expected="trigger_previous_entity_high/low equals previous_entity_high/low",
                actual="trigger_fields" if not trigger_baseline_legacy_usage_rows else str(len(trigger_baseline_legacy_usage_rows)),
                details={"current_seed_or_mismatch_samples": trigger_baseline_legacy_usage_rows[:20]},
            ),
            quality_item(
                "P0",
                "passed" if not trigger_baseline_semantic_missing_rows and not trigger_baseline_legacy_usage_rows else "failed",
                "n4_context_uses_trigger_baseline_fields",
                "N4 local context must read trigger_previous_* as the trigger baseline contract",
                expected="trigger_previous_*",
                actual="trigger_previous_*" if not trigger_baseline_semantic_missing_rows and not trigger_baseline_legacy_usage_rows else "current_seed_or_missing",
            ),
            quality_item(
                "P0",
                "passed" if not required_period_not_ready_rows else "failed",
                "period_trigger_baseline_required_periods_ready",
                "N4-R4 context rows must not require periods whose frozen trigger baseline is not ready",
                expected="required_period_not_ready_rows=0",
                actual="0" if not required_period_not_ready_rows else str(len(required_period_not_ready_rows)),
                details={"not_ready_samples": required_period_not_ready_rows[:20]},
            ),
            quality_item("P0", "passed", "n4_no_market_data_pull", "N4-0 does not pull market data or minute bars"),
            quality_item("P0", "passed", "n4_no_n3_event_consumption", "N4-0 does not consume real N3 events"),
            quality_item("P0", "passed", "n4_no_downstream_layer_write", "N4-0 does not write downstream action/user/voice/sim tables"),
            quality_item("P0", "passed", "n4_no_worker_started", "N4-0 does not start workers or long-running services"),
            quality_item("P0", "passed", "n4_no_external_n2_runtime_path", "N4-0 reads N2 through PostgreSQL only and does not use an external runtime path"),
            quality_item("P0", "passed", "n4_no_runtime_table_names", "N4 formal table names do not use *_runtime"),
        ]
    )
    return items


def count_by_asset(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        asset_kind: sum(1 for row in rows if row.get("asset_kind") == asset_kind)
        for asset_kind in ASSET_KINDS
    }


def object_count_by_asset_kind(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    grouped: dict[str, set[str]] = {asset_kind: set() for asset_kind in ASSET_KINDS}
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        identity_key = str(row.get("identity_key") or "")
        if asset_kind in grouped and identity_key:
            grouped[asset_kind].add(identity_key)
    return {asset_kind: len(grouped[asset_kind]) for asset_kind in ASSET_KINDS}


def count_hint_rows(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in rows if row.get("condition_key") in {"BUY_HINT", "SELL_HINT"})


def allowed_signal_type_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(
        signal_type
        for row in rows
        for signal_type in normalize_text_array(row.get("allowed_signal_types"))
    )
    return dict(sorted(counts.items()))


def trigger_candidate_count_by_signal_type(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for row in rows:
        for signal_type in normalize_text_array(row.get("allowed_signal_types")):
            counts[signal_type] += 1
    return dict(sorted(counts.items()))


def period_trigger_baseline_json_missing_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        1
        for row in rows
        if not period_trigger_baseline_has_required_shape(row.get("period_trigger_baseline_json"))
    )


def required_period_not_ready_rows_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for row in rows if missing_required_period_trigger_baseline_periods(row))


def missing_required_period_trigger_baseline_periods(row: Mapping[str, Any]) -> list[str]:
    required_periods = required_periods_for_condition_key(str(row.get("condition_key") or ""))
    return [
        period
        for period in required_periods
        if not n4_trigger_baseline_period_ready(
            row.get("period_trigger_baseline_json"),
            period,
            expected_source_trade_date=str(row.get("source_trade_date") or ""),
        )
    ]


def trigger_baseline_semantic_missing_count(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_source_trade_date: str,
) -> int:
    return sum(
        1
        for row in rows
        if missing_n4_trigger_baseline_periods(row, expected_source_trade_date=expected_source_trade_date)
    )


def trigger_baseline_source_trade_date_mismatch_count(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_source_trade_date: str,
) -> int:
    return sum(
        1
        for row in rows
        if trigger_baseline_source_trade_date_mismatch_periods(row, expected_source_trade_date=expected_source_trade_date)
    )


def trigger_baseline_legacy_previous_usage_count(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_source_trade_date: str,
) -> int:
    return sum(
        1
        for row in rows
        if trigger_baseline_legacy_previous_usage_periods(row, expected_source_trade_date=expected_source_trade_date)
    )


def missing_n4_trigger_baseline_periods(
    row: Mapping[str, Any],
    *,
    expected_source_trade_date: str,
) -> list[str]:
    baseline = row.get("period_trigger_baseline_json")
    periods = baseline.get("periods") if isinstance(baseline, Mapping) else {}
    required_periods = required_periods_for_condition_key(str(row.get("condition_key") or ""))
    if not isinstance(periods, Mapping):
        return list(required_periods)
    missing: list[str] = []
    for period in required_periods:
        entry = periods.get(period)
        if not isinstance(entry, Mapping):
            missing.append(period)
            continue
        if not n4_trigger_baseline_entry_has_fields(entry):
            missing.append(period)
            continue
        if str(entry.get("baseline_source_trade_date") or "") != expected_source_trade_date:
            missing.append(period)
    return missing


def trigger_baseline_source_trade_date_mismatch_periods(
    row: Mapping[str, Any],
    *,
    expected_source_trade_date: str,
) -> list[str]:
    baseline = row.get("period_trigger_baseline_json")
    periods = baseline.get("periods") if isinstance(baseline, Mapping) else {}
    required_periods = required_periods_for_condition_key(str(row.get("condition_key") or ""))
    if not isinstance(periods, Mapping):
        return list(required_periods)
    mismatches: list[str] = []
    for period in required_periods:
        entry = periods.get(period)
        if not isinstance(entry, Mapping):
            mismatches.append(period)
            continue
        if str(entry.get("baseline_source_trade_date") or "") != expected_source_trade_date:
            mismatches.append(period)
    return mismatches


def trigger_baseline_legacy_previous_usage_periods(
    row: Mapping[str, Any],
    *,
    expected_source_trade_date: str,
) -> list[str]:
    baseline = row.get("period_trigger_baseline_json")
    periods = baseline.get("periods") if isinstance(baseline, Mapping) else {}
    required_periods = required_periods_for_condition_key(str(row.get("condition_key") or ""))
    if not isinstance(periods, Mapping):
        return list(required_periods)
    legacy_periods: list[str] = []
    for period in required_periods:
        entry = periods.get(period)
        if not isinstance(entry, Mapping):
            continue
        if not n4_trigger_baseline_entry_has_fields(entry):
            continue
        trigger_high = entry.get("trigger_previous_entity_high")
        trigger_low = entry.get("trigger_previous_entity_low")
        previous_high = entry.get("previous_entity_high")
        previous_low = entry.get("previous_entity_low")
        if (
            trigger_high != previous_high
            or trigger_low != previous_low
        ):
            legacy_periods.append(period)
    return legacy_periods


def n4_trigger_baseline_period_ready(value: Any, period: str, *, expected_source_trade_date: str) -> bool:
    if not isinstance(value, Mapping):
        return False
    periods = value.get("periods")
    if not isinstance(periods, Mapping):
        return False
    entry = periods.get(period)
    if not isinstance(entry, Mapping):
        return False
    return n4_trigger_baseline_entry_has_fields(entry) and str(entry.get("baseline_source_trade_date") or "") == expected_source_trade_date


def n4_trigger_baseline_entry_has_fields(entry: Mapping[str, Any]) -> bool:
    return all(
        entry.get(field) not in (None, "")
        for field in (
            "trigger_previous_entity_high",
            "trigger_previous_entity_low",
            "trigger_previous_amount_baseline",
            "baseline_source_trade_date",
        )
    )


def required_periods_for_condition_key(condition_key: str) -> list[str]:
    condition_key = condition_key.strip().upper()
    if condition_key in HINT_CONDITION_KEYS:
        return []
    if condition_key in FULL_CONDITION_KEYS:
        return ["D"]
    if condition_key.startswith("BUY:") or condition_key.startswith("SELL:"):
        _, _, period_text = condition_key.partition(":")
        return [period for period in (item.strip().upper() for item in period_text.split(",")) if period in PERIODS]
    return []


def build_input_event_contract() -> dict[str, Any]:
    return {
        "source_layer": "N3_market_data",
        "accepted_event_types": list(INPUT_EVENT_TYPES),
        "ordinary_buy_sell_full_primary_event": "MarketSnapshotUpdated",
        "thirty_minute_confirmation_events": ["MinuteBarClosed"],
        "pending_market_data_events": ["MarketDataDelayed", "MarketDataMissing"],
        "does_not_call_market_adapter": True,
    }


def build_output_event_contract() -> dict[str, Any]:
    return {
        "source_layer": "N4_trigger",
        "emitted_event_types": list(OUTPUT_EVENT_TYPES),
        "payload_required_fields": list(N4_COMMON_PAYLOAD_KEYS),
        "same_transaction_required": True,
        "outbox_table": "common_event_outbox",
        "downstream_decision_policy": {
            "n4_decides_trade_or_hint_only": False,
            "n4_decides_sim_or_real_trade": False,
            "decision_layer": "N5_action_or_N6_user_policy",
        },
    }


def build_localization_contract() -> dict[str, Any]:
    return {
        "startup_or_trade_date_switch": [
            "read active N2 condition run",
            "read condition_pool, condition_basis, and minute_target_scope",
            "copy period_trigger_baseline_json into local N4 context",
            "write local trigger_context_snapshot in later execute stage",
        ],
        "intraday_n4_path": [
            "read local trigger_context_snapshot",
            "consume N3 standard events",
            "read N3 market facts only through allowed local runtime PostgreSQL references",
        ],
        "dry_run_writes": False,
        "external_n2_path_allowed_intraday": False,
        "old_system_access_allowed": False,
    }


def sample_context_refs(rows: Sequence[Mapping[str, Any]], limit: int = 20) -> str:
    refs = [
        f"{row.get('source_scope_table')}:{row.get('source_minute_target_scope_id')}"
        for row in rows[:limit]
    ]
    return ",".join(refs)


def summarize_active_run(active_run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": active_run.get("run_id"),
        "status": active_run.get("status"),
        "source_trade_date": active_run.get("source_trade_date"),
        "for_trade_date": active_run.get("for_trade_date"),
        "prev_trade_date": active_run.get("prev_trade_date"),
        "p0_count": active_run.get("p0_count"),
        "p1_count": active_run.get("p1_count"),
        "p2_count": active_run.get("p2_count"),
        "source_versions": active_run.get("source_versions") or {},
    }


def build_blocked_report(
    quality_items: Sequence[Mapping[str, Any]],
    active_runs: Sequence[Mapping[str, Any]],
    *,
    include_rows: bool,
) -> dict[str, Any]:
    severity_counts = count_quality_severities(list(quality_items))
    active_run = normalize_mapping(active_runs[0]) if len(active_runs) == 1 else {}
    return {
        "stage": "N4-0",
        "layer_role": "N4_trigger",
        "plan_mode": "n2_to_n4_local_context_preflight",
        "mode": "dry_run",
        "trigger_run_id": None,
        "source_condition_run_id": active_run.get("run_id"),
        "source_trade_date": active_run.get("source_trade_date"),
        "for_trade_date": active_run.get("for_trade_date"),
        "prev_trade_date": active_run.get("prev_trade_date"),
        "active_condition_run_candidates": [summarize_active_run(row) for row in active_runs],
        "candidate_context_row_count": 0,
        "condition_row_count": 0,
        "object_count": 0,
        "direction_distribution": {},
        "hint_condition_row_count": 0,
        "buy_hint_row_count": 0,
        "sell_hint_row_count": 0,
        "trigger_context_snapshot_dry_run_plan": rows_section([], include_rows=include_rows),
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": list(quality_items),
        },
        "blocked": True,
        "passed": False,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "trigger_context_snapshot_written": False,
            "trigger_state_written": False,
            "trigger_match_written": False,
            "event_outbox_written": False,
            "market_data_pulled": False,
            "n3_event_consumed": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
            "external_n2_runtime_path_accessed": False,
        },
    }
