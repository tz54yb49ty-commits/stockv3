from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import signal
import subprocess
import uuid
from collections.abc import Mapping as MappingABC
from collections.abc import Sequence as SequenceABC
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


class BoundedResult:
    PASS = "PASS"
    NOOP = "NOOP"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    CRASHED = "CRASHED"
    UNKNOWN_AFTER_TIMEOUT = "UNKNOWN_AFTER_TIMEOUT"
    COMMIT_UNKNOWN = "COMMIT_UNKNOWN"


_RESULT_EXIT_CODES = {
    BoundedResult.PASS: 0,
    BoundedResult.NOOP: 0,
    BoundedResult.PARTIAL: 2,
    BoundedResult.BLOCKED: 2,
    BoundedResult.CRASHED: 1,
    BoundedResult.UNKNOWN_AFTER_TIMEOUT: 3,
    BoundedResult.COMMIT_UNKNOWN: 3,
}

_SAFE_RUN_ID_PREFIX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TRADE_DATE = re.compile(r"^\d{8}$")
_STATUS_REQUIRES_POST_CHECK = {
    BoundedResult.PASS: False,
    BoundedResult.NOOP: False,
    BoundedResult.PARTIAL: False,
    BoundedResult.BLOCKED: False,
    BoundedResult.CRASHED: False,
    BoundedResult.UNKNOWN_AFTER_TIMEOUT: True,
    BoundedResult.COMMIT_UNKNOWN: True,
}
_TIMEOUT_TERMINATE_GRACE_SECONDS = 1.0


class SingletonLockHeld(RuntimeError):
    """Raised when another bounded worker owns the trade-date chain lock."""


def build_invocation_id() -> str:
    return uuid.uuid4().hex


def build_run_id(
    prefix: str,
    trade_date: str,
    invocation_id: str | None = None,
    now: datetime | None = None,
) -> str:
    safe_prefix = _validate_run_id_prefix(prefix)
    safe_trade_date = _validate_trade_date(trade_date)

    timestamp = _as_utc(now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%S%fZ")
    suffix = _normalize_invocation_id(invocation_id) if invocation_id else build_invocation_id()
    return f"{safe_prefix}_{safe_trade_date}_{timestamp}_{suffix}"


def build_phase1_realtime_chain_lock_path(repo_root: str | Path, trade_date: str) -> Path:
    if repo_root is None:
        raise ValueError("repo_root is required")
    if isinstance(repo_root, str) and not repo_root:
        raise ValueError("repo_root is required")
    try:
        root = Path(repo_root)
    except TypeError as exc:
        raise ValueError("repo_root must be a path-like value") from exc
    safe_trade_date = _validate_trade_date(trade_date)
    return root / "tmp" / f"v3_phase1_realtime_chain_{safe_trade_date}.lock"


@dataclass(frozen=True)
class BoundedWorkerConfig:
    worker_name: str
    trade_date: str
    lock_path: str | Path
    status_json: str | Path
    stop_file: str | Path | None = None
    max_runtime_seconds: float | None = None
    invocation_id: str = field(default_factory=build_invocation_id)
    run_id_prefix: str | None = None
    input_run_ids: Mapping[str, str] = field(default_factory=dict)
    git_sha: str | None = None
    config_hash: str | None = None

    def make_run_id(self, now: datetime | None = None) -> str:
        prefix = self.run_id_prefix or self.worker_name
        return build_run_id(prefix, self.trade_date, self.invocation_id, now=now)


def _default_external_side_effects() -> dict[str, Any]:
    return {
        "db_write": False,
        "worker_started": False,
        "n6_writes": 0,
        "real_trade_api_calls": 0,
        "sim_writes": 0,
        "voice_writes": 0,
        "mobile_writes": 0,
    }


@dataclass(frozen=True)
class BoundedWorkerStatus:
    result: str
    stop_reason: str | None
    requires_post_check: bool
    invocation_id: str
    run_id: str
    trade_date: str
    worker_name: str
    input_run_ids: Mapping[str, Any] = field(default_factory=dict)
    output_run_id: str | None = None
    completed_stages: Sequence[str] = field(default_factory=list)
    pending_stages: Sequence[str] = field(default_factory=list)
    partial_reason: str | None = None
    output_run_ids: Mapping[str, Any] = field(default_factory=dict)
    rollback_artifacts: Mapping[str, Any] = field(default_factory=dict)
    downstream_consumption_allowed: bool = False
    git_sha: str | None = None
    config_hash: str | None = None
    processed_count: int = 0
    written_count: int = 0
    skipped_count: int = 0
    blocked_count: int = 0
    external_side_effects: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_status_invariant(self.result, self.requires_post_check)
        if self.result == BoundedResult.PARTIAL:
            _validate_partial_status(self)

    def to_dict(self) -> dict[str, Any]:
        side_effects = _default_external_side_effects()
        side_effects.update(dict(self.external_side_effects))
        return {
            "result": self.result,
            "stop_reason": self.stop_reason,
            "requires_post_check": self.requires_post_check,
            "invocation_id": self.invocation_id,
            "run_id": self.run_id,
            "trade_date": self.trade_date,
            "worker_name": self.worker_name,
            "input_run_ids": dict(self.input_run_ids),
            "output_run_id": self.output_run_id,
            "completed_stages": list(self.completed_stages),
            "pending_stages": list(self.pending_stages),
            "partial_reason": self.partial_reason,
            "output_run_ids": dict(self.output_run_ids),
            "rollback_artifacts": dict(self.rollback_artifacts),
            "downstream_consumption_allowed": self.downstream_consumption_allowed,
            "git_sha": self.git_sha,
            "config_hash": self.config_hash,
            "processed_count": self.processed_count,
            "written_count": self.written_count,
            "skipped_count": self.skipped_count,
            "blocked_count": self.blocked_count,
            "external_side_effects": side_effects,
        }


@contextmanager
def acquire_global_chain_lock(
    lock_path: str | Path,
    metadata: Mapping[str, Any] | None = None,
) -> Iterator[Any]:
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = path.open("a+", encoding="utf-8")
    acquired = False
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise SingletonLockHeld("singleton_lock_held") from exc
            raise

        payload = dict(metadata or {})
        payload.setdefault("pid", os.getpid())
        payload.setdefault("acquired_at", datetime.now(timezone.utc).isoformat())
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        lock_file.write("\n")
        lock_file.flush()
        os.fsync(lock_file.fileno())
        yield lock_file
    finally:
        if acquired:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def check_stop_file(stop_file: str | Path | None) -> tuple[bool, str | None]:
    if stop_file is None:
        return False, None
    if Path(stop_file).exists():
        return True, "stop_file_present"
    return False, None


def deadline_from_now(
    max_runtime_seconds: float | int | None,
    now: datetime | None = None,
) -> datetime | None:
    if max_runtime_seconds is None:
        return None
    base = _as_utc(now or datetime.now(timezone.utc))
    return base + timedelta(seconds=float(max_runtime_seconds))


def remaining_deadline_seconds(
    deadline: datetime | None,
    now: datetime | None = None,
) -> float | None:
    if deadline is None:
        return None
    current = _as_utc(now or datetime.now(timezone.utc))
    return max(0.0, (_as_utc(deadline) - current).total_seconds())


def run_child_with_timeout(
    argv: Sequence[str],
    timeout_seconds: float | int | None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    command = [str(part) for part in argv]
    popen_kwargs: dict[str, Any] = {
        "cwd": str(cwd) if cwd is not None else None,
        "env": dict(env) if env is not None else None,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        sigterm_sent = _send_child_signal(process, signal.SIGTERM)
        sigkill_sent = False
        try:
            stdout, stderr = process.communicate(timeout=_TIMEOUT_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            sigkill_sent = _send_child_signal(process, getattr(signal, "SIGKILL", signal.SIGTERM))
            stdout, stderr = process.communicate()
        result = BoundedResult.UNKNOWN_AFTER_TIMEOUT
        return {
            "result": result,
            "returncode": process.returncode,
            "exit_code": result_to_exit_code(result),
            "requires_post_check": True,
            "timed_out": True,
            "argv": command,
            "stdout": _normalize_output(stdout if stdout is not None else exc.stdout),
            "stderr": _normalize_output(stderr if stderr is not None else exc.stderr),
            "timeout_sigterm_sent": sigterm_sent,
            "timeout_sigkill_sent": sigkill_sent,
        }

    result = BoundedResult.PASS if process.returncode == 0 else BoundedResult.CRASHED
    return {
        "result": result,
        "returncode": process.returncode,
        "exit_code": result_to_exit_code(result),
        "requires_post_check": False,
        "timed_out": False,
        "argv": command,
        "stdout": stdout,
        "stderr": stderr,
        "timeout_sigterm_sent": False,
        "timeout_sigkill_sent": False,
    }


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp.{os.getpid()}.{build_invocation_id()}")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        _fsync_parent_dir(target)
    finally:
        if tmp.exists():
            tmp.unlink()


def result_to_exit_code(result: str) -> int:
    try:
        return _RESULT_EXIT_CODES[result]
    except KeyError as exc:
        raise ValueError(f"unknown bounded worker result: {result}") from exc


def _validate_run_id_prefix(prefix: str) -> str:
    if not isinstance(prefix, str) or not prefix:
        raise ValueError("prefix is required")
    if not _SAFE_RUN_ID_PREFIX.fullmatch(prefix):
        raise ValueError("prefix must use 1-64 ASCII letters, digits, underscores, or hyphens")
    return prefix


def _validate_trade_date(trade_date: str) -> str:
    if not isinstance(trade_date, str) or not trade_date:
        raise ValueError("trade_date is required")
    if not _TRADE_DATE.fullmatch(trade_date):
        raise ValueError("trade_date must be YYYYMMDD")
    try:
        datetime.strptime(trade_date, "%Y%m%d")
    except ValueError as exc:
        raise ValueError("trade_date must be a real calendar date") from exc
    return trade_date


def _normalize_invocation_id(invocation_id: str) -> str:
    try:
        return uuid.UUID(str(invocation_id)).hex
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("invocation_id must be a UUID hex or canonical UUID string") from exc


def _validate_status_invariant(result: str, requires_post_check: bool) -> None:
    if not isinstance(requires_post_check, bool):
        raise ValueError("requires_post_check must be bool")
    try:
        expected = _STATUS_REQUIRES_POST_CHECK[result]
    except KeyError as exc:
        raise ValueError(f"unknown bounded worker result: {result}") from exc
    if requires_post_check != expected:
        raise ValueError(
            f"{result} requires requires_post_check={str(expected).lower()}"
        )


def _validate_partial_status(status: BoundedWorkerStatus) -> None:
    completed = _validate_stage_list("completed_stages", status.completed_stages)
    pending = _validate_stage_list("pending_stages", status.pending_stages)
    overlap = set(completed) & set(pending)
    if overlap:
        raise ValueError("completed_stages and pending_stages must not overlap")
    if not isinstance(status.partial_reason, str) or not status.partial_reason.strip():
        raise ValueError("partial_reason is required for PARTIAL")
    _validate_non_empty_mapping("output_run_ids", status.output_run_ids)
    _validate_non_empty_mapping("rollback_artifacts", status.rollback_artifacts)
    if status.downstream_consumption_allowed is not False:
        raise ValueError("PARTIAL requires downstream_consumption_allowed=false")


def _validate_stage_list(name: str, stages: Sequence[str]) -> list[str]:
    if isinstance(stages, (str, bytes)) or not isinstance(stages, SequenceABC):
        raise ValueError(f"{name} must be a list of stage names")
    values = list(stages)
    if not values:
        raise ValueError(f"{name} is required for PARTIAL")
    for stage in values:
        if not isinstance(stage, str) or not stage.strip():
            raise ValueError(f"{name} must contain non-empty stage names")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicate stage names")
    return values


def _validate_non_empty_mapping(name: str, value: Mapping[str, Any]) -> None:
    if not isinstance(value, MappingABC):
        raise ValueError(f"{name} must be a mapping")
    if not value:
        raise ValueError(f"{name} is required for PARTIAL")


def _send_child_signal(process: subprocess.Popen[str], signum: int) -> bool:
    if process.poll() is not None:
        return False
    try:
        if os.name == "posix":
            os.killpg(process.pid, signum)
        elif signum == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
        return True
    except ProcessLookupError:
        return False
    except OSError:
        if process.poll() is not None:
            return False
        raise


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _fsync_parent_dir(path: Path) -> None:
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


__all__ = [
    "BoundedResult",
    "BoundedWorkerConfig",
    "BoundedWorkerStatus",
    "SingletonLockHeld",
    "acquire_global_chain_lock",
    "atomic_write_json",
    "build_invocation_id",
    "build_phase1_realtime_chain_lock_path",
    "build_run_id",
    "check_stop_file",
    "deadline_from_now",
    "remaining_deadline_seconds",
    "result_to_exit_code",
    "run_child_with_timeout",
]
