#!/usr/bin/env python3
"""Copy verified historical runtime artifacts into one immutable archive batch.

This N1/archive entrypoint never mutates a source file, writes PostgreSQL, or
controls a service.  It accepts only the three artifact families frozen by the
disk-governance contract and leaves deletion authorization to runtime_control.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.run_runtime_hot_keep5_cleanup_once import discover_local_artifact_files
except ModuleNotFoundError:  # Direct ``python scripts/...`` invocation.
    from run_runtime_hot_keep5_cleanup_once import discover_local_artifact_files


MANIFEST_VERSION = "LocalArtifactArchiveManifest.v1"
ARCHIVE_BASE = Path("/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts")
EXACT_QUIESCE_EVIDENCE_PATH = Path(
    "/Users/chuanfuchen/.codex/worktrees/b564/A股监控系统v3/docs/runtime_archive/"
    "runtime_hot_cleanup_archive_gated_disk_governance_v1/"
    "20260821T023348+0800_cleanup_scheduler_quiesce/phase_evidence.json"
)
EXACT_QUIESCE_SIDECAR_PATH = EXACT_QUIESCE_EVIDENCE_PATH.with_suffix(".json.sha256")
FAMILIES = (
    "n3p_trigger_proof_contract",
    "intraday_live_current",
    "post_close_fastlane",
    "runtime_date_directory",
)
TRADE_DATE_RE = re.compile(r"^[0-9]{8}$")


class ArchiveBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class Candidate:
    family: str
    trade_date: str
    source_path: Path
    relative_path: Path


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_date(value: str, current_date: str) -> bool:
    if not TRADE_DATE_RE.fullmatch(value):
        return False
    try:
        parsed = datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d")
    except ValueError:
        return False
    return parsed == value and value <= current_date


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _regular_lstat(path: Path) -> os.stat_result:
    value = path.lstat()
    if not stat.S_ISREG(value.st_mode):
        raise ArchiveBlocked(f"not_regular_file:{path}")
    return value


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_mtime_ns, value.st_size)


def _iter_regular_names(directory: Path) -> Iterable[Path]:
    with os.scandir(directory) as scan:
        for item in sorted(scan, key=lambda value: value.name):
            yield Path(item.path)


def _require_safe_directory(path: Path) -> None:
    value = path.lstat()
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        raise ArchiveBlocked(f"unsafe_source_directory:{path}")


def discover_candidates(source_root: Path, retained_dates: set[str], current_date: str) -> tuple[list[Candidate], list[str], dict[str, int]]:
    root = source_root.resolve(strict=True)
    candidates: list[Candidate] = []
    blockers: list[str] = []
    retained_skipped = {family: 0 for family in FAMILIES}
    try:
        inventory = discover_local_artifact_files(
            project_root=root,
            current_date=datetime.strptime(current_date, "%Y%m%d").date(),
        )
    except (ValueError, OSError) as exc:
        return [], [f"runtime_cleanup_discovery_not_closed:{exc}"], retained_skipped
    for entry in inventory:
        path = Path(str(entry["source_path"]))
        family = str(entry["artifact_family"])
        trade_date = str(entry["trade_date"])
        if family not in FAMILIES:
            blockers.append(f"unsupported_runtime_cleanup_family:{family}:{path}")
            continue
        if not _valid_date(trade_date, current_date):
            blockers.append(f"invalid_runtime_cleanup_trade_date:{path}")
            continue
        if trade_date in retained_dates:
            retained_skipped[family] += 1
            continue
        try:
            relative_path = path.relative_to(root)
            _regular_lstat(path)
        except (ArchiveBlocked, ValueError) as exc:
            blockers.append(f"invalid_runtime_cleanup_candidate:{path}:{exc}")
            continue
        candidates.append(Candidate(family, trade_date, path, relative_path))

    seen_sources: set[Path] = set()
    seen_archive_relatives: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.source_path.resolve(strict=True)
        if not _inside(resolved, root):
            blockers.append(f"source_path_escape:{candidate.source_path}")
        archive_relative = Path("files") / candidate.family / candidate.relative_path
        if resolved in seen_sources:
            blockers.append(f"duplicate_source_path:{resolved}")
        if archive_relative in seen_archive_relatives:
            blockers.append(f"duplicate_archive_path:{archive_relative}")
        seen_sources.add(resolved)
        seen_archive_relatives.add(archive_relative)

    candidates.sort(key=lambda item: str(item.source_path))
    return candidates, sorted(set(blockers)), retained_skipped


def _mkdir_new(path: Path) -> None:
    path.mkdir(mode=0o755)


def _ensure_parent_under_batch(path: Path, batch_root: Path) -> None:
    relative = path.parent.relative_to(batch_root)
    current = batch_root
    for component in relative.parts:
        current = current / component
        try:
            current.mkdir(mode=0o755)
        except FileExistsError:
            value = current.lstat()
            if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
                raise ArchiveBlocked(f"unsafe_archive_parent:{current}")


def _atomic_write(path: Path, payload: bytes, batch_root: Path, mode: int = 0o444) -> None:
    _ensure_parent_under_batch(path, batch_root)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.link(temporary, path, follow_symlinks=False)
        os.unlink(temporary)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _copy_verified(candidate: Candidate, archive_path: Path, batch_root: Path, restore_proof_id: str) -> dict[str, Any]:
    before = _regular_lstat(candidate.source_path)
    before_identity = _identity(before)
    source_sha = _sha256_path(candidate.source_path)
    temporary = archive_path.with_name(f".{archive_path.name}.tmp-{os.getpid()}")
    _ensure_parent_under_batch(archive_path, batch_root)
    source_fd = os.open(candidate.source_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    target_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    archive_digest = hashlib.sha256()
    try:
        with os.fdopen(source_fd, "rb", closefd=True) as source_handle, os.fdopen(target_fd, "wb", closefd=True) as target_handle:
            opened = os.fstat(source_handle.fileno())
            if _identity(opened) != before_identity:
                raise ArchiveBlocked(f"source_identity_drift_before_copy:{candidate.source_path}")
            while chunk := source_handle.read(1024 * 1024):
                archive_digest.update(chunk)
                target_handle.write(chunk)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        os.chmod(temporary, 0o444)
        after = _regular_lstat(candidate.source_path)
        after_sha = _sha256_path(candidate.source_path)
        if _identity(after) != before_identity or after_sha != source_sha:
            raise ArchiveBlocked(f"source_drift_after_copy:{candidate.source_path}")
        archive_sha = archive_digest.hexdigest()
        if archive_sha != source_sha or _sha256_path(temporary) != source_sha:
            raise ArchiveBlocked(f"archive_hash_mismatch:{candidate.source_path}")
        os.link(temporary, archive_path, follow_symlinks=False)
        os.unlink(temporary)
    except BaseException:
        try:
            os.close(source_fd)
        except OSError:
            pass
        try:
            os.close(target_fd)
        except OSError:
            pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return {
        "source_path": str(candidate.source_path),
        "trade_date": candidate.trade_date,
        "artifact_family": candidate.family,
        "source_device": before.st_dev,
        "source_inode": before.st_ino,
        "source_mode": format(stat.S_IMODE(before.st_mode), "04o"),
        "source_mtime_ns": before.st_mtime_ns,
        "source_logical_bytes": before.st_size,
        "source_allocated_bytes": before.st_blocks * 512,
        "source_sha256": source_sha,
        "archive_path": str(archive_path),
        "archive_sha256": archive_sha,
        "reference_classification": "historical_non_retained_active_current_lineage_zero_v1",
        "restore_proof_id": restore_proof_id,
    }


def _copy_archive_to_restore(entry: dict[str, Any], restore_path: Path, batch_root: Path) -> None:
    source = Path(entry["archive_path"])
    _atomic_write(restore_path, source.read_bytes(), batch_root)
    if _sha256_path(restore_path) != entry["archive_sha256"]:
        raise ArchiveBlocked(f"restore_hash_mismatch:{restore_path}")


def execute_archive(
    *, source_root: Path, archive_base: Path, batch_id: str, retained_dates: list[str],
    current_date: str, quiesce_evidence_sha256: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", batch_id):
        raise ArchiveBlocked("invalid_batch_id")
    if not re.fullmatch(r"[0-9a-f]{64}", quiesce_evidence_sha256):
        raise ArchiveBlocked("invalid_quiesce_evidence_sha256")
    if len(retained_dates) != 6 or len(set(retained_dates)) != 6:
        raise ArchiveBlocked("invalid_retained_date_set")
    if any(not _valid_date(value, current_date) for value in retained_dates):
        raise ArchiveBlocked("invalid_retained_date")
    if current_date not in retained_dates:
        raise ArchiveBlocked("current_date_not_retained")
    if not archive_base.exists() or archive_base.is_symlink() or not archive_base.is_dir():
        raise ArchiveBlocked("archive_base_missing_or_unsafe")

    candidates, blockers, retained_skipped = discover_candidates(source_root, set(retained_dates), current_date)
    if blockers:
        raise ArchiveBlocked(";".join(blockers))
    by_family: dict[str, list[Candidate]] = {family: [] for family in FAMILIES}
    for candidate in candidates:
        by_family[candidate.family].append(candidate)

    logical_bytes = sum(_regular_lstat(item.source_path).st_size for item in candidates)
    restore_bytes = sum(
        sum(_regular_lstat(item.source_path).st_size for item in values if item.trade_date == min(item.trade_date for item in values))
        for values in by_family.values() if values
    )
    if shutil.disk_usage(archive_base).free < logical_bytes + restore_bytes + 1024 * 1024:
        raise ArchiveBlocked("insufficient_archive_space")

    batch_root = archive_base / f"batch={batch_id}"
    _mkdir_new(batch_root)
    entries: list[dict[str, Any]] = []
    selected_dates = {family: min(item.trade_date for item in values) if values else None for family, values in by_family.items()}
    proof_ids = {
        family: hashlib.sha256(f"{batch_id}:{family}:{selected_dates[family] or 'EMPTY'}".encode()).hexdigest()
        for family in FAMILIES
    }
    try:
        for candidate in candidates:
            archive_path = batch_root / "files" / candidate.family / candidate.relative_path
            entries.append(_copy_verified(candidate, archive_path, batch_root, proof_ids[candidate.family]))

        restore_families: dict[str, Any] = {}
        for family in FAMILIES:
            selected_date = selected_dates[family]
            if selected_date is None:
                restore_families[family] = {"status": "EMPTY", "restore_proof_id": proof_ids[family], "entry_count": 0}
                continue
            selected = [entry for entry in entries if entry["artifact_family"] == family and entry["trade_date"] == selected_date]
            for entry in selected:
                archive_relative = Path(entry["archive_path"]).relative_to(batch_root / "files" / family)
                restore_path = batch_root / "isolation_restore_staging" / family / archive_relative
                _copy_archive_to_restore(entry, restore_path, batch_root)
            restore_families[family] = {
                "status": "RESTORE_PROOF_PASS",
                "restore_proof_id": proof_ids[family],
                "trade_date": selected_date,
                "entry_count": len(selected),
                "source_logical_bytes": sum(entry["source_logical_bytes"] for entry in selected),
                "relative_paths": [str(Path(entry["archive_path"]).relative_to(batch_root / "files" / family)) for entry in selected],
                "sha256": [entry["archive_sha256"] for entry in selected],
            }

        restore_proof = {
            "schema_version": "LocalArtifactIsolationRestoreProof.v1",
            "batch_id": batch_id,
            "result": "RESTORE_PROOF_PASS",
            "families": restore_families,
        }
        restore_path = batch_root / "restore_proof.json"
        _atomic_write(restore_path, _canonical_json(restore_proof), batch_root)
        restore_sha = _sha256_path(restore_path)

        manifest_path = batch_root / "manifest.jsonl"
        _atomic_write(manifest_path, b"".join(_canonical_json(entry) for entry in entries), batch_root)
        manifest_sha = _sha256_path(manifest_path)

        allowlist_entries = [
            {
                **entry,
                "manifest_sha256": manifest_sha,
                "retained_date_overlap": 0,
                "active_current_lineage_overlap": 0,
                "source_identity_stable": True,
                "archive_fully_verified": True,
            }
            for entry in entries
        ]
        allowlist_path = batch_root / "exact_cleanup_allowlist.jsonl"
        _atomic_write(allowlist_path, b"".join(_canonical_json(entry) for entry in allowlist_entries), batch_root)
        allowlist_sha = _sha256_path(allowlist_path)

        family_summary: dict[str, Any] = {}
        for family in FAMILIES:
            values = [entry for entry in entries if entry["artifact_family"] == family]
            dates: dict[str, dict[str, int]] = defaultdict(
                lambda: {"entry_count": 0, "source_logical_bytes": 0, "source_allocated_bytes": 0}
            )
            for entry in values:
                item = dates[entry["trade_date"]]
                item["entry_count"] += 1
                item["source_logical_bytes"] += entry["source_logical_bytes"]
                item["source_allocated_bytes"] += entry["source_allocated_bytes"]
            family_summary[family] = {
                "status": "ARCHIVED_VERIFIED" if values else "EMPTY",
                "entry_count": len(values),
                "source_logical_bytes": sum(entry["source_logical_bytes"] for entry in values),
                "source_allocated_bytes": sum(entry["source_allocated_bytes"] for entry in values),
                "by_trade_date": dict(sorted(dates.items())),
                "retained_skipped_count": retained_skipped[family],
            }

        summary = {
            "schema_version": "LocalArtifactArchiveSummary.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "batch_id": batch_id,
            "archive_root": str(batch_root),
            "result": "ARCHIVED_VERIFIED",
            "restore_proof_result": "RESTORE_PROOF_PASS",
            "cleanup_eligible": False,
            "ready_for_runtime_exact_reclaim": True,
            "source_mutation_count": 0,
            "database_writes": 0,
            "service_operations": 0,
            "retained_trade_dates": retained_dates,
            "retained_date_overlap": 0,
            "active_current_lineage_overlap": 0,
            "cleanup_quiesce_evidence_sha256": quiesce_evidence_sha256,
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha,
            "allowlist_path": str(allowlist_path),
            "allowlist_sha256": allowlist_sha,
            "restore_proof_path": str(restore_path),
            "restore_proof_sha256": restore_sha,
            "entry_count": len(entries),
            "source_logical_bytes_total": sum(entry["source_logical_bytes"] for entry in entries),
            "source_allocated_bytes_total": sum(entry["source_allocated_bytes"] for entry in entries),
            "archive_logical_bytes_total": sum(Path(entry["archive_path"]).lstat().st_size for entry in entries),
            "source_archive_hash_equality_count": sum(
                entry["source_sha256"] == entry["archive_sha256"] for entry in entries
            ),
            "families": family_summary,
            "blockers": [],
        }
        summary_path = batch_root / "summary.json"
        _atomic_write(summary_path, _canonical_json(summary), batch_root)
        summary["summary_path"] = str(summary_path)
        summary["summary_sha256"] = _sha256_path(summary_path)
        return summary
    except BaseException as exc:
        failure = {
            "schema_version": "LocalArtifactArchiveSummary.v1",
            "batch_id": batch_id,
            "archive_root": str(batch_root),
            "result": "BLOCKED",
            "cleanup_eligible": False,
            "ready_for_runtime_exact_reclaim": False,
            "source_mutation_count": 0,
            "database_writes": 0,
            "service_operations": 0,
            "blockers": [str(exc)],
        }
        try:
            _atomic_write(batch_root / "failure_summary.json", _canonical_json(failure), batch_root)
        except BaseException:
            pass
        raise


def _legacy_source_bytes(entry: dict[str, Any], exact_name: str, alias: str) -> int:
    if exact_name in entry and alias in entry:
        raise ArchiveBlocked(f"ambiguous_old_manifest_bytes:{entry.get('source_path')}:{exact_name}")
    value = entry.get(exact_name, entry.get(alias))
    if not isinstance(value, int) or value < 0:
        raise ArchiveBlocked(f"missing_old_manifest_bytes:{entry.get('source_path')}:{exact_name}")
    return value


def _verify_superseded_restore_proof(
    *, old_batch_root: Path, old_entries: list[dict[str, Any]], batch_id: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    old_proof_path = old_batch_root / "restore_proof.json"
    old_proof = json.loads(old_proof_path.read_text(encoding="utf-8"))
    if old_proof.get("result") != "RESTORE_PROOF_PASS":
        raise ArchiveBlocked("superseded_restore_proof_not_pass")
    archive_by_relative: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in old_entries:
        family = entry["artifact_family"]
        archive_relative = Path(entry["archive_path"]).resolve(strict=True).relative_to(
            old_batch_root / "files" / family
        )
        archive_by_relative[(family, str(archive_relative))] = entry

    proof_ids: dict[str, str] = {}
    verified_families: dict[str, Any] = {}
    for family in FAMILIES:
        old_family = old_proof.get("families", {}).get(family)
        family_present = any(entry["artifact_family"] == family for entry in old_entries)
        if not family_present:
            if old_family is not None and old_family.get("status") != "EMPTY":
                raise ArchiveBlocked(f"missing_empty_restore_proof:{family}")
            proof_id = hashlib.sha256(f"{batch_id}:{family}:EMPTY".encode()).hexdigest()
            proof_ids[family] = proof_id
            verified_families[family] = {"status": "EMPTY", "entry_count": 0, "restore_proof_id": proof_id}
            continue
        if old_family is None or old_family.get("status") != "RESTORE_PROOF_PASS":
            raise ArchiveBlocked(f"missing_restore_proof:{family}")
        relative_paths = old_family.get("relative_paths")
        hashes = old_family.get("sha256")
        if (
            not isinstance(relative_paths, list)
            or not isinstance(hashes, list)
            or len(relative_paths) != len(hashes)
            or len(relative_paths) != old_family.get("entry_count")
            or not relative_paths
        ):
            raise ArchiveBlocked(f"invalid_restore_proof_shape:{family}")
        verified_paths: list[str] = []
        for relative_value, expected_sha in zip(relative_paths, hashes, strict=True):
            relative = Path(relative_value)
            if relative.is_absolute() or ".." in relative.parts:
                raise ArchiveBlocked(f"restore_path_escape:{family}:{relative_value}")
            old_entry = archive_by_relative.get((family, str(relative)))
            if old_entry is None or old_entry["archive_sha256"] != expected_sha:
                raise ArchiveBlocked(f"restore_archive_binding_mismatch:{family}:{relative_value}")
            restore_path = old_batch_root / "isolation_restore_staging" / family / relative
            before = _regular_lstat(restore_path)
            actual_sha = _sha256_path(restore_path)
            after = _regular_lstat(restore_path)
            if _identity(before) != _identity(after) or actual_sha != expected_sha:
                raise ArchiveBlocked(f"restore_staging_drift:{restore_path}")
            verified_paths.append(str(restore_path))
        trade_date = old_family.get("trade_date")
        proof_id = hashlib.sha256(f"{batch_id}:{family}:{trade_date}".encode()).hexdigest()
        proof_ids[family] = proof_id
        verified_families[family] = {
            "status": "RESTORE_PROOF_PASS",
            "restore_proof_id": proof_id,
            "trade_date": trade_date,
            "entry_count": len(verified_paths),
            "verified_restore_paths": verified_paths,
            "sha256": hashes,
        }
    return {
        "schema_version": "LocalArtifactIsolationRestoreProof.v1",
        "batch_id": batch_id,
        "result": "RESTORE_PROOF_PASS",
        "superseded_restore_proof_path": str(old_proof_path),
        "superseded_restore_proof_sha256": _sha256_path(old_proof_path),
        "families": verified_families,
    }, proof_ids


def execute_manifest_supersession(
    *, source_root: Path, archive_base: Path, batch_id: str,
    archive_payload_batch_id: str, supersedes_batch_root: Path,
    supersedes_manifest_sha256: str, retained_dates: list[str], current_date: str,
    quiesce_evidence_path: Path, quiesce_evidence_sha256: str,
    quiesce_sidecar_path: Path, quiesce_sidecar_sha256: str,
    expected_entry_count: int = 10227,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", batch_id):
        raise ArchiveBlocked("invalid_batch_id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", archive_payload_batch_id):
        raise ArchiveBlocked("invalid_archive_payload_batch_id")
    for name, value in (
        ("supersedes_manifest_sha256", supersedes_manifest_sha256),
        ("quiesce_evidence_sha256", quiesce_evidence_sha256),
        ("quiesce_sidecar_sha256", quiesce_sidecar_sha256),
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ArchiveBlocked(f"invalid_{name}")
    if len(retained_dates) != 6 or len(set(retained_dates)) != 6:
        raise ArchiveBlocked("invalid_retained_date_set")
    if current_date not in retained_dates or any(not _valid_date(value, current_date) for value in retained_dates):
        raise ArchiveBlocked("invalid_retained_date")
    if not archive_base.is_dir() or archive_base.is_symlink():
        raise ArchiveBlocked("archive_base_missing_or_unsafe")

    source_root = source_root.resolve(strict=True)
    old_batch_root = supersedes_batch_root.resolve(strict=True)
    if old_batch_root.name != f"batch={archive_payload_batch_id}":
        raise ArchiveBlocked("archive_payload_batch_id_path_mismatch")
    if not _inside(old_batch_root, archive_base.resolve(strict=True)):
        raise ArchiveBlocked("supersedes_batch_path_escape")
    old_batch_before = old_batch_root.lstat()
    old_manifest_path = old_batch_root / "manifest.jsonl"
    if _sha256_path(old_manifest_path) != supersedes_manifest_sha256:
        raise ArchiveBlocked("superseded_manifest_hash_mismatch")
    old_entries = [json.loads(line) for line in old_manifest_path.read_text(encoding="utf-8").splitlines()]
    if len(old_entries) != expected_entry_count:
        raise ArchiveBlocked("superseded_manifest_entry_count_mismatch")

    new_entries: list[dict[str, Any]] = []
    seen_sources: set[Path] = set()
    seen_archives: set[Path] = set()
    for old_entry in old_entries:
        source_path = Path(old_entry["source_path"])
        archive_path = Path(old_entry["archive_path"])
        source_resolved = source_path.resolve(strict=True)
        archive_resolved = archive_path.resolve(strict=True)
        if not _inside(source_resolved, source_root):
            raise ArchiveBlocked(f"source_path_escape:{source_path}")
        if not _inside(archive_resolved, old_batch_root / "files"):
            raise ArchiveBlocked(f"archive_path_escape:{archive_path}")
        if source_resolved in seen_sources or archive_resolved in seen_archives:
            raise ArchiveBlocked("duplicate_source_or_archive_path")
        seen_sources.add(source_resolved)
        seen_archives.add(archive_resolved)
        trade_date = old_entry.get("trade_date")
        if not isinstance(trade_date, str) or not _valid_date(trade_date, current_date):
            raise ArchiveBlocked(f"invalid_trade_date:{source_path}")
        if trade_date in retained_dates:
            raise ArchiveBlocked(f"retained_date_overlap:{source_path}")
        if old_entry.get("artifact_family") not in FAMILIES:
            raise ArchiveBlocked(f"invalid_artifact_family:{source_path}")
        if old_entry.get("reference_classification") != "historical_non_retained_active_current_lineage_zero_v1":
            raise ArchiveBlocked(f"active_current_lineage_not_excluded:{source_path}")

        source_before = _regular_lstat(source_path)
        archive_before = _regular_lstat(archive_path)
        old_logical = _legacy_source_bytes(old_entry, "source_logical_bytes", "logical_bytes")
        old_allocated = _legacy_source_bytes(old_entry, "source_allocated_bytes", "allocated_bytes")
        if (
            source_before.st_dev != old_entry.get("source_device")
            or source_before.st_ino != old_entry.get("source_inode")
            or format(stat.S_IMODE(source_before.st_mode), "04o") != old_entry.get("source_mode")
            or source_before.st_mtime_ns != old_entry.get("source_mtime_ns")
            or source_before.st_size != old_logical
            or source_before.st_blocks * 512 != old_allocated
        ):
            raise ArchiveBlocked(f"source_identity_drift:{source_path}")
        source_sha = _sha256_path(source_path)
        archive_sha = _sha256_path(archive_path)
        source_after = _regular_lstat(source_path)
        archive_after = _regular_lstat(archive_path)
        if _identity(source_before) != _identity(source_after):
            raise ArchiveBlocked(f"source_drift_during_hash:{source_path}")
        if _identity(archive_before) != _identity(archive_after):
            raise ArchiveBlocked(f"archive_drift_during_hash:{archive_path}")
        if (
            source_sha != archive_sha
            or source_sha != old_entry.get("source_sha256")
            or archive_sha != old_entry.get("archive_sha256")
        ):
            raise ArchiveBlocked(f"source_archive_hash_mismatch:{source_path}")
        new_entries.append({
            "source_path": str(source_path),
            "trade_date": trade_date,
            "artifact_family": old_entry["artifact_family"],
            "source_device": source_before.st_dev,
            "source_inode": source_before.st_ino,
            "source_mode": format(stat.S_IMODE(source_before.st_mode), "04o"),
            "source_mtime_ns": source_before.st_mtime_ns,
            "source_logical_bytes": source_before.st_size,
            "source_allocated_bytes": source_before.st_blocks * 512,
            "source_sha256": source_sha,
            "archive_path": str(archive_path),
            "archive_sha256": archive_sha,
            "reference_classification": old_entry["reference_classification"],
            "restore_proof_id": "pending",
        })

    restore_proof, proof_ids = _verify_superseded_restore_proof(
        old_batch_root=old_batch_root, old_entries=old_entries, batch_id=batch_id
    )
    for entry in new_entries:
        entry["restore_proof_id"] = proof_ids[entry["artifact_family"]]

    batch_root = archive_base / f"batch={batch_id}"
    _mkdir_new(batch_root)
    try:
        evidence_before = _regular_lstat(quiesce_evidence_path)
        sidecar_before = _regular_lstat(quiesce_sidecar_path)
        evidence_payload = quiesce_evidence_path.read_bytes()
        sidecar_payload = quiesce_sidecar_path.read_bytes()
        if hashlib.sha256(evidence_payload).hexdigest() != quiesce_evidence_sha256:
            raise ArchiveBlocked("quiesce_evidence_hash_mismatch")
        if hashlib.sha256(sidecar_payload).hexdigest() != quiesce_sidecar_sha256:
            raise ArchiveBlocked("quiesce_sidecar_hash_mismatch")
        sidecar_parts = sidecar_payload.decode("utf-8").strip().split()
        if sidecar_parts != [quiesce_evidence_sha256, "phase_evidence.json"]:
            raise ArchiveBlocked("quiesce_sidecar_content_mismatch")
        if _identity(evidence_before) != _identity(_regular_lstat(quiesce_evidence_path)):
            raise ArchiveBlocked("quiesce_evidence_drift")
        if _identity(sidecar_before) != _identity(_regular_lstat(quiesce_sidecar_path)):
            raise ArchiveBlocked("quiesce_sidecar_drift")
        copied_evidence = batch_root / "inputs" / "phase_evidence.json"
        copied_sidecar = batch_root / "inputs" / "phase_evidence.json.sha256"
        _atomic_write(copied_evidence, evidence_payload, batch_root)
        _atomic_write(copied_sidecar, sidecar_payload, batch_root)
        if _sha256_path(copied_evidence) != quiesce_evidence_sha256:
            raise ArchiveBlocked("copied_quiesce_evidence_hash_mismatch")
        if _sha256_path(copied_sidecar) != quiesce_sidecar_sha256:
            raise ArchiveBlocked("copied_quiesce_sidecar_hash_mismatch")

        restore_path = batch_root / "restore_proof.json"
        _atomic_write(restore_path, _canonical_json(restore_proof), batch_root)
        restore_sha = _sha256_path(restore_path)
        manifest_path = batch_root / "manifest.jsonl"
        _atomic_write(manifest_path, b"".join(_canonical_json(entry) for entry in new_entries), batch_root)
        manifest_sha = _sha256_path(manifest_path)
        allowlist_entries = [{
            **entry,
            "manifest_sha256": manifest_sha,
            "retained_date_overlap": 0,
            "active_current_lineage_overlap": 0,
            "source_identity_stable": True,
            "archive_fully_verified": True,
        } for entry in new_entries]
        allowlist_path = batch_root / "exact_cleanup_allowlist.jsonl"
        _atomic_write(allowlist_path, b"".join(_canonical_json(entry) for entry in allowlist_entries), batch_root)
        allowlist_sha = _sha256_path(allowlist_path)

        source_logical_total = sum(entry["source_logical_bytes"] for entry in new_entries)
        source_allocated_total = sum(entry["source_allocated_bytes"] for entry in new_entries)
        archive_logical_total = sum(Path(entry["archive_path"]).lstat().st_size for entry in new_entries)
        equality_count = sum(entry["source_sha256"] == entry["archive_sha256"] for entry in new_entries)
        if equality_count != len(new_entries) or archive_logical_total != source_logical_total:
            raise ArchiveBlocked("batch_source_archive_equality_mismatch")
        family_summary = {}
        for family in FAMILIES:
            values = [entry for entry in new_entries if entry["artifact_family"] == family]
            family_summary[family] = {
                "status": "ARCHIVED_VERIFIED" if values else "EMPTY",
                "entry_count": len(values),
                "source_logical_bytes": sum(entry["source_logical_bytes"] for entry in values),
                "source_allocated_bytes": sum(entry["source_allocated_bytes"] for entry in values),
                "archive_logical_bytes": sum(Path(entry["archive_path"]).lstat().st_size for entry in values),
                "source_archive_hash_equality_count": sum(
                    entry["source_sha256"] == entry["archive_sha256"] for entry in values
                ),
            }
        summary = {
            "schema_version": "LocalArtifactArchiveSummary.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "batch_id": batch_id,
            "archive_root": str(batch_root),
            "archive_payload_batch_id": archive_payload_batch_id,
            "supersedes_manifest_sha": supersedes_manifest_sha256,
            "result": "ARCHIVED_VERIFIED",
            "cleanup_eligible": False,
            "ready_for_runtime_exact_reclaim": True,
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_sha,
            "entry_count": len(new_entries),
            "source_logical_bytes_total": source_logical_total,
            "source_allocated_bytes_total": source_allocated_total,
            "archive_logical_bytes_total": archive_logical_total,
            "source_archive_hash_equality_count": equality_count,
            "retained_trade_dates": retained_dates,
            "restore_proof_result": "RESTORE_PROOF_PASS",
            "restore_proof_path": str(restore_path),
            "restore_proof_sha256": restore_sha,
            "allowlist_path": str(allowlist_path),
            "allowlist_sha256": allowlist_sha,
            "quiesce_evidence_source_path": str(quiesce_evidence_path),
            "quiesce_evidence_copied_path": str(copied_evidence),
            "quiesce_evidence_sha256": quiesce_evidence_sha256,
            "quiesce_evidence_sidecar_source_path": str(quiesce_sidecar_path),
            "quiesce_evidence_sidecar_copied_path": str(copied_sidecar),
            "quiesce_evidence_sidecar_sha256": quiesce_sidecar_sha256,
            "retained_date_overlap": 0,
            "active_current_lineage_overlap": 0,
            "source_mutation_count": 0,
            "archive_payload_batch_mutation_count": 0,
            "database_writes": 0,
            "service_operations": 0,
            "families": family_summary,
            "blockers": [],
        }
        if _identity(old_batch_before) != _identity(old_batch_root.lstat()):
            raise ArchiveBlocked("archive_payload_batch_root_drift")
        summary_path = batch_root / "summary.json"
        _atomic_write(summary_path, _canonical_json(summary), batch_root)
        summary["summary_path"] = str(summary_path)
        summary["summary_sha256"] = _sha256_path(summary_path)
        return summary
    except BaseException as exc:
        failure = {
            "schema_version": "LocalArtifactArchiveSummary.v1",
            "batch_id": batch_id,
            "archive_root": str(batch_root),
            "archive_payload_batch_id": archive_payload_batch_id,
            "result": "BLOCKED",
            "cleanup_eligible": False,
            "ready_for_runtime_exact_reclaim": False,
            "source_mutation_count": 0,
            "archive_payload_batch_mutation_count": 0,
            "database_writes": 0,
            "service_operations": 0,
            "blockers": [str(exc)],
        }
        try:
            _atomic_write(batch_root / "failure_summary.json", _canonical_json(failure), batch_root)
        except BaseException:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute one LocalArtifactArchiveManifest.v1 archive-only batch.")
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--archive-base", type=Path, default=ARCHIVE_BASE)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--current-date", required=True)
    parser.add_argument("--retained-trade-date", action="append", required=True)
    parser.add_argument("--cleanup-quiesce-evidence-sha256", required=True)
    parser.add_argument("--supersedes-batch-root", type=Path)
    parser.add_argument("--archive-payload-batch-id")
    parser.add_argument("--supersedes-manifest-sha256")
    parser.add_argument("--quiesce-evidence-path", type=Path)
    parser.add_argument("--quiesce-evidence-sidecar-path", type=Path)
    parser.add_argument("--quiesce-evidence-sidecar-sha256")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.execute or not args.user_confirmed:
        print(json.dumps({"result": "BLOCKED_EXECUTE_CONFIRMATION_REQUIRED", "source_mutation_count": 0}, sort_keys=True))
        return 2
    try:
        if args.supersedes_batch_root is not None:
            if args.quiesce_evidence_path != EXACT_QUIESCE_EVIDENCE_PATH:
                raise ArchiveBlocked("exact_quiesce_evidence_path_required")
            if args.quiesce_evidence_sidecar_path != EXACT_QUIESCE_SIDECAR_PATH:
                raise ArchiveBlocked("exact_quiesce_evidence_sidecar_path_required")
            if not args.archive_payload_batch_id or not args.supersedes_manifest_sha256:
                raise ArchiveBlocked("supersession_identity_required")
            if not args.quiesce_evidence_sidecar_sha256:
                raise ArchiveBlocked("quiesce_evidence_sidecar_sha256_required")
            summary = execute_manifest_supersession(
                source_root=args.source_root,
                archive_base=args.archive_base,
                batch_id=args.batch_id,
                archive_payload_batch_id=args.archive_payload_batch_id,
                supersedes_batch_root=args.supersedes_batch_root,
                supersedes_manifest_sha256=args.supersedes_manifest_sha256,
                retained_dates=args.retained_trade_date,
                current_date=args.current_date,
                quiesce_evidence_path=args.quiesce_evidence_path,
                quiesce_evidence_sha256=args.cleanup_quiesce_evidence_sha256,
                quiesce_sidecar_path=args.quiesce_evidence_sidecar_path,
                quiesce_sidecar_sha256=args.quiesce_evidence_sidecar_sha256,
            )
        else:
            summary = execute_archive(
                source_root=args.source_root,
                archive_base=args.archive_base,
                batch_id=args.batch_id,
                retained_dates=args.retained_trade_date,
                current_date=args.current_date,
                quiesce_evidence_sha256=args.cleanup_quiesce_evidence_sha256,
            )
    except (ArchiveBlocked, FileExistsError, OSError) as exc:
        print(json.dumps({"result": "BLOCKED", "blockers": [str(exc)], "source_mutation_count": 0}, sort_keys=True))
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
