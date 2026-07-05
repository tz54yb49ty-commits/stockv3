"""Read-only runtime dashboard artifact detection.

The detector reads only JSON files already present under docs/. It does not
open database connections, execute commands, consume outbox rows, or mutate
runtime/N1-N6 state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

from ashare_v3.runtime_control.pipeline import (
    BLOCKED,
    FAILED,
    NOT_RUN,
    PASS,
    READY,
    WAIT_MANUAL_CONFIRM,
    RuntimePipelineRun,
    normalize_quality,
)


STAGE_PATTERNS: dict[str, tuple[str, ...]] = {
    "calendar": (
        "N1_trade_calendar_{trade_date}_patch_preflight.json",
    ),
    "n1_official_daily": (
        "N1_official_daily_{trade_date}_v2_ingestion_execute_report.json",
        "N1_official_daily_{trade_date}_ingestion_execute_report.json",
        "N1_official_daily_*_v2_ingestion_execute_report.json",
        "N1_official_daily_*_ingestion_execute_report.json",
        "N1_official_daily_{trade_date}_v2_ingestion_execute_preflight.json",
        "N1_official_daily_{trade_date}_ingestion_execute_preflight.json",
        "N1_official_daily_*_v2_ingestion_execute_preflight.json",
        "N1_official_daily_*_ingestion_execute_preflight.json",
    ),
    "n1_condition_source": (
        "N1_condition_source_{trade_date}_v2_activation_execute_report.json",
        "N1_condition_source_{trade_date}_activation_execute_report.json",
        "N1_condition_source_*_v2_activation_execute_report.json",
        "N1_condition_source_*_activation_execute_report.json",
        "N1_condition_source_{trade_date}_v2_activation_preflight.json",
        "N1_condition_source_{trade_date}_activation_preflight.json",
        "N1_condition_source_*_v2_activation_preflight.json",
        "N1_condition_source_*_activation_preflight.json",
    ),
    "n2_condition_layer": (
        "N2_condition_layer_{trade_date}_final_execute_report.json",
        "N2_condition_layer_*_final_execute_report.json",
        "N2_condition_layer_{trade_date}_execute_preflight.json",
        "N2_condition_layer_*_execute_preflight.json",
    ),
    "n2_condition_layer_active": (
        "N2_condition_layer_*_to_{trade_date}_execute_report.json",
        "N2_condition_layer_*_to_{trade_date}_execute_preflight.json",
    ),
    "n3_subscription": (
        "N3_subscription_{trade_date}_execute_report.json",
        "N3_subscription_{trade_date}_execute_preflight.json",
        "N3_subscription_{trade_date}_dry_run_report.json",
    ),
    "n3_a1_previous_day_preload": (
        "N3_A1_previous_day_minute_{trade_date}_execute_report.json",
        "N3_A1_previous_day_minute_{trade_date}_execute_preflight.json",
    ),
    "n3_b1_live3_snapshot": (
        "N3_B1_realtime_snapshot_{trade_date}_live3_outbox_execute_report.json",
        "N3_B1_realtime_snapshot_{trade_date}_live3_outbox_execute_preflight.json",
    ),
    "n3_c1_today_minute": (
        "N3_C1_today_minute_bar_1m_{trade_date}_until_1105_execute_report.json",
        "N3_C1_today_minute_bar_1m_{trade_date}_execute_report.json",
    ),
    "n3_action_confirmation_projection": (
        "N3_action_confirmation_projection_writer_execute_report.json",
        "N3_action_confirmation_projection_writer_execute_preflight.json",
        "N3_action_confirmation_projection_writer_dry_run_report.json",
    ),
    "n4_action_confirmation_metric_execute": (
        "N4_action_confirmation_metric_business_execute_report.json",
        "N4_action_confirmation_metric_business_execute_final_preflight.json",
        "N4_action_confirmation_metric_dry_run_report.json",
    ),
    "n5_action_confirmation_metric_execute": (
        "N5_{trade_date}_action_confirmation_metric_execute_summary.json",
        "N5_{trade_date}_action_confirmation_metric_execute_report.json",
        "N5_{trade_date}_action_confirmation_metric_execute_preflight.json",
        "N5_{trade_date}_action_confirmation_metric_consumption_dry_run_report.json",
    ),
    "n6_shadow_projection": (
        "runtime_action_confirmation_chain_{trade_date}_closure.json",
        "N6_{trade_date}_action_confirmation_projection_execute_report.json",
        "N6_{trade_date}_action_confirmation_projection_dry_run_report.json",
        "N6_{trade_date}_action_confirmation_projection_preflight.json",
    ),
    "a1_previous_day_preload": (
        "N3_A1_previous_day_minute_preload_execute_report.json",
        "N3_A1_previous_day_minute_{trade_date}_execute_report.json",
        "N3_A1_previous_day_minute_{trade_date}_execute_preflight.json",
    ),
    "b1_realtime_snapshot_fact_only": (
        "N3_B1_realtime_daily_snapshot_execute_report.json",
        "N3_B1_realtime_snapshot_{trade_date}_execute_report.json",
        "N3_B1_realtime_snapshot_{trade_date}_execute_preflight.json",
        "N3_B1_realtime_snapshot_{trade_date}_dry_run_report.json",
    ),
}


RUN_ID_KEYS = (
    "run_id",
    "execute_run_id",
    "market_data_run_id",
    "snapshot_run_id",
    "preload_run_id",
    "today_minute_run_id",
    "projection_run_id",
    "user_projection_run_id",
    "action_run_id",
)
SOURCE_BATCH_KEYS = (
    "source_batch_id",
    "source_version",
)
ROLLBACK_KEYS = (
    "rollback_path",
    "rollback_sql_path",
    "rollback_sql",
)
STATUS_KEYS = (
    "result",
    "status",
    "stage_status",
)


@dataclass(frozen=True)
class StageArtifactDetection:
    stage_id: str
    status: str
    artifact_status: str
    report_path: str
    quality: dict[str, int]
    run_id: str = ""
    source_batch_id: str = ""
    rows_summary: dict[str, object] | None = None
    rollback_path: str = ""
    details: str = ""


def detect_stage_artifact(
    *,
    stage_id: str,
    trade_date: str,
    docs_dir: Path | str,
) -> StageArtifactDetection | None:
    docs_path = Path(docs_dir)
    for path in candidate_artifact_paths(stage_id=stage_id, trade_date=trade_date, docs_dir=docs_path):
        data = load_json(path)
        if data is None or not artifact_matches_trade_date(data, trade_date, stage_id=stage_id):
            continue
        stage_data = stage_specific_artifact_data(data, stage_id)
        relative_path = f"docs/{path.name}"
        quality = extract_quality(stage_data)
        status = detect_status(data=stage_data, path=path, quality=quality)
        return StageArtifactDetection(
            stage_id=stage_id,
            status=status,
            artifact_status=status,
            report_path=relative_path,
            quality=quality,
            run_id=extract_first_string(stage_data, RUN_ID_KEYS),
            source_batch_id=extract_first_string(stage_data, SOURCE_BATCH_KEYS),
            rows_summary=extract_rows_summary(stage_data),
            rollback_path=extract_first_string(stage_data, ROLLBACK_KEYS),
            details=f"Derived from {relative_path}",
        )
    return None


def apply_artifact_detections(
    run: RuntimePipelineRun,
    *,
    docs_dir: Path | str,
) -> RuntimePipelineRun:
    detected_stages = []
    for stage in run.stages:
        detection = detect_stage_artifact(stage_id=stage.stage_id, trade_date=run.trade_date, docs_dir=docs_dir)
        if detection is None:
            detected_stages.append(
                replace(
                    stage,
                    status=WAIT_MANUAL_CONFIRM,
                    artifact_status=NOT_RUN,
                    artifact_path="",
                    rows_summary={},
                    details="No docs/*.json artifact found; waiting for manual confirmation.",
                )
            )
            continue
        detected_stages.append(
            replace(
                stage,
                status=detection.status,
                report_path=detection.report_path,
                quality=detection.quality,
                details=detection.details,
                artifact_status=detection.artifact_status,
                artifact_path=detection.report_path,
                artifact_rollback_path=detection.rollback_path,
                run_id=detection.run_id,
                source_batch_id=detection.source_batch_id,
                rows_summary=detection.rows_summary or {},
            )
        )

    return replace(
        run,
        status=summarize_detected_run_status(stage.status for stage in detected_stages),
        stages=tuple(detected_stages),
    )


def candidate_artifact_paths(*, stage_id: str, trade_date: str, docs_dir: Path) -> list[Path]:
    if not docs_dir.exists() or not docs_dir.is_dir():
        return []
    paths: list[Path] = []
    seen: set[Path] = set()
    for raw_pattern in STAGE_PATTERNS.get(stage_id, ()):
        pattern = raw_pattern.format(trade_date=trade_date)
        candidates = sorted(docs_dir.glob(pattern), reverse="*" in pattern)
        for path in candidates:
            if path in seen or path.suffix != ".json" or path.parent != docs_dir:
                continue
            seen.add(path)
            paths.append(path)
    return paths


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def artifact_matches_trade_date(data: dict[str, Any], trade_date: str, *, stage_id: str) -> bool:
    for_trade_date = data.get("for_trade_date")
    if isinstance(for_trade_date, str):
        return for_trade_date == trade_date

    artifact_trade_date = data.get("trade_date")
    if isinstance(artifact_trade_date, str):
        if stage_id in ("n1_official_daily", "n1_condition_source"):
            return True
        return artifact_trade_date == trade_date

    return True


def detect_status(*, data: dict[str, Any], path: Path, quality: dict[str, int]) -> str:
    if is_blocked(data):
        return BLOCKED
    if quality["p0_count"] > 0:
        return BLOCKED
    status_text = " ".join(extract_status_strings(data)).lower()
    if any(token in status_text for token in ("failed", "failure", "error")):
        return FAILED
    if "blocked" in status_text:
        return BLOCKED
    if "preflight_pass" in status_text or path.name.endswith("_preflight.json"):
        return READY
    if "chain_closure_pass" in status_text:
        return PASS
    if "executed" in status_text:
        return PASS
    if "execute_pass" in status_text:
        return PASS
    if "passed_active" in status_text:
        return PASS
    if status_text.strip() == "passed":
        return PASS
    if "passed" in status_text and "execute" in path.name:
        return PASS
    if "execute_report" in path.name or "final_execute_report" in path.name:
        return PASS
    preflight = data.get("preflight")
    if isinstance(preflight, dict) and preflight.get("execute_allowed") is True:
        return READY
    return WAIT_MANUAL_CONFIRM


def is_blocked(data: dict[str, Any]) -> bool:
    if data.get("blocked") is True:
        return True
    for key in ("blockers", "blocked_reasons"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return True
    preflight = data.get("preflight")
    if isinstance(preflight, dict):
        reasons = preflight.get("blocked_reasons")
        if isinstance(reasons, list) and reasons:
            return True
    return False


def extract_status_strings(data: dict[str, Any]) -> list[str]:
    strings: list[str] = []
    for item in walk_json(data):
        if not isinstance(item, dict):
            continue
        for key in STATUS_KEYS:
            value = item.get(key)
            if isinstance(value, str):
                strings.append(value)
        value = item.get("run_status")
        if isinstance(value, str):
            strings.append(value)
    return strings


def extract_quality(data: dict[str, Any]) -> dict[str, int]:
    direct_candidates = (
        data.get("quality"),
        data.get("quality_summary"),
        nested_dict(data, ("preflight", "quality_summary")),
        nested_dict(data, ("dry_run_summary", "quality")),
    )
    for candidate in direct_candidates:
        if has_quality_counts(candidate):
            return normalize_quality(candidate)

    for item in walk_json(data.get("post_execute", {})):
        if has_quality_counts(item):
            return normalize_quality(item)

    for item in walk_json(data):
        if has_quality_counts(item):
            return normalize_quality(item)

    quality = data.get("quality")
    if isinstance(quality, dict):
        items = quality.get("items")
        if isinstance(items, list):
            counts = {"p0_count": 0, "p1_count": 0, "p2_count": 0}
            for item in items:
                if not isinstance(item, dict):
                    continue
                if str(item.get("status", "")).lower() == "passed":
                    continue
                severity = str(item.get("severity", "")).upper()
                if severity in ("P0", "P1", "P2"):
                    counts[f"{severity.lower()}_count"] += 1
            return counts

    return {"p0_count": 0, "p1_count": 0, "p2_count": 0}


def has_quality_counts(value: Any) -> bool:
    return isinstance(value, dict) and any(key in value for key in ("p0_count", "p1_count", "p2_count"))


def extract_rows_summary(data: dict[str, Any]) -> dict[str, object]:
    event_counts = nested_dict(data, ("output_event_plan_summary", "by_event_type"))
    if isinstance(event_counts, dict):
        summary = json_safe_dict(event_counts)
        inserted_counts = data.get("inserted_counts")
        if isinstance(inserted_counts, dict):
            summary.update(json_safe_dict(inserted_counts))
        return summary

    stage_rows = data.get("rows")
    if isinstance(stage_rows, dict):
        return json_safe_dict(stage_rows)

    for key in ("write_counts", "inserted_counts", "write_result", "actual_row_counts", "row_counts", "planned_row_counts"):
        value = data.get(key)
        if isinstance(value, dict):
            return json_safe_dict(value)

    expected = nested_dict(data, ("preflight", "expected_row_counts"))
    if isinstance(expected, dict):
        return json_safe_dict(expected)

    return {}


def stage_specific_artifact_data(data: dict[str, Any], stage_id: str) -> dict[str, Any]:
    stage_results = data.get("stage_results")
    if isinstance(stage_results, dict):
        stage_data = stage_results.get(stage_id)
        if isinstance(stage_data, dict):
            return stage_data
    return data


def extract_first_string(data: dict[str, Any], keys: Iterable[str]) -> str:
    key_set = set(keys)
    for item in walk_json(data):
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = item.get(key)
            if key in key_set and isinstance(value, str) and value:
                return value
    return ""


def nested_dict(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any] | None:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, dict) else None


def walk_json(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def json_safe_dict(value: dict[str, Any]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[str(key)] = item
        elif isinstance(item, dict):
            result[str(key)] = json_safe_dict(item)
        elif isinstance(item, list):
            result[str(key)] = [
                element
                if isinstance(element, (str, int, float, bool)) or element is None
                else str(element)
                for element in item
            ]
        else:
            result[str(key)] = str(item)
    return result


def summarize_detected_run_status(statuses: Iterable[str]) -> str:
    status_tuple = tuple(statuses)
    if any(status == FAILED for status in status_tuple):
        return FAILED
    if any(status == BLOCKED for status in status_tuple):
        return BLOCKED
    if any(status == WAIT_MANUAL_CONFIRM for status in status_tuple):
        return WAIT_MANUAL_CONFIRM
    if status_tuple and all(status == PASS for status in status_tuple):
        return PASS
    if any(status == READY for status in status_tuple):
        return READY
    return WAIT_MANUAL_CONFIRM
