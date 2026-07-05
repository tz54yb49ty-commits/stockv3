"""Whole condition-layer execute readiness plan.

The plan is built from N2-B/N2-C/N2-D dry-run reports. It does not open write
connections, execute SQL, or mutate condition tables.
"""

from __future__ import annotations

from typing import Any, Mapping

from ashare_v3.condition.execute_plan import stable_policy_hash


WRITE_ORDER = (
    "common_condition_run",
    "common_condition_quality_item",
    "stock_monitor_target",
    "index_monitor_target",
    "board_monitor_target",
    "stock_condition_basis",
    "index_condition_basis",
    "board_condition_basis",
    "stock_condition_pool",
    "index_condition_pool",
    "board_condition_pool",
    "index_minute_target_scope",
    "board_minute_target_scope",
    "stock_minute_target_scope",
)

ROLLBACK_ORDER = (
    "stock_minute_target_scope",
    "board_minute_target_scope",
    "index_minute_target_scope",
    "board_condition_pool",
    "index_condition_pool",
    "stock_condition_pool",
    "board_condition_basis",
    "index_condition_basis",
    "stock_condition_basis",
    "board_monitor_target",
    "index_monitor_target",
    "stock_monitor_target",
    "common_condition_quality_item",
    "common_condition_run",
)


def build_condition_layer_execute_readiness_plan(
    *,
    basis_report: Mapping[str, Any],
    pool_report: Mapping[str, Any],
    scope_report: Mapping[str, Any],
) -> dict[str, Any]:
    date_context = extract_date_contexts(basis_report, pool_report, scope_report)
    planned_run_id = f"condition_layer_{date_context['source_trade_date']}_to_{date_context['for_trade_date']}_execute"
    source_versions = merged_source_versions(basis_report, pool_report, scope_report)
    quality_summary = aggregate_quality_summary(basis_report, pool_report, scope_report)
    stage_counts = build_stage_counts(basis_report, pool_report, scope_report)
    would_write = build_would_write_counts(
        planned_run_id=planned_run_id,
        stage_counts=stage_counts,
        quality_item_count=quality_summary["quality_item_count"],
        quality_summary=quality_summary,
        source_versions=source_versions,
    )
    dependency_plan = build_dependency_plan(stage_counts)
    guards = build_execute_guards(
        basis_report=basis_report,
        pool_report=pool_report,
        scope_report=scope_report,
        quality_summary=quality_summary,
        date_context=date_context,
        dependency_plan=dependency_plan,
    )
    blocked_reasons = blocked_reasons_from_guards(guards)
    not_ready_reasons = list(blocked_reasons)
    if quality_summary["p1_count"] > 0:
        not_ready_reasons.append("p1_user_confirmation_required")
    not_ready_reasons.append("n2_e0_plan_only_execute_not_supported")

    return {
        "stage": "N2-E0",
        "plan_mode": "condition_layer_execute_readiness",
        "planned_run_id": planned_run_id,
        "source_trade_date": date_context["source_trade_date"],
        "for_trade_date": date_context["for_trade_date"],
        "prev_trade_date": date_context["prev_trade_date"],
        "source_versions": source_versions,
        "policy_name": scope_report.get("scope_policy", {}).get("policy_name"),
        "policy_hash": stable_policy_hash(scope_report.get("scope_policy", {}).get("effective_policy") or {}),
        "dry_run_reports": {
            "condition_basis": basis_report.get("run_id"),
            "condition_pool": pool_report.get("run_id"),
            "minute_target_scope": scope_report.get("run_id"),
        },
        "stage_counts": stage_counts,
        "quality_summary": quality_summary,
        "write_order": list(WRITE_ORDER),
        "would_write": would_write,
        "row_count_total": sum(int(item["row_count"]) for item in would_write.values()),
        "dependency_plan": dependency_plan,
        "execute_guards": guards,
        "execute_preconditions_passed": not blocked_reasons,
        "requires_user_confirmation": quality_summary["p1_count"] > 0,
        "blocked_reasons": blocked_reasons,
        "not_ready_reasons": not_ready_reasons,
        "rollback_plan": build_rollback_plan(planned_run_id),
        "execute_supported": False,
        "execute_ready": False,
        "execute_allowed_without_confirmation": False,
        "dry_run_only": True,
        "read_only_database_inputs_used": True,
        "will_open_write_connection": False,
        "will_execute_sql": False,
        "writes_performed": False,
        "condition_pool_written": False,
        "minute_kline_pulled": False,
    }


def merged_source_versions(*reports: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for report in reports:
        merged.update(dict(report.get("source_versions") or {}))
    return merged


def extract_date_contexts(*reports: Mapping[str, Any]) -> dict[str, Any]:
    contexts = [
        {
            "source_trade_date": report.get("source_trade_date"),
            "for_trade_date": report.get("for_trade_date"),
            "prev_trade_date": report.get("prev_trade_date"),
        }
        for report in reports
    ]
    first = contexts[0]
    return {
        **first,
        "consistent": all(context == first for context in contexts),
        "contexts": contexts,
    }


def aggregate_quality_summary(*reports: Mapping[str, Any]) -> dict[str, Any]:
    by_stage: dict[str, dict[str, int]] = {}
    item_count = 0
    for stage_name, report in zip(("condition_basis", "condition_pool", "minute_target_scope"), reports):
        quality = report.get("quality", {})
        by_stage[stage_name] = {
            "p0_count": int(quality.get("p0_count") or 0),
            "p1_count": int(quality.get("p1_count") or 0),
            "p2_count": int(quality.get("p2_count") or 0),
            "quality_item_count": len(quality.get("items") or []),
        }
        item_count += by_stage[stage_name]["quality_item_count"]
    return {
        "p0_count": sum(stage["p0_count"] for stage in by_stage.values()),
        "p1_count": sum(stage["p1_count"] for stage in by_stage.values()),
        "p2_count": sum(stage["p2_count"] for stage in by_stage.values()),
        "quality_item_count": item_count + readiness_guard_count(),
        "by_stage": by_stage,
    }


def build_stage_counts(
    basis_report: Mapping[str, Any],
    pool_report: Mapping[str, Any],
    scope_report: Mapping[str, Any],
) -> dict[str, Any]:
    basis = basis_report.get("basis_preview", {})
    pool = pool_report.get("pool_preview", {})
    scope = scope_report.get("scope_preview", {})
    return {
        "condition_basis": {
            "stock": int(basis.get("stock", {}).get("row_count") or 0),
            "index": int(basis.get("index", {}).get("row_count") or 0),
            "board": int(basis.get("board", {}).get("row_count") or 0),
        },
        "condition_pool": {
            "stock": int(pool.get("stock", {}).get("pool_row_count") or 0),
            "index": int(pool.get("index", {}).get("pool_row_count") or 0),
            "board": int(pool.get("board", {}).get("pool_row_count") or 0),
        },
        "minute_target_scope": {
            "stock": int(scope.get("stock", {}).get("scope_row_count") or 0),
            "index": int(scope.get("index", {}).get("scope_row_count") or 0),
            "board": int(scope.get("board", {}).get("scope_row_count") or 0),
        },
    }


def build_would_write_counts(
    *,
    planned_run_id: str,
    stage_counts: Mapping[str, Mapping[str, int]],
    quality_item_count: int,
    quality_summary: Mapping[str, Any],
    source_versions: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    basis = stage_counts["condition_basis"]
    pool = stage_counts["condition_pool"]
    scope = stage_counts["minute_target_scope"]
    return {
        "common_condition_run": {
            "row_count": 1,
            "operation": "insert",
            "mode": "execute",
            "status": "planned",
            "run_id": planned_run_id,
            "p0_count": quality_summary["p0_count"],
            "p1_count": quality_summary["p1_count"],
            "p2_count": quality_summary["p2_count"],
            "source_versions": dict(source_versions),
        },
        "common_condition_quality_item": {
            "row_count": quality_item_count,
            "operation": "insert",
            "run_id": planned_run_id,
        },
        "stock_monitor_target": {"row_count": basis["stock"], "operation": "insert", "source_version": planned_run_id},
        "index_monitor_target": {"row_count": basis["index"], "operation": "insert", "source_version": planned_run_id},
        "board_monitor_target": {"row_count": basis["board"], "operation": "insert", "source_version": planned_run_id},
        "stock_condition_basis": {"row_count": basis["stock"], "operation": "insert", "run_id": planned_run_id},
        "index_condition_basis": {"row_count": basis["index"], "operation": "insert", "run_id": planned_run_id},
        "board_condition_basis": {"row_count": basis["board"], "operation": "insert", "run_id": planned_run_id},
        "stock_condition_pool": {
            "row_count": pool["stock"],
            "operation": "insert",
            "run_id": planned_run_id,
            "requires_source_condition_basis_id": True,
        },
        "index_condition_pool": {
            "row_count": pool["index"],
            "operation": "insert",
            "run_id": planned_run_id,
            "requires_source_condition_basis_id": True,
        },
        "board_condition_pool": {
            "row_count": pool["board"],
            "operation": "insert",
            "run_id": planned_run_id,
            "requires_source_condition_basis_id": True,
        },
        "index_minute_target_scope": {"row_count": scope["index"], "operation": "insert", "run_id": planned_run_id},
        "board_minute_target_scope": {"row_count": scope["board"], "operation": "insert", "run_id": planned_run_id},
        "stock_minute_target_scope": {
            "row_count": scope["stock"],
            "operation": "insert",
            "run_id": planned_run_id,
            "requires_source_condition_pool_id": True,
        },
    }


def build_dependency_plan(stage_counts: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    pool_rows = sum(stage_counts["condition_pool"].values())
    scope_rows = sum(stage_counts["minute_target_scope"].values())
    stock_scope_rows = int(stage_counts["minute_target_scope"].get("stock") or 0)
    return {
        "condition_pool_source_basis_id": {
            "required": pool_rows > 0,
            "resolved_by": "condition_basis rows inserted earlier in the same planned run",
            "real_execute_requirement": "use INSERT ... RETURNING or equivalent identity-key mapping",
        },
        "condition_basis_source_monitor_target_id": {
            "required": True,
            "resolved_by": "monitor_target rows inserted earlier in the same execute transaction",
            "real_execute_requirement": "use INSERT ... RETURNING or equivalent identity-key mapping",
        },
        "stock_scope_source_pool_id": {
            "required": stock_scope_rows > 0,
            "resolved_by": "stock_condition_pool rows inserted earlier in the same planned run",
            "real_execute_requirement": "use INSERT ... RETURNING or equivalent condition_pool_ref mapping",
        },
        "scope_source_pool_id": {
            "required": scope_rows > 0,
            "resolved_by": "stock/index/board condition_pool rows inserted earlier in the same planned run",
            "real_execute_requirement": "use INSERT ... RETURNING or equivalent condition_pool_ref mapping for every scope row",
        },
    }


def build_execute_guards(
    *,
    basis_report: Mapping[str, Any],
    pool_report: Mapping[str, Any],
    scope_report: Mapping[str, Any],
    quality_summary: Mapping[str, Any],
    date_context: Mapping[str, Any],
    dependency_plan: Mapping[str, Any],
) -> list[dict[str, str]]:
    source_ready_passed = all(
        bool(report.get("source_ready_passed"))
        for report in (basis_report, pool_report, scope_report)
    )
    for_trade_calendar_row_exists = bool(scope_report.get("for_trade_calendar_row_exists"))
    return [
        guard("source_ready_passed", "P0", "passed" if source_ready_passed else "failed", "true", str(source_ready_passed).lower()),
        guard("date_context_consistent", "P0", "passed" if date_context["consistent"] else "failed", "same source/for/prev dates", str(date_context["contexts"])),
        guard("aggregate_p0_clean", "P0", "passed" if quality_summary["p0_count"] == 0 else "failed", "0", str(quality_summary["p0_count"])),
        guard("aggregate_p1_confirmation", "P1", "warning" if quality_summary["p1_count"] > 0 else "passed", "0 or user confirmation", str(quality_summary["p1_count"])),
        guard("aggregate_p2_recorded", "P2", "warning" if quality_summary["p2_count"] > 0 else "passed", "record only", str(quality_summary["p2_count"])),
        guard("for_trade_calendar_row_exists", "P1", "passed" if for_trade_calendar_row_exists else "warning", "true", str(for_trade_calendar_row_exists).lower()),
        guard("monitor_target_id_dependency_planned", "P0", "passed", "planned before condition_basis", "true"),
        guard("basis_id_dependency_planned", "P0", "passed", "planned before condition_pool", str(dependency_plan["condition_pool_source_basis_id"]["required"]).lower()),
        guard("pool_id_dependency_planned", "P0", "passed", "planned before stock/index/board scope", str(dependency_plan["scope_source_pool_id"]["required"]).lower()),
        guard("n2_e0_plan_only_no_sql", "P0", "passed", "false", "will_execute_sql=false"),
    ]


def guard(gate_code: str, severity: str, status: str, expected: str, actual: str) -> dict[str, str]:
    return {
        "gate_code": gate_code,
        "severity": severity,
        "status": status,
        "expected_value": expected,
        "actual_value": actual,
    }


def blocked_reasons_from_guards(guards: list[Mapping[str, str]]) -> list[str]:
    return [
        str(guard["gate_code"])
        for guard in guards
        if guard.get("severity") == "P0" and guard.get("status") == "failed"
    ]


def readiness_guard_count() -> int:
    return 10


def build_rollback_plan(planned_run_id: str) -> dict[str, Any]:
    return {
        "strategy": "delete_by_run_id",
        "run_id": planned_run_id,
        "delete_order": [
            {
                "table_name": table_name,
                "sql_template": rollback_sql_template(table_name, ":run_id"),
            }
            for table_name in ROLLBACK_ORDER
        ],
        "will_execute_sql": False,
    }


def rollback_sql_template(table_name: str, run_parameter: str) -> str:
    if table_name in {"stock_monitor_target", "index_monitor_target", "board_monitor_target"}:
        return f"DELETE FROM {table_name} WHERE source_version = {run_parameter};"
    return f"DELETE FROM {table_name} WHERE run_id = {run_parameter};"
