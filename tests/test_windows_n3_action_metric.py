from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ashare_v3.market.windows_n3_action_metric import (
    ACTION_INCREMENTAL_BAR_COUNT,
    ACTION_INITIAL_BAR_COUNT,
    EltdxBoardActionMetricProvider,
    EltdxIndexActionMetricProvider,
    EltdxStockActionMetricProvider,
    build_action_confirmation_metric,
)
from ashare_v3.market.windows_n3_minute_context import (
    NormalizedMinuteBar,
    build_minute_context,
)
from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotRequest,
    IndexSnapshotRequest,
    StockSnapshotRequest,
)


def _label(index: int) -> str:
    if index <= 120:
        value = datetime(2000, 1, 1, 9, 30) + timedelta(minutes=index)
    else:
        value = datetime(2000, 1, 1, 13, 0) + timedelta(minutes=index - 120)
    return value.strftime("%H:%M")


def _bars(
    identity: str,
    trade_date: str,
    count: int,
    *,
    amount_factory=lambda index: Decimal(index),
    close_factory=lambda index: Decimal(index) + Decimal("0.5"),
) -> tuple[NormalizedMinuteBar, ...]:
    return tuple(
        NormalizedMinuteBar(
            identity_key=identity,
            trade_date=trade_date,
            minute_index=index,
            time_label=_label(index),
            open=Decimal(index),
            high=Decimal(index) + 1,
            low=Decimal(index) - 1,
            close=close_factory(index),
            amount=amount_factory(index),
        )
        for index in range(1, count + 1)
    )


def _raw_rows(trade_date: str, first: int, last: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(first, last + 1):
        close_time = datetime.strptime(
            f"{trade_date} {_label(index)}", "%Y%m%d %H:%M"
        )
        rows.append(
            {
                "time": close_time - timedelta(minutes=1),
                "open": index,
                "high": index + 1,
                "low": index - 1,
                "close": index + 0.5,
                "amount": 10,
            }
        )
    return rows


def _previous(identity: str):
    return build_minute_context(identity, "20260826", _bars(identity, "20260826", 240))


def test_first_closed_minute_uses_previous_day_price_periods() -> None:
    identity = "stock:SZ:000001"
    metric = build_action_confirmation_metric(
        asset_kind="stock",
        identity_key=identity,
        trade_date="20260827",
        provider="fixture",
        current_bars=_bars(
            identity,
            "20260827",
            1,
            amount_factory=lambda _: Decimal(10),
            close_factory=lambda _: Decimal("300.5"),
        ),
        previous_context=_previous(identity),
        expected_minute_index=1,
    )

    assert metric.metric_ready is True
    assert metric.current_price == Decimal("300.5")
    assert metric.previous_1m_body_high == Decimal("240.5")
    assert metric.previous_5m_body_high == Decimal("240.5")
    assert metric.previous_30m_body_high == Decimal("240.5")
    assert metric.previous_120m_body_high == Decimal("240.5")
    assert metric.current_1m_amount == Decimal(10)
    assert metric.previous_1m_amount is None
    assert metric.previous_5m_full_amount is None
    assert metric.first_1m_amount_default_pass is True
    assert metric.first_5m_amount_default_pass is True
    assert metric.current_5m_virtual_amount == Decimal(150)
    assert metric.current_30m_virtual_amount == Decimal(4650)
    assert metric.previous_day_same_window_amount == Decimal(465)

def test_seventh_minute_uses_closed_current_day_periods_and_calibration() -> None:
    identity = "stock:SZ:000001"
    metric = build_action_confirmation_metric(
        asset_kind="stock",
        identity_key=identity,
        trade_date="20260827",
        provider="fixture",
        current_bars=_bars(
            identity,
            "20260827",
            7,
            amount_factory=lambda _: Decimal(10),
        ),
        previous_context=_previous(identity),
        expected_minute_index=7,
    )

    assert metric.metric_ready is True
    assert metric.previous_5m_period_source == "same_trade_date_previous_period"
    assert metric.previous_5m_body_high == Decimal("5.5")
    assert metric.previous_5m_body_low == Decimal(1)
    assert metric.previous_5m_full_amount == Decimal(50)
    assert metric.previous_1m_body_high == Decimal("6.5")
    assert metric.previous_1m_amount == Decimal(10)
    assert metric.current_5m_virtual_amount == Decimal(20) / Decimal(13) * Decimal(40)
    assert metric.current_30m_virtual_amount == Decimal(70) / Decimal(28) * Decimal(465)
    assert metric.current_price == Decimal("7.5")
    assert metric.amount_unit == "yuan"


@dataclass
class _Series:
    bars: list[dict[str, object]]


class _FakeBars:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, code, **kwargs):
        self.calls.append({"code": code, **kwargs})
        return _Series(self.responses.pop(0))


class _FakeClient:
    def __init__(self, responses):
        self.bars = _FakeBars(responses)


def test_provider_requests_600_then_3_and_only_active_identity() -> None:
    request = StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安银行")
    client = _FakeClient([
        _raw_rows("20260827", 1, 7),
        _raw_rows("20260827", 6, 8),
    ])
    provider = EltdxStockActionMetricProvider(client, max_workers=1)
    previous = {request.identity_key: _previous(request.identity_key)}

    first = provider.fetch_many([request, request], "20260827", previous, 7)
    second = provider.fetch_many([request], "20260827", previous, 8)

    assert first.metrics[request.identity_key].metric_ready is True
    assert second.metrics[request.identity_key].metric_minute_label == "09:38"
    assert [call["count"] for call in client.bars.calls] == [
        ACTION_INITIAL_BAR_COUNT,
        ACTION_INCREMENTAL_BAR_COUNT,
    ]
    assert len(client.bars.calls) == 2


def test_missing_expected_closed_minute_stays_pending() -> None:
    request = StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安银行")
    client = _FakeClient([_raw_rows("20260827", 1, 6)])
    provider = EltdxStockActionMetricProvider(client, max_workers=1)

    batch = provider.fetch_many(
        [request],
        "20260827",
        {request.identity_key: _previous(request.identity_key)},
        7,
    )

    metric = batch.metrics[request.identity_key]
    assert metric.metric_ready is False
    assert metric.error_summary == "expected_closed_minute_missing"
    assert batch.missing_identity_keys == (request.identity_key,)


@pytest.mark.parametrize(
    ("provider_class", "security_request", "expected_code", "expected_kind"),
    (
        (
            EltdxStockActionMetricProvider,
            StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安银行"),
            "sz000001",
            "stock",
        ),
        (
            EltdxIndexActionMetricProvider,
            IndexSnapshotRequest("index:SH:000001", "SH", "000001", "上证指数"),
            "sh000001",
            "index",
        ),
        (
            EltdxBoardActionMetricProvider,
            BoardSnapshotRequest("board:SH:881333", "SH", "881333", "元器件"),
            "sh881333",
            "index",
        ),
    ),
)
def test_three_provider_transport_contracts_are_independent(
    provider_class,
    security_request,
    expected_code,
    expected_kind,
) -> None:
    client = _FakeClient([_raw_rows("20260827", 1, 1)])
    provider = provider_class(client, max_workers=1)

    batch = provider.fetch_many(
        [security_request],
        "20260827",
        {security_request.identity_key: _previous(security_request.identity_key)},
        1,
    )

    assert batch.metrics[security_request.identity_key].metric_ready is True
    assert client.bars.calls[0]["code"] == expected_code
    assert client.bars.calls[0]["kind"] == expected_kind
    assert client.bars.calls[0]["period"] == "1m"


def test_incomplete_previous_context_stays_pending() -> None:
    identity = "stock:SZ:000001"
    incomplete = build_minute_context(
        identity, "20260826", _bars(identity, "20260826", 239)
    )
    metric = build_action_confirmation_metric(
        asset_kind="stock",
        identity_key=identity,
        trade_date="20260827",
        provider="fixture",
        current_bars=_bars(identity, "20260827", 1),
        previous_context=incomplete,
        expected_minute_index=1,
    )

    assert metric.metric_ready is False
    assert metric.error_summary == "previous_day_context_incomplete"


def test_module_has_no_database_outbox_or_n5_dependency() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "ashare_v3"
        / "market"
        / "windows_n3_action_metric.py"
    ).read_text(encoding="utf-8")

    assert "psycopg" not in source
    assert "outbox" not in source.lower()
    assert "ashare_v3.action" not in source
    assert "ashare_v3.trigger" not in source
