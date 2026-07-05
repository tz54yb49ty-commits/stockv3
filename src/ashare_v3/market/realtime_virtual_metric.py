"""N3-owned realtime virtual metric builder.

The functions here are pure calculation helpers. They do not read or write a
database, call market adapters, publish events, or invoke N4/N5. Runners can
wrap this module with lineage, schema, and rollback gates later.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence


HIGHER_PERIODS = ("D", "W", "M", "Q", "Y")
HIGHER_PERIOD_DB_TOKENS = {period: period.lower() for period in HIGHER_PERIODS}
VIRTUAL_AMOUNT_POLICY_VERSION = "previous_day_same_window_elapsed_ratio_v1"
CANONICAL_MINUTE_POLICY = "ashare_cn_1m_v1"
LEGACY_MIDDAY_BRIDGE_POLICY = "13:00_label_equivalent_to_missing_11:30_bar"
PREVIOUS_DAY_MIDDAY_BRIDGE_NORMALIZATION_POLICY = "previous_day_midday_bridge_1130_to_1300_v1"
FORMAL_AMOUNT_SOURCE_KIND = "N3_standard_period_metric"
FORMAL_AMOUNT_UNIT = "yuan"
FORMAL_AMOUNT_SOURCE_UNIT = "thousand_yuan"
FORMAL_AMOUNT_UNIT_CONVERSION_FACTOR = 1000.0
FORMAL_AMOUNT_UNIT_CONVERSION_POLICY = "formal_amount_chain_thousand_yuan_to_yuan_v1"
FORMAL_AMOUNT_YUAN_PASSTHROUGH_POLICY = "true_full_day_minute_series_yuan_passthrough_v1"
FORMAL_AMOUNT_UNIT_SOURCE_POLICY = "explicit_asset_kind_rule"
FORMAL_AMOUNT_RULE = "attachment_dwmqy_avg_chain"
FORMAL_AMOUNT_SOURCE_UNIT_BY_ASSET_KIND = {
    "stock": "thousand_yuan",
    "index": "yuan",
    "board": "yuan",
}
FORMAL_AMOUNT_AVG_FIELDS = {
    "W": ("weekly_avg_with_today", "prev_weekly_avg"),
    "M": ("monthly_avg_with_today", "prev_monthly_avg"),
    "Q": ("quarterly_avg_with_today", "prev_quarterly_avg"),
    "Y": ("yearly_avg_with_today", "prev_yearly_avg"),
}


def _build_field_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for period, db_period in HIGHER_PERIOD_DB_TOKENS.items():
        for prefix in ("current", "previous"):
            for suffix in ("body_high", "body_low"):
                aliases[f"{prefix}_{period}_{suffix}"] = f"{prefix}_{db_period}_{suffix}"
        aliases[f"current_{period}_virtual_amount"] = f"current_{db_period}_virtual_amount"
        aliases[f"previous_{period}_amount"] = f"previous_{db_period}_amount"
    return aliases


REALTIME_VIRTUAL_METRIC_FIELD_ALIASES = _build_field_aliases()

REALTIME_VIRTUAL_METRIC_DB_COLUMNS = (
    "realtime_metric_schema_version",
    "metric_time_label",
    "source_time",
    "observed_at",
    "snapshot_id",
    "event_id",
    "quality_status",
    "session_kind",
    "period_source",
    "is_closed_1m",
    "is_auction_virtual",
    "midday_bridge_policy",
    "deterministic_pass_flags",
    "current_1m_body_high",
    "current_1m_body_low",
    "current_5m_body_high",
    "current_5m_body_low",
    "current_30m_body_high",
    "current_30m_body_low",
    "current_120m_body_high",
    "current_120m_body_low",
    "current_d_body_high",
    "current_d_body_low",
    "current_w_body_high",
    "current_w_body_low",
    "current_m_body_high",
    "current_m_body_low",
    "current_q_body_high",
    "current_q_body_low",
    "current_y_body_high",
    "current_y_body_low",
    "previous_d_body_high",
    "previous_d_body_low",
    "previous_w_body_high",
    "previous_w_body_low",
    "previous_m_body_high",
    "previous_m_body_low",
    "previous_q_body_high",
    "previous_q_body_low",
    "previous_y_body_high",
    "previous_y_body_low",
    "current_30m_virtual_amount",
    "previous_day_same_window_amount",
    "previous_30m_full_amount",
    "current_120m_virtual_amount",
    "previous_120m_full_amount",
    "current_d_virtual_amount",
    "previous_d_amount",
    "current_w_virtual_amount",
    "previous_w_amount",
    "current_m_virtual_amount",
    "previous_m_amount",
    "current_q_virtual_amount",
    "previous_q_amount",
    "current_y_virtual_amount",
    "previous_y_amount",
    "trace_json",
)


def canonicalize_realtime_virtual_metric_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    for key, value in row.items():
        target = REALTIME_VIRTUAL_METRIC_FIELD_ALIASES.get(str(key), str(key))
        if str(key) in REALTIME_VIRTUAL_METRIC_FIELD_ALIASES and target in canonical:
            continue
        canonical[target] = value
    return canonical


def parse_minute(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def parse_observed_at(value: str | datetime | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    if isinstance(value, datetime):
        return value
    text = str(value).replace("T", " ")
    if "+" in text:
        text = text.split("+", 1)[0]
    if "." in text:
        text = text.split(".", 1)[0]
    if len(text) == 16:
        return datetime.strptime(text, "%Y-%m-%d %H:%M")
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): normalize_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [normalize_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def body_high(row: Mapping[str, Any]) -> float:
    return max(float(row["open"]), float(row["close"]))


def body_low(row: Mapping[str, Any]) -> float:
    return min(float(row["open"]), float(row["close"]))


def minute_index(dt: datetime) -> int | None:
    hm = dt.hour * 60 + dt.minute
    if 9 * 60 + 31 <= hm <= 11 * 60 + 30:
        return hm - (9 * 60 + 30)
    if hm == 13 * 60:
        return 120
    if 13 * 60 + 1 <= hm <= 15 * 60:
        return 120 + hm - 13 * 60
    return None


def segment_index(dt: datetime, period_minutes: int) -> int | None:
    idx = minute_index(dt)
    if idx is None:
        return None
    if period_minutes == 1:
        return idx - 1
    if period_minutes in (5, 30):
        return (idx - 1) // period_minutes
    if period_minutes == 120:
        return 0 if idx <= 120 else 1
    raise ValueError("period_minutes must be one of 1, 5, 30, 120")


def sort_minute_rows(rows: Iterable[Mapping[str, Any]], *, code: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("code") or "") != str(code):
            continue
        minute = row["datetime"]
        dt = minute if isinstance(minute, datetime) else parse_minute(str(minute))
        normalized_row = {
            "code": str(row["code"]),
            "datetime": dt.strftime("%Y-%m-%d %H:%M"),
            "_dt": dt,
            "open": float(row["open"] or 0.0),
            "high": float(row.get("high") or 0.0),
            "low": float(row.get("low") or 0.0),
            "close": _float_or_none(row.get("close")),
            "amount": _float_or_none(row.get("amount")),
        }
        for key in ("raw_bar_time", "canonical_bar_time", "normalization_policy"):
            if row.get(key) not in (None, ""):
                normalized_row[key] = str(row[key])
        normalized.append(normalized_row)
    normalized.sort(key=lambda item: item["_dt"])
    return normalized


def aggregate_segment(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    ordered = sorted(rows, key=lambda item: item["_dt"])
    return {
        "datetime": ordered[0]["datetime"],
        "open": float(ordered[0]["open"]),
        "close": float(ordered[-1]["close"]),
        "high": max(float(row["high"]) for row in ordered),
        "low": min(float(row["low"]) for row in ordered),
        "amount": sum(float(row.get("amount") or 0.0) for row in ordered),
        "minute_count": len(ordered),
        "body_high": max(float(ordered[0]["open"]), float(ordered[-1]["close"])),
        "body_low": min(float(ordered[0]["open"]), float(ordered[-1]["close"])),
        "source_minute_refs": [str(row["datetime"]) for row in ordered],
    }


def rows_for_segment(
    rows: Sequence[Mapping[str, Any]],
    *,
    trade_date: str,
    period_minutes: int,
    seg_index: int,
    through: datetime | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        dt = row["_dt"]
        if dt.strftime("%Y%m%d") != trade_date:
            continue
        if through is not None and dt > through:
            continue
        if segment_index(dt, period_minutes) == seg_index:
            selected.append(dict(row))
    return selected


def previous_trade_date(rows: Sequence[Mapping[str, Any]], trade_date: str) -> str | None:
    dates = sorted(
        {row["_dt"].strftime("%Y%m%d") for row in rows if row["_dt"].strftime("%Y%m%d") < trade_date}
    )
    return dates[-1] if dates else None


def previous_minute_row(rows: Sequence[Mapping[str, Any]], current_dt: datetime) -> tuple[dict[str, Any] | None, str]:
    earlier = [dict(row) for row in rows if row["_dt"] < current_dt]
    if not earlier:
        return None, "not_available"
    row = earlier[-1]
    source = (
        "same_trade_date_previous_period"
        if row["_dt"].strftime("%Y%m%d") == current_dt.strftime("%Y%m%d")
        else "previous_trade_date_last_period"
    )
    return row, source


def previous_segment_aggregate(
    rows: Sequence[Mapping[str, Any]],
    *,
    current_dt: datetime,
    period_minutes: int,
) -> tuple[dict[str, Any] | None, str]:
    current_trade_date = current_dt.strftime("%Y%m%d")
    current_seg = segment_index(current_dt, period_minutes)
    if current_seg is None:
        return None, "not_available"
    if current_seg > 0:
        agg = aggregate_segment(
            rows_for_segment(
                rows,
                trade_date=current_trade_date,
                period_minutes=period_minutes,
                seg_index=current_seg - 1,
            )
        )
        return agg, "same_trade_date_previous_period" if agg else "not_available"

    prev_date = previous_trade_date(rows, current_trade_date)
    if prev_date is None:
        return None, "not_available"
    prev_segments = [
        segment_index(row["_dt"], period_minutes)
        for row in rows
        if row["_dt"].strftime("%Y%m%d") == prev_date
    ]
    prev_segments = [seg for seg in prev_segments if seg is not None]
    if not prev_segments:
        return None, "not_available"
    agg = aggregate_segment(
        rows_for_segment(
            rows,
            trade_date=prev_date,
            period_minutes=period_minutes,
            seg_index=max(prev_segments),
        )
    )
    return agg, "previous_trade_date_last_period" if agg else "not_available"


def previous_day_refs_for_sources(*items: tuple[Mapping[str, Any] | None, str]) -> list[str]:
    refs: set[str] = set()
    for value, source in items:
        if source != "previous_trade_date_last_period" or not value:
            continue
        if value.get("source_minute_refs"):
            refs.update(str(ref) for ref in value.get("source_minute_refs") or [])
        elif value.get("datetime"):
            refs.add(str(value["datetime"]))
    return sorted(refs)


def current_period_virtual_amount(
    rows: Sequence[Mapping[str, Any]],
    *,
    current_dt: datetime,
    period_minutes: int,
) -> tuple[float | None, float, list[str], dict[str, Any]]:
    trade_date = current_dt.strftime("%Y%m%d")
    seg = segment_index(current_dt, period_minutes)
    if seg is None:
        return None, 0.0, [], {
            "status": "failed",
            "reason": "current_time_outside_trading_segment",
            "metric_policy": VIRTUAL_AMOUNT_POLICY_VERSION,
            "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
            "amount_unit": FORMAL_AMOUNT_UNIT,
            "current_period_amount_source_kind": FORMAL_AMOUNT_SOURCE_KIND,
        }
    current_rows = rows_for_segment(
        rows,
        trade_date=trade_date,
        period_minutes=period_minutes,
        seg_index=seg,
        through=current_dt,
    )
    current_amount = sum(float(row.get("amount") or 0.0) for row in current_rows)

    previous, _ = previous_segment_aggregate(rows, current_dt=current_dt, period_minutes=period_minutes)
    previous_full_amount = float(previous["amount"]) if previous else 0.0

    prev_date = previous_trade_date(rows, trade_date)
    previous_same_rows = (
        rows_for_segment(rows, trade_date=prev_date, period_minutes=period_minutes, seg_index=seg)
        if prev_date is not None
        else []
    )
    elapsed_count = len(current_rows)
    previous_elapsed_rows = previous_same_rows[:elapsed_count]
    previous_elapsed_amount = sum(float(row.get("amount") or 0.0) for row in previous_elapsed_rows)
    previous_same_full_amount = sum(float(row.get("amount") or 0.0) for row in previous_same_rows)
    proof = {
        "status": "passed",
        "metric_policy": VIRTUAL_AMOUNT_POLICY_VERSION,
        "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
        "period_minutes": period_minutes,
        "current_elapsed_amount": current_amount,
        "current_elapsed_count": elapsed_count,
        "previous_day_same_elapsed_amount": previous_elapsed_amount,
        "previous_day_same_full_amount": previous_same_full_amount,
        "amount_unit": FORMAL_AMOUNT_UNIT,
        "current_period_amount_source_kind": FORMAL_AMOUNT_SOURCE_KIND,
        "previous_day_same_elapsed_refs": [str(row["datetime"]) for row in previous_elapsed_rows],
        "previous_day_same_full_refs": [str(row["datetime"]) for row in previous_same_rows],
    }
    failure_reason = None
    if not current_rows:
        failure_reason = "current_elapsed_amount_missing"
    elif prev_date is None:
        failure_reason = "previous_trade_date_missing"
    elif not previous_same_rows:
        failure_reason = "previous_day_same_window_full_amount_missing"
    elif len(previous_same_rows) < elapsed_count:
        failure_reason = "previous_day_same_elapsed_window_incomplete"
    elif previous_elapsed_amount <= 0:
        failure_reason = "previous_day_same_elapsed_amount_non_positive"
    elif previous_same_full_amount <= 0:
        failure_reason = "previous_day_same_full_amount_non_positive"
    if failure_reason:
        proof["status"] = "failed"
        proof["reason"] = failure_reason
        return None, previous_full_amount, [str(row["datetime"]) for row in current_rows], proof

    current_virtual = current_amount / previous_elapsed_amount * previous_same_full_amount
    proof["current_virtual_amount"] = current_virtual
    return current_virtual, previous_full_amount, [str(row["datetime"]) for row in current_rows], proof


def current_day_virtual_amount(
    rows: Sequence[Mapping[str, Any]],
    *,
    current_dt: datetime,
) -> tuple[float | None, list[str], dict[str, Any]]:
    trade_date = current_dt.strftime("%Y%m%d")
    current_rows = [
        dict(row)
        for row in rows
        if row["_dt"].strftime("%Y%m%d") == trade_date and row["_dt"] <= current_dt
    ]
    current_amount = sum(float(row.get("amount") or 0.0) for row in current_rows)
    prev_date = previous_trade_date(rows, trade_date)
    previous_same_rows = [
        dict(row)
        for row in rows
        if prev_date is not None and row["_dt"].strftime("%Y%m%d") == prev_date
    ]
    elapsed_count = len(current_rows)
    previous_elapsed_rows = previous_same_rows[:elapsed_count]
    previous_elapsed_amount = sum(float(row.get("amount") or 0.0) for row in previous_elapsed_rows)
    previous_full_amount = sum(float(row.get("amount") or 0.0) for row in previous_same_rows)
    proof = {
        "status": "passed",
        "metric_policy": VIRTUAL_AMOUNT_POLICY_VERSION,
        "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
        "period": "D",
        "current_elapsed_amount": current_amount,
        "current_elapsed_count": elapsed_count,
        "previous_day_same_elapsed_amount": previous_elapsed_amount,
        "previous_day_same_full_amount": previous_full_amount,
        "amount_unit": FORMAL_AMOUNT_UNIT,
        "current_period_amount_source_kind": FORMAL_AMOUNT_SOURCE_KIND,
        "previous_day_same_elapsed_refs": [str(row["datetime"]) for row in previous_elapsed_rows],
        "previous_day_same_full_refs": [str(row["datetime"]) for row in previous_same_rows],
    }
    failure_reason = None
    if not current_rows:
        failure_reason = "current_elapsed_amount_missing"
    elif prev_date is None:
        failure_reason = "previous_trade_date_missing"
    elif not previous_same_rows:
        failure_reason = "previous_day_same_window_full_amount_missing"
    elif len(previous_same_rows) < elapsed_count:
        failure_reason = "previous_day_same_elapsed_window_incomplete"
    elif previous_elapsed_amount <= 0:
        failure_reason = "previous_day_same_elapsed_amount_non_positive"
    elif previous_full_amount <= 0:
        failure_reason = "previous_day_same_full_amount_non_positive"
    if failure_reason:
        proof["status"] = "failed"
        proof["reason"] = failure_reason
        return None, [str(row["datetime"]) for row in current_rows], proof

    current_virtual = current_amount / previous_elapsed_amount * previous_full_amount
    proof["current_virtual_amount"] = current_virtual
    return current_virtual, [str(row["datetime"]) for row in current_rows], proof


def canonical_trading_minute_labels(trade_date: str) -> list[str]:
    labels: list[str] = []
    for hour, minute_start, minute_end in (
        (9, 31, 59),
        (10, 0, 59),
        (11, 0, 29),
        (13, 0, 59),
        (14, 0, 59),
        (15, 0, 0),
    ):
        for minute in range(minute_start, minute_end + 1):
            labels.append(f"{trade_date} {hour:02d}:{minute:02d}")
    return labels


def _minute_label_from_row_value(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    text = str(value or "").replace("T", " ")
    if "+" in text:
        text = text.split("+", 1)[0]
    if "." in text:
        text = text.split(".", 1)[0]
    return text[:16] if len(text) >= 16 else ""


def _previous_day_row_label(row: Mapping[str, Any]) -> str:
    for key in ("datetime", "bar_time", "minute_label"):
        label = _minute_label_from_row_value(row.get(key))
        if label:
            return label
    return ""


def build_previous_day_cumulative_summary_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    asset_kind: str | None = None,
    identity_key: str | None = None,
    source_previous_day_minute_run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Build per-canonical-minute cumulative A1 summaries without mutating raw A1 rows."""
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        code = str(row.get("code") or "")
        row_asset_kind = str(asset_kind or row.get("asset_kind") or "")
        row_identity_key = str(identity_key or row.get("identity_key") or row.get(f"{row_asset_kind}_identity_key") or code)
        raw_label = _previous_day_row_label(row)
        if not code or not raw_label:
            continue
        grouped.setdefault((row_asset_kind, row_identity_key, code, raw_label[:10]), []).append(row)

    output: list[dict[str, Any]] = []
    for (row_asset_kind, row_identity_key, code, trade_date_label), group_rows in grouped.items():
        canonical_by_label: dict[str, dict[str, Any]] = {}
        raw_labels: list[str] = []
        group_normalized = False
        for row in group_rows:
            raw_label = _previous_day_row_label(row)
            raw_labels.append(raw_label)
            canonical_label = raw_label
            normalization_policy = ""
            if raw_label.endswith(" 11:30"):
                canonical_label = f"{raw_label[:10]} 13:00"
                normalization_policy = PREVIOUS_DAY_MIDDAY_BRIDGE_NORMALIZATION_POLICY
                group_normalized = True
            if canonical_label in canonical_by_label:
                existing_raw = str(canonical_by_label[canonical_label].get("raw_label") or "")
                if canonical_label.endswith(" 13:00") and (
                    raw_label.endswith(" 11:30")
                    or raw_label.endswith(" 13:00")
                    or existing_raw.endswith(" 11:30")
                    or existing_raw.endswith(" 13:00")
                ):
                    raise ValueError(f"previous_day_midday_bridge_duplicate:{code}:{trade_date_label}")
                raise ValueError(f"previous_day_cumulative_duplicate_canonical_label:{code}:{canonical_label}")
            canonical_by_label[canonical_label] = {
                "row": row,
                "raw_label": raw_label,
                "canonical_label": canonical_label,
                "normalization_policy": normalization_policy,
            }

        canonical_labels = canonical_trading_minute_labels(trade_date_label)
        if len(canonical_by_label) != len(canonical_labels) or any(label not in canonical_by_label for label in canonical_labels):
            raise ValueError(
                f"previous_day_cumulative_full_window_incomplete:{code}:{trade_date_label}:"
                f"{len(canonical_by_label)}/{len(canonical_labels)}"
            )
        full_amount = sum(float(canonical_by_label[label]["row"].get("amount") or 0.0) for label in canonical_labels)
        raw_first_label = min(raw_labels)
        raw_last_label = max(raw_labels)
        source_bar_ids = [
            item["row"].get("bar_id")
            for item in (canonical_by_label[label] for label in canonical_labels)
            if item["row"].get("bar_id") not in (None, "")
        ]
        elapsed_amount = 0.0
        for idx, label in enumerate(canonical_labels, start=1):
            item = canonical_by_label[label]
            row = item["row"]
            elapsed_amount += float(row.get("amount") or 0.0)
            output.append(
                {
                    "asset_kind": row_asset_kind,
                    "identity_key": row_identity_key,
                    "code": code,
                    "canonical_minute_label": label,
                    "previous_day_elapsed_amount": elapsed_amount,
                    "previous_day_full_amount": full_amount,
                    "elapsed_count": idx,
                    "full_count": len(canonical_labels),
                    "raw_label": item["raw_label"],
                    "raw_first_label": raw_first_label,
                    "raw_last_label": raw_last_label,
                    "normalization_policy": PREVIOUS_DAY_MIDDAY_BRIDGE_NORMALIZATION_POLICY
                    if group_normalized
                    else item["normalization_policy"],
                    "source_previous_day_minute_run_id": source_previous_day_minute_run_id
                    or row.get("source_previous_day_minute_run_id")
                    or row.get("run_id"),
                    "raw_source_refs": [item["raw_label"]],
                    "source_bar_ids": source_bar_ids,
                }
            )
    output.sort(key=lambda row: (str(row.get("asset_kind")), str(row.get("identity_key")), str(row.get("canonical_minute_label"))))
    return normalize_jsonable(output)


A1_CUMULATIVE_ASSET_KINDS = ("stock", "index", "board")
A1_CUMULATIVE_DEFAULT_SOURCE_AMOUNT_UNIT = {
    "stock": "thousand_yuan",
    "index": "yuan",
    "board": "yuan",
}
A1_CUMULATIVE_AMOUNT_UNIT_FACTORS = {
    "yuan": 1.0,
    "thousand_yuan": 1000.0,
}


def _a1_cumulative_empty_rows_by_asset() -> dict[str, list[dict[str, Any]]]:
    return {asset_kind: [] for asset_kind in A1_CUMULATIVE_ASSET_KINDS}


def _a1_cumulative_input_rows_by_asset(
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]],
) -> tuple[dict[str, list[Mapping[str, Any]]], list[dict[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {asset_kind: [] for asset_kind in A1_CUMULATIVE_ASSET_KINDS}
    errors: list[dict[str, Any]] = []
    if isinstance(rows_by_asset, Mapping):
        for asset_kind, rows in rows_by_asset.items():
            asset_key = str(asset_kind or "")
            if asset_key not in A1_CUMULATIVE_ASSET_KINDS:
                errors.append({"asset_kind": asset_key, "reason": "unknown_asset_kind"})
                continue
            grouped[asset_key].extend([row for row in rows if isinstance(row, Mapping)])
        return grouped, errors

    for row in rows_by_asset:
        if not isinstance(row, Mapping):
            continue
        asset_key = str(row.get("asset_kind") or "")
        if asset_key not in A1_CUMULATIVE_ASSET_KINDS:
            errors.append(
                {
                    "asset_kind": asset_key,
                    "identity_key": row.get("identity_key"),
                    "reason": "unknown_asset_kind",
                }
            )
            continue
        grouped[asset_key].append(row)
    return grouped, errors


def _a1_cumulative_source_unit(asset_kind: str, row: Mapping[str, Any]) -> str:
    return str(row.get("source_amount_unit") or A1_CUMULATIVE_DEFAULT_SOURCE_AMOUNT_UNIT[asset_kind])


def _a1_cumulative_amount_value(row: Mapping[str, Any]) -> float | None:
    for key in ("amount", "source_amount", "amount_yuan", "canonical_amount"):
        if key in row and row.get(key) not in (None, ""):
            try:
                return float(row.get(key))
            except (TypeError, ValueError):
                return None
    return None


def _a1_cumulative_has_forbidden_source_marker(row: Mapping[str, Any]) -> bool:
    marker_values = [
        row.get("source_marker"),
        row.get("source_origin"),
        row.get("quality_marker"),
        row.get("data_source_marker"),
    ]
    raw_payload = row.get("raw_json") or row.get("raw_payload")
    if isinstance(raw_payload, Mapping):
        marker_values.extend(raw_payload.values())
    marker_text = " ".join(str(value).lower() for value in marker_values if value is not None)
    return any(token in marker_text for token in ("fake", "synthetic", "fabricated"))


def build_previous_day_cumulative_amount_rows(
    rows_by_asset: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]],
    *,
    source_previous_day_minute_run_id: str,
    for_trade_date: str,
    source_trade_date: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build the N3-A1 per-minute cumulative amount product without DB or adapter side effects."""
    grouped, errors = _a1_cumulative_input_rows_by_asset(rows_by_asset)
    output = _a1_cumulative_empty_rows_by_asset()

    for physical_asset_kind, source_rows in grouped.items():
        if not source_rows:
            continue
        row_errors: list[dict[str, Any]] = []
        converted_rows: list[dict[str, Any]] = []
        for row in source_rows:
            row_asset_kind = str(row.get("asset_kind") or physical_asset_kind)
            identity_key = str(row.get("identity_key") or row.get(f"{physical_asset_kind}_identity_key") or "")
            raw_label = _previous_day_row_label(row)
            if row_asset_kind != physical_asset_kind:
                row_errors.append(
                    {
                        "asset_kind": physical_asset_kind,
                        "identity_key": identity_key,
                        "reason": "mixed_physical_table_source_leakage",
                    }
                )
                continue
            if raw_label and source_trade_date and raw_label[:10].replace("-", "") != str(source_trade_date):
                row_errors.append(
                    {
                        "asset_kind": physical_asset_kind,
                        "identity_key": identity_key,
                        "raw_bar_time": raw_label,
                        "reason": "source_trade_date_mismatch",
                    }
                )
                continue
            if _a1_cumulative_has_forbidden_source_marker(row):
                row_errors.append(
                    {
                        "asset_kind": physical_asset_kind,
                        "identity_key": identity_key,
                        "raw_bar_time": raw_label,
                        "reason": "forbidden_fake_synthetic_fabricated_source_row",
                    }
                )
                continue
            source_unit = _a1_cumulative_source_unit(physical_asset_kind, row)
            factor = A1_CUMULATIVE_AMOUNT_UNIT_FACTORS.get(source_unit)
            amount_value = _a1_cumulative_amount_value(row)
            if factor is None:
                row_errors.append(
                    {
                        "asset_kind": physical_asset_kind,
                        "identity_key": identity_key,
                        "raw_bar_time": raw_label,
                        "reason": "unknown_source_amount_unit",
                    }
                )
                continue
            if amount_value is None or amount_value < 0:
                row_errors.append(
                    {
                        "asset_kind": physical_asset_kind,
                        "identity_key": identity_key,
                        "raw_bar_time": raw_label,
                        "reason": "invalid_amount",
                    }
                )
                continue
            converted = dict(row)
            converted["asset_kind"] = physical_asset_kind
            converted["identity_key"] = identity_key
            converted["amount"] = amount_value * factor
            converted["source_amount_raw"] = amount_value
            converted["source_amount_unit"] = source_unit
            converted["canonical_amount_unit"] = FORMAL_AMOUNT_UNIT
            converted["unit_conversion_factor"] = factor
            converted_rows.append(converted)

        if row_errors:
            errors.extend(row_errors)
            continue

        try:
            summary_rows = build_previous_day_cumulative_summary_rows(
                converted_rows,
                asset_kind=physical_asset_kind,
                source_previous_day_minute_run_id=source_previous_day_minute_run_id,
            )
        except ValueError as exc:
            errors.append({"asset_kind": physical_asset_kind, "reason": str(exc)})
            continue

        source_by_raw_label = {_previous_day_row_label(row): row for row in converted_rows}
        fact_rows: list[dict[str, Any]] = []
        for row in summary_rows:
            raw_bar_time = str(row.get("raw_label") or "")
            source_row = source_by_raw_label.get(raw_bar_time, {})
            source_unit = str(source_row.get("source_amount_unit") or A1_CUMULATIVE_DEFAULT_SOURCE_AMOUNT_UNIT[physical_asset_kind])
            factor = float(source_row.get("unit_conversion_factor") or A1_CUMULATIVE_AMOUNT_UNIT_FACTORS[source_unit])
            canonical_label = str(row.get("canonical_minute_label") or "")
            identity_key = str(row.get("identity_key") or "")
            cumulative_id = (
                f"{source_previous_day_minute_run_id}__{physical_asset_kind}__"
                f"{identity_key}__{canonical_label.replace(' ', '_').replace(':', '')}"
            )
            trace_json = {
                "physical_table_asset_kind": physical_asset_kind,
                "raw_first_label": row.get("raw_first_label"),
                "raw_last_label": row.get("raw_last_label"),
                "normalization_policy": row.get("normalization_policy"),
                "raw_source_refs": list(row.get("raw_source_refs") or []),
                "source_bar_ids": list(row.get("source_bar_ids") or []),
                "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
            }
            raw_json = {
                "source_amount": source_row.get("source_amount_raw"),
                "source_amount_unit": source_unit,
                "canonical_amount_unit": FORMAL_AMOUNT_UNIT,
                "unit_conversion_factor": factor,
                "raw_bar_time": raw_bar_time,
                "canonical_bar_time": canonical_label,
                "source_bar_id": source_row.get("bar_id"),
            }
            fact_rows.append(
                {
                    "cumulative_id": cumulative_id,
                    "run_id": source_previous_day_minute_run_id,
                    "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
                    "for_trade_date": for_trade_date,
                    "source_trade_date": source_trade_date,
                    "asset_kind": physical_asset_kind,
                    "identity_key": identity_key,
                    "code": row.get("code"),
                    "exchange": source_row.get("exchange"),
                    "canonical_minute_label": canonical_label,
                    "canonical_bar_time": canonical_label,
                    "raw_bar_time": raw_bar_time,
                    "elapsed_index": row.get("elapsed_count"),
                    "elapsed_count": row.get("elapsed_count"),
                    "full_count": row.get("full_count"),
                    "cumulative_amount_yuan": row.get("previous_day_elapsed_amount"),
                    "full_day_amount_yuan": row.get("previous_day_full_amount"),
                    "previous_day_elapsed_amount": row.get("previous_day_elapsed_amount"),
                    "previous_day_full_amount": row.get("previous_day_full_amount"),
                    "source_amount_unit": source_unit,
                    "canonical_amount_unit": FORMAL_AMOUNT_UNIT,
                    "unit_conversion_factor": factor,
                    "normalization_policy": row.get("normalization_policy"),
                    "raw_json": raw_json,
                    "trace_json": trace_json,
                    "raw_first_label": row.get("raw_first_label"),
                    "raw_last_label": row.get("raw_last_label"),
                    "raw_source_refs": list(row.get("raw_source_refs") or []),
                    "source_bar_ids": list(row.get("source_bar_ids") or []),
                    "created_at": created_at or "",
                }
            )
        output[physical_asset_kind] = fact_rows

    quality_summary = {
        "status": "failed" if errors else "passed",
        "row_count_by_asset": {asset_kind: len(rows) for asset_kind, rows in output.items()},
        "object_count_by_asset": {
            asset_kind: len({str(row.get("identity_key") or "") for row in rows if row.get("identity_key")})
            for asset_kind, rows in output.items()
        },
        "expected_full_count": len(canonical_trading_minute_labels("2000-01-03")),
        "error_count": len(errors),
        "blocked_reasons": sorted({str(error.get("reason") or "") for error in errors if error.get("reason")}),
        "source_previous_day_minute_run_id": source_previous_day_minute_run_id,
        "for_trade_date": for_trade_date,
        "source_trade_date": source_trade_date,
        "writes_db": False,
        "writes_outbox": False,
    }
    return normalize_jsonable(
        {
            "rows_by_asset": output,
            "quality_summary": quality_summary,
            "errors": errors,
        }
    )


def current_day_virtual_amount_from_previous_day_cumulative(
    *,
    current_elapsed_amount: float | None,
    previous_day_cumulative_row: Mapping[str, Any] | None,
    current_dt: datetime,
    current_amount_source_kind: str,
) -> tuple[float | None, list[str], dict[str, Any]]:
    trade_date_label = current_dt.strftime("%Y-%m-%d")
    canonical_labels = canonical_trading_minute_labels(trade_date_label)
    current_label = current_dt.strftime("%Y-%m-%d %H:%M")
    elapsed_count = len([label for label in canonical_labels if label <= current_label])
    proof = {
        "status": "passed",
        "metric_policy": VIRTUAL_AMOUNT_POLICY_VERSION,
        "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
        "period": "D",
        "current_elapsed_amount": current_elapsed_amount,
        "current_elapsed_count": elapsed_count,
        "amount_unit": FORMAL_AMOUNT_UNIT,
        "current_period_amount_source_kind": current_amount_source_kind,
        "canonical_minute_policy": CANONICAL_MINUTE_POLICY,
        "previous_day_cumulative_source": True,
    }
    failure_reason = None
    if current_elapsed_amount is None:
        failure_reason = "current_elapsed_amount_missing"
    elif not canonical_labels or current_label not in canonical_labels:
        failure_reason = "current_time_outside_trading_session"
    elif not previous_day_cumulative_row:
        failure_reason = "previous_day_cumulative_row_missing"
    if failure_reason:
        proof["status"] = "failed"
        proof["reason"] = failure_reason
        return None, [], proof

    row = dict(previous_day_cumulative_row or {})
    previous_elapsed_amount = _float_or_none(row.get("previous_day_elapsed_amount"))
    previous_full_amount = _float_or_none(row.get("previous_day_full_amount"))
    row_elapsed_count = int(row.get("elapsed_count") or 0)
    row_full_count = int(row.get("full_count") or 0)
    canonical_full_count = len(canonical_labels)
    proof.update(
        {
            "previous_day_same_elapsed_amount": previous_elapsed_amount,
            "previous_day_same_full_amount": previous_full_amount,
            "previous_day_elapsed_amount": previous_elapsed_amount,
            "previous_day_full_amount": previous_full_amount,
            "elapsed_count": row_elapsed_count,
            "full_count": row_full_count,
            "canonical_minute_label": row.get("canonical_minute_label"),
            "normalization_policy": row.get("normalization_policy"),
            "source_previous_day_minute_run_id": row.get("source_previous_day_minute_run_id"),
            "raw_first_label": row.get("raw_first_label"),
            "raw_last_label": row.get("raw_last_label"),
            "raw_source_refs": list(row.get("raw_source_refs") or []),
            "source_bar_ids": list(row.get("source_bar_ids") or []),
            "previous_day_same_elapsed_refs": [str(row.get("canonical_minute_label") or "")],
            "previous_day_same_full_refs": [str(row.get("raw_first_label") or ""), str(row.get("raw_last_label") or "")],
        }
    )
    if row_elapsed_count != elapsed_count:
        failure_reason = "previous_day_cumulative_elapsed_count_mismatch"
    elif row_full_count != canonical_full_count:
        failure_reason = "previous_day_cumulative_full_window_incomplete"
    elif previous_elapsed_amount is None or previous_elapsed_amount <= 0:
        failure_reason = "previous_day_same_elapsed_amount_non_positive"
    elif previous_full_amount is None or previous_full_amount <= 0:
        failure_reason = "previous_day_same_full_amount_non_positive"
    if failure_reason:
        proof["status"] = "failed"
        proof["reason"] = failure_reason
        return None, [str(row.get("canonical_minute_label") or "")], proof

    current_virtual = float(current_elapsed_amount) / previous_elapsed_amount * previous_full_amount
    proof["current_virtual_amount"] = current_virtual
    return current_virtual, [str(row.get("canonical_minute_label") or "")], proof


def current_day_virtual_amount_from_cumulative_elapsed(
    *,
    current_elapsed_amount: float | None,
    previous_day_rows: Sequence[Mapping[str, Any]],
    current_dt: datetime,
    code: str,
    current_amount_source_kind: str,
) -> tuple[float | None, list[str], dict[str, Any]]:
    trade_date_label = current_dt.strftime("%Y-%m-%d")
    trade_date = current_dt.strftime("%Y%m%d")
    canonical_labels = canonical_trading_minute_labels(trade_date_label)
    current_label = current_dt.strftime("%Y-%m-%d %H:%M")
    elapsed_labels = [label for label in canonical_labels if label <= current_label]
    sorted_previous_rows = sort_minute_rows(previous_day_rows, code=code)
    prev_date = previous_trade_date(sorted_previous_rows, trade_date)
    previous_label_order = [label[-5:] for label in canonical_labels]
    previous_by_hhmm = {
        row["_dt"].strftime("%H:%M"): row
        for row in sorted_previous_rows
        if prev_date is not None and row["_dt"].strftime("%Y%m%d") == prev_date
    }
    previous_full_rows = [previous_by_hhmm[label] for label in previous_label_order if label in previous_by_hhmm]
    previous_elapsed_rows = [previous_by_hhmm[label[-5:]] for label in elapsed_labels if label[-5:] in previous_by_hhmm]
    previous_elapsed_amount = sum(float(row.get("amount") or 0.0) for row in previous_elapsed_rows)
    previous_full_amount = sum(float(row.get("amount") or 0.0) for row in previous_full_rows)
    previous_day_label_normalization_trace: list[dict[str, str]] = []
    seen_normalization_trace: set[tuple[str, str, str]] = set()
    for row in previous_full_rows:
        policy = str(row.get("normalization_policy") or "")
        if not policy:
            continue
        entry = (
            str(row.get("raw_bar_time") or ""),
            str(row.get("canonical_bar_time") or row.get("datetime") or ""),
            policy,
        )
        if entry in seen_normalization_trace:
            continue
        seen_normalization_trace.add(entry)
        previous_day_label_normalization_trace.append(
            {
                "raw_bar_time": entry[0],
                "canonical_bar_time": entry[1],
                "normalization_policy": entry[2],
            }
        )
    proof = {
        "status": "passed",
        "metric_policy": VIRTUAL_AMOUNT_POLICY_VERSION,
        "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
        "period": "D",
        "current_elapsed_amount": current_elapsed_amount,
        "current_elapsed_count": len(elapsed_labels),
        "previous_day_same_elapsed_amount": previous_elapsed_amount,
        "previous_day_same_full_amount": previous_full_amount,
        "amount_unit": FORMAL_AMOUNT_UNIT,
        "current_period_amount_source_kind": current_amount_source_kind,
        "canonical_minute_policy": CANONICAL_MINUTE_POLICY,
        "previous_day_same_elapsed_refs": [str(row["datetime"]) for row in previous_elapsed_rows],
        "previous_day_same_full_refs": [str(row["datetime"]) for row in previous_full_rows],
    }
    if previous_day_label_normalization_trace:
        proof["previous_day_label_normalization_trace"] = previous_day_label_normalization_trace
    failure_reason = None
    if current_elapsed_amount is None:
        failure_reason = "current_elapsed_amount_missing"
    elif not elapsed_labels or current_label not in canonical_labels:
        failure_reason = "current_time_outside_trading_session"
    elif prev_date is None:
        failure_reason = "previous_trade_date_missing"
    elif len(previous_elapsed_rows) < len(elapsed_labels):
        failure_reason = "previous_day_same_elapsed_window_incomplete"
    elif len(previous_full_rows) < len(canonical_labels):
        failure_reason = "previous_day_full_window_incomplete"
    elif previous_elapsed_amount <= 0:
        failure_reason = "previous_day_same_elapsed_amount_non_positive"
    elif previous_full_amount <= 0:
        failure_reason = "previous_day_same_full_amount_non_positive"
    if failure_reason:
        proof["status"] = "failed"
        proof["reason"] = failure_reason
        return None, [str(row["datetime"]) for row in previous_full_rows], proof

    current_virtual = float(current_elapsed_amount) / previous_elapsed_amount * previous_full_amount
    proof["current_virtual_amount"] = current_virtual
    return current_virtual, [str(row["datetime"]) for row in previous_full_rows], proof


def previous_day_same_window_amount(
    rows: Sequence[Mapping[str, Any]],
    *,
    current_dt: datetime,
    period_minutes: int,
) -> tuple[float | None, list[str]]:
    current_trade_date = current_dt.strftime("%Y%m%d")
    prev_date = previous_trade_date(rows, current_trade_date)
    current_seg = segment_index(current_dt, period_minutes)
    if prev_date is None or current_seg is None:
        return None, []
    previous_rows = rows_for_segment(
        rows,
        trade_date=prev_date,
        period_minutes=period_minutes,
        seg_index=current_seg,
    )
    if not previous_rows:
        return None, []
    return sum(float(row.get("amount") or 0.0) for row in previous_rows), [str(row["datetime"]) for row in previous_rows]


def _session_kind(minute_dt: datetime, observed_dt: datetime) -> tuple[str, bool]:
    observed_hm = observed_dt.hour * 60 + observed_dt.minute
    is_auction = (
        minute_dt.hour == 9
        and minute_dt.minute == 31
        and 9 * 60 + 20 <= observed_hm <= 9 * 60 + 30
    )
    if is_auction:
        return "auction", True
    if 11 * 60 + 31 <= observed_hm <= 12 * 60 + 59:
        return "midday", False
    return "regular", False


def _is_closed_1m(minute_dt: datetime, observed_dt: datetime) -> bool:
    return observed_dt >= minute_dt + timedelta(minutes=1)


def _intraday_amount_through(rows: Sequence[Mapping[str, Any]], current_dt: datetime) -> float:
    trade_date = current_dt.strftime("%Y%m%d")
    return sum(
        float(row.get("amount") or 0.0)
        for row in rows
        if row["_dt"].strftime("%Y%m%d") == trade_date and row["_dt"] <= current_dt
    )


def _build_higher_period_fields(
    *,
    current_price: float,
    intraday_amount: float,
    higher_period_context: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    fields: dict[str, Any] = {}
    period_source: dict[str, str] = {}
    context = higher_period_context or {}
    for period in HIGHER_PERIODS:
        db_period = HIGHER_PERIOD_DB_TOKENS[period]
        item = dict(context.get(period) or {})
        current_open = item.get("current_open")
        previous_open = item.get("previous_open")
        previous_close = item.get("previous_close")
        previous_amount = item.get("previous_amount")
        elapsed_units = float(item.get("elapsed_units") or 0.0)
        total_units = float(item.get("total_units") or 0.0)
        current_amount_seed = float(item.get("current_amount_seed") or 0.0)

        if current_open is None:
            fields[f"current_{db_period}_body_high"] = None
            fields[f"current_{db_period}_body_low"] = None
        else:
            current_open_f = float(current_open)
            fields[f"current_{db_period}_body_high"] = max(current_open_f, current_price)
            fields[f"current_{db_period}_body_low"] = min(current_open_f, current_price)

        if previous_open is None or previous_close is None:
            fields[f"previous_{db_period}_body_high"] = None
            fields[f"previous_{db_period}_body_low"] = None
        else:
            previous_open_f = float(previous_open)
            previous_close_f = float(previous_close)
            fields[f"previous_{db_period}_body_high"] = max(previous_open_f, previous_close_f)
            fields[f"previous_{db_period}_body_low"] = min(previous_open_f, previous_close_f)

        if elapsed_units > 0 and total_units > 0:
            fields[f"current_{db_period}_virtual_amount"] = (current_amount_seed + intraday_amount) / elapsed_units * total_units
            period_source[period] = "n2_period_context_plus_intraday_1m"
        else:
            fields[f"current_{db_period}_virtual_amount"] = None
            period_source[period] = "missing_n2_period_context"
        fields[f"previous_{db_period}_amount"] = float(previous_amount) if previous_amount is not None else None
    return fields, period_source


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _thousand_yuan_to_yuan(value: float | None) -> float | None:
    if value is None:
        return None
    return value * FORMAL_AMOUNT_UNIT_CONVERSION_FACTOR


def formal_amount_unit_rule_for_asset_kind(asset_kind: str | None = "stock") -> dict[str, Any]:
    normalized = str(asset_kind or "stock").strip().lower()
    source_unit = FORMAL_AMOUNT_SOURCE_UNIT_BY_ASSET_KIND.get(normalized)
    if source_unit is None:
        raise ValueError(f"unsupported formal amount asset_kind: {asset_kind}")
    factor = FORMAL_AMOUNT_UNIT_CONVERSION_FACTOR if source_unit == "thousand_yuan" else 1.0
    policy = (
        FORMAL_AMOUNT_UNIT_CONVERSION_POLICY
        if source_unit == "thousand_yuan"
        else FORMAL_AMOUNT_YUAN_PASSTHROUGH_POLICY
    )
    return {
        "asset_kind": normalized,
        "source_amount_unit": source_unit,
        "canonical_amount_unit": FORMAL_AMOUNT_UNIT,
        "unit_conversion_factor": factor,
        "unit_conversion_policy": policy,
        "amount_unit_source": FORMAL_AMOUNT_UNIT_SOURCE_POLICY,
        # The N4 matcher already accepts true-full-day yuan passthrough proofs
        # through schema inference when amount_rule is omitted.
        "amount_rule": FORMAL_AMOUNT_RULE if source_unit == "thousand_yuan" else None,
    }


def convert_formal_source_amount_to_yuan(
    value: Any,
    *,
    asset_kind: str | None = "stock",
    amount_unit_rule: Mapping[str, Any] | None = None,
) -> float | None:
    number = _float_or_none(value)
    if number is None:
        return None
    rule = dict(amount_unit_rule or formal_amount_unit_rule_for_asset_kind(asset_kind))
    return number * float(rule["unit_conversion_factor"])


def _positive_float_or_none(value: Any) -> float | None:
    number = _float_or_none(value)
    if number is None or number <= 0:
        return None
    return number


def _build_formal_amount_chain_fields(
    *,
    today_virt_amount: float | None,
    higher_period_context: Mapping[str, Mapping[str, Any]] | None,
    asset_kind: str | None = "stock",
) -> tuple[dict[str, Any], dict[str, Any]]:
    context = higher_period_context or {}
    unit_rule = formal_amount_unit_rule_for_asset_kind(asset_kind)
    metrics: dict[str, Any] = {"today_virt_amount": today_virt_amount}
    period_proofs: dict[str, dict[str, Any]] = {}
    for period, (avg_field, previous_avg_field) in FORMAL_AMOUNT_AVG_FIELDS.items():
        item = dict(context.get(period) or {})
        current_amount_seed = _float_or_none(item.get("current_amount_seed"))
        current_amount_total_seed = _float_or_none(item.get("current_amount_total_seed"))
        if item.get("period_seed_applied") is False:
            current_trade_days_seed = _float_or_none(item.get("current_trade_days_seed"))
        else:
            current_trade_days_seed = _positive_float_or_none(item.get("current_trade_days_seed"))
        previous_amount = _float_or_none(item.get("previous_amount"))
        previous_avg_amount = _float_or_none(item.get("previous_avg_amount"))
        total_units = _positive_float_or_none(item.get("total_units"))
        current_amount_total_seed_source = "missing_current_amount_seed"
        if current_amount_total_seed is not None:
            current_amount_total_seed_yuan = convert_formal_source_amount_to_yuan(
                current_amount_total_seed,
                amount_unit_rule=unit_rule,
            )
            current_amount_total_seed_source = "current_amount_total_seed"
        elif current_amount_seed is not None and current_trade_days_seed is not None:
            current_amount_total_seed_yuan = convert_formal_source_amount_to_yuan(
                current_amount_seed * current_trade_days_seed,
                amount_unit_rule=unit_rule,
            )
            current_amount_total_seed_source = "current_amount_seed_x_current_trade_days_seed"
        else:
            current_amount_total_seed_yuan = None

        with_today_units = current_trade_days_seed + 1.0 if current_trade_days_seed is not None else None
        avg_blocked_reason = None
        if today_virt_amount is None:
            avg_blocked_reason = "missing_today_virt_amount"
        elif current_trade_days_seed is None:
            avg_blocked_reason = "missing_current_trade_days_seed"
        elif current_amount_total_seed_yuan is None:
            avg_blocked_reason = current_amount_total_seed_source
        elif with_today_units is None or with_today_units <= 0:
            avg_blocked_reason = "invalid_with_today_units"

        if avg_blocked_reason is None and with_today_units is not None and current_amount_total_seed_yuan is not None:
            metrics[avg_field] = (current_amount_total_seed_yuan + today_virt_amount) / with_today_units
            avg_status = "passed"
        else:
            metrics[avg_field] = None
            avg_status = "failed"

        if previous_avg_amount is not None:
            previous_avg_amount_yuan = convert_formal_source_amount_to_yuan(
                previous_avg_amount,
                amount_unit_rule=unit_rule,
            )
            metrics[previous_avg_field] = previous_avg_amount_yuan
            previous_avg_source = "previous_avg_amount"
        elif previous_amount is not None and total_units is not None:
            previous_avg_amount_yuan = convert_formal_source_amount_to_yuan(
                previous_amount / total_units,
                amount_unit_rule=unit_rule,
            )
            metrics[previous_avg_field] = previous_avg_amount_yuan
            previous_avg_source = "previous_amount_div_total_units"
        else:
            previous_avg_amount_yuan = None
            metrics[previous_avg_field] = None
            previous_avg_source = "missing_previous_amount_or_total_units"
        period_proofs[period] = {
            "current_amount_source_kind": FORMAL_AMOUNT_SOURCE_KIND,
            "asset_kind": unit_rule["asset_kind"],
            "current_amount_unit": FORMAL_AMOUNT_UNIT,
            "source_amount_unit": unit_rule["source_amount_unit"],
            "proof_source_amount_unit": unit_rule["source_amount_unit"],
            "amount_unit": FORMAL_AMOUNT_UNIT,
            "proof_canonical_amount_unit": unit_rule["canonical_amount_unit"],
            "unit_conversion_factor": unit_rule["unit_conversion_factor"],
            "proof_unit_conversion_factor": unit_rule["unit_conversion_factor"],
            "unit_conversion_policy": unit_rule["unit_conversion_policy"],
            "proof_amount_unit_source": unit_rule["amount_unit_source"],
            "current_price_field": "current_price",
            "amount_rule": unit_rule["amount_rule"],
            "avg_field": avg_field,
            "previous_avg_field": previous_avg_field,
            "avg_status": avg_status,
            "avg_blocked_reason": avg_blocked_reason,
            "previous_avg_source": previous_avg_source,
            "current_amount_seed": current_amount_seed,
            "current_amount_seed_yuan": convert_formal_source_amount_to_yuan(
                current_amount_seed,
                amount_unit_rule=unit_rule,
            ),
            "current_amount_total_seed": current_amount_total_seed,
            "current_amount_total_seed_yuan": current_amount_total_seed_yuan,
            "current_amount_total_seed_source": current_amount_total_seed_source,
            "today_virt_amount": today_virt_amount,
            "today_virt_amount_yuan": today_virt_amount,
            "current_trade_days_seed": current_trade_days_seed,
            "with_today_units": with_today_units,
            "total_units": total_units,
            "previous_amount": previous_amount,
            "previous_avg_amount": previous_avg_amount,
            "previous_avg_amount_yuan": previous_avg_amount_yuan,
            "with_today_units_policy": "current_trade_days_seed_plus_one",
        }
    proof = {
        "source_kind": FORMAL_AMOUNT_SOURCE_KIND,
        "asset_kind": unit_rule["asset_kind"],
        "amount_unit": FORMAL_AMOUNT_UNIT,
        "source_amount_unit": unit_rule["source_amount_unit"],
        "proof_source_amount_unit": unit_rule["source_amount_unit"],
        "proof_canonical_amount_unit": unit_rule["canonical_amount_unit"],
        "unit_conversion_factor": unit_rule["unit_conversion_factor"],
        "proof_unit_conversion_factor": unit_rule["unit_conversion_factor"],
        "unit_conversion_policy": unit_rule["unit_conversion_policy"],
        "proof_amount_unit_source": unit_rule["amount_unit_source"],
        "amount_rule": unit_rule["amount_rule"],
        "amount_chain_metrics": dict(metrics),
        "periods": period_proofs,
    }
    return metrics, proof


def _amount_buy_pass(current: float | None, previous: float | None, first_period: bool) -> bool:
    if first_period:
        return True
    return current is not None and previous is not None and current > previous


def _amount_sell_pass(current: float | None, previous: float | None, first_period: bool) -> bool:
    if first_period:
        return True
    return current is not None and previous is not None and current < previous


def _deterministic_pass_flags(metric: Mapping[str, Any]) -> dict[str, dict[str, bool]]:
    price = metric.get("current_price")
    if price is None:
        price = 0.0
    price_f = float(price)
    current_1m_amount = metric.get("current_1m_amount")
    previous_1m_amount = metric.get("previous_1m_amount")
    current_5m_amount = metric.get("current_5m_virtual_amount")
    previous_5m_amount = metric.get("previous_5m_full_amount")

    return {
        "B_BUY": {
            "buy_120m_price_pass": price_f > float(metric.get("previous_120m_body_high") or float("inf")),
            "buy_30m_price_pass": price_f > float(metric.get("previous_30m_body_high") or float("inf")),
            "buy_5m_price_pass": price_f > float(metric.get("previous_5m_body_high") or float("inf")),
            "buy_1m_price_pass": price_f > float(metric.get("previous_1m_body_high") or float("inf")),
            "buy_5m_amount_pass": _amount_buy_pass(
                float(current_5m_amount) if current_5m_amount is not None else None,
                float(previous_5m_amount) if previous_5m_amount is not None else None,
                bool(metric.get("is_first_5m_of_day")),
            ),
            "buy_1m_amount_pass": _amount_buy_pass(
                float(current_1m_amount) if current_1m_amount is not None else None,
                float(previous_1m_amount) if previous_1m_amount is not None else None,
                bool(metric.get("is_first_1m_of_day")),
            ),
        },
        "S_SELL": {
            "sell_120m_price_pass": price_f < float(metric.get("previous_120m_body_low") or float("-inf")),
            "sell_30m_price_pass": price_f < float(metric.get("previous_30m_body_low") or float("-inf")),
            "sell_5m_price_pass": price_f < float(metric.get("previous_5m_body_low") or float("-inf")),
            "sell_1m_price_pass": price_f < float(metric.get("previous_1m_body_low") or float("-inf")),
            "sell_5m_amount_pass": _amount_sell_pass(
                float(current_5m_amount) if current_5m_amount is not None else None,
                float(previous_5m_amount) if previous_5m_amount is not None else None,
                bool(metric.get("is_first_5m_of_day")),
            ),
            "sell_1m_amount_pass": _amount_sell_pass(
                float(current_1m_amount) if current_1m_amount is not None else None,
                float(previous_1m_amount) if previous_1m_amount is not None else None,
                bool(metric.get("is_first_1m_of_day")),
            ),
        },
    }


def build_realtime_trigger_proof_metric_from_elapsed_amount(
    *,
    code: str,
    minute_label: str,
    observed_at: str | datetime | None,
    current_price: Any,
    current_open: Any = None,
    current_high: Any = None,
    current_low: Any = None,
    current_elapsed_amount: Any = None,
    current_amount_source_kind: str,
    previous_day_rows: Sequence[Mapping[str, Any]],
    previous_day_cumulative_row: Mapping[str, Any] | None = None,
    source_minute_refs: Sequence[str] | None = None,
    higher_period_context: Mapping[str, Mapping[str, Any]] | None = None,
    asset_kind: str | None = "stock",
    source_trace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    target_dt = parse_minute(minute_label)
    observed_dt = parse_observed_at(observed_at, target_dt)
    current_price_f = _float_or_none(current_price)
    current_open_f = _float_or_none(current_open)
    current_high_f = _float_or_none(current_high)
    current_low_f = _float_or_none(current_low)
    current_elapsed_amount_f = _float_or_none(current_elapsed_amount)
    source_trace_map = dict(source_trace or {})
    missing_current_fields = []
    if current_price_f is None:
        missing_current_fields.append("current_price_missing")
    if current_elapsed_amount_f is None:
        missing_current_fields.append("current_amount_missing")

    if previous_day_cumulative_row:
        today_virt_amount, previous_day_refs, today_virt_proof = current_day_virtual_amount_from_previous_day_cumulative(
            current_elapsed_amount=current_elapsed_amount_f,
            previous_day_cumulative_row=previous_day_cumulative_row,
            current_dt=target_dt,
            current_amount_source_kind=current_amount_source_kind,
        )
    else:
        today_virt_amount, previous_day_refs, today_virt_proof = current_day_virtual_amount_from_cumulative_elapsed(
            current_elapsed_amount=current_elapsed_amount_f,
            previous_day_rows=previous_day_rows,
            current_dt=target_dt,
            code=code,
            current_amount_source_kind=current_amount_source_kind,
        )
    source_blocked_reasons = [
        str(reason)
        for reason in source_trace_map.get("source_blocked_reasons", [])
        if str(reason or "")
    ]
    blocked = list(dict.fromkeys([*missing_current_fields, *source_blocked_reasons]))
    if today_virt_proof.get("status") != "passed":
        blocked.append(f"today_virtual_amount_calibration_failed:{today_virt_proof.get('reason')}")

    price_for_fields = current_price_f if current_price_f is not None else 0.0
    amount_for_fields = current_elapsed_amount_f or 0.0
    higher_fields, higher_period_source = _build_higher_period_fields(
        current_price=price_for_fields,
        intraday_amount=amount_for_fields,
        higher_period_context=higher_period_context,
    )
    formal_amount_chain_metrics, formal_amount_proof = _build_formal_amount_chain_fields(
        today_virt_amount=today_virt_amount,
        higher_period_context=higher_period_context,
        asset_kind=asset_kind,
    )
    session_kind, is_auction_virtual = _session_kind(target_dt, observed_dt)
    metric = {
        "code": code,
        "metric_time_label": minute_label,
        "metric_minute_label": minute_label,
        "snapshot_id": None,
        "event_id": None,
        "source_time": minute_label,
        "observed_at": observed_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "session_kind": session_kind,
        "period_source": {
            "1m": "not_required_for_trigger_proof",
            "5m": "not_required_for_trigger_proof",
            "30m": "not_required_for_trigger_proof",
            "120m": "not_required_for_trigger_proof",
            **higher_period_source,
        },
        "is_closed_1m": _is_closed_1m(target_dt, observed_dt),
        "is_auction_virtual": is_auction_virtual,
        "midday_bridge_policy": None,
        "metric_ready": not blocked,
        "quality_status": "passed" if not blocked else "failed",
        "blocked_reasons": blocked,
        "current_price": current_price_f,
        "current_price_source": current_amount_source_kind.replace("_amount", "_price"),
        "current_price_time": minute_label,
        "current_1m_amount": current_elapsed_amount_f,
        "previous_1m_amount": None,
        "current_1m_body_high": max(v for v in (current_open_f, current_price_f) if v is not None)
        if current_price_f is not None or current_open_f is not None
        else None,
        "current_1m_body_low": min(v for v in (current_open_f, current_price_f) if v is not None)
        if current_price_f is not None or current_open_f is not None
        else None,
        "previous_1m_body_high": None,
        "previous_1m_body_low": None,
        "current_5m_body_high": current_high_f,
        "current_5m_body_low": current_low_f,
        "previous_5m_body_high": None,
        "previous_5m_body_low": None,
        "current_30m_body_high": current_high_f,
        "current_30m_body_low": current_low_f,
        "previous_30m_body_high": None,
        "previous_30m_body_low": None,
        "current_120m_body_high": current_high_f,
        "current_120m_body_low": current_low_f,
        "previous_120m_body_high": None,
        "previous_120m_body_low": None,
        "current_5m_virtual_amount": None,
        "previous_5m_full_amount": None,
        "previous_day_same_5m_full_amount": None,
        "current_30m_virtual_amount": None,
        "previous_day_same_window_amount": None,
        "previous_day_same_30m_full_amount": None,
        "virtual_amount_policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
        "previous_30m_full_amount": None,
        "current_120m_virtual_amount": None,
        "previous_120m_full_amount": None,
        "is_first_1m_of_day": minute_label.endswith("09:31"),
        "is_first_5m_of_day": segment_index(target_dt, 5) == 0,
        "is_first_30m_of_day": segment_index(target_dt, 30) == 0,
        "is_first_120m_of_day": segment_index(target_dt, 120) == 0,
        "first_1m_amount_default_pass": minute_label.endswith("09:31"),
        "first_5m_amount_default_pass": segment_index(target_dt, 5) == 0,
        "previous_1m_period_source": "not_required_for_trigger_proof",
        "previous_5m_period_source": "not_required_for_trigger_proof",
        "previous_30m_period_source": "not_required_for_trigger_proof",
        "previous_120m_period_source": "not_required_for_trigger_proof",
        "boundary_policy_version": "v3.realtime_virtual_metric.boundary.trigger_proof_v1",
        "source_minute_refs": list(source_minute_refs or [minute_label]),
        "previous_day_minute_refs": sorted(set(previous_day_refs)),
        "trace_json": {
            "builder": "ashare_v3.market.realtime_virtual_metric.build_realtime_trigger_proof_metric_from_elapsed_amount",
            "higher_period_context_periods": sorted((higher_period_context or {}).keys()),
            "display_alias_to_db_column": dict(REALTIME_VIRTUAL_METRIC_FIELD_ALIASES),
            "formal_amount_chain_metrics": dict(formal_amount_chain_metrics),
            "formal_period_amount_proof": formal_amount_proof,
            "virtual_amount_policy": {
                "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
                "periods": {
                    "D": today_virt_proof,
                    "5m": {"status": "not_required_for_trigger_proof"},
                    "30m": {"status": "not_required_for_trigger_proof"},
                    "120m": {"status": "not_required_for_trigger_proof"},
                },
            },
            "source_trace": source_trace_map,
        },
        "raw_json": {
            "source": "n3_realtime_trigger_proof_metric",
            "canonical_minute_policy": CANONICAL_MINUTE_POLICY,
            "virtual_amount_policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
            "formal_amount_chain_metrics": dict(formal_amount_chain_metrics),
            "n3p_realtime_source_model": "n3p_trigger_proof_realtime_v1",
            "amount_source_kind": current_amount_source_kind,
            **source_trace_map,
        },
        **formal_amount_chain_metrics,
        **higher_fields,
    }
    metric["deterministic_pass_flags"] = _deterministic_pass_flags(metric)
    return normalize_jsonable(metric)


def build_realtime_virtual_metric(
    rows: Sequence[Mapping[str, Any]],
    *,
    code: str,
    minute_label: str,
    observed_at: str | datetime | None = None,
    higher_period_context: Mapping[str, Mapping[str, Any]] | None = None,
    asset_kind: str | None = "stock",
) -> dict[str, Any]:
    sorted_rows = sort_minute_rows(rows, code=code)
    target_dt = parse_minute(minute_label)
    observed_dt = parse_observed_at(observed_at, target_dt)
    target_rows = [row for row in sorted_rows if row["_dt"] == target_dt]
    if not target_rows:
        return normalize_jsonable(
            {
                "code": code,
                "metric_time_label": minute_label,
                "metric_ready": False,
                "quality_status": "failed",
                "blocked_reasons": ["current_1m_not_found"],
            }
        )

    current = target_rows[-1]
    current_price = _float_or_none(current.get("close"))
    current_amount = _float_or_none(current.get("amount"))
    missing_current_fields = []
    if current_price is None:
        missing_current_fields.append("current_price_missing")
    if current_amount is None:
        missing_current_fields.append("current_amount_missing")
    if missing_current_fields:
        return normalize_jsonable(
            {
                "code": code,
                "metric_time_label": minute_label,
                "metric_minute_label": minute_label,
                "source_time": minute_label,
                "observed_at": observed_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "metric_ready": False,
                "quality_status": "failed",
                "blocked_reasons": missing_current_fields,
                "current_price": current_price,
                "current_price_source": "n3_realtime_virtual_metric.current_1m.close",
                "current_price_time": minute_label,
                "current_1m_amount": current_amount,
                "source_minute_refs": [minute_label],
                "previous_day_minute_refs": [],
                "trace_json": {
                    "builder": "ashare_v3.market.realtime_virtual_metric.build_realtime_virtual_metric",
                    "blocked_reasons": missing_current_fields,
                },
                "raw_json": {
                    "source": "n3_realtime_virtual_metric",
                    "blocked_reasons": missing_current_fields,
                },
            }
        )
    previous_1m, previous_1m_source = previous_minute_row(sorted_rows, target_dt)
    previous_5m, previous_5m_source = previous_segment_aggregate(sorted_rows, current_dt=target_dt, period_minutes=5)
    previous_30m, previous_30m_source = previous_segment_aggregate(sorted_rows, current_dt=target_dt, period_minutes=30)
    previous_120m, previous_120m_source = previous_segment_aggregate(sorted_rows, current_dt=target_dt, period_minutes=120)
    current_5m_virtual, previous_5m_full, current_5m_refs, current_5m_virtual_proof = current_period_virtual_amount(
        sorted_rows, current_dt=target_dt, period_minutes=5
    )
    current_30m_virtual, previous_30m_full, current_30m_refs, current_30m_virtual_proof = current_period_virtual_amount(
        sorted_rows, current_dt=target_dt, period_minutes=30
    )
    previous_day_same_30m_amount, previous_day_same_30m_refs = previous_day_same_window_amount(
        sorted_rows,
        current_dt=target_dt,
        period_minutes=30,
    )
    current_120m_virtual, previous_120m_full, current_120m_refs, current_120m_virtual_proof = current_period_virtual_amount(
        sorted_rows, current_dt=target_dt, period_minutes=120
    )
    today_virt_amount, today_virt_refs, today_virt_proof = current_day_virtual_amount(
        sorted_rows,
        current_dt=target_dt,
    )

    blocked = []
    for name, value in (
        ("previous_1m", previous_1m),
        ("previous_5m", previous_5m),
        ("previous_30m", previous_30m),
        ("previous_120m", previous_120m),
    ):
        if value is None:
            blocked.append(f"{name}_not_found")
    for period_label, proof in (
        ("5m", current_5m_virtual_proof),
        ("30m", current_30m_virtual_proof),
    ):
        if proof.get("status") != "passed":
            blocked.append(f"current_{period_label}_virtual_amount_calibration_failed:{proof.get('reason')}")

    intraday_amount = _intraday_amount_through(sorted_rows, target_dt)
    higher_fields, higher_period_source = _build_higher_period_fields(
        current_price=current_price,
        intraday_amount=intraday_amount,
        higher_period_context=higher_period_context,
    )
    formal_amount_chain_metrics, formal_amount_proof = _build_formal_amount_chain_fields(
        today_virt_amount=today_virt_amount,
        higher_period_context=higher_period_context,
        asset_kind=asset_kind,
    )
    session_kind, is_auction_virtual = _session_kind(target_dt, observed_dt)
    midday_bridge_policy = None
    current_5m_seg = segment_index(target_dt, 5)
    current_30m_seg = segment_index(target_dt, 30)
    current_120m_seg = segment_index(target_dt, 120)
    previous_day_minute_refs = previous_day_refs_for_sources(
        (previous_1m, previous_1m_source),
        (previous_5m, previous_5m_source),
        (previous_30m, previous_30m_source),
        (previous_120m, previous_120m_source),
    )

    period_source = {
        "1m": previous_1m_source,
        "5m": previous_5m_source,
        "30m": previous_30m_source,
        "120m": previous_120m_source,
        **higher_period_source,
    }
    metric = {
        "code": code,
        "metric_time_label": minute_label,
        "metric_minute_label": minute_label,
        "snapshot_id": None,
        "event_id": None,
        "source_time": minute_label,
        "observed_at": observed_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "session_kind": session_kind,
        "period_source": period_source,
        "is_closed_1m": _is_closed_1m(target_dt, observed_dt),
        "is_auction_virtual": is_auction_virtual,
        "midday_bridge_policy": midday_bridge_policy,
        "metric_ready": not blocked,
        "quality_status": "passed" if not blocked else "failed",
        "blocked_reasons": blocked,
        "current_price": current_price,
        "current_price_source": "n3_realtime_virtual_metric.current_1m.close",
        "current_price_time": minute_label,
        "current_1m_amount": float(current["amount"]),
        "previous_1m_amount": float(previous_1m["amount"]) if previous_1m else None,
        "current_1m_body_high": body_high(current),
        "current_1m_body_low": body_low(current),
        "previous_1m_body_high": body_high(previous_1m) if previous_1m else None,
        "previous_1m_body_low": body_low(previous_1m) if previous_1m else None,
        "current_5m_body_high": aggregate_segment(
            rows_for_segment(sorted_rows, trade_date=target_dt.strftime("%Y%m%d"), period_minutes=5, seg_index=segment_index(target_dt, 5) or 0, through=target_dt)
        )["body_high"],
        "current_5m_body_low": aggregate_segment(
            rows_for_segment(sorted_rows, trade_date=target_dt.strftime("%Y%m%d"), period_minutes=5, seg_index=segment_index(target_dt, 5) or 0, through=target_dt)
        )["body_low"],
        "previous_5m_body_high": previous_5m["body_high"] if previous_5m else None,
        "previous_5m_body_low": previous_5m["body_low"] if previous_5m else None,
        "current_30m_body_high": aggregate_segment(
            rows_for_segment(sorted_rows, trade_date=target_dt.strftime("%Y%m%d"), period_minutes=30, seg_index=segment_index(target_dt, 30) or 0, through=target_dt)
        )["body_high"],
        "current_30m_body_low": aggregate_segment(
            rows_for_segment(sorted_rows, trade_date=target_dt.strftime("%Y%m%d"), period_minutes=30, seg_index=segment_index(target_dt, 30) or 0, through=target_dt)
        )["body_low"],
        "previous_30m_body_high": previous_30m["body_high"] if previous_30m else None,
        "previous_30m_body_low": previous_30m["body_low"] if previous_30m else None,
        "current_120m_body_high": aggregate_segment(
            rows_for_segment(sorted_rows, trade_date=target_dt.strftime("%Y%m%d"), period_minutes=120, seg_index=segment_index(target_dt, 120) or 0, through=target_dt)
        )["body_high"],
        "current_120m_body_low": aggregate_segment(
            rows_for_segment(sorted_rows, trade_date=target_dt.strftime("%Y%m%d"), period_minutes=120, seg_index=segment_index(target_dt, 120) or 0, through=target_dt)
        )["body_low"],
        "previous_120m_body_high": previous_120m["body_high"] if previous_120m else None,
        "previous_120m_body_low": previous_120m["body_low"] if previous_120m else None,
        "current_5m_virtual_amount": current_5m_virtual,
        "previous_5m_full_amount": float(previous_5m["amount"]) if previous_5m else previous_5m_full,
        "previous_day_same_5m_full_amount": current_5m_virtual_proof.get("previous_day_same_full_amount")
        if current_5m_virtual_proof.get("status") == "passed"
        else None,
        "current_30m_virtual_amount": current_30m_virtual,
        "previous_day_same_window_amount": previous_day_same_30m_amount,
        "previous_day_same_30m_full_amount": current_30m_virtual_proof.get("previous_day_same_full_amount")
        if current_30m_virtual_proof.get("status") == "passed"
        else None,
        "virtual_amount_policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
        "previous_30m_full_amount": previous_30m_full,
        "current_120m_virtual_amount": current_120m_virtual,
        "previous_120m_full_amount": previous_120m_full,
        "is_first_1m_of_day": minute_index(target_dt) == 1,
        "is_first_5m_of_day": current_5m_seg == 0,
        "is_first_30m_of_day": current_30m_seg == 0,
        "is_first_120m_of_day": current_120m_seg == 0,
        "first_1m_amount_default_pass": minute_index(target_dt) == 1,
        "first_5m_amount_default_pass": current_5m_seg == 0,
        "previous_1m_period_source": previous_1m_source,
        "previous_5m_period_source": previous_5m_source,
        "previous_30m_period_source": previous_30m_source,
        "previous_120m_period_source": previous_120m_source,
        "boundary_policy_version": "v3.realtime_virtual_metric.boundary.v1",
        "source_minute_refs": sorted(set([minute_label, *current_5m_refs, *current_30m_refs, *current_120m_refs])),
        "previous_day_minute_refs": sorted(
            set(
                [
                    *previous_day_minute_refs,
                    *previous_day_same_30m_refs,
                    *current_5m_virtual_proof.get("previous_day_same_full_refs", []),
                    *current_30m_virtual_proof.get("previous_day_same_full_refs", []),
                    *today_virt_proof.get("previous_day_same_full_refs", []),
                ]
            )
        ),
        "trace_json": {
            "builder": "ashare_v3.market.realtime_virtual_metric.build_realtime_virtual_metric",
            "higher_period_context_periods": sorted((higher_period_context or {}).keys()),
            "display_alias_to_db_column": dict(REALTIME_VIRTUAL_METRIC_FIELD_ALIASES),
            "formal_amount_chain_metrics": dict(formal_amount_chain_metrics),
            "formal_period_amount_proof": formal_amount_proof,
            "virtual_amount_policy": {
                "policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
                "periods": {
                    "D": today_virt_proof,
                    "5m": current_5m_virtual_proof,
                    "30m": current_30m_virtual_proof,
                    "120m": current_120m_virtual_proof,
                },
            },
        },
        "raw_json": {
            "source": "n3_realtime_virtual_metric",
            "auction_policy": "mootdx_0931_label_as_auction_realtime_virtual_1m",
            "canonical_minute_policy": CANONICAL_MINUTE_POLICY,
            "virtual_amount_policy_version": VIRTUAL_AMOUNT_POLICY_VERSION,
            "formal_amount_chain_metrics": dict(formal_amount_chain_metrics),
        },
        **formal_amount_chain_metrics,
        **higher_fields,
    }
    metric["deterministic_pass_flags"] = _deterministic_pass_flags(metric)
    return normalize_jsonable(metric)
