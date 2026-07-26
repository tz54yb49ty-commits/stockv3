#!/usr/bin/env python3
"""Explicit one-shot entrypoint for N6 virtual-position quote persistence."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import errno
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Callable, ContextManager, Iterator, Mapping
from zoneinfo import ZoneInfo

import psycopg

from ashare_v3.user.n6_virtual_quote_client import build_n6_virtual_quote_provider
from ashare_v3.user.virtual_quote_persistence import (
    PostgresVirtualQuoteRepository,
    run_virtual_quote_all_active_accounts_once,
)


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
MORNING_START = (9, 30)
MORNING_END = (11, 30)
AFTERNOON_START = (13, 0)
AFTERNOON_END = (15, 0)
QUOTE_WRITER_SERVICE = "n6_quote_writer"
QUOTE_WRITER_CONNINFO = f"service={QUOTE_WRITER_SERVICE}"
SCHEDULER_CADENCE_SECONDS = 5
FORBIDDEN_CONNECTION_ENV = frozenset(
    {
        "PGPASSWORD", "PGUSER", "PGHOST", "PGPORT", "PGDATABASE", "PGOPTIONS",
        "ASHARE_V3_POSTGRES_DSN", "N6_QUOTE_DSN", "N6_QUOTE_PASSWORD",
        "N6_QUOTE_WRITER_DSN", "N6_QUOTE_WRITER_PASSWORD",
    }
)


class ScheduledLockHeld(RuntimeError):
    """Another scheduled invocation currently owns the global quote lock."""


def scheduled_lock_path() -> Path:
    return Path("/tmp/ashare_v3_n6_virtual_quote.lock")


def scheduled_quote_minute(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduled time must be timezone-aware")
    return value.astimezone(ASIA_SHANGHAI).replace(second=0, microsecond=0)


def is_trading_session(value: datetime) -> bool:
    minute = scheduled_quote_minute(value)
    current = (minute.hour, minute.minute)
    return MORNING_START <= current <= MORNING_END or AFTERNOON_START <= current <= AFTERNOON_END


def quote_writer_conninfo(environ: Mapping[str, str]) -> str:
    service = str(environ.get("PGSERVICE") or "")
    if service != QUOTE_WRITER_SERVICE:
        raise ValueError("PGSERVICE must be exactly n6_quote_writer")
    forbidden = sorted(
        name
        for name in environ
        if name in FORBIDDEN_CONNECTION_ENV
        or (
            "QUOTE" in name.upper()
            and any(part in name.upper() for part in ("DSN", "PASSWORD", "SECRET"))
        )
    )
    if forbidden:
        raise ValueError("direct PostgreSQL connection overrides are forbidden")
    _validate_private_connection_file(environ, "PGSERVICEFILE")
    _validate_private_connection_file(environ, "PGPASSFILE")
    return QUOTE_WRITER_CONNINFO


def _validate_private_connection_file(
    environ: Mapping[str, str], name: str
) -> None:
    value = str(environ.get(name) or "")
    path = Path(value)
    if not value or not path.is_absolute():
        raise ValueError(f"{name} must be an absolute private file")
    try:
        metadata = path.stat()
    except OSError as exc:
        raise ValueError(f"{name} must be an existing private file") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise ValueError(f"{name} owner/mode must be current-user/0600")


def is_open_trade_date(conninfo: str, quote_minute: datetime) -> bool:
    trade_date = scheduled_quote_minute(quote_minute).strftime("%Y%m%d")
    with psycopg.connect(
        conninfo,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    ) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT public.n6_quote_writer_is_open_trade_date(%s)
            """,
            (trade_date,),
        )
        return bool(cur.fetchone()[0])


@contextmanager
def acquire_scheduled_lock(path: Path) -> Iterator[None]:
    handle = path.open("a+", encoding="utf-8")
    acquired = False
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise ScheduledLockHeld("scheduled_lock_held") from exc
            raise
        yield
    finally:
        try:
            if acquired:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _no_op(reason: str, quote_minute: datetime) -> tuple[int, dict[str, object]]:
    return 0, {
        "status": "no_op",
        "reason": reason,
        "quote_minute": quote_minute.isoformat(),
    }


def _run_quote_once(
    *,
    repository: object,
    provider: object,
    quote_minute: datetime,
):
    return run_virtual_quote_all_active_accounts_once(
        repository=repository,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
        quote_minute=quote_minute,
    )


def run_from_args(
    args: argparse.Namespace,
    *,
    now_factory: Callable[[], datetime] | None = None,
    trade_date_checker: Callable[[str, datetime], bool] = is_open_trade_date,
    lock_acquirer: Callable[[Path], ContextManager[None]] = acquire_scheduled_lock,
    repository_factory: Callable[[str], object] = PostgresVirtualQuoteRepository,
    provider_factory: Callable[[], object] | None = None,
    environment: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    provider_factory = provider_factory or build_n6_virtual_quote_provider
    now_factory = now_factory or (lambda: datetime.now(ASIA_SHANGHAI))
    conninfo = quote_writer_conninfo(os.environ if environment is None else environment)

    raw_time = (
        datetime.fromisoformat(args.quote_minute)
        if args.quote_minute
        else now_factory()
    )
    quote_minute = scheduled_quote_minute(raw_time)
    current_minute = scheduled_quote_minute(now_factory())
    if quote_minute != current_minute:
        return _no_op("not_current_quote_minute", quote_minute)
    if not is_trading_session(quote_minute):
        return _no_op("outside_trading_session", quote_minute)
    if not trade_date_checker(conninfo, quote_minute):
        return _no_op("closed_trade_date", quote_minute)
    try:
        with lock_acquirer(scheduled_lock_path()):
            repository = repository_factory(conninfo)
            provider = provider_factory()
            result = _run_quote_once(
                repository=repository,
                provider=provider,
                quote_minute=quote_minute,
            )
    except ScheduledLockHeld:
        return _no_op("scheduled_lock_held", quote_minute)

    payload = result.to_dict()
    return (0 if result.status in {"passed", "partial", "no_scope"} else 2), payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quote-minute",
        help="Timezone-aware, minute-aligned ISO-8601 timestamp; defaults to local current minute.",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--scheduled", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.execute:
        raise SystemExit("blocked: --execute is required")
    exit_code, payload = run_from_args(args)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
