"""N3-B1 realtime daily snapshot execute contract planner.

This preflight stage reads the N3-B0 dry-run report and the persisted N3-6
subscription control rows. It writes only contract/report files and rollback
SQL. It does not pull market data, write snapshot facts, write event outbox
rows, or start workers.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.preload_plan import REALTIME_SNAPSHOT_TABLES
from ashare_v3.market.realtime_snapshot_plan import (
    DEFAULT_N3_B0_JSON_REPORT_PATH,
    REQUIRED_DATA_KIND,
    SNAPSHOT_EVENT_TYPES,
    build_realtime_subscription_report,
)
from ashare_v3.market.subscription_plan import ASSET_KINDS


DEFAULT_B1_CONTRACT_JSON_PATH = "docs/N3_B1_realtime_daily_snapshot_execute_contract.json"
DEFAULT_B1_CONTRACT_MD_PATH = "docs/N3_B1_REALTIME_DAILY_SNAPSHOT_EXECUTE_CONTRACT.md"
DEFAULT_B1_ROLLBACK_SQL_PATH = "sql/N3_B1_realtime_daily_snapshot_rollback.sql"
REQUIRED_B1_OUTBOX_EVENTS = (
    "MarketSnapshotUpdated",
)


def build_realtime_snapshot_execute_contract(
    *,
    dsn: str,
    market_data_run_id: str,
    b0_report_path: str = DEFAULT_N3_B0_JSON_REPORT_PATH,
    contract_json_path: str = DEFAULT_B1_CONTRACT_JSON_PATH,
    contract_markdown_path: str = DEFAULT_B1_CONTRACT_MD_PATH,
    rollback_sql_path: str = DEFAULT_B1_ROLLBACK_SQL_PATH,
    snapshot_run_id: str | None = None,
    publish_display_event: bool = False,
    writes_outbox: bool = True,
    pre_open_source_policy: bool = False,
    source_returned_time_policy: bool = False,
) -> dict[str, Any]:
    b0_report = read_json(b0_report_path)
    persisted_report = build_realtime_subscription_report(
        dsn=dsn,
        market_data_run_id=market_data_run_id,
    )
    contract = build_execute_contract_from_reports(
        b0_report=b0_report,
        persisted_report=persisted_report,
        market_data_run_id=market_data_run_id,
        snapshot_run_id=snapshot_run_id,
        rollback_sql_path=rollback_sql_path,
        publish_display_event=publish_display_event,
        writes_outbox=writes_outbox,
        pre_open_source_policy=pre_open_source_policy,
        source_returned_time_policy=source_returned_time_policy,
    )
    rollback_sql = format_realtime_snapshot_rollback_sql(contract)
    contract["quality"]["items"].extend(
        build_rollback_quality_items(rollback_sql, writes_outbox=bool(contract.get("writes_outbox")))
    )
    contract["quality"] = summarize_quality(contract["quality"]["items"])

    write_text(rollback_sql_path, rollback_sql)
    write_json(contract_json_path, contract)
    write_text(contract_markdown_path, format_realtime_snapshot_execute_contract_markdown(contract))
    return contract


def build_execute_contract_from_reports(
    *,
    b0_report: Mapping[str, Any],
    persisted_report: Mapping[str, Any],
    market_data_run_id: str,
    snapshot_run_id: str | None = None,
    rollback_sql_path: str = DEFAULT_B1_ROLLBACK_SQL_PATH,
    publish_display_event: bool = False,
    writes_outbox: bool = True,
    pre_open_source_policy: bool = False,
    source_returned_time_policy: bool = False,
) -> dict[str, Any]:
    resolved_snapshot_run_id = snapshot_run_id or derive_snapshot_run_id(b0_report, market_data_run_id)
    expected_asset_counts = build_expected_asset_counts(b0_report)
    target_tables = build_target_tables(writes_outbox=writes_outbox)
    source_adapter_plan = build_source_adapter_plan(b0_report)
    event_contract = build_event_contract(publish_display_event=publish_display_event, writes_outbox=writes_outbox)
    post_execute_quality_gates = build_post_execute_quality_gates(
        b0_report=b0_report,
        publish_display_event=publish_display_event,
        writes_outbox=writes_outbox,
    )
    preflight_quality = build_preflight_quality_items(
        b0_report=b0_report,
        persisted_report=persisted_report,
        market_data_run_id=market_data_run_id,
        snapshot_run_id=resolved_snapshot_run_id,
        expected_asset_counts=expected_asset_counts,
        target_tables=target_tables,
        source_adapter_plan=source_adapter_plan,
        event_contract=event_contract,
        writes_outbox=writes_outbox,
    )
    quality = summarize_quality(preflight_quality)
    return {
        "stage": "N3-B1-preflight",
        "layer_role": "N3_market_data",
        "execution_mode": "realtime_daily_snapshot_run_once_execute_contract",
        "generated_at": utc_now_iso(),
        "source_run_id": market_data_run_id,
        "market_data_run_id": market_data_run_id,
        "snapshot_run_id": resolved_snapshot_run_id,
        "source_condition_run_id": b0_report.get("source_condition_run_id"),
        "for_trade_date": b0_report.get("for_trade_date"),
        "source_trade_date": b0_report.get("source_trade_date"),
        "prev_trade_date": b0_report.get("prev_trade_date"),
        "required_data_kind": REQUIRED_DATA_KIND,
        "target_tables": target_tables,
        "expected_asset_counts": expected_asset_counts,
        "expected_row_count": int(b0_report.get("expected_snapshot_rows") or 0),
        "source_adapter_plan": source_adapter_plan,
        "source_time_policy": build_source_time_policy(
            pre_open_source_policy=pre_open_source_policy,
            source_returned_time_policy=source_returned_time_policy,
        ),
        "event_contract": event_contract,
        "idempotency_policy": build_idempotency_policy(
            resolved_snapshot_run_id,
            market_data_run_id,
            writes_outbox=writes_outbox,
        ),
        "overwrite_policy": build_overwrite_policy(writes_outbox=writes_outbox),
        "writes_outbox": bool(writes_outbox),
        "writes_event_outbox": bool(writes_outbox),
        "writes_market_snapshot_updated": bool(writes_outbox),
        "writes_market_display_snapshot_updated": False,
        "rollback_sql_path": rollback_sql_path,
        "rollback_policy": {
            "delete_by": ["source_run_id", "snapshot_run_id", "for_trade_date"],
            "requires_raw_json_source_run_id": True,
            "touches_event_outbox": bool(writes_outbox),
            "requires_outbox_not_delivered": bool(writes_outbox),
            "requires_scoped_event_refs_zero": True,
            "does_not_touch_downstream_tables": True,
        },
        "execute_runner_readiness": {
            "runner_exists": True,
            "runner_path": "scripts/run_realtime_daily_snapshot_once.py",
            "runner_requires_execute_flag": True,
            "runner_requires_user_confirmed_flag": True,
            "runner_requires_explicit_outbox_policy": True,
            "runner_requires_no_outbox_flag": not bool(writes_outbox),
            "runner_requires_writes_outbox_true_flag": bool(writes_outbox),
            "runner_supports_writes_outbox_false": True,
            "runner_supports_writes_outbox_true": True,
            "runner_supports_pre_open_source_policy": True,
            "runner_supports_source_returned_time_policy": True,
            "execute_final_gate_allowed": True,
            "blocked_reason": None,
        },
        "post_execute_quality_gates": post_execute_quality_gates,
        "quality": quality,
        "side_effects": {
            "read_only_database_checks": True,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "realtime_snapshot_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def derive_snapshot_run_id(b0_report: Mapping[str, Any], source_run_id: str) -> str:
    for_trade_date = str(b0_report.get("for_trade_date") or "")
    return f"realtime_daily_snapshot_{for_trade_date}__{source_run_id}"


def build_source_time_policy(
    *,
    pre_open_source_policy: bool = False,
    source_returned_time_policy: bool = False,
) -> dict[str, Any]:
    if pre_open_source_policy and source_returned_time_policy:
        raise ValueError("pre_open_source_policy conflicts with source_returned_time_policy")
    if source_returned_time_policy:
        return {
            "mode": "source_returned_time",
            "allow_source_time_missing_or_preopen": False,
            "source_time_required": True,
            "local_observed_at_trace_only": True,
            "snapshot_time_fallback": "source_time_required",
            "source_time_future_guard_enabled": False,
            "future_source_time_handling": "allowed_when_source_trade_date_matches",
            "untrusted_source_time_label_handling": "NORMALIZE_TO_OBSERVED_AT",
            "index_board_period_label_policy": "normalize_to_observed_at_trace_raw_label",
            "index_board_only_normalization": True,
            "stock_missing_source_time_policy": "observed_at_fallback_when_effective_quote_present",
            "stock_observed_at_fallback": True,
            "stock_trusted_source_timestamp_required": False,
            "stock_fallback_quality_severity": "P1",
            "quality_gate_code": "BLOCKED_N3_SOURCE_RETURNED_TIME_INVALID",
            "raw_json_required_fields": [
                "source_time_policy",
                "source_snapshot_time",
                "source_snapshot_trade_date",
                "observed_at",
                "fetched_at",
                "raw_snapshot_time_label",
                "raw_snapshot_time_semantics",
                "source_time_trust_level",
                "trusted_source_timestamp_present",
                "source_time_observed_at_fallback",
            ],
            "notes": [
                "Readiness is based on source-returned source_snapshot_time, not local wall-clock.",
                "local_observed_at and fetched_at are trace only.",
                "TDX index/board frequency=9 period labels are retained as raw trace; observed_at/fetched_at is the effective source time under reviewed index/board policy.",
                "mootdx stock quotes() does not provide a trusted source timestamp; reviewed stock B1 fallback uses observed_at/fetched_at only when an effective quote is present.",
                "Missing source time, source date mismatch, or fake/synthetic/fabricated markers remain fail-closed.",
            ],
        }
    if not pre_open_source_policy:
        return {
            "mode": "strict_live",
            "allow_source_time_missing_or_preopen": False,
            "snapshot_time_fallback": "source_time_required_when_available",
            "source_time_future_guard_enabled": True,
            "future_tolerance_seconds": 120,
            "future_source_time_handling": "P0_BLOCK_NO_OUTBOX",
            "quality_gate_code": None,
        }
    return {
        "mode": "pre_open_fact_only",
        "allow_source_time_missing_or_preopen": True,
        "snapshot_time_fallback": "execution_time_when_source_time_missing",
        "source_time_future_guard_enabled": True,
        "future_tolerance_seconds": 120,
        "future_source_time_handling": "P0_BLOCK_NO_OUTBOX",
        "quality_gate_code": "n3_b1_pre_open_source_time_not_confirmed",
        "quality_severity": "P1",
        "quality_status": "partial",
        "raw_json_required_fields": [
            "source_time_status",
            "source_time_missing_or_preopen",
            "snapshot_time_policy",
            "source_snapshot_time",
            "effective_quote_present",
        ],
        "notes": [
            "Pre-open fact-only rows are settlement/bootstrap facts, not live trading-ready snapshots.",
            "Missing source timestamp or pre-open zero quote must be recorded in raw_json and P1 quality.",
            "Explicit source date mismatch remains a P0 blocker and must not be silently downgraded.",
        ],
    }


def build_expected_asset_counts(b0_report: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    object_counts = b0_report.get("snapshot_object_count_by_asset_kind") or {}
    row_counts = b0_report.get("expected_snapshot_rows_by_asset_kind") or {}
    adapter_rows = (b0_report.get("source_adapter_plan") or {}).get("rows") or []
    subscription_counts = {str(row.get("asset_kind")): int(row.get("subscription_count") or 0) for row in adapter_rows}
    output: dict[str, dict[str, int]] = {}
    for asset_kind in ASSET_KINDS:
        object_count = int(object_counts.get(asset_kind) or 0)
        output[asset_kind] = {
            "object_count": object_count,
            "subscription_count": int(subscription_counts.get(asset_kind, object_count)),
            "expected_snapshot_rows": int(row_counts.get(asset_kind) or object_count),
        }
    return output


def build_target_tables(*, writes_outbox: bool = True) -> dict[str, dict[str, str]]:
    identity_columns = {
        "stock": "stock_identity_key",
        "index": "index_identity_key",
        "board": "board_identity_key",
    }
    output: dict[str, dict[str, str]] = {}
    for asset_kind in ASSET_KINDS:
        output[asset_kind] = {
            "snapshot_fact_table": REALTIME_SNAPSHOT_TABLES[asset_kind],
            "identity_column": identity_columns[asset_kind],
            "quality_table": "common_market_data_quality_item",
        }
        if writes_outbox:
            output[asset_kind]["event_outbox_table"] = "common_event_outbox"
    return output


def build_source_adapter_plan(b0_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = (b0_report.get("source_adapter_plan") or {}).get("rows") or []
    output: list[dict[str, Any]] = []
    for row in rows:
        output.append(
            {
                "asset_kind": row.get("asset_kind"),
                "source_pull_plan_id": row.get("source_pull_plan_id"),
                "adapter_name": row.get("adapter_name"),
                "trade_date": row.get("trade_date"),
                "subscription_count": row.get("subscription_count"),
                "object_count": row.get("object_count"),
                "expected_snapshot_rows": row.get("expected_snapshot_rows"),
                "target_snapshot_table": row.get("target_snapshot_table"),
                "adapter_call_planned_in_preflight": False,
            }
        )
    return sorted(output, key=lambda item: str(item.get("asset_kind")))


def build_event_contract(*, publish_display_event: bool, writes_outbox: bool = True) -> dict[str, Any]:
    event_types = list(REQUIRED_B1_OUTBOX_EVENTS) if writes_outbox else []
    return {
        "writes_outbox": bool(writes_outbox),
        "required_outbox_events": list(REQUIRED_B1_OUTBOX_EVENTS) if writes_outbox else [],
        "optional_outbox_events": [],
        "generated_outbox_events_in_b1_default": event_types,
        "publish_display_event": False,
        "disabled_non_snapshot_outbox_events": True,
        "source_issue_outbox_policy": "block_or_fail_without_non_snapshot_outbox",
        "same_transaction_contracts": {
            "snapshot_success": [
                "BEGIN",
                "UPSERT stock/index/board_realtime_daily_snapshot",
                "INSERT common_event_outbox MarketSnapshotUpdated" if writes_outbox else "DO NOT WRITE common_event_outbox",
                "COMMIT",
            ],
            "snapshot_source_issue": [
                "BEGIN",
                "INSERT common_market_data_quality_item",
                "DO NOT WRITE common_event_outbox",
                "FINALIZE RUN AS failed or BLOCK before commit when source issue is P0",
                "COMMIT",
            ],
            "display_snapshot": [
                "BEGIN",
                "UPSERT stock/index/board_realtime_daily_snapshot",
                "DO NOT WRITE common_event_outbox",
                "COMMIT",
            ],
        },
        "payload_required_fields": {
            "MarketSnapshotUpdated": [
                "subscription_id",
                "pull_plan_id",
                "run_id",
                "source_adapter",
                "data_quality_status",
                "snapshot_id",
            ],
        }
        if writes_outbox
        else {},
        "dedup_keys": {
            "MarketSnapshotUpdated": "asset_kind + identity_key + trade_date + snapshot_time + source_adapter",
        },
        "partition_key": "identity_key",
        "source_layer": "N3_market_data",
        "display_event_policy": {
            "does_not_trigger_voice": True,
            "does_not_generate_action_card": True,
            "does_not_modify_user_projection_in_n3": True,
        },
    }


def build_idempotency_policy(snapshot_run_id: str, source_run_id: str, *, writes_outbox: bool = True) -> dict[str, Any]:
    return {
        "snapshot_run_id": snapshot_run_id,
        "source_run_id": source_run_id,
        "snapshot_fact_unique_keys": {
            asset_kind: ["run_id", "trade_date", f"{asset_kind}_identity_key", "snapshot_time", "source_adapter"]
            for asset_kind in ASSET_KINDS
        },
        "outbox_unique_keys": [
            "event_id",
            "source_layer + event_type + source_run_id + dedup_key + event_schema_version",
        ]
        if writes_outbox
        else [],
        "required_trace_fields": {
            "raw_json.source_run_id": source_run_id,
            "raw_json.snapshot_run_id": snapshot_run_id,
            "raw_json.required_data_kind": REQUIRED_DATA_KIND,
            "payload_json.run_id": snapshot_run_id if writes_outbox else "not_applicable_when_writes_outbox_false",
        },
        "repeat_execute_same_snapshot_run_id": "upsert_or_noop_by_snapshot_unique_key_after validating same source_run_id",
        "repeat_execute_different_snapshot_run_id": "allowed only after explicit user confirmation and separate rollback scope",
    }


def build_overwrite_policy(*, writes_outbox: bool = True) -> dict[str, Any]:
    return {
        "default": "no_silent_overwrite",
        "same_key_same_payload_hash": "noop",
        "same_key_different_payload_hash": "P0_block unless explicit snapshot correction mode is requested later",
        "existing_rows_for_snapshot_run_id": "must run rollback or idempotent verification before retry",
        "missing_objects": "record quality item; cannot silently pass"
        if not writes_outbox
        else "record quality item and fail/block run; do not write non-snapshot outbox",
        "delayed_objects": "record quality item; cannot silently pass"
        if not writes_outbox
        else "record quality item and fail/block run; do not write non-snapshot outbox",
        "writes_outbox": bool(writes_outbox),
    }


def build_post_execute_quality_gates(
    *,
    b0_report: Mapping[str, Any],
    publish_display_event: bool,
    writes_outbox: bool = True,
) -> list[dict[str, Any]]:
    expected_asset_counts = build_expected_asset_counts(b0_report)
    total_expected = int(b0_report.get("expected_snapshot_rows") or 0)
    display_expected = "disabled_by_standard_contract"
    gates = [
        {
            "gate_code": "n3_b1_snapshot_object_count_matches_b0",
            "severity": "P0",
            "expected": expected_asset_counts,
            "rule": "stock/index/board snapshot object_count must match B0 expected asset counts",
        },
        {
            "gate_code": "n3_b1_snapshot_rows_reasonable",
            "severity": "P0",
            "expected": {"min_total_rows": 0, "expected_full_total_rows": total_expected},
            "rule": "actual snapshot rows must be non-negative and missing objects must create quality items",
        },
        {
            "gate_code": "n3_b1_duplicate_snapshot_key_zero",
            "severity": "P0",
            "expected": 0,
            "rule": "duplicate key (run_id, trade_date, identity_key, snapshot_time, source_adapter) must be zero in each physical snapshot table",
        },
        {
            "gate_code": "n3_b1_physical_table_isolation",
            "severity": "P0",
            "expected": "stock rows only in stock table; index rows only in index table; board rows only in board table",
            "rule": "identity_key prefix must match physical snapshot table family",
        },
        {
            "gate_code": "n3_b1_display_event_policy",
            "severity": "P0",
            "expected": display_expected,
            "rule": "low-frequency display material is disabled for the standard B1 snapshot execute contract",
        },
        {
            "gate_code": "n3_b1_scoped_event_refs_zero",
            "severity": "P0",
            "expected": 0,
            "rule": "scoped outbox/inbox/checkpoint refs must remain zero",
        },
        {
            "gate_code": "n3_b1_no_downstream_consumption_before_rollback",
            "severity": "P0",
            "expected": 0,
            "rule": "rollback is only safe when scoped inbox and checkpoint refs remain zero",
        },
    ]
    if writes_outbox:
        gates.insert(
            2,
            {
                "gate_code": "n3_b1_market_snapshot_outbox_matches_successful_facts",
                "severity": "P0",
                "expected": "one MarketSnapshotUpdated outbox row per successful snapshot fact",
                "rule": "successful snapshot fact writes must have same-transaction MarketSnapshotUpdated outbox rows",
            },
        )
        gates.insert(
            3,
            {
                "gate_code": "n3_b1_no_non_snapshot_outbox_events",
                "severity": "P0",
                "expected": "only MarketSnapshotUpdated outbox rows",
                "rule": "source issue rows must be quality/failure evidence only and must not create non-snapshot outbox events",
            },
        )
    else:
        gates.insert(
            2,
            {
                "gate_code": "n3_b1_writes_outbox_false",
                "severity": "P0",
                "expected": 0,
                "rule": "common_event_outbox must receive zero rows for snapshot_run_id",
            },
        )
    return gates


def build_preflight_quality_items(
    *,
    b0_report: Mapping[str, Any],
    persisted_report: Mapping[str, Any],
    market_data_run_id: str,
    snapshot_run_id: str,
    expected_asset_counts: Mapping[str, Mapping[str, int]],
    target_tables: Mapping[str, Mapping[str, str]],
    source_adapter_plan: Sequence[Mapping[str, Any]],
    event_contract: Mapping[str, Any],
    writes_outbox: bool = True,
) -> list[dict[str, Any]]:
    b0_quality = b0_report.get("quality") or {}
    persisted_quality = persisted_report.get("quality") or {}
    b0_asset_counts = b0_report.get("snapshot_object_count_by_asset_kind") or {}
    persisted_realtime_rows = realtime_rows_from_persisted_report(persisted_report)
    persisted_asset_counts = Counter(str(row.get("asset_kind")) for row in persisted_realtime_rows)
    target_table_names = [
        str(table)
        for tables in target_tables.values()
        for table in tables.values()
        if table
    ]
    snapshot_table_names = [tables["snapshot_fact_table"] for tables in target_tables.values()]
    runtime_tables = [table for table in target_table_names if "_runtime" in table]
    physical_errors = [
        tables["snapshot_fact_table"]
        for asset_kind, tables in target_tables.items()
        if not str(tables["snapshot_fact_table"]).startswith(f"{asset_kind}_")
    ]
    downstream_table_hits = [
        table
        for table in target_table_names
        if table.startswith(("trigger_", "action_", "user_", "voice_", "sim_", "position_"))
    ]
    adapter_asset_kinds = {str(row.get("asset_kind")) for row in source_adapter_plan}
    event_types = set(event_contract.get("generated_outbox_events_in_b1_default") or [])
    event_types.update(event_contract.get("required_outbox_events") or [])
    event_types.update(event_contract.get("optional_outbox_events") or [])
    user_event_hits = sorted(event_type for event_type in event_types if event_type.startswith("User"))
    unsupported_event_hits = sorted(event_types - set(SNAPSHOT_EVENT_TYPES))
    missing_payload_requirements = (
        [
            event_type
            for event_type, fields in (event_contract.get("payload_required_fields") or {}).items()
            if not {"subscription_id", "pull_plan_id", "run_id", "source_adapter", "data_quality_status"}.issubset(set(fields))
        ]
        if writes_outbox
        else []
    )
    items = [
        quality_item(
            "P0",
            "passed" if b0_report.get("stage") == "N3-B0" else "failed",
            "n3_b1_b0_report_stage_valid",
            "N3-B1-preflight must consume an N3-B0 dry-run report",
            expected="N3-B0",
            actual=str(b0_report.get("stage")),
        ),
        quality_item(
            "P0",
            "passed" if int(b0_quality.get("p0_count") or 0) == 0 and not b0_report.get("blocked") else "failed",
            "n3_b1_b0_report_p0_zero",
            "N3-B1-preflight requires B0 P0=0 and blocked=false",
            expected="P0=0 blocked=false",
            actual=f"P0={b0_quality.get('p0_count')} blocked={b0_report.get('blocked')}",
        ),
        quality_item(
            "P1",
            "warning" if int(b0_quality.get("p1_count") or 0) > 0 else "passed",
            "n3_b1_b0_p1_carried",
            "N3-B1-preflight carries non-blocking B0 P1 items",
            expected="0",
            actual=str(b0_quality.get("p1_count") or 0),
        ),
        quality_item(
            "P0",
            "passed" if persisted_report.get("market_data_run_id") == market_data_run_id else "failed",
            "n3_b1_source_run_id_matches_n3_6",
            "contract source_run_id must match the persisted N3-6 market_data_run_id",
            expected=market_data_run_id,
            actual=str(persisted_report.get("market_data_run_id")),
        ),
        quality_item(
            "P0",
            "passed" if int(persisted_quality.get("p0_count") or 0) == 0 and persisted_report.get("passed") else "failed",
            "n3_b1_n3_6_source_p0_zero",
            "N3-B1-preflight requires persisted N3-6 subscription run P0=0",
            expected="P0=0 passed=true",
            actual=f"P0={persisted_quality.get('p0_count')} passed={persisted_report.get('passed')}",
        ),
        quality_item(
            "P0",
            "passed" if snapshot_run_id and snapshot_run_id != market_data_run_id else "failed",
            "n3_b1_snapshot_run_id_distinct",
            "snapshot_run_id must be present and distinct from source_run_id",
            expected="distinct non-empty snapshot_run_id",
            actual=snapshot_run_id,
        ),
        quality_item(
            "P0",
            "passed" if asset_counts_match(b0_asset_counts, persisted_asset_counts) else "failed",
            "n3_b1_asset_counts_match_n3_6",
            "B0 stock/index/board object counts must match persisted N3-6 realtime snapshot subscriptions",
            expected=str({asset: int(b0_asset_counts.get(asset) or 0) for asset in ASSET_KINDS}),
            actual=str({asset: int(persisted_asset_counts.get(asset) or 0) for asset in ASSET_KINDS}),
        ),
        quality_item(
            "P0",
            "passed" if adapter_asset_kinds == set(ASSET_KINDS) else "failed",
            "n3_b1_source_adapter_plan_covers_assets",
            "source_adapter_plan must cover stock/index/board",
            expected=",".join(ASSET_KINDS),
            actual=",".join(sorted(adapter_asset_kinds)),
        ),
        quality_item(
            "P0",
            "passed" if not runtime_tables else "failed",
            "n3_b1_target_tables_no_runtime_names",
            "N3-B1 target tables must not use *_runtime table names",
            expected="no *_runtime target table",
            actual="none" if not runtime_tables else ",".join(runtime_tables),
        ),
        quality_item(
            "P0",
            "passed" if not physical_errors else "failed",
            "n3_b1_snapshot_tables_physically_separated",
            "N3-B1 target snapshot tables must be physically separated by stock/index/board",
            expected="stock/index/board table prefixes",
            actual="separated" if not physical_errors else ",".join(physical_errors),
        ),
        quality_item(
            "P0",
            "passed" if not downstream_table_hits else "failed",
            "n3_b1_target_tables_no_downstream_tables",
            "N3-B1 target tables must not include trigger/action/user/voice/sim/position tables",
            expected="downstream table names absent",
            actual="absent" if not downstream_table_hits else ",".join(downstream_table_hits),
        ),
        quality_item(
            "P0",
            "passed"
            if ("common_event_outbox" in target_table_names) == bool(writes_outbox)
            else "failed",
            "n3_b1_target_tables_event_outbox_scope",
            "N3-B1 target tables must match writes_outbox contract",
            expected="common_event_outbox present" if writes_outbox else "common_event_outbox absent",
            actual="present" if "common_event_outbox" in target_table_names else "absent",
        ),
        quality_item(
            "P0",
            "passed" if not user_event_hits and not unsupported_event_hits else "failed",
            "n3_b1_event_contract_allowed_n3_events",
            "N3-B1 execute contract must use allowed N3 event types and no User-prefixed names",
            expected="allowed N3 snapshot/quality/display events",
            actual="allowed" if not user_event_hits and not unsupported_event_hits else ",".join(user_event_hits + unsupported_event_hits),
        ),
        quality_item(
            "P0",
            "passed" if not missing_payload_requirements else "failed",
            "n3_b1_event_payload_trace_fields_required",
            "N3-B1 event payload contracts must require trace fields",
            expected="subscription_id/pull_plan_id/run_id/source_adapter/data_quality_status plus id",
            actual="present" if not missing_payload_requirements else ",".join(missing_payload_requirements),
        ),
        quality_item(
            "P0",
            "passed" if set(snapshot_table_names) == set(REALTIME_SNAPSHOT_TABLES.values()) else "failed",
            "n3_b1_snapshot_target_tables_complete",
            "N3-B1 target tables must include stock/index/board realtime daily snapshot tables",
            expected=",".join(sorted(REALTIME_SNAPSHOT_TABLES.values())),
            actual=",".join(sorted(snapshot_table_names)),
        ),
        quality_item(
            "P0",
            "passed" if bool(writes_outbox) is bool(event_contract.get("writes_outbox")) else "failed",
            "n3_b1_contract_writes_outbox_matches_policy",
            "N3-B1 execute contract writes_outbox must match the requested policy",
            expected=str(bool(writes_outbox)).lower(),
            actual=str(bool(event_contract.get("writes_outbox"))).lower(),
        ),
        quality_item(
            "P0",
            "passed",
            "n3_b1_preflight_no_market_pull_or_write",
            "N3-B1-preflight does not pull market data or write market facts/outbox",
            expected="no side effects",
            actual="contract only",
        ),
    ]
    _ = expected_asset_counts
    return items


def realtime_rows_from_persisted_report(persisted_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in (persisted_report.get("market_data_subscription_dedup") or {}).get("rows", [])
        if row.get("required_data_kind") == REQUIRED_DATA_KIND
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


def format_realtime_snapshot_rollback_sql(contract: Mapping[str, Any]) -> str:
    source_run_id = sql_literal(str(contract["source_run_id"]))
    snapshot_run_id = sql_literal(str(contract["snapshot_run_id"]))
    for_trade_date = sql_literal(str(contract["for_trade_date"]))
    source_condition_run_id = sql_literal(str(contract["source_condition_run_id"]))
    writes_outbox = bool(contract.get("writes_outbox"))
    target_tables = contract["target_tables"]
    scope_comment = (
        "-- Scope: N3 realtime snapshot run, quality, facts, and scoped pending/failed/dead_letter N3 outbox rows."
        if writes_outbox
        else "-- Scope: N3 realtime snapshot run rows and quality rows only when writes_outbox=false."
    )
    lines = [
        "-- N3-B1 realtime_daily_snapshot rollback plan.",
        "-- Review before execution. Generated by N3-B1-preflight; not executed in preflight.",
        scope_comment,
        "-- Do not execute if scoped outbox/inbox/checkpoint references exist.",
        "",
        "\\set ON_ERROR_STOP on",
        f"\\set source_run_id {source_run_id}",
        f"\\set snapshot_run_id {snapshot_run_id}",
        f"\\set for_trade_date {for_trade_date}",
        f"\\set source_condition_run_id {source_condition_run_id}",
        "",
        "SELECT set_config('app.snapshot_run_id', :'snapshot_run_id', false);",
        "",
        "DO $$",
        "DECLARE",
        "  target_snapshot_run_id TEXT := current_setting('app.snapshot_run_id');",
        "  scoped_outbox_refs_must_be_zero BIGINT := 0;",
        "  delivered_or_delivering_outbox_rows_must_be_zero BIGINT := 0;",
        "  downstream_inbox_rows_must_be_zero BIGINT := 0;",
        "  checkpoint_refs_must_be_zero BIGINT := 0;",
        "  realtime_projection_refs BIGINT := 0;",
        "  trigger_refs BIGINT := 0;",
        "  trigger_state_refs BIGINT := 0;",
        "  action_refs BIGINT := 0;",
        "  n6_refs BIGINT := 0;",
        "  downstream_touched_refs BIGINT := 0;",
        "  worker_started_refs BIGINT := 0;",
        "BEGIN",
    ]
    if writes_outbox:
        lines.extend(
            [
                "  SELECT count(*) INTO delivered_or_delivering_outbox_rows_must_be_zero",
                "  FROM common_event_outbox",
                "  WHERE source_layer = 'N3_market_data'",
                "    AND source_run_id = target_snapshot_run_id",
                "    AND status IN ('delivering', 'delivered');",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "  SELECT count(*) INTO scoped_outbox_refs_must_be_zero",
                "  FROM common_event_outbox",
                "  WHERE source_layer = 'N3_market_data'",
                "    AND source_run_id = target_snapshot_run_id;",
                "",
            ]
        )
    lines.extend(
        [
            "  SELECT count(*) INTO downstream_inbox_rows_must_be_zero",
            "  FROM common_event_inbox",
            "  WHERE source_layer = 'N3_market_data'",
            "    AND source_run_id = target_snapshot_run_id;",
            "",
            "  SELECT count(*) INTO checkpoint_refs_must_be_zero",
            "  FROM common_event_consumer_checkpoint",
            "  WHERE checkpoint_payload::TEXT LIKE '%' || target_snapshot_run_id || '%';",
            "",
            "  IF to_regclass('stock_realtime_projection_metric') IS NOT NULL THEN",
            "    EXECUTE 'SELECT count(*) FROM stock_realtime_projection_metric WHERE to_jsonb(stock_realtime_projection_metric)::TEXT LIKE $1'",
            "      INTO realtime_projection_refs USING '%' || target_snapshot_run_id || '%';",
            "  END IF;",
            "  IF to_regclass('index_realtime_projection_metric') IS NOT NULL THEN",
            "    EXECUTE 'SELECT $1 + count(*) FROM index_realtime_projection_metric WHERE to_jsonb(index_realtime_projection_metric)::TEXT LIKE $2'",
            "      INTO realtime_projection_refs USING realtime_projection_refs, '%' || target_snapshot_run_id || '%';",
            "  END IF;",
            "  IF to_regclass('board_realtime_projection_metric') IS NOT NULL THEN",
            "    EXECUTE 'SELECT $1 + count(*) FROM board_realtime_projection_metric WHERE to_jsonb(board_realtime_projection_metric)::TEXT LIKE $2'",
            "      INTO realtime_projection_refs USING realtime_projection_refs, '%' || target_snapshot_run_id || '%';",
            "  END IF;",
            "",
            "  SELECT count(*) INTO trigger_refs",
            "  FROM common_trigger_match",
            "  WHERE raw_json::TEXT LIKE '%' || target_snapshot_run_id || '%'",
            "     OR source_event_id LIKE '%' || target_snapshot_run_id || '%';",
            "",
            "  IF to_regclass('common_trigger_state') IS NOT NULL THEN",
            "    EXECUTE 'SELECT count(*) FROM common_trigger_state WHERE to_jsonb(common_trigger_state)::TEXT LIKE $1'",
            "      INTO trigger_state_refs USING '%' || target_snapshot_run_id || '%';",
            "  END IF;",
            "",
            "  SELECT count(*) INTO action_refs",
            "  FROM common_action_event",
            "  WHERE source_market_data_run_id = target_snapshot_run_id",
            "     OR source_market_trace::TEXT LIKE '%' || target_snapshot_run_id || '%'",
            "     OR payload_json::TEXT LIKE '%' || target_snapshot_run_id || '%'",
            "     OR trace_json::TEXT LIKE '%' || target_snapshot_run_id || '%';",
            "",
        "  IF to_regclass('user_projection_run') IS NOT NULL THEN",
        "    EXECUTE 'SELECT count(*) FROM user_projection_run WHERE to_jsonb(user_projection_run)::TEXT LIKE $1'",
        "      INTO n6_refs USING '%' || target_snapshot_run_id || '%';",
        "  END IF;",
        "  IF to_regclass('user_signal_projection') IS NOT NULL THEN",
        "    EXECUTE 'SELECT $1 + count(*) FROM user_signal_projection WHERE to_jsonb(user_signal_projection)::TEXT LIKE $2'",
        "      INTO n6_refs USING n6_refs, '%' || target_snapshot_run_id || '%';",
        "  END IF;",
        "  IF to_regclass('user_signal_card') IS NOT NULL THEN",
        "    EXECUTE 'SELECT $1 + count(*) FROM user_signal_card WHERE to_jsonb(user_signal_card)::TEXT LIKE $2'",
        "      INTO n6_refs USING n6_refs, '%' || target_snapshot_run_id || '%';",
        "  END IF;",
        "  IF to_regclass('user_notification_queue') IS NOT NULL THEN",
        "    EXECUTE 'SELECT $1 + count(*) FROM user_notification_queue WHERE to_jsonb(user_notification_queue)::TEXT LIKE $2'",
        "      INTO n6_refs USING n6_refs, '%' || target_snapshot_run_id || '%';",
        "  END IF;",
            "",
            "  SELECT count(*) INTO downstream_touched_refs",
            "  FROM common_market_data_run",
            "  WHERE run_id = target_snapshot_run_id AND downstream_layers_touched = true;",
            "",
            "  SELECT count(*) INTO worker_started_refs",
            "  FROM common_market_data_run",
            "  WHERE run_id = target_snapshot_run_id AND worker_started = true;",
            "",
            "  IF scoped_outbox_refs_must_be_zero <> 0",
            "     OR delivered_or_delivering_outbox_rows_must_be_zero <> 0",
            "     OR downstream_inbox_rows_must_be_zero <> 0",
            "     OR checkpoint_refs_must_be_zero <> 0",
            "     OR realtime_projection_refs <> 0",
            "     OR trigger_refs <> 0",
            "     OR trigger_state_refs <> 0",
            "     OR action_refs <> 0",
            "     OR n6_refs <> 0",
            "     OR downstream_touched_refs <> 0",
            "     OR worker_started_refs <> 0 THEN",
            "    RAISE EXCEPTION",
            "      'N3-B1 rollback blocked for %, outbox=%, delivered_or_delivering=%, inbox=%, checkpoint=%, realtime_projection=%, trigger=%, trigger_state=%, action=%, n6=%, downstream_touched=%, worker=%',",
            "      target_snapshot_run_id, scoped_outbox_refs_must_be_zero, delivered_or_delivering_outbox_rows_must_be_zero,",
            "      downstream_inbox_rows_must_be_zero, checkpoint_refs_must_be_zero, realtime_projection_refs, trigger_refs,",
            "      trigger_state_refs, action_refs, n6_refs, downstream_touched_refs, worker_started_refs;",
            "  END IF;",
            "END $$;",
            "",
            "BEGIN;",
            "",
        ]
    )
    if writes_outbox:
        lines.extend(
            [
                "-- Delete scoped pending/failed/dead_letter N3 outbox rows generated by this B1 run.",
                "DELETE FROM common_event_outbox",
                "WHERE source_layer = 'N3_market_data'",
                "  AND source_run_id = :'snapshot_run_id'",
                "  AND status IN ('pending', 'failed', 'dead_letter');",
                "",
            ]
        )
    for asset_kind in ASSET_KINDS:
        snapshot_table = target_tables[asset_kind]["snapshot_fact_table"]
        identity_column = target_tables[asset_kind]["identity_column"]
        lines.extend(
            [
                f"DELETE FROM {snapshot_table}",
                "WHERE run_id = :'snapshot_run_id'",
                "  AND for_trade_date = :'for_trade_date'",
                "  AND trade_date = :'for_trade_date'",
                "  AND source_condition_run_id = :'source_condition_run_id'",
                f"  AND {identity_column} LIKE '{asset_kind}:%'",
                "  AND raw_json ->> 'source_run_id' = :'source_run_id'",
                "  AND raw_json ->> 'snapshot_run_id' = :'snapshot_run_id';",
                "",
            ]
        )
    lines.extend(
        [
            "DELETE FROM common_market_data_quality_item",
            "WHERE run_id = :'snapshot_run_id'",
            "  AND source_condition_run_id = :'source_condition_run_id'",
            "  AND for_trade_date = :'for_trade_date'",
            "  AND layer_scope = 'market_data_run'",
            "  AND details ->> 'source_run_id' = :'source_run_id'",
            "  AND details ->> 'snapshot_run_id' = :'snapshot_run_id';",
            "",
            "DELETE FROM common_market_data_run",
            "WHERE run_id = :'snapshot_run_id'",
            "  AND source_condition_run_id = :'source_condition_run_id'",
            "  AND for_trade_date = :'for_trade_date'",
            "  AND raw_json ->> 'source_run_id' = :'source_run_id'",
            "  AND (raw_json ->> 'snapshot_run_id' = :'snapshot_run_id' OR raw_json ->> 'run_id' = :'snapshot_run_id')",
            "  AND downstream_layers_touched = false",
            "  AND worker_started = false;",
            "",
            "COMMIT;",
            "",
        ]
    )
    return "\n".join(lines)


def build_rollback_quality_items(rollback_sql: str, *, writes_outbox: bool = True) -> list[dict[str, Any]]:
    lowered = rollback_sql.lower()
    forbidden_downstream_dml = [
        snippet
        for snippet in (
            "delete from trigger_",
            "delete from action_",
            "delete from user_",
            "delete from voice_",
            "delete from sim_",
            "delete from position_",
            "update trigger_",
            "update action_",
            "update user_",
            "update voice_",
            "update sim_",
            "update position_",
        )
        if snippet in lowered
    ]
    has_outbox_delete = "delete from common_event_outbox" in lowered
    has_outbox_delete_scope = has_outbox_delete and "source_run_id = :'snapshot_run_id'" in lowered
    has_outbox_delete_policy = has_outbox_delete_scope if writes_outbox else not has_outbox_delete
    has_outbox_precheck = (
        "delivered_or_delivering_outbox_rows_must_be_zero" in lowered
        if writes_outbox
        else "scoped_outbox_refs_must_be_zero" in lowered
    )
    has_downstream_precheck = "downstream_inbox_rows_must_be_zero" in lowered
    has_checkpoint_precheck = "checkpoint_refs_must_be_zero" in lowered
    first_delete_index = lowered.find("delete from")
    raise_exception_index = lowered.find("raise exception")
    has_hard_fail_before_delete = (
        first_delete_index >= 0 and raise_exception_index >= 0 and raise_exception_index < first_delete_index
    )
    return [
        quality_item(
            "P0",
            "passed" if has_outbox_delete_policy else "failed",
            "n3_b1_rollback_sql_event_outbox_policy",
            "N3-B1 rollback SQL event outbox DML must match writes_outbox policy",
            expected="scoped outbox delete" if writes_outbox else "no common_event_outbox delete",
            actual="scoped delete"
            if has_outbox_delete_scope
            else ("no delete" if not has_outbox_delete else "unscoped delete"),
        ),
        quality_item(
            "P0",
            "passed" if has_outbox_precheck and has_downstream_precheck and has_checkpoint_precheck else "failed",
            "n3_b1_rollback_sql_has_event_ref_guards",
            "N3-B1 rollback SQL must require scoped outbox/inbox/checkpoint prechecks",
            expected="outbox, inbox, and checkpoint prechecks present",
            actual="present" if has_outbox_precheck and has_downstream_precheck and has_checkpoint_precheck else "missing",
        ),
        quality_item(
            "P0",
            "passed" if has_hard_fail_before_delete else "failed",
            "n3_b1_rollback_sql_hard_fail_before_delete",
            "N3-B1 rollback SQL must RAISE EXCEPTION before the first DELETE when refs are unsafe",
            expected="RAISE EXCEPTION before first DELETE",
            actual="present" if has_hard_fail_before_delete else "missing",
        ),
        quality_item(
            "P0",
            "passed" if not forbidden_downstream_dml else "failed",
            "n3_b1_rollback_sql_does_not_touch_downstream_tables",
            "N3-B1 rollback SQL must not modify trigger/action/user/voice/sim/position tables",
            expected="no downstream DML",
            actual="absent" if not forbidden_downstream_dml else ",".join(forbidden_downstream_dml),
        ),
    ]


def format_realtime_snapshot_execute_contract_markdown(contract: Mapping[str, Any]) -> str:
    quality = contract["quality"]
    lines = [
        "# N3-B1 Realtime Daily Snapshot Execute Contract",
        "",
        "## Summary",
        "",
        f"- stage: `{contract['stage']}`",
        f"- layer_role: `{contract['layer_role']}`",
        f"- source_run_id: `{contract['source_run_id']}`",
        f"- snapshot_run_id: `{contract['snapshot_run_id']}`",
        f"- source_condition_run_id: `{contract['source_condition_run_id']}`",
        f"- for_trade_date: `{contract['for_trade_date']}`",
        f"- expected_row_count: `{contract['expected_row_count']}`",
        f"- writes_outbox: `{contract['writes_outbox']}`",
        f"- source_time_policy: `{(contract.get('source_time_policy') or {}).get('mode')}`",
        f"- writes_market_display_snapshot_updated: `{contract['writes_market_display_snapshot_updated']}`",
        f"- P0/P1/P2: `{quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}`",
        "",
        "## Expected Asset Counts",
        "",
    ]
    for asset_kind, counts in contract["expected_asset_counts"].items():
        lines.append(
            f"- {asset_kind}: objects=`{counts['object_count']}` subscriptions=`{counts['subscription_count']}` "
            f"expected_snapshot_rows=`{counts['expected_snapshot_rows']}`"
        )
    lines.extend(["", "## Target Tables", ""])
    for asset_kind, tables in contract["target_tables"].items():
        outbox_table = tables.get("event_outbox_table", "not_applicable_writes_outbox_false")
        lines.append(
            f"- {asset_kind}: snapshot_fact=`{tables['snapshot_fact_table']}` "
            f"quality=`{tables['quality_table']}` outbox=`{outbox_table}`"
        )
    lines.extend(["", "## Source Adapter Plan", ""])
    for row in contract["source_adapter_plan"]:
        lines.append(
            f"- {row['asset_kind']}: adapter=`{row['adapter_name']}` source_pull_plan_id=`{row['source_pull_plan_id']}` "
            f"objects=`{row['object_count']}` expected_rows=`{row['expected_snapshot_rows']}`"
        )
    lines.extend(["", "## Event Contract", ""])
    event_contract = contract["event_contract"]
    generated_events = event_contract["generated_outbox_events_in_b1_default"]
    if generated_events:
        for event_type in generated_events:
            lines.append(f"- `{event_type}`")
    else:
        lines.append("- no outbox events generated because `writes_outbox=false`")
    lines.extend(
        [
            f"- publish_display_event: `{event_contract['publish_display_event']}`",
            f"- display_policy_does_not_trigger_voice: `{event_contract['display_event_policy']['does_not_trigger_voice']}`",
            "",
            "## Policies",
            "",
            f"- idempotency_policy: `{contract['idempotency_policy']['repeat_execute_same_snapshot_run_id']}`",
            f"- overwrite_policy: `{contract['overwrite_policy']['default']}`",
            f"- rollback_sql_path: `{contract['rollback_sql_path']}`",
            f"- rollback_touches_event_outbox: `{contract['rollback_policy']['touches_event_outbox']}`",
            f"- rollback_requires_outbox_not_delivered: `{contract['rollback_policy']['requires_outbox_not_delivered']}`",
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
            f"Rollback SQL was generated at `{contract['rollback_sql_path']}`. It deletes rows by `source_run_id`, `snapshot_run_id`, and `for_trade_date`; it includes scoped outbox/inbox/checkpoint prechecks and does not modify downstream tables.",
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
