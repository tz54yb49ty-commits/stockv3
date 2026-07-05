"""N4-1 trigger schema gap and migration review.

This module reviews the N4 trigger schema draft against PostgreSQL metadata
through a read-only connection. It never executes migration SQL, writes trigger
rows, consumes N3 events, pulls market data, starts workers, or enters N5/N6.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from ashare_v3.condition.basis import count_quality_severities, quality_item
from ashare_v3.market.schema_gap_plan import (
    CurrentSchemaMetadata,
    MissingColumn,
    MissingUniqueConstraint,
    TargetSchema,
    TypeMismatch,
    fetch_current_schema_metadata,
    normalize_type,
    parse_target_schema,
    unique_constraint_satisfied,
)
from ashare_v3.trigger.context_preflight import INPUT_EVENT_TYPES, TARGET_CONTEXT_TABLES


DEFAULT_TRIGGER_SCHEMA_PATH = "sql/010_trigger_layer_schema.sql"
DEFAULT_TRIGGER_SCHEMA_REVIEW_JSON_PATH = "docs/N4_1_trigger_schema_gap_plan.json"
DEFAULT_TRIGGER_SCHEMA_REVIEW_MD_PATH = "docs/N4_1_TRIGGER_SCHEMA_MIGRATION_REVIEW.md"
DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH = "sql/N4_2_trigger_schema_rollback.sql"

REQUIRED_TRIGGER_TABLES = (
    "common_trigger_run",
    "common_trigger_quality_item",
    "stock_trigger_context_snapshot",
    "index_trigger_context_snapshot",
    "board_trigger_context_snapshot",
    "common_trigger_state",
    "common_trigger_match",
)
N4_TRIGGER_MATCH_SCHEMA_EVENT_TYPES = ("TriggerMatched", "TriggerPendingMarketData")
N4_TRIGGER_MATCH_SCHEMA_PAYLOAD_KEYS = (
    "run_id",
    "source_event_id",
    "identity_key",
    "asset_kind",
    "direction",
    "condition_key",
    "signal_type",
    "trigger_period",
    "data_quality_status",
)
REQUIRED_DEPENDENCY_TABLES = (
    "common_condition_run",
    "stock_identity",
    "index_identity",
    "board_identity",
    "stock_condition_basis",
    "index_condition_basis",
    "board_condition_basis",
    "stock_condition_pool",
    "index_condition_pool",
    "board_condition_pool",
    "stock_minute_target_scope",
    "index_minute_target_scope",
    "board_minute_target_scope",
    "common_market_data_run",
    "common_market_data_subscription",
    "common_event_outbox",
)
REQUIRED_COLUMNS = {
    "common_trigger_run": (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "layer_role",
        "mode",
        "status",
        "market_data_pulled",
        "action_layer_touched",
        "user_layer_touched",
        "voice_touched",
        "sim_touched",
        "real_trade_touched",
        "worker_started",
    ),
    "common_trigger_quality_item": (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "source_trade_date",
        "data_domain",
        "layer_scope",
        "gate_code",
        "severity",
        "status",
    ),
    "stock_trigger_context_snapshot": (
        "run_id",
        "source_condition_run_id",
        "source_condition_pool_id",
        "source_condition_basis_id",
        "source_minute_target_scope_id",
        "identity_key",
        "stock_identity_key",
        "direction",
        "condition_key",
        "allowed_signal_types",
        "context_hash",
    ),
    "index_trigger_context_snapshot": (
        "run_id",
        "source_condition_run_id",
        "source_condition_pool_id",
        "source_condition_basis_id",
        "source_minute_target_scope_id",
        "identity_key",
        "index_identity_key",
        "direction",
        "condition_key",
        "allowed_signal_types",
        "context_hash",
    ),
    "board_trigger_context_snapshot": (
        "run_id",
        "source_condition_run_id",
        "source_condition_pool_id",
        "source_condition_basis_id",
        "source_minute_target_scope_id",
        "identity_key",
        "board_identity_key",
        "direction",
        "condition_key",
        "allowed_signal_types",
        "context_hash",
    ),
    "common_trigger_state": (
        "run_id",
        "source_condition_run_id",
        "for_trade_date",
        "asset_kind",
        "identity_key",
        "direction",
        "signal_type",
        "condition_key",
        "trigger_period",
        "trigger_bucket",
        "current_status",
        "data_quality_status",
    ),
    "common_trigger_match": (
        "run_id",
        "trigger_state_id",
        "source_event_id",
        "source_event_type",
        "source_condition_run_id",
        "asset_kind",
        "identity_key",
        "direction",
        "signal_type",
        "condition_key",
        "trigger_time",
        "trigger_period",
        "trigger_bucket",
        "data_quality_status",
        "output_event_type",
        "output_event_id",
        "dedup_key",
    ),
}
UNSAFE_SQL_PATTERNS = (
    r"(^|;)\s*DROP\b",
    r"(^|;)\s*INSERT\b",
    r"(^|;)\s*UPDATE\b",
    r"(^|;)\s*DELETE\b",
    r"(^|;)\s*TRUNCATE\b",
    r"(^|;)\s*COPY\b",
    r"\bCREATE\s+TRIGGER\b",
    r"(^|;)\s*ALTER\s+TABLE\b",
)
FORBIDDEN_OUTPUT_EVENTS = (
    "ActionEvent",
    "HintEvent",
    "RiskEvent",
    "PositionEvent",
)
FORBIDDEN_PREFIX_EVENT_LITERAL = re.compile(r"['\"](?:User|Voice|Sim)[A-Za-z0-9_]+['\"]")
FORBIDDEN_RUNTIME_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*_runtime\b", re.IGNORECASE)
FORBIDDEN_DOWNSTREAM_TABLE_PREFIXES = (
    "action_",
    "user_",
    "voice_",
    "sim_",
    "position_",
    "common_action_",
    "common_user_",
    "common_voice_",
    "common_sim_",
    "common_position_",
)


def build_trigger_schema_migration_review(
    *,
    dsn: str,
    schema_path: str = DEFAULT_TRIGGER_SCHEMA_PATH,
    rollback_sql_path: str = DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    target_schema = parse_target_schema((schema_path,))
    current_metadata = fetch_current_schema_metadata(
        dsn,
        target_table_names=target_schema.table_names,
        dependency_table_names=REQUIRED_DEPENDENCY_TABLES,
    )
    return build_trigger_schema_migration_review_from_metadata(
        target_schema=target_schema,
        current_metadata=current_metadata,
        schema_path=schema_path,
        rollback_sql_path=rollback_sql_path,
    )


def build_trigger_schema_migration_review_from_metadata(
    *,
    target_schema: TargetSchema,
    current_metadata: CurrentSchemaMetadata,
    schema_path: str = DEFAULT_TRIGGER_SCHEMA_PATH,
    rollback_sql_path: str = DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH,
) -> dict[str, Any]:
    schema_text = "\n".join(Path(path).read_text(encoding="utf-8") for path in target_schema.schema_paths)
    static_review = review_trigger_schema_sql(schema_text, target_schema=target_schema)
    existing_tables = set(current_metadata.existing_tables)
    missing_tables = tuple(table for table in REQUIRED_TRIGGER_TABLES if table not in existing_tables)
    extra_target_tables = tuple(table for table in target_schema.table_names if table not in REQUIRED_TRIGGER_TABLES)
    missing_columns, type_mismatches, missing_unique_constraints = compare_existing_tables(
        target_schema=target_schema,
        current_metadata=current_metadata,
    )
    all_target_tables_missing = len(missing_tables) == len(REQUIRED_TRIGGER_TABLES)
    no_target_tables_missing = len(missing_tables) == 0
    partial_existing_target_tables = bool(existing_tables) and not no_target_tables_missing
    metadata_clean = (
        not current_metadata.missing_dependency_tables
        and not missing_columns
        and not type_mismatches
        and not missing_unique_constraints
        and not partial_existing_target_tables
    )
    migration_required = bool(missing_tables or missing_columns or missing_unique_constraints)
    migration_safe_to_apply = bool(
        static_review["static_ready"]
        and metadata_clean
        and all_target_tables_missing
    )
    ready_for_n4_2_user_confirmation = migration_required and migration_safe_to_apply
    manual_review_required = bool(
        partial_existing_target_tables
        or missing_columns
        or type_mismatches
        or missing_unique_constraints
        or current_metadata.missing_dependency_tables
        or not static_review["static_ready"]
    )
    rollback_sql_preview = build_trigger_schema_rollback_sql()
    quality_items = build_quality_items(
        static_review=static_review,
        current_metadata=current_metadata,
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        type_mismatches=type_mismatches,
        missing_unique_constraints=missing_unique_constraints,
        extra_target_tables=extra_target_tables,
        all_target_tables_missing=all_target_tables_missing,
        partial_existing_target_tables=partial_existing_target_tables,
        migration_safe_to_apply=migration_safe_to_apply,
        manual_review_required=manual_review_required,
    )
    severity_counts = count_quality_severities(quality_items)
    return {
        "stage": "N4-1",
        "layer_role": "N4_trigger",
        "plan_mode": "trigger_schema_gap_migration_review",
        "schema_path": schema_path,
        "rollback_sql_path": rollback_sql_path,
        "schema_hash": static_review["schema_hash"],
        "checked_readonly": current_metadata.checked_readonly,
        "will_execute_sql": False,
        "migration_executed": False,
        "writes_performed": False,
        "market_data_pulled": False,
        "n3_event_consumed": False,
        "trigger_context_snapshot_written": False,
        "trigger_state_written": False,
        "trigger_match_written": False,
        "event_outbox_written": False,
        "downstream_layers_touched": False,
        "worker_started": False,
        "old_system_touched": False,
        "migration_required": migration_required,
        "ready_for_n4_2_user_confirmation": ready_for_n4_2_user_confirmation,
        "migration_safe_to_apply_after_user_confirmation": migration_safe_to_apply,
        "manual_review_required": manual_review_required,
        "target_tables": list(REQUIRED_TRIGGER_TABLES),
        "target_tables_existing": list(current_metadata.existing_tables),
        "target_tables_missing": list(missing_tables),
        "all_target_tables_missing": all_target_tables_missing,
        "partial_existing_target_tables": partial_existing_target_tables,
        "missing_dependency_tables": list(current_metadata.missing_dependency_tables),
        "missing_columns": [item.to_dict() for item in missing_columns],
        "type_mismatch": [item.to_dict() for item in type_mismatches],
        "missing_unique_constraints": [item.to_dict() for item in missing_unique_constraints],
        "static_review": static_review,
        "backup_requirements": build_backup_requirements(),
        "rollback_requirements": build_rollback_requirements(rollback_sql_path),
        "rollback_sql_preview": rollback_sql_preview,
        "quality": {
            "p0_count": severity_counts["P0"],
            "p1_count": severity_counts["P1"],
            "p2_count": severity_counts["P2"],
            "items": quality_items,
        },
        "passed": severity_counts["P0"] == 0,
        "side_effects": {
            "read_only_database_checks": current_metadata.checked_readonly,
            "will_execute_sql": False,
            "migration_executed": False,
            "writes_performed": False,
            "market_data_pulled": False,
            "n3_event_consumed": False,
            "trigger_context_snapshot_written": False,
            "trigger_state_written": False,
            "trigger_match_written": False,
            "event_outbox_written": False,
            "downstream_layers_touched": False,
            "worker_started": False,
            "old_system_touched": False,
        },
    }


def review_trigger_schema_sql(sql_text: str, *, target_schema: TargetSchema | None = None) -> dict[str, Any]:
    executable_sql = strip_line_comments(sql_text)
    created_tables = tuple(extract_create_table_names(executable_sql))
    created_table_set = set(created_tables)
    required_table_set = set(REQUIRED_TRIGGER_TABLES)
    required_tables_missing = tuple(table for table in REQUIRED_TRIGGER_TABLES if table not in created_table_set)
    extra_created_tables = tuple(table for table in created_tables if table not in required_table_set)
    forbidden_downstream_table_hits = tuple(
        table
        for table in created_tables
        if table.lower().startswith(FORBIDDEN_DOWNSTREAM_TABLE_PREFIXES)
    )
    forbidden_output_event_hits = tuple(
        event_type
        for event_type in FORBIDDEN_OUTPUT_EVENTS
        if re.search(rf"['\"]{event_type}['\"]", executable_sql)
    )
    forbidden_prefix_event_hits = tuple(match.group(0) for match in FORBIDDEN_PREFIX_EVENT_LITERAL.finditer(executable_sql))
    runtime_identifier_hits = tuple(match.group(0) for match in FORBIDDEN_RUNTIME_IDENTIFIER.finditer(executable_sql))
    unsafe_sql_hits = tuple(
        pattern
        for pattern in UNSAFE_SQL_PATTERNS
        if re.search(pattern, executable_sql, flags=re.IGNORECASE)
    )
    missing_columns_by_table = {
        table: sorted(set(REQUIRED_COLUMNS[table]) - set(extract_columns_for_table(executable_sql, table)))
        for table in REQUIRED_TRIGGER_TABLES
    }
    missing_columns_by_table = {
        table: columns for table, columns in missing_columns_by_table.items() if columns
    }
    output_event_contract_present = all(
        event_type in executable_sql for event_type in N4_TRIGGER_MATCH_SCHEMA_EVENT_TYPES
    )
    input_event_contract_present = all(event_type in executable_sql for event_type in INPUT_EVENT_TYPES)
    payload_contract_present = all(
        key in executable_sql for key in N4_TRIGGER_MATCH_SCHEMA_PAYLOAD_KEYS
    )
    boundary_guard_columns_present = all(
        token in executable_sql
        for token in (
            "market_data_pulled",
            "action_layer_touched",
            "user_layer_touched",
            "voice_touched",
            "sim_touched",
            "real_trade_touched",
            "worker_started",
        )
    )
    context_tables_present = all(table in created_table_set for table in TARGET_CONTEXT_TABLES.values())
    additive_create_only = bool(created_tables) and not unsafe_sql_hits
    static_ready = (
        additive_create_only
        and not required_tables_missing
        and not extra_created_tables
        and not forbidden_downstream_table_hits
        and not forbidden_output_event_hits
        and not forbidden_prefix_event_hits
        and not runtime_identifier_hits
        and not missing_columns_by_table
        and output_event_contract_present
        and input_event_contract_present
        and payload_contract_present
        and boundary_guard_columns_present
        and context_tables_present
    )
    schema_hash = sha256(sql_text.encode("utf-8")).hexdigest()
    if target_schema is not None:
        schema_hash = sha256(json.dumps(target_schema.to_dict(), sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "schema_hash": schema_hash,
        "created_tables": list(created_tables),
        "required_tables": list(REQUIRED_TRIGGER_TABLES),
        "required_tables_missing": list(required_tables_missing),
        "extra_created_tables": list(extra_created_tables),
        "unsafe_sql_hits": list(unsafe_sql_hits),
        "runtime_identifier_hits": list(runtime_identifier_hits),
        "forbidden_downstream_table_hits": list(forbidden_downstream_table_hits),
        "forbidden_output_event_hits": list(forbidden_output_event_hits),
        "forbidden_prefix_event_hits": list(forbidden_prefix_event_hits),
        "missing_columns_by_table": missing_columns_by_table,
        "output_event_contract_present": output_event_contract_present,
        "input_event_contract_present": input_event_contract_present,
        "payload_contract_present": payload_contract_present,
        "boundary_guard_columns_present": boundary_guard_columns_present,
        "context_tables_present": context_tables_present,
        "additive_create_only": additive_create_only,
        "static_ready": static_ready,
    }


def compare_existing_tables(
    *,
    target_schema: TargetSchema,
    current_metadata: CurrentSchemaMetadata,
) -> tuple[tuple[MissingColumn, ...], tuple[TypeMismatch, ...], tuple[MissingUniqueConstraint, ...]]:
    current_tables = set(current_metadata.existing_tables)
    missing_columns: list[MissingColumn] = []
    type_mismatches: list[TypeMismatch] = []
    missing_unique_constraints: list[MissingUniqueConstraint] = []
    for table_name, target_table in target_schema.tables.items():
        if table_name not in current_tables:
            continue
        current_columns = current_metadata.columns_by_table.get(table_name, {})
        for column_name, target_column in target_table.columns.items():
            current_column = current_columns.get(column_name)
            if current_column is None:
                missing_columns.append(
                    MissingColumn(
                        table_name=table_name,
                        column_name=column_name,
                        migration_type=target_column.migration_type,
                        target_nullable=target_column.nullable,
                        target_has_default=target_column.has_default,
                        target_has_check=target_column.has_check,
                        target_has_references=target_column.has_references,
                        additive_safe=target_column.additive_safe,
                    )
                )
            elif normalize_type(target_column.target_type) != normalize_type(current_column.formatted_type):
                type_mismatches.append(
                    TypeMismatch(
                        table_name=table_name,
                        column_name=column_name,
                        target_type=target_column.target_type,
                        current_type=current_column.formatted_type,
                    )
                )
        current_uniques = current_metadata.unique_constraints_by_table.get(table_name, ())
        for target_unique in target_table.unique_constraints:
            if not unique_constraint_satisfied(target_unique, current_uniques):
                missing_unique_constraints.append(MissingUniqueConstraint.from_target(target_unique))
    return tuple(missing_columns), tuple(type_mismatches), tuple(missing_unique_constraints)


def build_quality_items(
    *,
    static_review: Mapping[str, Any],
    current_metadata: CurrentSchemaMetadata,
    missing_tables: tuple[str, ...],
    missing_columns: tuple[MissingColumn, ...],
    type_mismatches: tuple[TypeMismatch, ...],
    missing_unique_constraints: tuple[MissingUniqueConstraint, ...],
    extra_target_tables: tuple[str, ...],
    all_target_tables_missing: bool,
    partial_existing_target_tables: bool,
    migration_safe_to_apply: bool,
    manual_review_required: bool,
) -> list[dict[str, Any]]:
    no_migration_needed = bool(
        static_review["static_ready"]
        and not current_metadata.missing_dependency_tables
        and not missing_tables
        and not missing_columns
        and not type_mismatches
        and not missing_unique_constraints
        and not manual_review_required
    )
    return [
        quality_item(
            "P0",
            "passed" if current_metadata.checked_readonly else "failed",
            "n4_1_readonly_metadata_checked",
            "N4-1 must use a read-only PostgreSQL metadata check",
            expected="checked_readonly=true",
            actual=str(current_metadata.checked_readonly).lower(),
        ),
        quality_item(
            "P0",
            "passed" if not static_review["unsafe_sql_hits"] else "failed",
            "n4_schema_no_dml_or_destructive_sql",
            "010 trigger schema must not contain DML, destructive SQL, ALTER, or CREATE TRIGGER",
            expected="no DROP/INSERT/UPDATE/DELETE/TRUNCATE/COPY/ALTER/CREATE TRIGGER",
            actual="none" if not static_review["unsafe_sql_hits"] else ",".join(static_review["unsafe_sql_hits"]),
        ),
        quality_item(
            "P0",
            "passed" if not static_review["runtime_identifier_hits"] else "failed",
            "n4_schema_no_runtime_table_names",
            "N4 formal table names must not use *_runtime",
            expected="no *_runtime identifiers",
            actual="none" if not static_review["runtime_identifier_hits"] else ",".join(static_review["runtime_identifier_hits"]),
        ),
        quality_item(
            "P0",
            "passed" if not static_review["forbidden_downstream_table_hits"] else "failed",
            "n4_schema_no_downstream_tables",
            "N4 schema must not create or reference action/user/voice/sim/position tables as N4 targets",
            expected="no downstream table identifiers",
            actual=(
                "none"
                if not static_review["forbidden_downstream_table_hits"]
                else ",".join(static_review["forbidden_downstream_table_hits"])
            ),
        ),
        quality_item(
            "P0",
            "passed" if not static_review["forbidden_output_event_hits"] and not static_review["forbidden_prefix_event_hits"] else "failed",
            "n4_schema_no_downstream_events",
            "N4 schema/event contract must not output ActionEvent/User*/Voice*/Sim* events",
            expected="only N4 trigger-layer event types",
            actual="none" if not static_review["forbidden_output_event_hits"] and not static_review["forbidden_prefix_event_hits"] else str(static_review),
        ),
        quality_item(
            "P0",
            "passed" if not static_review["required_tables_missing"] and not extra_target_tables else "failed",
            "n4_schema_required_tables_only",
            "010 schema must create exactly the N4 target trigger tables",
            expected=",".join(REQUIRED_TRIGGER_TABLES),
            actual=f"missing={static_review['required_tables_missing']} extra={list(extra_target_tables)}",
        ),
        quality_item(
            "P0",
            "passed" if not current_metadata.missing_dependency_tables else "failed",
            "n4_dependency_tables_exist",
            "N4 schema requires N2/N3/event dependency tables to exist before 010 migration",
            expected=",".join(REQUIRED_DEPENDENCY_TABLES),
            actual="present" if not current_metadata.missing_dependency_tables else ",".join(current_metadata.missing_dependency_tables),
        ),
        quality_item(
            "P0",
            "passed" if not partial_existing_target_tables else "failed",
            "n4_no_partial_target_table_state",
            "Executing 010 directly is only safe when all N4 target tables are absent",
            expected="all N4 target tables missing before first apply",
            actual="all_missing" if all_target_tables_missing else f"missing={list(missing_tables)} existing={list(current_metadata.existing_tables)}",
        ),
        quality_item(
            "P0",
            "passed" if not type_mismatches else "failed",
            "n4_schema_no_type_mismatch",
            "Existing N4 tables must not disagree with 010 column types",
            expected="no type mismatch",
            actual="none" if not type_mismatches else str([item.to_dict() for item in type_mismatches]),
        ),
        quality_item(
            "P0",
            "passed" if not missing_columns else "failed",
            "n4_schema_no_existing_table_column_gap_for_010",
            "010 is a first-apply schema; existing N4 table column gaps require a separate additive migration",
            expected="no missing columns on existing N4 tables",
            actual="none" if not missing_columns else str([item.to_dict() for item in missing_columns]),
        ),
        quality_item(
            "P0",
            "passed" if not missing_unique_constraints else "failed",
            "n4_schema_no_existing_unique_gap_for_010",
            "Existing N4 unique constraint gaps require duplicate-risk review before any migration",
            expected="no missing unique constraints on existing N4 tables",
            actual="none" if not missing_unique_constraints else str([item.to_dict() for item in missing_unique_constraints]),
        ),
        quality_item(
            "P1",
            "warning" if missing_tables else "passed",
            "n4_schema_missing_tables",
            "Missing N4 tables require explicit N4-2 migration confirmation",
            expected="all target tables exist, or first-apply migration is planned",
            actual="none" if not missing_tables else ",".join(missing_tables),
        ),
        quality_item(
            "P1",
            "passed" if migration_safe_to_apply or no_migration_needed else "warning",
            "n4_schema_migration_safe_to_apply_after_confirmation",
            "010 can be applied only after explicit user confirmation and backup; no-op when already applied cleanly",
            expected="migration_safe_to_apply_after_user_confirmation=true or no migration required",
            actual=(
                f"migration_safe_to_apply_after_user_confirmation={str(migration_safe_to_apply).lower()} "
                f"no_migration_needed={str(no_migration_needed).lower()}"
            ),
        ),
        quality_item(
            "P1",
            "warning" if manual_review_required else "passed",
            "n4_schema_manual_review_required",
            "Manual review is required when target DB state is not a clean first-apply",
            expected="manual_review_required=false for clean first apply",
            actual=str(manual_review_required).lower(),
        ),
        quality_item("P0", "passed", "n4_1_no_migration_execute", "N4-1 does not execute migration SQL"),
        quality_item("P0", "passed", "n4_1_no_trigger_data_write", "N4-1 does not write trigger context/state/match rows"),
        quality_item("P0", "passed", "n4_1_no_market_data_pull", "N4-1 does not pull market data"),
        quality_item("P0", "passed", "n4_1_no_n3_event_consumption", "N4-1 does not consume N3 events"),
        quality_item("P0", "passed", "n4_1_no_worker_or_downstream", "N4-1 does not start workers or enter N5/N6"),
    ]


def build_backup_requirements() -> dict[str, Any]:
    return {
        "required_before_n4_2": True,
        "minimum_backup": [
            "schema-only dump or DDL snapshot for public schema",
            "table existence snapshot for N4 target tables",
            "dependency table existence snapshot for N2/N3/event tables",
        ],
        "recommended_command_template": "pg_dump --schema-only --no-owner --no-privileges --file backups/n4_2_schema_before_YYYYMMDD_HHMMSS.sql \"$ASHARE_V3_POSTGRES_DSN\"",
        "must_recheck_immediately_before_execute": [
            "all N4 target tables are still absent",
            "all dependency tables still exist",
            "010 static review still has P0=0",
        ],
    }


def build_rollback_requirements(rollback_sql_path: str) -> dict[str, Any]:
    return {
        "rollback_sql_path": rollback_sql_path,
        "generated_preview_only": True,
        "allowed_only_before_business_rows": True,
        "drops_only_n4_schema_objects": True,
        "does_not_touch_n1_n2_n3_facts": True,
        "does_not_delete_common_event_outbox": True,
        "requires_user_confirmation_before_execution": True,
    }


def build_trigger_schema_rollback_sql() -> str:
    lines = [
        "-- A-share monitor v3 N4 trigger schema rollback preview.",
        "-- Generated in N4-1 for review only. Do not execute unless N4-2 migration",
        "-- has been explicitly confirmed and no N4 business rows have been written.",
        "-- This rollback drops only N4 trigger-layer schema objects.",
        "",
        "BEGIN;",
        "",
        "DROP TABLE IF EXISTS common_trigger_match;",
        "DROP TABLE IF EXISTS common_trigger_state;",
        "DROP TABLE IF EXISTS board_trigger_context_snapshot;",
        "DROP TABLE IF EXISTS index_trigger_context_snapshot;",
        "DROP TABLE IF EXISTS stock_trigger_context_snapshot;",
        "DROP TABLE IF EXISTS common_trigger_quality_item;",
        "DROP TABLE IF EXISTS common_trigger_run;",
        "",
        "COMMIT;",
        "",
        "-- Boundary:",
        "-- - Does not touch common_condition_run or condition tables.",
        "-- - Does not touch common_market_data_* or market data fact tables.",
        "-- - Does not touch common_event_outbox.",
        "-- - Does not touch action/user/voice/sim/position tables.",
    ]
    return "\n".join(lines) + "\n"


def write_trigger_schema_review_files(
    report: Mapping[str, Any],
    *,
    report_path: str = DEFAULT_TRIGGER_SCHEMA_REVIEW_JSON_PATH,
    markdown_report_path: str = DEFAULT_TRIGGER_SCHEMA_REVIEW_MD_PATH,
    rollback_sql_path: str = DEFAULT_TRIGGER_SCHEMA_ROLLBACK_SQL_PATH,
) -> None:
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    Path(markdown_report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(markdown_report_path).write_text(format_trigger_schema_review_markdown(report), encoding="utf-8")
    Path(rollback_sql_path).parent.mkdir(parents=True, exist_ok=True)
    Path(rollback_sql_path).write_text(str(report["rollback_sql_preview"]), encoding="utf-8")


def format_trigger_schema_review_markdown(report: Mapping[str, Any]) -> str:
    quality = report["quality"]
    side_effects = report["side_effects"]
    lines = [
        "# N4-1 Trigger Schema Migration Review",
        "",
        "## Summary",
        "",
        f"- stage: {report['stage']}",
        f"- layer_role: {report['layer_role']}",
        f"- schema_path: {report['schema_path']}",
        f"- rollback_sql_path: {report['rollback_sql_path']}",
        f"- checked_readonly: {str(report['checked_readonly']).lower()}",
        f"- migration_required: {str(report['migration_required']).lower()}",
        f"- ready_for_n4_2_user_confirmation: {str(report['ready_for_n4_2_user_confirmation']).lower()}",
        f"- migration_safe_to_apply_after_user_confirmation: {str(report['migration_safe_to_apply_after_user_confirmation']).lower()}",
        f"- manual_review_required: {str(report['manual_review_required']).lower()}",
        f"- P0/P1/P2: {quality['p0_count']}/{quality['p1_count']}/{quality['p2_count']}",
        "",
        "## Gap Plan",
        "",
        f"- target_tables_existing: {report['target_tables_existing']}",
        f"- target_tables_missing: {report['target_tables_missing']}",
        f"- missing_dependency_tables: {report['missing_dependency_tables']}",
        f"- missing_columns: {report['missing_columns']}",
        f"- type_mismatch: {report['type_mismatch']}",
        f"- missing_unique_constraints: {report['missing_unique_constraints']}",
        "",
        "## Backup And Rollback",
        "",
        f"- backup_requirements: {report['backup_requirements']}",
        f"- rollback_requirements: {report['rollback_requirements']}",
        "",
        "## Quality",
        "",
    ]
    for item in quality["items"]:
        lines.append(
            f"- {item['severity']} {item['status']} {item['gate_code']}: "
            f"expected={item.get('expected_value')} actual={item.get('actual_value')}"
        )
    lines.extend(
        [
            "",
            "## Boundary Confirmation",
            "",
            f"- read_only_database_checks: {str(side_effects['read_only_database_checks']).lower()}",
            f"- will_execute_sql: {str(side_effects['will_execute_sql']).lower()}",
            f"- migration_executed: {str(side_effects['migration_executed']).lower()}",
            f"- writes_performed: {str(side_effects['writes_performed']).lower()}",
            f"- market_data_pulled: {str(side_effects['market_data_pulled']).lower()}",
            f"- n3_event_consumed: {str(side_effects['n3_event_consumed']).lower()}",
            f"- trigger_context_snapshot_written: {str(side_effects['trigger_context_snapshot_written']).lower()}",
            f"- trigger_state_written: {str(side_effects['trigger_state_written']).lower()}",
            f"- trigger_match_written: {str(side_effects['trigger_match_written']).lower()}",
            f"- event_outbox_written: {str(side_effects['event_outbox_written']).lower()}",
            f"- downstream_layers_touched: {str(side_effects['downstream_layers_touched']).lower()}",
            f"- worker_started: {str(side_effects['worker_started']).lower()}",
            f"- old_system_touched: {str(side_effects['old_system_touched']).lower()}",
            "",
            "## Rollback",
            "",
            "N4-1 did not execute migration SQL and did not write database rows. "
            "Rollback for this stage is deleting the generated N4-1 report files and rollback SQL preview.",
            "",
        ]
    )
    return "\n".join(lines)


def strip_line_comments(sql_text: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql_text.splitlines())


def extract_create_table_names(sql_text: str) -> list[str]:
    return re.findall(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\b",
        sql_text,
        flags=re.IGNORECASE,
    )


def extract_columns_for_table(sql_text: str, table_name: str) -> tuple[str, ...]:
    body = extract_create_table_body(sql_text, table_name)
    if body is None:
        return ()
    columns: list[str] = []
    for part in split_top_level_commas(body):
        match = re.match(r'"?([A-Za-z_][A-Za-z0-9_]*)"?\s+', part.strip())
        if match is None:
            continue
        column = match.group(1).lower()
        if column not in {"primary", "unique", "check", "foreign", "constraint", "exclude"}:
            columns.append(column)
    return tuple(columns)


def extract_create_table_body(sql_text: str, table_name: str) -> str | None:
    pattern = re.compile(
        rf"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{re.escape(table_name)}\s*\(",
        re.IGNORECASE,
    )
    match = pattern.search(sql_text)
    if match is None:
        return None
    open_paren_index = match.end() - 1
    close_paren_index = find_matching_paren(sql_text, open_paren_index)
    if close_paren_index < 0:
        return None
    return sql_text[open_paren_index + 1 : close_paren_index]


def find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    in_single_quote = False
    index = open_index
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if char == "'" and next_char == "'":
            index += 2
            continue
        if char == "'":
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    return -1


def split_top_level_commas(body: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_single_quote = False
    index = 0
    while index < len(body):
        char = body[index]
        next_char = body[index + 1] if index + 1 < len(body) else ""
        if char == "'" and next_char == "'":
            index += 2
            continue
        if char == "'":
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(body[start:index].strip())
                start = index + 1
        index += 1
    tail = body[start:].strip()
    if tail:
        parts.append(tail)
    return parts
