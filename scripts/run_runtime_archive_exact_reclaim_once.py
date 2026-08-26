#!/usr/bin/env python3
"""One-shot archive-verified exact local artifact reclaim."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo


POLICY_ID = "runtime_hot_cleanup_archive_gated_disk_governance_v1"
PHASE_MODE = "archive_verified_local_reclaim"
PROJECT_ROOT = Path("/Users/chuanfuchen/Documents/A股监控系统v3")
BATCH_DIR = Path(
    "/Volumes/MacRaid/stock_db_archive/v3_runtime_artifacts/"
    "batch=local_artifact_archive_20260821_n1_v2_manifest_supersession"
)
MANIFEST_PATH = BATCH_DIR / "manifest.jsonl"
SUMMARY_PATH = BATCH_DIR / "summary.json"
ALLOWLIST_PATH = BATCH_DIR / "exact_cleanup_allowlist.jsonl"
RESTORE_PROOF_PATH = BATCH_DIR / "restore_proof.json"
QUIESCE_PATH = BATCH_DIR / "inputs/phase_evidence.json"
QUIESCE_SIDECAR_PATH = BATCH_DIR / "inputs/phase_evidence.json.sha256"
EXPECTED_SHA256 = {
    MANIFEST_PATH: "127eefe4cb66b8bd9a6250bf700d3ad2e32b83bf590d800d50c3e45a5ed35769",
    SUMMARY_PATH: "32b92b5576bcb0849d11c1eca93aa01b0c9feda4482840156887004cb128ab2d",
    ALLOWLIST_PATH: "fc125ea314928e77949ac08ca6ed01c6da878c68179acaabb59a5d5a1ff5e7b6",
    RESTORE_PROOF_PATH: "e3af70ef12f24521be6e0c0476bd9ec2862ba9399171f3589d924b7deb08b634",
    QUIESCE_PATH: "ffc2efd8b15bf8c07c29df9e1573b0dd8d7de276eeb6eb7e33489e9212b9359b",
    QUIESCE_SIDECAR_PATH: "308fdcb250f8d230a393b01479e8aeaa3ad1061228144eb15eb368a53de363fd",
}
EXPECTED_BRANCH = "codex/new-demand-n2-n5-20260710"
EXPECTED_START_HEAD = "0c42c9ee2c9fd2049914cb69203cfea2fe437885"
EXPECTED_IMPLEMENTATION_PATHS = [
    "scripts/run_runtime_archive_exact_reclaim_once.py",
    "tests/test_runtime_archive_exact_reclaim.py",
]
EXPECTED_BATCH_ID = "local_artifact_archive_20260821_n1_v2_manifest_supersession"
EXPECTED_PAYLOAD_BATCH_ID = "local_artifact_archive_20260821_n1_v1"
EXPECTED_ENTRY_COUNT = 10227
EXPECTED_SOURCE_LOGICAL_BYTES = 160175105493
EXPECTED_SOURCE_ALLOCATED_BYTES = 160193548288
EXPECTED_ARCHIVE_LOGICAL_BYTES = 160175105493
EXPECTED_RETAINED_DATES = [
    "20260821", "20260820", "20260819", "20260818", "20260817", "20260814"
]
FAMILY_ORDER = {
    "n3p_trigger_proof_contract": 0,
    "intraday_live_current": 1,
    "post_close_fastlane": 2,
}
TARGET_FREE_BYTES = 268435456000
LABEL = "com.ashare-v3.runtime-hot-cleanup-keep5-daily"
EVIDENCE_PARENT = PROJECT_ROOT / "docs/runtime_archive" / POLICY_ID
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRADE_DATE_RE = re.compile(r"^[0-9]{8}$")


class ReclaimBlocked(RuntimeError):
    pass


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReclaimBlocked(f"invalid_jsonl:{path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ReclaimBlocked(f"non_object_jsonl:{path}:{line_number}")
            rows.append(value)
    return rows


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReclaimBlocked(f"non_object_json:{path}")
    return value


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, capture_output=True)


def git_freeze(expected_head: str) -> dict[str, Any]:
    if not GIT_COMMIT_RE.fullmatch(expected_head):
        raise ReclaimBlocked("expected_head_invalid")
    branch = run_checked(["git", "branch", "--show-current"])
    head = run_checked(["git", "rev-parse", "HEAD"])
    parent = run_checked(["git", "rev-parse", f"{expected_head}^"])
    paths = run_checked(["git", "diff", "--name-only", EXPECTED_START_HEAD, expected_head])
    worktree = run_checked(["git", "diff", "--quiet"])
    index = run_checked(["git", "diff", "--cached", "--quiet"])
    if branch.returncode or branch.stdout.strip() != EXPECTED_BRANCH:
        raise ReclaimBlocked("git_branch_drift")
    if head.returncode or head.stdout.strip() != expected_head:
        raise ReclaimBlocked("git_head_drift")
    if parent.returncode or parent.stdout.strip() != EXPECTED_START_HEAD:
        raise ReclaimBlocked("implementation_commit_parent_drift")
    if paths.returncode or paths.stdout.splitlines() != EXPECTED_IMPLEMENTATION_PATHS:
        raise ReclaimBlocked("implementation_commit_scope_drift")
    if worktree.returncode != 0 or index.returncode != 0:
        raise ReclaimBlocked("tracked_worktree_or_index_dirty")
    return {
        "branch": branch.stdout.strip(),
        "head": head.stdout.strip(),
        "expected_start_head": EXPECTED_START_HEAD,
        "tracked_worktree_and_index_clean": True,
    }


def calendar_freeze(dsn: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts/plan_runtime_disk_governance_retained_dates.py"),
        "--dsn", dsn,
        "--current-date", "20260821",
    ]
    completed = run_checked(command)
    if completed.returncode != 0:
        raise ReclaimBlocked("calendar_helper_failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReclaimBlocked("calendar_helper_invalid_json") from exc
    if (
        payload.get("result") != "RUNTIME_DISK_GOVERNANCE_RETAINED_DATES_READ_ONLY_PASS"
        or payload.get("retained_trade_dates") != EXPECTED_RETAINED_DATES
        or payload.get("database_read_only") is not True
        or payload.get("database_writes") != 0
    ):
        raise ReclaimBlocked("calendar_authority_drift")
    return payload


def cleanup_absence() -> dict[str, Any]:
    launchctl = run_checked(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"])
    if launchctl.returncode == 0:
        raise ReclaimBlocked("cleanup_job_loaded")
    processes = run_checked(["ps", "-axo", "pid=,ppid=,command="])
    if processes.returncode != 0:
        raise ReclaimBlocked("process_snapshot_failed")
    markers = (
        "scripts/run_runtime_hot_keep5_cleanup_once.py",
        "scripts/run_v3_runtime_archive_keep5_daily_once.py",
    )
    conflicts = [line.strip() for line in processes.stdout.splitlines() if any(marker in line for marker in markers)]
    if conflicts:
        raise ReclaimBlocked("cleanup_pid_or_child_present")
    return {
        "label": LABEL,
        "launchctl_print_exit_code": launchctl.returncode,
        "job_absent": True,
        "pid_absent": True,
        "child_absent": True,
        "process_snapshot_sha256": hashlib.sha256(processes.stdout.encode()).hexdigest(),
    }


def exact_open_handles(source_paths: set[str]) -> list[str]:
    process = subprocess.Popen(
        ["lsof", "-Fn"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
    )
    assert process.stdout is not None
    matches: list[str] = []
    for line in process.stdout:
        if line.startswith("n") and line[1:] in source_paths:
            matches.append(line[1:])
    return_code = process.wait()
    if return_code not in (0, 1):
        raise ReclaimBlocked("open_handle_inspection_failed")
    return sorted(set(matches))


def file_identity(path: Path, *, expected: dict[str, Any], archive: bool) -> dict[str, Any]:
    try:
        before_path = path.lstat()
    except OSError as exc:
        raise ReclaimBlocked(f"file_lstat_failed:{path}") from exc
    if stat.S_ISLNK(before_path.st_mode) or not stat.S_ISREG(before_path.st_mode):
        raise ReclaimBlocked(f"file_not_regular_or_symlink:{path}")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise ReclaimBlocked(f"file_open_failed:{path}") from exc
    digest = hashlib.sha256()
    try:
        before_fd = os.fstat(descriptor)
        with os.fdopen(descriptor, "rb", buffering=0, closefd=False) as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
        after_fd = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        after_path = path.lstat()
    except OSError as exc:
        raise ReclaimBlocked(f"file_post_hash_lstat_failed:{path}") from exc
    stable_fields = ("st_dev", "st_ino", "st_mode", "st_mtime_ns", "st_size", "st_blocks")
    if any(
        getattr(before_path, field) != getattr(before_fd, field)
        or getattr(before_fd, field) != getattr(after_fd, field)
        or getattr(after_fd, field) != getattr(after_path, field)
        for field in stable_fields
    ):
        raise ReclaimBlocked(f"file_changed_while_hashing:{path}")
    identity = {
        "device": after_fd.st_dev,
        "inode": after_fd.st_ino,
        "mode": f"{stat.S_IMODE(after_fd.st_mode):04o}",
        "mtime_ns": after_fd.st_mtime_ns,
        "logical_bytes": after_fd.st_size,
        "allocated_bytes": after_fd.st_blocks * 512,
        "sha256": digest.hexdigest(),
    }
    if archive:
        if identity["sha256"] != expected["archive_sha256"]:
            raise ReclaimBlocked(f"archive_hash_drift:{path}")
        if identity["logical_bytes"] != expected["source_logical_bytes"]:
            raise ReclaimBlocked(f"archive_size_drift:{path}")
    else:
        checks = {
            "device": expected["source_device"],
            "inode": expected["source_inode"],
            "mode": expected["source_mode"],
            "mtime_ns": expected["source_mtime_ns"],
            "logical_bytes": expected["source_logical_bytes"],
            "allocated_bytes": expected["source_allocated_bytes"],
            "sha256": expected["source_sha256"],
        }
        if identity != checks:
            raise ReclaimBlocked(f"source_identity_drift:{path}")
    return identity


def validate_frozen_evidence() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    for path, expected_sha in EXPECTED_SHA256.items():
        if sha256_path(path) != expected_sha:
            raise ReclaimBlocked(f"frozen_evidence_sha_drift:{path}")
    sidecar = QUIESCE_SIDECAR_PATH.read_text(encoding="utf-8").strip()
    if sidecar != f"{EXPECTED_SHA256[QUIESCE_PATH]}  phase_evidence.json":
        raise ReclaimBlocked("quiesce_sidecar_cross_bind_drift")

    summary = read_json(SUMMARY_PATH)
    restore = read_json(RESTORE_PROOF_PATH)
    quiesce = read_json(QUIESCE_PATH)
    summary_checks = {
        "batch_id": EXPECTED_BATCH_ID,
        "archive_payload_batch_id": EXPECTED_PAYLOAD_BATCH_ID,
        "manifest_sha256": EXPECTED_SHA256[MANIFEST_PATH],
        "allowlist_sha256": EXPECTED_SHA256[ALLOWLIST_PATH],
        "restore_proof_sha256": EXPECTED_SHA256[RESTORE_PROOF_PATH],
        "quiesce_evidence_sha256": EXPECTED_SHA256[QUIESCE_PATH],
        "entry_count": EXPECTED_ENTRY_COUNT,
        "source_logical_bytes_total": EXPECTED_SOURCE_LOGICAL_BYTES,
        "source_allocated_bytes_total": EXPECTED_SOURCE_ALLOCATED_BYTES,
        "archive_logical_bytes_total": EXPECTED_ARCHIVE_LOGICAL_BYTES,
        "source_archive_hash_equality_count": EXPECTED_ENTRY_COUNT,
        "retained_trade_dates": EXPECTED_RETAINED_DATES,
        "retained_date_overlap": 0,
        "active_current_lineage_overlap": 0,
        "restore_proof_result": "RESTORE_PROOF_PASS",
        "ready_for_runtime_exact_reclaim": True,
    }
    if any(summary.get(key) != value for key, value in summary_checks.items()):
        raise ReclaimBlocked("summary_cross_bind_drift")
    if restore.get("batch_id") != EXPECTED_BATCH_ID or restore.get("result") != "RESTORE_PROOF_PASS":
        raise ReclaimBlocked("restore_proof_drift")
    if set(restore.get("families", {})) != set(FAMILY_ORDER) or any(
        value.get("status") != "RESTORE_PROOF_PASS" for value in restore["families"].values()
    ):
        raise ReclaimBlocked("restore_family_proof_incomplete")
    if (
        quiesce.get("result") != "CLEANUP_SCHEDULER_QUIESCE_PASS"
        or quiesce.get("phase_mode") != "cleanup_scheduler_quiesce"
        or quiesce.get("operation_counts", {}).get("bootout_count") != 1
        or not quiesce.get("phase_postcondition", {}).get("cleanup_job_and_pid_absent_after_wait")
    ):
        raise ReclaimBlocked("quiesce_evidence_drift")

    manifest = load_jsonl(MANIFEST_PATH)
    allowlist = load_jsonl(ALLOWLIST_PATH)
    if len(manifest) != EXPECTED_ENTRY_COUNT or len(allowlist) != EXPECTED_ENTRY_COUNT:
        raise ReclaimBlocked("entry_count_drift")
    manifest_by_source = {row.get("source_path"): row for row in manifest}
    if None in manifest_by_source or len(manifest_by_source) != EXPECTED_ENTRY_COUNT:
        raise ReclaimBlocked("manifest_source_path_not_unique")
    required = {
        "source_path", "trade_date", "artifact_family", "source_device", "source_inode",
        "source_mode", "source_mtime_ns", "source_logical_bytes", "source_allocated_bytes",
        "source_sha256", "archive_path", "archive_sha256", "reference_classification",
        "restore_proof_id",
    }
    allocated = 0
    logical = 0
    seen: set[str] = set()
    for row in allowlist:
        if not required.issubset(row):
            raise ReclaimBlocked("allowlist_required_field_missing")
        source = str(row["source_path"])
        archive = str(row["archive_path"])
        if source in seen or not source.startswith(f"{PROJECT_ROOT}/"):
            raise ReclaimBlocked("allowlist_source_scope_invalid")
        if not archive.startswith(f"{BATCH_DIR.parent}/batch={EXPECTED_PAYLOAD_BATCH_ID}/files/"):
            raise ReclaimBlocked("allowlist_archive_scope_invalid")
        if row["artifact_family"] not in FAMILY_ORDER or not TRADE_DATE_RE.fullmatch(str(row["trade_date"])):
            raise ReclaimBlocked("allowlist_family_or_date_invalid")
        if row["trade_date"] in EXPECTED_RETAINED_DATES:
            raise ReclaimBlocked("retained_date_overlap")
        if row.get("retained_date_overlap") != 0 or row.get("active_current_lineage_overlap") != 0:
            raise ReclaimBlocked("active_or_retained_overlap")
        if row.get("archive_fully_verified") is not True or row.get("source_identity_stable") is not True:
            raise ReclaimBlocked("allowlist_not_fully_verified")
        if row.get("manifest_sha256") != EXPECTED_SHA256[MANIFEST_PATH]:
            raise ReclaimBlocked("allowlist_manifest_cross_bind_drift")
        manifest_row = manifest_by_source.get(source)
        if manifest_row is None or any(manifest_row.get(field) != row.get(field) for field in required):
            raise ReclaimBlocked("manifest_allowlist_cross_bind_drift")
        if row["source_sha256"] != row["archive_sha256"] or not SHA256_RE.fullmatch(row["source_sha256"]):
            raise ReclaimBlocked("source_archive_hash_cross_bind_drift")
        seen.add(source)
        allocated += int(row["source_allocated_bytes"])
        logical += int(row["source_logical_bytes"])
    if allocated != EXPECTED_SOURCE_ALLOCATED_BYTES or logical != EXPECTED_SOURCE_LOGICAL_BYTES:
        raise ReclaimBlocked("allowlist_totals_drift")
    return allowlist, summary


def global_file_preflight(rows: Iterable[dict[str, Any]]) -> None:
    for row in rows:
        source = Path(row["source_path"])
        archive = Path(row["archive_path"])
        source_identity = file_identity(source, expected=row, archive=False)
        archive_identity = file_identity(archive, expected=row, archive=True)
        if source_identity["sha256"] != archive_identity["sha256"]:
            raise ReclaimBlocked(f"source_archive_hash_mismatch:{source}")


def data_df() -> dict[str, Any]:
    completed = run_checked(["/bin/df", "-k", "/System/Volumes/Data"])
    if completed.returncode != 0:
        raise ReclaimBlocked("data_volume_df_failed")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 2:
        raise ReclaimBlocked("data_volume_df_unexpected_output")
    fields = lines[1].split()
    if len(fields) < 6:
        raise ReclaimBlocked("data_volume_df_unexpected_fields")
    return {"available_bytes": int(fields[3]) * 1024, "raw": completed.stdout.strip()}


def append_durable(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def progress_summary(path: Path) -> dict[str, int]:
    unlink_count = 0
    allocated = 0
    if path.exists():
        for row in load_jsonl(path):
            if row.get("event") == "unlink_committed":
                unlink_count += 1
                allocated += int(row.get("manifest_allocated_bytes", 0))
    return {"unlink_count": unlink_count, "manifest_allocated_bytes_unlinked": allocated}


def ordered_batches(rows: list[dict[str, Any]]) -> list[tuple[str, str, list[dict[str, Any]]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["artifact_family"], row["trade_date"])].append(row)
    keys = sorted(grouped, key=lambda item: (FAMILY_ORDER[item[0]], item[1]))
    return [(family, trade_date, sorted(grouped[(family, trade_date)], key=lambda row: row["source_path"])) for family, trade_date in keys]


def execute_batches(
    rows: list[dict[str, Any]],
    *,
    progress_path: Path,
    df_reader: Callable[[], dict[str, Any]] = data_df,
) -> dict[str, Any]:
    before = df_reader()
    unlinked = 0
    allocated = 0
    per_batch: list[dict[str, Any]] = []
    for family, trade_date, batch_rows in ordered_batches(rows):
        batch_allocated = 0
        for row in batch_rows:
            source = Path(row["source_path"])
            source_identity = file_identity(source, expected=row, archive=False)
            archive_identity = file_identity(Path(row["archive_path"]), expected=row, archive=True)
            if source_identity["sha256"] != archive_identity["sha256"]:
                raise ReclaimBlocked(f"pre_unlink_hash_mismatch:{source}")
            os.unlink(source)
            unlinked += 1
            allocated += int(row["source_allocated_bytes"])
            batch_allocated += int(row["source_allocated_bytes"])
            append_durable(progress_path, {
                "event": "unlink_committed",
                "sequence": unlinked,
                "artifact_family": family,
                "trade_date": trade_date,
                "source_path": str(source),
                "archive_path": row["archive_path"],
                "source_sha256": row["source_sha256"],
                "manifest_allocated_bytes": row["source_allocated_bytes"],
            })
        after_batch = df_reader()
        batch_record = {
            "event": "date_batch_committed",
            "artifact_family": family,
            "trade_date": trade_date,
            "unlink_count": len(batch_rows),
            "manifest_allocated_bytes": batch_allocated,
            "data_volume_available_bytes": after_batch["available_bytes"],
            "data_volume_df": after_batch["raw"],
        }
        append_durable(progress_path, batch_record)
        per_batch.append(batch_record)
        if after_batch["available_bytes"] >= TARGET_FREE_BYTES:
            break
    after = df_reader()
    remaining = len(rows) - unlinked
    target_reached = after["available_bytes"] >= TARGET_FREE_BYTES
    return {
        "result": "ARCHIVE_VERIFIED_LOCAL_RECLAIM_PASS" if target_reached else "BLOCKED_FOR_SEPARATE_SNAPSHOT_FALLBACK",
        "df_before": before,
        "df_after": after,
        "df_gain_bytes": after["available_bytes"] - before["available_bytes"],
        "target_free_bytes": TARGET_FREE_BYTES,
        "target_reached": target_reached,
        "unlink_count": unlinked,
        "manifest_allocated_bytes_unlinked": allocated,
        "remaining_count": remaining,
        "batches": per_batch,
    }


def write_final_evidence(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with path.open("rb") as handle:
        os.fsync(handle.fileno())
    digest = sha256_path(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    with sidecar.open("rb") as handle:
        os.fsync(handle.fileno())
    return {str(path): digest, str(sidecar): sha256_path(sidecar)}


def seal_evidence(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_file():
            path.chmod(0o444)
    directory.chmod(0o555)


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    timestamp = datetime.now(ASIA_SHANGHAI).strftime("%Y%m%dT%H%M%S%z")
    evidence_dir = EVIDENCE_PARENT / f"{timestamp}_{PHASE_MODE}"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    progress_path = evidence_dir / "durable_progress.jsonl"
    progress_path.touch(exist_ok=False)
    evidence: dict[str, Any] = {
        "schema": "RuntimeHotCleanupArchiveVerifiedLocalReclaimEvidence.v1",
        "policy_id": POLICY_ID,
        "phase_mode": PHASE_MODE,
        "layer_role": "runtime_control",
        "execution_mode": "FULL_MODE",
        "dag": ["PLAN", "VALIDATE", "MODIFY", "VERIFY", "FINALIZE"],
        "kernel_decision": "ACCEPT",
        "runtime_gate_decision": "ACCEPT",
        "implementation_commit": args.expected_head,
        "source_thread_id": args.source_thread_id,
        "execute": args.execute,
        "user_confirmed": args.user_confirmed,
        "started_at": timestamp,
        "result": "BLOCKED_PREFLIGHT",
        "unlink_count": 0,
        "operation_counts": {
            "bootout_count": 0, "bootstrap_count": 0, "kickstart_count": 0,
            "database_write_count": 0, "database_delete_count": 0,
            "snapshot_delete_count": 0, "business_launch_agent_operation_attempts": 0,
            "local_artifact_delete_count": 0, "retry_count": 0,
        },
    }
    exit_code = 2
    try:
        if not args.execute or not args.user_confirmed:
            raise ReclaimBlocked("execute_and_user_confirmed_required")
        evidence["git_freeze"] = git_freeze(args.expected_head)
        rows, summary = validate_frozen_evidence()
        evidence["frozen_archive_summary"] = summary
        evidence["calendar_freeze"] = calendar_freeze(args.dsn)
        evidence["cleanup_absence"] = cleanup_absence()
        global_file_preflight(rows)
        open_handles = exact_open_handles({str(row["source_path"]) for row in rows})
        evidence["candidate_open_handle_count"] = len(open_handles)
        if open_handles:
            raise ReclaimBlocked("candidate_open_handles_present")
        evidence["preflight"] = {
            "result": "PASS", "entry_count": len(rows),
            "archive_regular_and_hash_verified_count": len(rows),
            "source_regular_identity_and_hash_verified_count": len(rows),
            "retained_overlap": 0, "active_current_lineage_overlap": 0,
            "candidate_open_handle_count": 0,
        }
        outcome = execute_batches(rows, progress_path=progress_path)
        evidence.update(outcome)
        evidence["operation_counts"]["local_artifact_delete_count"] = outcome["unlink_count"]
        evidence["restore_entrypoint"] = {
            "manifest_path": str(MANIFEST_PATH),
            "restore_proof_path": str(RESTORE_PROOF_PATH),
            "archive_payload_batch_id": EXPECTED_PAYLOAD_BATCH_ID,
            "instruction": "restore only from each journaled archive_path after a separate authorized restore gate",
        }
        evidence["mutation_audit"] = {
            "exact_source_unlink_count": outcome["unlink_count"],
            "evidence_file_write_scope": str(evidence_dir),
            "other_filesystem_mutation_count": 0,
            "database_mutation_count": 0,
            "launchagent_mutation_count": 0,
            "service_mutation_count": 0,
            "snapshot_mutation_count": 0,
            "n1_n6_business_mutation_count": 0,
        }
        evidence["READY_FOR_SEPARATE_CLEANUP_FIX"] = True
        exit_code = 0 if outcome["target_reached"] else 3
    except Exception as exc:
        partial = progress_summary(progress_path)
        evidence.update(partial)
        evidence["operation_counts"]["local_artifact_delete_count"] = partial["unlink_count"]
        evidence["result"] = "BLOCKED_EXECUTION_ERROR" if partial["unlink_count"] else "BLOCKED_PREFLIGHT"
        evidence["blocker"] = str(exc) if isinstance(exc, ReclaimBlocked) else f"unexpected_{type(exc).__name__}"
        evidence["automatic_retry"] = False
        evidence["READY_FOR_SEPARATE_CLEANUP_FIX"] = False
    finally:
        evidence["finished_at"] = datetime.now(ASIA_SHANGHAI).strftime("%Y%m%dT%H%M%S%z")
        phase_path = evidence_dir / "phase_evidence.json"
        hashes = write_final_evidence(phase_path, evidence)
        if progress_path.stat().st_size:
            hashes[str(progress_path)] = sha256_path(progress_path)
        evidence["evidence_hashes_before_seal"] = hashes
        seal_evidence(evidence_dir)
    return exit_code, {"evidence_dir": str(evidence_dir), **evidence}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--source-thread-id", required=True)
    parser.add_argument("--dsn", default="postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser


def main() -> int:
    code, payload = run(build_parser().parse_args())
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
