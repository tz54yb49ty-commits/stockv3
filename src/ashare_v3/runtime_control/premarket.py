"""Read-only N1 -> N2 -> N3 -> A1 premarket pipeline checker."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from ashare_v3.runtime_control.fast_gate import build_fast_gate_decision


PASS = "PASS"
BLOCKED = "BLOCKED"
READY = "READY"
NOT_RUN = "NOT_RUN"


def expected_premarket_run_ids(
    *,
    source_trade_date: str,
    for_trade_date: str,
    condition_run_id: str,
) -> dict[str, str]:
    subscription_run_id = f"market_data_subscription_{for_trade_date}_{condition_run_id}"
    return {
        "n1_official_daily_batch_id": f"official_daily_ingest_{source_trade_date}_v1",
        "n1_condition_source_batch_id": f"condition_source_activation_{source_trade_date}_v1",
        "n2_condition_run_id": condition_run_id,
        "n3_subscription_run_id": subscription_run_id,
        "a1_preload_run_id": (
            f"previous_day_minute_preload_{source_trade_date}_for_{for_trade_date}__{subscription_run_id}"
        ),
    }


def build_premarket_pipeline_readiness(
    *,
    source_trade_date: str,
    for_trade_date: str,
    condition_run_id: str,
    docs_dir: Path | str,
    sql_dir: Path | str,
) -> dict[str, Any]:
    docs_path = Path(docs_dir)
    sql_path = Path(sql_dir)
    run_ids = expected_premarket_run_ids(
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        condition_run_id=condition_run_id,
    )
    run_id_check = check_run_id_rules(
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        condition_run_id=condition_run_id,
        run_ids=run_ids,
    )
    rollback = build_rollback_registry_summary(
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        condition_run_id=condition_run_id,
        sql_dir=sql_path,
    )
    stages = build_premarket_stage_statuses(
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        condition_run_id=condition_run_id,
        run_ids=run_ids,
        docs_dir=docs_path,
        rollback_items=rollback["items"],
    )
    blockers: list[str] = []
    blockers.extend(run_id_check["blockers"])
    blockers.extend(rollback["blockers"])
    for stage in stages:
        if stage["status"] == BLOCKED:
            blockers.append(f"{stage['stage_id']}_blocked")
    result = BLOCKED if blockers else PASS
    return {
        "result": result,
        "stage": "premarket_pipeline_readiness",
        "layer_role": "runtime_control",
        "source_trade_date": source_trade_date,
        "for_trade_date": for_trade_date,
        "run_ids": run_ids,
        "run_id_rules": run_id_check,
        "rollback_registry": rollback,
        "missing_rollback_paths": rollback["missing_paths"],
        "stages": stages,
        "risk_summary": {
            "cross_layer_risk": "not_detected_static",
            "worker_risk": "manual_pre_execute_check_required",
            "delivery_notification_risk": "blocked_by_scope",
            "downstream_risk": "B1/N4/N5/N6_not_allowed",
        },
        "side_effects": {
            "reads_docs": True,
            "reads_sql_files": True,
            "connects_database": False,
            "writes_database": False,
            "executes_n1_n6": False,
            "executes_sql": False,
            "executes_rollback": False,
            "consumes_outbox": False,
            "updates_outbox_status": False,
            "starts_worker": False,
            "push_voice_mobile_sim_position_real_trade": False,
            "touches_old_system": False,
        },
        "blockers": blockers,
        "next_step": next_step_for_result(result),
    }


def build_premarket_fast_gate(
    *,
    source_trade_date: str,
    for_trade_date: str,
    condition_run_id: str,
    sql_dir: Path | str,
) -> dict[str, str]:
    """Return only PASS / FAIL / BLOCK for the premarket gate.

    This intentionally skips artifact lineage analysis. Use
    build_premarket_pipeline_readiness for deferred analysis reports.
    """

    sql_path = Path(sql_dir)
    run_ids = expected_premarket_run_ids(
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        condition_run_id=condition_run_id,
    )
    run_id_check = check_run_id_rules(
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        condition_run_id=condition_run_id,
        run_ids=run_ids,
    )
    rollback = build_rollback_registry_summary(
        source_trade_date=source_trade_date,
        for_trade_date=for_trade_date,
        condition_run_id=condition_run_id,
        sql_dir=sql_path,
    )
    blockers = list(run_id_check["blockers"]) + list(rollback["blockers"])
    return build_fast_gate_decision(blockers=blockers, failures=[]).to_dict()


def check_run_id_rules(
    *,
    source_trade_date: str,
    for_trade_date: str,
    condition_run_id: str,
    run_ids: Mapping[str, str],
) -> dict[str, Any]:
    blockers: list[str] = []
    condition_pattern = rf"^condition_layer_{source_trade_date}_source_{source_trade_date}_v[0-9]+$"
    if not re.match(condition_pattern, condition_run_id):
        blockers.append("condition_run_id_does_not_match_source_trade_date_rule")
    expected_subscription = f"market_data_subscription_{for_trade_date}_{condition_run_id}"
    if run_ids["n3_subscription_run_id"] != expected_subscription:
        blockers.append("subscription_run_id_rule_mismatch")
    expected_a1 = f"previous_day_minute_preload_{source_trade_date}_for_{for_trade_date}__{expected_subscription}"
    if run_ids["a1_preload_run_id"] != expected_a1:
        blockers.append("a1_preload_run_id_rule_mismatch")
    return {
        "status": BLOCKED if blockers else PASS,
        "blockers": blockers,
        "rules": {
            "condition_run_id": condition_pattern,
            "subscription_run_id": "market_data_subscription_{for_trade_date}_{condition_run_id}",
            "a1_preload_run_id": (
                "previous_day_minute_preload_{source_trade_date}_for_{for_trade_date}__{subscription_run_id}"
            ),
        },
    }


def build_rollback_registry_summary(
    *,
    source_trade_date: str,
    for_trade_date: str,
    condition_run_id: str,
    sql_dir: Path,
) -> dict[str, Any]:
    rollback_paths = {
        "n1_official_daily": f"N1_official_daily_{source_trade_date}_ingestion_rollback.sql",
        "n1_condition_source": f"N1_condition_source_{source_trade_date}_activation_rollback.sql",
        "n2_condition_layer": n2_rollback_filename(source_trade_date, condition_run_id),
        "n3_subscription": f"N3_subscription_{for_trade_date}_rollback.sql",
        "a1_previous_day_preload": f"N3_A1_previous_day_minute_{for_trade_date}_rollback.sql",
    }
    items: list[dict[str, Any]] = []
    missing_paths: list[str] = []
    blockers: list[str] = []
    for stage_id, filename in rollback_paths.items():
        path = sql_dir / filename
        exists = path.exists()
        hard_fail = rollback_has_hard_fail_before_delete(path) if exists else False
        relative_path = f"sql/{filename}"
        if not exists:
            missing_paths.append(relative_path)
            blockers.append(f"missing_rollback:{relative_path}")
        items.append(
            {
                "stage_id": stage_id,
                "rollback_sql_path": relative_path,
                "exists": exists,
                "hard_fail_before_delete": hard_fail,
                "executes_rollback": False,
            }
        )
    return {
        "status": BLOCKED if blockers else PASS,
        "items": items,
        "missing_paths": missing_paths,
        "blockers": blockers,
    }


def n2_rollback_filename(source_trade_date: str, condition_run_id: str) -> str:
    match = re.match(rf"^condition_layer_{source_trade_date}_source_{source_trade_date}_v([0-9]+)$", condition_run_id)
    if match and match.group(1) == "6":
        return f"N2_level_score_{source_trade_date}_v6_rollback.sql"
    return f"N2_condition_layer_{source_trade_date}_rollback.sql"


def rollback_has_hard_fail_before_delete(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    first_delete = text.upper().find("DELETE")
    first_raise = text.upper().find("RAISE EXCEPTION")
    return first_raise >= 0 and (first_delete < 0 or first_raise < first_delete)


def build_premarket_stage_statuses(
    *,
    source_trade_date: str,
    for_trade_date: str,
    condition_run_id: str,
    run_ids: Mapping[str, str],
    docs_dir: Path,
    rollback_items: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rollback_by_stage = {item["stage_id"]: item for item in rollback_items}
    return [
        build_stage(
            stage_id="n1",
            title="N1 official daily + condition source",
            layer_role="N1_ingestion",
            report_patterns=(
                f"N1_official_daily_{source_trade_date}_ingestion_execute_report.json",
                f"N1_official_daily_{source_trade_date}_ingestion_execute_preflight.json",
                f"N1_condition_source_{source_trade_date}_activation_execute_report.json",
                f"N1_condition_source_{source_trade_date}_activation_execute_preflight.json",
            ),
            docs_dir=docs_dir,
            rollback_items=(rollback_by_stage["n1_official_daily"], rollback_by_stage["n1_condition_source"]),
        ),
        build_stage(
            stage_id="n2",
            title="N2 condition layer active",
            layer_role="N2_condition",
            report_patterns=n2_report_patterns(source_trade_date, condition_run_id),
            docs_dir=docs_dir,
            rollback_items=(rollback_by_stage["n2_condition_layer"],),
            run_id=condition_run_id,
        ),
        build_stage(
            stage_id="n3",
            title="N3 market data subscription",
            layer_role="N3_market_data",
            report_patterns=(
                f"N3_subscription_{for_trade_date}_execute_report.json",
                f"N3_subscription_{for_trade_date}_execute_preflight.json",
                "N3_latest_N2_v6_rebuild_preflight.json",
            ),
            docs_dir=docs_dir,
            rollback_items=(rollback_by_stage["n3_subscription"],),
            run_id=run_ids["n3_subscription_run_id"],
        ),
        build_stage(
            stage_id="a1",
            title="A1 previous-day minute preload",
            layer_role="N3_market_data",
            report_patterns=(
                f"N3_A1_previous_day_minute_{for_trade_date}_execute_report.json",
                f"N3_A1_previous_day_minute_{for_trade_date}_execute_preflight.json",
            ),
            docs_dir=docs_dir,
            rollback_items=(rollback_by_stage["a1_previous_day_preload"],),
            run_id=run_ids["a1_preload_run_id"],
        ),
    ]


def n2_report_patterns(source_trade_date: str, condition_run_id: str) -> tuple[str, ...]:
    if condition_run_id.endswith("_v6"):
        return (
            f"N2_level_score_{source_trade_date}_v6_execute_report.json",
            f"N2_level_score_{source_trade_date}_v6_post_review.json",
            f"N2_level_score_{source_trade_date}_v6_execute_preflight.json",
        )
    return (
        f"N2_condition_layer_{source_trade_date}_execute_report.json",
        f"N2_condition_layer_{source_trade_date}_execute_preflight.json",
    )


def build_stage(
    *,
    stage_id: str,
    title: str,
    layer_role: str,
    report_patterns: tuple[str, ...],
    docs_dir: Path,
    rollback_items: tuple[Mapping[str, Any], ...],
    run_id: str = "",
) -> dict[str, Any]:
    artifact = first_existing_artifact(docs_dir, report_patterns)
    rollback_missing = [item["rollback_sql_path"] for item in rollback_items if not item["exists"]]
    if rollback_missing:
        status = BLOCKED
    elif artifact is None:
        status = NOT_RUN
    else:
        status = artifact_status(artifact)
    return {
        "stage_id": stage_id,
        "title": title,
        "layer_role": layer_role,
        "status": status,
        "run_id": run_id,
        "artifact_path": f"docs/{artifact.name}" if artifact else "",
        "rollback_paths": [item["rollback_sql_path"] for item in rollback_items],
        "missing_rollback_paths": rollback_missing,
        "quality": extract_quality_from_artifact(artifact) if artifact else {"p0": 0, "p1": 0, "p2": 0},
    }


def first_existing_artifact(docs_dir: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        path = docs_dir / pattern
        if path.exists():
            return path
    return None


def artifact_status(path: Path) -> str:
    data = load_json(path)
    if data is None:
        return READY
    if is_blocked(data) or extract_quality_from_mapping(data)["p0"] > 0:
        return BLOCKED
    status_text = " ".join(str(data.get(key) or "") for key in ("result", "status", "stage_status")).lower()
    if "passed" in status_text or "pass" in status_text or "executed" in status_text:
        return PASS
    if "preflight" in status_text or path.name.endswith("_preflight.json"):
        return READY
    return READY


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_blocked(data: Mapping[str, Any]) -> bool:
    if data.get("blocked") is True:
        return True
    text = " ".join(str(data.get(key) or "") for key in ("result", "status", "stage_status")).lower()
    return "blocked" in text


def extract_quality_from_artifact(path: Path) -> dict[str, int]:
    data = load_json(path)
    return extract_quality_from_mapping(data or {})


def extract_quality_from_mapping(data: Mapping[str, Any]) -> dict[str, int]:
    quality = data.get("quality") if isinstance(data.get("quality"), Mapping) else data
    return {
        "p0": int(quality.get("p0_count") or quality.get("p0") or 0),
        "p1": int(quality.get("p1_count") or quality.get("p1") or 0),
        "p2": int(quality.get("p2_count") or quality.get("p2") or 0),
    }


def next_step_for_result(result: str) -> str:
    if result == PASS:
        return (
            "Ready for explicit layer-gated execution sequence: N1_ingestion -> N2_condition -> "
            "N3_market_data subscription -> N3_market_data A1. Stop before B1/N4/N5/N6."
        )
    return "Resolve missing rollback paths, run_id rule mismatches, or static blockers before any execute gate."
