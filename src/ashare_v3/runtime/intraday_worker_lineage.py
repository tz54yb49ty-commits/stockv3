"""Runtime lineage config for N3/N4 intraday proof pollers."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from typing import Any, Mapping


ASIA_SHANGHAI = timezone(timedelta(hours=8))
DEFAULT_LINEAGE_CONFIG_PATH = "docs/runtime/current_intraday_worker_lineage.json"
REQUIRED_FIELDS = (
    "enabled",
    "for_trade_date",
    "source_trade_date",
    "n2_run_id",
    "subscription_run_id",
    "a1_preload_run_id",
    "n4_context_run_id",
    "updated_by",
    "updated_at",
    "source_status_path",
    "source_oneshot_report_path",
)
STALE_LINEAGE_BLOCKER_CODE = "BLOCKED_STALE_INTRADAY_WORKER_LINEAGE"
LINEAGE_REFRESH_PASS = "LINEAGE_REFRESH_PASS"
LINEAGE_REFRESH_READY = "LINEAGE_REFRESH_READY"
LINEAGE_REFRESH_NOOP_ALREADY_CURRENT = "LINEAGE_REFRESH_NOOP_ALREADY_CURRENT"
LINEAGE_REFRESH_BLOCKED_FASTLANE_NOT_PASS = "BLOCKED_FASTLANE_NOT_PASS"
LINEAGE_SEMANTIC_FIELDS = (
    "enabled",
    "for_trade_date",
    "source_trade_date",
    "n2_run_id",
    "subscription_run_id",
    "a1_preload_run_id",
    "n4_context_run_id",
    "source_status_path",
    "source_oneshot_report_path",
)


class LineageConfigError(ValueError):
    """Raised when intraday worker lineage config is unsafe."""


def condition_run_id_for(source_trade_date: str, for_trade_date: str) -> str:
    return f"condition_layer_{source_trade_date}_source_{source_trade_date}_for_{for_trade_date}_v1"


def subscription_run_id_for(source_trade_date: str, for_trade_date: str) -> str:
    return f"market_data_subscription_{for_trade_date}_{condition_run_id_for(source_trade_date, for_trade_date)}"


def preload_run_id_for(source_trade_date: str, for_trade_date: str) -> str:
    subscription_run_id = subscription_run_id_for(source_trade_date, for_trade_date)
    return f"previous_day_minute_preload_{source_trade_date}_for_{for_trade_date}__{subscription_run_id}"


def n4_context_run_id_for(source_trade_date: str, for_trade_date: str) -> str:
    return f"trigger_context_snapshot_{for_trade_date}_{condition_run_id_for(source_trade_date, for_trade_date)}__atomic_rule_v1"


def load_intraday_worker_lineage_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LineageConfigError(f"lineage config missing: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise LineageConfigError(f"lineage config malformed json: {config_path}") from exc
    if not isinstance(payload, dict):
        raise LineageConfigError("lineage config must be a JSON object")
    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        raise LineageConfigError(f"lineage config missing fields: {','.join(missing)}")
    if payload.get("enabled") is not True:
        raise LineageConfigError("lineage config disabled")
    _validate_lineage_payload(payload)
    _validate_latest_attempted_fastlane(config_path, payload)
    return payload


def lineage_report_fields(path: str | Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lineage_config_path": str(path),
        "lineage_config_used": True,
        "effective_for_trade_date": str(payload["for_trade_date"]),
        "effective_source_trade_date": str(payload["source_trade_date"]),
        "effective_lineage_ids": {
            "n2_run_id": str(payload["n2_run_id"]),
            "subscription_run_id": str(payload["subscription_run_id"]),
            "a1_preload_run_id": str(payload["a1_preload_run_id"]),
            "n4_context_run_id": str(payload["n4_context_run_id"]),
        },
    }


def no_lineage_config_report_fields() -> dict[str, Any]:
    return {
        "lineage_config_path": "",
        "lineage_config_used": False,
        "effective_for_trade_date": "",
        "effective_source_trade_date": "",
        "effective_lineage_ids": {},
    }


def write_intraday_worker_lineage_config_after_fastlane_pass(
    *,
    docs_root: Path,
    docs_dir: Path,
    updated_by: str = "post_close_fastlane",
) -> Path | None:
    status_path = docs_dir / "00_status.json"
    report_path = docs_dir / "01_oneshot_execute_report.json"
    status = _load_json(status_path)
    report = _load_json(report_path)
    if not status or not report:
        return None
    if status.get("result") != "EXECUTE_PASS" or report.get("result") != "EXECUTE_PASS":
        return None
    try:
        payload = _lineage_payload_from_fastlane_pass(
            docs_dir=docs_dir,
            status_path=status_path,
            report_path=report_path,
            status=status,
            report=report,
            updated_by=updated_by,
        )
    except LineageConfigError:
        return None
    _validate_lineage_payload(payload)
    config_path = docs_root.parent / "runtime" / "current_intraday_worker_lineage.json"
    existing_payload = _load_json(config_path)
    if existing_payload and _lineage_semantic_payload_matches(existing_payload, payload):
        return config_path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(config_path)
    return config_path


def build_intraday_worker_lineage_refresh_report(
    *,
    docs_root: Path,
    docs_dir: Path,
    updated_by: str = "runtime_control_status_repair",
    execute: bool = False,
) -> dict[str, Any]:
    """Build and optionally execute a repair-safe active lineage refresh report."""

    status_path = docs_dir / "00_status.json"
    report_path = docs_dir / "01_oneshot_execute_report.json"
    config_path = docs_root.parent / "runtime" / "current_intraday_worker_lineage.json"
    base_report: dict[str, Any] = {
        "check": "intraday_worker_lineage_refresh_after_repair",
        "layer_role": "runtime_control",
        "docs_dir": str(docs_dir),
        "lineage_config_path": str(config_path),
        "execute": bool(execute),
        "writes_database": False,
        "runtime_executed": False,
        "launchd_mutated": False,
        "event_ledger_touched": False,
    }

    status = _load_json(status_path)
    oneshot_report = _load_json(report_path)
    if not status or not oneshot_report:
        return {
            **base_report,
            "result": LINEAGE_REFRESH_BLOCKED_FASTLANE_NOT_PASS,
            "blocked_reason": "fastlane_status_or_report_missing",
        }
    base_report.update(
        {
            "for_trade_date": str(status.get("for_trade_date") or ""),
            "source_trade_date": str(status.get("source_trade_date") or ""),
            "status_result": status.get("result"),
            "oneshot_result": oneshot_report.get("result"),
        }
    )
    if status.get("result") != "EXECUTE_PASS" or oneshot_report.get("result") != "EXECUTE_PASS":
        return {
            **base_report,
            "result": LINEAGE_REFRESH_BLOCKED_FASTLANE_NOT_PASS,
            "blocked_reason": "fastlane_not_execute_pass",
        }

    try:
        expected_payload = _lineage_payload_from_fastlane_pass(
            docs_dir=docs_dir,
            status_path=status_path,
            report_path=report_path,
            status=status,
            report=oneshot_report,
            updated_by=updated_by,
        )
    except LineageConfigError as exc:
        return {
            **base_report,
            "result": "BLOCKED_FASTLANE_LINEAGE_INVALID",
            "blocked_reason": str(exc),
        }

    existing_payload = _load_json(config_path)
    if existing_payload and _lineage_semantic_payload_matches(existing_payload, expected_payload):
        return {
            **base_report,
            "result": LINEAGE_REFRESH_NOOP_ALREADY_CURRENT,
            "lineage_written": False,
            "lineage_semantic_already_current": True,
        }
    if not execute:
        return {
            **base_report,
            "result": LINEAGE_REFRESH_READY,
            "lineage_written": False,
            "lineage_semantic_already_current": False,
        }

    written_path = write_intraday_worker_lineage_config_after_fastlane_pass(
        docs_root=docs_root,
        docs_dir=docs_dir,
        updated_by=updated_by,
    )
    if written_path is None:
        return {
            **base_report,
            "result": "BLOCKED_LINEAGE_REFRESH_WRITE_FAILED",
            "lineage_written": False,
        }
    return {
        **base_report,
        "result": LINEAGE_REFRESH_PASS,
        "lineage_written": True,
        "lineage_semantic_already_current": False,
    }


def _lineage_payload_from_fastlane_pass(
    *,
    docs_dir: Path,
    status_path: Path,
    report_path: Path,
    status: Mapping[str, Any],
    report: Mapping[str, Any],
    updated_by: str,
) -> dict[str, Any]:
    for_trade_date = str(status.get("for_trade_date") or "")
    source_trade_date = str(status.get("source_trade_date") or "")
    if for_trade_date != docs_dir.name:
        raise LineageConfigError("fastlane status for_trade_date does not match docs dir")
    if not _is_yyyymmdd(source_trade_date):
        raise LineageConfigError("fastlane source_trade_date must be YYYYMMDD")
    run_ids = report.get("run_ids") if isinstance(report.get("run_ids"), Mapping) else {}
    return {
        "enabled": True,
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "n2_run_id": str(run_ids.get("condition_run_id") or condition_run_id_for(source_trade_date, for_trade_date)),
        "subscription_run_id": str(run_ids.get("subscription_run_id") or subscription_run_id_for(source_trade_date, for_trade_date)),
        "a1_preload_run_id": str(run_ids.get("preload_run_id") or preload_run_id_for(source_trade_date, for_trade_date)),
        "n4_context_run_id": n4_context_run_id_for(source_trade_date, for_trade_date),
        "updated_by": updated_by,
        "updated_at": datetime.now(ASIA_SHANGHAI).isoformat(),
        "source_status_path": str(status_path),
        "source_oneshot_report_path": str(report_path),
    }


def _lineage_semantic_payload_matches(existing: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(existing.get(field) == expected.get(field) for field in LINEAGE_SEMANTIC_FIELDS)


def _validate_lineage_payload(payload: Mapping[str, Any]) -> None:
    for key in ("for_trade_date", "source_trade_date"):
        if not _is_yyyymmdd(str(payload.get(key) or "")):
            raise LineageConfigError(f"{key} must be YYYYMMDD")
    for key in ("n2_run_id", "subscription_run_id", "a1_preload_run_id", "n4_context_run_id"):
        if not str(payload.get(key) or ""):
            raise LineageConfigError(f"{key} is required")
    source_trade_date = str(payload["source_trade_date"])
    for_trade_date = str(payload["for_trade_date"])
    expected_condition = condition_run_id_for(source_trade_date, for_trade_date)
    if str(payload["n2_run_id"]) != expected_condition:
        raise LineageConfigError("n2_run_id date lineage mismatch")
    if str(payload["subscription_run_id"]) != subscription_run_id_for(source_trade_date, for_trade_date):
        raise LineageConfigError("subscription_run_id date lineage mismatch")
    if str(payload["a1_preload_run_id"]) != preload_run_id_for(source_trade_date, for_trade_date):
        raise LineageConfigError("a1_preload_run_id date lineage mismatch")
    if str(payload["n4_context_run_id"]) != n4_context_run_id_for(source_trade_date, for_trade_date):
        raise LineageConfigError("n4_context_run_id date lineage mismatch")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _validate_latest_attempted_fastlane(config_path: Path, payload: Mapping[str, Any]) -> None:
    docs_root = _docs_root_for_lineage_config(config_path)
    latest_path = docs_root / "post_close_fastlane" / "latest"
    if not latest_path.exists():
        raise LineageConfigError(f"latest attempted Fast Lane pointer missing: {latest_path}")
    try:
        latest_dir = latest_path.resolve(strict=True)
    except OSError as exc:
        raise LineageConfigError(f"latest attempted Fast Lane pointer invalid: {latest_path}") from exc
    latest_for_trade_date = latest_dir.name
    if not _is_yyyymmdd(latest_for_trade_date):
        raise LineageConfigError(f"latest attempted Fast Lane date invalid: {latest_for_trade_date}")
    status_path = latest_dir / "00_status.json"
    status = _load_json(status_path)
    if not status:
        raise LineageConfigError(f"latest attempted Fast Lane status missing or malformed: {status_path}")
    status_for_trade_date = str(status.get("for_trade_date") or "")
    if status_for_trade_date != latest_for_trade_date:
        raise LineageConfigError(
            "latest attempted Fast Lane status date mismatch: "
            f"latest_attempted_for_trade_date={latest_for_trade_date} "
            f"status_for_trade_date={status_for_trade_date}"
        )
    active_for_trade_date = str(payload["for_trade_date"])
    if latest_for_trade_date > active_for_trade_date and status.get("result") != "EXECUTE_PASS":
        raise LineageConfigError(
            f"{STALE_LINEAGE_BLOCKER_CODE}:"
            f"active_for_trade_date={active_for_trade_date};"
            f"latest_attempted_for_trade_date={latest_for_trade_date};"
            f"latest_result={status.get('result')};"
            f"latest_failed_step_id={status.get('failed_step_id')}"
        )


def _docs_root_for_lineage_config(config_path: Path) -> Path:
    if config_path.parent.name == "runtime":
        return config_path.parent.parent
    return config_path.parent


def _is_yyyymmdd(value: str) -> bool:
    return len(value) == 8 and value.isdigit()
