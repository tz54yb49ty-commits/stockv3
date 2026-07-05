"""Condition-layer execute writer for N2-E3.

This module writes only condition-layer tables. It does not pull market data,
start workers, or touch downstream runtime layers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
import json
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.condition.active_status import (
    CANONICAL_ACTIVE_STATUS,
    active_status_order_sql,
    active_status_sql_list,
    summarize_active_runs,
)
from ashare_v3.condition.execute_contract import build_condition_execute_contract
from ashare_v3.condition.execute_preflight import (
    build_condition_execute_preflight,
    fetch_active_run_status,
    fetch_run_id_status,
    fetch_schema_status,
)
from ashare_v3.condition.display_basis import (
    DOMAIN_CONFIGS,
    build_display_rows_for_domain,
    validate_display_rows,
)
from ashare_v3.condition.basis import (
    LEVEL_SCORE_FIELDS,
    STOCK_CANONICAL_FINANCIAL_FIELDS,
    STOCK_FINANCIAL_COMPATIBILITY_FIELDS,
    STOCK_FINANCIAL_JSON_FIELDS,
    SYMMETRY_SECONDARY_TARGET_FIELDS,
)
from ashare_v3.condition.pool import build_condition_pool_preview_from_basis_report
from ashare_v3.condition.readiness_plan import (
    ROLLBACK_ORDER,
    build_condition_layer_execute_readiness_plan,
)


MONITOR_ID_COLUMN = {
    "stock": "stock_monitor_target_id",
    "index": "index_monitor_target_id",
    "board": "board_monitor_target_id",
}
BASIS_ID_COLUMN = {
    "stock": "stock_condition_basis_id",
    "index": "index_condition_basis_id",
    "board": "board_condition_basis_id",
}
POOL_ID_COLUMN = {
    "stock": "stock_condition_pool_id",
    "index": "index_condition_pool_id",
    "board": "board_condition_pool_id",
}

MONITOR_TABLE = {"stock": "stock_monitor_target", "index": "index_monitor_target", "board": "board_monitor_target"}
BASIS_TABLE = {"stock": "stock_condition_basis", "index": "index_condition_basis", "board": "board_condition_basis"}
POOL_TABLE = {"stock": "stock_condition_pool", "index": "index_condition_pool", "board": "board_condition_pool"}
SCOPE_TABLE = {"stock": "stock_minute_target_scope", "index": "index_minute_target_scope", "board": "board_minute_target_scope"}
DISPLAY_TABLE = {
    "stock": "stock_condition_display_basis",
    "index": "index_condition_display_basis",
    "board": "board_condition_display_basis",
}
STOCK_FINANCIAL_COLUMNS = STOCK_CANONICAL_FINANCIAL_FIELDS + STOCK_FINANCIAL_COMPATIBILITY_FIELDS
STOCK_FINANCIAL_NEW_COLUMNS = STOCK_CANONICAL_FINANCIAL_FIELDS

STOCK_BASIS_COLUMNS = (
    "run_id",
    "for_trade_date",
    "source_trade_date",
    "prev_trade_date",
    "stock_identity_key",
    "code",
    "exchange",
    "name",
    "is_st",
    "stock_status",
    "official_daily_proof",
    "lane",
    "monitor_type",
    "monitor_status",
    "direction_scope",
    "source_monitor_target_id",
    "period_key_y",
    "period_key_q",
    "period_key_m",
    "period_key_w",
    "period_key_d",
    "period_grade_y",
    "period_grade_q",
    "period_grade_m",
    "period_grade_w",
    "period_grade_d",
    "period_transition_y",
    "period_transition_q",
    "period_transition_m",
    "period_transition_w",
    "period_transition_d",
    *LEVEL_SCORE_FIELDS,
    "prev_up_str",
    "prev_dn_str",
    "amount_day",
    "amount_prev_day",
    "amount_week",
    "amount_prev_week",
    "amount_month",
    "amount_prev_month",
    "amount_quarter",
    "amount_prev_quarter",
    "amount_year",
    "amount_prev_year",
    "amount_source",
    "amount_quality_status",
    "period_trigger_baseline_json",
    "main_up_anchor",
    "up_reference_period",
    "up_amplitude",
    "up_base_price",
    "buy_target_price",
    "buy_expected_return_pct",
    "up_trend_start_date",
    "up_trend_end_date",
    "up_reference_window_start",
    "up_reference_window_end",
    "main_down_anchor",
    "down_reference_period",
    "down_amplitude",
    "down_base_price",
    "sell_target_price",
    "sell_expected_return_pct",
    "up_sell_reference_period",
    "down_buy_reference_period",
    "down_trend_start_date",
    "down_trend_end_date",
    "down_reference_window_start",
    "down_reference_window_end",
    "clear_sell_ref_period",
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
    *SYMMETRY_SECONDARY_TARGET_FIELDS,
    "pe_core",
    "total_mv",
    "circ_mv",
    "score",
    "recommendation_level",
    "recommendation_reason",
    "financial_asof_date",
    "financial_quality_status",
    *STOCK_FINANCIAL_NEW_COLUMNS,
    "financial_source_version",
    "main_index_identity_key",
    "main_index_code",
    "main_index_name",
    "main_index_expected_return_pct",
    "preferred_board_identity_key",
    "preferred_board_code",
    "preferred_board_name",
    "preferred_board_expected_return_pct",
    "linked_board_identity_keys",
    "buy_necessary_base",
    "buy_necessary_key",
    "buy_necessary_periods",
    "sell_necessary_base",
    "sell_necessary_key",
    "sell_necessary_periods",
    "buy_full_necessary_base",
    "buy_full_necessary_key",
    "sell_full_necessary_base",
    "sell_full_necessary_key",
    "oversold_hint_necessary_base",
    "oversold_hint_key",
    "overbought_hint_necessary_base",
    "overbought_hint_key",
    "source_version",
    "source_batch_id",
    "quality_status",
    "quality_reason",
    "missing_fields_json",
    "raw_json",
)
INDEX_BASIS_COLUMNS = tuple(column for column in STOCK_BASIS_COLUMNS if column not in {
    "stock_identity_key",
    "ts_code",
    "is_st",
    "stock_status",
    "official_daily_proof",
    "pe_core",
    "total_mv",
    "circ_mv",
    "score",
    "recommendation_level",
    "recommendation_reason",
    "financial_asof_date",
    "financial_quality_status",
    "financial_source_version",
    "main_index_identity_key",
    "main_index_code",
    "main_index_name",
    "main_index_expected_return_pct",
    "preferred_board_identity_key",
    "preferred_board_code",
    "preferred_board_name",
    "preferred_board_expected_return_pct",
    "linked_board_identity_keys",
}.union(STOCK_FINANCIAL_NEW_COLUMNS)) + ("index_identity_key",)
BOARD_BASIS_COLUMNS = tuple(column for column in INDEX_BASIS_COLUMNS if column not in {"index_identity_key", "code", "exchange", "name"}) + (
    "board_identity_key",
    "board_code",
    "board_name",
    "board_type",
)

STOCK_POOL_COLUMNS = (
    "run_id",
    "for_trade_date",
    "source_trade_date",
    "prev_trade_date",
    "stock_identity_key",
    "code",
    "exchange",
    "name",
    "lane",
    "direction",
    "condition_key",
    "condition_periods",
    "allowed_signal_types",
    "is_hint_scope",
    "daily_snapshot_required",
    "minute_required",
    "previous_day_minute_required",
    "previous_day_minute_date",
    "previous_day_minute_quality_required",
    "minute_scope_reason",
    "market_data_consumer",
    "monitor_type",
    "policy_name",
    "policy_hash",
    "selected_reason",
    "excluded_reason",
    "period_trigger_baseline_json",
    *LEVEL_SCORE_FIELDS,
    "main_up_anchor",
    "up_reference_period",
    "buy_target_price",
    "buy_expected_return_pct",
    "main_down_anchor",
    "down_reference_period",
    "sell_target_price",
    "sell_expected_return_pct",
    "up_sell_reference_period",
    "down_buy_reference_period",
    "clear_sell_ref_period",
    "pe_core",
    "score",
    "financial_quality_status",
    *STOCK_FINANCIAL_NEW_COLUMNS,
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
    *SYMMETRY_SECONDARY_TARGET_FIELDS,
    "recommendation_level",
    "recommendation_reason",
    "main_index_identity_key",
    "main_index_code",
    "main_index_name",
    "main_index_expected_return_pct",
    "preferred_board_identity_key",
    "preferred_board_code",
    "preferred_board_name",
    "preferred_board_expected_return_pct",
    "linked_board_identity_keys",
    "source_condition_basis_id",
    "source_version",
    "active_target",
    "quality_status",
    "quality_reason",
    "missing_fields_json",
    "raw_json",
)
INDEX_POOL_COLUMNS = (
    "run_id",
    "for_trade_date",
    "source_trade_date",
    "prev_trade_date",
    "index_identity_key",
    "code",
    "exchange",
    "name",
    "lane",
    "direction",
    "condition_key",
    "condition_periods",
    "allowed_signal_types",
    "is_hint_scope",
    "daily_snapshot_required",
    "minute_required",
    "previous_day_minute_required",
    "previous_day_minute_date",
    "previous_day_minute_quality_required",
    "minute_scope_reason",
    "market_data_consumer",
    "monitor_type",
    "policy_name",
    "policy_hash",
    "selected_reason",
    "excluded_reason",
    "period_trigger_baseline_json",
    *LEVEL_SCORE_FIELDS,
    "up_sell_reference_period",
    "down_buy_reference_period",
    "clear_sell_ref_period",
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
    *SYMMETRY_SECONDARY_TARGET_FIELDS,
    "source_condition_basis_id",
    "source_version",
    "active_target",
    "quality_status",
    "quality_reason",
    "missing_fields_json",
    "raw_json",
)
BOARD_POOL_COLUMNS = tuple(column for column in INDEX_POOL_COLUMNS if column not in {"index_identity_key", "code", "exchange", "name"}) + (
    "board_identity_key",
    "board_code",
    "board_name",
    "board_type",
)

STOCK_SCOPE_COLUMNS = (
    "run_id",
    "for_trade_date",
    "source_trade_date",
    "prev_trade_date",
    "stock_identity_key",
    "code",
    "exchange",
    "name",
    "lane",
    "direction",
    "condition_key",
    "condition_periods",
    "allowed_signal_types",
    "is_hint_scope",
    "scope_source",
    "source_condition_pool_id",
    "reason",
    "total_mv",
    "market_value_threshold",
    "pe_core",
    "score",
    "financial_quality_status",
    *STOCK_FINANCIAL_NEW_COLUMNS,
    "period_trigger_baseline_json",
    *LEVEL_SCORE_FIELDS,
    "up_sell_reference_period",
    "down_buy_reference_period",
    "clear_sell_ref_period",
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
    *SYMMETRY_SECONDARY_TARGET_FIELDS,
    "daily_snapshot_required",
    "minute_required",
    "previous_day_minute_required",
    "previous_day_minute_date",
    "previous_day_minute_quality_required",
    "minute_scope_reason",
    "market_data_consumer",
    "source_version",
    "scope_status",
    "raw_json",
)
INDEX_SCOPE_COLUMNS = (
    "run_id",
    "for_trade_date",
    "source_trade_date",
    "prev_trade_date",
    "index_identity_key",
    "code",
    "exchange",
    "name",
    "lane",
    "direction",
    "condition_key",
    "condition_periods",
    "allowed_signal_types",
    "is_hint_scope",
    "scope_source",
    "source_condition_pool_id",
    "reason",
    "period_trigger_baseline_json",
    *LEVEL_SCORE_FIELDS,
    "up_sell_reference_period",
    "down_buy_reference_period",
    "clear_sell_ref_period",
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
    "daily_snapshot_required",
    "minute_required",
    "previous_day_minute_required",
    "previous_day_minute_date",
    "previous_day_minute_quality_required",
    "minute_scope_reason",
    "market_data_consumer",
    "source_version",
    "scope_status",
    "raw_json",
)
BOARD_SCOPE_COLUMNS = tuple(column for column in INDEX_SCOPE_COLUMNS if column not in {"index_identity_key", "code", "exchange", "name"}) + (
    "board_identity_key",
    "board_code",
    "board_name",
    "board_type",
)

BASIS_COLUMNS = {"stock": STOCK_BASIS_COLUMNS, "index": INDEX_BASIS_COLUMNS, "board": BOARD_BASIS_COLUMNS}
POOL_COLUMNS = {"stock": STOCK_POOL_COLUMNS, "index": INDEX_POOL_COLUMNS, "board": BOARD_POOL_COLUMNS}
SCOPE_COLUMNS = {"stock": STOCK_SCOPE_COLUMNS, "index": INDEX_SCOPE_COLUMNS, "board": BOARD_SCOPE_COLUMNS}

COMMON_DISPLAY_COLUMNS = (
    "run_id",
    "for_trade_date",
    "source_trade_date",
    "prev_trade_date",
    "display_code",
    "display_name",
    "display_title",
    "display_summary",
    "selected_directions",
    "selected_condition_keys",
    "selected_signal_types",
    "selected_lanes",
    "selected_monitor_types",
    "condition_summary_json",
    "target_price_summary_json",
    "reference_period_summary_json",
    "period_grade_summary_json",
    "period_transition_summary_json",
    "period_grade_y",
    "period_grade_q",
    "period_grade_m",
    "period_grade_w",
    "period_grade_d",
    "period_transition_y",
    "period_transition_q",
    "period_transition_m",
    "period_transition_w",
    "period_transition_d",
    *LEVEL_SCORE_FIELDS,
    "prev_up_str",
    "prev_dn_str",
    "buy_target_price",
    "buy_expected_return_pct",
    "sell_target_price",
    "up_sell_reference_period",
    "down_buy_reference_period",
    "clear_sell_ref_period",
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
    *SYMMETRY_SECONDARY_TARGET_FIELDS,
    "period_trigger_baseline_json",
    "display_policy_name",
    "display_policy_hash",
    "condition_pool_policy_name",
    "condition_pool_policy_hash",
    "scope_policy_name",
    "scope_policy_hash",
    "display_scope_reason",
    "selected_reason",
    "excluded_reason",
    "primary_source_condition_basis_id",
    "primary_source_condition_pool_id",
    "primary_source_minute_target_scope_id",
    "source_condition_basis_ids_json",
    "source_condition_pool_ids_json",
    "source_minute_target_scope_ids_json",
    "source_row_count_json",
    "source_version",
    "display_status",
    "quality_status",
    "quality_reason",
    "missing_fields_json",
    "raw_json",
)
STOCK_DISPLAY_COLUMNS = (
    "stock_identity_key",
    "code",
    "exchange",
    "name",
    *COMMON_DISPLAY_COLUMNS,
    "total_mv",
    "circ_mv",
    "pe_core",
    "score",
    "recommendation_level",
    "recommendation_reason",
    "is_st",
    "stock_status",
    "official_daily_proof",
    "financial_quality_status",
    *STOCK_FINANCIAL_NEW_COLUMNS,
    "main_index_identity_key",
    "main_index_code",
    "main_index_name",
    "preferred_board_identity_key",
    "preferred_board_code",
    "preferred_board_name",
    "linked_board_identity_keys",
)
INDEX_DISPLAY_COLUMNS = (
    "index_identity_key",
    "code",
    "exchange",
    "name",
    "fixed_index_member",
    *COMMON_DISPLAY_COLUMNS,
)
BOARD_DISPLAY_COLUMNS = (
    "board_identity_key",
    "board_code",
    "board_name",
    "board_type",
    "is_industry_board",
    *COMMON_DISPLAY_COLUMNS,
)
DISPLAY_COLUMNS = {
    "stock": STOCK_DISPLAY_COLUMNS,
    "index": INDEX_DISPLAY_COLUMNS,
    "board": BOARD_DISPLAY_COLUMNS,
}
DISPLAY_JSON_COLUMNS = {
    "condition_summary_json",
    "target_price_summary_json",
    "reference_period_summary_json",
    "period_grade_summary_json",
    "period_transition_summary_json",
    "period_trigger_baseline_json",
    "target_price_trace_json",
    "source_condition_basis_ids_json",
    "source_condition_pool_ids_json",
    "source_minute_target_scope_ids_json",
    "source_row_count_json",
    "missing_fields_json",
    "raw_json",
    *STOCK_FINANCIAL_JSON_FIELDS,
}
DISPLAY_ARRAY_COLUMNS = {
    "selected_directions",
    "selected_condition_keys",
    "selected_signal_types",
    "selected_lanes",
    "selected_monitor_types",
    "selected_reason",
    "excluded_reason",
    "linked_board_identity_keys",
}
DISPLAY_ROLLBACK_ORDER = (
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
)
FULL_ROLLBACK_ORDER = (*DISPLAY_ROLLBACK_ORDER, *ROLLBACK_ORDER)


class ConditionExecuteError(RuntimeError):
    """Raised when the condition-layer execute contract is not satisfied."""


def build_execute_run_id(
    source_trade_date: str,
    for_trade_date: str,
    now: datetime | None = None,
    *,
    run_id_override: str = "",
) -> str:
    if run_id_override:
        return run_id_override
    now = now or datetime.now()
    return f"condition_layer_{source_trade_date}_to_{for_trade_date}_{now.strftime('%Y%m%d%H%M%S')}_execute"


def execute_condition_layer(
    *,
    dsn: str,
    ready_check: Mapping[str, Any],
    basis_report: Mapping[str, Any],
    pool_report: Mapping[str, Any],
    scope_report: Mapping[str, Any],
    user_confirmed: bool,
    overwrite: bool = False,
    operator: str = "manual",
    confirmation_note: str = "",
    run_id_override: str = "",
    condition_pool_policy: Mapping[str, Any] | None = None,
    policy_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    readiness_plan = build_condition_layer_execute_readiness_plan(
        basis_report=basis_report,
        pool_report=pool_report,
        scope_report=scope_report,
    )
    contract = build_condition_execute_contract(
        readiness_plan,
        user_confirmed=user_confirmed,
        overwrite=overwrite,
        operator=operator,
        confirmation_note=confirmation_note,
    )
    execute_run_id = build_execute_run_id(
        str(readiness_plan["source_trade_date"]),
        str(readiness_plan["for_trade_date"]),
        run_id_override=run_id_override,
    )
    schema_status = fetch_schema_status(dsn)
    active_status = fetch_active_run_status(
        dsn,
        source_trade_date=str(readiness_plan["source_trade_date"]),
        for_trade_date=str(readiness_plan["for_trade_date"]),
        overwrite=overwrite,
    )
    run_id_status = fetch_run_id_status(dsn, execute_run_id)
    preflight = build_condition_execute_preflight(
        readiness_plan=readiness_plan,
        execute_contract=contract,
        schema_status=schema_status,
        active_run_status=active_status,
        run_id_status=run_id_status,
    )
    if not preflight["execute_allowed"]:
        raise ConditionExecuteError(f"condition execute blocked: {preflight['blocked_reasons']}")

    previous_active_run_id = first_active_run_id(active_status)
    expected_rows = dict(readiness_plan["would_write"])
    row_counts: dict[str, int] = {}
    source_versions = dict(readiness_plan.get("source_versions") or {})

    with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        try:
            with conn.cursor() as cur:
                lock_condition_run(cur, str(readiness_plan["source_trade_date"]), str(readiness_plan["for_trade_date"]), overwrite=overwrite)
                assert_run_id_unused(cur, execute_run_id)
                insert_condition_run(
                    cur,
                    execute_run_id=execute_run_id,
                    readiness_plan=readiness_plan,
                    ready_check=ready_check,
                    contract=contract,
                    previous_active_run_id=previous_active_run_id,
                    operator=operator,
                    confirmation_note=confirmation_note,
                    policy_metadata=policy_metadata,
                )
                row_counts["common_condition_run"] = 1
                row_counts["common_condition_quality_item"] = insert_quality_items(
                    cur,
                    execute_run_id=execute_run_id,
                    readiness_plan=readiness_plan,
                    basis_report=basis_report,
                    pool_report=pool_report,
                    scope_report=scope_report,
                )

                monitor_id_maps: dict[str, dict[str, int]] = {}
                basis_id_maps: dict[str, dict[str, int]] = {}
                pool_id_maps: dict[str, dict[str, int]] = {}
                for domain in ("stock", "index", "board"):
                    basis_rows = list(basis_report["basis_preview"][domain].get("basis_rows") or [])
                    monitor_id_maps[domain] = insert_monitor_targets(cur, domain, execute_run_id, basis_rows)
                    row_counts[MONITOR_TABLE[domain]] = len(monitor_id_maps[domain])
                    basis_id_maps[domain] = insert_basis_rows(cur, domain, execute_run_id, basis_rows, monitor_id_maps[domain])
                    row_counts[BASIS_TABLE[domain]] = len(basis_id_maps[domain])

                pool_preview = pool_preview_for_execute(
                    basis_report,
                    pool_report,
                    condition_pool_policy=condition_pool_policy,
                )
                for domain in ("stock", "index", "board"):
                    pool_rows = list(pool_preview[domain].get("pool_rows") or [])
                    pool_id_maps[domain] = insert_pool_rows(cur, domain, execute_run_id, pool_rows, basis_id_maps[domain])
                    row_counts[POOL_TABLE[domain]] = len(pool_id_maps[domain])

                for domain in ("index", "board", "stock"):
                    scope_rows = list(scope_report["scope_preview"][domain].get("scope_rows") or [])
                    row_counts[SCOPE_TABLE[domain]] = insert_scope_rows(cur, domain, execute_run_id, scope_rows, pool_id_maps.get(domain, {}))

                display_quality_items: list[dict[str, Any]] = []
                for domain in ("stock", "index", "board"):
                    display_rows = build_display_rows_from_inserted_condition_rows(cur, domain, execute_run_id)
                    row_counts[DISPLAY_TABLE[domain]] = insert_display_rows(cur, domain, display_rows)
                    display_quality_items.extend(display_quality_items_for_domain(domain, display_rows))
                display_quality_items.append(display_write_quality_item(execute_run_id, row_counts))
                row_counts["common_condition_quality_item"] += insert_display_quality_items(
                    cur,
                    execute_run_id=execute_run_id,
                    readiness_plan=readiness_plan,
                    display_quality_items=display_quality_items,
                )

                expected_rows = expected_rows_with_display(
                    expected_rows,
                    display_quality_item_count=len(display_quality_items),
                    display_row_counts={domain: row_counts[DISPLAY_TABLE[domain]] for domain in ("stock", "index", "board")},
                )
                verify_row_counts(row_counts, expected_rows)
                if previous_active_run_id and overwrite:
                    cur.execute(
                        "UPDATE common_condition_run SET status = 'superseded', updated_at = now() WHERE run_id = %s",
                        (previous_active_run_id,),
                    )
                update_condition_run_passed(cur, execute_run_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    postcheck = fetch_post_execute_counts(dsn, execute_run_id)
    report = {
        "stage": "N2-E3",
        "plan_mode": "condition_layer_execute",
        "execute_run_id": execute_run_id,
        "source_trade_date": readiness_plan["source_trade_date"],
        "for_trade_date": readiness_plan["for_trade_date"],
        "prev_trade_date": readiness_plan["prev_trade_date"],
        "source_versions": source_versions,
        "policy_name": readiness_plan.get("policy_name"),
        "policy_hash": readiness_plan.get("policy_hash"),
        "previous_active_run_id": previous_active_run_id,
        "overwrite": overwrite,
        "user_confirmed": user_confirmed,
        "operator": operator,
        "expected_row_counts": {table: int(spec.get("row_count") or 0) for table, spec in expected_rows.items()},
        "actual_row_counts": row_counts,
        "postcheck": postcheck,
        "preflight": preflight,
        "rollback_order": list(FULL_ROLLBACK_ORDER),
        "writes_performed": True,
        "will_execute_sql": True,
        "migration_performed": False,
        "minute_kline_pulled": False,
        "downstream_layers_touched": False,
        "condition_pool_written": True,
        "condition_display_basis_written": True,
    }
    if policy_metadata:
        report.update(dict(policy_metadata))
    return report


def pool_preview_for_execute(
    basis_report: Mapping[str, Any],
    pool_report: Mapping[str, Any],
    *,
    condition_pool_policy: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    preview = pool_report.get("pool_preview") if isinstance(pool_report, Mapping) else None
    if isinstance(preview, Mapping) and preview:
        return preview
    return build_condition_pool_preview_from_basis_report(
        basis_report,
        condition_pool_policy=condition_pool_policy,
    )


def lock_condition_run(cur: psycopg.Cursor[dict[str, Any]], source_trade_date: str, for_trade_date: str, *, overwrite: bool) -> None:
    cur.execute(
        """
        SELECT run_id
             , status
        FROM common_condition_run
        WHERE source_trade_date = %s
          AND for_trade_date = %s
          AND status IN (""" + active_status_sql_list() + """)
        ORDER BY """ + active_status_order_sql("status") + """,
                 finished_at DESC NULLS LAST,
                 created_at DESC
        FOR UPDATE
        """,
        (source_trade_date, for_trade_date),
    )
    rows = cur.fetchall()
    active_status = summarize_active_runs(rows, overwrite=overwrite)
    if active_status["blocked_by_multiple_passed_active"]:
        raise ConditionExecuteError(
            f"multiple passed_active condition runs exist: {[row['run_id'] for row in rows if row.get('status') == CANONICAL_ACTIVE_STATUS]}"
        )
    if active_status["blocked_by_active_run"]:
        raise ConditionExecuteError(f"active condition run exists: {[row['run_id'] for row in rows]}")


def assert_run_id_unused(cur: psycopg.Cursor[dict[str, Any]], execute_run_id: str) -> None:
    conflicts: dict[str, int] = {}
    for table_name in FULL_ROLLBACK_ORDER:
        where_column = "source_version" if table_name in MONITOR_TABLE.values() else "run_id"
        cur.execute(f"SELECT count(*)::bigint AS count FROM {table_name} WHERE {where_column} = %s", (execute_run_id,))
        count = int(cur.fetchone()["count"])
        if count:
            conflicts[table_name] = count
    if conflicts:
        raise ConditionExecuteError(f"run_id already exists: {conflicts}")


def insert_condition_run(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    readiness_plan: Mapping[str, Any],
    ready_check: Mapping[str, Any],
    contract: Mapping[str, Any],
    previous_active_run_id: str | None,
    operator: str,
    confirmation_note: str,
    policy_metadata: Mapping[str, Any] | None = None,
) -> None:
    source_trade_date = str(readiness_plan["source_trade_date"])
    cur.execute(
        """
        INSERT INTO common_condition_run (
          run_id, for_trade_date, source_trade_date, prev_trade_date,
          source_version, source_versions, source_ready_check, mode, status,
          p0_count, p1_count, p2_count, raw_json
        )
        VALUES (
          %(run_id)s, %(for_trade_date)s, %(source_trade_date)s, %(prev_trade_date)s,
          %(source_version)s, %(source_versions)s, %(source_ready_check)s, 'execute', 'running',
          %(p0_count)s, %(p1_count)s, %(p2_count)s, %(raw_json)s
        )
        """,
        {
            "run_id": execute_run_id,
            "for_trade_date": readiness_plan["for_trade_date"],
            "source_trade_date": source_trade_date,
            "prev_trade_date": readiness_plan["prev_trade_date"],
            "source_version": f"condition_source_bundle_{source_trade_date}",
            "source_versions": jsonb(readiness_plan.get("source_versions") or {}),
            "source_ready_check": jsonb(ready_check),
            "p0_count": readiness_plan["quality_summary"]["p0_count"],
            "p1_count": readiness_plan["quality_summary"]["p1_count"],
            "p2_count": readiness_plan["quality_summary"]["p2_count"],
            "raw_json": jsonb(
                {
                    "readiness_plan_id": readiness_plan.get("planned_run_id"),
                    "contract_hash": contract.get("contract_hash"),
                    "policy_hash": readiness_plan.get("policy_hash"),
                    "policy_metadata": dict(policy_metadata or {}),
                    "previous_active_run_id": previous_active_run_id,
                    "operator": operator,
                    "confirmation_note_present": bool(confirmation_note),
                    "write_order": readiness_plan.get("write_order"),
                }
            ),
        },
    )


def insert_quality_items(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    readiness_plan: Mapping[str, Any],
    basis_report: Mapping[str, Any],
    pool_report: Mapping[str, Any],
    scope_report: Mapping[str, Any],
) -> int:
    rows = []
    for stage_name, report, layer_scope in (
        ("condition_basis", basis_report, "condition_basis"),
        ("condition_pool", pool_report, "condition_pool"),
        ("minute_target_scope", scope_report, "minute_target_scope"),
    ):
        for item in report.get("quality", {}).get("items") or []:
            rows.append(quality_row(execute_run_id, readiness_plan, item, stage_name=stage_name, layer_scope=layer_scope))
    for guard in readiness_plan.get("execute_guards") or []:
        rows.append(quality_row(execute_run_id, readiness_plan, guard, stage_name="condition_run", layer_scope="condition_run"))
    insert_rows(cur, "common_condition_quality_item", (
        "run_id",
        "for_trade_date",
        "source_trade_date",
        "data_domain",
        "layer_scope",
        "table_name",
        "gate_code",
        "gate_name",
        "severity",
        "status",
        "expected_value",
        "actual_value",
        "identity_key",
        "details",
    ), rows)
    return len(rows)


def quality_row(
    execute_run_id: str,
    readiness_plan: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    stage_name: str,
    layer_scope: str,
) -> dict[str, Any]:
    return {
        "run_id": execute_run_id,
        "for_trade_date": readiness_plan["for_trade_date"],
        "source_trade_date": readiness_plan["source_trade_date"],
        "data_domain": str(item.get("data_domain") or "common"),
        "layer_scope": layer_scope,
        "table_name": item.get("table_name"),
        "gate_code": str(item.get("gate_code") or "unknown"),
        "gate_name": str(item.get("gate_name") or item.get("gate_code") or "unknown"),
        "severity": str(item.get("severity") or "P0"),
        "status": str(item.get("status") or "passed"),
        "expected_value": item.get("expected_value"),
        "actual_value": item.get("actual_value"),
        "identity_key": item.get("identity_key"),
        "details": jsonb({"stage": stage_name, **dict(item.get("details") or {})}),
    }


def insert_monitor_targets(
    cur: psycopg.Cursor[dict[str, Any]],
    domain: str,
    execute_run_id: str,
    basis_rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    rows = [monitor_target_row(domain, execute_run_id, row) for row in basis_rows]
    id_column = MONITOR_ID_COLUMN[domain]
    returned = insert_rows_returning(cur, MONITOR_TABLE[domain], monitor_columns(domain), rows, id_column)
    return {basis_ref(domain, idx, basis_rows[idx - 1]): int(row[id_column]) for idx, row in enumerate(returned, start=1)}


def monitor_target_row(domain: str, execute_run_id: str, row: Mapping[str, Any]) -> dict[str, Any]:
    base = {
        "for_trade_date": row.get("for_trade_date"),
        "source_trade_date": row.get("source_trade_date"),
        "monitor_type": execute_monitor_type(domain),
        "lane": execute_lane(domain, row),
        "status": "active",
        "direction_scope": list(row.get("direction_scope") or ["buy", "sell"]),
        "source": "condition_execute_fact_universe",
        "source_version": execute_run_id,
        "raw_json": jsonb({"source_basis_ref": row_identity(domain, row), "source_monitor_mode": "fact_universe_fallback"}),
    }
    if domain == "stock":
        base.update({
            "stock_identity_key": row.get("stock_identity_key"),
            "code": row.get("code"),
            "exchange": row.get("exchange"),
            "name": row.get("name") or row.get("code"),
        })
    elif domain == "index":
        base.update({
            "index_identity_key": row.get("index_identity_key"),
            "code": row.get("code"),
            "exchange": row.get("exchange"),
            "name": row.get("name") or row.get("code"),
        })
    elif domain == "board":
        base.update({
            "board_identity_key": row.get("board_identity_key"),
            "board_code": row.get("board_code"),
            "board_name": row.get("board_name") or row.get("board_code"),
            "board_type": row.get("board_type"),
        })
    else:
        raise ValueError(f"unsupported domain: {domain}")
    return base


def insert_basis_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    domain: str,
    execute_run_id: str,
    basis_rows: Sequence[Mapping[str, Any]],
    monitor_ids: Mapping[str, int],
) -> dict[str, int]:
    rows = []
    for idx, row in enumerate(basis_rows, start=1):
        ref = basis_ref(domain, idx, row)
        rows.append(basis_insert_row(domain, execute_run_id, row, monitor_ids[ref]))
    id_column = BASIS_ID_COLUMN[domain]
    returned = insert_rows_returning(cur, BASIS_TABLE[domain], BASIS_COLUMNS[domain], rows, id_column)
    return {basis_ref(domain, idx, basis_rows[idx - 1]): int(row[id_column]) for idx, row in enumerate(returned, start=1)}


def basis_insert_row(domain: str, execute_run_id: str, row: Mapping[str, Any], monitor_id: int) -> dict[str, Any]:
    output = {column: row.get(column) for column in BASIS_COLUMNS[domain]}
    output["run_id"] = execute_run_id
    output["monitor_type"] = execute_monitor_type(domain)
    output["lane"] = execute_lane(domain, row)
    output["source_monitor_target_id"] = monitor_id
    output["missing_fields_json"] = jsonb(row.get("missing_fields_json") or {})
    output["period_trigger_baseline_json"] = jsonb(row.get("period_trigger_baseline_json") or {})
    if "target_price_trace_json" in output:
        output["target_price_trace_json"] = jsonb(row.get("target_price_trace_json") or {})
    for column in STOCK_FINANCIAL_JSON_FIELDS:
        if column in output:
            output[column] = jsonb_or_none(row.get(column))
    output["raw_json"] = jsonb(row.get("raw_json") or {})
    output["direction_scope"] = list(row.get("direction_scope") or ["buy", "sell"])
    output["linked_board_identity_keys"] = list(row.get("linked_board_identity_keys") or [])
    for column in ("buy_necessary_periods", "sell_necessary_periods"):
        if column in output:
            output[column] = list(row.get(column) or [])
    if domain == "index":
        output["index_identity_key"] = row.get("index_identity_key")
    elif domain == "board":
        output["board_identity_key"] = row.get("board_identity_key")
        output["board_code"] = row.get("board_code")
        output["board_name"] = row.get("board_name")
        output["board_type"] = row.get("board_type")
    return output


def insert_pool_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    domain: str,
    execute_run_id: str,
    pool_rows: Sequence[Mapping[str, Any]],
    basis_ids: Mapping[str, int],
) -> dict[str, int]:
    rows = []
    for row in pool_rows:
        basis_ref_value = str(row.get("source_condition_basis_ref") or "")
        rows.append(pool_insert_row(domain, execute_run_id, row, basis_ids[basis_ref_value]))
    id_column = POOL_ID_COLUMN[domain]
    returned = insert_rows_returning(cur, POOL_TABLE[domain], POOL_COLUMNS[domain], rows, id_column)
    return {str(pool_rows[idx - 1].get("condition_pool_ref")): int(row[id_column]) for idx, row in enumerate(returned, start=1)}


def pool_insert_row(domain: str, execute_run_id: str, row: Mapping[str, Any], basis_id: int) -> dict[str, Any]:
    output = {column: row.get(column) for column in POOL_COLUMNS[domain]}
    output["run_id"] = execute_run_id
    output["monitor_type"] = execute_monitor_type(domain)
    output["lane"] = execute_lane(domain, row)
    output["source_condition_basis_id"] = basis_id
    output["condition_periods"] = list(row.get("condition_periods") or [])
    output["allowed_signal_types"] = list(row.get("allowed_signal_types") or [])
    output["selected_reason"] = list(row.get("selected_reason") or [])
    output["excluded_reason"] = list(row.get("excluded_reason") or [])
    output["linked_board_identity_keys"] = list(row.get("linked_board_identity_keys") or [])
    output["missing_fields_json"] = jsonb(row.get("missing_fields_json") or {})
    output["period_trigger_baseline_json"] = jsonb(row.get("period_trigger_baseline_json") or {})
    if "target_price_trace_json" in output:
        output["target_price_trace_json"] = jsonb(row.get("target_price_trace_json") or {})
    for column in STOCK_FINANCIAL_JSON_FIELDS:
        if column in output:
            output[column] = jsonb_or_none(row.get(column))
    output["raw_json"] = jsonb(row.get("raw_json") or {})
    if domain == "board":
        output["board_name"] = row.get("board_name") or row.get("name")
    return output


def insert_scope_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    domain: str,
    execute_run_id: str,
    scope_rows: Sequence[Mapping[str, Any]],
    pool_ids: Mapping[str, int],
) -> int:
    rows = [scope_insert_row(domain, execute_run_id, row, pool_ids) for row in scope_rows]
    insert_rows(cur, SCOPE_TABLE[domain], SCOPE_COLUMNS[domain], rows)
    return len(rows)


def scope_insert_row(domain: str, execute_run_id: str, row: Mapping[str, Any], pool_ids: Mapping[str, int]) -> dict[str, Any]:
    output = {column: row.get(column) for column in SCOPE_COLUMNS[domain]}
    output["run_id"] = execute_run_id
    output["condition_periods"] = list(row.get("condition_periods") or [])
    output["allowed_signal_types"] = list(row.get("allowed_signal_types") or [])
    output["period_trigger_baseline_json"] = jsonb(row.get("period_trigger_baseline_json") or {})
    if "target_price_trace_json" in output:
        output["target_price_trace_json"] = jsonb(row.get("target_price_trace_json") or {})
    for column in STOCK_FINANCIAL_JSON_FIELDS:
        if column in output:
            output[column] = jsonb_or_none(row.get(column))
    output["raw_json"] = jsonb(row.get("raw_json") or {})
    pool_ref = str(row.get("source_condition_pool_ref") or "")
    if pool_ref:
        output["source_condition_pool_id"] = pool_ids[pool_ref]
    if domain == "index":
        output["index_identity_key"] = row.get("index_identity_key") or row.get("identity_key")
    elif domain == "board":
        output["board_identity_key"] = row.get("board_identity_key") or row.get("identity_key")
    return output


def build_display_rows_from_inserted_condition_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    domain: str,
    execute_run_id: str,
) -> list[dict[str, Any]]:
    config = DOMAIN_CONFIGS[domain]
    basis_rows = fetch_inserted_rows(cur, BASIS_TABLE[domain], execute_run_id)
    pool_rows = fetch_inserted_rows(cur, POOL_TABLE[domain], execute_run_id)
    scope_rows = fetch_inserted_rows(cur, SCOPE_TABLE[domain], execute_run_id)
    return build_display_rows_for_domain(config, basis_rows=basis_rows, pool_rows=pool_rows, scope_rows=scope_rows)


def fetch_inserted_rows(cur: psycopg.Cursor[dict[str, Any]], table_name: str, execute_run_id: str) -> list[dict[str, Any]]:
    cur.execute(f"SELECT * FROM {table_name} WHERE run_id = %s ORDER BY 1", (execute_run_id,))
    return [to_jsonable(dict(row)) for row in cur.fetchall()]


def insert_display_rows(
    cur: psycopg.Cursor[dict[str, Any]],
    domain: str,
    display_rows: Sequence[Mapping[str, Any]],
) -> int:
    rows = [display_insert_row(domain, row) for row in display_rows]
    insert_rows(cur, DISPLAY_TABLE[domain], DISPLAY_COLUMNS[domain], rows)
    return len(rows)


def display_insert_row(domain: str, row: Mapping[str, Any]) -> dict[str, Any]:
    output = {column: row.get(column) for column in DISPLAY_COLUMNS[domain]}
    for column in DISPLAY_JSON_COLUMNS:
        if column in output:
            if column in STOCK_FINANCIAL_JSON_FIELDS:
                output[column] = jsonb_or_none(row.get(column))
            else:
                default_value: Any = [] if column.endswith("_ids_json") else {}
                output[column] = jsonb(row.get(column) if row.get(column) is not None else default_value)
    for column in DISPLAY_ARRAY_COLUMNS:
        if column in output:
            output[column] = list(row.get(column) or [])
    if domain == "stock":
        output["is_st"] = bool(row.get("is_st"))
        output["official_daily_proof"] = bool(row.get("official_daily_proof"))
        output["linked_board_identity_keys"] = list(row.get("linked_board_identity_keys") or [])
    if domain == "index":
        output["fixed_index_member"] = bool(row.get("fixed_index_member"))
    if domain == "board":
        output["is_industry_board"] = bool(row.get("is_industry_board"))
    return output


def display_quality_items_for_domain(domain: str, display_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    config = DOMAIN_CONFIGS[domain]
    checks = validate_display_rows(config, display_rows)
    uniqueness = checks["uniqueness"]
    integrity = checks["field_integrity"]
    traceability = checks["traceability"]
    forbidden = checks["forbidden_field_check"]
    table = DISPLAY_TABLE[domain]
    items: list[dict[str, Any]] = []
    append_display_quality_item(items, domain, table, "display_unique_identity", uniqueness.get("duplicate_count", 0) == 0, "0", str(uniqueness.get("duplicate_count", 0)))
    append_display_quality_item(items, domain, table, "display_basis_trace_present", integrity.get("source_condition_basis_ids_missing", 0) == 0, "0", str(integrity.get("source_condition_basis_ids_missing", 0)))
    append_display_quality_item(items, domain, table, "display_condition_keys_parseable", integrity.get("selected_condition_keys_invalid", 0) == 0, "0", str(integrity.get("selected_condition_keys_invalid", 0)))
    append_display_quality_item(items, domain, table, "display_signal_types_parseable", integrity.get("selected_signal_types_invalid", 0) == 0, "0", str(integrity.get("selected_signal_types_invalid", 0)))
    append_display_quality_item(items, domain, table, "display_baseline_shape_valid", integrity.get("period_trigger_baseline_invalid_shape", 0) == 0, "0", str(integrity.get("period_trigger_baseline_invalid_shape", 0)))
    append_display_quality_item(items, domain, table, "display_clear_sell_alias_match", integrity.get("clear_sell_ref_period_mismatch", 0) == 0, "0", str(integrity.get("clear_sell_ref_period_mismatch", 0)))
    append_display_quality_item(items, domain, table, "display_reference_period_valid", integrity.get("invalid_reference_period", 0) == 0, "0", str(integrity.get("invalid_reference_period", 0)))
    append_display_quality_item(items, domain, table, "display_forbidden_fields_absent", forbidden.get("forbidden_field_count", 0) == 0, "0", str(forbidden.get("forbidden_field_count", 0)))
    append_display_quality_item(
        items,
        domain,
        table,
        "display_scope_trace_empty_explained",
        bool(traceability.get("source_minute_target_scope_ids_empty_explained", False)),
        "true",
        str(traceability.get("source_minute_target_scope_ids_empty_explained", False)).lower(),
        severity="P1",
    )
    return items


def append_display_quality_item(
    items: list[dict[str, Any]],
    domain: str,
    table_name: str,
    gate_code: str,
    passed: bool,
    expected: str,
    actual: str,
    *,
    severity: str = "P0",
) -> None:
    items.append(
        {
            "data_domain": domain,
            "table_name": table_name,
            "gate_code": gate_code,
            "gate_name": gate_code.replace("_", " "),
            "severity": severity,
            "status": "passed" if passed else "failed",
            "expected_value": expected,
            "actual_value": actual,
        }
    )


def display_write_quality_item(execute_run_id: str, row_counts: Mapping[str, int]) -> dict[str, Any]:
    expected = {
        "stock_condition_display_basis": int(row_counts.get("stock_condition_display_basis") or 0),
        "index_condition_display_basis": int(row_counts.get("index_condition_display_basis") or 0),
        "board_condition_display_basis": int(row_counts.get("board_condition_display_basis") or 0),
    }
    actual = {table: int(row_counts.get(table) or 0) for table in DISPLAY_TABLE.values()}
    return {
        "data_domain": "common",
        "table_name": "stock/index/board_condition_display_basis",
        "gate_code": "display_rows_written_matches_plan",
        "gate_name": "display rows written matches plan",
        "severity": "P0",
        "status": "passed" if expected == actual else "failed",
        "expected_value": json.dumps(expected, sort_keys=True),
        "actual_value": json.dumps(actual, sort_keys=True),
        "details": {"execute_run_id": execute_run_id},
    }


def insert_display_quality_items(
    cur: psycopg.Cursor[dict[str, Any]],
    *,
    execute_run_id: str,
    readiness_plan: Mapping[str, Any],
    display_quality_items: Sequence[Mapping[str, Any]],
) -> int:
    rows = [
        quality_row(
            execute_run_id,
            readiness_plan,
            item,
            stage_name="condition_display_basis",
            layer_scope="condition_display_basis",
        )
        for item in display_quality_items
    ]
    insert_rows(cur, "common_condition_quality_item", (
        "run_id",
        "for_trade_date",
        "source_trade_date",
        "data_domain",
        "layer_scope",
        "table_name",
        "gate_code",
        "gate_name",
        "severity",
        "status",
        "expected_value",
        "actual_value",
        "identity_key",
        "details",
    ), rows)
    return len(rows)


def expected_rows_with_display(
    expected_rows: Mapping[str, Mapping[str, Any]],
    *,
    display_quality_item_count: int,
    display_row_counts: Mapping[str, int],
) -> dict[str, Mapping[str, Any]]:
    expected = {table: dict(spec) for table, spec in expected_rows.items()}
    quality = dict(expected.get("common_condition_quality_item") or {"row_count": 0})
    quality["row_count"] = int(quality.get("row_count") or 0) + display_quality_item_count
    expected["common_condition_quality_item"] = quality
    expected["stock_condition_display_basis"] = {"row_count": int(display_row_counts.get("stock") or 0)}
    expected["index_condition_display_basis"] = {"row_count": int(display_row_counts.get("index") or 0)}
    expected["board_condition_display_basis"] = {"row_count": int(display_row_counts.get("board") or 0)}
    return expected


def verify_row_counts(row_counts: Mapping[str, int], expected_rows: Mapping[str, Mapping[str, Any]]) -> None:
    mismatches = {
        table: {"expected": int(spec.get("row_count") or 0), "actual": int(row_counts.get(table) or 0)}
        for table, spec in expected_rows.items()
        if int(spec.get("row_count") or 0) != int(row_counts.get(table) or 0)
    }
    if mismatches:
        raise ConditionExecuteError(f"post-write row count mismatch before commit: {mismatches}")


def update_condition_run_passed(cur: psycopg.Cursor[dict[str, Any]], execute_run_id: str) -> None:
    cur.execute(
        "UPDATE common_condition_run SET status = 'passed_active', finished_at = now(), updated_at = now() WHERE run_id = %s",
        (execute_run_id,),
    )


def fetch_post_execute_counts(dsn: str, execute_run_id: str) -> dict[str, Any]:
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn, conn.cursor() as cur:
        counts: dict[str, int] = {}
        for table in FULL_ROLLBACK_ORDER:
            where = "source_version = %s" if table in MONITOR_TABLE.values() else "run_id = %s"
            cur.execute(f"SELECT count(*)::bigint AS count FROM {table} WHERE {where}", (execute_run_id,))
            counts[table] = int(cur.fetchone()["count"])
        cur.execute("SELECT status, source_trade_date, for_trade_date FROM common_condition_run WHERE run_id = %s", (execute_run_id,))
        row = cur.fetchone()
        status = None if row is None else row["status"]
        canonical_active_count = 0
        legacy_active_count = 0
        if row is not None:
            cur.execute(
                """
                SELECT status, count(*)::bigint AS count
                FROM common_condition_run
                WHERE source_trade_date = %s
                  AND for_trade_date = %s
                  AND status IN (""" + active_status_sql_list() + """)
                GROUP BY status
                """,
                (row["source_trade_date"], row["for_trade_date"]),
            )
            for status_row in cur.fetchall():
                if status_row["status"] == CANONICAL_ACTIVE_STATUS:
                    canonical_active_count = int(status_row["count"])
                else:
                    legacy_active_count += int(status_row["count"])
    return {
        "run_status": status,
        "active_run_count": canonical_active_count + legacy_active_count,
        "canonical_active_run_count": canonical_active_count,
        "legacy_active_run_count": legacy_active_count,
        "row_counts": counts,
    }


def insert_rows(cur: psycopg.Cursor[dict[str, Any]], table: str, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    placeholders = ", ".join(f"%({column})s" for column in columns)
    column_sql = ", ".join(columns)
    cur.executemany(f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})", [dict(row) for row in rows])


def insert_rows_returning(
    cur: psycopg.Cursor[dict[str, Any]],
    table: str,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    returning_column: str,
) -> list[Mapping[str, Any]]:
    returned: list[Mapping[str, Any]] = []
    if not rows:
        return returned
    placeholders = ", ".join(f"%({column})s" for column in columns)
    column_sql = ", ".join(columns)
    sql = f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) RETURNING {returning_column}"
    for row in rows:
        cur.execute(sql, dict(row))
        returned.append(dict(cur.fetchone() or {}))
    return returned


def monitor_columns(domain: str) -> tuple[str, ...]:
    if domain == "stock":
        return (
            "for_trade_date",
            "source_trade_date",
            "stock_identity_key",
            "code",
            "exchange",
            "name",
            "monitor_type",
            "lane",
            "status",
            "direction_scope",
            "source",
            "source_version",
            "raw_json",
        )
    if domain == "index":
        return (
            "for_trade_date",
            "source_trade_date",
            "index_identity_key",
            "code",
            "exchange",
            "name",
            "monitor_type",
            "lane",
            "status",
            "direction_scope",
            "source",
            "source_version",
            "raw_json",
        )
    if domain == "board":
        return (
            "for_trade_date",
            "source_trade_date",
            "board_identity_key",
            "board_code",
            "board_name",
            "board_type",
            "monitor_type",
            "lane",
            "status",
            "direction_scope",
            "source",
            "source_version",
            "raw_json",
        )
    raise ValueError(f"unsupported domain: {domain}")


def execute_monitor_type(domain: str) -> str:
    if domain == "stock":
        return "stock_hint_monitor"
    if domain in {"index", "board"}:
        return "market_watch"
    raise ValueError(f"unsupported domain: {domain}")


def execute_lane(domain: str, row: Mapping[str, Any]) -> str:
    if domain == "stock":
        return str(row.get("lane") or "stock_alert")
    return "market_alert"


def row_identity(domain: str, row: Mapping[str, Any]) -> str:
    if domain == "stock":
        return str(row.get("stock_identity_key"))
    if domain == "index":
        return str(row.get("index_identity_key"))
    if domain == "board":
        return str(row.get("board_identity_key"))
    raise ValueError(f"unsupported domain: {domain}")


def basis_ref(domain: str, index: int, row: Mapping[str, Any]) -> str:
    return f"dry_run:{domain}:{index}:{row_identity(domain, row)}"


def first_active_run_id(active_status: Mapping[str, Any]) -> str | None:
    active_runs = list(active_status.get("active_runs") or [])
    if not active_runs:
        return None
    return str(active_runs[0].get("run_id"))


def jsonb(value: Any) -> Jsonb:
    return Jsonb(to_jsonable(value))


def jsonb_or_none(value: Any) -> Jsonb | None:
    if value is None:
        return None
    return jsonb(value)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Jsonb):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value
