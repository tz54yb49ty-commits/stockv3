from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Protocol


QTY_SCALE = Decimal("0.0001")
PRICE_SCALE = Decimal("0.000001")
MONEY_SCALE = Decimal("0.0001")
ROUND_LOT = Decimal("100")

RUN_ID = "b_track_v1_virtual_buy_execution"
POLICY_VERSION = "b_track_v1_virtual_buy_execution_policy_v1"
POLICY_HASH = "b_track_v1_virtual_buy_execution_policy_v1"
FEE_POLICY_VERSION = "b_track_v1_fee_zero_v1"
TAX_POLICY_VERSION = "b_track_v1_tax_zero_v1"
EXECUTION_POLICY_VERSION = "b_track_v1_fill_immediate_v1"
EXECUTION_POLICY_HASH = "b_track_v1_fill_immediate_v1"
FILL_POLICY_VERSION = "b_track_v1_fill_immediate_v1"
FILL_POLICY_HASH = "b_track_v1_fill_immediate_v1"
MARKET_RULE_SET = "a_share_t_plus_1_virtual_v1"


@dataclass(frozen=True)
class VirtualBuyRequest:
    principal_id: int
    principal_type: str
    user_signal_projection_id: int
    quantity: Decimal | int | str
    price: Decimal | int | str
    trade_date: str
    available_date: str
    run_id: str = RUN_ID
    policy_version: str = POLICY_VERSION
    policy_hash: str = POLICY_HASH
    rollback_scope: str = RUN_ID
    fee_policy_version: str = FEE_POLICY_VERSION
    tax_policy_version: str = TAX_POLICY_VERSION
    execution_policy_version: str = EXECUTION_POLICY_VERSION
    execution_policy_hash: str = EXECUTION_POLICY_HASH
    fill_policy_version: str = FILL_POLICY_VERSION
    fill_policy_hash: str = FILL_POLICY_HASH
    market_rule_set: str = MARKET_RULE_SET


@dataclass(frozen=True)
class VirtualBuyResult:
    status: str
    idempotency_key: str
    virtual_order_id: int | None = None
    virtual_trade_id: int | None = None
    cash_ledger_id: int | None = None
    cash_snapshot_id: int | None = None
    virtual_position_id: int | None = None
    position_event_id: int | None = None
    fill: dict[str, Any] | None = None
    cash_after: dict[str, Any] | None = None
    position_after: dict[str, Any] | None = None


class VirtualBuyRejected(Exception):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class VirtualBuyExecutionRepository(Protocol):
    def fetch_signal_for_buy(
        self,
        user_signal_projection_id: int,
        principal_id: int,
        principal_type: str,
    ) -> Mapping[str, Any] | None:
        ...

    def fetch_active_virtual_account(self, principal_id: int, principal_type: str) -> Mapping[str, Any] | None:
        ...

    def fetch_current_cash_snapshot(self, virtual_account_id: int) -> Mapping[str, Any] | None:
        ...

    def fetch_position_for_update(
        self,
        virtual_account_id: int,
        asset_kind: str,
        identity_key: str,
    ) -> Mapping[str, Any] | None:
        ...

    def insert_virtual_order(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def insert_virtual_trade(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def insert_cash_ledger(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def insert_cash_snapshot(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def upsert_virtual_position(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def insert_position_event(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


def build_virtual_buy_idempotency_key(
    *,
    principal_id: int,
    virtual_account_id: int,
    user_signal_projection_id: int,
    side: str,
    quantity: Decimal | int | str,
    price: Decimal | int | str,
) -> str:
    normalized_quantity = _to_decimal(quantity).quantize(QTY_SCALE)
    normalized_price = _to_decimal(price).quantize(PRICE_SCALE)
    return (
        "b_track_v1_buy:"
        f"{int(principal_id)}:"
        f"{int(virtual_account_id)}:"
        f"{int(user_signal_projection_id)}:"
        f"{side}:"
        f"{normalized_quantity}:"
        f"{normalized_price}"
    )


def validate_virtual_buy_request(
    request: VirtualBuyRequest,
    *,
    signal: Mapping[str, Any] | None,
    account: Mapping[str, Any] | None,
    cash_snapshot: Mapping[str, Any] | None,
) -> None:
    quantity = _to_decimal(request.quantity)
    price = _to_decimal(request.price)
    if quantity <= 0:
        raise VirtualBuyRejected("quantity_not_positive")
    if quantity % ROUND_LOT != 0:
        raise VirtualBuyRejected("quantity_not_round_lot")
    if price <= 0:
        raise VirtualBuyRejected("price_not_positive")
    if signal is None:
        raise VirtualBuyRejected("signal_not_found")
    if str(signal.get("asset_kind") or "") != "stock":
        raise VirtualBuyRejected("asset_kind_not_stock")
    if str(signal.get("action_state") or "") != "executed":
        raise VirtualBuyRejected("action_state_not_executed")
    if _present(signal.get("principal_id")) and int(signal["principal_id"]) != int(request.principal_id):
        raise VirtualBuyRejected("principal_scope_mismatch")
    if _present(signal.get("principal_type")) and str(signal["principal_type"]) != str(request.principal_type):
        raise VirtualBuyRejected("principal_scope_mismatch")
    if account is None:
        raise VirtualBuyRejected("active_virtual_account_missing")
    if int(account.get("principal_id") or -1) != int(request.principal_id):
        raise VirtualBuyRejected("principal_scope_mismatch")
    if str(account.get("principal_type") or "") != str(request.principal_type):
        raise VirtualBuyRejected("principal_scope_mismatch")
    if str(account.get("virtual_account_status") or "active") != "active":
        raise VirtualBuyRejected("active_virtual_account_missing")
    if cash_snapshot is None:
        raise VirtualBuyRejected("cash_snapshot_missing")
    fill = compute_virtual_buy_fill(request)
    available_cash = _to_decimal(cash_snapshot.get("available_cash"))
    if available_cash < fill["cash_required"]:
        raise VirtualBuyRejected("insufficient_cash")


def compute_virtual_buy_fill(request: VirtualBuyRequest) -> dict[str, Decimal]:
    quantity = _to_decimal(request.quantity).quantize(QTY_SCALE)
    price = _to_decimal(request.price).quantize(PRICE_SCALE)
    gross_amount = (quantity * price).quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)
    fee_amount = Decimal("0.0000")
    tax_amount = Decimal("0.0000")
    cash_required = gross_amount + fee_amount + tax_amount
    return {
        "quantity": quantity,
        "price": price,
        "gross_amount": gross_amount,
        "fee_amount": fee_amount,
        "tax_amount": tax_amount,
        "total_fee_amount": fee_amount + tax_amount,
        "net_amount": cash_required,
        "net_cash_delta": -cash_required,
        "cash_required": cash_required,
    }


def compute_position_after_buy(
    old_position: Mapping[str, Any] | None,
    *,
    buy_quantity: Decimal | int | str,
    fill_price: Decimal | int | str,
    gross_amount: Decimal | int | str,
) -> dict[str, Any]:
    quantity_delta = _to_decimal(buy_quantity).quantize(QTY_SCALE)
    price = _to_decimal(fill_price).quantize(PRICE_SCALE)
    buy_cost = _to_decimal(gross_amount).quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)
    if old_position is None:
        return {
            "quantity": quantity_delta,
            "available_quantity": Decimal("0.0000"),
            "locked_quantity": quantity_delta,
            "average_cost": price,
        }

    old_quantity = _to_decimal(old_position.get("quantity")).quantize(QTY_SCALE)
    old_available = _to_decimal(old_position.get("available_quantity")).quantize(QTY_SCALE)
    old_locked = _to_decimal(old_position.get("locked_quantity")).quantize(QTY_SCALE)
    old_average_cost = _to_decimal(old_position.get("average_cost")).quantize(PRICE_SCALE)
    new_quantity = (old_quantity + quantity_delta).quantize(QTY_SCALE)
    if new_quantity <= 0:
        raise VirtualBuyRejected("position_quantity_not_positive")
    old_cost = old_quantity * old_average_cost
    average_cost = ((old_cost + buy_cost) / new_quantity).quantize(PRICE_SCALE, rounding=ROUND_HALF_UP)
    result = {
        "quantity": new_quantity,
        "available_quantity": old_available,
        "locked_quantity": (old_locked + quantity_delta).quantize(QTY_SCALE),
        "average_cost": average_cost,
    }
    if _present(old_position.get("virtual_position_id")):
        result["virtual_position_id"] = int(old_position["virtual_position_id"])
    return result


def execute_virtual_buy(
    repository: VirtualBuyExecutionRepository,
    request: VirtualBuyRequest,
) -> VirtualBuyResult:
    signal = repository.fetch_signal_for_buy(
        int(request.user_signal_projection_id),
        int(request.principal_id),
        str(request.principal_type),
    )
    account = repository.fetch_active_virtual_account(int(request.principal_id), str(request.principal_type))
    account_id = int(account["virtual_account_id"]) if account is not None else 0
    cash_snapshot = repository.fetch_current_cash_snapshot(account_id) if account is not None else None
    validate_virtual_buy_request(request, signal=signal, account=account, cash_snapshot=cash_snapshot)

    assert signal is not None
    assert account is not None
    assert cash_snapshot is not None

    asset_kind = str(signal["asset_kind"])
    identity_key = str(signal["identity_key"])
    virtual_account_id = int(account["virtual_account_id"])
    fill = compute_virtual_buy_fill(request)
    idempotency_key = build_virtual_buy_idempotency_key(
        principal_id=int(request.principal_id),
        virtual_account_id=virtual_account_id,
        user_signal_projection_id=int(request.user_signal_projection_id),
        side="buy",
        quantity=fill["quantity"],
        price=fill["price"],
    )
    old_position = repository.fetch_position_for_update(virtual_account_id, asset_kind, identity_key)

    order_payload = _build_order_payload(request, signal, virtual_account_id, fill, idempotency_key)
    order_result = repository.insert_virtual_order(order_payload)
    if bool(order_result.get("duplicate")):
        existing = order_result.get("existing") or {}
        return VirtualBuyResult(
            status="existing",
            idempotency_key=idempotency_key,
            virtual_order_id=_optional_int(existing.get("virtual_order_id")),
            virtual_trade_id=_optional_int(existing.get("virtual_trade_id")),
        )

    virtual_order_id = int(order_result["virtual_order_id"])
    trade_payload = _build_trade_payload(request, signal, virtual_account_id, virtual_order_id, fill, idempotency_key)
    trade_result = repository.insert_virtual_trade(trade_payload)
    virtual_trade_id = int(trade_result["virtual_trade_id"])

    cash_ledger_payload = _build_cash_ledger_payload(
        request,
        signal,
        virtual_account_id,
        virtual_order_id,
        virtual_trade_id,
        fill,
    )
    cash_ledger_result = repository.insert_cash_ledger(cash_ledger_payload)
    cash_ledger_id = int(cash_ledger_result["cash_ledger_id"])

    cash_after = _compute_cash_after(cash_snapshot, fill)
    cash_snapshot_payload = {
        **_execution_metadata(request),
        "virtual_account_id": virtual_account_id,
        "trade_date": _cash_trade_date(request.trade_date),
        "available_cash": cash_after["available_cash"],
        "frozen_cash": cash_after["frozen_cash"],
        "total_cash": cash_after["total_cash"],
        "currency": "CNY",
        "source_ledger_max_id": cash_ledger_id,
        "snapshot_status": "active",
        "source_lineage_json": _source_lineage(signal, idempotency_key),
    }
    cash_snapshot_result = repository.insert_cash_snapshot(cash_snapshot_payload)
    cash_snapshot_id = int(cash_snapshot_result["cash_snapshot_id"])

    position_after = compute_position_after_buy(
        old_position,
        buy_quantity=fill["quantity"],
        fill_price=fill["price"],
        gross_amount=fill["gross_amount"],
    )
    position_payload = {
        **_execution_metadata(request),
        **position_after,
        "virtual_account_id": virtual_account_id,
        "principal_id": int(request.principal_id),
        "principal_type": str(request.principal_type),
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "position_status": "open_virtual",
        "last_virtual_trade_id": virtual_trade_id,
        "source_lineage_json": _source_lineage(signal, idempotency_key),
    }
    position_result = repository.upsert_virtual_position(position_payload)
    virtual_position_id = int(position_result["virtual_position_id"])

    position_event_payload = _build_position_event_payload(
        request,
        signal,
        virtual_account_id,
        virtual_position_id,
        virtual_order_id,
        virtual_trade_id,
        fill,
        idempotency_key,
    )
    position_event_result = repository.insert_position_event(position_event_payload)
    position_event_id = int(position_event_result["position_event_id"])

    return VirtualBuyResult(
        status="executed",
        idempotency_key=idempotency_key,
        virtual_order_id=virtual_order_id,
        virtual_trade_id=virtual_trade_id,
        cash_ledger_id=cash_ledger_id,
        cash_snapshot_id=cash_snapshot_id,
        virtual_position_id=virtual_position_id,
        position_event_id=position_event_id,
        fill=dict(fill),
        cash_after=cash_after,
        position_after=position_after,
    )


def _build_order_payload(
    request: VirtualBuyRequest,
    signal: Mapping[str, Any],
    virtual_account_id: int,
    fill: Mapping[str, Decimal],
    idempotency_key: str,
) -> dict[str, Any]:
    return {
        **_execution_metadata(request),
        "virtual_account_id": virtual_account_id,
        "principal_id": int(request.principal_id),
        "principal_type": str(request.principal_type),
        "asset_kind": str(signal["asset_kind"]),
        "identity_key": str(signal["identity_key"]),
        "signal_type": str(signal.get("signal_type") or "B_BUY"),
        "order_side": "buy",
        "order_type": "limit_virtual",
        "order_status": "filled_virtual",
        "requested_quantity": fill["quantity"],
        "requested_price": fill["price"],
        "estimated_fee_amount": fill["fee_amount"],
        "estimated_tax_amount": fill["tax_amount"],
        "fee_policy_version": request.fee_policy_version,
        "tax_policy_version": request.tax_policy_version,
        "execution_policy_version": request.execution_policy_version,
        "execution_policy_hash": request.execution_policy_hash,
        "market_rule_set": request.market_rule_set,
        "source_action_event_id": _text_or_none(signal.get("source_action_event_id") or signal.get("source_event_id")),
        "source_signal_projection_id": int(request.user_signal_projection_id),
        "source_lineage_json": _source_lineage(signal, idempotency_key),
        "idempotency_key": idempotency_key,
        "source_message_key": _text_or_none(signal.get("source_message_key")),
        "source_signal_identity_key": _text_or_none(signal.get("source_signal_identity_key") or signal.get("identity_key")),
        "source_condition_key": _text_or_none(signal.get("source_condition_key") or signal.get("condition_key")),
        "source_event_time": _text_or_none(signal.get("source_event_time") or signal.get("event_time")),
        "source_for_trade_date": _text_or_none(signal.get("source_for_trade_date")),
        "source_trade_date": _text_or_none(signal.get("source_trade_date") or signal.get("trade_date")),
        "source_monitor_id": _optional_int(signal.get("source_monitor_id")),
        "source_strategy_id": _optional_int(signal.get("source_strategy_id")),
        "source_action_state": str(signal.get("source_action_state") or signal.get("action_state") or ""),
        "source_blocked_reason": _text_or_none(signal.get("source_blocked_reason") or signal.get("blocked_reason")),
        "source_json": _source_json(signal),
    }


def _build_trade_payload(
    request: VirtualBuyRequest,
    signal: Mapping[str, Any],
    virtual_account_id: int,
    virtual_order_id: int,
    fill: Mapping[str, Decimal],
    idempotency_key: str,
) -> dict[str, Any]:
    return {
        **_execution_metadata(request),
        "virtual_order_id": virtual_order_id,
        "virtual_account_id": virtual_account_id,
        "principal_id": int(request.principal_id),
        "principal_type": str(request.principal_type),
        "asset_kind": str(signal["asset_kind"]),
        "identity_key": str(signal["identity_key"]),
        "trade_side": "buy",
        "filled_quantity": fill["quantity"],
        "filled_price": fill["price"],
        "gross_amount": fill["gross_amount"],
        "commission_amount": Decimal("0.0000"),
        "stamp_tax_amount": Decimal("0.0000"),
        "transfer_fee_amount": Decimal("0.0000"),
        "total_fee_amount": Decimal("0.0000"),
        "net_amount": fill["net_amount"],
        "fill_policy_version": request.fill_policy_version,
        "fill_policy_hash": request.fill_policy_hash,
        "replay_deterministic_seed": idempotency_key,
        "trade_status": "filled_virtual",
        "trade_time": _text_or_none(signal.get("source_event_time") or signal.get("event_time")) or request.trade_date,
        "source_lineage_json": _source_lineage(signal, idempotency_key),
    }


def _build_cash_ledger_payload(
    request: VirtualBuyRequest,
    signal: Mapping[str, Any],
    virtual_account_id: int,
    virtual_order_id: int,
    virtual_trade_id: int,
    fill: Mapping[str, Decimal],
) -> dict[str, Any]:
    return {
        **_execution_metadata(request),
        "virtual_account_id": virtual_account_id,
        "ledger_type": "virtual_buy",
        "amount": fill["net_cash_delta"],
        "currency": "CNY",
        "trade_date": _cash_trade_date(request.trade_date),
        "event_time": _text_or_none(signal.get("source_event_time") or signal.get("event_time")) or request.trade_date,
        "source_event_type": "virtual_buy_fill",
        "source_event_id": _text_or_none(signal.get("source_action_event_id") or signal.get("source_event_id")),
        "source_virtual_order_id": virtual_order_id,
        "source_virtual_trade_id": virtual_trade_id,
        "source_lineage_json": _source_lineage(signal, None),
    }


def _build_position_event_payload(
    request: VirtualBuyRequest,
    signal: Mapping[str, Any],
    virtual_account_id: int,
    virtual_position_id: int,
    virtual_order_id: int,
    virtual_trade_id: int,
    fill: Mapping[str, Decimal],
    idempotency_key: str,
) -> dict[str, Any]:
    return {
        **_execution_metadata(request),
        "virtual_position_id": virtual_position_id,
        "virtual_account_id": virtual_account_id,
        "principal_id": int(request.principal_id),
        "principal_type": str(request.principal_type),
        "asset_kind": str(signal["asset_kind"]),
        "identity_key": str(signal["identity_key"]),
        "event_type": "virtual_buy_fill",
        "quantity_delta": fill["quantity"],
        "available_quantity_delta": Decimal("0.0000"),
        "locked_quantity_delta": fill["quantity"],
        "cost_delta": fill["gross_amount"],
        "price": fill["price"],
        "source_virtual_order_id": virtual_order_id,
        "source_virtual_trade_id": virtual_trade_id,
        "event_time": _text_or_none(signal.get("source_event_time") or signal.get("event_time")) or request.trade_date,
        "trade_date": request.trade_date,
        "available_date": request.available_date,
        "source_order_side": "buy",
        "source_for_trade_date": _text_or_none(signal.get("source_for_trade_date")) or request.trade_date,
        "source_trade_date": _text_or_none(signal.get("source_trade_date") or signal.get("trade_date")) or request.trade_date,
        "source_json": _source_json(signal),
        "source_lineage_json": _source_lineage(signal, idempotency_key),
    }


def _compute_cash_after(cash_snapshot: Mapping[str, Any], fill: Mapping[str, Decimal]) -> dict[str, Decimal]:
    available_cash = (_to_decimal(cash_snapshot.get("available_cash")) + fill["net_cash_delta"]).quantize(
        MONEY_SCALE,
        rounding=ROUND_HALF_UP,
    )
    frozen_cash = _to_decimal(cash_snapshot.get("frozen_cash")).quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)
    total_cash = (available_cash + frozen_cash).quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)
    return {
        "available_cash": available_cash,
        "frozen_cash": frozen_cash,
        "total_cash": total_cash,
    }


def _execution_metadata(request: VirtualBuyRequest) -> dict[str, Any]:
    return {
        "run_id": request.run_id,
        "policy_version": request.policy_version,
        "policy_hash": request.policy_hash,
        "rollback_scope": request.rollback_scope,
        "quality_status": "passed",
    }


def _source_lineage(signal: Mapping[str, Any], idempotency_key: str | None) -> dict[str, Any]:
    payload = {
        "source": "B_TRACK_V1_virtual_buy_execution",
        "user_signal_projection_id": signal.get("user_signal_projection_id"),
        "source_action_event_id": signal.get("source_action_event_id"),
        "source_event_id": signal.get("source_event_id"),
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return {key: value for key, value in payload.items() if value is not None}


def _source_json(signal: Mapping[str, Any]) -> dict[str, Any]:
    source = signal.get("source_json")
    if isinstance(source, Mapping):
        return dict(source)
    return {
        "user_signal_projection_id": signal.get("user_signal_projection_id"),
        "source_action_event_id": signal.get("source_action_event_id"),
        "source_event_id": signal.get("source_event_id"),
    }


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise VirtualBuyRejected("invalid_decimal") from exc


def _cash_trade_date(value: str) -> int:
    return int(str(value).replace("-", ""))


def _present(value: Any) -> bool:
    return value is not None and str(value) != ""


def _optional_int(value: Any) -> int | None:
    if not _present(value):
        return None
    return int(value)


def _text_or_none(value: Any) -> str | None:
    if not _present(value):
        return None
    return str(value)
