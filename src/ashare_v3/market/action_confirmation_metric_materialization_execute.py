"""Execute 20260603 N3 action-confirmation metric materialization.

This runner is payload-driven and inert unless both ``--execute`` and
``--user-confirmed`` are provided. The payload is built from the already
approved 20260603 dry-run lineage and carries per-row source minute run ids,
so execute never re-computes from N4/N5 and never mutates N4 payloads.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from ashare_v3.market.query_audit_phase3 import (
    audited_n3_market_execute_connect,
    audited_n3_market_readonly_plan_connect,
)
from psycopg.types.json import Jsonb

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.action_confirmation_projection_execute import (
    insert_action_confirmation_metric_rows,
)
from ashare_v3.market.action_confirmation_projection_plan import (
    ASSET_KINDS,
    IDENTITY_COLUMNS,
    METRIC_TABLES,
    MINUTE_TABLES,
    build_metric_candidate_rows_from_sources,
    load_minute_rows_for_metric_dry_run,
    load_snapshot_rows_for_metric_dry_run,
    normalize_jsonable,
    simulate_metric_ready_db_check,
    total_counts,
)
from ashare_v3.market.previous_day_preload_execute import utc_now_iso, write_json, write_text

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - script import fallback
    from scripts.check_condition_source_ready import DEFAULT_DSN


TARGET_RUN_ID = (
    "action_confirmation_projection_metric_20260603__"
    "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1"
)
TRIGGER_EXECUTE_RUN_ID = "trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1"
PROJECTION_ENRICHMENT_V4_RUN_ID = (
    "projection_enrichment_v4_20260603_until_1500__"
    "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1"
)
SOURCE_CONDITION_RUN_ID = "condition_layer_20260602_source_20260602_v1"
SOURCE_SNAPSHOT_RUN_ID = (
    "realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1"
)
FOR_TRADE_DATE = "20260603"
SOURCE_TRADE_DATE = "20260602"
PROJECTION_SCHEMA_VERSION = "n3.action_confirmation_metric.v1"

EXPECTED_ROW_COUNTS = {"stock": 640, "index": 34, "board": 148, "total": 822}
EXPECTED_N4_MATCHED = 863
EXPECTED_METRIC_READY = 822

MATERIALIZATION_TABLES = dict(METRIC_TABLES)
ALLOWED_WRITE_TABLES = [
    "common_market_data_run",
    "common_market_data_quality_item",
    "stock_action_confirmation_projection_metric",
    "index_action_confirmation_projection_metric",
    "board_action_confirmation_projection_metric",
]
REQUESTED_TARGET_ALIASES = [
    "stock_action_confirmation_metric",
    "index_action_confirmation_metric",
    "board_action_confirmation_metric",
]
FORBIDDEN_WRITE_TABLES = [
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "stock_projection_enrichment_v4_metric",
    "index_projection_enrichment_v4_metric",
    "board_projection_enrichment_v4_metric",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "stock_realtime_daily_snapshot",
    "index_realtime_daily_snapshot",
    "board_realtime_daily_snapshot",
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "N4/N5/N6 tables",
    "worker",
    "old system",
    "real trading",
]

N6_DOWNSTREAM_REF_TABLES = [
    "user_card_projection",
    "user_signal_projection",
    "user_signal_card",
    "user_notification_queue",
    "user_sim_order",
    "user_sim_trade",
    "user_sim_position",
    "n6_virtual_account",
    "n6_virtual_order",
    "n6_virtual_trade",
    "n6_virtual_position",
    "n6_virtual_position_event",
    "n6_virtual_pnl_snapshot",
]

DEFAULT_PAYLOAD_PATH = "docs/N3_action_confirmation_metric_20260603_materialization_payload.json"
DEFAULT_CONTRACT_PATH = "docs/N3_action_confirmation_metric_20260603_materialization_contract.json"
DEFAULT_CONTRACT_MD_PATH = "docs/N3_ACTION_CONFIRMATION_METRIC_20260603_MATERIALIZATION_CONTRACT.md"
DEFAULT_PREFLIGHT_PATH = "docs/N3_action_confirmation_metric_20260603_materialization_preflight.json"
DEFAULT_PREFLIGHT_MD_PATH = "docs/N3_ACTION_CONFIRMATION_METRIC_20260603_MATERIALIZATION_PREFLIGHT.md"
DEFAULT_REPORT_PATH = "docs/N3_action_confirmation_metric_20260603_materialization_execute_report.json"
DEFAULT_REPORT_MD_PATH = "docs/N3_ACTION_CONFIRMATION_METRIC_20260603_MATERIALIZATION_EXECUTE_REPORT.md"
DEFAULT_ROLLBACK_SQL_PATH = "sql/N3_action_confirmation_metric_20260603_materialization_rollback.sql"

SCRIPT_PATH = "scripts/run_n3_action_confirmation_metric_materialization_execute.py"
EXECUTE_COMMAND = (
    "PYTHONPATH=src:scripts python3 "
    "scripts/run_n3_action_confirmation_metric_materialization_execute.py "
    "--payload-path docs/N3_action_confirmation_metric_20260603_materialization_payload.json "
    "--contract-path docs/N3_action_confirmation_metric_20260603_materialization_contract.json "
    "--execute --user-confirmed"
)

TARGET_RUN_ID_20260605 = (
    "action_confirmation_projection_metric_20260605__"
    "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
)
TRIGGER_EXECUTE_RUN_ID_20260605 = "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
SOURCE_CONDITION_RUN_ID_20260605 = "condition_layer_20260604_source_20260604_v1"
SOURCE_SNAPSHOT_RUN_ID_20260605 = (
    "realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1"
)
SOURCE_REALTIME_PROJECTION_RUN_ID_20260605 = (
    "realtime_projection_metric_20260605_live2_compat__"
    "realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1"
)
SOURCE_SUBSCRIPTION_RUN_ID_20260605 = "market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1"
EXPANSION_SUBSCRIPTION_RUN_ID_20260605 = (
    "market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1"
)
SOURCE_TODAY_MINUTE_RUN_ID_20260605 = (
    "today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1"
)
EXPANSION_TODAY_MINUTE_RUN_ID_20260605 = (
    "today_minute_bar_1m_20260605_until_1127_b2_stock_index_lineage_expansion__"
    "market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1"
)
SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605 = (
    "previous_day_minute_preload_20260604_for_20260605__"
    "market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1"
)
EXPANSION_PREVIOUS_DAY_MINUTE_RUN_ID_20260605 = (
    "previous_day_minute_preload_20260604_for_20260605_b2_stock_index_lineage_expansion__"
    "market_data_subscription_20260605_b2_stock_index_lineage_expansion_condition_layer_20260604_source_20260604_v1"
)

EXPECTED_ROW_COUNTS_20260605 = {"stock": 595, "index": 0, "board": 0, "total": 595}
EXPECTED_N4_MATCHED_20260605 = 1240
READY_BACKED_COUNTS_20260605 = {"stock": 595, "index": 0, "board": 0, "total": 595}
NOT_READY_BACKED_COUNTS_20260605 = {"stock": 584, "index": 1, "board": 60, "total": 645}

DEFAULT_PAYLOAD_PATH_20260605 = "docs/N3_20260605_action_confirmation_metric_payload.json"
DEFAULT_CONTRACT_PATH_20260605 = "docs/N3_20260605_ACTION_CONFIRMATION_METRIC_CONTRACT.json"
DEFAULT_CONTRACT_MD_PATH_20260605 = "docs/N3_20260605_ACTION_CONFIRMATION_METRIC_CONTRACT.md"
DEFAULT_PREFLIGHT_PATH_20260605 = "docs/N3_20260605_ACTION_CONFIRMATION_METRIC_PREFLIGHT.json"
DEFAULT_PREFLIGHT_MD_PATH_20260605 = "docs/N3_20260605_ACTION_CONFIRMATION_METRIC_PREFLIGHT.md"
DEFAULT_DRY_RUN_PATH_20260605 = "docs/N3_20260605_action_confirmation_metric_dry_run_report.json"
DEFAULT_DRY_RUN_MD_PATH_20260605 = "docs/N3_20260605_ACTION_CONFIRMATION_METRIC_DRY_RUN_REPORT.md"
DEFAULT_ROLLBACK_SQL_PATH_20260605 = "sql/N3_action_confirmation_metric_20260605_materialization_rollback.sql"

DEFAULT_REPAIRED_CONTEXT_PAYLOAD_PATH_20260605 = (
    "docs/N3_20260605_repaired_context_action_confirmation_metric_payload.json"
)
DEFAULT_REPAIRED_CONTEXT_CONTRACT_PATH_20260605 = (
    "docs/N3_20260605_REPAIRED_CONTEXT_ACTION_CONFIRMATION_METRIC_CONTRACT.json"
)
DEFAULT_REPAIRED_CONTEXT_CONTRACT_MD_PATH_20260605 = (
    "docs/N3_20260605_REPAIRED_CONTEXT_ACTION_CONFIRMATION_METRIC_CONTRACT.md"
)
DEFAULT_REPAIRED_CONTEXT_PREFLIGHT_PATH_20260605 = (
    "docs/N3_20260605_REPAIRED_CONTEXT_ACTION_CONFIRMATION_METRIC_PREFLIGHT.json"
)
DEFAULT_REPAIRED_CONTEXT_PREFLIGHT_MD_PATH_20260605 = (
    "docs/N3_20260605_REPAIRED_CONTEXT_ACTION_CONFIRMATION_METRIC_PREFLIGHT.md"
)
DEFAULT_REPAIRED_CONTEXT_DRY_RUN_PATH_20260605 = (
    "docs/N3_20260605_repaired_context_action_confirmation_metric_dry_run_report.json"
)
DEFAULT_REPAIRED_CONTEXT_DRY_RUN_MD_PATH_20260605 = (
    "docs/N3_20260605_REPAIRED_CONTEXT_ACTION_CONFIRMATION_METRIC_DRY_RUN_REPORT.md"
)
DEFAULT_REPAIRED_CONTEXT_ROLLBACK_SQL_PATH_20260605 = (
    "sql/N3_repaired_context_action_confirmation_metric_20260605_materialization_rollback.sql"
)

COVERAGE_REPAIR_RUN_ID_20260605 = (
    "action_confirmation_projection_metric_20260605_repair_v1__"
    "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
)
COVERAGE_POLICY_VERSION_20260605 = "n3.action_confirmation_metric.coverage_policy.v2"
COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605 = TARGET_RUN_ID_20260605
COVERAGE_REPAIR_EXPECTED_ROWS_20260605 = {"stock": 256, "index": 0, "board": 5, "total": 261}
COVERAGE_REPAIR_REPAIRED_TOTAL_COVERAGE_20260605 = {"stock": 572, "index": 0, "board": 5, "total": 577}
COVERAGE_REPAIR_REMAINING_EXCLUDED_20260605 = {"stock": 0, "index": 0, "board": 28, "total": 28}

BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605 = (
    "action_confirmation_projection_metric_20260605_board_lineage_repair_v2__"
    "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
)
BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605 = (
    "market_data_subscription_20260605_action_metric_board_lineage_repair_"
    "condition_layer_20260604_source_20260604_v1"
)
BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605 = (
    "today_minute_bar_1m_20260605_until_1127_action_metric_board_lineage_repair__"
    "market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1"
)
BOARD_LINEAGE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605 = (
    "previous_day_minute_preload_20260604_for_20260605_action_metric_board_lineage_repair__"
    "market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1"
)
BOARD_LINEAGE_POLICY_VERSION_20260605 = "n3.action_confirmation_metric.board_lineage_repair.v2"
BOARD_LINEAGE_EXPECTED_ROWS_20260605 = {"stock": 0, "index": 0, "board": 28, "total": 28}
BOARD_LINEAGE_EXPECTED_CURRENT_COVERAGE_20260605 = 577
BOARD_LINEAGE_EXPECTED_FINAL_COVERAGE_20260605 = 605
BOARD_LINEAGE_SAMPLE_IDENTITIES_20260605 = [
    "board:TDX:880202",
    "board:TDX:880217",
    "board:TDX:880225",
    "board:TDX:880568",
    "board:TDX:880627",
]

DEFAULT_BOARD_LINEAGE_METRIC_V2_PAYLOAD_PATH_20260605 = "docs/N3_BOARD_LINEAGE_METRIC_V2_PAYLOAD.json"
DEFAULT_BOARD_LINEAGE_METRIC_V2_CONTRACT_PATH_20260605 = "docs/N3_BOARD_LINEAGE_METRIC_V2_CONTRACT.json"
DEFAULT_BOARD_LINEAGE_METRIC_V2_PREFLIGHT_PATH_20260605 = "docs/N3_BOARD_LINEAGE_METRIC_V2_PREFLIGHT.json"
DEFAULT_BOARD_LINEAGE_METRIC_V2_DRY_RUN_PATH_20260605 = "docs/N3_BOARD_LINEAGE_METRIC_V2_DRY_RUN.json"
DEFAULT_BOARD_LINEAGE_METRIC_V2_ROLLBACK_SQL_PATH_20260605 = "sql/N3_board_lineage_metric_v2_20260605_rollback.sql"

DEFAULT_COVERAGE_REPAIR_PAYLOAD_PATH_20260605 = (
    "docs/N3_action_confirmation_metric_coverage_policy_repair_payload.json"
)
DEFAULT_COVERAGE_REPAIR_CONTRACT_PATH_20260605 = (
    "docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_CONTRACT.json"
)
DEFAULT_COVERAGE_REPAIR_CONTRACT_MD_PATH_20260605 = (
    "docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_CONTRACT.md"
)
DEFAULT_COVERAGE_REPAIR_PREFLIGHT_PATH_20260605 = (
    "docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_PREFLIGHT.json"
)
DEFAULT_COVERAGE_REPAIR_PREFLIGHT_MD_PATH_20260605 = (
    "docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_PREFLIGHT.md"
)
DEFAULT_COVERAGE_REPAIR_DRY_RUN_PATH_20260605 = (
    "docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_DRY_RUN.json"
)
DEFAULT_COVERAGE_REPAIR_DRY_RUN_MD_PATH_20260605 = (
    "docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_DRY_RUN.md"
)
DEFAULT_COVERAGE_REPAIR_ROLLBACK_SQL_PATH_20260605 = (
    "sql/N3_action_confirmation_metric_coverage_policy_repair_20260605_rollback.sql"
)

EXECUTE_COMMAND_20260605 = (
    "PYTHONPATH=src:scripts python3 "
    "scripts/run_n3_action_confirmation_metric_materialization_execute.py "
    "--payload-path docs/N3_20260605_action_confirmation_metric_payload.json "
    "--contract-path docs/N3_20260605_ACTION_CONFIRMATION_METRIC_CONTRACT.json "
    "--execute --user-confirmed"
)

EXECUTE_COMMAND_REPAIRED_CONTEXT_20260605 = (
    "PYTHONPATH=src:scripts python3 "
    "scripts/run_n3_action_confirmation_metric_materialization_execute.py "
    "--payload-path docs/N3_20260605_repaired_context_action_confirmation_metric_payload.json "
    "--contract-path docs/N3_20260605_REPAIRED_CONTEXT_ACTION_CONFIRMATION_METRIC_CONTRACT.json "
    "--execute --user-confirmed"
)

EXECUTE_COMMAND_COVERAGE_REPAIR_20260605 = (
    "PYTHONPATH=src:scripts python3 "
    "scripts/run_n3_action_confirmation_metric_materialization_execute.py "
    "--payload-path docs/N3_action_confirmation_metric_coverage_policy_repair_payload.json "
    "--contract-path docs/N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_CONTRACT.json "
    "--execute --user-confirmed"
)

EXECUTE_COMMAND_BOARD_LINEAGE_METRIC_V2_20260605 = (
    "PYTHONPATH=src:scripts python3 "
    "scripts/run_n3_action_confirmation_metric_materialization_execute.py "
    "--payload-path docs/N3_BOARD_LINEAGE_METRIC_V2_PAYLOAD.json "
    "--contract-path docs/N3_BOARD_LINEAGE_METRIC_V2_CONTRACT.json "
    "--execute --user-confirmed"
)

PROJECTION_TABLES = {
    "stock": "stock_realtime_projection_metric",
    "index": "index_realtime_projection_metric",
    "board": "board_realtime_projection_metric",
}
PROJECTION_IDENTITY_COLUMNS = {
    "stock": "stock_identity_key",
    "index": "index_identity_key",
    "board": "board_identity_key",
}

ACTION_CONFIRMATION_METRIC_SCOPE = "action_confirmation_projection_metric"
QUALITY_LAYER_SCOPE = "market_data_run"


@dataclass(frozen=True)
class N4MatchEvent:
    trigger_match_id: int
    output_event_id: str | None
    event_id: str | None
    asset_kind: str
    identity_key: str
    direction: str | None
    signal_type: str | None
    condition_key: str | None
    trigger_mark_candidate: str | None
    trigger_period: str | None
    trigger_bucket: str | None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute N3 20260603 action-confirmation metric materialization.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--payload-path", default=DEFAULT_PAYLOAD_PATH)
    parser.add_argument("--contract-path", default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--report-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_REPORT_MD_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run(args)
    write_json(args.report_path, normalize_jsonable(report))
    write_text(args.markdown_report_path, format_execute_report_markdown(report))
    print(json.dumps(summary_for_stdout(report), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("result") == "EXECUTE_PASS" else 2


def run(
    args: argparse.Namespace,
    *,
    connect: Callable[..., Any] = audited_n3_market_execute_connect,
) -> dict[str, Any]:
    flag_gate = validate_execute_flags(execute=bool(args.execute), user_confirmed=bool(args.user_confirmed))
    if flag_gate["gate_result"] != "PASS":
        return blocked_report(args, flag_gate["blocked_reasons"], blocked_before_db=True)

    payload = read_json(args.payload_path)
    contract = read_json(args.contract_path)
    payload_validation = validate_payload(
        payload,
        target_run_id=contract_projection_run_id(contract),
        expected_row_counts=contract_expected_rows(contract),
        expected_metric_ready=contract_metric_ready_expected(contract),
        expected_n4_matched=contract_expected_n4_matched(contract),
    )
    if not payload_validation["valid"]:
        return blocked_report(
            args,
            payload_validation["blocked_reasons"],
            payload_validation=payload_validation,
            contract=contract,
            blocked_before_db=True,
        )
    contract_blockers = validate_contract(contract, payload_validation)
    if contract_blockers:
        return blocked_report(
            args,
            contract_blockers,
            payload_validation=payload_validation,
            contract=contract,
            blocked_before_db=True,
        )

    with connect(args.dsn, row_factory=dict_row) as conn:
        preflight = execute_preflight(conn, contract, payload_validation)
        if preflight["blocked"]:
            return blocked_report(
                args,
                preflight["blockers"],
                payload_validation=payload_validation,
                contract=contract,
                preflight=preflight,
                blocked_before_db=False,
            )
        quality_items = build_execute_quality_items(contract, payload_validation, preflight)
        quality_counts = count_quality_severities(quality_items)
        if quality_counts["P0"] > 0:
            return blocked_report(
                args,
                ["execute_quality_p0_present"],
                payload_validation=payload_validation,
                contract=contract,
                preflight=preflight,
                blocked_before_db=False,
            )

        rows_by_asset = rows_by_asset_kind(payload_rows(payload))
        with conn.transaction():
            insert_market_data_run(conn, contract, payload_validation, quality_counts)
            for asset_kind, rows in rows_by_asset.items():
                insert_action_confirmation_metric_rows(cur=conn.cursor(), table=MATERIALIZATION_TABLES[asset_kind], rows=rows)
            insert_quality_rows(conn, quality_items)

        postcheck = capture_baseline(conn, contract_projection_run_id(contract))

    return {
        "result": "EXECUTE_PASS",
        "layer_role": "N3_market_data",
        "projection_run_id": contract_projection_run_id(contract),
        "run_status": "passed",
        "actual_rows": payload_validation["row_counts"],
        "metric_ready": payload_validation["metric_ready"],
        "metric_not_ready": payload_validation["metric_not_ready"],
        "n4_matched_coverage": payload_validation["n4_matched_coverage"],
        "bj_excluded": payload_validation["bj_identity_rows"] == 0,
        "full_excluded": payload_validation["full_signal_type_rows"] == 0
        and payload_validation["full_condition_key_rows"] == 0,
        "quality": {
            "P0": quality_counts["P0"],
            "P1": quality_counts["P1"],
            "P2": quality_counts["P2"],
            "items": quality_items,
        },
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "outbox_inbox_checkpoint_refs": {
            "outbox": postcheck["common_event_outbox"],
            "inbox": postcheck["common_event_inbox"],
            "checkpoint": postcheck["common_event_consumer_checkpoint"],
        },
        "n4_n5_n6_refs": postcheck["downstream_refs"],
        "legacy_projection_tables_unchanged": True,
        "side_effects": side_effects(writes_database=True),
        "rollback": {
            "rollback_safe": postcheck["common_event_outbox"] == 0
            and postcheck["common_event_inbox"] == 0
            and postcheck["common_event_consumer_checkpoint"] == 0
            and postcheck["downstream_refs"]["total"] == 0,
            "rollback_sql_path": contract_rollback_sql_path(contract),
        },
        "report_artifacts": {
            "json_report_path": args.report_path,
            "markdown_report_path": args.markdown_report_path,
        },
        "generated_at": utc_now_iso(),
    }


def validate_execute_flags(*, execute: bool, user_confirmed: bool) -> dict[str, Any]:
    blocked: list[str] = []
    if not execute:
        blocked.append("missing_execute_flag")
    if not user_confirmed:
        blocked.append("missing_user_confirmed_flag")
    return {"gate_result": "PASS" if not blocked else "BLOCKED", "blocked_reasons": blocked}


def validate_payload(
    payload: Mapping[str, Any],
    *,
    target_run_id: str = TARGET_RUN_ID,
    expected_row_counts: Mapping[str, int] | None = None,
    expected_metric_ready: int | None = None,
    expected_n4_matched: int = EXPECTED_N4_MATCHED,
) -> dict[str, Any]:
    expected_counts = dict(expected_row_counts or EXPECTED_ROW_COUNTS)
    expected_ready = int(expected_metric_ready if expected_metric_ready is not None else expected_counts.get("total", EXPECTED_METRIC_READY))
    rows = payload_rows(payload)
    row_counts = count_rows(rows)
    metric_ready = sum(1 for row in rows if row.get("metric_ready") is True)
    metric_not_ready = len(rows) - metric_ready
    bj_identity_rows = sum(1 for row in rows if is_bj_identity(str(row.get("identity_key") or "")))
    full_signal_type_rows = 0
    full_condition_key_rows = 0
    db_check_failures = 0
    source_today_missing = 0
    source_previous_missing = 0
    for row in rows:
        events = row_n4_events(row)
        full_signal_type_rows += sum(1 for event in events if "FULL" in str(event.get("signal_type") or ""))
        full_condition_key_rows += sum(1 for event in events if "FULL" in str(event.get("condition_key") or ""))
        if not simulate_metric_ready_db_check(row)["passes"]:
            db_check_failures += 1
        if not row.get("source_today_minute_run_id"):
            source_today_missing += 1
        if not row.get("source_previous_day_minute_run_id"):
            source_previous_missing += 1
    coverage = dict(payload.get("n4_matched_coverage") or {})
    blocked: list[str] = []
    if payload.get("artifact_type") != "N3_action_confirmation_metric_materialization_payload":
        blocked.append("payload_artifact_type_mismatch")
    if (payload.get("projection_run_id") or payload.get("target_run_id")) != target_run_id:
        blocked.append("payload_projection_run_id_mismatch")
    if row_counts != expected_counts:
        blocked.append("row_count_mismatch")
    if metric_ready != expected_ready or metric_not_ready != 0:
        blocked.append("metric_ready_mismatch")
    if int(coverage.get("covered") or 0) != expected_n4_matched or int(coverage.get("missing") or 0) != 0:
        blocked.append("n4_trigger_matched_coverage_mismatch")
    if bj_identity_rows:
        blocked.append("bj_rows_must_be_excluded")
    if full_signal_type_rows or full_condition_key_rows:
        blocked.append("full_rows_must_be_excluded")
    if db_check_failures:
        blocked.append("metric_ready_db_check_simulation_failed")
    if source_today_missing or source_previous_missing:
        blocked.append("source_minute_run_ids_missing")
    return {
        "valid": not blocked,
        "blocked_reasons": blocked,
        "projection_run_id": payload.get("projection_run_id") or payload.get("target_run_id"),
        "expected_row_counts": expected_counts,
        "expected_metric_ready": expected_ready,
        "expected_n4_matched": expected_n4_matched,
        "row_counts": row_counts,
        "metric_ready": metric_ready,
        "metric_not_ready": metric_not_ready,
        "n4_matched_coverage": coverage,
        "bj_identity_rows": bj_identity_rows,
        "full_signal_type_rows": full_signal_type_rows,
        "full_condition_key_rows": full_condition_key_rows,
        "db_check_failures": db_check_failures,
        "source_today_missing": source_today_missing,
        "source_previous_missing": source_previous_missing,
    }


def validate_contract(contract: Mapping[str, Any], payload_validation: Mapping[str, Any]) -> list[str]:
    blocked: list[str] = []
    contract_run_id = str(contract.get("projection_run_id") or "")
    contract_expected_rows = dict(contract.get("expected_rows") or {})
    if contract_run_id != payload_validation.get("projection_run_id"):
        blocked.append("contract_projection_run_id_mismatch")
    if contract_expected_rows != dict(payload_validation.get("expected_row_counts") or {}):
        blocked.append("contract_expected_rows_mismatch")
    if list(contract.get("allowed_write_tables") or []) != ALLOWED_WRITE_TABLES:
        blocked.append("contract_allowed_write_tables_mismatch")
    if set(contract.get("requested_target_aliases") or []) != set(REQUESTED_TARGET_ALIASES):
        blocked.append("contract_requested_aliases_missing")
    forbidden = set(contract.get("forbidden_write_tables") or [])
    for table in FORBIDDEN_WRITE_TABLES:
        if table not in forbidden:
            blocked.append(f"contract_missing_forbidden_table:{table}")
    if contract.get("writes_outbox") is not False:
        blocked.append("contract_writes_outbox_not_false")
    if not (contract.get("rollback") or {}).get("rollback_sql_path"):
        blocked.append("contract_rollback_sql_path_mismatch")
    if payload_validation["row_counts"] != contract_expected_rows:
        blocked.append("payload_contract_row_counts_mismatch")
    return blocked


def contract_projection_run_id(contract: Mapping[str, Any]) -> str:
    return str(contract.get("projection_run_id") or TARGET_RUN_ID)


def contract_expected_rows(contract: Mapping[str, Any]) -> dict[str, int]:
    values = dict(contract.get("expected_rows") or EXPECTED_ROW_COUNTS)
    return {asset: int(values.get(asset, 0)) for asset in ("stock", "index", "board", "total")}


def contract_metric_ready_expected(contract: Mapping[str, Any]) -> int:
    return int(contract.get("metric_ready_expected") or contract_expected_rows(contract).get("total", EXPECTED_METRIC_READY))


def contract_expected_n4_matched(contract: Mapping[str, Any]) -> int:
    coverage = dict(contract.get("expected_n4_matched_coverage") or {})
    return int(coverage.get("covered") or coverage.get("expected") or EXPECTED_N4_MATCHED)


def contract_rollback_sql_path(contract: Mapping[str, Any]) -> str:
    return str((contract.get("rollback") or {}).get("rollback_sql_path") or DEFAULT_ROLLBACK_SQL_PATH)


def build_payload_from_db(dsn: str) -> dict[str, Any]:
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        n4_events = load_n4_matched_events(cur)
        selected_v4_rows = select_projection_enrichment_rows(cur, n4_events)
        rows_by_asset = build_action_metric_rows_from_v4(cur, selected_v4_rows, n4_events)
    rows = [row for asset in ASSET_KINDS for row in rows_by_asset.get(asset, [])]
    row_counts = count_rows(rows)
    coverage = {
        "covered": sum(len(events) for events in n4_events.values()),
        "expected": EXPECTED_N4_MATCHED,
        "missing": EXPECTED_N4_MATCHED - sum(len(events) for events in n4_events.values()),
        "distinct_metric_rows": len(rows),
    }
    payload = {
        "artifact_type": "N3_action_confirmation_metric_materialization_payload",
        "layer_role": "N3_market_data",
        "projection_run_id": TARGET_RUN_ID,
        "target_run_id": TARGET_RUN_ID,
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "for_trade_date": FOR_TRADE_DATE,
        "source_trade_date": SOURCE_TRADE_DATE,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID,
        "source_projection_enrichment_v4_run_id": PROJECTION_ENRICHMENT_V4_RUN_ID,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID,
        "expected_rows": row_counts,
        "metric_ready_expected": sum(1 for row in rows if row.get("metric_ready")),
        "n4_matched_coverage": coverage,
        "bj_full_scope_decision": {
            "bj_identity_rows": sum(1 for row in rows if is_bj_identity(str(row.get("identity_key") or ""))),
            "full_signal_type_rows": sum(
                1 for row in rows for event in row_n4_events(row) if "FULL" in str(event.get("signal_type") or "")
            ),
            "full_condition_key_rows": sum(
                1 for row in rows for event in row_n4_events(row) if "FULL" in str(event.get("condition_key") or "")
            ),
            "policy": "BJ and FULL are excluded from 20260603 N3 action-confirmation metric lineage",
        },
        "rows": normalize_jsonable(rows),
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }
    return normalize_jsonable(payload)


def build_20260605_payload_from_db(
    dsn: str,
    *,
    expected_n4_matched: int | None = EXPECTED_N4_MATCHED_20260605,
    projection_run_id: str = TARGET_RUN_ID_20260605,
    lineage_scope: str = "legacy_20260605",
) -> dict[str, Any]:
    """Build the 20260605 action-confirmation metric payload from reviewed N3/N4 inputs.

    20260605 deliberately materializes only N4 TriggerMatched identities whose
    B2 realtime projection row is ready-backed. Projection not-ready rows remain
    quality-visible as pending_market_data and are excluded from metric rows.
    """

    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        n4_events = load_n4_matched_events_for_run(cur, TRIGGER_EXECUTE_RUN_ID_20260605)
        projection_rows = load_realtime_projection_rows_for_events(
            cur,
            projection_run_id=SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
            n4_events=n4_events,
        )
        lineage_summary = summarize_20260605_lineage(n4_events, projection_rows)
        ready_groups = choose_20260605_ready_source_groups(cur, projection_rows)
        rows_by_asset = build_20260605_metric_rows(
            cur,
            ready_groups,
            n4_events,
            projection_rows,
            projection_run_id=projection_run_id,
        )

    rows = [row for asset in ASSET_KINDS for row in rows_by_asset.get(asset, [])]
    row_counts = count_rows(rows)
    coverage_expected = int(expected_n4_matched) if expected_n4_matched is not None else int(lineage_summary["candidate_total"])
    payload = {
        "artifact_type": "N3_action_confirmation_metric_materialization_payload",
        "layer_role": "N3_market_data",
        "projection_run_id": projection_run_id,
        "target_run_id": projection_run_id,
        "lineage_scope": lineage_scope,
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "for_trade_date": "20260605",
        "source_trade_date": "20260604",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID_20260605,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID_20260605,
        "source_today_minute_run_ids": [
            SOURCE_TODAY_MINUTE_RUN_ID_20260605,
            EXPANSION_TODAY_MINUTE_RUN_ID_20260605,
        ],
        "source_previous_day_minute_run_ids": [
            SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
            EXPANSION_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        ],
        "expected_rows": row_counts,
        "metric_ready_expected": sum(1 for row in rows if row.get("metric_ready")),
        "n4_matched_coverage": {
            "covered": lineage_summary["candidate_total"],
            "expected": coverage_expected,
            "missing": max(0, coverage_expected - int(lineage_summary["candidate_total"])),
            "distinct_metric_rows": len(rows),
            "ready_backed": lineage_summary["ready_total"],
            "pending_market_data": lineage_summary["not_ready_total"],
            "missing_projection": lineage_summary["missing_projection_total"],
        },
        "ready_backed_policy": {
            "policy": "materialize_metric",
            "materialize_metric_rows": True,
            "counts": lineage_summary["ready_by_asset"],
        },
        "not_ready_policy": {
            "policy": "pending_market_data",
            "materialize_metric_rows": False,
            "counts": lineage_summary["not_ready_by_asset"],
            "quality_visibility": "P1",
            "reason": "B2 projection rows with projection_status != ready are kept quality-visible and excluded from N3 action-confirmation metric materialization.",
        },
        "bj_full_scope_decision": {
            "bj_identity_rows": lineage_summary["bj_rows"],
            "full_signal_type_rows": lineage_summary["full_rows"],
            "full_condition_key_rows": lineage_summary["full_rows"],
            "policy": "BJ and FULL are excluded from 20260605 N3 action-confirmation metric lineage",
        },
        "rows": normalize_jsonable(rows),
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }
    return normalize_jsonable(payload)


def build_20260605_coverage_repair_payload_from_db(dsn: str) -> dict[str, Any]:
    """Build the additive 20260605 coverage-repair payload without DB writes."""

    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        n4_events = load_n4_matched_events_for_run(cur, TRIGGER_EXECUTE_RUN_ID_20260605)
        projection_rows = load_realtime_projection_rows_for_events(
            cur,
            projection_run_id=SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
            n4_events=n4_events,
        )
        source_groups = choose_20260605_metric_trace_source_groups(cur, projection_rows)
        candidate_rows_by_asset = build_20260605_metric_rows(
            cur,
            source_groups,
            n4_events,
            projection_rows,
            projection_run_id=COVERAGE_REPAIR_RUN_ID_20260605,
        )
        original_by_asset = load_existing_metric_identities(
            cur,
            projection_run_id=COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        )

    original_identities = flatten_identity_sets(original_by_asset)
    candidate_rows_by_identity = {
        str(row.get("identity_key")): row
        for rows in candidate_rows_by_asset.values()
        for row in rows
    }
    repair_rows_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    excluded_by_reason: dict[str, dict[str, list[str]]] = defaultdict(lambda: {asset: [] for asset in ASSET_KINDS})
    decisions: dict[str, dict[str, Any]] = {}

    for identity, events in sorted(n4_events.items()):
        asset_kind = events[0].asset_kind if events else str(identity).split(":", 1)[0]
        projection_row = projection_rows.get(identity)
        metric_row = candidate_rows_by_identity.get(identity)
        decision = classify_20260605_metric_trace_eligibility(
            metric_row=metric_row,
            projection_row=projection_row,
            original_metric_identities=original_identities,
        )
        decisions[identity] = decision
        if decision["eligible"] and metric_row:
            row = apply_coverage_repair_trace(row=metric_row, projection_row=projection_row, decision=decision)
            repair_rows_by_asset[asset_kind].append(row)
        else:
            reason = str(decision.get("excluded_reason") or "unknown")
            excluded_by_reason[reason][asset_kind].append(identity)

    for rows in repair_rows_by_asset.values():
        rows.sort(key=lambda row: str(row.get("identity_key") or ""))
    repair_rows = [row for asset in ASSET_KINDS for row in repair_rows_by_asset.get(asset, [])]
    repair_counts = count_rows(repair_rows)
    original_counts = {asset: len(original_by_asset.get(asset, set())) for asset in ASSET_KINDS}
    original_counts["total"] = sum(original_counts.values())
    repaired_total = {
        asset: original_counts.get(asset, 0) + repair_counts.get(asset, 0)
        for asset in ASSET_KINDS
    }
    repaired_total["total"] = sum(repaired_total.values())
    lineage_missing = {
        asset: len(excluded_by_reason.get("lineage_missing", {}).get(asset, []))
        for asset in ASSET_KINDS
    }
    lineage_missing["total"] = sum(lineage_missing.values())
    duplicate_vs_original = sum(1 for row in repair_rows if str(row.get("identity_key")) in original_identities)
    duplicate_inside = len(repair_rows) - len({str(row.get("identity_key")) for row in repair_rows})
    sample_stock = build_coverage_repair_sample_proof(
        identity="stock:SH:688690",
        decision=decisions.get("stock:SH:688690") or {},
        projection_row=projection_rows.get("stock:SH:688690") or {},
        metric_row=candidate_rows_by_identity.get("stock:SH:688690"),
    )
    board_additive = [str(row.get("identity_key")) for row in repair_rows_by_asset.get("board", [])]
    board_lineage_missing = sorted(excluded_by_reason.get("lineage_missing", {}).get("board", []))
    payload = {
        "artifact_type": "N3_action_confirmation_metric_materialization_payload",
        "artifact_subtype": "coverage_policy_repair_v1",
        "layer_role": "N3_market_data",
        "projection_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
        "target_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
        "lineage_scope": "coverage_policy_repair_v1",
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "coverage_policy_version": COVERAGE_POLICY_VERSION_20260605,
        "for_trade_date": "20260605",
        "source_trade_date": "20260604",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID_20260605,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID_20260605,
        "source_today_minute_run_ids": [
            SOURCE_TODAY_MINUTE_RUN_ID_20260605,
            EXPANSION_TODAY_MINUTE_RUN_ID_20260605,
        ],
        "source_previous_day_minute_run_ids": [
            SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
            EXPANSION_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        ],
        "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        "expected_rows": repair_counts,
        "metric_ready_expected": sum(1 for row in repair_rows if row.get("metric_ready")),
        "n4_matched_coverage": {
            "covered": sum(len(events) for events in n4_events.values()),
            "expected": sum(len(events) for events in n4_events.values()),
            "missing": 0,
            "distinct_metric_rows": repair_counts["total"],
            "original_metric_rows": original_counts["total"],
            "repair_additive_rows": repair_counts["total"],
            "repaired_total_coverage": repaired_total["total"],
            "remaining_excluded": lineage_missing["total"],
        },
        "coverage_policy": {
            "policy": "metric_trace_complete_plus_db_check",
            "eligibility_source": "metric_trace_complete",
            "coverage_policy_version": COVERAGE_POLICY_VERSION_20260605,
            "original_projection_status_preserved": True,
            "original_projection_quality_status_preserved": True,
            "original_projection_trace_status_preserved": True,
            "original_metric_run_preserved": True,
            "additive_repair_only": True,
        },
        "repair_summary": {
            "original_metric_rows": original_counts["total"],
            "n4_matched_universe": sum(len(events) for events in n4_events.values()),
            "repair_additive_rows": repair_counts,
            "stock_additive": repair_counts["stock"],
            "index_additive": repair_counts["index"],
            "board_additive": repair_counts["board"],
            "repaired_total_coverage": repaired_total,
            "remaining_excluded": lineage_missing,
            "remaining_excluded_reason": "board_lineage_missing",
            "duplicate_vs_original_metric": duplicate_vs_original,
            "duplicate_inside_repair_payload": duplicate_inside,
            "excluded_by_reason": {
                reason: {
                    asset: len(values)
                    for asset, values in by_asset.items()
                }
                for reason, by_asset in excluded_by_reason.items()
            },
        },
        "ready_backed_policy": {
            "policy": "preserve_original_metric_rows",
            "materialize_metric_rows": False,
            "counts": original_counts,
            "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        },
        "not_ready_policy": {
            "policy": "materialize_when_metric_trace_complete",
            "materialize_metric_rows": True,
            "counts": repair_counts,
            "quality_visibility": "trace_preserved",
        },
        "remaining_excluded_policy": {
            "policy": "excluded_lineage_missing",
            "counts": lineage_missing,
            "quality_visibility": "P1",
            "reason": "board identities without today/previous-day minute lineage remain excluded; no silent fallback.",
        },
        "sample_proof": {
            "stock_SH_688690": sample_stock,
            "board_additive_samples": board_additive[:5],
            "board_excluded_lineage_missing_samples": board_lineage_missing[:12],
        },
        "bj_full_scope_decision": {
            "bj_identity_rows": 0,
            "full_signal_type_rows": 0,
            "full_condition_key_rows": 0,
            "policy": "BJ and FULL remain excluded from 20260605 N3 action-confirmation metric lineage",
        },
        "rows": normalize_jsonable(repair_rows),
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }
    return normalize_jsonable(payload)


def build_20260605_board_lineage_metric_v2_payload_from_db(dsn: str) -> dict[str, Any]:
    """Build the additive board-lineage metric_v2 payload after scoped A1/C1 minute rows exist."""

    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        n4_events = load_n4_matched_events_for_run(cur, TRIGGER_EXECUTE_RUN_ID_20260605)
        projection_rows = load_realtime_projection_rows_for_events(
            cur,
            projection_run_id=SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
            n4_events=n4_events,
        )
        original_by_asset = load_existing_metric_identities(
            cur,
            projection_run_id=COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        )
        additive_v1_by_asset = load_existing_metric_identities(
            cur,
            projection_run_id=COVERAGE_REPAIR_RUN_ID_20260605,
        )
        existing_identities = flatten_identity_sets(original_by_asset)
        additive_v1_identities = flatten_identity_sets(additive_v1_by_asset)
        existing_plus_additive_v1 = set(existing_identities)
        existing_plus_additive_v1.update(additive_v1_identities)
        board_today = load_identity_set_for_minute_run(
            cur,
            asset_kind="board",
            run_id=BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605,
        )
        board_previous = load_identity_set_for_minute_run(
            cur,
            asset_kind="board",
            run_id=BOARD_LINEAGE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        )
        board_lineage_identities = sorted(board_today & board_previous)
        candidate_identities = [
            identity
            for identity in board_lineage_identities
            if identity in n4_events and identity not in existing_plus_additive_v1
        ]
        source_groups = {
            "board_lineage": {"stock": [], "index": [], "board": candidate_identities},
        }
        candidate_rows_by_asset = build_20260605_metric_rows(
            cur,
            source_groups,
            n4_events,
            projection_rows,
            projection_run_id=BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
            group_config_override={
                "board_lineage": (
                    BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605,
                    BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605,
                    BOARD_LINEAGE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
                ),
            },
        )

    metric_rows_by_identity = {
        str(row.get("identity_key")): row
        for rows in candidate_rows_by_asset.values()
        for row in rows
    }
    repair_rows_by_asset: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    excluded_by_reason: dict[str, dict[str, list[str]]] = defaultdict(lambda: {asset: [] for asset in ASSET_KINDS})
    decisions: dict[str, dict[str, Any]] = {}

    for identity in sorted(identity for identity in n4_events if str(identity).startswith("board:")):
        if identity in existing_plus_additive_v1:
            continue
        projection_row = projection_rows.get(identity)
        metric_row = metric_rows_by_identity.get(identity)
        decision = classify_20260605_metric_trace_eligibility(
            metric_row=metric_row,
            projection_row=projection_row,
            original_metric_identities=existing_plus_additive_v1,
        )
        decisions[identity] = decision
        if decision["eligible"] and metric_row:
            row = apply_board_lineage_metric_v2_trace(
                row=metric_row,
                projection_row=projection_row,
                decision=decision,
            )
            repair_rows_by_asset["board"].append(row)
        else:
            reason = str(decision.get("excluded_reason") or "unknown")
            excluded_by_reason[reason]["board"].append(identity)

    for rows in repair_rows_by_asset.values():
        rows.sort(key=lambda row: str(row.get("identity_key") or ""))
    repair_rows = [row for asset in ASSET_KINDS for row in repair_rows_by_asset.get(asset, [])]
    repair_counts = count_rows(repair_rows)
    original_counts = {asset: len(original_by_asset.get(asset, set())) for asset in ASSET_KINDS}
    original_counts["total"] = sum(original_counts.values())
    additive_v1_counts = {asset: len(additive_v1_by_asset.get(asset, set())) for asset in ASSET_KINDS}
    additive_v1_counts["total"] = sum(additive_v1_counts.values())
    existing_coverage = len(existing_plus_additive_v1)
    expected_coverage = len(n4_events)
    duplicate_vs_original = sum(1 for row in repair_rows if str(row.get("identity_key")) in existing_identities)
    duplicate_vs_additive_v1 = sum(1 for row in repair_rows if str(row.get("identity_key")) in additive_v1_identities)
    duplicate_inside = len(repair_rows) - len({str(row.get("identity_key")) for row in repair_rows})
    final_coverage = existing_coverage + repair_counts["total"]
    remaining_excluded_total = max(0, expected_coverage - final_coverage)
    sample_proof = build_board_lineage_metric_v2_sample_proof(
        sample_identities=BOARD_LINEAGE_SAMPLE_IDENTITIES_20260605,
        rows_by_identity={str(row.get("identity_key")): row for row in repair_rows},
        decisions=decisions,
        projection_rows=projection_rows,
    )

    payload = {
        "artifact_type": "N3_action_confirmation_metric_materialization_payload",
        "artifact_subtype": "board_lineage_metric_v2",
        "layer_role": "N3_market_data",
        "projection_run_id": BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
        "target_run_id": BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
        "lineage_scope": "board_lineage_metric_v2",
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "coverage_policy_version": BOARD_LINEAGE_POLICY_VERSION_20260605,
        "for_trade_date": "20260605",
        "source_trade_date": "20260604",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID_20260605,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID_20260605,
        "source_subscription_run_ids": [BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605],
        "source_today_minute_run_ids": [BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605],
        "source_previous_day_minute_run_ids": [BOARD_LINEAGE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605],
        "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        "additive_v1_metric_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
        "expected_rows": repair_counts,
        "metric_ready_expected": sum(1 for row in repair_rows if row.get("metric_ready")),
        "n4_matched_coverage": {
            "covered": expected_coverage,
            "expected": expected_coverage,
            "missing": 0,
            "distinct_metric_rows": repair_counts["total"],
            "existing_coverage": existing_coverage,
            "board_lineage_metric_v2_additive": repair_counts["total"],
            "expected_final_coverage": expected_coverage,
            "final_coverage_after_metric_v2": final_coverage,
            "remaining_excluded": remaining_excluded_total,
        },
        "coverage_policy": {
            "policy": "board_lineage_metric_trace_complete_plus_db_check",
            "eligibility_source": "metric_trace_complete",
            "coverage_policy_version": BOARD_LINEAGE_POLICY_VERSION_20260605,
            "original_projection_status_preserved": True,
            "original_projection_quality_status_preserved": True,
            "original_projection_trace_status_preserved": True,
            "additive_repair_only": True,
            "does_not_overwrite_original_metric_run": True,
            "does_not_overwrite_additive_v1_metric_run": True,
        },
        "repair_summary": {
            "existing_coverage": existing_coverage,
            "original_metric_rows": original_counts,
            "additive_v1_metric_rows": additive_v1_counts,
            "board_metric_v2_additive": repair_counts,
            "expected_coverage": expected_coverage,
            "final_coverage_after_metric_v2": final_coverage,
            "remaining_excluded": {"stock": 0, "index": 0, "board": remaining_excluded_total, "total": remaining_excluded_total},
            "remaining_excluded_reason": None if remaining_excluded_total == 0 else "lineage_missing",
            "duplicate_vs_original_metric": duplicate_vs_original,
            "duplicate_vs_additive_v1": duplicate_vs_additive_v1,
            "duplicate_inside_metric_v2_payload": duplicate_inside,
            "excluded_by_reason": {
                reason: {
                    asset: len(values)
                    for asset, values in by_asset.items()
                }
                for reason, by_asset in excluded_by_reason.items()
            },
        },
        "ready_backed_policy": {
            "policy": "preserve_original_and_additive_v1_metric_rows",
            "materialize_metric_rows": False,
            "counts": {"original": original_counts, "additive_v1": additive_v1_counts},
        },
        "not_ready_policy": {
            "policy": "materialize_when_board_lineage_metric_trace_complete",
            "materialize_metric_rows": True,
            "counts": repair_counts,
            "quality_visibility": "trace_preserved",
        },
        "remaining_excluded_policy": {
            "policy": "none_remaining_after_board_lineage_metric_v2" if remaining_excluded_total == 0 else "excluded_lineage_missing",
            "counts": {"stock": 0, "index": 0, "board": remaining_excluded_total, "total": remaining_excluded_total},
            "quality_visibility": "P1_when_nonzero",
        },
        "sample_proof": sample_proof,
        "bj_full_scope_decision": {
            "bj_identity_rows": 0,
            "full_signal_type_rows": 0,
            "full_condition_key_rows": 0,
            "policy": "BJ and FULL remain excluded from 20260605 N3 action-confirmation metric lineage",
        },
        "rows": normalize_jsonable(repair_rows),
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }
    return normalize_jsonable(payload)


def apply_board_lineage_metric_v2_trace(
    *,
    row: Mapping[str, Any],
    projection_row: Mapping[str, Any] | None,
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    repaired = dict(row)
    raw = dict(repaired.get("raw_json") or {})
    raw.update(
        {
            "board_lineage_metric_v2": True,
            "coverage_policy_version": BOARD_LINEAGE_POLICY_VERSION_20260605,
            "eligibility_source": "metric_trace_complete",
            "metric_trace_complete": decision.get("metric_trace_complete"),
            "db_check_pass": decision.get("db_check_pass"),
            "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
            "additive_v1_metric_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
            "original_projection_status": decision.get("original_projection_status"),
            "original_projection_quality_status": decision.get("original_projection_quality_status"),
            "original_projection_trace_status": decision.get("original_projection_trace_status"),
            "original_projection_missing_reasons": decision.get("original_projection_missing_reasons"),
            "source_realtime_projection": {
                **dict(raw.get("source_realtime_projection") or {}),
                "projection_id": (projection_row or {}).get("projection_id"),
                "projection_run_id": (projection_row or {}).get("projection_run_id"),
                "projection_status": (projection_row or {}).get("projection_status"),
                "projection_quality_status": (projection_row or {}).get("projection_quality_status"),
                "trace_status": (projection_row or {}).get("trace_status"),
            },
            "ready_backed_policy": "original_and_additive_v1_metric_rows_preserved",
            "not_ready_policy": "materialize_when_board_lineage_metric_trace_complete",
            "remaining_excluded_policy": "none_after_board_lineage_metric_v2",
        }
    )
    source_fact_ids = dict(repaired.get("source_fact_ids") or {})
    source_fact_ids.update(
        {
            "coverage_policy_version": BOARD_LINEAGE_POLICY_VERSION_20260605,
            "eligibility_source": "metric_trace_complete",
            "source_realtime_projection_id": (projection_row or {}).get("projection_id"),
            "source_realtime_projection_run_id": (projection_row or {}).get("projection_run_id"),
            "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
            "additive_v1_metric_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
        }
    )
    repaired["raw_json"] = raw
    repaired["source_fact_ids"] = source_fact_ids
    repaired["calculation_config_hash"] = BOARD_LINEAGE_POLICY_VERSION_20260605
    return normalize_jsonable(repaired)


def build_board_lineage_metric_v2_sample_proof(
    *,
    sample_identities: Sequence[str],
    rows_by_identity: Mapping[str, Mapping[str, Any]],
    decisions: Mapping[str, Mapping[str, Any]],
    projection_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    proof: dict[str, Any] = {}
    for identity in sample_identities:
        row = rows_by_identity.get(identity)
        decision = decisions.get(identity) or {}
        projection_row = projection_rows.get(identity) or {}
        proof[identity] = {
            "identity_key": identity,
            "materialized_in_metric_v2": row is not None,
            "metric_ready": (row or {}).get("metric_ready"),
            "metric_trace_complete": decision.get("metric_trace_complete"),
            "db_check_pass": decision.get("db_check_pass"),
            "original_projection_status": decision.get("original_projection_status") or projection_row.get("projection_status"),
            "original_projection_quality_status": decision.get("original_projection_quality_status") or projection_row.get("projection_quality_status"),
            "original_projection_trace_status": decision.get("original_projection_trace_status") or projection_row.get("trace_status"),
            "source_today_minute_run_id": (row or {}).get("source_today_minute_run_id"),
            "source_previous_day_minute_run_id": (row or {}).get("source_previous_day_minute_run_id"),
            "source_minute_refs_count": len((row or {}).get("source_minute_refs") or []),
            "previous_day_minute_refs_count": len((row or {}).get("previous_day_minute_refs") or []),
        }
    return proof


def apply_coverage_repair_trace(
    *,
    row: Mapping[str, Any],
    projection_row: Mapping[str, Any] | None,
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    repaired = dict(row)
    raw = dict(repaired.get("raw_json") or {})
    raw.update(
        {
            "coverage_policy_repair": True,
            "coverage_policy_version": COVERAGE_POLICY_VERSION_20260605,
            "eligibility_source": "metric_trace_complete",
            "metric_trace_complete": decision.get("metric_trace_complete"),
            "db_check_pass": decision.get("db_check_pass"),
            "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
            "original_projection_status": decision.get("original_projection_status"),
            "original_projection_quality_status": decision.get("original_projection_quality_status"),
            "original_projection_trace_status": decision.get("original_projection_trace_status"),
            "original_projection_missing_reasons": decision.get("original_projection_missing_reasons"),
            "source_realtime_projection": {
                **dict(raw.get("source_realtime_projection") or {}),
                "projection_id": (projection_row or {}).get("projection_id"),
                "projection_run_id": (projection_row or {}).get("projection_run_id"),
                "projection_status": (projection_row or {}).get("projection_status"),
                "projection_quality_status": (projection_row or {}).get("projection_quality_status"),
                "trace_status": (projection_row or {}).get("trace_status"),
            },
            "ready_backed_policy": "original_metric_rows_preserved",
            "not_ready_policy": "materialize_when_metric_trace_complete",
            "remaining_excluded_policy": "lineage_missing_stays_quality_visible",
        }
    )
    source_fact_ids = dict(repaired.get("source_fact_ids") or {})
    source_fact_ids.update(
        {
            "coverage_policy_version": COVERAGE_POLICY_VERSION_20260605,
            "eligibility_source": "metric_trace_complete",
            "source_realtime_projection_id": (projection_row or {}).get("projection_id"),
            "source_realtime_projection_run_id": (projection_row or {}).get("projection_run_id"),
            "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        }
    )
    repaired["raw_json"] = raw
    repaired["source_fact_ids"] = source_fact_ids
    repaired["calculation_config_hash"] = COVERAGE_POLICY_VERSION_20260605
    return normalize_jsonable(repaired)


def build_coverage_repair_sample_proof(
    *,
    identity: str,
    decision: Mapping[str, Any],
    projection_row: Mapping[str, Any],
    metric_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "identity_key": identity,
        "original_projection_status": decision.get("original_projection_status") or projection_row.get("projection_status"),
        "original_projection_quality_status": decision.get("original_projection_quality_status") or projection_row.get("projection_quality_status"),
        "original_projection_trace_status": decision.get("original_projection_trace_status") or projection_row.get("trace_status"),
        "reason": decision.get("original_projection_missing_reasons") or projection_missing_reasons(projection_row),
        "metric_trace_complete": decision.get("metric_trace_complete"),
        "db_check_pass": decision.get("db_check_pass"),
        "would_materialize_in_repair": decision.get("eligible"),
        "source_minute_refs_count": len((metric_row or {}).get("source_minute_refs") or []),
        "previous_day_minute_refs_count": len((metric_row or {}).get("previous_day_minute_refs") or []),
    }


def load_n4_matched_events_for_run(cur: Any, trigger_execute_run_id: str) -> dict[str, list[N4MatchEvent]]:
    cur.execute(
        """
        SELECT
          m.trigger_match_id,
          m.output_event_id,
          o.event_id,
          m.asset_kind,
          m.identity_key,
          m.direction,
          m.signal_type,
          m.condition_key,
          m.trigger_mark_candidate,
          m.trigger_period,
          m.trigger_bucket
        FROM common_trigger_match m
        LEFT JOIN common_event_outbox o
          ON o.source_run_id = m.run_id
         AND o.event_type = 'TriggerMatched'
         AND o.event_id = m.output_event_id
        WHERE m.run_id = %s
          AND m.output_event_type = 'TriggerMatched'
          AND m.identity_key NOT LIKE '%%:BJ:%%'
          AND COALESCE(m.signal_type, '') NOT LIKE '%%FULL%%'
          AND COALESCE(m.condition_key, '') NOT LIKE '%%FULL%%'
        ORDER BY m.asset_kind, m.identity_key, m.trigger_match_id
        """,
        (trigger_execute_run_id,),
    )
    grouped: dict[str, list[N4MatchEvent]] = defaultdict(list)
    for row in cur.fetchall():
        grouped[str(row["identity_key"])].append(
            N4MatchEvent(
                trigger_match_id=int(row["trigger_match_id"]),
                output_event_id=row.get("output_event_id"),
                event_id=row.get("event_id"),
                asset_kind=str(row["asset_kind"]),
                identity_key=str(row["identity_key"]),
                direction=row.get("direction"),
                signal_type=row.get("signal_type"),
                condition_key=row.get("condition_key"),
                trigger_mark_candidate=row.get("trigger_mark_candidate"),
                trigger_period=row.get("trigger_period"),
                trigger_bucket=row.get("trigger_bucket"),
            )
        )
    return dict(grouped)


def load_realtime_projection_rows_for_events(
    cur: Any,
    *,
    projection_run_id: str,
    n4_events: Mapping[str, Sequence[N4MatchEvent]],
) -> dict[str, dict[str, Any]]:
    rows_by_identity: dict[str, dict[str, Any]] = {}
    for asset_kind in ASSET_KINDS:
        identities = [identity for identity, events in n4_events.items() if events and events[0].asset_kind == asset_kind]
        if not identities:
            continue
        table = PROJECTION_TABLES[asset_kind]
        identity_col = PROJECTION_IDENTITY_COLUMNS[asset_kind]
        cur.execute(
            f"""
            SELECT *, {identity_col} AS identity_key
            FROM {table}
            WHERE projection_run_id = %s
              AND {identity_col} = ANY(%s)
            ORDER BY {identity_col}, projection_id DESC
            """,
            (projection_run_id, identities),
        )
        for row in cur.fetchall():
            identity = str(row["identity_key"])
            rows_by_identity.setdefault(identity, normalize_jsonable(dict(row)))
    return rows_by_identity


def summarize_20260605_lineage(
    n4_events: Mapping[str, Sequence[N4MatchEvent]],
    projection_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    ready_by_asset = {"stock": 0, "index": 0, "board": 0, "total": 0}
    not_ready_by_asset = {"stock": 0, "index": 0, "board": 0, "total": 0}
    missing_by_asset = {"stock": 0, "index": 0, "board": 0, "total": 0}
    bj_rows = 0
    full_rows = 0
    for identity, events in n4_events.items():
        if not events:
            continue
        event = events[0]
        asset_kind = event.asset_kind
        if is_bj_identity(identity):
            bj_rows += len(events)
            continue
        if any("FULL" in str(value or "") for e in events for value in (e.signal_type, e.condition_key)):
            full_rows += len(events)
            continue
        projection_row = projection_rows.get(identity)
        if not projection_row:
            missing_by_asset[asset_kind] += 1
            missing_by_asset["total"] += 1
        elif projection_row.get("projection_status") == "ready":
            ready_by_asset[asset_kind] += 1
            ready_by_asset["total"] += 1
        else:
            not_ready_by_asset[asset_kind] += 1
            not_ready_by_asset["total"] += 1
    return {
        "candidate_by_asset": {
            asset: ready_by_asset[asset] + not_ready_by_asset[asset] + missing_by_asset[asset]
            for asset in ("stock", "index", "board")
        },
        "candidate_total": ready_by_asset["total"] + not_ready_by_asset["total"] + missing_by_asset["total"],
        "ready_by_asset": ready_by_asset,
        "ready_total": ready_by_asset["total"],
        "not_ready_by_asset": not_ready_by_asset,
        "not_ready_total": not_ready_by_asset["total"],
        "missing_projection_by_asset": missing_by_asset,
        "missing_projection_total": missing_by_asset["total"],
        "bj_rows": bj_rows,
        "full_rows": full_rows,
    }


def choose_20260605_ready_source_groups(
    cur: Any,
    projection_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    groups = {
        "expansion": {"stock": [], "index": [], "board": []},
        "original": {"stock": [], "index": [], "board": []},
    }
    for asset_kind in ASSET_KINDS:
        ready_identities = sorted(
            identity
            for identity, row in projection_rows.items()
            if str(identity).startswith(f"{asset_kind}:") and row.get("projection_status") == "ready"
        )
        if not ready_identities:
            continue
        expansion_today = load_identity_set_for_minute_run(
            cur,
            asset_kind=asset_kind,
            run_id=EXPANSION_TODAY_MINUTE_RUN_ID_20260605,
        )
        expansion_previous = load_identity_set_for_minute_run(
            cur,
            asset_kind=asset_kind,
            run_id=EXPANSION_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        )
        for identity in ready_identities:
            if identity in expansion_today and identity in expansion_previous:
                groups["expansion"][asset_kind].append(identity)
            else:
                groups["original"][asset_kind].append(identity)
    return groups


def choose_20260605_metric_trace_source_groups(
    cur: Any,
    projection_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    """Group all projection-joined identities by the minute lineage they actually have.

    This is the forward coverage policy used by the additive repair path. It does
    not require the B2 realtime projection row to be ``ready``; the final
    eligibility gate is metric trace completeness plus the 032 DB CHECK
    simulation after metric-row construction.
    """

    groups = {
        "expansion": {"stock": [], "index": [], "board": []},
        "original": {"stock": [], "index": [], "board": []},
    }
    for asset_kind in ASSET_KINDS:
        identities = sorted(
            identity
            for identity in projection_rows
            if str(identity).startswith(f"{asset_kind}:")
        )
        if not identities:
            continue
        expansion_today = load_identity_set_for_minute_run(
            cur,
            asset_kind=asset_kind,
            run_id=EXPANSION_TODAY_MINUTE_RUN_ID_20260605,
        )
        expansion_previous = load_identity_set_for_minute_run(
            cur,
            asset_kind=asset_kind,
            run_id=EXPANSION_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        )
        original_today = load_identity_set_for_minute_run(
            cur,
            asset_kind=asset_kind,
            run_id=SOURCE_TODAY_MINUTE_RUN_ID_20260605,
        )
        original_previous = load_identity_set_for_minute_run(
            cur,
            asset_kind=asset_kind,
            run_id=SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        )
        for identity in identities:
            if identity in expansion_today and identity in expansion_previous:
                groups["expansion"][asset_kind].append(identity)
            elif identity in original_today and identity in original_previous:
                groups["original"][asset_kind].append(identity)
            elif identity in expansion_today or identity in expansion_previous:
                groups["expansion"][asset_kind].append(identity)
            else:
                groups["original"][asset_kind].append(identity)
    return groups


def load_identity_set_for_minute_run(cur: Any, *, asset_kind: str, run_id: str) -> set[str]:
    table = MINUTE_TABLES[asset_kind]
    identity = IDENTITY_COLUMNS[asset_kind]
    cur.execute(f"SELECT DISTINCT {identity} AS identity_key FROM {table} WHERE run_id = %s", (run_id,))
    return {str(row["identity_key"]) for row in cur.fetchall()}


def load_existing_metric_identities(
    cur: Any,
    *,
    projection_run_id: str,
) -> dict[str, set[str]]:
    existing = {asset: set() for asset in ASSET_KINDS}
    for asset_kind, table in MATERIALIZATION_TABLES.items():
        cur.execute(
            f"""
            SELECT identity_key
            FROM {table}
            WHERE projection_run_id = %s
            """,
            (projection_run_id,),
        )
        existing[asset_kind] = {str(row["identity_key"]) for row in cur.fetchall()}
    return existing


def flatten_identity_sets(identity_sets: Mapping[str, set[str]]) -> set[str]:
    flattened: set[str] = set()
    for values in identity_sets.values():
        flattened.update(values)
    return flattened


def projection_missing_reasons(projection_row: Mapping[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    if not projection_row:
        return ["missing_projection"]
    for obj in (projection_row.get("source_fact_ids"), projection_row.get("raw_json")):
        if not isinstance(obj, Mapping):
            continue
        for key in ("missing_reason", "not_ready_reason", "blocked_reason"):
            value = obj.get(key)
            if isinstance(value, list):
                reasons.extend(str(item) for item in value if item)
            elif value:
                reasons.append(str(value))
    return sorted(set(reasons))


def reasons_indicate_lineage_missing(reasons: Sequence[str]) -> bool:
    tokens = (
        "missing_today_minute",
        "missing_current_lineage",
        "previous_day",
        "lineage_missing",
    )
    return any(any(token in reason for token in tokens) for reason in reasons)


def metric_trace_complete(row: Mapping[str, Any] | None) -> bool:
    if not row:
        return False
    return (
        bool(row.get("source_today_minute_run_id"))
        and bool(row.get("source_previous_day_minute_run_id"))
        and isinstance(row.get("source_fact_ids"), Mapping)
        and bool(row.get("source_fact_ids"))
        and isinstance(row.get("source_minute_refs"), list)
        and bool(row.get("source_minute_refs"))
        and row.get("metric_ready") is True
    )


def classify_20260605_metric_trace_eligibility(
    *,
    metric_row: Mapping[str, Any] | None,
    projection_row: Mapping[str, Any] | None,
    original_metric_identities: set[str],
) -> dict[str, Any]:
    identity = str((metric_row or {}).get("identity_key") or (projection_row or {}).get("identity_key") or "")
    reasons = projection_missing_reasons(projection_row)
    db_check = simulate_metric_ready_db_check(metric_row) if metric_row else {"passes": False, "failures": ["metric_row_missing"]}
    trace_complete = metric_trace_complete(metric_row)
    already_materialized = bool(identity and identity in original_metric_identities)
    if already_materialized:
        excluded_reason = "already_materialized_original_metric"
    elif not metric_row:
        excluded_reason = "lineage_missing" if reasons_indicate_lineage_missing(reasons) else "metric_row_not_buildable"
    elif not trace_complete:
        excluded_reason = "metric_trace_incomplete"
    elif not db_check["passes"]:
        excluded_reason = "db_check_failed"
    else:
        excluded_reason = None
    return {
        "identity_key": identity,
        "eligible": excluded_reason is None,
        "eligibility_source": "metric_trace_complete",
        "coverage_policy_version": COVERAGE_POLICY_VERSION_20260605,
        "metric_trace_complete": trace_complete,
        "db_check_pass": bool(db_check["passes"]),
        "db_check_failures": list(db_check.get("failures") or []),
        "original_projection_status": (projection_row or {}).get("projection_status"),
        "original_projection_quality_status": (projection_row or {}).get("projection_quality_status"),
        "original_projection_trace_status": (projection_row or {}).get("trace_status"),
        "original_projection_missing_reasons": reasons,
        "excluded_reason": excluded_reason,
    }


def build_20260605_metric_rows(
    cur: Any,
    ready_groups: Mapping[str, Mapping[str, list[str]]],
    n4_events: Mapping[str, Sequence[N4MatchEvent]],
    projection_rows: Mapping[str, Mapping[str, Any]],
    *,
    projection_run_id: str = TARGET_RUN_ID_20260605,
    group_config_override: Mapping[str, tuple[str, str, str]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    snapshot_rows_by_asset = load_snapshot_rows_for_metric_dry_run(
        cur,
        source_snapshot_run_id=SOURCE_SNAPSHOT_RUN_ID_20260605,
    )
    output: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    group_config = {
        "expansion": (
            EXPANSION_SUBSCRIPTION_RUN_ID_20260605,
            EXPANSION_TODAY_MINUTE_RUN_ID_20260605,
            EXPANSION_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        ),
        "original": (
            SOURCE_SUBSCRIPTION_RUN_ID_20260605,
            SOURCE_TODAY_MINUTE_RUN_ID_20260605,
            SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        ),
    }
    if group_config_override:
        group_config.update(dict(group_config_override))
    for group_name, candidate_identities in ready_groups.items():
        source_subscription_run_id, today_run_id, previous_run_id = group_config[group_name]
        snapshot_subset = filter_snapshot_rows(snapshot_rows_by_asset, candidate_identities)
        today_rows = load_minute_rows_for_metric_dry_run(
            cur,
            run_id=today_run_id,
            candidate_identities=candidate_identities,
        )
        previous_rows = load_minute_rows_for_metric_dry_run(
            cur,
            run_id=previous_run_id,
            candidate_identities=candidate_identities,
        )
        built = build_metric_candidate_rows_from_sources(
            projection_run_id=projection_run_id,
            projection_schema_version=PROJECTION_SCHEMA_VERSION,
            for_trade_date="20260605",
            source_condition_run_id=SOURCE_CONDITION_RUN_ID_20260605,
            source_subscription_run_id=source_subscription_run_id,
            source_snapshot_run_id=SOURCE_SNAPSHOT_RUN_ID_20260605,
            source_today_minute_run_id=today_run_id,
            source_previous_day_minute_run_id=previous_run_id,
            snapshot_rows_by_asset=snapshot_subset,
            today_minute_rows_by_asset=today_rows,
            previous_day_minute_rows_by_asset=previous_rows,
        )
        for asset_kind, rows in built.items():
            for row in rows:
                identity = str(row["identity_key"])
                row["calculation_config_hash"] = "n3.action_confirmation_metric.20260605.materialization.v1"
                row["raw_json"] = enrich_20260605_raw_json(
                    row,
                    projection_rows.get(identity) or {},
                    n4_events.get(identity) or [],
                    group_name=group_name,
                )
                row["source_fact_ids"] = enrich_20260605_source_fact_ids(
                    row,
                    projection_rows.get(identity) or {},
                    n4_events.get(identity) or [],
                )
                output[asset_kind].append(normalize_jsonable(row))
    for asset_kind in ASSET_KINDS:
        output[asset_kind].sort(key=lambda row: str(row["identity_key"]))
    return output


def enrich_20260605_raw_json(
    row: Mapping[str, Any],
    projection_row: Mapping[str, Any],
    events: Sequence[N4MatchEvent],
    *,
    group_name: str,
) -> dict[str, Any]:
    raw = dict(row.get("raw_json") or {})
    raw.update(
        {
            "materialization_payload": True,
            "dry_run_only": False,
            "metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
            "source_realtime_projection": {
                "projection_run_id": projection_row.get("projection_run_id"),
                "projection_id": projection_row.get("projection_id"),
                "projection_status": projection_row.get("projection_status"),
                "projection_quality_status": projection_row.get("projection_quality_status"),
                "projection_signal_status": projection_row.get("projection_signal_status"),
                "trace_status": projection_row.get("trace_status"),
            },
            "source_minute_group": group_name,
            "n4_trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID_20260605,
            "n4_trigger_matched_event_count": len(events),
            "n4_trigger_matched_events": [normalize_jsonable(event.__dict__) for event in events],
            "ready_backed_policy": "materialize_metric",
            "not_ready_policy": "pending_market_data_excluded_from_metric_rows",
            "n4_recompute_allowed": False,
            "n5_opaque_payload_trust_allowed": False,
            "bj_excluded": True,
            "full_excluded": True,
        }
    )
    return raw


def enrich_20260605_source_fact_ids(
    row: Mapping[str, Any],
    projection_row: Mapping[str, Any],
    events: Sequence[N4MatchEvent],
) -> dict[str, Any]:
    source_fact_ids = dict(row.get("source_fact_ids") or {})
    source_fact_ids.update(
        {
            "source_realtime_projection_id": projection_row.get("projection_id"),
            "source_realtime_projection_run_id": projection_row.get("projection_run_id"),
            "n4_trigger_match_ids": [event.trigger_match_id for event in events],
            "n4_output_event_ids": [event.output_event_id for event in events if event.output_event_id],
        }
    )
    return source_fact_ids


def load_n4_matched_events(cur: Any) -> dict[str, list[N4MatchEvent]]:
    cur.execute(
        """
        SELECT
          m.trigger_match_id,
          m.output_event_id,
          o.event_id,
          m.asset_kind,
          m.identity_key,
          m.direction,
          m.signal_type,
          m.condition_key,
          m.trigger_mark_candidate,
          m.trigger_period,
          m.trigger_bucket
        FROM common_trigger_match m
        LEFT JOIN common_event_outbox o
          ON o.source_run_id = m.run_id
         AND o.event_type = 'TriggerMatched'
         AND o.event_id = m.output_event_id
        WHERE m.run_id = %s
          AND m.output_event_type = 'TriggerMatched'
          AND m.identity_key NOT LIKE '%%:BJ:%%'
          AND COALESCE(m.signal_type, '') NOT LIKE '%%FULL%%'
          AND COALESCE(m.condition_key, '') NOT LIKE '%%FULL%%'
        ORDER BY m.asset_kind, m.identity_key, m.trigger_match_id
        """,
        (TRIGGER_EXECUTE_RUN_ID,),
    )
    grouped: dict[str, list[N4MatchEvent]] = defaultdict(list)
    for row in cur.fetchall():
        grouped[str(row["identity_key"])].append(
            N4MatchEvent(
                trigger_match_id=int(row["trigger_match_id"]),
                output_event_id=row.get("output_event_id"),
                event_id=row.get("event_id"),
                asset_kind=str(row["asset_kind"]),
                identity_key=str(row["identity_key"]),
                direction=row.get("direction"),
                signal_type=row.get("signal_type"),
                condition_key=row.get("condition_key"),
                trigger_mark_candidate=row.get("trigger_mark_candidate"),
                trigger_period=row.get("trigger_period"),
                trigger_bucket=row.get("trigger_bucket"),
            )
        )
    return dict(grouped)


def select_projection_enrichment_rows(cur: Any, n4_events: Mapping[str, Sequence[N4MatchEvent]]) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for asset_kind in ASSET_KINDS:
        identities = [identity for identity, events in n4_events.items() if events and events[0].asset_kind == asset_kind]
        if not identities:
            continue
        table = projection_enrichment_table(asset_kind)
        cur.execute(
            f"""
            SELECT *
            FROM {table}
            WHERE projection_run_id = %s
              AND metric_ready = true
              AND identity_key = ANY(%s)
            ORDER BY identity_key, source_trigger_context_id NULLS LAST, projection_enrichment_id
            """,
            (PROJECTION_ENRICHMENT_V4_RUN_ID, identities),
        )
        candidates_by_identity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in cur.fetchall():
            candidates_by_identity[str(row["identity_key"])].append(normalize_jsonable(dict(row)))
        for identity, candidates in candidates_by_identity.items():
            selected[identity] = choose_v4_row_for_identity(candidates, n4_events[identity])
    return selected


def choose_v4_row_for_identity(candidates: Sequence[Mapping[str, Any]], events: Sequence[N4MatchEvent]) -> dict[str, Any]:
    event_condition_keys = {str(event.condition_key) for event in events if event.condition_key}
    event_directions = {str(event.direction) for event in events if event.direction}

    def score(row: Mapping[str, Any]) -> tuple[int, int, int]:
        condition_key = str(row.get("condition_key") or "")
        direction = str(row.get("direction") or "")
        source_pair_ready = bool(row.get("source_today_minute_run_id")) and bool(row.get("source_previous_day_minute_run_id"))
        return (
            0 if condition_key in event_condition_keys else 1,
            0 if direction in event_directions else 1,
            0 if source_pair_ready else 1,
        )

    return dict(sorted(candidates, key=score)[0])


def build_action_metric_rows_from_v4(
    cur: Any,
    selected_v4_rows: Mapping[str, Mapping[str, Any]],
    n4_events: Mapping[str, Sequence[N4MatchEvent]],
) -> dict[str, list[dict[str, Any]]]:
    snapshot_rows_by_asset = load_snapshot_rows_for_metric_dry_run(cur, source_snapshot_run_id=SOURCE_SNAPSHOT_RUN_ID)
    output: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for identity, row in selected_v4_rows.items():
        key = (
            str(row.get("source_subscription_run_id") or ""),
            str(row.get("source_today_minute_run_id") or ""),
            str(row.get("source_previous_day_minute_run_id") or ""),
        )
        groups[key].append(identity)

    for (subscription_run_id, today_run_id, previous_run_id), identities in groups.items():
        candidate_identities = identities_by_asset(identities)
        group_snapshot_rows = filter_snapshot_rows(snapshot_rows_by_asset, candidate_identities)
        today_rows = load_minute_rows_for_metric_dry_run(
            cur,
            run_id=today_run_id,
            candidate_identities=candidate_identities,
        )
        previous_rows = load_minute_rows_for_metric_dry_run(
            cur,
            run_id=previous_run_id,
            candidate_identities=candidate_identities,
        )
        built = build_metric_candidate_rows_from_sources(
            projection_run_id=TARGET_RUN_ID,
            projection_schema_version=PROJECTION_SCHEMA_VERSION,
            for_trade_date=FOR_TRADE_DATE,
            source_condition_run_id=SOURCE_CONDITION_RUN_ID,
            source_subscription_run_id=subscription_run_id,
            source_snapshot_run_id=SOURCE_SNAPSHOT_RUN_ID,
            source_today_minute_run_id=today_run_id,
            source_previous_day_minute_run_id=previous_run_id,
            snapshot_rows_by_asset=group_snapshot_rows,
            today_minute_rows_by_asset=today_rows,
            previous_day_minute_rows_by_asset=previous_rows,
        )
        for asset_kind, rows in built.items():
            for row in rows:
                identity = str(row["identity_key"])
                v4_row = selected_v4_rows[identity]
                row["raw_json"] = enrich_raw_json(row, v4_row, n4_events[identity])
                row["source_fact_ids"] = enrich_source_fact_ids(row, v4_row, n4_events[identity])
                row["calculation_config_hash"] = "n3.action_confirmation_metric.20260603.materialization.v1"
                output[asset_kind].append(normalize_jsonable(row))
    for asset_kind in ASSET_KINDS:
        output[asset_kind].sort(key=lambda row: str(row["identity_key"]))
    return output


def enrich_raw_json(row: Mapping[str, Any], v4_row: Mapping[str, Any], events: Sequence[N4MatchEvent]) -> dict[str, Any]:
    raw = dict(row.get("raw_json") or {})
    raw.update(
        {
            "materialization_payload": True,
            "dry_run_only": False,
            "metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
            "source_projection_enrichment_v4": {
                "projection_run_id": v4_row.get("projection_run_id"),
                "projection_enrichment_id": v4_row.get("projection_enrichment_id"),
                "source_trigger_context_run_id": v4_row.get("source_trigger_context_run_id"),
                "source_trigger_context_id": v4_row.get("source_trigger_context_id"),
                "materialization_row_key": v4_row.get("materialization_row_key"),
                "condition_key": v4_row.get("condition_key"),
                "trigger_amount_chain_pass": v4_row.get("trigger_amount_chain_pass"),
                "projection_30m_flag": v4_row.get("projection_30m_flag"),
                "projection_30m_type": v4_row.get("projection_30m_type"),
            },
            "n4_trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID,
            "n4_trigger_matched_event_count": len(events),
            "n4_trigger_matched_events": [normalize_jsonable(event.__dict__) for event in events],
            "n4_recompute_allowed": False,
            "n5_opaque_payload_trust_allowed": False,
            "bj_excluded": True,
            "full_excluded": True,
        }
    )
    return raw


def enrich_source_fact_ids(row: Mapping[str, Any], v4_row: Mapping[str, Any], events: Sequence[N4MatchEvent]) -> dict[str, Any]:
    source_fact_ids = dict(row.get("source_fact_ids") or {})
    source_fact_ids.update(
        {
            "source_projection_enrichment_v4_id": v4_row.get("projection_enrichment_id"),
            "source_projection_enrichment_v4_run_id": v4_row.get("projection_run_id"),
            "source_trigger_context_id": v4_row.get("source_trigger_context_id"),
            "n4_trigger_match_ids": [event.trigger_match_id for event in events],
            "n4_output_event_ids": [event.output_event_id for event in events if event.output_event_id],
        }
    )
    return source_fact_ids


def build_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_payload(payload)
    return {
        "stage": "N3 action-confirmation metric 20260603 materialization execute contract",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS" if validation["valid"] else "CONTRACT_BLOCKED",
        "execute_authorized_now": False,
        "runner_exists": True,
        "runner_readiness": "ready",
        "execute_command": EXECUTE_COMMAND,
        "projection_run_id": TARGET_RUN_ID,
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "for_trade_date": FOR_TRADE_DATE,
        "source_trade_date": SOURCE_TRADE_DATE,
        "prev_trade_date": SOURCE_TRADE_DATE,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID,
        "source_projection_enrichment_v4_run_id": PROJECTION_ENRICHMENT_V4_RUN_ID,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID,
        "expected_rows": EXPECTED_ROW_COUNTS,
        "metric_ready_expected": EXPECTED_METRIC_READY,
        "expected_n4_matched_coverage": {"covered": EXPECTED_N4_MATCHED, "expected": EXPECTED_N4_MATCHED, "missing": 0},
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "requested_target_aliases": list(REQUESTED_TARGET_ALIASES),
        "actual_032_target_tables": dict(MATERIALIZATION_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "pulls_market_data": False,
        "enters_n4_n5_n6": False,
        "starts_worker": False,
        "quality_rollback_predicate": {
            "layer_scope": QUALITY_LAYER_SCOPE,
            "details.metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
        },
        "row_policy": {
            "BJ_excluded": True,
            "FULL_excluded": True,
            "metric_grain": "identity-level 032 metric row; multiple N4 TriggerMatched events are carried in raw_json.n4_trigger_matched_events",
            "n4_payload_mutation_allowed": False,
        },
        "rollback": {
            "rollback_sql_path": DEFAULT_ROLLBACK_SQL_PATH,
            "scope": "projection_run_id",
            "hard_fail_before_delete": True,
            "guard": [
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "common_trigger_match/common_trigger_run",
                "common_action_event",
                "N6/user refs",
                "downstream_layers_touched",
                "worker_started",
            ],
        },
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }


def build_20260605_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_payload(
        payload,
        target_run_id=TARGET_RUN_ID_20260605,
        expected_row_counts=EXPECTED_ROW_COUNTS_20260605,
        expected_metric_ready=EXPECTED_ROW_COUNTS_20260605["total"],
        expected_n4_matched=EXPECTED_N4_MATCHED_20260605,
    )
    return {
        "stage": "N3 20260605 action-confirmation metric materialization contract",
        "preflight_stage": "N3 20260605 action-confirmation metric materialization preflight",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS" if validation["valid"] else "CONTRACT_BLOCKED",
        "execute_authorized_now": False,
        "runner_exists": True,
        "runner_readiness": "ready_contract_driven",
        "execute_command": EXECUTE_COMMAND_20260605,
        "projection_run_id": TARGET_RUN_ID_20260605,
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "for_trade_date": "20260605",
        "source_trade_date": "20260604",
        "prev_trade_date": "20260604",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID_20260605,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID_20260605,
        "source_subscription_run_ids": [
            SOURCE_SUBSCRIPTION_RUN_ID_20260605,
            EXPANSION_SUBSCRIPTION_RUN_ID_20260605,
        ],
        "source_today_minute_run_ids": [
            SOURCE_TODAY_MINUTE_RUN_ID_20260605,
            EXPANSION_TODAY_MINUTE_RUN_ID_20260605,
        ],
        "source_previous_day_minute_run_ids": [
            SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
            EXPANSION_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        ],
        "expected_rows": dict(EXPECTED_ROW_COUNTS_20260605),
        "metric_ready_expected": EXPECTED_ROW_COUNTS_20260605["total"],
        "expected_n4_matched_coverage": {
            "covered": EXPECTED_N4_MATCHED_20260605,
            "expected": EXPECTED_N4_MATCHED_20260605,
            "missing": 0,
            "distinct_metric_rows": EXPECTED_ROW_COUNTS_20260605["total"],
        },
        "ready_backed_policy": {
            "policy": "materialize_metric",
            "counts": dict(READY_BACKED_COUNTS_20260605),
        },
        "not_ready_policy": {
            "policy": "pending_market_data",
            "counts": dict(NOT_READY_BACKED_COUNTS_20260605),
            "materialize_metric_rows": False,
            "quality_visibility": "P1",
        },
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "requested_target_aliases": list(REQUESTED_TARGET_ALIASES),
        "actual_032_target_tables": dict(MATERIALIZATION_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "pulls_market_data": False,
        "enters_n4_n5_n6": False,
        "starts_worker": False,
        "quality_rollback_predicate": {
            "layer_scope": QUALITY_LAYER_SCOPE,
            "details.metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
        },
        "row_policy": {
            "BJ_excluded": True,
            "FULL_excluded": True,
            "ready_backed": "materialize",
            "not_ready_backed": "pending_market_data_excluded",
            "metric_grain": "identity-level 032 metric row; multiple N4 TriggerMatched events are carried in raw_json.n4_trigger_matched_events",
            "n4_payload_mutation_allowed": False,
        },
        "rollback": {
            "rollback_sql_path": DEFAULT_ROLLBACK_SQL_PATH_20260605,
            "scope": "projection_run_id",
            "hard_fail_before_delete": True,
            "guard": [
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "common_trigger_match/common_trigger_run",
                "common_action_event",
                "N6/user refs",
                "downstream_layers_touched",
                "worker_started",
            ],
        },
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }


def build_20260605_repaired_context_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    expected_rows = {
        asset: int((payload.get("expected_rows") or {}).get(asset, 0))
        for asset in ("stock", "index", "board", "total")
    }
    coverage = dict(payload.get("n4_matched_coverage") or {})
    expected_n4_matched = int(coverage.get("expected") or coverage.get("covered") or 0)
    validation = validate_payload(
        payload,
        target_run_id=TARGET_RUN_ID_20260605,
        expected_row_counts=expected_rows,
        expected_metric_ready=expected_rows["total"],
        expected_n4_matched=expected_n4_matched,
    )
    ready_policy = dict(payload.get("ready_backed_policy") or {})
    not_ready_policy = dict(payload.get("not_ready_policy") or {})
    return {
        "stage": "N3 20260605 repaired-context action-confirmation metric materialization contract",
        "preflight_stage": "N3 20260605 repaired-context action-confirmation metric materialization preflight",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS" if validation["valid"] else "CONTRACT_BLOCKED",
        "execute_authorized_now": False,
        "runner_exists": True,
        "runner_readiness": "ready_contract_driven",
        "execute_command": EXECUTE_COMMAND_REPAIRED_CONTEXT_20260605,
        "projection_run_id": TARGET_RUN_ID_20260605,
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "for_trade_date": "20260605",
        "source_trade_date": "20260604",
        "prev_trade_date": "20260604",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID_20260605,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID_20260605,
        "source_subscription_run_ids": [
            SOURCE_SUBSCRIPTION_RUN_ID_20260605,
            EXPANSION_SUBSCRIPTION_RUN_ID_20260605,
        ],
        "source_today_minute_run_ids": [
            SOURCE_TODAY_MINUTE_RUN_ID_20260605,
            EXPANSION_TODAY_MINUTE_RUN_ID_20260605,
        ],
        "source_previous_day_minute_run_ids": [
            SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
            EXPANSION_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        ],
        "expected_rows": expected_rows,
        "metric_ready_expected": expected_rows["total"],
        "expected_n4_matched_coverage": {
            "covered": expected_n4_matched,
            "expected": expected_n4_matched,
            "missing": int(coverage.get("missing") or 0),
            "distinct_metric_rows": expected_rows["total"],
            "ready_backed": int(coverage.get("ready_backed") or expected_rows["total"]),
            "pending_market_data": int(coverage.get("pending_market_data") or 0),
        },
        "ready_backed_policy": {
            "policy": "materialize_metric",
            "materialize_metric_rows": True,
            "counts": dict(ready_policy.get("counts") or expected_rows),
        },
        "not_ready_policy": {
            "policy": "pending_market_data",
            "counts": dict(not_ready_policy.get("counts") or {"stock": 0, "index": 0, "board": 0, "total": 0}),
            "materialize_metric_rows": False,
            "quality_visibility": "P1",
            "reason": "repaired-context N4 TriggerMatched rows backed by B2 projection not_ready are excluded from N3 action-confirmation metric materialization; N5 must not infer confirmation from opaque payload.",
        },
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "requested_target_aliases": list(REQUESTED_TARGET_ALIASES),
        "actual_032_target_tables": dict(MATERIALIZATION_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "pulls_market_data": False,
        "enters_n4_n5_n6": False,
        "starts_worker": False,
        "quality_rollback_predicate": {
            "layer_scope": QUALITY_LAYER_SCOPE,
            "details.metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
        },
        "row_policy": {
            "BJ_excluded": True,
            "FULL_excluded": True,
            "ready_backed": "materialize",
            "not_ready_backed": "pending_market_data_excluded",
            "metric_grain": "identity-level 032 metric row; multiple N4 TriggerMatched events are carried in raw_json.n4_trigger_matched_events",
            "n4_payload_mutation_allowed": False,
            "n5_opaque_payload_trust_allowed": False,
        },
        "rollback": {
            "rollback_sql_path": DEFAULT_REPAIRED_CONTEXT_ROLLBACK_SQL_PATH_20260605,
            "scope": "projection_run_id",
            "hard_fail_before_delete": True,
            "guard": [
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "common_trigger_match/common_trigger_run",
                "common_action_event",
                "N6/user refs",
                "downstream_layers_touched",
                "worker_started",
            ],
        },
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }


def build_20260605_coverage_repair_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    expected_rows = {
        asset: int((payload.get("expected_rows") or {}).get(asset, 0))
        for asset in ("stock", "index", "board", "total")
    }
    coverage = dict(payload.get("n4_matched_coverage") or {})
    repair_summary = dict(payload.get("repair_summary") or {})
    validation = validate_payload(
        payload,
        target_run_id=COVERAGE_REPAIR_RUN_ID_20260605,
        expected_row_counts=expected_rows,
        expected_metric_ready=expected_rows["total"],
        expected_n4_matched=int(coverage.get("expected") or coverage.get("covered") or 605),
    )
    return {
        "stage": "N3 action-confirmation metric coverage policy repair contract",
        "preflight_stage": "N3 action-confirmation metric coverage policy repair preflight",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS" if validation["valid"] else "CONTRACT_BLOCKED",
        "execute_authorized_now": False,
        "runner_exists": True,
        "runner_readiness": "ready_contract_driven",
        "execute_command": EXECUTE_COMMAND_COVERAGE_REPAIR_20260605,
        "projection_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
        "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "coverage_policy_version": COVERAGE_POLICY_VERSION_20260605,
        "for_trade_date": "20260605",
        "source_trade_date": "20260604",
        "prev_trade_date": "20260604",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID_20260605,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID_20260605,
        "source_subscription_run_ids": [
            SOURCE_SUBSCRIPTION_RUN_ID_20260605,
            EXPANSION_SUBSCRIPTION_RUN_ID_20260605,
        ],
        "source_today_minute_run_ids": [
            SOURCE_TODAY_MINUTE_RUN_ID_20260605,
            EXPANSION_TODAY_MINUTE_RUN_ID_20260605,
        ],
        "source_previous_day_minute_run_ids": [
            SOURCE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
            EXPANSION_PREVIOUS_DAY_MINUTE_RUN_ID_20260605,
        ],
        "expected_rows": expected_rows,
        "metric_ready_expected": expected_rows["total"],
        "expected_n4_matched_coverage": {
            "covered": int(coverage.get("covered") or 0),
            "expected": int(coverage.get("expected") or coverage.get("covered") or 0),
            "missing": int(coverage.get("missing") or 0),
            "distinct_metric_rows": expected_rows["total"],
            "original_metric_rows": int(repair_summary.get("original_metric_rows") or 0),
            "repair_additive_rows": expected_rows["total"],
            "repaired_total_coverage": int((repair_summary.get("repaired_total_coverage") or {}).get("total") or 0),
            "remaining_excluded": int((repair_summary.get("remaining_excluded") or {}).get("total") or 0),
        },
        "coverage_policy": {
            "policy": "metric_trace_complete_plus_db_check",
            "eligibility_source": "metric_trace_complete",
            "coverage_policy_version": COVERAGE_POLICY_VERSION_20260605,
            "original_projection_status_preserved": True,
            "original_projection_quality_status_preserved": True,
            "original_projection_trace_status_preserved": True,
            "additive_repair_only": True,
            "does_not_overwrite_original_metric_run": True,
        },
        "repair_summary": repair_summary,
        "ready_backed_policy": dict(payload.get("ready_backed_policy") or {}),
        "not_ready_policy": dict(payload.get("not_ready_policy") or {}),
        "remaining_excluded_policy": dict(payload.get("remaining_excluded_policy") or {}),
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "requested_target_aliases": list(REQUESTED_TARGET_ALIASES),
        "actual_032_target_tables": dict(MATERIALIZATION_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "pulls_market_data": False,
        "enters_n4_n5_n6": False,
        "starts_worker": False,
        "quality_rollback_predicate": {
            "layer_scope": QUALITY_LAYER_SCOPE,
            "details.metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
        },
        "row_policy": {
            "BJ_excluded": True,
            "FULL_excluded": True,
            "ready_backed": "preserve_original_metric_rows",
            "not_ready_backed": "materialize_when_metric_trace_complete",
            "lineage_missing": "excluded_quality_visible",
            "metric_grain": "identity-level 032 metric row; multiple N4 TriggerMatched events are carried in raw_json.n4_trigger_matched_events",
            "n4_payload_mutation_allowed": False,
            "n5_opaque_payload_trust_allowed": False,
        },
        "rollback": {
            "rollback_sql_path": DEFAULT_COVERAGE_REPAIR_ROLLBACK_SQL_PATH_20260605,
            "scope": "projection_run_id",
            "hard_fail_before_delete": True,
            "guard": [
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "common_trigger_match/common_trigger_run",
                "common_action_event",
                "N5/N6/user/delivery/sim/position/virtual refs",
                "downstream_layers_touched",
                "worker_started",
            ],
            "does_not_delete_original_metric_run": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
            "no_cascade_drop_truncate": True,
        },
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }


def build_20260605_board_lineage_metric_v2_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    expected_rows = {
        asset: int((payload.get("expected_rows") or {}).get(asset, 0))
        for asset in ("stock", "index", "board", "total")
    }
    coverage = dict(payload.get("n4_matched_coverage") or {})
    repair_summary = dict(payload.get("repair_summary") or {})
    validation = validate_payload(
        payload,
        target_run_id=BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
        expected_row_counts=expected_rows,
        expected_metric_ready=expected_rows["total"],
        expected_n4_matched=int(coverage.get("expected") or BOARD_LINEAGE_EXPECTED_FINAL_COVERAGE_20260605),
    )
    return {
        "stage": "N3_BOARD_LINEAGE_METRIC_V2_CONTRACT",
        "preflight_stage": "N3_BOARD_LINEAGE_METRIC_V2_PREFLIGHT",
        "layer_role": "N3_market_data",
        "contract_result": "CONTRACT_PASS" if validation["valid"] else "CONTRACT_BLOCKED",
        "execute_authorized_now": False,
        "runner_exists": True,
        "runner_readiness": "ready_contract_driven",
        "execute_command": EXECUTE_COMMAND_BOARD_LINEAGE_METRIC_V2_20260605,
        "projection_run_id": BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
        "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        "additive_v1_metric_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
        "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        "coverage_policy_version": BOARD_LINEAGE_POLICY_VERSION_20260605,
        "for_trade_date": "20260605",
        "source_trade_date": "20260604",
        "prev_trade_date": "20260604",
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID_20260605,
        "trigger_execute_run_id": TRIGGER_EXECUTE_RUN_ID_20260605,
        "source_realtime_projection_run_id": SOURCE_REALTIME_PROJECTION_RUN_ID_20260605,
        "source_snapshot_run_id": SOURCE_SNAPSHOT_RUN_ID_20260605,
        "source_subscription_run_ids": [BOARD_LINEAGE_SUBSCRIPTION_RUN_ID_20260605],
        "source_today_minute_run_ids": [BOARD_LINEAGE_TODAY_MINUTE_RUN_ID_20260605],
        "source_previous_day_minute_run_ids": [BOARD_LINEAGE_PREVIOUS_DAY_MINUTE_RUN_ID_20260605],
        "expected_rows": expected_rows,
        "metric_ready_expected": expected_rows["total"],
        "expected_n4_matched_coverage": {
            "covered": int(coverage.get("covered") or 0),
            "expected": int(coverage.get("expected") or 0),
            "missing": int(coverage.get("missing") or 0),
            "distinct_metric_rows": expected_rows["total"],
            "existing_coverage": int(coverage.get("existing_coverage") or 0),
            "board_lineage_metric_v2_additive": expected_rows["total"],
            "final_coverage_after_metric_v2": int(coverage.get("final_coverage_after_metric_v2") or 0),
            "remaining_excluded": int(coverage.get("remaining_excluded") or 0),
        },
        "coverage_policy": dict(payload.get("coverage_policy") or {}),
        "repair_summary": repair_summary,
        "ready_backed_policy": dict(payload.get("ready_backed_policy") or {}),
        "not_ready_policy": dict(payload.get("not_ready_policy") or {}),
        "remaining_excluded_policy": dict(payload.get("remaining_excluded_policy") or {}),
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "requested_target_aliases": list(REQUESTED_TARGET_ALIASES),
        "actual_032_target_tables": dict(MATERIALIZATION_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "pulls_market_data": False,
        "enters_n4_n5_n6": False,
        "starts_worker": False,
        "quality_rollback_predicate": {
            "layer_scope": QUALITY_LAYER_SCOPE,
            "details.metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
        },
        "row_policy": {
            "BJ_excluded": True,
            "FULL_excluded": True,
            "original_metric_rows_preserved": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
            "additive_v1_metric_rows_preserved": COVERAGE_REPAIR_RUN_ID_20260605,
            "board_lineage_metric_v2": "materialize_when_metric_trace_complete_and_db_check_pass",
            "metric_grain": "identity-level 032 board_action_confirmation_projection_metric row",
            "n4_payload_mutation_allowed": False,
            "n5_opaque_payload_trust_allowed": False,
        },
        "rollback": {
            "rollback_sql_path": DEFAULT_BOARD_LINEAGE_METRIC_V2_ROLLBACK_SQL_PATH_20260605,
            "scope": "projection_run_id",
            "hard_fail_before_delete": True,
            "guard": [
                "common_event_outbox",
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "common_trigger_match/common_trigger_run",
                "common_action_event",
                "N5/N6/user/delivery/sim/position/virtual refs",
                "downstream_layers_touched",
                "worker_started",
            ],
            "delete_scope": [
                "board_action_confirmation_projection_metric",
                "common_market_data_quality_item",
                "common_market_data_run",
            ],
            "does_not_delete_original_metric_run": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
            "does_not_delete_additive_v1_metric_run": COVERAGE_REPAIR_RUN_ID_20260605,
            "does_not_delete_a1_c1_minute_rows": True,
            "does_not_delete_subscription_rows": True,
            "no_cascade_drop_truncate": True,
        },
        "validation": validation,
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }


def build_preflight(dsn: str, payload: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_payload(
        payload,
        target_run_id=contract_projection_run_id(contract),
        expected_row_counts=contract_expected_rows(contract),
        expected_metric_ready=contract_metric_ready_expected(contract),
        expected_n4_matched=contract_expected_n4_matched(contract),
    )
    with audited_n3_market_readonly_plan_connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn:
        preflight = execute_preflight(conn, contract, validation)
    quality_items = build_preflight_quality_items(contract, validation, preflight)
    quality_counts = count_quality_severities(quality_items)
    return {
        "stage": str(contract.get("preflight_stage") or contract.get("stage") or "N3 action-confirmation metric materialization execute preflight"),
        "layer_role": "N3_market_data",
        "result": "PREFLIGHT_BLOCKED" if quality_counts["P0"] else "PREFLIGHT_PASS",
        "blocked": bool(quality_counts["P0"]),
        "blockers": [
            item["gate_code"]
            for item in quality_items
            if item["severity"] == "P0" and item["status"] == "failed"
        ],
        "projection_run_id": contract_projection_run_id(contract),
        "expected_rows": contract_expected_rows(contract),
        "metric_ready_expected": contract_metric_ready_expected(contract),
        "payload_validation": validation,
        "baseline_summary": preflight.get("baseline_summary"),
        "source_status": preflight.get("source_status"),
        "event_refs": preflight.get("event_refs"),
        "downstream_refs": preflight.get("downstream_refs"),
        "allowed_write_tables": list(ALLOWED_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
        "execute_command": contract.get("execute_command") or EXECUTE_COMMAND,
        "quality": {
            "P0": quality_counts["P0"],
            "P1": quality_counts["P1"],
            "P2": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": side_effects(writes_database=False),
        "generated_at": utc_now_iso(),
    }


def execute_preflight(
    conn: psycopg.Connection[dict[str, Any]],
    contract: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    projection_run_id = contract_projection_run_id(contract)
    baseline = capture_baseline(conn, projection_run_id)
    source_status = fetch_source_status(conn, contract)
    blockers: list[str] = []
    baseline_nonzero = {
        key: value
        for key, value in baseline.items()
        if key != "downstream_refs" and int(value or 0) != 0
    }
    if baseline_nonzero:
        blockers.append("scoped_baseline_nonzero")
    if baseline["downstream_refs"]["total"]:
        blockers.append("downstream_refs_nonzero")
    failed_sources = {
        source_name: status
        for source_name, status in source_status.items()
        if status not in {"passed", "passed_active"}
    }
    if failed_sources:
        blockers.append("source_run_not_passed")
    if not validation.get("valid"):
        blockers.append("payload_validation_failed")
    return {
        "blocked": bool(blockers),
        "blockers": blockers,
        "baseline_summary": baseline,
        "source_status": source_status,
        "event_refs": {
            "outbox": baseline["common_event_outbox"],
            "inbox": baseline["common_event_inbox"],
            "checkpoint": baseline["common_event_consumer_checkpoint"],
        },
        "downstream_refs": baseline["downstream_refs"],
    }


def capture_baseline(conn: psycopg.Connection[dict[str, Any]], projection_run_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        counts: dict[str, Any] = {
            "common_market_data_run": count_where(cur, "common_market_data_run", "run_id = %s", (projection_run_id,)),
            "common_market_data_quality_item": count_where(cur, "common_market_data_quality_item", "run_id = %s", (projection_run_id,)),
            "common_event_outbox": count_where(cur, "common_event_outbox", "source_run_id = %s OR payload_json::text LIKE %s", (projection_run_id, like_ref(projection_run_id))),
            "common_event_inbox": count_where(cur, "common_event_inbox", "source_run_id = %s OR payload_json::text LIKE %s OR raw_json::text LIKE %s", (projection_run_id, like_ref(projection_run_id), like_ref(projection_run_id))),
            "common_event_consumer_checkpoint": checkpoint_refs(cur, projection_run_id),
        }
        for asset_kind, table in MATERIALIZATION_TABLES.items():
            counts[table] = count_where(cur, table, "projection_run_id = %s", (projection_run_id,))
        counts["downstream_refs"] = downstream_refs(cur, projection_run_id)
    return counts


def fetch_source_status(conn: psycopg.Connection[dict[str, Any]], contract: Mapping[str, Any] | None = None) -> dict[str, str | None]:
    contract = contract or {}
    source_run_ids = {
        "source_condition_run_id": str(contract.get("source_condition_run_id") or SOURCE_CONDITION_RUN_ID),
        "source_snapshot_run_id": str(contract.get("source_snapshot_run_id") or SOURCE_SNAPSHOT_RUN_ID),
        "source_projection_enrichment_v4_run_id": str(contract.get("source_projection_enrichment_v4_run_id") or ""),
        "source_realtime_projection_run_id": str(contract.get("source_realtime_projection_run_id") or ""),
        "trigger_execute_run_id": str(contract.get("trigger_execute_run_id") or TRIGGER_EXECUTE_RUN_ID),
    }
    result: dict[str, str | None] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM common_condition_run WHERE run_id = %s", (source_run_ids["source_condition_run_id"],))
        row = cur.fetchone()
        result["source_condition_run_id"] = row["status"] if row else None
        for key in ("source_snapshot_run_id", "source_projection_enrichment_v4_run_id", "source_realtime_projection_run_id"):
            if not source_run_ids.get(key):
                continue
            cur.execute("SELECT status FROM common_market_data_run WHERE run_id = %s", (source_run_ids[key],))
            row = cur.fetchone()
            result[key] = row["status"] if row else None
        cur.execute("SELECT status FROM common_trigger_run WHERE run_id = %s", (source_run_ids["trigger_execute_run_id"],))
        row = cur.fetchone()
        result["trigger_execute_run_id"] = row["status"] if row else None
        for list_key in ("source_today_minute_run_ids", "source_previous_day_minute_run_ids"):
            run_ids = [str(item) for item in (contract.get(list_key) or []) if item]
            for index, run_id in enumerate(run_ids, start=1):
                cur.execute("SELECT status FROM common_market_data_run WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
                result[f"{list_key}[{index}]"] = row["status"] if row else None
    return result


def build_execute_quality_items(
    contract: Mapping[str, Any],
    validation: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> list[dict[str, Any]]:
    items = build_preflight_quality_items(contract, validation, preflight)
    source_trade_date = str(contract.get("source_trade_date") or SOURCE_TRADE_DATE)
    projection_run_id = contract_projection_run_id(contract)
    source_condition_run_id = str(contract.get("source_condition_run_id") or SOURCE_CONDITION_RUN_ID)
    for_trade_date = str(contract.get("for_trade_date") or FOR_TRADE_DATE)
    for item in items:
        item.update(
            {
                "run_id": projection_run_id,
                "source_condition_run_id": source_condition_run_id,
                "for_trade_date": for_trade_date,
                "source_trade_date": source_trade_date,
                "data_domain": "common",
                "layer_scope": QUALITY_LAYER_SCOPE,
                "table_name": "common_market_data_run",
            }
        )
        details = dict(item.get("details") or {})
        details.setdefault("metric_scope", ACTION_CONFIRMATION_METRIC_SCOPE)
        details.setdefault("projection_run_id", projection_run_id)
        item["details"] = details
    return items


def build_preflight_quality_items(
    contract: Mapping[str, Any],
    validation: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> list[dict[str, Any]]:
    row_counts = validation.get("row_counts") or {}
    coverage = validation.get("n4_matched_coverage") or {}
    baseline = preflight.get("baseline_summary") or {}
    baseline_nonzero = {
        key: value
        for key, value in baseline.items()
        if key != "downstream_refs" and int(value or 0) != 0
    }
    items = [
        quality_item(
            "P0",
            "passed" if validation.get("valid") else "failed",
            "n3_action_metric_materialization_payload_valid",
            "payload row counts, metric_ready, BJ/FULL exclusion, and DB CHECK simulation must pass",
            expected=json.dumps(validation.get("expected_row_counts") or contract_expected_rows(contract), sort_keys=True),
            actual=json.dumps(row_counts, sort_keys=True),
            details={"blocked_reasons": validation.get("blocked_reasons", [])},
        ),
        quality_item(
            "P0",
            "passed" if int(coverage.get("covered") or 0) == contract_expected_n4_matched(contract) and int(coverage.get("missing") or 0) == 0 else "failed",
            "n3_action_metric_materialization_n4_coverage",
            "payload must account for every in-scope N4 TriggerMatched event; excluded rows stay quality-visible and are not silently materialized",
            expected=str(contract_expected_n4_matched(contract)),
            actual=json.dumps(coverage, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if not baseline_nonzero else "failed",
            "n3_action_metric_materialization_scoped_baseline_zero",
            "projection_run_id scoped run/quality/metric/outbox/inbox/checkpoint rows must be zero",
            expected="all scoped counts 0",
            actual=json.dumps(baseline, sort_keys=True),
            details={"nonzero": baseline_nonzero},
        ),
        quality_item(
            "P0",
            "passed" if not (preflight.get("downstream_refs") or {}).get("total") else "failed",
            "n3_action_metric_materialization_downstream_refs_zero",
            "N4/N5/N6 downstream refs for projection_run_id must be zero before execute",
            expected="0",
            actual=json.dumps(preflight.get("downstream_refs") or {}, sort_keys=True),
        ),
        quality_item(
            "P0",
            "passed" if not validation.get("bj_identity_rows") else "failed",
            "n3_action_metric_materialization_bj_excluded",
            "BJ identities are intentionally excluded from this action-confirmation metric lineage",
            expected="0",
            actual=str(validation.get("bj_identity_rows")),
        ),
        quality_item(
            "P0",
            "passed" if not validation.get("full_signal_type_rows") and not validation.get("full_condition_key_rows") else "failed",
            "n3_action_metric_materialization_full_excluded",
            "FULL rows are intentionally excluded from this action-confirmation metric lineage",
            expected="0",
            actual=json.dumps(
                {
                    "full_signal_type_rows": validation.get("full_signal_type_rows"),
                    "full_condition_key_rows": validation.get("full_condition_key_rows"),
                },
                sort_keys=True,
            ),
        ),
        quality_item(
            "P1",
            "warning",
            "n3_action_metric_materialization_n4_payload_metric_id_still_zero",
            "N3 materialization does not mutate N4 payload source_action_confirmation_metric_id; downstream must use deterministic join or a separate link refresh",
            expected="explicit downstream join/link policy",
            actual="N4 payload unchanged by N3",
            details={"metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE},
        ),
    ]
    not_ready_policy = dict(contract.get("not_ready_policy") or {})
    not_ready_counts = dict(not_ready_policy.get("counts") or {})
    not_ready_total = int(not_ready_counts.get("total") or 0)
    if not_ready_policy.get("policy") == "pending_market_data" and not_ready_total:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_action_metric_materialization_not_ready_pending_market_data_visible",
                "N4 matched rows backed by B2 projection not_ready are excluded from metric rows and remain pending_market_data quality-visible",
                expected="pending_market_data excluded, not silent pass",
                actual=json.dumps(not_ready_counts, sort_keys=True),
                details={"metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE, "policy": not_ready_policy},
            )
        )
    remaining_policy = dict(contract.get("remaining_excluded_policy") or {})
    remaining_counts = dict(remaining_policy.get("counts") or {})
    remaining_total = int(remaining_counts.get("total") or 0)
    if remaining_policy.get("policy") == "excluded_lineage_missing" and remaining_total:
        items.append(
            quality_item(
                "P1",
                "warning",
                "n3_action_metric_materialization_remaining_lineage_missing_visible",
                "N4 matched rows without today/previous-day minute lineage remain excluded and quality-visible",
                expected="lineage missing excluded, no silent fallback",
                actual=json.dumps(remaining_counts, sort_keys=True),
                details={"metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE, "policy": remaining_policy},
            )
        )
    return items


def insert_market_data_run(
    conn: psycopg.Connection[dict[str, Any]],
    contract: Mapping[str, Any],
    validation: Mapping[str, Any],
    quality_counts: Mapping[str, int],
) -> None:
    projection_run_id = contract_projection_run_id(contract)
    source_condition_run_id = str(contract.get("source_condition_run_id") or SOURCE_CONDITION_RUN_ID)
    for_trade_date = str(contract.get("for_trade_date") or FOR_TRADE_DATE)
    source_trade_date = str(contract.get("source_trade_date") or SOURCE_TRADE_DATE)
    prev_trade_date = str(contract.get("prev_trade_date") or source_trade_date)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO common_market_data_run (
              run_id, source_condition_run_id, for_trade_date, source_trade_date,
              prev_trade_date, mode, status, p0_count, p1_count, p2_count,
              source_scope_row_count, candidate_row_count, subscription_row_count,
              subscription_object_count, dedup_ratio, generated_by,
              market_data_pulled, market_data_fact_written,
              downstream_layers_touched, worker_started, started_at, finished_at, raw_json
            )
            VALUES (
              %(run_id)s, %(source_condition_run_id)s, %(for_trade_date)s, %(source_trade_date)s,
              %(prev_trade_date)s, 'execute', 'passed', %(p0_count)s, %(p1_count)s, %(p2_count)s,
              %(source_scope_row_count)s, %(candidate_row_count)s, 0,
              %(subscription_object_count)s, 1, %(generated_by)s,
              false, true, false, false, now(), now(), %(raw_json)s
            )
            """,
            {
                "run_id": projection_run_id,
                "source_condition_run_id": source_condition_run_id,
                "for_trade_date": for_trade_date,
                "source_trade_date": source_trade_date,
                "prev_trade_date": prev_trade_date,
                "p0_count": quality_counts["P0"],
                "p1_count": quality_counts["P1"],
                "p2_count": quality_counts["P2"],
                "source_scope_row_count": validation["row_counts"]["total"],
                "candidate_row_count": validation["row_counts"]["total"],
                "subscription_object_count": validation["row_counts"]["total"],
                "generated_by": SCRIPT_PATH,
                "raw_json": Jsonb(
                    {
                        "stage": "N3-action-confirmation-metric-materialization-execute",
                        "metric_scope": ACTION_CONFIRMATION_METRIC_SCOPE,
                        "source_projection_enrichment_v4_run_id": contract.get("source_projection_enrichment_v4_run_id"),
                        "source_realtime_projection_run_id": contract.get("source_realtime_projection_run_id"),
                        "trigger_execute_run_id": contract.get("trigger_execute_run_id") or TRIGGER_EXECUTE_RUN_ID,
                        "allowed_write_tables": ALLOWED_WRITE_TABLES,
                        "forbidden_write_tables": FORBIDDEN_WRITE_TABLES,
                        "writes_outbox": False,
                        "consumes_outbox": False,
                        "n4_payload_mutation_allowed": False,
                        "bj_excluded": True,
                        "full_excluded": True,
                    }
                ),
            },
        )


def insert_quality_rows(conn: psycopg.Connection[dict[str, Any]], quality_items: Sequence[Mapping[str, Any]]) -> None:
    columns = (
        "run_id",
        "source_condition_run_id",
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
    )
    rows = []
    for item in quality_items:
        rows.append(
            (
                item["run_id"],
                item["source_condition_run_id"],
                item["for_trade_date"],
                item["source_trade_date"],
                item.get("data_domain") or "common",
                item["layer_scope"],
                item.get("table_name"),
                item["gate_code"],
                item["gate_name"],
                item["severity"],
                item["status"],
                item.get("expected_value"),
                item.get("actual_value"),
                item.get("identity_key"),
                Jsonb(item.get("details") or {}),
            )
        )
    with conn.cursor() as cur:
        cur.executemany(
            f"""
            INSERT INTO common_market_data_quality_item ({", ".join(columns)})
            VALUES ({", ".join(["%s"] * len(columns))})
            """,
            rows,
        )


def write_artifacts(
    *,
    dsn: str,
    payload_path: str | Path = DEFAULT_PAYLOAD_PATH,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
    contract_md_path: str | Path = DEFAULT_CONTRACT_MD_PATH,
    preflight_path: str | Path = DEFAULT_PREFLIGHT_PATH,
    preflight_md_path: str | Path = DEFAULT_PREFLIGHT_MD_PATH,
    rollback_sql_path: str | Path = DEFAULT_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    payload = build_payload_from_db(dsn)
    contract = build_contract(payload)
    preflight = build_preflight(dsn, payload, contract)
    write_json(payload_path, payload)
    write_json(contract_path, contract)
    write_text(contract_md_path, format_contract_markdown(contract))
    write_json(preflight_path, preflight)
    write_text(preflight_md_path, format_preflight_markdown(preflight))
    write_text(rollback_sql_path, build_rollback_sql())
    return {
        "payload_path": str(payload_path),
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "rollback_sql_path": str(rollback_sql_path),
        "payload_validation": validate_payload(payload),
        "preflight_result": preflight["result"],
    }


def write_20260605_artifacts(
    *,
    dsn: str,
    payload_path: str | Path = DEFAULT_PAYLOAD_PATH_20260605,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH_20260605,
    contract_md_path: str | Path = DEFAULT_CONTRACT_MD_PATH_20260605,
    preflight_path: str | Path = DEFAULT_PREFLIGHT_PATH_20260605,
    preflight_md_path: str | Path = DEFAULT_PREFLIGHT_MD_PATH_20260605,
    dry_run_path: str | Path = DEFAULT_DRY_RUN_PATH_20260605,
    dry_run_md_path: str | Path = DEFAULT_DRY_RUN_MD_PATH_20260605,
    rollback_sql_path: str | Path = DEFAULT_ROLLBACK_SQL_PATH_20260605,
) -> dict[str, Any]:
    payload = build_20260605_payload_from_db(dsn)
    contract = build_20260605_contract(payload)
    preflight = build_preflight(dsn, payload, contract)
    dry_run = build_20260605_dry_run_report(payload=payload, contract=contract, preflight=preflight)
    write_json(payload_path, payload)
    write_json(contract_path, contract)
    write_text(contract_md_path, format_20260605_contract_markdown(contract))
    write_json(preflight_path, preflight)
    write_text(preflight_md_path, format_20260605_preflight_markdown(preflight))
    write_json(dry_run_path, dry_run)
    write_text(dry_run_md_path, format_20260605_dry_run_markdown(dry_run))
    write_text(rollback_sql_path, build_rollback_sql(TARGET_RUN_ID_20260605, label="20260605"))
    return {
        "payload_path": str(payload_path),
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "dry_run_path": str(dry_run_path),
        "rollback_sql_path": str(rollback_sql_path),
        "payload_validation": validate_payload(
            payload,
            target_run_id=TARGET_RUN_ID_20260605,
            expected_row_counts=EXPECTED_ROW_COUNTS_20260605,
            expected_metric_ready=EXPECTED_ROW_COUNTS_20260605["total"],
            expected_n4_matched=EXPECTED_N4_MATCHED_20260605,
        ),
        "preflight_result": preflight["result"],
        "dry_run_result": dry_run["result"],
    }


def write_20260605_repaired_context_artifacts(
    *,
    dsn: str,
    payload_path: str | Path = DEFAULT_REPAIRED_CONTEXT_PAYLOAD_PATH_20260605,
    contract_path: str | Path = DEFAULT_REPAIRED_CONTEXT_CONTRACT_PATH_20260605,
    contract_md_path: str | Path = DEFAULT_REPAIRED_CONTEXT_CONTRACT_MD_PATH_20260605,
    preflight_path: str | Path = DEFAULT_REPAIRED_CONTEXT_PREFLIGHT_PATH_20260605,
    preflight_md_path: str | Path = DEFAULT_REPAIRED_CONTEXT_PREFLIGHT_MD_PATH_20260605,
    dry_run_path: str | Path = DEFAULT_REPAIRED_CONTEXT_DRY_RUN_PATH_20260605,
    dry_run_md_path: str | Path = DEFAULT_REPAIRED_CONTEXT_DRY_RUN_MD_PATH_20260605,
    rollback_sql_path: str | Path = DEFAULT_REPAIRED_CONTEXT_ROLLBACK_SQL_PATH_20260605,
) -> dict[str, Any]:
    payload = build_20260605_payload_from_db(
        dsn,
        expected_n4_matched=None,
        projection_run_id=TARGET_RUN_ID_20260605,
        lineage_scope="repaired_context",
    )
    contract = build_20260605_repaired_context_contract(payload)
    preflight = build_preflight(dsn, payload, contract)
    dry_run = build_20260605_dry_run_report(
        payload=payload,
        contract=contract,
        preflight=preflight,
        artifact_paths={
            "payload_path": str(payload_path),
            "contract_path": str(contract_path),
            "preflight_path": str(preflight_path),
            "rollback_sql_path": str(rollback_sql_path),
        },
    )
    write_json(payload_path, payload)
    write_json(contract_path, contract)
    write_text(contract_md_path, format_20260605_contract_markdown(contract))
    write_json(preflight_path, preflight)
    write_text(preflight_md_path, format_20260605_preflight_markdown(preflight))
    write_json(dry_run_path, dry_run)
    write_text(dry_run_md_path, format_20260605_dry_run_markdown(dry_run))
    write_text(rollback_sql_path, build_rollback_sql(TARGET_RUN_ID_20260605, label="20260605 repaired-context"))
    expected_rows = contract_expected_rows(contract)
    expected_n4_matched = contract_expected_n4_matched(contract)
    return {
        "payload_path": str(payload_path),
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "dry_run_path": str(dry_run_path),
        "rollback_sql_path": str(rollback_sql_path),
        "payload_validation": validate_payload(
            payload,
            target_run_id=TARGET_RUN_ID_20260605,
            expected_row_counts=expected_rows,
            expected_metric_ready=expected_rows["total"],
            expected_n4_matched=expected_n4_matched,
        ),
        "preflight_result": preflight["result"],
        "dry_run_result": dry_run["result"],
    }


def write_20260605_coverage_repair_artifacts(
    *,
    dsn: str,
    payload_path: str | Path = DEFAULT_COVERAGE_REPAIR_PAYLOAD_PATH_20260605,
    contract_path: str | Path = DEFAULT_COVERAGE_REPAIR_CONTRACT_PATH_20260605,
    contract_md_path: str | Path = DEFAULT_COVERAGE_REPAIR_CONTRACT_MD_PATH_20260605,
    preflight_path: str | Path = DEFAULT_COVERAGE_REPAIR_PREFLIGHT_PATH_20260605,
    preflight_md_path: str | Path = DEFAULT_COVERAGE_REPAIR_PREFLIGHT_MD_PATH_20260605,
    dry_run_path: str | Path = DEFAULT_COVERAGE_REPAIR_DRY_RUN_PATH_20260605,
    dry_run_md_path: str | Path = DEFAULT_COVERAGE_REPAIR_DRY_RUN_MD_PATH_20260605,
    rollback_sql_path: str | Path = DEFAULT_COVERAGE_REPAIR_ROLLBACK_SQL_PATH_20260605,
) -> dict[str, Any]:
    payload = build_20260605_coverage_repair_payload_from_db(dsn)
    contract = build_20260605_coverage_repair_contract(payload)
    preflight = build_preflight(dsn, payload, contract)
    dry_run = build_20260605_coverage_repair_dry_run_report(
        payload=payload,
        contract=contract,
        preflight=preflight,
        artifact_paths={
            "payload_path": str(payload_path),
            "contract_path": str(contract_path),
            "preflight_path": str(preflight_path),
            "rollback_sql_path": str(rollback_sql_path),
        },
    )
    write_json(payload_path, payload)
    write_json(contract_path, contract)
    write_text(contract_md_path, format_20260605_coverage_repair_contract_markdown(contract))
    write_json(preflight_path, preflight)
    write_text(preflight_md_path, format_20260605_coverage_repair_preflight_markdown(preflight, contract))
    write_json(dry_run_path, dry_run)
    write_text(dry_run_md_path, format_20260605_coverage_repair_dry_run_markdown(dry_run))
    write_text(
        rollback_sql_path,
        build_rollback_sql(COVERAGE_REPAIR_RUN_ID_20260605, label="20260605 coverage-policy repair"),
    )
    expected_rows = contract_expected_rows(contract)
    return {
        "payload_path": str(payload_path),
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "dry_run_path": str(dry_run_path),
        "rollback_sql_path": str(rollback_sql_path),
        "payload_validation": validate_payload(
            payload,
            target_run_id=COVERAGE_REPAIR_RUN_ID_20260605,
            expected_row_counts=expected_rows,
            expected_metric_ready=expected_rows["total"],
            expected_n4_matched=contract_expected_n4_matched(contract),
        ),
        "preflight_result": preflight["result"],
        "dry_run_result": dry_run["result"],
        "dry_run_proof": dry_run.get("dry_run_proof"),
    }


def write_20260605_board_lineage_metric_v2_artifacts(
    *,
    dsn: str,
    payload_path: str | Path = DEFAULT_BOARD_LINEAGE_METRIC_V2_PAYLOAD_PATH_20260605,
    contract_path: str | Path = DEFAULT_BOARD_LINEAGE_METRIC_V2_CONTRACT_PATH_20260605,
    preflight_path: str | Path = DEFAULT_BOARD_LINEAGE_METRIC_V2_PREFLIGHT_PATH_20260605,
    dry_run_path: str | Path = DEFAULT_BOARD_LINEAGE_METRIC_V2_DRY_RUN_PATH_20260605,
    rollback_sql_path: str | Path = DEFAULT_BOARD_LINEAGE_METRIC_V2_ROLLBACK_SQL_PATH_20260605,
) -> dict[str, Any]:
    payload = build_20260605_board_lineage_metric_v2_payload_from_db(dsn)
    contract = build_20260605_board_lineage_metric_v2_contract(payload)
    preflight = build_preflight(dsn, payload, contract)
    dry_run = build_20260605_board_lineage_metric_v2_dry_run_report(
        payload=payload,
        contract=contract,
        preflight=preflight,
        artifact_paths={
            "payload_path": str(payload_path),
            "contract_path": str(contract_path),
            "preflight_path": str(preflight_path),
            "rollback_sql_path": str(rollback_sql_path),
        },
    )
    write_json(payload_path, payload)
    write_json(contract_path, contract)
    write_json(preflight_path, preflight)
    write_json(dry_run_path, dry_run)
    write_text(rollback_sql_path, build_board_lineage_metric_v2_rollback_sql())
    expected_rows = contract_expected_rows(contract)
    return {
        "payload_path": str(payload_path),
        "contract_path": str(contract_path),
        "preflight_path": str(preflight_path),
        "dry_run_path": str(dry_run_path),
        "rollback_sql_path": str(rollback_sql_path),
        "payload_validation": validate_payload(
            payload,
            target_run_id=BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
            expected_row_counts=expected_rows,
            expected_metric_ready=expected_rows["total"],
            expected_n4_matched=contract_expected_n4_matched(contract),
        ),
        "contract_result": contract["contract_result"],
        "preflight_result": preflight["result"],
        "dry_run_result": dry_run["result"],
        "coverage_proof": dry_run.get("coverage_proof"),
        "sample_proof": dry_run.get("sample_proof"),
    }


def build_board_lineage_metric_v2_rollback_sql(
    projection_run_id: str = BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
) -> str:
    n6_guard_sql = "\n".join(format_optional_downstream_ref_guard(table_name) for table_name in N6_DOWNSTREAM_REF_TABLES)
    return f"""-- N3 board-lineage action-confirmation metric_v2 rollback.
-- Scope: delete only board metric_v2 rows, quality rows, and run row for projection_run_id={projection_run_id}.
-- Does not delete A1/C1 minute rows, scoped subscription rows, N4 TriggerMatched, N5 action, or N6 projections/cards.
-- Hard-fails before DELETE when event infra, downstream N4/N5/N6 refs,
-- downstream_layers_touched, or worker_started indicate consumption.

\\set ON_ERROR_STOP on
\\set projection_run_id '{projection_run_id}'

SELECT set_config('app.projection_run_id', :'projection_run_id', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.projection_run_id');
  outbox_refs BIGINT;
  inbox_refs BIGINT;
  checkpoint_refs BIGINT;
  trigger_refs BIGINT;
  action_refs BIGINT;
  n6_refs BIGINT;
  v_count BIGINT;
  touched_refs BIGINT;
  worker_refs BIGINT;
BEGIN
  n6_refs := 0;

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

{n6_guard_sql}

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
      'N3 board lineage metric_v2 rollback blocked for %, outbox=%, inbox=%, checkpoint=%, trigger=%, action=%, n6=%, downstream_touched=%, worker=%',
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


def build_20260605_dry_run_report(
    *,
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    artifact_paths: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    expected_rows = contract_expected_rows(contract)
    expected_n4_matched = contract_expected_n4_matched(contract)
    validation = validate_payload(
        payload,
        target_run_id=contract_projection_run_id(contract),
        expected_row_counts=expected_rows,
        expected_metric_ready=expected_rows["total"],
        expected_n4_matched=expected_n4_matched,
    )
    rows = payload_rows(payload)
    trace_proof = {
        "source_fact_ids_non_empty": sum(1 for row in rows if isinstance(row.get("source_fact_ids"), Mapping) and bool(row.get("source_fact_ids"))),
        "source_minute_refs_non_empty": sum(1 for row in rows if isinstance(row.get("source_minute_refs"), list) and bool(row.get("source_minute_refs"))),
        "previous_day_minute_refs_required": sum(
            1
            for row in rows
            if any(
                row.get(field) == "previous_trade_date_last_period"
                for field in (
                    "previous_1m_period_source",
                    "previous_5m_period_source",
                    "previous_30m_period_source",
                    "previous_120m_period_source",
                )
            )
        ),
        "previous_day_minute_refs_non_empty": sum(1 for row in rows if isinstance(row.get("previous_day_minute_refs"), list) and bool(row.get("previous_day_minute_refs"))),
        "db_check_failures": validation.get("db_check_failures", 0),
    }
    quality = preflight.get("quality") or {}
    return {
        "stage": str(contract.get("stage") or "N3_20260605_ACTION_CONFIRMATION_METRIC_MATERIALIZATION_DRY_RUN"),
        "layer_role": "N3_market_data",
        "result": "DRY_RUN_PASS" if preflight.get("result") == "PREFLIGHT_PASS" and validation["valid"] else "BLOCKED",
        "blocked": not (preflight.get("result") == "PREFLIGHT_PASS" and validation["valid"]),
        "blockers": list(preflight.get("blockers") or validation.get("blocked_reasons") or []),
        "projection_run_id": contract_projection_run_id(contract),
        "expected_metric_rows": expected_rows,
        "ready_backed_policy": contract.get("ready_backed_policy"),
        "not_ready_policy": contract.get("not_ready_policy"),
        "n4_matched_coverage": payload.get("n4_matched_coverage"),
        "metric_ready_distribution": {
            "ready": validation.get("metric_ready"),
            "not_ready": validation.get("metric_not_ready"),
        },
        "trace_refs_proof": trace_proof,
        "quality": {
            "P0": quality.get("P0", 0),
            "P1": quality.get("P1", 0),
            "P2": quality.get("P2", 0),
            "items": quality.get("items", []),
        },
        "write_scope": {
            "future_execute_allowed_write_tables": list(ALLOWED_WRITE_TABLES),
            "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
            "writes_outbox": False,
            "consumes_outbox": False,
            "enters_n4_n5_n6": False,
        },
        "rollback": contract.get("rollback"),
        "side_effects": side_effects(writes_database=False),
        "artifacts": {
            "payload_path": (artifact_paths or {}).get("payload_path", DEFAULT_PAYLOAD_PATH_20260605),
            "contract_path": (artifact_paths or {}).get("contract_path", DEFAULT_CONTRACT_PATH_20260605),
            "preflight_path": (artifact_paths or {}).get("preflight_path", DEFAULT_PREFLIGHT_PATH_20260605),
            "rollback_sql_path": (artifact_paths or {}).get("rollback_sql_path", DEFAULT_ROLLBACK_SQL_PATH_20260605),
        },
        "generated_at": utc_now_iso(),
    }


def build_20260605_coverage_repair_dry_run_report(
    *,
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    artifact_paths: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    expected_rows = contract_expected_rows(contract)
    validation = validate_payload(
        payload,
        target_run_id=COVERAGE_REPAIR_RUN_ID_20260605,
        expected_row_counts=expected_rows,
        expected_metric_ready=expected_rows["total"],
        expected_n4_matched=contract_expected_n4_matched(contract),
    )
    rows = payload_rows(payload)
    repair_summary = dict(payload.get("repair_summary") or {})
    quality = preflight.get("quality") or {}
    duplicate_vs_original = int(repair_summary.get("duplicate_vs_original_metric") or 0)
    duplicate_inside = int(repair_summary.get("duplicate_inside_repair_payload") or 0)
    dry_run_pass = (
        preflight.get("result") == "PREFLIGHT_PASS"
        and validation["valid"]
        and duplicate_vs_original == 0
        and duplicate_inside == 0
    )
    return {
        "stage": "N3_ACTION_CONFIRMATION_METRIC_COVERAGE_POLICY_REPAIR_DRY_RUN",
        "layer_role": "N3_market_data",
        "result": "DRY_RUN_PASS" if dry_run_pass else "BLOCKED",
        "blocked": not dry_run_pass,
        "blockers": list(preflight.get("blockers") or validation.get("blocked_reasons") or []),
        "projection_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
        "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        "coverage_policy": contract.get("coverage_policy"),
        "expected_metric_rows": expected_rows,
        "dry_run_proof": {
            "original_metric_rows": int(repair_summary.get("original_metric_rows") or 0),
            "n4_matched_universe": int(repair_summary.get("n4_matched_universe") or 0),
            "repair_additive_rows": dict(repair_summary.get("repair_additive_rows") or expected_rows),
            "stock_additive": int(repair_summary.get("stock_additive") or expected_rows.get("stock", 0)),
            "index_additive": int(repair_summary.get("index_additive") or expected_rows.get("index", 0)),
            "board_additive": int(repair_summary.get("board_additive") or expected_rows.get("board", 0)),
            "repaired_total_coverage": dict(repair_summary.get("repaired_total_coverage") or {}),
            "remaining_excluded": dict(repair_summary.get("remaining_excluded") or {}),
            "remaining_excluded_reason": repair_summary.get("remaining_excluded_reason"),
            "duplicate_vs_original_metric": duplicate_vs_original,
            "duplicate_inside_repair_payload": duplicate_inside,
        },
        "sample_proof": payload.get("sample_proof"),
        "metric_ready_distribution": {
            "ready": validation.get("metric_ready"),
            "not_ready": validation.get("metric_not_ready"),
        },
        "trace_refs_proof": {
            "source_fact_ids_non_empty": sum(1 for row in rows if isinstance(row.get("source_fact_ids"), Mapping) and bool(row.get("source_fact_ids"))),
            "source_minute_refs_non_empty": sum(1 for row in rows if isinstance(row.get("source_minute_refs"), list) and bool(row.get("source_minute_refs"))),
            "previous_day_minute_refs_non_empty": sum(1 for row in rows if isinstance(row.get("previous_day_minute_refs"), list) and bool(row.get("previous_day_minute_refs"))),
            "db_check_failures": validation.get("db_check_failures", 0),
        },
        "quality": {
            "P0": quality.get("P0", 0),
            "P1": quality.get("P1", 0),
            "P2": quality.get("P2", 0),
            "items": quality.get("items", []),
        },
        "write_scope": {
            "future_execute_allowed_write_tables": list(ALLOWED_WRITE_TABLES),
            "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
            "writes_outbox": False,
            "consumes_outbox": False,
            "enters_n4_n5_n6": False,
        },
        "rollback": contract.get("rollback"),
        "side_effects": side_effects(writes_database=False),
        "artifacts": {
            "payload_path": (artifact_paths or {}).get("payload_path", DEFAULT_COVERAGE_REPAIR_PAYLOAD_PATH_20260605),
            "contract_path": (artifact_paths or {}).get("contract_path", DEFAULT_COVERAGE_REPAIR_CONTRACT_PATH_20260605),
            "preflight_path": (artifact_paths or {}).get("preflight_path", DEFAULT_COVERAGE_REPAIR_PREFLIGHT_PATH_20260605),
            "rollback_sql_path": (artifact_paths or {}).get("rollback_sql_path", DEFAULT_COVERAGE_REPAIR_ROLLBACK_SQL_PATH_20260605),
        },
        "generated_at": utc_now_iso(),
    }


def build_20260605_board_lineage_metric_v2_dry_run_report(
    *,
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
    preflight: Mapping[str, Any],
    artifact_paths: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    expected_rows = contract_expected_rows(contract)
    validation = validate_payload(
        payload,
        target_run_id=BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
        expected_row_counts=expected_rows,
        expected_metric_ready=expected_rows["total"],
        expected_n4_matched=contract_expected_n4_matched(contract),
    )
    rows = payload_rows(payload)
    repair_summary = dict(payload.get("repair_summary") or {})
    quality = preflight.get("quality") or {}
    duplicate_vs_original = int(repair_summary.get("duplicate_vs_original_metric") or 0)
    duplicate_vs_additive_v1 = int(repair_summary.get("duplicate_vs_additive_v1") or 0)
    duplicate_inside = int(repair_summary.get("duplicate_inside_metric_v2_payload") or 0)
    remaining_excluded = int((repair_summary.get("remaining_excluded") or {}).get("total") or 0)
    sample_proof = dict(payload.get("sample_proof") or {})
    samples_materialized = all(
        (sample_proof.get(identity) or {}).get("materialized_in_metric_v2") is True
        for identity in BOARD_LINEAGE_SAMPLE_IDENTITIES_20260605
    )
    dry_run_pass = (
        preflight.get("result") == "PREFLIGHT_PASS"
        and validation["valid"]
        and duplicate_vs_original == 0
        and duplicate_vs_additive_v1 == 0
        and duplicate_inside == 0
        and remaining_excluded == 0
        and samples_materialized
    )
    return {
        "stage": "N3_BOARD_LINEAGE_METRIC_V2_DRY_RUN",
        "layer_role": "N3_market_data",
        "result": "DRY_RUN_PASS" if dry_run_pass else "BLOCKED",
        "blocked": not dry_run_pass,
        "blockers": list(preflight.get("blockers") or validation.get("blocked_reasons") or []),
        "projection_run_id": BOARD_LINEAGE_METRIC_V2_RUN_ID_20260605,
        "original_metric_run_id": COVERAGE_REPAIR_ORIGINAL_RUN_ID_20260605,
        "additive_v1_metric_run_id": COVERAGE_REPAIR_RUN_ID_20260605,
        "expected_metric_rows": expected_rows,
        "coverage_proof": {
            "existing_coverage": int(repair_summary.get("existing_coverage") or 0),
            "board_metric_v2_additive": int((repair_summary.get("board_metric_v2_additive") or {}).get("total") or expected_rows["total"]),
            "expected_coverage": int(repair_summary.get("expected_coverage") or 0),
            "final_coverage_after_metric_v2": int(repair_summary.get("final_coverage_after_metric_v2") or 0),
            "remaining_excluded": dict(repair_summary.get("remaining_excluded") or {}),
            "remaining_excluded_reason": repair_summary.get("remaining_excluded_reason"),
            "duplicate_vs_original": duplicate_vs_original,
            "duplicate_vs_additive_v1": duplicate_vs_additive_v1,
            "duplicate_inside_metric_v2_payload": duplicate_inside,
        },
        "sample_proof": sample_proof,
        "metric_ready_distribution": {
            "ready": validation.get("metric_ready"),
            "not_ready": validation.get("metric_not_ready"),
        },
        "trace_refs_proof": {
            "source_fact_ids_non_empty": sum(1 for row in rows if isinstance(row.get("source_fact_ids"), Mapping) and bool(row.get("source_fact_ids"))),
            "source_minute_refs_non_empty": sum(1 for row in rows if isinstance(row.get("source_minute_refs"), list) and bool(row.get("source_minute_refs"))),
            "previous_day_minute_refs_non_empty": sum(1 for row in rows if isinstance(row.get("previous_day_minute_refs"), list) and bool(row.get("previous_day_minute_refs"))),
            "db_check_failures": validation.get("db_check_failures", 0),
        },
        "quality": {
            "P0": quality.get("P0", 0),
            "P1": quality.get("P1", 0),
            "P2": quality.get("P2", 0),
            "items": quality.get("items", []),
        },
        "write_scope": {
            "future_execute_allowed_write_tables": list(ALLOWED_WRITE_TABLES),
            "forbidden_write_tables": list(FORBIDDEN_WRITE_TABLES),
            "writes_outbox": False,
            "consumes_outbox": False,
            "enters_n4_n5_n6": False,
        },
        "rollback": contract.get("rollback"),
        "side_effects": side_effects(writes_database=False),
        "artifacts": {
            "payload_path": (artifact_paths or {}).get("payload_path", DEFAULT_BOARD_LINEAGE_METRIC_V2_PAYLOAD_PATH_20260605),
            "contract_path": (artifact_paths or {}).get("contract_path", DEFAULT_BOARD_LINEAGE_METRIC_V2_CONTRACT_PATH_20260605),
            "preflight_path": (artifact_paths or {}).get("preflight_path", DEFAULT_BOARD_LINEAGE_METRIC_V2_PREFLIGHT_PATH_20260605),
            "rollback_sql_path": (artifact_paths or {}).get("rollback_sql_path", DEFAULT_BOARD_LINEAGE_METRIC_V2_ROLLBACK_SQL_PATH_20260605),
        },
        "generated_at": utc_now_iso(),
    }


def build_rollback_sql(projection_run_id: str = TARGET_RUN_ID, *, label: str = "20260603") -> str:
    n6_guard_sql = "\n".join(format_optional_downstream_ref_guard(table_name) for table_name in N6_DOWNSTREAM_REF_TABLES)
    return f"""-- N3 action-confirmation metric {label} materialization business rollback.
-- Scope: delete only rows for projection_run_id={projection_run_id}.
-- Hard-fail before DELETE when event infra, downstream N4/N5/N6 refs,
-- downstream_layers_touched, or worker_started indicate consumption.

\\set ON_ERROR_STOP on
\\set projection_run_id '{projection_run_id}'

SELECT set_config('app.projection_run_id', :'projection_run_id', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.projection_run_id');
  outbox_refs BIGINT;
  inbox_refs BIGINT;
  checkpoint_refs BIGINT;
  trigger_refs BIGINT;
  action_refs BIGINT;
  n6_refs BIGINT;
  v_count BIGINT;
  touched_refs BIGINT;
  worker_refs BIGINT;
BEGIN
  n6_refs := 0;

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

{n6_guard_sql}

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
      'N3 action metric rollback blocked for %, outbox=%, inbox=%, checkpoint=%, trigger=%, action=%, n6=%, downstream_touched=%, worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, trigger_refs, action_refs, n6_refs, touched_refs, worker_refs;
  END IF;
END $$;

BEGIN;

DELETE FROM stock_action_confirmation_projection_metric
WHERE projection_run_id = :'projection_run_id';

DELETE FROM index_action_confirmation_projection_metric
WHERE projection_run_id = :'projection_run_id';

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


def format_optional_downstream_ref_guard(table_name: str) -> str:
    return f"""  IF to_regclass('public.{table_name}') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.{table_name} AS t WHERE to_jsonb(t)::TEXT LIKE $1'
      INTO v_count
      USING '%' || target_run_id || '%';
    n6_refs := n6_refs + COALESCE(v_count, 0);
  END IF;"""


def format_contract_markdown(contract: Mapping[str, Any]) -> str:
    rows = contract.get("expected_rows") or {}
    return f"""# N3 Action-Confirmation Metric 20260603 Materialization Contract

Status: {contract.get("contract_result")}

```text
projection_run_id={contract.get("projection_run_id")}
runner_readiness={contract.get("runner_readiness")}
expected_rows stock/index/board/total={rows.get("stock")}/{rows.get("index")}/{rows.get("board")}/{rows.get("total")}
writes_outbox=false
allowed_write_tables={contract.get("allowed_write_tables")}
actual_032_target_tables={contract.get("actual_032_target_tables")}
requested_target_aliases={contract.get("requested_target_aliases")}
rollback_sql={contract.get("rollback", {}).get("rollback_sql_path")}
```
"""


def format_20260605_contract_markdown(contract: Mapping[str, Any]) -> str:
    rows = contract.get("expected_rows") or {}
    ready = (contract.get("ready_backed_policy") or {}).get("counts") or {}
    pending = (contract.get("not_ready_policy") or {}).get("counts") or {}
    return f"""# N3 20260605 Action-Confirmation Metric Contract

Status: {contract.get("contract_result")}

```text
projection_run_id={contract.get("projection_run_id")}
trigger_execute_run_id={contract.get("trigger_execute_run_id")}
source_realtime_projection_run_id={contract.get("source_realtime_projection_run_id")}
expected_metric_rows stock/index/board/total={rows.get("stock")}/{rows.get("index")}/{rows.get("board")}/{rows.get("total")}
ready_backed stock/index/board/total={ready.get("stock")}/{ready.get("index")}/{ready.get("board")}/{ready.get("total")}
not_ready_policy=pending_market_data
not_ready_backed stock/index/board/total={pending.get("stock")}/{pending.get("index")}/{pending.get("board")}/{pending.get("total")}
writes_outbox=false
allowed_write_tables={contract.get("allowed_write_tables")}
rollback_sql={contract.get("rollback", {}).get("rollback_sql_path")}
```
"""


def format_20260605_coverage_repair_contract_markdown(contract: Mapping[str, Any]) -> str:
    rows = contract.get("expected_rows") or {}
    summary = contract.get("repair_summary") or {}
    repaired = summary.get("repaired_total_coverage") or {}
    remaining = summary.get("remaining_excluded") or {}
    return f"""# N3 Action-Confirmation Metric Coverage Policy Repair Contract

Status: {contract.get("contract_result")}

```text
projection_run_id={contract.get("projection_run_id")}
original_metric_run_id={contract.get("original_metric_run_id")}
coverage_policy_version={contract.get("coverage_policy_version")}
eligibility_source={(contract.get("coverage_policy") or {}).get("eligibility_source")}
repair_additive_rows stock/index/board/total={rows.get("stock")}/{rows.get("index")}/{rows.get("board")}/{rows.get("total")}
repaired_total_coverage stock/index/board/total={repaired.get("stock")}/{repaired.get("index")}/{repaired.get("board")}/{repaired.get("total")}
remaining_excluded stock/index/board/total={remaining.get("stock")}/{remaining.get("index")}/{remaining.get("board")}/{remaining.get("total")}
remaining_excluded_reason={summary.get("remaining_excluded_reason")}
duplicate_vs_original_metric={summary.get("duplicate_vs_original_metric")}
duplicate_inside_repair_payload={summary.get("duplicate_inside_repair_payload")}
writes_outbox=false
allowed_write_tables={contract.get("allowed_write_tables")}
rollback_sql={contract.get("rollback", {}).get("rollback_sql_path")}
```
"""


def format_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    rows = preflight.get("expected_rows") or {}
    quality = preflight.get("quality") or {}
    return f"""# N3 Action-Confirmation Metric 20260603 Materialization Preflight

Status: {preflight.get("result")}

```text
projection_run_id={preflight.get("projection_run_id")}
expected_rows stock/index/board/total={rows.get("stock")}/{rows.get("index")}/{rows.get("board")}/{rows.get("total")}
P0/P1/P2={quality.get("P0")}/{quality.get("P1")}/{quality.get("P2")}
blockers={preflight.get("blockers")}
writes_outbox=false
```
"""


def format_20260605_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    rows = preflight.get("expected_rows") or {}
    quality = preflight.get("quality") or {}
    return f"""# N3 20260605 Action-Confirmation Metric Preflight

Status: {preflight.get("result")}

```text
projection_run_id={preflight.get("projection_run_id")}
expected_metric_rows stock/index/board/total={rows.get("stock")}/{rows.get("index")}/{rows.get("board")}/{rows.get("total")}
P0/P1/P2={quality.get("P0")}/{quality.get("P1")}/{quality.get("P2")}
blockers={preflight.get("blockers")}
writes_outbox=false
consumes_outbox=false
```
"""


def format_20260605_coverage_repair_preflight_markdown(
    preflight: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> str:
    rows = preflight.get("expected_rows") or {}
    quality = preflight.get("quality") or {}
    summary = contract.get("repair_summary") or {}
    return f"""# N3 Action-Confirmation Metric Coverage Policy Repair Preflight

Status: {preflight.get("result")}

```text
projection_run_id={preflight.get("projection_run_id")}
repair_additive_rows stock/index/board/total={rows.get("stock")}/{rows.get("index")}/{rows.get("board")}/{rows.get("total")}
original_metric_rows={summary.get("original_metric_rows")}
remaining_excluded_reason={summary.get("remaining_excluded_reason")}
P0/P1/P2={quality.get("P0")}/{quality.get("P1")}/{quality.get("P2")}
blockers={preflight.get("blockers")}
writes_outbox=false
consumes_outbox=false
```
"""


def format_20260605_dry_run_markdown(report: Mapping[str, Any]) -> str:
    rows = report.get("expected_metric_rows") or {}
    quality = report.get("quality") or {}
    ready = ((report.get("ready_backed_policy") or {}).get("counts") or {})
    pending = ((report.get("not_ready_policy") or {}).get("counts") or {})
    return f"""# N3 20260605 Action-Confirmation Metric Dry Run

Status: {report.get("result")}

```text
projection_run_id={report.get("projection_run_id")}
metric_rows stock/index/board/total={rows.get("stock")}/{rows.get("index")}/{rows.get("board")}/{rows.get("total")}
ready_backed stock/index/board/total={ready.get("stock")}/{ready.get("index")}/{ready.get("board")}/{ready.get("total")}
not_ready_policy=pending_market_data
not_ready_backed stock/index/board/total={pending.get("stock")}/{pending.get("index")}/{pending.get("board")}/{pending.get("total")}
P0/P1/P2={quality.get("P0")}/{quality.get("P1")}/{quality.get("P2")}
writes_database=false
```
"""


def format_20260605_coverage_repair_dry_run_markdown(report: Mapping[str, Any]) -> str:
    rows = report.get("expected_metric_rows") or {}
    quality = report.get("quality") or {}
    proof = report.get("dry_run_proof") or {}
    repaired = proof.get("repaired_total_coverage") or {}
    remaining = proof.get("remaining_excluded") or {}
    return f"""# N3 Action-Confirmation Metric Coverage Policy Repair Dry Run

Status: {report.get("result")}

```text
projection_run_id={report.get("projection_run_id")}
original_metric_run_id={report.get("original_metric_run_id")}
repair_additive_rows stock/index/board/total={rows.get("stock")}/{rows.get("index")}/{rows.get("board")}/{rows.get("total")}
original_metric_rows={proof.get("original_metric_rows")}
n4_matched_universe={proof.get("n4_matched_universe")}
repaired_total_coverage stock/index/board/total={repaired.get("stock")}/{repaired.get("index")}/{repaired.get("board")}/{repaired.get("total")}
remaining_excluded stock/index/board/total={remaining.get("stock")}/{remaining.get("index")}/{remaining.get("board")}/{remaining.get("total")}
remaining_excluded_reason={proof.get("remaining_excluded_reason")}
duplicate_vs_original_metric={proof.get("duplicate_vs_original_metric")}
duplicate_inside_repair_payload={proof.get("duplicate_inside_repair_payload")}
P0/P1/P2={quality.get("P0")}/{quality.get("P1")}/{quality.get("P2")}
writes_database=false
```
"""


def format_execute_report_markdown(report: Mapping[str, Any]) -> str:
    rows = report.get("actual_rows") or {}
    quality = report.get("quality") or {}
    rollback = report.get("rollback") or {}
    return f"""# N3 Action-Confirmation Metric 20260603 Materialization Execute Report

Status: {report.get("result")}

```text
projection_run_id={report.get("projection_run_id")}
rows stock/index/board/total={rows.get("stock", 0)}/{rows.get("index", 0)}/{rows.get("board", 0)}/{rows.get("total", 0)}
metric_ready={report.get("metric_ready")}
P0/P1/P2={quality.get("P0", 0)}/{quality.get("P1", 0)}/{quality.get("P2", 0)}
writes_outbox=false
rollback_safe={rollback.get("rollback_safe")}
```
"""


def blocked_report(
    args: argparse.Namespace,
    blocked_reasons: Sequence[str],
    *,
    payload_validation: Mapping[str, Any] | None = None,
    contract: Mapping[str, Any] | None = None,
    preflight: Mapping[str, Any] | None = None,
    blocked_before_db: bool,
) -> dict[str, Any]:
    projection_run_id = (
        str((contract or {}).get("projection_run_id") or "")
        or str((payload_validation or {}).get("projection_run_id") or "")
        or TARGET_RUN_ID
    )
    return {
        "result": "BLOCKED",
        "layer_role": "N3_market_data",
        "projection_run_id": projection_run_id,
        "blocked_reasons": list(blocked_reasons),
        "payload_path": args.payload_path,
        "contract_path": args.contract_path,
        "payload_validation": dict(payload_validation or {}),
        "contract_summary": {
            "allowed_write_tables": list((contract or {}).get("allowed_write_tables") or ALLOWED_WRITE_TABLES),
            "writes_outbox": (contract or {}).get("writes_outbox", False),
        },
        "preflight": dict(preflight or {}),
        "side_effects": side_effects(writes_database=False),
        "blocked_before_database_write": blocked_before_db,
        "generated_at": utc_now_iso(),
    }


def summary_for_stdout(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "result": report.get("result"),
        "projection_run_id": report.get("projection_run_id"),
        "blocked_reasons": report.get("blocked_reasons", []),
        "rows": report.get("actual_rows") or (report.get("payload_validation") or {}).get("row_counts"),
        "quality": report.get("quality"),
        "writes_database": (report.get("side_effects") or {}).get("writes_database"),
        "writes_outbox": (report.get("side_effects") or {}).get("writes_outbox"),
    }


def payload_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def rows_by_asset_kind(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {asset: [] for asset in ASSET_KINDS}
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind in grouped:
            grouped[asset_kind].append(dict(row))
    return grouped


def count_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"stock": 0, "index": 0, "board": 0, "total": 0}
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind in ASSET_KINDS:
            counts[asset_kind] += 1
            counts["total"] += 1
    return counts


def row_n4_events(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("raw_json")
    if not isinstance(raw, Mapping):
        return []
    events = raw.get("n4_trigger_matched_events")
    if not isinstance(events, list):
        return []
    return [dict(event) for event in events if isinstance(event, Mapping)]


def identities_by_asset(identities: Iterable[str]) -> dict[str, list[str]]:
    grouped = {asset: [] for asset in ASSET_KINDS}
    for identity in identities:
        asset = identity.split(":", 1)[0]
        if asset in grouped:
            grouped[asset].append(identity)
    return grouped


def filter_snapshot_rows(
    snapshot_rows_by_asset: Mapping[str, list[Mapping[str, Any]]],
    candidate_identities: Mapping[str, list[str]],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for asset_kind in ASSET_KINDS:
        wanted = set(candidate_identities.get(asset_kind) or [])
        output[asset_kind] = [
            dict(row)
            for row in snapshot_rows_by_asset.get(asset_kind, [])
            if str(row.get("identity_key") or "") in wanted
        ]
    return output


def projection_enrichment_table(asset_kind: str) -> str:
    return {
        "stock": "stock_projection_enrichment_v4_metric",
        "index": "index_projection_enrichment_v4_metric",
        "board": "board_projection_enrichment_v4_metric",
    }[asset_kind]


def is_bj_identity(identity_key: str) -> bool:
    return ":BJ:" in identity_key


def count_where(cur: Any, table: str, where_sql: str, params: tuple[Any, ...]) -> int:
    cur.execute(f"SELECT count(*)::bigint AS row_count FROM {table} WHERE {where_sql}", params)
    return int(cur.fetchone()["row_count"])


def checkpoint_refs(cur: Any, run_id: str) -> int:
    cur.execute(
        """
        SELECT count(*)::bigint AS row_count
        FROM common_event_consumer_checkpoint
        WHERE checkpoint_payload::TEXT LIKE %s OR last_event_id LIKE %s
        """,
        (like_ref(run_id), like_ref(run_id)),
    )
    return int(cur.fetchone()["row_count"])


def downstream_refs(cur: Any, run_id: str) -> dict[str, int]:
    result: dict[str, int] = {}
    result["common_trigger_match"] = count_where(cur, "common_trigger_match", "raw_json::TEXT LIKE %s", (like_ref(run_id),))
    result["common_trigger_state"] = safe_count_where(cur, "common_trigger_state", "to_jsonb(common_trigger_state)::TEXT LIKE %s", (like_ref(run_id),))
    result["common_action_event"] = count_where(cur, "common_action_event", "trace_json::TEXT LIKE %s", (like_ref(run_id),))
    for table_name in N6_DOWNSTREAM_REF_TABLES:
        result[table_name] = safe_count_where(
            cur,
            table_name,
            f"to_jsonb({table_name})::TEXT LIKE %s",
            (like_ref(run_id),),
        )
    result["total"] = total_counts_generic(result)
    return result


def safe_count_where(cur: Any, table: str, where_sql: str, params: tuple[Any, ...]) -> int:
    cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table}",))
    if not cur.fetchone()["table_name"]:
        return 0
    return count_where(cur, table, where_sql, params)


def total_counts_generic(values: Mapping[str, int]) -> int:
    return sum(int(value or 0) for key, value in values.items() if key != "total")


def like_ref(value: str) -> str:
    return f"%{value}%"


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def side_effects(*, writes_database: bool) -> dict[str, bool]:
    return {
        "writes_database": writes_database,
        "writes_run_or_quality": writes_database,
        "writes_action_confirmation_metric_rows": writes_database,
        "writes_projection_enrichment_v4": False,
        "writes_realtime_projection_metric": False,
        "writes_snapshot_or_minute": False,
        "writes_outbox": False,
        "consumes_outbox": False,
        "writes_inbox_or_checkpoint": False,
        "enters_n4_n5_n6": False,
        "worker_started": False,
        "old_system_touched": False,
        "real_trade": False,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
