"""Runtime-control contract for the N5/N3T action-confirmation fastlane.

This module is pure planning logic. It never installs launchd jobs, starts
workers, connects to DB, pulls market data, or mutates N1-N6 facts.
"""

from __future__ import annotations

import json
import plistlib
import re
import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any


FASTLANE_LANE_ID = "n5_action_confirmation_fastlane_v1"
DEFAULT_PYTHON_EXECUTABLE = "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
FASTLANE_ACTIVATION_POLICY = "load_safe_activation_guard_v1"
FASTLANE_ACTIVE_PLAN_POLICY = "active_launchd_schedule_v1"
FASTLANE_ACTIVATION_CONFIG_ARTIFACT_TYPE = "n5_n3t_fastlane_activation_config_v1"
FASTLANE_WRITE_ENABLED_EXECUTE_POLICY_TYPE = "n5_n3t_fastlane_write_enabled_execute_policy_v1"
FASTLANE_SESSION_PHASE_POLICY_TYPE = "fastlane_session_phase_policy_v1"
FASTLANE_ACTIVE_WORKER_POLICY_TYPE = "fastlane_active_worker_policy_v1"
FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_PATH_POLICY_TYPE = "fastlane_active_worker_policy_review_runtime_resolved_v1"
FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_DEFERRED_AUTHORIZATION_TIMING = "runtime_deferred_to_runner"
FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_DEFERRED_BOOTSTRAP_MODE = "runtime_review_path_deferred"
FASTLANE_RUNTIME_SESSION_CONTEXT_POLICY_TYPE = "fastlane_runtime_clock_session_context_v1"
FASTLANE_SOURCE_RUN_SCOPED_DRAIN_PLAN_TYPE = "n5_n3t_fastlane_source_run_scoped_bounded_drain_plan_v1"

FASTLANE_LABELS = {
    "n5_intake": "com.ashare-v3.n5.action-intake-poller",
    "n3_c1_n3t": "com.ashare-v3.n3.c1-n3t-action-confirmation-poller",
    "n5_executed": "com.ashare-v3.n5.action-executed-poller",
}

PROTECTED_EXISTING_LABELS = (
    "com.ashare-v3.n3.intraday-proof-poller",
    "com.ashare-v3.n3.intraday-proof-poller.n3p",
    "com.ashare-v3.n3.intraday-proof-poller.hint",
    "com.ashare-v3.n4.proof-discovery-poller",
)

FASTLANE_PIPELINE_ORDER = (
    "N4 TriggerMatched",
    "N5 ActionEligible + active tracking",
    "N5 active scope artifact",
    "N3-C1 scoped closed 1m",
    "N3T_C1_CLOSED metric",
    "N5 ActionExecuted",
)

N5_OUTPUT_EVENT_TYPES = ("ActionEligible", "ActionExecuted")
N5_MARKET_CONTEXT_PERMISSION = ("C1 scoped closed 1m context", "N3T metric")
FASTLANE_ACTIVE_WORKER_LANES = (
    "n5_action_intake",
    "n3_c1_n3t_action_confirmation",
    "n5_action_executed",
)
N3T_METRIC_LINEAGE = {
    "source_basis": "N3T_C1_CLOSED",
    "metric_role": "action_confirmation",
    "proof_consumer": "N5",
    "not_n5_final_proof": False,
    "metric_ready": True,
    "metric_quality_status": "passed",
}


def build_fastlane_source_run_namespace(
    *,
    for_trade_date: str,
    source_trigger_run_id: str = "",
    action_run_id: str = "",
    target_hhmm: str = "",
) -> dict[str, str]:
    """Return the short source-run-scoped namespace used by Fastlane artifacts.

    The token intentionally includes only the trade date, HHMM, and a short
    source-run hash. Full source/action run IDs stay in artifact payloads, not in
    filenames, so ordinary and B2 runs with the same HHMM cannot collide.
    """

    safe_trade_date = "".join(ch for ch in str(for_trade_date or "") if ch.isdigit()) or "unknown"
    source_text = str(source_trigger_run_id or action_run_id or "")
    hhmm = _fastlane_namespace_hhmm(str(target_hhmm or ""), source_text, str(action_run_id or ""))
    hash_input = "|".join([safe_trade_date, str(source_trigger_run_id or ""), str(action_run_id or "")])
    source_run_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:12]
    token = f"{safe_trade_date}_{hhmm}_{source_run_hash}"
    return {
        "for_trade_date": safe_trade_date,
        "target_hhmm": hhmm,
        "source_run_hash": source_run_hash,
        "token": token,
        "hhmm_hash_token": f"{hhmm}_{source_run_hash}",
    }


def build_fastlane_action_run_id(*, for_trade_date: str, source_trigger_run_id: str) -> str:
    safe_source = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(source_trigger_run_id).strip()
    )
    return f"n5_live_tracking_{for_trade_date}__{safe_source}__fastlane_v1"


def build_fastlane_ordinary_source_trigger_run_id(*, for_trade_date: str, target_hhmm: str) -> str:
    return (
        f"trigger_provisional_ordinary_{for_trade_date}_until_{target_hhmm}"
        f"__realtime_action_confirmation_metric_{for_trade_date}_until_{target_hhmm}"
        "__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1"
        "_current_period_avg_v1__atomic_rule_v1_period_rollover_guard_v1"
    )


def build_fastlane_n3t_metric_run_id(
    *,
    for_trade_date: str,
    target_hhmm: str,
    source_run_hash: str,
) -> str:
    return (
        f"n3t_action_confirmation_metric_{for_trade_date}_until_{target_hhmm}"
        f"__fastlane_sr_{source_run_hash}_raw_prevday_c1_amount_v1"
    )


def build_fastlane_source_run_scoped_bounded_drain_plan(
    *,
    for_trade_date: str,
    consumer_name: str,
    source_run_family: str,
    max_source_runs: int,
    max_runtime_seconds: int | float,
    candidate_source_runs: Sequence[Mapping[str, Any]],
    working_directory: str,
    start_after: str = "",
    first_source_run: str = "",
    n5_active_scope_artifact_dir: str = "",
    n3_c1_n3t_artifact_dir: str = "",
    python_executable: str = DEFAULT_PYTHON_EXECUTABLE,
) -> dict[str, Any]:
    """Build a bounded post-close drain plan without executing child runners."""

    if int(max_source_runs or 0) <= 0:
        raise ValueError("max_source_runs_must_be_positive")
    if float(max_runtime_seconds or 0) <= 0:
        raise ValueError("max_runtime_seconds_must_be_positive")
    if source_run_family != "ordinary":
        raise ValueError("source_run_family_must_be_ordinary")

    safe_trade_date = "".join(ch for ch in str(for_trade_date or "") if ch.isdigit())
    if len(safe_trade_date) != 8:
        raise ValueError("for_trade_date_must_be_yyyymmdd")
    resolved_consumer_name = str(consumer_name or "").strip()
    if not resolved_consumer_name:
        raise ValueError("consumer_name_required")

    scope_dir = str(n5_active_scope_artifact_dir or f"docs/runtime/{safe_trade_date}/n5_fastlane_active_scope")
    n3_output_dir = str(n3_c1_n3t_artifact_dir or f"docs/runtime/{safe_trade_date}/n3_c1_n3t_fastlane")
    closeout_hhmm = _fastlane_closeout_hhmm(str(start_after or "")) or "0943"
    closeout_pre_step = _build_fastlane_drain_closeout_pre_step(
        python_executable=str(python_executable or DEFAULT_PYTHON_EXECUTABLE),
        for_trade_date=safe_trade_date,
        consumer_name=resolved_consumer_name,
        target_hhmm=closeout_hhmm,
        max_runtime_seconds=float(max_runtime_seconds),
    )
    ordered, excluded = _select_fastlane_drain_source_runs(
        candidate_source_runs,
        for_trade_date=safe_trade_date,
        first_source_run=first_source_run,
        max_source_runs=int(max_source_runs),
    )
    selected: list[dict[str, Any]] = []
    for row in ordered:
        source_run_id = str(row.get("source_run_id") or "")
        target_hhmm = _fastlane_namespace_hhmm(source_run_id, str(row.get("target_hhmm") or ""))
        action_run_id = build_fastlane_action_run_id(
            for_trade_date=safe_trade_date,
            source_trigger_run_id=source_run_id,
        )
        namespace = build_fastlane_source_run_namespace(
            for_trade_date=safe_trade_date,
            source_trigger_run_id=source_run_id,
            action_run_id=action_run_id,
            target_hhmm=target_hhmm,
        )
        source_run_hash = namespace["source_run_hash"]
        artifact_path = str(
            Path(scope_dir)
            / f"n5_active_scope_snapshot_v1_{namespace['token']}.json"
        )
        n3t_metric_run_id = build_fastlane_n3t_metric_run_id(
            for_trade_date=safe_trade_date,
            target_hhmm=target_hhmm,
            source_run_hash=source_run_hash,
        )
        commands = _build_fastlane_drain_lane_commands(
            python_executable=str(python_executable or DEFAULT_PYTHON_EXECUTABLE),
            for_trade_date=safe_trade_date,
            consumer_name=resolved_consumer_name,
            source_trigger_run_id=source_run_id,
            action_run_id=action_run_id,
            source_metric_run_id=n3t_metric_run_id,
            active_scope_artifact_path=artifact_path,
            active_scope_artifact_dir=scope_dir,
            n3_output_dir=n3_output_dir,
            max_runtime_seconds=float(max_runtime_seconds),
        )
        selected.append(
            {
                "source_run_id": source_run_id,
                "event_time": str(row.get("event_time") or ""),
                "event_count": int(row.get("row_count") or row.get("event_count") or 0),
                "target_hhmm": target_hhmm,
                "source_run_hash": source_run_hash,
                "namespace_token": namespace["token"],
                "action_run_id": action_run_id,
                "n5_active_scope_artifact_path": artifact_path,
                "n3t_metric_run_id": n3t_metric_run_id,
                "commands": commands,
                "phase_write_boundaries": {
                    "n5_intake_writes_only_tracking_outbox_inbox_checkpoint": True,
                    "n5_intake_updates_n4_outbox": False,
                    "n3_consumes_only_explicit_active_scope_artifact": True,
                    "n3_scans_n5_db": False,
                    "n3_full_market_fallback": False,
                    "n3t_writes_only_action_confirmation_metric_tables": True,
                    "n5_executed_writes_only_tracking_outbox": True,
                    "n5_executed_writes_inbox_checkpoint": False,
                    "n5_executed_consumes_n4_events": False,
                },
            }
        )

    return {
        "artifact_type": FASTLANE_SOURCE_RUN_SCOPED_DRAIN_PLAN_TYPE,
        "result": "PLAN_PASS",
        "for_trade_date": safe_trade_date,
        "consumer_name": resolved_consumer_name,
        "drain_mode": "post_close_source_run_scoped",
        "source_run_family": source_run_family,
        "start_after": str(start_after or ""),
        "first_source_run": str(first_source_run or ""),
        "max_source_runs": int(max_source_runs),
        "max_runtime_seconds": float(max_runtime_seconds),
        "selected_source_run_count": len(selected),
        "selected_source_runs": selected,
        "excluded_source_runs": excluded,
        "ordinary_only": True,
        "b2_hint_projection_included": False,
        "updates_n4_outbox_status": False,
        "touches_n6": False,
        "pre_drain_steps": [closeout_pre_step],
        "closeout_registration_before_drain": {
            "enabled": True,
            "source_run": closeout_pre_step["source_trigger_run_id"],
            "if_missing": "generate_before_first_selected_source_run",
            "execution": "pre_drain_step",
            "status": "required_before_selected_source_runs",
            "step_id": closeout_pre_step["step_id"],
        },
        "boundary": {
            "n4_outbox_status_used_as_completion_proof": False,
            "n3_consumes_only_explicit_n5_active_scope_artifact": True,
            "n3t_source_basis": "N3T_C1_CLOSED",
            "legacy_metric_fallback_allowed": False,
            "old_n3_n4_runtime_allowed": False,
            "n6_touched": False,
        },
        "forbidden_operation_proof": _forbidden_operation_proof(),
        "working_directory": str(working_directory or ""),
    }


def _fastlane_closeout_hhmm(value: str) -> str:
    match = re.search(r"(?<!\d)(\d{1,2}):?(\d{2})(?!\d)", str(value or ""))
    if not match:
        return ""
    return f"{int(match.group(1)):02d}{match.group(2)}"


def _build_fastlane_drain_closeout_pre_step(
    *,
    python_executable: str,
    for_trade_date: str,
    consumer_name: str,
    target_hhmm: str,
    max_runtime_seconds: float,
) -> dict[str, Any]:
    source_trigger_run_id = build_fastlane_ordinary_source_trigger_run_id(
        for_trade_date=for_trade_date,
        target_hhmm=target_hhmm,
    )
    action_run_id = build_fastlane_action_run_id(
        for_trade_date=for_trade_date,
        source_trigger_run_id=source_trigger_run_id,
    )
    source_metric_run_id = (
        f"n3t_action_confirmation_metric_{for_trade_date}_until_{target_hhmm}"
        "__fastlane_raw_prevday_c1_amount_v1"
    )
    json_path = f"docs/runtime/{for_trade_date}/n5_fastlane_{target_hhmm}_actionexecuted_closeout_registration.json"
    md_path = f"docs/runtime/{for_trade_date}/N5_FASTLANE_{target_hhmm}_ACTIONEXECUTED_CLOSEOUT_REGISTRATION.md"
    command = [
        python_executable,
        "scripts/run_n5_n3t_fastlane_source_run_scoped_bounded_drain_once.py",
        "--closeout-prestep-only",
        "--for-trade-date",
        for_trade_date,
        "--consumer-name",
        consumer_name,
        "--source-run-family",
        "ordinary",
        "--max-source-runs",
        "1",
        "--max-runtime-seconds",
        _format_fastlane_seconds(max_runtime_seconds),
        "--source-trigger-run-id",
        source_trigger_run_id,
        "--action-run-id",
        action_run_id,
        "--source-metric-run-id",
        source_metric_run_id,
        "--closeout-json-path",
        json_path,
        "--closeout-md-path",
        md_path,
        "--execute",
        "--user-confirmed",
        "--json",
    ]
    return {
        "step_id": f"n5_fastlane_{target_hhmm}_closeout_registration",
        "step_type": "n5_closeout_registration",
        "target_hhmm": target_hhmm,
        "source_trigger_run_id": source_trigger_run_id,
        "action_run_id": action_run_id,
        "source_metric_run_id": source_metric_run_id,
        "output_json_path": json_path,
        "output_md_path": md_path,
        "must_run_before_selected_source_runs": True,
        "db_write_allowed": False,
        "outbox_write_allowed": False,
        "n4_outbox_status_update_allowed": False,
        "touches_n6": False,
        "command": command,
    }


def _select_fastlane_drain_source_runs(
    candidate_source_runs: Sequence[Mapping[str, Any]],
    *,
    for_trade_date: str,
    first_source_run: str,
    max_source_runs: int,
) -> tuple[list[Mapping[str, Any]], list[dict[str, str]]]:
    accepted_by_source_run: dict[str, Mapping[str, Any]] = {}
    excluded_by_source_run: dict[str, dict[str, str]] = {}
    for row in candidate_source_runs:
        source_run_id = str(row.get("source_run_id") or "")
        if not source_run_id or source_run_id in accepted_by_source_run:
            continue
        reason = _fastlane_drain_candidate_exclusion_reason(row, for_trade_date=for_trade_date)
        if reason:
            if reason not in {"trigger_state_changed_true_ignored", "non_triggermatched_event_ignored"}:
                excluded_by_source_run.setdefault(source_run_id, {"source_run_id": source_run_id, "reason": reason})
            continue
        accepted_by_source_run[source_run_id] = row

    ordered = sorted(
        accepted_by_source_run.values(),
        key=lambda item: (str(item.get("event_time") or ""), str(item.get("source_run_id") or "")),
    )
    if first_source_run:
        start_index = next(
            (idx for idx, item in enumerate(ordered) if str(item.get("source_run_id") or "") == first_source_run),
            None,
        )
        ordered = [] if start_index is None else ordered[start_index:]
    return ordered[:max_source_runs], list(excluded_by_source_run.values())


def _fastlane_drain_candidate_exclusion_reason(row: Mapping[str, Any], *, for_trade_date: str) -> str:
    source_run_id = str(row.get("source_run_id") or "")
    status = str(row.get("status") or row.get("outbox_status") or "").lower()
    if status == "dead_letter" or bool(row.get("dead_letter")):
        return "dead_letter_ignored"
    if str(row.get("event_type") or "") != "TriggerMatched":
        if str(row.get("event_type") or "") == "TriggerStateChanged" and _fastlane_truthy(row.get("trigger_live")):
            return "trigger_state_changed_true_ignored"
        return "non_triggermatched_event_ignored"
    if f"_{for_trade_date}_" not in source_run_id:
        return "trade_date_mismatch"
    family = str(row.get("source_run_family") or "")
    if not family:
        family = "ordinary" if "_ordinary_" in source_run_id else "b2_hint_projection"
    if family != "ordinary":
        return "source_run_family_not_ordinary"
    return ""


def _fastlane_truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "t", "1", "yes", "y"}


def _build_fastlane_drain_lane_commands(
    *,
    python_executable: str,
    for_trade_date: str,
    consumer_name: str,
    source_trigger_run_id: str,
    action_run_id: str,
    source_metric_run_id: str,
    active_scope_artifact_path: str,
    active_scope_artifact_dir: str,
    n3_output_dir: str,
    max_runtime_seconds: float,
) -> dict[str, list[str]]:
    max_runtime = _format_fastlane_seconds(max_runtime_seconds)
    common_n5 = [
        python_executable,
        "scripts/run_n5_live_tracking_poller_once.py",
        "--for-trade-date",
        for_trade_date,
        "--source-trigger-run-id",
        source_trigger_run_id,
        "--action-run-id",
        action_run_id,
        "--consumer-name",
        consumer_name,
        "--max-events",
        "300",
        "--max-runtime-seconds",
        max_runtime,
        "--fastlane-lane-id",
        FASTLANE_LANE_ID,
    ]
    return {
        "n5_intake": [
            *common_n5,
            "--fastlane-phase",
            "intake",
            "--active-scope-artifact-path",
            active_scope_artifact_path,
            "--write-active-scope-artifact",
            "--execute",
            "--user-confirmed",
            "--json",
        ],
        "n3_c1_n3t": [
            python_executable,
            "scripts/run_n3_c1_n3t_action_confirmation_fastlane_once.py",
            "--fastlane-lane-id",
            FASTLANE_LANE_ID,
            "--active-scope-artifact-path",
            active_scope_artifact_path,
            "--active-scope-artifact-dir",
            active_scope_artifact_dir,
            "--output-dir",
            n3_output_dir,
            "--max-runtime-seconds",
            max_runtime,
            "--execute",
            "--user-confirmed",
            "--json",
        ],
        "n5_executed": [
            *common_n5,
            "--source-metric-run-id",
            source_metric_run_id,
            "--fastlane-phase",
            "executed",
            "--execute",
            "--user-confirmed",
            "--json",
        ],
    }


def _format_fastlane_seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _fastlane_namespace_hhmm(*values: str) -> str:
    for value in values:
        text = str(value or "")
        match = re.search(r"(?:^|_)until_([0-2][0-9][0-5][0-9])(?:_|$)", text)
        if match:
            return _normalize_fastlane_namespace_hhmm(match.group(1))
        match = re.search(r"(?:^|_)([0-2][0-9][0-5][0-9])(?:_|\.|$)", text)
        if match:
            return _normalize_fastlane_namespace_hhmm(match.group(1))
    return "unknown"


def _normalize_fastlane_namespace_hhmm(hhmm: str) -> str:
    if re.fullmatch(r"[0-2][0-9][0-5][0-9]", str(hhmm or "")):
        value = int(hhmm)
        if 925 <= value < 930:
            return "0930"
        return str(hhmm)
    return "unknown"


def build_fastlane_session_phase_policy() -> dict[str, Any]:
    phases = [
        "pre_open_before_0925",
        "pre_open_call_auction_after_0925",
        "trading",
        "lunch_break",
        "post_close",
        "closed_day_or_non_trading",
    ]
    return {
        "policy_type": FASTLANE_SESSION_PHASE_POLICY_TYPE,
        "phases": phases,
        "classification_inputs": [
            "for_trade_date",
            "trigger_time",
            "current_exchange_time",
            "trade_calendar.is_open",
            "trading_session_boundary",
        ],
        "consumption_completion_rule": {
            "uses_n4_outbox_status": False,
            "n5_owned_completion_evidence": [
                "common_event_inbox",
                "common_event_consumer_checkpoint",
                "common_action_tracking_state",
                "common_event_outbox",
            ],
            "n5_output_event_types": list(N5_OUTPUT_EVENT_TYPES),
        },
        "n3_boundary": {
            "scans_common_action_tracking_state": False,
            "input_artifact_type": "n5_active_scope_snapshot_v1",
            "consumes_only_explicit_active_scope_artifact": True,
            "full_market_fallback_allowed": False,
        },
        "pre_open_before_0925": {
            "n5_intake": "read_only_discovery_or_plan_only",
            "action_eligible_write_allowed": False,
            "n3_c1_n3t": "blocked_no_closed_current_day_minute",
            "action_executed": "blocked_until_n3t_c1_closed_metric",
        },
        "pre_open_call_auction_after_0925": {
            "n5_intake": "TriggerMatched_to_ActionEligible_active_tracking_allowed",
            "action_eligible_write_allowed": True,
            "active_scope_artifact_allowed": True,
            "n3_c1_n3t": "wait_first_closed_minute",
            "action_executed": "blocked_until_n3t_c1_closed_metric",
        },
        "trading": {
            "n5_intake_interval_seconds": 3,
            "n3_c1_n3t_interval_seconds": 5,
            "n5_executed_interval_seconds": 3,
            "n3_c1_n3t_input": "explicit_n5_active_scope_artifact",
        },
        "lunch_break": {
            "n5_intake_allowed": True,
            "source_gap_policy": "session_boundary_source_gap_excluded_v1",
            "allows_fake_1130_row": False,
            "allows_1300_to_1130_bridge": False,
        },
        "post_close": {
            "drain_mode": True,
            "backlog_order": ["event_time ASC", "source_run_id ASC"],
            "n3_c1_n3t_mode": "one_scoped_c1_n3t_pass_per_source_run",
        },
        "closed_day_or_non_trading": {
            "read_only_discovery_allowed": True,
            "action_eligible_write_allowed": False,
            "current_day_c1_n3t_allowed": False,
        },
    }


def build_fastlane_active_worker_policy() -> dict[str, Any]:
    return {
        "policy_type": FASTLANE_ACTIVE_WORKER_POLICY_TYPE,
        "session_phase_policy": FASTLANE_SESSION_PHASE_POLICY_TYPE,
        "lanes": list(FASTLANE_ACTIVE_WORKER_LANES),
        "lane_model": "separate_bounded_one_shot",
        "n5_direct_call_to_n3_runtime_allowed": False,
        "n3_scans_n5_db_allowed": False,
        "n4_outbox_status_consumed_proof_allowed": False,
        "legacy_metric_fallback_allowed": False,
        "default_without_execute_gate": {
            "writes_enabled": False,
            "artifact_writes_enabled": False,
        },
        "runtime_session_context_policy": {
            "policy_type": FASTLANE_RUNTIME_SESSION_CONTEXT_POLICY_TYPE,
            "current_exchange_time_source": "runtime_clock",
            "trade_calendar_source": "explicit_config_or_fail_closed",
            "no_secret_embedded": True,
        },
        "write_authorization": {
            "requires_explicit_execute_gate": True,
            "requires_user_confirmed": True,
            "n5_action_intake": "formal_TriggerMatched_or_inactive_TriggerStateChanged_false_cleanup",
            "n5_actioneligible_entry": "formal_TriggerMatched_only",
            "n3_c1_n3t_action_confirmation": "explicit_n5_active_scope_artifact_and_closed_minute",
            "n5_action_executed": "matching_N3T_C1_CLOSED_metric",
        },
        "phase_modes": {
            "pre_open_before_0925": {
                "n5_action_intake": "read_only_discovery",
                "n3_c1_n3t_action_confirmation": "disabled",
                "n5_action_executed": "disabled",
            },
            "pre_open_call_auction_after_0925": {
                "n5_action_intake": "write_enabled_bounded_if_formal_TriggerMatched_or_inactive_cleanup",
                "n3_c1_n3t_action_confirmation": "wait_first_closed_minute",
                "n5_action_executed": "wait_matching_n3t_metric",
            },
            "trading": {
                "n5_action_intake": "write_enabled_bounded_for_TriggerMatched_or_inactive_cleanup",
                "n3_c1_n3t_action_confirmation": "write_enabled_bounded_after_closed_minute",
                "n5_action_executed": "write_enabled_bounded_if_matching_n3t_metric",
            },
            "lunch_break": {
                "n5_action_intake": "write_enabled_bounded_for_TriggerMatched_or_inactive_cleanup",
                "n3_c1_n3t_action_confirmation": "write_enabled_bounded_with_session_gap_policy",
                "n5_action_executed": "write_enabled_bounded_if_matching_n3t_metric",
            },
            "post_close": {
                "n5_action_intake": "time_ordered_drain",
                "n3_c1_n3t_action_confirmation": "time_ordered_scoped_drain",
                "n5_action_executed": "time_ordered_metric_drain",
            },
            "closed_day_or_non_trading": {
                "n5_action_intake": "fail_closed",
                "n3_c1_n3t_action_confirmation": "fail_closed",
                "n5_action_executed": "fail_closed",
            },
        },
    }


def resolve_fastlane_runtime_session_context(
    config: Mapping[str, Any],
    *,
    trigger_time: str = "",
    current_exchange_time: str = "",
    formal_trigger_matched_available: bool = False,
    inactive_trigger_state_changed_available: bool = False,
    closed_minute_available: bool | None = None,
    matching_n3t_metric_available: bool = False,
) -> dict[str, Any]:
    configured_context = config.get("session_context") or {}
    if isinstance(configured_context, Mapping) and configured_context:
        return dict(configured_context)

    policy = config.get("session_context_policy") or {}
    if not isinstance(policy, Mapping) or not policy:
        return {}
    if policy.get("policy_type") != FASTLANE_RUNTIME_SESSION_CONTEXT_POLICY_TYPE:
        raise ValueError("fastlane session_context_policy policy_type mismatch")
    if "trade_calendar_is_open" not in policy:
        raise ValueError("fastlane_session_context_trade_calendar_required")

    resolved_current_exchange_time = str(
        policy.get("current_exchange_time_override")
        or current_exchange_time
        or datetime.now().astimezone().isoformat()
    )
    resolved_trigger_time = str(policy.get("trigger_time_override") or trigger_time or resolved_current_exchange_time)
    if closed_minute_available is None:
        closed_minute_available = _first_closed_minute_available(resolved_current_exchange_time)

    return {
        "policy_type": FASTLANE_RUNTIME_SESSION_CONTEXT_POLICY_TYPE,
        "trigger_time": resolved_trigger_time,
        "current_exchange_time": resolved_current_exchange_time,
        "trade_calendar_is_open": bool(policy.get("trade_calendar_is_open")),
        "formal_trigger_matched_available": bool(policy.get("formal_trigger_matched_available"))
        or bool(formal_trigger_matched_available),
        "inactive_trigger_state_changed_available": bool(policy.get("inactive_trigger_state_changed_available"))
        or bool(inactive_trigger_state_changed_available),
        "closed_minute_available": bool(policy.get("closed_minute_available"))
        if "closed_minute_available" in policy
        else bool(closed_minute_available),
        "matching_n3t_metric_available": bool(policy.get("matching_n3t_metric_available"))
        or bool(matching_n3t_metric_available),
    }


def resolve_fastlane_active_worker_decision(
    *,
    lane_key: str,
    session_phase: str,
    formal_trigger_matched_available: bool,
    inactive_trigger_state_changed_available: bool = False,
    closed_minute_available: bool,
    matching_n3t_metric_available: bool,
) -> dict[str, Any]:
    if lane_key not in FASTLANE_ACTIVE_WORKER_LANES:
        raise ValueError(f"unknown fastlane active worker lane: {lane_key}")

    decision: dict[str, Any] = {
        "policy_type": FASTLANE_ACTIVE_WORKER_POLICY_TYPE,
        "lane_key": lane_key,
        "session_phase": session_phase,
        "worker_mode": "fail_closed",
        "writes_enabled_allowed": False,
        "artifact_writes_enabled_allowed": False,
        "uses_n4_outbox_status_as_consumed_proof": False,
        "legacy_metric_fallback_allowed": False,
        "requires_explicit_active_scope_artifact": lane_key == "n3_c1_n3t_action_confirmation",
    }

    if session_phase == "closed_day_or_non_trading":
        decision["blocked_reason"] = "closed_day_or_non_trading"
        return decision

    if session_phase == "pre_open_before_0925":
        decision["worker_mode"] = "read_only_discovery" if lane_key == "n5_action_intake" else "disabled"
        decision["blocked_reason"] = "pre_open_before_0925_no_write"
        return decision

    if session_phase == "pre_open_call_auction_after_0925":
        if lane_key == "n5_action_intake":
            if formal_trigger_matched_available:
                decision["required_proof"] = "formal_TriggerMatched"
                decision["action_eligible_entry_allowed"] = True
                decision["trigger_live_false_cleanup_allowed"] = False
                decision["worker_mode"] = "write_enabled_bounded"
                decision["writes_enabled_allowed"] = True
                decision["artifact_writes_enabled_allowed"] = True
            elif inactive_trigger_state_changed_available:
                decision["required_proof"] = "inactive_TriggerStateChanged_false"
                decision["action_eligible_entry_allowed"] = False
                decision["trigger_live_false_cleanup_allowed"] = True
                decision["worker_mode"] = "write_enabled_bounded"
                decision["writes_enabled_allowed"] = True
                decision["artifact_writes_enabled_allowed"] = True
            else:
                decision["worker_mode"] = "read_only_discovery"
                decision["blocked_reason"] = "waiting_for_n4_triggermatched"
            return decision
        if lane_key == "n3_c1_n3t_action_confirmation":
            if not closed_minute_available:
                decision["worker_mode"] = "wait_first_closed_minute"
                decision["blocked_reason"] = "first_closed_minute_not_available"
                return decision
            return _active_worker_write_enabled(decision)
        if matching_n3t_metric_available:
            return _active_worker_write_enabled(decision)
        decision["worker_mode"] = "wait_matching_n3t_metric"
        decision["blocked_reason"] = "matching_n3t_metric_missing"
        return decision

    if session_phase in {"trading", "lunch_break"}:
        if lane_key == "n5_action_intake":
            if formal_trigger_matched_available:
                decision["required_proof"] = "formal_TriggerMatched"
                decision["action_eligible_entry_allowed"] = True
                decision["trigger_live_false_cleanup_allowed"] = False
                return _active_worker_write_enabled(decision)
            if inactive_trigger_state_changed_available:
                decision["required_proof"] = "inactive_TriggerStateChanged_false"
                decision["action_eligible_entry_allowed"] = False
                decision["trigger_live_false_cleanup_allowed"] = True
                return _active_worker_write_enabled(decision)
            decision["worker_mode"] = "read_only_discovery"
            decision["blocked_reason"] = "waiting_for_n4_triggermatched"
            return decision
        if lane_key == "n3_c1_n3t_action_confirmation":
            if session_phase == "lunch_break":
                decision["source_gap_policy"] = "session_boundary_source_gap_excluded_v1"
                decision["allows_fake_1130_row"] = False
                decision["allows_1300_to_1130_bridge"] = False
            if closed_minute_available:
                return _active_worker_write_enabled(decision)
            decision["worker_mode"] = "wait_closed_minute"
            decision["blocked_reason"] = "closed_minute_not_available"
            return decision
        if matching_n3t_metric_available:
            return _active_worker_write_enabled(decision)
        decision["worker_mode"] = "wait_matching_n3t_metric"
        decision["blocked_reason"] = "matching_n3t_metric_missing"
        return decision

    if session_phase == "post_close":
        if lane_key == "n5_action_intake":
            decision["worker_mode"] = "time_ordered_drain"
            decision["writes_enabled_allowed"] = True
            decision["artifact_writes_enabled_allowed"] = True
            decision["backlog_order"] = ["event_time ASC", "source_run_id ASC"]
            return decision
        if lane_key == "n3_c1_n3t_action_confirmation":
            decision["worker_mode"] = "time_ordered_scoped_drain"
            decision["writes_enabled_allowed"] = True
            decision["artifact_writes_enabled_allowed"] = True
            decision["backlog_order"] = ["event_time ASC", "source_run_id ASC"]
            return decision
        if not matching_n3t_metric_available:
            decision["worker_mode"] = "wait_matching_n3t_metric"
            decision["blocked_reason"] = "matching_n3t_metric_missing"
            return decision
        decision["worker_mode"] = "time_ordered_metric_drain"
        decision["writes_enabled_allowed"] = True
        decision["backlog_order"] = ["event_time ASC", "source_run_id ASC"]
        return decision

    decision["blocked_reason"] = "unknown_session_phase"
    return decision


def _active_worker_write_enabled(decision: dict[str, Any]) -> dict[str, Any]:
    decision["worker_mode"] = "write_enabled_bounded"
    decision["writes_enabled_allowed"] = True
    if decision["lane_key"] in {"n5_action_intake", "n3_c1_n3t_action_confirmation"}:
        decision["artifact_writes_enabled_allowed"] = True
    return decision


def classify_fastlane_session_phase(
    *,
    for_trade_date: str,
    trigger_time: str,
    current_exchange_time: str,
    trade_calendar_is_open: bool,
) -> dict[str, Any]:
    phase = _fastlane_phase_name(
        for_trade_date=for_trade_date,
        trigger_time=trigger_time,
        current_exchange_time=current_exchange_time,
        trade_calendar_is_open=trade_calendar_is_open,
    )
    output = {
        "policy_type": FASTLANE_SESSION_PHASE_POLICY_TYPE,
        "phase": phase,
        "for_trade_date": str(for_trade_date),
        "trigger_date_matches_for_trade_date": _yyyymmdd(trigger_time) == str(for_trade_date),
        "current_date_matches_for_trade_date": _yyyymmdd(current_exchange_time) == str(for_trade_date),
        "n5_intake": {
            "interval_seconds": 3,
            "action_eligible_write_allowed": False,
            "active_tracking_write_allowed": False,
            "active_scope_artifact_allowed": False,
            "uses_n4_outbox_status_as_consumed_proof": False,
        },
        "n3_c1_n3t": {
            "interval_seconds": 5,
            "consumes_only_explicit_active_scope_artifact": True,
            "scans_common_action_tracking_state": False,
            "metric_generation_allowed": False,
            "full_market_fallback_allowed": False,
        },
        "n5_executed": {
            "interval_seconds": 3,
            "requires_matching_n3t_c1_closed_metric": True,
            "legacy_metric_fallback_allowed": False,
        },
        "post_close_drain": {
            "enabled": False,
            "backlog_order": ["event_time ASC", "source_run_id ASC"],
        },
    }
    if phase == "pre_open_call_auction_after_0925":
        output["n5_intake"]["action_eligible_write_allowed"] = True
        output["n5_intake"]["active_tracking_write_allowed"] = True
        output["n5_intake"]["active_scope_artifact_allowed"] = True
        output["n3_c1_n3t"]["blocked_until"] = "first_closed_minute_available"
    elif phase == "trading":
        output["n5_intake"]["action_eligible_write_allowed"] = True
        output["n5_intake"]["active_tracking_write_allowed"] = True
        output["n5_intake"]["active_scope_artifact_allowed"] = True
        output["n3_c1_n3t"]["metric_generation_allowed"] = True
        output["n3_c1_n3t"]["requires_closed_minute"] = True
    elif phase == "lunch_break":
        output["n5_intake"]["action_eligible_write_allowed"] = True
        output["n5_intake"]["active_tracking_write_allowed"] = True
        output["n5_intake"]["active_scope_artifact_allowed"] = True
        output["n3_c1_n3t"]["source_gap_policy"] = "session_boundary_source_gap_excluded_v1"
        output["n3_c1_n3t"]["allows_fake_1130_row"] = False
        output["n3_c1_n3t"]["allows_1300_to_1130_bridge"] = False
        output["n3_c1_n3t"]["metric_generation_allowed"] = True
        output["n3_c1_n3t"]["requires_closed_minute"] = True
    elif phase == "post_close":
        output["n5_intake"]["action_eligible_write_allowed"] = True
        output["n5_intake"]["active_tracking_write_allowed"] = True
        output["n5_intake"]["active_scope_artifact_allowed"] = True
        output["n3_c1_n3t"]["metric_generation_allowed"] = True
        output["n3_c1_n3t"]["requires_closed_minute"] = True
        output["post_close_drain"]["enabled"] = True
    return output


def build_fastlane_contract() -> dict[str, Any]:
    return {
        "lane_id": FASTLANE_LANE_ID,
        "layer_role": "runtime_control",
        "runtime_model": "bounded_one_shot_micro_batch",
        "labels": dict(FASTLANE_LABELS),
        "protected_existing_labels": list(PROTECTED_EXISTING_LABELS),
        "pipeline_order": list(FASTLANE_PIPELINE_ORDER),
        "n5_market_context_permission": list(N5_MARKET_CONTEXT_PERMISSION),
        "n5_output_event_types": list(N5_OUTPUT_EVENT_TYPES),
        "n3t_metric_lineage": dict(N3T_METRIC_LINEAGE),
        "session_phase_policy": build_fastlane_session_phase_policy(),
        "active_worker_policy": build_fastlane_active_worker_policy(),
        "mutates_n4_outbox": False,
        "touches_n6": False,
        "long_running_worker": False,
        "permission_boundary": {
            "n5_reads_n4_pending_outbox_read_only": True,
            "n5_updates_n4_outbox_status": False,
            "n5_writes_only_tracking_outbox_inbox_checkpoint_for_intake": True,
            "n5_executed_writes_only_tracking_and_outbox": True,
            "n3_consumes_only_explicit_n5_active_scope_artifact": True,
            "n3_scans_n5_db": False,
            "n3_full_market_fallback": False,
            "n3_writes_canonical_minute_bar_1m": False,
            "n3_uses_a1_cumulative_authority": False,
            "n3_uses_n3p_b1_b2_or_realtime_metric": False,
            "n6_touched": False,
        },
        "next_gates": [
            "RUNTIME_CONTROL_N5_N3T_FASTLANE_CONTRACT_GATE",
            "N5_ACTION_INTAKE_POLLER_PATCH_GATE",
            "N3_C1_N3T_SCOPED_REALTIME_POLLER_PATCH_GATE",
            "N5_ACTION_EXECUTED_POLLER_PATCH_GATE",
            "RUNTIME_CONTROL_FASTLANE_LAUNCHD_PLAN_GATE",
            "RUNTIME_CONTROL_FASTLANE_PREFLIGHT_GATE",
            "FASTLANE_BOUNDED_SMOKE_EXECUTE_GATE",
            "FASTLANE_POST_REVIEW_READ_ONLY_GATE",
        ],
    }


def build_fastlane_active_loaded_state_review(
    *,
    for_trade_date: str,
    current_exchange_time: str,
    launchd_states: Mapping[str, Any],
    plist_summaries: Mapping[str, Any],
    recent_log_manifests: Mapping[str, Any],
    stderr_snapshots: Mapping[str, Any],
) -> dict[str, Any]:
    expected_intervals = {
        FASTLANE_LABELS["n5_intake"]: 3,
        FASTLANE_LABELS["n3_c1_n3t"]: 5,
        FASTLANE_LABELS["n5_executed"]: 3,
    }
    expected_labels = set(expected_intervals)
    blockers: list[str] = []
    loaded_labels: list[str] = []
    running_pid_labels: list[str] = []
    writes_enabled_observed = False
    recent_noop_ok = True
    stderr_growth_observed = False

    for label, expected_interval in expected_intervals.items():
        state = launchd_states.get(label)
        if not isinstance(state, Mapping):
            blockers.append(f"launchd_state_missing:{label}")
            continue
        if bool(state.get("loaded")):
            loaded_labels.append(label)
        else:
            blockers.append(f"label_not_loaded:{label}")
        if state.get("pid") not in (None, "", 0, "0"):
            blockers.append("running_pid_present")
            running_pid_labels.append(label)
        if int(state.get("runs") or 0) < 1:
            blockers.append(f"bounded_run_missing:{label}")
        if int(state.get("last_exit_code") or 0) != 0:
            blockers.append(f"last_exit_nonzero:{label}")

        plist = plist_summaries.get(label)
        if not isinstance(plist, Mapping):
            blockers.append(f"plist_summary_missing:{label}")
            continue
        if plist.get("label") != label:
            blockers.append(f"plist_label_mismatch:{label}")
        if plist.get("expected_sha256") and plist.get("sha256") != plist.get("expected_sha256"):
            blockers.append(f"plist_sha_mismatch:{label}")
        if int(plist.get("start_interval") or 0) != expected_interval:
            blockers.append(f"plist_interval_mismatch:{label}")
        if plist.get("run_at_load") is not False or plist.get("keep_alive") is not False:
            blockers.append(f"plist_launchd_flags_mismatch:{label}")
        if not bool(plist.get(f"activation_config_{for_trade_date}")):
            blockers.append(f"activation_config_trade_date_mismatch:{label}")
        if not bool(plist.get("scheduler_quiet")):
            blockers.append(f"scheduler_quiet_missing:{label}")
        if bool(plist.get("has_placeholder")):
            blockers.append(f"plist_placeholder:{label}")
        if bool(plist.get("has_secret_literal")):
            blockers.append(f"plist_secret_literal:{label}")
        if bool(plist.get("has_old_runner_ref")):
            blockers.append(f"old_runner_ref:{label}")

        for manifest in _as_mapping_list(recent_log_manifests.get(label)):
            if manifest.get("writes_enabled") is True:
                blockers.append("writes_enabled_true")
                writes_enabled_observed = True
            if _yyyymmdd(current_exchange_time) != str(for_trade_date):
                if manifest.get("verdict") != "FASTLANE_SCHEDULER_NOOP":
                    blockers.append(f"unexpected_noop_verdict:{label}")
                    recent_noop_ok = False
                if manifest.get("session_phase") != "closed_day_or_non_trading":
                    blockers.append(f"unexpected_noop_session_phase:{label}")
                    recent_noop_ok = False
                if manifest.get("scheduler_quiet") is not True:
                    blockers.append(f"scheduler_quiet_false:{label}")
                    recent_noop_ok = False

        stderr = stderr_snapshots.get(label)
        if isinstance(stderr, Mapping) and bool(stderr.get("grew_after_load")):
            blockers.append(f"stderr_growth:{label}")
            stderr_growth_observed = True

    unexpected_labels = set(launchd_states) - expected_labels
    if unexpected_labels:
        blockers.append("unexpected_fastlane_label:" + ",".join(sorted(unexpected_labels)))

    all_labels_loaded = set(loaded_labels) == expected_labels
    bounded_exit_ok = not running_pid_labels and not any(
        int((launchd_states.get(label) or {}).get("last_exit_code") or 0) != 0 for label in expected_labels
    )
    runtime_write_risk = writes_enabled_observed or bool(running_pid_labels) or stderr_growth_observed
    unique_blockers = sorted(set(blockers))
    result = "PASS" if not unique_blockers else "BLOCKED"
    return {
        "result": result,
        "final_verdict": "FASTLANE_ACTIVE_LOADED_STATE_REVIEW_PASS"
        if result == "PASS"
        else "FASTLANE_ACTIVE_LOADED_STATE_REVIEW_BLOCKED",
        "policy_type": FASTLANE_ACTIVE_WORKER_POLICY_TYPE,
        "for_trade_date": str(for_trade_date),
        "current_exchange_time": str(current_exchange_time),
        "labels": sorted(expected_labels),
        "all_labels_loaded": all_labels_loaded,
        "bounded_one_shot_exit_ok": bounded_exit_ok,
        "closed_day_noop_verified": bool(recent_noop_ok and _yyyymmdd(current_exchange_time) != str(for_trade_date)),
        "writes_enabled_observed": writes_enabled_observed,
        "runtime_write_risk": runtime_write_risk,
        "blockers": unique_blockers,
        "rollback_unload_scope": sorted(expected_labels),
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }


def build_fastlane_trading_day_monitor_review(
    *,
    for_trade_date: str,
    current_exchange_time: str,
    launchd_states: Mapping[str, Any],
    plist_summaries: Mapping[str, Any],
    recent_log_manifests: Mapping[str, Any],
    chain_evidence: Mapping[str, Any],
    stderr_snapshots: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected_intervals = {
        FASTLANE_LABELS["n5_intake"]: 3,
        FASTLANE_LABELS["n3_c1_n3t"]: 5,
        FASTLANE_LABELS["n5_executed"]: 3,
    }
    blockers: list[str] = []
    waiting_reasons: list[str] = []
    stderr_error_observed = False
    stderr_snapshots = stderr_snapshots or {}

    for label, expected_interval in expected_intervals.items():
        state = launchd_states.get(label)
        if not isinstance(state, Mapping):
            blockers.append(f"launchd_state_missing:{label}")
        else:
            if not bool(state.get("loaded")):
                blockers.append(f"label_not_loaded:{label}")
            if int(state.get("runs") or 0) < 1:
                blockers.append(f"bounded_run_missing:{label}")
            if int(state.get("last_exit_code") or 0) != 0:
                blockers.append(f"last_exit_nonzero:{label}")

        plist = plist_summaries.get(label)
        if not isinstance(plist, Mapping):
            blockers.append(f"plist_summary_missing:{label}")
            continue
        if plist.get("label") != label:
            blockers.append(f"plist_label_mismatch:{label}")
        if int(plist.get("start_interval") or 0) != expected_interval:
            blockers.append(f"plist_interval_mismatch:{label}")
        if plist.get("run_at_load") is not False or plist.get("keep_alive") is not False:
            blockers.append(f"plist_launchd_flags_mismatch:{label}")
        if not bool(plist.get("uses_activation_config")) and not bool(plist.get(f"activation_config_{for_trade_date}")):
            blockers.append(f"activation_config_missing:{label}")
        if bool(plist.get("has_placeholder")):
            blockers.append(f"plist_placeholder:{label}")
        if bool(plist.get("has_secret_literal")):
            blockers.append(f"plist_secret_literal:{label}")
        if bool(plist.get("has_old_runner_ref")):
            blockers.append(f"old_runner_ref:{label}")

    unexpected_labels = set(launchd_states) - set(expected_intervals)
    if unexpected_labels:
        blockers.append("unexpected_fastlane_label:" + ",".join(sorted(unexpected_labels)))

    session_phase = str(chain_evidence.get("session_phase") or "")
    for label in expected_intervals:
        for manifest in _as_mapping_list(recent_log_manifests.get(label)):
            if bool(manifest.get("legacy_metric_used")):
                blockers.append("legacy_metric_used")
            if bool(manifest.get("old_runner_ref")):
                blockers.append(f"old_runner_ref:{label}")
            if bool(manifest.get("manual_gate_required")):
                blockers.append("manual_gate_required")
            manifest_fastlane = manifest.get("fastlane") if isinstance(manifest.get("fastlane"), Mapping) else {}
            manifest_phase = str(manifest.get("session_phase") or manifest_fastlane.get("session_phase") or "")
            if (
                manifest_phase
                and session_phase
                and manifest_phase != session_phase
                and not _is_stale_scheduler_noop_manifest(manifest)
            ):
                blockers.append(f"runner_session_phase_mismatch:{label}")
            decision = manifest.get("active_worker_decision") or manifest_fastlane.get("active_worker_decision")
            if isinstance(decision, Mapping):
                expected_lane = {
                    FASTLANE_LABELS["n5_intake"]: "n5_action_intake",
                    FASTLANE_LABELS["n3_c1_n3t"]: "n3_c1_n3t_action_confirmation",
                    FASTLANE_LABELS["n5_executed"]: "n5_action_executed",
                }[label]
                if str(decision.get("policy_type") or "") != FASTLANE_ACTIVE_WORKER_POLICY_TYPE:
                    blockers.append(f"runner_active_worker_policy_mismatch:{label}")
                if str(decision.get("lane_key") or "") and str(decision.get("lane_key") or "") != expected_lane:
                    blockers.append(f"runner_lane_mismatch:{label}")
                if bool(manifest.get("writes_enabled")) and decision.get("writes_enabled_allowed") is False:
                    blockers.append(f"runner_write_enabled_outside_phase_policy:{label}")
                if (
                    bool(manifest.get("artifact_writes_enabled"))
                    and decision.get("artifact_writes_enabled_allowed") is False
                ):
                    blockers.append(f"runner_artifact_write_enabled_outside_phase_policy:{label}")
        stderr = stderr_snapshots.get(label)
        if isinstance(stderr, Mapping) and (
            bool(stderr.get("has_current_error"))
            or bool(stderr.get("grew_after_load"))
        ):
            blockers.append(f"stderr_runtime_error:{label}")
            stderr_error_observed = True

    if not bool(chain_evidence.get("n4_outbox_status_unchanged")) or bool(chain_evidence.get("n4_outbox_updated")):
        blockers.append("n4_outbox_status_changed")
    if set(chain_evidence.get("n5_output_event_types") or []) - set(N5_OUTPUT_EVENT_TYPES):
        blockers.append("n5_output_event_type_mismatch")
    if not bool(chain_evidence.get("n3_consumed_only_explicit_active_scope_artifact")):
        blockers.append("n3_explicit_artifact_boundary_mismatch")
    if bool(chain_evidence.get("n3_scanned_n5_db")):
        blockers.append("n3_scanned_n5_db")
    if bool(chain_evidence.get("n3_full_market_fallback")):
        blockers.append("n3_full_market_fallback")
    if bool(chain_evidence.get("legacy_metric_used")):
        blockers.append("legacy_metric_used")
    if not bool(chain_evidence.get("old_n3_n4_labels_unchanged")):
        blockers.append("old_n3_n4_label_risk")
    if bool(chain_evidence.get("n6_touched")):
        blockers.append("n6_touched")

    same_trade_date = _yyyymmdd(current_exchange_time) == str(for_trade_date)
    if not same_trade_date:
        waiting_reasons.append("waiting_for_trade_date")
    if session_phase in {"", "pre_open_before_0925", "closed_day_or_non_trading"}:
        waiting_reasons.append(f"waiting_for_actionable_session_phase:{session_phase or 'missing'}")

    n4_triggermatched = _fastlane_int(chain_evidence.get("n4_triggermatched"))
    n5_actioneligible = _fastlane_int(chain_evidence.get("n5_actioneligible"))
    n5_active_tracking = _fastlane_int(chain_evidence.get("n5_active_tracking"))
    n5_active_scope_artifacts = _fastlane_int(chain_evidence.get("n5_active_scope_artifacts"))
    n3_scoped_c1_artifacts = _fastlane_int(chain_evidence.get("n3_scoped_c1_artifacts"))
    n3t_rows = _fastlane_int(chain_evidence.get("n3t_c1_closed_metric_rows"))
    n5_actionexecuted = _fastlane_int(chain_evidence.get("n5_actionexecuted"))
    closed_minute_available = bool(chain_evidence.get("closed_minute_available"))
    n5_intake_remaining = max(n4_triggermatched - n5_actioneligible, 0)
    n3t_metric_remaining = max(n5_actioneligible - n3t_rows, 0)

    if n4_triggermatched <= 0:
        waiting_reasons.append("waiting_for_n4_triggermatched")
    else:
        if n5_actioneligible <= 0:
            blockers.append("n5_actioneligible_not_advancing")
        if n5_active_tracking <= 0:
            blockers.append("n5_active_tracking_not_advancing")
        if n5_actioneligible > 0 and n5_active_scope_artifacts <= 0:
            blockers.append("n5_active_scope_artifact_not_advancing")
        if n5_intake_remaining > 0:
            waiting_reasons.append("waiting_for_n5_intake_exact_cover")
        if not closed_minute_available:
            waiting_reasons.append("waiting_for_closed_minute")
        else:
            if n5_active_scope_artifacts > 0 and n3_scoped_c1_artifacts <= 0:
                blockers.append("n3_scoped_c1_not_advancing_after_closed_minute")
            if not bool(chain_evidence.get("n3t_lineage_ok")):
                blockers.append("n3t_lineage_mismatch")
            if n3t_rows <= 0:
                blockers.append("n3t_c1_closed_metric_missing_after_closed_minute")
            if n3t_metric_remaining > 0:
                waiting_reasons.append("waiting_for_n3t_metric_exact_cover")
            if n5_actionexecuted <= 0:
                blockers.append("n5_actionexecuted_not_advancing")

    unique_blockers = sorted(set(blockers))
    unique_waiting_reasons = sorted(set(waiting_reasons))
    automatic_chain_verified = (
        not unique_blockers
        and not unique_waiting_reasons
        and n4_triggermatched > 0
        and n5_actioneligible > 0
        and n5_active_tracking > 0
        and n5_active_scope_artifacts > 0
        and n3_scoped_c1_artifacts > 0
        and n3t_rows > 0
        and n5_actionexecuted > 0
        and n5_intake_remaining == 0
        and n3t_metric_remaining == 0
    )
    if unique_blockers:
        result = "BLOCKED"
    elif automatic_chain_verified:
        result = "PASS"
    else:
        result = "WAITING"

    exact_cover_waiting = n5_intake_remaining > 0 or n3t_metric_remaining > 0
    final_verdict = {
        "PASS": "FASTLANE_TRADING_DAY_MONITOR_PASS_AUTOMATIC_CHAIN_VERIFIED",
        "WAITING": "FASTLANE_TRADING_DAY_MONITOR_WAITING_FOR_EXACT_COVER"
        if exact_cover_waiting
        else "FASTLANE_TRADING_DAY_MONITOR_WAITING_FOR_INPUT_OR_CLOSED_MINUTE",
        "BLOCKED": "FASTLANE_TRADING_DAY_MONITOR_BLOCKED",
    }[result]
    return {
        "result": result,
        "final_verdict": final_verdict,
        "policy_type": FASTLANE_ACTIVE_WORKER_POLICY_TYPE,
        "for_trade_date": str(for_trade_date),
        "current_exchange_time": str(current_exchange_time),
        "session_phase": session_phase,
        "automatic_chain_verified": automatic_chain_verified,
        "manual_gate_required": "manual_gate_required" in unique_blockers,
        "stderr_error_observed": stderr_error_observed,
        "chain_counts": {
            "n4_triggermatched": n4_triggermatched,
            "n5_actioneligible": n5_actioneligible,
            "n5_active_tracking": n5_active_tracking,
            "n5_active_scope_artifacts": n5_active_scope_artifacts,
            "n3_scoped_c1_artifacts": n3_scoped_c1_artifacts,
            "n3t_c1_closed_metric_rows": n3t_rows,
            "n5_actionexecuted": n5_actionexecuted,
        },
        "chain_exact_cover": {
            "n5_intake": n5_intake_remaining == 0 and n4_triggermatched > 0,
            "n3t_metric": n3t_metric_remaining == 0 and n5_actioneligible > 0,
        },
        "chain_backlog": {
            "n5_intake_remaining": n5_intake_remaining,
            "n3t_metric_remaining": n3t_metric_remaining,
        },
        "waiting_reasons": unique_waiting_reasons,
        "blockers": unique_blockers,
        "rollback_unload_scope": sorted(expected_intervals),
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }


def build_fastlane_active_worker_policy_review(
    *,
    for_trade_date: str,
    monitor_review: Mapping[str, Any],
) -> dict[str, Any]:
    """Review whether the active worker policy can be treated as automated.

    The policy gate is intentionally downstream of the trading-day monitor: a
    loaded scheduler with partial samples is not enough. The chain must either
    be fully verified by the monitor, or this gate stays waiting/blocking.
    """

    if not isinstance(monitor_review, Mapping):
        raise ValueError("fastlane active worker policy review requires monitor_review")

    monitor_result = str(monitor_review.get("result") or "")
    monitor_verdict = str(monitor_review.get("final_verdict") or "")
    monitor_blockers = [str(item) for item in monitor_review.get("blockers") or []]
    waiting_reasons = [str(item) for item in monitor_review.get("waiting_reasons") or []]
    chain_backlog = monitor_review.get("chain_backlog") or {}
    n5_intake_remaining = _fastlane_int(
        chain_backlog.get("n5_intake_remaining") if isinstance(chain_backlog, Mapping) else 0
    )
    n3t_metric_remaining = _fastlane_int(
        chain_backlog.get("n3t_metric_remaining") if isinstance(chain_backlog, Mapping) else 0
    )
    manual_gate_required = bool(monitor_review.get("manual_gate_required"))
    automatic_chain_verified = bool(monitor_review.get("automatic_chain_verified"))
    session_phase = str(monitor_review.get("session_phase") or "")

    blockers = list(monitor_blockers)
    if manual_gate_required:
        blockers.append("manual_gate_required")

    exact_cover_waiting = (
        n5_intake_remaining > 0
        or n3t_metric_remaining > 0
        or monitor_verdict == "FASTLANE_TRADING_DAY_MONITOR_WAITING_FOR_EXACT_COVER"
        or any(reason.endswith("_exact_cover") for reason in waiting_reasons)
    )
    if monitor_result == "BLOCKED":
        blockers.append("trading_day_monitor_blocked")
    elif monitor_result != "PASS" and not waiting_reasons:
        waiting_reasons.append("waiting_for_trading_day_monitor_pass")

    unique_blockers = sorted(set(blockers))
    unique_waiting_reasons = sorted(set(waiting_reasons))
    non_bootstrap_waiting_reasons = [
        reason
        for reason in unique_waiting_reasons
        if not _is_fastlane_exact_cover_waiting_reason(reason)
        and not _is_fastlane_idle_open_waiting_reason(reason, session_phase=session_phase)
    ]
    idle_open_waiting = (
        bool(unique_waiting_reasons)
        and not non_bootstrap_waiting_reasons
        and any(_is_fastlane_idle_open_waiting_reason(reason, session_phase=session_phase) for reason in unique_waiting_reasons)
    )
    active_worker_write_enabled_ready = (
        not unique_blockers
        and not non_bootstrap_waiting_reasons
        and monitor_result in {"PASS", "WAITING"}
        and (automatic_chain_verified or exact_cover_waiting or idle_open_waiting)
    )
    full_chain_automatic_worker_ready = (
        active_worker_write_enabled_ready
        and automatic_chain_verified
        and not exact_cover_waiting
        and monitor_result == "PASS"
    )
    activation_scope = (
        "full_chain_automatic_worker"
        if full_chain_automatic_worker_ready
        else "idle_open_scheduler"
        if active_worker_write_enabled_ready and idle_open_waiting
        else "exact_cover_backlog_bootstrap"
        if active_worker_write_enabled_ready and exact_cover_waiting
        else "not_ready"
    )

    if unique_blockers:
        result = "BLOCKED"
    elif active_worker_write_enabled_ready:
        result = "PASS"
    else:
        result = "WAITING"

    if result == "PASS":
        final_verdict = "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_PASS_READY_FOR_WRITE_ENABLED_ACTIVATION_CONFIG_GATE"
        next_safe_order = "RUNTIME_CONTROL_FASTLANE_WRITE_ENABLED_ACTIVATION_CONFIG_PREFLIGHT_GATE"
    elif result == "WAITING" and exact_cover_waiting:
        final_verdict = "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_WAITING_FOR_EXACT_COVER"
        next_safe_order = "RUNTIME_CONTROL_FASTLANE_TRADING_DAY_MONITOR_REVIEW_READ_ONLY_GATE"
    elif result == "WAITING":
        final_verdict = "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_WAITING_FOR_MONITOR_PASS"
        next_safe_order = "RUNTIME_CONTROL_FASTLANE_TRADING_DAY_MONITOR_REVIEW_READ_ONLY_GATE"
    else:
        final_verdict = "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_BLOCKED"
        next_safe_order = "RUNTIME_CONTROL_FASTLANE_ACTIVE_WORKER_POLICY_REPAIR_GATE"

    return {
        "result": result,
        "final_verdict": final_verdict,
        "policy_type": FASTLANE_ACTIVE_WORKER_POLICY_TYPE,
        "for_trade_date": str(for_trade_date),
        "session_phase": session_phase,
        "session_phase_policy": build_fastlane_session_phase_policy(),
        "active_worker_policy": build_fastlane_active_worker_policy(),
        "monitor_result": monitor_result,
        "monitor_final_verdict": monitor_verdict,
        "active_worker_write_enabled_ready": active_worker_write_enabled_ready,
        "full_chain_automatic_worker_ready": full_chain_automatic_worker_ready,
        "activation_scope": activation_scope,
        "automatic_chain_verified": automatic_chain_verified,
        "manual_gate_required": manual_gate_required,
        "chain_backlog": {
            "n5_intake_remaining": n5_intake_remaining,
            "n3t_metric_remaining": n3t_metric_remaining,
        },
        "waiting_reasons": unique_waiting_reasons,
        "blockers": unique_blockers,
        "next_safe_order": next_safe_order,
        "next_full_chain_order": (
            "RUNTIME_CONTROL_FASTLANE_WRITE_ENABLED_ACTIVATION_CONFIG_FULL_CHAIN_PREFLIGHT_GATE"
            if full_chain_automatic_worker_ready
            else "RUNTIME_CONTROL_FASTLANE_TRADING_DAY_MONITOR_REVIEW_READ_ONLY_GATE"
        ),
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }


def build_fastlane_chain_evidence(
    *,
    for_trade_date: str,
    session_phase: str,
    closed_minute_available: bool,
    db_summary: Mapping[str, Any],
    artifact_summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_type": "n5_n3t_fastlane_chain_evidence_v1",
        "for_trade_date": str(for_trade_date),
        "session_phase": str(session_phase),
        "n4_triggermatched": _fastlane_int(db_summary.get("n4_triggermatched")),
        "n5_actioneligible": _fastlane_int(db_summary.get("n5_actioneligible")),
        "n5_active_tracking": _fastlane_int(db_summary.get("n5_active_tracking")),
        "n5_active_scope_artifacts": _fastlane_int(artifact_summary.get("n5_active_scope_artifacts")),
        "n3_scoped_c1_artifacts": _fastlane_int(artifact_summary.get("n3_scoped_c1_artifacts")),
        "n3t_c1_closed_metric_rows": _fastlane_int(db_summary.get("n3t_c1_closed_metric_rows")),
        "n5_actionexecuted": _fastlane_int(db_summary.get("n5_actionexecuted")),
        "closed_minute_available": bool(closed_minute_available),
        "n4_outbox_status_unchanged": bool(db_summary.get("n4_outbox_status_unchanged")),
        "n4_outbox_updated": bool(db_summary.get("n4_outbox_updated")),
        "n5_output_event_types": sorted(str(value) for value in (db_summary.get("n5_output_event_types") or [])),
        "n3_consumed_only_explicit_active_scope_artifact": bool(
            artifact_summary.get("n3_consumed_only_explicit_active_scope_artifact")
        ),
        "n3_scanned_n5_db": bool(artifact_summary.get("n3_scanned_n5_db")),
        "n3_full_market_fallback": bool(artifact_summary.get("n3_full_market_fallback")),
        "n3t_lineage_ok": bool(db_summary.get("n3t_lineage_ok")),
        "legacy_metric_used": bool(db_summary.get("legacy_metric_used")),
        "old_n3_n4_labels_unchanged": bool(artifact_summary.get("old_n3_n4_labels_unchanged")),
        "n6_touched": bool(artifact_summary.get("n6_touched")),
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }


def _fastlane_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _is_stale_scheduler_noop_manifest(manifest: Mapping[str, Any]) -> bool:
    return (
        manifest.get("verdict") == "FASTLANE_SCHEDULER_NOOP"
        and manifest.get("scheduler_quiet") is True
        and manifest.get("writes_enabled") is False
    )


def build_fastlane_launchd_plan(
    *,
    working_directory: str,
    python_executable: str = DEFAULT_PYTHON_EXECUTABLE,
    n5_intake_interval_seconds: int = 3,
    n3_c1_n3t_interval_seconds: int = 5,
    n5_executed_interval_seconds: int = 3,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "gate": "RUNTIME_CONTROL_FASTLANE_LAUNCHD_PLAN_GATE",
        "result": "PLAN_ONLY_PASS",
        "activation_policy": FASTLANE_ACTIVATION_POLICY,
        "activation_requires_explicit_gate": True,
        "lane_contract": build_fastlane_contract(),
        "launchd_plist_keys": ["n5_intake", "n3_c1_n3t", "n5_executed"],
        "activation_intervals_seconds": {
            "n5_intake": n5_intake_interval_seconds,
            "n3_c1_n3t": n3_c1_n3t_interval_seconds,
            "n5_executed": n5_executed_interval_seconds,
        },
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }
    report["n5_intake"] = {
        "label": FASTLANE_LABELS["n5_intake"],
        "phase": "n5_intake",
        "plist": _build_plist(
            label=FASTLANE_LABELS["n5_intake"],
            working_directory=working_directory,
            program_arguments=[
                python_executable,
                "scripts/plan_n5_n3t_fastlane_launchd.py",
                "--activation-guard",
                FASTLANE_LABELS["n5_intake"],
                "--json",
            ],
        ),
    }
    report["n3_c1_n3t"] = {
        "label": FASTLANE_LABELS["n3_c1_n3t"],
        "phase": "n3_c1_n3t",
        "plist": _build_plist(
            label=FASTLANE_LABELS["n3_c1_n3t"],
            working_directory=working_directory,
            program_arguments=[
                python_executable,
                "scripts/plan_n5_n3t_fastlane_launchd.py",
                "--activation-guard",
                FASTLANE_LABELS["n3_c1_n3t"],
                "--json",
            ],
        ),
    }
    report["n5_executed"] = {
        "label": FASTLANE_LABELS["n5_executed"],
        "phase": "n5_executed",
        "plist": _build_plist(
            label=FASTLANE_LABELS["n5_executed"],
            working_directory=working_directory,
            program_arguments=[
                python_executable,
                "scripts/plan_n5_n3t_fastlane_launchd.py",
                "--activation-guard",
                FASTLANE_LABELS["n5_executed"],
                "--json",
            ],
        ),
    }
    for key in report["launchd_plist_keys"]:
        _assert_fastlane_plist_safe(report[key]["plist"])
    return report


def build_fastlane_active_launchd_plan(
    *,
    working_directory: str,
    activation_config_path: str,
    python_executable: str = DEFAULT_PYTHON_EXECUTABLE,
) -> dict[str, Any]:
    config = load_fastlane_activation_config(activation_config_path)
    write_policy = _normalize_write_enabled_execute_policy(config.get("execute_policy"))
    intervals = {
        "n5_intake": int(config.get("n5_intake_interval_seconds") or 3),
        "n3_c1_n3t": int(config.get("n3_c1_n3t_interval_seconds") or 5),
        "n5_executed": int(config.get("n5_executed_interval_seconds") or 3),
    }
    report: dict[str, Any] = {
        "gate": "RUNTIME_CONTROL_FASTLANE_ACTIVE_LAUNCHD_PLAN_GATE",
        "result": "ACTIVE_PLAN_ONLY_PASS",
        "activation_policy": FASTLANE_ACTIVE_PLAN_POLICY,
        "activation_config_path": activation_config_path,
        "activation_config_artifact_type": config.get("artifact_type"),
        "session_phase_policy": build_fastlane_session_phase_policy(),
        "active_worker_policy": build_fastlane_active_worker_policy(),
        "lane_contract": build_fastlane_contract(),
        "launchd_plist_keys": ["n5_intake", "n3_c1_n3t", "n5_executed"],
        "activation_intervals_seconds": intervals,
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }
    if write_policy:
        _assert_write_enabled_plan_has_session_context_policy(config)
        active_worker_policy_review_ref = _resolve_active_worker_policy_review_ref_for_active_plan(config)
        if (write_policy.get("n3_c1_n3t_action_confirmation") or {}).get("execute"):
            _assert_n3_c1_n3t_write_enabled_config_ready(config)
        lane_readiness = _write_enabled_lane_readiness(write_policy)
        runtime_deferred = (
            active_worker_policy_review_ref.get("bootstrap_mode")
            == FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_DEFERRED_BOOTSTRAP_MODE
        )
        report["write_enabled_execute_policy"] = write_policy
        report["active_worker_policy_review_ref"] = active_worker_policy_review_ref
        report["write_enabled_lane_readiness"] = lane_readiness
        report["automatic_worker_activation_ready"] = all(lane_readiness.values())
        report["runtime_write_authorization"] = (
            "deferred_to_runner" if runtime_deferred else "ready_at_plan_generation"
        )
        report["runtime_write_authorization_ready"] = (
            not runtime_deferred
            and active_worker_policy_review_ref.get("active_worker_write_enabled_ready") is True
        )
        if report["automatic_worker_activation_ready"]:
            report["activation_scope"] = (
                "full_chain_automatic_worker"
                if active_worker_policy_review_ref.get("bootstrap_mode") == "automatic_chain_verified"
                and active_worker_policy_review_ref.get("automatic_chain_verified") is True
                else str(active_worker_policy_review_ref.get("bootstrap_mode") or "active_worker_review_pass")
            )
        else:
            report["activation_scope"] = "partial_lane_bootstrap"
    n5_intake_args = [
        python_executable,
        "scripts/run_n5_live_tracking_poller_once.py",
        "--activation-config",
        activation_config_path,
        "--fastlane-phase",
        "intake",
        "--scheduler-quiet",
        "--json",
    ]
    if (write_policy.get("n5_action_intake") or {}).get("execute"):
        n5_intake_args.extend(["--execute", "--user-confirmed"])
    if (write_policy.get("n5_action_intake") or {}).get("write_active_scope_artifact"):
        n5_intake_args.append("--write-active-scope-artifact")
    n3_c1_n3t_args = [
        python_executable,
        "scripts/run_n3_c1_n3t_action_confirmation_fastlane_once.py",
        "--activation-config",
        activation_config_path,
        "--scheduler-quiet",
        "--json",
    ]
    if (write_policy.get("n3_c1_n3t_action_confirmation") or {}).get("execute"):
        n3_c1_n3t_args.extend(["--execute", "--user-confirmed"])
    n5_executed_args = [
        python_executable,
        "scripts/run_n5_live_tracking_poller_once.py",
        "--activation-config",
        activation_config_path,
        "--fastlane-phase",
        "executed",
        "--scheduler-quiet",
        "--json",
    ]
    if (write_policy.get("n5_action_executed") or {}).get("execute"):
        n5_executed_args.extend(["--execute", "--user-confirmed"])
    report["n5_intake"] = {
        "label": FASTLANE_LABELS["n5_intake"],
        "phase": "n5_intake",
        "plist": _build_plist(
            label=FASTLANE_LABELS["n5_intake"],
            working_directory=working_directory,
            program_arguments=n5_intake_args,
            start_interval=intervals["n5_intake"],
        ),
    }
    report["n3_c1_n3t"] = {
        "label": FASTLANE_LABELS["n3_c1_n3t"],
        "phase": "n3_c1_n3t",
        "plist": _build_plist(
            label=FASTLANE_LABELS["n3_c1_n3t"],
            working_directory=working_directory,
            program_arguments=n3_c1_n3t_args,
            start_interval=intervals["n3_c1_n3t"],
        ),
    }
    report["n5_executed"] = {
        "label": FASTLANE_LABELS["n5_executed"],
        "phase": "n5_executed",
        "plist": _build_plist(
            label=FASTLANE_LABELS["n5_executed"],
            working_directory=working_directory,
            program_arguments=n5_executed_args,
            start_interval=intervals["n5_executed"],
        ),
    }
    for key in report["launchd_plist_keys"]:
        _assert_fastlane_active_plist_safe(report[key]["plist"])
    return report


def build_fastlane_write_enabled_activation_config(
    base_config: Mapping[str, Any],
    *,
    trade_calendar_is_open: bool,
    active_worker_policy_review: Mapping[str, Any] | None = None,
    enable_n5_intake: bool = False,
    enable_n5_active_scope_artifact: bool = False,
    enable_n3_c1_n3t: bool = False,
    n3_c1_n3t_current_day_source_artifact_dir: str = "",
    n3_c1_n3t_current_day_source_provider: str = "",
    n3_c1_n3t_metric_context_source_artifact_dir: str = "",
    n3_c1_n3t_previous_day_context_artifact_dir: str = "",
    n3_c1_n3t_previous_day_context_provider: str = "",
    n3_c1_n3t_n3t_writer_adapter: str = "",
    enable_n5_executed: bool = False,
    defer_active_worker_policy_review_to_runtime: bool = False,
) -> dict[str, Any]:
    if not isinstance(base_config, Mapping):
        raise ValueError("base activation config must be a JSON object")
    _assert_no_unresolved_placeholder_or_secret(json.dumps(base_config, ensure_ascii=False, sort_keys=True))
    if base_config.get("artifact_type") != FASTLANE_ACTIVATION_CONFIG_ARTIFACT_TYPE:
        raise ValueError("base activation config artifact_type mismatch")
    if active_worker_policy_review is None and not defer_active_worker_policy_review_to_runtime:
        raise ValueError("active_worker_policy_review is required for write-enabled activation config")

    config = json.loads(json.dumps(dict(base_config), ensure_ascii=False))
    config.pop("session_context", None)
    config["session_context_policy"] = {
        "policy_type": FASTLANE_RUNTIME_SESSION_CONTEXT_POLICY_TYPE,
        "current_exchange_time_source": "runtime_clock",
        "trade_calendar_source": "explicit_activation_config",
        "trade_calendar_is_open": bool(trade_calendar_is_open),
        "no_secret_embedded": True,
    }
    config["execute_policy"] = {
        "policy_type": FASTLANE_WRITE_ENABLED_EXECUTE_POLICY_TYPE,
        "user_confirmed": True,
        "n5_action_intake": {
            "execute": bool(enable_n5_intake),
            "write_active_scope_artifact": bool(enable_n5_active_scope_artifact),
        },
        "n3_c1_n3t_action_confirmation": {
            "execute": bool(enable_n3_c1_n3t),
        },
        "n5_action_executed": {
            "execute": bool(enable_n5_executed),
        },
    }
    current_day_source_dir = str(n3_c1_n3t_current_day_source_artifact_dir or "").strip()
    if current_day_source_dir:
        config["n3_c1_n3t_current_day_source_artifact_dir"] = current_day_source_dir
    current_day_source_provider = str(n3_c1_n3t_current_day_source_provider or "").strip()
    if current_day_source_provider:
        config["n3_c1_n3t_current_day_source_provider"] = current_day_source_provider
    metric_context_source_dir = str(n3_c1_n3t_metric_context_source_artifact_dir or "").strip()
    if metric_context_source_dir:
        config["n3_c1_n3t_metric_context_source_artifact_dir"] = metric_context_source_dir
    previous_day_context_dir = str(n3_c1_n3t_previous_day_context_artifact_dir or "").strip()
    if previous_day_context_dir:
        config["n3_c1_n3t_previous_day_context_artifact_dir"] = previous_day_context_dir
    previous_day_context_provider = str(n3_c1_n3t_previous_day_context_provider or "").strip()
    if previous_day_context_provider:
        config["n3_c1_n3t_previous_day_context_provider"] = previous_day_context_provider
    n3t_writer_adapter = str(n3_c1_n3t_n3t_writer_adapter or "").strip()
    if n3t_writer_adapter:
        config["n3_c1_n3t_n3t_writer_adapter"] = n3t_writer_adapter
    if enable_n3_c1_n3t:
        _assert_n3_c1_n3t_write_enabled_config_ready(config)
    config["active_worker_policy"] = build_fastlane_active_worker_policy()
    if active_worker_policy_review is not None:
        config["active_worker_policy_review_ref"] = _active_worker_policy_review_ref(
            active_worker_policy_review
        )
    config["activation_config_policy"] = {
        "policy_type": "fastlane_write_enabled_activation_config_artifact_v1",
        "runtime_session_context_source": FASTLANE_RUNTIME_SESSION_CONTEXT_POLICY_TYPE,
        "dsn_env_policy": config.get("dsn_env_policy") or "runtime_env_required_no_secret_in_artifact",
        "n5_direct_call_to_n3_runtime_allowed": False,
        "n3_scans_n5_db_allowed": False,
        "old_n3_n4_labels_unchanged": True,
    }
    config["forbidden_operation_proof"] = _forbidden_operation_proof()
    _assert_no_unresolved_placeholder_or_secret(json.dumps(config, ensure_ascii=False, sort_keys=True))
    return config


def write_fastlane_write_enabled_activation_config(
    *,
    base_activation_config_path: Path,
    active_worker_policy_review_path: Path,
    output_activation_config_path: Path,
    trade_calendar_is_open: bool,
    enable_n5_intake: bool = False,
    enable_n5_active_scope_artifact: bool = False,
    enable_n3_c1_n3t: bool = False,
    n3_c1_n3t_current_day_source_artifact_dir: str = "",
    n3_c1_n3t_current_day_source_provider: str = "",
    n3_c1_n3t_metric_context_source_artifact_dir: str = "",
    n3_c1_n3t_previous_day_context_artifact_dir: str = "",
    n3_c1_n3t_previous_day_context_provider: str = "",
    n3_c1_n3t_n3t_writer_adapter: str = "",
    enable_n5_executed: bool = False,
    defer_active_worker_policy_review_to_runtime: bool = False,
) -> dict[str, Any]:
    base_config = load_fastlane_activation_config(base_activation_config_path)
    active_worker_policy_review = load_fastlane_active_worker_policy_review(active_worker_policy_review_path)
    if defer_active_worker_policy_review_to_runtime:
        _assert_active_worker_policy_review_runtime_deferred_loadable(
            active_worker_policy_review,
            for_trade_date=str(base_config.get("for_trade_date") or ""),
        )
    else:
        _assert_active_worker_policy_review_ready(
            active_worker_policy_review,
            for_trade_date=str(base_config.get("for_trade_date") or ""),
        )
    config = build_fastlane_write_enabled_activation_config(
        base_config,
        trade_calendar_is_open=trade_calendar_is_open,
        active_worker_policy_review=None
        if defer_active_worker_policy_review_to_runtime
        else active_worker_policy_review,
        enable_n5_intake=enable_n5_intake,
        enable_n5_active_scope_artifact=enable_n5_active_scope_artifact,
        enable_n3_c1_n3t=enable_n3_c1_n3t,
        n3_c1_n3t_current_day_source_artifact_dir=n3_c1_n3t_current_day_source_artifact_dir,
        n3_c1_n3t_current_day_source_provider=n3_c1_n3t_current_day_source_provider,
        n3_c1_n3t_metric_context_source_artifact_dir=n3_c1_n3t_metric_context_source_artifact_dir,
        n3_c1_n3t_previous_day_context_artifact_dir=n3_c1_n3t_previous_day_context_artifact_dir,
        n3_c1_n3t_previous_day_context_provider=n3_c1_n3t_previous_day_context_provider,
        n3_c1_n3t_n3t_writer_adapter=n3_c1_n3t_n3t_writer_adapter,
        enable_n5_executed=enable_n5_executed,
        defer_active_worker_policy_review_to_runtime=defer_active_worker_policy_review_to_runtime,
    )
    config["active_worker_policy_review_path"] = str(active_worker_policy_review_path)
    config["active_worker_policy_review_path_policy"] = {
        "policy_type": FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_PATH_POLICY_TYPE,
        "resolution": "runtime_read_only_latest_artifact",
        "authorization_timing": FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_DEFERRED_AUTHORIZATION_TIMING
        if defer_active_worker_policy_review_to_runtime
        else "activation_config_build_time_ready",
        "no_secret_embedded": True,
    }
    _assert_no_unresolved_placeholder_or_secret(json.dumps(config, ensure_ascii=False, sort_keys=True))
    output_activation_config_path.parent.mkdir(parents=True, exist_ok=True)
    payload_text = json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _assert_no_unresolved_placeholder_or_secret(payload_text)
    output_activation_config_path.write_text(payload_text, encoding="utf-8")
    return {
        "gate": "RUNTIME_CONTROL_FASTLANE_WRITE_ENABLED_ACTIVATION_CONFIG_GATE",
        "result": "WRITE_ENABLED_ACTIVATION_CONFIG_ONLY_PASS",
        "base_activation_config_path": str(base_activation_config_path),
        "active_worker_policy_review_path": str(active_worker_policy_review_path),
        "output_activation_config_path": str(output_activation_config_path),
        "output_sha256": _sha256_file(output_activation_config_path),
        "active_worker_policy_review": {
            "result": active_worker_policy_review.get("result"),
            "final_verdict": active_worker_policy_review.get("final_verdict"),
            "active_worker_write_enabled_ready": active_worker_policy_review.get(
                "active_worker_write_enabled_ready"
            ),
        },
        "execute_policy": config["execute_policy"],
        "session_context_policy": config["session_context_policy"],
        "active_worker_policy_review_ref": config.get("active_worker_policy_review_ref", {}),
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }


def build_fastlane_write_enabled_activation_config_full_chain_preflight(
    *,
    activation_config_path: str | Path,
) -> dict[str, Any]:
    config_path = Path(activation_config_path)
    blockers: list[str] = []
    config: dict[str, Any] = {}
    write_policy: dict[str, Any] = {}
    lane_readiness = {
        "n5_action_intake": False,
        "n5_active_scope_artifact": False,
        "n3_c1_n3t_action_confirmation": False,
        "n5_action_executed": False,
    }
    active_worker_policy_review_ref: Mapping[str, Any] = {}

    try:
        config = load_fastlane_activation_config(config_path)
        _assert_write_enabled_plan_has_session_context_policy(config)
        active_worker_policy_review_ref = _resolve_active_worker_policy_review_ref(config)
        write_policy = _normalize_write_enabled_execute_policy(config.get("execute_policy"))
        if not write_policy:
            blockers.append("execute_policy_missing")
        else:
            lane_readiness = _write_enabled_lane_readiness(write_policy)
            if not all(lane_readiness.values()):
                blockers.append("full_chain_lane_readiness_mismatch")
            if lane_readiness.get("n3_c1_n3t_action_confirmation"):
                _assert_n3_c1_n3t_write_enabled_config_ready(config)
        if active_worker_policy_review_ref.get("automatic_chain_verified") is not True:
            blockers.append("active_worker_policy_review_not_automatic_chain_verified")
        if active_worker_policy_review_ref.get("bootstrap_mode") != "automatic_chain_verified":
            blockers.append("active_worker_policy_review_bootstrap_mode_not_automatic")
        _assert_no_unresolved_placeholder_or_secret(json.dumps(config, ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        blockers.append(_write_enabled_activation_config_preflight_blocker(exc))

    automatic_worker_activation_ready = bool(config) and not blockers and all(lane_readiness.values())
    activation_scope = (
        "full_chain_automatic_worker"
        if automatic_worker_activation_ready
        else "partial_lane_bootstrap"
        if any(lane_readiness.values())
        else "not_write_enabled"
    )
    result = "PREFLIGHT_PASS" if automatic_worker_activation_ready else "BLOCKED"
    if result == "PREFLIGHT_PASS":
        final_verdict = (
            "RUNTIME_CONTROL_FASTLANE_WRITE_ENABLED_ACTIVATION_CONFIG_FULL_CHAIN_PREFLIGHT_PASS_READY_FOR_ACTIVE_PLAN_REGEN"
        )
    elif "active_worker_policy_review_ref_missing" in blockers:
        final_verdict = "BLOCKED_FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_REF_MISSING"
    elif "active_worker_policy_review_ref_not_ready" in blockers:
        final_verdict = "BLOCKED_FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_NOT_READY"
    else:
        final_verdict = "BLOCKED_FASTLANE_FULL_CHAIN_ACTIVATION_CONFIG_MISMATCH"
    activation_config_sha256 = ""
    if config_path.exists() and config_path.is_file():
        activation_config_sha256 = _sha256_file(config_path)
    return {
        "gate": "RUNTIME_CONTROL_FASTLANE_WRITE_ENABLED_ACTIVATION_CONFIG_FULL_CHAIN_PREFLIGHT_GATE",
        "result": result,
        "final_verdict": final_verdict,
        "activation_config_path": str(config_path),
        "activation_config_sha256": activation_config_sha256,
        "activation_config_artifact_type": config.get("artifact_type") if config else "",
        "for_trade_date": str(config.get("for_trade_date") or "") if config else "",
        "write_enabled_execute_policy": write_policy,
        "write_enabled_lane_readiness": lane_readiness,
        "automatic_worker_activation_ready": automatic_worker_activation_ready,
        "activation_scope": activation_scope,
        "active_worker_policy_review_ref": dict(active_worker_policy_review_ref),
        "blockers": blockers,
        "forbidden_operation_proof": _forbidden_operation_proof(),
        "next_safe_order": (
            "RUNTIME_CONTROL_FASTLANE_ACTIVE_LAUNCHD_PLAN_REGEN_FOR_FULL_CHAIN_GATE"
            if result == "PREFLIGHT_PASS"
            else "RUNTIME_CONTROL_FASTLANE_WRITE_ENABLED_ACTIVATION_CONFIG_REPAIR_GATE"
        ),
    }


def _write_enabled_activation_config_preflight_blocker(exc: BaseException) -> str:
    message = str(exc)
    if "requires active_worker_policy_review_ref" in message:
        return "active_worker_policy_review_ref_missing"
    if (
        "active_worker_policy_review_ref" in message
        or "active_worker_policy_review_path" in message
        or "active worker policy review" in message
    ):
        return "active_worker_policy_review_ref_not_ready"
    return message


def _assert_active_worker_policy_review_runtime_deferred_loadable(
    review: Mapping[str, Any],
    *,
    for_trade_date: str,
) -> None:
    if review.get("policy_type") not in (None, FASTLANE_ACTIVE_WORKER_POLICY_TYPE):
        raise ValueError("active worker policy review policy_type mismatch")
    if str(review.get("for_trade_date") or "") != str(for_trade_date):
        raise ValueError("active worker policy review for_trade_date mismatch")
    if review.get("manual_gate_required") is True:
        raise ValueError("active worker policy review not ready: manual_gate_required")
    if review.get("blockers"):
        raise ValueError("active worker policy review not ready: blockers_or_waiting_reasons")
    chain_backlog = review.get("chain_backlog") or {}
    if not isinstance(chain_backlog, Mapping):
        raise ValueError("active worker policy review chain_backlog mismatch")


def _active_worker_policy_review_runtime_deferred_ref(review: Mapping[str, Any]) -> dict[str, Any]:
    chain_backlog = review.get("chain_backlog") or {}
    if not isinstance(chain_backlog, Mapping):
        chain_backlog = {}
    return {
        "result": str(review.get("result") or ""),
        "final_verdict": str(review.get("final_verdict") or ""),
        "for_trade_date": str(review.get("for_trade_date") or ""),
        "active_worker_write_enabled_ready": bool(review.get("active_worker_write_enabled_ready")),
        "automatic_chain_verified": bool(review.get("automatic_chain_verified")),
        "bootstrap_mode": FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_DEFERRED_BOOTSTRAP_MODE,
        "chain_backlog": {
            "n5_intake_remaining": _fastlane_int(chain_backlog.get("n5_intake_remaining")),
            "n3t_metric_remaining": _fastlane_int(chain_backlog.get("n3t_metric_remaining")),
        },
        "waiting_reasons": [str(item) for item in review.get("waiting_reasons") or []],
    }


def validate_fastlane_write_enabled_activation_authorization(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return normalized write policy after proving write-enabled config authorization."""
    write_policy = _normalize_write_enabled_execute_policy(config.get("execute_policy"))
    if not write_policy:
        return {}
    _assert_write_enabled_plan_has_session_context_policy(config)
    active_worker_policy_review_ref = _resolve_active_worker_policy_review_ref_for_runtime_authorization(config)
    _assert_active_worker_policy_review_ref_runtime_ready(
        active_worker_policy_review_ref,
        for_trade_date=str(config.get("for_trade_date") or ""),
    )
    if (write_policy.get("n3_c1_n3t_action_confirmation") or {}).get("execute"):
        _assert_n3_c1_n3t_write_enabled_config_ready(config)
    return write_policy


def load_fastlane_active_worker_policy_review(path: str | Path) -> dict[str, Any]:
    review_path = Path(path)
    payload_text = review_path.read_text(encoding="utf-8")
    _assert_no_unresolved_placeholder_or_secret(payload_text)
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError("active worker policy review must be a JSON object")
    return payload


def _assert_active_worker_policy_review_ref_runtime_ready(
    review_ref: Mapping[str, Any],
    *,
    for_trade_date: str,
) -> None:
    if str(review_ref.get("for_trade_date") or "") != str(for_trade_date):
        raise ValueError("fastlane active_worker_policy_review_ref for_trade_date mismatch")
    if review_ref.get("result") != "PASS" or review_ref.get("active_worker_write_enabled_ready") is not True:
        waiting_reasons = ",".join(str(item) for item in review_ref.get("waiting_reasons") or [])
        suffix = waiting_reasons or str(review_ref.get("result") or "not_ready")
        raise ValueError(f"fastlane active_worker_policy_review_ref_not_ready:{suffix}")


def _assert_active_worker_policy_review_ready(review: Mapping[str, Any], *, for_trade_date: str) -> None:
    if review.get("policy_type") not in (None, FASTLANE_ACTIVE_WORKER_POLICY_TYPE):
        raise ValueError("active worker policy review policy_type mismatch")
    if str(review.get("for_trade_date") or "") != str(for_trade_date):
        raise ValueError("active worker policy review for_trade_date mismatch")
    if review.get("result") != "PASS" or review.get("active_worker_write_enabled_ready") is not True:
        raise ValueError("active worker policy review not ready")
    if review.get("manual_gate_required") is True:
        raise ValueError("active worker policy review not ready: manual_gate_required")
    waiting_reasons = [str(item) for item in review.get("waiting_reasons") or []]
    activation_scope = str(review.get("activation_scope") or "")
    session_phase = str(review.get("session_phase") or "")
    if review.get("blockers") or any(
        not _is_fastlane_exact_cover_waiting_reason(reason)
        and not (
            activation_scope == "idle_open_scheduler"
            and _is_fastlane_idle_open_waiting_reason(reason, session_phase=session_phase)
        )
        for reason in waiting_reasons
    ):
        raise ValueError("active worker policy review not ready: blockers_or_waiting_reasons")
    chain_backlog = review.get("chain_backlog") or {}
    if not isinstance(chain_backlog, Mapping):
        raise ValueError("active worker policy review chain_backlog mismatch")


def _active_worker_policy_review_ref(review: Mapping[str, Any]) -> dict[str, Any]:
    waiting_reasons = [str(item) for item in review.get("waiting_reasons") or []]
    chain_backlog = review.get("chain_backlog") or {}
    if not isinstance(chain_backlog, Mapping):
        chain_backlog = {}
    activation_scope = str(review.get("activation_scope") or "")
    if activation_scope in {
        "full_chain_automatic_worker",
        "exact_cover_backlog_bootstrap",
        "idle_open_scheduler",
    }:
        bootstrap_mode = (
            "automatic_chain_verified"
            if activation_scope == "full_chain_automatic_worker"
            else activation_scope
        )
    else:
        bootstrap_mode = (
            "automatic_chain_verified"
            if bool(review.get("automatic_chain_verified"))
            else "exact_cover_backlog_bootstrap"
            if any(_is_fastlane_exact_cover_waiting_reason(reason) for reason in waiting_reasons)
            else "active_worker_review_pass"
        )
    return {
        "result": str(review.get("result") or ""),
        "final_verdict": str(review.get("final_verdict") or ""),
        "for_trade_date": str(review.get("for_trade_date") or ""),
        "active_worker_write_enabled_ready": bool(review.get("active_worker_write_enabled_ready")),
        "automatic_chain_verified": bool(review.get("automatic_chain_verified")),
        "bootstrap_mode": bootstrap_mode,
        "chain_backlog": {
            "n5_intake_remaining": _fastlane_int(chain_backlog.get("n5_intake_remaining")),
            "n3t_metric_remaining": _fastlane_int(chain_backlog.get("n3t_metric_remaining")),
        },
        "waiting_reasons": waiting_reasons,
    }


def _is_fastlane_exact_cover_waiting_reason(reason: str) -> bool:
    return reason in {
        "waiting_for_n5_intake_exact_cover",
        "waiting_for_n3t_metric_exact_cover",
    }


def _is_fastlane_idle_open_waiting_reason(reason: str, *, session_phase: str) -> bool:
    return reason == "waiting_for_n4_triggermatched" and session_phase in {
        "pre_open_call_auction_after_0925",
        "trading",
        "lunch_break",
        "post_close",
    }


def _normalize_write_enabled_execute_policy(policy: Any) -> dict[str, Any]:
    if not policy:
        return {}
    if not isinstance(policy, dict):
        raise ValueError("fastlane execute_policy must be an object")
    if policy.get("policy_type") != FASTLANE_WRITE_ENABLED_EXECUTE_POLICY_TYPE:
        raise ValueError("fastlane execute_policy policy_type mismatch")
    if policy.get("user_confirmed") is not True:
        raise ValueError("fastlane execute_policy requires user_confirmed=true")
    return {
        "policy_type": FASTLANE_WRITE_ENABLED_EXECUTE_POLICY_TYPE,
        "user_confirmed": True,
        "n5_action_intake": {
            "execute": bool((policy.get("n5_action_intake") or {}).get("execute")),
            "write_active_scope_artifact": bool(
                (policy.get("n5_action_intake") or {}).get("write_active_scope_artifact")
            ),
        },
        "n3_c1_n3t_action_confirmation": {
            "execute": bool((policy.get("n3_c1_n3t_action_confirmation") or {}).get("execute")),
        },
        "n5_action_executed": {
            "execute": bool((policy.get("n5_action_executed") or {}).get("execute")),
        },
    }


def _write_enabled_lane_readiness(write_policy: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "n5_action_intake": bool((write_policy.get("n5_action_intake") or {}).get("execute")),
        "n5_active_scope_artifact": bool(
            (write_policy.get("n5_action_intake") or {}).get("write_active_scope_artifact")
        ),
        "n3_c1_n3t_action_confirmation": bool(
            (write_policy.get("n3_c1_n3t_action_confirmation") or {}).get("execute")
        ),
        "n5_action_executed": bool((write_policy.get("n5_action_executed") or {}).get("execute")),
    }


def _assert_write_enabled_plan_has_session_context_policy(config: Mapping[str, Any]) -> None:
    session_context = config.get("session_context") or {}
    session_context_policy = config.get("session_context_policy") or {}
    if isinstance(session_context, Mapping) and session_context:
        return
    if isinstance(session_context_policy, Mapping) and session_context_policy:
        if session_context_policy.get("policy_type") != FASTLANE_RUNTIME_SESSION_CONTEXT_POLICY_TYPE:
            raise ValueError("fastlane session_context_policy policy_type mismatch")
        if "trade_calendar_is_open" not in session_context_policy:
            raise ValueError("fastlane write-enabled active plan requires session_context_policy.trade_calendar_is_open")
        return
    raise ValueError("fastlane write-enabled active plan requires session_context or session_context_policy")


def _assert_write_enabled_plan_has_active_worker_policy_review_ref(config: Mapping[str, Any]) -> None:
    review_ref = config.get("active_worker_policy_review_ref") or {}
    if not isinstance(review_ref, Mapping) or not review_ref:
        raise ValueError("fastlane write-enabled active plan requires active_worker_policy_review_ref")
    if review_ref.get("result") != "PASS" or review_ref.get("active_worker_write_enabled_ready") is not True:
        raise ValueError("fastlane active_worker_policy_review_ref not ready")
    if str(review_ref.get("for_trade_date") or "") != str(config.get("for_trade_date") or ""):
        raise ValueError("fastlane active_worker_policy_review_ref for_trade_date mismatch")


def _resolve_active_worker_policy_review_ref(config: Mapping[str, Any]) -> dict[str, Any]:
    review_path = str(config.get("active_worker_policy_review_path") or "").strip()
    if review_path:
        path_policy = config.get("active_worker_policy_review_path_policy") or {}
        if isinstance(path_policy, Mapping) and path_policy:
            if path_policy.get("policy_type") != FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_PATH_POLICY_TYPE:
                raise ValueError("fastlane active_worker_policy_review_path_policy mismatch")
        _assert_no_unresolved_placeholder_or_secret(review_path)
        try:
            review = load_fastlane_active_worker_policy_review(review_path)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("fastlane active_worker_policy_review_path not readable") from exc
        _assert_active_worker_policy_review_ready(
            review,
            for_trade_date=str(config.get("for_trade_date") or ""),
        )
        return _active_worker_policy_review_ref(review)
    _assert_write_enabled_plan_has_active_worker_policy_review_ref(config)
    return dict(config.get("active_worker_policy_review_ref") or {})


def _resolve_active_worker_policy_review_ref_for_active_plan(config: Mapping[str, Any]) -> dict[str, Any]:
    review_path = str(config.get("active_worker_policy_review_path") or "").strip()
    path_policy = config.get("active_worker_policy_review_path_policy") or {}
    if (
        review_path
        and isinstance(path_policy, Mapping)
        and path_policy.get("authorization_timing")
        == FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_DEFERRED_AUTHORIZATION_TIMING
    ):
        if path_policy.get("policy_type") != FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_PATH_POLICY_TYPE:
            raise ValueError("fastlane active_worker_policy_review_path_policy mismatch")
        _assert_no_unresolved_placeholder_or_secret(review_path)
        try:
            review = load_fastlane_active_worker_policy_review(review_path)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("fastlane active_worker_policy_review_path not readable") from exc
        _assert_active_worker_policy_review_runtime_deferred_loadable(
            review,
            for_trade_date=str(config.get("for_trade_date") or ""),
        )
        return _active_worker_policy_review_runtime_deferred_ref(review)
    return _resolve_active_worker_policy_review_ref(config)


def _resolve_active_worker_policy_review_ref_for_runtime_authorization(config: Mapping[str, Any]) -> dict[str, Any]:
    review_path = str(config.get("active_worker_policy_review_path") or "").strip()
    path_policy = config.get("active_worker_policy_review_path_policy") or {}
    if (
        review_path
        and isinstance(path_policy, Mapping)
        and path_policy.get("authorization_timing")
        == FASTLANE_ACTIVE_WORKER_POLICY_REVIEW_DEFERRED_AUTHORIZATION_TIMING
    ):
        return _resolve_active_worker_policy_review_ref_for_active_plan(config)
    return _resolve_active_worker_policy_review_ref(config)


def _assert_n3_c1_n3t_write_enabled_config_ready(config: Mapping[str, Any]) -> None:
    required_fields = (
        "n3_c1_n3t_current_day_source_artifact_dir",
        "n3_c1_n3t_current_day_source_provider",
        "n3_c1_n3t_metric_context_source_artifact_dir",
        "n3_c1_n3t_previous_day_context_artifact_dir",
        "n3_c1_n3t_previous_day_context_provider",
        "n3_c1_n3t_n3t_writer_adapter",
    )
    missing = [field for field in required_fields if not str(config.get(field) or "").strip()]
    if missing:
        raise ValueError("n3_c1_n3t_write_enabled_contract_missing:" + ",".join(missing))
    if config.get("n3_c1_n3t_current_day_source_provider") != "mootdx_today_minute_adapter_v1":
        raise ValueError("n3_c1_n3t_write_enabled_contract_current_day_source_provider")
    if config.get("n3_c1_n3t_previous_day_context_provider") != "postgres_previous_day_raw_c1_context_v1":
        raise ValueError("n3_c1_n3t_write_enabled_contract_previous_day_context_provider")
    if config.get("n3_c1_n3t_n3t_writer_adapter") != "postgres_n3t_action_confirmation_metric_writer_v1":
        raise ValueError("n3_c1_n3t_write_enabled_contract_n3t_writer_adapter")


def write_fastlane_active_launchd_plan(
    *,
    output_dir: Path,
    working_directory: str,
    activation_config_path: str,
    python_executable: str = DEFAULT_PYTHON_EXECUTABLE,
    require_full_chain_activation: bool = False,
) -> dict[str, Any]:
    full_chain_preflight: dict[str, Any] | None = None
    if require_full_chain_activation:
        full_chain_preflight = build_fastlane_write_enabled_activation_config_full_chain_preflight(
            activation_config_path=activation_config_path,
        )
        if full_chain_preflight.get("result") != "PREFLIGHT_PASS":
            raise ValueError(
                "fastlane full-chain activation preflight not pass: "
                + ",".join(str(item) for item in full_chain_preflight.get("blockers") or [])
            )
    report = build_fastlane_active_launchd_plan(
        working_directory=working_directory,
        activation_config_path=activation_config_path,
        python_executable=python_executable,
    )
    if full_chain_preflight is not None:
        report["full_chain_activation_preflight"] = full_chain_preflight
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in report["launchd_plist_keys"]:
        plist_path = output_dir / f"{report[key]['label']}.plist"
        with plist_path.open("wb") as fh:
            plistlib.dump(report[key]["plist"], fh, sort_keys=True)
        report[key]["plist_path"] = str(plist_path)
    report_path = output_dir / "N5_N3T_action_confirmation_fastlane_active_launchd_plan.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def write_fastlane_launchd_plan(
    *,
    output_dir: Path,
    working_directory: str,
    python_executable: str = DEFAULT_PYTHON_EXECUTABLE,
) -> dict[str, Any]:
    report = build_fastlane_launchd_plan(
        working_directory=working_directory,
        python_executable=python_executable,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    for key in report["launchd_plist_keys"]:
        plist_path = output_dir / f"{report[key]['label']}.plist"
        with plist_path.open("wb") as fh:
            plistlib.dump(report[key]["plist"], fh, sort_keys=True)
        report[key]["plist_path"] = str(plist_path)
    report_path = output_dir / "N5_N3T_action_confirmation_fastlane_launchd_plan.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _build_plist(
    *,
    label: str,
    working_directory: str,
    program_arguments: list[str],
    start_interval: int | None = None,
) -> dict[str, Any]:
    plist: dict[str, Any] = {
        "Label": label,
        "ProgramArguments": program_arguments,
        "WorkingDirectory": working_directory,
        "EnvironmentVariables": {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "src:scripts:.",
        },
        "RunAtLoad": False,
        "KeepAlive": False,
        "StandardOutPath": f"{working_directory}/tmp/{label}.out.log",
        "StandardErrorPath": f"{working_directory}/tmp/{label}.err.log",
    }
    if start_interval is not None:
        plist["StartInterval"] = int(start_interval)
    return plist


def _assert_fastlane_plist_safe(plist: dict[str, Any]) -> None:
    if plist.get("RunAtLoad") is not False or plist.get("KeepAlive") is not False:
        raise ValueError("fastlane launchd plan must keep RunAtLoad=false and KeepAlive=false")
    if plist.get("Disabled") is True:
        raise ValueError("fastlane install/load plan must not use Disabled=true; it prevents bootstrap")
    if "StartInterval" in plist:
        raise ValueError("fastlane install/load plan must not schedule StartInterval before activation")
    label = str(plist.get("Label") or "")
    if label not in FASTLANE_LABELS.values():
        raise ValueError(f"unexpected fastlane label: {label}")
    joined = " ".join(str(value) for value in plist.get("ProgramArguments", []))
    for placeholder in (
        "__FOR_TRADE_DATE__",
        "__SOURCE_TRIGGER_RUN_ID__",
        "__SOURCE_METRIC_RUN_ID__",
        "__ACTION_RUN_ID__",
        "__CONSUMER_NAME__",
        "__MAX_EVENTS__",
    ):
        if placeholder in joined:
            raise ValueError(f"unresolved fastlane ProgramArguments placeholder: {placeholder}")
    for forbidden in (
        "run_n3_intraday_proof_poller_once.py",
        "run_n4_intraday_proof_discovery_poll_once.py",
        "run_n3_intraday_b1_c1_b2_auto_poll_once.py",
        "run_n3p",
        "run_n4",
        "run_n6",
        "launchctl",
        "rollback",
        "schema",
        "migration",
        "--execute",
        "--user-confirmed",
    ):
        if forbidden in joined:
            raise ValueError(f"forbidden fastlane ProgramArguments token: {forbidden}")


def _assert_fastlane_active_plist_safe(plist: dict[str, Any]) -> None:
    if plist.get("RunAtLoad") is not False or plist.get("KeepAlive") is not False:
        raise ValueError("fastlane active plan must keep RunAtLoad=false and KeepAlive=false")
    if "Disabled" in plist:
        raise ValueError("fastlane active plan must not use Disabled")
    if int(plist.get("StartInterval") or 0) <= 0:
        raise ValueError("fastlane active plan requires positive StartInterval")
    label = str(plist.get("Label") or "")
    if label not in FASTLANE_LABELS.values():
        raise ValueError(f"unexpected fastlane label: {label}")
    joined = " ".join(str(value) for value in plist.get("ProgramArguments", []))
    if "--activation-config" not in joined:
        raise ValueError("fastlane active plan must pass activation config")
    _assert_no_unresolved_placeholder_or_secret(json.dumps(plist, ensure_ascii=False, sort_keys=True))
    for forbidden in (
        "--source-trigger-run-id",
        "--source-metric-run-id",
        "--action-run-id",
        "--consumer-name",
        "run_n3_intraday_proof_poller_once.py",
        "run_n4_intraday_proof_discovery_poll_once.py",
        "run_n3_intraday_b1_c1_b2_auto_poll_once.py",
        "run_n3p",
        "run_n4",
        "run_n6",
        "launchctl",
        "rollback",
        "schema",
        "migration",
    ):
        if forbidden in joined:
            raise ValueError(f"forbidden fastlane active ProgramArguments token: {forbidden}")


def load_fastlane_activation_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    payload_text = config_path.read_text(encoding="utf-8")
    _assert_no_unresolved_placeholder_or_secret(payload_text)
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError("activation config must be a JSON object")
    if payload.get("artifact_type") != FASTLANE_ACTIVATION_CONFIG_ARTIFACT_TYPE:
        raise ValueError("activation config artifact_type mismatch")
    return payload


def _assert_no_unresolved_placeholder_or_secret(text: str) -> None:
    if re.search(r"__[A-Z0-9_]+__", text):
        raise ValueError("unresolved placeholder in fastlane activation config or plan")
    if re.search(r"postgres(?:ql)?://", text, flags=re.IGNORECASE):
        raise ValueError("DSN secret must not be embedded in fastlane activation config or plan")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fastlane_phase_name(
    *,
    for_trade_date: str,
    trigger_time: str,
    current_exchange_time: str,
    trade_calendar_is_open: bool,
) -> str:
    if not trade_calendar_is_open:
        return "closed_day_or_non_trading"
    if _yyyymmdd(trigger_time) != str(for_trade_date) or _yyyymmdd(current_exchange_time) != str(for_trade_date):
        return "closed_day_or_non_trading"
    hhmm = _hhmm_int(current_exchange_time)
    if hhmm < 925:
        return "pre_open_before_0925"
    if hhmm < 930:
        return "pre_open_call_auction_after_0925"
    if 930 <= hhmm < 1130:
        return "trading"
    if 1130 <= hhmm < 1300:
        return "lunch_break"
    if 1300 <= hhmm < 1500:
        return "trading"
    return "post_close"


def _yyyymmdd(value: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[0-9]{8}", text):
        return text
    try:
        return datetime.fromisoformat(text).strftime("%Y%m%d")
    except ValueError:
        pass
    match = re.search(r"(20[0-9]{2})-?([0-9]{2})-?([0-9]{2})", text)
    return "".join(match.groups()) if match else ""


def _hhmm_int(value: str) -> int:
    text = str(value or "").strip()
    try:
        return int(datetime.fromisoformat(text).strftime("%H%M"))
    except ValueError:
        pass
    match = re.search(r"([0-2][0-9]):?([0-5][0-9])", text)
    if not match:
        return 0
    return int(match.group(1) + match.group(2))


def _first_closed_minute_available(value: str) -> bool:
    return _hhmm_int(value) >= 931


def build_fastlane_activation_guard(label: str) -> dict[str, Any]:
    if label not in FASTLANE_LABELS.values():
        raise ValueError(f"unexpected fastlane label: {label}")
    return {
        "verdict": "FASTLANE_ACTIVATION_REQUIRED",
        "label": label,
        "lane_id": FASTLANE_LANE_ID,
        "activation_policy": FASTLANE_ACTIVATION_POLICY,
        "activation_requires_explicit_gate": True,
        "message": "This installed launchd label is load-safe only. Generate an activation plan with real runtime inputs before enabling scheduled execution.",
        "forbidden_operation_proof": _forbidden_operation_proof(),
    }


def _forbidden_operation_proof() -> dict[str, bool]:
    return {
        "database_written_by_plan": False,
        "launchd_loaded_or_started": False,
        "old_n3_a1_b1_b2_n3p_labels_modified": False,
        "n4_code_or_runtime_modified": False,
        "n4_outbox_updated": False,
        "n6_touched": False,
        "full_market_fallback_enabled": False,
        "long_running_worker_started": False,
        "schema_changed": False,
        "commit_created": False,
    }
