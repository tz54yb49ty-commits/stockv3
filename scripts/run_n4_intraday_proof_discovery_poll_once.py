#!/usr/bin/env python3
"""Plan one bounded N4 proof-discovery polling pass.

This wrapper discovers passed N3 proof targets and builds exact N4 child
commands. It is plan-only by default and never consumes outbox, inbox, or
checkpoint rows.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ashare_v3.runtime.intraday_worker_lineage import (
    LineageConfigError,
    lineage_report_fields,
    load_intraday_worker_lineage_config,
    no_lineage_config_report_fields,
)
from ashare_v3.trigger.provisional_ordinary_execute import (
    build_n4p_ordinary_trigger_run_id,
    parse_n4p_ordinary_trigger_run_id,
)
from ashare_v3.trigger.provisional_projection_execute import (
    build_provisional_projection_trigger_run_id,
    parse_provisional_projection_trigger_run_id,
)


ORDINARY_SOURCE_VARIANT = "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
HINT_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"
DEFAULT_PYTHON_EXECUTABLE = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"

ORDINARY_SOURCE_RE = re.compile(
    r"^realtime_action_confirmation_metric_"
    r"(?P<for_trade_date>\d{8})_until_(?P<until_hhmm>\d{4})"
    r"__asset_all__"
    r"(?P<source_variant>b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1)"
    r"__(?P<subscription_run_id>market_data_subscription_(?P=for_trade_date)_condition_layer_"
    r"(?P<source_trade_date>\d{8})_source_(?P=source_trade_date)_for_(?P=for_trade_date)_v\d+)$"
)
HINT_SOURCE_RE = re.compile(
    r"^realtime_hint_projection_metric_"
    r"(?P<for_trade_date>\d{8})_until_(?P<until_hhmm>\d{4})"
    r"__asset_index_board__"
    r"(?P<proof_kind>index_board_1m_hint_projection_v1_midday_bridge_v1)"
    r"__(?P<subscription_run_id>market_data_subscription_(?P=for_trade_date)_condition_layer_"
    r"(?P<source_trade_date>\d{8})_source_(?P=source_trade_date)_for_(?P=for_trade_date)_v\d+)$"
)

SIDE_EFFECTS_FALSE = {
    "database_written": False,
    "child_executed": False,
    "outbox_consumed": False,
    "inbox_or_checkpoint_updated": False,
    "n5_n6_entered": False,
    "worker_or_launchd_touched": False,
    "rollback_executed": False,
    "schema_changed": False,
}
SELECTION_POLICY = "latest_unprocessed_only"
SELECTION_MODE_REALTIME = "realtime_latest_only"
SELECTION_MODE_CATCHUP = "catchup_latest_unprocessed"
SELECTION_MODES = (SELECTION_MODE_REALTIME, SELECTION_MODE_CATCHUP)
SELECTED_CHILD_ORDER_POLICY = "hint_first_realtime_latency_v1"
HISTORY_MAX_LINES = 500
DEFAULT_HISTORY_PATH = Path("tmp/N4_intraday_proof_discovery_poller_history.jsonl")
DEFAULT_HINT_HISTORY_PATH = Path("tmp/N4_intraday_proof_discovery_poller_hint_history.jsonl")
BASELINE_METADATA_COMPAT_REASON = "missing_or_legacy_baseline_metadata_with_verified_exact_source_and_counts"
FORBIDDEN_COMMAND_TOKENS = (
    "n5",
    "n6",
    "consume",
    "checkpoint",
    "launchctl",
    "bootstrap",
    "rollback",
    "schema",
)


class ProofDiscoveryBlocked(RuntimeError):
    """Raised when N4 proof discovery must fail closed."""


def _timing_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _new_report_timing() -> dict[str, Any]:
    return {
        "started_at": _timing_timestamp(),
        "finished_at": "",
        "total_duration_ms": 0,
        "phases": [],
    }


def _start_phase() -> tuple[str, float]:
    return _timing_timestamp(), time.perf_counter()


def _append_phase(
    report: dict[str, Any],
    *,
    phase_name: str,
    started_at: str,
    started_perf: float,
    status: str,
    child_step: str = "",
) -> None:
    timing = report.setdefault("timing", _new_report_timing())
    phase: dict[str, Any] = {
        "phase_name": phase_name,
        "started_at": started_at,
        "finished_at": _timing_timestamp(),
        "duration_ms": max(0, round((time.perf_counter() - started_perf) * 1000, 3)),
        "status": status,
    }
    if child_step:
        phase["child_step"] = child_step
    timing.setdefault("phases", []).append(phase)


def _finish_report_timing(report: dict[str, Any], *, started_perf: float) -> dict[str, Any]:
    timing = report.setdefault("timing", _new_report_timing())
    timing["finished_at"] = _timing_timestamp()
    timing["total_duration_ms"] = max(0, round((time.perf_counter() - started_perf) * 1000, 3))
    return report


def _child_timing_fields(*, started_at: str, started_perf: float) -> dict[str, Any]:
    return {
        "child_started_at": started_at,
        "child_finished_at": _timing_timestamp(),
        "child_duration_ms": max(0, round((time.perf_counter() - started_perf) * 1000, 3)),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan one N4 intraday proof-discovery poll.")
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", ""))
    parser.add_argument("--for-trade-date", default="")
    parser.add_argument("--source-trade-date", default="")
    parser.add_argument("--source-condition-run-id", default="")
    parser.add_argument("--trigger-context-run-id", default="")
    parser.add_argument("--lineage-config", default="")
    parser.add_argument("--mode", choices=("ordinary", "hint", "both"), default="both")
    parser.add_argument("--selection-mode", choices=SELECTION_MODES, default=SELECTION_MODE_REALTIME)
    parser.add_argument("--json-report-path")
    parser.add_argument("--history-path")
    parser.add_argument("--python-executable", default=DEFAULT_PYTHON_EXECUTABLE)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def build_proof_discovery_plan(
    *,
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    trigger_context_run_id: str,
    mode: str = "both",
    selection_mode: str = SELECTION_MODE_REALTIME,
    dsn: str = "",
    ordinary_candidates: Sequence[Mapping[str, Any]] | None = None,
    hint_candidates: Sequence[Mapping[str, Any]] | None = None,
    existing_targets: Sequence[Mapping[str, Any]] | None = None,
    python_executable: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    lineage_config_path: str = "",
) -> dict[str, Any]:
    """Build a plan-only proof-discovery report."""

    lineage_fields = no_lineage_config_report_fields()
    if lineage_config_path:
        try:
            lineage = load_intraday_worker_lineage_config(lineage_config_path)
        except LineageConfigError as exc:
            raise ProofDiscoveryBlocked(f"BLOCKED_INTRADAY_WORKER_LINEAGE_CONFIG:{exc}") from exc
        for_trade_date = str(lineage["for_trade_date"])
        source_trade_date = str(lineage["source_trade_date"])
        source_condition_run_id = str(lineage["n2_run_id"])
        trigger_context_run_id = str(lineage["n4_context_run_id"])
        lineage_fields = lineage_report_fields(lineage_config_path, lineage)

    _validate_inputs(
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        source_condition_run_id=source_condition_run_id,
        trigger_context_run_id=trigger_context_run_id,
        mode=mode,
        selection_mode=selection_mode,
    )
    if execute or user_confirmed:
        raise ProofDiscoveryBlocked("execute blocked: N4 proof-discovery poller is plan-only in this gate")

    if ordinary_candidates is None or hint_candidates is None or existing_targets is None:
        discovered = discover_proofs_from_db(
            dsn=dsn,
            for_trade_date=for_trade_date,
            source_trade_date=source_trade_date,
            selection_mode=selection_mode,
            mode=mode,
        )
        if ordinary_candidates is None:
            ordinary_candidates = discovered["ordinary_candidates"]
        if hint_candidates is None:
            hint_candidates = discovered["hint_candidates"]
        if existing_targets is None:
            existing_targets = discovered["existing_targets"]

    skipped: list[dict[str, str]] = []
    selected: dict[str, dict[str, Any] | None] = {"ordinary": None, "hint": None}
    if mode in {"ordinary", "both"}:
        selected["ordinary"] = _select_family_candidate(
            family="ordinary",
            candidates=ordinary_candidates,
            existing_targets=existing_targets,
            for_trade_date=for_trade_date,
            source_trade_date=source_trade_date,
            source_condition_run_id=source_condition_run_id,
            trigger_context_run_id=trigger_context_run_id,
            python_executable=python_executable or DEFAULT_PYTHON_EXECUTABLE,
            dsn=dsn,
            selection_mode=selection_mode,
            skipped=skipped,
        )
    if mode in {"hint", "both"}:
        selected["hint"] = _select_family_candidate(
            family="hint",
            candidates=hint_candidates,
            existing_targets=existing_targets,
            for_trade_date=for_trade_date,
            source_trade_date=source_trade_date,
            source_condition_run_id=source_condition_run_id,
            trigger_context_run_id=trigger_context_run_id,
            python_executable=python_executable or DEFAULT_PYTHON_EXECUTABLE,
            dsn=dsn,
            selection_mode=selection_mode,
            skipped=skipped,
        )

    _assert_child_argv_safe(selected)
    selected_child_order = _selected_child_order(selected)
    backlog_candidate_run_ids = [
        str(item["source_run_id"])
        for item in skipped
        if item.get("reason") == "backlog_requires_manual_catchup"
    ]
    no_candidate_reason = str(discovered.get("no_candidate_reason") or "") if "discovered" in locals() else ""
    return {
        "gate": "N4_INTRADAY_PROOF_DISCOVERY_POLLER_CONTRACT_PATCH_GATE",
        "layer_role": "N4_trigger",
        "result": "PLAN_ONLY_PASS",
        "mode": "plan_only",
        "poller_mode": mode,
        "selection_mode": selection_mode,
        "selection_policy": SELECTION_POLICY,
        "discovery_policy": str(discovered.get("discovery_policy") or "full_discovery_v1") if "discovered" in locals() else "injected_candidates",
        **({"no_candidate_reason": no_candidate_reason} if no_candidate_reason else {}),
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "dsn_redacted": _redact_dsn(dsn),
        "source_condition_run_id": source_condition_run_id,
        "trigger_context_run_id": trigger_context_run_id,
        **lineage_fields,
        "effective_for_trade_date": for_trade_date,
        "effective_source_trade_date": source_trade_date,
        "discovered": {
            "ordinary_candidates": len(ordinary_candidates),
            "hint_candidates": len(hint_candidates),
            "existing_targets": len(existing_targets),
        },
        "selected": selected,
        "selected_child_order_policy": SELECTED_CHILD_ORDER_POLICY,
        "selected_child_order": selected_child_order,
        "skipped_candidates": skipped,
        "backlog_requires_manual_catchup": bool(backlog_candidate_run_ids),
        "backlog_candidate_count": len(backlog_candidate_run_ids),
        "backlog_candidate_run_ids": backlog_candidate_run_ids,
        "child_execution": _empty_child_execution(selected_child_order=selected_child_order),
        "side_effects": dict(SIDE_EFFECTS_FALSE),
        "forbidden_operation_proof": _forbidden_operation_proof(child_executed=False),
    }


def run_proof_discovery_poll(
    *,
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    trigger_context_run_id: str,
    mode: str = "both",
    selection_mode: str = SELECTION_MODE_REALTIME,
    dsn: str = "",
    ordinary_candidates: Sequence[Mapping[str, Any]] | None = None,
    hint_candidates: Sequence[Mapping[str, Any]] | None = None,
    existing_targets: Sequence[Mapping[str, Any]] | None = None,
    python_executable: str | None = None,
    execute: bool = False,
    user_confirmed: bool = False,
    command_runner: Callable[[Sequence[str]], Any] | None = None,
    lineage_config_path: str = "",
) -> tuple[int, dict[str, Any]]:
    """Build a discovery plan and optionally run selected child wrappers.

    The command runner is injectable so tests can prove bounded execute
    behavior without launching real N4 child runtimes.
    """

    report_started_perf = time.perf_counter()
    timing = _new_report_timing()
    if execute and not user_confirmed:
        return _blocked_poll_report("execute requires --user-confirmed", timing=timing, started_perf=report_started_perf)
    if user_confirmed and not execute:
        return _blocked_poll_report("--user-confirmed requires --execute", timing=timing, started_perf=report_started_perf)

    discovery_started_at, discovery_started_perf = _start_phase()
    try:
        report = build_proof_discovery_plan(
            dsn=dsn,
            for_trade_date=for_trade_date,
            source_trade_date=source_trade_date,
            source_condition_run_id=source_condition_run_id,
            trigger_context_run_id=trigger_context_run_id,
            mode=mode,
            selection_mode=selection_mode,
            ordinary_candidates=ordinary_candidates,
            hint_candidates=hint_candidates,
            existing_targets=existing_targets,
            python_executable=python_executable,
            lineage_config_path=lineage_config_path,
        )
    except ProofDiscoveryBlocked as exc:
        blocked_code, blocked_report = _blocked_poll_report(str(exc), timing=timing, started_perf=report_started_perf)
        _append_phase(
            blocked_report,
            phase_name="discovery",
            started_at=discovery_started_at,
            started_perf=discovery_started_perf,
            status="blocked",
        )
        return blocked_code, _finish_report_timing(blocked_report, started_perf=report_started_perf)
    report["timing"] = timing
    _append_phase(
        report,
        phase_name="discovery",
        started_at=discovery_started_at,
        started_perf=discovery_started_perf,
        status="passed",
    )

    if not execute:
        closeout_started_at, closeout_started_perf = _start_phase()
        _append_phase(
            report,
            phase_name="report_closeout",
            started_at=closeout_started_at,
            started_perf=closeout_started_perf,
            status="passed",
        )
        return 0, _finish_report_timing(report, started_perf=report_started_perf)

    selection_started_at, selection_started_perf = _start_phase()
    selected_children = _selected_child_items(report.get("selected", {}))
    selected_child_order = [family for family, _ in selected_children]
    report["selected_child_order_policy"] = SELECTED_CHILD_ORDER_POLICY
    report["selected_child_order"] = selected_child_order
    _append_phase(
        report,
        phase_name="candidate_selection",
        started_at=selection_started_at,
        started_perf=selection_started_perf,
        status="passed",
    )
    if not selected_children:
        execute_report = dict(report)
        execute_report.update({"result": "noop", "status": "noop", "mode": "execute"})
        execute_report["child_execution"] = _empty_child_execution(selected_child_order=selected_child_order)
        execute_report["side_effects"] = dict(SIDE_EFFECTS_FALSE)
        closeout_started_at, closeout_started_perf = _start_phase()
        _append_phase(
            execute_report,
            phase_name="report_closeout",
            started_at=closeout_started_at,
            started_perf=closeout_started_perf,
            status="noop",
        )
        return 0, _finish_report_timing(execute_report, started_perf=report_started_perf)

    effective_trigger_context_run_id = str(report.get("trigger_context_run_id") or trigger_context_run_id)
    effective_for_trade_date = str(report.get("for_trade_date") or for_trade_date)
    effective_source_condition_run_id = str(report.get("source_condition_run_id") or source_condition_run_id)
    runner = command_runner or _default_command_runner
    child_reports: list[dict[str, Any]] = []
    for family, item in selected_children:
        argv = _runtime_child_argv(
            item,
            family=family,
            python_executable=python_executable or DEFAULT_PYTHON_EXECUTABLE,
            trigger_context_run_id=effective_trigger_context_run_id,
            for_trade_date=effective_for_trade_date,
            source_condition_run_id=effective_source_condition_run_id,
            dsn=dsn,
        )
        child_started_at, child_started_perf = _start_phase()
        result = _normalize_command_result(runner(argv))
        child_timing = _child_timing_fields(started_at=child_started_at, started_perf=child_started_perf)
        child_report = {
            "family": family,
            "argv": _redact_child_argv_for_report(argv),
            "returncode": result["returncode"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            **child_timing,
        }
        child_reports.append(child_report)
        child_phase_name = f"{family}_child_execution"
        child_phase_status = "blocked" if result["returncode"] != 0 else "passed"
        _append_phase(
            report,
            phase_name=child_phase_name,
            started_at=child_started_at,
            started_perf=child_started_perf,
            status=child_phase_status,
            child_step=family,
        )
        if result["returncode"] != 0:
            blocked_report = dict(report)
            blocked_report.update({"result": "blocked", "status": "blocked", "mode": "execute"})
            blocked_report["child_execution"] = {
                "executed_child_command_count": len(child_reports),
                "children": child_reports,
                "stopped_after_failure": True,
                "selected_child_order_policy": SELECTED_CHILD_ORDER_POLICY,
                "selected_child_order": selected_child_order,
            }
            side_effects = dict(SIDE_EFFECTS_FALSE)
            side_effects["child_executed"] = True
            blocked_report["side_effects"] = side_effects
            blocked_report["forbidden_operation_proof"] = _forbidden_operation_proof(child_executed=True)
            blocked_report["error"] = f"{family} child command failed with returncode={result['returncode']}"
            closeout_started_at, closeout_started_perf = _start_phase()
            _append_phase(
                blocked_report,
                phase_name="report_closeout",
                started_at=closeout_started_at,
                started_perf=closeout_started_perf,
                status="blocked",
            )
            return result["returncode"] or 2, _finish_report_timing(blocked_report, started_perf=report_started_perf)

    passed_report = dict(report)
    passed_report.update({"result": "passed", "status": "passed", "mode": "execute"})
    passed_report["child_execution"] = {
        "executed_child_command_count": len(child_reports),
        "children": child_reports,
        "stopped_after_failure": False,
        "selected_child_order_policy": SELECTED_CHILD_ORDER_POLICY,
        "selected_child_order": selected_child_order,
    }
    side_effects = dict(SIDE_EFFECTS_FALSE)
    side_effects["child_executed"] = True
    passed_report["side_effects"] = side_effects
    passed_report["forbidden_operation_proof"] = _forbidden_operation_proof(child_executed=True)
    closeout_started_at, closeout_started_perf = _start_phase()
    _append_phase(
        passed_report,
        phase_name="report_closeout",
        started_at=closeout_started_at,
        started_perf=closeout_started_perf,
        status="passed",
    )
    return 0, _finish_report_timing(passed_report, started_perf=report_started_perf)


def _selected_child_items(selected: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    items: list[tuple[str, Mapping[str, Any]]] = []
    for family in ("hint", "ordinary"):
        item = selected.get(family)
        if item:
            items.append((family, item))
    return items


def _selected_child_order(selected: Mapping[str, Any]) -> list[str]:
    return [family for family, _ in _selected_child_items(selected)]


def _default_command_runner(argv: Sequence[str]) -> dict[str, Any]:
    completed = subprocess.run(list(argv), text=True, capture_output=True, check=False)
    return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def _normalize_command_result(result: Any) -> dict[str, Any]:
    if isinstance(result, Mapping):
        return {
            "returncode": int(result.get("returncode") or 0),
            "stdout": str(result.get("stdout") or ""),
            "stderr": str(result.get("stderr") or ""),
        }
    return {
        "returncode": int(getattr(result, "returncode", 0) or 0),
        "stdout": str(getattr(result, "stdout", "") or ""),
        "stderr": str(getattr(result, "stderr", "") or ""),
    }


def _empty_child_execution(*, selected_child_order: Sequence[str] | None = None) -> dict[str, Any]:
    return {
        "executed_child_command_count": 0,
        "children": [],
        "stopped_after_failure": False,
        "selected_child_order_policy": SELECTED_CHILD_ORDER_POLICY,
        "selected_child_order": list(selected_child_order or []),
    }


def _blocked_poll_report(error: str, *, timing: dict[str, Any] | None = None, started_perf: float | None = None) -> tuple[int, dict[str, Any]]:
    report = {
            "result": "blocked",
            "status": "blocked",
            "mode": "blocked",
            "error": error,
            "child_execution": _empty_child_execution(),
            "side_effects": dict(SIDE_EFFECTS_FALSE),
            "forbidden_operation_proof": _forbidden_operation_proof(child_executed=False),
    }
    if timing is not None:
        report["timing"] = timing
    if started_perf is not None:
        _finish_report_timing(report, started_perf=started_perf)
    return 2, report


def discover_proofs_from_db(
    *,
    dsn: str,
    for_trade_date: str,
    source_trade_date: str,
    selection_mode: str = SELECTION_MODE_REALTIME,
    mode: str = "both",
) -> dict[str, Any]:
    """Read N3 proof candidates and existing N4 targets from PostgreSQL."""

    if not dsn:
        raise ProofDiscoveryBlocked("dsn is required for DB proof discovery")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as exc:  # pragma: no cover - import failures are surfaced by CLI reports
        raise ProofDiscoveryBlocked(f"psycopg unavailable for proof discovery: {exc}") from exc

    with psycopg.connect(dsn, row_factory=dict_row, options="-c default_transaction_read_only=on") as conn:
        conn.execute("BEGIN READ ONLY")
        with conn.cursor() as cur:
            if mode == "ordinary" and selection_mode == SELECTION_MODE_REALTIME:
                return _db_ordinary_realtime_latest_fast_discovery(
                    cur,
                    for_trade_date=for_trade_date,
                    source_trade_date=source_trade_date,
                )
            if mode == "hint" and selection_mode == SELECTION_MODE_REALTIME:
                return _db_hint_realtime_latest_fast_discovery(
                    cur,
                    for_trade_date=for_trade_date,
                    source_trade_date=source_trade_date,
                )
            ordinary_source_like = "realtime_action_confirmation_metric_%current_period_avg_v1%"
            hint_source_like = "realtime_hint_projection_metric_%index_board_1m_hint_projection_v1_midday_bridge_v1%"
            cur.execute(
                """
                SELECT run_id, status, for_trade_date, source_trade_date, source_condition_run_id
                FROM common_market_data_run
                WHERE for_trade_date = %s
                  AND source_trade_date = %s
                  AND status = 'passed'
                  AND (
                    run_id LIKE %s
                    OR run_id LIKE %s
                  )
                ORDER BY run_id
                """,
                (for_trade_date, source_trade_date, ordinary_source_like, hint_source_like),
            )
            market_runs = [dict(row) for row in cur.fetchall()]
            existing_targets = _db_existing_targets(cur, for_trade_date=for_trade_date)
            ordinary_runs = []
            hint_runs = []
            for run in market_runs:
                run_id = str(run["run_id"])
                if ORDINARY_SOURCE_RE.match(run_id):
                    ordinary_runs.append(run)
                elif HINT_SOURCE_RE.match(run_id):
                    hint_runs.append(run)
            ordinary_candidates = _db_candidates_for_selection_mode(
                cur,
                family="ordinary",
                runs=ordinary_runs,
                existing_targets=existing_targets,
                for_trade_date=for_trade_date,
                source_trade_date=source_trade_date,
                selection_mode=selection_mode,
            )
            hint_candidates = _db_candidates_for_selection_mode(
                cur,
                family="hint",
                runs=hint_runs,
                existing_targets=existing_targets,
                for_trade_date=for_trade_date,
                source_trade_date=source_trade_date,
                selection_mode=selection_mode,
            )
    return {
        "ordinary_candidates": ordinary_candidates,
        "hint_candidates": hint_candidates,
        "existing_targets": existing_targets,
        "discovery_policy": "full_discovery_v1",
    }


def _db_ordinary_realtime_latest_fast_discovery(
    cur: Any,
    *,
    for_trade_date: str,
    source_trade_date: str,
) -> dict[str, Any]:
    ordinary_source_like = "realtime_action_confirmation_metric_%current_period_avg_v1%"
    cur.execute(
        """
        SELECT run_id, status, for_trade_date, source_trade_date, source_condition_run_id
        FROM common_market_data_run
        WHERE for_trade_date = %s
          AND source_trade_date = %s
          AND status = 'passed'
          AND run_id LIKE %s
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (for_trade_date, source_trade_date, ordinary_source_like),
    )
    rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return {
            "ordinary_candidates": [],
            "hint_candidates": [],
            "existing_targets": [],
            "discovery_policy": "ordinary_realtime_latest_fast_path_v1",
            "no_candidate_reason": "no_latest_ordinary_source_run",
        }

    candidate = _db_ordinary_candidate(cur, rows[0])
    parsed = _parse_source_candidate("ordinary", candidate, for_trade_date=for_trade_date, source_trade_date=source_trade_date)
    if not parsed:
        return {
            "ordinary_candidates": [candidate],
            "hint_candidates": [],
            "existing_targets": [],
            "discovery_policy": "ordinary_realtime_latest_fast_path_v1",
            "no_candidate_reason": "latest_ordinary_run_id_invalid",
        }

    target_run_id = _target_run_id_for_candidate("ordinary", str(candidate["run_id"]), parsed)
    target_rows = _db_target_rows_by_run_ids(cur, [target_run_id])
    previous_target_row = _db_previous_ordinary_target_row(
        cur,
        for_trade_date=for_trade_date,
        before_target_run_id=target_run_id,
    )
    if previous_target_row:
        target_rows.append(previous_target_row)
    return {
        "ordinary_candidates": [candidate],
        "hint_candidates": [],
        "existing_targets": _db_targets_from_rows(cur, target_rows),
        "discovery_policy": "ordinary_realtime_latest_fast_path_v1",
    }


def _db_hint_realtime_latest_fast_discovery(
    cur: Any,
    *,
    for_trade_date: str,
    source_trade_date: str,
) -> dict[str, Any]:
    hint_source_like = "realtime_hint_projection_metric_%index_board_1m_hint_projection_v1_midday_bridge_v1%"
    cur.execute(
        """
        SELECT run_id, status, for_trade_date, source_trade_date, source_condition_run_id
        FROM common_market_data_run
        WHERE for_trade_date = %s
          AND source_trade_date = %s
          AND status = 'passed'
          AND run_id LIKE %s
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (for_trade_date, source_trade_date, hint_source_like),
    )
    rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return {
            "ordinary_candidates": [],
            "hint_candidates": [],
            "existing_targets": [],
            "discovery_policy": "hint_realtime_latest_fast_path_v1",
            "no_candidate_reason": "no_latest_hint_source_run",
        }

    candidate = _db_hint_candidate(cur, rows[0])
    parsed = _parse_source_candidate("hint", candidate, for_trade_date=for_trade_date, source_trade_date=source_trade_date)
    if not parsed:
        return {
            "ordinary_candidates": [],
            "hint_candidates": [candidate],
            "existing_targets": [],
            "discovery_policy": "hint_realtime_latest_fast_path_v1",
            "no_candidate_reason": "latest_hint_run_id_invalid",
        }

    target_run_id = _target_run_id_for_candidate("hint", str(candidate["run_id"]), parsed)
    target_rows = _db_target_rows_by_run_ids(cur, [target_run_id])
    previous_target_row = _db_previous_hint_target_row(
        cur,
        for_trade_date=for_trade_date,
        before_target_run_id=target_run_id,
    )
    if previous_target_row:
        target_rows.append(previous_target_row)
    return {
        "ordinary_candidates": [],
        "hint_candidates": [candidate],
        "existing_targets": _db_targets_from_rows(cur, target_rows),
        "discovery_policy": "hint_realtime_latest_fast_path_v1",
    }


def _db_target_rows_by_run_ids(cur: Any, run_ids: Sequence[str]) -> list[dict[str, Any]]:
    clean_run_ids = [str(run_id) for run_id in run_ids if str(run_id)]
    if not clean_run_ids:
        return []
    cur.execute(
        """
        SELECT to_jsonb(r) AS j
        FROM common_trigger_run r
        WHERE run_id = ANY(%s)
        ORDER BY run_id
        """,
        (clean_run_ids,),
    )
    return [dict(row["j"]) for row in cur.fetchall()]


def _db_previous_ordinary_target_row(cur: Any, *, for_trade_date: str, before_target_run_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT to_jsonb(r) AS j
        FROM common_trigger_run r
        WHERE for_trade_date = %s
          AND status = 'passed'
          AND run_id LIKE %s
          AND run_id < %s
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (for_trade_date, f"trigger_provisional_ordinary_{for_trade_date}_until_%", before_target_run_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return dict(row["j"])


def _db_previous_hint_target_row(cur: Any, *, for_trade_date: str, before_target_run_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT to_jsonb(r) AS j
        FROM common_trigger_run r
        WHERE for_trade_date = %s
          AND status = 'passed'
          AND run_id LIKE %s
          AND run_id < %s
        ORDER BY run_id DESC
        LIMIT 1
        """,
        (for_trade_date, f"trigger_provisional_b2_{for_trade_date}_until_%", before_target_run_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    return dict(row["j"])


def _db_candidates_for_selection_mode(
    cur: Any,
    *,
    family: str,
    runs: Sequence[Mapping[str, Any]],
    existing_targets: Sequence[Mapping[str, Any]],
    for_trade_date: str,
    source_trade_date: str,
    selection_mode: str,
) -> list[dict[str, Any]]:
    if selection_mode != SELECTION_MODE_REALTIME:
        return [_db_candidate_with_contract_counts(cur, family=family, run=run) for run in runs]

    parsed_runs: list[tuple[dict[str, str], Mapping[str, Any]]] = []
    for run in runs:
        parsed = _parse_source_candidate(family, run, for_trade_date=for_trade_date, source_trade_date=source_trade_date)
        if parsed:
            parsed_runs.append((parsed, run))
    parsed_runs.sort(key=lambda item: (item[0]["until_hhmm"], str(item[1].get("run_id") or "")), reverse=True)

    candidates: list[dict[str, Any]] = []
    for index, (_parsed, run) in enumerate(parsed_runs):
        if index == 0:
            candidates.append(_db_candidate_with_contract_counts(cur, family=family, run=run))
        else:
            candidates.append(_db_candidate_without_contract_counts(family=family, run=run))
    return candidates


def _db_candidate_with_contract_counts(cur: Any, *, family: str, run: Mapping[str, Any]) -> dict[str, Any]:
    if family == "ordinary":
        return _db_ordinary_candidate(cur, run)
    return _db_hint_candidate(cur, run)


def _db_candidate_without_contract_counts(*, family: str, run: Mapping[str, Any]) -> dict[str, Any]:
    expected_role = "trigger_proof" if family == "ordinary" else "hint_trigger_proof"
    return {
        **dict(run),
        "proof_family": family,
        "metric_role": expected_role,
        "proof_owner": "N3",
        "proof_consumer": "N4",
        "not_n5_final_proof": True,
        "contract_validation_deferred": True,
    }


def _db_ordinary_candidate(cur: Any, run: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(run["run_id"])
    by_asset: dict[str, int] = {}
    contract_counts = {"metric_role": 0, "proof_owner": 0, "proof_consumer": 0, "not_n5_final_proof": 0}
    for asset_kind, table_name in (
        ("stock", "stock_action_confirmation_projection_metric"),
        ("index", "index_action_confirmation_projection_metric"),
        ("board", "board_action_confirmation_projection_metric"),
    ):
        counts = _proof_contract_counts(cur, table_name=table_name, run_id=run_id, role="trigger_proof")
        by_asset[asset_kind] = int(counts["row_count"])
        for key in contract_counts:
            contract_counts[key] += int(counts[key])
    row_count = sum(by_asset.values())
    return {
        **dict(run),
        "proof_family": "ordinary",
        "metric_role": "trigger_proof" if contract_counts["metric_role"] == row_count else "",
        "proof_owner": "N3" if contract_counts["proof_owner"] == row_count else "",
        "proof_consumer": "N4" if contract_counts["proof_consumer"] == row_count else "",
        "not_n5_final_proof": contract_counts["not_n5_final_proof"] == row_count,
        "row_count": row_count,
        "stock_row_count": by_asset["stock"],
        "index_row_count": by_asset["index"],
        "board_row_count": by_asset["board"],
    }


def _db_hint_candidate(cur: Any, run: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(run["run_id"])
    by_asset: dict[str, int] = {"stock": 0}
    contract_counts = {"metric_role": 0, "proof_owner": 0, "proof_consumer": 0, "not_n5_final_proof": 0}
    for asset_kind, table_name in (
        ("index", "index_realtime_hint_projection_metric"),
        ("board", "board_realtime_hint_projection_metric"),
    ):
        counts = _proof_contract_counts(cur, table_name=table_name, run_id=run_id, role="hint_trigger_proof")
        by_asset[asset_kind] = int(counts["row_count"])
        for key in contract_counts:
            contract_counts[key] += int(counts[key])
    row_count = by_asset["index"] + by_asset["board"]
    return {
        **dict(run),
        "proof_family": "hint",
        "metric_role": "hint_trigger_proof" if contract_counts["metric_role"] == row_count else "",
        "proof_owner": "N3" if contract_counts["proof_owner"] == row_count else "",
        "proof_consumer": "N4" if contract_counts["proof_consumer"] == row_count else "",
        "not_n5_final_proof": contract_counts["not_n5_final_proof"] == row_count,
        "row_count": row_count,
        "stock_row_count": 0,
        "index_row_count": by_asset["index"],
        "board_row_count": by_asset["board"],
    }


def _proof_contract_counts(cur: Any, *, table_name: str, run_id: str, role: str) -> dict[str, int]:
    cur.execute(
        f"""
        WITH rows AS (
          SELECT to_jsonb(t) AS j
          FROM {table_name} t
          WHERE projection_run_id = %s
        )
        SELECT count(*)::int AS row_count,
               count(*) FILTER (
                 WHERE coalesce(j->>'metric_role', j#>>'{{raw_json,metric_role}}') = %s
               )::int AS metric_role,
               count(*) FILTER (
                 WHERE coalesce(j->>'proof_owner', j#>>'{{raw_json,proof_owner}}') = 'N3'
               )::int AS proof_owner,
               count(*) FILTER (
                 WHERE coalesce(j->>'proof_consumer', j#>>'{{raw_json,proof_consumer}}') = 'N4'
               )::int AS proof_consumer,
               count(*) FILTER (
                 WHERE lower(coalesce(j->>'not_n5_final_proof', j#>>'{{raw_json,not_n5_final_proof}}', '')) = 'true'
               )::int AS not_n5_final_proof
        FROM rows
        """,
        (run_id, role),
    )
    return dict(cur.fetchone())


def _db_existing_targets(cur: Any, *, for_trade_date: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT to_jsonb(r) AS j
        FROM common_trigger_run r
        WHERE for_trade_date = %s
          AND (
            run_id LIKE %s
            OR run_id LIKE %s
          )
        ORDER BY run_id
        """,
        (for_trade_date, "trigger_provisional_ordinary_%", "trigger_provisional_b2_%"),
    )
    rows = [dict(row["j"]) for row in cur.fetchall()]
    return _db_targets_from_rows(cur, rows)


def _db_targets_from_rows(cur: Any, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    run_ids = [str(row.get("run_id") or "") for row in rows if str(row.get("run_id") or "")]
    if not run_ids:
        return []

    state_counts = _batch_count_trigger_table(cur, "common_trigger_state", run_ids)
    match_counts = _batch_count_trigger_table(cur, "common_trigger_match", run_ids)
    outbox_counts = _batch_count_outbox(cur, run_ids)
    inbox_counts = _batch_count_inbox_refs(cur, run_ids)
    checkpoint_counts = _batch_count_checkpoint_refs(cur, run_ids)
    optional_counts = _batch_count_optional_source_trigger_refs(
        cur,
        run_ids,
        tables=(
            "common_action_run",
            "common_action_event",
            "common_action_quality_item",
            "common_action_tracking_state",
            "stock_action_fact",
            "index_action_fact",
            "board_action_fact",
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "user_signal_card_projection",
            "user_signal_projection_event",
            "user_notification_queue",
            "user_card_projection",
            "user_voice_delivery",
            "user_device_ack",
            "n6_virtual_account",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "user_sim_order",
            "user_sim_trade",
            "user_sim_position",
        ),
    )

    targets: list[dict[str, Any]] = []
    for j in rows:
        run_id = str(j.get("run_id") or "")
        outbox = outbox_counts.get(run_id, {})
        targets.append(
            {
                "run_id": run_id,
                "status": str(j.get("status") or ""),
                "source_run_id": str(j.get("source_market_data_run_id") or j.get("source_projection_run_id") or ""),
                "previous_trigger_run_id": str(_nested_json(j, "raw_json", "previous_trigger_run_id") or ""),
                "run_state_count": int(j.get("trigger_state_row_count") or 0),
                "run_match_count": int(j.get("trigger_match_row_count") or 0),
                "run_outbox_count": int(j.get("trigger_event_outbox_count") or 0),
                "state_count": int(state_counts.get(run_id, 0)),
                "match_count": int(match_counts.get(run_id, 0)),
                "outbox_count": int(outbox.get("outbox_count", 0)),
                "outbox_delivered_delivering": int(outbox.get("outbox_delivered_delivering", 0)),
                "downstream_ref_count": int(inbox_counts.get(run_id, 0))
                + int(checkpoint_counts.get(run_id, 0))
                + int(optional_counts.get(run_id, 0)),
            }
        )
    return targets


def _batch_count_trigger_table(cur: Any, table_name: str, run_ids: Sequence[str]) -> dict[str, int]:
    if not run_ids:
        return {}
    cur.execute(
        f"""
        SELECT run_id, count(*)::int AS count
        FROM {table_name}
        WHERE run_id = ANY(%s)
        GROUP BY run_id
        """,
        (list(run_ids),),
    )
    return {str(row["run_id"]): int(row["count"] or 0) for row in cur.fetchall()}


def _batch_count_outbox(cur: Any, run_ids: Sequence[str]) -> dict[str, dict[str, int]]:
    if not run_ids:
        return {}
    cur.execute(
        """
        SELECT source_run_id,
               count(*)::int AS outbox_count,
               count(*) FILTER (WHERE status = ANY(%s))::int AS outbox_delivered_delivering
        FROM common_event_outbox
        WHERE source_layer = 'N4_trigger'
          AND source_run_id = ANY(%s)
        GROUP BY source_run_id
        """,
        (["delivered", "delivering"], list(run_ids)),
    )
    return {
        str(row["source_run_id"]): {
            "outbox_count": int(row["outbox_count"] or 0),
            "outbox_delivered_delivering": int(row["outbox_delivered_delivering"] or 0),
        }
        for row in cur.fetchall()
    }


def _batch_count_inbox_refs(cur: Any, run_ids: Sequence[str]) -> dict[str, int]:
    if not run_ids:
        return {}
    cur.execute(
        """
        SELECT source_run_id, count(*)::int AS count
        FROM common_event_inbox
        WHERE source_run_id = ANY(%s)
        GROUP BY source_run_id
        """,
        (list(run_ids),),
    )
    return {str(row["source_run_id"]): int(row["count"] or 0) for row in cur.fetchall()}


def _batch_count_checkpoint_refs(cur: Any, run_ids: Sequence[str]) -> dict[str, int]:
    if not run_ids:
        return {}
    cur.execute(
        """
        WITH refs AS (
          SELECT DISTINCT o.source_run_id, c.consumer_name, c.partition_key, c.source_layer
          FROM common_event_consumer_checkpoint c
          JOIN common_event_outbox o
            ON o.event_id = c.last_event_id
            OR o.outbox_id = c.last_outbox_id
          WHERE o.source_run_id = ANY(%s)
        )
        SELECT source_run_id, count(*)::int AS count
        FROM refs
        GROUP BY source_run_id
        """,
        (list(run_ids),),
    )
    return {str(row["source_run_id"]): int(row["count"] or 0) for row in cur.fetchall()}


def _count_trigger_table(cur: Any, table_name: str, run_id: str) -> int:
    cur.execute(f"SELECT count(*)::int AS count FROM {table_name} WHERE run_id = %s", (run_id,))
    return int(cur.fetchone()["count"])


def _count_outbox(cur: Any, run_id: str, *, statuses: Sequence[str]) -> int:
    if statuses:
        cur.execute(
            """
            SELECT count(*)::int AS count
            FROM common_event_outbox
            WHERE source_layer = 'N4_trigger'
              AND source_run_id = %s
              AND status = ANY(%s)
            """,
            (run_id, list(statuses)),
        )
    else:
        cur.execute(
            """
            SELECT count(*)::int AS count
            FROM common_event_outbox
            WHERE source_layer = 'N4_trigger'
              AND source_run_id = %s
            """,
            (run_id,),
        )
    return int(cur.fetchone()["count"])


def _count_existing_target_downstream_refs(cur: Any, run_id: str) -> int:
    total = 0
    cur.execute("SELECT count(*)::int AS count FROM common_event_inbox WHERE source_run_id = %s", (run_id,))
    total += int(cur.fetchone()["count"])
    cur.execute(
        """
        SELECT count(*)::int AS count
        FROM common_event_consumer_checkpoint c
        WHERE EXISTS (
          SELECT 1
          FROM common_event_outbox o
          WHERE o.source_run_id = %s
            AND (o.event_id = c.last_event_id OR o.outbox_id = c.last_outbox_id)
        )
        """,
        (run_id,),
    )
    total += int(cur.fetchone()["count"])
    total += _count_optional_source_trigger_refs(
        cur,
        run_id,
        tables=(
            "common_action_run",
            "common_action_event",
            "common_action_quality_item",
            "common_action_tracking_state",
            "stock_action_fact",
            "index_action_fact",
            "board_action_fact",
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "user_signal_card_projection",
            "user_signal_projection_event",
            "user_notification_queue",
            "user_card_projection",
            "user_voice_delivery",
            "user_device_ack",
            "n6_virtual_account",
            "n6_virtual_order",
            "n6_virtual_trade",
            "n6_virtual_position",
            "user_sim_order",
            "user_sim_trade",
            "user_sim_position",
        ),
    )
    return total


def _count_optional_source_trigger_refs(cur: Any, run_id: str, *, tables: Sequence[str]) -> int:
    total = 0
    for table_name in tables:
        cur.execute("SELECT to_regclass(%s) AS regclass", (table_name,))
        if _row_value(cur.fetchone(), "regclass") is None:
            continue
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = %s
                AND column_name = 'source_trigger_run_id'
            ) AS has_column
            """,
            (table_name,),
        )
        if not _row_value(cur.fetchone(), "has_column"):
            continue
        cur.execute(f"SELECT count(*)::int AS count FROM {table_name} WHERE source_trigger_run_id = %s", (run_id,))
        total += int(_row_value(cur.fetchone(), "count") or 0)
    return total


def _batch_count_optional_source_trigger_refs(cur: Any, run_ids: Sequence[str], *, tables: Sequence[str]) -> dict[str, int]:
    totals = {str(run_id): 0 for run_id in run_ids}
    if not run_ids:
        return {}
    for table_name in tables:
        cur.execute("SELECT to_regclass(%s) AS regclass", (table_name,))
        if _row_value(cur.fetchone(), "regclass") is None:
            continue
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = %s
                AND column_name = 'source_trigger_run_id'
            ) AS has_column
            """,
            (table_name,),
        )
        if not _row_value(cur.fetchone(), "has_column"):
            continue
        cur.execute(
            f"""
            SELECT source_trigger_run_id, count(*)::int AS count
            FROM {table_name}
            WHERE source_trigger_run_id = ANY(%s)
            GROUP BY source_trigger_run_id
            """,
            (list(run_ids),),
        )
        for row in cur.fetchall():
            run_id = str(_row_value(row, "source_trigger_run_id") or "")
            if run_id:
                totals[run_id] = totals.get(run_id, 0) + int(_row_value(row, "count") or 0)
    return totals


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _select_family_candidate(
    *,
    family: str,
    candidates: Sequence[Mapping[str, Any]],
    existing_targets: Sequence[Mapping[str, Any]],
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    trigger_context_run_id: str,
    python_executable: str,
    dsn: str,
    selection_mode: str,
    skipped: list[dict[str, str]],
) -> dict[str, Any] | None:
    parsed_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        parsed = _parse_source_candidate(family, candidate, for_trade_date=for_trade_date, source_trade_date=source_trade_date)
        if not parsed:
            skipped.append({"family": family, "source_run_id": str(candidate.get("run_id") or ""), "reason": f"{family}_run_id_invalid"})
            continue
        target_run_id = _target_run_id_for_candidate(family, str(candidate["run_id"]), parsed)
        previous_trigger_run_id = _previous_target_for_candidate(family, parsed, existing_targets)
        parsed_candidates.append(
            {
                "candidate": dict(candidate),
                "parsed": parsed,
                "target_run_id": target_run_id,
                "previous_trigger_run_id": previous_trigger_run_id,
            }
        )

    parsed_candidates.sort(key=lambda item: (item["parsed"]["until_hhmm"], str(item["candidate"]["run_id"])), reverse=True)
    if not parsed_candidates:
        return None
    if selection_mode == SELECTION_MODE_REALTIME:
        chosen = parsed_candidates[0]
        contract_reason = _candidate_contract_blocker(family, chosen["candidate"])
        if contract_reason:
            raise ProofDiscoveryBlocked(
                f"latest {family} candidate contract invalid: {contract_reason}: {chosen['candidate'].get('run_id')}"
            )
        for backlog in parsed_candidates[1:]:
            exact_backlog_target = _existing_target(existing_targets, str(backlog["target_run_id"]))
            if exact_backlog_target:
                _skip_existing_realtime_backlog_target(
                    skipped,
                    family=family,
                    candidate=backlog["candidate"],
                    target=exact_backlog_target,
                    previous_trigger_run_id=str(backlog["previous_trigger_run_id"]),
                )
            else:
                _skip_manual_backlog(skipped, family=family, source_run_id=str(backlog["candidate"]["run_id"]))
        exact_target = _existing_target(existing_targets, str(chosen["target_run_id"]))
        if exact_target:
            _skip_existing_realtime_latest_target(
                skipped,
                family=family,
                candidate=chosen["candidate"],
                target=exact_target,
                previous_trigger_run_id=str(chosen["previous_trigger_run_id"]),
            )
            return None
        return _selected_item_for_candidate(
            family=family,
            chosen=chosen,
            python_executable=python_executable,
            trigger_context_run_id=trigger_context_run_id,
            for_trade_date=for_trade_date,
            source_condition_run_id=source_condition_run_id,
            dsn=dsn,
        )

    unprocessed: list[dict[str, Any]] = []
    for item in parsed_candidates:
        contract_reason = _candidate_contract_blocker(family, item["candidate"])
        if contract_reason:
            skipped.append({"family": family, "source_run_id": str(item["candidate"].get("run_id") or ""), "reason": contract_reason})
            continue
        exact_target = _existing_target(existing_targets, str(item["target_run_id"]))
        if exact_target:
            _skip_existing_target(
                skipped,
                family=family,
                candidate=item["candidate"],
                target=exact_target,
                previous_trigger_run_id=str(item["previous_trigger_run_id"]),
            )
            continue
        unprocessed.append(item)
    if not unprocessed:
        return None
    chosen = unprocessed[0]
    for backlog in unprocessed[1:]:
        skipped.append(
            {
                "family": family,
                "source_run_id": str(backlog["candidate"]["run_id"]),
                "reason": "backlog_older_than_selected_latest",
            }
        )
    return _selected_item_for_candidate(
        family=family,
        chosen=chosen,
        python_executable=python_executable,
        trigger_context_run_id=trigger_context_run_id,
        for_trade_date=for_trade_date,
        source_condition_run_id=source_condition_run_id,
        dsn=dsn,
    )


def _skip_existing_target(
    skipped: list[dict[str, str]],
    *,
    family: str,
    candidate: Mapping[str, Any],
    target: Mapping[str, Any],
    previous_trigger_run_id: str,
) -> None:
    compat_metadata = _assert_existing_target_safe(
        target,
        source_run_id=str(candidate["run_id"]),
        previous_trigger_run_id=previous_trigger_run_id,
        expected_counts=_expected_counts(candidate),
    )
    skipped_item = {"family": family, "source_run_id": str(candidate["run_id"]), "reason": "already_passed_exact_target"}
    skipped_item.update(compat_metadata)
    skipped.append(skipped_item)


def _skip_existing_realtime_backlog_target(
    skipped: list[dict[str, str]],
    *,
    family: str,
    candidate: Mapping[str, Any],
    target: Mapping[str, Any],
    previous_trigger_run_id: str,
) -> None:
    compat_metadata = _assert_existing_target_safe(
        target,
        source_run_id=str(candidate["run_id"]),
        previous_trigger_run_id=previous_trigger_run_id,
        expected_counts=_expected_counts(candidate),
        allow_downstream_refs=True,
    )
    downstream_ref_count = int(target.get("downstream_ref_count") or 0)
    skipped_item = {"family": family, "source_run_id": str(candidate["run_id"]), "reason": "already_passed_exact_target"}
    if downstream_ref_count:
        skipped_item.update(
            {
                "reason": "already_passed_exact_backlog_target_with_downstream_refs",
                "downstream_ref_count": str(downstream_ref_count),
                "downstream_ref_policy": "ignored_for_realtime_backlog",
            }
        )
    skipped_item.update(compat_metadata)
    skipped.append(skipped_item)


def _skip_existing_realtime_latest_target(
    skipped: list[dict[str, str]],
    *,
    family: str,
    candidate: Mapping[str, Any],
    target: Mapping[str, Any],
    previous_trigger_run_id: str,
) -> None:
    compat_metadata = _assert_existing_target_safe(
        target,
        source_run_id=str(candidate["run_id"]),
        previous_trigger_run_id=previous_trigger_run_id,
        expected_counts=_expected_counts(candidate),
        allow_downstream_refs=True,
    )
    downstream_ref_count = int(target.get("downstream_ref_count") or 0)
    skipped_item = {"family": family, "source_run_id": str(candidate["run_id"]), "reason": "already_passed_exact_target"}
    if downstream_ref_count:
        skipped_item.update(
            {
                "reason": "already_passed_exact_target_with_downstream_refs",
                "downstream_ref_count": str(downstream_ref_count),
                "downstream_ref_policy": "ignored_for_realtime_latest",
            }
        )
    skipped_item.update(compat_metadata)
    skipped.append(skipped_item)


def _skip_manual_backlog(skipped: list[dict[str, str]], *, family: str, source_run_id: str) -> None:
    skipped.append(
        {
            "family": family,
            "source_run_id": source_run_id,
            "reason": "backlog_requires_manual_catchup",
        }
    )


def _selected_item_for_candidate(
    *,
    family: str,
    chosen: Mapping[str, Any],
    python_executable: str,
    trigger_context_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    dsn: str,
) -> dict[str, Any]:
    base_argv = _child_argv_plan_only(
        family=family,
        python_executable=python_executable,
        trigger_context_run_id=trigger_context_run_id,
        source_run_id=str(chosen["candidate"]["run_id"]),
        target_run_id=str(chosen["target_run_id"]),
        for_trade_date=for_trade_date,
        until_hhmm=str(chosen["parsed"]["until_hhmm"]),
        source_condition_run_id=source_condition_run_id,
        previous_trigger_run_id=str(chosen["previous_trigger_run_id"]),
        dsn=dsn,
        redact_dsn_for_report=True,
    )
    return {
        "family": family,
        "source_run_id": str(chosen["candidate"]["run_id"]),
        "target_run_id": str(chosen["target_run_id"]),
        "until_hhmm": str(chosen["parsed"]["until_hhmm"]),
        "previous_trigger_run_id": str(chosen["previous_trigger_run_id"]),
        "baseline_mode": "exact_previous_baseline" if chosen["previous_trigger_run_id"] else "no_previous_baseline",
        "child_argv_plan_only": base_argv,
        "child_argv_for_execute": [*base_argv, "--execute", "--user-confirmed"],
    }


def _parse_source_candidate(
    family: str,
    candidate: Mapping[str, Any],
    *,
    for_trade_date: str,
    source_trade_date: str,
) -> dict[str, str] | None:
    run_id = str(candidate.get("run_id") or "")
    matched = ORDINARY_SOURCE_RE.match(run_id) if family == "ordinary" else HINT_SOURCE_RE.match(run_id)
    if not matched:
        return None
    parsed = matched.groupdict()
    if parsed["for_trade_date"] != for_trade_date or parsed["source_trade_date"] != source_trade_date:
        return None
    return parsed


def _candidate_contract_blocker(family: str, candidate: Mapping[str, Any]) -> str:
    if str(candidate.get("proof_family") or "") != family:
        return f"{family}_contract_invalid"
    expected_role = "trigger_proof" if family == "ordinary" else "hint_trigger_proof"
    if str(candidate.get("status") or "") != "passed":
        return f"{family}_status_not_passed"
    if int(candidate.get("row_count") or 0) <= 0:
        return f"{family}_row_count_zero"
    if str(candidate.get("metric_role") or "") != expected_role:
        return f"{family}_contract_invalid"
    if str(candidate.get("proof_owner") or "") != "N3" or str(candidate.get("proof_consumer") or "") != "N4":
        return f"{family}_contract_invalid"
    if bool(candidate.get("not_n5_final_proof")) is not True:
        return f"{family}_contract_invalid"
    if family == "hint" and int(candidate.get("stock_row_count") or 0) != 0:
        return "hint_stock_scope_violation"
    return ""


def _target_run_id_for_candidate(family: str, source_run_id: str, parsed: Mapping[str, str]) -> str:
    if family == "ordinary":
        return build_n4p_ordinary_trigger_run_id(
            for_trade_date=parsed["for_trade_date"],
            until_hhmm=parsed["until_hhmm"],
            asset_scope="asset_all",
            source_metric_run_id=source_run_id,
            rule_suffix="atomic_rule_v1",
            n4_rule_suffix="period_rollover_guard_v1",
        )
    return build_provisional_projection_trigger_run_id(
        for_trade_date=parsed["for_trade_date"],
        until_hhmm=parsed["until_hhmm"],
        source_metric_run_id=source_run_id,
        rule_suffix="atomic_rule_v1",
    )


def _previous_target_for_candidate(
    family: str,
    parsed_candidate: Mapping[str, str],
    existing_targets: Sequence[Mapping[str, Any]],
) -> str:
    candidates: list[tuple[str, str]] = []
    for target in existing_targets:
        run_id = str(target.get("run_id") or "")
        if str(target.get("status") or "") != "passed":
            continue
        parsed = _parse_target_by_family(family, run_id)
        if not parsed:
            continue
        if parsed["for_trade_date"] != parsed_candidate["for_trade_date"]:
            continue
        if parsed["until_hhmm"] >= parsed_candidate["until_hhmm"]:
            continue
        candidates.append((parsed["until_hhmm"], run_id))
    if not candidates:
        return ""
    return sorted(candidates)[-1][1]


def _parse_target_by_family(family: str, run_id: str) -> dict[str, str] | None:
    try:
        if family == "ordinary":
            parsed = parse_n4p_ordinary_trigger_run_id(run_id)
            if parsed.get("mode") != "provisional_ordinary":
                return None
            return parsed
        parsed = parse_provisional_projection_trigger_run_id(run_id)
        if parsed.get("mode") != "provisional_hint_v2":
            return None
        return parsed
    except Exception:
        return None


def _existing_target(existing_targets: Sequence[Mapping[str, Any]], target_run_id: str) -> Mapping[str, Any] | None:
    for target in existing_targets:
        if str(target.get("run_id") or "") == target_run_id:
            return target
    return None


def _assert_existing_target_safe(
    target: Mapping[str, Any],
    *,
    source_run_id: str,
    previous_trigger_run_id: str,
    expected_counts: Mapping[str, int],
    allow_downstream_refs: bool = False,
) -> dict[str, str]:
    if int(target.get("outbox_delivered_delivering") or 0) != 0:
        raise ProofDiscoveryBlocked(f"existing N4 target has delivered/delivering outbox refs: {target.get('run_id')}")
    if not allow_downstream_refs and int(target.get("downstream_ref_count") or 0) != 0:
        raise ProofDiscoveryBlocked(f"existing N4 target has downstream refs: {target.get('run_id')}")
    if str(target.get("status") or "") != "passed":
        raise ProofDiscoveryBlocked(f"dirty existing N4 target blocks proof discovery: {target.get('run_id')}")
    if str(target.get("source_run_id") or "") != source_run_id:
        raise ProofDiscoveryBlocked(f"dirty existing N4 target source mismatch: {target.get('run_id')}")
    _assert_existing_target_counts_safe(target, expected_counts=expected_counts)
    if str(target.get("previous_trigger_run_id") or "") != str(previous_trigger_run_id or ""):
        if _existing_target_baseline_metadata_compat(target, previous_trigger_run_id=previous_trigger_run_id):
            return {
                "baseline_policy": "baseline_metadata_compat_pass",
                "baseline_policy_compat_reason": BASELINE_METADATA_COMPAT_REASON,
            }
        raise ProofDiscoveryBlocked(f"dirty existing N4 target baseline mismatch: {target.get('run_id')}")
    return {}


def _assert_existing_target_counts_safe(target: Mapping[str, Any], *, expected_counts: Mapping[str, int]) -> None:
    for run_key, actual_key in (
        ("run_state_count", "state_count"),
        ("run_match_count", "match_count"),
        ("run_outbox_count", "outbox_count"),
    ):
        if run_key in target and target.get(run_key) is not None:
            run_count = int(target.get(run_key) or 0)
            actual_count = int(target.get(actual_key) or 0)
            if run_count != actual_count:
                raise ProofDiscoveryBlocked(
                    f"dirty existing N4 target run count mismatch: {target.get('run_id')} "
                    f"{run_key}={run_count} {actual_key}={actual_count}"
                )
    for target_key, expected in expected_counts.items():
        actual = int(target.get(target_key) or 0)
        if actual != expected:
            raise ProofDiscoveryBlocked(
                f"dirty existing N4 target count mismatch: {target.get('run_id')} {target_key}={actual} expected={expected}"
            )


def _existing_target_baseline_metadata_compat(target: Mapping[str, Any], *, previous_trigger_run_id: str) -> bool:
    if not previous_trigger_run_id:
        return False
    if str(target.get("previous_trigger_run_id") or ""):
        return False
    return all(
        key in target and target.get(key) is not None
        for key in ("run_state_count", "run_match_count", "run_outbox_count", "state_count", "match_count", "outbox_count")
    )


def _expected_counts(candidate: Mapping[str, Any]) -> dict[str, int]:
    mapping = {
        "expected_state_count": "state_count",
        "expected_match_count": "match_count",
        "expected_outbox_count": "outbox_count",
    }
    expected: dict[str, int] = {}
    for source_key, target_key in mapping.items():
        if source_key in candidate and candidate[source_key] is not None:
            expected[target_key] = int(candidate[source_key])
    return expected


def _child_argv_plan_only(
    *,
    family: str,
    python_executable: str,
    trigger_context_run_id: str,
    source_run_id: str,
    target_run_id: str,
    for_trade_date: str,
    until_hhmm: str,
    source_condition_run_id: str,
    previous_trigger_run_id: str,
    dsn: str = "",
    redact_dsn_for_report: bool = True,
) -> list[str]:
    if family == "ordinary":
        argv = [
            python_executable,
            "scripts/run_n4_provisional_ordinary_execute_once.py",
            "--trigger-context-run-id",
            trigger_context_run_id,
            "--source-metric-run-id",
            source_run_id,
            "--trigger-run-id",
            target_run_id,
            "--for-trade-date",
            for_trade_date,
            "--source-condition-run-id",
            source_condition_run_id,
            "--json-report-path",
            f"tmp/N4_{for_trade_date}_{until_hhmm}_ordinary_matcher_execute_report.json",
        ]
        if dsn:
            argv.extend(["--dsn", _redact_dsn(dsn) if redact_dsn_for_report else dsn])
        if previous_trigger_run_id:
            argv.extend(["--previous-trigger-run-id", previous_trigger_run_id])
        else:
            argv.extend(["--baseline-mode", "no_previous_baseline"])
        return argv
    argv = [
        python_executable,
        "scripts/run_n4_provisional_projection_execute_once.py",
        "--trigger-context-run-id",
        trigger_context_run_id,
        "--projection-run-id",
        source_run_id,
        "--source-projection-run-id",
        source_run_id,
        "--trigger-run-id",
        target_run_id,
        "--for-trade-date",
        for_trade_date,
        "--source-condition-run-id",
        source_condition_run_id,
        "--json-report-path",
        f"tmp/N4_{for_trade_date}_{until_hhmm}_hint_matcher_execute_report.json",
    ]
    if dsn:
        argv.extend(["--dsn", _redact_dsn(dsn) if redact_dsn_for_report else dsn])
    if previous_trigger_run_id:
        argv.extend(["--previous-trigger-run-id", previous_trigger_run_id])
    else:
        argv.append("--no-previous-baseline")
    return argv


def _runtime_child_argv(
    item: Mapping[str, Any],
    *,
    family: str,
    python_executable: str,
    trigger_context_run_id: str,
    for_trade_date: str,
    source_condition_run_id: str,
    dsn: str,
) -> list[str]:
    base = _child_argv_plan_only(
        family=family,
        python_executable=python_executable,
        trigger_context_run_id=trigger_context_run_id,
        source_run_id=str(item["source_run_id"]),
        target_run_id=str(item["target_run_id"]),
        for_trade_date=for_trade_date,
        until_hhmm=str(item["until_hhmm"]),
        source_condition_run_id=source_condition_run_id,
        previous_trigger_run_id=str(item.get("previous_trigger_run_id") or ""),
        dsn=dsn,
        redact_dsn_for_report=False,
    )
    return [*base, "--execute", "--user-confirmed"]


def _redact_dsn(dsn: str) -> str:
    if not dsn:
        return ""
    try:
        parsed = urlsplit(dsn)
        if parsed.password:
            username = parsed.username or ""
            hostname = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            auth = f"{username}:***@{hostname}{port}" if username else f"***@{hostname}{port}"
            return urlunsplit((parsed.scheme, auth, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        pass
    redacted = re.sub(r":([^:@/\s]+)@", ":***@", dsn)
    redacted = re.sub(r"(password=)[^\s]+", r"\1***", redacted, flags=re.IGNORECASE)
    return redacted


def _redact_child_argv_for_report(argv: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    redact_next = False
    for part in argv:
        text = str(part)
        if redact_next:
            redacted.append(_redact_dsn(text))
            redact_next = False
            continue
        redacted.append(text)
        if text == "--dsn":
            redact_next = True
    return redacted


def _forbidden_operation_proof(*, child_executed: bool) -> dict[str, bool]:
    return {
        "child_executed": child_executed,
        "outbox_consumed": False,
        "inbox_checkpoint_updated": False,
        "n5_n6_entered": False,
        "worker_launchd_touched": False,
        "rollback_executed": False,
        "schema_changed": False,
    }


def _assert_child_argv_safe(selected: Mapping[str, Mapping[str, Any] | None]) -> None:
    blob = " ".join(
        " ".join(str(part) for part in item.get("child_argv_for_execute", []))
        for item in selected.values()
        if item
    ).lower()
    for token in FORBIDDEN_COMMAND_TOKENS:
        if token in blob:
            raise ProofDiscoveryBlocked(f"forbidden child argv token detected: {token}")


def _validate_inputs(
    *,
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    trigger_context_run_id: str,
    mode: str,
    selection_mode: str,
) -> None:
    if mode not in {"ordinary", "hint", "both"}:
        raise ProofDiscoveryBlocked(f"invalid mode: {mode}")
    if selection_mode not in SELECTION_MODES:
        raise ProofDiscoveryBlocked(f"invalid selection_mode: {selection_mode}")
    for name, value in (("for_trade_date", for_trade_date), ("source_trade_date", source_trade_date)):
        if not (str(value).isdigit() and len(str(value)) == 8):
            raise ProofDiscoveryBlocked(f"{name} must be YYYYMMDD")
    if not source_condition_run_id.startswith(f"condition_layer_{source_trade_date}_source_{source_trade_date}_for_{for_trade_date}_"):
        raise ProofDiscoveryBlocked("source_condition_run_id date lineage mismatch")
    if f"trigger_context_snapshot_{for_trade_date}_condition_layer_{source_trade_date}_" not in trigger_context_run_id:
        raise ProofDiscoveryBlocked("trigger_context_run_id date lineage mismatch")


def _nested_json(row: Mapping[str, Any], *keys: str) -> Any:
    value: Any = row
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def poll_history_path_for_mode(mode: str) -> Path:
    return DEFAULT_HINT_HISTORY_PATH if mode == "hint" else DEFAULT_HISTORY_PATH


def append_poll_history(
    report: Mapping[str, Any],
    *,
    report_path: str | Path = "",
    history_path: str | Path | None = None,
    max_lines: int = HISTORY_MAX_LINES,
) -> dict[str, Any]:
    record = _build_poll_history_record(report, report_path=report_path)
    target = Path(history_path) if history_path is not None else poll_history_path_for_mode(str(report.get("poller_mode") or ""))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
        keep = max(0, max_lines - 1)
        lines = [*existing[-keep:], json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"history_written": True, "history_path": str(target), "history_record": record}
    except Exception as exc:  # pragma: no cover - fail-open evidence path for launchd safety
        return {"history_written": False, "history_path": str(target), "history_error": str(exc), "history_record": record}


def _build_poll_history_record(report: Mapping[str, Any], *, report_path: str | Path = "") -> dict[str, Any]:
    timing = report.get("timing") if isinstance(report.get("timing"), Mapping) else {}
    selected = report.get("selected") if isinstance(report.get("selected"), Mapping) else {}
    selected_items = [
        item
        for item in selected.values()
        if isinstance(item, Mapping) and item
    ]
    selected_run_ids = [str(item.get("target_run_id") or "") for item in selected_items if str(item.get("target_run_id") or "")]
    selected_source_run_ids = [str(item.get("source_run_id") or "") for item in selected_items if str(item.get("source_run_id") or "")]
    child_execution = report.get("child_execution") if isinstance(report.get("child_execution"), Mapping) else {}
    children = _history_child_records(selected=selected, child_execution=child_execution)
    skipped_candidates = report.get("skipped_candidates")
    if not isinstance(skipped_candidates, Sequence) or isinstance(skipped_candidates, (str, bytes)):
        skipped_candidates = []
    existing_target_skips = [
        dict(item)
        for item in skipped_candidates
        if isinstance(item, Mapping) and "already_passed" in str(item.get("reason") or "")
    ]
    no_candidate_reason = ""
    if not selected_items:
        no_candidate_reason = "no_selected_candidate"
    return {
        "started_at": str(timing.get("started_at") or ""),
        "finished_at": str(timing.get("finished_at") or ""),
        "duration_ms": timing.get("total_duration_ms", 0),
        "mode": str(report.get("poller_mode") or ""),
        "result": str(report.get("result") or ""),
        "status": str(report.get("status") or ""),
        "reason": str(report.get("reason") or report.get("error") or no_candidate_reason),
        "discovery_policy": str(report.get("discovery_policy") or ""),
        "selected_child_order_policy": str(report.get("selected_child_order_policy") or SELECTED_CHILD_ORDER_POLICY),
        "selected_child_order": list(report.get("selected_child_order") or []),
        "selected_run_id": selected_run_ids[0] if len(selected_run_ids) == 1 else "",
        "selected_run_ids": selected_run_ids,
        "selected_source_market_data_run_id": selected_source_run_ids[0] if len(selected_source_run_ids) == 1 else "",
        "selected_source_market_data_run_ids": selected_source_run_ids,
        "no_candidate_reason": no_candidate_reason,
        "existing_target_skip": existing_target_skips,
        "executed_child_command_count": int(child_execution.get("executed_child_command_count") or 0),
        "children": children,
        "report_path": str(report_path or ""),
    }


def _history_child_records(*, selected: Mapping[str, Any], child_execution: Mapping[str, Any]) -> list[dict[str, Any]]:
    selected_by_family = {
        str(item.get("family") or family): item
        for family, item in selected.items()
        if isinstance(item, Mapping) and item
    }
    raw_children = child_execution.get("children") if isinstance(child_execution.get("children"), Sequence) else []
    records: list[dict[str, Any]] = []
    for child in raw_children:
        if not isinstance(child, Mapping):
            continue
        family = str(child.get("family") or "")
        selected_item = selected_by_family.get(family, {})
        records.append(
            {
                "family": family,
                "source_run_id": str(selected_item.get("source_run_id") or ""),
                "target_run_id": str(selected_item.get("target_run_id") or ""),
                "returncode": int(child.get("returncode") or 0),
                "duration_ms": child.get("child_duration_ms", 0),
                "started_at": str(child.get("child_started_at") or ""),
                "finished_at": str(child.get("child_finished_at") or ""),
            }
        )
    return records


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    exit_code, report = run_proof_discovery_poll(
        dsn=args.dsn,
        for_trade_date=args.for_trade_date,
        source_trade_date=args.source_trade_date,
        source_condition_run_id=args.source_condition_run_id,
        trigger_context_run_id=args.trigger_context_run_id,
        mode=args.mode,
        selection_mode=args.selection_mode,
        python_executable=args.python_executable,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        lineage_config_path=args.lineage_config,
    )

    append_poll_history(report, report_path=args.json_report_path or "", history_path=args.history_path)
    if args.json_report_path:
        write_json(args.json_report_path, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    elif exit_code:
        print(f"BLOCKED: {report.get('error', 'proof-discovery poll failed')}", file=sys.stderr)
    else:
        print(f"result={report['result']} mode={report['poller_mode']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
