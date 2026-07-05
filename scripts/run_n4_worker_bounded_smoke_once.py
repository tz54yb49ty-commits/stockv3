#!/usr/bin/env python3
"""Prepare a bounded N4 worker smoke report.

This implementation gate runner is intentionally non-executing: it validates
CLI guards and writes report artifacts, but does not connect to the database,
start a worker, or consume/update outbox rows.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

import psycopg

from ashare_v3.trigger.worker_consumer import (
    ALLOWED_SMOKE_WRITE_TABLES,
    DEFAULT_CONSUMER_NAME,
    DEFAULT_DSN,
    DEFAULT_SMOKE_RUN_ID,
    N4WorkerSmokeBlocked,
    assert_bounded_smoke_confirmed,
    assert_explicit_smoke_run_id_for_execute,
    assert_smoke_baseline_clean,
    apply_idempotency_scenario,
    build_bounded_controls,
    build_implementation_report,
    build_smoke_write_plan,
    build_worker_rollback_sql,
    build_worker_smoke_plan,
    fetch_existing_consume_keys,
    fetch_smoke_baseline_counts,
    fetch_smoke_run_metadata,
    fetch_source_events_by_event_ids_for_smoke,
    fetch_source_events_for_smoke,
    format_implementation_report,
    load_idempotency_scenario,
    load_semantic_fixture,
    load_semantic_oracle_evaluations,
    persist_worker_smoke_write_plan,
    require_semantic_inputs,
    semantic_source_event_ids,
    validate_source_events_for_execute,
    write_status_json,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="N4 bounded worker smoke implementation-gate runner.")
    parser.add_argument("--contract-path", default="docs/N4_WORKER_CONTINUOUS_STATE_TRANSITION_CONTRACT.json")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--smoke-run-id")
    parser.add_argument("--consumer-name", default=DEFAULT_CONSUMER_NAME)
    parser.add_argument("--source-run-id")
    parser.add_argument("--source-event-type", default="MarketSnapshotUpdated")
    parser.add_argument("--source-trade-date")
    parser.add_argument("--max-events", type=int, default=50)
    parser.add_argument("--max-runtime-seconds", type=int, default=120)
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=10)
    parser.add_argument("--stop-file", default="tmp/n4_worker_bounded_smoke.stop")
    parser.add_argument("--status-json", default="docs/N4_WORKER_BOUNDED_SMOKE_STATUS.json")
    parser.add_argument("--json-report-path", default="docs/N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION.json")
    parser.add_argument("--markdown-report-path", default="docs/N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION.md")
    parser.add_argument("--rollback-sql-path", default="sql/N4_worker_bounded_smoke_rollback.sql")
    parser.add_argument("--semantic-smoke", action="store_true")
    parser.add_argument("--semantic-fixture-path")
    parser.add_argument("--semantic-oracle-run-id")
    parser.add_argument("--idempotency-scenario-path")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    return parser


def validate_execute_cli(*, execute: bool, user_confirmed: bool, smoke_run_id: str | None) -> None:
    assert_bounded_smoke_confirmed(execute=execute, user_confirmed=user_confirmed)
    assert_explicit_smoke_run_id_for_execute(execute=execute, smoke_run_id=smoke_run_id)


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    contract_scope = _load_contract_scope(args.contract_path)
    smoke_run_id = args.smoke_run_id or contract_scope.get("smoke_run_id") or DEFAULT_SMOKE_RUN_ID
    source_run_id = args.source_run_id or contract_scope.get("source_run_id")
    source_event_type = args.source_event_type or contract_scope.get("source_event_type") or "MarketSnapshotUpdated"
    source_trade_date = args.source_trade_date or contract_scope.get("source_trade_date")

    controls = build_bounded_controls(
        max_events=args.max_events,
        max_runtime_seconds=args.max_runtime_seconds,
        stop_file=args.stop_file,
        status_json=args.status_json,
        heartbeat_interval_seconds=args.heartbeat_interval_seconds,
    )
    report: dict[str, Any] = build_implementation_report()
    report.update(
        {
            "contract_path": args.contract_path,
            "consumer_name": args.consumer_name,
            "smoke_run_id": smoke_run_id,
            "source_run_id": source_run_id,
            "source_event_type": source_event_type,
            "source_trade_date": source_trade_date,
            "bounded_controls": controls,
            "cli": {
                "execute_requested": bool(args.execute),
                "user_confirmed": bool(args.user_confirmed),
                "default_dry_validation_only": not bool(args.execute),
                "explicit_smoke_run_id": bool(args.smoke_run_id),
                "semantic_smoke": bool(args.semantic_smoke),
                "semantic_fixture_path": args.semantic_fixture_path,
                "semantic_oracle_run_id": args.semantic_oracle_run_id,
                "idempotency_scenario_path": args.idempotency_scenario_path,
            },
            "idempotency_scenario": {"scenario_enabled": False},
            "side_effects": {
                "worker_started": False,
                "database_written": False,
                "scoped_n4_database_writes": False,
                "n3_outbox_updated": False,
                "n3_outbox_status_updated": False,
                "n5_n6_entered": False,
            },
            "next_gate": "N4_WORKER_BOUNDED_SMOKE_IMPLEMENTATION_POST_REVIEW_GATE",
        }
    )

    exit_code = 0
    if args.execute or args.user_confirmed or args.idempotency_scenario_path:
        try:
            validate_execute_cli(execute=args.execute, user_confirmed=args.user_confirmed, smoke_run_id=args.smoke_run_id)
            idempotency_scenario = _load_idempotency_scenario(args)
            report["idempotency_scenario"] = _scenario_report_summary(idempotency_scenario)
            require_semantic_inputs(
                semantic_smoke=bool(args.semantic_smoke),
                semantic_fixture_path=args.semantic_fixture_path,
                semantic_oracle_run_id=args.semantic_oracle_run_id,
            )
            if not source_run_id or not source_trade_date:
                raise N4WorkerSmokeBlocked("N4 worker bounded smoke blocked before DB write: missing source run/date")
            if controls["stop_requested"]:
                raise N4WorkerSmokeBlocked("N4 worker bounded smoke blocked before DB write: stop_file already exists")
            execute_report = _execute_scoped_smoke(
                args,
                smoke_run_id,
                source_run_id,
                source_event_type,
                source_trade_date,
                idempotency_scenario=idempotency_scenario,
            )
            report.update(execute_report)
            _align_execute_report_metadata(report)
            report["result"] = "EXECUTE_PASS"
            report["execute_authorized_for_future_gate"] = True
        except N4WorkerSmokeBlocked as exc:
            report["result"] = "BLOCKED"
            report["blocked_reason"] = str(exc)
            report["execute_authorized_for_future_gate"] = False
            exit_code = 2
    else:
        report["result"] = "DRY_VALIDATION_PASS"
        report["execute_authorized_for_future_gate"] = False

    _write_text(args.json_report_path, json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text(args.markdown_report_path, format_implementation_report(report))
    _write_text(args.rollback_sql_path, build_worker_rollback_sql(smoke_run_id=smoke_run_id, consumer_name=args.consumer_name))
    if args.status_json:
        write_status_json(
            args.status_json,
            {
                "result": report["result"],
                "worker_started": False,
                "database_written": bool(report.get("database_written")),
                "scoped_n4_database_writes": bool(report.get("scoped_n4_database_writes")),
                "n3_outbox_updated": False,
                "n5_n6_entered": False,
                "processed_event_count": 0,
            },
        )
    return exit_code


def _execute_scoped_smoke(
    args: argparse.Namespace,
    smoke_run_id: str,
    source_run_id: str,
    source_event_type: str,
    source_trade_date: str,
    *,
    idempotency_scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with psycopg.connect(args.dsn) as conn:
        baseline = fetch_smoke_baseline_counts(conn, smoke_run_id=smoke_run_id, consumer_name=args.consumer_name)
        assert_smoke_baseline_clean(baseline)
        semantic_inputs = _load_semantic_inputs(args, conn)
        if args.semantic_smoke:
            source_event_ids = semantic_source_event_ids(
                semantic_inputs["evaluations"],
                max_events=int(args.max_events),
            )
            source_events = fetch_source_events_by_event_ids_for_smoke(
                conn,
                source_run_id=source_run_id,
                source_event_type=source_event_type,
                source_trade_date=source_trade_date,
                source_event_ids=source_event_ids,
            )
        else:
            source_events = fetch_source_events_for_smoke(
                conn,
                source_run_id=source_run_id,
                source_event_type=source_event_type,
                source_trade_date=source_trade_date,
                max_events=args.max_events,
                consumer_name=args.consumer_name,
            )
        validate_source_events_for_execute(source_events, source_event_type=source_event_type, max_events=args.max_events)
        existing_consume_keys = fetch_existing_consume_keys(
            conn,
            consumer_name=args.consumer_name,
            source_run_id=source_run_id,
            source_event_type=source_event_type,
        )
        source_events, existing_consume_keys, scenario_summary = apply_idempotency_scenario(
            source_events,
            existing_consume_keys=existing_consume_keys,
            scenario=idempotency_scenario,
        )
        dry_run_plan = build_worker_smoke_plan(
            smoke_run_id=smoke_run_id,
            consumer_name=args.consumer_name,
            source_events=source_events,
            evaluations=semantic_inputs["evaluations"],
            previous_states=semantic_inputs["previous_states"],
            existing_consume_keys=existing_consume_keys,
            max_events=args.max_events,
        )
        metadata = fetch_smoke_run_metadata(conn, source_run_id=source_run_id)
        write_plan = build_smoke_write_plan(
            smoke_run_id=smoke_run_id,
            consumer_name=args.consumer_name,
            source_condition_run_id=str(metadata["source_condition_run_id"]),
            source_market_data_run_id=str(metadata["source_market_data_run_id"]),
            for_trade_date=str(metadata["for_trade_date"]),
            source_trade_date=str(metadata["source_trade_date"]),
            prev_trade_date=str(metadata["prev_trade_date"]),
            dry_run_plan=dry_run_plan,
        )
        _raise_failure_injection_if_requested(idempotency_scenario, point="before_write")
        write_counts = persist_worker_smoke_write_plan(conn, write_plan)
        _raise_failure_injection_if_requested(idempotency_scenario, point="after_persist_before_commit")
    return {
        "dry_run_summary": dry_run_plan["summary"],
        "write_counts": write_counts,
        "write_scope": write_plan["allowed_write_tables"],
        "idempotency_scenario": {
            **scenario_summary,
            "accepted_source_event_count": dry_run_plan["summary"]["accepted_source_event_count"],
            "skipped_duplicate_source_event_count": dry_run_plan["summary"]["skipped_duplicate_source_event_count"],
        },
        "semantic_smoke": bool(args.semantic_smoke),
        "semantic_input_summary": {
            "fixture_only": bool(semantic_inputs.get("fixture_only")),
            "source_oracle_run_id": semantic_inputs.get("source_oracle_run_id"),
            "not_new_market_decision": bool(semantic_inputs.get("not_new_market_decision")),
            "evaluation_count": len(semantic_inputs["evaluations"]),
            "previous_state_count": len(semantic_inputs["previous_states"]),
        },
        "n3_outbox_status_updated": False,
        "n3_outbox_updated": False,
        "worker_started": False,
        "n5_n6_entered": False,
    }


def _align_execute_report_metadata(report: dict[str, Any]) -> None:
    write_counts = report.get("write_counts") if isinstance(report.get("write_counts"), Mapping) else {}
    scoped_n4_database_writes = _has_scoped_n4_database_writes(write_counts)
    report["database_written"] = scoped_n4_database_writes
    report["scoped_n4_database_writes"] = scoped_n4_database_writes
    report["worker_started"] = False
    report["long_running_worker_started"] = False
    report["n3_outbox_updated"] = False
    report["n3_outbox_status_updated"] = False
    report["n5_n6_entered"] = False
    side_effects = dict(report.get("side_effects") or {})
    side_effects.update(
        {
            "database_written": scoped_n4_database_writes,
            "scoped_n4_database_writes": scoped_n4_database_writes,
            "worker_started": False,
            "long_running_worker_started": False,
            "n3_outbox_updated": False,
            "n3_outbox_status_updated": False,
            "n5_n6_entered": False,
        }
    )
    report["side_effects"] = side_effects


def _has_scoped_n4_database_writes(write_counts: Mapping[str, Any]) -> bool:
    for table in ALLOWED_SMOKE_WRITE_TABLES:
        try:
            count = int(write_counts.get(table) or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            return True
    return False


def _load_semantic_inputs(args: argparse.Namespace, conn: Any) -> dict[str, Any]:
    if not args.semantic_smoke:
        return {
            "fixture_only": False,
            "source_oracle_run_id": None,
            "not_new_market_decision": False,
            "evaluations": [],
            "previous_states": {},
        }
    if args.semantic_fixture_path:
        return load_semantic_fixture(args.semantic_fixture_path)
    return load_semantic_oracle_evaluations(
        conn,
        semantic_oracle_run_id=str(args.semantic_oracle_run_id),
        max_events=int(args.max_events),
    )


def _load_idempotency_scenario(args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.idempotency_scenario_path:
        return None
    return load_idempotency_scenario(args.idempotency_scenario_path, consumer_name=args.consumer_name)


def _scenario_report_summary(scenario: Mapping[str, Any] | None) -> dict[str, Any]:
    if not scenario:
        return {"scenario_enabled": False}
    failure_injection = scenario.get("failure_injection") if isinstance(scenario.get("failure_injection"), dict) else {}
    return {
        "scenario_enabled": True,
        "scenario_path": scenario.get("scenario_path"),
        "configured_duplicate_source_event_count": sum(
            int(count) for count in dict(scenario.get("duplicate_source_event_counts") or {}).values()
        ),
        "configured_existing_consume_key_count": len(scenario.get("existing_consume_keys") or []),
        "retry_failure_injection_enabled": bool(failure_injection.get("enabled")),
        "failure_injection_point": failure_injection.get("point"),
    }


def _raise_failure_injection_if_requested(scenario: Mapping[str, Any] | None, *, point: str) -> None:
    if not scenario:
        return
    failure_injection = scenario.get("failure_injection") if isinstance(scenario.get("failure_injection"), Mapping) else {}
    if bool(failure_injection.get("enabled")) and failure_injection.get("point") == point:
        raise N4WorkerSmokeBlocked(
            "N4 worker bounded smoke retry failure injection triggered before commit: "
            f"{point} ({failure_injection.get('reason') or 'idempotency_retry_failure_injection'})"
        )


def _load_contract_scope(path: str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    scope = payload.get("scope")
    return dict(scope) if isinstance(scope, dict) else {}


def _write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
