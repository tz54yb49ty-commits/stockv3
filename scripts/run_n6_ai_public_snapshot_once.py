#!/usr/bin/env python3
"""Publish one sanitized public AI-account snapshot for the research room."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import stat
from typing import Any, MutableMapping

import psycopg
from psycopg.rows import dict_row

from ashare_v3.user.ai_agent import AI_AGENT_SERVICE
from ashare_v3.user.ai_research_bridge import (
    AI_PUBLIC_SNAPSHOT_RELATIVE_PATH,
    validate_public_ai_snapshot,
)
from ashare_v3.web.n6_app_v1 import app_ai_agent_public_model


PUBLIC_SNAPSHOT_FEATURE_FLAG = (
    "ASHARE_V3_N6_AI_PUBLIC_SNAPSHOT_ENABLED"
)
PUBLIC_SNAPSHOT_FILE_ENV = "ASHARE_V3_N6_AI_PUBLIC_SNAPSHOT_FILE"
PUBLIC_SNAPSHOT_ROOT = Path(
    "/Users/chuanfuchen/Documents/Obsidian Vault/A股监控系统v3"
)
PUBLIC_SNAPSHOT_PATH = (
    PUBLIC_SNAPSHOT_ROOT / AI_PUBLIC_SNAPSHOT_RELATIVE_PATH
)
PUBLIC_SNAPSHOT_QUERY = (
    "SELECT public.n6_btrack_ai_public_snapshot("
    "repeat('0',64),50,50,30) AS payload"
)
PUBLIC_SNAPSHOT_IDENTITY_QUERY = (
    "SELECT SESSION_USER AS session_user, "
    "CURRENT_USER AS current_user"
)
MAX_PUBLIC_SNAPSHOT_BYTES = 2_000_000
_FORBIDDEN_ENV_KEYS = frozenset(
    {
        "PGPASSWORD",
        "DATABASE_URL",
        "ASHARE_V3_POSTGRES_DSN",
        "ASHARE_V3_N6_AI_AGENT_DSN",
        "OPENAI_API_KEY",
        "ASHARE_V3_OPENAI_API_KEY",
    }
)


def scrub_inherited_forbidden_environment(
    environment: MutableMapping[str, str],
) -> tuple[str, ...]:
    """Remove launchd-global secrets before publisher validation/connect."""

    removed = []
    for key in sorted(_FORBIDDEN_ENV_KEYS):
        if key in environment:
            environment.pop(key)
            removed.append(key)
    return tuple(removed)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    return parser


def _default_connection_factory():
    return psycopg.connect(
        f"service={AI_AGENT_SERVICE}",
        connect_timeout=10,
        autocommit=True,
        row_factory=dict_row,
        options=(
            "-c default_transaction_read_only=on "
            "-c statement_timeout=30000 "
            "-c lock_timeout=1000"
        ),
    )


def run_from_args(
    args: argparse.Namespace,
    *,
    environment: Mapping[str, str] | None = None,
    connection_factory: Callable[[], Any] | None = None,
    snapshot_root: Path = PUBLIC_SNAPSHOT_ROOT,
) -> dict[str, Any]:
    env = os.environ if environment is None else environment
    enabled = env.get(PUBLIC_SNAPSHOT_FEATURE_FLAG) == "1"
    if not args.execute:
        return {
            "ok": True,
            "status": "dry_run_preflight",
            "publisher_enabled": enabled,
            "db_connected": False,
            "snapshot_written": False,
        }
    if not enabled:
        return {
            "ok": True,
            "status": "feature_disabled",
            "publisher_enabled": False,
            "db_connected": False,
            "snapshot_written": False,
        }

    root = Path(snapshot_root)
    target = root / AI_PUBLIC_SNAPSHOT_RELATIVE_PATH
    try:
        _validate_environment(env, expected_target=target)
    except (OSError, ValueError):
        return _failed("publisher_environment_invalid")

    factory = connection_factory or _default_connection_factory
    try:
        connection = factory()
    except Exception:
        return _failed("publisher_database_unavailable")
    try:
        raw_snapshot = _read_public_snapshot(connection)
        if not isinstance(raw_snapshot, dict):
            return _failed(
                "public_snapshot_authority_unavailable",
                db_connected=True,
            )
        public_model = app_ai_agent_public_model(raw_snapshot)
        sanitized = validate_public_ai_snapshot(public_model)
        payload = (
            json.dumps(
                sanitized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        if len(payload) > MAX_PUBLIC_SNAPSHOT_BYTES:
            return _failed(
                "public_snapshot_too_large",
                db_connected=True,
            )
        _atomic_write_public_snapshot(root, payload)
    except Exception:
        return _failed(
            "public_snapshot_publish_failed",
            db_connected=True,
        )
    finally:
        try:
            connection.close()
        except Exception:
            pass

    return {
        "ok": True,
        "status": "published",
        "publisher_enabled": True,
        "db_connected": True,
        "snapshot_written": True,
        "snapshot_sha256": sha256(payload).hexdigest(),
        "position_count": len(sanitized["positions"]),
        "trade_count": len(sanitized["trades"]),
        "decision_count": len(sanitized["decisions"]),
        "daily_summary_count": len(sanitized["daily_summaries"]),
    }


def _validate_environment(
    environment: Mapping[str, str],
    *,
    expected_target: Path,
) -> None:
    if environment.get("PGSERVICE") != AI_AGENT_SERVICE:
        raise ValueError("publisher_pgservice_invalid")
    if any(environment.get(key) for key in _FORBIDDEN_ENV_KEYS):
        raise ValueError("publisher_secret_environment_forbidden")
    service_file = _absolute_environment_path(
        environment, "PGSERVICEFILE", "pg_service.conf"
    )
    pass_file = _absolute_environment_path(
        environment, "PGPASSFILE", "n6_ai_agent.pgpass"
    )
    if service_file == pass_file:
        raise ValueError("publisher_credential_paths_not_distinct")
    _assert_owner_mode_regular(service_file, 0o600)
    _assert_owner_mode_regular(pass_file, 0o600)
    configured_target = Path(
        environment.get(PUBLIC_SNAPSHOT_FILE_ENV, "")
    )
    if (
        not configured_target.is_absolute()
        or configured_target != expected_target
    ):
        raise ValueError("publisher_snapshot_path_invalid")


def _absolute_environment_path(
    environment: Mapping[str, str],
    key: str,
    expected_name: str,
) -> Path:
    value = environment.get(key, "")
    path = Path(value)
    if (
        not value
        or not path.is_absolute()
        or path.name != expected_name
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        raise ValueError(f"{key.lower()}_invalid")
    return path


def _assert_owner_mode_regular(path: Path, mode: int) -> None:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        raise ValueError(f"{path.name}_authority_invalid")


def _read_public_snapshot(connection: Any) -> dict[str, Any] | None:
    cursor = connection.cursor()
    try:
        cursor.execute("BEGIN READ ONLY")
        cursor.execute("SHOW default_transaction_read_only")
        row = cursor.fetchone()
        if _first_column(row) != "on":
            raise RuntimeError("publisher_transaction_not_read_only")
        cursor.execute(PUBLIC_SNAPSHOT_IDENTITY_QUERY)
        identity = cursor.fetchone()
        if (
            _named_column(identity, "session_user")
            != AI_AGENT_SERVICE
            or _named_column(identity, "current_user")
            != AI_AGENT_SERVICE
        ):
            raise RuntimeError("publisher_database_identity_mismatch")
        cursor.execute(PUBLIC_SNAPSHOT_QUERY)
        result = cursor.fetchone()
        return _named_column(result, "payload")
    finally:
        try:
            cursor.execute("ROLLBACK")
        finally:
            cursor.close()


def _first_column(row: Any) -> Any:
    if isinstance(row, Mapping):
        return next(iter(row.values()), None)
    if isinstance(row, (tuple, list)):
        return row[0] if row else None
    return None


def _named_column(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    if isinstance(row, (tuple, list)):
        return row[0] if row else None
    return None


def _atomic_write_public_snapshot(root: Path, payload: bytes) -> None:
    parts = PurePosixPath(AI_PUBLIC_SNAPSHOT_RELATIVE_PATH).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("publisher_relative_path_invalid")
    directory_fd = _open_safe_directory_chain(root, parts[:-1])
    target_name = parts[-1]
    temporary_name = (
        f".{target_name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    temporary_fd: int | None = None
    try:
        _validate_existing_target(directory_fd, target_name)
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        os.fchmod(temporary_fd, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(temporary_fd, payload[offset:])
            if written <= 0:
                raise OSError("publisher_short_write")
            offset += written
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = None
        os.replace(
            temporary_name,
            target_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)


def _open_safe_directory_chain(
    root: Path,
    relative_directories: tuple[str, ...],
) -> int:
    current_fd = os.open(
        root,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        _assert_safe_directory_fd(current_fd)
        for part in relative_directories:
            next_fd = os.open(
                part,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
            _assert_safe_directory_fd(current_fd)
    except Exception:
        os.close(current_fd)
        raise
    return current_fd


def _assert_safe_directory_fd(directory_fd: int) -> None:
    metadata = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise ValueError("publisher_directory_authority_invalid")


def _validate_existing_target(
    directory_fd: int,
    target_name: str,
) -> None:
    try:
        target_fd = os.open(
            target_name,
            os.O_RDONLY
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_fd,
        )
    except FileNotFoundError:
        return
    try:
        metadata = os.fstat(target_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise ValueError("publisher_existing_target_invalid")
    finally:
        os.close(target_fd)


def _failed(
    reason: str,
    *,
    db_connected: bool = False,
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "failed_closed",
        "reason": reason,
        "publisher_enabled": True,
        "db_connected": db_connected,
        "snapshot_written": False,
    }


def main() -> int:
    scrub_inherited_forbidden_environment(os.environ)
    payload = run_from_args(build_parser().parse_args())
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    )
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
