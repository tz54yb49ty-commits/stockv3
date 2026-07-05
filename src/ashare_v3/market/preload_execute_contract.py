"""N3-A1 previous-day minute preload execute contract planner.

This preflight stage reads the N3-A0 dry-run report and the persisted N3-6
subscription control rows. It writes only contract/report files and rollback
SQL. It does not pull market data, write market facts, write event outbox rows,
or start workers.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.preload_plan import (
    EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
    MINUTE_FACT_TABLES,
    PRELOAD_STATUS_TABLES,
    build_persisted_subscription_report,
)
from ashare_v3.market.subscription_plan import ASSET_KINDS


DEFAULT_A0_REPORT_PATH = "docs/N3_A0_previous_day_minute_preload_dry_run.json"
DEFAULT_A1_CONTRACT_JSON_PATH = "docs/N3_A1_previous_day_minute_execute_contract.json"
DEFAULT_A1_CONTRACT_MD_PATH = "docs/N3_A1_PREVIOUS_DAY_MINUTE_EXECUTE_CONTRACT.md"
DEFAULT_A1_ROLLBACK_SQL_PATH = "sql/N3_A1_previous_day_minute_rollback.sql"
DEFAULT_A1_PREFLIGHT_JSON_PATH = "docs/N3_A1_previous_day_minute_execute_preflight.json"
DEFAULT_A1_PREFLIGHT_MD_PATH = "docs/N3_A1_PREVIOUS_DAY_MINUTE_EXECUTE_PREFLIGHT.md"

ALLOWED_A1_WRITE_TABLES = (
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_previous_day_minute_preload_status",
    "index_previous_day_minute_preload_status",
    "board_previous_day_minute_preload_status",
)

FORBIDDEN_A1_WRITE_TABLES = (
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "trigger tables",
    "action tables",
    "user tables",
    "voice/mobile/sim/position tables",
    "worker",
    "old system",
    "real trading",
)

ROLLBACK_DOWNSTREAM_REFERENCE_TABLES = (
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "common_trigger_run",
    "common_trigger_state",
    "common_trigger_match",
    "common_trigger_quality_item",
    "common_action_run",
    "common_action_event",
    "common_action_quality_item",
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card",
    "user_market_projection",
    "user_card_projection",
    "user_voice_delivery",
    "user_notification_queue",
    "sim_projection",
    "position_projection",
    "real_trade_order",
    "user_sim_order",
    "user_sim_trade",
    "user_sim_position",
    "n6_virtual_account",
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_position",
    "n6_virtual_position_event",
    "n6_virtual_pnl_snapshot",
    "stock_closed_30m_summary",
    "index_closed_30m_summary",
    "board_closed_30m_summary",
    "stock_closed_30m_signal_enrichment",
    "index_closed_30m_signal_enrichment",
    "board_closed_30m_signal_enrichment",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "stock_projection_enrichment_v4_metric",
    "index_projection_enrichment_v4_metric",
    "board_projection_enrichment_v4_metric",
    "stock_action_confirmation_projection_metric",
    "index_action_confirmation_projection_metric",
    "board_action_confirmation_projection_metric",
)


def build_previous_day_minute_execute_contract(
    *,
    dsn: str,
    market_data_run_id: str,
    a0_report_path: str = DEFAULT_A0_REPORT_PATH,
    contract_json_path: str = DEFAULT_A1_CONTRACT_JSON_PATH,
    contract_markdown_path: str = DEFAULT_A1_CONTRACT_MD_PATH,
    rollback_sql_path: str = DEFAULT_A1_ROLLBACK_SQL_PATH,
    preflight_json_path: str = DEFAULT_A1_PREFLIGHT_JSON_PATH,
    preflight_markdown_path: str = DEFAULT_A1_PREFLIGHT_MD_PATH,
    preload_run_id: str | None = None,
) -> dict[str, Any]:
    a0_report = read_json(a0_report_path)
    persisted_report = build_persisted_subscription_report(dsn=dsn, market_data_run_id=market_data_run_id)
    contract = build_execute_contract_from_reports(
        a0_report=a0_report,
        persisted_report=persisted_report,
        market_data_run_id=market_data_run_id,
        preload_run_id=preload_run_id,
        contract_json_path=contract_json_path,
        rollback_sql_path=rollback_sql_path,
    )
    rollback_sql = format_previous_day_minute_rollback_sql(contract)
    rollback_touches_outbox = rollback_sql_touches_event_outbox(rollback_sql)
    rollback_check = quality_item(
        "P0",
        "passed" if not rollback_touches_outbox else "failed",
        "n3_a1_rollback_sql_does_not_touch_event_outbox",
        "N3-A1 rollback SQL must not touch common_event_outbox",
        expected="no DML against common_event_outbox",
        actual="absent" if not rollback_touches_outbox else "present",
    )
    contract["quality"]["items"].append(rollback_check)
    contract["quality"] = summarize_quality(contract["quality"]["items"])

    write_text(rollback_sql_path, rollback_sql)
    write_json(contract_json_path, contract)
    write_text(contract_markdown_path, format_previous_day_minute_execute_contract_markdown(contract))
    baseline = fetch_previous_day_minute_execute_baseline(dsn=dsn, contract=contract)
    preflight = build_execute_preflight_from_contract(contract, baseline)
    write_json(preflight_json_path, preflight)
    write_text(preflight_markdown_path, format_previous_day_minute_execute_preflight_markdown(preflight))
    return contract


def build_execute_contract_from_reports(
    *,
    a0_report: Mapping[str, Any],
    persisted_report: Mapping[str, Any],
    market_data_run_id: str,
    preload_run_id: str | None = None,
    contract_json_path: str = DEFAULT_A1_CONTRACT_JSON_PATH,
    rollback_sql_path: str = DEFAULT_A1_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    expected_date = str(a0_report.get("expected_previous_day_minute_date") or a0_report.get("prev_trade_date") or "")
    resolved_preload_run_id = preload_run_id or derive_preload_run_id(a0_report, market_data_run_id)
    expected_asset_counts = build_expected_asset_counts(a0_report)
    target_tables = build_target_tables()
    source_adapter_plan = build_source_adapter_plan(a0_report)
    post_execute_quality_gates = build_post_execute_quality_gates(a0_report)
    preflight_quality = build_preflight_quality_items(
        a0_report=a0_report,
        persisted_report=persisted_report,
        market_data_run_id=market_data_run_id,
        preload_run_id=resolved_preload_run_id,
        expected_asset_counts=expected_asset_counts,
        target_tables=target_tables,
        source_adapter_plan=source_adapter_plan,
        previous_day_minute_date=expected_date,
    )
    quality = summarize_quality(preflight_quality)
    return {
        "stage": "N3-A1-preflight",
        "layer_role": "N3_market_data",
        "execution_mode": "previous_day_minute_preload_execute_contract",
        "generated_at": utc_now_iso(),
        "source_run_id": market_data_run_id,
        "source_subscription_run_id": market_data_run_id,
        "market_data_run_id": market_data_run_id,
        "contract_json_path": contract_json_path,
        "preload_run_id": resolved_preload_run_id,
        "source_condition_run_id": a0_report.get("source_condition_run_id"),
        "for_trade_date": a0_report.get("for_trade_date"),
        "source_trade_date": a0_report.get("source_trade_date"),
        "previous_day_minute_date": expected_date,
        "data_trade_date": expected_date,
        "required_data_kind": "previous_day_minute_bar_1m",
        "historical_preload": True,
        "target_tables": target_tables,
        "expected_asset_counts": expected_asset_counts,
        "expected_row_count": int(a0_report.get("estimated_minute_bar_row_count") or 0),
        "expected_bar_count_per_object": int(a0_report.get("expected_minute_bar_count_per_object") or EXPECTED_A_SHARE_MINUTE_BAR_COUNT),
        "source_adapter_plan": source_adapter_plan,
        "idempotency_policy": build_idempotency_policy(resolved_preload_run_id, market_data_run_id),
        "overwrite_policy": build_overwrite_policy(),
        "writes_outbox": False,
        "writes_event_outbox": False,
        "rollback_sql_path": rollback_sql_path,
        "rollback_policy": {
            "delete_by": ["source_run_id", "preload_run_id"],
            "requires_raw_json_source_run_id": True,
            "touches_event_outbox": False,
            "hard_fail_before_delete": True,
            "hard_fail_guards": [
                "common_event_outbox source_run_id/payload_json refs",
                "common_event_inbox source_run_id/payload_json/raw_json refs",
                "common_event_consumer_checkpoint last_event_id/checkpoint_payload refs",
                "common_market_data_run downstream_layers_touched/worker_started flags",
                "N4/N5/N6 downstream refs",
                "C2 closed summary refs",
                "closed signal enrichment refs",
                "realtime projection refs",
                "action-confirmation projection refs",
            ],
        },
        "post_execute_quality_gates": post_execute_quality_gates,
        "quality": quality,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def derive_preload_run_id(a0_report: Mapping[str, Any], source_run_id: str) -> str:
    previous_day = str(a0_report.get("expected_previous_day_minute_date") or a0_report.get("prev_trade_date") or "")
    for_trade_date = str(a0_report.get("for_trade_date") or "")
    return f"previous_day_minute_preload_{previous_day}_for_{for_trade_date}__{source_run_id}"


def build_expected_asset_counts(a0_report: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    object_counts = a0_report.get("previous_day_minute_object_count_by_asset_kind") or {}
    row_counts = a0_report.get("estimated_minute_bar_row_count_by_asset_kind") or {}
    adapter_rows = (a0_report.get("source_adapter_plan") or {}).get("rows") or []
    subscription_counts = {str(row.get("asset_kind")): int(row.get("subscription_count") or 0) for row in adapter_rows}
    output: dict[str, dict[str, int]] = {}
    for asset_kind in ASSET_KINDS:
        object_count = int(object_counts.get(asset_kind) or 0)
        output[asset_kind] = {
            "object_count": object_count,
            "subscription_count": int(subscription_counts.get(asset_kind, object_count)),
            "expected_minute_bar_rows": int(row_counts.get(asset_kind) or object_count * EXPECTED_A_SHARE_MINUTE_BAR_COUNT),
            "expected_bar_count_per_object": EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
        }
    return output


def build_target_tables() -> dict[str, dict[str, str]]:
    identity_columns = {
        "stock": "stock_identity_key",
        "index": "index_identity_key",
        "board": "board_identity_key",
    }
    return {
        asset_kind: {
            "minute_fact_table": MINUTE_FACT_TABLES[asset_kind],
            "preload_status_table": PRELOAD_STATUS_TABLES[asset_kind],
            "identity_column": identity_columns[asset_kind],
        }
        for asset_kind in ASSET_KINDS
    }


def build_source_adapter_plan(a0_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = (a0_report.get("source_adapter_plan") or {}).get("rows") or []
    output: list[dict[str, Any]] = []
    for row in rows:
        output.append(
            {
                "asset_kind": row.get("asset_kind"),
                "source_pull_plan_id": row.get("source_pull_plan_id"),
                "adapter_name": row.get("adapter_name"),
                "previous_day_minute_date": row.get("previous_day_minute_date"),
                "subscription_count": row.get("subscription_count"),
                "object_count": row.get("object_count"),
                "expected_minute_bar_rows": row.get("expected_minute_bar_rows"),
                "target_minute_fact_table": row.get("target_minute_fact_table"),
                "target_preload_status_table": row.get("target_preload_status_table"),
                "adapter_call_planned_in_preflight": False,
            }
        )
    return sorted(output, key=lambda item: str(item.get("asset_kind")))


def build_idempotency_policy(preload_run_id: str, source_run_id: str) -> dict[str, Any]:
    return {
        "preload_run_id": preload_run_id,
        "source_run_id": source_run_id,
        "execute_runner": "scripts/run_previous_day_minute_preload_execute.py",
        "execute_requires_flags": ["--execute", "--user-confirmed"],
        "minute_fact_unique_keys": {
            asset_kind: ["run_id", "trade_date", f"{asset_kind}_identity_key", "bar_time", "source_adapter"]
            for asset_kind in ASSET_KINDS
        },
        "preload_status_unique_keys": {
            asset_kind: ["run_id", "trade_date", f"{asset_kind}_identity_key", "source_adapter"]
            for asset_kind in ASSET_KINDS
        },
        "required_trace_fields": {
            "raw_json.source_run_id": source_run_id,
            "raw_json.preload_run_id": preload_run_id,
            "raw_json.required_data_kind": "previous_day_minute_bar_1m",
        },
        "repeat_execute_same_preload_run_id": "upsert_or_noop_by_unique_key_after validating same source_run_id",
        "repeat_execute_different_preload_run_id": "allowed only after explicit user confirmation and separate rollback scope",
    }


def build_overwrite_policy() -> dict[str, Any]:
    return {
        "default": "no_silent_overwrite",
        "same_key_same_payload_hash": "noop",
        "same_key_different_payload_hash": "P0_block unless explicit correction mode is requested later",
        "existing_rows_for_preload_run_id": "must run rollback or idempotent verification before retry",
        "missing_objects": "record quality item; P1/P2 allowed by configured threshold, never silently pass",
        "writes_outbox": False,
    }


def build_post_execute_quality_gates(a0_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_asset_counts = build_expected_asset_counts(a0_report)
    total_expected = int(a0_report.get("estimated_minute_bar_row_count") or 0)
    gates = [
        {
            "gate_code": "n3_a1_asset_object_count_matches_a0",
            "severity": "P0",
            "expected": expected_asset_counts,
            "rule": "stock/index/board preload_status object_count must match A0 expected asset counts",
        },
        {
            "gate_code": "n3_a1_minute_rows_reasonable",
            "severity": "P0",
            "expected": {
                "min_total_rows": 0,
                "max_total_rows": total_expected,
                "expected_full_total_rows": total_expected,
                "expected_bar_count_per_object": EXPECTED_A_SHARE_MINUTE_BAR_COUNT,
            },
            "rule": "actual minute rows must be non-negative and not exceed expected A-share minute rows; missing/partial rows must create quality items",
        },
        {
            "gate_code": "n3_a1_duplicate_minute_key_zero",
            "severity": "P0",
            "expected": 0,
            "rule": "duplicate key (run_id, trade_date, identity_key, bar_time, source_adapter) must be zero in each physical minute table",
        },
        {
            "gate_code": "n3_a1_missing_object_not_silent",
            "severity": "P1/P2",
            "expected": "missing_object_count=0 or quality_item recorded",
            "rule": "missing object can be P1/P2 by threshold, but cannot pass without preload_status and quality_item evidence",
        },
        {
            "gate_code": "n3_a1_physical_table_isolation",
            "severity": "P0",
            "expected": "stock rows only in stock tables; index rows only in index tables; board rows only in board tables",
            "rule": "identity_key prefix must match physical table family",
        },
        {
            "gate_code": "n3_a1_outbox_rows_zero",
            "severity": "P0",
            "expected": 0,
            "rule": "N3-A1 previous-day preload writes_outbox=false; common_event_outbox must not receive rows",
        },
    ]
    return gates


def build_preflight_quality_items(
    *,
    a0_report: Mapping[str, Any],
    persisted_report: Mapping[str, Any],
    market_data_run_id: str,
    preload_run_id: str,
    expected_asset_counts: Mapping[str, Mapping[str, int]],
    target_tables: Mapping[str, Mapping[str, str]],
    source_adapter_plan: Sequence[Mapping[str, Any]],
    previous_day_minute_date: str,
) -> list[dict[str, Any]]:
    a0_quality = a0_report.get("quality") or {}
    persisted_quality = persisted_report.get("quality") or {}
    a0_asset_counts = a0_report.get("previous_day_minute_object_count_by_asset_kind") or {}
    persisted_previous_rows = previous_day_rows_from_persisted_report(persisted_report)
    persisted_asset_counts = Counter(str(row.get("asset_kind")) for row in persisted_previous_rows)
    runtime_tables = [
        table
        for tables in target_tables.values()
        for table in (tables.get("minute_fact_table"), tables.get("preload_status_table"))
        if table and "_runtime" in table
    ]
    outbox_targets = [
        table
        for tables in target_tables.values()
        for table in (tables.get("minute_fact_table"), tables.get("preload_status_table"))
        if table == "common_event_outbox"
    ]
    adapter_asset_kinds = {str(row.get("asset_kind")) for row in source_adapter_plan}
    required_adapter_asset_kinds = {
        asset_kind
        for asset_kind in ASSET_KINDS
        if int((expected_asset_counts.get(asset_kind) or {}).get("object_count") or 0) > 0
    }
    items = [
        quality_item(
            "P0",
            "passed" if a0_report.get("stage") == "N3-A0" else "failed",
            "n3_a1_a0_report_stage_valid",
            "N3-A1-preflight must consume an N3-A0 dry-run report",
            expected="N3-A0",
            actual=str(a0_report.get("stage")),
        ),
        quality_item(
            "P0",
            "passed" if int(a0_quality.get("p0_count") or 0) == 0 and not a0_report.get("blocked") else "failed",
            "n3_a1_a0_report_p0_zero",
            "N3-A1-preflight requires A0 P0=0 and blocked=false",
            expected="P0=0 blocked=false",
            actual=f"P0={a0_quality.get('p0_count')} blocked={a0_report.get('blocked')}",
        ),
        quality_item(
            "P1",
            "warning" if int(a0_quality.get("p1_count") or 0) > 0 else "passed",
            "n3_a1_a0_p1_carried",
            "N3-A1-preflight carries non-blocking A0 P1 items",
            expected="0",
            actual=str(a0_quality.get("p1_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if persisted_report.get("market_data_run_id") == market_data_run_id else "failed",
            "n3_a1_source_run_id_matches_n3_6",
            "contract source_run_id must match the persisted N3-6 market_data_run_id",
            expected=market_data_run_id,
            actual=str(persisted_report.get("market_data_run_id")),
        ),
        quality_item(
            "P0",
            "passed" if int(persisted_quality.get("p0_count") or 0) == 0 and persisted_report.get("passed") else "failed",
            "n3_a1_n3_6_source_p0_zero",
            "N3-A1-preflight requires persisted N3-6 subscription run P0=0",
            expected="P0=0 passed=true",
            actual=f"P0={persisted_quality.get('p0_count')} passed={persisted_report.get('passed')}",
        ),
        quality_item(
            "P0",
            "passed" if previous_day_minute_date == str(a0_report.get("prev_trade_date")) else "failed",
            "n3_a1_previous_day_minute_date_matches_prev_trade_date",
            "contract previous_day_minute_date must match A0 prev_trade_date",
            expected=str(a0_report.get("prev_trade_date")),
            actual=previous_day_minute_date,
        ),
        quality_item(
            "P0",
            "passed" if preload_run_id and preload_run_id != market_data_run_id else "failed",
            "n3_a1_preload_run_id_distinct",
            "preload_run_id must be present and distinct from source_run_id",
            expected="distinct non-empty preload_run_id",
            actual=preload_run_id,
        ),
        quality_item(
            "P0",
            "passed" if asset_counts_match(a0_asset_counts, persisted_asset_counts) else "failed",
            "n3_a1_asset_counts_match_n3_6",
            "A0 stock/index/board object counts must match persisted N3-6 previous-day subscriptions",
            expected=str({asset: int(a0_asset_counts.get(asset) or 0) for asset in ASSET_KINDS}),
            actual=str({asset: int(persisted_asset_counts.get(asset) or 0) for asset in ASSET_KINDS}),
        ),
        quality_item(
            "P0",
            "passed" if adapter_asset_kinds == required_adapter_asset_kinds else "failed",
            "n3_a1_source_adapter_plan_covers_assets",
            "source_adapter_plan must cover exactly the asset kinds with previous-day minute objects",
            expected=",".join(asset for asset in ASSET_KINDS if asset in required_adapter_asset_kinds),
            actual=",".join(asset for asset in ASSET_KINDS if asset in adapter_asset_kinds),
        ),
        quality_item(
            "P0",
            "passed" if not runtime_tables else "failed",
            "n3_a1_target_tables_no_runtime_names",
            "N3-A1 target tables must not use *_runtime table names",
            expected="no *_runtime target table",
            actual="none" if not runtime_tables else ",".join(runtime_tables),
        ),
        quality_item(
            "P0",
            "passed" if not outbox_targets else "failed",
            "n3_a1_target_tables_no_outbox",
            "N3-A1 target tables must not include common_event_outbox",
            expected="common_event_outbox absent",
            actual="absent" if not outbox_targets else ",".join(outbox_targets),
        ),
        quality_item(
            "P0",
            "passed",
            "n3_a1_contract_writes_outbox_false",
            "N3-A1 execute contract sets writes_outbox=false",
            expected="false",
            actual="false",
        ),
        quality_item(
            "P0",
            "passed",
            "n3_a1_preflight_no_market_pull_or_write",
            "N3-A1-preflight does not pull market data or write market facts",
        ),
    ]
    _ = expected_asset_counts
    return items


def previous_day_rows_from_persisted_report(persisted_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in (persisted_report.get("market_data_subscription_dedup") or {}).get("rows", [])
        if row.get("required_data_kind") == "previous_day_minute_bar_1m"
    ]


def asset_counts_match(expected: Mapping[str, Any], actual: Mapping[str, int]) -> bool:
    return all(int(expected.get(asset) or 0) == int(actual.get(asset) or 0) for asset in ASSET_KINDS)


def summarize_quality(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = count_quality_severities(list(items))
    return {
        "p0_count": counts["P0"],
        "p1_count": counts["P1"],
        "p2_count": counts["P2"],
        "items": list(items),
    }


def format_previous_day_minute_rollback_sql(contract: Mapping[str, Any]) -> str:
    source_run_id = sql_literal(str(contract["source_run_id"]))
    preload_run_id = sql_literal(str(contract["preload_run_id"]))
    previous_day = sql_literal(str(contract["previous_day_minute_date"]))
    preload_run_id_text = str(contract["preload_run_id"])
    preload_run_id_do_literal = sql_literal(preload_run_id_text)
    target_tables = contract["target_tables"]
    source_condition_run_id = sql_literal(str(contract["source_condition_run_id"]))
    downstream_table_lines = [
        f"    {sql_literal(table_name)}{',' if index < len(ROLLBACK_DOWNSTREAM_REFERENCE_TABLES) - 1 else ''}"
        for index, table_name in enumerate(ROLLBACK_DOWNSTREAM_REFERENCE_TABLES)
    ]
    lines = [
        "-- N3-A1 previous_day_minute_bar_1m rollback plan.",
        "-- Review before execution. Generated by N3-A1-preflight; not executed in preflight.",
        "-- Scope: N3 previous-day minute preload rows only. It intentionally does not write or delete event infrastructure.",
        "",
        "\\set ON_ERROR_STOP on",
        f"\\set source_run_id {source_run_id}",
        f"\\set preload_run_id {preload_run_id}",
        f"\\set previous_day_minute_date {previous_day}",
        f"\\set source_condition_run_id {source_condition_run_id}",
        "",
        "BEGIN;",
        "",
        "DO $$",
        "DECLARE",
        f"  v_preload_run_id TEXT := {preload_run_id_do_literal};",
        "  v_count BIGINT;",
        "  v_table TEXT;",
        "BEGIN",
        "  SELECT count(*) INTO v_count",
        "  FROM common_market_data_run",
        "  WHERE run_id = v_preload_run_id",
        "    AND (downstream_layers_touched = true OR worker_started = true);",
        "",
        "  IF v_count <> 0 THEN",
        "    RAISE EXCEPTION 'Refusing N3-A1 rollback: common_market_data_run has downstream/worker flags for %', v_preload_run_id;",
        "  END IF;",
        "",
        "  SELECT count(*) INTO v_count",
        "  FROM common_event_outbox",
        "  WHERE source_run_id = v_preload_run_id",
        "     OR payload_json::TEXT LIKE '%' || v_preload_run_id || '%';",
        "",
        "  IF v_count <> 0 THEN",
        "    RAISE EXCEPTION 'Refusing N3-A1 rollback: common_event_outbox has % rows for %', v_count, v_preload_run_id;",
        "  END IF;",
        "",
        "  SELECT count(*) INTO v_count",
        "  FROM common_event_inbox",
        "  WHERE source_run_id = v_preload_run_id",
        "     OR payload_json::TEXT LIKE '%' || v_preload_run_id || '%'",
        "     OR raw_json::TEXT LIKE '%' || v_preload_run_id || '%';",
        "",
        "  IF v_count <> 0 THEN",
        "    RAISE EXCEPTION 'Refusing N3-A1 rollback: common_event_inbox has % rows for %', v_count, v_preload_run_id;",
        "  END IF;",
        "",
        "  SELECT count(*) INTO v_count",
        "  FROM common_event_consumer_checkpoint",
        "  WHERE checkpoint_payload::TEXT LIKE '%' || v_preload_run_id || '%'",
        "     OR last_event_id LIKE '%' || v_preload_run_id || '%';",
        "",
        "  IF v_count <> 0 THEN",
        "    RAISE EXCEPTION 'Refusing N3-A1 rollback: common_event_consumer_checkpoint references % in % rows', v_preload_run_id, v_count;",
        "  END IF;",
        "",
        "  FOREACH v_table IN ARRAY ARRAY[",
        *downstream_table_lines,
        "  ] LOOP",
        "    IF to_regclass('public.' || v_table) IS NOT NULL THEN",
        "      EXECUTE format('SELECT count(*) FROM %I t WHERE row_to_json(t)::TEXT LIKE ''%%'' || $1 || ''%%''', v_table)",
        "        INTO v_count",
        "        USING v_preload_run_id;",
        "",
        "      IF v_count <> 0 THEN",
        "        RAISE EXCEPTION 'Refusing N3-A1 rollback: downstream table % references % in % rows', v_table, v_preload_run_id, v_count;",
        "      END IF;",
        "    END IF;",
        "  END LOOP;",
        "END $$;",
        "",
    ]
    for asset_kind in ASSET_KINDS:
        status_table = target_tables[asset_kind]["preload_status_table"]
        minute_table = target_tables[asset_kind]["minute_fact_table"]
        identity_column = target_tables[asset_kind]["identity_column"]
        lines.extend(
            [
                f"DELETE FROM {status_table}",
                "WHERE run_id = :'preload_run_id'",
                "  AND trade_date = :'previous_day_minute_date'",
                "  AND source_condition_run_id = :'source_condition_run_id'",
                "  AND raw_json ->> 'source_run_id' = :'source_run_id'",
                "  AND raw_json ->> 'preload_run_id' = :'preload_run_id';",
                "",
                f"DELETE FROM {minute_table}",
                "WHERE run_id = :'preload_run_id'",
                "  AND trade_date = :'previous_day_minute_date'",
                "  AND source_condition_run_id = :'source_condition_run_id'",
                "  AND is_previous_day_preload = true",
                f"  AND {identity_column} LIKE '{asset_kind}:%'",
                "  AND raw_json ->> 'source_run_id' = :'source_run_id'",
                "  AND raw_json ->> 'preload_run_id' = :'preload_run_id';",
                "",
            ]
        )
    lines.extend(
        [
            "DELETE FROM common_market_data_quality_item",
            "WHERE run_id = :'preload_run_id'",
            "  AND source_condition_run_id = :'source_condition_run_id'",
            "  AND details ->> 'source_run_id' = :'source_run_id'",
            "  AND details ->> 'preload_run_id' = :'preload_run_id';",
            "",
            "DELETE FROM common_market_data_run",
            "WHERE run_id = :'preload_run_id'",
            "  AND source_condition_run_id = :'source_condition_run_id'",
            "  AND raw_json ->> 'source_run_id' = :'source_run_id'",
            "  AND raw_json ->> 'preload_run_id' = :'preload_run_id'",
            "  AND downstream_layers_touched = false",
            "  AND worker_started = false;",
            "",
            "COMMIT;",
            "",
        ]
    )
    return "\n".join(lines)


def fetch_previous_day_minute_execute_baseline(*, dsn: str, contract: Mapping[str, Any]) -> dict[str, int]:
    preload_run_id = str(contract["preload_run_id"])
    previous_day = str(contract["previous_day_minute_date"])
    target_tables = contract["target_tables"]
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        baseline: dict[str, int] = {
            "common_market_data_run": count_where(cur, "common_market_data_run", "run_id = %s", (preload_run_id,)),
            "common_market_data_quality_item": count_where(cur, "common_market_data_quality_item", "run_id = %s", (preload_run_id,)),
            "common_event_outbox": count_where(cur, "common_event_outbox", "source_run_id = %s", (preload_run_id,)),
            "common_event_inbox": count_where(cur, "common_event_inbox", "source_run_id = %s", (preload_run_id,)),
            "common_event_consumer_checkpoint": count_where(
                cur,
                "common_event_consumer_checkpoint",
                "checkpoint_payload::TEXT LIKE %s",
                (f"%{preload_run_id}%",),
            ),
        }
        for asset_kind in ASSET_KINDS:
            minute_table = target_tables[asset_kind]["minute_fact_table"]
            status_table = target_tables[asset_kind]["preload_status_table"]
            baseline[minute_table] = count_where(
                cur,
                minute_table,
                "run_id = %s AND trade_date = %s AND is_previous_day_preload = true",
                (preload_run_id, previous_day),
            )
            baseline[status_table] = count_where(
                cur,
                status_table,
                "run_id = %s AND trade_date = %s",
                (preload_run_id, previous_day),
            )
    return baseline


def count_where(cur: Any, table_name: str, where_clause: str, params: Sequence[Any]) -> int:
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table_name} WHERE {where_clause}", tuple(params))
    return int(cur.fetchone()["row_count"])


def build_execute_preflight_from_contract(
    contract: Mapping[str, Any],
    baseline_counts: Mapping[str, Any],
) -> dict[str, Any]:
    scoped_rows = {key: int(value or 0) for key, value in baseline_counts.items()}
    total_scoped_rows = sum(scoped_rows.values())
    items = [
        quality_item(
            "P0",
            "passed" if contract.get("stage") == "N3-A1-preflight" else "failed",
            "n3_a1_contract_stage_valid",
            "N3-A1 execute preflight must consume an N3-A1 execute contract",
            expected="N3-A1-preflight",
            actual=str(contract.get("stage")),
        ),
        quality_item(
            "P0",
            "passed" if int((contract.get("quality") or {}).get("p0_count") or 0) == 0 else "failed",
            "n3_a1_contract_p0_zero",
            "N3-A1 execute preflight requires contract P0=0",
            expected="0",
            actual=str((contract.get("quality") or {}).get("p0_count")),
        ),
        quality_item(
            "P0",
            "passed" if total_scoped_rows == 0 else "failed",
            "n3_a1_preload_scoped_baseline_zero",
            "N3-A1 execute target run must not already have run/quality/fact/status/event refs",
            expected="0",
            actual=str(total_scoped_rows),
            details={"scoped_rows": scoped_rows},
        ),
        quality_item(
            "P0",
            "passed" if contract.get("writes_outbox") is False else "failed",
            "n3_a1_preflight_writes_outbox_false",
            "N3-A1 previous-day preload must not write common_event_outbox",
            expected="false",
            actual=str(contract.get("writes_outbox")).lower(),
        ),
        quality_item(
            "P0",
            "passed",
            "n3_a1_preflight_no_execute_authorization",
            "This preflight artifact is not execute authorization",
            expected="execute_authorized=false",
            actual="false",
        ),
    ]
    quality = summarize_quality(items)
    result = "PREFLIGHT_PASS" if quality["p0_count"] == 0 else "PREFLIGHT_BLOCKED"
    contract_json_path = str(contract.get("contract_json_path") or DEFAULT_A1_CONTRACT_JSON_PATH)
    return {
        "stage": "N3-A1-execute-preflight",
        "layer_role": "N3_market_data",
        "result": result,
        "generated_at": utc_now_iso(),
        "source_run_id": contract.get("source_run_id"),
        "source_subscription_run_id": contract.get("source_subscription_run_id") or contract.get("source_run_id"),
        "market_data_run_id": contract.get("market_data_run_id"),
        "preload_run_id": contract.get("preload_run_id"),
        "source_condition_run_id": contract.get("source_condition_run_id"),
        "for_trade_date": contract.get("for_trade_date"),
        "previous_day_minute_date": contract.get("previous_day_minute_date"),
        "data_trade_date": contract.get("data_trade_date") or contract.get("previous_day_minute_date"),
        "required_data_kind": contract.get("required_data_kind") or "previous_day_minute_bar_1m",
        "historical_preload": bool(contract.get("historical_preload", True)),
        "contract_json_path": contract.get("contract_json_path"),
        "expected_asset_counts": contract.get("expected_asset_counts"),
        "expected_row_count": contract.get("expected_row_count"),
        "expected_bar_count_per_object": contract.get("expected_bar_count_per_object"),
        "source_adapter_plan": contract.get("source_adapter_plan"),
        "baseline": {
            "scoped_rows": scoped_rows | {"total": total_scoped_rows},
            "requires_zero_before_execute": True,
        },
        "execute_runner": "scripts/run_previous_day_minute_preload_execute.py",
        "execute_requires_flags": ["--execute", "--user-confirmed"],
        "execute_command_template": (
            "PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py "
            f"--contract-path {contract_json_path} "
            "--historical-preload "
            f"--source-subscription-run-id {contract.get('source_subscription_run_id') or contract.get('source_run_id')} "
            f"--preload-run-id {contract.get('preload_run_id')} "
            f"--data-trade-date {contract.get('data_trade_date') or contract.get('previous_day_minute_date')} "
            "--execute --user-confirmed"
        ),
        "future_write_scope": {
            "allowed_tables": list(ALLOWED_A1_WRITE_TABLES),
            "forbidden_tables": list(FORBIDDEN_A1_WRITE_TABLES),
        },
        "execute_authorized": False,
        "execute_final_gate_required": True,
        "writes_outbox": False,
        "rollback_sql_path": contract.get("rollback_sql_path"),
        "rollback_guard": {
            "hard_fail_before_first_delete": True,
            "common_event_outbox_source_run_id_or_payload_refs": "must be 0",
            "common_event_inbox_source_run_id_or_payload_refs": "must be 0",
            "common_event_consumer_checkpoint_refs": "must be 0",
            "common_market_data_run_downstream_or_worker_flags": "must be 0 before any DELETE",
            "downstream_trigger_action_user_refs": "must be 0 before any DELETE",
            "c2_closed_summary_refs": "must be 0 before any DELETE",
            "closed_signal_enrichment_refs": "must be 0 before any DELETE",
            "realtime_projection_refs": "must be 0 before any DELETE",
            "action_confirmation_projection_refs": "must be 0 before any DELETE",
        },
        "quality": quality,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "market_data_fact_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def rollback_sql_touches_event_outbox(sql_text: str) -> bool:
    lowered = sql_text.lower()
    forbidden_snippets = (
        "delete from common_event_outbox",
        "insert into common_event_outbox",
        "update common_event_outbox",
        "truncate common_event_outbox",
    )
    return any(snippet in lowered for snippet in forbidden_snippets)


def format_previous_day_minute_execute_contract_markdown(contract: Mapping[str, Any]) -> str:
    quality = contract["quality"]
    lines = [
        "# N3-A1 Previous-Day Minute Execute Contract",
        "",
        "## Summary",
        "",
        f"- stage: `{contract['stage']}`",
        f"- layer_role: `{contract['layer_role']}`",
        f"- source_run_id: `{contract['source_run_id']}`",
        f"- preload_run_id: `{contract['preload_run_id']}`",
        f"- source_condition_run_id: `{contract['source_condition_run_id']}`",
        f"- for_trade_date: `{contract['for_trade_date']}`",
        f"- previous_day_minute_date: `{contract['previous_day_minute_date']}`",
        f"- expected_row_count: `{contract['expected_row_count']}`",
        f"- writes_outbox: `{contract['writes_outbox']}`",
        f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
        "",
        "## Expected Asset Counts",
        "",
    ]
    for asset_kind, counts in contract["expected_asset_counts"].items():
        lines.append(
            f"- {asset_kind}: objects=`{counts['object_count']}` subscriptions=`{counts['subscription_count']}` "
            f"expected_minute_rows=`{counts['expected_minute_bar_rows']}`"
        )
    lines.extend(["", "## Target Tables", ""])
    for asset_kind, tables in contract["target_tables"].items():
        lines.append(
            f"- {asset_kind}: minute_fact=`{tables['minute_fact_table']}` preload_status=`{tables['preload_status_table']}`"
        )
    lines.extend(["", "## Source Adapter Plan", ""])
    for row in contract["source_adapter_plan"]:
        lines.append(
            f"- {row['asset_kind']}: adapter=`{row['adapter_name']}` source_pull_plan_id=`{row['source_pull_plan_id']}` "
            f"objects=`{row['object_count']}` expected_rows=`{row['expected_minute_bar_rows']}`"
        )
    lines.extend(
        [
            "",
            "## Policies",
            "",
            f"- idempotency_policy: `{contract['idempotency_policy']['repeat_execute_same_preload_run_id']}`",
            f"- execute_runner: `{contract['idempotency_policy']['execute_runner']}`",
            f"- execute_requires_flags: `{', '.join(contract['idempotency_policy']['execute_requires_flags'])}`",
            f"- overwrite_policy: `{contract['overwrite_policy']['default']}`",
            f"- rollback_sql_path: `{contract['rollback_sql_path']}`",
            f"- rollback_touches_event_outbox: `{contract['rollback_policy']['touches_event_outbox']}`",
            "",
            "## Post-Execute Quality Gates",
            "",
        ]
    )
    for gate in contract["post_execute_quality_gates"]:
        lines.append(f"- {gate['severity']} {gate['gate_code']}: {gate['rule']}")
    lines.extend(["", "## Preflight Quality", ""])
    for item in quality["items"]:
        lines.append(
            f"- {item.get('severity')} {item.get('status')} {item.get('gate_code')}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(["", "## Boundary", ""])
    for key, value in contract["side_effects"].items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.extend(
        [
            "",
            "## Rollback",
            "",
            f"Rollback SQL was generated at `{contract['rollback_sql_path']}`. It deletes rows by `source_run_id` and `preload_run_id` and does not touch `common_event_outbox`.",
            "",
        ]
    )
    return "\n".join(lines)


def format_previous_day_minute_execute_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    quality = preflight["quality"]
    baseline = preflight.get("baseline") or {}
    scoped_rows = baseline.get("scoped_rows") or {}
    write_scope = preflight.get("future_write_scope") or {}
    lines = [
        "# N3-A1 Previous-Day Minute Execute Preflight",
        "",
        "## Summary",
        "",
        f"- result: `{preflight['result']}`",
        f"- stage: `{preflight['stage']}`",
        f"- layer_role: `{preflight['layer_role']}`",
        f"- source_run_id: `{preflight['source_run_id']}`",
        f"- preload_run_id: `{preflight['preload_run_id']}`",
        f"- source_condition_run_id: `{preflight['source_condition_run_id']}`",
        f"- for_trade_date: `{preflight['for_trade_date']}`",
        f"- previous_day_minute_date: `{preflight['previous_day_minute_date']}`",
        f"- expected_row_count: `{preflight['expected_row_count']}`",
        f"- expected_bar_count_per_object: `{preflight['expected_bar_count_per_object']}`",
        f"- writes_outbox: `{preflight['writes_outbox']}`",
        f"- execute_authorized: `{preflight['execute_authorized']}`",
        f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
        "",
        "## Expected Asset Counts",
        "",
    ]
    for asset_kind, counts in (preflight.get("expected_asset_counts") or {}).items():
        lines.append(
            f"- {asset_kind}: objects=`{counts['object_count']}` subscriptions=`{counts['subscription_count']}` "
            f"expected_minute_rows=`{counts['expected_minute_bar_rows']}`"
        )
    lines.extend(["", "## Baseline Guard", ""])
    for table_name, count in scoped_rows.items():
        lines.append(f"- {table_name}: `{count}`")
    lines.extend(["", "## Allowed Future Writes", ""])
    for table_name in write_scope.get("allowed_tables") or []:
        lines.append(f"- `{table_name}`")
    lines.extend(["", "## Forbidden", ""])
    for table_name in write_scope.get("forbidden_tables") or []:
        lines.append(f"- `{table_name}`")
    lines.extend(["", "## Quality", ""])
    for item in quality["items"]:
        lines.append(
            f"- {item.get('severity')} {item.get('status')} {item.get('gate_code')}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(["", "## Boundary", ""])
    for key, value in (preflight.get("side_effects") or {}).items():
        lines.append(f"- {key}: `{str(value).lower()}`")
    lines.extend(
        [
            "",
            "## Execute Command Candidate",
            "",
            "```bash",
            preflight["execute_command_template"].replace(
                "<contract_json_path>",
                str(preflight.get("contract_json_path") or "<contract_json_path>"),
            ),
            "```",
            "",
            f"- execute_runner: `{preflight['execute_runner']}`",
            f"- execute_requires_flags: `{', '.join(preflight['execute_requires_flags'])}`",
            "- This preflight artifact is not execute authorization.",
            "",
            "## Rollback",
            "",
            f"- rollback_sql_path: `{preflight['rollback_sql_path']}`",
            "- rollback guard requires scoped outbox/inbox/checkpoint refs to remain zero.",
            "",
        ]
    )
    return "\n".join(lines)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


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
