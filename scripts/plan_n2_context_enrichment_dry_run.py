#!/usr/bin/env python3
"""Build N2 context enrichment schema/contract/dry-run artifacts.

This gate is read-only. It reads an existing N2 condition run and previews the
JSON context that N4 v4 may localize later. It never writes condition tables,
event tables, downstream layers, or starts workers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.context_enrichment import (
    build_context_enrichment_contract,
    build_context_enrichment_snapshot,
    summarize_context_enrichment_rows,
)
from ashare_v3.condition.pool import required_periods_for_condition_key

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:
    from scripts.check_condition_source_ready import DEFAULT_DSN


DEFAULT_CONTRACT_JSON = "docs/N2_context_enrichment_contract.json"
DEFAULT_CONTRACT_MD = "docs/N2_CONTEXT_ENRICHMENT_CONTRACT.md"
DEFAULT_REPORT_JSON = "docs/N2_context_enrichment_schema_contract_dry_run_report.json"
DEFAULT_REPORT_MD = "docs/N2_CONTEXT_ENRICHMENT_SCHEMA_CONTRACT_DRY_RUN_REPORT.md"

CONTEXT_TABLES = {
    "basis": {
        "stock": {"table": "stock_condition_basis", "identity_column": "stock_identity_key", "source_id_column": "stock_condition_basis_id"},
        "index": {"table": "index_condition_basis", "identity_column": "index_identity_key", "source_id_column": "index_condition_basis_id"},
        "board": {"table": "board_condition_basis", "identity_column": "board_identity_key", "source_id_column": "board_condition_basis_id"},
    },
    "scope": {
        "stock": {"table": "stock_minute_target_scope", "identity_column": "stock_identity_key", "source_id_column": "stock_minute_target_scope_id"},
        "index": {"table": "index_minute_target_scope", "identity_column": "index_identity_key", "source_id_column": "index_minute_target_scope_id"},
        "board": {"table": "board_minute_target_scope", "identity_column": "board_identity_key", "source_id_column": "board_minute_target_scope_id"},
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan N2 context enrichment contract/dry-run.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", default="", help="Existing N2 run_id to inspect. Defaults to latest active.")
    parser.add_argument("--for-trade-date", default="", help="Optional for_trade_date guard for refresh artifacts.")
    parser.add_argument("--context-source", choices=sorted(CONTEXT_TABLES), default="basis")
    parser.add_argument("--expected-context-candidates", type=int, default=0)
    parser.add_argument("--contract-json-path", default=DEFAULT_CONTRACT_JSON)
    parser.add_argument("--contract-report-path", default=DEFAULT_CONTRACT_MD)
    parser.add_argument("--dry-run-json-path", default=DEFAULT_REPORT_JSON)
    parser.add_argument("--dry-run-report-path", default=DEFAULT_REPORT_MD)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    contract = build_context_enrichment_contract()
    report = build_report(
        args.dsn,
        args.run_id,
        contract,
        context_source=args.context_source,
        for_trade_date=args.for_trade_date,
        expected_context_candidates=args.expected_context_candidates,
    )
    write_json(Path(args.contract_json_path), contract)
    write_text(Path(args.contract_report_path), format_contract_markdown(contract))
    write_json(Path(args.dry_run_json_path), report)
    write_text(Path(args.dry_run_report_path), format_report_markdown(report))
    summary = {
        "status": report.get("refresh_result") or report["gate_result"],
        "run_id": report.get("source_run", {}).get("run_id"),
        "rows": report.get("rows"),
        "P0": report["quality"]["P0"],
        "P1": report["quality"]["P1"],
        "P2": report["quality"]["P2"],
        "contract_json": args.contract_json_path,
        "dry_run_json": args.dry_run_json_path,
        "writes_performed": False,
        "will_execute_sql": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else format_summary(summary))
    return 0 if report["gate_result"] == "DRY_RUN_PASS" else 2


def build_report(dsn: str, requested_run_id: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    return build_report(
        dsn,
        requested_run_id,
        contract,
        context_source="basis",
        for_trade_date="",
        expected_context_candidates=0,
    )


def build_report(
    dsn: str,
    requested_run_id: str,
    contract: Mapping[str, Any],
    *,
    context_source: str,
    for_trade_date: str,
    expected_context_candidates: int,
) -> dict[str, Any]:
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn:
        run = fetch_condition_run(conn, requested_run_id)
        if run is None:
            return blocked_report(contract, "active_condition_run_missing", requested_run_id)
        if for_trade_date and str(run.get("for_trade_date") or "") != for_trade_date:
            report = blocked_report(contract, "for_trade_date_mismatch", requested_run_id)
            report["source_run"] = run
            report["expected_for_trade_date"] = for_trade_date
            return report
        rows_by_domain = {
            domain: fetch_enriched_context_rows(conn, spec, run, for_trade_date=for_trade_date)
            for domain, spec in context_table_specs(context_source).items()
        }
    summary = summarize_context_enrichment_rows(rows_by_domain)
    refresh_summary = build_context_refresh_summary(
        rows_by_domain,
        expected_context_candidates=expected_context_candidates,
    )
    baseline_summary = summarize_period_baseline(rows_by_domain)
    quality = build_quality(summary, baseline_summary)
    if refresh_summary["context_candidate_mismatch"]:
        quality["P0"] += 1
    if int(refresh_summary.get("required_period_baseline_missing_rows") or 0):
        quality["P0"] += 1
    return {
        "gate_result": "DRY_RUN_PASS" if quality["P0"] == 0 else "DRY_RUN_BLOCKED",
        "refresh_result": "REFRESH_PASS" if quality["P0"] == 0 else "BLOCKED",
        "gate": "N2_CONTEXT_ENRICHMENT_SCHEMA_CONTRACT_DRY_RUN_GATE",
        "layer_role": "N2_condition",
        "source_run": run,
        "context_source": context_source,
        "expected_context_candidates": expected_context_candidates,
        "contract": contract,
        "rows": summary["rows"],
        "refresh_summary": refresh_summary,
        "coverage": summary["coverage"],
        "baseline_summary": baseline_summary,
        "full_prerequisite_quality_status_counts": summary["full_prerequisite_quality_status_counts"],
        "hint_prerequisite_quality_status_counts": summary["hint_prerequisite_quality_status_counts"],
        "quality": quality,
        "sample_rows": sample_rows(rows_by_domain),
        "implementation_gate": {
            "allowed": quality["P0"] == 0,
            "next_gate": "N2_CONTEXT_ENRICHMENT_IMPLEMENTATION_GATE",
            "reason": "JSON context contract is dry-run ready; physical columns are not required for this gate.",
        },
        "boundary_proof": {
            "writes_performed": False,
            "will_execute_sql": False,
            "database_write_scope": [],
            "outbox_consumed": False,
            "worker_started": False,
            "downstream_layers_entered": False,
            "market_data_pulled": False,
            "old_system_touched": False,
        },
    }


def context_table_specs(context_source: str) -> dict[str, dict[str, str]]:
    if context_source not in CONTEXT_TABLES:
        raise ValueError(f"unsupported context_source: {context_source!r}")
    return CONTEXT_TABLES[context_source]


def fetch_condition_run(conn: psycopg.Connection[dict[str, Any]], requested_run_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        if requested_run_id:
            cur.execute(
                """
                SELECT run_id, source_trade_date, for_trade_date, prev_trade_date, status, created_at
                FROM common_condition_run
                WHERE run_id = %s
                """,
                (requested_run_id,),
            )
        else:
            cur.execute(
                """
                SELECT run_id, source_trade_date, for_trade_date, prev_trade_date, status, created_at
                FROM common_condition_run
                WHERE status IN ('passed_active', 'passed')
                ORDER BY
                  CASE status WHEN 'passed_active' THEN 0 ELSE 1 END,
                  source_trade_date DESC,
                  created_at DESC
                LIMIT 1
                """
            )
        row = cur.fetchone()
    return dict(row) if row else None


def fetch_enriched_context_rows(
    conn: psycopg.Connection[dict[str, Any]],
    spec: Mapping[str, str],
    run: Mapping[str, Any],
    *,
    for_trade_date: str,
) -> list[dict[str, Any]]:
    run_id = str(run["run_id"])
    source_trade_date = str(run.get("source_trade_date") or "")
    table = str(spec["table"])
    identity_column = str(spec["identity_column"])
    source_id_column = str(spec.get("source_id_column") or "")
    params: list[Any] = [run_id]
    date_clause = ""
    if for_trade_date:
        date_clause = " AND for_trade_date = %s"
        params.append(for_trade_date)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT *
            FROM {table}
            WHERE run_id = %s
            {date_clause}
            ORDER BY 1
            """,
            tuple(params),
        )
        rows = cur.fetchall()
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = build_context_enrichment_snapshot(
            row,
            baseline_source_trade_date=source_trade_date,
            baseline_source_version=str(row.get("source_version") or ""),
        )
        item["identity_key"] = (
            row.get(identity_column)
            or row.get("identity_key")
            or row.get("stock_identity_key")
            or row.get("index_identity_key")
            or row.get("board_identity_key")
        )
        item["condition_basis_run_id"] = run_id
        item["context_source_table"] = table
        item["source_row_id"] = row.get(source_id_column) if source_id_column else None
        item["condition_key"] = row.get("condition_key")
        item["source_trade_date"] = row.get("source_trade_date") or run.get("source_trade_date")
        item["direction"] = row.get("direction")
        item["allowed_signal_types"] = list(row.get("allowed_signal_types") or [])
        enriched.append(item)
    return enriched


def build_context_refresh_summary(
    rows_by_domain: Mapping[str, list[Mapping[str, Any]]],
    *,
    expected_context_candidates: int,
) -> dict[str, Any]:
    all_rows = [row for rows in rows_by_domain.values() for row in rows]
    context_row_count = len(all_rows)
    return {
        "context_row_count": context_row_count,
        "context_enrichment_rows": sum(1 for row in all_rows if row.get("context_enrichment_hash")),
        "previous_transition_rows": sum(1 for row in all_rows if all_periods_have(row, "previous_transition")),
        "trigger_previous_entity_bound_rows": sum(
            1
            for row in all_rows
            if all_periods_have(row, "trigger_previous_entity_high")
            and all_periods_have(row, "trigger_previous_entity_low")
        ),
        "trigger_previous_amount_baseline_rows": sum(1 for row in all_rows if all_periods_have(row, "trigger_previous_amount_baseline")),
        "previous_entity_bound_rows": sum(1 for row in all_rows if all_periods_have(row, "previous_entity_high") and all_periods_have(row, "previous_entity_low")),
        "previous_amount_baseline_rows": sum(1 for row in all_rows if all_periods_have(row, "previous_amount_baseline")),
        "period_baseline_ready_distribution": period_baseline_ready_distribution(all_rows),
        "required_period_baseline_missing_rows": required_period_baseline_missing_rows(all_rows),
        "FULL_trace_rows": sum(1 for row in all_rows if row.get("FULL_prerequisite_trace_json")),
        "HINT_trace_rows": sum(1 for row in all_rows if row.get("HINT_prerequisite_trace_json")),
        "freshness_status_counts": freshness_status_counts(all_rows),
        "expected_context_candidates": expected_context_candidates,
        "context_candidate_mismatch": (
            0 if not expected_context_candidates or context_row_count == expected_context_candidates else 1
        ),
    }


def required_period_baseline_missing_rows(rows: list[Mapping[str, Any]]) -> int:
    missing = 0
    for row in rows:
        condition_key = str(row.get("condition_key") or "")
        required_periods = required_periods_for_condition_key(condition_key)
        if any(not period_ready_for_enrichment(row, period) for period in required_periods):
            missing += 1
    return missing


def period_ready_for_enrichment(row: Mapping[str, Any], period: str) -> bool:
    periods = ((row.get("period_trigger_baseline_json") or {}).get("periods") or {})
    entry = periods.get(period) if isinstance(periods, Mapping) else {}
    if not isinstance(entry, Mapping):
        return False
    if all(
        entry.get(field) not in (None, "")
        for field in (
            "trigger_previous_entity_high",
            "trigger_previous_entity_low",
            "trigger_previous_amount_baseline",
            "baseline_source_trade_date",
        )
    ):
        return True
    if "period_baseline_ready" in entry:
        return bool(entry.get("period_baseline_ready"))
    return all(
        entry.get(field) not in (None, "")
        for field in ("previous_entity_high", "previous_entity_low", "previous_amount_baseline")
    )


def all_periods_have(row: Mapping[str, Any], field: str) -> bool:
    periods = ((row.get("period_trigger_baseline_json") or {}).get("periods") or {})
    if not isinstance(periods, Mapping):
        return False
    for period in ("Y", "Q", "M", "W", "D"):
        entry = periods.get(period)
        if not isinstance(entry, Mapping) or entry.get(field) in (None, ""):
            return False
    return True


def period_baseline_ready_distribution(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    distribution = {"all_ready": 0, "partial_or_not_ready": 0}
    for row in rows:
        periods = ((row.get("period_trigger_baseline_json") or {}).get("periods") or {})
        if isinstance(periods, Mapping) and all(
            isinstance(periods.get(period), Mapping) and bool(periods[period].get("period_baseline_ready"))
            for period in ("Y", "Q", "M", "W", "D")
        ):
            distribution["all_ready"] += 1
        else:
            distribution["partial_or_not_ready"] += 1
    return distribution


def freshness_status_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        context = (row.get("period_trigger_baseline_json") or {}).get("context_enrichment") or {}
        status = str(context.get("freshness_status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def summarize_period_baseline(rows_by_domain: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    total_periods = 0
    ready_periods = 0
    freshness_counts: dict[str, int] = {}
    previous_transition_missing = 0
    previous_amount_baseline_missing = 0
    trigger_previous_entity_bound_missing = 0
    trigger_previous_amount_baseline_missing = 0
    for rows in rows_by_domain.values():
        for row in rows:
            periods = ((row.get("period_trigger_baseline_json") or {}).get("periods") or {})
            if not isinstance(periods, Mapping):
                continue
            for period in ("Y", "Q", "M", "W", "D"):
                entry = periods.get(period) if isinstance(periods.get(period), Mapping) else {}
                total_periods += 1
                if bool(entry.get("period_baseline_ready")):
                    ready_periods += 1
                if entry.get("previous_transition") in (None, ""):
                    previous_transition_missing += 1
                if entry.get("previous_amount_baseline") in (None, ""):
                    previous_amount_baseline_missing += 1
                if entry.get("trigger_previous_entity_high") in (None, "") or entry.get("trigger_previous_entity_low") in (None, ""):
                    trigger_previous_entity_bound_missing += 1
                if entry.get("trigger_previous_amount_baseline") in (None, ""):
                    trigger_previous_amount_baseline_missing += 1
                freshness = str(entry.get("freshness_status") or "unknown")
                freshness_counts[freshness] = freshness_counts.get(freshness, 0) + 1
    return {
        "total_period_entries": total_periods,
        "period_baseline_ready_entries": ready_periods,
        "period_baseline_not_ready_entries": total_periods - ready_periods,
        "previous_transition_missing": previous_transition_missing,
        "previous_amount_baseline_missing": previous_amount_baseline_missing,
        "trigger_previous_entity_bound_missing": trigger_previous_entity_bound_missing,
        "trigger_previous_amount_baseline_missing": trigger_previous_amount_baseline_missing,
        "freshness_status_counts": freshness_counts,
    }


def build_quality(summary: Mapping[str, Any], baseline_summary: Mapping[str, Any]) -> dict[str, int]:
    p0 = 0
    p1 = 0
    p2 = 0
    coverage = summary.get("coverage") or {}
    if any(int(coverage.get(key) or 0) for key in ("context_hash_missing", "amount_chain_missing", "formula_hash_missing", "full_trace_missing", "hint_trace_missing")):
        p0 += 1
    if int(baseline_summary.get("previous_transition_missing") or 0):
        p0 += 1
    if int(baseline_summary.get("trigger_previous_entity_bound_missing") or 0):
        p0 += 1
    if int(baseline_summary.get("trigger_previous_amount_baseline_missing") or 0):
        p0 += 1
    if int(baseline_summary.get("previous_amount_baseline_missing") or 0):
        p1 += 1
    if int(baseline_summary.get("period_baseline_not_ready_entries") or 0):
        p2 += 1
    return {"P0": p0, "P1": p1, "P2": p2}


def sample_rows(rows_by_domain: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    samples: dict[str, list[dict[str, Any]]] = {}
    for domain, rows in rows_by_domain.items():
        samples[domain] = [
            {
                "identity_key": row.get("identity_key"),
                "context_enrichment_hash": row.get("context_enrichment_hash"),
                "FULL_prerequisite_quality_status": row.get("FULL_prerequisite_quality_status"),
                "HINT_prerequisite_quality_status": row.get("HINT_prerequisite_quality_status"),
            }
            for row in rows[:3]
        ]
    return samples


def blocked_report(contract: Mapping[str, Any], reason: str, requested_run_id: str) -> dict[str, Any]:
    return {
        "gate_result": "DRY_RUN_BLOCKED",
        "gate": "N2_CONTEXT_ENRICHMENT_SCHEMA_CONTRACT_DRY_RUN_GATE",
        "layer_role": "N2_condition",
        "contract": contract,
        "source_run": {"requested_run_id": requested_run_id},
        "rows": {"stock": 0, "index": 0, "board": 0},
        "coverage": {},
        "baseline_summary": {},
        "quality": {"P0": 1, "P1": 0, "P2": 0},
        "blocked_reasons": [reason],
        "boundary_proof": {
            "writes_performed": False,
            "will_execute_sql": False,
            "outbox_consumed": False,
            "worker_started": False,
            "downstream_layers_entered": False,
        },
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def format_contract_markdown(contract: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N2 Context Enrichment Contract",
            "",
            f"- contract_version: {contract['contract_version']}",
            f"- downstream_consumer: {contract['downstream_consumer']}",
            f"- physical_columns_required: {contract['physical_columns_required']}",
            f"- schema_migration_required: {contract['schema_migration_required']}",
            f"- n4_can_recompute_context: {contract['n4_can_recompute_context']}",
            "- JSON extension paths:",
            *[f"  - {path}" for path in contract["json_extension_paths"]],
            "",
            "FULL policy: BUY:FULL / SELL:FULL remain trace-only and blocked for N4 v4 execute matcher.",
            "HINT policy: BUY_HINT / SELL_HINT keep N2 prerequisite trace; N4 must confirm standardized N3 projection.",
        ]
    ) + "\n"


def format_report_markdown(report: Mapping[str, Any]) -> str:
    source = report.get("source_run") or {}
    baseline = report.get("baseline_summary") or {}
    coverage = report.get("coverage") or {}
    quality = report.get("quality") or {}
    return "\n".join(
        [
            "# N2 Context Enrichment Schema/Contract Dry-Run Report",
            "",
            f"- gate_result: {report['gate_result']}",
            f"- refresh_result: {report.get('refresh_result')}",
            f"- run_id: {source.get('run_id')}",
            f"- source_trade_date: {source.get('source_trade_date')}",
            f"- for_trade_date: {source.get('for_trade_date')}",
            f"- rows: {json.dumps(report.get('rows') or {}, ensure_ascii=False, sort_keys=True)}",
            f"- context_source: {report.get('context_source')}",
            f"- expected_context_candidates: {report.get('expected_context_candidates')}",
            f"- P0/P1/P2: {quality.get('P0')}/{quality.get('P1')}/{quality.get('P2')}",
            "",
            "## Refresh Summary",
            f"- context_row_count: {(report.get('refresh_summary') or {}).get('context_row_count')}",
            f"- context_enrichment_rows: {(report.get('refresh_summary') or {}).get('context_enrichment_rows')}",
            f"- previous_transition_rows: {(report.get('refresh_summary') or {}).get('previous_transition_rows')}",
            f"- trigger_previous_entity_bound_rows: {(report.get('refresh_summary') or {}).get('trigger_previous_entity_bound_rows')}",
            f"- trigger_previous_amount_baseline_rows: {(report.get('refresh_summary') or {}).get('trigger_previous_amount_baseline_rows')}",
            f"- previous_entity_bound_rows: {(report.get('refresh_summary') or {}).get('previous_entity_bound_rows')}",
            f"- previous_amount_baseline_rows: {(report.get('refresh_summary') or {}).get('previous_amount_baseline_rows')}",
            f"- period_baseline_ready_distribution: {json.dumps((report.get('refresh_summary') or {}).get('period_baseline_ready_distribution') or {}, ensure_ascii=False, sort_keys=True)}",
            f"- required_period_baseline_missing_rows: {(report.get('refresh_summary') or {}).get('required_period_baseline_missing_rows')}",
            f"- FULL_trace_rows: {(report.get('refresh_summary') or {}).get('FULL_trace_rows')}",
            f"- HINT_trace_rows: {(report.get('refresh_summary') or {}).get('HINT_trace_rows')}",
            "",
            "## Coverage",
            f"- context_hash_missing: {coverage.get('context_hash_missing')}",
            f"- amount_chain_missing: {coverage.get('amount_chain_missing')}",
            f"- formula_hash_missing: {coverage.get('formula_hash_missing')}",
            f"- full_trace_missing: {coverage.get('full_trace_missing')}",
            f"- hint_trace_missing: {coverage.get('hint_trace_missing')}",
            f"- previous_transition_missing: {baseline.get('previous_transition_missing')}",
            f"- trigger_previous_entity_bound_missing: {baseline.get('trigger_previous_entity_bound_missing')}",
            f"- trigger_previous_amount_baseline_missing: {baseline.get('trigger_previous_amount_baseline_missing')}",
            f"- previous_amount_baseline_missing: {baseline.get('previous_amount_baseline_missing')}",
            f"- period_baseline_not_ready_entries: {baseline.get('period_baseline_not_ready_entries')}",
            "",
            "## Boundary",
            "- writes_performed: false",
            "- will_execute_sql: false",
            "- N3/N4/N5/N6 implementation: not entered",
            "- outbox consumption: false",
            "- worker_started: false",
            "",
            "## Next Gate",
            f"- implementation_allowed: {(report.get('implementation_gate') or {}).get('allowed')}",
            f"- next_gate: {(report.get('implementation_gate') or {}).get('next_gate')}",
        ]
    ) + "\n"


def format_summary(summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "N2 context enrichment dry-run",
            f"  status={summary['status']}",
            f"  run_id={summary.get('run_id')}",
            f"  rows={summary.get('rows')}",
            f"  P0/P1/P2={summary['P0']}/{summary['P1']}/{summary['P2']}",
            f"  contract_json={summary['contract_json']}",
            f"  dry_run_json={summary['dry_run_json']}",
            "  writes_performed=false will_execute_sql=false",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
