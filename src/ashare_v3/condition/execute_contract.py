"""Execute and rollback contract for the condition layer.

N2-E1 only emits a contract/report. It never executes SQL and never mutates the
condition layer.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from ashare_v3.condition.active_status import CANONICAL_ACTIVE_STATUS, LEGACY_ACTIVE_STATUS
from ashare_v3.condition.readiness_plan import ROLLBACK_ORDER, WRITE_ORDER, rollback_sql_template


RUN_ID_TEMPLATE = "condition_layer_{source_trade_date}_to_{for_trade_date}_{yyyymmddHHMMSS}_execute"
FORBIDDEN_WRITE_DOMAINS = ("trigger", "action", "mobile", "voice", "sim", "worker", "old_system")


def build_condition_execute_contract(
    readiness_plan: Mapping[str, Any],
    *,
    user_confirmed: bool = False,
    overwrite: bool = False,
    operator: str = "manual",
    confirmation_note: str = "",
) -> dict[str, Any]:
    """Build the N2-E1 execute/rollback contract from an N2-E0 readiness plan."""
    quality_summary = dict(readiness_plan.get("quality_summary") or {})
    p0_count = int(quality_summary.get("p0_count") or 0)
    p1_count = int(quality_summary.get("p1_count") or 0)
    readiness_passed = bool(readiness_plan.get("execute_preconditions_passed"))
    user_confirmation_required = p1_count > 0 or overwrite
    active_run_policy = "overwrite_requires_confirmation" if overwrite else "reject_if_active_exists"
    expected_hash = stable_contract_hash(
        {
            "source_trade_date": readiness_plan.get("source_trade_date"),
            "for_trade_date": readiness_plan.get("for_trade_date"),
            "prev_trade_date": readiness_plan.get("prev_trade_date"),
            "source_versions": readiness_plan.get("source_versions") or {},
            "policy_hash": readiness_plan.get("policy_hash"),
            "stage_counts": readiness_plan.get("stage_counts") or {},
            "quality_summary": quality_summary,
        }
    )
    execute_request_allowed = (
        readiness_passed
        and p0_count == 0
        and (not user_confirmation_required or user_confirmed)
    )
    blocked_reasons = contract_blocked_reasons(
        readiness_passed=readiness_passed,
        p0_count=p0_count,
    )
    not_ready_reasons = list(blocked_reasons)
    if user_confirmation_required and not user_confirmed:
        not_ready_reasons.append("user_confirmation_required")
    if overwrite and not user_confirmed:
        not_ready_reasons.append("overwrite_requires_user_confirmation")
    not_ready_reasons.append("n2_e1_contract_only_execute_not_supported")

    return {
        "stage": "N2-E1",
        "plan_mode": "condition_layer_execute_contract",
        "readiness_plan_id": readiness_plan.get("planned_run_id"),
        "source_trade_date": readiness_plan.get("source_trade_date"),
        "for_trade_date": readiness_plan.get("for_trade_date"),
        "prev_trade_date": readiness_plan.get("prev_trade_date"),
        "source_versions": dict(readiness_plan.get("source_versions") or {}),
        "policy_name": readiness_plan.get("policy_name"),
        "policy_hash": readiness_plan.get("policy_hash"),
        "operator": operator,
        "user_confirmed": bool(user_confirmed),
        "confirmation_note_present": bool(confirmation_note),
        "overwrite": bool(overwrite),
        "run_id_contract": build_run_id_contract(readiness_plan),
        "source_version_contract": build_source_version_contract(readiness_plan),
        "quality_policy": build_quality_policy(quality_summary, user_confirmation_required),
        "row_count_contract": build_row_count_contract(readiness_plan, expected_hash),
        "write_contract": build_write_contract(readiness_plan),
        "active_run_contract": build_active_run_contract(readiness_plan, active_run_policy),
        "rollback_contract": build_rollback_contract(readiness_plan),
        "verification_contract": build_verification_contract(readiness_plan, expected_hash),
        "execute_guards": build_execute_guards(
            readiness_passed=readiness_passed,
            p0_count=p0_count,
            p1_count=p1_count,
            user_confirmed=user_confirmed,
            overwrite=overwrite,
        ),
        "contract_hash": stable_contract_hash(
            {
                "readiness_plan_id": readiness_plan.get("planned_run_id"),
                "source_versions": readiness_plan.get("source_versions") or {},
                "policy_hash": readiness_plan.get("policy_hash"),
                "expected_hash": expected_hash,
                "active_run_policy": active_run_policy,
                "overwrite": overwrite,
            }
        ),
        "execute_request_allowed": execute_request_allowed,
        "execute_ready": False,
        "execute_supported": False,
        "blocked_reasons": blocked_reasons,
        "not_ready_reasons": not_ready_reasons,
        "dry_run_only": True,
        "will_open_write_connection": False,
        "will_execute_sql": False,
        "writes_performed": False,
        "migration_performed": False,
        "minute_kline_pulled": False,
    }


def build_run_id_contract(readiness_plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "readiness_planned_run_id": readiness_plan.get("planned_run_id"),
        "execute_run_id_template": RUN_ID_TEMPLATE,
        "must_generate_new_run_id_per_execute": True,
        "reuse_existing_run_id_allowed": False,
        "shared_by_tables": list(WRITE_ORDER),
        "same_transaction_required": True,
    }


def build_source_version_contract(readiness_plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_versions": dict(readiness_plan.get("source_versions") or {}),
        "must_match_readiness_plan": True,
        "drift_check_required": True,
        "drift_check_sql_template": (
            "SELECT data_type, active_source_version FROM common_condition_active_source_version_view "
            "WHERE trade_date = :source_trade_date;"
        ),
        "on_drift": "abort_execute_and_rerun_n2_e0_n2_e1",
    }


def build_quality_policy(quality_summary: Mapping[str, Any], user_confirmation_required: bool) -> dict[str, Any]:
    return {
        "p0_count": int(quality_summary.get("p0_count") or 0),
        "p1_count": int(quality_summary.get("p1_count") or 0),
        "p2_count": int(quality_summary.get("p2_count") or 0),
        "p0_policy": "block_execute",
        "p1_policy": "requires_user_confirmation" if user_confirmation_required else "allow_if_zero",
        "p2_policy": "record_only",
        "user_confirmation_required": user_confirmation_required,
    }


def build_row_count_contract(readiness_plan: Mapping[str, Any], expected_hash: str) -> dict[str, Any]:
    would_write = readiness_plan.get("would_write") or {}
    return {
        "expected_rows_by_table": {
            table_name: int(spec.get("row_count") or 0)
            for table_name, spec in would_write.items()
        },
        "pre_execute_expected_hash": expected_hash,
        "post_execute_hash_must_match": True,
        "row_count_mismatch_policy": "mark_run_failed_and_rollback",
    }


def build_write_contract(readiness_plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "write_order": list(WRITE_ORDER),
        "transaction_required": True,
        "common_condition_run_initial_status": "running",
        "common_condition_run_success_status": CANONICAL_ACTIVE_STATUS,
        "common_condition_run_failure_status": "failed",
        "id_mapping_requirements": {
            "condition_basis_source_monitor_target_id": "use INSERT RETURNING or equivalent monitor target identity-key mapping",
            "condition_pool_source_condition_basis_id": "use INSERT RETURNING or equivalent basis identity-key mapping",
            "scope_source_condition_pool_id": "use INSERT RETURNING or equivalent condition_pool_ref mapping for stock/index/board scope rows",
        },
        "stage_counts": dict(readiness_plan.get("stage_counts") or {}),
    }


def build_active_run_contract(readiness_plan: Mapping[str, Any], active_run_policy: str) -> dict[str, Any]:
    return {
        "active_pointer": "common_condition_run.status = 'passed_active'",
        "legacy_active_pointer_read_compat": "common_condition_run.status = 'passed'",
        "canonical_active_status": CANONICAL_ACTIVE_STATUS,
        "legacy_active_status": LEGACY_ACTIVE_STATUS,
        "active_run_lookup_sql_template": (
            "SELECT run_id FROM common_condition_run "
            "WHERE source_trade_date = :source_trade_date AND for_trade_date = :for_trade_date "
            "AND status IN ('passed_active', 'passed') "
            "ORDER BY CASE status WHEN 'passed_active' THEN 0 WHEN 'passed' THEN 1 ELSE 2 END, "
            "finished_at DESC NULLS LAST, created_at DESC LIMIT 1;"
        ),
        "canonical_active_uniqueness": "one passed_active per source_trade_date + for_trade_date",
        "default_policy": "reject_if_active_exists",
        "active_run_policy": active_run_policy,
        "overwrite_requires_explicit_flag": active_run_policy == "overwrite_requires_confirmation",
        "overwrite_requires_user_confirmation": True,
        "previous_active_run_id_storage": "new common_condition_run.raw_json.previous_active_run_id",
        "switch_after_postcheck_sql_templates": [
            "UPDATE common_condition_run SET status = 'superseded', updated_at = now() WHERE run_id = :previous_active_run_id;",
            "UPDATE common_condition_run SET status = 'passed_active', finished_at = now(), updated_at = now() WHERE run_id = :execute_run_id;",
        ],
        "on_postcheck_failed": "keep_previous_active_status_and_mark_new_run_failed",
        "source_trade_date": readiness_plan.get("source_trade_date"),
        "for_trade_date": readiness_plan.get("for_trade_date"),
    }


def build_rollback_contract(readiness_plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy": "delete_by_run_id_then_restore_previous_active",
        "run_id_parameter": ":execute_run_id",
        "delete_order": [
            {
                "table_name": table_name,
                "sql_template": rollback_sql_template(table_name, ":execute_run_id"),
            }
            for table_name in ROLLBACK_ORDER
        ],
        "restore_previous_active_sql_template": (
            "UPDATE common_condition_run SET status = 'passed_active', updated_at = now() "
            "WHERE run_id = :previous_active_run_id;"
        ),
        "rollback_report_required": True,
        "rollback_report_fields": [
            "execute_run_id",
            "previous_active_run_id",
            "operator",
            "reason",
            "started_at",
            "finished_at",
            "deleted_row_counts",
            "pre_rollback_hash",
            "post_rollback_hash",
        ],
        "readiness_rollback_plan": dict(readiness_plan.get("rollback_plan") or {}),
        "will_execute_sql": False,
    }


def build_verification_contract(readiness_plan: Mapping[str, Any], expected_hash: str) -> dict[str, Any]:
    return {
        "pre_execute": [
            "readiness_plan_hash_recorded",
            "source_versions_match_active_source",
            "policy_hash_match",
            "expected_row_counts_recorded",
            "p0_count_is_zero",
            "user_confirmation_is_true",
            "active_run_conflict_checked",
        ],
        "post_execute": [
            "common_condition_run_row_count_matches",
            "common_condition_quality_item_row_count_matches",
            "stock_index_board_condition_basis_row_counts_match",
            "stock_index_board_condition_pool_row_counts_match",
            "stock_index_board_minute_target_scope_row_counts_match",
            "source_versions_not_drifted",
            "policy_hash_not_drifted",
            "physical_table_family_split_checked",
            "forbidden_field_scan_passed",
            "downstream_write_absence_checked",
        ],
        "expected_hash": expected_hash,
        "forbidden_field_scan_manifest": "condition_layer_execution_field_blocklist_from_AGENTS_and_design_doc",
        "forbidden_write_domains": list(FORBIDDEN_WRITE_DOMAINS),
        "downstream_write_policy": "no writes to trigger/action/mobile/voice/sim/worker/old_system",
    }


def build_execute_guards(
    *,
    readiness_passed: bool,
    p0_count: int,
    p1_count: int,
    user_confirmed: bool,
    overwrite: bool,
) -> list[dict[str, str]]:
    return [
        guard("readiness_preconditions_passed", "P0", "passed" if readiness_passed else "failed", "true", str(readiness_passed).lower()),
        guard("p0_count_zero", "P0", "passed" if p0_count == 0 else "failed", "0", str(p0_count)),
        guard("p1_user_confirmation", "P1", "passed" if p1_count == 0 or user_confirmed else "warning", "true when P1 > 0", str(user_confirmed).lower()),
        guard("overwrite_user_confirmation", "P1", "passed" if not overwrite or user_confirmed else "warning", "true when overwrite", str(user_confirmed).lower()),
        guard("n2_e1_contract_only_no_sql", "P0", "passed", "false", "will_execute_sql=false"),
    ]


def guard(gate_code: str, severity: str, status: str, expected: str, actual: str) -> dict[str, str]:
    return {
        "gate_code": gate_code,
        "severity": severity,
        "status": status,
        "expected_value": expected,
        "actual_value": actual,
    }


def contract_blocked_reasons(*, readiness_passed: bool, p0_count: int) -> list[str]:
    reasons: list[str] = []
    if not readiness_passed:
        reasons.append("readiness_preconditions_failed")
    if p0_count > 0:
        reasons.append("p0_quality_failures")
    return reasons


def stable_contract_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
