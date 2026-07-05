"""Shared N3 minute label normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta
import re
from typing import Any
from zoneinfo import ZoneInfo


ASIA_SHANGHAI = ZoneInfo("Asia/Shanghai")
ASHARE_CN_1M_CANONICAL_POLICY = "ashare_cn_1m_v1"
C1_TRADING_MINUTE_LABEL_POLICY = "ashare_c1_start_label_session_v1"
BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE = "BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE"
MOOTDX_INTRADAY_1300_TO_1130_POLICY = "mootdx_intraday_1300_to_1130"
RAW_LUNCH_CLOSE = (13, 0)
CANONICAL_LUNCH_CLOSE = (11, 30)
C1_MORNING_FIRST_LABEL = time(9, 30)
C1_MORNING_LAST_LABEL = time(11, 29)
C1_AFTERNOON_FIRST_LABEL = time(13, 0)
C1_AFTERNOON_LAST_LABEL = time(14, 59)


class MinuteLabelNormalizationError(RuntimeError):
    """Raised when minute label normalization must fail closed."""


def normalize_mootdx_intraday_1m_labels(
    rows: Sequence[Mapping[str, Any]],
    *,
    trade_date: str,
    intraday_trade_date: str,
    source_adapter: str,
    identity_key: str | None = None,
) -> list[dict[str, Any]]:
    """Legacy N3P/realtime projection bridge; do not use for N3-C1 physical C1."""

    output = [dict(row) for row in rows]
    if not _is_current_day_mootdx(trade_date=trade_date, intraday_trade_date=intraday_trade_date, source_adapter=source_adapter):
        return sorted(output, key=_sort_key)

    rows_by_identity: dict[str, list[dict[str, Any]]] = {}
    for row in output:
        key = str(
            identity_key
            or row.get("identity_key")
            or row.get("stock_identity_key")
            or row.get("index_identity_key")
            or row.get("board_identity_key")
            or row.get("code")
            or ""
        )
        rows_by_identity.setdefault(key, []).append(row)

    for key, group in rows_by_identity.items():
        raw_1300 = [row for row in group if _row_matches(row, *RAW_LUNCH_CLOSE)]
        raw_1130 = [row for row in group if _row_matches(row, *CANONICAL_LUNCH_CLOSE)]
        if raw_1300 and raw_1130:
            raise MinuteLabelNormalizationError(
                f"duplicate-source anomaly: mootdx current-day 1m emitted both raw 11:30 and raw 13:00 for {key or 'unknown_identity'}"
            )
        if len(raw_1300) > 1:
            raise MinuteLabelNormalizationError(
                f"duplicate-source anomaly: mootdx current-day 1m emitted duplicate raw 13:00 for {key or 'unknown_identity'}"
            )
        for row in raw_1300:
            _normalize_1300_to_1130(row)
    return sorted(output, key=_sort_key)


def normalize_c1_physical_intraday_1m_labels(
    rows: Sequence[Mapping[str, Any]],
    *,
    trade_date: str,
    intraday_trade_date: str,
    source_adapter: str,
    identity_key: str | None = None,
) -> list[dict[str, Any]]:
    """Validate N3-C1 physical 1m labels without legacy lunch bridge rewriting."""

    output = [dict(row) for row in rows]
    if not _is_current_day_mootdx(trade_date=trade_date, intraday_trade_date=intraday_trade_date, source_adapter=source_adapter):
        return sorted(output, key=_sort_key)

    for row in output:
        try:
            validate_ashare_c1_minute_label(_coerce_shanghai(row[_time_key(row)]).strftime("%H:%M"))
        except MinuteLabelNormalizationError as exc:
            key = str(
                identity_key
                or row.get("identity_key")
                or row.get("stock_identity_key")
                or row.get("index_identity_key")
                or row.get("board_identity_key")
                or row.get("code")
                or "unknown_identity"
            )
            raise MinuteLabelNormalizationError(f"{exc}: {key}") from exc
    return sorted(output, key=_sort_key)


def canonical_ashare_1m_labels(trade_date: str) -> list[str]:
    trade_day = _parse_trade_date(trade_date)
    return [
        *(dt.strftime("%H:%M") for dt in _iter_labels(trade_day, C1_MORNING_FIRST_LABEL, C1_MORNING_LAST_LABEL)),
        *(dt.strftime("%H:%M") for dt in _iter_labels(trade_day, C1_AFTERNOON_FIRST_LABEL, C1_AFTERNOON_LAST_LABEL)),
    ]


def validate_ashare_c1_minute_label(minute_label: Any) -> str:
    label = _hhmm_text(minute_label)
    if label not in _c1_label_index():
        raise MinuteLabelNormalizationError(f"{BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE}: {label}")
    return label


def is_valid_ashare_c1_minute_label(minute_label: Any) -> bool:
    try:
        validate_ashare_c1_minute_label(minute_label)
    except MinuteLabelNormalizationError:
        return False
    return True


def ashare_c1_minute_close_time(trade_date: str, minute_label: Any) -> datetime:
    label = validate_ashare_c1_minute_label(minute_label)
    trade_day = _parse_trade_date(trade_date)
    base = datetime.strptime(f"{trade_day.isoformat()} {label}", "%Y-%m-%d %H:%M").replace(tzinfo=ASIA_SHANGHAI)
    return base + timedelta(minutes=1)


def previous_ashare_c1_trading_minute_label(minute_label: Any) -> str | None:
    label = validate_ashare_c1_minute_label(minute_label)
    labels = _c1_labels()
    index = labels.index(label)
    if index == 0:
        return None
    return labels[index - 1]


def next_ashare_c1_trading_minute_label(minute_label: Any) -> str | None:
    label = validate_ashare_c1_minute_label(minute_label)
    labels = _c1_labels()
    index = labels.index(label)
    if index == len(labels) - 1:
        return None
    return labels[index + 1]


def normalize_ashare_c1_target_minute_label(minute_label: Any, *, policy: str = "fail_closed") -> dict[str, Any]:
    label = _hhmm_text(minute_label)
    if label in _c1_label_index():
        return {
            "status": "valid",
            "minute_label": label,
            "normalized_minute_label": label,
            "reason": None,
            "policy": C1_TRADING_MINUTE_LABEL_POLICY,
        }
    if policy == "latest_closed_tradable" and label == "11:30":
        return {
            "status": "normalized",
            "minute_label": label,
            "normalized_minute_label": "11:29",
            "reason": "session_close_boundary_latest_closed_tradable",
            "policy": C1_TRADING_MINUTE_LABEL_POLICY,
        }
    return {
        "status": "blocked",
        "minute_label": label,
        "normalized_minute_label": None,
        "reason": BLOCKED_C1_MINUTE_LABEL_NOT_TRADABLE,
        "policy": C1_TRADING_MINUTE_LABEL_POLICY,
    }


def minute_label_normalization_trace(row: Mapping[str, Any]) -> dict[str, Any] | None:
    raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), Mapping) else {}
    if raw_payload.get("time_label_normalization") != MOOTDX_INTRADAY_1300_TO_1130_POLICY:
        return None
    return {
        "raw_bar_time": raw_payload.get("raw_bar_time") or raw_payload.get("source_bar_time"),
        "source_bar_time": raw_payload.get("source_bar_time") or raw_payload.get("raw_bar_time"),
        "canonical_bar_time": raw_payload.get("canonical_bar_time"),
        "time_label_normalization": raw_payload.get("time_label_normalization"),
        "canonical_minute_policy": raw_payload.get("canonical_minute_policy"),
    }


def _is_current_day_mootdx(*, trade_date: str, intraday_trade_date: str, source_adapter: str) -> bool:
    return str(trade_date) == str(intraday_trade_date) and "mootdx" in str(source_adapter or "").lower()


def _normalize_1300_to_1130(row: dict[str, Any]) -> None:
    key = _time_key(row)
    source_dt = _coerce_shanghai(row[key])
    canonical_dt = source_dt.replace(hour=CANONICAL_LUNCH_CLOSE[0], minute=CANONICAL_LUNCH_CLOSE[1], second=0, microsecond=0)
    row[key] = _format_like(row[key], canonical_dt)
    raw_payload = dict(row.get("raw_payload") or {})
    raw_payload.update(
        {
            "raw_bar_time": source_dt.isoformat(),
            "source_bar_time": source_dt.isoformat(),
            "canonical_bar_time": canonical_dt.isoformat(),
            "time_label_normalization": MOOTDX_INTRADAY_1300_TO_1130_POLICY,
            "canonical_minute_policy": ASHARE_CN_1M_CANONICAL_POLICY,
        }
    )
    row["raw_payload"] = raw_payload


def _row_matches(row: Mapping[str, Any], hour: int, minute: int) -> bool:
    dt = _coerce_shanghai(row[_time_key(row)])
    return dt.hour == hour and dt.minute == minute


def _time_key(row: Mapping[str, Any]) -> str:
    for key in ("bar_time", "datetime", "minute_label", "date_time", "time"):
        if key in row and row.get(key) is not None:
            return key
    raise MinuteLabelNormalizationError("missing minute time field")


def _coerce_shanghai(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("T", " ")
        if "+" in text:
            text = text.split("+", 1)[0]
        if "." in text:
            text = text.split(".", 1)[0]
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M" if len(text) == 16 else "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ASIA_SHANGHAI)
    return dt.astimezone(ASIA_SHANGHAI)


def _format_like(original: Any, dt: datetime) -> Any:
    if isinstance(original, datetime):
        return dt
    text = str(original)
    if "T" in text:
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    if len(text) == 16:
        return dt.strftime("%Y-%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _sort_key(row: Mapping[str, Any]) -> datetime:
    try:
        return _coerce_shanghai(row[_time_key(row)])
    except MinuteLabelNormalizationError:
        return datetime.min.replace(tzinfo=ASIA_SHANGHAI)


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(str(value), "%Y%m%d").date()


def _hhmm_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(ASIA_SHANGHAI).strftime("%H:%M") if value.tzinfo else value.strftime("%H:%M")
    text = str(value or "").strip()
    if re.fullmatch(r"\d{2}:\d{2}", text):
        return text
    match = re.search(r"(\d{2}:\d{2})(?::\d{2})?", text)
    if match:
        return match.group(1)
    raise MinuteLabelNormalizationError("minute_label must be HH:MM")


def _c1_labels() -> list[str]:
    return [
        *(f"09:{minute:02d}" for minute in range(30, 60)),
        *(f"10:{minute:02d}" for minute in range(60)),
        *(f"11:{minute:02d}" for minute in range(30)),
        *(f"13:{minute:02d}" for minute in range(60)),
        *(f"14:{minute:02d}" for minute in range(60)),
    ]


def _c1_label_index() -> set[str]:
    return set(_c1_labels())


def _iter_labels(trade_day: date, start: time, end: time) -> list[datetime]:
    current = datetime.combine(trade_day, start, tzinfo=ASIA_SHANGHAI)
    final = datetime.combine(trade_day, end, tzinfo=ASIA_SHANGHAI)
    rows = []
    while current <= final:
        rows.append(current)
        current += timedelta(minutes=1)
    return rows
