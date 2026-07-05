from __future__ import annotations

from decimal import Decimal

from ashare_v3.user.virtual_buy_execution import (
    VirtualBuyRejected,
    VirtualBuyRequest,
    build_virtual_buy_idempotency_key,
    compute_position_after_buy,
    execute_virtual_buy,
)


class FakeVirtualBuyRepository:
    def __init__(self) -> None:
        self.signal = {
            "user_signal_projection_id": 101,
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "signal_type": "B_BUY",
            "action_state": "executed",
            "source_action_event_id": "action-executed-101",
            "source_event_id": "action-executed-101",
            "source_message_key": "message-101",
            "source_signal_identity_key": "stock:SH:600000:B_BUY",
            "source_condition_key": "BUY:M,W,D",
            "source_event_time": "2026-06-24T10:30:00+08:00",
            "source_for_trade_date": "2026-06-24",
            "source_trade_date": "2026-06-24",
            "source_action_state": "executed",
            "source_json": {"source": "unit-test"},
            "principal_id": 1,
            "principal_type": "admin",
        }
        self.account = {
            "virtual_account_id": 11,
            "principal_id": 1,
            "principal_type": "admin",
            "virtual_account_status": "active",
        }
        self.cash_snapshot = {
            "cash_snapshot_id": 21,
            "available_cash": Decimal("20000.0000"),
            "frozen_cash": Decimal("100.0000"),
            "total_cash": Decimal("20100.0000"),
            "source_ledger_max_id": 20,
        }
        self.position = None
        self.calls: list[str] = []
        self.next_ids = {
            "order": 31,
            "trade": 41,
            "cash_ledger": 51,
            "cash_snapshot": 61,
            "position": 71,
            "position_event": 81,
        }
        self.inserted: dict[str, dict] = {}
        self.duplicate_order = False
        self.existing_order = {
            "virtual_order_id": 1301,
            "virtual_trade_id": 1401,
            "idempotency_key": "existing-key",
        }

    def fetch_signal_for_buy(self, user_signal_projection_id, principal_id, principal_type):
        self.calls.append("fetch_signal")
        if user_signal_projection_id != self.signal["user_signal_projection_id"]:
            return None
        return dict(self.signal)

    def fetch_active_virtual_account(self, principal_id, principal_type):
        self.calls.append("fetch_account")
        if self.account is None:
            return None
        return dict(self.account)

    def fetch_current_cash_snapshot(self, virtual_account_id):
        self.calls.append("fetch_cash")
        if self.cash_snapshot is None:
            return None
        return dict(self.cash_snapshot)

    def fetch_position_for_update(self, virtual_account_id, asset_kind, identity_key):
        self.calls.append("fetch_position")
        return dict(self.position) if self.position else None

    def insert_virtual_order(self, payload):
        self.calls.append("order")
        self.inserted["order"] = dict(payload)
        if self.duplicate_order:
            return {"duplicate": True, "existing": dict(self.existing_order)}
        return {"virtual_order_id": self.next_ids["order"]}

    def insert_virtual_trade(self, payload):
        self.calls.append("trade")
        self.inserted["trade"] = dict(payload)
        return {"virtual_trade_id": self.next_ids["trade"]}

    def insert_cash_ledger(self, payload):
        self.calls.append("cash_ledger")
        self.inserted["cash_ledger"] = dict(payload)
        return {"cash_ledger_id": self.next_ids["cash_ledger"]}

    def insert_cash_snapshot(self, payload):
        self.calls.append("cash_snapshot")
        self.inserted["cash_snapshot"] = dict(payload)
        return {"cash_snapshot_id": self.next_ids["cash_snapshot"]}

    def upsert_virtual_position(self, payload):
        self.calls.append("position")
        self.inserted["position"] = dict(payload)
        return {"virtual_position_id": self.next_ids["position"]}

    def insert_position_event(self, payload):
        self.calls.append("position_event")
        self.inserted["position_event"] = dict(payload)
        return {"position_event_id": self.next_ids["position_event"]}


def request(**overrides) -> VirtualBuyRequest:
    base = {
        "principal_id": 1,
        "principal_type": "admin",
        "user_signal_projection_id": 101,
        "quantity": Decimal("200"),
        "price": Decimal("12.50"),
        "trade_date": "2026-06-24",
        "available_date": "2026-06-25",
    }
    base.update(overrides)
    return VirtualBuyRequest(**base)


def assert_rejected(code: str, repo: FakeVirtualBuyRepository, buy_request: VirtualBuyRequest) -> None:
    try:
        execute_virtual_buy(repo, buy_request)
    except VirtualBuyRejected as exc:
        assert exc.code == code
        return
    raise AssertionError(f"expected VirtualBuyRejected({code})")


def test_executed_stock_signal_buy_success_writes_virtual_execution_chain() -> None:
    repo = FakeVirtualBuyRepository()

    result = execute_virtual_buy(repo, request())

    assert result.status == "executed"
    assert result.virtual_order_id == 31
    assert result.virtual_trade_id == 41
    assert result.cash_snapshot_id == 61
    assert result.virtual_position_id == 71
    assert result.position_event_id == 81
    assert repo.inserted["order"]["order_side"] == "buy"
    assert repo.inserted["trade"]["trade_side"] == "buy"
    assert repo.inserted["trade"]["gross_amount"] == Decimal("2500.0000")
    assert repo.inserted["cash_ledger"]["ledger_type"] == "virtual_buy"
    assert repo.inserted["cash_ledger"]["amount"] == Decimal("-2500.0000")
    assert repo.inserted["cash_snapshot"]["available_cash"] == Decimal("17500.0000")
    assert repo.inserted["cash_snapshot"]["frozen_cash"] == Decimal("100.0000")
    assert repo.inserted["cash_snapshot"]["total_cash"] == Decimal("17600.0000")


def test_non_stock_signal_is_rejected() -> None:
    repo = FakeVirtualBuyRepository()
    repo.signal["asset_kind"] = "index"

    assert_rejected("asset_kind_not_stock", repo, request())


def test_action_state_other_than_executed_is_rejected() -> None:
    repo = FakeVirtualBuyRepository()
    repo.signal["action_state"] = "eligible"

    assert_rejected("action_state_not_executed", repo, request())


def test_quantity_must_be_round_lot() -> None:
    repo = FakeVirtualBuyRepository()

    assert_rejected("quantity_not_round_lot", repo, request(quantity=Decimal("150")))


def test_insufficient_cash_is_rejected_before_writes() -> None:
    repo = FakeVirtualBuyRepository()
    repo.cash_snapshot["available_cash"] = Decimal("1000.0000")

    assert_rejected("insufficient_cash", repo, request())
    assert "order" not in repo.calls
    assert "trade" not in repo.calls


def test_new_position_after_buy_locks_all_bought_quantity_for_t_plus_one() -> None:
    repo = FakeVirtualBuyRepository()

    execute_virtual_buy(repo, request())

    position = repo.inserted["position"]
    assert position["quantity"] == Decimal("200.0000")
    assert position["available_quantity"] == Decimal("0.0000")
    assert position["locked_quantity"] == Decimal("200.0000")
    assert position["average_cost"] == Decimal("12.500000")


def test_existing_position_after_buy_recomputes_weighted_average_cost() -> None:
    old_position = {
        "virtual_position_id": 77,
        "quantity": Decimal("300.0000"),
        "available_quantity": Decimal("300.0000"),
        "locked_quantity": Decimal("0.0000"),
        "average_cost": Decimal("10.000000"),
    }

    position = compute_position_after_buy(
        old_position,
        buy_quantity=Decimal("200"),
        fill_price=Decimal("12.50"),
        gross_amount=Decimal("2500.0000"),
    )

    assert position["virtual_position_id"] == 77
    assert position["quantity"] == Decimal("500.0000")
    assert position["available_quantity"] == Decimal("300.0000")
    assert position["locked_quantity"] == Decimal("200.0000")
    assert position["average_cost"] == Decimal("11.000000")


def test_position_event_records_t_plus_one_locked_and_available_delta() -> None:
    repo = FakeVirtualBuyRepository()

    execute_virtual_buy(repo, request())

    event = repo.inserted["position_event"]
    assert event["event_type"] == "virtual_buy_fill"
    assert event["quantity_delta"] == Decimal("200.0000")
    assert event["available_quantity_delta"] == Decimal("0.0000")
    assert event["locked_quantity_delta"] == Decimal("200.0000")
    assert event["cost_delta"] == Decimal("2500.0000")
    assert event["price"] == Decimal("12.500000")
    assert event["trade_date"] == "2026-06-24"
    assert event["available_date"] == "2026-06-25"


def test_idempotency_key_is_stable() -> None:
    first = build_virtual_buy_idempotency_key(
        principal_id=1,
        virtual_account_id=11,
        user_signal_projection_id=101,
        side="buy",
        quantity=Decimal("200.0000"),
        price=Decimal("12.500000"),
    )
    second = build_virtual_buy_idempotency_key(
        principal_id=1,
        virtual_account_id=11,
        user_signal_projection_id=101,
        side="buy",
        quantity=Decimal("200"),
        price=Decimal("12.50"),
    )

    assert first == second
    assert first == "b_track_v1_buy:1:11:101:buy:200.0000:12.500000"


def test_repository_write_order_is_order_trade_cash_position_event_chain() -> None:
    repo = FakeVirtualBuyRepository()

    execute_virtual_buy(repo, request())

    assert repo.calls[-6:] == [
        "order",
        "trade",
        "cash_ledger",
        "cash_snapshot",
        "position",
        "position_event",
    ]


def test_duplicate_order_returns_existing_result_without_followup_writes() -> None:
    repo = FakeVirtualBuyRepository()
    repo.duplicate_order = True

    result = execute_virtual_buy(repo, request())

    assert result.status == "existing"
    assert result.virtual_order_id == 1301
    assert result.virtual_trade_id == 1401
    assert repo.calls[-1] == "order"
