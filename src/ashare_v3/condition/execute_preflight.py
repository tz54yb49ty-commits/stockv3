"""Final read-only preflight before condition-layer execute.

N2-E2 may inspect PostgreSQL metadata and existing active runs with a read-only
connection. It never writes condition tables, runs migrations, or pulls market
data.
"""

from __future__ import annotations

from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.active_status import (
    CONDITION_RUN_STATUS_CHECK_NAME,
    active_status_order_sql,
    active_status_sql_list,
    status_check_supports_passed_active,
    summarize_active_runs,
)
from ashare_v3.condition.basis import (
    LEVEL_SCORE_FIELDS,
    STOCK_CANONICAL_FINANCIAL_FIELDS,
    STOCK_FINANCIAL_COMPATIBILITY_FIELDS,
    SYMMETRY_SECONDARY_TARGET_FIELDS,
)


REQUIRED_SCHEMA_TABLES = (
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
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
)
CANONICAL_TARGET_SCHEMA_TABLES = (
    "stock_condition_basis",
    "index_condition_basis",
    "board_condition_basis",
    "stock_condition_pool",
    "index_condition_pool",
    "board_condition_pool",
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
)
CANONICAL_TARGET_SCHEMA_COLUMNS = (
    "symmetry_anchor",
    "secondary_symmetry_anchor",
    "amplitude_source_period",
    "a_segment_start_date",
    "a_segment_end_date",
    "a_segment_high",
    "a_segment_low",
    "a_segment_amplitude",
    "base_price_policy",
    "base_price",
    "reference_target_price",
    "secondary_target_price",
    "target_price_trace_json",
) + SYMMETRY_SECONDARY_TARGET_FIELDS
FORBIDDEN_TARGET_SCHEMA_COLUMNS = ("locked_target_price", "target_lock_status")
STOCK_FINANCIAL_SCHEMA_TABLES = (
    "stock_condition_basis",
    "stock_condition_pool",
    "stock_minute_target_scope",
    "stock_condition_display_basis",
)
STOCK_FINANCIAL_SCHEMA_COLUMNS = STOCK_CANONICAL_FINANCIAL_FIELDS + STOCK_FINANCIAL_COMPATIBILITY_FIELDS
LEVEL_SCORE_SCHEMA_TABLES = CANONICAL_TARGET_SCHEMA_TABLES
LEVEL_SCORE_SCHEMA_COLUMNS = LEVEL_SCORE_FIELDS

REQUIRED_SOURCE_VERSION_KEYS = (
    "stock_daily",
    "stock_daily_basic",
    "stock_financial",
    "index_daily",
    "index_membership",
    "board_daily",
    "board_membership",
)

RUN_ID_TARGET_TABLES = (
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
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
    "stock_condition_display_basis",
    "index_condition_display_basis",
    "board_condition_display_basis",
)

MONITOR_TARGET_TABLES = {"stock_monitor_target", "index_monitor_target", "board_monitor_target"}


def fetch_schema_status(dsn: str) -> dict[str, Any]:
    """Read-only schema existence check for condition-layer execute tables."""
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        table_status: dict[str, dict[str, Any]] = {}
        for table_name in REQUIRED_SCHEMA_TABLES:
            cur.execute("SELECT to_regclass(%s) AS table_regclass", (f"public.{table_name}",))
            exists = cur.fetchone()["table_regclass"] is not None
            table_status[table_name] = {
                "exists": exists,
                "regclass": f"public.{table_name}" if exists else None,
            }
        canonical_target_status: dict[str, dict[str, Any]] = {}
        for table_name in CANONICAL_TARGET_SCHEMA_TABLES:
            cur.execute("SELECT to_regclass(%s) AS table_regclass", (f"public.{table_name}",))
            exists = cur.fetchone()["table_regclass"] is not None
            if not exists:
                canonical_target_status[table_name] = {
                    "exists": False,
                    "missing_columns": list(CANONICAL_TARGET_SCHEMA_COLUMNS),
                    "forbidden_columns_present": [],
                    "ready": False,
                }
                continue
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                """,
                (table_name,),
            )
            columns = {str(row["column_name"]) for row in cur.fetchall()}
            missing_columns = [column for column in CANONICAL_TARGET_SCHEMA_COLUMNS if column not in columns]
            forbidden_columns_present = [column for column in FORBIDDEN_TARGET_SCHEMA_COLUMNS if column in columns]
            canonical_target_status[table_name] = {
                "exists": True,
                "missing_columns": missing_columns,
                "forbidden_columns_present": forbidden_columns_present,
                "ready": not missing_columns and not forbidden_columns_present,
            }
        stock_financial_status: dict[str, dict[str, Any]] = {}
        for table_name in STOCK_FINANCIAL_SCHEMA_TABLES:
            cur.execute("SELECT to_regclass(%s) AS table_regclass", (f"public.{table_name}",))
            exists = cur.fetchone()["table_regclass"] is not None
            if not exists:
                stock_financial_status[table_name] = {
                    "exists": False,
                    "missing_columns": list(STOCK_FINANCIAL_SCHEMA_COLUMNS),
                    "forbidden_columns_present": [],
                    "ready": False,
                }
                continue
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                """,
                (table_name,),
            )
            columns = {str(row["column_name"]) for row in cur.fetchall()}
            missing_columns = [column for column in STOCK_FINANCIAL_SCHEMA_COLUMNS if column not in columns]
            forbidden_columns_present = [column for column in FORBIDDEN_TARGET_SCHEMA_COLUMNS if column in columns]
            stock_financial_status[table_name] = {
                "exists": True,
                "missing_columns": missing_columns,
                "forbidden_columns_present": forbidden_columns_present,
                "ready": not missing_columns and not forbidden_columns_present,
            }
        level_score_status: dict[str, dict[str, Any]] = {}
        for table_name in LEVEL_SCORE_SCHEMA_TABLES:
            cur.execute("SELECT to_regclass(%s) AS table_regclass", (f"public.{table_name}",))
            exists = cur.fetchone()["table_regclass"] is not None
            if not exists:
                level_score_status[table_name] = {
                    "exists": False,
                    "missing_columns": list(LEVEL_SCORE_SCHEMA_COLUMNS),
                    "ready": False,
                }
                continue
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                """,
                (table_name,),
            )
            columns = {str(row["column_name"]) for row in cur.fetchall()}
            missing_columns = [column for column in LEVEL_SCORE_SCHEMA_COLUMNS if column not in columns]
            level_score_status[table_name] = {
                "exists": True,
                "missing_columns": missing_columns,
                "ready": not missing_columns,
            }
        cur.execute(
            """
            SELECT pg_get_constraintdef(c.oid) AS check_definition
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
              AND t.relname = 'common_condition_run'
              AND c.conname = %s
            """,
            (CONDITION_RUN_STATUS_CHECK_NAME,),
        )
        constraint_row = cur.fetchone()
        status_check_definition = None if constraint_row is None else constraint_row["check_definition"]
    missing = [table_name for table_name, status in table_status.items() if not status["exists"]]
    passed_active_supported = status_check_supports_passed_active(status_check_definition)
    canonical_target_missing_columns = {
        table_name: status["missing_columns"]
        for table_name, status in canonical_target_status.items()
        if status.get("missing_columns")
    }
    canonical_target_forbidden_columns = {
        table_name: status["forbidden_columns_present"]
        for table_name, status in canonical_target_status.items()
        if status.get("forbidden_columns_present")
    }
    canonical_target_fields_ready = not canonical_target_missing_columns and not canonical_target_forbidden_columns
    stock_financial_missing_columns = {
        table_name: status["missing_columns"]
        for table_name, status in stock_financial_status.items()
        if status.get("missing_columns")
    }
    stock_financial_forbidden_columns = {
        table_name: status["forbidden_columns_present"]
        for table_name, status in stock_financial_status.items()
        if status.get("forbidden_columns_present")
    }
    stock_financial_fields_ready = not stock_financial_missing_columns and not stock_financial_forbidden_columns
    level_score_missing_columns = {
        table_name: status["missing_columns"]
        for table_name, status in level_score_status.items()
        if status.get("missing_columns")
    }
    level_score_fields_ready = not level_score_missing_columns
    return {
        "schema_ready": not missing and passed_active_supported and canonical_target_fields_ready and stock_financial_fields_ready and level_score_fields_ready,
        "required_tables": list(REQUIRED_SCHEMA_TABLES),
        "table_status": table_status,
        "missing_tables": missing,
        "canonical_target_schema_tables": list(CANONICAL_TARGET_SCHEMA_TABLES),
        "canonical_target_schema_columns": list(CANONICAL_TARGET_SCHEMA_COLUMNS),
        "canonical_target_table_status": canonical_target_status,
        "canonical_target_fields_ready": canonical_target_fields_ready,
        "canonical_target_missing_columns": canonical_target_missing_columns,
        "canonical_target_forbidden_columns": canonical_target_forbidden_columns,
        "stock_financial_schema_tables": list(STOCK_FINANCIAL_SCHEMA_TABLES),
        "stock_financial_schema_columns": list(STOCK_FINANCIAL_SCHEMA_COLUMNS),
        "stock_financial_table_status": stock_financial_status,
        "stock_financial_fields_ready": stock_financial_fields_ready,
        "stock_financial_missing_columns": stock_financial_missing_columns,
        "stock_financial_forbidden_columns": stock_financial_forbidden_columns,
        "level_score_schema_tables": list(LEVEL_SCORE_SCHEMA_TABLES),
        "level_score_schema_columns": list(LEVEL_SCORE_SCHEMA_COLUMNS),
        "level_score_table_status": level_score_status,
        "level_score_fields_ready": level_score_fields_ready,
        "level_score_missing_columns": level_score_missing_columns,
        "condition_run_status_check_name": CONDITION_RUN_STATUS_CHECK_NAME,
        "condition_run_status_check_definition": status_check_definition,
        "passed_active_status_supported": passed_active_supported,
        "status_migration_required": not passed_active_supported,
        "migration_required": bool(missing) or not passed_active_supported or not canonical_target_fields_ready or not stock_financial_fields_ready or not level_score_fields_ready,
        "migration_performed": False,
        "read_only": True,
    }


def fetch_active_run_status(
    dsn: str,
    *,
    source_trade_date: str,
    for_trade_date: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Read-only active condition run check for the requested date pair."""
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.common_condition_run') AS table_regclass")
        table_exists = cur.fetchone()["table_regclass"] is not None
        if not table_exists:
            return {
                "table_exists": False,
                "active_exists": False,
                "active_runs": [],
                "default_policy": "reject_if_active_exists",
                "overwrite": overwrite,
                "blocked_by_active_run": False,
                "read_only": True,
            }
        cur.execute(
            """
            SELECT run_id, status, source_trade_date, for_trade_date, prev_trade_date,
                   source_versions, p0_count, p1_count, p2_count,
                   created_at, finished_at
            FROM common_condition_run
            WHERE source_trade_date = %s
              AND for_trade_date = %s
              AND status IN (""" + active_status_sql_list() + """)
            ORDER BY """ + active_status_order_sql("status") + """,
                     finished_at DESC NULLS LAST,
                     created_at DESC
            """,
            (source_trade_date, for_trade_date),
        )
        active_runs = [normalize_row(row) for row in cur.fetchall()]
    return summarize_active_runs(active_runs, overwrite=overwrite)


def fetch_run_id_status(dsn: str, requested_run_id: str) -> dict[str, Any]:
    """Read-only target-table baseline check for a requested execute run id."""
    table_counts: dict[str, int] = {}
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for table_name in RUN_ID_TARGET_TABLES:
            cur.execute("SELECT to_regclass(%s) AS table_regclass", (f"public.{table_name}",))
            exists = cur.fetchone()["table_regclass"] is not None
            if not exists:
                table_counts[table_name] = 0
                continue
            where_column = "source_version" if table_name in MONITOR_TARGET_TABLES else "run_id"
            cur.execute(f"SELECT count(*)::bigint AS count FROM {table_name} WHERE {where_column} = %s", (requested_run_id,))
            table_counts[table_name] = int(cur.fetchone()["count"])
    total = sum(table_counts.values())
    return {
        "requested_run_id": requested_run_id,
        "table_counts": table_counts,
        "total_existing_rows": total,
        "run_id_available": total == 0,
        "read_only": True,
    }


def build_condition_execute_preflight(
    *,
    readiness_plan: Mapping[str, Any],
    execute_contract: Mapping[str, Any],
    schema_status: Mapping[str, Any],
    active_run_status: Mapping[str, Any],
    run_id_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine readiness, contract, schema, and active-run checks."""
    quality = dict(readiness_plan.get("quality_summary") or execute_contract.get("quality_policy") or {})
    source_version_status = build_source_version_status(execute_contract)
    rollback_sql_preview = [
        item.get("sql_template")
        for item in execute_contract.get("rollback_contract", {}).get("delete_order", [])
    ]
    blocked_reasons = build_blocked_reasons(
        readiness_plan=readiness_plan,
        execute_contract=execute_contract,
        schema_status=schema_status,
        active_run_status=active_run_status,
        run_id_status=run_id_status,
        source_version_status=source_version_status,
    )
    user_confirmation_required = bool(execute_contract.get("quality_policy", {}).get("user_confirmation_required"))
    execute_allowed = (
        not blocked_reasons
        and bool(execute_contract.get("execute_request_allowed"))
        and bool(schema_status.get("schema_ready"))
        and not bool(active_run_status.get("blocked_by_active_run"))
    )
    return {
        "stage": "N2-E2",
        "plan_mode": "condition_layer_execute_preflight",
        "source_trade_date": readiness_plan.get("source_trade_date"),
        "for_trade_date": readiness_plan.get("for_trade_date"),
        "prev_trade_date": readiness_plan.get("prev_trade_date"),
        "run_id_preview": execute_contract.get("run_id_contract", {}).get("execute_run_id_template"),
        "readiness_plan_id": readiness_plan.get("planned_run_id"),
        "policy_name": execute_contract.get("policy_name"),
        "policy_hash": execute_contract.get("policy_hash"),
        "expected_row_counts": dict(execute_contract.get("row_count_contract", {}).get("expected_rows_by_table") or {}),
        "expected_hash": execute_contract.get("row_count_contract", {}).get("pre_execute_expected_hash"),
        "quality_summary": {
            "p0_count": int(quality.get("p0_count") or 0),
            "p1_count": int(quality.get("p1_count") or 0),
            "p2_count": int(quality.get("p2_count") or 0),
        },
        "schema_status": dict(schema_status),
        "active_run_status": dict(active_run_status),
        "run_id_status": dict(run_id_status or {}),
        "source_version_status": source_version_status,
        "rollback_sql_preview": rollback_sql_preview,
        "rollback_strategy": execute_contract.get("rollback_contract", {}).get("strategy"),
        "user_confirmation_required": user_confirmation_required,
        "user_confirmed": bool(execute_contract.get("user_confirmed")),
        "overwrite": bool(execute_contract.get("overwrite")),
        "execute_allowed": execute_allowed,
        "execute_allowed_meaning": "true means eligible to request N2-E3 execute; N2-E2 never executes SQL",
        "blocked_reasons": blocked_reasons,
        "preflight_guards": build_preflight_guards(
            readiness_plan=readiness_plan,
            execute_contract=execute_contract,
            schema_status=schema_status,
            active_run_status=active_run_status,
            run_id_status=run_id_status,
            source_version_status=source_version_status,
            rollback_sql_preview=rollback_sql_preview,
        ),
        "dry_run_only": True,
        "read_only_database_checks": True,
        "will_execute_sql": False,
        "writes_performed": False,
        "migration_performed": False,
        "minute_kline_pulled": False,
        "downstream_layers_touched": False,
    }


def build_blocked_reasons(
    *,
    readiness_plan: Mapping[str, Any],
    execute_contract: Mapping[str, Any],
    schema_status: Mapping[str, Any],
    active_run_status: Mapping[str, Any],
    run_id_status: Mapping[str, Any] | None,
    source_version_status: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if not readiness_plan.get("execute_preconditions_passed"):
        reasons.append("readiness_preconditions_failed")
    if execute_contract.get("blocked_reasons"):
        reasons.extend(str(reason) for reason in execute_contract.get("blocked_reasons") or [])
    if not schema_status.get("schema_ready"):
        reasons.append("schema_not_migrated")
    if schema_status.get("canonical_target_fields_ready") is False:
        reasons.append("canonical_target_schema_not_ready")
    if schema_status.get("stock_financial_fields_ready") is False:
        reasons.append("stock_financial_schema_not_ready")
    if not schema_status.get("passed_active_status_supported", True):
        reasons.append("passed_active_status_not_migrated")
    if active_run_status.get("blocked_by_active_run"):
        reasons.append("active_run_exists")
    if active_run_status.get("blocked_by_multiple_passed_active"):
        reasons.append("multiple_passed_active_runs")
    if run_id_status and not run_id_status.get("run_id_available"):
        reasons.append("run_id_already_exists")
    if not source_version_status.get("complete"):
        reasons.append("source_versions_incomplete")
    quality_policy = dict(execute_contract.get("quality_policy") or {})
    if quality_policy.get("user_confirmation_required") and not execute_contract.get("user_confirmed"):
        reasons.append("user_confirmation_required")
    return sorted(set(reasons))


def build_preflight_guards(
    *,
    readiness_plan: Mapping[str, Any],
    execute_contract: Mapping[str, Any],
    schema_status: Mapping[str, Any],
    active_run_status: Mapping[str, Any],
    run_id_status: Mapping[str, Any] | None,
    source_version_status: Mapping[str, Any],
    rollback_sql_preview: list[Any],
) -> list[dict[str, str]]:
    quality = dict(readiness_plan.get("quality_summary") or {})
    p0_count = int(quality.get("p0_count") or 0)
    user_required = bool(execute_contract.get("quality_policy", {}).get("user_confirmation_required"))
    user_confirmed = bool(execute_contract.get("user_confirmed"))
    return [
        guard("schema_ready", "P0", "passed" if schema_status.get("schema_ready") else "failed", "true", str(bool(schema_status.get("schema_ready"))).lower()),
        guard("canonical_target_schema_ready", "P0", "passed" if schema_status.get("canonical_target_fields_ready", True) else "failed", "true", str(bool(schema_status.get("canonical_target_fields_ready", True))).lower()),
        guard("stock_financial_schema_ready", "P0", "passed" if schema_status.get("stock_financial_fields_ready", True) else "failed", "true", str(bool(schema_status.get("stock_financial_fields_ready", True))).lower()),
        guard("passed_active_status_supported", "P0", "passed" if schema_status.get("passed_active_status_supported", True) else "failed", "true", str(bool(schema_status.get("passed_active_status_supported", True))).lower()),
        guard("active_run_conflict", "P0", "passed" if not active_run_status.get("blocked_by_active_run") else "failed", "no active run unless overwrite", str(bool(active_run_status.get("active_exists"))).lower()),
        guard("single_passed_active_per_date_pair", "P0", "passed" if not active_run_status.get("blocked_by_multiple_passed_active") else "failed", "0 or 1", str(active_run_status.get("canonical_active_run_count", 0))),
        guard("requested_run_id_available", "P0", "passed" if not run_id_status or run_id_status.get("run_id_available") else "failed", "0 existing rows for requested run_id", str((run_id_status or {}).get("total_existing_rows", 0))),
        guard("source_versions_complete", "P0", "passed" if source_version_status.get("complete") else "failed", "all required source versions", ",".join(source_version_status.get("missing_keys") or [])),
        guard("readiness_preconditions", "P0", "passed" if readiness_plan.get("execute_preconditions_passed") else "failed", "true", str(bool(readiness_plan.get("execute_preconditions_passed"))).lower()),
        guard("aggregate_p0_clean", "P0", "passed" if p0_count == 0 else "failed", "0", str(p0_count)),
        guard("user_confirmation", "P1", "passed" if not user_required or user_confirmed else "warning", "true when required", str(user_confirmed).lower()),
        guard("rollback_sql_preview_present", "P0", "passed" if rollback_sql_preview else "failed", ">0 rollback SQL templates", str(len(rollback_sql_preview))),
        guard("no_migration_performed", "P0", "passed", "false", "migration_performed=false"),
        guard("no_business_write", "P0", "passed", "false", "writes_performed=false"),
        guard("no_market_data_pull", "P0", "passed", "false", "minute_kline_pulled=false"),
    ]


def build_source_version_status(execute_contract: Mapping[str, Any]) -> dict[str, Any]:
    source_versions = dict(execute_contract.get("source_versions") or {})
    missing = [key for key in REQUIRED_SOURCE_VERSION_KEYS if key not in source_versions]
    return {
        "source_versions": source_versions,
        "required_keys": list(REQUIRED_SOURCE_VERSION_KEYS),
        "missing_keys": missing,
        "complete": not missing,
        "drift_check_required": True,
        "drift_check_performed": False,
        "status": "contract_frozen_pending_execute_recheck" if not missing else "source_version_incomplete",
    }


def guard(gate_code: str, severity: str, status: str, expected: str, actual: str) -> dict[str, str]:
    return {
        "gate_code": gate_code,
        "severity": severity,
        "status": status,
        "expected_value": expected,
        "actual_value": actual,
    }


def normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        else:
            output[key] = value
    return output
