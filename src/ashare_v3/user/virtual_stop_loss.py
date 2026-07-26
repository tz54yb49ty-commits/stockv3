"""Pure, fail-closed N6 virtual stop-loss policy helpers."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, TypeVar
from zoneinfo import ZoneInfo


DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")
SUPPORTED_EXCHANGES = frozenset({"SH", "SZ"})
QUOTE_FRESH_SECONDS = 120
FREEZE_WINDOW_START = time(14, 55)
FREEZE_WINDOW_END = time(15, 5)
T = TypeVar("T")


def first_ready_candidate(candidates: Iterable[T], ready: Callable[[T], bool]) -> T | None:
    """Select the first ready row; an earlier not-ready row cannot starve it."""
    return next((candidate for candidate in candidates if ready(candidate)), None)


def finite_positive(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=DISPLAY_TIMEZONE)


def valid_runtime_quote(
    snapshot: dict[str, Any], *, identity_key: str, now: datetime
) -> tuple[bool, Decimal | None]:
    parts = identity_key.split(":")
    exchange = parts[1] if len(parts) == 3 else ""
    if (
        exchange not in SUPPORTED_EXCHANGES
        or snapshot.get("identity_key") != identity_key
        or snapshot.get("exchange") != exchange
        or snapshot.get("quality_status") != "passed"
        or snapshot.get("quality_reason") != "ok"
    ):
        return False, None
    price = finite_positive(snapshot.get("current_price"))
    quote_minute = _aware(snapshot.get("quote_minute"))
    fetched_at = _aware(snapshot.get("fetched_at"))
    comparable_now = _aware(now)
    if price is None or quote_minute is None or fetched_at is None or comparable_now is None:
        return False, None
    if fetched_at < quote_minute:
        return False, None
    for timestamp in (quote_minute, fetched_at):
        age = (comparable_now - timestamp).total_seconds()
        if age < 0 or age > QUOTE_FRESH_SECONDS:
            return False, None
    return True, price


def freeze_candidate(
    snapshots: Iterable[dict[str, Any]], *, identity_key: str, first_open_date: date
) -> tuple[str, Decimal | None, int | None]:
    parts = identity_key.split(":")
    exchange = parts[1] if len(parts) == 3 else ""
    if exchange not in SUPPORTED_EXCHANGES:
        return "not_ready", None, None
    candidates: list[tuple[datetime, int, Decimal]] = []
    for snapshot in snapshots:
        quote_minute = _aware(snapshot.get("quote_minute"))
        fetched_at = _aware(snapshot.get("fetched_at"))
        day_low = finite_positive(snapshot.get("day_low"))
        snapshot_id = snapshot.get("virtual_quote_snapshot_id")
        if (
            snapshot.get("identity_key") != identity_key
            or snapshot.get("exchange") != exchange
            or snapshot.get("quality_status") != "passed"
            or snapshot.get("quality_reason") != "ok"
            or quote_minute is None
            or fetched_at is None
            or quote_minute.astimezone(DISPLAY_TIMEZONE).date() != first_open_date
            or fetched_at.astimezone(DISPLAY_TIMEZONE).date() != first_open_date
            or day_low is None
            or isinstance(snapshot_id, bool)
            or not isinstance(snapshot_id, int)
            or snapshot_id <= 0
        ):
            continue
        local_time = quote_minute.astimezone(DISPLAY_TIMEZONE).time().replace(tzinfo=None)
        if fetched_at < quote_minute or FREEZE_WINDOW_START > local_time or local_time > FREEZE_WINDOW_END:
            continue
        candidates.append((quote_minute, snapshot_id, day_low))
    if not candidates:
        return "not_ready", None, None
    _minute, snapshot_id, day_low = max(candidates)
    return "frozen", day_low, snapshot_id


def adjacent_pair(
    snapshots: Iterable[dict[str, Any]],
    *,
    identity_key: str,
    stop_loss_price: Any,
    now: datetime,
    relation: str,
) -> tuple[int, int] | None:
    stop = finite_positive(stop_loss_price)
    if stop is None or relation not in {"at_or_below", "above"}:
        return None
    by_minute: dict[datetime, tuple[int, dict[str, Any]]] = {}
    for snapshot in snapshots:
        minute = _aware(snapshot.get("quote_minute"))
        snapshot_id = snapshot.get("virtual_quote_snapshot_id")
        if minute is None or isinstance(snapshot_id, bool) or not isinstance(snapshot_id, int):
            continue
        minute = minute.replace(second=0, microsecond=0)
        existing = by_minute.get(minute)
        if existing is None or snapshot_id > existing[0]:
            by_minute[minute] = (snapshot_id, snapshot)
    if not by_minute:
        return None
    latest_minute = max(by_minute)
    previous_minute = latest_minute - timedelta(minutes=1)
    if previous_minute not in by_minute:
        return None
    first_id, first_snapshot = by_minute[previous_minute]
    second_id, second_snapshot = by_minute[latest_minute]
    first_ready, first_price = valid_runtime_quote(
        first_snapshot, identity_key=identity_key, now=now
    )
    second_ready, second_price = valid_runtime_quote(
        second_snapshot, identity_key=identity_key, now=now
    )
    if not first_ready or not second_ready or first_price is None or second_price is None:
        return None
    if relation == "at_or_below" and first_price <= stop and second_price <= stop:
        return first_id, second_id
    if relation == "above" and first_price > stop and second_price > stop:
        return first_id, second_id
    return None


def matured_lot_quantity(
    lots: Iterable[dict[str, Any]],
    *,
    scope: dict[str, Any],
    current_trade_date: date,
) -> Decimal:
    total = Decimal("0")
    for lot in lots:
        if any(lot.get(key) != scope.get(key) for key in (
            "virtual_position_id", "virtual_account_id", "principal_id",
            "principal_type", "identity_key", "holding_episode_no",
        )):
            continue
        quantity = finite_positive(lot.get("remaining_quantity"))
        available_date = lot.get("available_trade_date")
        if (
            quantity is not None
            and isinstance(available_date, date)
            and available_date <= current_trade_date
            and lot.get("lot_status") in {"locked_t1", "available"}
        ):
            total += quantity
    return total
