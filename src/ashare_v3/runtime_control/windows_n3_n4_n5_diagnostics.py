"""Atomic local diagnostics for the Windows N3/N4/N5 runtime."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any

from ashare_v3.action.event_factory import json_safe_value
from ashare_v3.runtime_control.windows_n3_n4_n5_memory import (
    ASSET_KINDS,
    WindowsN3N4N5FinalizeResult,
    WindowsN3N4N5RuntimeSummary,
    WindowsStateBridgeSnapshot,
)


DIAGNOSTIC_SCHEMA_VERSION = "windows_n3_n4_n5_diagnostics_v1"
DEFAULT_DIAGNOSTIC_ROOT = Path(
    r"C:\Users\Public\Documents\AshareV3-evidence\windows-n3n4n5-runtime"
)
_DSN_PATTERN = re.compile(r"(?i)(postgres(?:ql)?://)[^\s@]+@")
_PASSWORD_PATTERN = re.compile(r"(?i)(password\s*[=:]\s*)[^\s|;]+")


class WindowsN3N4N5DiagnosticWriter:
    """Write one immutable run directory without touching business state."""

    def __init__(
        self,
        *,
        for_trade_date: str,
        started_at: datetime,
        root: Path | str = DEFAULT_DIAGNOSTIC_ROOT,
        process_id: int | None = None,
    ) -> None:
        if len(for_trade_date) != 8 or not for_trade_date.isdigit():
            raise ValueError("for_trade_date must be YYYYMMDD")
        pid = os.getpid() if process_id is None else process_id
        if type(pid) is not int or pid <= 0:
            raise ValueError("process_id must be a positive integer")
        self.for_trade_date = for_trade_date
        self.started_at = started_at
        self.process_id = pid
        self.run_directory = (
            Path(root)
            / for_trade_date
            / f"{started_at:%Y%m%dT%H%M%S}-pid{pid}"
        )
        self.run_directory.mkdir(parents=True, exist_ok=False)
        self._last_confirmation_minute_index = -1

    def write_confirmation_latest(
        self,
        snapshot: WindowsStateBridgeSnapshot,
        summary: WindowsN3N4N5RuntimeSummary,
    ) -> bool:
        minute_index = summary.completed_minute_index
        if minute_index <= 0:
            return False
        if minute_index <= self._last_confirmation_minute_index:
            return False
        self._last_confirmation_minute_index = minute_index
        payload = {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "artifact_type": "confirmation_latest",
            "for_trade_date": self.for_trade_date,
            "started_at": self.started_at,
            "process_id": self.process_id,
            "generated_at": snapshot.generated_at,
            "completed_minute_index": minute_index,
            "channels": _channel_payload(snapshot, summary),
            "diagnostic": snapshot.diagnostic,
        }
        _atomic_replace_json(
            self.run_directory / "confirmation-latest.json",
            _sanitized_json_value(payload),
        )
        return True

    def write_session_final(
        self,
        result: WindowsN3N4N5FinalizeResult,
        summary: WindowsN3N4N5RuntimeSummary,
    ) -> Path:
        channels = {}
        for kind in ASSET_KINDS:
            events = result.action_events[kind]
            channels[kind] = {
                "pre_finalize_active_count": len(
                    result.pre_finalize_snapshots[kind].active
                ),
                "pre_finalize_episodes": _episode_rows(
                    result.pre_finalize_snapshots[kind]
                ),
                "window_expired_event_count": sum(
                    1
                    for event in events
                    if event.event_type == "ActionSkipped"
                    and event.payload_json.get("skipped_reason")
                    == "window_expired"
                ),
                "emitted_event_counts": dict(
                    Counter(event.event_type for event in events)
                ),
                "post_finalize_active_count": len(
                    result.post_finalize_snapshots[kind].active
                ),
                "post_finalize_version": (
                    result.post_finalize_snapshots[kind].version
                ),
            }
        payload = {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "artifact_type": "session_final",
            "for_trade_date": self.for_trade_date,
            "started_at": self.started_at,
            "process_id": self.process_id,
            "finalized_at": result.observed_at,
            "channels": channels,
            "runtime_summary": summary.as_dict(),
        }
        target = self.run_directory / "session-final.json"
        encoded = _encoded_json(_sanitized_json_value(payload))
        _exclusive_write(target, encoded)
        digest = hashlib.sha256(encoded).hexdigest()
        _exclusive_write(
            self.run_directory / "session-final.sha256",
            f"{digest}  session-final.json\n".encode("ascii"),
        )
        return target


def _channel_payload(
    snapshot: WindowsStateBridgeSnapshot,
    summary: WindowsN3N4N5RuntimeSummary,
) -> dict[str, Any]:
    rows = {}
    for kind in ASSET_KINDS:
        confirmation = dict(snapshot.action_confirmation.get(kind, {}))
        confirmation["pending_reason_counts"] = dict(
            summary.action_metric_pending_reason_counts.get(kind, {})
        )
        rows[kind] = {
            "action_confirmation": confirmation,
            "n4_snapshot_version": (
                snapshot.n4_states[kind].source_n4_version
            ),
            "n5_snapshot_version": snapshot.n5_episodes[kind].version,
            "active_episodes": _episode_rows(snapshot.n5_episodes[kind]),
            "database_write_count": summary.database_write_counts[kind],
            "event_persistence_count": (
                summary.event_persistence_counts[kind]
            ),
        }
    return rows


def _episode_rows(snapshot: Any) -> list[dict[str, Any]]:
    return [
        _dataclass_value(snapshot.runtime_states[key])
        for key in sorted(
            snapshot.active,
            key=lambda value: (
                value.identity_key,
                value.direction,
                value.episode_entry_event_id,
            ),
        )
    ]


def _dataclass_value(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _dataclass_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (MappingProxyType, Mapping)):
        return {
            str(key): _dataclass_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_dataclass_value(item) for item in value]
    return json_safe_value(value)


def _sanitized_json_value(value: Any, *, field_name: str = "") -> Any:
    value = _dataclass_value(value)
    if isinstance(value, dict):
        return {
            key: _sanitized_json_value(item, field_name=key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitized_json_value(item, field_name=field_name)
            for item in value
        ]
    if isinstance(value, str) and "error" in field_name.lower():
        return _sanitize_error(value)
    return value


def _sanitize_error(value: str) -> str:
    compact = value.replace("\r", " ").replace("\n", " ")
    compact = _DSN_PATTERN.sub(r"\1<redacted>@", compact)
    compact = _PASSWORD_PATTERN.sub(r"\1<redacted>", compact)
    return compact[:512]


def _encoded_json(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_replace_json(path: Path, payload: Any) -> None:
    encoded = _encoded_json(payload)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _exclusive_write(path: Path, encoded: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
