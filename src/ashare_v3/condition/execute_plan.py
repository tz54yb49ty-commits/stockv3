"""Dry-run write plan for condition-layer minute_target_scope execution.

This module does not open database connections or execute SQL. It only turns a
minute_target_scope dry-run report into an auditable future-write plan.
"""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from typing import Any, Mapping


WRITE_ORDER = (
    "common_condition_run",
    "common_condition_quality_item",
    "index_minute_target_scope",
    "board_minute_target_scope",
    "stock_minute_target_scope",
)

ROLLBACK_ORDER = (
    "stock_minute_target_scope",
    "board_minute_target_scope",
    "index_minute_target_scope",
    "common_condition_quality_item",
    "common_condition_run",
)


def build_minute_scope_execute_plan(scope_report: Mapping[str, Any]) -> dict[str, Any]:
    """Build an N2-D3 plan-execute report from an N2-D dry-run report."""
    quality = scope_report.get("quality", {})
    scope_preview = scope_report.get("scope_preview", {})
    source_ready_passed = bool(scope_report.get("source_ready_passed"))
    p0_count = int(quality.get("p0_count") or 0)
    p1_count = int(quality.get("p1_count") or 0)
    p2_count = int(quality.get("p2_count") or 0)
    quality_items = list(quality.get("items") or [])
    scope_rows_total = sum(scope_row_count(scope_preview, domain) for domain in ("stock", "index", "board"))
    source_condition_pool_ids_available = bool(
        scope_report.get("condition_pool_source", {}).get("source_condition_pool_ids_available")
    )
    requires_persisted_pool_ids = scope_rows_total > 0 and not source_condition_pool_ids_available

    planned_run_id = planned_execute_run_id(scope_report)
    would_write = build_would_write_counts(
        scope_report=scope_report,
        planned_run_id=planned_run_id,
        quality_item_count=len(quality_items),
    )
    blocked_reasons = execution_blocked_reasons(
        source_ready_passed=source_ready_passed,
        p0_count=p0_count,
    )
    not_ready_reasons = list(blocked_reasons)
    if p1_count > 0:
        not_ready_reasons.append("p1_user_confirmation_required")
    if requires_persisted_pool_ids:
        not_ready_reasons.append("source_condition_pool_ids_unavailable")
    not_ready_reasons.append("n2_d3_plan_only_execute_not_supported")

    return {
        "stage": "N2-D3",
        "plan_mode": "plan_execute",
        "dry_run_report_id": scope_report.get("run_id"),
        "planned_run_id": planned_run_id,
        "source_trade_date": scope_report.get("source_trade_date"),
        "for_trade_date": scope_report.get("for_trade_date"),
        "prev_trade_date": scope_report.get("prev_trade_date"),
        "source_versions": dict(scope_report.get("source_versions") or {}),
        "policy_name": scope_report.get("scope_policy", {}).get("policy_name"),
        "policy_hash": stable_policy_hash(scope_report.get("scope_policy", {}).get("effective_policy") or {}),
        "write_order": list(WRITE_ORDER),
        "would_write": would_write,
        "row_count_total": sum(int(item["row_count"]) for item in would_write.values()),
        "rollback_plan": build_rollback_plan(planned_run_id),
        "execute_guards": build_execute_guards(
            source_ready_passed=source_ready_passed,
            p0_count=p0_count,
            p1_count=p1_count,
            p2_count=p2_count,
            for_trade_calendar_row_exists=bool(scope_report.get("for_trade_calendar_row_exists")),
            requires_persisted_pool_ids=requires_persisted_pool_ids,
        ),
        "execute_preconditions_passed": source_ready_passed and p0_count == 0,
        "requires_user_confirmation": p1_count > 0,
        "requires_persisted_condition_pool_ids": requires_persisted_pool_ids,
        "source_condition_pool_ids_available": source_condition_pool_ids_available,
        "blocked_reasons": blocked_reasons,
        "not_ready_reasons": not_ready_reasons,
        "execute_supported": False,
        "execute_ready": False,
        "execute_allowed_without_confirmation": False,
        "dry_run_only": True,
        "will_connect_database": False,
        "will_execute_sql": False,
        "writes_performed": False,
    }


def build_would_write_counts(
    *,
    scope_report: Mapping[str, Any],
    planned_run_id: str,
    quality_item_count: int,
) -> dict[str, dict[str, Any]]:
    scope_preview = scope_report.get("scope_preview", {})
    p0_count = int(scope_report.get("quality", {}).get("p0_count") or 0)
    p1_count = int(scope_report.get("quality", {}).get("p1_count") or 0)
    p2_count = int(scope_report.get("quality", {}).get("p2_count") or 0)
    source_versions = dict(scope_report.get("source_versions") or {})
    return {
        "common_condition_run": {
            "row_count": 1,
            "operation": "insert",
            "mode": "execute",
            "status": "planned",
            "run_id": planned_run_id,
            "p0_count": p0_count,
            "p1_count": p1_count,
            "p2_count": p2_count,
            "source_versions": source_versions,
        },
        "common_condition_quality_item": {
            "row_count": quality_item_count,
            "operation": "insert",
            "run_id": planned_run_id,
        },
        "index_minute_target_scope": {
            "row_count": scope_row_count(scope_preview, "index"),
            "operation": "insert",
            "run_id": planned_run_id,
            "scope_source": scope_source_counts(scope_preview, "index"),
            "requires_source_condition_pool_id": True,
        },
        "board_minute_target_scope": {
            "row_count": scope_row_count(scope_preview, "board"),
            "operation": "insert",
            "run_id": planned_run_id,
            "scope_source": scope_source_counts(scope_preview, "board"),
            "requires_source_condition_pool_id": True,
        },
        "stock_minute_target_scope": {
            "row_count": scope_row_count(scope_preview, "stock"),
            "operation": "insert",
            "run_id": planned_run_id,
            "scope_source": scope_source_counts(scope_preview, "stock"),
            "requires_source_condition_pool_id": True,
        },
    }


def build_rollback_plan(planned_run_id: str) -> dict[str, Any]:
    return {
        "strategy": "delete_by_run_id",
        "run_id": planned_run_id,
        "delete_order": [
            {
                "table_name": table_name,
                "sql_template": f"DELETE FROM {table_name} WHERE run_id = :run_id;",
            }
            for table_name in ROLLBACK_ORDER
        ],
        "will_execute_sql": False,
    }


def build_execute_guards(
    *,
    source_ready_passed: bool,
    p0_count: int,
    p1_count: int,
    p2_count: int,
    for_trade_calendar_row_exists: bool,
    requires_persisted_pool_ids: bool,
) -> list[dict[str, Any]]:
    return [
        guard("source_ready_passed", "P0", "passed" if source_ready_passed else "failed", expected="true", actual=str(source_ready_passed).lower()),
        guard("dry_run_p0_clean", "P0", "passed" if p0_count == 0 else "failed", expected="0", actual=str(p0_count)),
        guard("dry_run_p1_confirmation", "P1", "warning" if p1_count > 0 else "passed", expected="0 or user confirmation", actual=str(p1_count)),
        guard("dry_run_p2_recorded", "P2", "warning" if p2_count > 0 else "passed", expected="record only", actual=str(p2_count)),
        guard(
            "for_trade_calendar_row_exists",
            "P1",
            "passed" if for_trade_calendar_row_exists else "warning",
            expected="true",
            actual=str(for_trade_calendar_row_exists).lower(),
        ),
        guard(
            "source_condition_pool_ids_available",
            "P1",
            "warning" if requires_persisted_pool_ids else "passed",
            expected="true before real scope execute",
            actual="false" if requires_persisted_pool_ids else "true",
        ),
        guard("n2_d3_plan_only_no_sql", "P0", "passed", expected="false", actual="will_execute_sql=false"),
    ]


def guard(gate_code: str, severity: str, status: str, *, expected: str, actual: str) -> dict[str, str]:
    return {
        "gate_code": gate_code,
        "severity": severity,
        "status": status,
        "expected_value": expected,
        "actual_value": actual,
    }


def execution_blocked_reasons(*, source_ready_passed: bool, p0_count: int) -> list[str]:
    reasons: list[str] = []
    if not source_ready_passed:
        reasons.append("condition_source_not_ready")
    if p0_count > 0:
        reasons.append("p0_quality_failures")
    return reasons


def planned_execute_run_id(scope_report: Mapping[str, Any]) -> str:
    dry_run_id = str(scope_report.get("run_id") or "")
    if dry_run_id.endswith("_dry_run"):
        return f"{dry_run_id.removesuffix('_dry_run')}_execute"
    source_trade_date = scope_report.get("source_trade_date")
    for_trade_date = scope_report.get("for_trade_date")
    return f"minute_target_scope_{source_trade_date}_to_{for_trade_date}_execute"


def scope_row_count(scope_preview: Mapping[str, Any], domain: str) -> int:
    return int(scope_preview.get(domain, {}).get("scope_row_count") or 0)


def scope_source_counts(scope_preview: Mapping[str, Any], domain: str) -> dict[str, int]:
    return dict(scope_preview.get(domain, {}).get("scope_source_counts") or {})


def stable_policy_hash(policy: Mapping[str, Any]) -> str:
    payload = json.dumps(canonical_json(policy), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): canonical_json(value[key]) for key in sorted(value.keys(), key=str)}
    if isinstance(value, (list, tuple)):
        return [canonical_json(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    return value
