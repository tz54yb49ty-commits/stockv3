#!/usr/bin/env python3
"""Run N2 context enrichment row-level materialization.

This command is intentionally guarded: database writes require both
``--execute`` and ``--user-confirmed``. Missing either flag returns BLOCKED
before opening a database connection.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ashare_v3.condition.context_materialization import (
    MATERIALIZATION_TABLES,
    materialization_run_column,
    validate_execute_flags,
)

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:
    from scripts.check_condition_source_ready import DEFAULT_DSN


DEFAULT_REPORT_PATH = "docs/N2_20260603_context_enrichment_row_level_materialization_execute_report.json"
ALLOWED_WRITE_TABLES = list(MATERIALIZATION_TABLES)


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    report = run(args)
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary_for_stdout(report), ensure_ascii=False, indent=2, default=str))
    return 0 if report["execute_result"] == "EXECUTED" else 2


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute N2 context enrichment row-level materialization.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--payload-path", required=True)
    parser.add_argument("--contract-path", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--operator", default="codex")
    parser.add_argument("--confirmation-note", default="")
    parser.add_argument("--report-path", default=DEFAULT_REPORT_PATH)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    flag_gate = validate_execute_flags(execute=bool(args.execute), user_confirmed=bool(args.user_confirmed))
    if flag_gate["gate_result"] != "PASS":
        return blocked_report(args, flag_gate["blocked_reasons"])

    contract = read_json(Path(args.contract_path))
    payload_rows = read_payload_jsonl(Path(args.payload_path))
    target_run_id = str(contract["target_run_id"])
    source_condition_run_id = str(contract["source_condition_run_id"])
    row_counts = count_rows_by_asset(payload_rows)
    expected_rows = int(contract.get("expected_context_rows") or 0)
    if expected_rows and row_counts["total"] != expected_rows:
        return blocked_report(args, ["payload_row_count_mismatch"], contract=contract, row_counts=row_counts)

    with psycopg.connect(args.dsn, row_factory=dict_row) as conn:
        with conn.transaction():
            preflight = execute_preflight(conn, target_run_id)
            if preflight["blocked_reasons"]:
                raise RuntimeError(f"execute blocked: {preflight['blocked_reasons']}")
            source_run = fetch_source_condition_run(conn, source_condition_run_id)
            if source_run is None:
                raise RuntimeError(f"source condition run missing: {source_condition_run_id}")
            insert_run_row(conn, contract, source_run, row_counts, args)
            insert_payload_rows(conn, payload_rows)

    return {
        "execute_result": "EXECUTED",
        "layer_role": "N2_condition",
        "target_run_id": target_run_id,
        "source_condition_run_id": source_condition_run_id,
        "row_counts": row_counts,
        "allowed_write_tables": ALLOWED_WRITE_TABLES,
        "forbidden_scopes": [
            "condition_basis",
            "condition_pool",
            "minute_target_scope",
            "condition_display_basis",
            "common_event_outbox",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
            "N3/N4/N5/N6",
            "worker",
        ],
        "writes_performed": True,
        "common_event_outbox_written": False,
        "downstream_layers_entered": False,
        "worker_started": False,
    }


def blocked_report(
    args: argparse.Namespace,
    blocked_reasons: Sequence[str],
    *,
    contract: Mapping[str, Any] | None = None,
    row_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "execute_result": "BLOCKED",
        "layer_role": "N2_condition",
        "blocked_reasons": list(blocked_reasons),
        "payload_path": args.payload_path,
        "contract_path": args.contract_path,
        "target_run_id": (contract or {}).get("target_run_id"),
        "row_counts": dict(row_counts or {}),
        "allowed_write_tables": ALLOWED_WRITE_TABLES,
        "writes_performed": False,
        "will_execute_sql": False,
        "blocked_before_database_write": True,
    }


def execute_preflight(conn: psycopg.Connection[dict[str, Any]], target_run_id: str) -> dict[str, Any]:
    target_rows: dict[str, int] = {}
    for table in ALLOWED_WRITE_TABLES:
        column = materialization_run_column(table)
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) AS count FROM {table} WHERE {column} = %s", (target_run_id,))
            target_rows[table] = int(cur.fetchone()["count"])
    blocked_reasons = ["target_run_rows_exist"] if any(target_rows.values()) else []
    return {"target_rows": target_rows, "blocked_reasons": blocked_reasons}


def fetch_source_condition_run(conn: psycopg.Connection[dict[str, Any]], run_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT run_id, source_trade_date, for_trade_date, prev_trade_date, status
            FROM common_condition_run
            WHERE run_id = %s
            """,
            (run_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def insert_run_row(
    conn: psycopg.Connection[dict[str, Any]],
    contract: Mapping[str, Any],
    source_run: Mapping[str, Any],
    row_counts: Mapping[str, int],
    args: argparse.Namespace,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO common_condition_context_enrichment_run (
              run_id, source_condition_run_id, source_trade_date, for_trade_date, prev_trade_date,
              spec_version, policy_hash, policy_json, materialization_status,
              expected_context_rows, stock_rows, index_rows, board_rows, total_rows,
              p0_count, p1_count, p2_count, payload_artifact_path, payload_artifact_format,
              rollback_sql_path, report_json_path, operator, confirmation_note, raw_json
            )
            VALUES (
              %(run_id)s, %(source_condition_run_id)s, %(source_trade_date)s, %(for_trade_date)s, %(prev_trade_date)s,
              %(spec_version)s, %(policy_hash)s, %(policy_json)s, 'passed',
              %(expected_context_rows)s, %(stock_rows)s, %(index_rows)s, %(board_rows)s, %(total_rows)s,
              0, 0, 0, %(payload_artifact_path)s, 'jsonl',
              %(rollback_sql_path)s, %(report_json_path)s, %(operator)s, %(confirmation_note)s, %(raw_json)s
            )
            """,
            {
                "run_id": contract["target_run_id"],
                "source_condition_run_id": contract["source_condition_run_id"],
                "source_trade_date": source_run.get("source_trade_date"),
                "for_trade_date": contract["for_trade_date"],
                "prev_trade_date": source_run.get("prev_trade_date"),
                "spec_version": contract["spec_version"],
                "policy_hash": contract["policy_hash"],
                "policy_json": Jsonb(contract.get("policy") or {}),
                "expected_context_rows": int(contract.get("expected_context_rows") or row_counts["total"]),
                "stock_rows": row_counts["stock"],
                "index_rows": row_counts["index"],
                "board_rows": row_counts["board"],
                "total_rows": row_counts["total"],
                "payload_artifact_path": args.payload_path,
                "rollback_sql_path": contract.get("rollback_sql_path"),
                "report_json_path": args.report_path,
                "operator": args.operator,
                "confirmation_note": args.confirmation_note,
                "raw_json": Jsonb(
                    {
                        "downstream_layers_touched": False,
                        "worker_started": False,
                        "common_event_outbox_written": False,
                        "allowed_write_tables": ALLOWED_WRITE_TABLES,
                    }
                ),
            },
        )


def insert_payload_rows(conn: psycopg.Connection[dict[str, Any]], rows: Sequence[Mapping[str, Any]]) -> None:
    for asset_kind in ("stock", "index", "board"):
        table = f"{asset_kind}_condition_context_enrichment"
        identity_column = f"{asset_kind}_identity_key"
        domain_rows = [row for row in rows if row.get("asset_kind") == asset_kind]
        if not domain_rows:
            continue
        with conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {table} (
                  materialization_run_id, source_condition_run_id, for_trade_date, source_trade_date,
                  spec_version, policy_hash, {identity_column}, condition_key, direction,
                  allowed_signal_types, source_scope_table, source_minute_target_scope_id,
                  context_materialization_row_key, context_enrichment_version, context_enrichment_hash,
                  period_trigger_baseline_json, trigger_amount_chain_baseline_json,
                  trigger_amount_chain_formula_hash, FULL_prerequisite_trace_json,
                  FULL_prerequisite_quality_status, HINT_prerequisite_trace_json,
                  HINT_prerequisite_quality_status, freshness_status, period_baseline_ready_json,
                  payload_json
                )
                VALUES (
                  %(materialization_run_id)s, %(source_condition_run_id)s, %(for_trade_date)s, %(source_trade_date)s,
                  %(spec_version)s, %(policy_hash)s, %(identity_key)s, %(condition_key)s, %(direction)s,
                  %(allowed_signal_types)s, %(source_scope_table)s, %(source_scope_id)s,
                  %(context_materialization_row_key)s, %(context_enrichment_version)s, %(context_enrichment_hash)s,
                  %(period_trigger_baseline_json)s, %(trigger_amount_chain_baseline_json)s,
                  %(trigger_amount_chain_formula_hash)s, %(FULL_prerequisite_trace_json)s,
                  %(FULL_prerequisite_quality_status)s, %(HINT_prerequisite_trace_json)s,
                  %(HINT_prerequisite_quality_status)s, %(freshness_status)s, %(period_baseline_ready_json)s,
                  %(payload_json)s
                )
                """,
                [row_insert_params(row) for row in domain_rows],
            )


def row_insert_params(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json") if isinstance(row.get("payload_json"), Mapping) else {}
    baseline = payload.get("period_trigger_baseline_json") if isinstance(payload.get("period_trigger_baseline_json"), Mapping) else {}
    context = baseline.get("context_enrichment") if isinstance(baseline.get("context_enrichment"), Mapping) else {}
    return {
        "materialization_run_id": row.get("materialization_run_id"),
        "source_condition_run_id": row.get("source_condition_run_id"),
        "for_trade_date": row.get("for_trade_date"),
        "source_trade_date": row.get("source_trade_date"),
        "spec_version": row.get("spec_version"),
        "policy_hash": row.get("policy_hash"),
        "identity_key": row.get("identity_key"),
        "condition_key": row.get("condition_key"),
        "direction": row.get("direction"),
        "allowed_signal_types": list(row.get("allowed_signal_types") or []),
        "source_scope_table": row.get("source_scope_table"),
        "source_scope_id": row.get("source_scope_id"),
        "context_materialization_row_key": row.get("context_materialization_row_key"),
        "context_enrichment_version": payload.get("context_enrichment_version"),
        "context_enrichment_hash": row.get("context_enrichment_hash"),
        "period_trigger_baseline_json": Jsonb(baseline),
        "trigger_amount_chain_baseline_json": Jsonb(payload.get("trigger_amount_chain_baseline_json") or {}),
        "trigger_amount_chain_formula_hash": payload.get("trigger_amount_chain_formula_hash"),
        "FULL_prerequisite_trace_json": Jsonb(payload.get("FULL_prerequisite_trace_json") or {}),
        "FULL_prerequisite_quality_status": payload.get("FULL_prerequisite_quality_status"),
        "HINT_prerequisite_trace_json": Jsonb(payload.get("HINT_prerequisite_trace_json") or {}),
        "HINT_prerequisite_quality_status": payload.get("HINT_prerequisite_quality_status"),
        "freshness_status": context.get("freshness_status") or "unknown",
        "period_baseline_ready_json": Jsonb(period_baseline_ready_json(baseline)),
        "payload_json": Jsonb(payload),
    }


def period_baseline_ready_json(baseline: Mapping[str, Any]) -> dict[str, bool]:
    periods = baseline.get("periods") if isinstance(baseline.get("periods"), Mapping) else {}
    return {
        period: bool((periods.get(period) or {}).get("period_baseline_ready"))
        for period in ("Y", "Q", "M", "W", "D")
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_payload_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def count_rows_by_asset(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"stock": 0, "index": 0, "board": 0, "total": 0}
    for row in rows:
        asset_kind = str(row.get("asset_kind") or "")
        if asset_kind in ("stock", "index", "board"):
            counts[asset_kind] += 1
            counts["total"] += 1
    return counts


def summary_for_stdout(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "execute_result": report.get("execute_result"),
        "target_run_id": report.get("target_run_id"),
        "blocked_reasons": report.get("blocked_reasons", []),
        "row_counts": report.get("row_counts", {}),
        "writes_performed": report.get("writes_performed", False),
        "will_execute_sql": report.get("execute_result") == "EXECUTED",
        "blocked_before_database_write": report.get("blocked_before_database_write", False),
    }


if __name__ == "__main__":
    raise SystemExit(main())
