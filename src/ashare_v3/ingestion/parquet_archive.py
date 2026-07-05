"""Parquet archive manifest dry-run planning.

This module only builds deterministic archive plans. It does not create
directories, write Parquet files, write manifests, connect PostgreSQL, or mark a
source version active.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.common import IngestionValidationError, QualityGateResult, stable_raw_hash


DEFAULT_DATA_ROOT = "/Volumes/MacRaid/database"
DATA_LAKE_DIR = "data_lake"
MANIFEST_VERSION = "v1"

DATASET_PARTITION_KEYS: dict[str, tuple[str, ...]] = {
    "stock_daily_bar_fact": ("trade_date",),
    "stock_daily_basic": ("trade_date",),
    "index_daily_bar_fact": ("trade_date",),
    "board_daily_bar_fact": ("trade_date",),
    "stock_financial_metrics_fact": ("asof_date",),
    "index_membership_fact": ("trade_date",),
    "board_membership_fact": ("trade_date",),
}

PATH_SAFE_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(frozen=True)
class ArchiveFilePlan:
    path: str
    row_count: int
    partition_values: dict[str, str]

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "row_count": self.row_count,
            "partition_values": dict(self.partition_values),
        }


@dataclass(frozen=True)
class ParquetArchivePlan:
    dataset: str
    source_batch_id: str
    source_version: str
    schema_version: str
    row_count: int
    raw_hash: str
    partition_keys: tuple[str, ...]
    manifest_path: str
    files: tuple[ArchiveFilePlan, ...]
    quality_gates: tuple[QualityGateResult, ...]
    data_root: str = DEFAULT_DATA_ROOT
    manifest_version: str = MANIFEST_VERSION
    will_connect_database: bool = False
    will_write_data_files: bool = False

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    @property
    def file_paths(self) -> list[str]:
        return [file.path for file in self.files]

    @property
    def rollback_paths(self) -> list[str]:
        return [self.manifest_path, *self.file_paths]

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "dataset": self.dataset,
            "source_batch_id": self.source_batch_id,
            "source_version": self.source_version,
            "schema_version": self.schema_version,
            "row_count": self.row_count,
            "raw_hash": self.raw_hash,
            "partition_keys": list(self.partition_keys),
            "manifest_path": self.manifest_path,
            "file_paths": self.file_paths,
            "files": [file.to_manifest_dict() for file in self.files],
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
                "strategy": "delete_manifest_and_unactivated_files_by_source_batch_id",
                "paths": self.rollback_paths,
            },
            "will_connect_database": self.will_connect_database,
            "will_write_data_files": self.will_write_data_files,
        }


def build_parquet_archive_plan(
    *,
    dataset: str,
    rows: Sequence[Mapping[str, Any]],
    source_batch_id: str,
    source_version: str,
    schema_version: str = "v1",
    data_root: str = DEFAULT_DATA_ROOT,
    raw_hash: str | None = None,
) -> ParquetArchivePlan:
    normalized_dataset = validate_dataset(dataset)
    validate_path_component(source_batch_id, "source_batch_id")
    validate_path_component(source_version, "source_version")
    validate_path_component(schema_version, "schema_version")

    row_list = [dict(row) for row in rows]
    partition_keys = DATASET_PARTITION_KEYS[normalized_dataset]
    partitions = group_rows_by_partition(row_list, partition_keys)
    manifest_path = make_manifest_path(
        data_root=data_root,
        dataset=normalized_dataset,
        source_version=source_version,
        source_batch_id=source_batch_id,
    )
    files = tuple(
        ArchiveFilePlan(
            path=make_parquet_file_path(
                data_root=data_root,
                dataset=normalized_dataset,
                source_version=source_version,
                partition_values=partition_values,
            ),
            row_count=len(partition_rows),
            partition_values=dict(partition_values),
        )
        for partition_values, partition_rows in partitions
    )
    quality_gates = build_archive_quality_gates(
        dataset=normalized_dataset,
        rows=row_list,
        source_batch_id=source_batch_id,
        source_version=source_version,
        partition_keys=partition_keys,
        files=files,
    )

    return ParquetArchivePlan(
        dataset=normalized_dataset,
        source_batch_id=source_batch_id,
        source_version=source_version,
        schema_version=schema_version,
        row_count=len(row_list),
        raw_hash=raw_hash or stable_raw_hash(row_list),
        partition_keys=partition_keys,
        manifest_path=manifest_path,
        files=files,
        quality_gates=tuple(quality_gates),
        data_root=data_root,
    )


def build_archive_quality_gates(
    *,
    dataset: str,
    rows: Sequence[Mapping[str, Any]],
    source_batch_id: str,
    source_version: str,
    partition_keys: Sequence[str],
    files: Sequence[ArchiveFilePlan],
) -> list[QualityGateResult]:
    total_file_rows = sum(file.row_count for file in files)
    return [
        QualityGateResult(
            gate_name="archive_dataset_allowed",
            status="passed" if dataset in DATASET_PARTITION_KEYS else "failed",
            expected_value="known raw ingestion dataset",
            actual_value=dataset,
            details={},
        ),
        QualityGateResult(
            gate_name="archive_source_metadata_present",
            status="passed" if source_batch_id and source_version else "failed",
            expected_value="source_batch_id and source_version",
            actual_value=f"{bool(source_batch_id)}/{bool(source_version)}",
            details={},
        ),
        QualityGateResult(
            gate_name="archive_partition_keys_present",
            status="passed",
            expected_value="100%",
            actual_value=f"{len(rows) * len(partition_keys)}/{len(rows) * len(partition_keys)}",
            details={"partition_keys": list(partition_keys)},
        ),
        QualityGateResult(
            gate_name="archive_row_count_matches_files",
            status="passed" if len(rows) == total_file_rows else "failed",
            expected_value=str(len(rows)),
            actual_value=str(total_file_rows),
            details={"file_count": len(files)},
        ),
    ]


def group_rows_by_partition(
    rows: Sequence[Mapping[str, Any]],
    partition_keys: Sequence[str],
) -> tuple[tuple[dict[str, str], list[dict[str, Any]]], ...]:
    grouped: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = {}
    for row_index, row in enumerate(rows):
        values: list[tuple[str, str]] = []
        for key in partition_keys:
            value = row.get(key)
            if value is None or str(value).strip() == "":
                raise IngestionValidationError(f"row {row_index} missing archive partition key {key!r}")
            partition_value = str(value).strip()
            validate_path_component(partition_value, key)
            values.append((key, partition_value))
        grouped.setdefault(tuple(values), []).append(dict(row))

    return tuple(
        (dict(key_values), grouped[key_values])
        for key_values in sorted(grouped)
    )


def make_manifest_path(
    *,
    data_root: str,
    dataset: str,
    source_version: str,
    source_batch_id: str,
) -> str:
    return str(
        PurePosixPath(data_root)
        / DATA_LAKE_DIR
        / "_manifests"
        / dataset
        / f"source_version={source_version}"
        / f"{source_batch_id}.manifest.json"
    )


def make_parquet_file_path(
    *,
    data_root: str,
    dataset: str,
    source_version: str,
    partition_values: Mapping[str, str],
) -> str:
    path = PurePosixPath(data_root) / DATA_LAKE_DIR / dataset / f"source_version={source_version}"
    for key, value in partition_values.items():
        path = path / f"{key}={value}"
    return str(path / "part-00000.parquet")


def validate_dataset(dataset: str) -> str:
    normalized = str(dataset).strip()
    if normalized not in DATASET_PARTITION_KEYS:
        raise IngestionValidationError(f"unsupported archive dataset: {dataset!r}")
    return normalized


def validate_path_component(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise IngestionValidationError(f"{field_name} is required")
    if "/" in text or "\\" in text or not PATH_SAFE_RE.match(text):
        raise IngestionValidationError(f"{field_name} is not path safe: {value!r}")
    return text
