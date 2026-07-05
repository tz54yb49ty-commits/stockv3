"""N3 20260605 board lineage repair planner for action-confirmation metrics.

This gate is deliberately read-only. It scopes the remaining 28 board
TriggerMatched identities whose action-confirmation metric lineage is blocked by
missing today/previous-day minute rows. It produces additive subscription and
metric-repair artifacts, but does not execute any DB write.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import audited_n3_market_readonly_plan_connect

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.action_confirmation_metric_materialization_execute import (
    COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
    COVERAGE_REPAIR_RUN_ID_20260605,
    N6_DOWNSTREAM_REF_TABLES,
    PROJECTION_SCHEMA_VERSION,
    SOURCE_CONDITION_RUN_ID_20260605,
    SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
    SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
    SOURCE_SNAPSHOT_RUN_ID_20260605,
    SOURCE_SUBSCRIPTION_RUN_ID_20260605,
    SOURCE_TODAY_MINUTE_RUN_ID_20260605,
    TRIGGER_EXECUTE_RUN_ID_20260605,
    build_20260605_metric_rows,
    choose_20260605_metric_trace_source_groups,
    classify_20260605_metric_trace_eligibility,
    flatten_identity_sets,
    load_existing_metric_identities,
    load_n4_matched_events_for_run,
    load_realtime_projection_rows_for_events,
    normalize_jsonable,
    projection_missing_reasons,
    side_effects,
)
from ashare_v3.market.previous_day_preload_execute import utc_now_iso, write_json, write_text
from ashare_v3.market.subscription_execute import (
    capture_subscription_execution_backup,
    persist_subscription_plan,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


FOR_TRADE_DATE_20260605 = "20260605"
SOURCE_TRADE_DATE_20260605 = "20260604"
EXPECTED_BOARD_OBJECTS = 28
PREVIOUS_DAY_BARS_PER_OBJECT = 240
TODAY_BARS_PER_OBJECT_UNTIL_1127 = 117

BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605 = (
    "market_data_subscription_20260605_action_metric_board_lineage_repair_"
    "condition_layer_20260604_source_20260604_v1"
)
BOARD_LINEAGE_PREVIOUS_DAY_RUN_ID_20260605 = (
    "previous_day_minute_preload_20260604_for_20260605_action_metric_board_lineage_repair__"
    "market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1"
)
BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605 = (
    "today_minute_bar_1m_20260605_until_1127_action_metric_board_lineage_repair__"
    "market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1"
)
BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605 = (
    "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__"
    "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
)
BOARD_LINEAGE_POLICY_VERSION = "n3.action_confirmation_metric.board_lineage_repair.v2"

DEFAULT_CONTRACT_JSON_PATH = "docs/N3_ACTION_CONFIRMATION_METRIC_BOARD_LINEAGE_REPAIR_CONTRACT.json"
DEFAULT_CONTRACT_MD_PATH = "docs/N3_ACTION_CONFIRMATION_METRIC_BOARD_LINEAGE_REPAIR_CONTRACT.md"
DEFAULT_PREFLIGHT_JSON_PATH = "docs/N3_ACTION_CONFIRMATION_METRIC_BOARD_LINEAGE_REPAIR_PREFLIGHT.json"
DEFAULT_PREFLIGHT_MD_PATH = "docs/N3_ACTION_CONFIRMATION_METRIC_BOARD_LINEAGE_REPAIR_PREFLIGHT.md"
DEFAULT_DRY_RUN_JSON_PATH = "docs/N3_ACTION_CONFIRMATION_METRIC_BOARD_LINEAGE_REPAIR_DRY_RUN.json"
DEFAULT_DRY_RUN_MD_PATH = "docs/N3_ACTION_CONFIRMATION_METRIC_BOARD_LINEAGE_REPAIR_DRY_RUN.md"
DEFAULT_PAYLOAD_JSON_PATH = "docs/N3_action_confirmation_metric_board_lineage_repair_payload.json"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N3_action_confirmation_metric_board_lineage_repair_20260605_rollback.sql"
DEFAULT_SUBSCRIPTION_CONTRACT_JSON_PATH = "docs/N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE_CONTRACT.json"
DEFAULT_SUBSCRIPTION_CONTRACT_MD_PATH = "docs/N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE_CONTRACT.md"
DEFAULT_SUBSCRIPTION_PREFLIGHT_JSON_PATH = "docs/N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE_PREFLIGHT.json"
DEFAULT_SUBSCRIPTION_PREFLIGHT_MD_PATH = "docs/N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE_PREFLIGHT.md"
DEFAULT_SUBSCRIPTION_ROLLBACK_SQL_PATH = "sql/N3_board_lineage_scoped_subscription_20260605_rollback.sql"
DEFAULT_SUBSCRIPTION_EXECUTE_REPORT_JSON_PATH = "docs/N3_board_lineage_scoped_subscription_20260605_execute_report.json"
DEFAULT_SUBSCRIPTION_EXECUTE_REPORT_MD_PATH = "docs/N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_20260605_EXECUTE_REPORT.md"

REQUIRED_DATA_KINDS = ("previous_day_minute_bar_1m", "minute_bar_1m")

FORBIDDEN_SCOPE = [
    "N5/N6 action/outbox",
    "common_event_outbox/inbox/checkpoint",
    "worker",
    "delivery/push/voice/mobile",
    "sim/position/pnl/real trade",
    "proposal/order/trade",
    "original action-confirmation metric run",
    "N4 TriggerMatched/outbox",
]

SUBSCRIPTION_EXECUTE_COMMAND = (
    "PYTHONPATH=src:scripts python3 scripts/run_n3_board_lineage_scoped_subscription_execute.py "
    "--contract-path docs/N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE_CONTRACT.json "
    "--preflight-path docs/N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE_PREFLIGHT.json "
    "--payload-path docs/N3_action_confirmation_metric_board_lineage_repair_payload.json "
    "--json-report-path docs/N3_board_lineage_scoped_subscription_20260605_execute_report.json "
    "--markdown-report-path docs/N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_20260605_EXECUTE_REPORT.md "
    "--execute --user-confirmed"
)

SUBSCRIPTION_ALLOWED_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "common_market_data_subscription_candidate",
    "common_market_data_subscription",
    "common_market_data_pull_plan",
]

SUBSCRIPTION_FORBIDDEN_WRITE_TABLES = [
    "board_action_confirmation_projection_metric",
    "stock_action_confirmation_projection_metric",
    "index_action_confirmation_projection_metric",
    "stock/index/board_minute_bar_1m",
    "stock/index/board_previous_day_minute_preload_status",
    "stock/index/board_realtime_daily_snapshot",
    "stock/index/board_realtime_projection_metric",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "N4/N5/N6",
    "worker",
    "delivery/push/voice/mobile",
    "sim/position/pnl/real trade",
    "proposal/order/trade",
]


def build_board_lineage_repair_artifacts(
    *,
    missing_board_rows: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, int],
    source_status: Mapping[str, str | None],
) -> dict[str, Any]:
    normalized_boards = [normalize_missing_board_row(row, index) for index, row in enumerate(missing_board_rows, start=1)]
    candidates = build_subscription_candidates(normalized_boards)
    subscriptions = build_subscription_rows(candidates)
    pull_plan = build_pull_plan_rows(subscriptions)
    quality_items = build_quality_items(
        boards=normalized_boards,
        candidates=candidates,
        subscriptions=subscriptions,
        pull_plan=pull_plan,
        baseline=baseline,
        source_status=source_status,
    )
    severity_counts = count_quality_severities(quality_items)
    payload = build_payload(
        boards=normalized_boards,
        candidates=candidates,
        subscriptions=subscriptions,
        pull_plan=pull_plan,
    )
    contract = build_contract(payload=payload, quality_counts=severity_counts)
    preflight = build_preflight(
        payload=payload,
        contract=contract,
        baseline=baseline,
        source_status=source_status,
        quality_items=quality_items,
        quality_counts=severity_counts,
    )
    dry_run = build_dry_run(payload=payload, contract=contract, preflight=preflight)
    return {
        "payload": payload,
        "contract": contract,
        "preflight": preflight,
        "dry_run": dry_run,
        "rollback_sql": build_board_lineage_repair_rollback_sql(),
    }


def build_subscription_execute_artifacts(
    *,
    repair_payload: Mapping[str, Any],
    repair_preflight: Mapping[str, Any],
) -> dict[str, Any]:
    execute_dry_run_report = build_subscription_execute_dry_run_report(
        payload=repair_payload,
        repair_preflight=repair_preflight,
    )
    contract = build_subscription_execute_contract(
        payload=repair_payload,
        repair_preflight=repair_preflight,
        execute_dry_run_report=execute_dry_run_report,
    )
    preflight = build_subscription_execute_preflight(
        contract=contract,
        payload=repair_payload,
        repair_preflight=repair_preflight,
        execute_dry_run_report=execute_dry_run_report,
    )
    return {
        "payload": normalize_jsonable(dict(repair_payload)),
        "execute_dry_run_report": execute_dry_run_report,
        "contract": contract,
        "preflight": preflight,
        "rollback_sql": build_board_lineage_subscription_rollback_sql(),
    }


def build_subscription_execute_dry_run_report(
    *,
    payload: Mapping[str, Any],
    repair_preflight: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = list((payload.get("market_data_subscription_candidate") or {}).get("rows") or [])
    subscriptions = list((payload.get("market_data_subscription_dedup") or {}).get("rows") or [])
    pull_plan = list((payload.get("market_data_pull_plan") or {}).get("rows") or [])
    quality = dict(repair_preflight.get("quality") or {})
    p0 = int(quality.get("P0") or 0)
    p1 = int(quality.get("P1") or 0)
    p2 = int(quality.get("P2") or 0)
    unique_board_objects = len({str(row.get("identity_key") or "") for row in subscriptions})
    return normalize_jsonable(
        {
            "stage": "N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_SCOPE",
            "layer_role": "N3_market_data",
            "plan_mode": "board_lineage_scoped_subscription_control_dry_run",
            "mode": "dry_run",
            "market_data_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
            "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
            "source_trade_date": SOURCE_TRADE_DATE_20260605,
            "for_trade_date": FOR_TRADE_DATE_20260605,
            "prev_trade_date": SOURCE_TRADE_DATE_20260605,
            "source_scope_row_count": len(candidates),
            "candidate_row_count": len(candidates),
            "subscription_row_count": len(subscriptions),
            "subscription_object_count": len(subscriptions),
            "unique_board_object_count": unique_board_objects,
            "market_data_pull_plan_row_count": len(pull_plan),
            "dedup_ratio": 1.0,
            "object_count_by_asset_kind": {"stock": 0, "index": 0, "board": EXPECTED_BOARD_OBJECTS, "total": EXPECTED_BOARD_OBJECTS},
            "required_data_kind_counts": {
                "previous_day_minute_bar_1m": EXPECTED_BOARD_OBJECTS,
                "minute_bar_1m": EXPECTED_BOARD_OBJECTS,
            },
            "expected_minute_rows_by_kind": {
                "previous_day_minute_bar_1m": EXPECTED_BOARD_OBJECTS * PREVIOUS_DAY_BARS_PER_OBJECT,
                "minute_bar_1m": EXPECTED_BOARD_OBJECTS * TODAY_BARS_PER_OBJECT_UNTIL_1127,
            },
            "market_data_subscription_candidate": {
                "row_count": len(candidates),
                "rows_included": True,
                "rows": candidates,
                "sample_rows": candidates[:20],
            },
            "market_data_subscription_dedup": {
                "row_count": len(subscriptions),
                "rows_included": True,
                "rows": subscriptions,
                "sample_rows": subscriptions[:20],
            },
            "market_data_pull_plan": {
                "row_count": len(pull_plan),
                "rows_included": True,
                "rows": pull_plan,
                "sample_rows": pull_plan[:20],
            },
            "quality": {
                "p0_count": p0,
                "p1_count": p1,
                "p2_count": p2,
                "items": list(quality.get("items") or []),
            },
            "write_scope": {
                "future_execute_allowed_write_tables": list(SUBSCRIPTION_ALLOWED_WRITE_TABLES),
                "forbidden_writes": list(SUBSCRIPTION_FORBIDDEN_WRITE_TABLES),
            },
            "rollback": {
                "rollback_sql_path": DEFAULT_SUBSCRIPTION_ROLLBACK_SQL_PATH,
                "hard_fail_before_delete": True,
                "scope": "subscription_run_id",
            },
            "blocked": p0 > 0,
            "passed": p0 == 0,
            "side_effects": subscription_side_effects(writes_database=False),
            "generated_at": utc_now_iso(),
        }
    )


def build_subscription_execute_contract(
    *,
    payload: Mapping[str, Any],
    repair_preflight: Mapping[str, Any],
    execute_dry_run_report: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_subscription_execute_inputs(
        contract_candidate={
            "execute_target": "subscription_control_only",
            "metric_v2_execute": False,
            "board_objects": EXPECTED_BOARD_OBJECTS,
            "subscription_candidate_rows": execute_dry_run_report["candidate_row_count"],
            "subscription_rows": execute_dry_run_report["subscription_row_count"],
            "pull_plan_rows": execute_dry_run_report["market_data_pull_plan_row_count"],
        },
        preflight_candidate={"result": "PREFLIGHT_PASS", "quality": repair_preflight.get("quality") or {}},
        payload=payload,
    )
    return normalize_jsonable(
        {
            "stage": "N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE_CONTRACT",
            "layer_role": "N3_market_data",
            "contract_result": "CONTRACT_PASS" if validation["valid"] else "CONTRACT_BLOCKED",
            "execute_authorized_now": False,
            "runner_exists": True,
            "runner_readiness": "ready_contract_driven",
            "required_flags": ["--execute", "--user-confirmed"],
            "execute_command": SUBSCRIPTION_EXECUTE_COMMAND,
            "contract_path": DEFAULT_SUBSCRIPTION_CONTRACT_JSON_PATH,
            "preflight_path": DEFAULT_SUBSCRIPTION_PREFLIGHT_JSON_PATH,
            "payload_path": DEFAULT_PAYLOAD_JSON_PATH,
            "execute_target": "subscription_control_only",
            "subscription_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
            "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
            "for_trade_date": FOR_TRADE_DATE_20260605,
            "source_trade_date": SOURCE_TRADE_DATE_20260605,
            "prev_trade_date": SOURCE_TRADE_DATE_20260605,
            "board_objects": EXPECTED_BOARD_OBJECTS,
            "subscription_candidate_rows": execute_dry_run_report["candidate_row_count"],
            "subscription_rows": execute_dry_run_report["subscription_row_count"],
            "pull_plan_rows": execute_dry_run_report["market_data_pull_plan_row_count"],
            "previous_day_planned_rows": EXPECTED_BOARD_OBJECTS * PREVIOUS_DAY_BARS_PER_OBJECT,
            "today_planned_rows_until_1127": EXPECTED_BOARD_OBJECTS * TODAY_BARS_PER_OBJECT_UNTIL_1127,
            "metric_v2_execute": False,
            "n5_n6_execute": False,
            "worker_started": False,
            "allowed_write_tables": list(SUBSCRIPTION_ALLOWED_WRITE_TABLES),
            "forbidden_write_tables": list(SUBSCRIPTION_FORBIDDEN_WRITE_TABLES),
            "writes_outbox": False,
            "consumes_outbox": False,
            "writes_inbox_or_checkpoint": False,
            "pulls_market_data": False,
            "enters_n4_n5_n6": False,
            "starts_worker": False,
            "rollback": {
                "rollback_sql_path": DEFAULT_SUBSCRIPTION_ROLLBACK_SQL_PATH,
                "scope": "subscription_run_id",
                "hard_fail_before_delete": True,
                "delete_scope": list(SUBSCRIPTION_ALLOWED_WRITE_TABLES),
                "forbidden_delete_scope": [
                    "board_action_confirmation_projection_metric",
                    "N4/N5/N6",
                    "common_event_outbox/inbox/checkpoint",
                ],
            },
            "validation": validation,
            "side_effects": subscription_side_effects(writes_database=False),
            "generated_at": utc_now_iso(),
        }
    )


def build_subscription_execute_preflight(
    *,
    contract: Mapping[str, Any],
    payload: Mapping[str, Any],
    repair_preflight: Mapping[str, Any],
    execute_dry_run_report: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_subscription_execute_inputs(
        contract_candidate=contract,
        preflight_candidate={"result": repair_preflight.get("result"), "quality": repair_preflight.get("quality") or {}},
        payload=payload,
    )
    blockers = [] if validation["valid"] else list(validation["blocked_reasons"])
    baseline = dict(repair_preflight.get("baseline_summary") or {})
    baseline_nonzero = {key: value for key, value in baseline.items() if int(value or 0) != 0}
    if baseline_nonzero:
        blockers.append("scoped_subscription_baseline_nonzero")
    quality = dict(repair_preflight.get("quality") or {})
    return normalize_jsonable(
        {
            "stage": "N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE_PREFLIGHT",
            "layer_role": "N3_market_data",
            "result": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
            "blocked": bool(blockers),
            "blockers": blockers,
            "subscription_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
            "execute_target": "subscription_control_only",
            "board_objects": EXPECTED_BOARD_OBJECTS,
            "subscription_candidate_rows": execute_dry_run_report["candidate_row_count"],
            "subscription_rows": execute_dry_run_report["subscription_row_count"],
            "pull_plan_rows": execute_dry_run_report["market_data_pull_plan_row_count"],
            "previous_day_planned_rows": EXPECTED_BOARD_OBJECTS * PREVIOUS_DAY_BARS_PER_OBJECT,
            "today_planned_rows_until_1127": EXPECTED_BOARD_OBJECTS * TODAY_BARS_PER_OBJECT_UNTIL_1127,
            "metric_v2_execute": False,
            "baseline_summary": baseline,
            "source_status": repair_preflight.get("source_status"),
            "allowed_write_tables": list(SUBSCRIPTION_ALLOWED_WRITE_TABLES),
            "forbidden_write_tables": list(SUBSCRIPTION_FORBIDDEN_WRITE_TABLES),
            "execute_command": SUBSCRIPTION_EXECUTE_COMMAND,
            "rollback": contract.get("rollback"),
            "quality": {
                "P0": int(quality.get("P0") or 0),
                "P1": int(quality.get("P1") or 0),
                "P2": int(quality.get("P2") or 0),
                "items": list(quality.get("items") or []),
            },
            "validation": validation,
            "side_effects": subscription_side_effects(writes_database=False),
            "generated_at": utc_now_iso(),
        }
    )


def validate_subscription_execute_inputs(
    *,
    contract_candidate: Mapping[str, Any],
    preflight_candidate: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = list((payload.get("market_data_subscription_candidate") or {}).get("rows") or [])
    subscriptions = list((payload.get("market_data_subscription_dedup") or {}).get("rows") or [])
    pull_plan = list((payload.get("market_data_pull_plan") or {}).get("rows") or [])
    subscription_keys = [
        (
            row.get("asset_kind"),
            row.get("identity_key"),
            row.get("required_data_kind"),
            row.get("data_trade_date"),
        )
        for row in subscriptions
    ]
    duplicate_keys = len(subscription_keys) - len(set(subscription_keys))
    kind_counts = Counter(str(row.get("required_data_kind") or "") for row in subscriptions)
    blockers: list[str] = []
    if contract_candidate.get("execute_target") != "subscription_control_only":
        blockers.append("execute_target_must_be_subscription_control_only")
    if contract_candidate.get("metric_v2_execute") is not False:
        blockers.append("metric_v2_execute_must_be_false")
    if preflight_candidate.get("result") not in {"PREFLIGHT_PASS", "PASS"}:
        blockers.append("source_preflight_not_pass")
    quality = dict(preflight_candidate.get("quality") or {})
    if int(quality.get("P0") or quality.get("p0_count") or 0) != 0:
        blockers.append("source_preflight_p0_nonzero")
    if int(contract_candidate.get("board_objects") or 0) != EXPECTED_BOARD_OBJECTS:
        blockers.append("board_count_mismatch")
    if "subscription_candidate_rows" in contract_candidate and int(contract_candidate.get("subscription_candidate_rows") or 0) != len(candidates):
        blockers.append("contract_candidate_row_count_mismatch")
    if "subscription_rows" in contract_candidate and int(contract_candidate.get("subscription_rows") or 0) != len(subscriptions):
        blockers.append("contract_subscription_row_count_mismatch")
    if "pull_plan_rows" in contract_candidate and int(contract_candidate.get("pull_plan_rows") or 0) != len(pull_plan):
        blockers.append("contract_pull_plan_row_count_mismatch")
    if len(candidates) != EXPECTED_BOARD_OBJECTS * 2:
        blockers.append("candidate_row_count_mismatch")
    if len(subscriptions) != EXPECTED_BOARD_OBJECTS * 2:
        blockers.append("subscription_row_count_mismatch")
    if len(pull_plan) != 2:
        blockers.append("pull_plan_row_count_mismatch")
    if duplicate_keys:
        blockers.append("duplicate_subscription_keys")
    if set(row.get("asset_kind") for row in subscriptions) != {"board"}:
        blockers.append("subscription_scope_not_board_only")
    if any(row.get("source_scope_table") != "board_minute_target_scope" for row in candidates):
        blockers.append("candidate_source_scope_table_must_be_board_minute_target_scope")
    if any("board_minute_target_scope" not in set(row.get("source_scope_tables") or []) for row in subscriptions):
        blockers.append("subscription_source_scope_table_must_be_board_minute_target_scope")
    if any(int(row.get("source_scope_id") or 0) <= 0 for row in candidates):
        blockers.append("candidate_source_scope_id_missing")
    if any(not row.get("source_scope_ids") or int((row.get("source_scope_ids") or [0])[0] or 0) <= 0 for row in subscriptions):
        blockers.append("subscription_source_scope_id_missing")
    if dict(kind_counts) != {"previous_day_minute_bar_1m": EXPECTED_BOARD_OBJECTS, "minute_bar_1m": EXPECTED_BOARD_OBJECTS}:
        blockers.append("required_data_kind_distribution_mismatch")
    return {
        "valid": not blockers,
        "blocked_reasons": blockers,
        "candidate_rows": len(candidates),
        "subscription_rows": len(subscriptions),
        "pull_plan_rows": len(pull_plan),
        "duplicate_subscription_keys": duplicate_keys,
        "required_data_kind_counts": dict(kind_counts),
    }


def normalize_missing_board_row(row: Mapping[str, Any], index: int) -> dict[str, Any]:
    identity = str(row.get("identity_key") or "")
    code = str(row.get("code") or row.get("board_code") or identity.rsplit(":", 1)[-1])
    source_minute_target_scope_id = int(row.get("source_minute_target_scope_id") or 0)
    return normalize_jsonable(
        {
            "identity_key": identity,
            "asset_kind": "board",
            "exchange": str(row.get("exchange") or "TDX"),
            "code": code,
            "display_code": str(row.get("display_code") or code),
            "name": str(row.get("name") or row.get("board_name") or identity),
            "board_type": row.get("board_type"),
            "trigger_match_id": int(row.get("trigger_match_id") or index),
            "source_scope_table": "board_minute_target_scope",
            "source_minute_target_scope_id": source_minute_target_scope_id,
            "source_scope_ref": f"board_minute_target_scope:{source_minute_target_scope_id}" if source_minute_target_scope_id else "",
            "source_condition_pool_id": int(row.get("source_condition_pool_id") or 0),
            "source_condition_basis_id": int(row.get("source_condition_basis_id") or 0),
            "direction": str(row.get("direction") or "unknown"),
            "signal_type": str(row.get("signal_type") or ""),
            "condition_key": str(row.get("condition_key") or ""),
            "source_scope_direction": row.get("source_scope_direction"),
            "source_scope_condition_key": row.get("source_scope_condition_key"),
            "source_scope_allowed_signal_types": list(row.get("source_scope_allowed_signal_types") or []),
            "projection_status": row.get("projection_status"),
            "projection_quality_status": row.get("projection_quality_status"),
            "trace_status": row.get("trace_status"),
            "excluded_reason": row.get("excluded_reason") or "lineage_missing",
            "metric_trace_complete": bool(row.get("metric_trace_complete")),
            "db_check_pass": bool(row.get("db_check_pass")),
            "missing_reasons": list(row.get("missing_reasons") or []),
        }
    )


def build_subscription_candidates(boards: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for board in boards:
        for required_data_kind in REQUIRED_DATA_KINDS:
            data_trade_date = SOURCE_TRADE_DATE_20260605 if required_data_kind == "previous_day_minute_bar_1m" else FOR_TRADE_DATE_20260605
            rows.append(
                {
                    "candidate_ref": f"dry_run:board_lineage_repair_candidate:{len(rows) + 1}",
                    "run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
                    "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
                    "for_trade_date": FOR_TRADE_DATE_20260605,
                    "source_trade_date": SOURCE_TRADE_DATE_20260605,
                    "prev_trade_date": SOURCE_TRADE_DATE_20260605,
                    "asset_kind": "board",
                    "identity_key": board["identity_key"],
                    "exchange": board["exchange"],
                    "code": board["code"],
                    "display_code": board["display_code"],
                    "name": board["name"],
                    "required_data_kind": required_data_kind,
                    "data_trade_date": data_trade_date,
                    "source_scope_table": board["source_scope_table"],
                    "source_scope_id": board["source_minute_target_scope_id"],
                    "source_scope_ref": board["source_scope_ref"],
                    "source_condition_pool_id": board["source_condition_pool_id"],
                    "direction": board["direction"],
                    "condition_key": board["condition_key"],
                    "allowed_signal_types": [board["signal_type"]] if board.get("signal_type") else [],
                    "source_scope_required_flags": {
                        "daily_snapshot_required": False,
                        "minute_required": required_data_kind == "minute_bar_1m",
                        "previous_day_minute_required": required_data_kind == "previous_day_minute_bar_1m",
                        "action_metric_board_lineage_repair": True,
                        "source_trigger_match_id": board["trigger_match_id"],
                        "source_trigger_match_ref": f"common_trigger_match:{board['trigger_match_id']}",
                        "source_scope_direction": board.get("source_scope_direction"),
                        "source_scope_condition_key": board.get("source_scope_condition_key"),
                        "source_scope_allowed_signal_types": board.get("source_scope_allowed_signal_types") or [],
                        "source_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
                    },
                    "candidate_status": "planned",
                    "selected_reason": "action-confirmation metric board lineage repair: missing today/previous-day minute refs",
                }
            )
    return rows


def build_subscription_rows(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        rows.append(
            {
                "subscription_ref": f"dry_run:board_lineage_repair_subscription:{len(rows) + 1}",
                "run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
                "for_trade_date": candidate["for_trade_date"],
                "source_trade_date": candidate["source_trade_date"],
                "prev_trade_date": candidate["prev_trade_date"],
                "asset_kind": "board",
                "identity_key": candidate["identity_key"],
                "exchange": candidate["exchange"],
                "code": candidate["code"],
                "display_code": candidate["display_code"],
                "name": candidate["name"],
                "required_data_kind": candidate["required_data_kind"],
                "data_trade_date": candidate["data_trade_date"],
                "data_trade_dates": [candidate["data_trade_date"]],
                "source_scope_row_count": 1,
                "source_scope_tables": [candidate["source_scope_table"]],
                "source_scope_ids": [candidate["source_scope_id"]],
                "source_scope_refs": [candidate["source_scope_ref"]],
                "source_condition_pool_ids": [candidate["source_condition_pool_id"]],
                "condition_keys": [candidate["condition_key"]],
                "directions": [candidate["direction"]],
                "allowed_signal_types": list(candidate.get("allowed_signal_types") or []),
                "priority": 120,
                "status": "planned",
                "selected_reason": "deduped board lineage repair minute subscription",
            }
        )
    return rows


def build_pull_plan_rows(subscriptions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for required_data_kind in REQUIRED_DATA_KINDS:
        group = [row for row in subscriptions if row["required_data_kind"] == required_data_kind]
        rows.append(
            {
                "pull_plan_ref": f"dry_run:board_lineage_repair_pull_plan:{len(rows) + 1}",
                "run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
                "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
                "for_trade_date": FOR_TRADE_DATE_20260605,
                "source_trade_date": SOURCE_TRADE_DATE_20260605,
                "prev_trade_date": SOURCE_TRADE_DATE_20260605,
                "asset_kind": "board",
                "required_data_kind": required_data_kind,
                "data_trade_date": SOURCE_TRADE_DATE_20260605 if required_data_kind == "previous_day_minute_bar_1m" else FOR_TRADE_DATE_20260605,
                "adapter_name": "BoardMarketDataAdapter",
                "subscription_count": len(group),
                "object_count": len({row["identity_key"] for row in group}),
                "subscription_refs_sample": [row["subscription_ref"] for row in group[:20]],
                "identity_keys_sample": [row["identity_key"] for row in group[:20]],
                "plan_status": "planned",
                "execute_allowed": False,
                "selected_reason": "board lineage repair scope only; A1/C1 execute remains separate",
            }
        )
    return rows


def build_payload(
    *,
    boards: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    subscriptions: Sequence[Mapping[str, Any]],
    pull_plan: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return normalize_jsonable(
        {
            "artifact_type": "N3_action_confirmation_metric_board_lineage_repair_payload",
            "layer_role": "N3_market_data",
            "for_trade_date": FOR_TRADE_DATE_20260605,
            "source_trade_date": SOURCE_TRADE_DATE_20260605,
            "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
            "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID_20260605,
            "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
            "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID_20260605,
            "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
            "coverage_repair_v1_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
            "repair_run_id": BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
            "subscription_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
            "planned_previous_day_minute_run_id": BOARD_LINEAGE_PREVIOUS_DAY_RUN_ID_20260605,
            "planned_today_minute_run_id": BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605,
            "projection_schema_version": PROJECTION_SCHEMA_VERSION,
            "coverage_policy_version": BOARD_LINEAGE_POLICY_VERSION,
            "missing_board_objects": len(boards),
            "missing_board_objects_expected": EXPECTED_BOARD_OBJECTS,
            "missing_board_objects_by_asset_kind": {"stock": 0, "index": 0, "board": len(boards), "total": len(boards)},
            "expected_rows": {
                "subscription_candidate": len(candidates),
                "subscription": len(subscriptions),
                "pull_plan": len(pull_plan),
                "previous_day_minute": len(boards) * PREVIOUS_DAY_BARS_PER_OBJECT,
                "today_minute": len(boards) * TODAY_BARS_PER_OBJECT_UNTIL_1127,
                "additive_metric_v2_max": len(boards),
            },
            "metric_v2_eligibility_gate": {
                "metric_trace_complete_required": True,
                "db_check_pass_required": True,
                "silent_fallback_allowed": False,
                "materialize_only_after_a1_c1_board_lineage_exists": True,
            },
            "missing_board_objects_list": [row["identity_key"] for row in boards],
            "missing_board_objects": list(boards),
            "market_data_subscription_candidate": {"row_count": len(candidates), "rows_included": True, "rows": list(candidates)},
            "market_data_subscription_dedup": {"row_count": len(subscriptions), "rows_included": True, "rows": list(subscriptions)},
            "market_data_pull_plan": {"row_count": len(pull_plan), "rows_included": True, "rows": list(pull_plan)},
            "side_effects": side_effects(writes_database=False),
            "generated_at": utc_now_iso(),
        }
    )


def build_contract(*, payload: Mapping[str, Any], quality_counts: Mapping[str, int]) -> dict[str, Any]:
    return normalize_jsonable(
        {
            "stage": "N3_ACTION_CONFIRMATION_METRIC_BOARD_LINEAGE_REPAIR_CONTRACT",
            "layer_role": "N3_market_data",
            "contract_result": "CONTRACT_PASS" if int(quality_counts.get("P0", 0)) == 0 else "CONTRACT_BLOCKED",
            "execute_authorized_now": False,
            "repair_run_id": BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
            "subscription_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
            "previous_day_minute_run_id": BOARD_LINEAGE_PREVIOUS_DAY_RUN_ID_20260605,
            "today_minute_run_id": BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605,
            "expected_scope": {
                "asset_kind": "board",
                "board_objects": payload["missing_board_objects_expected"],
                "required_data_kind": list(REQUIRED_DATA_KINDS),
                "previous_day_minute_rows": EXPECTED_BOARD_OBJECTS * PREVIOUS_DAY_BARS_PER_OBJECT,
                "today_minute_rows_until_1127": EXPECTED_BOARD_OBJECTS * TODAY_BARS_PER_OBJECT_UNTIL_1127,
                "additive_board_metric_v2_max_rows": EXPECTED_BOARD_OBJECTS,
            },
            "future_write_scope": {
                "subscription_control": [
                    "common_market_data_run",
                    "common_market_data_quality_item",
                    "common_market_data_subscription_candidate",
                    "common_market_data_subscription",
                    "common_market_data_pull_plan",
                ],
                "previous_day_minute": [
                    "common_market_data_run",
                    "common_market_data_quality_item",
                    "board_minute_bar_1m",
                    "board_previous_day_minute_preload_status",
                ],
                "today_minute": [
                    "common_market_data_run",
                    "common_market_data_quality_item",
                    "board_minute_bar_1m",
                ],
                "metric_v2": [
                    "common_market_data_run",
                    "common_market_data_quality_item",
                    "board_action_confirmation_projection_metric",
                ],
            },
            "forbidden_scope": list(FORBIDDEN_SCOPE),
            "metric_v2_policy": {
                "additive_repair_only": True,
                "does_not_cover_original_metric_run": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
                "does_not_cover_repair_v1_run": COVERAGE_REPAIR_RUN_ID_20260605,
                "metric_trace_complete_required": True,
                "db_check_pass_required": True,
                "expected_max_rows": EXPECTED_BOARD_OBJECTS,
            },
            "rollback": {
                "rollback_sql_path": DEFAULT_ROLLBACK_SQL_PATH,
                "scope": "metric_v2_repair_run_id_only",
                "hard_fail_before_delete": True,
                "delete_scope": [
                    "board_action_confirmation_projection_metric",
                    "common_market_data_quality_item",
                    "common_market_data_run",
                ],
                "no_cascade_drop_truncate": True,
            },
            "side_effects": side_effects(writes_database=False),
            "generated_at": utc_now_iso(),
        }
    )


def build_preflight(
    *,
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
    baseline: Mapping[str, int],
    source_status: Mapping[str, str | None],
    quality_items: Sequence[Mapping[str, Any]],
    quality_counts: Mapping[str, int],
) -> dict[str, Any]:
    blockers = [
        item["gate_code"]
        for item in quality_items
        if item.get("severity") == "P0" and item.get("status") == "failed"
    ]
    return normalize_jsonable(
        {
            "stage": "N3_ACTION_CONFIRMATION_METRIC_BOARD_LINEAGE_REPAIR_PREFLIGHT",
            "layer_role": "N3_market_data",
            "result": "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS",
            "blocked": bool(blockers),
            "blockers": blockers,
            "repair_run_id": BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
            "subscription_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
            "expected_rows": payload["expected_rows"],
            "baseline_summary": dict(baseline),
            "source_status": dict(source_status),
            "contract_result": contract["contract_result"],
            "quality": {
                "P0": int(quality_counts.get("P0", 0)),
                "P1": int(quality_counts.get("P1", 0)),
                "P2": int(quality_counts.get("P2", 0)),
                "items": list(quality_items),
            },
            "forbidden_scope": list(FORBIDDEN_SCOPE),
            "side_effects": side_effects(writes_database=False),
            "generated_at": utc_now_iso(),
        }
    )


def build_dry_run(*, payload: Mapping[str, Any], contract: Mapping[str, Any], preflight: Mapping[str, Any]) -> dict[str, Any]:
    expected = payload["expected_rows"]
    return normalize_jsonable(
        {
            "stage": "N3_ACTION_CONFIRMATION_METRIC_BOARD_LINEAGE_REPAIR_DRY_RUN",
            "layer_role": "N3_market_data",
            "result": "DRY_RUN_PASS" if preflight["result"] == "PREFLIGHT_PASS" else "BLOCKED",
            "blocked": preflight["blocked"],
            "blockers": preflight["blockers"],
            "repair_run_id": BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
            "subscription_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
            "missing_board_objects": payload["missing_board_objects_expected"],
            "subscription_plan": {
                "candidate_rows": expected["subscription_candidate"],
                "subscription_rows": expected["subscription"],
                "pull_plan_rows": expected["pull_plan"],
                "required_data_kind_distribution": {
                    "previous_day_minute_bar_1m": EXPECTED_BOARD_OBJECTS,
                    "minute_bar_1m": EXPECTED_BOARD_OBJECTS,
                },
            },
            "minute_plan": {
                "previous_day_minute_run_id": BOARD_LINEAGE_PREVIOUS_DAY_RUN_ID_20260605,
                "previous_day_minute_rows": expected["previous_day_minute"],
                "today_minute_run_id": BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605,
                "today_cutoff_label": "11:27",
                "today_bars_per_object": TODAY_BARS_PER_OBJECT_UNTIL_1127,
                "today_minute_rows": expected["today_minute"],
            },
            "metric_repair_plan": {
                "metric_repair_run_id": BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
                "additive_metric_rows_max": expected["additive_metric_v2_max"],
                "metric_trace_complete_required": True,
                "db_check_pass_required": True,
            },
            "sample_proof": build_sample_proof(payload),
            "quality": preflight["quality"],
            "rollback": contract["rollback"],
            "forbidden_scope": contract["forbidden_scope"],
            "side_effects": side_effects(writes_database=False),
            "artifacts": {
                "contract_json": DEFAULT_CONTRACT_JSON_PATH,
                "preflight_json": DEFAULT_PREFLIGHT_JSON_PATH,
                "dry_run_json": DEFAULT_DRY_RUN_JSON_PATH,
                "payload_json": DEFAULT_PAYLOAD_JSON_PATH,
                "rollback_sql": DEFAULT_ROLLBACK_SQL_PATH,
            },
            "generated_at": utc_now_iso(),
        }
    )


def build_quality_items(
    *,
    boards: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    subscriptions: Sequence[Mapping[str, Any]],
    pull_plan: Sequence[Mapping[str, Any]],
    baseline: Mapping[str, int],
    source_status: Mapping[str, str | None],
) -> list[dict[str, Any]]:
    board_count = len({row["identity_key"] for row in boards if row.get("identity_key", "").startswith("board:")})
    non_board = [row.get("identity_key") for row in boards if not str(row.get("identity_key") or "").startswith("board:")]
    baseline_nonzero = {key: value for key, value in baseline.items() if key != "total" and int(value or 0) != 0}
    if int(baseline.get("total") or 0) != 0:
        baseline_nonzero.setdefault("total", int(baseline.get("total") or 0))
    source_not_ready = {
        key: value
        for key, value in source_status.items()
        if value not in {"passed", "passed_active"}
    }
    kind_counts = Counter(row["required_data_kind"] for row in subscriptions)
    missing_scope_refs = [
        row["identity_key"]
        for row in boards
        if row.get("source_scope_table") != "board_minute_target_scope" or int(row.get("source_minute_target_scope_id") or 0) <= 0
    ]
    invalid_candidate_scope_tables = sorted(
        {
            str(row.get("source_scope_table") or "")
            for row in candidates
            if row.get("source_scope_table") != "board_minute_target_scope"
        }
    )
    return [
        quality_item(
            "P0",
            "passed" if board_count == EXPECTED_BOARD_OBJECTS and not non_board else "failed",
            "n3_board_lineage_repair_missing_board_count",
            "repair scope must contain exactly the 28 missing board identities and no stock/index rows",
            expected=str(EXPECTED_BOARD_OBJECTS),
            actual=json.dumps({"board_count": board_count, "non_board": non_board}, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if len(candidates) == EXPECTED_BOARD_OBJECTS * 2 and len(subscriptions) == EXPECTED_BOARD_OBJECTS * 2 else "failed",
            "n3_board_lineage_repair_subscription_rows_match",
            "each board must get previous_day_minute_bar_1m and minute_bar_1m scoped subscriptions",
            expected=str(EXPECTED_BOARD_OBJECTS * 2),
            actual=json.dumps({"candidate_rows": len(candidates), "subscription_rows": len(subscriptions)}, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if dict(kind_counts) == {"previous_day_minute_bar_1m": EXPECTED_BOARD_OBJECTS, "minute_bar_1m": EXPECTED_BOARD_OBJECTS} else "failed",
            "n3_board_lineage_repair_required_data_kind_distribution",
            "required_data_kind distribution must be board-only previous-day and today minute scopes",
            expected=json.dumps({"previous_day_minute_bar_1m": EXPECTED_BOARD_OBJECTS, "minute_bar_1m": EXPECTED_BOARD_OBJECTS}, sort_keys=True),
            actual=json.dumps(dict(kind_counts), sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if not missing_scope_refs and not invalid_candidate_scope_tables else "failed",
            "n3_board_lineage_repair_source_scope_maps_to_board_minute_target_scope",
            "subscription control rows must use board_minute_target_scope as DB-accepted source scope while retaining TriggerMatched as trace",
            expected="board_minute_target_scope source_scope_id for every board",
            actual=json.dumps(
                {
                    "missing_or_invalid_scope_refs": missing_scope_refs,
                    "invalid_candidate_scope_tables": invalid_candidate_scope_tables,
                },
                sort_keys=True,
            ),
        ),
        quality_item(
            "P0",
            "passed" if len(pull_plan) == 2 and all(row["asset_kind"] == "board" for row in pull_plan) else "failed",
            "n3_board_lineage_repair_pull_plan_board_only",
            "pull plan must contain exactly two board rows, one per required data kind",
            expected="2 board pull_plan rows",
            actual=json.dumps({"pull_plan_rows": len(pull_plan), "asset_kinds": sorted({row['asset_kind'] for row in pull_plan})}, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if not baseline_nonzero else "failed",
            "n3_board_lineage_repair_scoped_baseline_zero",
            "all scoped run/quality/subscription/minute/metric/event/downstream refs must be zero before future execute",
            expected="0",
            actual=json.dumps(baseline_nonzero, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if not source_not_ready else "failed",
            "n3_board_lineage_repair_source_runs_ready",
            "source N4/N3 runs must remain passed before scoped repair planning",
            expected="passed/passed_active",
            actual=json.dumps(source_not_ready, sort_keys=True),
        ),
        quality_item(
            "P1",
            "warning",
            "n3_board_lineage_repair_metric_v2_waits_for_minute_execute",
            "additive board metric v2 remains a future execute after scoped A1/C1 board minute lineage exists; current gate only plans scope",
            expected="future metric rows pass metric_trace + db_check",
            actual="metric_v2_execute_not_authorized_now",
        ),
    ]


def build_sample_proof(payload: Mapping[str, Any]) -> dict[str, Any]:
    boards = list(payload.get("missing_board_objects") or [])
    return {
        "missing_board_samples": boards[:5],
        "metric_v2_gate": payload.get("metric_v2_eligibility_gate"),
        "all_missing_reason_sample": [
            {
                "identity_key": row.get("identity_key"),
                "excluded_reason": row.get("excluded_reason"),
                "missing_reasons": row.get("missing_reasons"),
            }
            for row in boards[:5]
        ],
    }


def build_board_lineage_repair_rollback_sql(
    metric_run_id: str = BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
) -> str:
    optional_n6_guard = "\n".join(format_optional_downstream_ref_guard(table) for table in N6_DOWNSTREAM_REF_TABLES)
    return f"""-- N3 action-confirmation metric board lineage repair rollback.
-- Scope: delete only additive metric-v2 rows for projection_run_id={metric_run_id}.
-- The scoped subscription/A1/C1 rows have their own future execute rollback gates.
-- Hard-fail before DELETE when event infra or downstream N4/N5/N6 refs exist.

\\set ON_ERROR_STOP on
\\set projection_run_id '{metric_run_id}'

SELECT set_config('app.projection_run_id', :'projection_run_id', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.projection_run_id');
  outbox_refs BIGINT;
  inbox_refs BIGINT;
  checkpoint_refs BIGINT;
  trigger_refs BIGINT;
  action_refs BIGINT;
  n6_refs BIGINT := 0;
  v_count BIGINT;
  touched_refs BIGINT;
  worker_refs BIGINT;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%' OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%' OR last_event_id LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO trigger_refs
  FROM common_trigger_match
  WHERE raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO action_refs
  FROM common_action_event
  WHERE trace_json::TEXT LIKE '%' || target_run_id || '%';

{optional_n6_guard}

  SELECT count(*) INTO touched_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND downstream_layers_touched = true;

  SELECT count(*) INTO worker_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND worker_started = true;

  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0
     OR trigger_refs <> 0 OR action_refs <> 0 OR n6_refs <> 0
     OR touched_refs <> 0 OR worker_refs <> 0 THEN
    RAISE EXCEPTION
      'N3 board lineage metric repair rollback blocked for %, outbox=%, inbox=%, checkpoint=%, trigger=%, action=%, n6=%, downstream_touched=%, worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, trigger_refs, action_refs, n6_refs, touched_refs, worker_refs;
  END IF;
END $$;

BEGIN;

DELETE FROM board_action_confirmation_projection_metric
WHERE projection_run_id = :'projection_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'projection_run_id'
  AND layer_scope = 'market_data_run'
  AND details ->> 'metric_scope' = 'action_confirmation_projection_metric';

DELETE FROM common_market_data_run
WHERE run_id = :'projection_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
"""


def build_board_lineage_subscription_rollback_sql(
    subscription_run_id: str = BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
    previous_day_run_id: str = BOARD_LINEAGE_PREVIOUS_DAY_RUN_ID_20260605,
    today_minute_run_id: str = BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605,
    metric_run_id: str = BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
) -> str:
    optional_n6_guard = "\n".join(format_optional_downstream_ref_guard(table) for table in N6_DOWNSTREAM_REF_TABLES)
    return f"""-- N3 board-lineage scoped subscription control rollback.
-- Scope: delete only subscription control rows for run_id={subscription_run_id}.
-- Hard-fail before DELETE when pull plans were executed, minute facts or metric-v2 rows exist,
-- event infra/downstream refs exist, or worker/downstream flags indicate consumption.

\\set ON_ERROR_STOP on
\\set subscription_run_id '{subscription_run_id}'
\\set previous_day_run_id '{previous_day_run_id}'
\\set today_minute_run_id '{today_minute_run_id}'
\\set metric_run_id '{metric_run_id}'

SELECT set_config('app.subscription_run_id', :'subscription_run_id', false);
SELECT set_config('app.previous_day_run_id', :'previous_day_run_id', false);
SELECT set_config('app.today_minute_run_id', :'today_minute_run_id', false);
SELECT set_config('app.metric_run_id', :'metric_run_id', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.subscription_run_id');
  prev_run_id TEXT := current_setting('app.previous_day_run_id');
  today_run_id TEXT := current_setting('app.today_minute_run_id');
  metric_target_run_id TEXT := current_setting('app.metric_run_id');
  outbox_refs BIGINT;
  inbox_refs BIGINT;
  checkpoint_refs BIGINT;
  trigger_refs BIGINT;
  action_refs BIGINT;
  n6_refs BIGINT := 0;
  v_count BIGINT;
  pull_plan_executed_refs BIGINT;
  minute_fact_refs BIGINT;
  preload_status_refs BIGINT;
  metric_v2_refs BIGINT;
  touched_refs BIGINT;
  worker_refs BIGINT;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id IN (target_run_id, prev_run_id, today_run_id, metric_target_run_id)
     OR payload_json::TEXT LIKE '%' || target_run_id || '%'
     OR payload_json::TEXT LIKE '%' || prev_run_id || '%'
     OR payload_json::TEXT LIKE '%' || today_run_id || '%'
     OR payload_json::TEXT LIKE '%' || metric_target_run_id || '%';

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id IN (target_run_id, prev_run_id, today_run_id, metric_target_run_id)
     OR payload_json::TEXT LIKE '%' || target_run_id || '%'
     OR payload_json::TEXT LIKE '%' || prev_run_id || '%'
     OR payload_json::TEXT LIKE '%' || today_run_id || '%'
     OR payload_json::TEXT LIKE '%' || metric_target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || prev_run_id || '%'
     OR raw_json::TEXT LIKE '%' || today_run_id || '%'
     OR raw_json::TEXT LIKE '%' || metric_target_run_id || '%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || prev_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || today_run_id || '%'
     OR checkpoint_payload::TEXT LIKE '%' || metric_target_run_id || '%'
     OR last_event_id LIKE '%' || target_run_id || '%'
     OR last_event_id LIKE '%' || prev_run_id || '%'
     OR last_event_id LIKE '%' || today_run_id || '%'
     OR last_event_id LIKE '%' || metric_target_run_id || '%';

  SELECT count(*) INTO trigger_refs
  FROM common_trigger_match
  WHERE raw_json::TEXT LIKE '%' || target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || prev_run_id || '%'
     OR raw_json::TEXT LIKE '%' || today_run_id || '%'
     OR raw_json::TEXT LIKE '%' || metric_target_run_id || '%';

  SELECT count(*) INTO action_refs
  FROM common_action_event
  WHERE trace_json::TEXT LIKE '%' || target_run_id || '%'
     OR trace_json::TEXT LIKE '%' || prev_run_id || '%'
     OR trace_json::TEXT LIKE '%' || today_run_id || '%'
     OR trace_json::TEXT LIKE '%' || metric_target_run_id || '%';

{optional_n6_guard}

  SELECT count(*) INTO pull_plan_executed_refs
  FROM common_market_data_pull_plan
  WHERE run_id = target_run_id
    AND (execute_allowed = true OR plan_status IN ('executed', 'running', 'pulled', 'completed'));

  SELECT count(*) INTO minute_fact_refs
  FROM board_minute_bar_1m
  WHERE run_id IN (prev_run_id, today_run_id)
     OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO preload_status_refs
  FROM board_previous_day_minute_preload_status
  WHERE run_id = prev_run_id OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO metric_v2_refs
  FROM board_action_confirmation_projection_metric
  WHERE projection_run_id = metric_target_run_id
     OR source_minute_refs::TEXT LIKE '%' || target_run_id || '%'
     OR previous_day_minute_refs::TEXT LIKE '%' || target_run_id || '%'
     OR source_fact_ids::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO touched_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND downstream_layers_touched = true;

  SELECT count(*) INTO worker_refs
  FROM common_market_data_run
  WHERE run_id = target_run_id AND worker_started = true;

  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0
     OR trigger_refs <> 0 OR action_refs <> 0 OR n6_refs <> 0
     OR pull_plan_executed_refs <> 0 OR minute_fact_refs <> 0
     OR preload_status_refs <> 0 OR metric_v2_refs <> 0
     OR touched_refs <> 0 OR worker_refs <> 0 THEN
    RAISE EXCEPTION
      'N3 board-lineage subscription rollback blocked for %, outbox=%, inbox=%, checkpoint=%, trigger=%, action=%, n6=%, pull_plan_executed=%, minute=%, preload_status=%, metric_v2=%, downstream_touched=%, worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, trigger_refs, action_refs, n6_refs,
      pull_plan_executed_refs, minute_fact_refs, preload_status_refs, metric_v2_refs, touched_refs, worker_refs;
  END IF;
END $$;

BEGIN;

DELETE FROM common_market_data_pull_plan
WHERE run_id = :'subscription_run_id';

DELETE FROM common_market_data_subscription
WHERE run_id = :'subscription_run_id';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = :'subscription_run_id';

DELETE FROM common_market_data_quality_item
WHERE run_id = :'subscription_run_id';

DELETE FROM common_market_data_run
WHERE run_id = :'subscription_run_id'
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;
"""


def format_optional_downstream_ref_guard(table_name: str) -> str:
    return f"""  IF to_regclass('public.{table_name}') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.{table_name} AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;"""


def build_from_db(dsn: str = DEFAULT_DSN) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        missing = fetch_missing_board_rows(cur)
        baseline = fetch_scoped_baseline(cur)
        source_status = fetch_source_status(cur)
    return build_board_lineage_repair_artifacts(
        missing_board_rows=missing,
        baseline=baseline,
        source_status=source_status,
    )


def fetch_missing_board_rows(cur: Any) -> list[dict[str, Any]]:
    n4_events = load_n4_matched_events_for_run(cur, TRIGGER_EXECUTE_RUN_ID_20260605)
    projection_rows = load_realtime_projection_rows_for_events(
        cur,
        projection_run_id=SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
        n4_events=n4_events,
    )
    groups = choose_20260605_metric_trace_source_groups(cur, projection_rows)
    candidate_rows_by_asset = build_20260605_metric_rows(
        cur,
        groups,
        n4_events,
        projection_rows,
        projection_run_id=BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
    )
    candidate_rows_by_identity = {
        str(row.get("identity_key")): row
        for rows in candidate_rows_by_asset.values()
        for row in rows
    }
    existing = flatten_identity_sets(load_existing_metric_identities(cur, projection_run_id=COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605))
    existing.update(flatten_identity_sets(load_existing_metric_identities(cur, projection_run_id=COVERAGE_REPAIR_RUN_ID_20260605)))
    board_identity = fetch_board_identity_rows(cur)
    match_rows = fetch_trigger_match_rows(cur)
    minute_scope_rows = fetch_board_minute_target_scope_rows(cur)
    output: list[dict[str, Any]] = []
    for identity, events in sorted(n4_events.items()):
        if not identity.startswith("board:") or identity in existing:
            continue
        projection_row = projection_rows.get(identity)
        decision = classify_20260605_metric_trace_eligibility(
            metric_row=candidate_rows_by_identity.get(identity),
            projection_row=projection_row,
            original_metric_identities=existing,
        )
        if decision.get("excluded_reason") != "lineage_missing":
            continue
        match = match_rows.get(identity) or {}
        scope = minute_scope_rows.get((identity, int(match.get("source_condition_pool_id") or 0))) or {}
        identity_row = board_identity.get(identity) or {}
        output.append(
            {
                "identity_key": identity,
                "code": identity_row.get("board_code") or identity.rsplit(":", 1)[-1],
                "name": identity_row.get("board_name") or identity,
                "board_type": identity_row.get("board_type"),
                "trigger_match_id": match.get("trigger_match_id") or events[0].trigger_match_id,
                "source_minute_target_scope_id": scope.get("board_minute_target_scope_id") or 0,
                "source_condition_pool_id": match.get("source_condition_pool_id") or 0,
                "source_condition_basis_id": match.get("source_condition_basis_id") or 0,
                "direction": match.get("direction") or events[0].direction,
                "signal_type": match.get("signal_type") or events[0].signal_type,
                "condition_key": match.get("condition_key") or events[0].condition_key,
                "source_scope_direction": scope.get("direction"),
                "source_scope_condition_key": scope.get("condition_key"),
                "source_scope_allowed_signal_types": list(scope.get("allowed_signal_types") or []),
                "projection_status": (projection_row or {}).get("projection_status"),
                "projection_quality_status": (projection_row or {}).get("projection_quality_status"),
                "trace_status": (projection_row or {}).get("trace_status"),
                "excluded_reason": decision.get("excluded_reason"),
                "metric_trace_complete": decision.get("metric_trace_complete"),
                "db_check_pass": decision.get("db_check_pass"),
                "missing_reasons": projection_missing_reasons(projection_row),
            }
        )
    return output


def fetch_board_identity_rows(cur: Any) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT board_identity_key, board_code, board_name, board_type
        FROM board_identity
        """
    )
    return {str(row["board_identity_key"]): dict(row) for row in cur.fetchall()}


def fetch_trigger_match_rows(cur: Any) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT trigger_match_id, identity_key, direction, signal_type, condition_key,
               source_condition_pool_id, source_condition_basis_id
        FROM common_trigger_match
        WHERE run_id = %s
          AND asset_kind = 'board'
          AND output_event_type = 'TriggerMatched'
        """,
        (TRIGGER_EXECUTE_RUN_ID_20260605,),
    )
    return {str(row["identity_key"]): dict(row) for row in cur.fetchall()}


def fetch_board_minute_target_scope_rows(cur: Any) -> dict[tuple[str, int], dict[str, Any]]:
    cur.execute(
        """
        SELECT board_minute_target_scope_id,
               board_identity_key,
               source_condition_pool_id,
               direction,
               condition_key,
               allowed_signal_types
        FROM board_minute_target_scope
        WHERE run_id = %s
        """,
        (SOURCE_CONDITION_RUN_ID_20260605,),
    )
    return {
        (str(row["board_identity_key"]), int(row["source_condition_pool_id"] or 0)): dict(row)
        for row in cur.fetchall()
    }


def fetch_scoped_baseline(cur: Any) -> dict[str, int]:
    run_ids = [
        BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
        BOARD_LINEAGE_PREVIOUS_DAY_RUN_ID_20260605,
        BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605,
        BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
    ]
    baseline = {
        "common_market_data_run": count_run_ids(cur, "common_market_data_run", run_ids),
        "common_market_data_quality_item": count_run_ids(cur, "common_market_data_quality_item", run_ids),
        "common_market_data_subscription_candidate": count_run_ids(cur, "common_market_data_subscription_candidate", [BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605]),
        "common_market_data_subscription": count_run_ids(cur, "common_market_data_subscription", [BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605]),
        "common_market_data_pull_plan": count_run_ids(cur, "common_market_data_pull_plan", [BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605]),
        "board_minute_bar_1m_previous_day": count_run_ids(cur, "board_minute_bar_1m", [BOARD_LINEAGE_PREVIOUS_DAY_RUN_ID_20260605]),
        "board_minute_bar_1m_today": count_run_ids(cur, "board_minute_bar_1m", [BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605]),
        "board_previous_day_minute_preload_status": count_run_ids(cur, "board_previous_day_minute_preload_status", [BOARD_LINEAGE_PREVIOUS_DAY_RUN_ID_20260605]),
        "board_action_confirmation_projection_metric": count_projection_run(cur, "board_action_confirmation_projection_metric", BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605),
        "common_event_outbox_refs": count_event_refs(cur, "common_event_outbox", run_ids),
        "common_event_inbox_refs": count_inbox_refs(cur, run_ids),
        "common_event_consumer_checkpoint_refs": count_checkpoint_refs(cur, run_ids),
    }
    baseline["total"] = sum(baseline.values())
    return baseline


def count_run_ids(cur: Any, table: str, run_ids: Sequence[str]) -> int:
    cur.execute(f"SELECT count(*) AS c FROM {table} WHERE run_id = ANY(%s)", (list(run_ids),))
    return int(cur.fetchone()["c"] or 0)


def count_projection_run(cur: Any, table: str, run_id: str) -> int:
    cur.execute(f"SELECT count(*) AS c FROM {table} WHERE projection_run_id = %s", (run_id,))
    return int(cur.fetchone()["c"] or 0)


def count_event_refs(cur: Any, table: str, run_ids: Sequence[str]) -> int:
    total = 0
    for run_id in run_ids:
        cur.execute(
            f"SELECT count(*) AS c FROM {table} WHERE source_run_id = %s OR payload_json::TEXT LIKE %s",
            (run_id, f"%{run_id}%"),
        )
        total += int(cur.fetchone()["c"] or 0)
    return total


def count_inbox_refs(cur: Any, run_ids: Sequence[str]) -> int:
    total = 0
    for run_id in run_ids:
        cur.execute(
            """
            SELECT count(*) AS c
            FROM common_event_inbox
            WHERE source_run_id = %s OR payload_json::TEXT LIKE %s OR raw_json::TEXT LIKE %s
            """,
            (run_id, f"%{run_id}%", f"%{run_id}%"),
        )
        total += int(cur.fetchone()["c"] or 0)
    return total


def count_checkpoint_refs(cur: Any, run_ids: Sequence[str]) -> int:
    total = 0
    for run_id in run_ids:
        cur.execute(
            """
            SELECT count(*) AS c
            FROM common_event_consumer_checkpoint
            WHERE checkpoint_payload::TEXT LIKE %s OR last_event_id LIKE %s
            """,
            (f"%{run_id}%", f"%{run_id}%"),
        )
        total += int(cur.fetchone()["c"] or 0)
    return total


def fetch_source_status(cur: Any) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    cur.execute("SELECT status FROM common_condition_run WHERE run_id = %s", (SOURCE_CONDITION_RUN_ID_20260605,))
    row = cur.fetchone()
    result["source_condition"] = row["status"] if row else None
    for key, run_id in {
        "source_snapshot": SOURCE_SNAPSHOT_RUN_ID_20260605,
        "source_realtime_projection": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
        "source_today_minute": SOURCE_TODAY_MINUTE_RUN_ID_20260605,
        "source_previous_day_minute": SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
    }.items():
        cur.execute("SELECT status FROM common_market_data_run WHERE run_id = %s", (run_id,))
        row = cur.fetchone()
        result[key] = row["status"] if row else None
    cur.execute("SELECT status FROM common_trigger_run WHERE run_id = %s", (TRIGGER_EXECUTE_RUN_ID_20260605,))
    row = cur.fetchone()
    result["n4_trigger_execute"] = row["status"] if row else None
    return result


def write_artifacts(
    *,
    dsn: str = DEFAULT_DSN,
    contract_json_path: str | Path = DEFAULT_CONTRACT_JSON_PATH,
    contract_md_path: str | Path = DEFAULT_CONTRACT_MD_PATH,
    preflight_json_path: str | Path = DEFAULT_PREFLIGHT_JSON_PATH,
    preflight_md_path: str | Path = DEFAULT_PREFLIGHT_MD_PATH,
    dry_run_json_path: str | Path = DEFAULT_DRY_RUN_JSON_PATH,
    dry_run_md_path: str | Path = DEFAULT_DRY_RUN_MD_PATH,
    payload_json_path: str | Path = DEFAULT_PAYLOAD_JSON_PATH,
    rollback_sql_path: str | Path = DEFAULT_ROLLBACK_SQL_PATH,
    subscription_contract_json_path: str | Path = DEFAULT_SUBSCRIPTION_CONTRACT_JSON_PATH,
    subscription_contract_md_path: str | Path = DEFAULT_SUBSCRIPTION_CONTRACT_MD_PATH,
    subscription_preflight_json_path: str | Path = DEFAULT_SUBSCRIPTION_PREFLIGHT_JSON_PATH,
    subscription_preflight_md_path: str | Path = DEFAULT_SUBSCRIPTION_PREFLIGHT_MD_PATH,
    subscription_rollback_sql_path: str | Path = DEFAULT_SUBSCRIPTION_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    artifacts = build_from_db(dsn)
    subscription_artifacts = build_subscription_execute_artifacts(
        repair_payload=artifacts["payload"],
        repair_preflight=artifacts["preflight"],
    )
    write_json(payload_json_path, artifacts["payload"])
    write_json(contract_json_path, artifacts["contract"])
    write_text(contract_md_path, format_contract_markdown(artifacts["contract"]))
    write_json(preflight_json_path, artifacts["preflight"])
    write_text(preflight_md_path, format_preflight_markdown(artifacts["preflight"]))
    write_json(dry_run_json_path, artifacts["dry_run"])
    write_text(dry_run_md_path, format_dry_run_markdown(artifacts["dry_run"]))
    write_text(rollback_sql_path, artifacts["rollback_sql"])
    write_json(subscription_contract_json_path, subscription_artifacts["contract"])
    write_text(subscription_contract_md_path, format_subscription_contract_markdown(subscription_artifacts["contract"]))
    write_json(subscription_preflight_json_path, subscription_artifacts["preflight"])
    write_text(subscription_preflight_md_path, format_subscription_preflight_markdown(subscription_artifacts["preflight"]))
    write_text(subscription_rollback_sql_path, subscription_artifacts["rollback_sql"])
    return {
        "result": artifacts["dry_run"]["result"],
        "repair_run_id": BOARD_LINEAGE_METRIC_REPAIR_RUN_ID_20260605,
        "subscription_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
        "contract_json": str(contract_json_path),
        "preflight_json": str(preflight_json_path),
        "dry_run_json": str(dry_run_json_path),
        "payload_json": str(payload_json_path),
        "rollback_sql": str(rollback_sql_path),
        "subscription_contract_json": str(subscription_contract_json_path),
        "subscription_preflight_json": str(subscription_preflight_json_path),
        "subscription_rollback_sql": str(subscription_rollback_sql_path),
        "subscription_execute_command": SUBSCRIPTION_EXECUTE_COMMAND,
        "expected_rows": artifacts["dry_run"]["metric_repair_plan"],
        "quality": artifacts["dry_run"]["quality"],
    }


def format_contract_markdown(contract: Mapping[str, Any]) -> str:
    expected = contract.get("expected_scope") or {}
    return f"""# N3 Action-Confirmation Metric Board Lineage Repair Contract

Status: {contract.get("contract_result")}

```text
repair_run_id={contract.get("repair_run_id")}
subscription_run_id={contract.get("subscription_run_id")}
board_objects={expected.get("board_objects")}
previous_day_minute_rows={expected.get("previous_day_minute_rows")}
today_minute_rows_until_1127={expected.get("today_minute_rows_until_1127")}
additive_board_metric_v2_max_rows={expected.get("additive_board_metric_v2_max_rows")}
rollback_sql={contract.get("rollback", {}).get("rollback_sql_path")}
execute_authorized_now=false
```
"""


def format_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    quality = preflight.get("quality") or {}
    return f"""# N3 Action-Confirmation Metric Board Lineage Repair Preflight

Status: {preflight.get("result")}

```text
repair_run_id={preflight.get("repair_run_id")}
subscription_run_id={preflight.get("subscription_run_id")}
P0/P1/P2={quality.get("P0")}/{quality.get("P1")}/{quality.get("P2")}
blockers={preflight.get("blockers")}
writes_database=false
```
"""


def format_dry_run_markdown(dry_run: Mapping[str, Any]) -> str:
    minute = dry_run.get("minute_plan") or {}
    metric = dry_run.get("metric_repair_plan") or {}
    quality = dry_run.get("quality") or {}
    return f"""# N3 Action-Confirmation Metric Board Lineage Repair Dry Run

Status: {dry_run.get("result")}

```text
repair_run_id={dry_run.get("repair_run_id")}
missing_board_objects={dry_run.get("missing_board_objects")}
previous_day_minute_rows={minute.get("previous_day_minute_rows")}
today_minute_rows={minute.get("today_minute_rows")}
additive_metric_rows_max={metric.get("additive_metric_rows_max")}
P0/P1/P2={quality.get("P0")}/{quality.get("P1")}/{quality.get("P2")}
writes_database=false
```
"""


def format_subscription_contract_markdown(contract: Mapping[str, Any]) -> str:
    return f"""# N3 Board-Lineage Scoped Subscription Execute Contract

Status: {contract.get("contract_result")}

```text
subscription_run_id={contract.get("subscription_run_id")}
execute_target={contract.get("execute_target")}
board_objects={contract.get("board_objects")}
subscription_candidates={contract.get("subscription_candidate_rows")}
subscriptions={contract.get("subscription_rows")}
pull_plan_rows={contract.get("pull_plan_rows")}
previous_day_planned_rows={contract.get("previous_day_planned_rows")}
today_planned_rows_until_1127={contract.get("today_planned_rows_until_1127")}
metric_v2_execute={contract.get("metric_v2_execute")}
execute_command={contract.get("execute_command")}
rollback_sql={contract.get("rollback", {}).get("rollback_sql_path")}
```
"""


def format_subscription_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    quality = preflight.get("quality") or {}
    return f"""# N3 Board-Lineage Scoped Subscription Execute Preflight

Status: {preflight.get("result")}

```text
subscription_run_id={preflight.get("subscription_run_id")}
execute_target={preflight.get("execute_target")}
board_objects={preflight.get("board_objects")}
subscription_candidates={preflight.get("subscription_candidate_rows")}
subscriptions={preflight.get("subscription_rows")}
pull_plan_rows={preflight.get("pull_plan_rows")}
P0/P1/P2={quality.get("P0")}/{quality.get("P1")}/{quality.get("P2")}
blockers={preflight.get("blockers")}
metric_v2_execute={preflight.get("metric_v2_execute")}
```
"""


def subscription_side_effects(*, writes_database: bool) -> dict[str, bool]:
    return {
        "writes_database": writes_database,
        "writes_subscription_control_rows": writes_database,
        "writes_run_or_quality": writes_database,
        "writes_market_data_facts": False,
        "writes_snapshot_or_minute": False,
        "writes_action_confirmation_metric_rows": False,
        "writes_realtime_projection_metric": False,
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "enters_n4_n5_n6": False,
        "worker_started": False,
        "delivery_push_voice_mobile": False,
        "sim_position_pnl_real_trade": False,
        "real_trade": False,
        "old_system_touched": False,
    }


def run_board_lineage_scoped_subscription_execute(
    *,
    dsn: str,
    contract_path: str | Path,
    preflight_path: str | Path,
    payload_path: str | Path,
    json_report_path: str | Path = DEFAULT_SUBSCRIPTION_EXECUTE_REPORT_JSON_PATH,
    markdown_report_path: str | Path = DEFAULT_SUBSCRIPTION_EXECUTE_REPORT_MD_PATH,
    execute: bool,
    user_confirmed: bool,
) -> dict[str, Any]:
    flag_blockers = []
    if not execute:
        flag_blockers.append("missing_execute_flag")
    if not user_confirmed:
        flag_blockers.append("missing_user_confirmed_flag")
    if flag_blockers:
        return subscription_blocked_report(
            blocked_reasons=flag_blockers,
            blocked_before_database_write=True,
            contract_path=contract_path,
            preflight_path=preflight_path,
            payload_path=payload_path,
        )

    contract = read_json(contract_path)
    preflight = read_json(preflight_path)
    payload = read_json(payload_path)
    validation = validate_subscription_execute_inputs(
        contract_candidate=contract,
        preflight_candidate=preflight,
        payload=payload,
    )
    if not validation["valid"]:
        return subscription_blocked_report(
            blocked_reasons=validation["blocked_reasons"],
            blocked_before_database_write=True,
            contract_path=contract_path,
            preflight_path=preflight_path,
            payload_path=payload_path,
            validation=validation,
        )
    dry_run_report = build_subscription_execute_dry_run_report(
        payload=payload,
        repair_preflight=preflight,
    )
    pre_backup = capture_subscription_execution_backup(
        dsn,
        phase="before_board_lineage_subscription_execute",
        execute_run_id=BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
    )
    if pre_backup.get("target_run_exists"):
        return subscription_blocked_report(
            blocked_reasons=["subscription_run_already_exists"],
            blocked_before_database_write=True,
            contract_path=contract_path,
            preflight_path=preflight_path,
            payload_path=payload_path,
            validation=validation,
        )

    write_result = persist_subscription_plan(
        dsn=dsn,
        dry_run_report=dry_run_report,
        execute_run_id=BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
    )
    post_backup = capture_subscription_execution_backup(
        dsn,
        phase="after_board_lineage_subscription_execute",
        execute_run_id=BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
    )
    quality = dry_run_report["quality"]
    report = {
        "result": "EXECUTE_PASS",
        "stage": "N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE",
        "layer_role": "N3_market_data",
        "subscription_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
        "run_status": (post_backup.get("market_data_run_row") or {}).get("status") or "passed",
        "actual_rows": {
            "common_market_data_run": int(write_result.get("market_data_run_rows_written") or 0),
            "common_market_data_quality_item": int(write_result.get("quality_item_rows_written") or 0),
            "common_market_data_subscription_candidate": int(write_result.get("candidate_rows_written") or 0),
            "common_market_data_subscription": int(write_result.get("subscription_rows_written") or 0),
            "common_market_data_pull_plan": int(write_result.get("pull_plan_rows_written") or 0),
        },
        "write_result": dict(write_result),
        "quality": {
            "P0": int(quality.get("p0_count") or 0),
            "P1": int(quality.get("p1_count") or 0),
            "P2": int(quality.get("p2_count") or 0),
            "items": quality.get("items") or [],
        },
        "pre_backup": pre_backup,
        "post_backup": post_backup,
        "side_effects": subscription_side_effects(writes_database=True),
        "rollback": {
            "rollback_safe": True,
            "rollback_sql_path": DEFAULT_SUBSCRIPTION_ROLLBACK_SQL_PATH,
        },
        "report_artifacts": {
            "json_report_path": str(json_report_path),
            "markdown_report_path": str(markdown_report_path),
        },
        "generated_at": utc_now_iso(),
    }
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_subscription_execute_report_markdown(report))
    return normalize_jsonable(report)


def subscription_blocked_report(
    *,
    blocked_reasons: Sequence[str],
    blocked_before_database_write: bool,
    contract_path: str | Path,
    preflight_path: str | Path,
    payload_path: str | Path,
    validation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "result": "BLOCKED",
        "stage": "N3_BOARD_LINEAGE_SCOPED_SUBSCRIPTION_EXECUTE",
        "layer_role": "N3_market_data",
        "subscription_run_id": BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
        "blocked_reasons": list(blocked_reasons),
        "blocked_before_database_write": blocked_before_database_write,
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "payload_path": str(payload_path),
        "validation": dict(validation or {}),
        "side_effects": subscription_side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }


def format_subscription_execute_report_markdown(report: Mapping[str, Any]) -> str:
    rows = report.get("actual_rows") or {}
    quality = report.get("quality") or {}
    rollback = report.get("rollback") or {}
    return f"""# N3 Board-Lineage Scoped Subscription Execute Report

Status: {report.get("result")}

```text
subscription_run_id={report.get("subscription_run_id")}
run_status={report.get("run_status")}
candidate_rows={rows.get("common_market_data_subscription_candidate")}
subscription_rows={rows.get("common_market_data_subscription")}
pull_plan_rows={rows.get("common_market_data_pull_plan")}
P0/P1/P2={quality.get("P0")}/{quality.get("P1")}/{quality.get("P2")}
writes_outbox=false
market_data_fact_written=false
rollback_safe={rollback.get("rollback_safe")}
rollback_sql={rollback.get("rollback_sql_path")}
```
"""


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
