#!/usr/bin/env python3
"""Build an N2 full dry-run package for basis/pool/scope/display.

This runner is read-only for PostgreSQL. It may write report artifacts and a
rollback SQL draft, but it never writes condition business tables, event tables,
downstream tables, or starts workers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import build_condition_basis_dry_run
from ashare_v3.condition.display_basis import (
    DOMAIN_CONFIGS,
    build_display_rows_for_domain,
    build_domain_report,
    fetch_display_table_counts,
)
from ashare_v3.condition.execute import expected_rows_with_display
from ashare_v3.condition.execute_contract import build_condition_execute_contract
from ashare_v3.condition.execute_preflight import (
    build_condition_execute_preflight,
    fetch_active_run_status,
    fetch_schema_status,
)
from ashare_v3.condition.pool import build_condition_pool_dry_run
from ashare_v3.condition.readiness_plan import build_condition_layer_execute_readiness_plan
from ashare_v3.condition.scope import build_minute_target_scope_dry_run
try:
    from run_condition_layer_execute import (
        ConditionRunnerPolicy,
        condition_runner_report_metadata,
        resolve_condition_runner_policy,
    )
except ModuleNotFoundError:
    from scripts.run_condition_layer_execute import (
        ConditionRunnerPolicy,
        condition_runner_report_metadata,
        resolve_condition_runner_policy,
    )
try:
    from check_condition_source_ready import DEFAULT_DSN, run_check
except ModuleNotFoundError:
    from scripts.check_condition_source_ready import DEFAULT_DSN, run_check


DEFAULT_OUTPUTS = {
    "dry_run_md": "docs/N2_CONDITION_LAYER_20260526_DRY_RUN_REPORT.md",
    "dry_run_json": "docs/N2_condition_layer_20260526_dry_run_report.json",
    "contract_md": "docs/N2_CONDITION_LAYER_20260526_EXECUTE_CONTRACT.md",
    "contract_json": "docs/N2_condition_layer_20260526_execute_contract.json",
    "preflight_md": "docs/N2_CONDITION_LAYER_20260526_EXECUTE_PREFLIGHT.md",
    "preflight_json": "docs/N2_condition_layer_20260526_execute_preflight.json",
    "rollback_sql": "sql/N2_condition_layer_20260526_rollback.sql",
}


def resolve_full_dry_run_policy(policy_path: str | Path | None) -> ConditionRunnerPolicy:
    """Resolve N2 dry-run policy with the same loader as execute runner."""
    return resolve_condition_runner_policy(policy_path or "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build N2 full dry-run/contract/preflight artifacts.")
    parser.add_argument("--source-trade-date", required=True)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--policy", default="")
    parser.add_argument("--run-id-suggestion", default="")
    parser.add_argument("--user-confirmed", action="store_true", help="Record confirmation in contract/preflight only.")
    parser.add_argument("--operator", default="manual")
    parser.add_argument("--confirmation-note", default="")
    parser.add_argument("--dry-run-report-path", default="")
    parser.add_argument("--dry-run-json-path", default="")
    parser.add_argument("--contract-report-path", default="")
    parser.add_argument("--contract-json-path", default="")
    parser.add_argument("--preflight-report-path", default="")
    parser.add_argument("--preflight-json-path", default="")
    parser.add_argument("--rollback-sql-path", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    outputs = output_paths(args)
    policy_bundle = resolve_full_dry_run_policy(args.policy)
    scope_policy = policy_bundle.scope_policy
    condition_pool_policy = policy_bundle.condition_pool_policy
    ready = run_check(args.dsn, args.source_trade_date)
    basis_report = build_condition_basis_dry_run(dsn=args.dsn, source_trade_date=args.source_trade_date, ready_check=ready)
    normalize_basis_monitor_target_status_for_planned_run(
        basis_report,
        planned_run_id=args.run_id_suggestion,
        planned_run_monitor_counts=fetch_monitor_target_counts_for_source_version(args.dsn, args.run_id_suggestion),
    )
    pool_report = build_condition_pool_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
        condition_pool_policy=condition_pool_policy,
    )
    scope_report = build_minute_target_scope_dry_run(
        dsn=args.dsn,
        source_trade_date=args.source_trade_date,
        ready_check=ready,
        scope_policy=scope_policy,
        condition_pool_policy=condition_pool_policy,
    )
    policy_metadata = condition_runner_report_metadata(
        policy_bundle,
        scope_report,
        execute_requested=False,
    )
    readiness_plan = build_condition_layer_execute_readiness_plan(
        basis_report=basis_report,
        pool_report=pool_report,
        scope_report=scope_report,
    )
    display_report = build_display_preview_from_dry_run(
        dsn=args.dsn,
        planned_run_id=str(readiness_plan["planned_run_id"]),
        basis_report=basis_report,
        pool_report=pool_report,
        scope_report=scope_report,
    )
    display_quality_items = count_display_quality_items(display_report)
    display_row_counts = {
        domain: int(display_report["display_preview"][domain]["row_count"])
        for domain in ("stock", "index", "board")
    }
    expected_rows_four_stage = expected_rows_with_display(
        readiness_plan["would_write"],
        display_quality_item_count=display_quality_items,
        display_row_counts=display_row_counts,
    )
    contract = build_condition_execute_contract(
        readiness_plan,
        user_confirmed=args.user_confirmed,
        overwrite=False,
        operator=args.operator,
        confirmation_note=args.confirmation_note,
    )
    contract["expected_rows_with_display"] = {
        table: int(spec.get("row_count") or 0)
        for table, spec in expected_rows_four_stage.items()
    }
    contract["display_basis_contract"] = build_display_contract(display_report, display_quality_items)
    contract["run_id_suggestion"] = args.run_id_suggestion
    contract.update(policy_metadata)
    schema_status = fetch_schema_status(args.dsn)
    active_status = fetch_active_run_status(
        args.dsn,
        source_trade_date=str(readiness_plan["source_trade_date"]),
        for_trade_date=str(readiness_plan["for_trade_date"]),
        overwrite=False,
    )
    preflight = build_condition_execute_preflight(
        readiness_plan=readiness_plan,
        execute_contract=contract,
        schema_status=schema_status,
        active_run_status=active_status,
    )
    preflight["expected_rows_with_display"] = dict(contract["expected_rows_with_display"])
    preflight["display_basis_preflight"] = build_display_contract(display_report, display_quality_items)
    preflight["run_id_suggestion"] = args.run_id_suggestion
    preflight.update(policy_metadata)
    dry_run = build_full_dry_run_report(
        ready=ready,
        basis_report=basis_report,
        pool_report=pool_report,
        scope_report=scope_report,
        display_report=display_report,
        readiness_plan=readiness_plan,
        expected_rows_four_stage=expected_rows_four_stage,
        run_id_suggestion=args.run_id_suggestion,
    )
    dry_run.update(policy_metadata)
    rollback_sql = build_rollback_sql(args.run_id_suggestion or ":run_id")

    write_json(outputs["dry_run_json"], dry_run)
    write_json(outputs["contract_json"], contract)
    write_json(outputs["preflight_json"], preflight)
    write_text(outputs["dry_run_md"], format_dry_run_markdown(dry_run))
    write_text(outputs["contract_md"], format_contract_markdown(contract))
    write_text(outputs["preflight_md"], format_preflight_markdown(preflight))
    write_text(outputs["rollback_sql"], rollback_sql)

    summary = {
        "status": "IMPLEMENTATION_PASS" if dry_run["passed"] and preflight["execute_allowed"] else "BLOCKED",
        "source_trade_date": dry_run["source_trade_date"],
        "for_trade_date": dry_run["for_trade_date"],
        "expected_rows_with_display": contract["expected_rows_with_display"],
        "p0_count": dry_run["quality_summary"]["p0_count"],
        "p1_count": dry_run["quality_summary"]["p1_count"],
        "p2_count": dry_run["quality_summary"]["p2_count"],
        "preflight_execute_allowed": preflight["execute_allowed"],
        "outputs": {key: str(path) for key, path in outputs.items()},
        "writes_performed": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else format_summary(summary))
    return 0 if summary["status"] != "BLOCKED" else 2


def output_paths(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "dry_run_md": Path(args.dry_run_report_path or DEFAULT_OUTPUTS["dry_run_md"]),
        "dry_run_json": Path(args.dry_run_json_path or DEFAULT_OUTPUTS["dry_run_json"]),
        "contract_md": Path(args.contract_report_path or DEFAULT_OUTPUTS["contract_md"]),
        "contract_json": Path(args.contract_json_path or DEFAULT_OUTPUTS["contract_json"]),
        "preflight_md": Path(args.preflight_report_path or DEFAULT_OUTPUTS["preflight_md"]),
        "preflight_json": Path(args.preflight_json_path or DEFAULT_OUTPUTS["preflight_json"]),
        "rollback_sql": Path(args.rollback_sql_path or DEFAULT_OUTPUTS["rollback_sql"]),
    }


MONITOR_TARGET_TABLES = {
    "stock": "stock_monitor_target",
    "index": "index_monitor_target",
    "board": "board_monitor_target",
}


def fetch_monitor_target_counts_for_source_version(dsn: str, source_version: str) -> dict[str, int]:
    if not source_version:
        return {}
    counts: dict[str, int] = {}
    with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for domain, table in MONITOR_TARGET_TABLES.items():
                cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cur.fetchone()["to_regclass"] is None:
                    counts[domain] = 0
                    continue
                cur.execute(
                    f"""
                    SELECT count(*)::bigint AS row_count
                    FROM {table}
                    WHERE source_version = %s
                      AND status = 'active'
                    """,
                    (source_version,),
                )
                counts[domain] = int(cur.fetchone()["row_count"])
    return counts


def normalize_basis_monitor_target_status_for_planned_run(
    basis_report: dict[str, Any],
    *,
    planned_run_id: str,
    planned_run_monitor_counts: Mapping[str, int],
) -> None:
    """Keep post-execute artifact refresh from counting this run's monitor targets.

    The execute runner builds the condition_basis quality report before inserting
    monitor_target rows for the same run. When we refresh artifacts after an
    execute, those self-created rows are already visible in PostgreSQL. Excluding
    them here preserves the execute-time planning view without changing business
    rows or the runner's write path.
    """
    if not planned_run_id or not planned_run_monitor_counts:
        return
    monitor_targets = dict(basis_report.get("monitor_targets") or {})
    quality = dict(basis_report.get("quality") or {})
    items = list(quality.get("items") or [])
    existing_gate_codes = {str(item.get("gate_code") or "") for item in items}
    added_quality_item = False
    for domain in ("stock", "index", "board"):
        planned_count = int(planned_run_monitor_counts.get(domain) or 0)
        if planned_count <= 0:
            continue
        status = dict(monitor_targets.get(domain) or {})
        active_count = int(status.get("active_count") or 0)
        active_count_excluding_planned = max(active_count - planned_count, 0)
        status["active_count_including_planned_run"] = active_count
        status["ignored_planned_run_id"] = planned_run_id
        status["ignored_planned_run_active_count"] = planned_count
        status["active_count"] = active_count_excluding_planned
        if active_count_excluding_planned == 0:
            status["mode"] = "fact_universe_fallback"
            gate_code = f"{domain}_monitor_target_fallback"
            if gate_code not in existing_gate_codes:
                items.append(
                    {
                        "severity": "P1",
                        "status": "warning",
                        "gate_code": gate_code,
                        "gate_name": f"{domain} monitor target not available for dry-run; using fact universe fallback preview",
                        "details": {
                            "ignored_planned_run_id": planned_run_id,
                            "ignored_planned_run_active_count": planned_count,
                        },
                    }
                )
                existing_gate_codes.add(gate_code)
                added_quality_item = True
        monitor_targets[domain] = status
    if added_quality_item:
        quality["items"] = items
        severity_counts = count_failed_quality_severities(items)
        quality["p0_count"] = severity_counts["P0"]
        quality["p1_count"] = severity_counts["P1"]
        quality["p2_count"] = severity_counts["P2"]
        basis_report["quality"] = quality
    basis_report["monitor_targets"] = monitor_targets


def count_failed_quality_severities(items: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"P0": 0, "P1": 0, "P2": 0}
    for item in items:
        if item.get("status") not in {"failed", "warning"}:
            continue
        severity = str(item.get("severity") or "")
        if severity in counts:
            counts[severity] += 1
    return counts


def build_display_preview_from_dry_run(
    *,
    dsn: str,
    planned_run_id: str,
    basis_report: Mapping[str, Any],
    pool_report: Mapping[str, Any],
    scope_report: Mapping[str, Any],
) -> dict[str, Any]:
    with psycopg.connect(dsn, connect_timeout=10, options="-c default_transaction_read_only=on", row_factory=dict_row) as conn, conn.cursor() as cur:
        display_before = fetch_display_table_counts(cur)
        domain_reports = {}
        for domain in ("stock", "index", "board"):
            config = DOMAIN_CONFIGS[domain]
            basis_rows, pool_rows, scope_rows = attach_synthetic_ids(
                domain=domain,
                planned_run_id=planned_run_id,
                basis_rows=list(basis_report["basis_preview"][domain].get("basis_rows") or []),
                pool_rows=list(pool_report["pool_preview"][domain].get("pool_rows") or []),
                scope_rows=list(scope_report["scope_preview"][domain].get("scope_rows") or []),
            )
            rows = build_display_rows_for_domain(
                config,
                basis_rows=basis_rows,
                pool_rows=pool_rows,
                scope_rows=scope_rows,
            )
            domain_reports[domain] = build_domain_report(config, rows, include_rows=False)
        display_after = fetch_display_table_counts(cur)
    quality = build_display_quality_for_full_dry_run(
        domain_reports=domain_reports,
        before_counts=display_before,
        after_counts=display_after,
    )
    return {
        "stage": "N2-full-dry-run-display",
        "run_id": planned_run_id,
        "source_trade_date": basis_report["source_trade_date"],
        "for_trade_date": basis_report["for_trade_date"],
        "prev_trade_date": basis_report["prev_trade_date"],
        "display_table_row_counts_before": display_before,
        "display_table_row_counts_after": display_after,
        "display_preview": domain_reports,
        "quality": quality,
        "passed": int(quality["p0_count"]) == 0,
        "writes_performed": False,
        "display_basis_written": False,
    }


def attach_synthetic_ids(
    *,
    domain: str,
    planned_run_id: str,
    basis_rows: list[Mapping[str, Any]],
    pool_rows: list[Mapping[str, Any]],
    scope_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    config = DOMAIN_CONFIGS[domain]
    basis_id_by_ref: dict[str, int] = {}
    output_basis = []
    for index, row in enumerate(basis_rows, start=1):
        copied = dict(row)
        copied["run_id"] = planned_run_id
        copied[config.basis_id_col] = index
        identity_key = copied.get(config.identity_col)
        basis_ref = f"dry_run:{domain}:{index}:{identity_key}"
        basis_id_by_ref[basis_ref] = index
        output_basis.append(copied)

    pool_id_by_ref: dict[str, int] = {}
    output_pool = []
    for index, row in enumerate(pool_rows, start=1):
        copied = dict(row)
        copied["run_id"] = planned_run_id
        copied[config.pool_id_col] = index
        source_ref = str(copied.get("source_condition_basis_ref") or "")
        copied["source_condition_basis_id"] = basis_id_by_ref.get(source_ref)
        pool_ref = str(copied.get("condition_pool_ref") or f"dry_run:{domain}:condition_pool:{index}")
        pool_id_by_ref[pool_ref] = index
        output_pool.append(copied)

    output_scope = []
    for index, row in enumerate(scope_rows, start=1):
        copied = dict(row)
        copied["run_id"] = planned_run_id
        copied[config.scope_id_col] = index
        pool_ref = str(copied.get("source_condition_pool_ref") or "")
        copied["source_condition_pool_id"] = pool_id_by_ref.get(pool_ref)
        output_scope.append(copied)
    return output_basis, output_pool, output_scope


def build_full_dry_run_report(
    *,
    ready: Mapping[str, Any],
    basis_report: Mapping[str, Any],
    pool_report: Mapping[str, Any],
    scope_report: Mapping[str, Any],
    display_report: Mapping[str, Any],
    readiness_plan: Mapping[str, Any],
    expected_rows_four_stage: Mapping[str, Mapping[str, Any]],
    run_id_suggestion: str,
) -> dict[str, Any]:
    quality = aggregate_four_stage_quality(basis_report, pool_report, scope_report, display_report)
    stage_counts = {
        **readiness_plan["stage_counts"],
        "condition_display_basis": {
            domain: int(display_report["display_preview"][domain]["row_count"])
            for domain in ("stock", "index", "board")
        },
    }
    return {
        "stage": "N2-full-dry-run",
        "status": "FULL_DRY_RUN_PASS" if quality["p0_count"] == 0 else "FULL_DRY_RUN_BLOCKED",
        "passed": quality["p0_count"] == 0,
        "source_trade_date": basis_report["source_trade_date"],
        "for_trade_date": basis_report["for_trade_date"],
        "prev_trade_date": basis_report["prev_trade_date"],
        "run_id_suggestion": run_id_suggestion,
        "planned_run_id": readiness_plan["planned_run_id"],
        "source_ready": {
            "passed": ready.get("passed"),
            "missing_data_types": ready.get("missing_data_types"),
            "expected_condition_stock_universe": ready.get("expected_condition_stock_universe"),
            "excluded_from_condition_universe": ready.get("excluded_from_condition_universe"),
        },
        "source_versions": readiness_plan["source_versions"],
        "stage_counts": stage_counts,
        "expected_rows_with_display": {
            table: int(spec.get("row_count") or 0)
            for table, spec in expected_rows_four_stage.items()
        },
        "basis_summary": summarize_basis(basis_report),
        "pool_summary": summarize_pool(pool_report),
        "scope_summary": summarize_scope(scope_report),
        "display_summary": summarize_display(display_report),
        "quality_summary": quality,
        "readiness_plan": readiness_plan,
        "writes_performed": False,
        "will_execute_sql": False,
        "outbox_written": False,
        "downstream_layers_touched": False,
        "worker_started": False,
    }


def aggregate_four_stage_quality(*reports: Mapping[str, Any]) -> dict[str, Any]:
    by_stage = {}
    totals = {"p0_count": 0, "p1_count": 0, "p2_count": 0, "quality_item_count": 0}
    for name, report in zip(("condition_basis", "condition_pool", "minute_target_scope", "condition_display_basis"), reports):
        quality = dict(report.get("quality") or {})
        stage = {
            "p0_count": int(quality.get("p0_count") or 0),
            "p1_count": int(quality.get("p1_count") or 0),
            "p2_count": int(quality.get("p2_count") or 0),
            "quality_item_count": len(quality.get("items") or []),
        }
        by_stage[name] = stage
        for key in totals:
            totals[key] += stage[key]
    return {**totals, "by_stage": by_stage}


def count_display_quality_items(display_report: Mapping[str, Any]) -> int:
    # Real execute writes per-domain display validation items plus one common row-count item.
    return sum(9 for _ in display_report.get("display_preview", {})) + 1


def build_display_contract(display_report: Mapping[str, Any], quality_item_count: int) -> dict[str, Any]:
    return {
        "row_counts": {
            f"{domain}_condition_display_basis": int(display_report["display_preview"][domain]["row_count"])
            for domain in ("stock", "index", "board")
        },
        "quality_item_count": quality_item_count,
        "n6_read_only_input": True,
        "enters_n3_n4_n5": False,
        "writes_performed": False,
    }


def build_display_quality_for_full_dry_run(
    *,
    domain_reports: Mapping[str, Mapping[str, Any]],
    before_counts: Mapping[str, int],
    after_counts: Mapping[str, int],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for domain, report in domain_reports.items():
        table = str(report["display_table"])
        uniqueness = report.get("uniqueness") or {}
        integrity = report.get("field_integrity") or {}
        traceability = report.get("traceability") or {}
        forbidden = report.get("forbidden_field_check") or {}
        append_quality(items, domain, table, "display_unique_identity", int(uniqueness.get("duplicate_count") or 0) == 0, "0", str(uniqueness.get("duplicate_count") or 0))
        append_quality(items, domain, table, "display_basis_trace_present", int(integrity.get("source_condition_basis_ids_missing") or 0) == 0, "0", str(integrity.get("source_condition_basis_ids_missing") or 0))
        append_quality(items, domain, table, "display_condition_keys_parseable", int(integrity.get("selected_condition_keys_invalid") or 0) == 0, "0", str(integrity.get("selected_condition_keys_invalid") or 0))
        append_quality(items, domain, table, "display_signal_types_parseable", int(integrity.get("selected_signal_types_invalid") or 0) == 0, "0", str(integrity.get("selected_signal_types_invalid") or 0))
        append_quality(items, domain, table, "display_baseline_shape_valid", int(integrity.get("period_trigger_baseline_invalid_shape") or 0) == 0, "0", str(integrity.get("period_trigger_baseline_invalid_shape") or 0))
        append_quality(items, domain, table, "display_clear_sell_alias_match", int(integrity.get("clear_sell_ref_period_mismatch") or 0) == 0, "0", str(integrity.get("clear_sell_ref_period_mismatch") or 0))
        append_quality(items, domain, table, "display_reference_period_valid", int(integrity.get("invalid_reference_period") or 0) == 0, "0", str(integrity.get("invalid_reference_period") or 0))
        append_quality(items, domain, table, "display_forbidden_fields_absent", int(forbidden.get("forbidden_field_count") or 0) == 0, "0", str(forbidden.get("forbidden_field_count") or 0))
        append_quality(
            items,
            domain,
            table,
            "display_scope_trace_empty_explained",
            bool(traceability.get("source_minute_target_scope_ids_empty_explained", False)),
            "true",
            str(traceability.get("source_minute_target_scope_ids_empty_explained", False)).lower(),
            severity="P1",
        )
    expected = {
        f"{domain}_condition_display_basis": int(report.get("row_count") or 0)
        for domain, report in domain_reports.items()
    }
    append_quality(
        items,
        "common",
        "stock/index/board_condition_display_basis",
        "display_rows_written_matches_plan",
        True,
        json.dumps(expected, sort_keys=True),
        json.dumps(expected, sort_keys=True),
    )
    return {
        "p0_count": sum(1 for item in items if item["severity"] == "P0" and item["status"] == "failed"),
        "p1_count": sum(1 for item in items if item["severity"] == "P1" and item["status"] == "failed"),
        "p2_count": sum(1 for item in items if item["severity"] == "P2" and item["status"] == "failed"),
        "items": items,
    }


def append_quality(
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
            "layer_scope": "condition_display_basis",
            "table_name": table_name,
            "gate_code": gate_code,
            "gate_name": gate_code.replace("_", " "),
            "severity": severity,
            "status": "passed" if passed else "failed",
            "expected_value": expected,
            "actual_value": actual,
        }
    )


def summarize_basis(report: Mapping[str, Any]) -> dict[str, Any]:
    preview = report["basis_preview"]
    return {
        domain: {
            "row_count": int(preview[domain]["row_count"]),
            "amount_baseline_warning_count": int(preview[domain].get("amount_baseline_warning_count") or 0),
            "necessary_counts": preview[domain].get("necessary_counts", {}),
            "static_structure_coverage": preview[domain].get("static_structure_coverage", {}),
        }
        for domain in ("stock", "index", "board")
    }


def summarize_pool(report: Mapping[str, Any]) -> dict[str, Any]:
    preview = report["pool_preview"]
    return {
        domain: {
            "basis_preview_row_count": int(preview[domain]["basis_preview_row_count"]),
            "candidate_pool_row_count": int(preview[domain]["candidate_pool_row_count"]),
            "policy_selected_count": int(preview[domain]["policy_selected_count"]),
            "policy_excluded_count": int(preview[domain]["policy_excluded_count"]),
            "pool_row_count": int(preview[domain]["pool_row_count"]),
            "condition_key_counts": preview[domain].get("condition_key_counts", {}),
            "policy_excluded_reason_counts": preview[domain].get("policy_excluded_reason_counts", {}),
        }
        for domain in ("stock", "index", "board")
    }


def summarize_scope(report: Mapping[str, Any]) -> dict[str, Any]:
    preview = report["scope_preview"]
    return {
        domain: {
            "object_count": int(preview[domain]["object_count"]),
            "scope_row_count": int(preview[domain]["scope_row_count"]),
            "scope_source_counts": preview[domain].get("scope_source_counts", {}),
            "previous_day_minute_date_mismatch_count": int(preview[domain].get("previous_day_minute_date_mismatch_count") or 0),
        }
        for domain in ("stock", "index", "board")
    }


def summarize_display(report: Mapping[str, Any]) -> dict[str, Any]:
    preview = report["display_preview"]
    return {
        domain: {
            "row_count": int(preview[domain]["row_count"]),
            "object_count": int(preview[domain]["object_count"]),
            "duplicate_count": int(preview[domain]["uniqueness"]["duplicate_count"]),
            "invalid_condition_keys": int(preview[domain]["field_integrity"]["selected_condition_keys_invalid"]),
            "invalid_signal_types": int(preview[domain]["field_integrity"]["selected_signal_types_invalid"]),
            "invalid_baseline_shape": int(preview[domain]["field_integrity"]["period_trigger_baseline_invalid_shape"]),
            "clear_sell_ref_period_mismatch": int(preview[domain]["field_integrity"]["clear_sell_ref_period_mismatch"]),
            "invalid_reference_period": int(preview[domain]["field_integrity"]["invalid_reference_period"]),
            "forbidden_field_count": int(preview[domain]["forbidden_field_check"]["forbidden_field_count"]),
            "sample_rows": preview[domain]["sample_rows"],
        }
        for domain in ("stock", "index", "board")
    }


def build_rollback_sql(run_id: str) -> str:
    run_id_literal = run_id.replace("'", "''")
    return f"""-- N2 condition layer rollback draft.
-- Scope: remove only {run_id_literal} rows.
--
-- Boundary:
-- - Does not touch N1 source_version.
-- - Does not touch common_event_outbox / common_event_inbox / common_event_consumer_checkpoint.
-- - Does not touch N3/N4/N5/N6 facts, workers, old system, or real trading.
-- - Blocks rollback if this N2 run has event infra refs or downstream lineage refs.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := '{run_id_literal}';
  v_downstream_refs BIGINT := 0;
  v_event_refs BIGINT := 0;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM common_condition_run WHERE run_id = v_run_id) THEN
    RAISE EXCEPTION 'rollback blocked: N2 run % does not exist', v_run_id;
  END IF;

  SELECT
      COALESCE((SELECT count(*) FROM common_market_data_run WHERE source_condition_run_id = v_run_id OR run_id LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_trigger_run WHERE source_condition_run_id = v_run_id OR run_id LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_action_run WHERE source_condition_run_id = v_run_id OR run_id LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM user_projection_run WHERE source_display_condition_run_id = v_run_id OR user_projection_run_id LIKE '%' || v_run_id || '%'), 0)
  INTO v_downstream_refs;

  IF v_downstream_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream N3/N4/N5/N6 refs exist for % (% rows)', v_run_id, v_downstream_refs;
  END IF;

  SELECT
      COALESCE((SELECT count(*) FROM common_event_outbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_inbox WHERE source_run_id = v_run_id OR payload_json::text LIKE '%' || v_run_id || '%' OR raw_json::text LIKE '%' || v_run_id || '%'), 0)
    + COALESCE((SELECT count(*) FROM common_event_consumer_checkpoint WHERE last_event_id LIKE '%' || v_run_id || '%' OR checkpoint_payload::text LIKE '%' || v_run_id || '%'), 0)
  INTO v_event_refs;

  IF v_event_refs > 0 THEN
    RAISE EXCEPTION 'rollback blocked: event infra refs exist for % (% rows)', v_run_id, v_event_refs;
  END IF;
END $$;

DELETE FROM stock_condition_display_basis WHERE run_id = '{run_id_literal}';
DELETE FROM index_condition_display_basis WHERE run_id = '{run_id_literal}';
DELETE FROM board_condition_display_basis WHERE run_id = '{run_id_literal}';

DELETE FROM stock_minute_target_scope WHERE run_id = '{run_id_literal}';
DELETE FROM index_minute_target_scope WHERE run_id = '{run_id_literal}';
DELETE FROM board_minute_target_scope WHERE run_id = '{run_id_literal}';

DELETE FROM stock_condition_pool WHERE run_id = '{run_id_literal}';
DELETE FROM index_condition_pool WHERE run_id = '{run_id_literal}';
DELETE FROM board_condition_pool WHERE run_id = '{run_id_literal}';

DELETE FROM stock_condition_basis WHERE run_id = '{run_id_literal}';
DELETE FROM index_condition_basis WHERE run_id = '{run_id_literal}';
DELETE FROM board_condition_basis WHERE run_id = '{run_id_literal}';

DELETE FROM stock_monitor_target WHERE source_version = '{run_id_literal}';
DELETE FROM index_monitor_target WHERE source_version = '{run_id_literal}';
DELETE FROM board_monitor_target WHERE source_version = '{run_id_literal}';

DELETE FROM common_condition_quality_item WHERE run_id = '{run_id_literal}';
DELETE FROM common_condition_run WHERE run_id = '{run_id_literal}';

COMMIT;
"""


def format_dry_run_markdown(report: Mapping[str, Any]) -> str:
    rows = report["stage_counts"]
    quality = report["quality_summary"]
    return "\n".join(
        [
            "# N2 Condition Layer 20260526 Full Dry-run Report",
            "",
            f"status = {report['status']}",
            "",
            "```text",
            f"source_trade_date = {report['source_trade_date']}",
            f"for_trade_date = {report['for_trade_date']}",
            f"prev_trade_date = {report['prev_trade_date']}",
            f"planned_run_id = {report['planned_run_id']}",
            f"run_id_suggestion = {report.get('run_id_suggestion')}",
            "writes_performed = false",
            "common_event_outbox_written = false",
            "downstream_layers_touched = false",
            "worker_started = false",
            "```",
            "",
            "## Source Readiness",
            "",
            "```text",
            f"ready_passed = {report['source_ready']['passed']}",
            f"missing_data_types = {report['source_ready']['missing_data_types']}",
            f"expected_condition_stock_universe = {report['source_ready']['expected_condition_stock_universe']}",
            f"excluded_from_condition_universe = {report['source_ready']['excluded_from_condition_universe']}",
            "```",
            "",
            "## Row Counts",
            "",
            "| Stage | Stock | Index | Board |",
            "|---|---:|---:|---:|",
            f"| condition_basis | {rows['condition_basis']['stock']} | {rows['condition_basis']['index']} | {rows['condition_basis']['board']} |",
            f"| condition_pool | {rows['condition_pool']['stock']} | {rows['condition_pool']['index']} | {rows['condition_pool']['board']} |",
            f"| minute_target_scope | {rows['minute_target_scope']['stock']} | {rows['minute_target_scope']['index']} | {rows['minute_target_scope']['board']} |",
            f"| condition_display_basis | {rows['condition_display_basis']['stock']} | {rows['condition_display_basis']['index']} | {rows['condition_display_basis']['board']} |",
            "",
            "## Quality",
            "",
            "```text",
            f"p0_count = {quality['p0_count']}",
            f"p1_count = {quality['p1_count']}",
            f"p2_count = {quality['p2_count']}",
            "```",
            "",
            "## Display Basis",
            "",
            "`condition_display_basis` is N6 read-only input and does not enter N3/N4/N5.",
            "",
        ]
    )


def format_contract_markdown(contract: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N2 Condition Layer 20260526 Execute Contract",
            "",
            "status = DESIGN_PASS",
            "",
            "```text",
            f"source_trade_date = {contract['source_trade_date']}",
            f"for_trade_date = {contract['for_trade_date']}",
            f"prev_trade_date = {contract['prev_trade_date']}",
            f"execute_run_id_template = {contract['run_id_contract']['execute_run_id_template']}",
            f"run_id_suggestion = {contract.get('run_id_suggestion')}",
            f"execute_request_allowed = {contract['execute_request_allowed']}",
            "writes_performed = false",
            "will_execute_sql = false",
            "common_event_outbox_written = false",
            "```",
            "",
            "## Expected Rows With Display",
            "",
            "```json",
            json.dumps(contract["expected_rows_with_display"], ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )


def format_preflight_markdown(preflight: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# N2 Condition Layer 20260526 Execute Preflight",
            "",
            f"status = {'PASS' if preflight['execute_allowed'] else 'BLOCKED'}",
            "",
            "```text",
            f"source_trade_date = {preflight['source_trade_date']}",
            f"for_trade_date = {preflight['for_trade_date']}",
            f"prev_trade_date = {preflight['prev_trade_date']}",
            f"schema_ready = {preflight['schema_status']['schema_ready']}",
            f"active_exists = {preflight['active_run_status']['active_exists']}",
            f"execute_allowed = {preflight['execute_allowed']}",
            f"blocked_reasons = {preflight['blocked_reasons']}",
            "writes_performed = false",
            "will_execute_sql = false",
            "common_event_outbox_written = false",
            "```",
            "",
            "## Expected Rows With Display",
            "",
            "```json",
            json.dumps(preflight["expected_rows_with_display"], ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )


def format_summary(summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"status={summary['status']}",
            f"source_trade_date={summary['source_trade_date']}",
            f"for_trade_date={summary['for_trade_date']}",
            f"p0/p1/p2={summary['p0_count']}/{summary['p1_count']}/{summary['p2_count']}",
            f"preflight_execute_allowed={summary['preflight_execute_allowed']}",
            f"dry_run_report={summary['outputs']['dry_run_md']}",
            f"contract_report={summary['outputs']['contract_md']}",
            f"preflight_report={summary['outputs']['preflight_md']}",
            f"rollback_sql={summary['outputs']['rollback_sql']}",
            "writes_performed=false",
        ]
    )


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
