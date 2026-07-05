"""Read-only N3-N6 runtime archive planning helpers.

The runtime archive flow deliberately starts as a plan/status layer. It does
not connect to PostgreSQL, create Parquet files, write manifests, or clean hot
runtime rows. N1/archive can later consume the deterministic manifest paths
after a separate execute gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

from ashare_v3.ingestion.common import IngestionValidationError, require_yyyymmdd


DEFAULT_RUNTIME_ARCHIVE_ROOT = "/Volumes/MacRaid/stock_db_archive/v3_runtime"
DEFAULT_MINIMUM_FREE_BYTES = 5 * 1024**3
RUNTIME_ARCHIVE_MANIFEST_VERSION = "v3-runtime-archive.v1"
RUNTIME_ARCHIVE_LAYERS = ("n3", "n4", "n5", "n6")
PATH_SAFE_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


@dataclass(frozen=True)
class RuntimeArchiveFilePlan:
    layer: str
    table: str
    row_count: int
    path: str
    checksum: str = ""

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "table": self.table,
            "row_count": self.row_count,
            "path": self.path,
            "checksum": self.checksum,
            "format": "parquet",
        }


@dataclass(frozen=True)
class RuntimeArchivePlan:
    trade_date: str
    archive_root: str
    status: str
    files: tuple[RuntimeArchiveFilePlan, ...]
    manifest_path: str
    report_path: str
    blockers: tuple[str, ...]
    cleanup_eligible: bool
    cleanup_blockers: tuple[str, ...]
    storage_status: dict[str, Any]
    hot_retention_days: int = 5
    manifest_version: str = RUNTIME_ARCHIVE_MANIFEST_VERSION

    @property
    def total_rows(self) -> int:
        return sum(file.row_count for file in self.files)

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "trade_date": self.trade_date,
            "archive_root": self.archive_root,
            "status": self.status,
            "files": [file.to_manifest_dict() for file in self.files],
            "file_count": len(self.files),
            "total_rows": self.total_rows,
            "manifest_path": self.manifest_path,
            "report_path": self.report_path,
            "blockers": list(self.blockers),
            "cleanup_eligible": self.cleanup_eligible,
            "cleanup_blockers": list(self.cleanup_blockers),
            "storage": dict(self.storage_status),
            "hot_retention_days": self.hot_retention_days,
            "rollback": {
                "strategy": "manifest_scoped_archive_files_only_no_hot_cleanup",
                "paths": [self.manifest_path, self.report_path, *[file.path for file in self.files]],
            },
            "side_effects": runtime_archive_side_effects(),
        }


def runtime_archive_side_effects() -> dict[str, bool | int]:
    return {
        "writes_database": False,
        "database_written": False,
        "writes_archive_files": False,
        "archive_files_written": False,
        "cleanup_local_runtime": False,
        "outbox_consumed": False,
        "outbox_status_updated": False,
        "outbox_status_updates": 0,
        "worker_started": False,
        "voice_triggered": False,
        "mobile_triggered": False,
        "sim_written": False,
        "position_written": False,
        "real_trade_submitted": False,
    }


def inspect_archive_storage(
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    *,
    minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_BYTES,
) -> dict[str, Any]:
    root = Path(archive_root)
    probe = root
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    mounted = probe.exists() and probe.is_dir()
    writable = bool(mounted and os.access(probe, os.W_OK))
    free_bytes = 0
    if mounted:
        try:
            stat = os.statvfs(probe)
            free_bytes = int(stat.f_bavail * stat.f_frsize)
        except OSError:
            free_bytes = 0
    return {
        "archive_root": str(root),
        "probe_path": str(probe),
        "archive_root_exists": root.exists(),
        "mounted": mounted,
        "writable": writable,
        "free_bytes": free_bytes,
        "minimum_free_bytes": int(minimum_free_bytes),
        "free_space_ok": bool(free_bytes >= int(minimum_free_bytes)),
    }


def build_runtime_archive_plan(
    *,
    trade_date: str,
    table_summaries: Sequence[Mapping[str, Any]],
    archive_root: str = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    sealed_layers: Mapping[str, bool] | None = None,
    storage_status: Mapping[str, Any] | None = None,
    active_writer_count: int = 0,
    delivering_outbox_count: int = 0,
    hot_retention_days: int = 5,
    minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_BYTES,
) -> RuntimeArchivePlan:
    normalized_trade_date = require_yyyymmdd(str(trade_date), "trade_date")
    storage = dict(storage_status or inspect_archive_storage(archive_root, minimum_free_bytes=minimum_free_bytes))
    files = tuple(
        RuntimeArchiveFilePlan(
            layer=normalize_layer(summary.get("layer")),
            table=validate_path_component(str(summary.get("table") or ""), "table"),
            row_count=max(0, int(summary.get("row_count") or 0)),
            path=make_runtime_archive_file_path(
                archive_root=archive_root,
                trade_date=normalized_trade_date,
                layer=normalize_layer(summary.get("layer")),
                table=validate_path_component(str(summary.get("table") or ""), "table"),
            ),
            checksum=str(summary.get("checksum") or ""),
        )
        for summary in table_summaries
    )
    blockers = build_archive_blockers(
        files=files,
        sealed_layers=sealed_layers or {},
        storage_status=storage,
        active_writer_count=active_writer_count,
        delivering_outbox_count=delivering_outbox_count,
    )
    status = "BLOCKED" if blockers else "ARCHIVE_PREFLIGHT_PASS"
    cleanup_blockers = ("manual_cleanup_required",)
    if status != "ARCHIVE_PREFLIGHT_PASS":
        cleanup_blockers = ("archive_preflight_not_passed", *cleanup_blockers)
    return RuntimeArchivePlan(
        trade_date=normalized_trade_date,
        archive_root=str(archive_root),
        status=status,
        files=files,
        manifest_path=make_runtime_archive_manifest_path(
            archive_root=archive_root,
            trade_date=normalized_trade_date,
        ),
        report_path=make_runtime_archive_report_path(
            archive_root=archive_root,
            trade_date=normalized_trade_date,
        ),
        blockers=tuple(blockers),
        cleanup_eligible=False,
        cleanup_blockers=cleanup_blockers,
        storage_status=storage,
        hot_retention_days=hot_retention_days,
    )


def build_archive_blockers(
    *,
    files: Sequence[RuntimeArchiveFilePlan],
    sealed_layers: Mapping[str, bool],
    storage_status: Mapping[str, Any],
    active_writer_count: int,
    delivering_outbox_count: int,
) -> list[str]:
    blockers: list[str] = []
    if not bool(storage_status.get("mounted")):
        blockers.append("macraid_not_mounted")
    if not bool(storage_status.get("writable")):
        blockers.append("macraid_not_writable")
    if not bool(storage_status.get("free_space_ok", True)):
        blockers.append("macraid_free_space_below_threshold")
    for layer in sorted({file.layer for file in files}):
        if not bool(sealed_layers.get(layer)):
            blockers.append(f"layer_not_sealed:{layer}")
    if int(active_writer_count or 0) != 0:
        blockers.append("active_writer_not_zero")
    if int(delivering_outbox_count or 0) != 0:
        blockers.append("outbox_delivering_not_zero")
    return blockers


def make_runtime_archive_file_path(
    *,
    archive_root: str,
    trade_date: str,
    layer: str,
    table: str,
) -> str:
    return str(PurePosixPath(archive_root) / f"trade_date={trade_date}" / layer / f"{table}.parquet")


def make_runtime_archive_manifest_path(*, archive_root: str, trade_date: str) -> str:
    return str(PurePosixPath(archive_root) / f"trade_date={trade_date}" / "manifests" / "archive_manifest.json")


def make_runtime_archive_report_path(*, archive_root: str, trade_date: str) -> str:
    return str(PurePosixPath(archive_root) / f"trade_date={trade_date}" / "reports" / "archive_report.json")


def normalize_layer(value: Any) -> str:
    layer = str(value or "").strip().lower()
    if layer not in RUNTIME_ARCHIVE_LAYERS:
        raise IngestionValidationError(f"unsupported runtime archive layer: {value!r}")
    return layer


def validate_path_component(value: str, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise IngestionValidationError(f"{field_name} is required")
    if "/" in text or "\\" in text or not PATH_SAFE_RE.match(text):
        raise IngestionValidationError(f"{field_name} is not path safe: {value!r}")
    return text
