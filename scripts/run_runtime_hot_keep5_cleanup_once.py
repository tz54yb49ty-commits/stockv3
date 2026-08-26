#!/usr/bin/env python3
"""Plan or execute manifest-gated runtime hot-store keep-5 cleanup."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from time import perf_counter
from typing import Any, Callable, Iterable, Iterator
from zoneinfo import ZoneInfo

from ashare_v3.ingestion.runtime_archive import DEFAULT_RUNTIME_ARCHIVE_ROOT, runtime_archive_side_effects
from ashare_v3.ingestion.runtime_archive_execute import DEFAULT_DSN
from ashare_v3.ingestion.runtime_hot_cleanup import (
    DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN,
    KEEP5_CONFIRM_TOKEN,
    RuntimeHotCleanupSpec,
    append_durable_progress_journal,
    build_runtime_hot_cleanup_plan_v2,
    build_keep2_dirty_hot_cleanup_plan,
    execute_frozen_inbox_units,
    execute_keep2_dirty_hot_cleanup,
    execute_runtime_hot_cleanup_database_v2,
)


DEFAULT_REPORT_DIR = "docs/runtime_archive/hot_keep5_cleanup"
DEFAULT_RETENTION_TRADE_DAYS = 5
LOCAL_ARCHIVE_MANIFEST_SCHEMA = "LocalArtifactArchiveManifest.v1"
LOCAL_ARCHIVE_REQUIRED_MODE = "verified-archive-required"
LOCAL_ARCHIVE_CURRENT_POINTER_SCHEMA = "LocalArtifactArchiveCurrentPointer.v1"
LOCAL_ARCHIVE_CURRENT_POINTER_NAME = "current_verified_batch.json"
DEFAULT_SINGLE_FLIGHT_LOCK_NAME = ".keep5_cleanup.lock"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
ARCHIVE_WRAPPER_SCRIPT = "scripts/run_v3_runtime_archive_keep5_daily_once.py"
RUNTIME_ARTIFACT_PREFIXES = ("n3_", "n4_", "n5_")
TMP_ARTIFACT_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^N3P_(\d{8})_(\d{4})_trigger_proof_contract\.json$"), "n3"),
    (re.compile(r"^N3_hint_(\d{8})_(\d{4})_midday_bridge_v1_contract\.json$"), "n3"),
    (re.compile(r"^N4_(\d{8})_(\d{4})_(?:ordinary_matcher|hint_matcher)_execute_report\.json$"), "n4"),
)
N5_DATED_ARTIFACT_ROOTS = (
    "tmp/N5_N3T_action_confirmation_fastlane_monitor",
    "tmp/N5_N3T_action_confirmation_fastlane_open_monitor_precheck",
    "tmp/n5_active_scope_terminal_ref_repair",
)
RUNTIME_WRITER_MARKERS = (
    "scripts/run_n3_",
    "scripts/run_n4_",
    "scripts/run_n5_",
    "scripts/run_n6_",
    "run_n3_",
    "run_n4_",
    "run_n5_",
    "run_n6_",
    "provisional_ordinary",
    "provisional_projection",
    "intraday_proof_poller",
    "proof_discovery_poll",
    "live_tracking_poller",
)
RUNTIME_WRITER_EXCLUDE_MARKERS = (
    "scripts/run_runtime_hot_keep5_cleanup_once.py",
    "scripts/run_runtime_dirty_hot_keep2_cleanup_once.py",
    "scripts/run_v3_runtime_archive_keep5_daily_once.py",
    "run_n6_user_app.py",
    "run_n6_ai_research_bridge.py",
    "run_n6_virtual_executor_once.py",
    "run_n6_virtual_stop_loss_once.py",
    "run_n6_virtual_quote_once.py",
)


class CleanupAlreadyRunningError(RuntimeError):
    def __init__(self, lock_path: Path, holder_evidence: str) -> None:
        super().__init__(f"cleanup already running; lock_path={lock_path}")
        self.lock_path = lock_path
        self.holder_evidence = holder_evidence


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=json_default) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def cleanup_local_runtime_artifacts(
    *,
    project_root: str | Path = PROJECT_ROOT,
    retention_trade_days: int = DEFAULT_RETENTION_TRADE_DAYS,
    retained_trade_dates: Iterable[str] | None = None,
    cleanup_trade_dates: Iterable[str] | None = None,
    execute: bool = False,
    direct_delete_no_archive: bool = False,
    confirm_token: str = "",
    current_date: date | None = None,
) -> dict[str, Any]:
    """Plan or delete exact N3/N4/N5 daily filesystem artifacts."""

    started_monotonic = perf_counter()
    started_at = datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()
    today = current_date or datetime.now(ASIA_SHANGHAI).date()
    root_input = Path(project_root)
    payload = _local_file_cleanup_base(execute=execute, project_root=root_input, started_at=started_at)

    if retention_trade_days != DEFAULT_RETENTION_TRADE_DAYS:
        payload["blockers"] = ["retention_trade_days_must_equal_5"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_RETENTION_CONTRACT")
    if root_input.is_symlink() or not root_input.is_dir():
        payload["blockers"] = ["project_root_missing_or_symlink"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_PROJECT_ROOT")
    if execute and (
        not direct_delete_no_archive or confirm_token != DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN
    ):
        payload["blockers"] = ["direct_delete_confirm_token_required"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_CONFIRM_TOKEN")

    if retained_trade_dates is None or cleanup_trade_dates is None:
        payload["blockers"] = ["authoritative_trade_date_partition_required"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_TRADE_DATE_PARTITION")
    retained_dates = [str(item) for item in retained_trade_dates]
    cleanup_dates = [str(item) for item in cleanup_trade_dates]
    partition_dates = retained_dates + cleanup_dates
    if (
        retained_dates != sorted(set(retained_dates))
        or cleanup_dates != sorted(set(cleanup_dates))
        or set(retained_dates).intersection(cleanup_dates)
        or len(retained_dates) > retention_trade_days
        or any(not _valid_local_artifact_trade_date(item, today=today) for item in partition_dates)
    ):
        payload["blockers"] = ["authoritative_trade_date_partition_invalid"]
        return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_TRADE_DATE_PARTITION")

    root = root_input.resolve()
    targets, skipped = _discover_local_artifact_targets(root, today=today)
    cleanup_set = set(cleanup_dates)
    payload.update(
        {
            "project_root": str(root),
            "retained_trade_dates": retained_dates,
            "cleanup_trade_dates": cleanup_dates,
            "skipped_count": len(skipped),
            "skipped": skipped,
        }
    )

    safe_targets: list[tuple[dict[str, Any], dict[str, int]]] = []
    for target in targets:
        if target["trade_date"] not in cleanup_set:
            continue
        stats, error = _local_artifact_target_stats(Path(target["path"]))
        if error:
            payload["errors"].append(error)
            continue
        safe_targets.append((target, stats))
        _add_local_file_counts(payload, layer=str(target["layer"]), prefix="candidate", stats=stats)

    if execute:
        for target, stats in safe_targets:
            path = Path(target["path"])
            try:
                if path.is_symlink():
                    raise OSError("symlink target refused")
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except OSError as exc:
                payload["errors"].append(f"delete_failed:{path}:{exc}")
                continue
            _add_local_file_counts(payload, layer=str(target["layer"]), prefix="deleted", stats=stats)
            payload["released_bytes"] += stats["bytes"]
        payload["deleted_empty_date_directory_count"] = _remove_empty_runtime_date_directories(
            root / "docs/runtime",
            cleanup_dates,
        )
        payload["deleted_directory_count"] += payload["deleted_empty_date_directory_count"]
        payload["cleanup_executed"] = True
        result = "LOCAL_FILE_KEEP5_EXECUTE_PASS" if not payload["errors"] else "LOCAL_FILE_KEEP5_EXECUTE_PARTIAL"
    else:
        result = "LOCAL_FILE_KEEP5_DRY_RUN_PASS" if not payload["errors"] else "LOCAL_FILE_KEEP5_DRY_RUN_PARTIAL"

    if payload["errors"]:
        payload["blockers"] = ["local_artifact_cleanup_errors"]
    payload["side_effects"]["cleanup_local_runtime_files"] = bool(
        payload["deleted_file_count"] or payload["deleted_directory_count"]
    )
    return _finish_local_file_cleanup(payload, started_monotonic, result=result)


def discover_local_artifact_files(
    *, project_root: str | Path, current_date: date | None = None
) -> list[dict[str, Any]]:
    """Discover the local date domain and exact regular files independently of DB."""

    root = Path(project_root).resolve()
    today = current_date or datetime.now(ASIA_SHANGHAI).date()
    targets, skipped = _discover_local_artifact_targets(root, today=today)
    if skipped:
        raise ValueError("local_artifact_discovery_not_closed:" + ";".join(skipped))
    files: list[dict[str, Any]] = []
    for target in targets:
        path = Path(target["path"])
        for candidate in _discover_regular_files_under_target(path, root=root):
            relative = candidate.relative_to(root)
            family = (
                "n3p_trigger_proof_contract"
                if candidate.name.startswith("N3P_")
                else "post_close_fastlane"
                if any("post_close_fastlane" in part for part in relative.parts)
                else "runtime_date_directory"
                if relative.parts[:2] == ("docs", "runtime")
                else "intraday_live_current"
            )
            files.append(
                {
                    "source_path": str(candidate),
                    "trade_date": str(target["trade_date"]),
                    "artifact_family": family,
                }
            )
    return sorted(files, key=lambda item: str(item["source_path"]))


def _discover_regular_files_under_target(path: Path, *, root: Path) -> list[Path]:
    """Return only regular files, rejecting every unsafe path in a declared scope."""

    try:
        root.lstat()
        first = path.lstat()
    except OSError as exc:
        raise ValueError(f"local_artifact_discovery_stat_failed:{path}:{type(exc).__name__}") from exc
    if stat.S_ISLNK(first.st_mode):
        raise ValueError(f"local_artifact_discovery_symlink:{path}")
    if stat.S_ISREG(first.st_mode):
        candidates = [path]
    elif stat.S_ISDIR(first.st_mode):
        candidates = []
        stack = [path]
        while stack:
            directory = stack.pop()
            try:
                children = sorted(Path(item.path) for item in os.scandir(directory))
            except OSError as exc:
                raise ValueError(f"local_artifact_discovery_scan_failed:{directory}:{type(exc).__name__}") from exc
            for child in children:
                try:
                    child_stat = child.lstat()
                except OSError as exc:
                    raise ValueError(f"local_artifact_discovery_stat_failed:{child}:{type(exc).__name__}") from exc
                if stat.S_ISLNK(child_stat.st_mode):
                    raise ValueError(f"local_artifact_discovery_symlink:{child}")
                if stat.S_ISDIR(child_stat.st_mode):
                    stack.append(child)
                elif stat.S_ISREG(child_stat.st_mode):
                    candidates.append(child)
                else:
                    raise ValueError(f"local_artifact_discovery_non_regular:{child}")
    else:
        raise ValueError(f"local_artifact_discovery_non_regular:{path}")
    for candidate in candidates:
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"local_artifact_discovery_path_escape:{candidate}") from exc
    return sorted(candidates, key=str)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_local_archive_current_pointer(
    *,
    pointer_path: str | Path,
    for_cleanup_date: str,
    archive_root: str | Path,
) -> tuple[dict[str, Path], dict[str, Any], list[str]]:
    """Resolve a current-date pointer to one immutable verified archive batch."""

    pointer = Path(pointer_path)
    archive_base = Path(archive_root)
    try:
        archive_stat = archive_base.lstat()
        pointer_stat = pointer.lstat()
        archive_resolved = archive_base.resolve(strict=True)
        pointer_resolved = pointer.resolve(strict=True)
    except OSError:
        return {}, {}, ["local_archive_pointer_missing_or_unsafe"]
    if (
        not stat.S_ISDIR(archive_stat.st_mode)
        or archive_base.is_symlink()
        or not stat.S_ISREG(pointer_stat.st_mode)
        or pointer.is_symlink()
        or pointer.name != LOCAL_ARCHIVE_CURRENT_POINTER_NAME
        or pointer_resolved.parent != archive_resolved
    ):
        return {}, {}, ["local_archive_pointer_missing_or_unsafe"]
    try:
        raw = pointer.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}, {}, ["local_archive_pointer_invalid"]
    if not isinstance(payload, dict):
        return {}, {}, ["local_archive_pointer_invalid"]
    blockers: list[str] = []
    if payload.get("schema_version") != LOCAL_ARCHIVE_CURRENT_POINTER_SCHEMA:
        blockers.append("local_archive_pointer_schema_mismatch")
    if str(payload.get("for_cleanup_date") or "") != for_cleanup_date:
        blockers.append("local_archive_pointer_cleanup_date_mismatch")
    if payload.get("result") != "ARCHIVED_VERIFIED":
        blockers.append("local_archive_pointer_result_mismatch")
    if payload.get("restore_proof_result") != "RESTORE_PROOF_PASS":
        blockers.append("local_archive_pointer_restore_proof_mismatch")
    batch_id = str(payload.get("batch_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", batch_id):
        blockers.append("local_archive_pointer_batch_id_invalid")
    raw_entry_count = payload.get("entry_count")
    if type(raw_entry_count) is not int:
        entry_count = -1
    else:
        entry_count = raw_entry_count
    if entry_count < 0:
        blockers.append("local_archive_pointer_entry_count_invalid")
    retained_dates = [str(item) for item in payload.get("retained_trade_dates") or []]
    if (
        len(retained_dates) != 6
        or len(set(retained_dates)) != 6
        or for_cleanup_date not in retained_dates
        or any(not re.fullmatch(r"\d{8}", item) for item in retained_dates)
    ):
        blockers.append("local_archive_pointer_retained_dates_invalid")

    evidence_paths: dict[str, Path] = {}
    expected_names = {
        "manifest": "manifest.jsonl",
        "summary": "summary.json",
        "allowlist": "exact_cleanup_allowlist.jsonl",
        "restore_proof": "restore_proof.json",
    }
    batch_root = archive_resolved / f"batch={batch_id}"
    try:
        batch_stat = batch_root.lstat()
        batch_resolved = batch_root.resolve(strict=True)
    except OSError:
        batch_stat = None
        batch_resolved = batch_root
        blockers.append("local_archive_pointer_batch_root_invalid")
    if batch_stat is not None and (not stat.S_ISDIR(batch_stat.st_mode) or batch_root.is_symlink()):
        blockers.append("local_archive_pointer_batch_root_invalid")
    for field, expected_name in expected_names.items():
        evidence = payload.get(field)
        if not isinstance(evidence, dict):
            blockers.append(f"local_archive_pointer_{field}_invalid")
            continue
        evidence_path = Path(str(evidence.get("path") or ""))
        expected_sha = str(evidence.get("sha256") or "")
        try:
            evidence_stat = evidence_path.lstat()
            evidence_resolved = evidence_path.resolve(strict=True)
        except OSError:
            blockers.append(f"local_archive_pointer_{field}_invalid")
            continue
        if (
            not evidence_path.is_absolute()
            or not stat.S_ISREG(evidence_stat.st_mode)
            or evidence_path.is_symlink()
            or evidence_resolved.parent != batch_resolved
            or evidence_resolved.name != expected_name
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
        ):
            blockers.append(f"local_archive_pointer_{field}_invalid")
            continue
        if _sha256_file(evidence_resolved) != expected_sha:
            blockers.append(f"local_archive_pointer_{field}_sha256_mismatch")
            continue
        evidence_paths[field] = evidence_resolved
    summary_path = evidence_paths.get("summary")
    if summary_path is not None:
        try:
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            blockers.append("local_archive_pointer_summary_invalid")
        else:
            if not isinstance(summary_payload, dict) or str(summary_payload.get("batch_id") or "") != batch_id:
                blockers.append("local_archive_pointer_batch_binding_mismatch")
    metadata = {
        "schema_version": str(payload.get("schema_version") or ""),
        "pointer_path": str(pointer_resolved),
        "pointer_sha256": hashlib.sha256(raw).hexdigest(),
        "for_cleanup_date": str(payload.get("for_cleanup_date") or ""),
        "batch_id": batch_id,
        "retained_trade_dates": retained_dates,
        "entry_count": entry_count,
        "result": str(payload.get("result") or ""),
        "restore_proof_result": str(payload.get("restore_proof_result") or ""),
    }
    return evidence_paths, metadata, sorted(set(blockers))


def load_verified_local_archive_allowlist(
    *,
    manifest_path: str | Path,
    batch_summary_path: str | Path,
    allowlist_path: str | Path,
    restore_proof_path: str | Path,
    discovered_cleanup_files: Iterable[dict[str, Any]],
    retained_trade_dates: Iterable[str],
    archive_root: str | Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate the frozen manifest, summary, allowlist, and restore proof."""

    blockers: list[str] = []
    manifest = Path(manifest_path)
    summary_path = Path(batch_summary_path)
    allowlist = Path(allowlist_path)
    restore_proof = Path(restore_proof_path)
    try:
        raw = manifest.read_bytes()
        entries = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        allowlist_raw = allowlist.read_bytes()
        allowlist_entries = [json.loads(line) for line in allowlist_raw.decode("utf-8").splitlines() if line.strip()]
        restore = json.loads(restore_proof.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [], [f"local_archive_evidence_invalid:{type(exc).__name__}"]
    manifest_sha256 = hashlib.sha256(raw).hexdigest()
    allowlist_sha256 = hashlib.sha256(allowlist_raw).hexdigest()
    if summary.get("schema_version") != "LocalArtifactArchiveSummary.v1":
        blockers.append("local_archive_summary_schema_mismatch")
    if summary.get("result") != "ARCHIVED_VERIFIED" or summary.get("ready_for_runtime_exact_reclaim") is not True:
        blockers.append("local_archive_summary_not_ready_for_exact_reclaim")
    if summary.get("restore_proof_result") != "RESTORE_PROOF_PASS":
        blockers.append("local_archive_restore_proof_not_pass")
    if summary.get("manifest_sha256") != manifest_sha256:
        blockers.append("local_archive_manifest_sha256_mismatch")
    if summary.get("allowlist_sha256") != allowlist_sha256:
        blockers.append("local_archive_allowlist_sha256_mismatch")
    if summary.get("restore_proof_sha256") != _sha256_file(restore_proof):
        blockers.append("local_archive_restore_proof_sha256_mismatch")
    for field, expected_path in (
        ("manifest_path", manifest),
        ("allowlist_path", allowlist),
        ("restore_proof_path", restore_proof),
    ):
        if Path(str(summary.get(field) or "")).resolve() != expected_path.resolve():
            blockers.append(f"local_archive_summary_{field}_mismatch")
    summary_entry_count = summary.get("entry_count")
    if type(summary_entry_count) is not int or summary_entry_count != len(entries):
        blockers.append("local_archive_manifest_entry_count_mismatch")
    required_batch_fields = {
        "batch_id", "manifest_sha256", "entry_count", "source_logical_bytes_total",
        "source_allocated_bytes_total", "archive_logical_bytes_total",
        "source_archive_hash_equality_count", "retained_trade_dates", "restore_proof_result",
    }
    if not required_batch_fields.issubset(summary):
        blockers.append("local_archive_batch_fields_missing")
    retained = set(str(item) for item in retained_trade_dates)
    if restore.get("schema_version") != "LocalArtifactIsolationRestoreProof.v1" or restore.get("result") != "RESTORE_PROOF_PASS":
        blockers.append("local_archive_restore_proof_schema_or_result_mismatch")
    if restore.get("batch_id") != summary.get("batch_id"):
        blockers.append("local_archive_restore_proof_batch_id_mismatch")
    def scope_key(item: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(item.get("source_path") or ""),
            str(item.get("trade_date") or ""),
            str(item.get("artifact_family") or ""),
        )

    required_rows = [dict(item) for item in discovered_cleanup_files]
    required = {scope_key(item): item for item in required_rows}
    manifest_entries = {scope_key(item): item for item in entries}
    actual = {scope_key(item): item for item in allowlist_entries}
    if (
        len(required) != len(required_rows)
        or len(manifest_entries) != len(entries)
        or len(actual) != len(allowlist_entries)
        or set(manifest_entries) != set(required)
        or set(actual) != set(required)
        or any(not key[0] or not key[1] or not key[2] for key in actual)
    ):
        blockers.append("local_archive_exact_allowlist_mismatch")
    archive_base = Path(archive_root).resolve()
    required_fields = {
        "source_path", "trade_date", "artifact_family", "source_device", "source_inode",
        "source_mode", "source_mtime_ns", "source_logical_bytes", "source_allocated_bytes",
        "source_sha256", "archive_path", "archive_sha256", "reference_classification",
        "restore_proof_id",
    }
    restore_families = restore.get("families") if isinstance(restore.get("families"), dict) else {}
    archive_logical_total = 0
    for entry in allowlist_entries:
        if not required_fields.issubset(entry):
            blockers.append(f"local_archive_entry_fields_missing:{entry.get('source_path', '')}")
            continue
        manifest_entry = manifest_entries.get(scope_key(entry))
        if manifest_entry is None or any(manifest_entry.get(key) != entry.get(key) for key in required_fields):
            blockers.append(f"local_archive_allowlist_manifest_binding_mismatch:{entry['source_path']}")
        if entry.get("manifest_sha256") != manifest_sha256:
            blockers.append(f"local_archive_allowlist_manifest_sha256_mismatch:{entry['source_path']}")
        family_proof = restore_families.get(str(entry["artifact_family"]))
        if not isinstance(family_proof, dict) or family_proof.get("restore_proof_id") != entry["restore_proof_id"]:
            blockers.append(f"local_archive_allowlist_restore_proof_binding_mismatch:{entry['source_path']}")
        if str(entry["trade_date"]) in retained:
            blockers.append(f"local_archive_retained_date_overlap:{entry['trade_date']}")
        if int(entry.get("retained_date_overlap") or 0):
            blockers.append(f"local_archive_retained_overlap_flag:{entry['source_path']}")
        if int(entry.get("active_current_lineage_overlap") or 0):
            blockers.append(f"local_archive_active_lineage_overlap:{entry['source_path']}")
        if entry.get("archive_fully_verified") is False:
            blockers.append(f"local_archive_entry_not_fully_verified:{entry['source_path']}")
        if str(entry["source_sha256"]) != str(entry["archive_sha256"]):
            blockers.append(f"local_archive_hash_inequality:{entry['source_path']}")
        archive_path = Path(str(entry["archive_path"]))
        try:
            archive_stat = archive_path.lstat()
            archive_resolved = archive_path.resolve(strict=True)
        except OSError:
            blockers.append(f"local_archive_entry_archive_invalid:{entry['archive_path']}")
            continue
        if (
            not stat.S_ISREG(archive_stat.st_mode)
            or archive_path.is_symlink()
            or archive_base not in archive_resolved.parents
        ):
            blockers.append(f"local_archive_path_outside_root:{entry['archive_path']}")
            continue
        archive_logical_total += int(archive_stat.st_size)
        entry["exact_allowlisted"] = True
        entry["archive_fully_verified"] = True
    source_logical_total = sum(int(entry.get("source_logical_bytes") or 0) for entry in allowlist_entries)
    source_allocated_total = sum(int(entry.get("source_allocated_bytes") or 0) for entry in allowlist_entries)
    expected_summary_counts = (
        ("source_logical_bytes_total", source_logical_total, "local_archive_source_logical_bytes_total_mismatch"),
        ("source_allocated_bytes_total", source_allocated_total, "local_archive_source_allocated_bytes_total_mismatch"),
        ("archive_logical_bytes_total", archive_logical_total, "local_archive_logical_bytes_total_mismatch"),
        ("source_archive_hash_equality_count", len(allowlist_entries), "local_archive_hash_equality_count_mismatch"),
    )
    for field, expected, blocker in expected_summary_counts:
        actual = summary.get(field)
        if type(actual) is not int or actual != expected:
            blockers.append(blocker)
    if sorted(str(item) for item in summary.get("retained_trade_dates") or []) != sorted(retained):
        blockers.append("local_archive_retained_trade_dates_mismatch")
    return allowlist_entries, sorted(set(blockers))


def execute_verified_local_allowlist(
    *,
    entries: Iterable[dict[str, Any]],
    active_paths: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """Unlink only revalidated regular files from the frozen archive allowlist."""

    active = {str(Path(item).resolve()) for item in active_paths}
    removed: list[str] = []
    for entry in entries:
        source = Path(str(entry["source_path"]))
        archive = Path(str(entry["archive_path"]))
        try:
            source_stat = source.lstat()
            if not stat.S_ISREG(source_stat.st_mode) or source.is_symlink():
                raise OSError("source_not_exact_regular_file")
            archive_stat = archive.lstat()
            if not stat.S_ISREG(archive_stat.st_mode) or archive.is_symlink():
                raise OSError("archive_not_exact_regular_file")
            if str(source.resolve()) in active:
                raise OSError("active_lineage_path")
            expected_mode = int(str(entry["source_mode"]), 8) if isinstance(entry["source_mode"], str) else int(entry["source_mode"])
            expected = (
                int(entry["source_device"]), int(entry["source_inode"]), expected_mode,
                int(entry["source_mtime_ns"]), int(entry["source_logical_bytes"]),
                int(entry["source_allocated_bytes"]),
            )
            actual = (
                int(source_stat.st_dev), int(source_stat.st_ino), int(stat.S_IMODE(source_stat.st_mode)),
                int(source_stat.st_mtime_ns), int(source_stat.st_size),
                int(source_stat.st_blocks * 512),
            )
            if actual != expected:
                raise OSError("source_identity_drift")
            source_sha = _sha256_file(source)
            archive_sha = _sha256_file(archive)
            if source_sha != entry["source_sha256"] or archive_sha != entry["archive_sha256"] or source_sha != archive_sha:
                raise OSError("source_archive_sha256_drift")
            source.unlink()
            removed.append(str(source))
        except Exception as exc:
            return {
                "result": "BLOCKED_LOCAL_ARCHIVE_VERIFIED_RECLAIM",
                "cleanup_complete": False,
                "retry_attempts": 0,
                "removed_paths": removed,
                "failed_path": str(source),
                "error": f"{type(exc).__name__}: {exc}",
            }
    return {
        "result": "LOCAL_ARCHIVE_VERIFIED_RECLAIM_PASS",
        "cleanup_complete": True,
        "retry_attempts": 0,
        "removed_paths": removed,
    }


def blocked_local_file_cleanup(
    *,
    project_root: str | Path,
    execute: bool,
    blocker: str,
) -> dict[str, Any]:
    started_monotonic = perf_counter()
    payload = _local_file_cleanup_base(
        execute=execute,
        project_root=Path(project_root),
        started_at=datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat(),
    )
    payload["blockers"] = [blocker]
    return _finish_local_file_cleanup(payload, started_monotonic, result="BLOCKED_LOCAL_FILE_CLEANUP")


def _local_file_cleanup_base(*, execute: bool, project_root: Path, started_at: str) -> dict[str, Any]:
    per_layer = {
        layer: {
            "candidate_file_count": 0,
            "candidate_directory_count": 0,
            "candidate_bytes": 0,
            "deleted_file_count": 0,
            "deleted_directory_count": 0,
            "released_bytes": 0,
        }
        for layer in ("n3", "n4", "n5")
    }
    return {
        "result": "LOCAL_FILE_KEEP5_NOT_RUN",
        "mode": "execute" if execute else "dry_run",
        "started_at": started_at,
        "finished_at": "",
        "duration_ms": 0,
        "project_root": str(project_root),
        "retention_trade_days": DEFAULT_RETENTION_TRADE_DAYS,
        "retained_trade_dates": [],
        "cleanup_trade_dates": [],
        "candidate_file_count": 0,
        "candidate_directory_count": 0,
        "candidate_bytes": 0,
        "deleted_file_count": 0,
        "deleted_directory_count": 0,
        "deleted_empty_date_directory_count": 0,
        "released_bytes": 0,
        "cleanup_executed": False,
        "skipped_count": 0,
        "skipped": [],
        "errors": [],
        "blockers": [],
        "per_layer": per_layer,
        "side_effects": {
            "writes_database": False,
            "writes_archive_files": False,
            "cleanup_local_runtime_files": False,
            "outbox_inbox_checkpoint_touched": False,
            "launchctl_touched": False,
            "runtime_started": False,
        },
    }


def _finish_local_file_cleanup(payload: dict[str, Any], started_monotonic: float, *, result: str) -> dict[str, Any]:
    payload["result"] = result
    payload["finished_at"] = datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()
    payload["duration_ms"] = round((perf_counter() - started_monotonic) * 1000.0, 3)
    return payload


def _discover_local_artifact_targets(root: Path, *, today: date) -> tuple[list[dict[str, Any]], list[str]]:
    targets: list[dict[str, Any]] = []
    skipped: list[str] = []
    runtime_root = root / "docs/runtime"
    if runtime_root.is_dir() and not runtime_root.is_symlink():
        for date_dir in sorted(runtime_root.iterdir(), key=lambda item: item.name):
            trade_date = _valid_local_artifact_trade_date(date_dir.name, today=today)
            if not trade_date or not date_dir.is_dir() or date_dir.is_symlink():
                continue
            for child in sorted(date_dir.iterdir(), key=lambda item: item.name):
                layer = _runtime_artifact_layer(child.name)
                if not layer:
                    continue
                if child.is_symlink():
                    skipped.append(f"symlink_skipped:{child}")
                    continue
                targets.append({"path": child, "trade_date": trade_date, "layer": layer})

    tmp_root = root / "tmp"
    if tmp_root.is_dir() and not tmp_root.is_symlink():
        for child in sorted(tmp_root.iterdir(), key=lambda item: item.name):
            for pattern, layer in TMP_ARTIFACT_RULES:
                matched = pattern.fullmatch(child.name)
                if not matched:
                    continue
                if child.is_symlink():
                    skipped.append(f"symlink_skipped:{child}")
                    break
                if not child.is_file():
                    break
                trade_date = _valid_local_artifact_trade_date(matched.group(1), today=today)
                if trade_date:
                    targets.append({"path": child, "trade_date": trade_date, "layer": layer})
                else:
                    skipped.append(f"invalid_or_future_date_skipped:{child}")
                break

    for relative_root in N5_DATED_ARTIFACT_ROOTS:
        dated_root = root / relative_root
        if not dated_root.is_dir() or dated_root.is_symlink():
            continue
        for child in sorted(dated_root.iterdir(), key=lambda item: item.name):
            trade_date = _valid_local_artifact_trade_date(child.name, today=today)
            if not trade_date or not child.is_dir():
                continue
            if child.is_symlink():
                skipped.append(f"symlink_skipped:{child}")
                continue
            targets.append({"path": child, "trade_date": trade_date, "layer": "n5"})

    return sorted(targets, key=lambda item: str(item["path"])), skipped


def _runtime_artifact_layer(name: str) -> str:
    lowered = name.lower()
    for prefix in RUNTIME_ARTIFACT_PREFIXES:
        if lowered.startswith(prefix):
            return prefix[:2]
    return ""


def _valid_local_artifact_trade_date(value: str, *, today: date) -> str:
    if not re.fullmatch(r"\d{8}", value):
        return ""
    try:
        parsed = datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return ""
    return value if parsed <= today else ""


def _local_artifact_target_stats(path: Path) -> tuple[dict[str, int], str]:
    try:
        root_stat = path.lstat()
    except OSError as exc:
        return {}, f"stat_failed:{path}:{exc}"
    if stat.S_ISLNK(root_stat.st_mode):
        return {}, f"symlink_skipped:{path}"
    if stat.S_ISREG(root_stat.st_mode):
        return {"file_count": 1, "directory_count": 0, "bytes": int(root_stat.st_size)}, ""
    if not stat.S_ISDIR(root_stat.st_mode):
        return {}, f"non_regular_path_skipped:{path}"

    file_count = 0
    directory_count = 1
    total_bytes = 0
    stack = [path]
    try:
        while stack:
            current = stack.pop()
            with os.scandir(current) as entries:
                for entry in entries:
                    entry_stat = entry.stat(follow_symlinks=False)
                    entry_path = Path(entry.path)
                    if stat.S_ISLNK(entry_stat.st_mode):
                        return {}, f"symlink_skipped:{entry_path}"
                    if stat.S_ISDIR(entry_stat.st_mode):
                        directory_count += 1
                        stack.append(entry_path)
                    elif stat.S_ISREG(entry_stat.st_mode):
                        file_count += 1
                        total_bytes += int(entry_stat.st_size)
                    else:
                        return {}, f"non_regular_path_skipped:{entry_path}"
    except OSError as exc:
        return {}, f"stat_failed:{path}:{exc}"
    return {"file_count": file_count, "directory_count": directory_count, "bytes": total_bytes}, ""


def _add_local_file_counts(payload: dict[str, Any], *, layer: str, prefix: str, stats: dict[str, int]) -> None:
    file_key = f"{prefix}_file_count"
    directory_key = f"{prefix}_directory_count"
    bytes_key = "candidate_bytes" if prefix == "candidate" else "released_bytes"
    payload[file_key] += stats["file_count"]
    payload[directory_key] += stats["directory_count"]
    if prefix == "candidate":
        payload[bytes_key] += stats["bytes"]
    layer_payload = payload["per_layer"][layer]
    layer_payload[file_key] += stats["file_count"]
    layer_payload[directory_key] += stats["directory_count"]
    layer_payload[bytes_key] += stats["bytes"]


def _remove_empty_runtime_date_directories(runtime_root: Path, cleanup_trade_dates: list[str]) -> int:
    removed = 0
    for trade_date in cleanup_trade_dates:
        date_dir = runtime_root / trade_date
        try:
            if date_dir.is_dir() and not date_dir.is_symlink() and not any(date_dir.iterdir()):
                date_dir.rmdir()
                removed += 1
        except OSError:
            continue
    return removed


@contextmanager
def keep5_cleanup_single_flight_lock(report_root: Path) -> Iterator[Path]:
    report_root.mkdir(parents=True, exist_ok=True)
    lock_path = report_root / DEFAULT_SINGLE_FLIGHT_LOCK_NAME
    lock_file = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock_file.seek(0)
            holder_evidence = lock_file.read().strip()
            raise CleanupAlreadyRunningError(lock_path, holder_evidence) from exc

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "started_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
                    "lock_policy": "keep5_cleanup_single_flight_v1",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        lock_file.flush()
        yield lock_path
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


def blocked_already_running_report(*, report_root: Path, execute: bool, error: CleanupAlreadyRunningError) -> dict[str, Any]:
    side_effects = runtime_archive_side_effects()
    side_effects["cleanup_local_runtime_files"] = False
    return {
        "result": "BLOCKED_CLEANUP_ALREADY_RUNNING",
        "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
        "execute": bool(execute),
        "required_confirm_token": KEEP5_CONFIRM_TOKEN,
        "docs_report_path": str(report_root / "keep5_cleanup_status.json"),
        "cleanup_authorized": False,
        "cleanup_executed": False,
        "database_written": False,
        "deleted_total_rows": 0,
        "blockers": ["BLOCKED_CLEANUP_ALREADY_RUNNING"],
        "single_flight_lock_policy": "keep5_cleanup_single_flight_v1",
        "single_flight_lock_acquired": False,
        "single_flight_lock_path": str(error.lock_path),
        "single_flight_lock_holder": error.holder_evidence,
        "side_effects": side_effects,
    }


def read_process_table() -> str:
    """Read the process table without assuming every argv byte is valid UTF-8."""

    output = subprocess.check_output(["ps", "-axo", "pid=,etime=,stat=,comm=,args="])
    return output.decode("utf-8", errors="replace")


def detect_active_archive_processes() -> list[dict[str, Any]]:
    output = read_process_table()
    processes: list[dict[str, Any]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if ARCHIVE_WRAPPER_SCRIPT not in stripped:
            continue
        if "python3 scripts/" not in stripped and "Python scripts/" not in stripped:
            continue
        parts = stripped.split(None, 4)
        if len(parts) < 5:
            continue
        processes.append(
            {
                "pid": int(parts[0]),
                "etime": parts[1],
                "stat": parts[2],
                "command": parts[4],
            }
        )
    return processes


def detect_active_runtime_writer_processes() -> list[dict[str, Any]]:
    output = read_process_table()
    processes: list[dict[str, Any]] = []
    current_pid = os.getpid()
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in RUNTIME_WRITER_EXCLUDE_MARKERS):
            continue
        if not any(marker in stripped for marker in RUNTIME_WRITER_MARKERS):
            continue
        if "python" not in stripped.lower():
            continue
        parts = stripped.split(None, 4)
        if len(parts) < 5:
            continue
        pid = int(parts[0])
        if pid == current_pid:
            continue
        processes.append(
            {
                "pid": pid,
                "etime": parts[1],
                "stat": parts[2],
                "command": parts[4],
            }
        )
    return processes


def blocked_process_inspection_report(
    *,
    report_root: Path,
    execute: bool,
    direct_delete_no_archive: bool,
    required_confirm_token: str,
    failed_detector: str,
    error: Exception,
    lock_path: Path,
) -> dict[str, Any]:
    side_effects = runtime_archive_side_effects()
    side_effects["cleanup_local_runtime_files"] = False
    return {
        "result": "BLOCKED_PROCESS_INSPECTION_FAILED",
        "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
        "failed_stage": "process_inspection",
        "failed_detector": failed_detector,
        "error_type": type(error).__name__,
        "execute": bool(execute),
        "direct_delete_no_archive": bool(direct_delete_no_archive),
        "required_confirm_token": required_confirm_token,
        "docs_report_path": str(report_root / "keep5_cleanup_status.json"),
        "cleanup_authorized": False,
        "cleanup_executed": False,
        "cleanup_complete": False,
        "database_written": False,
        "deleted_rows": [],
        "deleted_total_rows": 0,
        "blockers": ["process_inspection_failed"],
        "single_flight_lock_policy": "keep5_cleanup_single_flight_v1",
        "single_flight_lock_acquired": True,
        "single_flight_lock_path": str(lock_path),
        "side_effects": side_effects,
    }


def blocked_runtime_writer_active_report(
    *,
    report_root: Path,
    execute: bool,
    active_runtime_writer_processes: list[dict[str, Any]],
    required_confirm_token: str,
    lock_path: Path,
) -> dict[str, Any]:
    side_effects = runtime_archive_side_effects()
    side_effects["cleanup_local_runtime_files"] = False
    return {
        "result": "BLOCKED_RUNTIME_WRITER_ACTIVE",
        "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
        "execute": bool(execute),
        "required_confirm_token": required_confirm_token,
        "docs_report_path": str(report_root / "keep5_cleanup_status.json"),
        "cleanup_authorized": False,
        "cleanup_executed": False,
        "cleanup_complete": False,
        "database_written": False,
        "deleted_rows": [],
        "deleted_total_rows": 0,
        "blockers": ["runtime_writer_active"],
        "active_runtime_writer_processes": active_runtime_writer_processes,
        "single_flight_lock_policy": "keep5_cleanup_single_flight_v1",
        "single_flight_lock_acquired": True,
        "single_flight_lock_path": str(lock_path),
        "side_effects": side_effects,
    }


def summarize_deleted_rows(deleted_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in deleted_rows:
        deleted_count = int(row.get("deleted_rows") or 0)
        if deleted_count <= 0:
            continue
        key = (str(row.get("layer") or ""), str(row.get("table") or ""))
        item = grouped.setdefault(
            key,
            {
                "layer": key[0],
                "table": key[1],
                "trade_dates": set(),
                "deleted_rows": 0,
            },
        )
        trade_date = str(row.get("trade_date") or "")
        if trade_date:
            item["trade_dates"].add(trade_date)
        item["deleted_rows"] += deleted_count
    summary: list[dict[str, Any]] = []
    for item in grouped.values():
        trade_dates = sorted(item.pop("trade_dates"))
        summary.append(
            {
                "layer": item["layer"],
                "table": item["table"],
                "trade_date_count": len(trade_dates),
                "deleted_rows": int(item["deleted_rows"]),
            }
        )
    return sorted(summary, key=lambda row: (str(row["layer"]), str(row["table"])))


def augment_cleanup_report(
    report: dict[str, Any],
    *,
    started_at: str,
    started_monotonic: float,
) -> dict[str, Any]:
    finished_at = datetime.now().astimezone().replace(microsecond=0).isoformat()
    summary = summarize_deleted_rows(list(report.get("deleted_rows") or []))
    row_cleanup_success = (
        str(report.get("result") or "").endswith("EXECUTE_PASS")
        and bool(report.get("cleanup_executed"))
        and bool(report.get("cleanup_complete", True))
    )
    local_cleanup = dict(report.get("local_file_cleanup") or {})
    local_cleanup_required = bool(report.get("execute")) and bool(report.get("direct_delete_no_archive"))
    local_cleanup_success = (
        not local_cleanup_required
        or (
            str(local_cleanup.get("result") or "") == "LOCAL_FILE_KEEP5_EXECUTE_PASS"
            and bool(local_cleanup.get("cleanup_executed"))
            and not list(local_cleanup.get("errors") or [])
            and not list(local_cleanup.get("blockers") or [])
        )
    )
    cleanup_success = row_cleanup_success and local_cleanup_success
    result = str(report.get("result") or "")
    if row_cleanup_success and local_cleanup_required and not local_cleanup_success:
        if str(local_cleanup.get("result") or "").startswith("BLOCKED_"):
            result = "BLOCKED_RUNTIME_HOT_KEEP5_LOCAL_FILE_CLEANUP"
        else:
            result = "RUNTIME_HOT_KEEP5_CLEANUP_EXECUTE_PARTIAL"
    retained_after = list(report.get("retained_trade_dates") or []) if cleanup_success else []
    return {
        **report,
        "result": result,
        "cleanup_success": cleanup_success,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": round((perf_counter() - started_monotonic) * 1000.0, 3),
        "deleted_table_summary": summary,
        "deleted_table_summary_count": len(summary),
        "current_hot_trade_dates_after": retained_after,
        "retained_trade_dates_after": retained_after,
    }


def sync_closeout_with_status(closeout_path: Path, report: dict[str, Any]) -> None:
    if not closeout_path.exists():
        return
    try:
        closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(closeout, dict):
        return
    for key in (
        "cleanup_success",
        "started_at",
        "finished_at",
        "duration_ms",
        "deleted_table_summary",
        "deleted_table_summary_count",
        "current_hot_trade_dates_after",
        "retained_trade_dates_after",
    ):
        closeout[key] = report.get(key)
    write_json(closeout_path, closeout)


def run_runtime_hot_cleanup_v2(
    *,
    dsn: str,
    report_root: Path,
    local_project_root: Path,
    archive_root: str | Path,
    execute: bool,
    confirm_token: str,
    trade_dates: Iterable[str] | None,
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None,
    table_deleter: Callable[[RuntimeHotCleanupSpec, str], int] | None,
    local_artifact_current_date: date | None,
    local_archive_manifest_path: str | Path | None,
    local_archive_batch_summary_path: str | Path | None,
    local_archive_allowlist_path: str | Path | None,
    local_archive_restore_proof_path: str | Path | None,
    local_archive_current_pointer_path: str | Path | None,
    local_archive_root: str | Path,
    active_local_artifact_paths: Iterable[str | Path],
    local_only: bool,
) -> dict[str, Any]:
    today = local_artifact_current_date or datetime.now(ASIA_SHANGHAI).date()
    current_trade_date = today.strftime("%Y%m%d")
    local_files = discover_local_artifact_files(project_root=local_project_root, current_date=today)
    injected_dates = sorted(set(str(item) for item in trade_dates)) if trade_dates is not None else None
    injected_retained = injected_dates[-6:] if injected_dates is not None else None
    effective_current_trade_date = current_trade_date if injected_retained is None else injected_retained[-1]
    plan = build_runtime_hot_cleanup_plan_v2(
        current_trade_date=effective_current_trade_date,
        local_files=local_files,
        dsn=dsn,
        retained_trade_dates=injected_retained,
        database_trade_dates=[] if local_only else injected_dates,
        inbox_delete_units=[] if local_only or (injected_dates is not None and table_counter is not None) else None,
        table_counter=table_counter,
        database_cleanup_enabled=not local_only,
    )
    plan_payload = plan.as_dict()
    cleanup_local_files = [
        entry for entry in local_files if entry["trade_date"] in set(plan.local_cleanup_trade_dates)
    ]
    legacy_archive_paths = (
        local_archive_manifest_path,
        local_archive_batch_summary_path,
        local_archive_allowlist_path,
        local_archive_restore_proof_path,
    )
    pointer_metadata: dict[str, Any] = {}
    pointer_blockers: list[str] = []
    if local_archive_current_pointer_path is not None and any(path is not None for path in legacy_archive_paths):
        pointer_blockers = ["local_archive_input_mode_conflict"]
    elif local_archive_current_pointer_path is not None:
        evidence_paths, pointer_metadata, pointer_blockers = load_local_archive_current_pointer(
            pointer_path=local_archive_current_pointer_path,
            for_cleanup_date=effective_current_trade_date,
            archive_root=local_archive_root,
        )
        if not pointer_blockers:
            local_archive_manifest_path = evidence_paths.get("manifest")
            local_archive_batch_summary_path = evidence_paths.get("summary")
            local_archive_allowlist_path = evidence_paths.get("allowlist")
            local_archive_restore_proof_path = evidence_paths.get("restore_proof")
    elif any(path is not None for path in legacy_archive_paths) and not all(
        path is not None for path in legacy_archive_paths
    ):
        pointer_blockers = ["legacy_local_archive_evidence_incomplete"]

    if pointer_blockers:
        local_entries: list[dict[str, Any]] = []
        local_blockers = list(pointer_blockers)
    elif (
        local_archive_manifest_path is None
        or local_archive_batch_summary_path is None
        or local_archive_allowlist_path is None
        or local_archive_restore_proof_path is None
    ):
        local_entries = []
        local_blockers = ["verified_local_archive_evidence_required"]
    else:
        local_entries, local_blockers = load_verified_local_archive_allowlist(
            manifest_path=local_archive_manifest_path,
            batch_summary_path=local_archive_batch_summary_path,
            allowlist_path=local_archive_allowlist_path,
            restore_proof_path=local_archive_restore_proof_path,
            discovered_cleanup_files=cleanup_local_files,
            retained_trade_dates=plan.retained_trade_dates,
            archive_root=local_archive_root,
        )
        if pointer_metadata and int(pointer_metadata["entry_count"]) != len(local_entries):
            local_blockers.append("local_archive_pointer_entry_count_mismatch")
        if pointer_metadata and sorted(pointer_metadata.get("retained_trade_dates") or []) != sorted(
            plan.retained_trade_dates
        ):
            local_blockers.append("local_archive_pointer_retained_dates_mismatch")
    plan_payload["local_archive_verified"] = not local_blockers
    plan_payload["local_allowlist"] = [dict(entry) for entry in local_entries]
    plan_payload["local_archive_pointer"] = dict(pointer_metadata)
    plan_payload["local_only"] = bool(local_only)
    plan_payload["blockers"] = sorted(set(list(plan_payload.get("blockers") or []) + local_blockers))
    write_json(report_root / "keep5_cleanup_plan.json", plan_payload)
    active_paths = {str(Path(item).resolve()) for item in active_local_artifact_paths}
    active_entries = [
        entry for entry in local_entries
        if str(Path(str(entry["source_path"])).resolve()) in active_paths
    ]
    if active_entries:
        local_blockers.append("local_archive_active_lineage_overlap")
        local_entries = [entry for entry in local_entries if entry not in active_entries]
    plan = replace(
        plan,
        local_allowlist=tuple(local_entries),
        local_archive_verified=not local_blockers,
        blockers=tuple(sorted(set((*plan.blockers, *local_blockers)))),
    )
    plan_payload = plan.as_dict()
    plan_payload["local_archive_pointer"] = dict(pointer_metadata)
    plan_payload["local_only"] = bool(local_only)
    write_json(report_root / "keep5_cleanup_plan.json", plan_payload)
    if not execute:
        if not local_blockers and plan.database_discovery_blocker:
            result = "RUNTIME_HOT_CLEANUP_V2_LOCAL_READY_DATABASE_BLOCKED"
        else:
            result = "RUNTIME_HOT_CLEANUP_V2_PLAN_PASS" if not plan.blockers else "RUNTIME_HOT_CLEANUP_V2_PLAN_BLOCKED"
        return {
            **plan_payload,
            "result": result,
            "mode": "plan_only",
            "execute": False,
            "archive_mode": LOCAL_ARCHIVE_REQUIRED_MODE,
            "local_archive_blockers": sorted(set(local_blockers)),
            "cleanup_executed": False,
            "timeout": False,
            "deleted_total_rows": 0,
            "deleted_active_lineage_count": 0,
            "database_written": False,
            "side_effects": {**runtime_archive_side_effects(), "cleanup_local_runtime_files": False},
        }
    if local_blockers:
        return {
            **plan_payload,
            "result": "RUNTIME_HOT_CLEANUP_V2_EXECUTE_BLOCKED",
            "mode": "execute",
            "execute": True,
            "archive_mode": LOCAL_ARCHIVE_REQUIRED_MODE,
            "local_archive_blockers": sorted(set(local_blockers)),
            "cleanup_executed": False,
            "cleanup_complete": False,
            "timeout": False,
            "deleted_total_rows": 0,
            "deleted_active_lineage_count": 0,
            "database_written": False,
            "side_effects": {**runtime_archive_side_effects(), "cleanup_local_runtime_files": False},
        }
    # DB and local are independent units. A DB timeout cannot suppress an already
    # archive-verified local reclaim; neither side is reported as globally rolled back.
    local_result = (
        execute_verified_local_allowlist(entries=local_entries, active_paths=active_local_artifact_paths)
        if not local_blockers
        else {
            "result": "BLOCKED_LOCAL_ARCHIVE_VERIFIED_RECLAIM",
            "cleanup_complete": False,
            "retry_attempts": 0,
            "removed_paths": [],
            "blockers": local_blockers,
        }
    )
    database_plan_blockers = [
        blocker for blocker in plan.blockers
        if blocker.startswith("database_date_discovery_failed:")
        or blocker.startswith("database_plan_count_failed:")
    ]
    if local_only:
        database_result = {
            "result": "DATABASE_CLEANUP_NOT_RUN_LOCAL_ONLY",
            "cleanup_complete": True,
            "retry_attempts": 0,
            "committed_units": [],
            "committed_unit_count": 0,
            "blockers": [],
        }
    elif database_plan_blockers:
        database_result = {
            "result": (
                "BLOCKED_DATABASE_DATE_DISCOVERY"
                if plan.database_discovery_blocker
                else "BLOCKED_DATABASE_PLAN_COUNT"
            ),
            "cleanup_complete": False,
            "retry_attempts": 0,
            "committed_units": [],
            "committed_unit_count": 0,
            "blockers": database_plan_blockers,
        }
    else:
        database_result = execute_runtime_hot_cleanup_database_v2(
            plan=plan,
            progress_journal_path=report_root / "keep5_cleanup_progress.jsonl",
            dsn=dsn,
            table_counter=table_counter,
            table_deleter=table_deleter,
        )
    complete = bool(local_result["cleanup_complete"]) and bool(database_result["cleanup_complete"])
    deleted_total_rows = sum(
        int(unit.get("deleted_rows") or 0) for unit in database_result.get("committed_units") or []
    )
    timeout = "TIMEOUT" in str(database_result.get("result") or "")
    return {
        **plan_payload,
        "result": "RUNTIME_HOT_CLEANUP_V2_EXECUTE_PASS" if complete else "RUNTIME_HOT_CLEANUP_V2_EXECUTE_PARTIAL",
        "mode": "execute",
        "execute": True,
        "archive_mode": LOCAL_ARCHIVE_REQUIRED_MODE,
        "cleanup_executed": True,
        "cleanup_complete": complete,
        "database_cleanup": database_result,
        "local_file_cleanup": local_result,
        "timeout": timeout,
        "deleted_total_rows": deleted_total_rows,
        "deleted_active_lineage_count": 0,
        "database_written": bool(database_result["committed_unit_count"]),
        "rollback_claimed": False,
        "side_effects": {
            **runtime_archive_side_effects(),
            "writes_database": bool(database_result["committed_unit_count"]),
            "cleanup_local_runtime_files": bool(local_result.get("removed_paths")),
        },
    }


def run_runtime_hot_keep5_cleanup_once(
    *,
    dsn: str = DEFAULT_DSN,
    archive_root: str | Path = DEFAULT_RUNTIME_ARCHIVE_ROOT,
    report_dir: str | Path = DEFAULT_REPORT_DIR,
    execute: bool = False,
    confirm_token: str = "",
    direct_delete_no_archive: bool = False,
    skip_row_count_plan: bool = False,
    trade_dates: Iterable[str] | None = None,
    table_counter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    table_deleter: Callable[[RuntimeHotCleanupSpec, str], int] | None = None,
    archive_process_detector: Callable[[], list[dict[str, Any]]] = detect_active_archive_processes,
    runtime_writer_process_detector: Callable[[], list[dict[str, Any]]] = detect_active_runtime_writer_processes,
    fk_closure_auditor: Callable[..., dict[str, Any]] | None = None,
    max_delete_units: int | None = None,
    local_artifact_project_root: str | Path | None = None,
    local_artifact_current_date: date | None = None,
    local_archive_manifest_path: str | Path | None = None,
    local_archive_batch_summary_path: str | Path | None = None,
    local_archive_allowlist_path: str | Path | None = None,
    local_archive_restore_proof_path: str | Path | None = None,
    local_archive_current_pointer_path: str | Path | None = None,
    local_archive_root: str | Path = "/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts",
    active_local_artifact_paths: Iterable[str | Path] = (),
    local_only: bool = False,
) -> dict[str, Any]:
    started_at = datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat()
    started_monotonic = perf_counter()
    report_root = Path(report_dir)
    local_project_root = Path(local_artifact_project_root) if local_artifact_project_root is not None else (
        PROJECT_ROOT if trade_dates is None else report_root.parent
    )
    plan_path = report_root / "keep5_cleanup_plan.json"
    closeout_path = report_root / "keep5_cleanup_closeout.json"
    if direct_delete_no_archive:
        report = {
            "schema": "RuntimeHotCleanupPlan.v2",
            "result": "BLOCKED_DIRECT_DELETE_NO_ARCHIVE_REJECTED",
            "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
            "execute": bool(execute),
            "archive_mode": LOCAL_ARCHIVE_REQUIRED_MODE,
            "cleanup_executed": False,
            "blockers": ["direct_delete_no_archive_rejected"],
            "blocked_by_layer": [{"scope": "n6_user_projection", "layer_role": "N6_user"}],
            "side_effects": {**runtime_archive_side_effects(), "cleanup_local_runtime_files": False},
        }
        report["docs_report_path"] = str(report_root / "keep5_cleanup_status.json")
        write_json(report["docs_report_path"], report)
        return report
    try:
        with keep5_cleanup_single_flight_lock(report_root) as lock_path:
            try:
                active_runtime_writers = runtime_writer_process_detector()
            except Exception as exc:
                report = blocked_process_inspection_report(
                    report_root=report_root,
                    execute=execute,
                    direct_delete_no_archive=False,
                    required_confirm_token=KEEP5_CONFIRM_TOKEN,
                    failed_detector="runtime_writer_process",
                    error=exc,
                    lock_path=lock_path,
                )
            else:
                if active_runtime_writers:
                    report = blocked_runtime_writer_active_report(
                        report_root=report_root,
                        execute=execute,
                        active_runtime_writer_processes=active_runtime_writers,
                        required_confirm_token=KEEP5_CONFIRM_TOKEN,
                        lock_path=lock_path,
                    )
                else:
                    report = run_runtime_hot_cleanup_v2(
                        dsn=dsn,
                        report_root=report_root,
                        local_project_root=local_project_root,
                        archive_root=archive_root,
                        execute=execute,
                        confirm_token=confirm_token,
                        trade_dates=trade_dates,
                        table_counter=table_counter,
                        table_deleter=table_deleter,
                        local_artifact_current_date=local_artifact_current_date,
                        local_archive_manifest_path=local_archive_manifest_path,
                        local_archive_batch_summary_path=local_archive_batch_summary_path,
                        local_archive_allowlist_path=local_archive_allowlist_path,
                        local_archive_restore_proof_path=local_archive_restore_proof_path,
                        local_archive_current_pointer_path=local_archive_current_pointer_path,
                        local_archive_root=local_archive_root,
                        active_local_artifact_paths=active_local_artifact_paths,
                        local_only=local_only,
                    )
    except CleanupAlreadyRunningError as exc:
        report = blocked_already_running_report(report_root=report_root, execute=execute, error=exc)
    report = {
        **report,
        "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
        "docs_report_path": str(report_root / "keep5_cleanup_status.json"),
        "started_at": started_at,
        "finished_at": datetime.now(ASIA_SHANGHAI).replace(microsecond=0).isoformat(),
        "duration_ms": round((perf_counter() - started_monotonic) * 1000.0, 3),
    }
    write_json(report["docs_report_path"], report)
    return report

    # Legacy keep-2 implementation is retained below for its separate historical
    # entrypoint; the keep-5 runner never reaches it.
    required_confirm_token = DIRECT_DELETE_NO_ARCHIVE_CONFIRM_TOKEN if direct_delete_no_archive else KEEP5_CONFIRM_TOKEN
    try:
        with keep5_cleanup_single_flight_lock(report_root) as lock_path:
            active_archive_processes: list[dict[str, Any]] = []
            active_runtime_writer_processes: list[dict[str, Any]] = []
            failed_detector = ""
            process_inspection_error: Exception | None = None
            if direct_delete_no_archive:
                try:
                    active_archive_processes = archive_process_detector()
                except Exception as exc:
                    failed_detector = "archive_process"
                    process_inspection_error = exc
                if process_inspection_error is None:
                    try:
                        active_runtime_writer_processes = runtime_writer_process_detector()
                    except Exception as exc:
                        failed_detector = "runtime_writer_process"
                        process_inspection_error = exc

            if process_inspection_error is not None:
                report = blocked_process_inspection_report(
                    report_root=report_root,
                    execute=execute,
                    direct_delete_no_archive=direct_delete_no_archive,
                    required_confirm_token=required_confirm_token,
                    failed_detector=failed_detector,
                    error=process_inspection_error,
                    lock_path=lock_path,
                )
                report["local_file_cleanup"] = blocked_local_file_cleanup(
                    project_root=local_project_root,
                    execute=execute,
                    blocker="process_inspection_failed",
                )
            elif active_runtime_writer_processes:
                report = blocked_runtime_writer_active_report(
                    report_root=report_root,
                    execute=execute,
                    active_runtime_writer_processes=active_runtime_writer_processes,
                    required_confirm_token=required_confirm_token,
                    lock_path=lock_path,
                )
                report["local_file_cleanup"] = blocked_local_file_cleanup(
                    project_root=local_project_root,
                    execute=execute,
                    blocker="runtime_writer_active",
                )
            else:
                plan = build_keep2_dirty_hot_cleanup_plan(
                    dsn=dsn,
                    trade_dates=trade_dates,
                    retention_trade_days=DEFAULT_RETENTION_TRADE_DAYS,
                    plan_path=plan_path,
                    archive_root=archive_root,
                    require_verified_archive=not direct_delete_no_archive,
                    direct_delete_no_archive=direct_delete_no_archive,
                    skip_row_count_plan=skip_row_count_plan,
                    table_counter=table_counter,
                    active_archive_processes=active_archive_processes,
                    fk_closure_auditor=fk_closure_auditor,
                )
                if execute:
                    report = execute_keep2_dirty_hot_cleanup(
                        plan_path=plan_path,
                        confirm_token=confirm_token,
                        expected_confirm_token=required_confirm_token,
                        dsn=dsn,
                        closeout_path=closeout_path,
                        current_trade_dates=trade_dates,
                        table_counter=table_counter,
                        table_deleter=table_deleter,
                        max_delete_units=max_delete_units,
                    )
                else:
                    report = plan
                report = {
                    **report,
                    "stage": "V3_RUNTIME_HOT_KEEP5_CLEANUP_ONCE",
                    "execute": bool(execute),
                    "required_confirm_token": required_confirm_token,
                    "docs_report_path": str(report_root / "keep5_cleanup_status.json"),
                    "single_flight_lock_policy": "keep5_cleanup_single_flight_v1",
                    "single_flight_lock_acquired": True,
                    "single_flight_lock_path": str(lock_path),
                }
                row_cleanup_execute_ready = (
                    str(report.get("result") or "") == "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS"
                    and bool(report.get("cleanup_executed"))
                    and bool(report.get("cleanup_complete"))
                )
                if not direct_delete_no_archive:
                    local_file_cleanup = blocked_local_file_cleanup(
                        project_root=local_project_root,
                        execute=execute,
                        blocker="direct_delete_no_archive_mode_required",
                    )
                elif active_archive_processes:
                    local_file_cleanup = blocked_local_file_cleanup(
                        project_root=local_project_root,
                        execute=execute,
                        blocker="archive_process_conflict",
                    )
                elif execute and not row_cleanup_execute_ready:
                    local_file_cleanup = blocked_local_file_cleanup(
                        project_root=local_project_root,
                        execute=execute,
                        blocker="hot_row_cleanup_not_complete",
                    )
                else:
                    local_file_cleanup = cleanup_local_runtime_artifacts(
                        project_root=local_project_root,
                        retained_trade_dates=list(report.get("retained_trade_dates") or []),
                        cleanup_trade_dates=list(report.get("cleanup_trade_dates") or []),
                        execute=execute,
                        direct_delete_no_archive=direct_delete_no_archive,
                        confirm_token=confirm_token,
                        current_date=local_artifact_current_date,
                    )
                report["local_file_cleanup"] = local_file_cleanup
                report["side_effects"] = {
                    **dict(report.get("side_effects") or {}),
                    "cleanup_local_runtime_files": bool(
                        dict(local_file_cleanup.get("side_effects") or {}).get("cleanup_local_runtime_files")
                    ),
                }
    except CleanupAlreadyRunningError as exc:
        report = blocked_already_running_report(report_root=report_root, execute=execute, error=exc)
        report["local_file_cleanup"] = blocked_local_file_cleanup(
            project_root=local_project_root,
            execute=execute,
            blocker="cleanup_already_running",
        )

    report = augment_cleanup_report(report, started_at=started_at, started_monotonic=started_monotonic)
    sync_closeout_with_status(closeout_path, report)
    write_json(report["docs_report_path"], report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--archive-root", default=DEFAULT_RUNTIME_ARCHIVE_ROOT)
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--local-archive-manifest-path")
    parser.add_argument("--local-archive-batch-summary-path")
    parser.add_argument("--local-archive-allowlist-path")
    parser.add_argument("--local-archive-restore-proof-path")
    parser.add_argument("--local-archive-current-pointer-path")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument(
        "--local-archive-root",
        default="/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts",
    )
    parser.add_argument(
        "--max-delete-units",
        type=int,
        default=None,
        help="Optional resumable execute limit. One unit is one simple table delete or one expanded batch delete.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_runtime_hot_keep5_cleanup_once(
        dsn=args.dsn,
        archive_root=args.archive_root,
        report_dir=args.report_dir,
        execute=args.execute,
        max_delete_units=args.max_delete_units,
        local_archive_manifest_path=args.local_archive_manifest_path,
        local_archive_batch_summary_path=args.local_archive_batch_summary_path,
        local_archive_allowlist_path=args.local_archive_allowlist_path,
        local_archive_restore_proof_path=args.local_archive_restore_proof_path,
        local_archive_current_pointer_path=args.local_archive_current_pointer_path,
        local_archive_root=args.local_archive_root,
        local_only=args.local_only,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=json_default))
    return 0 if str(report["result"]).endswith("_PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
