"""Parquet archive directory readiness dry-run checks.

This module only builds deterministic path readiness reports. It does not
create directories, write data files, connect PostgreSQL, call external data
sources, or read local TDX files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

from ashare_v3.ingestion.common import QualityGateResult
from ashare_v3.ingestion.ingestion_acceptance import quality_gate_to_dict
from ashare_v3.ingestion.parquet_archive import (
    DATASET_PARTITION_KEYS,
    DATA_LAKE_DIR,
    DEFAULT_DATA_ROOT,
    make_manifest_path,
    make_parquet_file_path,
)


SAMPLE_PARTITION_DATE = "20260522"
EXPECTED_ARCHIVE_DATASET_COUNT = 7

SAMPLE_SOURCE_IDS: dict[str, str] = {
    "stock_daily_bar_fact": "stock_daily_20260522_v1",
    "stock_daily_basic": "stock_daily_basic_20260522_v1",
    "index_daily_bar_fact": "index_daily_20260522_v1",
    "board_daily_bar_fact": "board_daily_20260522_v1",
    "stock_financial_metrics_fact": "stock_financial_20260522_v1",
    "index_membership_fact": "index_membership_20260522_v1",
    "board_membership_fact": "board_membership_20260522_v1",
}


@dataclass(frozen=True)
class ParquetDatasetReadiness:
    dataset: str
    partition_keys: tuple[str, ...]
    dataset_root: str
    manifest_root: str
    sample_source_batch_id: str
    sample_source_version: str
    sample_partition_values: Mapping[str, str]
    sample_parquet_path: str
    sample_manifest_path: str
    sample_rollback_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "partition_keys": list(self.partition_keys),
            "dataset_root": self.dataset_root,
            "manifest_root": self.manifest_root,
            "sample_source_batch_id": self.sample_source_batch_id,
            "sample_source_version": self.sample_source_version,
            "sample_partition_values": dict(self.sample_partition_values),
            "sample_parquet_path": self.sample_parquet_path,
            "sample_manifest_path": self.sample_manifest_path,
            "sample_rollback_paths": list(self.sample_rollback_paths),
        }


@dataclass(frozen=True)
class ParquetReadinessReport:
    data_root: str
    data_lake_dir: str
    dataset_count: int
    dataset_summaries: tuple[ParquetDatasetReadiness, ...]
    quality_gates: tuple[QualityGateResult, ...]
    will_create_directories: bool = False
    will_write_data_files: bool = False
    will_connect_database: bool = False
    will_execute_sql: bool = False
    will_call_external_sources: bool = False
    will_read_tdx_files: bool = False

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_root": self.data_root,
            "data_lake_dir": self.data_lake_dir,
            "dataset_count": self.dataset_count,
            "expected_dataset_count": EXPECTED_ARCHIVE_DATASET_COUNT,
            "passed": self.passed,
            "dataset_summaries": [summary.to_dict() for summary in self.dataset_summaries],
            "quality_gates": [quality_gate_to_dict(gate) for gate in self.quality_gates],
            "side_effects": {
                "will_create_directories": self.will_create_directories,
                "will_write_data_files": self.will_write_data_files,
                "will_connect_database": self.will_connect_database,
                "will_execute_sql": self.will_execute_sql,
                "will_call_external_sources": self.will_call_external_sources,
                "will_read_tdx_files": self.will_read_tdx_files,
            },
        }


def build_parquet_readiness_report(data_root: str = DEFAULT_DATA_ROOT) -> ParquetReadinessReport:
    dataset_summaries = tuple(
        build_dataset_readiness(dataset=dataset, partition_keys=partition_keys, data_root=data_root)
        for dataset, partition_keys in sorted(DATASET_PARTITION_KEYS.items())
    )
    report = ParquetReadinessReport(
        data_root=data_root,
        data_lake_dir=DATA_LAKE_DIR,
        dataset_count=len(dataset_summaries),
        dataset_summaries=dataset_summaries,
        quality_gates=(),
    )
    return ParquetReadinessReport(
        data_root=report.data_root,
        data_lake_dir=report.data_lake_dir,
        dataset_count=report.dataset_count,
        dataset_summaries=report.dataset_summaries,
        quality_gates=tuple(build_parquet_readiness_quality_gates(report)),
    )


def build_dataset_readiness(
    *,
    dataset: str,
    partition_keys: tuple[str, ...],
    data_root: str,
) -> ParquetDatasetReadiness:
    sample_source_id = SAMPLE_SOURCE_IDS[dataset]
    partition_values = sample_partition_values(partition_keys)
    dataset_root = str(PurePosixPath(data_root) / DATA_LAKE_DIR / dataset)
    manifest_root = str(PurePosixPath(data_root) / DATA_LAKE_DIR / "_manifests" / dataset)
    sample_parquet_path = make_parquet_file_path(
        data_root=data_root,
        dataset=dataset,
        source_version=sample_source_id,
        partition_values=partition_values,
    )
    sample_manifest_path = make_manifest_path(
        data_root=data_root,
        dataset=dataset,
        source_version=sample_source_id,
        source_batch_id=sample_source_id,
    )
    return ParquetDatasetReadiness(
        dataset=dataset,
        partition_keys=partition_keys,
        dataset_root=dataset_root,
        manifest_root=manifest_root,
        sample_source_batch_id=sample_source_id,
        sample_source_version=sample_source_id,
        sample_partition_values=partition_values,
        sample_parquet_path=sample_parquet_path,
        sample_manifest_path=sample_manifest_path,
        sample_rollback_paths=(sample_manifest_path, sample_parquet_path),
    )


def sample_partition_values(partition_keys: tuple[str, ...]) -> dict[str, str]:
    return {key: SAMPLE_PARTITION_DATE for key in partition_keys}


def build_parquet_readiness_quality_gates(report: ParquetReadinessReport) -> list[QualityGateResult]:
    data_lake_root = str(PurePosixPath(report.data_root) / DATA_LAKE_DIR)
    manifest_root = str(PurePosixPath(report.data_root) / DATA_LAKE_DIR / "_manifests")
    dataset_names = [summary.dataset for summary in report.dataset_summaries]
    missing_source_ids = sorted(set(dataset_names) - set(SAMPLE_SOURCE_IDS))
    missing_partition_keys = [summary.dataset for summary in report.dataset_summaries if not summary.partition_keys]
    manifest_path_failures = [
        summary.dataset
        for summary in report.dataset_summaries
        if not summary.sample_manifest_path.startswith(f"{manifest_root}/{summary.dataset}/")
    ]
    parquet_path_failures = [
        summary.dataset
        for summary in report.dataset_summaries
        if not summary.sample_parquet_path.startswith(f"{data_lake_root}/{summary.dataset}/")
    ]
    unsupported_datasets = [
        dataset
        for dataset in dataset_names
        if dataset == "daily_bar_fact" or dataset.endswith("_runtime_archive") or dataset.startswith(("snapshot_", "minute_"))
    ]
    rollback_failures = [
        summary.dataset
        for summary in report.dataset_summaries
        if summary.sample_rollback_paths != (summary.sample_manifest_path, summary.sample_parquet_path)
    ]
    side_effect_flags = {
        "will_create_directories": report.will_create_directories,
        "will_write_data_files": report.will_write_data_files,
        "will_connect_database": report.will_connect_database,
        "will_execute_sql": report.will_execute_sql,
        "will_call_external_sources": report.will_call_external_sources,
        "will_read_tdx_files": report.will_read_tdx_files,
    }
    enabled_side_effects = sorted(name for name, enabled in side_effect_flags.items() if enabled)

    return [
        QualityGateResult(
            gate_name="parquet_data_root_expected",
            status="passed" if report.data_root == DEFAULT_DATA_ROOT else "failed",
            expected_value=DEFAULT_DATA_ROOT,
            actual_value=report.data_root,
            details={},
        ),
        QualityGateResult(
            gate_name="parquet_data_lake_dir_expected",
            status="passed" if report.data_lake_dir == DATA_LAKE_DIR else "failed",
            expected_value="data_lake",
            actual_value=report.data_lake_dir,
            details={},
        ),
        QualityGateResult(
            gate_name="parquet_archive_dataset_count",
            status="passed" if report.dataset_count == EXPECTED_ARCHIVE_DATASET_COUNT else "failed",
            expected_value=str(EXPECTED_ARCHIVE_DATASET_COUNT),
            actual_value=str(report.dataset_count),
            details={"datasets": dataset_names},
        ),
        QualityGateResult(
            gate_name="parquet_partition_keys_defined",
            status="passed" if not missing_partition_keys else "failed",
            expected_value="partition keys on every archive dataset",
            actual_value=str(len(missing_partition_keys)),
            details={"missing_partition_keys": missing_partition_keys},
        ),
        QualityGateResult(
            gate_name="parquet_source_ids_defined",
            status="passed" if not missing_source_ids else "failed",
            expected_value="sample source ids on every archive dataset",
            actual_value=str(len(missing_source_ids)),
            details={"missing_source_ids": missing_source_ids},
        ),
        QualityGateResult(
            gate_name="parquet_manifest_paths_under_data_root",
            status="passed" if not manifest_path_failures else "failed",
            expected_value=f"{manifest_root}/DATASET/source_version=SOURCE_VERSION/SOURCE_BATCH_ID.manifest.json",
            actual_value=str(len(manifest_path_failures)),
            details={"manifest_path_failures": manifest_path_failures},
        ),
        QualityGateResult(
            gate_name="parquet_file_paths_under_data_root",
            status="passed" if not parquet_path_failures else "failed",
            expected_value=f"{data_lake_root}/DATASET/source_version=SOURCE_VERSION/PARTITION/part-00000.parquet",
            actual_value=str(len(parquet_path_failures)),
            details={"parquet_path_failures": parquet_path_failures},
        ),
        QualityGateResult(
            gate_name="parquet_no_legacy_or_mixed_dataset",
            status="passed" if not unsupported_datasets else "failed",
            expected_value="only approved stock/index/board archive datasets",
            actual_value=str(len(unsupported_datasets)),
            details={"unsupported_datasets": unsupported_datasets},
        ),
        QualityGateResult(
            gate_name="parquet_rollback_paths_planned",
            status="passed" if not rollback_failures else "failed",
            expected_value="manifest path plus parquet file path for every dataset",
            actual_value=str(len(rollback_failures)),
            details={"rollback_failures": rollback_failures},
        ),
        QualityGateResult(
            gate_name="parquet_no_side_effects",
            status="passed" if not enabled_side_effects else "failed",
            expected_value="readiness report only",
            actual_value=str(len(enabled_side_effects)),
            details={"enabled_side_effects": enabled_side_effects},
        ),
    ]
