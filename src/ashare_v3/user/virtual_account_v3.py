"""Fail-closed N6 virtual-account V3 decision rules.

This module owns no network client and imports no N1-N5 runtime module.  It
turns server-owned proposal/account/position/quote facts into an execution
decision.  Persistence remains an atomic responsibility of the dedicated N6
virtual executor, never of the B-track web process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any, Iterable
from zoneinfo import ZoneInfo


DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")
DEFAULT_BUY_BUDGET = Decimal("300000")
DEFAULT_VIRTUAL_ACCOUNT_INITIAL_CASH = Decimal("100000000")
LOT_SIZE = Decimal("100")
QUOTE_FRESH_SECONDS = 120
PROPOSAL_TTL_SECONDS = 60
SUPPORTED_EXCHANGES = frozenset({"SH", "SZ"})


@dataclass(frozen=True)
class VirtualExecutionDecision:
    ready: bool
    reason: str
    side: str
    identity_key: str
    quantity: Decimal | None
    fill_price: Decimal | None
    gross_amount: Decimal | None
    quote_snapshot_id: int | None


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def calculate_default_buy_quantity(
    *,
    available_cash: Any,
    current_price: Any,
    budget: Decimal = DEFAULT_BUY_BUDGET,
) -> Decimal:
    cash = decimal_or_none(available_cash)
    price = decimal_or_none(current_price)
    if cash is None or price is None or cash <= 0 or price <= 0 or budget <= 0:
        return Decimal("0")
    usable_cash = min(cash, budget)
    lots = (usable_cash / price / LOT_SIZE).to_integral_value(rounding=ROUND_FLOOR)
    return lots * LOT_SIZE


def valid_fresh_quote(
    quote: dict[str, Any] | None,
    *,
    identity_key: str,
    now: datetime,
    max_age_seconds: int = QUOTE_FRESH_SECONDS,
) -> tuple[bool, str, Decimal | None]:
    if not quote:
        return False, "quote_not_ready", None
    if str(quote.get("identity_key") or "") != identity_key:
        return False, "quote_identity_mismatch", None
    parts = identity_key.split(":")
    exchange = parts[1] if len(parts) == 3 else ""
    if exchange not in SUPPORTED_EXCHANGES or str(quote.get("exchange") or "") != exchange:
        return False, "quote_exchange_not_supported", None
    if quote.get("quality_status") != "passed" or quote.get("quality_reason") != "ok":
        return False, "quote_quality_not_passed", None
    price = decimal_or_none(quote.get("current_price"))
    if price is None or price <= 0:
        return False, "quote_price_invalid", None
    fetched_at = quote.get("fetched_at")
    if not isinstance(fetched_at, datetime):
        return False, "quote_time_invalid", None
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=DISPLAY_TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=DISPLAY_TIMEZONE)
    age_seconds = (now.astimezone(DISPLAY_TIMEZONE) - fetched_at.astimezone(DISPLAY_TIMEZONE)).total_seconds()
    if age_seconds < 0 or age_seconds > max_age_seconds:
        return False, "quote_stale", None
    snapshot_id = quote.get("virtual_quote_snapshot_id")
    if isinstance(snapshot_id, bool) or not isinstance(snapshot_id, int) or snapshot_id <= 0:
        return False, "quote_snapshot_id_invalid", None
    return True, "ready", price


def evaluate_confirmed_proposal(
    proposal: dict[str, Any],
    *,
    quote: dict[str, Any] | None,
    available_cash: Any,
    available_quantity: Any,
    now: datetime,
) -> VirtualExecutionDecision:
    side = str(proposal.get("proposal_side") or "")
    identity_key = str(proposal.get("identity_key") or "")
    if proposal.get("proposal_status") != "confirmed":
        return VirtualExecutionDecision(False, "proposal_not_confirmed", side, identity_key, None, None, None, None)
    expires_at = proposal.get("expires_at")
    if not isinstance(expires_at, datetime):
        return VirtualExecutionDecision(False, "proposal_expiry_invalid", side, identity_key, None, None, None, None)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=DISPLAY_TIMEZONE)
    comparable_now = now if now.tzinfo else now.replace(tzinfo=DISPLAY_TIMEZONE)
    if comparable_now >= expires_at:
        return VirtualExecutionDecision(False, "proposal_expired", side, identity_key, None, None, None, None)
    if proposal.get("asset_kind") != "stock" or side not in {"buy", "sell"}:
        return VirtualExecutionDecision(False, "stock_side_required", side, identity_key, None, None, None, None)
    quote_ready, quote_reason, price = valid_fresh_quote(quote, identity_key=identity_key, now=now)
    if not quote_ready or price is None:
        return VirtualExecutionDecision(False, quote_reason, side, identity_key, None, None, None, None)
    if side == "buy":
        quantity = calculate_default_buy_quantity(available_cash=available_cash, current_price=price)
        if quantity < LOT_SIZE:
            return VirtualExecutionDecision(False, "cash_not_sufficient_for_one_lot", side, identity_key, None, None, None, None)
    else:
        quantity = decimal_or_none(available_quantity)
        if quantity is None or quantity <= 0 or quantity % LOT_SIZE != 0:
            return VirtualExecutionDecision(False, "t1_available_quantity_not_sellable", side, identity_key, None, None, None, None)
    gross_amount = (quantity * price).quantize(Decimal("0.0001"))
    return VirtualExecutionDecision(
        True,
        "ready",
        side,
        identity_key,
        quantity,
        price,
        gross_amount,
        int(quote["virtual_quote_snapshot_id"]),
    )


def two_adjacent_minute_stop_breach(
    snapshots: Iterable[dict[str, Any]],
    *,
    stop_loss_price: Any,
    now: datetime,
) -> bool:
    stop = decimal_or_none(stop_loss_price)
    if stop is None or stop <= 0:
        return False
    valid: list[tuple[str, datetime, Decimal]] = []
    for snapshot in snapshots:
        identity_key = str(snapshot.get("identity_key") or "")
        ready, _reason, price = valid_fresh_quote(snapshot, identity_key=identity_key, now=now)
        quote_minute = snapshot.get("quote_minute")
        if ready and price is not None and isinstance(quote_minute, datetime):
            minute = quote_minute if quote_minute.tzinfo else quote_minute.replace(tzinfo=DISPLAY_TIMEZONE)
            valid.append(
                (
                    identity_key,
                    minute.astimezone(DISPLAY_TIMEZONE).replace(second=0, microsecond=0),
                    price,
                )
            )
    if len(valid) < 2:
        return False
    valid.sort(key=lambda item: item[1])
    previous, latest = valid[-2], valid[-1]
    return (
        previous[0] == latest[0]
        and latest[1] - previous[1] == timedelta(minutes=1)
        and previous[2] <= stop
        and latest[2] <= stop
    )


def freeze_first_day_stop_loss(
    snapshots: Iterable[dict[str, Any]],
    *,
    identity_key: str,
    first_open_trade_date: str,
) -> tuple[str, Decimal | None, int | None]:
    identity_parts = identity_key.split(":")
    target_exchange = identity_parts[1] if len(identity_parts) == 3 else ""
    if target_exchange not in SUPPORTED_EXCHANGES:
        return "not_ready", None, None
    candidates: list[tuple[datetime, Decimal, int]] = []
    for snapshot in snapshots:
        if str(snapshot.get("identity_key") or "") != identity_key:
            return "not_ready", None, None
        if str(snapshot.get("quote_minute") or "")[:10].replace("-", "") != first_open_trade_date.replace("-", ""):
            continue
        quote_minute = snapshot.get("quote_minute")
        day_low = decimal_or_none(snapshot.get("day_low"))
        snapshot_id = snapshot.get("virtual_quote_snapshot_id")
        if not isinstance(quote_minute, datetime) or day_low is None or day_low <= 0:
            continue
        if (
            str(snapshot.get("exchange") or "") != target_exchange
            or snapshot.get("quality_status") != "passed"
            or snapshot.get("quality_reason") != "ok"
        ):
            continue
        minute = quote_minute if quote_minute.tzinfo else quote_minute.replace(tzinfo=DISPLAY_TIMEZONE)
        local_minute = minute.astimezone(DISPLAY_TIMEZONE)
        if not (14 * 60 + 55 <= local_minute.hour * 60 + local_minute.minute <= 15 * 60 + 5):
            continue
        if isinstance(snapshot_id, int) and not isinstance(snapshot_id, bool) and snapshot_id > 0:
            candidates.append((local_minute, day_low, snapshot_id))
    if not candidates:
        return "not_ready", None, None
    candidates.sort(key=lambda item: item[0])
    _minute, day_low, snapshot_id = candidates[-1]
    return "frozen", day_low, snapshot_id
