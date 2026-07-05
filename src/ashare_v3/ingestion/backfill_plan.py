"""Initial raw ingestion backfill dry-run planning.

This module only builds deterministic batch plans for the initial historical
backfill. It never calls external APIs, reads local TDX files, connects
PostgreSQL, executes SQL, writes Parquet, or creates files under the data root.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.common import IngestionValidationError, QualityGateResult, make_source_batch_id, require_yyyymmdd
from ashare_v3.ingestion.parquet_archive import DATASET_PARTITION_KEYS, DEFAULT_DATA_ROOT


DEFAULT_BACKFILL_START_DATE = "20230101"
DEFAULT_BACKFILL_END_DATE = "20260521"


@dataclass(frozen=True)
class BackfillTaskSpec:
    task_id: str
    table_name: str
    data_domain: str
    data_type: str
    source: str
    slice_kind: str
    dependencies: tuple[str, ...]
    source_path: str | None = None
    source_params: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BackfillBatchPlan:
    spec: BackfillTaskSpec
    source_batch_id: str
    source_version: str
    start_date: str
    end_date: str
    period: str
    quality_gates: tuple[QualityGateResult, ...]
    data_root: str = DEFAULT_DATA_ROOT
    will_call_external_source: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_write_data_files: bool = False

    @property
    def archive_dataset(self) -> str | None:
        if self.spec.table_name in DATASET_PARTITION_KEYS:
            return self.spec.table_name
        return None

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.spec.task_id,
            "target_table": self.spec.table_name,
            "data_domain": self.spec.data_domain,
            "data_type": self.spec.data_type,
            "source": self.spec.source,
            "source_path": self.spec.source_path,
            "source_params": dict(self.spec.source_params or {}),
            "slice_kind": self.spec.slice_kind,
            "dependencies": list(self.spec.dependencies),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "period": self.period,
            "source_batch_id": self.source_batch_id,
            "source_version": self.source_version,
            "archive_dataset": self.archive_dataset,
            "passed": self.passed,
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_call_external_source": self.will_call_external_source,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_write_data_files": self.will_write_data_files,
            },
            "rollback": {
                "postgres_target": f"DELETE FROM {self.spec.table_name} WHERE source_batch_id = :source_batch_id;",
                "common_ingest_batch": "DELETE FROM common_ingest_batch WHERE batch_id = :source_batch_id;",
                "common_quality_gate_result": "DELETE FROM common_quality_gate_result WHERE source_batch_id = :source_batch_id;",
                "archive": "planned manifest paths only; no files are written in dry-run",
            },
        }


@dataclass(frozen=True)
class InitialBackfillPlan:
    start_date: str
    end_date: str
    snapshot_date: str
    version: str
    data_root: str
    monthly_periods: tuple[str, ...]
    batches: tuple[BackfillBatchPlan, ...]
    quality_gates: tuple[QualityGateResult, ...]
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_write_data_files: bool = False

    @property
    def batch_count(self) -> int:
        return len(self.batches)

    @property
    def passed(self) -> bool:
        return all(batch.passed for batch in self.batches) and all(gate.passed for gate in self.quality_gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "snapshot_date": self.snapshot_date,
            "version": self.version,
            "data_root": self.data_root,
            "monthly_periods": list(self.monthly_periods),
            "batch_count": self.batch_count,
            "passed": self.passed,
            "batches": [batch.to_dict() for batch in self.batches],
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_write_data_files": self.will_write_data_files,
            },
            "rollback": {
                "strategy": "delete_each_source_batch_id_then_restore_active_source_versions; archive paths are planned only",
                "source_batch_ids": [batch.source_batch_id for batch in self.batches],
            },
        }


RANGE_TASK_SPECS: tuple[BackfillTaskSpec, ...] = (
    BackfillTaskSpec(
        task_id="common_trade_calendar",
        table_name="common_trade_calendar",
        data_domain="common",
        data_type="trade_calendar",
        source="tushare.trade_cal",
        slice_kind="range",
        dependencies=(),
        source_params={"exchange": "SSE"},
    ),
)

SNAPSHOT_TASK_SPECS: tuple[BackfillTaskSpec, ...] = (
    BackfillTaskSpec(
        task_id="stock_identity",
        table_name="stock_identity",
        data_domain="stock",
        data_type="stock_identity",
        source="tushare.stock_basic",
        slice_kind="snapshot",
        dependencies=("common_trade_calendar",),
        source_params={"exchange": "", "list_status": "L,D,P"},
    ),
    BackfillTaskSpec(
        task_id="index_identity",
        table_name="index_identity",
        data_domain="index",
        data_type="index_identity",
        source="tushare.index_basic",
        slice_kind="snapshot",
        dependencies=("common_trade_calendar",),
    ),
    BackfillTaskSpec(
        task_id="board_identity",
        table_name="board_identity",
        data_domain="board",
        data_type="board_identity",
        source="tdx.local_txt",
        slice_kind="snapshot",
        dependencies=("common_trade_calendar",),
        source_path="/Volumes/MacRaid/tdxdata/tdx",
    ),
    BackfillTaskSpec(
        task_id="index_membership",
        table_name="index_membership_fact",
        data_domain="index",
        data_type="index_membership",
        source="tdx.local_txt.index_board",
        slice_kind="snapshot",
        dependencies=("stock_identity", "index_identity"),
        source_path="/Volumes/MacRaid/tdxdata/tdx/指数板块.txt",
    ),
    BackfillTaskSpec(
        task_id="board_membership",
        table_name="board_membership_fact",
        data_domain="board",
        data_type="board_membership",
        source="tdx.local_txt.board",
        slice_kind="snapshot",
        dependencies=("stock_identity", "board_identity"),
        source_path="/Volumes/MacRaid/tdxdata/tdx",
    ),
)

MONTHLY_TASK_SPECS: tuple[BackfillTaskSpec, ...] = (
    BackfillTaskSpec(
        task_id="stock_daily",
        table_name="stock_daily_bar_fact",
        data_domain="stock",
        data_type="stock_daily",
        source="tushare.pro_bar.qfq",
        slice_kind="month",
        dependencies=("common_trade_calendar", "stock_identity"),
        source_params={"asset": "E", "freq": "D", "adj": "qfq"},
    ),
    BackfillTaskSpec(
        task_id="stock_daily_basic",
        table_name="stock_daily_basic",
        data_domain="stock",
        data_type="stock_daily_basic",
        source="tushare.daily_basic",
        slice_kind="month",
        dependencies=("common_trade_calendar", "stock_identity"),
    ),
    BackfillTaskSpec(
        task_id="index_daily",
        table_name="index_daily_bar_fact",
        data_domain="index",
        data_type="index_daily",
        source="mootdx.index",
        slice_kind="month",
        dependencies=("common_trade_calendar", "index_identity"),
    ),
    BackfillTaskSpec(
        task_id="board_daily",
        table_name="board_daily_bar_fact",
        data_domain="board",
        data_type="board_daily",
        source="mootdx.index",
        slice_kind="month",
        dependencies=("common_trade_calendar", "board_identity"),
    ),
    BackfillTaskSpec(
        task_id="stock_financial",
        table_name="stock_financial_metrics_fact",
        data_domain="stock",
        data_type="stock_financial",
        source="mootdx.finance",
        slice_kind="month",
        dependencies=("common_trade_calendar", "stock_identity"),
    ),
)


def build_initial_backfill_plan(
    *,
    start_date: str = DEFAULT_BACKFILL_START_DATE,
    end_date: str = DEFAULT_BACKFILL_END_DATE,
    snapshot_date: str | None = None,
    version: str = "v1",
    data_root: str = DEFAULT_DATA_ROOT,
) -> InitialBackfillPlan:
    normalized_start = require_yyyymmdd(start_date, "start_date")
    normalized_end = require_yyyymmdd(end_date, "end_date")
    normalized_snapshot = require_yyyymmdd(snapshot_date or normalized_end, "snapshot_date")
    normalized_version = validate_version(version)
    validate_date_order(normalized_start, normalized_end)
    validate_snapshot_date(normalized_snapshot, normalized_start, normalized_end)

    monthly_periods = month_periods_between(normalized_start, normalized_end)
    seen_task_ids: set[str] = set()
    batches: list[BackfillBatchPlan] = []

    for spec in RANGE_TASK_SPECS:
        batch = build_range_batch(spec, normalized_start, normalized_end, normalized_version, data_root, seen_task_ids)
        batches.append(batch)
        seen_task_ids.add(spec.task_id)

    for spec in SNAPSHOT_TASK_SPECS:
        batch = build_snapshot_batch(spec, normalized_snapshot, normalized_version, data_root, seen_task_ids)
        batches.append(batch)
        seen_task_ids.add(spec.task_id)

    aggregate_versions = {
        spec.data_type: make_source_batch_id(spec.data_type, f"{normalized_start}_{normalized_end}", normalized_version)
        for spec in MONTHLY_TASK_SPECS
    }
    for period in monthly_periods:
        period_start, period_end = clipped_month_range(period, normalized_start, normalized_end)
        for spec in MONTHLY_TASK_SPECS:
            batch = build_monthly_batch(
                spec=spec,
                period=period,
                period_start=period_start,
                period_end=period_end,
                source_version=aggregate_versions[spec.data_type],
                version=normalized_version,
                data_root=data_root,
                seen_task_ids=seen_task_ids,
            )
            batches.append(batch)

    plan_quality_gates = tuple(build_plan_quality_gates(batches, monthly_periods, normalized_start, normalized_end, normalized_snapshot))
    return InitialBackfillPlan(
        start_date=normalized_start,
        end_date=normalized_end,
        snapshot_date=normalized_snapshot,
        version=normalized_version,
        data_root=data_root,
        monthly_periods=monthly_periods,
        batches=tuple(batches),
        quality_gates=plan_quality_gates,
    )


def build_range_batch(
    spec: BackfillTaskSpec,
    start_date: str,
    end_date: str,
    version: str,
    data_root: str,
    seen_task_ids: set[str],
) -> BackfillBatchPlan:
    period = f"{start_date}_{end_date}"
    source_batch_id = make_source_batch_id(spec.data_type, period, version)
    return BackfillBatchPlan(
        spec=spec,
        source_batch_id=source_batch_id,
        source_version=source_batch_id,
        start_date=start_date,
        end_date=end_date,
        period=period,
        quality_gates=tuple(build_batch_quality_gates(spec, seen_task_ids)),
        data_root=data_root,
    )


def build_snapshot_batch(
    spec: BackfillTaskSpec,
    snapshot_date: str,
    version: str,
    data_root: str,
    seen_task_ids: set[str],
) -> BackfillBatchPlan:
    source_batch_id = make_source_batch_id(spec.data_type, snapshot_date, version)
    return BackfillBatchPlan(
        spec=spec,
        source_batch_id=source_batch_id,
        source_version=source_batch_id,
        start_date=snapshot_date,
        end_date=snapshot_date,
        period=snapshot_date,
        quality_gates=tuple(build_batch_quality_gates(spec, seen_task_ids)),
        data_root=data_root,
    )


def build_monthly_batch(
    *,
    spec: BackfillTaskSpec,
    period: str,
    period_start: str,
    period_end: str,
    source_version: str,
    version: str,
    data_root: str,
    seen_task_ids: set[str],
) -> BackfillBatchPlan:
    source_batch_id = make_source_batch_id(spec.data_type, period, version)
    return BackfillBatchPlan(
        spec=spec,
        source_batch_id=source_batch_id,
        source_version=source_version,
        start_date=period_start,
        end_date=period_end,
        period=period,
        quality_gates=tuple(build_batch_quality_gates(spec, seen_task_ids)),
        data_root=data_root,
    )


def build_batch_quality_gates(spec: BackfillTaskSpec, seen_task_ids: set[str]) -> list[QualityGateResult]:
    missing_dependencies = [dependency for dependency in spec.dependencies if dependency not in seen_task_ids]
    expected_prefix = f"{spec.data_domain}_"
    return [
        QualityGateResult(
            gate_name="backfill_dependencies_precede_batch",
            status="passed" if not missing_dependencies else "failed",
            expected_value="all dependencies already planned",
            actual_value=str(len(missing_dependencies)),
            details={"missing_dependencies": missing_dependencies},
        ),
        QualityGateResult(
            gate_name="backfill_physical_table_prefix",
            status="passed" if spec.table_name.startswith(expected_prefix) else "failed",
            expected_value=expected_prefix,
            actual_value=spec.table_name,
            details={"data_domain": spec.data_domain},
        ),
        QualityGateResult(
            gate_name="backfill_source_metadata_planned",
            status="passed",
            expected_value="source_batch_id/source_version/source",
            actual_value="planned",
            details={"source": spec.source},
        ),
        QualityGateResult(
            gate_name="backfill_dry_run_only",
            status="passed",
            expected_value="no source calls, no database execution, no data file writes",
            actual_value="dry_run",
            details={},
        ),
    ]


def build_plan_quality_gates(
    batches: Sequence[BackfillBatchPlan],
    monthly_periods: Sequence[str],
    start_date: str,
    end_date: str,
    snapshot_date: str,
) -> list[QualityGateResult]:
    source_batch_ids = [batch.source_batch_id for batch in batches]
    monthly_batches = [batch for batch in batches if batch.spec.slice_kind == "month"]
    membership_batches = [batch for batch in batches if batch.spec.data_type in {"index_membership", "board_membership"}]
    side_effect_violations = [
        batch.source_batch_id
        for batch in batches
        if any(
            (
                batch.will_call_external_source,
                batch.will_read_tdx_files,
                batch.will_connect_database,
                batch.will_execute_sql,
                batch.will_write_data_files,
            )
        )
    ]
    expected_batch_count = len(RANGE_TASK_SPECS) + len(SNAPSHOT_TASK_SPECS) + len(monthly_periods) * len(MONTHLY_TASK_SPECS)
    bad_physical_tables = [
        batch.spec.table_name
        for batch in batches
        if not batch.spec.table_name.startswith(f"{batch.spec.data_domain}_")
    ]
    return [
        QualityGateResult(
            gate_name="backfill_date_range_valid",
            status="passed",
            expected_value="start_date <= snapshot_date <= end_date",
            actual_value=f"{start_date}<={snapshot_date}<={end_date}",
            details={},
        ),
        QualityGateResult(
            gate_name="backfill_month_period_count",
            status="passed" if len(monthly_batches) == len(monthly_periods) * len(MONTHLY_TASK_SPECS) else "failed",
            expected_value=str(len(monthly_periods) * len(MONTHLY_TASK_SPECS)),
            actual_value=str(len(monthly_batches)),
            details={"monthly_periods": list(monthly_periods)},
        ),
        QualityGateResult(
            gate_name="backfill_core_batch_count",
            status="passed" if len(batches) == expected_batch_count else "failed",
            expected_value=str(expected_batch_count),
            actual_value=str(len(batches)),
            details={},
        ),
        QualityGateResult(
            gate_name="backfill_membership_snapshot_only",
            status="passed" if all(batch.start_date == snapshot_date and batch.end_date == snapshot_date for batch in membership_batches) else "failed",
            expected_value="membership batches only at snapshot_date",
            actual_value=str(len(membership_batches)),
            details={"membership_batch_ids": [batch.source_batch_id for batch in membership_batches]},
        ),
        QualityGateResult(
            gate_name="backfill_source_batch_ids_unique",
            status="passed" if len(source_batch_ids) == len(set(source_batch_ids)) else "failed",
            expected_value=str(len(source_batch_ids)),
            actual_value=str(len(set(source_batch_ids))),
            details={"source_batch_ids": source_batch_ids},
        ),
        QualityGateResult(
            gate_name="backfill_physical_tables_split",
            status="passed" if not bad_physical_tables and "daily_bar_fact" not in {batch.spec.table_name for batch in batches} else "failed",
            expected_value="stock/index/board/common physical tables only",
            actual_value=str(len(bad_physical_tables)),
            details={"bad_tables": bad_physical_tables},
        ),
        QualityGateResult(
            gate_name="backfill_no_side_effects",
            status="passed" if not side_effect_violations else "failed",
            expected_value="0",
            actual_value=str(len(side_effect_violations)),
            details={"violations": side_effect_violations},
        ),
        QualityGateResult(
            gate_name="backfill_all_batches_passed",
            status="passed" if all(batch.passed for batch in batches) else "failed",
            expected_value="all batch plans pass",
            actual_value=str(sum(1 for batch in batches if batch.passed)),
            details={"failed_batch_ids": [batch.source_batch_id for batch in batches if not batch.passed]},
        ),
    ]


def month_periods_between(start_date: str, end_date: str) -> tuple[str, ...]:
    start = parse_yyyymmdd(start_date)
    end = parse_yyyymmdd(end_date)
    periods: list[str] = []
    year = start.year
    month = start.month
    while (year, month) <= (end.year, end.month):
        periods.append(f"{year:04d}{month:02d}")
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return tuple(periods)


def clipped_month_range(period: str, start_date: str, end_date: str) -> tuple[str, str]:
    if len(period) != 6 or not period.isdigit():
        raise IngestionValidationError(f"period must be YYYYMM: {period!r}")
    year = int(period[:4])
    month = int(period[4:])
    _, last_day = monthrange(year, month)
    month_start = f"{year:04d}{month:02d}01"
    month_end = f"{year:04d}{month:02d}{last_day:02d}"
    return max(month_start, start_date), min(month_end, end_date)


def validate_version(version: str) -> str:
    text = str(version).strip()
    if not text.startswith("v") or len(text) < 2 or not text[1:].isdigit():
        raise IngestionValidationError(f"version must look like vN: {version!r}")
    return text


def validate_date_order(start_date: str, end_date: str) -> None:
    if parse_yyyymmdd(start_date) > parse_yyyymmdd(end_date):
        raise IngestionValidationError(f"start_date must be <= end_date: {start_date!r} > {end_date!r}")


def validate_snapshot_date(snapshot_date: str, start_date: str, end_date: str) -> None:
    snapshot = parse_yyyymmdd(snapshot_date)
    if not parse_yyyymmdd(start_date) <= snapshot <= parse_yyyymmdd(end_date):
        raise IngestionValidationError("snapshot_date must be within start_date/end_date")


def parse_yyyymmdd(value: str) -> date:
    require_yyyymmdd(value)
    return datetime.strptime(value, "%Y%m%d").date()


def quality_gate_to_dict(gate: QualityGateResult) -> dict[str, Any]:
    return {
        "gate_name": gate.gate_name,
        "status": gate.status,
        "severity": gate.severity,
        "expected_value": gate.expected_value,
        "actual_value": gate.actual_value,
        "details": dict(gate.details or {}),
    }
