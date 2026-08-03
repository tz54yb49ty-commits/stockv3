#!/usr/bin/env python3
"""Refresh the runtime-deferred N5/N3T policy review from canonical evidence."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from ashare_v3.runtime_control.n5_n3t_fastlane import (
    FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_DEFERRED_AUTHORIZATION_TIMING,
    FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_PATH_POLICY_TYPE,
    classify_fastlane_policy_review_auto_refresh,
    default_fastlane_stable_activation_config_path,
    load_fastlane_activation_config,
    write_fastlane_active_worker_policy_review_atomic,
)
from review_n5_n3t_fastlane_trading_day_monitor import (
    build_arg_parser as build_monitor_arg_parser,
    build_monitor_report,
)


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
SAFE_VALUE_ERROR_CODES = frozenset(
    {
        "ASHARE_V3_POSTGRES_DSN_missing",
        "active_worker_policy_review_path_missing",
        "active_worker_policy_review_path_policy_mismatch",
        "expected_json_object",
    }
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh N5/N3T runtime-deferred policy review after 09:25."
    )
    parser.add_argument(
        "--activation-config",
        default=default_fastlane_stable_activation_config_path(),
    )
    parser.add_argument("--launchagents-dir", default=str(Path.home() / "Library" / "LaunchAgents"))
    parser.add_argument("--log-dir", default="tmp")
    parser.add_argument("--scheduler-quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def run_policy_review_auto_refresh_once(
    *,
    activation_config_path: Path,
    current_exchange_time: str,
    launchagents_dir: Path,
    log_dir: Path,
    dsn: str,
    calendar_reader: Callable[..., bool] | None = None,
    monitor_report_builder: Callable[[argparse.Namespace], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = load_fastlane_activation_config(activation_config_path)
    for_trade_date = str(config.get("for_trade_date") or "")
    review_path_text = str(config.get("active_worker_policy_review_path") or "").strip()
    path_policy = config.get("active_worker_policy_review_path_policy") or {}
    if not review_path_text:
        raise ValueError("active_worker_policy_review_path_missing")
    if not isinstance(path_policy, Mapping) or (
        path_policy.get("policy_type") != FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_PATH_POLICY_TYPE
        or path_policy.get("authorization_timing")
        != FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_DEFERRED_AUTHORIZATION_TIMING
    ):
        raise ValueError("active_worker_policy_review_path_policy_mismatch")

    review_path = Path(review_path_text)
    existing_review = _read_json_object(review_path) if review_path.exists() else {}
    decision = classify_fastlane_policy_review_auto_refresh(
        for_trade_date=for_trade_date,
        current_exchange_time=current_exchange_time,
        existing_review=existing_review,
    )
    base_report = {
        "artifact_type": "n5_n3t_policy_review_auto_refresh_report_v1",
        "for_trade_date": for_trade_date,
        "current_exchange_time": current_exchange_time,
        "activation_config_path": str(activation_config_path),
        "active_worker_policy_review_path": str(review_path),
        "decision": decision,
        "boundary": {
            "db_written": False,
            "read_only_db_queries": False,
            "business_runtime_executed": False,
            "n4_outbox_updated": False,
            "n5_outbox_updated": False,
            "inbox_checkpoint_written": False,
            "launchd_touched": False,
            "stable_config_modified": False,
            "n6_touched": False,
        },
    }
    action = str(decision["action"])
    if action.startswith("NOOP_"):
        return {
            **base_report,
            "result": "NOOP",
            "final_verdict": f"N5_N3T_POLICY_REVIEW_AUTO_REFRESH_{action}",
            "policy_review_written": False,
        }
    if action != "REFRESH_REQUIRED":
        return {
            **base_report,
            "result": "BLOCKED",
            "final_verdict": "BLOCKED_N5_N3T_POLICY_REVIEW_AUTO_REFRESH_STALE_CONFIG",
            "policy_review_written": False,
        }
    if not str(dsn or "").strip():
        raise ValueError("ASHARE_V3_POSTGRES_DSN_missing")

    calendar_reader = calendar_reader or _read_trade_calendar_is_open
    monitor_report_builder = monitor_report_builder or build_monitor_report
    trade_calendar_is_open = bool(calendar_reader(dsn=dsn, for_trade_date=for_trade_date))
    base_report["boundary"]["read_only_db_queries"] = True
    if not trade_calendar_is_open:
        return {
            **base_report,
            "result": "BLOCKED",
            "final_verdict": "BLOCKED_N5_N3T_POLICY_REVIEW_AUTO_REFRESH_TRADE_DATE_NOT_OPEN",
            "policy_review_written": False,
        }

    monitor_args = build_monitor_arg_parser().parse_args(
        [
            "--for-trade-date",
            for_trade_date,
            "--current-exchange-time",
            current_exchange_time,
            "--launchagents-dir",
            str(launchagents_dir),
            "--log-dir",
            str(log_dir),
            "--dsn",
            dsn,
            "--n5-active-scope-artifact-dir",
            str(config.get("n5_active_scope_artifact_dir") or ""),
            "--n3-c1-n3t-artifact-dir",
            str(config.get("n3_c1_n3t_artifact_dir") or ""),
            "--trade-calendar-is-open",
            "true",
        ]
    )
    monitor_report = monitor_report_builder(monitor_args)
    candidate = monitor_report.get("active_worker_policy_review") or {}
    atomic_write = write_fastlane_active_worker_policy_review_atomic(
        policy_review_path=review_path,
        review=candidate,
        expected_for_trade_date=for_trade_date,
    )
    review_result = str(candidate.get("result") or "BLOCKED")
    return {
        **base_report,
        "result": review_result,
        "final_verdict": {
            "PASS": "N5_N3T_POLICY_REVIEW_AUTO_REFRESH_PASS_ACTIVE_WORKERS_READY",
            "WAITING": "WAITING_N5_N3T_POLICY_REVIEW_AUTO_REFRESH",
            "BLOCKED": "BLOCKED_N5_N3T_POLICY_REVIEW_AUTO_REFRESH_CONTRACT",
        }.get(review_result, "BLOCKED_N5_N3T_POLICY_REVIEW_AUTO_REFRESH_CONTRACT"),
        "policy_review_written": True,
        "policy_review": {
            "result": review_result,
            "session_phase": candidate.get("session_phase"),
            "active_worker_write_enabled_ready": candidate.get(
                "active_worker_write_enabled_ready"
            ),
            "activation_scope": candidate.get("activation_scope"),
            "waiting_reasons": list(candidate.get("waiting_reasons") or []),
            "blockers": list(candidate.get("blockers") or []),
        },
        "atomic_write": atomic_write,
    }


def _read_trade_calendar_is_open(*, dsn: str, for_trade_date: str) -> bool:
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - surfaced by the CLI
        raise RuntimeError("psycopg_required") from exc
    with psycopg.connect(
        dsn,
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    ) as conn:
        conn.execute("BEGIN READ ONLY")
        row = conn.execute(
            "SELECT is_open FROM common_trade_calendar WHERE trade_date = %s",
            (str(for_trade_date),),
        ).fetchone()
    if not row:
        raise RuntimeError("trade_calendar_row_missing")
    return bool(row[0])


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected_json_object")
    return payload


def _exchange_now_iso() -> str:
    return datetime.now(SHANGHAI_TZ).replace(microsecond=0).isoformat()


def _compact_report(report: Mapping[str, Any]) -> dict[str, Any]:
    policy_review = report.get("policy_review") or {}
    return {
        "result": report.get("result"),
        "final_verdict": report.get("final_verdict"),
        "blocked_reason": report.get("blocked_reason"),
        "for_trade_date": report.get("for_trade_date"),
        "current_exchange_time": report.get("current_exchange_time"),
        "policy_review_written": report.get("policy_review_written"),
        "session_phase": policy_review.get("session_phase") if isinstance(policy_review, Mapping) else None,
        "active_worker_write_enabled_ready": (
            policy_review.get("active_worker_write_enabled_ready")
            if isinstance(policy_review, Mapping)
            else None
        ),
        "activation_scope": policy_review.get("activation_scope") if isinstance(policy_review, Mapping) else None,
    }


def _safe_failure_code(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, ValueError) and message in SAFE_VALUE_ERROR_CODES:
        return message
    return type(exc).__name__


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        report = run_policy_review_auto_refresh_once(
            activation_config_path=Path(args.activation_config),
            current_exchange_time=_exchange_now_iso(),
            launchagents_dir=Path(args.launchagents_dir),
            log_dir=Path(args.log_dir),
            dsn=str(os.environ.get("ASHARE_V3_POSTGRES_DSN") or ""),
        )
    except Exception as exc:
        report = {
            "result": "BLOCKED",
            "final_verdict": "BLOCKED_N5_N3T_POLICY_REVIEW_AUTO_REFRESH_CONTRACT",
            "blocked_reason": f"policy_review_auto_refresh_failed:{_safe_failure_code(exc)}",
            "policy_review_written": False,
        }

    if not (args.scheduler_quiet and report.get("result") == "NOOP"):
        payload = _compact_report(report) if args.scheduler_quiet else report
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 2 if report.get("result") == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
