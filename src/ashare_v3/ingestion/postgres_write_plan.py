"""PostgreSQL write and rollback dry-run planning.

The functions in this module generate SQL templates and validation gates only.
They do not import a database driver, open a connection, execute SQL, or mutate
any PostgreSQL database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.common import IngestionValidationError, QualityGateResult, stable_raw_hash


COMMON_AUDIT_COLUMNS = ("source", "source_batch_id", "source_version", "raw_payload", "created_at", "updated_at")


@dataclass(frozen=True)
class TableWriteSpec:
    table_name: str
    data_domain: str
    conflict_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    allowed_columns: tuple[str, ...]
    rollback_column: str
    required_identity_columns: tuple[str, ...] = ()
    forbidden_columns: tuple[str, ...] = ()
    stock_code_column: str | None = None
    board_code_column: str | None = None


@dataclass(frozen=True)
class PostgresWritePlan:
    table_name: str
    operation: str
    source_batch_id: str | None
    source_version: str | None
    row_count: int
    raw_hash: str
    columns: tuple[str, ...]
    conflict_key: tuple[str, ...]
    insert_sql_template: str
    rollback_sql_template: str
    quality_gates: tuple[QualityGateResult, ...]
    will_connect_database: bool = False
    will_execute_sql: bool = False

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "operation": self.operation,
            "source_batch_id": self.source_batch_id,
            "source_version": self.source_version,
            "row_count": self.row_count,
            "raw_hash": self.raw_hash,
            "columns": list(self.columns),
            "conflict_key": list(self.conflict_key),
            "insert_sql_template": self.insert_sql_template,
            "rollback_sql_template": self.rollback_sql_template,
            "quality_gates": [
                {
                    "gate_name": gate.gate_name,
                    "status": gate.status,
                    "severity": gate.severity,
                    "expected_value": gate.expected_value,
                    "actual_value": gate.actual_value,
                    "details": dict(gate.details or {}),
                }
                for gate in self.quality_gates
            ],
            "rollback": {
                "strategy": "delete_by_source_batch_id",
                "sql_template": self.rollback_sql_template,
            },
            "will_connect_database": self.will_connect_database,
            "will_execute_sql": self.will_execute_sql,
        }


TABLE_SPECS: dict[str, TableWriteSpec] = {
    "common_ingest_batch": TableWriteSpec(
        table_name="common_ingest_batch",
        data_domain="common",
        conflict_key=("batch_id",),
        required_columns=("batch_id", "trade_date", "data_domain", "data_type", "source", "source_version", "status", "started_at"),
        allowed_columns=(
            "batch_id",
            "trade_date",
            "data_domain",
            "data_type",
            "source",
            "source_version",
            "source_path",
            "source_params",
            "raw_hash",
            "row_count",
            "error_count",
            "quality_gate_summary",
            "error_summary",
            "rollback_strategy",
            "status",
            "started_at",
            "finished_at",
            "created_at",
        ),
        rollback_column="batch_id",
    ),
    "common_quality_gate_result": TableWriteSpec(
        table_name="common_quality_gate_result",
        data_domain="common",
        conflict_key=(),
        required_columns=("source_batch_id", "source_version", "data_domain", "data_type", "gate_name", "severity", "status"),
        allowed_columns=(
            "source_batch_id",
            "source_version",
            "data_domain",
            "data_type",
            "gate_name",
            "severity",
            "status",
            "expected_value",
            "actual_value",
            "details",
            "created_at",
        ),
        rollback_column="source_batch_id",
    ),
    "common_trade_calendar": TableWriteSpec(
        table_name="common_trade_calendar",
        data_domain="common",
        conflict_key=("trade_date",),
        required_columns=("trade_date", "exchange", "is_open", "source", "source_batch_id", "source_version"),
        allowed_columns=("trade_date", "exchange", "is_open", "prev_trade_date", "next_trade_date", *COMMON_AUDIT_COLUMNS),
        rollback_column="source_batch_id",
    ),
    "stock_identity": TableWriteSpec(
        table_name="stock_identity",
        data_domain="stock",
        conflict_key=("stock_identity_key",),
        required_columns=("stock_identity_key", "ts_code", "code", "exchange", "name", "source", "source_batch_id", "source_version"),
        allowed_columns=(
            "stock_identity_key",
            "ts_code",
            "code",
            "exchange",
            "name",
            "display_code",
            "area",
            "industry",
            "market",
            "listed_date",
            "delisted_date",
            "is_st",
            "status",
            *COMMON_AUDIT_COLUMNS,
        ),
        rollback_column="source_batch_id",
        required_identity_columns=("stock_identity_key",),
        forbidden_columns=("index_identity_key", "board_identity_key"),
        stock_code_column="code",
    ),
    "index_identity": TableWriteSpec(
        table_name="index_identity",
        data_domain="index",
        conflict_key=("index_identity_key",),
        required_columns=("index_identity_key", "code", "exchange", "name", "source", "source_batch_id", "source_version"),
        allowed_columns=(
            "index_identity_key",
            "ts_code",
            "code",
            "exchange",
            "name",
            "source_namespace",
            "publisher",
            "index_category",
            "base_date",
            "listed_date",
            "status",
            *COMMON_AUDIT_COLUMNS,
        ),
        rollback_column="source_batch_id",
        required_identity_columns=("index_identity_key",),
        forbidden_columns=("stock_identity_key", "board_identity_key"),
    ),
    "board_identity": TableWriteSpec(
        table_name="board_identity",
        data_domain="board",
        conflict_key=("board_identity_key",),
        required_columns=("board_identity_key", "board_code", "board_name", "board_type", "source", "source_batch_id", "source_version"),
        allowed_columns=(
            "board_identity_key",
            "board_code",
            "board_name",
            "board_type",
            "source_namespace",
            "source_file",
            "status",
            *COMMON_AUDIT_COLUMNS,
        ),
        rollback_column="source_batch_id",
        required_identity_columns=("board_identity_key",),
        forbidden_columns=("stock_identity_key", "index_identity_key"),
        board_code_column="board_code",
    ),
    "stock_daily_bar_fact": TableWriteSpec(
        table_name="stock_daily_bar_fact",
        data_domain="stock",
        conflict_key=("stock_identity_key", "trade_date", "source_version"),
        required_columns=("stock_identity_key", "trade_date", "ts_code", "code", "exchange", "open", "high", "low", "close", "source", "source_batch_id", "source_version"),
        allowed_columns=(
            "stock_identity_key",
            "trade_date",
            "ts_code",
            "code",
            "exchange",
            "name",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "adj_factor",
            "adjust_type",
            "official_daily_proof",
            *COMMON_AUDIT_COLUMNS,
        ),
        rollback_column="source_batch_id",
        required_identity_columns=("stock_identity_key",),
        forbidden_columns=("index_identity_key", "board_identity_key"),
        stock_code_column="code",
    ),
    "stock_daily_basic": TableWriteSpec(
        table_name="stock_daily_basic",
        data_domain="stock",
        conflict_key=("stock_identity_key", "trade_date", "source_version"),
        required_columns=("stock_identity_key", "trade_date", "ts_code", "code", "exchange", "source", "source_batch_id", "source_version"),
        allowed_columns=(
            "stock_identity_key",
            "trade_date",
            "ts_code",
            "code",
            "exchange",
            "close",
            "turnover_rate",
            "turnover_rate_f",
            "volume_ratio",
            "pe",
            "pe_ttm",
            "pb",
            "ps",
            "ps_ttm",
            "dv_ratio",
            "dv_ttm",
            "total_share",
            "float_share",
            "free_share",
            "total_mv",
            "circ_mv",
            *COMMON_AUDIT_COLUMNS,
        ),
        rollback_column="source_batch_id",
        required_identity_columns=("stock_identity_key",),
        forbidden_columns=("index_identity_key", "board_identity_key"),
        stock_code_column="code",
    ),
    "index_daily_bar_fact": TableWriteSpec(
        table_name="index_daily_bar_fact",
        data_domain="index",
        conflict_key=("index_identity_key", "trade_date", "source_version"),
        required_columns=("index_identity_key", "trade_date", "code", "exchange", "open", "high", "low", "close", "source", "source_batch_id", "source_version"),
        allowed_columns=("index_identity_key", "trade_date", "code", "exchange", "name", "open", "high", "low", "close", "volume", "amount", *COMMON_AUDIT_COLUMNS),
        rollback_column="source_batch_id",
        required_identity_columns=("index_identity_key",),
        forbidden_columns=("stock_identity_key", "board_identity_key"),
    ),
    "board_daily_bar_fact": TableWriteSpec(
        table_name="board_daily_bar_fact",
        data_domain="board",
        conflict_key=("board_identity_key", "trade_date", "source_version"),
        required_columns=("board_identity_key", "trade_date", "board_code", "board_type", "open", "high", "low", "close", "source", "source_batch_id", "source_version"),
        allowed_columns=("board_identity_key", "trade_date", "board_code", "board_name", "board_type", "open", "high", "low", "close", "volume", "amount", *COMMON_AUDIT_COLUMNS),
        rollback_column="source_batch_id",
        required_identity_columns=("board_identity_key",),
        forbidden_columns=("stock_identity_key", "index_identity_key"),
        board_code_column="board_code",
    ),
    "stock_financial_metrics_fact": TableWriteSpec(
        table_name="stock_financial_metrics_fact",
        data_domain="stock",
        conflict_key=("stock_identity_key", "asof_date", "source_version"),
        required_columns=("stock_identity_key", "asof_date", "ts_code", "code", "exchange", "source", "source_batch_id", "source_version"),
        allowed_columns=(
            "stock_identity_key",
            "asof_date",
            "report_period",
            "ts_code",
            "code",
            "exchange",
            "roe",
            "revenue_yoy",
            "profit_yoy",
            "total_revenue",
            "net_profit",
            "net_assets",
            "eps",
            "bps",
            *COMMON_AUDIT_COLUMNS,
        ),
        rollback_column="source_batch_id",
        required_identity_columns=("stock_identity_key",),
        forbidden_columns=("index_identity_key", "board_identity_key"),
        stock_code_column="code",
    ),
    "index_membership_fact": TableWriteSpec(
        table_name="index_membership_fact",
        data_domain="index",
        conflict_key=("trade_date", "index_identity_key", "stock_identity_key", "source_version"),
        required_columns=("trade_date", "index_identity_key", "stock_identity_key", "index_code", "stock_code", "source", "source_batch_id", "source_version"),
        allowed_columns=("trade_date", "index_identity_key", "stock_identity_key", "index_code", "index_name", "stock_code", "stock_name", "source", "source_file", "source_batch_id", "source_version", "raw_payload", "created_at"),
        rollback_column="source_batch_id",
        required_identity_columns=("index_identity_key", "stock_identity_key"),
        forbidden_columns=("board_identity_key",),
        stock_code_column="stock_code",
    ),
    "board_membership_fact": TableWriteSpec(
        table_name="board_membership_fact",
        data_domain="board",
        conflict_key=("trade_date", "board_identity_key", "stock_identity_key", "source_version"),
        required_columns=("trade_date", "board_identity_key", "stock_identity_key", "board_code", "board_type", "stock_code", "source", "source_batch_id", "source_version"),
        allowed_columns=("trade_date", "board_identity_key", "stock_identity_key", "board_code", "board_name", "board_type", "stock_code", "stock_name", "source", "source_file", "source_batch_id", "source_version", "raw_payload", "created_at"),
        rollback_column="source_batch_id",
        required_identity_columns=("board_identity_key", "stock_identity_key"),
        forbidden_columns=("index_identity_key",),
        stock_code_column="stock_code",
        board_code_column="board_code",
    ),
}


def build_postgres_write_plan(
    *,
    table_name: str,
    rows: Sequence[Mapping[str, Any]],
) -> PostgresWritePlan:
    spec = get_table_spec(table_name)
    row_list = [dict(row) for row in rows]
    columns = infer_columns(row_list, spec)
    source_batch_id = infer_single_metadata_value(row_list, spec.rollback_column)
    source_version = infer_single_metadata_value(row_list, "source_version")
    operation = "insert" if not spec.conflict_key else "insert_on_conflict_update"
    insert_sql_template = build_insert_sql_template(spec, columns)
    rollback_sql_template = f"DELETE FROM {spec.table_name} WHERE {spec.rollback_column} = :source_batch_id;"
    quality_gates = tuple(build_write_quality_gates(spec, row_list, columns, source_batch_id, source_version))

    return PostgresWritePlan(
        table_name=spec.table_name,
        operation=operation,
        source_batch_id=source_batch_id,
        source_version=source_version,
        row_count=len(row_list),
        raw_hash=stable_raw_hash(row_list),
        columns=columns,
        conflict_key=spec.conflict_key,
        insert_sql_template=insert_sql_template,
        rollback_sql_template=rollback_sql_template,
        quality_gates=quality_gates,
    )


def get_table_spec(table_name: str) -> TableWriteSpec:
    normalized = str(table_name).strip()
    if normalized not in TABLE_SPECS:
        raise IngestionValidationError(f"unsupported PostgreSQL write table: {table_name!r}")
    return TABLE_SPECS[normalized]


def infer_columns(rows: Sequence[Mapping[str, Any]], spec: TableWriteSpec) -> tuple[str, ...]:
    present = set()
    for row in rows:
        present.update(str(column) for column in row.keys())
    ordered = [column for column in spec.allowed_columns if column in present]
    extras = sorted(present - set(spec.allowed_columns))
    return tuple([*ordered, *extras])


def infer_single_metadata_value(rows: Sequence[Mapping[str, Any]], column: str) -> str | None:
    values = {str(row.get(column)).strip() for row in rows if row.get(column) not in (None, "")}
    if len(values) == 1:
        return next(iter(values))
    return None


def build_insert_sql_template(spec: TableWriteSpec, columns: Sequence[str]) -> str:
    quoted_columns = ", ".join(columns)
    placeholders = ", ".join(f":{column}" for column in columns)
    base_sql = f"INSERT INTO {spec.table_name} ({quoted_columns}) VALUES ({placeholders})"
    if not spec.conflict_key:
        return base_sql + ";"

    update_columns = [column for column in columns if column not in spec.conflict_key and column != "created_at"]
    conflict_columns = ", ".join(spec.conflict_key)
    if not update_columns:
        return f"{base_sql} ON CONFLICT ({conflict_columns}) DO NOTHING;"
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
    return f"{base_sql} ON CONFLICT ({conflict_columns}) DO UPDATE SET {assignments};"


def build_write_quality_gates(
    spec: TableWriteSpec,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    source_batch_id: str | None,
    source_version: str | None,
) -> list[QualityGateResult]:
    return [
        gate_non_empty(rows),
        gate_allowed_columns(spec, columns),
        gate_required_columns(spec, rows),
        gate_single_source_batch(spec, rows, source_batch_id),
        gate_single_source_version(rows, source_version),
        gate_identity_columns(spec, rows),
        gate_forbidden_columns_absent(spec, rows),
        gate_code_shape(spec, rows),
        gate_rollback_sql_available(spec),
    ]


def gate_non_empty(rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    return QualityGateResult(
        gate_name="postgres_row_count_non_empty",
        status="passed" if rows else "failed",
        expected_value=">0",
        actual_value=str(len(rows)),
        details={},
    )


def gate_allowed_columns(spec: TableWriteSpec, columns: Sequence[str]) -> QualityGateResult:
    extras = sorted(set(columns) - set(spec.allowed_columns))
    return QualityGateResult(
        gate_name="postgres_allowed_columns",
        status="passed" if not extras else "failed",
        expected_value="columns in N1 schema allowlist",
        actual_value=str(len(extras)),
        details={"extra_columns": extras[:50]},
    )


def gate_required_columns(spec: TableWriteSpec, rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    missing = [
        {"row_index": idx, "column": column}
        for idx, row in enumerate(rows)
        for column in spec.required_columns
        if row.get(column) in (None, "")
    ]
    return QualityGateResult(
        gate_name="postgres_required_columns_present",
        status="passed" if not missing else "failed",
        expected_value="100%",
        actual_value=f"{len(rows) * len(spec.required_columns) - len(missing)}/{len(rows) * len(spec.required_columns)}",
        details={"missing": missing[:50]},
    )


def gate_single_source_batch(
    spec: TableWriteSpec,
    rows: Sequence[Mapping[str, Any]],
    source_batch_id: str | None,
) -> QualityGateResult:
    values = sorted({str(row.get(spec.rollback_column)).strip() for row in rows if row.get(spec.rollback_column) not in (None, "")})
    return QualityGateResult(
        gate_name="postgres_source_batch_id_single",
        status="passed" if len(values) == 1 and source_batch_id else "failed",
        expected_value="exactly one rollback batch key",
        actual_value=str(len(values)),
        details={"rollback_column": spec.rollback_column, "values": values[:20]},
    )


def gate_single_source_version(
    rows: Sequence[Mapping[str, Any]],
    source_version: str | None,
) -> QualityGateResult:
    values = sorted({str(row.get("source_version")).strip() for row in rows if row.get("source_version") not in (None, "")})
    return QualityGateResult(
        gate_name="postgres_source_version_single",
        status="passed" if len(values) == 1 and source_version else "failed",
        expected_value="exactly one source_version",
        actual_value=str(len(values)),
        details={"values": values[:20]},
    )


def gate_identity_columns(spec: TableWriteSpec, rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    missing = [
        {"row_index": idx, "column": column}
        for idx, row in enumerate(rows)
        for column in spec.required_identity_columns
        if row.get(column) in (None, "")
    ]
    denominator = len(rows) * len(spec.required_identity_columns)
    return QualityGateResult(
        gate_name="postgres_identity_key_coverage",
        status="passed" if not missing else "failed",
        expected_value="100%",
        actual_value=f"{denominator - len(missing)}/{denominator}" if denominator else "not_applicable",
        details={"identity_columns": list(spec.required_identity_columns), "missing": missing[:50]},
    )


def gate_forbidden_columns_absent(spec: TableWriteSpec, rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    bad = [
        {"row_index": idx, "column": column}
        for idx, row in enumerate(rows)
        for column in spec.forbidden_columns
        if row.get(column) not in (None, "")
    ]
    return QualityGateResult(
        gate_name="postgres_physical_table_forbidden_columns",
        status="passed" if not bad else "failed",
        expected_value="0 forbidden asset columns",
        actual_value=str(len(bad)),
        details={"forbidden_columns": list(spec.forbidden_columns), "bad": bad[:50]},
    )


def gate_code_shape(spec: TableWriteSpec, rows: Sequence[Mapping[str, Any]]) -> QualityGateResult:
    violations: list[dict[str, Any]] = []
    if spec.stock_code_column:
        for idx, row in enumerate(rows):
            value = str(row.get(spec.stock_code_column) or "")
            if value.startswith("88"):
                violations.append({"row_index": idx, "column": spec.stock_code_column, "value": value})
    if spec.board_code_column:
        for idx, row in enumerate(rows):
            value = str(row.get(spec.board_code_column) or "")
            if value and not value.startswith("88"):
                violations.append({"row_index": idx, "column": spec.board_code_column, "value": value})

    return QualityGateResult(
        gate_name="postgres_physical_code_shape",
        status="passed" if not violations else "failed",
        expected_value="stock codes not 88xxxx; board codes 88xxxx",
        actual_value=str(len(violations)),
        details={"violations": violations[:50]},
    )


def gate_rollback_sql_available(spec: TableWriteSpec) -> QualityGateResult:
    return QualityGateResult(
        gate_name="postgres_rollback_sql_available",
        status="passed" if spec.rollback_column else "failed",
        expected_value="delete by source batch rollback key",
        actual_value=spec.rollback_column,
        details={"table": spec.table_name},
    )
