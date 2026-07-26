from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from ashare_v3.n3n6q.contract import QuoteIdentity
from ashare_v3.n3n6q.mootdx_adapter import MootdxStockQuoteAdapter
from ashare_v3.n3n6q.provider import QuoteProvider


NOW = datetime(2026, 7, 16, 9, 31, tzinfo=timezone.utc)
BATCH_ID = UUID("12345678-1234-5678-1234-567812345678")


class FakeAdapter:
    source_adapter = "mootdx.std"
    source_version = "fake-1.0"

    def __init__(self, rows=(), *, error: Exception | None = None):
        self.rows = list(rows)
        self.error = error
        self.calls = []

    def fetch_stock_quotes(self, identities):
        self.calls.append(tuple(identities))
        if self.error is not None:
            raise self.error
        return list(self.rows)


def identity(exchange: str, code: str) -> QuoteIdentity:
    return QuoteIdentity(
        identity_key=f"stock:{exchange}:{code}",
        exchange=exchange,
        stock_code=code,
    )


def provider(adapter: FakeAdapter) -> QuoteProvider:
    return QuoteProvider(
        adapter,
        clock=lambda: NOW,
        uuid_factory=lambda: BATCH_ID,
    )


def valid_row(*, market=1, code="600000", price="10.25", low="10.01", servertime="09:31:02"):
    return {
        "market": market,
        "code": code,
        "price": price,
        "last_close": "10.00",
        "open": "10.10",
        "high": "10.30",
        "low": low,
        "servertime": servertime,
        "volume": 999999,
    }


@pytest.mark.parametrize(
    "request",
    [
        [],
        [identity("SH", f"{code:06d}") for code in range(81)],
        [identity("SH", "600000"), identity("SH", "600000")],
        [{"identity_key": "stock:SH:600000", "exchange": "SH", "stock_code": "600000", "quantity": 1}],
        [{"identity_key": "stock:SZ:600000", "exchange": "SH", "stock_code": "600000"}],
        [{"identity_key": "index:SH:000001", "exchange": "SH", "stock_code": "000001"}],
        [{"identity_key": "stock:SH:60000", "exchange": "SH", "stock_code": "60000"}],
    ],
)
def test_invalid_batch_is_rejected_before_adapter_call(request):
    adapter = FakeAdapter()

    with pytest.raises(ValueError):
        provider(adapter).fetch_quotes(request)

    assert adapter.calls == []


def test_passed_batch_has_exact_v1_fields_decimal_strings_and_request_order():
    adapter = FakeAdapter(
        [
            valid_row(market=0, code="000001", price=12.5, low=12.0, servertime="09:31"),
            valid_row(market=1, code="600000"),
        ]
    )

    batch = provider(adapter).fetch_quotes(
        [identity("SH", "600000"), identity("SZ", "000001")]
    )
    payload = batch.to_dict()

    assert set(payload) == {
        "contract_version",
        "batch_id",
        "source_adapter",
        "source_version",
        "source_time_semantics",
        "requested_at",
        "completed_at",
        "batch_status",
        "item_count",
        "items",
    }
    assert payload | {} == {
        **payload,
        "contract_version": "1.0.0",
        "batch_id": str(BATCH_ID),
        "source_adapter": "mootdx.std",
        "source_version": "fake-1.0",
        "source_time_semantics": "provider_intraday_time_without_trade_date",
        "requested_at": NOW.isoformat(),
        "completed_at": NOW.isoformat(),
        "batch_status": "passed",
        "item_count": 2,
    }
    assert [item["identity_key"] for item in payload["items"]] == [
        "stock:SH:600000",
        "stock:SZ:000001",
    ]
    assert set(payload["items"][0]) == {
        "identity_key",
        "exchange",
        "market",
        "stock_code",
        "current_price",
        "last_close",
        "day_open",
        "day_high",
        "day_low",
        "source_time_text",
        "fetched_at",
        "quality_status",
        "quality_reason",
    }
    assert payload["items"][0]["current_price"] == "10.25"
    assert payload["items"][1]["current_price"] == "12.5"
    assert "volume" not in payload["items"][0]


def test_missing_item_is_not_backfilled_and_makes_batch_partial():
    adapter = FakeAdapter([valid_row(market=1, code="600000")])

    batch = provider(adapter).fetch_quotes(
        [identity("SH", "600000"), identity("SZ", "000001")]
    )

    assert batch.batch_status == "partial"
    assert batch.items[1].quality_reason == "missing"
    assert batch.items[1].current_price is None

    reverse_batch = provider(
        FakeAdapter([valid_row(market=0, code="000001")])
    ).fetch_quotes([identity("SH", "600000"), identity("SZ", "000001")])
    assert reverse_batch.items[0].quality_reason == "missing"
    assert reverse_batch.items[1].quality_reason == "ok"


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([valid_row(market=0, code="600000")], "identity_mismatch"),
        ([valid_row(code="000001")], "identity_mismatch"),
        ([valid_row(), valid_row()], "identity_mismatch"),
        ([valid_row(price="0")], "invalid_price"),
        ([valid_row(low="0")], "invalid_price"),
        ([valid_row(servertime="2026-07-16 09:31:02")], "invalid_source_time"),
        ([valid_row(servertime=None)], "invalid_source_time"),
    ],
)
def test_bad_provider_item_fails_closed(rows, reason):
    batch = provider(FakeAdapter(rows)).fetch_quotes([identity("SH", "600000")])

    assert batch.batch_status == "failed"
    assert batch.items[0].quality_status == "not_ready"
    assert batch.items[0].quality_reason == reason
    assert batch.items[0].current_price is None
    assert batch.items[0].day_low is None


def test_bj_is_unsupported_until_live_mapping_is_proven():
    adapter = FakeAdapter([valid_row(market=0, code="430047")])

    batch = provider(adapter).fetch_quotes([identity("BJ", "430047")])

    assert adapter.calls == []
    assert batch.batch_status == "failed"
    assert batch.items[0].quality_reason == "unsupported_exchange"


def test_adapter_exception_returns_provider_error_for_every_supported_item():
    adapter = FakeAdapter(error=RuntimeError("offline"))

    batch = provider(adapter).fetch_quotes(
        [identity("SH", "600000"), identity("SZ", "000001")]
    )

    assert batch.batch_status == "failed"
    assert [item.quality_reason for item in batch.items] == [
        "provider_error",
        "provider_error",
    ]
    assert all(item.current_price is None for item in batch.items)


def test_mootdx_adapter_uses_one_batch_call_with_fake_client():
    class FakeMootdxClient:
        def __init__(self):
            self.calls = []

        def quotes(self, *, symbol):
            self.calls.append(symbol)
            return [valid_row()]

    client = FakeMootdxClient()
    adapter = MootdxStockQuoteAdapter(client_factory=lambda: client)

    rows = adapter.fetch_stock_quotes([identity("SH", "600000")])

    assert client.calls == [["600000"]]
    assert rows == [valid_row()]
