"""Read-only N3-B1 -> N4 -> N5 intraday run-once pipeline checker."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from ashare_v3.runtime_control.fast_gate import build_fast_gate_decision


PASS = "PASS"
WARNING = "WARNING"
BLOCKED = "BLOCKED"


def expected_intraday_run_ids(
    *,
    for_trade_date: str,
    minute_label: str,
    condition_run_id: str,
    b1_label: str,
    subscription_run_id: str | None = None,
) -> dict[str, str]:
    subscription = subscription_run_id or f"market_data_subscription_{for_trade_date}_{condition_run_id}"
    b1_snapshot = f"realtime_snapshot_{for_trade_date}_{b1_label}_{subscription}"
    n4_execute = f"trigger_action_confirmation_metric_execute_{for_trade_date}_{minute_label}__{condition_run_id}"
    return {
        "condition_run_id": condition_run_id,
        "subscription_run_id": subscription,
        "b1_snapshot_run_id": b1_snapshot,
        "c1_today_minute_run_id": f"today_minute_bar_1m_{for_trade_date}_until_{minute_label}__{subscription}",
        "n3_action_confirmation_projection_run_id": (
            f"action_confirmation_projection_metric_{for_trade_date}_{minute_label}__{b1_snapshot}"
        ),
        "n4_execute_run_id": n4_execute,
        "n5_action_run_id": f"action_consumer_action_confirmation_metric_execute_{for_trade_date}_{minute_label}__{n4_execute}",
    }


def build_intraday_pipeline_readiness(
    *,
    for_trade_date: str,
    minute_label: str,
    condition_run_id: str,
    b1_label: str,
    docs_dir: Path | str,
    sql_dir: Path | str,
    subscription_run_id: str | None = None,
) -> dict[str, Any]:
    docs_path = Path(docs_dir)
    sql_path = Path(sql_dir)
    run_ids = expected_intraday_run_ids(
        for_trade_date=for_trade_date,
        minute_label=minute_label,
        condition_run_id=condition_run_id,
        b1_label=b1_label,
        subscription_run_id=subscription_run_id,
    )
    run_id_rules = check_run_id_rules(
        for_trade_date=for_trade_date,
        minute_label=minute_label,
        condition_run_id=condition_run_id,
        b1_label=b1_label,
        run_ids=run_ids,
    )
    rollback = build_rollback_registry(
        for_trade_date=for_trade_date,
        minute_label=minute_label,
        b1_label=b1_label,
        sql_dir=sql_path,
    )
    artifacts = load_intraday_artifacts(
        for_trade_date=for_trade_date,
        minute_label=minute_label,
        b1_label=b1_label,
        docs_dir=docs_path,
    )
    stages = build_stage_statuses(run_ids=run_ids, artifacts=artifacts, rollback_items=rollback["items"])
    blockers = list(run_id_rules["blockers"]) + list(rollback["blockers"])
    warnings = list(rollback["warnings"])
    for stage in stages:
        blockers.extend(stage["blockers"])
        warnings.extend(stage["warnings"])
    forbidden = check_forbidden_downstream_risk(artifacts)
    blockers.extend(forbidden["blockers"])
    warnings.extend(forbidden["warnings"])
    result = BLOCKED if blockers else (WARNING if warnings else PASS)
    return {
        "result": result,
        "stage": "intraday_pipeline_readiness",
        "layer_role": "runtime_control",
        "for_trade_date": for_trade_date,
        "minute_label": minute_label,
        "run_ids": run_ids,
        "run_id_rules": run_id_rules,
        "stages": stages,
        "rollback_registry": rollback,
        "missing_rollback_paths": rollback["missing_paths"],
        "event_summary": build_event_summary(artifacts),
        "outbox_inbox_checkpoint_risk": {
            "status": WARNING,
            "reason": "read_only_checker_requires_manual_pre_execute_db_ref_check",
            "checks": [
                "delivered_or_delivering_outbox_zero",
                "downstream_inbox_refs_zero",
                "consumer_checkpoint_refs_zero",
                "worker_consumer_process_scope_clear",
            ],
        },
        "excluded_lanes": {
            "c2_closed_30m": "separate_gate",
            "c3_minute_bar_closed": "separate_gate",
            "reason": "not_part_of_minimal_B1_to_N4_to_N5_live_chain",
        },
        "side_effects": {
            "reads_docs": True,
            "reads_sql_files": True,
            "connects_database": False,
            "writes_database": False,
            "executes_n3_n5": False,
            "executes_sql": False,
            "executes_rollback": False,
            "consumes_outbox": False,
            "updates_outbox_status": False,
            "starts_worker": False,
            "triggers_delivery_or_notification": False,
            "push_voice_mobile_sim_position_real_trade": False,
            "touches_old_system": False,
        },
        "warnings": sorted(set(warnings)),
        "blockers": sorted(set(blockers)),
        "next_step": next_step_for_result(result),
    }


def build_intraday_fast_gate(
    *,
    for_trade_date: str,
    minute_label: str,
    condition_run_id: str,
    b1_label: str,
    sql_dir: Path | str,
    subscription_run_id: str | None = None,
) -> dict[str, str]:
    """Return only PASS / FAIL / BLOCK for the intraday gate.

    This skips artifact/event analysis. Use build_intraday_pipeline_readiness
    for deferred analysis reports.
    """

    sql_path = Path(sql_dir)
    run_ids = expected_intraday_run_ids(
        for_trade_date=for_trade_date,
        minute_label=minute_label,
        condition_run_id=condition_run_id,
        b1_label=b1_label,
        subscription_run_id=subscription_run_id,
    )
    run_id_rules = check_run_id_rules(
        for_trade_date=for_trade_date,
        minute_label=minute_label,
        condition_run_id=condition_run_id,
        b1_label=b1_label,
        run_ids=run_ids,
    )
    rollback = build_rollback_registry(
        for_trade_date=for_trade_date,
        minute_label=minute_label,
        b1_label=b1_label,
        sql_dir=sql_path,
    )
    blockers = list(run_id_rules["blockers"]) + list(rollback["blockers"])
    return build_fast_gate_decision(blockers=blockers, failures=[]).to_dict()


def check_run_id_rules(
    *,
    for_trade_date: str,
    minute_label: str,
    condition_run_id: str,
    b1_label: str,
    run_ids: Mapping[str, str],
) -> dict[str, Any]:
    blockers: list[str] = []
    subscription = run_ids["subscription_run_id"]
    rules = {
        "subscription_run_id": f"market_data_subscription_{for_trade_date}_<condition_run_id>",
        "b1_snapshot_run_id": f"realtime_snapshot_{for_trade_date}_{b1_label}_<subscription_run_id>",
        "c1_today_minute_run_id": f"today_minute_bar_1m_{for_trade_date}_until_{minute_label}__<subscription_run_id>",
        "n3_action_confirmation_projection_run_id": (
            f"action_confirmation_projection_metric_{for_trade_date}_{minute_label}__<b1_snapshot_run_id>"
        ),
        "n4_execute_run_id": f"trigger_action_confirmation_metric_execute_{for_trade_date}_{minute_label}__<condition_run_id>",
        "n5_action_run_id": f"action_consumer_action_confirmation_metric_execute_{for_trade_date}_{minute_label}__<n4_execute_run_id>",
    }
    expected = expected_intraday_run_ids(
        for_trade_date=for_trade_date,
        minute_label=minute_label,
        condition_run_id=condition_run_id,
        b1_label=b1_label,
        subscription_run_id=subscription,
    )
    for key, value in expected.items():
        if run_ids[key] != value:
            blockers.append(f"{key}_rule_mismatch")
    if not re.match(r"^condition_layer_[0-9]{8}_source_[0-9]{8}_v[0-9]+$", condition_run_id):
        blockers.append("condition_run_id_format_mismatch")
    return {"status": BLOCKED if blockers else PASS, "rules": rules, "blockers": blockers}


def build_rollback_registry(
    *,
    for_trade_date: str,
    minute_label: str,
    b1_label: str,
    sql_dir: Path,
) -> dict[str, Any]:
    filenames = {
        "b1": f"N3_B1_realtime_snapshot_{for_trade_date}_{b1_label}_rollback.sql",
        "c1": f"N3_C1_today_minute_bar_1m_{for_trade_date}_until_{minute_label}_rollback.sql",
        "n3_action_confirmation_projection": "N3_action_confirmation_projection_metric_business_rollback.sql",
        "n4": "N4_action_confirmation_metric_business_execute_rollback.sql",
        "n5": f"N5_{for_trade_date}_action_confirmation_metric_execute_rollback.sql",
    }
    items: list[dict[str, Any]] = []
    missing: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []
    for stage_id, filename in filenames.items():
        path = sql_dir / filename
        exists = path.exists()
        hard_fail = rollback_has_hard_fail_before_delete(path) if exists else False
        relative = f"sql/{filename}"
        if not exists:
            missing.append(relative)
            blockers.append(f"missing_rollback:{relative}")
        elif not hard_fail:
            warnings.append(f"rollback_not_hard_fail_before_delete:{relative}")
        items.append(
            {
                "stage_id": stage_id,
                "rollback_sql_path": relative,
                "exists": exists,
                "hard_fail_before_delete": hard_fail,
                "executes_rollback": False,
            }
        )
    return {
        "status": BLOCKED if blockers else (WARNING if warnings else PASS),
        "items": items,
        "missing_paths": missing,
        "warnings": warnings,
        "blockers": blockers,
    }


def rollback_has_hard_fail_before_delete(path: Path) -> bool:
    text = strip_sql_line_comments(path.read_text(encoding="utf-8"))
    first_delete = find_sql_word(text, "DELETE")
    first_raise = text.upper().find("RAISE EXCEPTION")
    return first_raise >= 0 and (first_delete < 0 or first_raise < first_delete)


def strip_sql_line_comments(text: str) -> str:
    cleaned: list[str] = []
    for line in text.splitlines():
        cleaned.append(line.split("--", 1)[0])
    return "\n".join(cleaned)


def find_sql_word(text: str, word: str) -> int:
    match = re.search(rf"\b{re.escape(word)}\b", text, flags=re.IGNORECASE)
    return -1 if match is None else match.start()


def load_intraday_artifacts(
    *,
    for_trade_date: str,
    minute_label: str,
    b1_label: str,
    docs_dir: Path,
) -> dict[str, dict[str, Any]]:
    paths = {
        "b1": f"N3_B1_realtime_snapshot_{for_trade_date}_{b1_label}_execute_report.json",
        "c1": f"N3_C1_today_minute_bar_1m_{for_trade_date}_until_{minute_label}_execute_report.json",
        "n3_action_confirmation_projection": "N3_action_confirmation_projection_writer_execute_report.json",
        "n4": "N4_action_confirmation_metric_business_execute_report.json",
        "n5": f"N5_{for_trade_date}_action_confirmation_metric_execute_summary.json",
    }
    return {
        stage_id: {
            "path": f"docs/{filename}",
            "data": load_json_file(docs_dir / filename),
            "exists": (docs_dir / filename).exists(),
        }
        for stage_id, filename in paths.items()
    }


def load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size > 1_000_000:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def build_stage_statuses(
    *,
    run_ids: Mapping[str, str],
    artifacts: Mapping[str, Mapping[str, Any]],
    rollback_items: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rollback_by_stage = {item["stage_id"]: item for item in rollback_items}
    specs = [
        ("b1", "N3 B1 realtime snapshot outbox", "N3_market_data", "b1_snapshot_run_id", "snapshot_run_id"),
        ("c1", "N3 C1 today minute 1m", "N3_market_data", "c1_today_minute_run_id", "today_minute_run_id"),
        (
            "n3_action_confirmation_projection",
            "N3 action-confirmation projection",
            "N3_market_data",
            "n3_action_confirmation_projection_run_id",
            "projection_run_id",
        ),
        ("n4", "N4 action-confirmation metric trigger", "N4_trigger", "n4_execute_run_id", "execute_run_id"),
        ("n5", "N5 action-confirmation metric action", "N5_action", "n5_action_run_id", "action_run_id"),
    ]
    stages: list[dict[str, Any]] = []
    for stage_id, title, layer_role, expected_key, artifact_key in specs:
        artifact = artifacts[stage_id]
        data = artifact["data"]
        blockers: list[str] = []
        warnings: list[str] = []
        if not artifact["exists"]:
            blockers.append(f"missing_artifact:{artifact['path']}")
        elif data is None:
            blockers.append(f"artifact_unreadable_or_too_large:{artifact['path']}")
        expected_run_id = run_ids[expected_key]
        actual_run_id = str((data or {}).get(artifact_key) or "")
        if data is not None and actual_run_id != expected_run_id:
            blockers.append(f"{stage_id}_run_id_mismatch")
        quality = extract_quality(data or {})
        if quality["p0"] > 0:
            blockers.append(f"{stage_id}_p0_nonzero")
        if quality["p1"] > 0 or quality["p2"] > 0:
            warnings.append(f"{stage_id}_quality_warning_p1_p2={quality['p1']}/{quality['p2']}")
        rollback = rollback_by_stage[stage_id]
        if not rollback["exists"]:
            blockers.append(f"{stage_id}_rollback_missing")
        elif not rollback["hard_fail_before_delete"]:
            warnings.append(f"{stage_id}_rollback_not_hard_fail_before_delete")
        status = BLOCKED if blockers else (WARNING if warnings else PASS)
        stages.append(
            {
                "stage_id": stage_id,
                "title": title,
                "layer_role": layer_role,
                "status": status,
                "run_id": expected_run_id,
                "artifact_path": artifact["path"],
                "rollback_sql_path": rollback["rollback_sql_path"],
                "quality": quality,
                "warnings": warnings,
                "blockers": blockers,
            }
        )
    return stages


def extract_quality(data: Mapping[str, Any]) -> dict[str, int]:
    quality = data.get("quality") if isinstance(data.get("quality"), Mapping) else data
    return {
        "p0": int(quality.get("p0_count") or quality.get("p0") or 0),
        "p1": int(quality.get("p1_count") or quality.get("p1") or 0),
        "p2": int(quality.get("p2_count") or quality.get("p2") or 0),
    }


def check_forbidden_downstream_risk(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    forbidden_true_keys = {
        "worker_started",
        "old_system_touched",
        "real_trade_touched",
        "voice_touched",
        "mobile_touched",
        "sim_touched",
        "position_state_written",
        "position_event_written",
        "n6_user_layer_touched",
        "user_layer_touched",
        "n4_outbox_status_updated",
        "n4_outbox_consumed",
    }
    for stage_id, artifact in artifacts.items():
        data = artifact["data"] or {}
        for section_name in ("side_effects", "boundary"):
            section = data.get(section_name)
            if not isinstance(section, Mapping):
                continue
            for key in forbidden_true_keys:
                if section.get(key) is True:
                    blockers.append(f"{stage_id}_{section_name}_{key}_true")
    warnings.append("manual_worker_consumer_process_check_required")
    warnings.append("manual_outbox_inbox_checkpoint_db_ref_check_required")
    return {"blockers": blockers, "warnings": warnings}


def build_event_summary(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    b1_data = artifacts["b1"]["data"] or {}
    c1_data = artifacts["c1"]["data"] or {}
    n3_metric_data = artifacts["n3_action_confirmation_projection"]["data"] or {}
    n4_data = artifacts["n4"]["data"] or {}
    n5_data = artifacts["n5"]["data"] or {}
    return {
        "b1_market_snapshot_updated": nested_get(
            b1_data, ("post_checks", "n3_b1_outbox_counts_by_type", "MarketSnapshotUpdated"), default=0
        ),
        "c1_minute_rows": nested_get(c1_data, ("write_result", "minute_rows_written"), default=0),
        "n3_action_metric_rows": nested_get(
            n3_metric_data, ("write_result", "rows_written", "total"), default=0
        ),
        "n4_outbox": {
            "common_event_outbox": nested_get(n4_data, ("write_counts", "common_event_outbox"), default=0),
            "TriggerMatched": nested_get(n5_data, ("n4_outbox_input_summary", "matched_count"), default=0),
            "TriggerPendingMarketData": nested_get(n5_data, ("n4_outbox_input_summary", "pending_count"), default=0),
        },
        "n5_pending_outbox": n5_data.get("n5_outbox_pending_summary") or {},
    }


def nested_get(data: Mapping[str, Any], path: tuple[str, ...], default: Any) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def next_step_for_result(result: str) -> str:
    if result == BLOCKED:
        return "Resolve missing artifacts, rollback paths, run_id mismatches, P0 quality, or forbidden downstream risk."
    if result == WARNING:
        return (
            "Review warnings, run manual worker/outbox ref pre-checks, then use explicit layer gates for B1, "
            "N3 action metrics, N4, and N5. Stop before delivery/N6/worker."
        )
    return "Ready for explicit layer-gated intraday run-once sequence. Stop before delivery/N6/worker."
