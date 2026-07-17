#!/usr/bin/env python3
"""Plan one bounded N3 proof poller pass.

This wrapper is a contract surface for the post-20260701 N3 proof path.  It
does not fetch行情 or write DB by default.  It composes only audited N3 child
wrappers and leaves the proof minute as a source-returned placeholder until the
source fetch child produces an actual HHMM.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

from ashare_v3.runtime.intraday_worker_lineage import (
    LineageConfigError,
    lineage_report_fields,
    load_intraday_worker_lineage_config,
    no_lineage_config_report_fields,
)


MIDDAY_BRIDGE_HINT_PROOF_KIND = "index_board_1m_hint_projection_v1_midday_bridge_v1"
N3P_SOURCE_VARIANT = "b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1"
ACTUAL_HHMM_PLACEHOLDER = "{actual_hhmm}"
SOURCE_RETURNED_CANDIDATE = "source_returned"
N3P_SOURCE_ALIGNMENT_BLOCKER = "BLOCKED_N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT"
N3P_SOURCE_ALIGNMENT_RETRY_EXHAUSTED_BLOCKER = "BLOCKED_N3P_SOURCE_CANONICAL_MINUTE_ALIGNMENT_RETRY_EXHAUSTED"
N3P_SOURCE_ALIGNMENT_ADJACENT_RACE = "adjacent_minute_source_boundary_race"
N3P_ROLLBACK_ARTIFACT_MISSING_BLOCKER = "BLOCKED_N3P_ROLLBACK_ARTIFACT_MISSING"
N3P_ROLLBACK_ARTIFACT_UNSAFE_BLOCKER = "BLOCKED_N3P_ROLLBACK_ARTIFACT_UNSAFE"
HINT_SOURCE_IDEMPOTENT_NOOP_RESULT = "NOOP_N3_HINT_TARGET_ALREADY_PASSED"
HINT_SOURCE_IDEMPOTENT_NOOP_REASON = "noop_existing_hint_target_passed"
SOURCE_FETCH_WINDOW_START_HHMM = "0925"
SOURCE_FETCH_WINDOW_END_HHMM = "1530"
DEFAULT_MAX_ALIGNMENT_RETRIES = 2
DEFAULT_RETRY_SLEEP_SECONDS = 2.0
DEFAULT_PYTHON_EXECUTABLE = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
BRANCH_MODES = {"both", "n3p_only", "hint_only"}
CHILD_STDOUT_REDACTION_THRESHOLD = 4096
LARGE_CHILD_JSON_FIELDS = {"index_board_1m_rows", "proof_rows"}
CHILD_JSON_RAW_PAYLOAD_FIELDS = {"raw_payload"}
CommandRunner = Callable[[list[str]], Any]
SleepFn = Callable[[float], Any]
ProgressWriter = Callable[[Mapping[str, Any]], Any]
CloseNoopChecker = Callable[[Mapping[str, Any]], Mapping[str, Any]]
ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _timing_timestamp() -> str:
    return datetime.now(ASIA_SHANGHAI).isoformat(timespec="microseconds")


def _refresh_report_timing(
    report: dict[str, Any],
    *,
    started_at: str,
    started_perf: float,
    branch_mode: str,
) -> None:
    timing = report.setdefault(
        "timing",
        {
            "started_at": started_at,
            "finished_at": "",
            "total_duration_ms": 0,
            "branch_mode": branch_mode,
            "phases": [],
        },
    )
    timing["started_at"] = str(timing.get("started_at") or started_at)
    timing["branch_mode"] = str(report.get("branch_mode") or branch_mode)
    timing["finished_at"] = _timing_timestamp()
    timing["total_duration_ms"] = max(0, round((time.perf_counter() - started_perf) * 1000, 3))
    timing["phases"] = [
        {
            "phase_name": str(step.get("step_id") or ""),
            "started_at": str(step.get("child_started_at") or ""),
            "finished_at": str(step.get("child_finished_at") or ""),
            "duration_ms": max(0, float(step.get("child_duration_ms") or 0)),
            "status": "blocked" if _child_failed(step) else "passed",
            "child_step": str(step.get("step_id") or ""),
        }
        for step in report.get("executed_child_steps") or []
        if step.get("step_id")
    ]


def _attach_child_timing(result: dict[str, Any], *, started_at: str, started_perf: float) -> dict[str, Any]:
    result["child_started_at"] = started_at
    result["child_finished_at"] = _timing_timestamp()
    result["child_duration_ms"] = max(0, round((time.perf_counter() - started_perf) * 1000, 3))
    return result


def _summarize_child_artifacts(payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    artifact_paths: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(value, str):
            continue
        if key.endswith("_path") or key.endswith("_report_path") or key.endswith("_artifact_path"):
            artifact_paths[key] = value
        if "hash" in key or "sha256" in key:
            hashes[key] = value
    summary: dict[str, dict[str, str]] = {}
    if artifact_paths:
        summary["artifact_paths"] = artifact_paths
    if hashes:
        summary["hashes"] = hashes
    return summary


def _redact_child_json_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    redacted_fields: list[str] = []
    row_counts: dict[str, int] = {}

    def redact(value: Any, path: tuple[str, ...]) -> Any:
        if isinstance(value, Mapping):
            redacted: dict[str, Any] = {}
            for key, nested in value.items():
                key_str = str(key)
                nested_path = (*path, key_str)
                dotted = ".".join(nested_path)
                if key_str in LARGE_CHILD_JSON_FIELDS and isinstance(nested, list):
                    redacted_fields.append(f"json.{dotted}")
                    row_counts[dotted] = len(nested)
                    continue
                if key_str in CHILD_JSON_RAW_PAYLOAD_FIELDS and isinstance(nested, (dict, list)):
                    redacted_fields.append(f"json.{dotted}")
                    if isinstance(nested, list):
                        row_counts[dotted] = len(nested)
                    continue
                redacted[key_str] = redact(nested, nested_path)
            return redacted
        if isinstance(value, list):
            return [redact(item, (*path, "[]")) for item in value]
        return value

    redacted_payload = redact(payload, ())
    summary: dict[str, Any] = _summarize_child_artifacts(payload)
    if row_counts:
        summary["row_counts"] = row_counts
    return redacted_payload, redacted_fields, summary


def _redact_child_result_for_parent_report(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("json")
    redacted_fields: list[str] = []
    summary: dict[str, Any] = {}
    if isinstance(payload, Mapping):
        redacted_payload, json_redacted_fields, json_summary = _redact_child_json_payload(payload)
        result["json"] = redacted_payload
        redacted_fields.extend(json_redacted_fields)
        summary.update(json_summary)

    stdout = result.get("stdout")
    if isinstance(stdout, str) and len(stdout) > CHILD_STDOUT_REDACTION_THRESHOLD:
        result["stdout_original_length"] = len(stdout)
        result["stdout"] = "[redacted_large_child_stdout_json; see child_json_summary and standalone child artifacts]"
        redacted_fields.append("stdout")

    if redacted_fields:
        result["child_json_redacted"] = True
        result["redacted_fields"] = sorted(dict.fromkeys(redacted_fields))
        result["child_json_summary"] = summary
    else:
        result.setdefault("child_json_redacted", False)
    return result


def _side_effects() -> dict[str, bool]:
    return {
        "market_data_pulled": False,
        "database_written": False,
        "writes_outbox": False,
        "consumes_outbox": False,
        "updates_inbox_or_checkpoint": False,
        "touches_n4_n5_n6": False,
        "starts_worker": False,
        "rollback_executed": False,
        "schema_changed": False,
    }


def n3p_source_payload_run_id(for_trade_date: str, hhmm: str = ACTUAL_HHMM_PLACEHOLDER) -> str:
    return f"n3p_mixed_realtime_source_payload_{for_trade_date}_until_{hhmm}_v1"


def n3p_source_payload_candidate_run_id(for_trade_date: str) -> str:
    return n3p_source_payload_run_id(for_trade_date, SOURCE_RETURNED_CANDIDATE)


def n3p_target_run_id(for_trade_date: str, subscription_run_id: str, hhmm: str = ACTUAL_HHMM_PLACEHOLDER) -> str:
    return f"realtime_action_confirmation_metric_{for_trade_date}_until_{hhmm}__asset_all__{N3P_SOURCE_VARIANT}__{subscription_run_id}"


def hint_target_run_id(
    for_trade_date: str,
    subscription_run_id: str,
    hhmm: str = ACTUAL_HHMM_PLACEHOLDER,
    *,
    hint_proof_kind: str = MIDDAY_BRIDGE_HINT_PROOF_KIND,
) -> str:
    return f"realtime_hint_projection_metric_{for_trade_date}_until_{hhmm}__asset_index_board__{hint_proof_kind}__{subscription_run_id}"


def hint_source_artifact_path(for_trade_date: str, hhmm: str = ACTUAL_HHMM_PLACEHOLDER) -> str:
    return f"docs/intraday_live_current/{for_trade_date}/N3_hint_index_board_1m_{hhmm}_midday_bridge_frequency8_payload.json"


def hint_source_child_report_path(for_trade_date: str) -> str:
    return f"tmp/N3_hint_{for_trade_date}_{SOURCE_RETURNED_CANDIDATE}_source_child_report.json"


def n3p_source_artifact_path(for_trade_date: str, hhmm: str = ACTUAL_HHMM_PLACEHOLDER) -> str:
    return f"docs/intraday_live_current/{for_trade_date}/N3P_mixed_realtime_{hhmm}_source_fetch_payload.json"


def n3p_rollback_sql_path(for_trade_date: str, hhmm: str = ACTUAL_HHMM_PLACEHOLDER) -> str:
    return f"sql/N3P_{for_trade_date}_{hhmm}_trigger_proof_rollback.sql"


def hint_source_candidate_run_id(for_trade_date: str) -> str:
    return f"n3_hint_index_board_1m_source_payload_{for_trade_date}_until_{SOURCE_RETURNED_CANDIDATE}_v1"


def _normalize_branch_mode(branch_mode: str) -> str:
    normalized = str(branch_mode or "both").strip()
    return normalized if normalized in BRANCH_MODES else ""


def _branch_status_fields(branch_mode: str) -> dict[str, Any]:
    if branch_mode == "n3p_only":
        return {
            "branch_mode": branch_mode,
            "n3p_status": "planned",
            "hint_status": "skipped",
            "skipped_branch_reason": {"hint": "branch_mode_n3p_only"},
        }
    if branch_mode == "hint_only":
        return {
            "branch_mode": branch_mode,
            "n3p_status": "skipped",
            "hint_status": "planned",
            "skipped_branch_reason": {"n3p": "branch_mode_hint_only"},
        }
    return {
        "branch_mode": "both",
        "n3p_status": "planned",
        "hint_status": "planned",
        "skipped_branch_reason": {},
    }


def _filter_child_steps_for_branch(child_steps: list[dict[str, Any]], branch_mode: str) -> list[dict[str, Any]]:
    if branch_mode == "n3p_only":
        return [step for step in child_steps if str(step.get("step_id") or "").startswith("n3p_")]
    if branch_mode == "hint_only":
        return [step for step in child_steps if str(step.get("step_id") or "").startswith("n3_hint_")]
    return child_steps


def decide_source_payload_idempotency(*, existing: Mapping[str, Any] | None, candidate_payload_hash: str) -> dict[str, Any]:
    if not existing or not existing.get("exists"):
        return {"decision": "write_allowed", "reason": "source_payload_absent"}
    if existing.get("status") == "passed" and str(existing.get("payload_hash") or "") == candidate_payload_hash:
        return {"decision": "idempotent_pass", "reason": "same_hhmm_same_source_hash"}
    return {"decision": "blocked", "reason": "same_hhmm_different_source_hash"}


def decide_proof_target_idempotency(*, existing: Mapping[str, Any] | None, candidate: Mapping[str, Any]) -> dict[str, Any]:
    if not existing or not existing.get("exists"):
        return {"decision": "write_allowed", "reason": "proof_target_absent"}
    if existing.get("outbox_refs") or existing.get("writes_outbox"):
        return {"decision": "blocked", "reason": "existing_target_has_outbox_refs"}
    expected = {
        "status": "passed",
        "source_payload_hash": candidate.get("source_payload_hash"),
        "rows_by_asset": candidate.get("rows_by_asset"),
        "metric_ready": candidate.get("metric_ready"),
    }
    actual = {
        "status": existing.get("status"),
        "source_payload_hash": existing.get("source_payload_hash"),
        "rows_by_asset": existing.get("rows_by_asset"),
        "metric_ready": existing.get("metric_ready"),
    }
    if actual == expected:
        return {"decision": "idempotent_pass", "reason": "existing_target_same_source_hash_baseline_counts"}
    return {"decision": "blocked", "reason": "existing_target_baseline_mismatch"}


def build_proof_poller_plan(
    *,
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    n4_context_run_id: str,
    hint_proof_kind: str = MIDDAY_BRIDGE_HINT_PROOF_KIND,
    execute: bool = False,
    python_executable: str = DEFAULT_PYTHON_EXECUTABLE,
    max_alignment_retries: int = DEFAULT_MAX_ALIGNMENT_RETRIES,
    retry_sleep_seconds: float = DEFAULT_RETRY_SLEEP_SECONDS,
    branch_mode: str = "both",
) -> dict[str, Any]:
    branch_mode = _normalize_branch_mode(branch_mode) or "both"
    ordinary_source_run_id = n3p_source_payload_run_id(for_trade_date)
    ordinary_target_run_id = n3p_target_run_id(for_trade_date, subscription_run_id)
    hint_target = hint_target_run_id(for_trade_date, subscription_run_id, hint_proof_kind=hint_proof_kind)
    common = {
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "source_condition_run_id": source_condition_run_id,
        "subscription_run_id": subscription_run_id,
        "preload_run_id": preload_run_id,
        "n4_context_run_id": n4_context_run_id,
    }
    child_steps = [
        {
            "step_id": "n3p_current_source_fetch",
            "runner_path": "scripts/run_n3p_current_source_fetch_once.py",
            "target_run_id": ordinary_source_run_id,
            "argv": _child_argv(
                python_executable,
                "scripts/run_n3p_current_source_fetch_once.py",
                common,
                target_run_id=ordinary_source_run_id,
                json_report_path=f"tmp/N3P_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_source_fetch_report.json",
                execute=execute,
            ),
        },
        {
            "step_id": "n3p_trigger_proof_preflight",
            "runner_path": "scripts/run_n3p_trigger_proof_preflight_once.py",
            "source_run_id": ordinary_source_run_id,
            "target_run_id": ordinary_target_run_id,
            "argv": _child_argv(
                python_executable,
                "scripts/run_n3p_trigger_proof_preflight_once.py",
                common,
                source_run_id=ordinary_source_run_id,
                target_run_id=ordinary_target_run_id,
                source_payload_path=n3p_source_artifact_path(for_trade_date),
                contract_path=f"tmp/N3P_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_trigger_proof_contract.json",
                preflight_path=f"tmp/N3P_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_trigger_proof_preflight.json",
                json_report_path=f"tmp/N3P_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_trigger_proof_preflight_report.json",
                execute=False,
            ),
        },
        {
            "step_id": "n3p_trigger_proof_execute",
            "runner_path": "scripts/run_v3_realtime_virtual_metric_writer_once.py",
            "source_run_id": ordinary_source_run_id,
            "target_run_id": ordinary_target_run_id,
            "argv": [
                python_executable,
                "scripts/run_v3_realtime_virtual_metric_writer_once.py",
                "--contract-path",
                f"tmp/N3P_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_trigger_proof_contract.json",
                "--preflight-path",
                f"tmp/N3P_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_trigger_proof_preflight.json",
                "--source-payload-path",
                n3p_source_artifact_path(for_trade_date),
                "--json-report-path",
                f"tmp/N3P_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_trigger_proof_execute_report.json",
                "--rollback-sql-path",
                n3p_rollback_sql_path(for_trade_date),
            ]
            + (["--execute", "--user-confirmed"] if execute else []),
        },
        {
            "step_id": "n3_hint_source_fetch",
            "runner_path": "scripts/run_n3_hint_index_board_1m_source_fetch_once.py",
            "target_run_id": f"n3_hint_index_board_1m_source_payload_{for_trade_date}_until_{ACTUAL_HHMM_PLACEHOLDER}_v1",
            "argv": _child_argv(
                python_executable,
                "scripts/run_n3_hint_index_board_1m_source_fetch_once.py",
                common,
                target_run_id=f"n3_hint_index_board_1m_source_payload_{for_trade_date}_until_{ACTUAL_HHMM_PLACEHOLDER}_v1",
                hint_proof_kind=hint_proof_kind,
                json_report_path=hint_source_child_report_path(for_trade_date),
                execute=execute,
            ),
        },
        {
            "step_id": "n3_hint_proof_preflight",
            "runner_path": "scripts/run_n3_hint_index_board_1m_proof_preflight_once.py",
            "target_run_id": hint_target,
            "argv": _child_argv(
                python_executable,
                "scripts/run_n3_hint_index_board_1m_proof_preflight_once.py",
                common,
                target_run_id=hint_target,
                source_artifact_path=hint_source_artifact_path(for_trade_date),
                hint_proof_kind=hint_proof_kind,
                contract_path=f"tmp/N3_hint_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_midday_bridge_v1_contract.json",
                preflight_path=f"tmp/N3_hint_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_midday_bridge_v1_preflight.json",
                json_report_path=f"tmp/N3_hint_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_midday_bridge_v1_preflight_report.json",
                execute=False,
            ),
        },
        {
            "step_id": "n3_hint_proof_execute",
            "runner_path": "scripts/run_n3_hint_index_board_1m_proof_execute_once.py",
            "target_run_id": hint_target,
            "argv": _child_argv(
                python_executable,
                "scripts/run_n3_hint_index_board_1m_proof_execute_once.py",
                common,
                target_run_id=hint_target,
                source_artifact_path=hint_source_artifact_path(for_trade_date),
                hint_proof_kind=hint_proof_kind,
                contract_path=f"tmp/N3_hint_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_midday_bridge_v1_contract.json",
                preflight_path=f"tmp/N3_hint_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_midday_bridge_v1_preflight.json",
                json_report_path=f"tmp/N3_hint_index_board_1m_{for_trade_date}_{ACTUAL_HHMM_PLACEHOLDER}_midday_bridge_v1_execute_report.json",
                execute=execute,
            ),
        },
    ]
    plan = {
        "selected_candidate_minute": "from_source_returned_time",
        "no_op_reason": "",
        "source_selection_policy": "exact_lineage_source_returned_hhmm_no_wildcard_v1",
        "target_run_id_preview": {
            "ordinary_hhmm": ACTUAL_HHMM_PLACEHOLDER,
            "ordinary_source_run_id": ordinary_source_run_id,
            "ordinary_target_run_id": ordinary_target_run_id,
            "hint_hhmm": ACTUAL_HHMM_PLACEHOLDER,
            "hint_target_run_id": hint_target,
        },
        "n3p_source_alignment_retry_policy": {
            "enabled": True,
            "retryable_failure_class": N3P_SOURCE_ALIGNMENT_ADJACENT_RACE,
            "max_alignment_retries": max(0, int(max_alignment_retries)),
            "retry_sleep_seconds": max(0.0, float(retry_sleep_seconds)),
            "no_relabel": True,
            "applies_before_artifact_register_write": True,
        },
        "planned_child_steps": _filter_child_steps_for_branch(child_steps, branch_mode),
    }
    plan.update(_branch_status_fields(branch_mode))
    return plan


def run_proof_poller_once(
    *,
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    n4_context_run_id: str,
    hint_proof_kind: str = MIDDAY_BRIDGE_HINT_PROOF_KIND,
    execute: bool = False,
    user_confirmed: bool = False,
    python_executable: str = DEFAULT_PYTHON_EXECUTABLE,
    command_runner: CommandRunner | None = None,
    sleep_fn: SleepFn | None = None,
    max_alignment_retries: int = DEFAULT_MAX_ALIGNMENT_RETRIES,
    retry_sleep_seconds: float = DEFAULT_RETRY_SLEEP_SECONDS,
    json_report_path: str = "",
    post_close_noop_checker: CloseNoopChecker | None = None,
    lineage_config_path: str = "",
    branch_mode: str = "both",
) -> dict[str, Any]:
    timing_started_at = _timing_timestamp()
    timing_started_perf = time.perf_counter()

    def finish_timing(report: dict[str, Any], resolved_branch_mode: str) -> dict[str, Any]:
        _refresh_report_timing(
            report,
            started_at=timing_started_at,
            started_perf=timing_started_perf,
            branch_mode=resolved_branch_mode,
        )
        return report

    raw_branch_mode = branch_mode
    branch_mode = _normalize_branch_mode(branch_mode)
    if not branch_mode:
        return finish_timing({
            "status": "blocked",
            "reason": "unsupported_branch_mode",
            "layer_role": "N3_market_data",
            "execution_mode": "blocked",
            "branch_mode": str(raw_branch_mode or ""),
            "allowed_branch_modes": sorted(BRANCH_MODES),
            "executed_child_command_count": 0,
            "side_effects": _side_effects(),
        }, str(raw_branch_mode or ""))
    lineage_fields = no_lineage_config_report_fields()
    if lineage_config_path:
        try:
            lineage = load_intraday_worker_lineage_config(lineage_config_path)
        except LineageConfigError as exc:
            return finish_timing({
                "status": "blocked",
                "reason": "BLOCKED_INTRADAY_WORKER_LINEAGE_CONFIG",
                "lineage_config_path": lineage_config_path,
                "lineage_config_used": False,
                "lineage_config_error": str(exc),
                "execution_mode": "blocked",
                "executed_child_command_count": 0,
                "side_effects": _side_effects(),
            }, branch_mode)
        for_trade_date = str(lineage["for_trade_date"])
        source_trade_date = str(lineage["source_trade_date"])
        source_condition_run_id = str(lineage["n2_run_id"])
        subscription_run_id = str(lineage["subscription_run_id"])
        preload_run_id = str(lineage["a1_preload_run_id"])
        n4_context_run_id = str(lineage["n4_context_run_id"])
        lineage_fields = lineage_report_fields(lineage_config_path, lineage)
    report = {
        "status": "ready",
        "reason": "",
        "layer_role": "N3_market_data",
        "execution_mode": "execute" if execute else "plan_only",
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "source_condition_run_id": source_condition_run_id,
        "subscription_run_id": subscription_run_id,
        "preload_run_id": preload_run_id,
        "n4_context_run_id": n4_context_run_id,
        "hint_proof_kind": hint_proof_kind,
        "required_hint_proof_kind": MIDDAY_BRIDGE_HINT_PROOF_KIND,
        "branch_mode": branch_mode,
        "executed_child_command_count": 0,
        "n3p_source_alignment_retry_policy": {
            "enabled": True,
            "retryable_failure_class": N3P_SOURCE_ALIGNMENT_ADJACENT_RACE,
            "max_alignment_retries": max(0, int(max_alignment_retries)),
            "retry_sleep_seconds": max(0.0, float(retry_sleep_seconds)),
            "no_relabel": True,
            "applies_before_artifact_register_write": True,
        },
        "side_effects": _side_effects(),
    }
    report.update(_branch_status_fields(branch_mode))
    report.update(lineage_fields)
    report["effective_for_trade_date"] = for_trade_date
    report["effective_source_trade_date"] = source_trade_date
    progress_writer = _progress_writer(json_report_path)
    if hint_proof_kind != MIDDAY_BRIDGE_HINT_PROOF_KIND:
        report.update({"status": "blocked", "reason": "unsupported_hint_proof_kind"})
        finish_timing(report, branch_mode)
        progress_writer(report)
        return report
    if execute != user_confirmed:
        report.update({"status": "blocked", "reason": "n3_proof_poller_execute_requires_user_confirmed"})
        report["execution_mode"] = "blocked"
        finish_timing(report, branch_mode)
        progress_writer(report)
        return report
    if execute:
        session_guard = _evaluate_for_trade_date_session_guard(for_trade_date)
        session_guard["lineage_config_used"] = bool(report.get("lineage_config_used", False))
        report["session_guard"] = session_guard
        if session_guard.get("status") == "blocked":
            report.update(
                {
                    "status": "blocked",
                    "reason": "BLOCKED_N3_PROOF_POLLER_SESSION_GUARD",
                    "execution_mode": "blocked",
                    "session_guard_reason": str(session_guard.get("session_guard_reason") or ""),
                    "observed_local_date": str(session_guard.get("observed_local_date") or ""),
                    "observed_local_time": str(session_guard.get("observed_local_time") or ""),
                    "planned_child_steps": [],
                    "executed_child_steps": [],
                    "actual_hhmm_handoff": {},
                }
            )
            finish_timing(report, branch_mode)
            progress_writer(report)
            return report
        if session_guard.get("status") == "noop":
            report.update(
                {
                    "status": "noop",
                    "reason": "noop_for_trade_date_not_current_session",
                    "execution_mode": "noop",
                    "post_close_noop": False,
                    "noop_reason": "for_trade_date_not_current_session",
                    "session_guard_reason": str(session_guard.get("session_guard_reason") or ""),
                    "observed_local_date": str(session_guard.get("observed_local_date") or ""),
                    "observed_local_time": str(session_guard.get("observed_local_time") or ""),
                    "planned_child_steps": [],
                    "executed_child_steps": [],
                    "actual_hhmm_handoff": {},
                }
            )
            finish_timing(report, branch_mode)
            progress_writer(report)
            return report
        source_fetch_session_guard = _evaluate_source_fetch_session_guard(for_trade_date, session_guard=session_guard)
        report["source_fetch_session_guard"] = source_fetch_session_guard
        if source_fetch_session_guard.get("status") == "blocked":
            report.update(
                {
                    "status": "blocked",
                    "reason": "BLOCKED_N3_SOURCE_FETCH_SESSION_GUARD",
                    "execution_mode": "blocked",
                    "source_fetch_session_reason": str(source_fetch_session_guard.get("source_fetch_session_reason") or ""),
                    "observed_local_date": str(source_fetch_session_guard.get("observed_local_date") or ""),
                    "observed_local_time": str(source_fetch_session_guard.get("observed_local_time") or ""),
                    "planned_child_steps": [],
                    "executed_child_steps": [],
                    "actual_hhmm_handoff": {},
                }
            )
            finish_timing(report, branch_mode)
            progress_writer(report)
            return report
        if source_fetch_session_guard.get("status") == "noop":
            report.update(
                {
                    "status": "noop",
                    "reason": "non_trading_session_source_fetch_noop",
                    "execution_mode": "noop",
                    "post_close_noop": False,
                    "noop_reason": "non_trading_session_source_fetch_noop",
                    "source_fetch_session_reason": str(source_fetch_session_guard.get("source_fetch_session_reason") or ""),
                    "observed_local_date": str(source_fetch_session_guard.get("observed_local_date") or ""),
                    "observed_local_time": str(source_fetch_session_guard.get("observed_local_time") or ""),
                    "planned_child_steps": [],
                    "executed_child_steps": [],
                    "actual_hhmm_handoff": {},
                }
            )
            finish_timing(report, branch_mode)
            progress_writer(report)
            return report
    plan = build_proof_poller_plan(
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        source_condition_run_id=source_condition_run_id,
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        n4_context_run_id=n4_context_run_id,
        hint_proof_kind=hint_proof_kind,
        execute=execute,
        python_executable=python_executable,
        max_alignment_retries=max_alignment_retries,
        retry_sleep_seconds=retry_sleep_seconds,
        branch_mode=branch_mode,
    )
    report.update(plan)
    if not execute:
        finish_timing(report, branch_mode)
        progress_writer(report)
        return report
    return _execute_child_sequence(
        report=report,
        for_trade_date=for_trade_date,
        source_trade_date=source_trade_date,
        source_condition_run_id=source_condition_run_id,
        subscription_run_id=subscription_run_id,
        preload_run_id=preload_run_id,
        n4_context_run_id=n4_context_run_id,
        hint_proof_kind=hint_proof_kind,
        python_executable=python_executable,
        command_runner=command_runner or _run_subprocess_command,
        sleep_fn=sleep_fn or time.sleep,
        max_alignment_retries=max_alignment_retries,
        retry_sleep_seconds=retry_sleep_seconds,
        progress_writer=progress_writer,
        post_close_noop_checker=post_close_noop_checker,
        branch_mode=branch_mode,
        timing_started_at=timing_started_at,
        timing_started_perf=timing_started_perf,
    )


def _execute_child_sequence(
    *,
    report: dict[str, Any],
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    n4_context_run_id: str,
    hint_proof_kind: str,
    python_executable: str,
    command_runner: CommandRunner,
    sleep_fn: SleepFn,
    max_alignment_retries: int,
    retry_sleep_seconds: float,
    progress_writer: ProgressWriter,
    post_close_noop_checker: CloseNoopChecker | None,
    branch_mode: str,
    timing_started_at: str,
    timing_started_perf: float,
) -> dict[str, Any]:
    common = {
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "source_condition_run_id": source_condition_run_id,
        "subscription_run_id": subscription_run_id,
        "preload_run_id": preload_run_id,
        "n4_context_run_id": n4_context_run_id,
    }
    executed_steps: list[dict[str, Any]] = []
    report["executed_child_steps"] = executed_steps
    report["actual_hhmm_handoff"] = {}

    def flush_progress() -> None:
        _refresh_closeout_progress(report)
        _refresh_report_timing(
            report,
            started_at=timing_started_at,
            started_perf=timing_started_perf,
            branch_mode=branch_mode,
        )
        progress_writer(report)

    flush_progress()

    session_guard = _evaluate_for_trade_date_session_guard(for_trade_date)
    session_guard["lineage_config_used"] = bool(report.get("lineage_config_used", False))
    report["session_guard"] = session_guard
    if session_guard.get("status") == "blocked":
        report.update(
            {
                "status": "blocked",
                "reason": "BLOCKED_N3_PROOF_POLLER_SESSION_GUARD",
                "execution_mode": "blocked",
                "session_guard_reason": str(session_guard.get("session_guard_reason") or ""),
                "observed_local_date": str(session_guard.get("observed_local_date") or ""),
                "observed_local_time": str(session_guard.get("observed_local_time") or ""),
            }
        )
        flush_progress()
        return report
    if session_guard.get("status") == "noop":
        report.update(
            {
                "status": "noop",
                "reason": "noop_for_trade_date_not_current_session",
                "execution_mode": "noop",
                "post_close_noop": False,
                "noop_reason": "for_trade_date_not_current_session",
                "session_guard_reason": str(session_guard.get("session_guard_reason") or ""),
                "observed_local_date": str(session_guard.get("observed_local_date") or ""),
                "observed_local_time": str(session_guard.get("observed_local_time") or ""),
            }
        )
        flush_progress()
        return report
    flush_progress()

    n3p_source_run_id = ""
    n3p_target = ""
    hint_target = ""
    if branch_mode in {"both", "n3p_only"}:
        post_close_noop = _evaluate_post_close_noop(
            checker=post_close_noop_checker,
            for_trade_date=for_trade_date,
            source_trade_date=source_trade_date,
            source_condition_run_id=source_condition_run_id,
            subscription_run_id=subscription_run_id,
            preload_run_id=preload_run_id,
            n4_context_run_id=n4_context_run_id,
        )
        report["post_close_noop_check"] = post_close_noop
        if post_close_noop.get("post_close_noop") is True:
            source_run_id = str(post_close_noop.get("existing_source_run_id") or n3p_source_payload_run_id(for_trade_date, "1500"))
            target_run_id = str(post_close_noop.get("existing_n3p_target_run_id") or n3p_target_run_id(for_trade_date, subscription_run_id, "1500"))
            report.update(
                {
                    "status": "noop",
                    "reason": "noop_existing_close_proof_passed",
                    "execution_mode": "noop",
                    "post_close_noop": True,
                    "noop_reason": str(post_close_noop.get("noop_reason") or "existing_1500_source_and_proof_passed"),
                    "n3p_status": "noop_existing_close_proof_passed",
                    "existing_n3p_source_run_id": source_run_id,
                    "existing_n3p_target_run_id": target_run_id,
                    "resolved_target_run_ids": {
                        "n3p_source_payload_run_id": source_run_id,
                        "n3p_target_run_id": target_run_id,
                    },
                }
            )
            report["actual_hhmm_handoff"]["n3p"] = {
                "actual_hhmm": str(post_close_noop.get("actual_hhmm") or "1500"),
                "source_payload_run_id": source_run_id,
                "target_run_id": target_run_id,
            }
            report["n3p_actual_hhmm"] = report["actual_hhmm_handoff"]["n3p"]["actual_hhmm"]
            report["n3p_target_run_id"] = target_run_id
            flush_progress()
            return report
        report["post_close_noop"] = False
        flush_progress()

        n3p_source_step = {
            "step_id": "n3p_current_source_fetch",
            "runner_path": "scripts/run_n3p_current_source_fetch_once.py",
            "argv": _child_argv(
                python_executable,
                "scripts/run_n3p_current_source_fetch_once.py",
                common,
                target_run_id=n3p_source_payload_candidate_run_id(for_trade_date),
                execute=True,
            ),
        }
        n3p_source_result, retry_trace = _run_n3p_source_fetch_with_alignment_retry(
            n3p_source_step,
            command_runner=command_runner,
            executed_steps=executed_steps,
            sleep_fn=sleep_fn,
            max_alignment_retries=max_alignment_retries,
            retry_sleep_seconds=retry_sleep_seconds,
            progress_callback=flush_progress,
        )
        report["n3p_source_alignment_retry"] = retry_trace
        flush_progress()
        if _child_failed(n3p_source_result):
            blocked = _blocked_after_child(report, n3p_source_result)
            report["n3p_status"] = "blocked"
            flush_progress()
            return blocked
        n3p_source_payload = n3p_source_result.get("json", {})
        n3p_hhmm = _extract_string(n3p_source_payload, "actual_until_hhmm", "actual_hhmm", "canonical_proof_minute", "actual_proof_minute")
        if not n3p_hhmm:
            blocked = _blocked_missing_handoff(report, "n3p_current_source_fetch", "actual_hhmm")
            report["n3p_status"] = "blocked"
            flush_progress()
            return blocked
        n3p_source_run_id = _extract_string(
            n3p_source_payload,
            "source_payload_run_id",
            "mixed_realtime_source_payload_run_id",
        ) or n3p_source_payload_run_id(for_trade_date, n3p_hhmm)
        n3p_source_path = _extract_string(
            n3p_source_payload,
            "source_artifact_path",
            "source_payload_path",
            "payload_path",
        ) or n3p_source_artifact_path(for_trade_date, n3p_hhmm)
        n3p_target = n3p_target_run_id(for_trade_date, subscription_run_id, n3p_hhmm)
        report["actual_hhmm_handoff"]["n3p"] = {
            "actual_hhmm": n3p_hhmm,
            "source_payload_run_id": n3p_source_run_id,
            "source_artifact_path": n3p_source_path,
            "source_payload_hash": _extract_string(n3p_source_payload, "source_payload_hash", "payload_hash"),
            "target_run_id": n3p_target,
        }
        report["n3p_actual_hhmm"] = n3p_hhmm
        report["n3p_target_run_id"] = n3p_target
        flush_progress()

        n3p_preflight_step = {
            "step_id": "n3p_trigger_proof_preflight",
            "runner_path": "scripts/run_n3p_trigger_proof_preflight_once.py",
            "argv": _child_argv(
                python_executable,
                "scripts/run_n3p_trigger_proof_preflight_once.py",
                common,
                source_run_id=n3p_source_run_id,
                target_run_id=n3p_target,
                source_payload_path=n3p_source_path,
                contract_path=f"tmp/N3P_{for_trade_date}_{n3p_hhmm}_trigger_proof_contract.json",
                preflight_path=f"tmp/N3P_{for_trade_date}_{n3p_hhmm}_trigger_proof_preflight.json",
                json_report_path=f"tmp/N3P_{for_trade_date}_{n3p_hhmm}_trigger_proof_preflight_report.json",
                execute=False,
            ),
        }
        n3p_preflight_result = _run_child_step(
            n3p_preflight_step,
            command_runner=command_runner,
            executed_steps=executed_steps,
            progress_callback=flush_progress,
        )
        if _child_failed(n3p_preflight_result):
            blocked = _blocked_after_child(report, n3p_preflight_result)
            report["n3p_status"] = "blocked"
            flush_progress()
            return blocked
        n3p_preflight_handoff = _validate_n3p_preflight_artifacts(
            n3p_preflight_result=n3p_preflight_result,
            expected_target_run_id=n3p_target,
        )
        report["actual_hhmm_handoff"]["n3p"]["preflight_artifacts"] = n3p_preflight_handoff
        flush_progress()
        if n3p_preflight_handoff.get("status") != "passed":
            blocked = _blocked_preflight_artifact_handoff(report, n3p_preflight_handoff)
            report["n3p_status"] = "blocked"
            flush_progress()
            return blocked

        n3p_execute_step = {
            "step_id": "n3p_trigger_proof_execute",
            "runner_path": "scripts/run_v3_realtime_virtual_metric_writer_once.py",
            "argv": [
                python_executable,
                "scripts/run_v3_realtime_virtual_metric_writer_once.py",
                "--contract-path",
                str(n3p_preflight_handoff["contract_path"]),
                "--preflight-path",
                str(n3p_preflight_handoff["preflight_path"]),
                "--source-payload-path",
                n3p_source_path,
                "--json-report-path",
                f"tmp/N3P_{for_trade_date}_{n3p_hhmm}_trigger_proof_execute_report.json",
                "--rollback-sql-path",
                n3p_rollback_sql_path(for_trade_date, n3p_hhmm),
                "--execute",
                "--user-confirmed",
            ],
        }
        n3p_execute_result = _run_child_step(
            n3p_execute_step,
            command_runner=command_runner,
            executed_steps=executed_steps,
            progress_callback=flush_progress,
        )
        if _child_failed(n3p_execute_result):
            blocked = _blocked_after_child(report, n3p_execute_result)
            report["n3p_status"] = "blocked"
            flush_progress()
            return blocked
        n3p_rollback_handoff = _validate_n3p_rollback_artifact(
            rollback_sql_path=n3p_rollback_sql_path(for_trade_date, n3p_hhmm),
            expected_target_run_id=n3p_target,
        )
        report["actual_hhmm_handoff"]["n3p"]["rollback_artifact"] = n3p_rollback_handoff
        flush_progress()
        if n3p_rollback_handoff.get("status") != "passed":
            blocked = _blocked_n3p_rollback_handoff(report, n3p_rollback_handoff)
            report["n3p_status"] = "blocked"
            flush_progress()
            return blocked
        report["n3p_status"] = "passed"
        flush_progress()
        if branch_mode == "n3p_only":
            report["status"] = "passed"
            report["reason"] = ""
            report["execution_mode"] = "execute"
            report["hint_status"] = "skipped"
            report["resolved_target_run_ids"] = {
                "n3p_source_payload_run_id": n3p_source_run_id,
                "n3p_target_run_id": n3p_target,
            }
            flush_progress()
            return report

    hint_source_step = {
        "step_id": "n3_hint_source_fetch",
        "runner_path": "scripts/run_n3_hint_index_board_1m_source_fetch_once.py",
        "argv": _child_argv(
            python_executable,
            "scripts/run_n3_hint_index_board_1m_source_fetch_once.py",
            common,
            target_run_id=hint_source_candidate_run_id(for_trade_date),
            hint_proof_kind=hint_proof_kind,
            json_report_path=hint_source_child_report_path(for_trade_date),
            execute=True,
        ),
    }
    hint_source_result = _run_child_step(
        hint_source_step,
        command_runner=command_runner,
        executed_steps=executed_steps,
        progress_callback=flush_progress,
    )
    if _child_failed(hint_source_result):
        blocked = _blocked_after_child(report, hint_source_result)
        report["hint_status"] = "blocked"
        flush_progress()
        return blocked
    hint_source_payload = hint_source_result.get("json", {})
    hint_hhmm = _extract_string(hint_source_payload, "actual_until_hhmm", "actual_hhmm", "canonical_proof_minute", "actual_proof_minute")
    if not hint_hhmm:
        blocked = _blocked_missing_handoff(report, "n3_hint_source_fetch", "actual_hhmm")
        report["hint_status"] = "blocked"
        flush_progress()
        return blocked
    hint_source_path = _extract_string(
        hint_source_payload,
        "source_artifact_path",
        "source_payload_path",
        "payload_path",
    ) or hint_source_artifact_path(for_trade_date, hint_hhmm)
    hint_target = hint_target_run_id(for_trade_date, subscription_run_id, hint_hhmm, hint_proof_kind=hint_proof_kind)
    report["actual_hhmm_handoff"]["hint"] = {
        "actual_hhmm": hint_hhmm,
        "source_artifact_path": hint_source_path,
        "source_report_path": _extract_string(hint_source_payload, "source_report_path", "report_path"),
        "source_payload_hash": _extract_string(hint_source_payload, "source_payload_hash", "payload_hash"),
        "source_artifact_file_sha256": _extract_string(hint_source_payload, "source_artifact_file_sha256", "file_sha256"),
        "idempotency_decision": str(hint_source_payload.get("idempotency_decision") or ""),
        "artifact_written": hint_source_payload.get("artifact_written"),
        "artifact_reused": hint_source_payload.get("artifact_reused"),
        "candidate_payload_hash": str(hint_source_payload.get("candidate_payload_hash") or ""),
        "candidate_differs_from_persisted": bool(hint_source_payload.get("candidate_differs_from_persisted")),
        "target_run_id": hint_target,
    }
    report["hint_actual_hhmm"] = hint_hhmm
    report["hint_target_run_id"] = hint_target
    flush_progress()

    if _is_hint_source_noop_claim(hint_source_payload):
        noop_handoff = _validate_hint_source_noop_handoff(
            hint_source_payload=hint_source_payload,
            expected_hhmm=hint_hhmm,
            expected_target_run_id=hint_target,
            expected_for_trade_date=for_trade_date,
            expected_subscription_run_id=subscription_run_id,
            expected_hint_proof_kind=hint_proof_kind,
        )
        report["actual_hhmm_handoff"]["hint"]["idempotency"] = noop_handoff
        if noop_handoff.get("status") != "passed":
            report.update(
                {
                    "status": "blocked",
                    "reason": str(noop_handoff.get("reason") or "hint_source_noop_handoff_invalid"),
                    "execution_mode": "blocked",
                    "hint_status": "blocked",
                    "blocked_hint_source_noop_handoff": dict(noop_handoff),
                }
            )
            flush_progress()
            return report

        report["hint_status"] = "noop"
        report["hint_noop_reason"] = HINT_SOURCE_IDEMPOTENT_NOOP_REASON
        resolved_target_run_ids = {"hint_target_run_id": hint_target}
        if n3p_source_run_id:
            resolved_target_run_ids["n3p_source_payload_run_id"] = n3p_source_run_id
        if n3p_target:
            resolved_target_run_ids["n3p_target_run_id"] = n3p_target
        report["resolved_target_run_ids"] = resolved_target_run_ids
        if branch_mode == "hint_only":
            report.update(
                {
                    "status": "noop",
                    "reason": HINT_SOURCE_IDEMPOTENT_NOOP_REASON,
                    "execution_mode": "noop",
                    "noop_reason": HINT_SOURCE_IDEMPOTENT_NOOP_REASON,
                }
            )
        else:
            report.update(
                {
                    "status": "passed",
                    "reason": "",
                    "execution_mode": "execute",
                }
            )
        flush_progress()
        return report

    hint_preflight_step = {
        "step_id": "n3_hint_proof_preflight",
        "runner_path": "scripts/run_n3_hint_index_board_1m_proof_preflight_once.py",
        "argv": _child_argv(
            python_executable,
            "scripts/run_n3_hint_index_board_1m_proof_preflight_once.py",
            common,
            target_run_id=hint_target,
            source_artifact_path=hint_source_path,
            hint_proof_kind=hint_proof_kind,
            contract_path=f"tmp/N3_hint_{for_trade_date}_{hint_hhmm}_midday_bridge_v1_contract.json",
            preflight_path=f"tmp/N3_hint_{for_trade_date}_{hint_hhmm}_midday_bridge_v1_preflight.json",
            json_report_path=f"tmp/N3_hint_{for_trade_date}_{hint_hhmm}_midday_bridge_v1_preflight_report.json",
            execute=False,
        ),
    }
    hint_preflight_result = _run_child_step(
        hint_preflight_step,
        command_runner=command_runner,
        executed_steps=executed_steps,
        progress_callback=flush_progress,
    )
    if _child_failed(hint_preflight_result):
        blocked = _blocked_after_child(report, hint_preflight_result)
        report["hint_status"] = "blocked"
        flush_progress()
        return blocked
    hint_preflight_handoff = _validate_hint_preflight_artifacts(
        hint_preflight_result=hint_preflight_result,
        expected_target_run_id=hint_target,
        expected_proof_kind=hint_proof_kind,
    )
    report["actual_hhmm_handoff"]["hint"]["preflight_artifacts"] = hint_preflight_handoff
    flush_progress()
    if hint_preflight_handoff.get("status") != "passed":
        blocked = _blocked_preflight_artifact_handoff(report, hint_preflight_handoff)
        report["hint_status"] = "blocked"
        flush_progress()
        return blocked

    hint_execute_step = {
        "step_id": "n3_hint_proof_execute",
        "runner_path": "scripts/run_n3_hint_index_board_1m_proof_execute_once.py",
        "argv": _child_argv(
            python_executable,
            "scripts/run_n3_hint_index_board_1m_proof_execute_once.py",
            common,
            target_run_id=hint_target,
            source_artifact_path=hint_source_path,
            hint_proof_kind=hint_proof_kind,
            contract_path=str(hint_preflight_handoff["contract_path"]),
            preflight_path=str(hint_preflight_handoff["preflight_path"]),
            json_report_path=f"tmp/N3_hint_index_board_1m_{for_trade_date}_{hint_hhmm}_midday_bridge_v1_execute_report.json",
            execute=True,
        ),
    }
    hint_execute_result = _run_child_step(
        hint_execute_step,
        command_runner=command_runner,
        executed_steps=executed_steps,
        progress_callback=flush_progress,
    )
    if _child_failed(hint_execute_result):
        blocked = _blocked_after_child(report, hint_execute_result)
        report["hint_status"] = "blocked"
        flush_progress()
        return blocked

    report["status"] = "passed"
    report["reason"] = ""
    report["execution_mode"] = "execute"
    report["hint_status"] = "passed"
    resolved_target_run_ids = {"hint_target_run_id": hint_target}
    if n3p_source_run_id:
        resolved_target_run_ids["n3p_source_payload_run_id"] = n3p_source_run_id
    if n3p_target:
        resolved_target_run_ids["n3p_target_run_id"] = n3p_target
    report["resolved_target_run_ids"] = resolved_target_run_ids
    flush_progress()
    return report


def _run_n3p_source_fetch_with_alignment_retry(
    step: Mapping[str, Any],
    *,
    command_runner: CommandRunner,
    executed_steps: list[dict[str, Any]],
    sleep_fn: SleepFn,
    max_alignment_retries: int,
    retry_sleep_seconds: float,
    progress_callback: Callable[[], Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    max_retries = max(0, int(max_alignment_retries))
    sleep_seconds = max(0.0, float(retry_sleep_seconds))
    attempts: list[dict[str, Any]] = []

    for attempt_index in range(max_retries + 1):
        result = _run_child_step(
            step,
            command_runner=command_runner,
            executed_steps=executed_steps,
            progress_callback=progress_callback,
        )
        attempts.append(_alignment_attempt_summary(result, attempt_index + 1))
        if not _child_failed(result):
            status = "aligned" if attempt_index == 0 else "aligned_after_retry"
            return result, _alignment_retry_trace(status=status, attempts=attempts, max_retries=max_retries, sleep_seconds=sleep_seconds)
        if not _is_retryable_adjacent_alignment_blocker(result):
            return result, _alignment_retry_trace(status="not_retryable", attempts=attempts, max_retries=max_retries, sleep_seconds=sleep_seconds)
        if attempt_index >= max_retries:
            exhausted = dict(result)
            payload = dict(_child_payload(result))
            payload.update(
                {
                    "result": N3P_SOURCE_ALIGNMENT_RETRY_EXHAUSTED_BLOCKER,
                    "reason": "adjacent_minute_source_boundary_race_retry_exhausted",
                    "retry_attempt_count": len(attempts),
                    "max_alignment_retries": max_retries,
                    "n3p_source_alignment_retry_attempts": attempts,
                    "artifact_written": False,
                    "source_payload_registered": False,
                    "database_written": False,
                }
            )
            exhausted["returncode"] = 2
            exhausted["json"] = payload
            return exhausted, _alignment_retry_trace(
                status="retry_exhausted",
                attempts=attempts,
                max_retries=max_retries,
                sleep_seconds=sleep_seconds,
            )
        if sleep_seconds:
            sleep_fn(sleep_seconds)

    # Defensive fallback; the loop always returns.
    return result, _alignment_retry_trace(status="retry_exhausted", attempts=attempts, max_retries=max_retries, sleep_seconds=sleep_seconds)


def _evaluate_post_close_noop(
    *,
    checker: CloseNoopChecker | None,
    for_trade_date: str,
    source_trade_date: str,
    source_condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    n4_context_run_id: str,
) -> dict[str, Any]:
    if checker is None:
        return {"post_close_noop": False, "noop_reason": "post_close_noop_checker_not_configured"}
    context = {
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "source_condition_run_id": source_condition_run_id,
        "subscription_run_id": subscription_run_id,
        "preload_run_id": preload_run_id,
        "n4_context_run_id": n4_context_run_id,
        "close_hhmm": "1500",
        "expected_source_run_id": n3p_source_payload_run_id(for_trade_date, "1500"),
        "expected_n3p_target_run_id": n3p_target_run_id(for_trade_date, subscription_run_id, "1500"),
    }
    try:
        result = dict(checker(context))
    except Exception as exc:  # pragma: no cover - defensive guard for production CLI.
        return {
            "post_close_noop": False,
            "noop_reason": "post_close_noop_checker_error",
            "error": str(exc),
        }
    result.setdefault("post_close_noop", False)
    return result


def _evaluate_for_trade_date_session_guard(for_trade_date: str) -> dict[str, Any]:
    try:
        observation = _current_session_observation()
    except Exception as exc:  # pragma: no cover - defensive guard for production CLI.
        return {
            "effective_for_trade_date": _date_digits(for_trade_date) or str(for_trade_date or ""),
            "observed_local_date": "",
            "observed_local_time": "",
            "observed_local_datetime": "",
            "lineage_config_used": None,
            "session_guard_policy": "for_trade_date_not_future_before_source_fetch_v1",
            "status": "blocked",
            "session_guard_passed": False,
            "session_guard_reason": "session_observation_failed",
            "error": str(exc),
        }
    effective_for_trade_date = _date_digits(for_trade_date)
    observed_local_date = _date_digits(str(observation.get("observed_local_date") or ""))
    guard = {
        "effective_for_trade_date": effective_for_trade_date or str(for_trade_date or ""),
        "observed_local_date": observed_local_date,
        "observed_local_time": str(observation.get("observed_local_time") or ""),
        "observed_local_datetime": str(observation.get("observed_local_datetime") or ""),
        "lineage_config_used": None,
        "session_guard_policy": "for_trade_date_not_future_before_source_fetch_v1",
    }
    if len(effective_for_trade_date) != 8:
        return {
            **guard,
            "status": "blocked",
            "session_guard_passed": False,
            "session_guard_reason": "invalid_effective_for_trade_date",
        }
    if len(observed_local_date) != 8:
        return {
            **guard,
            "status": "blocked",
            "session_guard_passed": False,
            "session_guard_reason": "observed_local_date_unavailable",
        }
    if observed_local_date < effective_for_trade_date:
        return {
            **guard,
            "status": "noop",
            "session_guard_passed": False,
            "post_close_noop": False,
            "session_guard_reason": "for_trade_date_after_observed_local_date",
        }
    return {
        **guard,
        "status": "passed",
        "session_guard_passed": True,
        "session_guard_reason": (
            "for_trade_date_is_observed_local_date"
            if observed_local_date == effective_for_trade_date
            else "for_trade_date_before_observed_local_date"
        ),
    }


def _evaluate_source_fetch_session_guard(for_trade_date: str, *, session_guard: Mapping[str, Any]) -> dict[str, Any]:
    effective_for_trade_date = _date_digits(for_trade_date)
    observed_local_date = _date_digits(str(session_guard.get("observed_local_date") or ""))
    observed_local_time = str(session_guard.get("observed_local_time") or "")
    observed_hhmm = _hhmm_from_time(observed_local_time)
    guard = {
        "effective_for_trade_date": effective_for_trade_date or str(for_trade_date or ""),
        "observed_local_date": observed_local_date,
        "observed_local_time": observed_local_time,
        "observed_local_datetime": str(session_guard.get("observed_local_datetime") or ""),
        "source_fetch_session_policy": "same_date_source_fetch_window_0925_1530_v1",
        "source_fetch_window_start_hhmm": SOURCE_FETCH_WINDOW_START_HHMM,
        "source_fetch_window_end_hhmm": SOURCE_FETCH_WINDOW_END_HHMM,
        "observed_hhmm": observed_hhmm,
    }
    if len(effective_for_trade_date) != 8:
        return {
            **guard,
            "status": "blocked",
            "source_fetch_session_passed": False,
            "source_fetch_session_reason": "invalid_effective_for_trade_date",
        }
    if len(observed_local_date) != 8:
        return {
            **guard,
            "status": "blocked",
            "source_fetch_session_passed": False,
            "source_fetch_session_reason": "observed_local_date_unavailable",
        }
    if not observed_hhmm:
        return {
            **guard,
            "status": "blocked",
            "source_fetch_session_passed": False,
            "source_fetch_session_reason": "observed_local_time_unavailable",
        }
    if observed_local_date != effective_for_trade_date:
        return {
            **guard,
            "status": "passed",
            "source_fetch_session_passed": True,
            "source_fetch_session_reason": "not_same_local_date",
        }
    if observed_hhmm < SOURCE_FETCH_WINDOW_START_HHMM:
        return {
            **guard,
            "status": "noop",
            "source_fetch_session_passed": False,
            "source_fetch_session_reason": "before_source_fetch_window",
        }
    if observed_hhmm > SOURCE_FETCH_WINDOW_END_HHMM:
        return {
            **guard,
            "status": "noop",
            "source_fetch_session_passed": False,
            "source_fetch_session_reason": "after_source_fetch_window",
        }
    return {
        **guard,
        "status": "passed",
        "source_fetch_session_passed": True,
        "source_fetch_session_reason": "source_fetch_window_open",
    }


def _hhmm_from_time(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:4] if len(digits) >= 4 else ""


def _current_session_observation() -> dict[str, str]:
    now = datetime.now(ASIA_SHANGHAI)
    return {
        "observed_local_date": now.strftime("%Y%m%d"),
        "observed_local_time": now.strftime("%H:%M:%S"),
        "observed_local_datetime": now.isoformat(),
    }


def _date_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def _default_post_close_noop_checker(context: Mapping[str, Any]) -> dict[str, Any]:
    for_trade_date = str(context.get("for_trade_date") or "")
    if not _is_today_trade_date(for_trade_date):
        return {"post_close_noop": False, "noop_reason": "for_trade_date_not_today"}
    current_canonical = _current_local_canonical_hhmm()
    if current_canonical != "1500":
        return {
            "post_close_noop": False,
            "noop_reason": "canonical_time_not_close",
            "actual_hhmm": current_canonical,
        }
    dsn = _resolve_readonly_dsn()
    if not dsn:
        return {"post_close_noop": False, "noop_reason": "db_config_unavailable"}
    source_run_id = str(context.get("expected_source_run_id") or "")
    target_run_id = str(context.get("expected_n3p_target_run_id") or "")
    try:
        source_status, target_status = _read_market_data_run_statuses(
            dsn=dsn,
            source_run_id=source_run_id,
            target_run_id=target_run_id,
        )
    except Exception as exc:  # pragma: no cover - defensive guard for production CLI.
        return {
            "post_close_noop": False,
            "noop_reason": "read_only_db_check_failed",
            "error": str(exc),
        }
    if source_status == "passed" and target_status == "passed":
        return {
            "post_close_noop": True,
            "noop_reason": "existing_1500_source_and_proof_passed",
            "actual_hhmm": "1500",
            "existing_source_run_id": source_run_id,
            "existing_n3p_target_run_id": target_run_id,
            "source_status": source_status,
            "proof_status": target_status,
            "read_only_db_check": True,
        }
    return {
        "post_close_noop": False,
        "noop_reason": "existing_1500_source_or_proof_not_passed",
        "actual_hhmm": "1500",
        "existing_source_run_id": source_run_id,
        "existing_n3p_target_run_id": target_run_id,
        "source_status": source_status,
        "proof_status": target_status,
        "read_only_db_check": True,
    }


def _is_today_trade_date(for_trade_date: str) -> bool:
    return datetime.now(ASIA_SHANGHAI).strftime("%Y%m%d") == for_trade_date


def _current_local_canonical_hhmm() -> str:
    now = datetime.now(ASIA_SHANGHAI)
    if now.hour > 15 or (now.hour == 15 and now.minute >= 0):
        return "1500"
    return now.strftime("%H%M")


def _resolve_readonly_dsn() -> str:
    for name in ("ASHARE_V3_POSTGRES_DSN", "DATABASE_URL", "PG_DSN", "POSTGRES_DSN"):
        value = os.environ.get(name)
        if value and not _is_placeholder_dsn(value):
            return value
    if os.environ.get("PGHOST") and os.environ.get("PGDATABASE"):
        return ""
    try:
        from scripts.check_condition_source_ready import DEFAULT_DSN  # type: ignore

        return str(DEFAULT_DSN)
    except Exception:
        return ""


def _is_placeholder_dsn(value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return True
    if normalized.startswith("__") and normalized.endswith("__"):
        return True
    return normalized.upper() in {
        "CHANGE_ME",
        "CHANGEME",
        "TODO",
        "PLACEHOLDER",
        "REPLACE_ME",
    }


def _read_market_data_run_statuses(*, dsn: str, source_run_id: str, target_run_id: str) -> tuple[str, str]:
    import psycopg

    with psycopg.connect(dsn) as conn:
        conn.execute("BEGIN READ ONLY")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT run_id, status
            FROM common_market_data_run
            WHERE run_id IN (%s, %s)
            """,
            (source_run_id, target_run_id),
        )
        statuses = {str(run_id): str(status) for run_id, status in cur.fetchall()}
    return statuses.get(source_run_id, ""), statuses.get(target_run_id, "")


def _alignment_retry_trace(
    *,
    status: str,
    attempts: list[dict[str, Any]],
    max_retries: int,
    sleep_seconds: float,
) -> dict[str, Any]:
    return {
        "status": status,
        "retryable_failure_class": N3P_SOURCE_ALIGNMENT_ADJACENT_RACE,
        "attempt_count": len(attempts),
        "max_alignment_retries": max_retries,
        "retry_sleep_seconds": sleep_seconds,
        "attempts": attempts,
        "no_relabel": True,
        "applies_before_artifact_register_write": True,
    }


def _alignment_attempt_summary(result: Mapping[str, Any], attempt: int) -> dict[str, Any]:
    payload = _child_payload(result)
    stock_hhmm = _extract_string(payload, "stock_canonical_hhmm", "stock_canonical_until_hhmm")
    index_board_hhmm = _extract_string(payload, "index_board_hhmm", "index_board_until_hhmm")
    minute_delta = payload.get("minute_delta")
    if minute_delta in (None, "") and stock_hhmm and index_board_hhmm:
        minute_delta = _hhmm_minute_delta(stock_hhmm, index_board_hhmm)
    return {
        "attempt": attempt,
        "result": str(payload.get("result") or ""),
        "reason": str(payload.get("reason") or ""),
        "alignment_failure_class": str(payload.get("alignment_failure_class") or ""),
        "minute_delta": minute_delta,
        "stock_canonical_hhmm": stock_hhmm,
        "index_board_hhmm": index_board_hhmm,
        "artifact_written": bool(payload.get("artifact_written", False)),
        "source_payload_registered": bool(payload.get("source_payload_registered", False)),
        "database_written": bool(payload.get("database_written", False)),
        "market_data_pulled": bool(payload.get("market_data_pulled", False)),
        "writes_outbox": bool(payload.get("writes_outbox", False)),
        "retryable": _is_retryable_adjacent_alignment_blocker(result),
    }


def _is_retryable_adjacent_alignment_blocker(result: Mapping[str, Any]) -> bool:
    payload = _child_payload(result)
    if str(payload.get("result") or "") != N3P_SOURCE_ALIGNMENT_BLOCKER:
        return False
    failure_class = str(payload.get("alignment_failure_class") or "")
    if failure_class == N3P_SOURCE_ALIGNMENT_ADJACENT_RACE:
        return True
    minute_delta = payload.get("minute_delta")
    if minute_delta in (None, ""):
        stock_hhmm = _extract_string(payload, "stock_canonical_hhmm", "stock_canonical_until_hhmm")
        index_board_hhmm = _extract_string(payload, "index_board_hhmm", "index_board_until_hhmm")
        minute_delta = _hhmm_minute_delta(stock_hhmm, index_board_hhmm)
    try:
        return int(minute_delta) == 1
    except (TypeError, ValueError):
        return False


def _child_payload(result: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = result.get("json")
    return payload if isinstance(payload, Mapping) else {}


def _hhmm_minute_delta(left_hhmm: str, right_hhmm: str) -> int | None:
    left = _hhmm_to_minutes(left_hhmm)
    right = _hhmm_to_minutes(right_hhmm)
    if left is None or right is None:
        return None
    return abs(left - right)


def _hhmm_to_minutes(hhmm: str) -> int | None:
    value = "".join(ch for ch in str(hhmm or "") if ch.isdigit())
    if len(value) != 4:
        return None
    hour = int(value[:2])
    minute = int(value[2:])
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _run_child_step(
    step: Mapping[str, Any],
    *,
    command_runner: CommandRunner,
    executed_steps: list[dict[str, Any]],
    progress_callback: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    child_started_at = _timing_timestamp()
    child_started_perf = time.perf_counter()
    argv = [str(value) for value in step["argv"]]
    placeholder_tokens = [value for value in argv if ACTUAL_HHMM_PLACEHOLDER in value]
    forbidden_tokens = _forbidden_executable_argv_tokens(argv)
    if placeholder_tokens or forbidden_tokens:
        result = _attach_child_timing({
            "step_id": step["step_id"],
            "argv": argv,
            "returncode": 1,
            "json": {
                "result": "BLOCKED_N3_POLLER_EXECUTABLE_ARGV",
                "placeholder_tokens": placeholder_tokens,
                "forbidden_tokens": forbidden_tokens,
            },
        }, started_at=child_started_at, started_perf=child_started_perf)
        executed_steps.append(result)
        if progress_callback:
            progress_callback()
        return result
    try:
        raw = command_runner(argv)
    except Exception as exc:  # pragma: no cover - defensive path for real CLI runner.
        result = _attach_child_timing({
            "step_id": step["step_id"],
            "argv": argv,
            "returncode": 1,
            "json": {"result": "BLOCKED_N3_POLLER_CHILD_EXCEPTION", "reason": str(exc)},
        }, started_at=child_started_at, started_perf=child_started_perf)
        executed_steps.append(result)
        if progress_callback:
            progress_callback()
        return result
    result = _coerce_child_result(raw)
    result["step_id"] = step["step_id"]
    result["argv"] = argv
    _attach_child_timing(result, started_at=child_started_at, started_perf=child_started_perf)
    _redact_child_result_for_parent_report(result)
    executed_steps.append(result)
    if progress_callback:
        progress_callback()
    return result


def _run_subprocess_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False)


def _coerce_child_result(raw: Any) -> dict[str, Any]:
    if isinstance(raw, subprocess.CompletedProcess):
        payload = _parse_json_stdout(raw.stdout)
        return {
            "returncode": int(raw.returncode),
            "stdout": raw.stdout,
            "stderr": raw.stderr,
            "json": payload,
        }
    if isinstance(raw, Mapping):
        result = dict(raw)
        if "json" not in result:
            if "stdout" in result:
                result["json"] = _parse_json_stdout(str(result.get("stdout") or ""))
            else:
                result["json"] = {key: value for key, value in result.items() if key not in {"returncode", "stdout", "stderr"}}
        result.setdefault("returncode", 0)
        return result
    return {"returncode": 1, "json": {"result": "BLOCKED_N3_POLLER_CHILD_RESULT_UNSUPPORTED"}}


def _parse_json_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed([line.strip() for line in stdout.splitlines() if line.strip()]):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _child_failed(result: Mapping[str, Any]) -> bool:
    if int(result.get("returncode") or 0) != 0:
        return True
    payload = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    status = str(payload.get("status") or "").lower()
    child_result = str(payload.get("result") or "")
    return status in {"blocked", "failed", "error"} or child_result.startswith("BLOCKED")


def _blocked_after_child(report: dict[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    step_id = str(result.get("step_id") or "")
    payload = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    report["status"] = "blocked"
    if payload.get("result") == N3P_SOURCE_ALIGNMENT_RETRY_EXHAUSTED_BLOCKER:
        report["reason"] = N3P_SOURCE_ALIGNMENT_RETRY_EXHAUSTED_BLOCKER
    else:
        report["reason"] = f"child_step_failed:{step_id}"
    report["execution_mode"] = "blocked"
    report["executed_child_command_count"] = len(report.get("executed_child_steps") or [])
    report["blocked_child_result"] = payload
    _refresh_closeout_progress(report, blocked_child_step=step_id)
    return report


def _blocked_missing_handoff(report: dict[str, Any], step_id: str, field_name: str) -> dict[str, Any]:
    report["status"] = "blocked"
    report["reason"] = f"child_step_missing_handoff:{step_id}:{field_name}"
    report["execution_mode"] = "blocked"
    report["executed_child_command_count"] = len(report.get("executed_child_steps") or [])
    _refresh_closeout_progress(report, blocked_child_step=step_id)
    return report


def _validate_hint_source_noop_handoff(
    *,
    hint_source_payload: Mapping[str, Any],
    expected_hhmm: str,
    expected_target_run_id: str,
    expected_for_trade_date: str,
    expected_subscription_run_id: str,
    expected_hint_proof_kind: str,
) -> dict[str, Any]:
    payload_hash = str(hint_source_payload.get("payload_hash") or "")
    source_payload_hash = str(hint_source_payload.get("source_payload_hash") or "")
    checks = {
        "result": str(hint_source_payload.get("result") or "") == HINT_SOURCE_IDEMPOTENT_NOOP_RESULT,
        "status": str(hint_source_payload.get("status") or "") == "noop",
        "execution_mode": str(hint_source_payload.get("execution_mode") or "") == "noop",
        "idempotency_decision": str(hint_source_payload.get("idempotency_decision") or "") == "idempotent_pass",
        "reason": str(hint_source_payload.get("reason") or "") == HINT_SOURCE_IDEMPOTENT_NOOP_REASON,
        "for_trade_date": str(hint_source_payload.get("for_trade_date") or "") == expected_for_trade_date,
        "subscription_run_id": str(hint_source_payload.get("subscription_run_id") or "") == expected_subscription_run_id,
        "hint_proof_kind": str(hint_source_payload.get("hint_proof_kind") or "") == expected_hint_proof_kind,
        "proof_kind": str(hint_source_payload.get("proof_kind") or "") == expected_hint_proof_kind,
        "actual_until_hhmm": str(hint_source_payload.get("actual_until_hhmm") or "") == expected_hhmm,
        "target_run_id": str(hint_source_payload.get("target_run_id") or "") == expected_target_run_id,
        "source_artifact_path": bool(_extract_string(hint_source_payload, "source_artifact_path", "payload_path")),
        "source_report_path": bool(_extract_string(hint_source_payload, "source_report_path", "report_path")),
        "payload_hash": bool(payload_hash),
        "source_payload_hash": bool(source_payload_hash),
        "payload_hash_alias_matches": payload_hash == source_payload_hash,
        "source_artifact_file_sha256": bool(
            _extract_string(hint_source_payload, "source_artifact_file_sha256", "file_sha256")
        ),
        "candidate_payload_hash": bool(str(hint_source_payload.get("candidate_payload_hash") or "")),
        "artifact_written": hint_source_payload.get("artifact_written") is False,
        "artifact_reused": hint_source_payload.get("artifact_reused") is True,
        "market_data_pulled": hint_source_payload.get("market_data_pulled") is True,
        "database_written": hint_source_payload.get("database_written") is False,
        "idempotent_target_execute_contract_ready": (
            hint_source_payload.get("idempotent_target_execute_contract_ready") is False
        ),
        "writes_outbox": hint_source_payload.get("writes_outbox") is False,
        "consumes_outbox": hint_source_payload.get("consumes_outbox") is False,
        "updates_inbox_or_checkpoint": hint_source_payload.get("updates_inbox_or_checkpoint") is False,
        "starts_worker": hint_source_payload.get("starts_worker") is False,
        "touches_n4_n5_n6": hint_source_payload.get("touches_n4_n5_n6") is False,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        return {
            "status": "blocked",
            "reason": f"hint_source_noop_handoff_invalid:{','.join(failed_checks)}",
            "checks": checks,
        }
    return {
        "status": "passed",
        "reason": HINT_SOURCE_IDEMPOTENT_NOOP_REASON,
        "checks": checks,
        "target_run_id": expected_target_run_id,
        "source_artifact_path": _extract_string(hint_source_payload, "source_artifact_path", "payload_path"),
        "source_report_path": _extract_string(hint_source_payload, "source_report_path", "report_path"),
        "source_payload_hash": _extract_string(hint_source_payload, "source_payload_hash", "payload_hash"),
        "source_artifact_file_sha256": _extract_string(
            hint_source_payload,
            "source_artifact_file_sha256",
            "file_sha256",
        ),
        "candidate_payload_hash": str(hint_source_payload.get("candidate_payload_hash") or ""),
        "candidate_differs_from_persisted": bool(hint_source_payload.get("candidate_differs_from_persisted")),
        "downstream_refs": dict(hint_source_payload.get("downstream_refs") or {}),
    }


def _is_hint_source_noop_claim(hint_source_payload: Mapping[str, Any]) -> bool:
    return any(
        (
            str(hint_source_payload.get("result") or "") == HINT_SOURCE_IDEMPOTENT_NOOP_RESULT,
            str(hint_source_payload.get("status") or "") == "noop",
            str(hint_source_payload.get("execution_mode") or "") == "noop",
            str(hint_source_payload.get("idempotency_decision") or "") == "idempotent_pass",
        )
    )


def _blocked_preflight_artifact_handoff(report: dict[str, Any], handoff: Mapping[str, Any]) -> dict[str, Any]:
    report["status"] = "blocked"
    report["reason"] = str(handoff.get("reason") or "BLOCKED_PREFLIGHT_ARTIFACT_HANDOFF")
    report["execution_mode"] = "blocked"
    report["executed_child_command_count"] = len(report.get("executed_child_steps") or [])
    report["blocked_preflight_artifact_handoff"] = dict(handoff)
    _refresh_closeout_progress(report)
    return report


def _blocked_n3p_rollback_handoff(report: dict[str, Any], handoff: Mapping[str, Any]) -> dict[str, Any]:
    report["status"] = "blocked"
    report["reason"] = str(handoff.get("reason") or N3P_ROLLBACK_ARTIFACT_MISSING_BLOCKER)
    report["execution_mode"] = "blocked"
    report["executed_child_command_count"] = len(report.get("executed_child_steps") or [])
    report["blocked_n3p_rollback_handoff"] = dict(handoff)
    _refresh_closeout_progress(report, blocked_child_step="n3p_trigger_proof_execute")
    return report


def _refresh_closeout_progress(report: dict[str, Any], *, blocked_child_step: str = "") -> None:
    steps = report.get("executed_child_steps") or []
    report["executed_child_command_count"] = len(steps)
    last_successful = _last_successful_child_step(steps)
    if last_successful:
        report["last_successful_child"] = last_successful
    if blocked_child_step:
        report["blocked_child_step"] = blocked_child_step
    if report.get("status") == "blocked":
        if "blocked_child_step" not in report:
            failed_step = _first_failed_child_step(steps)
            if failed_step:
                report["blocked_child_step"] = failed_step
        n3p_summary = _n3p_output_summary(report)
        if n3p_summary:
            report["n3p_output_summary"] = n3p_summary
        step_id = str(report.get("blocked_child_step") or "")
        if step_id.startswith("n3_hint"):
            report["hint_not_reached_or_absent_reason"] = f"blocked_before_hint_target_execute:{step_id}"


def _last_successful_child_step(steps: list[dict[str, Any]]) -> str:
    for step in reversed(steps):
        if not _child_failed(step):
            return str(step.get("step_id") or "")
    return ""


def _first_failed_child_step(steps: list[dict[str, Any]]) -> str:
    for step in steps:
        if _child_failed(step):
            return str(step.get("step_id") or "")
    return ""


def _n3p_output_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    handoff = report.get("actual_hhmm_handoff")
    if not isinstance(handoff, Mapping):
        return {}
    n3p = handoff.get("n3p")
    if not isinstance(n3p, Mapping):
        return {}
    summary = {
        "actual_hhmm": n3p.get("actual_hhmm"),
        "source_payload_run_id": n3p.get("source_payload_run_id"),
        "source_artifact_path": n3p.get("source_artifact_path"),
        "source_payload_hash": n3p.get("source_payload_hash"),
        "target_run_id": n3p.get("target_run_id"),
    }
    if isinstance(n3p.get("preflight_artifacts"), Mapping):
        summary["preflight_artifacts"] = dict(n3p["preflight_artifacts"])
    if isinstance(n3p.get("rollback_artifact"), Mapping):
        summary["rollback_artifact"] = dict(n3p["rollback_artifact"])
    return {key: value for key, value in summary.items() if value not in ("", None, {})}


def _progress_writer(json_report_path: str) -> ProgressWriter:
    def write(report: Mapping[str, Any]) -> None:
        if not json_report_path:
            return
        path = Path(json_report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    return write


def _validate_n3p_preflight_artifacts(
    *,
    n3p_preflight_result: Mapping[str, Any],
    expected_target_run_id: str,
) -> dict[str, Any]:
    payload = n3p_preflight_result.get("json") if isinstance(n3p_preflight_result.get("json"), Mapping) else {}
    contract_path = _extract_string(payload, "contract_path")
    preflight_path = _extract_string(payload, "preflight_path")
    reported_target_run_id = _extract_string(payload, "target_run_id")
    handoff: dict[str, Any] = {
        "status": "passed",
        "contract_path": contract_path,
        "preflight_path": preflight_path,
        "reported_target_run_id": reported_target_run_id,
        "expected_target_run_id": expected_target_run_id,
    }
    missing_paths = [
        name
        for name, path in (("contract_path", contract_path), ("preflight_path", preflight_path))
        if not path or not Path(path).exists()
    ]
    if missing_paths:
        handoff.update(
            {
                "status": "blocked",
                "reason": "BLOCKED_N3P_PREFLIGHT_ARTIFACT_MISSING",
                "missing_paths": missing_paths,
            }
        )
        return handoff
    target_values = {
        "reported_target_run_id": reported_target_run_id,
        "contract_target_run_id": _read_artifact_target_run_id(contract_path),
        "preflight_target_run_id": _read_artifact_target_run_id(preflight_path),
    }
    handoff.update(target_values)
    mismatched = {
        key: value
        for key, value in target_values.items()
        if value != expected_target_run_id
    }
    if mismatched:
        handoff.update(
            {
                "status": "blocked",
                "reason": "BLOCKED_N3P_PREFLIGHT_ARTIFACT_TARGET_MISMATCH",
                "mismatched_targets": mismatched,
            }
        )
    return handoff


def _validate_hint_preflight_artifacts(
    *,
    hint_preflight_result: Mapping[str, Any],
    expected_target_run_id: str,
    expected_proof_kind: str,
) -> dict[str, Any]:
    payload = hint_preflight_result.get("json") if isinstance(hint_preflight_result.get("json"), Mapping) else {}
    contract_path = _extract_string(payload, "contract_path")
    preflight_path = _extract_string(payload, "preflight_path")
    reported_target_run_id = _extract_string(payload, "target_run_id")
    reported_proof_kind = _extract_string(payload, "proof_kind")
    handoff: dict[str, Any] = {
        "status": "passed",
        "contract_path": contract_path,
        "preflight_path": preflight_path,
        "reported_target_run_id": reported_target_run_id,
        "reported_proof_kind": reported_proof_kind,
        "expected_target_run_id": expected_target_run_id,
        "expected_proof_kind": expected_proof_kind,
    }
    missing_paths = [
        name
        for name, path in (("contract_path", contract_path), ("preflight_path", preflight_path))
        if not path or not Path(path).exists()
    ]
    if missing_paths:
        handoff.update(
            {
                "status": "blocked",
                "reason": "BLOCKED_N3_HINT_PREFLIGHT_ARTIFACT_MISSING",
                "missing_paths": missing_paths,
            }
        )
        return handoff

    target_values = {
        "reported_target_run_id": reported_target_run_id,
        "contract_target_run_id": _read_artifact_field(contract_path, "target_run_id"),
        "preflight_target_run_id": _read_artifact_field(preflight_path, "target_run_id"),
    }
    proof_kind_values = {
        "reported_proof_kind": reported_proof_kind,
        "contract_proof_kind": _read_artifact_field(contract_path, "proof_kind"),
        "preflight_proof_kind": _read_artifact_field(preflight_path, "proof_kind"),
    }
    handoff.update(target_values)
    handoff.update(proof_kind_values)
    mismatched_targets = {
        key: value
        for key, value in target_values.items()
        if value != expected_target_run_id
    }
    if mismatched_targets:
        handoff.update(
            {
                "status": "blocked",
                "reason": "BLOCKED_N3_HINT_PREFLIGHT_ARTIFACT_TARGET_MISMATCH",
                "mismatched_targets": mismatched_targets,
            }
        )
        return handoff
    mismatched_proof_kinds = {
        key: value
        for key, value in proof_kind_values.items()
        if value != expected_proof_kind
    }
    if mismatched_proof_kinds:
        handoff.update(
            {
                "status": "blocked",
                "reason": "BLOCKED_N3_HINT_PREFLIGHT_ARTIFACT_PROOF_KIND_MISMATCH",
                "mismatched_proof_kinds": mismatched_proof_kinds,
            }
        )
    return handoff


def _validate_n3p_rollback_artifact(*, rollback_sql_path: str, expected_target_run_id: str) -> dict[str, Any]:
    path = Path(rollback_sql_path)
    handoff: dict[str, Any] = {
        "status": "passed",
        "rollback_sql_path": rollback_sql_path,
        "expected_target_run_id": expected_target_run_id,
    }
    if not path.exists():
        handoff.update({"status": "blocked", "reason": N3P_ROLLBACK_ARTIFACT_MISSING_BLOCKER})
        return handoff
    try:
        sql = path.read_text(encoding="utf-8")
    except OSError as exc:
        handoff.update({"status": "blocked", "reason": N3P_ROLLBACK_ARTIFACT_MISSING_BLOCKER, "error": str(exc)})
        return handoff
    required_tokens = [
        expected_target_run_id,
        "delivering",
        "delivered",
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        "common_trigger_run",
        "common_action_run",
        "user",
        "sim",
        "stock_action_confirmation_projection_metric",
        "index_action_confirmation_projection_metric",
        "board_action_confirmation_projection_metric",
        "common_market_data_quality_item",
        "common_market_data_run",
    ]
    missing_tokens = [token for token in required_tokens if token not in sql]
    if missing_tokens:
        handoff.update(
            {
                "status": "blocked",
                "reason": N3P_ROLLBACK_ARTIFACT_UNSAFE_BLOCKER,
                "missing_tokens": missing_tokens,
            }
        )
    return handoff


def _read_artifact_target_run_id(path: str) -> str:
    return _read_artifact_field(path, "target_run_id")


def _read_artifact_field(path: str, key: str) -> str:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if isinstance(payload, Mapping):
        return _extract_string(payload, key)
    return ""


def _extract_string(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        found = _find_key(payload, key)
        if found is not None and str(found):
            return str(found)
    return ""


def _find_key(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found is not None:
                return found
    return None


def _forbidden_executable_argv_tokens(argv: list[str]) -> list[str]:
    blob = json.dumps(argv, sort_keys=True)
    forbidden = [
        "run_n4",
        "run_n5",
        "run_n6",
        "common_event_outbox",
        "common_event_inbox",
        "common_event_consumer_checkpoint",
        "launchctl",
        "kickstart",
        "bootstrap",
        "bootout",
        "schema_migration",
    ]
    return [token for token in forbidden if token in blob]


def _child_argv(
    python_executable: str,
    runner_path: str,
    common: Mapping[str, str],
    *,
    target_run_id: str,
    source_run_id: str = "",
    source_payload_path: str = "",
    source_artifact_path: str = "",
    contract_path: str = "",
    preflight_path: str = "",
    hint_proof_kind: str = "",
    json_report_path: str = "",
    execute: bool,
) -> list[str]:
    argv = [
        python_executable,
        runner_path,
        "--for-trade-date",
        common["for_trade_date"],
        "--n4-context-run-id",
        common["n4_context_run_id"],
        "--subscription-run-id",
        common["subscription_run_id"],
        "--source-condition-run-id",
        common["source_condition_run_id"],
        "--target-run-id",
        target_run_id,
    ]
    optional = {
        "--source-run-id": source_run_id,
        "--source-payload-path": source_payload_path,
        "--source-artifact-path": source_artifact_path,
        "--contract-path": contract_path,
        "--preflight-path": preflight_path,
        "--hint-proof-kind": hint_proof_kind,
        "--json-report-path": json_report_path,
    }
    for flag, value in optional.items():
        if value:
            argv.extend([flag, value])
    if execute:
        argv.extend(["--execute", "--user-confirmed"])
    argv.append("--json")
    return argv


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan one bounded N3 intraday proof poller pass.")
    parser.add_argument("--for-trade-date", default="")
    parser.add_argument("--source-trade-date", default="")
    parser.add_argument("--source-condition-run-id", default="")
    parser.add_argument("--subscription-run-id", default="")
    parser.add_argument("--preload-run-id", default="")
    parser.add_argument("--n4-context-run-id", default="")
    parser.add_argument("--lineage-config", default="")
    parser.add_argument("--hint-proof-kind", default=MIDDAY_BRIDGE_HINT_PROOF_KIND)
    parser.add_argument("--python-executable", default=DEFAULT_PYTHON_EXECUTABLE)
    parser.add_argument("--json-report-path", default="")
    parser.add_argument("--branch", choices=sorted(BRANCH_MODES), default="both")
    parser.add_argument("--max-alignment-retries", type=int, default=DEFAULT_MAX_ALIGNMENT_RETRIES)
    parser.add_argument("--retry-sleep-seconds", type=float, default=DEFAULT_RETRY_SLEEP_SECONDS)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--user-confirmed", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_proof_poller_once(
        for_trade_date=args.for_trade_date,
        source_trade_date=args.source_trade_date,
        source_condition_run_id=args.source_condition_run_id,
        subscription_run_id=args.subscription_run_id,
        preload_run_id=args.preload_run_id,
        n4_context_run_id=args.n4_context_run_id,
        hint_proof_kind=args.hint_proof_kind,
        execute=args.execute,
        user_confirmed=args.user_confirmed,
        python_executable=args.python_executable,
        max_alignment_retries=args.max_alignment_retries,
        retry_sleep_seconds=args.retry_sleep_seconds,
        json_report_path=args.json_report_path,
        post_close_noop_checker=_default_post_close_noop_checker,
        lineage_config_path=args.lineage_config,
        branch_mode=args.branch,
    )
    if args.json_report_path:
        path = Path(args.json_report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("status") in {"passed", "ready", "noop"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
