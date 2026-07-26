#!/usr/bin/env python3
"""One Shadow-only N6 AI strategy-policy audit; never a resident worker."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from datetime import datetime, time
import json
import os
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ashare_v3.user.ai_agent import (
    AI_AGENT_SERVICE,
    DISPLAY_TIMEZONE,
    five_minute_bucket,
    validate_agent_environment,
)
from ashare_v3.user.ai_investor_strategy_policy_v1 import (
    KNOWLEDGE_BUNDLE_SHA256,
    KNOWLEDGE_BUNDLE_VERSION,
    POLICY_DOCUMENT_SHA256,
    POLICY_VERSION,
)


STRATEGY_POLICY_SHADOW_FEATURE_FLAG = (
    "ASHARE_V3_N6_AI_STRATEGY_POLICY_SHADOW_ENABLED"
)
STRATEGY_POLICY_SQL = (
    "SELECT public.n6_ai_strategy_shadow_evaluate(%s, %s, %s) AS result"
)
_MUTATION_FIELDS = (
    "proposal_created",
    "order_created",
    "trade_created",
    "position_mutated",
    "cash_mutated",
)
_EXPECTED_RESPONSE_IDENTITY = {
    "policy_version": POLICY_VERSION,
    "policy_document_sha256": POLICY_DOCUMENT_SHA256,
    "knowledge_bundle_version": KNOWLEDGE_BUNDLE_VERSION,
    "knowledge_bundle_sha256": KNOWLEDGE_BUNDLE_SHA256,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-at",
        help="Timezone-aware ISO-8601 time; defaults to Asia/Shanghai now.",
    )
    parser.add_argument(
        "--mode", choices=("shadow",), default="shadow"
    )
    parser.add_argument("--execute", action="store_true")
    return parser


def _default_connection_factory():
    return psycopg.connect(
        f"service={AI_AGENT_SERVICE}",
        connect_timeout=10,
        row_factory=dict_row,
        autocommit=False,
        options="-c statement_timeout=30000 -c lock_timeout=1000",
    )


def _base_result(status: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "status": status,
        "mode": "shadow",
        "db_connected": False,
        "model_called": False,
        "proposal_created": False,
        "order_created": False,
        "trade_created": False,
        "position_mutated": False,
        "cash_mutated": False,
        "execution_authorized": False,
        **extra,
    }


def _failed(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        **_base_result("failed_closed"),
        "ok": False,
        "reason": reason,
        **extra,
    }


def _parse_run_at(
    value: str | None, now_factory: Callable[[], datetime]
) -> datetime:
    run_at = datetime.fromisoformat(value) if value else now_factory()
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ValueError("timezone_aware_run_time_required")
    return run_at.astimezone(DISPLAY_TIMEZONE)


def _in_trading_session(value: datetime) -> bool:
    if value.weekday() >= 5:
        return False
    local_time = value.timetz().replace(tzinfo=None)
    return (
        time(9, 30) <= local_time <= time(11, 30)
        or time(13, 0) <= local_time <= time(15, 0)
    )


def _result_mapping(row: Any) -> Mapping[str, Any] | None:
    if isinstance(row, Mapping):
        value = row.get("result")
    elif isinstance(row, (tuple, list)) and len(row) == 1:
        value = row[0]
    else:
        return None
    return value if isinstance(value, Mapping) else None


def run_from_args(
    args: argparse.Namespace,
    *,
    environment: Mapping[str, str] | None = None,
    now_factory: Callable[[], datetime] | None = None,
    connection_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Run one hardened Shadow audit with no model or business-table DML."""

    env = os.environ if environment is None else environment
    if args.mode != "shadow":
        return _failed("invalid_strategy_mode")
    if not args.execute:
        return _base_result(
            "dry_run_preflight",
            feature_enabled=(
                str(
                    env.get(
                        STRATEGY_POLICY_SHADOW_FEATURE_FLAG
                    )
                    or ""
                )
                == "1"
            ),
        )
    if (
        str(env.get(STRATEGY_POLICY_SHADOW_FEATURE_FLAG) or "")
        != "1"
    ):
        return _base_result(
            "feature_disabled",
            reason="strategy_policy_shadow_feature_disabled",
        )
    try:
        run_at = _parse_run_at(
            args.run_at,
            now_factory
            or (lambda: datetime.now(DISPLAY_TIMEZONE)),
        )
    except (TypeError, ValueError):
        return _failed("invalid_run_time")
    if not _in_trading_session(run_at):
        return _base_result(
            "outside_trading_session",
            run_at=run_at.isoformat(),
        )
    try:
        validate_agent_environment(env)
    except ValueError:
        return _failed("agent_environment_invalid")

    factory = connection_factory or _default_connection_factory
    try:
        connection = factory()
    except Exception:
        return _failed("strategy_policy_service_unavailable")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                STRATEGY_POLICY_SQL,
                (
                    run_at.date(),
                    five_minute_bucket(run_at),
                    POLICY_DOCUMENT_SHA256,
                ),
            )
            result = _result_mapping(cursor.fetchone())
        if result is None:
            connection.rollback()
            return _failed(
                "strategy_policy_response_invalid",
                db_connected=True,
            )
        if (
            any(result.get(field) is not False for field in _MUTATION_FIELDS)
            or result.get("execution_authorized") is not False
        ):
            connection.rollback()
            return _failed(
                "shadow_mutation_contract_breach",
                db_connected=True,
            )
        if any(
            result.get(field) != expected
            for field, expected in _EXPECTED_RESPONSE_IDENTITY.items()
        ):
            connection.rollback()
            return _failed(
                "strategy_policy_identity_mismatch",
                db_connected=True,
            )
        if (
            result.get("ok") is not True
            or result.get("status")
            not in {
                "shadow_policy_evaluated",
                "not_open_trade_date",
            }
        ):
            connection.rollback()
            return _failed(
                "strategy_policy_evaluation_rejected",
                db_connected=True,
            )
        if result.get("status") == "not_open_trade_date":
            connection.rollback()
        else:
            workset_hash = result.get("strategy_workset_hash")
            if (
                not isinstance(workset_hash, str)
                or len(workset_hash) != 64
                or not set(workset_hash) <= set("0123456789abcdef")
            ):
                connection.rollback()
                return _failed(
                    "strategy_workset_hash_invalid",
                    db_connected=True,
                )
            connection.commit()
        safe_result = {
            key: value
            for key, value in result.items()
            if key
            in {
                "ok",
                "status",
                "candidate_rank_audit_count",
                "strategy_action_audit_count",
                "completed_strategy_episode_count",
                "strategy_workset_hash",
                "execution_authorized",
                *_MUTATION_FIELDS,
                *_EXPECTED_RESPONSE_IDENTITY,
            }
        }
        return {
            **_base_result(str(result["status"])),
            **safe_result,
            "db_connected": True,
            "run_bucket": five_minute_bucket(run_at),
            "policy_document_sha256": POLICY_DOCUMENT_SHA256,
        }
    except Exception:
        connection.rollback()
        return _failed(
            "strategy_policy_service_unavailable",
            db_connected=True,
        )
    finally:
        connection.close()


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
