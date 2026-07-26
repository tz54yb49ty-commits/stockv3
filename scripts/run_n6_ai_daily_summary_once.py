#!/usr/bin/env python3
"""Create at most one deterministic AI virtual-account summary per day."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from datetime import date, datetime
import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ashare_v3.user.ai_agent import (
    AI_AGENT_SERVICE,
    DAILY_SUMMARY_FEATURE_FLAG,
    DISPLAY_TIMEZONE,
    FunctionOnlyAIAgentRepository,
    feature_enabled,
    run_daily_summary_once,
    validate_agent_environment,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--for-trade-date",
        help="Current Asia/Shanghai date in YYYYMMDD form.",
    )
    parser.add_argument(
        "--run-at",
        help="Timezone-aware ISO-8601 time; defaults to Asia/Shanghai now.",
    )
    parser.add_argument("--execute", action="store_true")
    return parser


def _default_repository_factory():
    connection = psycopg.connect(
        f"service={AI_AGENT_SERVICE}",
        connect_timeout=10,
        row_factory=dict_row,
        autocommit=False,
    )
    return FunctionOnlyAIAgentRepository(connection), connection.close


def _parse_trade_date(value: str | None) -> date | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y%m%d").date()


def run_from_args(
    args: argparse.Namespace,
    *,
    environment: Mapping[str, str] | None = None,
    now_factory: Callable[[], datetime] | None = None,
    repository_factory: Callable[[], tuple[Any, Callable[[], None]]] | None = None,
) -> dict[str, Any]:
    env = os.environ if environment is None else environment
    enabled = feature_enabled(env, DAILY_SUMMARY_FEATURE_FLAG)
    if not args.execute:
        return {
            "ok": True,
            "status": "dry_run_preflight",
            "daily_summary_enabled": enabled,
            "db_connected": False,
            "summary_recorded": False,
        }
    if not enabled:
        return {
            "ok": True,
            "status": "feature_disabled",
            "reason": "daily_summary_feature_disabled",
            "db_connected": False,
            "summary_recorded": False,
        }
    validate_agent_environment(env)
    now_factory = now_factory or (
        lambda: datetime.now(DISPLAY_TIMEZONE)
    )
    run_at = (
        datetime.fromisoformat(args.run_at)
        if args.run_at
        else now_factory()
    )
    try:
        for_trade_date = _parse_trade_date(args.for_trade_date)
    except ValueError:
        return {
            "ok": False,
            "status": "failed_closed",
            "reason": "invalid_for_trade_date",
            "db_connected": False,
            "summary_recorded": False,
        }
    factory = repository_factory or _default_repository_factory
    repository, close = factory()
    try:
        return run_daily_summary_once(
            repository=repository,
            now=run_at,
            for_trade_date=for_trade_date,
            enabled=enabled,
        )
    finally:
        close()


def main() -> int:
    payload = run_from_args(build_parser().parse_args())
    print(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=str
        )
    )
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
