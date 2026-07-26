#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os

from ashare_v3.user.strategy_center_worker import (
    PostgresStrategyCenterEvaluatorRepository,
    StrategyEvaluatorScope,
    run_strategy_center_once,
)


WORKER_SERVICE = "n6_strategy_worker"
ALLOWED_LIBPQ_ENV = frozenset({"PGSERVICE", "PGSERVICEFILE", "PGPASSFILE"})
FORBIDDEN_CONNECTION_ENV = frozenset(
    {
        "DATABASE_URL",
        "PG_DSN",
        "POSTGRES_DSN",
        "ASHARE_V3_POSTGRES_DSN",
        "ASHARE_V3_RUNTIME_DATABASE_URL",
        "PGPASSWORD",
    }
)


def validate_worker_environment(environ: Mapping[str, str]) -> None:
    if environ.get("PGSERVICE") != WORKER_SERVICE:
        raise ValueError("exact_PGSERVICE_n6_strategy_worker_required")
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


def strict_positive_int(value: object) -> int:
    if isinstance(value, bool):
        raise argparse.ArgumentTypeError("strict_positive_integer_required")
    text = str(value)
    if not text.isascii() or not text.isdigit() or not text or text.startswith("0"):
        raise argparse.ArgumentTypeError("strict_positive_integer_required")
    parsed = int(text)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("strict_positive_integer_required")
    return parsed


def evaluator_scope_from_args(
    args: argparse.Namespace,
) -> StrategyEvaluatorScope | None:
    values = (
        args.principal_id,
        args.user_id,
        args.selection_revision_id,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("strategy_evaluator_scope_all_or_none_required")
    return StrategyEvaluatorScope(
        principal_id=args.principal_id,
        user_id=args.user_id,
        selection_revision_id=args.selection_revision_id,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the display-only N6 strategy-center evaluator once."
    )
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--evaluator-run-id", required=True)
    parser.add_argument("--principal-id", type=strict_positive_int)
    parser.add_argument("--user-id", type=strict_positive_int)
    parser.add_argument("--selection-revision-id", type=strict_positive_int)
    parser.add_argument(
        "--evaluation-time",
        help=(
            "Frozen evaluation instant from the dry-run, as an ISO-8601 "
            "Asia/Shanghai timestamp (for primary/replay)."
        ),
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--runtime-authorized", action="store_true")
    return parser


def run_from_args(args: argparse.Namespace) -> dict[str, object]:
    scope = evaluator_scope_from_args(args)
    validate_worker_environment(os.environ)
    repository = PostgresStrategyCenterEvaluatorRepository(
        f"service={WORKER_SERVICE}"
    )
    return run_strategy_center_once(
        repository=repository,
        trade_date=args.trade_date,
        evaluator_run_id=args.evaluator_run_id,
        execute=bool(args.execute),
        runtime_authorized=bool(args.runtime_authorized),
        scope=scope,
        evaluation_time=args.evaluation_time,
    )


def main() -> int:
    payload = run_from_args(build_parser().parse_args())
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
