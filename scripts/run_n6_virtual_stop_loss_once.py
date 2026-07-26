#!/usr/bin/env python3
"""One freeze attempt and one evaluate attempt; never a resident worker."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os

import psycopg
from psycopg.rows import dict_row


EXECUTOR_SERVICE = "n6_virtual_executor"
ALLOWED_LIBPQ_ENV = frozenset({"PGSERVICE", "PGSERVICEFILE", "PGPASSFILE"})


def validate_executor_environment(environ: Mapping[str, str]) -> None:
    if environ.get("PGSERVICE") != EXECUTOR_SERVICE:
        raise ValueError("exact_PGSERVICE_n6_virtual_executor_required")
    for key in environ:
        upper = key.upper()
        if "PASSWORD" in upper or "DSN" in upper or upper.endswith("DATABASE_URL"):
            raise ValueError("dsn_or_password_environment_not_allowed")
        if upper.startswith("PG") and upper not in ALLOWED_LIBPQ_ENV:
            raise ValueError("libpq_environment_override_not_allowed")
    for key in ("PGSERVICEFILE", "PGPASSFILE"):
        value = environ.get(key)
        if value is not None and (not os.path.isabs(value) or any(c in value for c in "\x00\r\n")):
            raise ValueError(f"valid_{key}_path_required")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executor-run-id", required=True)
    parser.add_argument("--execute", action="store_true")
    return parser


def _call(cursor, function_name: str, run_id: str) -> dict[str, object]:
    cursor.execute(f"SELECT public.{function_name}(%s) AS result", (run_id,))
    row = cursor.fetchone()
    value = row["result"] if isinstance(row, Mapping) else row[0]
    if not isinstance(value, Mapping):
        raise RuntimeError("stop_loss_function_returned_invalid_payload")
    return dict(value)


def run_from_args(args: argparse.Namespace, *, connect=psycopg.connect) -> dict[str, object]:
    run_id = str(args.executor_run_id or "")
    if not run_id.strip() or len(run_id) > 200:
        raise ValueError("invalid_executor_run_id")
    if getattr(args, "dsn", None) is not None:
        raise ValueError("--dsn is not allowed")
    if not args.execute:
        return {"ok": True, "status": "read_only_preflight", "db_connected": False,
                "dml": False, "freeze_attempted": False, "evaluate_attempted": False}
    validate_executor_environment(os.environ)
    connection = connect(f"service={EXECUTOR_SERVICE}", row_factory=dict_row, autocommit=False)
    try:
        with connection.cursor() as cursor:
            freeze = _call(cursor, "n6_executor_freeze_next_stop_loss", run_id)
            evaluate = _call(cursor, "n6_executor_evaluate_next_stop_loss", run_id)
        connection.commit()
        return {"ok": bool(freeze.get("ok")) and bool(evaluate.get("ok")),
                "status": "completed", "freeze": freeze, "evaluate": evaluate}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> int:
    payload = run_from_args(build_parser().parse_args())
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
