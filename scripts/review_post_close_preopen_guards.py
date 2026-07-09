#!/usr/bin/env python3
"""Post-close Fast Lane pre-open read-only guards.

The script writes only local report artifacts. It does not mutate database
rows, consume event ledgers, execute rollback SQL, or start/stop workers.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

try:
    from check_condition_source_ready import DEFAULT_DSN
except ModuleNotFoundError:  # Imported as scripts.review_post_close_preopen_guards in tests.
    from scripts.check_condition_source_ready import DEFAULT_DSN

from ashare_v3.runtime.intraday_worker_lineage import DEFAULT_LINEAGE_CONFIG_PATH


class GuardBlocked(RuntimeError):
    """Raised when a pre-open guard fails closed."""

    def __init__(self, message: str, *, report: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = dict(report) if report is not None else None


REQUIRED_ROLLBACK_GUARD_MARKERS = (
    "RAISE EXCEPTION",
    "common_event_outbox",
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_action_run",
)

REQUIRED_READINESS_KEYS = (
    "n2_condition",
    "n3_subscription",
    "n3_a1_preload",
    "n3_a1_cumulative_amount",
    "n4_trigger_context_snapshot",
)

WORKER_PROCESS_MARKERS = {
    "n3_worker": ("run_n3_bounded_worker_once.py", "run_n3_intraday_b1_c1_b2_auto_poll_once.py"),
    "n4_worker": ("run_n4_replay_bounded_worker_once.py", "run_n4_worker_bounded_poll_once.py"),
    "n5_worker": ("run_n5_bounded_action_worker_once.py", "run_action_consumer_once.py"),
    "n6_worker": ("run_n6_delivery_once.py", "uvicorn"),
}

SAFE_PROOF_POLLER_ALLOWLIST = {
    "n3_worker": {
        "label": "com.ashare-v3.n3.intraday-proof-poller",
        "report_path": "tmp/N3_intraday_proof_poller_launchd_report.json",
        "kind": "n3",
    },
    "n3p_worker": {
        "label": "com.ashare-v3.n3.intraday-proof-poller.n3p",
        "report_path": "tmp/N3_intraday_proof_poller_n3p_launchd_report.json",
        "kind": "n3",
    },
    "n3_hint_worker": {
        "label": "com.ashare-v3.n3.intraday-proof-poller.hint",
        "report_path": "tmp/N3_intraday_proof_poller_hint_launchd_report.json",
        "kind": "n3",
    },
    "n4_worker": {
        "label": "com.ashare-v3.n4.proof-discovery-poller",
        "report_path": "tmp/N4_intraday_proof_discovery_poller_launchd_report.json",
        "kind": "n4",
    },
    "n4_hint_worker": {
        "label": "com.ashare-v3.n4.proof-discovery-poller.hint",
        "report_path": "tmp/N4_intraday_proof_discovery_poller_hint_launchd_report.json",
        "kind": "n4",
    },
}

UNSAFE_LAUNCHD_LABELS = {
    "n3_worker": ("com.ashare-v3.n3.intraday-b1-c1-b2-auto-poll",),
    "n4_worker": ("com.ashare-v3.n4.bounded-polling",),
}

SAFE_REPORT_MAX_AGE_SECONDS = 300


def build_n4_context_rollback_ready_report(*, for_trade_date: str, rollback_sql_path: str | Path) -> dict[str, Any]:
    path = Path(rollback_sql_path)
    if not path.exists():
        raise GuardBlocked(f"rollback_missing:{path}")
    text = path.read_text(encoding="utf-8")
    upper = text.upper()
    first_delete = upper.find("DELETE FROM")
    if first_delete < 0:
        raise GuardBlocked("rollback_missing_delete_scope")
    missing = [marker for marker in REQUIRED_ROLLBACK_GUARD_MARKERS if marker.upper() not in upper]
    if missing:
        raise GuardBlocked("rollback_missing_guard:" + ",".join(missing))
    first_raise = upper.find("RAISE EXCEPTION")
    if first_raise < 0 or first_raise > first_delete:
        raise GuardBlocked("rollback_guard_not_before_delete")
    forbidden_delete = [
        table
        for table in ("common_event_outbox", "common_event_inbox", "common_event_consumer_checkpoint", "common_action_run")
        if f"DELETE FROM {table}".upper() in upper
    ]
    if forbidden_delete:
        raise GuardBlocked("rollback_delete_scope_forbidden:" + ",".join(forbidden_delete))
    required_deletes = (
        "DELETE FROM common_trigger_quality_item",
        "DELETE FROM stock_trigger_context_snapshot",
        "DELETE FROM index_trigger_context_snapshot",
        "DELETE FROM board_trigger_context_snapshot",
        "DELETE FROM common_trigger_run",
    )
    missing_delete_scope = [stmt for stmt in required_deletes if stmt.upper() not in upper]
    if missing_delete_scope:
        raise GuardBlocked("rollback_missing_delete_scope:" + ",".join(missing_delete_scope))
    return {
        "result": "PASS",
        "check": "n4_context_rollback_ready",
        "layer_role": "runtime_control",
        "for_trade_date": for_trade_date,
        "rollback_sql_path": str(path),
        "rollback_guard": {
            "guard_before_delete": True,
            "outbox_guard": True,
            "inbox_guard": True,
            "checkpoint_guard": True,
            "downstream_guard": True,
            "delete_scope_context_only": True,
        },
        "writes_database": False,
        "event_ledger_touched": False,
        "worker_started": False,
    }


def build_preopen_readiness_noop_report(*, for_trade_date: str, readiness: Mapping[str, Any]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_READINESS_KEYS if not bool(readiness.get(key))]
    if missing:
        raise GuardBlocked("preopen_readiness_missing:" + ",".join(missing))
    return {
        "result": "PASS",
        "check": "preopen_readiness_noop",
        "layer_role": "runtime_control",
        "for_trade_date": for_trade_date,
        "readiness": {key: bool(readiness.get(key)) for key in REQUIRED_READINESS_KEYS},
        "writes_database": False,
        "event_ledger_touched": False,
        "worker_started": False,
    }


def build_lineage_pollution_guard_report(*, for_trade_date: str, pollution_counts: Mapping[str, Any]) -> dict[str, Any]:
    nonzero = {key: int(value or 0) for key, value in pollution_counts.items() if int(value or 0) != 0}
    if nonzero:
        details = ",".join(f"{key}={value}" for key, value in sorted(nonzero.items()))
        raise GuardBlocked("lineage_pollution_detected:" + details)
    return {
        "result": "PASS",
        "check": "lineage_pollution_guard",
        "layer_role": "runtime_control",
        "for_trade_date": for_trade_date,
        "pollution_counts": dict(pollution_counts),
        "writes_database": False,
        "event_ledger_touched": False,
        "worker_started": False,
    }


def build_active_lineage_materialization_guard_report(
    *,
    for_trade_date: str,
    docs_root: str | Path = "docs/post_close_fastlane",
    lineage_config_path: str | Path = DEFAULT_LINEAGE_CONFIG_PATH,
) -> dict[str, Any]:
    docs_root_path = Path(docs_root)
    latest_dir = _latest_fastlane_dir_for(docs_root_path, for_trade_date)
    status_path = latest_dir / "00_status.json"
    oneshot_path = latest_dir / "01_oneshot_execute_report.json"
    status = _load_json_object(status_path)
    oneshot = _load_json_object(oneshot_path)
    base_report = {
        "check": "active_lineage_materialization_guard",
        "layer_role": "runtime_control",
        "for_trade_date": for_trade_date,
        "latest_fastlane_dir": str(latest_dir),
        "lineage_config_path": str(lineage_config_path),
        "writes_database": False,
        "event_ledger_touched": False,
        "worker_started": False,
        "launchd_mutated": False,
    }
    if not status or not oneshot:
        blocked = {
            **base_report,
            "result": "BLOCKED",
            "blocked_reason": "BLOCKED_FASTLANE_NOT_PASS:status_or_report_missing",
        }
        raise GuardBlocked(str(blocked["blocked_reason"]), report=blocked)
    if latest_dir.name != for_trade_date or str(status.get("for_trade_date") or "") != for_trade_date:
        blocked = {
            **base_report,
            "result": "BLOCKED",
            "status_result": status.get("result"),
            "oneshot_result": oneshot.get("result"),
            "blocked_reason": "BLOCKED_FASTLANE_NOT_PASS:latest_for_trade_date_mismatch",
        }
        raise GuardBlocked(str(blocked["blocked_reason"]), report=blocked)
    if status.get("result") != "EXECUTE_PASS" or oneshot.get("result") != "EXECUTE_PASS":
        blocked = {
            **base_report,
            "result": "BLOCKED",
            "status_result": status.get("result"),
            "oneshot_result": oneshot.get("result"),
            "failed_step_id": status.get("failed_step_id"),
            "blocked_reason": "BLOCKED_FASTLANE_NOT_PASS",
        }
        raise GuardBlocked(str(blocked["blocked_reason"]), report=blocked)

    lineage = _load_json_object(Path(lineage_config_path))
    mismatches: list[str] = []
    if not lineage:
        mismatches.append("lineage_config_missing_or_malformed")
    else:
        expected_paths = {
            "source_status_path": status_path,
            "source_oneshot_report_path": oneshot_path,
        }
        if str(lineage.get("for_trade_date") or "") != for_trade_date:
            mismatches.append("for_trade_date")
        if str(lineage.get("source_trade_date") or "") != str(status.get("source_trade_date") or ""):
            mismatches.append("source_trade_date")
        for key, expected_path in expected_paths.items():
            if not _paths_match(lineage.get(key), expected_path):
                mismatches.append(key)
    if mismatches:
        blocked = {
            **base_report,
            "result": "BLOCKED",
            "status_result": status.get("result"),
            "oneshot_result": oneshot.get("result"),
            "blocked_reason": "BLOCKED_ACTIVE_LINEAGE_NOT_MATERIALIZED",
            "mismatches": mismatches,
            "active_lineage_for_trade_date": lineage.get("for_trade_date") if lineage else "",
            "active_lineage_source_trade_date": lineage.get("source_trade_date") if lineage else "",
        }
        raise GuardBlocked(str(blocked["blocked_reason"]), report=blocked)

    return {
        **base_report,
        "result": "PASS",
        "status_result": status.get("result"),
        "oneshot_result": oneshot.get("result"),
        "active_lineage_for_trade_date": lineage.get("for_trade_date"),
        "active_lineage_source_trade_date": lineage.get("source_trade_date"),
        "active_lineage_materialized": True,
    }


def _latest_fastlane_dir_for(docs_root: Path, for_trade_date: str) -> Path:
    latest_path = docs_root / "latest"
    if latest_path.exists():
        try:
            return latest_path.resolve(strict=True)
        except OSError:
            return latest_path
    return docs_root / for_trade_date


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _paths_match(left: Any, right: Path) -> bool:
    if not left:
        return False
    left_path = Path(str(left))
    try:
        return left_path.resolve() == right.resolve()
    except OSError:
        return str(left_path) == str(right)


def _worker_state_active(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value.get("active") or value.get("loaded") or value.get("running"))
    return bool(value)


def _worker_state_label(worker_name: str, value: Any) -> str | None:
    if isinstance(value, Mapping):
        label = value.get("label")
        return str(label) if label else None
    return None


def _worker_state_report_path(worker_name: str, value: Any) -> str:
    if isinstance(value, Mapping) and value.get("report_path"):
        return str(value["report_path"])
    allowlisted = SAFE_PROOF_POLLER_ALLOWLIST.get(worker_name)
    return str(allowlisted["report_path"]) if allowlisted else ""


def _nested_child_count(report: Mapping[str, Any]) -> int:
    if "executed_child_command_count" in report:
        return int(report.get("executed_child_command_count") or 0)
    child_execution = report.get("child_execution")
    if isinstance(child_execution, Mapping):
        return int(child_execution.get("executed_child_command_count") or 0)
    return 0


def _require_false(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if mapping.get(key) is not False:
            return key
    return None


def _validate_safe_proof_poller_report(
    *,
    worker_name: str,
    state: Any,
    report_max_age_seconds: int,
) -> tuple[bool, dict[str, Any], str]:
    allowlisted = SAFE_PROOF_POLLER_ALLOWLIST.get(worker_name)
    label = _worker_state_label(worker_name, state)
    if not allowlisted or label != allowlisted["label"]:
        return False, {"classification": "loaded_unsafe_blocked", "label": label}, "label_not_allowlisted"

    report_path = Path(_worker_state_report_path(worker_name, state))
    evidence: dict[str, Any] = {
        "classification": "loaded_safe_but_report_unsafe_blocked",
        "label": label,
        "report_path": str(report_path),
    }
    if not report_path.exists():
        return False, evidence, "report_missing"
    age_seconds = max(0, int(time.time() - report_path.stat().st_mtime))
    evidence["report_age_seconds"] = age_seconds
    if age_seconds > report_max_age_seconds:
        return False, evidence, "report_stale"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, evidence, "report_unreadable"

    status = report.get("status")
    result = report.get("result")
    evidence["status"] = status
    evidence["result"] = result
    child_count = _nested_child_count(report)
    evidence["executed_child_command_count"] = child_count
    if child_count != 0:
        return False, evidence, "child_executed"
    if status not in ("noop", "ready") and result not in ("noop", "ready"):
        return False, evidence, "report_status_not_safe"

    side_effects = report.get("side_effects")
    if not isinstance(side_effects, Mapping):
        return False, evidence, "side_effects_missing"
    if allowlisted["kind"] == "n3":
        required_false = (
            "database_written",
            "market_data_pulled",
            "writes_outbox",
            "consumes_outbox",
            "updates_inbox_or_checkpoint",
            "touches_n4_n5_n6",
            "rollback_executed",
            "schema_changed",
            "starts_worker",
        )
    else:
        required_false = (
            "child_executed",
            "database_written",
            "outbox_consumed",
            "inbox_or_checkpoint_updated",
            "n5_n6_entered",
            "rollback_executed",
            "schema_changed",
            "worker_or_launchd_touched",
        )
    bad_side_effect = _require_false(side_effects, required_false)
    if bad_side_effect:
        return False, evidence, "side_effect_" + bad_side_effect

    forbidden = report.get("forbidden_operation_proof")
    if allowlisted["kind"] == "n4":
        if not isinstance(forbidden, Mapping):
            return False, evidence, "forbidden_operation_proof_missing"
        bad_forbidden = _require_false(
            forbidden,
            (
                "child_executed",
                "outbox_consumed",
                "inbox_checkpoint_updated",
                "n5_n6_entered",
                "rollback_executed",
                "schema_changed",
                "worker_launchd_touched",
            ),
        )
        if bad_forbidden:
            return False, evidence, "forbidden_operation_" + bad_forbidden

    evidence["classification"] = "loaded_safe_noop_allowlisted"
    return True, evidence, ""


def build_worker_launchd_guard_report(
    *,
    for_trade_date: str,
    worker_states: Mapping[str, Any],
    report_max_age_seconds: int = SAFE_REPORT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    classifications: dict[str, str] = {}
    allowlist_evidence: dict[str, Any] = {}
    blockers: list[str] = []

    for key, value in sorted(worker_states.items()):
        if not _worker_state_active(value):
            classifications[key] = "not_loaded_or_running"
            continue
        allowed, evidence, reason = _validate_safe_proof_poller_report(
            worker_name=key,
            state=value,
            report_max_age_seconds=report_max_age_seconds,
        )
        allowlist_evidence[key] = evidence
        classifications[key] = str(evidence["classification"])
        if not allowed:
            if classifications[key] == "loaded_safe_but_report_unsafe_blocked":
                blockers.append(f"{classifications[key]}:{key}:{reason}")
            else:
                blockers.append(key)

    if blockers:
        blocked_report = {
            "result": "BLOCKED",
            "check": "worker_launchd_guard",
            "layer_role": "runtime_control",
            "for_trade_date": for_trade_date,
            "blocked_reason": "worker_loaded_or_running:" + ",".join(blockers),
            "worker_guard_policy": "safe_proof_poller_allowlist_v1",
            "worker_guard_classification": classifications,
            "safe_allowlist_evidence": allowlist_evidence,
            "worker_states": dict(worker_states),
            "writes_database": False,
            "event_ledger_touched": False,
            "worker_started": False,
            "launchd_mutated": False,
        }
        raise GuardBlocked(str(blocked_report["blocked_reason"]), report=blocked_report)
    return {
        "result": "PASS",
        "check": "worker_launchd_guard",
        "layer_role": "runtime_control",
        "for_trade_date": for_trade_date,
        "worker_states": dict(worker_states),
        "worker_guard_policy": "safe_proof_poller_allowlist_v1",
        "worker_guard_classification": classifications,
        "safe_allowlist_evidence": allowlist_evidence,
        "writes_database": False,
        "event_ledger_touched": False,
        "worker_started": False,
        "launchd_mutated": False,
    }


def fetch_preopen_readiness(
    *,
    dsn: str,
    condition_run_id: str,
    subscription_run_id: str,
    preload_run_id: str,
    n4_context_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
) -> dict[str, bool]:
    import psycopg

    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        conn.execute("BEGIN READ ONLY")
        n2 = _scalar_count(
            conn,
            "SELECT count(*) FROM common_condition_run WHERE run_id = %s AND status IN ('passed', 'passed_active')",
            (condition_run_id,),
        )
        subscription = _scalar_count(
            conn,
            "SELECT count(*) FROM common_market_data_run WHERE run_id = %s AND status = 'passed'",
            (subscription_run_id,),
        )
        preload = _scalar_count(
            conn,
            "SELECT count(*) FROM common_market_data_run WHERE run_id = %s AND status = 'passed'",
            (preload_run_id,),
        )
        cumulative = 0
        for table_name in (
            "stock_previous_day_minute_cumulative",
            "index_previous_day_minute_cumulative",
            "board_previous_day_minute_cumulative",
        ):
            cumulative += _scalar_count(
                conn,
                f"""
                SELECT count(*)
                FROM {table_name}
                WHERE source_previous_day_minute_run_id = %s
                  AND for_trade_date = %s
                  AND source_trade_date = %s
                """,
                (preload_run_id, for_trade_date, source_trade_date),
            )
        context = _scalar_count(
            conn,
            """
            SELECT count(*)
            FROM common_trigger_run
            WHERE run_id = %s
              AND status = 'passed'
              AND context_snapshot_row_count > 0
            """,
            (n4_context_run_id,),
        )
    return {
        "n2_condition": n2 > 0,
        "n3_subscription": subscription > 0,
        "n3_a1_preload": preload > 0,
        "n3_a1_cumulative_amount": cumulative > 0,
        "n4_trigger_context_snapshot": context > 0,
    }


def fetch_lineage_pollution_counts(*, dsn: str, for_trade_date: str) -> dict[str, int]:
    import psycopg

    like_date = f"%{for_trade_date}%"
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        conn.execute("BEGIN READ ONLY")
        return {
            "n3p_runs": _scalar_count(
                conn,
                "SELECT count(*) FROM common_market_data_run WHERE run_id LIKE %s",
                (f"realtime_action_confirmation_metric_{for_trade_date}%",),
            ),
            "n4_matcher_runs": _scalar_count(
                conn,
                "SELECT count(*) FROM common_trigger_run WHERE run_id LIKE %s AND run_id NOT LIKE %s",
                (f"%{for_trade_date}%", f"trigger_context_snapshot_{for_trade_date}%"),
            ),
            "n5_runs": _scalar_count(
                conn,
                "SELECT count(*) FROM common_action_run WHERE run_id LIKE %s OR source_trigger_run_id LIKE %s",
                (like_date, like_date),
            ),
            "delivered_or_delivering_outbox": _scalar_count(
                conn,
                "SELECT count(*) FROM common_event_outbox WHERE source_run_id LIKE %s AND status IN ('delivered', 'delivering')",
                (like_date,),
            ),
            "inbox_refs": _scalar_count(
                conn,
                "SELECT count(*) FROM common_event_inbox WHERE source_run_id LIKE %s OR payload_json::text LIKE %s OR raw_json::text LIKE %s",
                (like_date, like_date, like_date),
            ),
            "checkpoint_refs": _scalar_count(
                conn,
                "SELECT count(*) FROM common_event_consumer_checkpoint WHERE checkpoint_payload::text LIKE %s OR last_event_id LIKE %s",
                (like_date, like_date),
            ),
        }


def detect_worker_states() -> dict[str, Any]:
    states: dict[str, Any] = {
        "n3_worker": False,
        "n3p_worker": False,
        "n3_hint_worker": False,
        "n4_worker": False,
        "n4_hint_worker": False,
        "n5_worker": False,
        "n6_worker": False,
    }
    for worker_name, labels in UNSAFE_LAUNCHD_LABELS.items():
        if any(_launchd_label_loaded(label) for label in labels):
            states[worker_name] = True
    for worker_name, allowlisted in SAFE_PROOF_POLLER_ALLOWLIST.items():
        label = str(allowlisted["label"])
        loaded = _launchd_label_loaded(label)
        if loaded:
            states[worker_name] = {
                "active": True,
                "loaded": True,
                "label": label,
                "report_path": allowlisted["report_path"],
            }
    for line in _process_command_lines():
        lowered = line.lower()
        tokens = _command_tokens(line)
        if _command_invokes_script(tokens, "scripts/run_n3_intraday_proof_poller_once.py"):
            worker_name = "n3_worker"
            if _command_has_branch(tokens, "n3p_only"):
                worker_name = "n3p_worker"
            elif _command_has_branch(tokens, "hint_only"):
                worker_name = "n3_hint_worker"
            allowlisted = SAFE_PROOF_POLLER_ALLOWLIST[worker_name]
            states[worker_name] = {
                "active": True,
                "running": True,
                "label": allowlisted["label"],
                "report_path": allowlisted["report_path"],
            }
            continue
        if _command_invokes_script(tokens, "scripts/run_n4_intraday_proof_discovery_poll_once.py"):
            worker_name = "n4_hint_worker" if _command_has_mode(tokens, "hint") else "n4_worker"
            allowlisted = SAFE_PROOF_POLLER_ALLOWLIST[worker_name]
            states[worker_name] = {
                "active": True,
                "running": True,
                "label": allowlisted["label"],
                "report_path": allowlisted["report_path"],
            }
            continue
        for worker_name, markers in WORKER_PROCESS_MARKERS.items():
            if any(_command_has_worker_marker(tokens, lowered, marker) for marker in markers):
                states[worker_name] = True
    return states


def _process_command_lines() -> list[str]:
    try:
        completed = subprocess.run(["ps", "-axo", "pid=,command="], check=False, capture_output=True, text=True)
    except OSError:
        return []
    return (completed.stdout or "").splitlines()


def _command_tokens(line: str) -> list[str]:
    try:
        tokens = shlex.split(line)
    except ValueError:
        tokens = line.split()
    if tokens and tokens[0].isdigit():
        return tokens[1:]
    return tokens


def _command_has_script(tokens: list[str], script_path: str) -> bool:
    normalized = script_path.strip("/")
    return any(token.strip("'\"").strip("/").endswith(normalized) for token in tokens)


def _command_invokes_script(tokens: list[str], script_path: str) -> bool:
    normalized = script_path.strip("/")
    if not tokens:
        return False
    executable = Path(tokens[0]).name
    if tokens[0].strip("'\"").strip("/").endswith(normalized):
        return True
    if executable.startswith("python") and _command_has_script(tokens[1:], script_path):
        return True
    if executable == "env":
        env_payload = [token for token in tokens[1:] if "=" not in token]
        return _command_invokes_script(env_payload, script_path)
    if executable in {"sh", "bash", "zsh"} and "-c" in tokens:
        command_index = tokens.index("-c") + 1
        if command_index < len(tokens):
            return _command_invokes_script(_command_tokens(tokens[command_index]), script_path)
    return False


def _command_has_branch(tokens: list[str], branch: str) -> bool:
    for index, token in enumerate(tokens):
        if token == "--branch" and index + 1 < len(tokens) and tokens[index + 1] == branch:
            return True
        if token == f"--branch={branch}":
            return True
    return False


def _command_has_mode(tokens: list[str], mode: str) -> bool:
    for index, token in enumerate(tokens):
        if token == "--mode" and index + 1 < len(tokens) and tokens[index + 1] == mode:
            return True
        if token == f"--mode={mode}":
            return True
    return False


def _command_has_worker_marker(tokens: list[str], lowered_line: str, marker: str) -> bool:
    if marker.endswith(".py"):
        return _command_invokes_script(tokens, f"scripts/{marker}")
    return marker.lower() in lowered_line


def _launchd_label_loaded(label: str) -> bool:
    domain = f"gui/{os.getuid()}/{label}"
    try:
        completed = subprocess.run(["launchctl", "print", domain], check=False, capture_output=True, text=True)
    except OSError:
        return False
    return completed.returncode == 0


def _scalar_count(conn: Any, sql: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] if row else 0)


def write_report(report: Mapping[str, Any], *, json_report_path: str | Path, markdown_report_path: str | Path) -> None:
    json_path = Path(json_report_path)
    md_path = Path(markdown_report_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    md_path.write_text(format_markdown_report(report), encoding="utf-8")


def format_markdown_report(report: Mapping[str, Any]) -> str:
    lines = [
        f"# {report.get('check', 'post_close_preopen_guard')}",
        "",
        f"- result: `{report.get('result')}`",
        f"- layer_role: `{report.get('layer_role')}`",
        f"- for_trade_date: `{report.get('for_trade_date')}`",
        f"- writes_database: `{report.get('writes_database')}`",
        f"- event_ledger_touched: `{report.get('event_ledger_touched')}`",
        f"- worker_started: `{report.get('worker_started')}`",
    ]
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review post-close pre-open guard readiness.")
    parser.add_argument(
        "--check",
        required=True,
        choices=[
            "n4_context_rollback_ready",
            "preopen_readiness_noop",
            "lineage_pollution_guard",
            "active_lineage_materialization_guard",
            "worker_launchd_guard",
        ],
    )
    parser.add_argument("--dsn", default=os.environ.get("ASHARE_V3_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--docs-root", default="docs/post_close_fastlane")
    parser.add_argument("--lineage-config-path", default=DEFAULT_LINEAGE_CONFIG_PATH)
    parser.add_argument("--for-trade-date", required=True)
    parser.add_argument("--source-trade-date", default="")
    parser.add_argument("--condition-run-id", default="")
    parser.add_argument("--subscription-run-id", default="")
    parser.add_argument("--preload-run-id", default="")
    parser.add_argument("--n4-context-run-id", default="")
    parser.add_argument("--rollback-sql-path", default="")
    parser.add_argument("--json-report-path", required=True)
    parser.add_argument("--markdown-report-path", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        if args.check == "n4_context_rollback_ready":
            report = build_n4_context_rollback_ready_report(
                for_trade_date=args.for_trade_date,
                rollback_sql_path=args.rollback_sql_path,
            )
        elif args.check == "preopen_readiness_noop":
            readiness = fetch_preopen_readiness(
                dsn=args.dsn,
                condition_run_id=args.condition_run_id,
                subscription_run_id=args.subscription_run_id,
                preload_run_id=args.preload_run_id,
                n4_context_run_id=args.n4_context_run_id,
                for_trade_date=args.for_trade_date,
                source_trade_date=args.source_trade_date,
            )
            report = build_preopen_readiness_noop_report(for_trade_date=args.for_trade_date, readiness=readiness)
        elif args.check == "lineage_pollution_guard":
            pollution_counts = fetch_lineage_pollution_counts(dsn=args.dsn, for_trade_date=args.for_trade_date)
            report = build_lineage_pollution_guard_report(for_trade_date=args.for_trade_date, pollution_counts=pollution_counts)
        elif args.check == "active_lineage_materialization_guard":
            report = build_active_lineage_materialization_guard_report(
                for_trade_date=args.for_trade_date,
                docs_root=args.docs_root,
                lineage_config_path=args.lineage_config_path,
            )
        else:
            report = build_worker_launchd_guard_report(for_trade_date=args.for_trade_date, worker_states=detect_worker_states())
    except GuardBlocked as exc:
        report = exc.report or {
            "result": "BLOCKED",
            "check": args.check,
            "layer_role": "runtime_control",
            "for_trade_date": args.for_trade_date,
            "blocked_reason": str(exc),
            "writes_database": False,
            "event_ledger_touched": False,
            "worker_started": False,
        }
        write_report(report, json_report_path=args.json_report_path, markdown_report_path=args.markdown_report_path)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    write_report(report, json_report_path=args.json_report_path, markdown_report_path=args.markdown_report_path)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
