"""N3 source-returned time policy helpers.

The helpers validate source timestamps as lineage.  They intentionally do not
use local wall-clock time as a readiness gate.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Mapping
from zoneinfo import ZoneInfo


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
SOURCE_RETURNED_TIME_POLICY = "source_returned_time"
PROJECTED_30M_CLOSED_STATUS = "projected"
TRADING_WINDOWS = (
    (time(9, 30), time(11, 30)),
    (time(13, 0), time(15, 0)),
)
TRADING_BUCKETS_30M = (
    ("09:30", "10:00"),
    ("10:00", "10:30"),
    ("10:30", "11:00"),
    ("11:00", "11:30"),
    ("13:00", "13:30"),
    ("13:30", "14:00"),
    ("14:00", "14:30"),
    ("14:30", "15:00"),
)
FAKE_SOURCE_MARKERS = {"fake", "synthetic", "fabricated"}


class N3SourceTimePolicyError(ValueError):
    """Raised when source-returned time is not valid N3 lineage."""


def parse_source_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return ensure_shanghai_time(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return ensure_shanghai_time(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def ensure_shanghai_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=ASIA_SHANGHAI)
    return value.astimezone(ASIA_SHANGHAI)


def normalize_source_trade_date(value: Any) -> str:
    text = str(value or "").strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise N3SourceTimePolicyError("missing_or_invalid_source_trade_date")
    return text


def source_marker_from_mapping(row: Mapping[str, Any]) -> Any:
    return (
        row.get("source_marker")
        or row.get("source_kind")
        or row.get("source_time_kind")
        or row.get("bar_kind")
        or row.get("snapshot_kind")
    )


def validate_source_returned_time(
    *,
    source_time: datetime | None,
    source_trade_date: Any,
    for_trade_date: Any,
    source_marker: Any = None,
) -> dict[str, Any]:
    if source_time is None:
        raise N3SourceTimePolicyError("missing_source_time")
    if str(source_marker or "").strip().lower() in FAKE_SOURCE_MARKERS:
        raise N3SourceTimePolicyError("fake_source_time_forbidden")
    expected_trade_date = normalize_source_trade_date(for_trade_date)
    normalized_source_trade_date = normalize_source_trade_date(source_trade_date)
    if normalized_source_trade_date != expected_trade_date:
        raise N3SourceTimePolicyError("source_trade_date_mismatch")
    resolved_source_time = ensure_shanghai_time(source_time)
    if resolved_source_time.strftime("%Y%m%d") != expected_trade_date:
        raise N3SourceTimePolicyError("source_time_date_mismatch")
    return {
        "source_time_policy": SOURCE_RETURNED_TIME_POLICY,
        "source_time": resolved_source_time,
        "source_trade_date": normalized_source_trade_date,
        "for_trade_date": expected_trade_date,
    }


def map_source_time_to_trade_window(*, source_time: datetime, for_trade_date: Any) -> dict[str, Any]:
    validated = validate_source_returned_time(
        source_time=source_time,
        source_trade_date=for_trade_date,
        for_trade_date=for_trade_date,
    )
    resolved_source_time = validated["source_time"]
    source_clock = resolved_source_time.time()
    for start, end in TRADING_WINDOWS:
        if start <= source_clock <= end:
            return {
                **validated,
                "window_start": datetime.combine(resolved_source_time.date(), start, tzinfo=ASIA_SHANGHAI),
                "window_end": datetime.combine(resolved_source_time.date(), end, tzinfo=ASIA_SHANGHAI),
            }
    raise N3SourceTimePolicyError("source_time_outside_trading_window")


def map_source_time_to_30m_window(*, source_time: datetime, for_trade_date: Any) -> dict[str, Any]:
    validated = validate_source_returned_time(
        source_time=source_time,
        source_trade_date=for_trade_date,
        for_trade_date=for_trade_date,
    )
    resolved_source_time = validated["source_time"]
    day: date = resolved_source_time.date()
    for start_label, end_label in TRADING_BUCKETS_30M:
        start = _combine(day, start_label)
        end = _combine(day, end_label)
        if start <= resolved_source_time <= end:
            return {
                **validated,
                "source_30m_k_time": resolved_source_time,
                "source_30m_k_window_start": start,
                "source_30m_k_window_end": end,
                "source_30m_k_closed_status": PROJECTED_30M_CLOSED_STATUS,
                "projection_mode": "realtime_virtual_30m",
            }
    raise N3SourceTimePolicyError("source_time_outside_30m_window")


def _combine(day: date, hhmm: str) -> datetime:
    hour, minute = [int(part) for part in hhmm.split(":")]
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ASIA_SHANGHAI)
