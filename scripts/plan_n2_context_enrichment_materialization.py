#!/usr/bin/env python3
"""Plan row-level N2 context enrichment materialization artifacts.

This gate is read-only. It turns the existing N2 scope context enrichment into
row-level JSONL payloads that a later N2-owned execute gate may persist for N4.
It never writes database rows, consumes outbox, starts workers, or enters N3+.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ashare_v3.condition.context_materialization import (
    MATERIALIZATION_POLICY,
    MATERIALIZATION_POLICY_HASH,
    MATERIALIZATION_SPEC_VERSION,
    build_execute_command_candidate,
    build_materialization_payload_rows,
    build_materialization_rollback_sql,
    materialization_run_column,
    materialization_table_plan,
    summarize_materialization_payload_rows,
    validate_execute_flags,
    write_payload_jsonl,
)
from scripts.plan_n2_context_enrichment_dry_run import (
    build_context_refresh_summary,
    context_table_specs,
    fetch_condition_run,
    fetch_enriched_context_rows,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:
    from scripts.check_condition_source_ready import DEFAULT_DSN


DEFAULT_SOURCE_CONDITION_RUN_ID = "condition_layer_20260602_source_20260602_v1"
DEFAULT_FOR_TRADE_DATE = "20260603"
DEFAULT_TARGET_RUN_ID = "condition_context_enrichment_v4_20260603_condition_layer_20260602_source_20260602_v1"
DEFAULT_EXPECTED_CONTEXT_ROWS = 5222
DEFAULT_PAYLOAD_PATH = "docs/N2_20260603_context_enrichment_row_level_payload.jsonl"
DEFAULT_CONTRACT_JSON = "docs/N2_20260603_context_enrichment_row_level_materialization_contract.json"
DEFAULT_CONTRACT_MD = "docs/N2_20260603_CONTEXT_ENRICHMENT_ROW_LEVEL_MATERIALIZATION_CONTRACT.md"
DEFAULT_PREFLIGHT_JSON = "docs/N2_20260603_context_enrichment_row_level_materialization_preflight.json"
DEFAULT_PREFLIGHT_MD = "docs/N2_20260603_CONTEXT_ENRICHMENT_ROW_LEVEL_MATERIALIZATION_PREFLIGHT.md"
DEFAULT_REPORT_JSON = "docs/N2_20260603_context_enrichment_row_level_materialization_dry_run_report.json"
DEFAULT_REPORT_MD = "docs/N2_20260603_CONTEXT_ENRICHMENT_ROW_LEVEL_MATERIALIZATION_DRY_RUN_REPORT.md"
DEFAULT_ROLLBACK_SQL = "sql/N2_20260603_context_enrichment_row_level_materialization_rollback.sql"


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan N2 context enrichment row-level materialization.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--source-condition-run-id", default=DEFAULT_SOURCE_CONDITION_RUN_ID)
    parser.add_argument("--for-trade-date", default=DEFAULT_FOR_TRADE_DATE)
    parser.add_argument("--target-run-id", default=DEFAULT_TARGET_RUN_ID)
    parser.add_argument("--expected-context-rows", type=int, default=DEFAULT_EXPECTED_CONTEXT_ROWS)
    parser.add_argument("--payload-path", default=DEFAULT_PAYLOAD_PATH)
    parser.add_argument("--contract-json-path", default=DEFAULT_CONTRACT_JSON)
    parser.add_argument("--contract-report-path", default=DEFAULT_CONTRACT_MD)
    parser.add_argument("--preflight-json-path", default=DEFAULT_PREFLIGHT_JSON)
    parser.add_argument("--preflight-report-path", default=DEFAULT_PREFLIGHT_MD)
    parser.add_argument("--dry-run-json-path", default=DEFAULT_REPORT_JSON)
    parser.add_argument("--dry-run-report-path", default=DEFAULT_REPORT_MD)
    parser.add_argument("--rollback-sql-path", default=DEFAULT_ROLLBACK_SQL)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_materialization_report(
        args.dsn,
        source_condition_run_id=args.source_condition_run_id,
        target_run_id=args.target_run_id,
        for_trade_date=args.for_trade_date,
        expected_context_rows=args.expected_context_rows,
        payload_path=args.payload_path,
        contract_path=args.contract_json_path,
        rollback_sql_path=args.rollback_sql_path,
    )
    contract = report["contract"]
    preflight = report["preflight"]
    rollback_sql = build_materialization_rollback_sql(
        args.target_run_id,
        report["db_materialization_plan"]["future_execute_write_tables"],
    )

    write_json(Path(args.contract_json_path), contract)
    write_text(Path(args.contract_report_path), format_contract_markdown(contract))
    write_json(Path(args.preflight_json_path), preflight)
    write_text(Path(args.preflight_report_path), format_preflight_markdown(preflight))
    write_json(Path(args.dry_run_json_path), report)
    write_text(Path(args.dry_run_report_path), format_report_markdown(report))
    write_text(Path(args.rollback_sql_path), rollback_sql)

    summary = {
        "status": report["materialization_result"],
        "source_condition_run_id": args.source_condition_run_id,
        "target_run_id": args.target_run_id,
        "rows": report["target_rows"],
        "P0": report["quality"]["P0"],
        "P1": report["quality"]["P1"],
        "P2": report["quality"]["P2"],
        "payload_path": args.payload_path,
        "rollback_sql_path": args.rollback_sql_path,
        "allow_enter_execute_final_gate": report["allow_enter_execute_final_gate"],
        "writes_performed": False,
        "will_execute_sql": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else format_summary(summary))
    return 0 if report["materialization_result"] == "MATERIALIZATION_DRY_RUN_PASS" else 2


def build_materialization_report(
    dsn: str,
    *,
    source_condition_run_id: str,
    target_run_id: str,
    for_trade_date: str,
    expected_context_rows: int,
    payload_path: str,
    contract_path: str,
    rollback_sql_path: str,
) -> dict[str, Any]:
    table_plan = materialization_table_plan()
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn:
        run = fetch_condition_run(conn, source_condition_run_id)
        if run is None:
            return blocked_report(
                source_condition_run_id=source_condition_run_id,
                target_run_id=target_run_id,
                for_trade_date=for_trade_date,
                reason="source_condition_run_missing",
                table_plan=table_plan,
                payload_path=payload_path,
                contract_path=contract_path,
                rollback_sql_path=rollback_sql_path,
            )
        rows_by_domain = {
            domain: fetch_enriched_context_rows(conn, spec, run, for_trade_date=for_trade_date)
            for domain, spec in context_table_specs("scope").items()
        }
        db_plan = build_db_materialization_plan(conn, target_run_id, table_plan)

    payload_rows = build_materialization_payload_rows(
        rows_by_domain,
        source_condition_run_id=source_condition_run_id,
        target_run_id=target_run_id,
        for_trade_date=for_trade_date,
    )
    payload_count = write_payload_jsonl(payload_path, payload_rows)
    materialization_summary = summarize_materialization_payload_rows(
        payload_rows,
        expected_context_rows=expected_context_rows,
    )
    refresh_summary = build_context_refresh_summary(rows_by_domain, expected_context_candidates=expected_context_rows)
    quality = build_quality(materialization_summary)
    materialization_result = "MATERIALIZATION_DRY_RUN_PASS" if quality["P0"] == 0 else "BLOCKED"
    preflight = build_preflight(
        source_run=run,
        source_condition_run_id=source_condition_run_id,
        target_run_id=target_run_id,
        for_trade_date=for_trade_date,
        expected_context_rows=expected_context_rows,
        db_plan=db_plan,
        quality=quality,
        payload_path=payload_path,
        contract_path=contract_path,
        rollback_sql_path=rollback_sql_path,
    )
    contract = build_contract(
        source_condition_run_id=source_condition_run_id,
        target_run_id=target_run_id,
        for_trade_date=for_trade_date,
        expected_context_rows=expected_context_rows,
        table_plan=table_plan,
        payload_path=payload_path,
        contract_path=contract_path,
        rollback_sql_path=rollback_sql_path,
    )
    allow_enter_execute_final_gate = (
        materialization_result == "MATERIALIZATION_DRY_RUN_PASS"
        and bool(preflight["execute_final_gate_ready"])
    )
    return {
        "materialization_result": materialization_result,
        "gate": "N2_CONTEXT_ENRICHMENT_ROW_LEVEL_MATERIALIZATION_GATE",
        "layer_role": "N2_condition",
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "target_run_id": target_run_id,
        "spec_version": MATERIALIZATION_SPEC_VERSION,
        "policy_hash": MATERIALIZATION_POLICY_HASH,
        "source_run": run,
        "target_rows": materialization_summary["rows"],
        "payload_artifact": {
            "path": payload_path,
            "format": "jsonl",
            "row_count": payload_count,
        },
        "materialization_summary": materialization_summary,
        "refresh_summary": refresh_summary,
        "db_materialization_plan": db_plan,
        "allowed_write_tables": {
            "current_gate": table_plan["current_gate_write_tables"],
            "future_execute_gate": table_plan["future_execute_write_tables"],
        },
        "rollback_sql_path": rollback_sql_path,
        "rollback_hard_fail_guard": {
            "event_infra": ["common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint"],
            "downstream_refs": [
                "common_market_data_run",
                "common_trigger_run",
                "common_trigger_state",
                "common_trigger_match",
                "common_action_run",
                "common_action_event",
                "user_projection_run",
                "user_signal_projection",
                "user_signal_card",
                "user_notification_queue",
            ],
            "runtime_flags": ["downstream_layers_touched", "worker_started"],
            "guard_before_first_delete": True,
            "delete_before_guard": False,
        },
        "quality": quality,
        "contract": contract,
        "preflight": preflight,
        "allow_enter_execute_final_gate": allow_enter_execute_final_gate,
        "boundary_proof": {
            "writes_performed": False,
            "will_execute_sql": False,
            "database_write_scope": [],
            "downstream_layers_entered": False,
            "outbox_consumed": False,
            "worker_started": False,
            "market_data_pulled": False,
            "old_system_touched": False,
        },
    }


def build_db_materialization_plan(
    conn: psycopg.Connection[dict[str, Any]],
    target_run_id: str,
    table_plan: Mapping[str, Any],
) -> dict[str, Any]:
    tables = list(table_plan["future_execute_write_tables"])
    existing_tables = fetch_existing_tables(conn, tables)
    missing_tables = [table for table in tables if table not in existing_tables]
    target_run_rows: dict[str, int | None] = {}
    for table in tables:
        if table not in existing_tables:
            target_run_rows[table] = None
            continue
        column = materialization_run_column(table)
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS count FROM {table} WHERE {column} = %s", (target_run_id,))
            target_run_rows[table] = int(cur.fetchone()["count"])
    schema_ready = not missing_tables
    return {
        "current_gate_writes_allowed": False,
        "schema_ready": schema_ready,
        "missing_tables": missing_tables,
        "future_execute_write_tables": tables,
        "target_run_rows": target_run_rows,
        "target_run_baseline_zero": schema_ready and all((target_run_rows.get(table) or 0) == 0 for table in tables),
        "requires_schema_migration_before_execute": not schema_ready,
        "execute_blocked_reasons": [] if schema_ready else ["materialization_tables_missing"],
    }


def fetch_existing_tables(conn: psycopg.Connection[dict[str, Any]], tables: list[str]) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (tables,),
        )
        return {str(row["table_name"]) for row in cur.fetchall()}


def build_quality(summary: Mapping[str, Any]) -> dict[str, int]:
    total = int((summary.get("rows") or {}).get("total") or 0)
    p0 = 0
    p1 = 0
    p2 = 0
    if int(summary.get("context_row_mismatch") or 0):
        p0 += 1
    if int(summary.get("context_enrichment_hash_rows") or 0) != total:
        p0 += 1
    if int(summary.get("previous_transition_rows") or 0) != total:
        p0 += 1
    if int(summary.get("FULL_trace_rows") or 0) != total:
        p0 += 1
    if int(summary.get("HINT_trace_rows") or 0) != total:
        p0 += 1
    if int(summary.get("previous_amount_baseline_rows") or 0) != total:
        p1 += 1
    distribution = summary.get("period_baseline_ready_distribution") or {}
    if int(distribution.get("partial_or_not_ready") or 0):
        p2 += 1
    return {"P0": p0, "P1": p1, "P2": p2}


def build_contract(
    *,
    source_condition_run_id: str,
    target_run_id: str,
    for_trade_date: str,
    expected_context_rows: int,
    table_plan: Mapping[str, Any],
    payload_path: str,
    contract_path: str,
    rollback_sql_path: str,
) -> dict[str, Any]:
    execute_command_candidate = build_execute_command_candidate(
        payload_path=payload_path,
        contract_path=contract_path,
    )
    return {
        "gate": "N2_CONTEXT_ENRICHMENT_ROW_LEVEL_MATERIALIZATION_GATE",
        "layer_role": "N2_condition",
        "contract_result": "CONTRACT_READY",
        "source_condition_run_id": source_condition_run_id,
        "target_run_id": target_run_id,
        "for_trade_date": for_trade_date,
        "expected_context_rows": expected_context_rows,
        "spec_version": MATERIALIZATION_SPEC_VERSION,
        "policy": MATERIALIZATION_POLICY,
        "policy_hash": MATERIALIZATION_POLICY_HASH,
        "row_level_source": "stock/index/board_minute_target_scope",
        "payload_format": "jsonl",
        "payload_path": payload_path,
        "contract_path": contract_path,
        "execute_command_candidate": execute_command_candidate,
        "execute_flag_requirements": {
            "requires_execute": True,
            "requires_user_confirmed": True,
            "missing_execute_gate": validate_execute_flags(execute=False, user_confirmed=True),
            "missing_user_confirmed_gate": validate_execute_flags(execute=True, user_confirmed=False),
            "both_required_gate": validate_execute_flags(execute=True, user_confirmed=True),
            "blocked_before_database_write": True,
        },
        "allowed_write_tables": {
            "current_gate": table_plan["current_gate_write_tables"],
            "future_execute_gate": table_plan["future_execute_write_tables"],
        },
        "rollback_sql_path": rollback_sql_path,
        "forbidden_scopes": table_plan["forbidden_write_scopes"],
        "n4_can_recompute_context": False,
        "n3_lineage_auto_switch": False,
    }


def build_preflight(
    *,
    source_run: Mapping[str, Any],
    source_condition_run_id: str,
    target_run_id: str,
    for_trade_date: str,
    expected_context_rows: int,
    db_plan: Mapping[str, Any],
    quality: Mapping[str, int],
    payload_path: str,
    contract_path: str,
    rollback_sql_path: str,
) -> dict[str, Any]:
    execute_ready = (
        int(quality.get("P0") or 0) == 0
        and bool(db_plan.get("schema_ready"))
        and bool(db_plan.get("target_run_baseline_zero"))
    )
    blocked_reasons = []
    if int(quality.get("P0") or 0):
        blocked_reasons.append("P0_quality_blocker")
    blocked_reasons.extend(list(db_plan.get("execute_blocked_reasons") or []))
    if db_plan.get("schema_ready") and not db_plan.get("target_run_baseline_zero"):
        blocked_reasons.append("target_run_rows_exist")
    return {
        "preflight_result": "PASS" if execute_ready else "BLOCKED",
        "execute_final_gate_ready": execute_ready,
        "blocked_reasons": blocked_reasons,
        "source_condition_run_id": source_condition_run_id,
        "source_condition_run_status": source_run.get("status"),
        "target_run_id": target_run_id,
        "for_trade_date": for_trade_date,
        "expected_context_rows": expected_context_rows,
        "spec_version": MATERIALIZATION_SPEC_VERSION,
        "policy_hash": MATERIALIZATION_POLICY_HASH,
        "execute_command_candidate": build_execute_command_candidate(
            payload_path=payload_path,
            contract_path=contract_path,
        ),
        "execute_flag_requirements": {
            "requires_execute": True,
            "requires_user_confirmed": True,
            "missing_execute_gate": validate_execute_flags(execute=False, user_confirmed=True),
            "missing_user_confirmed_gate": validate_execute_flags(execute=True, user_confirmed=False),
            "blocked_before_database_write": True,
        },
        "db_materialization_plan": db_plan,
        "quality": dict(quality),
        "rollback_sql_path": rollback_sql_path,
        "writes_performed": False,
        "will_execute_sql": False,
    }


def blocked_report(
    *,
    source_condition_run_id: str,
    target_run_id: str,
    for_trade_date: str,
    reason: str,
    table_plan: Mapping[str, Any],
    payload_path: str,
    contract_path: str,
    rollback_sql_path: str,
) -> dict[str, Any]:
    contract = build_contract(
        source_condition_run_id=source_condition_run_id,
        target_run_id=target_run_id,
        for_trade_date=for_trade_date,
        expected_context_rows=0,
        table_plan=table_plan,
        payload_path=payload_path,
        contract_path=contract_path,
        rollback_sql_path=rollback_sql_path,
    )
    preflight = {
        "preflight_result": "BLOCKED",
        "execute_final_gate_ready": False,
        "blocked_reasons": [reason],
        "source_condition_run_id": source_condition_run_id,
        "target_run_id": target_run_id,
        "for_trade_date": for_trade_date,
        "execute_command_candidate": build_execute_command_candidate(
            payload_path=payload_path,
            contract_path=contract_path,
        ),
        "execute_flag_requirements": {
            "requires_execute": True,
            "requires_user_confirmed": True,
            "missing_execute_gate": validate_execute_flags(execute=False, user_confirmed=True),
            "missing_user_confirmed_gate": validate_execute_flags(execute=True, user_confirmed=False),
            "blocked_before_database_write": True,
        },
        "quality": {"P0": 1, "P1": 0, "P2": 0},
        "writes_performed": False,
        "will_execute_sql": False,
    }
    return {
        "materialization_result": "BLOCKED",
        "gate": "N2_CONTEXT_ENRICHMENT_ROW_LEVEL_MATERIALIZATION_GATE",
        "layer_role": "N2_condition",
        "source_condition_run_id": source_condition_run_id,
        "for_trade_date": for_trade_date,
        "target_run_id": target_run_id,
        "target_rows": {"stock": 0, "index": 0, "board": 0, "total": 0},
        "payload_artifact": {"path": payload_path, "format": "jsonl", "row_count": 0},
        "quality": {"P0": 1, "P1": 0, "P2": 0},
        "blocked_reasons": [reason],
        "contract": contract,
        "preflight": preflight,
        "allow_enter_execute_final_gate": False,
        "rollback_sql_path": rollback_sql_path,
        "boundary_proof": {
            "writes_performed": False,
            "will_execute_sql": False,
            "downstream_layers_entered": False,
            "outbox_consumed": False,
            "worker_started": False,
        },
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def format_contract_markdown(contract: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N2 Context Enrichment Row-Level Materialization Contract",
            "",
            f"- contract_result: {contract['contract_result']}",
            f"- source_condition_run_id: {contract['source_condition_run_id']}",
            f"- target_run_id: {contract['target_run_id']}",
            f"- for_trade_date: {contract['for_trade_date']}",
            f"- spec_version: {contract['spec_version']}",
            f"- policy_hash: {contract['policy_hash']}",
            f"- expected_context_rows: {contract['expected_context_rows']}",
            f"- row_level_source: {contract['row_level_source']}",
            f"- payload_format: {contract['payload_format']}",
            f"- payload_path: {contract['payload_path']}",
            f"- contract_path: {contract['contract_path']}",
            "",
            "## Execute Command Candidate",
            "```bash",
            contract["execute_command_candidate"],
            "```",
            f"- requires_execute: {contract['execute_flag_requirements']['requires_execute']}",
            f"- requires_user_confirmed: {contract['execute_flag_requirements']['requires_user_confirmed']}",
            f"- missing_execute_gate: {json.dumps(contract['execute_flag_requirements']['missing_execute_gate'], ensure_ascii=False, sort_keys=True)}",
            f"- missing_user_confirmed_gate: {json.dumps(contract['execute_flag_requirements']['missing_user_confirmed_gate'], ensure_ascii=False, sort_keys=True)}",
            f"- blocked_before_database_write: {contract['execute_flag_requirements']['blocked_before_database_write']}",
            "",
            "## Write Scope",
            f"- current_gate: {json.dumps(contract['allowed_write_tables']['current_gate'], ensure_ascii=False)}",
            f"- future_execute_gate: {json.dumps(contract['allowed_write_tables']['future_execute_gate'], ensure_ascii=False)}",
            "",
            "## Boundary",
            "- N3/N4/N5/N6: not entered",
            "- outbox/inbox/checkpoint: not written or consumed",
            "- n4_can_recompute_context: false",
            "- n3_lineage_auto_switch: false",
            f"- rollback_sql_path: {contract['rollback_sql_path']}",
        ]
    ) + "\n"


def format_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    db_plan = preflight.get("db_materialization_plan") or {}
    return "\n".join(
        [
            "# N2 Context Enrichment Row-Level Materialization Preflight",
            "",
            f"- preflight_result: {preflight['preflight_result']}",
            f"- execute_final_gate_ready: {preflight['execute_final_gate_ready']}",
            f"- blocked_reasons: {json.dumps(preflight.get('blocked_reasons') or [], ensure_ascii=False)}",
            f"- source_condition_run_id: {preflight['source_condition_run_id']}",
            f"- target_run_id: {preflight['target_run_id']}",
            f"- P0/P1/P2: {preflight['quality']['P0']}/{preflight['quality']['P1']}/{preflight['quality']['P2']}",
            "",
            "## DB Materialization Plan",
            f"- schema_ready: {db_plan.get('schema_ready')}",
            f"- missing_tables: {json.dumps(db_plan.get('missing_tables') or [], ensure_ascii=False)}",
            f"- target_run_baseline_zero: {db_plan.get('target_run_baseline_zero')}",
            f"- requires_schema_migration_before_execute: {db_plan.get('requires_schema_migration_before_execute')}",
            f"- future_execute_write_tables: {json.dumps(db_plan.get('future_execute_write_tables') or [], ensure_ascii=False)}",
            "",
            "## Execute Flag Gate",
            "```bash",
            preflight["execute_command_candidate"],
            "```",
            f"- requires_execute: {preflight['execute_flag_requirements']['requires_execute']}",
            f"- requires_user_confirmed: {preflight['execute_flag_requirements']['requires_user_confirmed']}",
            f"- missing_execute_gate: {json.dumps(preflight['execute_flag_requirements']['missing_execute_gate'], ensure_ascii=False, sort_keys=True)}",
            f"- missing_user_confirmed_gate: {json.dumps(preflight['execute_flag_requirements']['missing_user_confirmed_gate'], ensure_ascii=False, sort_keys=True)}",
            f"- blocked_before_database_write: {preflight['execute_flag_requirements']['blocked_before_database_write']}",
            "",
            "## Boundary",
            "- writes_performed: false",
            "- will_execute_sql: false",
            "- worker_started: false",
        ]
    ) + "\n"


def format_report_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("materialization_summary") or {}
    refresh = report.get("refresh_summary") or {}
    quality = report.get("quality") or {}
    rollback_guard = report.get("rollback_hard_fail_guard") or {}
    contract = report.get("contract") or {}
    return "\n".join(
        [
            "# N2 Context Enrichment Row-Level Materialization Dry-Run Report",
            "",
            f"- materialization_result: {report['materialization_result']}",
            f"- source_condition_run_id: {report['source_condition_run_id']}",
            f"- target_run_id: {report['target_run_id']}",
            f"- for_trade_date: {report['for_trade_date']}",
            f"- spec_version: {report['spec_version']}",
            f"- policy_hash: {report['policy_hash']}",
            f"- target_rows: {json.dumps(report['target_rows'], ensure_ascii=False, sort_keys=True)}",
            f"- payload_artifact: {report['payload_artifact']['path']}",
            f"- P0/P1/P2: {quality.get('P0')}/{quality.get('P1')}/{quality.get('P2')}",
            "",
            "## Coverage",
            f"- previous_transition_rows: {summary.get('previous_transition_rows')}",
            f"- previous_entity_bound_rows: {summary.get('previous_entity_bound_rows')}",
            f"- previous_amount_baseline_rows: {summary.get('previous_amount_baseline_rows')}",
            f"- context_enrichment_hash_rows: {summary.get('context_enrichment_hash_rows')}",
            f"- FULL_trace_rows: {summary.get('FULL_trace_rows')}",
            f"- HINT_trace_rows: {summary.get('HINT_trace_rows')}",
            f"- period_baseline_ready_distribution: {json.dumps(summary.get('period_baseline_ready_distribution') or {}, ensure_ascii=False, sort_keys=True)}",
            f"- required_period_baseline_missing_rows: {refresh.get('required_period_baseline_missing_rows')}",
            "",
            "## DB Materialization Plan",
            f"- current_gate_write_tables: {json.dumps(report['allowed_write_tables']['current_gate'], ensure_ascii=False)}",
            f"- future_execute_write_tables: {json.dumps(report['allowed_write_tables']['future_execute_gate'], ensure_ascii=False)}",
            f"- rollback_sql_path: {report['rollback_sql_path']}",
            f"- execute_final_gate_ready: {report['allow_enter_execute_final_gate']}",
            "",
            "## Execute Gate",
            "```bash",
            str(contract.get("execute_command_candidate") or ""),
            "```",
            f"- missing_execute_gate: {json.dumps((contract.get('execute_flag_requirements') or {}).get('missing_execute_gate') or {}, ensure_ascii=False, sort_keys=True)}",
            f"- missing_user_confirmed_gate: {json.dumps((contract.get('execute_flag_requirements') or {}).get('missing_user_confirmed_gate') or {}, ensure_ascii=False, sort_keys=True)}",
            "",
            "## Rollback Hard-Fail Guard",
            f"- event_infra: {json.dumps(rollback_guard.get('event_infra') or [], ensure_ascii=False)}",
            f"- downstream_refs: {json.dumps(rollback_guard.get('downstream_refs') or [], ensure_ascii=False)}",
            f"- runtime_flags: {json.dumps(rollback_guard.get('runtime_flags') or [], ensure_ascii=False)}",
            f"- guard_before_first_delete: {rollback_guard.get('guard_before_first_delete')}",
            f"- delete_before_guard: {rollback_guard.get('delete_before_guard')}",
            "",
            "## Boundary",
            "- writes_performed: false",
            "- will_execute_sql: false",
            "- N3/N4/N5/N6: not entered",
            "- outbox_consumed: false",
            "- worker_started: false",
        ]
    ) + "\n"


def format_summary(summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "N2 context enrichment row-level materialization",
            f"  status={summary['status']}",
            f"  source_condition_run_id={summary['source_condition_run_id']}",
            f"  target_run_id={summary['target_run_id']}",
            f"  rows={summary['rows']}",
            f"  P0/P1/P2={summary['P0']}/{summary['P1']}/{summary['P2']}",
            f"  payload_path={summary['payload_path']}",
            f"  rollback_sql_path={summary['rollback_sql_path']}",
            f"  allow_enter_execute_final_gate={summary['allow_enter_execute_final_gate']}",
            "  writes_performed=false will_execute_sql=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
