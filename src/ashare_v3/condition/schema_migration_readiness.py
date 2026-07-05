"""Static and read-only readiness checks for condition-layer schema migration.

N2-E2A explains whether the condition-layer SQL draft is ready to be reviewed
for a future development-database migration. It never executes SQL, writes
condition tables, pulls market data, or touches downstream layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Mapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.execute_preflight import REQUIRED_SCHEMA_TABLES
from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.schema_readiness import parse_create_tables


DEFAULT_CONDITION_SCHEMA_PATH = "sql/002_condition_layer_schema.sql"
CANONICAL_N2_SIGNAL_LITERALS = ("BUY", "SELL", "BUY:FULL", "SELL:FULL", "BUY_HINT", "SELL_HINT")
FOREIGN_KEY_DEPENDENCY_TABLES = (
    "common_ingest_batch",
    "stock_identity",
    "index_identity",
    "board_identity",
)
RUNTIME_DEPENDENCY_OBJECTS = (
    "common_active_source_version",
    "common_condition_active_source_version_view",
    "common_trade_calendar",
)
EXPECTED_ASSET_TABLE_GROUPS = {
    "monitor_target": ("stock_monitor_target", "index_monitor_target", "board_monitor_target"),
    "condition_basis": ("stock_condition_basis", "index_condition_basis", "board_condition_basis"),
    "condition_pool": ("stock_condition_pool", "index_condition_pool", "board_condition_pool"),
    "minute_target_scope": ("stock_minute_target_scope", "index_minute_target_scope", "board_minute_target_scope"),
}
REQUIRED_COLUMN_GROUPS = {
    "common_condition_run": (
        "run_id",
        "for_trade_date",
        "source_trade_date",
        "prev_trade_date",
        "source_versions",
        "mode",
        "status",
        "p0_count",
        "p1_count",
        "p2_count",
    ),
    "common_condition_quality_item": (
        "run_id",
        "for_trade_date",
        "source_trade_date",
        "data_domain",
        "layer_scope",
        "gate_code",
        "severity",
        "status",
    ),
    "stock_monitor_target": ("stock_identity_key", "for_trade_date", "source_trade_date", "lane", "direction_scope", "source_version"),
    "index_monitor_target": ("index_identity_key", "for_trade_date", "source_trade_date", "lane", "direction_scope", "source_version"),
    "board_monitor_target": ("board_identity_key", "for_trade_date", "source_trade_date", "lane", "direction_scope", "source_version"),
    "stock_condition_basis": (
        "run_id",
        "stock_identity_key",
        "source_monitor_target_id",
        "is_st",
        "stock_status",
        "official_daily_proof",
        "period_grade_d",
        "buy_target_price",
        "sell_target_price",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "buy_necessary_base",
        "sell_necessary_base",
        "buy_full_necessary_base",
        "sell_full_necessary_base",
        "oversold_hint_necessary_base",
        "overbought_hint_necessary_base",
        "financial_quality_status",
        "source_version",
    ),
    "index_condition_basis": (
        "run_id",
        "index_identity_key",
        "source_monitor_target_id",
        "period_grade_d",
        "buy_target_price",
        "sell_target_price",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "buy_necessary_base",
        "sell_necessary_base",
        "buy_full_necessary_base",
        "sell_full_necessary_base",
        "oversold_hint_necessary_base",
        "overbought_hint_necessary_base",
        "source_version",
    ),
    "board_condition_basis": (
        "run_id",
        "board_identity_key",
        "source_monitor_target_id",
        "period_grade_d",
        "buy_target_price",
        "sell_target_price",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "buy_necessary_base",
        "sell_necessary_base",
        "buy_full_necessary_base",
        "sell_full_necessary_base",
        "oversold_hint_necessary_base",
        "overbought_hint_necessary_base",
        "source_version",
    ),
    "stock_condition_pool": (
        "run_id",
        "stock_identity_key",
        "direction",
        "condition_key",
        "condition_periods",
        "allowed_signal_types",
        "is_hint_scope",
        "policy_name",
        "policy_hash",
        "selected_reason",
        "excluded_reason",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "source_condition_basis_id",
        "source_version",
    ),
    "index_condition_pool": (
        "run_id",
        "index_identity_key",
        "direction",
        "condition_key",
        "condition_periods",
        "allowed_signal_types",
        "is_hint_scope",
        "policy_name",
        "policy_hash",
        "selected_reason",
        "excluded_reason",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "source_condition_basis_id",
        "source_version",
    ),
    "board_condition_pool": (
        "run_id",
        "board_identity_key",
        "direction",
        "condition_key",
        "condition_periods",
        "allowed_signal_types",
        "is_hint_scope",
        "policy_name",
        "policy_hash",
        "selected_reason",
        "excluded_reason",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "source_condition_basis_id",
        "source_version",
    ),
    "stock_minute_target_scope": (
        "run_id",
        "stock_identity_key",
        "direction",
        "condition_key",
        "allowed_signal_types",
        "scope_source",
        "source_condition_pool_id",
        "total_mv",
        "market_value_threshold",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "previous_day_minute_required",
        "previous_day_minute_date",
        "previous_day_minute_quality_required",
        "market_data_consumer",
    ),
    "index_minute_target_scope": (
        "run_id",
        "index_identity_key",
        "direction",
        "condition_key",
        "allowed_signal_types",
        "scope_source",
        "source_condition_pool_id",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "previous_day_minute_required",
        "previous_day_minute_date",
        "previous_day_minute_quality_required",
        "market_data_consumer",
    ),
    "board_minute_target_scope": (
        "run_id",
        "board_identity_key",
        "direction",
        "condition_key",
        "allowed_signal_types",
        "scope_source",
        "source_condition_pool_id",
        "up_sell_reference_period",
        "down_buy_reference_period",
        "clear_sell_ref_period",
        "previous_day_minute_required",
        "previous_day_minute_date",
        "previous_day_minute_quality_required",
        "market_data_consumer",
    ),
}
FORBIDDEN_EXACT_TABLES = (
    "condition_basis",
    "condition_pool",
    "minute_target_scope",
    "daily_bar_fact",
)
DANGEROUS_SQL_PATTERNS = (
    r"\bCREATE\s+TRIGGER\b",
    r"\bCREATE\s+TABLE\s+[A-Za-z_][A-Za-z0-9_]*action[A-Za-z0-9_]*\b",
    r"\bCREATE\s+TABLE\s+[A-Za-z_][A-Za-z0-9_]*voice[A-Za-z0-9_]*\b",
    r"\bCREATE\s+TABLE\s+[A-Za-z_][A-Za-z0-9_]*sim[A-Za-z0-9_]*\b",
    r"\bCREATE\s+TABLE\s+[A-Za-z_][A-Za-z0-9_]*worker[A-Za-z0-9_]*\b",
)


@dataclass(frozen=True)
class ConditionSchemaTableSummary:
    table_name: str
    column_names: tuple[str, ...]
    missing_required_columns: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.missing_required_columns

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "column_count": len(self.column_names),
            "column_names": list(self.column_names),
            "missing_required_columns": list(self.missing_required_columns),
            "ready": self.ready,
        }


@dataclass(frozen=True)
class ConditionSchemaMigrationReadinessReport:
    stage: str
    plan_mode: str
    schema_path: str
    schema_hash: str
    table_count: int
    index_count: int
    table_summaries: tuple[ConditionSchemaTableSummary, ...]
    quality_gates: tuple[QualityGateResult, ...]
    database_status: Mapping[str, Any] | None = None
    dry_run_only: bool = True
    will_connect_database: bool = False
    read_only_database_checks: bool = False
    will_execute_sql: bool = False
    migration_performed: bool = False
    writes_performed: bool = False
    minute_kline_pulled: bool = False
    downstream_layers_touched: bool = False

    @property
    def static_ready(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    @property
    def database_ready_for_first_apply(self) -> bool | None:
        if not self.database_status:
            return None
        return bool(self.database_status.get("ready_for_first_apply"))

    @property
    def ready_for_user_migration_review(self) -> bool:
        database_ready = self.database_ready_for_first_apply
        return self.static_ready if database_ready is None else self.static_ready and database_ready

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "plan_mode": self.plan_mode,
            "schema_path": self.schema_path,
            "schema_hash": self.schema_hash,
            "table_count": self.table_count,
            "index_count": self.index_count,
            "required_tables": list(REQUIRED_SCHEMA_TABLES),
            "foreign_key_dependency_tables": list(FOREIGN_KEY_DEPENDENCY_TABLES),
            "runtime_dependency_objects": list(RUNTIME_DEPENDENCY_OBJECTS),
            "static_ready": self.static_ready,
            "ready_for_user_migration_review": self.ready_for_user_migration_review,
            "table_summaries": [summary.to_dict() for summary in self.table_summaries],
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "database_status": dict(self.database_status or {}),
            "side_effects": {
                "dry_run_only": self.dry_run_only,
                "will_connect_database": self.will_connect_database,
                "read_only_database_checks": self.read_only_database_checks,
                "will_execute_sql": self.will_execute_sql,
                "migration_performed": self.migration_performed,
                "writes_performed": self.writes_performed,
                "minute_kline_pulled": self.minute_kline_pulled,
                "downstream_layers_touched": self.downstream_layers_touched,
            },
        }


def build_condition_schema_migration_readiness_report(
    *,
    schema_path: str | Path = DEFAULT_CONDITION_SCHEMA_PATH,
    database_status: Mapping[str, Any] | None = None,
) -> ConditionSchemaMigrationReadinessReport:
    path = Path(schema_path)
    sql_text = path.read_text(encoding="utf-8")
    return build_condition_schema_migration_readiness_report_from_sql(
        sql_text,
        schema_path=str(schema_path),
        database_status=database_status,
    )


def build_condition_schema_migration_readiness_report_from_sql(
    sql_text: str,
    *,
    schema_path: str = "<memory>",
    database_status: Mapping[str, Any] | None = None,
) -> ConditionSchemaMigrationReadinessReport:
    tables = parse_create_tables(sql_text)
    summaries = tuple(build_table_summaries(tables))
    gates = tuple(build_quality_gates(sql_text, tables, summaries))
    return ConditionSchemaMigrationReadinessReport(
        stage="N2-E2A",
        plan_mode="condition_schema_migration_readiness",
        schema_path=schema_path,
        schema_hash=sha256(sql_text.encode("utf-8")).hexdigest(),
        table_count=len(tables),
        index_count=parse_create_index_count(sql_text),
        table_summaries=summaries,
        quality_gates=gates,
        database_status=database_status,
        will_connect_database=database_status is not None,
        read_only_database_checks=database_status is not None,
    )


def build_table_summaries(tables: Mapping[str, tuple[str, ...]]) -> list[ConditionSchemaTableSummary]:
    summaries: list[ConditionSchemaTableSummary] = []
    for table_name in REQUIRED_SCHEMA_TABLES:
        columns = tables.get(table_name, ())
        required_columns = REQUIRED_COLUMN_GROUPS.get(table_name, ())
        summaries.append(
            ConditionSchemaTableSummary(
                table_name=table_name,
                column_names=columns,
                missing_required_columns=tuple(column for column in required_columns if column not in columns),
            )
        )
    return summaries


def build_quality_gates(
    sql_text: str,
    tables: Mapping[str, tuple[str, ...]],
    summaries: tuple[ConditionSchemaTableSummary, ...],
) -> list[QualityGateResult]:
    table_names = set(tables)
    missing_tables = sorted(set(REQUIRED_SCHEMA_TABLES) - table_names)
    forbidden_tables = sorted(table for table in FORBIDDEN_EXACT_TABLES if table in table_names)
    dangerous_pattern_hits = [
        pattern
        for pattern in DANGEROUS_SQL_PATTERNS
        if re.search(pattern, sql_text, flags=re.IGNORECASE)
    ]
    missing_required_columns = {
        summary.table_name: list(summary.missing_required_columns)
        for summary in summaries
        if summary.missing_required_columns
    }
    asset_group_failures = {
        group_name: [table for table in group_tables if table not in table_names]
        for group_name, group_tables in EXPECTED_ASSET_TABLE_GROUPS.items()
        if any(table not in table_names for table in group_tables)
    }
    external_reference_tables = sorted(parse_reference_tables(sql_text) - set(REQUIRED_SCHEMA_TABLES))
    missing_fk_dependencies_in_sql = sorted(set(FOREIGN_KEY_DEPENDENCY_TABLES) - set(external_reference_tables))
    signal_literals = parse_sql_array_literals(sql_text)
    signal_whitelist_ready = all(signal in signal_literals for signal in CANONICAL_N2_SIGNAL_LITERALS)
    transaction_ready = has_single_begin_commit(sql_text)
    prev_trade_date_ready = "previous_day_minute_date = prev_trade_date" in sql_text
    stock_mv_scope_ready = "total_mv >= market_value_threshold" in sql_text
    source_prev_guard_ready = "source_trade_date = prev_trade_date" in sql_text

    return [
        QualityGateResult(
            gate_name="condition_schema_required_tables_present",
            status="passed" if not missing_tables else "failed",
            expected_value=str(len(REQUIRED_SCHEMA_TABLES)),
            actual_value=str(len(REQUIRED_SCHEMA_TABLES) - len(missing_tables)),
            details={"missing_tables": missing_tables},
        ),
        QualityGateResult(
            gate_name="condition_schema_physical_asset_groups",
            status="passed" if not asset_group_failures else "failed",
            expected_value="stock/index/board split for monitor, basis, pool, and scope",
            actual_value=str(len(asset_group_failures)),
            details={"asset_group_failures": asset_group_failures},
        ),
        QualityGateResult(
            gate_name="condition_schema_required_columns_present",
            status="passed" if not missing_required_columns else "failed",
            expected_value="all required condition-layer columns",
            actual_value=str(len(missing_required_columns)),
            details={"missing_required_columns": missing_required_columns},
        ),
        QualityGateResult(
            gate_name="condition_schema_no_mixed_or_legacy_tables",
            status="passed" if not forbidden_tables else "failed",
            expected_value="no unsplit or legacy table names",
            actual_value=str(len(forbidden_tables)),
            details={"forbidden_tables": forbidden_tables},
        ),
        QualityGateResult(
            gate_name="condition_schema_no_downstream_runtime_sql",
            status="passed" if not dangerous_pattern_hits else "failed",
            expected_value="no downstream runtime objects",
            actual_value=str(len(dangerous_pattern_hits)),
            details={"dangerous_pattern_hits": dangerous_pattern_hits},
        ),
        QualityGateResult(
            gate_name="condition_schema_fk_dependencies_declared",
            status="passed" if not missing_fk_dependencies_in_sql else "failed",
            expected_value="condition schema references required ingestion dependencies",
            actual_value=str(len(FOREIGN_KEY_DEPENDENCY_TABLES) - len(missing_fk_dependencies_in_sql)),
            details={
                "external_reference_tables": external_reference_tables,
                "missing_fk_dependencies_in_sql": missing_fk_dependencies_in_sql,
            },
        ),
        QualityGateResult(
            gate_name="condition_schema_standard_signal_whitelist",
            status="passed" if signal_whitelist_ready else "failed",
            expected_value="canonical N2 signal candidates: " + ", ".join(CANONICAL_N2_SIGNAL_LITERALS),
            actual_value="present" if signal_whitelist_ready else "incomplete",
            details={"signal_literals": sorted(signal_literals)},
        ),
        QualityGateResult(
            gate_name="condition_schema_previous_day_minute_guard",
            status="passed" if prev_trade_date_ready else "failed",
            expected_value="previous day minute date equals prev_trade_date",
            actual_value=str(prev_trade_date_ready).lower(),
            details={},
        ),
        QualityGateResult(
            gate_name="condition_schema_stock_scope_market_value_guard",
            status="passed" if stock_mv_scope_ready else "failed",
            expected_value="stock scope market value threshold check",
            actual_value=str(stock_mv_scope_ready).lower(),
            details={},
        ),
        QualityGateResult(
            gate_name="condition_schema_source_prev_date_guard",
            status="passed" if source_prev_guard_ready else "failed",
            expected_value="source_trade_date equals prev_trade_date",
            actual_value=str(source_prev_guard_ready).lower(),
            details={},
        ),
        QualityGateResult(
            gate_name="condition_schema_transaction_wrapper",
            status="passed" if transaction_ready else "failed",
            expected_value="single BEGIN and COMMIT wrapper",
            actual_value=str(transaction_ready).lower(),
            details={},
        ),
        QualityGateResult(
            gate_name="condition_schema_readiness_only_no_sql_execution",
            status="passed",
            expected_value="dry-run report only",
            actual_value="will_execute_sql=false",
            details={},
        ),
    ]


def parse_create_index_count(sql_text: str) -> int:
    return len(re.findall(r"\bCREATE\s+INDEX\b", sql_text, flags=re.IGNORECASE))


def parse_reference_tables(sql_text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(r"\bREFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\b", sql_text, flags=re.IGNORECASE)
    }


def parse_sql_array_literals(sql_text: str) -> set[str]:
    return set(re.findall(r"'([A-Z0-9_:]+)'", sql_text))


def has_single_begin_commit(sql_text: str) -> bool:
    begin_count = len(re.findall(r"^\s*BEGIN\s*;", sql_text, flags=re.IGNORECASE | re.MULTILINE))
    commit_count = len(re.findall(r"^\s*COMMIT\s*;", sql_text, flags=re.IGNORECASE | re.MULTILINE))
    return begin_count == 1 and commit_count == 1 and sql_text.upper().find("BEGIN") < sql_text.upper().rfind("COMMIT")


def fetch_condition_schema_database_status(dsn: str) -> dict[str, Any]:
    """Inspect development database objects with a read-only connection."""
    objects_to_check = tuple(dict.fromkeys(REQUIRED_SCHEMA_TABLES + FOREIGN_KEY_DEPENDENCY_TABLES + RUNTIME_DEPENDENCY_OBJECTS))
    with psycopg.connect(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        object_status: dict[str, dict[str, Any]] = {}
        for object_name in objects_to_check:
            cur.execute("SELECT to_regclass(%s) AS object_regclass", (f"public.{object_name}",))
            regclass = cur.fetchone()["object_regclass"]
            object_status[object_name] = {
                "exists": regclass is not None,
                "regclass": f"public.{object_name}" if regclass is not None else None,
            }

    condition_existing = [table for table in REQUIRED_SCHEMA_TABLES if object_status[table]["exists"]]
    condition_missing = [table for table in REQUIRED_SCHEMA_TABLES if not object_status[table]["exists"]]
    fk_dependency_missing = [table for table in FOREIGN_KEY_DEPENDENCY_TABLES if not object_status[table]["exists"]]
    runtime_dependency_missing = [obj for obj in RUNTIME_DEPENDENCY_OBJECTS if not object_status[obj]["exists"]]
    ready_for_first_apply = not condition_existing and not fk_dependency_missing
    return {
        "checked": True,
        "read_only": True,
        "condition_tables_existing": condition_existing,
        "condition_tables_missing": condition_missing,
        "condition_table_count_existing": len(condition_existing),
        "condition_table_count_missing": len(condition_missing),
        "fk_dependency_missing": fk_dependency_missing,
        "runtime_dependency_missing": runtime_dependency_missing,
        "ready_for_first_apply": ready_for_first_apply,
        "manual_review_required": bool(condition_existing or fk_dependency_missing),
        "migration_required": bool(condition_missing),
        "migration_performed": False,
        "object_status": object_status,
    }
