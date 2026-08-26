#!/usr/bin/env python3
"""Build and publish one archive-verified local-artifact batch for next cleanup.

This N1 entrypoint is archive-only.  It never removes source artifacts, writes
PostgreSQL, or starts/stops services.  Its only mutable outputs (with explicit
confirmation) are a new immutable batch under the MacRaid archive root and the
atomic current-batch pointer consumed by the later runtime-control cleanup gate.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

import psycopg

try:
    from scripts.run_local_artifact_archive_manifest_once import (
        ARCHIVE_BASE,
        ArchiveBlocked,
        execute_archive,
    )
    from scripts.run_runtime_hot_keep5_cleanup_once import detect_active_runtime_writer_processes
except ModuleNotFoundError:  # Direct ``python scripts/...`` invocation.
    from run_local_artifact_archive_manifest_once import ARCHIVE_BASE, ArchiveBlocked, execute_archive
    from run_runtime_hot_keep5_cleanup_once import detect_active_runtime_writer_processes


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_POINTER_NAME = "current_verified_batch.json"
POINTER_SCHEMA_VERSION = "LocalArtifactArchiveCurrentPointer.v1"
TRADE_DATE_RE = re.compile(r"^[0-9]{8}$")


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(path: Path) -> os.stat_result:
    value = path.lstat()
    if not stat.S_ISREG(value.st_mode) or stat.S_ISLNK(value.st_mode):
        raise ArchiveBlocked(f"not_regular_file:{path}")
    return value


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_archive_base(archive_base: Path) -> Path:
    value = archive_base.lstat()
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        raise ArchiveBlocked("archive_base_missing_or_unsafe")
    return archive_base.resolve(strict=True)


def _safe_source_root(source_root: Path) -> Path:
    value = source_root.lstat()
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        raise ArchiveBlocked("source_root_missing_or_unsafe")
    return source_root.resolve(strict=True)


def next_cleanup_date(now: datetime | None = None) -> str:
    """Return the calendar date that the following 01:00 cleanup will use."""

    local_now = now.astimezone(ASIA_SHANGHAI) if now is not None else datetime.now(ASIA_SHANGHAI)
    return (local_now.date() + timedelta(days=1)).strftime("%Y%m%d")


def read_retained_trade_dates(
    *,
    dsn: str,
    for_cleanup_date: str,
    connection_factory: Callable[..., Any] = psycopg.connect,
) -> list[str]:
    """Read next cleanup date plus its five completed predecessors, read-only."""

    if not TRADE_DATE_RE.fullmatch(for_cleanup_date):
        raise ArchiveBlocked("invalid_for_cleanup_date")
    connection = connection_factory(
        dsn,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT trade_date::text
                FROM common_trade_calendar
                WHERE is_open IS TRUE
                  AND trade_date < %s
                ORDER BY trade_date DESC
                LIMIT 5
                """,
                (for_cleanup_date,),
            )
            previous = [str(row[0]) for row in cursor.fetchall()]
    finally:
        connection.close()
    if len(previous) != 5 or any(not TRADE_DATE_RE.fullmatch(value) for value in previous):
        raise ArchiveBlocked("common_trade_calendar_previous_completed_dates_must_equal_5")
    if len(set(previous)) != 5 or any(value >= for_cleanup_date for value in previous):
        raise ArchiveBlocked("common_trade_calendar_returned_invalid_predecessors")
    return [for_cleanup_date, *sorted(previous)]


def _evidence_entry(path: Path, batch_root: Path) -> dict[str, str]:
    resolved = path.resolve(strict=True)
    if not _inside(resolved, batch_root):
        raise ArchiveBlocked(f"evidence_path_escape:{path}")
    _regular_file(resolved)
    return {"path": str(resolved), "sha256": _sha256_path(resolved)}


def build_current_pointer(*, summary: dict[str, Any], archive_base: Path, for_cleanup_date: str) -> dict[str, Any]:
    """Validate one completed batch and create its cleanup-consumable pointer."""

    archive_root = _safe_archive_base(archive_base)
    batch_id = summary.get("batch_id")
    if not isinstance(batch_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", batch_id):
        raise ArchiveBlocked("invalid_batch_id")
    batch_root = (archive_root / f"batch={batch_id}").resolve(strict=True)
    if not _inside(batch_root, archive_root) or batch_root.name != f"batch={batch_id}":
        raise ArchiveBlocked("batch_root_escape")
    if summary.get("result") != "ARCHIVED_VERIFIED" or summary.get("restore_proof_result") != "RESTORE_PROOF_PASS":
        raise ArchiveBlocked("archive_summary_not_verified")
    retained_dates = summary.get("retained_trade_dates")
    entry_count = summary.get("entry_count")
    if retained_dates is None or not isinstance(retained_dates, list) or entry_count is None or not isinstance(entry_count, int):
        raise ArchiveBlocked("archive_summary_missing_pointer_fields")
    if retained_dates != read_retained_trade_dates_from_summary(for_cleanup_date, retained_dates):
        raise ArchiveBlocked("archive_summary_retained_dates_mismatch")
    evidence = {
        "manifest": _evidence_entry(Path(str(summary.get("manifest_path", ""))), batch_root),
        "summary": _evidence_entry(Path(str(summary.get("summary_path", ""))), batch_root),
        "allowlist": _evidence_entry(Path(str(summary.get("allowlist_path", ""))), batch_root),
        "restore_proof": _evidence_entry(Path(str(summary.get("restore_proof_path", ""))), batch_root),
    }
    for name, expected in (
        ("manifest", summary.get("manifest_sha256")),
        ("summary", summary.get("summary_sha256")),
        ("allowlist", summary.get("allowlist_sha256")),
        ("restore_proof", summary.get("restore_proof_sha256")),
    ):
        if not isinstance(expected, str) or evidence[name]["sha256"] != expected:
            raise ArchiveBlocked(f"{name}_sha256_mismatch")
    proof = json.loads(Path(evidence["restore_proof"]["path"]).read_text(encoding="utf-8"))
    if proof.get("result") != "RESTORE_PROOF_PASS" or proof.get("batch_id") != batch_id:
        raise ArchiveBlocked("restore_proof_not_verified")
    return {
        "schema_version": POINTER_SCHEMA_VERSION,
        "for_cleanup_date": for_cleanup_date,
        "batch_id": batch_id,
        "retained_trade_dates": retained_dates,
        "entry_count": entry_count,
        "result": "ARCHIVED_VERIFIED",
        "restore_proof_result": "RESTORE_PROOF_PASS",
        **evidence,
    }


def read_retained_trade_dates_from_summary(for_cleanup_date: str, retained_dates: list[Any]) -> list[str]:
    """Validate canonical date ordering without consulting a second DB snapshot."""

    if len(retained_dates) != 6 or retained_dates[0] != for_cleanup_date:
        raise ArchiveBlocked("archive_summary_retained_dates_mismatch")
    if any(not isinstance(value, str) or not TRADE_DATE_RE.fullmatch(value) for value in retained_dates):
        raise ArchiveBlocked("archive_summary_retained_dates_mismatch")
    if len(set(retained_dates)) != 6 or any(value >= for_cleanup_date for value in retained_dates[1:]):
        raise ArchiveBlocked("archive_summary_retained_dates_mismatch")
    return retained_dates


def publish_current_pointer(*, pointer: dict[str, Any], archive_base: Path) -> Path:
    """Atomically replace only the regular current pointer after all validation."""

    archive_root = _safe_archive_base(archive_base)
    target = archive_root / CURRENT_POINTER_NAME
    if target.exists() or target.is_symlink():
        _regular_file(target)
    temporary = archive_root / f".{CURRENT_POINTER_NAME}.tmp-{os.getpid()}"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(_canonical_json(pointer))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444)
        os.replace(temporary, target)
        directory_fd = os.open(archive_root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    _regular_file(target)
    return target


def run_local_artifact_archive_daily_once(
    *,
    dsn: str = DEFAULT_DSN,
    source_root: Path = PROJECT_ROOT,
    archive_base: Path = ARCHIVE_BASE,
    for_cleanup_date: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    connection_factory: Callable[..., Any] = psycopg.connect,
    writer_detector: Callable[[], list[dict[str, Any]]] = detect_active_runtime_writer_processes,
    archive_executor: Callable[..., dict[str, Any]] = execute_archive,
) -> dict[str, Any]:
    cleanup_date = for_cleanup_date or next_cleanup_date()
    payload: dict[str, Any] = {
        "stage": "N1_LOCAL_ARTIFACT_ARCHIVE_DAILY_ONCE",
        "layer_role": "N1_ingestion",
        "for_cleanup_date": cleanup_date,
        "execute": bool(execute),
        "user_confirmed": bool(user_confirmed),
        "source_mutation_count": 0,
        "database_writes": 0,
        "service_operations": 0,
        "source_delete_or_move_count": 0,
        "retry_count": 0,
        "pointer_published": False,
        "blockers": [],
    }
    if not execute or not user_confirmed:
        payload["result"] = "BLOCKED_EXECUTE_CONFIRMATION_REQUIRED"
        payload["blockers"] = ["execute_and_user_confirmed_required"]
        return payload
    try:
        writers = writer_detector()
        if writers:
            raise ArchiveBlocked("runtime_writer_active")
        retained_dates = read_retained_trade_dates(
            dsn=dsn,
            for_cleanup_date=cleanup_date,
            connection_factory=connection_factory,
        )
        archive_root = _safe_archive_base(Path(archive_base))
        source = _safe_source_root(Path(source_root))
        batch_id = f"local-artifact-archive-{cleanup_date}"
        # The manifest v1 field is retained for compatibility; this runner's
        # actual precondition is the immediately preceding writer-absence check.
        writer_absence_sha256 = hashlib.sha256(
            f"daily_writer_absence_v1:{cleanup_date}".encode("utf-8")
        ).hexdigest()
        summary = archive_executor(
            source_root=source,
            archive_base=archive_root,
            batch_id=batch_id,
            retained_dates=retained_dates,
            current_date=cleanup_date,
            quiesce_evidence_sha256=writer_absence_sha256,
        )
        pointer = build_current_pointer(
            summary=summary,
            archive_base=archive_root,
            for_cleanup_date=cleanup_date,
        )
        pointer_path = publish_current_pointer(pointer=pointer, archive_base=archive_root)
    except (ArchiveBlocked, FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        payload["result"] = "BLOCKED"
        payload["blockers"] = [str(exc)]
        return payload
    payload.update({
        "result": "ARCHIVED_VERIFIED",
        "batch_id": summary["batch_id"],
        "retained_trade_dates": retained_dates,
        "entry_count": summary["entry_count"],
        "manifest": pointer["manifest"],
        "summary": pointer["summary"],
        "allowlist": pointer["allowlist"],
        "restore_proof": pointer["restore_proof"],
        "pointer_path": str(pointer_path),
        "pointer_sha256": _sha256_path(pointer_path),
        "pointer_published": True,
    })
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--archive-base", type=Path, default=ARCHIVE_BASE)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_local_artifact_archive_daily_once(
        dsn=args.dsn,
        archive_base=args.archive_base,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["result"] == "ARCHIVED_VERIFIED" else 2


if __name__ == "__main__":
    sys.exit(main())
