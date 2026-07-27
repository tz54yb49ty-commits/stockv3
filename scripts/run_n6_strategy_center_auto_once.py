#!/usr/bin/env python3
"""Run one bounded, display-only N6 strategy-center auto-evaluation pass."""

from __future__ import annotations

if __name__ == "__main__":
    raise SystemExit("strategy_center_retired")

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import tempfile
import time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from ashare_v3.user.strategy_center import EVALUATOR_POLICY_HASH
from ashare_v3.user.strategy_center_worker import (
    AutoEvaluationState,
    N6DisplayBatchAuthority,
    N6TradeDateAuthority,
    PostgresStrategyCenterEvaluatorRepository,
    StrategyEvaluatorScope,
    StrategyCenterWorkerBlocked,
    run_strategy_center_once,
)
from scripts.run_n6_strategy_center_once import validate_worker_environment


RELEASE_ID_PATTERN = re.compile(r"^[0-9]{8}_[0-9]{6}__[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
STATE_VERSION = 1
BACKOFF_SECONDS = (5, 10, 20, 40, 60)
# Keep the existing bounded evaluator contract.  Evidence persistence receives
# its own timer after the evaluator timer is cancelled; it never consumes the
# database/evaluator SQL deadline.
DEFAULT_MAX_RUNTIME_SECONDS = 12
EVIDENCE_MAX_RUNTIME_SECONDS = 1.0
DEFAULT_SIGNAL_SOURCE_USER_ID = 1
SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")
HISTORY_MAX_BYTES = 1024 * 1024
HISTORY_ROTATION_COUNT = 3
RUNTIME_STATE_DIR = Path(
    "/Users/chuanfuchen/.local/state/ashare-v3/n6-b-track/strategy-center"
)
EXPECTED_RUNTIME_PATHS = {
    "state_path": RUNTIME_STATE_DIR / "evaluator-state.json",
    "lock_path": RUNTIME_STATE_DIR / "evaluator.lock",
    "report_path": RUNTIME_STATE_DIR / "latest-report.json",
    "history_path": RUNTIME_STATE_DIR / "history.jsonl",
}


class AutoEvaluatorStateBlocked(RuntimeError):
    pass


class AutoEvaluatorDeadlineExceeded(TimeoutError):
    pass


class AutoEvaluatorRepository(Protocol):
    def load_auto_evaluation_state(self) -> AutoEvaluationState: ...

    def mark_pending_replay_status(
        self, revision_ids: Sequence[int], status: str
    ) -> tuple[int, ...]: ...


EvaluateOnce = Callable[
    [str, str, StrategyEvaluatorScope, bool, bool],
    Mapping[str, Any],
]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _attempt_key(
    current: AutoEvaluationState,
    *,
    release_id: str,
    trigger_kind: str,
    selected_scope: StrategyEvaluatorScope,
    evaluator_policy_hash: str = EVALUATOR_POLICY_HASH,
) -> str:
    body = {
        "trade_date": current.trade_date,
        "trade_date_authority": _trade_date_authority_payload(current),
        "source_fingerprint": current.source_fingerprint,
        "release_id": release_id,
        "evaluator_policy_hash": evaluator_policy_hash,
        "trigger_kind": trigger_kind,
        "selected_scope": _scope_payload(selected_scope),
    }
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def _trade_date_authority_payload(
    current: AutoEvaluationState,
) -> dict[str, Any]:
    authority = current.trade_date_authority
    if not isinstance(authority, N6TradeDateAuthority):
        raise AutoEvaluatorStateBlocked(
            "n6_trade_date_authority_missing"
        )
    if authority.trade_date != current.trade_date:
        raise AutoEvaluatorStateBlocked(
            "n6_trade_date_authority_mismatch"
        )
    return asdict(authority)


def _trade_date_authority_from_payload(
    value: Any,
) -> N6TradeDateAuthority:
    if not isinstance(value, Mapping) or set(value) != {
        "trade_date",
        "batches",
    }:
        raise AutoEvaluatorStateBlocked(
            "state_trade_date_authority_invalid"
        )
    raw_batches = value.get("batches")
    if not isinstance(raw_batches, (list, tuple)):
        raise AutoEvaluatorStateBlocked(
            "state_trade_date_authority_invalid"
        )
    try:
        batches = tuple(
            N6DisplayBatchAuthority(**dict(item))
            for item in raw_batches
            if isinstance(item, Mapping)
        )
        if len(batches) != len(raw_batches):
            raise ValueError("batch_payload_invalid")
        return N6TradeDateAuthority(
            trade_date=str(value.get("trade_date") or ""),
            batches=batches,
        )
    except (TypeError, ValueError) as exc:
        raise AutoEvaluatorStateBlocked(
            "state_trade_date_authority_invalid"
        ) from exc


def _scope_payload(scope: StrategyEvaluatorScope) -> dict[str, int]:
    return {
        "principal_id": scope.principal_id,
        "user_id": scope.user_id,
        "selection_revision_id": scope.selection_revision_id,
    }


def _scope_from_payload(value: Any) -> StrategyEvaluatorScope:
    if not isinstance(value, Mapping) or set(value) != {
        "principal_id",
        "user_id",
        "selection_revision_id",
    }:
        raise AutoEvaluatorStateBlocked("scope_cursor_scope_invalid")
    try:
        return StrategyEvaluatorScope(
            principal_id=value["principal_id"],
            user_id=value["user_id"],
            selection_revision_id=value["selection_revision_id"],
        )
    except (TypeError, ValueError) as exc:
        raise AutoEvaluatorStateBlocked("scope_cursor_scope_invalid") from exc


def _ordered_scopes(
    scopes: Sequence[StrategyEvaluatorScope],
) -> tuple[StrategyEvaluatorScope, ...]:
    ordered = tuple(
        sorted(
            scopes,
            key=lambda scope: (
                scope.selection_revision_id,
                scope.principal_id,
                scope.user_id,
            ),
        )
    )
    if len(set(ordered)) != len(ordered):
        raise AutoEvaluatorStateBlocked("auto_scope_authority_duplicate")
    return ordered


def _local_trade_date_relation(
    trade_date: str,
    observed_at: datetime,
) -> int:
    if not re.fullmatch(r"[0-9]{8}", trade_date):
        raise AutoEvaluatorStateBlocked("trade_date_authority_invalid")
    reviewed_date = datetime.strptime(trade_date, "%Y%m%d").date()
    local_date = observed_at.astimezone(SHANGHAI_TIMEZONE).date()
    return (local_date > reviewed_date) - (local_date < reviewed_date)


def _source_cursor_payload(
    current: AutoEvaluationState,
    *,
    release_id: str,
) -> dict[str, str]:
    return {
        "trade_date": current.trade_date,
        "fingerprint": current.source_fingerprint,
        "release_id": release_id,
        "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
    }


def _scope_cursor_payload(
    current: AutoEvaluationState,
    *,
    release_id: str,
    authority_scopes: Sequence[StrategyEvaluatorScope],
    remaining_scopes: Sequence[StrategyEvaluatorScope],
    last_completed_scope: StrategyEvaluatorScope | None,
) -> dict[str, Any]:
    return {
        **_source_cursor_payload(current, release_id=release_id),
        "authority_scopes": [
            _scope_payload(scope) for scope in authority_scopes
        ],
        "remaining_scopes": [
            _scope_payload(scope) for scope in remaining_scopes
        ],
        "last_completed_scope": (
            _scope_payload(last_completed_scope)
            if last_completed_scope is not None
            else None
        ),
    }


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_state_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("state_version") != STATE_VERSION:
        raise AutoEvaluatorStateBlocked("state_version_invalid")

    failures = value.get("consecutive_failures")
    if isinstance(failures, bool) or not isinstance(failures, int) or failures < 0:
        raise AutoEvaluatorStateBlocked("state_failure_count_invalid")

    release_id = value.get("release_id")
    if not isinstance(release_id, str) or not RELEASE_ID_PATTERN.fullmatch(
        release_id
    ):
        raise AutoEvaluatorStateBlocked("state_release_id_invalid")
    policy_hash = value.get("evaluator_policy_hash")
    if not isinstance(policy_hash, str) or not SHA256_PATTERN.fullmatch(
        policy_hash
    ):
        raise AutoEvaluatorStateBlocked("state_policy_hash_invalid")
    state_trade_date_authority = None
    if "trade_date_authority" in value:
        state_trade_date_authority = _trade_date_authority_from_payload(
            value.get("trade_date_authority")
        )

    cursor = value.get("source_cursor", {})
    if not isinstance(cursor, dict):
        raise AutoEvaluatorStateBlocked("source_cursor_invalid")
    if cursor:
        required_cursor_keys = {
            "trade_date",
            "fingerprint",
            "release_id",
            "evaluator_policy_hash",
        }
        if set(cursor) != required_cursor_keys:
            raise AutoEvaluatorStateBlocked("source_cursor_schema_invalid")
        if not re.fullmatch(r"[0-9]{8}", str(cursor.get("trade_date") or "")):
            raise AutoEvaluatorStateBlocked("source_cursor_trade_date_invalid")
        if not SHA256_PATTERN.fullmatch(str(cursor.get("fingerprint") or "")):
            raise AutoEvaluatorStateBlocked("source_cursor_fingerprint_invalid")
        if not RELEASE_ID_PATTERN.fullmatch(str(cursor.get("release_id") or "")):
            raise AutoEvaluatorStateBlocked("source_cursor_release_id_invalid")
        if not SHA256_PATTERN.fullmatch(
            str(cursor.get("evaluator_policy_hash") or "")
        ):
            raise AutoEvaluatorStateBlocked("source_cursor_policy_hash_invalid")
        if (
            state_trade_date_authority is not None
            and str(cursor.get("trade_date") or "")
            != state_trade_date_authority.trade_date
        ):
            raise AutoEvaluatorStateBlocked(
                "state_trade_date_authority_mismatch"
            )

    scope_cursor = value.get("scope_cursor", {})
    if not isinstance(scope_cursor, dict):
        raise AutoEvaluatorStateBlocked("scope_cursor_invalid")
    if scope_cursor:
        required_scope_cursor_keys = {
            "trade_date",
            "fingerprint",
            "release_id",
            "evaluator_policy_hash",
            "authority_scopes",
            "remaining_scopes",
            "last_completed_scope",
        }
        if set(scope_cursor) != required_scope_cursor_keys:
            raise AutoEvaluatorStateBlocked("scope_cursor_schema_invalid")
        if not re.fullmatch(
            r"[0-9]{8}", str(scope_cursor.get("trade_date") or "")
        ):
            raise AutoEvaluatorStateBlocked("scope_cursor_trade_date_invalid")
        if not SHA256_PATTERN.fullmatch(
            str(scope_cursor.get("fingerprint") or "")
        ):
            raise AutoEvaluatorStateBlocked("scope_cursor_fingerprint_invalid")
        if not RELEASE_ID_PATTERN.fullmatch(
            str(scope_cursor.get("release_id") or "")
        ):
            raise AutoEvaluatorStateBlocked("scope_cursor_release_id_invalid")
        if not SHA256_PATTERN.fullmatch(
            str(scope_cursor.get("evaluator_policy_hash") or "")
        ):
            raise AutoEvaluatorStateBlocked("scope_cursor_policy_hash_invalid")
        raw_authority = scope_cursor.get("authority_scopes")
        raw_remaining = scope_cursor.get("remaining_scopes")
        if not isinstance(raw_authority, list) or not isinstance(
            raw_remaining, list
        ):
            raise AutoEvaluatorStateBlocked("scope_cursor_queue_invalid")
        authority_scopes = tuple(
            _scope_from_payload(item) for item in raw_authority
        )
        remaining_scopes = tuple(
            _scope_from_payload(item) for item in raw_remaining
        )
        valid_suffix = any(
            authority_scopes[index:] == remaining_scopes
            for index in range(1, len(authority_scopes) + 1)
        )
        if (
            authority_scopes != _ordered_scopes(authority_scopes)
            or not authority_scopes
            or not valid_suffix
        ):
            raise AutoEvaluatorStateBlocked("scope_cursor_queue_invalid")
        last_completed = scope_cursor.get("last_completed_scope")
        if last_completed is None:
            raise AutoEvaluatorStateBlocked("scope_cursor_completed_invalid")
        completed_scope = _scope_from_payload(last_completed)
        completed_index = len(authority_scopes) - len(remaining_scopes) - 1
        if authority_scopes[completed_index] != completed_scope:
            raise AutoEvaluatorStateBlocked("scope_cursor_completed_invalid")

    failed_attempt_key = value.get("last_failed_attempt_key", "")
    next_retry_at = value.get("next_retry_at", "")
    if not isinstance(failed_attempt_key, str) or not isinstance(
        next_retry_at, str
    ):
        raise AutoEvaluatorStateBlocked("state_backoff_schema_invalid")
    if failures:
        if not SHA256_PATTERN.fullmatch(failed_attempt_key):
            raise AutoEvaluatorStateBlocked("state_failed_attempt_key_invalid")
        if _parse_utc(next_retry_at) is None:
            raise AutoEvaluatorStateBlocked("state_next_retry_at_invalid")
    elif failed_attempt_key or next_retry_at:
        raise AutoEvaluatorStateBlocked("state_stale_backoff_invalid")

    for key in ("last_success_at", "last_failure_at"):
        timestamp = value.get(key, "")
        if not isinstance(timestamp, str):
            raise AutoEvaluatorStateBlocked(f"state_{key}_invalid")
        if timestamp and _parse_utc(timestamp) is None:
            raise AutoEvaluatorStateBlocked(f"state_{key}_invalid")
    for key in (
        "last_error",
        "last_error_message",
        "last_trigger_kind",
        "last_evaluator_run_id",
    ):
        item = value.get(key, "")
        if not isinstance(item, str) or len(item) > 500:
            raise AutoEvaluatorStateBlocked(f"state_{key}_invalid")
    return dict(value)


def _report_envelope(
    payload: Mapping[str, Any],
    *,
    started_monotonic: float,
    release_id: str,
    current: AutoEvaluationState | None = None,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(payload)
    pending_ids: list[int] | None
    if current is not None:
        pending_ids = [int(value) for value in current.pending_revision_ids]
    else:
        raw_pending = result.get("pending_revision_ids")
        pending_ids = (
            [int(value) for value in raw_pending]
            if isinstance(raw_pending, (list, tuple))
            else None
        )
    failures = result.get("consecutive_failures")
    if failures is None and previous is not None:
        failures = previous.get("consecutive_failures")
    source_watermarks = (
        dict(current.source_watermarks) if current is not None else {}
    )
    trade_date_authority = (
        _trade_date_authority_payload(current)
        if current is not None
        else None
    )
    result.update(
        {
            "trigger_kind": str(result.get("trigger_kind") or "unknown"),
            "duration_ms": round(
                (time.monotonic() - started_monotonic) * 1000,
                3,
            ),
            "trade_date": (
                current.trade_date
                if current is not None
                else result.get("trade_date")
            ),
            "source_fingerprint": (
                current.source_fingerprint
                if current is not None
                else result.get("source_fingerprint")
            ),
            "source_watermarks": source_watermarks,
            "trade_date_authority": trade_date_authority,
            "source_authority_status": (
                str(result.get("source_authority_status") or "")
                or (
                    "reviewed_n6_display_consensus"
                    if trade_date_authority is not None
                    else "unavailable"
                )
            ),
            "pending_revision_ids": pending_ids,
            "pending_revision_count": (
                len(pending_ids) if pending_ids is not None else None
            ),
            "pending_authority_status": (
                "available" if pending_ids is not None else "unavailable"
            ),
            "selected_scope": result.get("selected_scope"),
            "remaining_count": int(result.get("remaining_count") or 0),
            "cursor": result.get("cursor"),
            "per_scope_result": result.get("per_scope_result"),
            "consecutive_failures": (
                int(failures) if failures is not None else None
            ),
            "database_committed": bool(result.get("database_committed", False)),
            "write_called": bool(result.get("write_called", False)),
            "release_id": release_id,
            "release_commit": release_id.rsplit("__", 1)[-1],
            "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
        }
    )
    return result


def _ensure_private_directory(directory: Path) -> None:
    if not directory.is_absolute():
        raise AutoEvaluatorStateBlocked("runtime_directory_must_be_absolute")
    try:
        directory_stat = directory.lstat()
    except OSError as exc:
        raise AutoEvaluatorStateBlocked("runtime_directory_unavailable") from exc
    if not stat.S_ISDIR(directory_stat.st_mode):
        raise AutoEvaluatorStateBlocked("runtime_directory_must_be_directory")
    if directory_stat.st_uid != os.getuid():
        raise AutoEvaluatorStateBlocked("runtime_directory_owner_invalid")
    if stat.S_IMODE(directory_stat.st_mode) != 0o700:
        raise AutoEvaluatorStateBlocked("runtime_directory_mode_invalid")
    try:
        resolved = directory.resolve(strict=True)
    except OSError as exc:
        raise AutoEvaluatorStateBlocked("runtime_directory_realpath_invalid") from exc
    if resolved != directory:
        raise AutoEvaluatorStateBlocked("runtime_directory_symlink_forbidden")


def _validate_private_file(path: Path) -> os.stat_result:
    try:
        file_stat = path.lstat()
    except OSError as exc:
        raise AutoEvaluatorStateBlocked("runtime_file_unavailable") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise AutoEvaluatorStateBlocked("runtime_file_must_be_regular")
    if file_stat.st_uid != os.getuid():
        raise AutoEvaluatorStateBlocked("runtime_file_owner_invalid")
    if stat.S_IMODE(file_stat.st_mode) != 0o600:
        raise AutoEvaluatorStateBlocked("runtime_file_mode_invalid")
    if file_stat.st_nlink != 1:
        raise AutoEvaluatorStateBlocked("runtime_file_hardlink_forbidden")
    return file_stat


def _read_private_text(path: Path, *, missing_ok: bool) -> str | None:
    _ensure_private_directory(path.parent)
    try:
        _validate_private_file(path)
    except AutoEvaluatorStateBlocked as exc:
        if missing_ok and not path.exists() and not path.is_symlink():
            return None
        raise exc
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
        opened_stat = os.fstat(handle.fileno())
        if opened_stat.st_ino != path.lstat().st_ino:
            raise AutoEvaluatorStateBlocked("runtime_file_replaced_during_read")
        return handle.read()


def _read_state(path: Path) -> dict[str, Any]:
    raw = _read_private_text(path, missing_ok=True)
    if raw is None:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AutoEvaluatorStateBlocked("state_json_invalid") from exc
    if not isinstance(value, dict):
        raise AutoEvaluatorStateBlocked("state_payload_invalid")
    return _validate_state_payload(value)


def _atomic_write_text(path: Path, value: str) -> None:
    _ensure_private_directory(path.parent)
    if path.exists() or path.is_symlink():
        _validate_private_file(path)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
        temporary_name = None
        directory_fd = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    value = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"
    _atomic_write_text(path, value)


def _append_history(
    path: Path,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    _ensure_private_directory(path.parent)
    history_metadata = {
        "history_rotated": False,
        "history_rotation_count": HISTORY_ROTATION_COUNT,
        "history_max_bytes": HISTORY_MAX_BYTES,
    }
    encoded = (
        _canonical_json({**dict(payload), **history_metadata}) + "\n"
    ).encode("utf-8")
    if len(encoded) > HISTORY_MAX_BYTES:
        raise AutoEvaluatorStateBlocked("history_record_too_large")
    if path.exists() or path.is_symlink():
        current_stat = _validate_private_file(path)
        if current_stat.st_size + len(encoded) > HISTORY_MAX_BYTES:
            for index in range(HISTORY_ROTATION_COUNT, 0, -1):
                source = path if index == 1 else Path(f"{path}.{index - 1}")
                target = Path(f"{path}.{index}")
                if source.exists() or source.is_symlink():
                    _validate_private_file(source)
                    if target.exists() or target.is_symlink():
                        _validate_private_file(target)
                    os.replace(source, target)
            history_metadata["history_rotated"] = True
            encoded = (
                _canonical_json({**dict(payload), **history_metadata}) + "\n"
            ).encode("utf-8")
            if len(encoded) > HISTORY_MAX_BYTES:
                raise AutoEvaluatorStateBlocked("history_record_too_large")

    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        opened_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_stat.st_mode)
            or opened_stat.st_uid != os.getuid()
            or stat.S_IMODE(opened_stat.st_mode) != 0o600
            or opened_stat.st_nlink != 1
        ):
            raise AutoEvaluatorStateBlocked("history_file_invalid")
        written = 0
        while written < len(encoded):
            appended = os.write(descriptor, encoded[written:])
            if appended <= 0:
                raise AutoEvaluatorStateBlocked("history_append_incomplete")
            written += appended
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(
        path.parent,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return history_metadata


@contextmanager
def _singleton_lock(path: Path):
    _ensure_private_directory(path.parent)
    if path.exists() or path.is_symlink():
        _validate_private_file(path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        lock_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(lock_stat.st_mode):
            raise ValueError("singleton_lock_must_be_regular_file")
        if lock_stat.st_uid != os.getuid():
            raise ValueError("singleton_lock_must_be_owned_by_runtime_user")
        if stat.S_IMODE(lock_stat.st_mode) != 0o600:
            raise ValueError("singleton_lock_mode_invalid")
        if lock_stat.st_nlink != 1:
            raise ValueError("singleton_lock_hardlink_forbidden")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _build_failure_state(
    *,
    previous: Mapping[str, Any],
    observed_at: datetime,
    attempt_key: str,
    trigger_kind: str,
    release_id: str,
    error: Exception,
) -> tuple[dict[str, Any], int, datetime]:
    previous_failures = int(previous.get("consecutive_failures") or 0)
    failures = (
        previous_failures + 1
        if previous.get("last_failed_attempt_key") == attempt_key
        else 1
    )
    delay = BACKOFF_SECONDS[min(failures - 1, len(BACKOFF_SECONDS) - 1)]
    retry_time = datetime.fromtimestamp(
        observed_at.timestamp() + delay,
        timezone.utc,
    )
    state = {
        **dict(previous),
        "state_version": STATE_VERSION,
        "consecutive_failures": failures,
        "last_failed_attempt_key": attempt_key,
        "next_retry_at": _iso_utc(retry_time),
        "last_error": type(error).__name__,
        "last_error_message": str(error)[:500],
        "last_failure_at": _iso_utc(datetime.now(timezone.utc)),
        "last_trigger_kind": trigger_kind,
        "release_id": release_id,
        "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
    }
    return state, failures, retry_time


def run_auto_once(
    *,
    repository: AutoEvaluatorRepository,
    state_path: Path,
    lock_path: Path,
    release_id: str,
    execute: bool = False,
    runtime_authorized: bool = False,
    now: datetime | None = None,
    evaluate_once: EvaluateOnce | None = None,
) -> dict[str, Any]:
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise ValueError("invalid_immutable_release_id")
    for name, path in (("state_path", state_path), ("lock_path", lock_path)):
        if not path.is_absolute():
            raise ValueError(f"{name}_must_be_absolute")
    if execute and not runtime_authorized:
        raise ValueError("runtime_authorization_required")

    observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    started_monotonic = time.monotonic()

    def finalize(
        payload: Mapping[str, Any],
        *,
        current_state: AutoEvaluationState | None = None,
        previous_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _report_envelope(
            payload,
            started_monotonic=started_monotonic,
            release_id=release_id,
            current=current_state,
            previous=previous_state,
        )

    with _singleton_lock(lock_path) as acquired:
        if not acquired:
            return finalize(
                {
                    "ok": True,
                    "status": "noop_lock_held",
                    "trigger_kind": "local_lock",
                    "display_only": True,
                    "observed_at": _iso_utc(observed_at),
                }
            )

        try:
            previous = _read_state(state_path)
        except AutoEvaluatorStateBlocked as exc:
            return finalize(
                {
                    "ok": False,
                    "status": "blocked_state_invalid",
                    "trigger_kind": "state_validation",
                    "error": type(exc).__name__,
                    "error_message": str(exc),
                    "display_only": True,
                    "observed_at": _iso_utc(observed_at),
                }
            )

        source_state_attempt_key = hashlib.sha256(
            _canonical_json(
                {
                    "stage": "source_state",
                    "release_id": release_id,
                    "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
                }
            ).encode("utf-8")
        ).hexdigest()
        next_retry_at = _parse_utc(previous.get("next_retry_at"))
        if (
            previous.get("last_trigger_kind") == "source_state"
            and previous.get("last_failed_attempt_key")
            == source_state_attempt_key
            and next_retry_at is not None
            and observed_at < next_retry_at
        ):
            return finalize(
                {
                    "ok": True,
                    "status": "noop_backoff",
                    "trigger_kind": "source_state",
                    "display_only": True,
                    "consecutive_failures": int(
                        previous.get("consecutive_failures") or 0
                    ),
                    "next_retry_at": _iso_utc(next_retry_at),
                    "observed_at": _iso_utc(observed_at),
                },
                previous_state=previous,
            )
        try:
            current = repository.load_auto_evaluation_state()
            _trade_date_authority_payload(current)
        except Exception as exc:
            failed_state, failures, retry_time = _build_failure_state(
                previous=previous,
                observed_at=observed_at,
                attempt_key=source_state_attempt_key,
                trigger_kind="source_state",
                release_id=release_id,
                error=exc,
            )
            state_persist_error = ""
            if execute:
                try:
                    _atomic_write_json(state_path, failed_state)
                except AutoEvaluatorDeadlineExceeded:
                    raise
                except Exception as state_exc:
                    state_persist_error = (
                        f"{type(state_exc).__name__}:{str(state_exc)[:300]}"
                    )
            return finalize(
                {
                    "ok": False,
                    "status": "failed_source_state",
                    "error": type(exc).__name__,
                    "error_message": str(exc)[:500],
                    "trigger_kind": "source_state",
                    "consecutive_failures": failures,
                    "next_retry_at": _iso_utc(retry_time),
                    "state_persist_error": state_persist_error,
                    "display_only": True,
                    "observed_at": _iso_utc(observed_at),
                },
                previous_state=previous,
            )

        trade_date_relation = _local_trade_date_relation(
            current.trade_date,
            observed_at,
        )
        if trade_date_relation < 0:
            return finalize(
                {
                    "ok": True,
                    "status": "WAITING_OPEN_TRADE_DATE",
                    "trigger_kind": "trade_date_authority_wait",
                    "display_only": True,
                    "consecutive_failures": int(
                        previous.get("consecutive_failures") or 0
                    ),
                    "database_committed": False,
                    "write_called": False,
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )
        if trade_date_relation > 0:
            return finalize(
                {
                    "ok": False,
                    "status": "BLOCKED_STALE_TRADE_DATE_AUTHORITY",
                    "trigger_kind": "trade_date_authority_stale",
                    "error": "AutoEvaluatorStateBlocked",
                    "error_message": "reviewed_trade_date_is_stale",
                    "display_only": True,
                    "consecutive_failures": int(
                        previous.get("consecutive_failures") or 0
                    ),
                    "database_committed": False,
                    "write_called": False,
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )

        pending_ids = tuple(int(value) for value in current.pending_revision_ids)
        try:
            pending_scopes = _ordered_scopes(current.pending_scopes)
            active_scopes = _ordered_scopes(current.active_scopes)
            replay_pending_active_scopes = _ordered_scopes(
                current.replay_pending_active_scopes
            )
        except AutoEvaluatorStateBlocked as exc:
            return finalize(
                {
                    "ok": False,
                    "status": "blocked_scope_authority_invalid",
                    "trigger_kind": "scope_authority",
                    "error": type(exc).__name__,
                    "error_message": str(exc),
                    "display_only": True,
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )
        if not set(replay_pending_active_scopes).issubset(set(active_scopes)):
            return finalize(
                {
                    "ok": False,
                    "status": "blocked_scope_authority_invalid",
                    "trigger_kind": "scope_authority",
                    "error": "AutoEvaluatorStateBlocked",
                    "error_message": "replay_pending_active_scope_mismatch",
                    "display_only": True,
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )
        if pending_ids != tuple(
            scope.selection_revision_id for scope in pending_scopes
        ):
            return finalize(
                {
                    "ok": False,
                    "status": "blocked_scope_authority_invalid",
                    "trigger_kind": "scope_authority",
                    "error": "AutoEvaluatorStateBlocked",
                    "error_message": "pending_scope_authority_mismatch",
                    "display_only": True,
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )
        previous_cursor = previous.get("source_cursor", {})
        if not isinstance(previous_cursor, Mapping):
            return finalize(
                {
                    "ok": False,
                    "status": "blocked_state_invalid",
                    "trigger_kind": "state_validation",
                    "error": "AutoEvaluatorStateBlocked",
                    "error_message": "source_cursor_invalid",
                    "display_only": True,
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )
        release_changed = (
            str(previous_cursor.get("release_id") or "") != release_id
            or str(previous_cursor.get("evaluator_policy_hash") or "")
            != EVALUATOR_POLICY_HASH
        )
        source_changed = (
            str(previous_cursor.get("trade_date") or "") != current.trade_date
            or str(previous_cursor.get("fingerprint") or "")
            != current.source_fingerprint
        )
        source_state_recovered = (
            previous.get("last_trigger_kind") == "source_state"
            and int(previous.get("consecutive_failures") or 0) > 0
        )
        trigger_kind = "none"
        selected_scope: StrategyEvaluatorScope | None = None
        queued_scopes: tuple[StrategyEvaluatorScope, ...] = ()
        previous_scope_cursor = previous.get("scope_cursor", {})
        if not isinstance(previous_scope_cursor, Mapping):
            return finalize(
                {
                    "ok": False,
                    "status": "blocked_state_invalid",
                    "trigger_kind": "state_validation",
                    "error": "AutoEvaluatorStateBlocked",
                    "error_message": "scope_cursor_invalid",
                    "display_only": True,
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )
        if pending_scopes:
            trigger_kind = "pending_selection"
            queued_scopes = pending_scopes
            selected_scope = queued_scopes[0]
        elif replay_pending_active_scopes:
            trigger_kind = "active_replay_pending"
            queued_scopes = replay_pending_active_scopes
            selected_scope = queued_scopes[0]
        elif release_changed or source_changed:
            trigger_kind = "release_changed" if release_changed else "source_changed"
            current_authority = [_scope_payload(scope) for scope in active_scopes]
            scope_cursor_matches = bool(previous_scope_cursor) and all(
                (
                    str(previous_scope_cursor.get("trade_date") or "")
                    == current.trade_date,
                    str(previous_scope_cursor.get("fingerprint") or "")
                    == current.source_fingerprint,
                    str(previous_scope_cursor.get("release_id") or "")
                    == release_id,
                    str(
                        previous_scope_cursor.get("evaluator_policy_hash") or ""
                    )
                    == EVALUATOR_POLICY_HASH,
                    previous_scope_cursor.get("authority_scopes")
                    == current_authority,
                )
            )
            if scope_cursor_matches:
                queued_scopes = tuple(
                    _scope_from_payload(value)
                    for value in previous_scope_cursor.get("remaining_scopes", [])
                )
            else:
                queued_scopes = active_scopes
            if not queued_scopes:
                return finalize(
                    {
                        "ok": False,
                        "status": "blocked_scope_authority_invalid",
                        "trigger_kind": trigger_kind,
                        "error": "AutoEvaluatorStateBlocked",
                        "error_message": "active_scope_authority_empty",
                        "display_only": True,
                        "remaining_count": 0,
                        "cursor": {
                            "source_cursor": dict(previous_cursor),
                            "scope_cursor": dict(previous_scope_cursor),
                        },
                        "observed_at": _iso_utc(observed_at),
                    },
                    current_state=current,
                    previous_state=previous,
                )
            selected_scope = queued_scopes[0]
        elif active_scopes and not source_state_recovered:
            # Temporal Confluence has lifecycle transitions (fresh -> stale)
            # even when no source watermark changes.  Keep the canonical
            # one-scope-per-tick boundary and advance a persistent round-robin
            # cursor instead of treating an unchanged source as a global noop.
            trigger_kind = "time_tick"
            current_authority = [_scope_payload(scope) for scope in active_scopes]
            scope_cursor_matches = bool(previous_scope_cursor) and all(
                (
                    str(previous_scope_cursor.get("trade_date") or "")
                    == current.trade_date,
                    str(previous_scope_cursor.get("fingerprint") or "")
                    == current.source_fingerprint,
                    str(previous_scope_cursor.get("release_id") or "")
                    == release_id,
                    str(
                        previous_scope_cursor.get("evaluator_policy_hash") or ""
                    )
                    == EVALUATOR_POLICY_HASH,
                    previous_scope_cursor.get("authority_scopes")
                    == current_authority,
                )
            )
            if scope_cursor_matches:
                queued_scopes = tuple(
                    _scope_from_payload(value)
                    for value in previous_scope_cursor.get("remaining_scopes", [])
                )
            if not queued_scopes:
                queued_scopes = active_scopes
            selected_scope = queued_scopes[0]
        attempt_key = (
            _attempt_key(
                current,
                release_id=release_id,
                trigger_kind=trigger_kind,
                selected_scope=selected_scope,
            )
            if selected_scope is not None
            else ""
        )
        next_retry_at = _parse_utc(previous.get("next_retry_at"))
        if (
            trigger_kind != "none"
            and previous.get("last_failed_attempt_key") == attempt_key
            and next_retry_at is not None
            and observed_at < next_retry_at
        ):
            return finalize(
                {
                    "ok": True,
                    "status": "noop_backoff",
                    "trigger_kind": trigger_kind,
                    "display_only": True,
                    "next_retry_at": _iso_utc(next_retry_at),
                    "selected_scope": _scope_payload(selected_scope),
                    "remaining_count": len(queued_scopes),
                    "cursor": {
                        "source_cursor": dict(previous_cursor),
                        "scope_cursor": dict(previous_scope_cursor),
                    },
                    "consecutive_failures": int(
                        previous.get("consecutive_failures") or 0
                    ),
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )
        if trigger_kind == "none":
            state_persist_error = ""
            if source_state_recovered and execute:
                recovered_state = {
                    **dict(previous),
                    "state_version": STATE_VERSION,
                    "consecutive_failures": 0,
                    "last_failed_attempt_key": "",
                    "next_retry_at": "",
                    "last_error": "",
                    "last_error_message": "",
                    "last_success_at": _iso_utc(datetime.now(timezone.utc)),
                    "last_trigger_kind": "source_state_recovered",
                    "release_id": release_id,
                    "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
                    "trade_date_authority": (
                        _trade_date_authority_payload(current)
                    ),
                }
                try:
                    _atomic_write_json(state_path, recovered_state)
                except AutoEvaluatorDeadlineExceeded:
                    raise
                except Exception as exc:
                    state_persist_error = (
                        f"{type(exc).__name__}:{str(exc)[:300]}"
                    )
            return finalize(
                {
                    "ok": not bool(state_persist_error),
                    "status": (
                        "source_state_recovered_state_persist_failed"
                        if state_persist_error
                        else (
                            "noop_source_state_recovered"
                            if source_state_recovered
                            else "noop_unchanged"
                        )
                    ),
                    "trigger_kind": (
                        "source_state_recovered"
                        if source_state_recovered
                        else "none"
                    ),
                    "display_only": True,
                    "consecutive_failures": (
                        0
                        if source_state_recovered and not state_persist_error
                        else int(previous.get("consecutive_failures") or 0)
                    ),
                    "state_persist_error": state_persist_error,
                    "remaining_count": 0,
                    "cursor": {
                        "source_cursor": dict(previous_cursor),
                        "scope_cursor": dict(previous_scope_cursor),
                    },
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )

        assert selected_scope is not None
        evaluator_run_id = (
            f"strategy-center-auto-{current.trade_date}-"
            f"{trigger_kind}-r{selected_scope.selection_revision_id}-"
            f"{attempt_key[:16]}"
            + (
                f"-{observed_at.strftime('%H%M%S')}"
                if trigger_kind == "time_tick"
                else ""
            )
        )
        try:
            evaluator = evaluate_once or (
                lambda trade_date, run_id, scope, should_execute, authorized: (
                    run_strategy_center_once(
                        repository=repository,  # type: ignore[arg-type]
                        trade_date=trade_date,
                        evaluator_run_id=run_id,
                        scope=scope,
                        evaluation_time=observed_at.astimezone(
                            SHANGHAI_TIMEZONE
                        ).isoformat(),
                        execute=should_execute,
                        runtime_authorized=authorized,
                    )
                )
            )
            evaluation = dict(
                evaluator(
                    current.trade_date,
                    evaluator_run_id,
                    selected_scope,
                    execute,
                    runtime_authorized,
                )
            )
            if execute and not bool(evaluation.get("write_called")):
                raise RuntimeError("execute_commit_evidence_missing")
        except Exception as exc:  # DB evaluation did not commit successfully.
            if (
                isinstance(exc, StrategyCenterWorkerBlocked)
                and str(exc)
                in {
                    "strategy_worker_snapshot_cas_mismatch",
                    "strategy_selection_lifecycle_cas_mismatch",
                }
            ):
                return finalize(
                    {
                        "ok": True,
                        "status": "noop_input_drift",
                        "trigger_kind": trigger_kind,
                        "selected_scope": _scope_payload(selected_scope),
                        "remaining_count": len(queued_scopes),
                        "cursor": {
                            "source_cursor": dict(previous_cursor),
                            "scope_cursor": dict(previous_scope_cursor),
                        },
                        "per_scope_result": None,
                        "database_committed": False,
                        "write_called": False,
                        "input_drift_reason": str(exc),
                        "consecutive_failures": 0,
                        "display_only": True,
                        "observed_at": _iso_utc(observed_at),
                    },
                    current_state=current,
                    previous_state=previous,
                )
            if (
                trigger_kind == "pending_selection"
                and isinstance(exc, StrategyCenterWorkerBlocked)
                and str(exc)
                == "reviewed_n6_natural_event_group_missing"
            ):
                return finalize(
                    {
                        "ok": True,
                        "status": "noop_waiting_for_reviewed_n6_events",
                        "trigger_kind": trigger_kind,
                        "selected_scope": _scope_payload(selected_scope),
                        "remaining_count": len(queued_scopes),
                        "cursor": {
                            "source_cursor": dict(previous_cursor),
                            "scope_cursor": dict(previous_scope_cursor),
                        },
                        "per_scope_result": None,
                        "marked_failed_revision_ids": [],
                        "replay_status_write_called": False,
                        "evaluator_run_id": evaluator_run_id,
                        "consecutive_failures": int(
                            previous.get("consecutive_failures") or 0
                        ),
                        "display_only": True,
                        "database_committed": False,
                        "write_called": False,
                        "observed_at": _iso_utc(observed_at),
                    },
                    current_state=current,
                    previous_state=previous,
                )
            marked_failed: tuple[int, ...] = ()
            if (
                execute
                and trigger_kind == "pending_selection"
                and not isinstance(exc, TimeoutError)
            ):
                try:
                    marked_failed = repository.mark_pending_replay_status(
                        (selected_scope.selection_revision_id,), "failed"
                    )
                except AutoEvaluatorDeadlineExceeded:
                    raise
                except Exception:
                    pass
            failed_state, failures, retry_time = _build_failure_state(
                previous=previous,
                observed_at=observed_at,
                attempt_key=attempt_key,
                trigger_kind=trigger_kind,
                release_id=release_id,
                error=exc,
            )
            state_persist_error = ""
            if execute:
                try:
                    _atomic_write_json(state_path, failed_state)
                except AutoEvaluatorDeadlineExceeded:
                    raise
                except Exception as state_exc:
                    state_persist_error = (
                        f"{type(state_exc).__name__}:{str(state_exc)[:300]}"
                    )
            return finalize(
                {
                    "ok": False,
                    "status": "failed",
                    "error": type(exc).__name__,
                    "error_message": str(exc)[:500],
                    "trigger_kind": trigger_kind,
                    "selected_scope": _scope_payload(selected_scope),
                    "remaining_count": len(queued_scopes),
                    "cursor": {
                        "source_cursor": dict(previous_cursor),
                        "scope_cursor": dict(previous_scope_cursor),
                    },
                    "per_scope_result": None,
                    "marked_failed_revision_ids": list(marked_failed),
                    "replay_status_write_called": bool(marked_failed),
                    "evaluator_run_id": evaluator_run_id,
                    "consecutive_failures": failures,
                    "next_retry_at": _iso_utc(retry_time),
                    "state_persist_error": state_persist_error,
                    "display_only": True,
                    "database_committed": False,
                    "write_called": bool(marked_failed),
                    "observed_at": _iso_utc(observed_at),
                },
                current_state=current,
                previous_state=previous,
            )

        finished = datetime.now(timezone.utc)
        report = {
            "ok": True,
            "status": "committed" if execute else "dry_run",
            "trigger_kind": trigger_kind,
            "trade_date": current.trade_date,
            "pending_revision_ids": list(pending_ids),
            "source_fingerprint": current.source_fingerprint,
            "source_watermarks": dict(current.source_watermarks),
            "trade_date_authority": _trade_date_authority_payload(current),
            "evaluator_run_id": evaluator_run_id,
            "evaluation": evaluation,
            "selected_scope": _scope_payload(selected_scope),
            "per_scope_result": evaluation,
            "display_only": True,
            "database_committed": bool(
                execute and evaluation.get("write_called")
            ),
            "write_called": bool(evaluation.get("write_called")),
            "consecutive_failures": 0,
            "observed_at": _iso_utc(observed_at),
        }
        if execute:
            cursor = dict(previous_cursor)
            scope_cursor = dict(previous_scope_cursor)
            remaining_scopes = queued_scopes[1:]
            if trigger_kind not in {
                "pending_selection",
                "active_replay_pending",
            }:
                if trigger_kind == "time_tick":
                    cursor = _source_cursor_payload(
                        current, release_id=release_id
                    )
                    scope_cursor = _scope_cursor_payload(
                        current,
                        release_id=release_id,
                        authority_scopes=active_scopes,
                        remaining_scopes=remaining_scopes,
                        last_completed_scope=selected_scope,
                    )
                elif remaining_scopes:
                    scope_cursor = _scope_cursor_payload(
                        current,
                        release_id=release_id,
                        authority_scopes=active_scopes,
                        remaining_scopes=remaining_scopes,
                        last_completed_scope=selected_scope,
                    )
                else:
                    cursor = _source_cursor_payload(
                        current, release_id=release_id
                    )
                    scope_cursor = {}
            report["remaining_count"] = len(remaining_scopes)
            report["cursor"] = {
                "source_cursor": cursor,
                "scope_cursor": scope_cursor,
            }
            state = {
                "state_version": STATE_VERSION,
                "source_cursor": cursor,
                "scope_cursor": scope_cursor,
                "consecutive_failures": 0,
                "last_failed_attempt_key": "",
                "next_retry_at": "",
                "last_error": "",
                "last_success_at": _iso_utc(finished),
                "last_trigger_kind": trigger_kind,
                "last_evaluator_run_id": evaluator_run_id,
                "release_id": release_id,
                "evaluator_policy_hash": EVALUATOR_POLICY_HASH,
                "trade_date_authority": (
                    _trade_date_authority_payload(current)
                ),
            }
            try:
                _atomic_write_json(state_path, state)
            except AutoEvaluatorDeadlineExceeded:
                raise
            except Exception as exc:
                return finalize(
                    {
                        **report,
                        "ok": False,
                        "status": "committed_state_persist_failed",
                        "state_persisted": False,
                        "state_persist_error": (
                            f"{type(exc).__name__}:{str(exc)[:300]}"
                        ),
                    },
                    current_state=current,
                    previous_state=previous,
                )
            report["state_persisted"] = True
        else:
            report["remaining_count"] = len(queued_scopes)
            report["cursor"] = {
                "source_cursor": dict(previous_cursor),
                "scope_cursor": dict(previous_scope_cursor),
            }
        return finalize(
            report,
            current_state=current,
            previous_state=previous,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--singleton-lock-path", required=True)
    parser.add_argument("--json-report-path", required=True)
    parser.add_argument("--history-path", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument(
        "--signal-source-user-id",
        type=int,
        default=DEFAULT_SIGNAL_SOURCE_USER_ID,
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=int,
        default=DEFAULT_MAX_RUNTIME_SECONDS,
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--runtime-authorized", action="store_true")
    return parser


def _evaluation_budget_seconds(max_runtime_seconds: int) -> float:
    if (
        max_runtime_seconds <= EVIDENCE_MAX_RUNTIME_SECONDS
        or max_runtime_seconds > DEFAULT_MAX_RUNTIME_SECONDS
    ):
        raise ValueError("max_runtime_seconds_must_be_between_2_and_12")
    return max_runtime_seconds - EVIDENCE_MAX_RUNTIME_SECONDS


def _timeout_handler(_signum: int, _frame: Any) -> None:
    raise AutoEvaluatorDeadlineExceeded(
        "strategy_center_auto_evaluation_deadline_exceeded"
    )


def _evidence_timeout_handler(_signum: int, _frame: Any) -> None:
    raise AutoEvaluatorDeadlineExceeded(
        "strategy_center_auto_evidence_deadline_exceeded"
    )


def validate_runtime_paths(paths: Mapping[str, Path]) -> None:
    if set(paths) != set(EXPECTED_RUNTIME_PATHS):
        raise ValueError("runtime_path_keys_invalid")
    for key, expected in EXPECTED_RUNTIME_PATHS.items():
        if paths[key] != expected:
            raise ValueError(f"{key}_must_equal_fixed_runtime_path")
    _ensure_private_directory(RUNTIME_STATE_DIR)


def _persist_runtime_evidence(
    *,
    report: Mapping[str, Any],
    report_path: Path,
    history_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    final_report = dict(report)
    evidence_errors: list[str] = []
    report_persisted = False
    try:
        _atomic_write_json(report_path, final_report)
        report_persisted = True
    except AutoEvaluatorDeadlineExceeded:
        raise
    except Exception as exc:
        evidence_errors.append(
            f"report:{type(exc).__name__}:{str(exc)[:300]}"
        )
        final_report = {
            **final_report,
            "ok": False,
            "evidence_persist_errors": list(evidence_errors),
        }

    try:
        history_metadata = _append_history(history_path, final_report)
        final_report.update(history_metadata)
        if report_persisted:
            _atomic_write_json(report_path, final_report)
    except AutoEvaluatorDeadlineExceeded:
        raise
    except Exception as exc:
        evidence_errors.append(
            f"history:{type(exc).__name__}:{str(exc)[:300]}"
        )
        final_report = {
            **final_report,
            "ok": False,
            "evidence_persist_errors": list(evidence_errors),
        }
        if report_persisted:
            try:
                _atomic_write_json(report_path, final_report)
            except AutoEvaluatorDeadlineExceeded:
                raise
            except Exception as rewrite_exc:
                evidence_errors.append(
                    "report_rewrite:"
                    f"{type(rewrite_exc).__name__}:"
                    f"{str(rewrite_exc)[:300]}"
                )
                final_report["evidence_persist_errors"] = list(
                    evidence_errors
                )
    return final_report, evidence_errors


def _read_previous_report(path: Path) -> dict[str, Any]:
    raw = _read_private_text(path, missing_ok=True)
    if raw is None:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AutoEvaluatorStateBlocked("runtime_report_json_invalid") from exc
    if not isinstance(value, dict):
        raise AutoEvaluatorStateBlocked("runtime_report_payload_invalid")
    return value


def _report_log_signature(report: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "status": report.get("status"),
                "trigger_kind": report.get("trigger_kind"),
                "trade_date": report.get("trade_date"),
                "selected_scope": report.get("selected_scope"),
                "error": report.get("error"),
                "error_message": report.get("error_message"),
            }
        ).encode("utf-8")
    ).hexdigest()


def _should_emit_report(
    report: Mapping[str, Any],
    previous_report: Mapping[str, Any],
) -> bool:
    if report.get("history_rotated"):
        return True
    if not report.get("ok") or report.get("status") in {"committed", "dry_run"}:
        return True
    if not previous_report:
        return True
    return _report_log_signature(report) != _report_log_signature(
        previous_report
    )


def main() -> int:
    args = build_parser().parse_args()
    validate_worker_environment(os.environ)
    evaluation_budget = _evaluation_budget_seconds(args.max_runtime_seconds)
    if args.signal_source_user_id < 1:
        raise ValueError("signal_source_user_id_must_be_positive")
    paths = {
        "state_path": Path(args.state_path),
        "lock_path": Path(args.singleton_lock_path),
        "report_path": Path(args.json_report_path),
        "history_path": Path(args.history_path),
    }
    validate_runtime_paths(paths)
    prior_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, evaluation_budget)
    try:
        repository = PostgresStrategyCenterEvaluatorRepository(
            "service=n6_strategy_worker",
            signal_source_user_id=args.signal_source_user_id,
        )
        report = run_auto_once(
            repository=repository,
            state_path=paths["state_path"],
            lock_path=paths["lock_path"],
            release_id=args.release_id,
            execute=bool(args.execute),
            runtime_authorized=bool(args.runtime_authorized),
        )
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, _evidence_timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, EVIDENCE_MAX_RUNTIME_SECONDS)
        previous_report = _read_previous_report(paths["report_path"])
        report, evidence_errors = _persist_runtime_evidence(
            report=report,
            report_path=paths["report_path"],
            history_path=paths["history_path"],
        )
        if _should_emit_report(report, previous_report):
            print(_canonical_json(report))
        exit_code = (
            3
            if evidence_errors
            else (0 if report.get("ok") else 2)
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_handler)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
