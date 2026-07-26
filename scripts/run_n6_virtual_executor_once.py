#!/usr/bin/env python3
"""KeepAlive=false one-shot entrypoint for the N6 virtual executor."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os

import psycopg
from psycopg.rows import dict_row

from ashare_v3.user.virtual_executor import (
    VirtualExecutorRequest,
    execute_proposal,
)


EXECUTOR_SERVICE = "n6_virtual_executor"
ALLOWED_LIBPQ_ENV = frozenset({"PGSERVICE", "PGSERVICEFILE", "PGPASSFILE"})
FORBIDDEN_CONNECTION_ENV = frozenset(
    {
        "DATABASE_URL",
        "PG_DSN",
        "POSTGRES_DSN",
        "ASHARE_V3_POSTGRES_DSN",
        "ASHARE_V3_RUNTIME_DATABASE_URL",
        "ASHARE_V3_N6_VIRTUAL_EXECUTOR_DSN",
        "ASHARE_V3_N6_VIRTUAL_EXECUTOR_PASSWORD",
    }
)


def validate_executor_environment(environ: Mapping[str, str]) -> None:
    if environ.get("PGSERVICE") != EXECUTOR_SERVICE:
        raise ValueError("exact_PGSERVICE_n6_virtual_executor_required")
    if "PGPASSWORD" in environ:
        raise ValueError("PGPASSWORD_not_allowed")
    if any(key in environ for key in FORBIDDEN_CONNECTION_ENV) or any(
        "DSN" in key.upper()
        or "PASSWORD" in key.upper()
        or key.upper().endswith("DATABASE_URL")
        for key in environ
    ):
        raise ValueError("custom_DSN_or_password_configuration_not_allowed")
    if any(key.startswith("PG") and key not in ALLOWED_LIBPQ_ENV for key in environ):
        raise ValueError("libpq_environment_override_not_allowed")
    for key in ("PGSERVICEFILE", "PGPASSFILE"):
        path = environ.get(key)
        if (
            not path
            or not os.path.isabs(path)
            or "\x00" in path
            or "\n" in path
            or "\r" in path
        ):
            raise ValueError(f"valid_{key}_path_required")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal-id", type=int)
    parser.add_argument("--executor-run-id", required=True)
    parser.add_argument("--execute", action="store_true")
    return parser


def run_from_args(
    args: argparse.Namespace,
    *,
    connect=psycopg.connect,
) -> dict[str, object]:
    request = VirtualExecutorRequest(args.proposal_id, args.executor_run_id)
    if getattr(args, "dsn", None) is not None:
        raise ValueError("--dsn is not allowed")
    if not args.execute:
        return {
            "ok": True,
            "status": "read_only_preflight",
            "claim_called": False,
            "dml": False,
            "proposal_id": request.proposal_id,
            "claim_mode": "explicit_canary" if request.proposal_id else "claim_next",
            "executor_run_id": request.executor_run_id,
        }
    validate_executor_environment(os.environ)
    connection = connect(
        f"service={EXECUTOR_SERVICE}",
        row_factory=dict_row,
        autocommit=False,
    )
    try:
        return execute_proposal(connection, request)
    finally:
        connection.close()


def main() -> int:
    payload = run_from_args(build_parser().parse_args())
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return (
        0
        if payload.get("ok") or payload.get("status") == "no_claimable_proposal"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
