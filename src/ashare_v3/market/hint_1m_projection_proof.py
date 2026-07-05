"""N3 index/board 1m forming-30m hint projection proof helpers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping, Sequence


HINT_1M_PROOF_KIND = "index_board_1m_hint_projection_v1"
HINT_1M_SOURCE_MODE = "index_board_frequency8_1m"
HINT_1M_METRIC_ROLE = "hint_trigger_proof"
HINT_1M_PROOF_OWNER = "N3"
HINT_1M_PROOF_CONSUMER = "N4"
HINT_1M_ASSET_SCOPE = "index_board_only"
HINT_1M_SOURCE_MARKER = "mootdx_index_frequency_8"
HINT_1M_MIDDAY_BRIDGE_POLICY = "hint_1300_as_1130_close_v1"
HINT_1M_MIDDAY_RAW_LABEL = "13:00"
HINT_1M_MIDDAY_LOGICAL_LABEL = "11:30"

CANONICAL_30M_WINDOWS: tuple[tuple[str, str], ...] = (
    ("09:31", "10:00"),
    ("10:01", "10:30"),
    ("10:31", "11:00"),
    ("11:01", "11:30"),
    ("13:01", "13:30"),
    ("13:31", "14:00"),
    ("14:01", "14:30"),
    ("14:31", "15:00"),
)


def index_board_hint_30m_window_for_minute(proof_input_time: Any) -> dict[str, Any]:
    proof_label = _hhmm(proof_input_time)
    if proof_label == HINT_1M_MIDDAY_LOGICAL_LABEL:
        raise ValueError("proof_input_time_canonical_1130_forbidden")
    midday_bridge = proof_label == HINT_1M_MIDDAY_RAW_LABEL
    logical_proof_label = HINT_1M_MIDDAY_LOGICAL_LABEL if midday_bridge else proof_label
    for index, (start, end) in enumerate(CANONICAL_30M_WINDOWS):
        full_labels = _labels_between(start, end)
        if logical_proof_label in full_labels:
            previous = CANONICAL_30M_WINDOWS[index - 1] if index > 0 else None
            elapsed_labels = full_labels[: full_labels.index(logical_proof_label) + 1]
            raw_elapsed_labels = _raw_labels_for_logical_labels(elapsed_labels, bridge_midday=midday_bridge)
            return {
                "proof_input_minute_label": proof_label,
                "current_window_start": start,
                "current_window_end": end,
                "previous_completed_window_start": previous[0] if previous else None,
                "previous_completed_window_end": previous[1] if previous else None,
                "elapsed_labels": elapsed_labels,
                "full_window_labels": full_labels,
                "closed_status": "projected" if logical_proof_label != end else "closed",
                "midday_bridge_policy": HINT_1M_MIDDAY_BRIDGE_POLICY if midday_bridge else None,
                "raw_minute_label": proof_label,
                "logical_minute_label": logical_proof_label,
                "current_window_raw_elapsed_labels": raw_elapsed_labels,
                "current_window_logical_elapsed_labels": list(elapsed_labels),
            }
    raise ValueError("proof_input_time_outside_canonical_30m_windows")


def build_index_board_1m_hint_projection_proof(
    *,
    asset_kind: str,
    identity_key: str,
    for_trade_date: str,
    previous_trade_date: str,
    proof_input_time: Any,
    current_day_1m_rows: Sequence[Mapping[str, Any]],
    previous_day_1m_rows: Sequence[Mapping[str, Any]],
    projection_run_id: str | None = None,
    projection_id: Any = None,
) -> dict[str, Any]:
    base = _base_proof(
        asset_kind=asset_kind,
        identity_key=identity_key,
        for_trade_date=for_trade_date,
        previous_trade_date=previous_trade_date,
        proof_input_time=proof_input_time,
        projection_run_id=projection_run_id,
        projection_id=projection_id,
    )
    if asset_kind not in {"index", "board"}:
        return _blocked(base, "asset_kind_not_applicable", not_ready_classification="not_applicable")

    try:
        window = index_board_hint_30m_window_for_minute(proof_input_time)
    except ValueError as exc:
        return _blocked(base, str(exc))
    base.update({key: value for key, value in window.items() if key != "elapsed_labels" and key != "full_window_labels"})
    base["current_window_elapsed_count"] = len(window["elapsed_labels"])
    base["full_window_count"] = len(window["full_window_labels"])
    base["current_window_elapsed_labels"] = list(window["elapsed_labels"])
    base["current_window_full_labels"] = list(window["full_window_labels"])

    previous_start = window.get("previous_completed_window_start")
    previous_end = window.get("previous_completed_window_end")
    if not previous_start or not previous_end:
        return _blocked(base, "first_30m_window_no_previous_completed_window")

    current_by_label, current_reasons = _rows_by_label(
        current_day_1m_rows,
        asset_kind=asset_kind,
        identity_key=identity_key,
        trade_date=for_trade_date,
        allow_midday_bridge=True,
        allow_logical_1130=False,
    )
    previous_by_label, previous_reasons = _rows_by_label(
        previous_day_1m_rows,
        asset_kind=asset_kind,
        identity_key=identity_key,
        trade_date=previous_trade_date,
        allow_midday_bridge=True,
        allow_logical_1130=True,
    )
    blocked_reasons = [*current_reasons, *previous_reasons]

    elapsed_labels = list(window["elapsed_labels"])
    full_labels = list(window["full_window_labels"])
    previous_completed_labels = _labels_between(str(previous_start), str(previous_end))
    missing_current = [label for label in elapsed_labels if label not in current_by_label]
    if missing_current:
        blocked_reasons.append("missing_current_day_1m_rows")
    if previous_completed_labels[0] not in current_by_label or previous_completed_labels[-1] not in current_by_label:
        blocked_reasons.append("missing_previous_completed_30m_open_close")
    missing_previous_elapsed = [label for label in elapsed_labels if label not in previous_by_label]
    if missing_previous_elapsed:
        blocked_reasons.append("missing_previous_day_same_elapsed_rows")
    missing_previous_full = [label for label in full_labels if label not in previous_by_label]
    if missing_previous_full:
        blocked_reasons.append("missing_previous_day_full_30m_rows")
    if blocked_reasons:
        return _blocked(base, *blocked_reasons)

    current_elapsed_amount, current_amount_missing = _sum_amount(current_by_label, elapsed_labels)
    previous_elapsed_amount, previous_elapsed_missing = _sum_amount(previous_by_label, elapsed_labels)
    previous_full_amount, previous_full_missing = _sum_amount(previous_by_label, full_labels)
    current_price = _decimal_from_row(current_by_label[elapsed_labels[-1]], "close")
    previous_completed_open = _decimal_from_row(current_by_label[previous_completed_labels[0]], "open")
    previous_completed_close = _decimal_from_row(current_by_label[previous_completed_labels[-1]], "close")

    if current_amount_missing or current_elapsed_amount is None:
        blocked_reasons.append("missing_current_30m_elapsed_amount")
    if previous_elapsed_missing or previous_elapsed_amount is None:
        blocked_reasons.append("missing_previous_day_same_elapsed_rows")
    elif previous_elapsed_amount <= 0:
        blocked_reasons.append("previous_day_same_elapsed_30m_amount_non_positive")
    if previous_full_missing or previous_full_amount is None:
        blocked_reasons.append("missing_previous_day_full_30m_amount")
    if current_price is None:
        blocked_reasons.append("missing_current_30m_price")
    if previous_completed_open is None or previous_completed_close is None:
        blocked_reasons.append("missing_previous_completed_30m_open_close")
    if blocked_reasons:
        return _blocked(base, *blocked_reasons)

    assert current_elapsed_amount is not None
    assert previous_elapsed_amount is not None
    assert previous_full_amount is not None
    assert current_price is not None
    assert previous_completed_open is not None
    assert previous_completed_close is not None

    virtual_amount = current_elapsed_amount / previous_elapsed_amount * previous_full_amount
    reference_high = max(previous_completed_open, previous_completed_close)
    reference_low = min(previous_completed_open, previous_completed_close)
    projection_type = "none"
    if virtual_amount > previous_full_amount and current_price > reference_high:
        projection_type = "volume_up"
    elif virtual_amount < previous_full_amount and current_price < reference_low:
        projection_type = "shrink_down"

    base.update(
        {
            "valid": True,
            "blocked_reasons": [],
            "not_ready_classification": None,
            "current_30m_price": _to_float(current_price),
            "current_30m_elapsed_amount": _to_float(current_elapsed_amount),
            "previous_day_same_elapsed_30m_amount": _to_float(previous_elapsed_amount),
            "previous_day_full_30m_amount": _to_float(previous_full_amount),
            "current_30m_virtual_amount": _to_float(virtual_amount),
            "reference_30m_amount": _to_float(previous_full_amount),
            "reference_30m_entity_high": _to_float(reference_high),
            "reference_30m_entity_low": _to_float(reference_low),
            "projection_30m_type": projection_type,
            "projection_30m_flag": projection_type in {"volume_up", "shrink_down"},
        }
    )
    return base


def _base_proof(
    *,
    asset_kind: str,
    identity_key: str,
    for_trade_date: str,
    previous_trade_date: str,
    proof_input_time: Any,
    projection_run_id: str | None,
    projection_id: Any,
) -> dict[str, Any]:
    return {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "for_trade_date": for_trade_date,
        "previous_trade_date": previous_trade_date,
        "proof_input_time": proof_input_time,
        "proof_input_minute_label": _hhmm(proof_input_time) if proof_input_time else None,
        "proof_kind": HINT_1M_PROOF_KIND,
        "source_mode": HINT_1M_SOURCE_MODE,
        "asset_scope": HINT_1M_ASSET_SCOPE,
        "metric_role": HINT_1M_METRIC_ROLE,
        "proof_owner": HINT_1M_PROOF_OWNER,
        "proof_consumer": HINT_1M_PROOF_CONSUMER,
        "not_n5_final_proof": True,
        "source_projection_proof_run_id": projection_run_id,
        "source_projection_proof_metric_id": projection_id,
        "source_projection_proof_time": proof_input_time,
        "projection_30m_type": "unknown",
        "projection_30m_flag": False,
        "valid": False,
        "blocked_reasons": [],
    }


def _blocked(base: Mapping[str, Any], *reasons: str, not_ready_classification: str = "blocked") -> dict[str, Any]:
    output = dict(base)
    output["valid"] = False
    output["projection_30m_type"] = "unknown"
    output["projection_30m_flag"] = False
    output["not_ready_classification"] = not_ready_classification
    output["blocked_reasons"] = sorted(set(reason for reason in reasons if reason))
    return output


def _rows_by_label(
    rows: Sequence[Mapping[str, Any]],
    *,
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    allow_midday_bridge: bool = False,
    allow_logical_1130: bool = False,
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    by_label: dict[str, Mapping[str, Any]] = {}
    reasons: list[str] = []
    for row in rows:
        if str(row.get("asset_kind") or "") != asset_kind or str(row.get("identity_key") or "") != identity_key:
            continue
        if _is_fake_marker(row):
            reasons.append("fake_source_marker")
            continue
        label, row_trade_date = _row_label_and_trade_date(row)
        if not label:
            reasons.append("missing_canonical_label")
            continue
        if label == HINT_1M_MIDDAY_LOGICAL_LABEL and not allow_logical_1130:
            reasons.append("canonical_1130_forbidden")
        logical_label = _logical_label_for_row(label, allow_midday_bridge=allow_midday_bridge)
        explicit_trade_date = str(row.get("trade_date") or row.get("for_trade_date") or row_trade_date or "")
        if explicit_trade_date and explicit_trade_date != trade_date:
            reasons.append("source_trade_date_mismatch")
        if row_trade_date and row_trade_date != trade_date:
            reasons.append("source_trade_date_mismatch")
        if logical_label in by_label:
            reasons.append("duplicate_canonical_label")
        by_label[logical_label] = row
    return by_label, sorted(set(reasons))


def _logical_label_for_row(label: str, *, allow_midday_bridge: bool) -> str:
    if allow_midday_bridge and label == HINT_1M_MIDDAY_RAW_LABEL:
        return HINT_1M_MIDDAY_LOGICAL_LABEL
    return label


def _raw_labels_for_logical_labels(labels: Sequence[str], *, bridge_midday: bool) -> list[str]:
    if not bridge_midday:
        return list(labels)
    return [HINT_1M_MIDDAY_RAW_LABEL if label == HINT_1M_MIDDAY_LOGICAL_LABEL else label for label in labels]


def _row_label_and_trade_date(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for key in ("canonical_minute_label", "minute_label", "bar_time", "datetime", "time"):
        value = row.get(key)
        if value in (None, ""):
            continue
        text = str(value)
        parsed = _parse_datetime(text)
        if parsed is not None:
            return parsed.strftime("%H:%M"), parsed.strftime("%Y%m%d")
        match = re.search(r"(\d{2}:\d{2})", text)
        if match:
            return match.group(1), None
    return None, None


def _hhmm(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    text = str(value)
    parsed = _parse_datetime(text)
    if parsed is not None:
        return parsed.strftime("%H:%M")
    match = re.search(r"(\d{2}:\d{2})", text)
    if match:
        return match.group(1)
    raise ValueError("invalid_minute_label")


def _parse_datetime(text: str) -> datetime | None:
    normalized = text.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _labels_between(start: str, end: str) -> list[str]:
    hour, minute = [int(part) for part in start.split(":")]
    end_hour, end_minute = [int(part) for part in end.split(":")]
    labels: list[str] = []
    while (hour, minute) <= (end_hour, end_minute):
        labels.append(f"{hour:02d}:{minute:02d}")
        minute += 1
        if minute == 60:
            hour += 1
            minute = 0
    return labels


def _sum_amount(rows_by_label: Mapping[str, Mapping[str, Any]], labels: Sequence[str]) -> tuple[Decimal | None, bool]:
    total = Decimal("0")
    missing = False
    for label in labels:
        amount = _decimal_from_row(rows_by_label[label], "amount")
        if amount is None:
            missing = True
            continue
        total += amount
    return (None if missing else total), missing


def _decimal_from_row(row: Mapping[str, Any], key: str) -> Decimal | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _is_fake_marker(row: Mapping[str, Any]) -> bool:
    marker = str(row.get("source_marker") or row.get("source_30m_k_source_marker") or "").strip().lower()
    return marker in {"fake", "synthetic", "fabricated"}


def _to_float(value: Decimal) -> float:
    return float(value)
