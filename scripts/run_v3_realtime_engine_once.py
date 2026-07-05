#!/usr/bin/env python3
"""Run one bounded V3 realtime engine pass.

This wrapper is the runtime_control scheduler entrypoint. It is an orchestrator
only: it may invoke pre-approved layer run-once children as argv lists, enforce
a no-overlap lock, and collect reports. It must not contain N3/N4/N5/N6 business
logic and must not be treated as a layer implementation.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
import errno
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Iterator, Mapping, Sequence
from zoneinfo import ZoneInfo


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
RUNTIME_CONTROL_ORCHESTRATOR = True
ORCHESTRATOR_BOUNDARY = "runtime_control_only"
ORCHESTRATOR_ALLOWED_CHILD_STAGES = (
    "N3_REALTIME_VIRTUAL_METRIC",
    "N4_TRIGGER",
    "N5_ACTION",
    "N6_USER_PROJECTION",
)
ORCHESTRATOR_FORBIDDEN_LAYER_LOGIC = (
    "no_market_data_calculation",
    "no_trigger_rule_evaluation",
    "no_action_confirmation_rule_evaluation",
    "no_user_policy_projection_logic",
)
DEFAULT_LOCK_PATH = "tmp/v3_realtime_engine.lock"
DEFAULT_JSON_REPORT_PATH = "docs/V3_REALTIME_ENGINE_PRODUCTION_RUN_ONCE_REPORT.json"
DEFAULT_MD_REPORT_PATH = "docs/V3_REALTIME_ENGINE_PRODUCTION_RUN_ONCE_REPORT.md"
DEFAULT_SCHEDULER_CONTRACT_PATH = "docs/V3_REALTIME_ENGINE_PRODUCTION_SCHEDULER_CONTRACT.json"
DEFAULT_CLOSEOUT_PATH = "docs/V3_20260612_NEW_PLAN_N3_N4_N5_RUNTIME_CLOSEOUT.json"
DEFAULT_N3_CONTRACT_PATH = "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_CONTRACT.json"
DEFAULT_N3_PREFLIGHT_PATH = "docs/V3_20260612_REALTIME_VIRTUAL_METRIC_WRITER_RUNNER_PREFLIGHT.json"
DEFAULT_N3_SOURCE_PAYLOAD_PATH = "docs/V3_20260612_realtime_virtual_metric_writer_payload.json"
DEFAULT_N3_ROLLBACK_SQL = "sql/V3_20260612_realtime_virtual_metric_writer_runner_rollback.sql"
DEFAULT_N4_ROLLBACK_SQL = "sql/V3_20260612_n4_action_confirmation_metric_business_execute_after_n3_writer_rollback.sql"
DEFAULT_N5_ROLLBACK_SQL = "sql/V3_20260612_n5_action_consumer_after_n4_action_confirmation_metric_rollback.sql"
DEFAULT_N6_CONTRACT_PATH = "docs/N6_canonical_projection_execute_contract.json"
DEFAULT_N6_PREFLIGHT_PATH = "docs/N6_canonical_projection_execute_preflight.json"
DEFAULT_N6_ROLLBACK_SQL = "sql/N6_projection_business_rollback.sql"

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # pragma: no cover - only for stripped test envs
    DEFAULT_DSN = "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3"


class NoOverlapLockHeld(RuntimeError):
    """Raised when another bounded engine pass already holds the lock."""


@dataclass(frozen=True)
class EngineLineage:
    for_trade_date: str
    source_condition_run_id: str
    n3_metric_run_id: str
    n4_trigger_run_id: str
    n5_action_run_id: str
    n6_projection_run_id: str
    source_snapshot_run_id: str
    trigger_context_run_id: str


@contextmanager
def acquire_no_overlap_lock(lock_path: str | Path) -> Iterator[None]:
    """Acquire a non-blocking process lock for one bounded wrapper pass."""

    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise NoOverlapLockHeld("no_overlap_lock_already_held") from exc
            raise
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid(), "acquired_at": datetime.now(ASIA_SHANGHAI).isoformat()}))
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def local_now() -> datetime:
    return datetime.now(ASIA_SHANGHAI)


def coerce_shanghai(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ASIA_SHANGHAI)
    return value.astimezone(ASIA_SHANGHAI)


def normalize_completed_process(result: Any) -> dict[str, Any]:
    return {
        "returncode": int(getattr(result, "returncode", 0)),
        "stdout": str(getattr(result, "stdout", "") or ""),
        "stderr": str(getattr(result, "stderr", "") or ""),
    }


def run_command(argv: list[str]) -> Any:
    return subprocess.run(argv, check=False, text=True, capture_output=True)


def forbidden_scope_proof() -> dict[str, bool]:
    return {
        "n6_projection_only": True,
        "voice_mobile_sim_trade_touched": False,
        "proposal_order_trade_sim_position_pnl_real_trade": False,
        "old_system_touched": False,
        "long_running_worker_started": False,
        "scheduler_installed_or_enabled": False,
        "rollback_executed": False,
        "shell_string_used": False,
        "non_authorized_outbox_inbox_checkpoint_consumed_or_updated": False,
    }


def base_report(*, execute: bool, user_confirmed: bool, as_of: datetime, lock_path: str | Path) -> dict[str, Any]:
    return {
        "stage": "V3_REALTIME_ENGINE_PRODUCTION_RUN_ONCE_WRAPPER",
        "layer_role": "N3_market_data",
        "result": "PLAN_ONLY",
        "reason": None,
        "blocked_reason": None,
        "as_of": as_of.isoformat(),
        "execution_mode": "execute" if execute and user_confirmed else "plan_only",
        "execute": bool(execute),
        "user_confirmed": bool(user_confirmed),
        "no_overlap_lock": {"path": str(lock_path), "required": True, "acquired": False},
        "lineage": {},
        "child_command_plan": [],
        "executed_steps": [],
        "skipped_steps": [],
        "stage_status": {},
        "idempotency": {"watermark_source": "passed deterministic run_id", "all_passed": False},
        "policy_proof": {
            "n3_auction_virtual_1m_policy": "09:20-09:30 auction virtual 1m is owned by N3 child contracts",
            "n3_midday_policy": "13:00 bridge and 13:01 compare policy is owned by N3 virtual metric writer artifacts",
            "n4_input": "N3 standard realtime virtual metric only",
            "n5_entry_event_only": "TriggerMatched",
            "n6_projection_only": True,
            "bounded_run_once": True,
        },
        "side_effects": {
            "database_written_by_wrapper": False,
            "child_commands_invoked": False,
            "n3_child_invoked": False,
            "n4_child_invoked": False,
            "n5_child_invoked": False,
            "n6_child_invoked": False,
            "scheduler_installed_or_enabled": False,
            "long_running_worker_started": False,
            "n6_projection_entered": False,
            "voice_mobile_sim_trade_touched": False,
            "proposal_order_trade_sim_position_pnl_real_trade": False,
        },
        "forbidden_scope_proof": forbidden_scope_proof(),
    }


def command_plan(stage: str, argv: list[str]) -> dict[str, Any]:
    return {
        "stage": stage,
        "argv": list(argv),
        "uses_shell": False,
        "requires_execute": "--execute" in argv,
        "requires_user_confirmed": "--user-confirmed" in argv,
    }


def resolve_lineage_from_artifacts(
    *,
    for_trade_date: str | None,
    source_condition_run_id: str | None,
    n3_metric_run_id: str | None,
    n4_trigger_run_id: str | None,
    n5_action_run_id: str | None,
    n6_projection_run_id: str | None,
    source_snapshot_run_id: str | None,
    trigger_context_run_id: str | None,
    n3_contract_path: str | Path,
    closeout_path: str | Path,
) -> dict[str, Any]:
    contract = read_json(n3_contract_path) if Path(n3_contract_path).exists() else {}
    closeout = read_json(closeout_path) if Path(closeout_path).exists() else {}
    source_scope = dict(contract.get("source_scope") or {})
    source_run_ids = dict(closeout.get("source_run_ids") or {})
    resolved_for_trade_date = for_trade_date or source_scope.get("for_trade_date") or closeout.get("for_trade_date")
    resolved_source_condition = source_condition_run_id or source_scope.get("source_condition_run_id")
    resolved_n3_run = n3_metric_run_id or contract.get("target_run_id") or source_run_ids.get("n3_projection_run_id")
    resolved_n4_run = n4_trigger_run_id or source_run_ids.get("n4_trigger_run_id")
    resolved_n5_run = n5_action_run_id or source_run_ids.get("n5_action_run_id")
    resolved_n6_run = n6_projection_run_id or source_run_ids.get("n6_projection_run_id")
    if not resolved_n6_run and resolved_for_trade_date and resolved_n5_run:
        resolved_n6_run = f"v3_n6_user_projection_{resolved_for_trade_date}_after_{resolved_n5_run}"
    resolved_snapshot = source_snapshot_run_id or source_scope.get("source_snapshot_run_id")
    if trigger_context_run_id:
        resolved_context = trigger_context_run_id
    elif resolved_for_trade_date and resolved_source_condition:
        resolved_context = f"trigger_context_snapshot_{resolved_for_trade_date}_{resolved_source_condition}"
    else:
        resolved_context = None
    values = {
        "for_trade_date": resolved_for_trade_date,
        "source_condition_run_id": resolved_source_condition,
        "n3_metric_run_id": resolved_n3_run,
        "n4_trigger_run_id": resolved_n4_run,
        "n5_action_run_id": resolved_n5_run,
        "n6_projection_run_id": resolved_n6_run,
        "source_snapshot_run_id": resolved_snapshot,
        "trigger_context_run_id": resolved_context,
    }
    artifact_dates = {
        str(value)
        for value in (
            source_scope.get("for_trade_date"),
            closeout.get("for_trade_date"),
        )
        if value
    }
    if for_trade_date and artifact_dates and artifact_dates != {str(for_trade_date)}:
        return {
            "status": "blocked",
            "reason": "stale_artifact_lineage_mismatch",
            "requested_for_trade_date": str(for_trade_date),
            "artifact_for_trade_dates": sorted(artifact_dates),
            **values,
        }
    missing = [key for key, value in values.items() if not value]
    if missing:
        return {"status": "blocked", "reason": "lineage_arguments_missing", "missing": missing, **values}
    return {"status": "resolved", "reason": "artifact_or_explicit_lineage", **values}


def coerce_lineage(raw: Mapping[str, Any]) -> EngineLineage:
    return EngineLineage(
        for_trade_date=str(raw["for_trade_date"]),
        source_condition_run_id=str(raw["source_condition_run_id"]),
        n3_metric_run_id=str(raw["n3_metric_run_id"]),
        n4_trigger_run_id=str(raw["n4_trigger_run_id"]),
        n5_action_run_id=str(raw["n5_action_run_id"]),
        n6_projection_run_id=str(raw["n6_projection_run_id"]),
        source_snapshot_run_id=str(raw["source_snapshot_run_id"]),
        trigger_context_run_id=str(raw["trigger_context_run_id"]),
    )


def default_stage_status(*, dsn: str, stage: str, run_id: str) -> dict[str, Any]:
    table = {
        "N3_REALTIME_VIRTUAL_METRIC": "common_market_data_run",
        "N4_TRIGGER": "common_trigger_run",
        "N5_ACTION": "common_action_run",
        "N6_USER_PROJECTION": "user_projection_run",
    }.get(stage)
    if not table:
        return {"status": "unknown", "reason": "unsupported_stage"}
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass(%s) AS table_name", (table,))
                if not cur.fetchone()["table_name"]:
                    return {"status": "missing_table", "table": table}
                id_column = "user_projection_run_id" if table == "user_projection_run" else "run_id"
                cur.execute(f"SELECT status FROM {table} WHERE {id_column} = %s", (run_id,))
                row = cur.fetchone()
    except Exception as exc:  # pragma: no cover - defensive production proof
        return {"status": "unknown", "reason": f"status_probe_failed:{exc.__class__.__name__}"}
    if not row:
        return {"status": "missing", "table": table}
    return {"status": row["status"], "table": table}


def default_metric_coverage_guard(*, dsn: str, lineage: EngineLineage) -> dict[str, Any]:
    try:
        from ashare_v3.market.v3_full_day_replay_plan import build_realtime_metric_coverage_guard_report

        return build_realtime_metric_coverage_guard_report(
            dsn=dsn,
            for_trade_date=lineage.for_trade_date,
            source_condition_run_id=lineage.source_condition_run_id,
            trigger_context_run_id=lineage.trigger_context_run_id,
            projection_run_id=lineage.n3_metric_run_id,
        )
    except Exception as exc:  # pragma: no cover - production defensive report
        return {
            "result": "BLOCKED",
            "blocked_reason": f"metric_coverage_guard_probe_failed:{exc.__class__.__name__}",
            "missing_identity_count": None,
            "missing_identity_sample": [],
        }


def build_n3_command(
    *,
    python_executable: str,
    contract_path: str | Path,
    preflight_path: str | Path,
    source_payload_path: str | Path,
    docs_root: str | Path,
    for_trade_date: str,
) -> list[str]:
    docs = Path(docs_root)
    return [
        python_executable,
        "scripts/run_v3_realtime_virtual_metric_writer_once.py",
        "--contract-path",
        str(contract_path),
        "--preflight-path",
        str(preflight_path),
        "--source-payload-path",
        str(source_payload_path),
        "--json-report-path",
        str(docs / f"V3_REALTIME_ENGINE_N3_VIRTUAL_METRIC_WRITER_REPORT_{for_trade_date}.json"),
        "--markdown-report-path",
        str(docs / f"V3_REALTIME_ENGINE_N3_VIRTUAL_METRIC_WRITER_REPORT_{for_trade_date}.md"),
        "--execute",
        "--user-confirmed",
    ]


def build_n4_command(
    *,
    python_executable: str,
    dsn: str,
    lineage: EngineLineage,
    docs_root: str | Path,
    rollback_sql_path: str | Path,
) -> list[str]:
    docs = Path(docs_root)
    return [
        python_executable,
        "scripts/run_trigger_projection_matcher_once.py",
        "--dsn",
        dsn,
        "--execute-run-id",
        lineage.n4_trigger_run_id,
        "--trigger-context-run-id",
        lineage.trigger_context_run_id,
        "--projection-run-id",
        lineage.n3_metric_run_id,
        "--snapshot-run-id",
        lineage.source_snapshot_run_id,
        "--consumer-name",
        f"v3_realtime_engine_n4_consumer_{lineage.for_trade_date}",
        "--json-report-path",
        str(docs / f"V3_REALTIME_ENGINE_N4_TRIGGER_REPORT_{lineage.for_trade_date}.json"),
        "--markdown-report-path",
        str(docs / f"V3_REALTIME_ENGINE_N4_TRIGGER_REPORT_{lineage.for_trade_date}.md"),
        "--rollback-sql-path",
        str(rollback_sql_path),
        "--execute",
        "--user-confirmed",
    ]


def build_n5_command(
    *,
    python_executable: str,
    dsn: str,
    lineage: EngineLineage,
    docs_root: str | Path,
    rollback_sql_path: str | Path,
    max_events: int,
    max_runtime_seconds: int,
    heartbeat_interval_seconds: int,
) -> list[str]:
    docs = Path(docs_root)
    return [
        python_executable,
        "scripts/run_action_consumer_once.py",
        "--dsn",
        dsn,
        "--semantic-action-smoke",
        "--smoke-run-id",
        lineage.n5_action_run_id,
        "--action-run-id",
        lineage.n5_action_run_id,
        "--source-run-id",
        lineage.n4_trigger_run_id,
        "--consumer-name",
        f"v3_realtime_engine_n5_consumer_{lineage.for_trade_date}",
        "--metric-run-id",
        lineage.n3_metric_run_id,
        "--source-event-type",
        "TriggerMatched",
        "--max-events",
        str(max_events),
        "--max-runtime-seconds",
        str(max_runtime_seconds),
        "--heartbeat-interval-seconds",
        str(heartbeat_interval_seconds),
        "--json-report-path",
        str(docs / f"V3_REALTIME_ENGINE_N5_ACTION_REPORT_{lineage.for_trade_date}.json"),
        "--markdown-report-path",
        str(docs / f"V3_REALTIME_ENGINE_N5_ACTION_REPORT_{lineage.for_trade_date}.md"),
        "--rollback-sql-path",
        str(rollback_sql_path),
        "--execute",
        "--user-confirmed",
    ]


def build_n6_command(
    *,
    python_executable: str,
    dsn: str,
    lineage: EngineLineage,
    n6_contract_path: str | Path,
    n6_preflight_path: str | Path,
    n6_rollback_sql_path: str | Path = DEFAULT_N6_ROLLBACK_SQL,
    expected_n5_outbox_counts: Mapping[str, int] | None = None,
) -> list[str]:
    argv = [
        python_executable,
        "scripts/run_n6_projection_once.py",
        "--dsn",
        dsn,
        "--projection-run-id",
        lineage.n6_projection_run_id,
        "--source-action-run-id",
        lineage.n5_action_run_id,
        "--contract-json-path",
        str(n6_contract_path),
        "--preflight-json-path",
        str(n6_preflight_path),
        "--rollback-sql-path",
        str(n6_rollback_sql_path),
        "--execute",
        "--user-confirmed",
        "--json",
    ]
    for key, count in sorted((expected_n5_outbox_counts or {}).items()):
        argv.extend(["--expected-n5-outbox-count", f"{key}={int(count)}"])
    return argv


def build_child_commands(
    *,
    lineage: EngineLineage,
    dsn: str,
    python_executable: str,
    docs_root: str | Path,
    n3_contract_path: str | Path,
    n3_preflight_path: str | Path,
    n3_source_payload_path: str | Path,
    n6_contract_path: str | Path,
    n6_preflight_path: str | Path,
    n6_rollback_sql_path: str | Path,
    n4_rollback_sql_path: str | Path,
    n5_rollback_sql_path: str | Path,
    max_n5_events: int,
    max_n5_runtime_seconds: int,
    n5_heartbeat_interval_seconds: int,
) -> list[tuple[str, str, list[str]]]:
    return [
        (
            "N3_REALTIME_VIRTUAL_METRIC",
            lineage.n3_metric_run_id,
            build_n3_command(
                python_executable=python_executable,
                contract_path=n3_contract_path,
                preflight_path=n3_preflight_path,
                source_payload_path=n3_source_payload_path,
                docs_root=docs_root,
                for_trade_date=lineage.for_trade_date,
            ),
        ),
        (
            "N4_TRIGGER",
            lineage.n4_trigger_run_id,
            build_n4_command(
                python_executable=python_executable,
                dsn=dsn,
                lineage=lineage,
                docs_root=docs_root,
                rollback_sql_path=n4_rollback_sql_path,
            ),
        ),
        (
            "N5_ACTION",
            lineage.n5_action_run_id,
            build_n5_command(
                python_executable=python_executable,
                dsn=dsn,
                lineage=lineage,
                docs_root=docs_root,
                rollback_sql_path=n5_rollback_sql_path,
                max_events=max_n5_events,
                max_runtime_seconds=max_n5_runtime_seconds,
                heartbeat_interval_seconds=n5_heartbeat_interval_seconds,
            ),
        ),
        (
            "N6_USER_PROJECTION",
            lineage.n6_projection_run_id,
            build_n6_command(
                python_executable=python_executable,
                dsn=dsn,
                lineage=lineage,
                n6_contract_path=n6_contract_path,
                n6_preflight_path=n6_preflight_path,
                n6_rollback_sql_path=n6_rollback_sql_path,
            ),
        ),
    ]


def run_v3_realtime_engine_once(
    *,
    dsn: str = DEFAULT_DSN,
    auto_resolve_lineage: bool = False,
    for_trade_date: str | None = None,
    source_condition_run_id: str | None = None,
    n3_metric_run_id: str | None = None,
    n4_trigger_run_id: str | None = None,
    n5_action_run_id: str | None = None,
    n6_projection_run_id: str | None = None,
    source_snapshot_run_id: str | None = None,
    trigger_context_run_id: str | None = None,
    docs_root: str | Path = "docs",
    sql_root: str | Path = "sql",
    n3_contract_path: str | Path = DEFAULT_N3_CONTRACT_PATH,
    n3_preflight_path: str | Path = DEFAULT_N3_PREFLIGHT_PATH,
    n3_source_payload_path: str | Path = DEFAULT_N3_SOURCE_PAYLOAD_PATH,
    n6_contract_path: str | Path = DEFAULT_N6_CONTRACT_PATH,
    n6_preflight_path: str | Path = DEFAULT_N6_PREFLIGHT_PATH,
    closeout_path: str | Path = DEFAULT_CLOSEOUT_PATH,
    scheduler_contract_path: str | Path = DEFAULT_SCHEDULER_CONTRACT_PATH,
    lock_path: str | Path = DEFAULT_LOCK_PATH,
    json_report_path: str | Path | None = None,
    markdown_report_path: str | Path | None = None,
    python_executable: str = sys.executable,
    execute: bool = False,
    user_confirmed: bool = False,
    as_of: datetime | None = None,
    max_n5_events: int = 5000,
    max_n5_runtime_seconds: int = 120,
    n5_heartbeat_interval_seconds: int = 10,
    allow_overwrite: bool = False,
    lineage_resolver: Callable[..., Mapping[str, Any]] | None = None,
    status_provider: Callable[[str, str], Mapping[str, Any]] | None = None,
    command_runner: Callable[[list[str]], Any] | None = None,
    metric_coverage_guard: Callable[..., Mapping[str, Any]] | None = None,
    n5_outbox_counts_provider: Callable[..., Mapping[str, int]] | None = None,
) -> dict[str, Any]:
    resolved_as_of = coerce_shanghai(as_of or local_now())
    report = base_report(execute=execute, user_confirmed=user_confirmed, as_of=resolved_as_of, lock_path=lock_path)
    report["scheduler_contract_path"] = str(scheduler_contract_path)
    report["rollback_registry"] = {
        "n3": DEFAULT_N3_ROLLBACK_SQL,
        "n4": DEFAULT_N4_ROLLBACK_SQL,
        "n5": DEFAULT_N5_ROLLBACK_SQL,
        "n6": DEFAULT_N6_ROLLBACK_SQL,
        "automatic_rollback_executed": False,
    }
    if execute and not user_confirmed:
        report.update({"result": "BLOCKED", "blocked_reason": "missing_user_confirmed_flag"})
        return maybe_write_report(report, json_report_path, markdown_report_path)
    if user_confirmed and not execute:
        report.update({"result": "BLOCKED", "blocked_reason": "missing_execute_flag"})
        return maybe_write_report(report, json_report_path, markdown_report_path)

    lock_cm = acquire_no_overlap_lock(lock_path) if execute else _null_lock()
    try:
        with lock_cm:
            if execute:
                report["no_overlap_lock"]["acquired"] = True
            if auto_resolve_lineage and for_trade_date is None and lineage_resolver is None:
                report["lineage"] = {"status": "delegated", "reason": "auto_resolve_lineage_delegated_to_dynamic_chain"}
                return run_dynamic_chain_fallback(
                    report=report,
                    dsn=dsn,
                    docs_root=docs_root,
                    sql_root=sql_root,
                    for_trade_date=None,
                    python_executable=python_executable,
                    execute=execute,
                    runner=command_runner or run_command,
                    json_report_path=json_report_path,
                    markdown_report_path=markdown_report_path,
                    n6_contract_path=n6_contract_path,
                    n6_preflight_path=n6_preflight_path,
                    status_provider=status_provider,
                    n5_outbox_counts_provider=n5_outbox_counts_provider,
                    allow_overwrite=allow_overwrite,
                )
            raw_lineage = (
                lineage_resolver(dsn=dsn, as_of=resolved_as_of, for_trade_date=for_trade_date)
                if lineage_resolver
                else resolve_lineage_from_artifacts(
                    for_trade_date=for_trade_date,
                    source_condition_run_id=source_condition_run_id,
                    n3_metric_run_id=n3_metric_run_id,
                    n4_trigger_run_id=n4_trigger_run_id,
                    n5_action_run_id=n5_action_run_id,
                    n6_projection_run_id=n6_projection_run_id,
                    source_snapshot_run_id=source_snapshot_run_id,
                    trigger_context_run_id=trigger_context_run_id,
                    n3_contract_path=n3_contract_path,
                    closeout_path=closeout_path,
                )
            )
            report["lineage"] = dict(raw_lineage)
            if raw_lineage.get("status") == "blocked" and raw_lineage.get("reason") == "stale_artifact_lineage_mismatch" and auto_resolve_lineage:
                return run_dynamic_chain_fallback(
                    report=report,
                    dsn=dsn,
                    docs_root=docs_root,
                    sql_root=sql_root,
                    for_trade_date=for_trade_date,
                    python_executable=python_executable,
                    execute=execute,
                    runner=command_runner or run_command,
                    json_report_path=json_report_path,
                    markdown_report_path=markdown_report_path,
                    n6_contract_path=n6_contract_path,
                    n6_preflight_path=n6_preflight_path,
                    status_provider=status_provider,
                    n5_outbox_counts_provider=n5_outbox_counts_provider,
                    allow_overwrite=allow_overwrite,
                )
            if raw_lineage.get("status") == "noop":
                report.update({"result": "NOOP_PASS", "reason": raw_lineage.get("reason")})
                return maybe_write_report(report, json_report_path, markdown_report_path)
            if raw_lineage.get("status") != "resolved":
                report.update({"result": "BLOCKED", "blocked_reason": raw_lineage.get("reason", "lineage_not_resolved")})
                return maybe_write_report(report, json_report_path, markdown_report_path)

            lineage = coerce_lineage(raw_lineage)
            report["lineage"] = {"status": "resolved", **asdict(lineage)}
            report["for_trade_date"] = lineage.for_trade_date
            commands = build_child_commands(
                lineage=lineage,
                dsn=dsn,
                python_executable=python_executable,
                docs_root=docs_root,
                n3_contract_path=n3_contract_path,
                n3_preflight_path=n3_preflight_path,
                n3_source_payload_path=n3_source_payload_path,
                n6_contract_path=n6_contract_path,
                n6_preflight_path=n6_preflight_path,
                n6_rollback_sql_path=Path(sql_root) / Path(DEFAULT_N6_ROLLBACK_SQL).name,
                n4_rollback_sql_path=Path(sql_root) / Path(DEFAULT_N4_ROLLBACK_SQL).name,
                n5_rollback_sql_path=Path(sql_root) / Path(DEFAULT_N5_ROLLBACK_SQL).name,
                max_n5_events=max_n5_events,
                max_n5_runtime_seconds=max_n5_runtime_seconds,
                n5_heartbeat_interval_seconds=n5_heartbeat_interval_seconds,
            )
            report["child_command_plan"] = [command_plan(stage, argv) for stage, _run_id, argv in commands]
            if not execute:
                report["result"] = "PLAN_ONLY"
                return maybe_write_report(report, json_report_path, markdown_report_path)

            statuses = []
            status_of = status_provider or (lambda stage, run_id: default_stage_status(dsn=dsn, stage=stage, run_id=run_id))
            for stage, run_id, _argv in commands:
                status = dict(status_of(stage, run_id))
                report["stage_status"][stage] = {"run_id": run_id, **status}
                if status.get("status") == "passed":
                    report["skipped_steps"].append({"stage": stage, "run_id": run_id, "reason": "already_passed"})
                statuses.append(status.get("status"))
            if statuses and all(status == "passed" for status in statuses):
                report["idempotency"]["all_passed"] = True
                report.update({"result": "NOOP_PASS", "reason": "all_deterministic_runs_already_passed"})
                return maybe_write_report(report, json_report_path, markdown_report_path)

            runner = command_runner or run_command
            guard_checked = False
            guard = metric_coverage_guard or default_metric_coverage_guard
            for stage, run_id, argv in commands:
                if stage == "N4_TRIGGER" and not guard_checked:
                    guard_report = dict(guard(dsn=dsn, lineage=lineage))
                    report["metric_coverage_guard"] = guard_report
                    guard_checked = True
                    if guard_report.get("result") not in {"PASS", "PREFLIGHT_PASS", "NOOP_PASS"}:
                        report.update({"result": "BLOCKED", "blocked_reason": "metric_coverage_guard_failed"})
                        return maybe_write_report(report, json_report_path, markdown_report_path)
                if report["stage_status"][stage].get("status") == "passed":
                    continue
                child_result = normalize_completed_process(runner(argv))
                report["executed_steps"].append({"stage": stage, "run_id": run_id, "command": argv, **child_result})
                report["side_effects"]["child_commands_invoked"] = True
                if stage == "N3_REALTIME_VIRTUAL_METRIC":
                    report["side_effects"]["n3_child_invoked"] = True
                if stage == "N4_TRIGGER":
                    report["side_effects"]["n4_child_invoked"] = True
                if stage == "N5_ACTION":
                    report["side_effects"]["n5_child_invoked"] = True
                if stage == "N6_USER_PROJECTION":
                    report["side_effects"]["n6_child_invoked"] = True
                    report["side_effects"]["n6_projection_entered"] = True
                if child_result["returncode"] != 0:
                    report.update({"result": "BLOCKED", "blocked_reason": f"{stage.lower()}_failed"})
                    return maybe_write_report(report, json_report_path, markdown_report_path)
            report["result"] = "EXECUTE_PASS"
            return maybe_write_report(report, json_report_path, markdown_report_path)
    except NoOverlapLockHeld:
        report.update({"result": "BLOCKED", "blocked_reason": "no_overlap_lock_already_held"})
        return maybe_write_report(report, json_report_path, markdown_report_path)


def run_dynamic_chain_fallback(
    *,
    report: dict[str, Any],
    dsn: str,
    docs_root: str | Path,
    sql_root: str | Path,
    for_trade_date: str | None,
    python_executable: str,
    execute: bool,
    runner: Callable[[list[str]], Any],
    json_report_path: str | Path | None,
    markdown_report_path: str | Path | None,
    n6_contract_path: str | Path,
    n6_preflight_path: str | Path,
    status_provider: Callable[[str, str], Mapping[str, Any]] | None = None,
    n5_outbox_counts_provider: Callable[..., Mapping[str, int]] | None = None,
    allow_overwrite: bool,
) -> dict[str, Any]:
    report["dynamic_chain_fallback"] = {
        "enabled": False,
        "removed": True,
        "reason": "cross_layer_dynamic_chain_fallback_removed",
        "replacement": "invoke N3, N4, N5, and N6 layer gates independently",
        "for_trade_date": for_trade_date,
    }
    report["next_required_gates"] = [
        "N3_market_data: generate/execute metric or market-data contract",
        "N4_trigger: replay/execute trigger contract from reviewed N3 artifact",
        "N5_action: replay/execute action contract from reviewed N4 TriggerMatched",
        "N6_user: project user messages from reviewed N5 action events",
    ]
    report.update({"result": "BLOCKED" if execute else "PLAN_ONLY", "blocked_reason": "dynamic_chain_fallback_removed"})
    return maybe_write_report(report, json_report_path, markdown_report_path)


@contextmanager
def _null_lock() -> Iterator[None]:
    yield


def maybe_write_report(
    report: dict[str, Any],
    json_report_path: str | Path | None,
    markdown_report_path: str | Path | None,
) -> dict[str, Any]:
    if json_report_path:
        write_json(json_report_path, report)
    if markdown_report_path:
        write_text(markdown_report_path, format_markdown_report(report))
    return report


def format_markdown_report(report: Mapping[str, Any]) -> str:
    lines = [
        "# V3 Realtime Engine Production Run Once",
        "",
        f"- result: `{report.get('result')}`",
        f"- reason: `{report.get('reason')}`",
        f"- blocked_reason: `{report.get('blocked_reason')}`",
        f"- execution_mode: `{report.get('execution_mode')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        "",
        "## Child Command Plan",
        "",
    ]
    for step in report.get("child_command_plan") or []:
        lines.append(f"- {step.get('stage')}: argv_list={not step.get('uses_shell')} execute={step.get('requires_execute')} user_confirmed={step.get('requires_user_confirmed')}")
    lines.extend(["", "## Executed Steps", ""])
    for step in report.get("executed_steps") or []:
        lines.append(f"- {step.get('stage')}: returncode={step.get('returncode')}")
    lines.extend(["", "## Forbidden Scope", ""])
    for key, value in dict(report.get("forbidden_scope_proof") or {}).items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines).rstrip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--auto-resolve-lineage", action="store_true")
    parser.add_argument("--for-trade-date", default=None)
    parser.add_argument("--source-condition-run-id", default=None)
    parser.add_argument("--n3-metric-run-id", default=None)
    parser.add_argument("--n4-trigger-run-id", default=None)
    parser.add_argument("--n5-action-run-id", default=None)
    parser.add_argument("--n6-projection-run-id", default=None)
    parser.add_argument("--source-snapshot-run-id", default=None)
    parser.add_argument("--trigger-context-run-id", default=None)
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--sql-root", default="sql")
    parser.add_argument("--n3-contract-path", default=DEFAULT_N3_CONTRACT_PATH)
    parser.add_argument("--n3-preflight-path", default=DEFAULT_N3_PREFLIGHT_PATH)
    parser.add_argument("--n3-source-payload-path", default=DEFAULT_N3_SOURCE_PAYLOAD_PATH)
    parser.add_argument("--n6-contract-path", default=DEFAULT_N6_CONTRACT_PATH)
    parser.add_argument("--n6-preflight-path", default=DEFAULT_N6_PREFLIGHT_PATH)
    parser.add_argument("--closeout-path", default=DEFAULT_CLOSEOUT_PATH)
    parser.add_argument("--scheduler-contract-path", default=DEFAULT_SCHEDULER_CONTRACT_PATH)
    parser.add_argument("--lock-path", default=DEFAULT_LOCK_PATH)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--json-report-path", default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report-path", default=DEFAULT_MD_REPORT_PATH)
    parser.add_argument("--max-n5-events", type=int, default=5000)
    parser.add_argument("--max-n5-runtime-seconds", type=int, default=120)
    parser.add_argument("--n5-heartbeat-interval-seconds", type=int, default=10)
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    as_of = datetime.fromisoformat(args.as_of) if args.as_of else None
    report = run_v3_realtime_engine_once(
        dsn=args.dsn,
        auto_resolve_lineage=args.auto_resolve_lineage,
        for_trade_date=args.for_trade_date,
        source_condition_run_id=args.source_condition_run_id,
        n3_metric_run_id=args.n3_metric_run_id,
        n4_trigger_run_id=args.n4_trigger_run_id,
        n5_action_run_id=args.n5_action_run_id,
        n6_projection_run_id=args.n6_projection_run_id,
        source_snapshot_run_id=args.source_snapshot_run_id,
        trigger_context_run_id=args.trigger_context_run_id,
        docs_root=args.docs_root,
        sql_root=args.sql_root,
        n3_contract_path=args.n3_contract_path,
        n3_preflight_path=args.n3_preflight_path,
        n3_source_payload_path=args.n3_source_payload_path,
        n6_contract_path=args.n6_contract_path,
        n6_preflight_path=args.n6_preflight_path,
        closeout_path=args.closeout_path,
        scheduler_contract_path=args.scheduler_contract_path,
        lock_path=args.lock_path,
        json_report_path=args.json_report_path,
        markdown_report_path=args.markdown_report_path,
        python_executable=args.python_executable,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        as_of=as_of,
        max_n5_events=args.max_n5_events,
        max_n5_runtime_seconds=args.max_n5_runtime_seconds,
        n5_heartbeat_interval_seconds=args.n5_heartbeat_interval_seconds,
        allow_overwrite=args.allow_overwrite,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"V3 realtime engine once result={report.get('result')} reason={report.get('reason') or report.get('blocked_reason')}")
    return 0 if report.get("result") in {"PLAN_ONLY", "NOOP_PASS", "EXECUTE_PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
