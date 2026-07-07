#!/usr/bin/env python3
"""Generate local launchd plan artifacts for the N5/N3T fastlane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from ashare_v3.runtime_control.n5_n3t_fastlane import (
    DEFAULT_PYTHON_EXECUTABLE,
    build_fastlane_activation_guard,
    build_fastlane_write_enabled_activation_config_full_chain_preflight,
    write_fastlane_write_enabled_activation_config,
    write_fastlane_active_launchd_plan,
    write_fastlane_launchd_plan,
    write_fastlane_post_close_readiness_config_rollover,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate local N5/N3T fastlane launchd plan artifacts.")
    parser.add_argument("--output-dir", default="tmp/N5_N3T_action_confirmation_fastlane_launchd_plan")
    parser.add_argument("--working-directory", default=str(Path.cwd()))
    parser.add_argument("--python-executable", default=DEFAULT_PYTHON_EXECUTABLE)
    parser.add_argument("--activation-guard")
    parser.add_argument("--activation-config")
    parser.add_argument("--for-trade-date")
    parser.add_argument("--dsn")
    parser.add_argument("--current-exchange-time", default="")
    parser.add_argument("--active-plan", action="store_true")
    parser.add_argument("--write-enabled-activation-config", action="store_true")
    parser.add_argument("--post-close-readiness-config-rollover", action="store_true")
    parser.add_argument("--full-chain-activation-preflight", action="store_true")
    parser.add_argument("--require-full-chain-activation", action="store_true")
    parser.add_argument("--defer-active-worker-policy-review-to-runtime", action="store_true")
    parser.add_argument("--base-activation-config")
    parser.add_argument("--active-worker-policy-review")
    parser.add_argument("--output-activation-config")
    parser.add_argument("--trade-calendar-is-open", choices=("true", "false"))
    parser.add_argument("--enable-n5-intake", action="store_true")
    parser.add_argument("--enable-n5-active-scope-artifact", action="store_true")
    parser.add_argument("--enable-n3-c1-n3t", action="store_true")
    parser.add_argument("--n3-c1-n3t-current-day-source-artifact-dir", default="")
    parser.add_argument("--n3-c1-n3t-current-day-source-provider", default="")
    parser.add_argument("--n3-c1-n3t-metric-context-source-artifact-dir", default="")
    parser.add_argument("--n3-c1-n3t-previous-day-context-artifact-dir", default="")
    parser.add_argument("--n3-c1-n3t-previous-day-context-provider", default="")
    parser.add_argument("--n3-c1-n3t-n3t-writer-adapter", default="")
    parser.add_argument("--enable-n5-executed", action="store_true")
    parser.add_argument("--json-output-path")
    parser.add_argument("--json", action="store_true")
    return parser


def _fetch_next_trade_date_from_calendar(*, dsn: str, for_trade_date: str) -> tuple[str, bool]:
    try:
        import psycopg
    except ModuleNotFoundError as exc:  # pragma: no cover - surfaced in CLI
        raise RuntimeError("psycopg is required for post-close readiness rollover") from exc
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        conn.execute("BEGIN READ ONLY")
        row = conn.execute(
            """
            SELECT current_day.next_trade_date, COALESCE(next_day.is_open, false)
            FROM common_trade_calendar AS current_day
            LEFT JOIN common_trade_calendar AS next_day
              ON next_day.trade_date = current_day.next_trade_date
            WHERE current_day.trade_date = %s
            """,
            (str(for_trade_date),),
        ).fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"next_trade_date_not_found:{for_trade_date}")
    return str(row[0]), bool(row[1])


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    if args.post_close_readiness_config_rollover:
        if not args.for_trade_date:
            raise SystemExit("--for-trade-date is required with --post-close-readiness-config-rollover")
        if not args.dsn:
            raise SystemExit("--dsn is required with --post-close-readiness-config-rollover")
        if not args.base_activation_config:
            raise SystemExit("--base-activation-config is required with --post-close-readiness-config-rollover")
        try:
            next_trade_date, next_trade_day_is_open = _fetch_next_trade_date_from_calendar(
                dsn=args.dsn,
                for_trade_date=args.for_trade_date,
            )
            report = write_fastlane_post_close_readiness_config_rollover(
                base_activation_config_path=Path(args.base_activation_config),
                output_dir=Path(args.output_dir),
                for_trade_date=args.for_trade_date,
                next_trade_date=next_trade_date,
                trade_calendar_is_open=next_trade_day_is_open,
                current_exchange_time=args.current_exchange_time,
            )
        except Exception as exc:
            raise SystemExit(str(exc)) from exc
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print(
                f"result={report['result']} "
                f"next_trade_date={report['next_trade_date']} "
                f"stable_activation_config_path={report['stable_activation_config_path']}"
            )
        return 0
    if args.full_chain_activation_preflight:
        if not args.activation_config:
            raise SystemExit("--activation-config is required with --full-chain-activation-preflight")
        report = build_fastlane_write_enabled_activation_config_full_chain_preflight(
            activation_config_path=Path(args.activation_config),
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print(
                f"result={report['result']} "
                f"activation_scope={report['activation_scope']} "
                f"final_verdict={report['final_verdict']}"
            )
        return 0
    if args.write_enabled_activation_config:
        if not args.base_activation_config:
            raise SystemExit("--base-activation-config is required with --write-enabled-activation-config")
        if not args.active_worker_policy_review:
            raise SystemExit(
                "--active-worker-policy-review is required with --write-enabled-activation-config"
            )
        if not args.output_activation_config:
            raise SystemExit("--output-activation-config is required with --write-enabled-activation-config")
        if args.trade_calendar_is_open is None:
            raise SystemExit("--trade-calendar-is-open is required with --write-enabled-activation-config")
        try:
            report = write_fastlane_write_enabled_activation_config(
                base_activation_config_path=Path(args.base_activation_config),
                active_worker_policy_review_path=Path(args.active_worker_policy_review),
                output_activation_config_path=Path(args.output_activation_config),
                trade_calendar_is_open=args.trade_calendar_is_open == "true",
                enable_n5_intake=bool(args.enable_n5_intake),
                enable_n5_active_scope_artifact=bool(args.enable_n5_active_scope_artifact),
                enable_n3_c1_n3t=bool(args.enable_n3_c1_n3t),
                n3_c1_n3t_current_day_source_artifact_dir=args.n3_c1_n3t_current_day_source_artifact_dir,
                n3_c1_n3t_current_day_source_provider=args.n3_c1_n3t_current_day_source_provider,
                n3_c1_n3t_metric_context_source_artifact_dir=args.n3_c1_n3t_metric_context_source_artifact_dir,
                n3_c1_n3t_previous_day_context_artifact_dir=args.n3_c1_n3t_previous_day_context_artifact_dir,
                n3_c1_n3t_previous_day_context_provider=args.n3_c1_n3t_previous_day_context_provider,
                n3_c1_n3t_n3t_writer_adapter=args.n3_c1_n3t_n3t_writer_adapter,
                enable_n5_executed=bool(args.enable_n5_executed),
                defer_active_worker_policy_review_to_runtime=bool(
                    args.defer_active_worker_policy_review_to_runtime
                ),
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print(
                f"result={report['result']} "
                f"output_activation_config_path={report['output_activation_config_path']} "
                f"sha256={report['output_sha256']}"
            )
        return 0
    if args.activation_guard:
        payload = build_fastlane_activation_guard(args.activation_guard)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if args.json_output_path:
            Path(args.json_output_path).write_text(encoded + "\n", encoding="utf-8")
        if args.json:
            print(encoded)
        elif not args.json_output_path:
            print(f"verdict={payload['verdict']} label={payload['label']}")
        return 0
    if args.active_plan:
        if not args.activation_config:
            raise SystemExit("--activation-config is required with --active-plan")
        report = write_fastlane_active_launchd_plan(
            output_dir=Path(args.output_dir),
            working_directory=args.working_directory,
            activation_config_path=args.activation_config,
            python_executable=args.python_executable,
            require_full_chain_activation=bool(args.require_full_chain_activation),
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            print(f"result={report['result']} report_path={report['report_path']}")
        return 0
    report = write_fastlane_launchd_plan(
        output_dir=Path(args.output_dir),
        working_directory=args.working_directory,
        python_executable=args.python_executable,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(f"result={report['result']} report_path={report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
