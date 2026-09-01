from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock

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
    PreviousDayMinuteContext,
    ThirtyMinuteWindow,
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


def _raw_rows(
    trade_date: str,
    first: int,
    last: int,
    *,
    start_labelled: bool = True,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(first, last + 1):
        close_time = datetime.strptime(
            f"{trade_date} {_label(index)}", "%Y%m%d %H:%M"
        )
        rows.append(
            {
                "time": (
                    close_time - timedelta(minutes=1)
                    if start_labelled
                    else close_time
                ),
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


def _compressed_previous(identity: str) -> PreviousDayMinuteContext:
    context = _previous(identity)
    return PreviousDayMinuteContext(
        identity_key=context.identity_key,
        source_trade_date=context.source_trade_date,
        bars=(),
        cumulative_day_amounts=context.cumulative_day_amounts,
        windows=context.windows,
    )


def _persisted_previous_template() -> PreviousDayMinuteContext:
    identity = "fixture:SH:000000"
    context = build_minute_context(
        identity,
        "20260831",
        _bars(identity, "20260831", 240),
    )
    windows = tuple(
        ThirtyMinuteWindow(
            bucket_index=window.bucket_index,
            bars=(),
            cumulative_amounts=window.cumulative_amounts,
            full_amount=window.full_amount,
            open=window.open,
            high=window.high,
            low=window.low,
            close=window.close,
        )
        for window in context.windows
    )
    return replace(context, bars=(), windows=windows)


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
    assert metric.metric_time is not None
    assert metric.metric_time.isoformat() == "2026-08-27T09:31:00+08:00"
    assert metric.metric_time == metric.metric_time.astimezone(timezone.utc)

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


class _SharedRowsBars:
    def __init__(self, rows):
        self.rows = tuple(rows)
        self.calls: list[dict[str, object]] = []
        self._lock = Lock()

    def get(self, code, **kwargs):
        with self._lock:
            self.calls.append({"code": code, **kwargs})
        return _Series(self.rows)


class _SharedRowsClient:
    def __init__(self, rows):
        self.bars = _SharedRowsBars(rows)


NATURAL_ACTION_ELIGIBLE_COUNTS_20260901 = {
    "stock": 664,
    "index": 6,
    "board": 32,
}


def _natural_requests(asset_kind: str, count: int):
    if asset_kind == "stock":
        return tuple(
            StockSnapshotRequest(
                f"stock:SZ:{index:06d}",
                "SZ",
                f"{index:06d}",
                f"stock-{index}",
            )
            for index in range(1, count + 1)
        )
    if asset_kind == "index":
        return tuple(
            IndexSnapshotRequest(
                f"index:SH:{index:06d}",
                "SH",
                f"{index:06d}",
                f"index-{index}",
            )
            for index in range(1, count + 1)
        )
    return tuple(
        BoardSnapshotRequest(
            f"board:SH:{881000 + index:06d}",
            "SH",
            f"{881000 + index:06d}",
            f"board-{index}",
        )
        for index in range(1, count + 1)
    )


def test_natural_702_action_eligible_first_minute_provider_load_isolated_by_channel() -> None:
    rows = (
        _raw_rows("20260831", 1, 240)
        + _raw_rows("20260901", 1, 1)
    )
    template = _persisted_previous_template()
    provider_classes = {
        "stock": EltdxStockActionMetricProvider,
        "index": EltdxIndexActionMetricProvider,
        "board": EltdxBoardActionMetricProvider,
    }
    clients = {
        asset_kind: _SharedRowsClient(rows)
        for asset_kind in NATURAL_ACTION_ELIGIBLE_COUNTS_20260901
    }
    requests = {
        asset_kind: _natural_requests(asset_kind, count)
        for asset_kind, count in NATURAL_ACTION_ELIGIBLE_COUNTS_20260901.items()
    }
    contexts = {
        asset_kind: {
            request.identity_key: replace(
                template,
                identity_key=request.identity_key,
            )
            for request in channel_requests
        }
        for asset_kind, channel_requests in requests.items()
    }
    providers = {
        asset_kind: provider_classes[asset_kind](
            clients[asset_kind],
            max_workers=16,
        )
        for asset_kind in requests
    }

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            asset_kind: pool.submit(
                providers[asset_kind].fetch_many,
                requests[asset_kind],
                "20260901",
                contexts[asset_kind],
                1,
            )
            for asset_kind in requests
        }
        batches = {
            asset_kind: future.result()
            for asset_kind, future in futures.items()
        }

    for asset_kind, expected_count in NATURAL_ACTION_ELIGIBLE_COUNTS_20260901.items():
        batch = batches[asset_kind]
        assert len(batch.metrics) == expected_count
        assert batch.missing_identity_keys == ()
        assert batch.errors == ()
        assert batch.pending_reason_counts == {}
        assert all(metric.metric_ready for metric in batch.metrics.values())
        assert {
            metric.metric_minute_label for metric in batch.metrics.values()
        } == {"09:31"}
        assert {
            metric.metric_time.utcoffset() for metric in batch.metrics.values()
        } == {timedelta(hours=8)}
        assert len(clients[asset_kind].bars.calls) == expected_count
        assert {
            call["count"] for call in clients[asset_kind].bars.calls
        } == {ACTION_INITIAL_BAR_COUNT}


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


@pytest.mark.parametrize(
    ("provider_class", "security_request"),
    (
        (
            EltdxStockActionMetricProvider,
            StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安银行"),
        ),
        (
            EltdxIndexActionMetricProvider,
            IndexSnapshotRequest("index:SH:000001", "SH", "000001", "上证指数"),
        ),
        (
            EltdxBoardActionMetricProvider,
            BoardSnapshotRequest("board:SH:881333", "SH", "881333", "元器件"),
        ),
    ),
)
def test_three_channels_rebuild_previous_prices_from_initial_history(
    provider_class,
    security_request,
) -> None:
    identity = security_request.identity_key
    client = _FakeClient([
        _raw_rows("20260826", 1, 240) + _raw_rows("20260827", 1, 7),
    ])
    provider = provider_class(client, max_workers=1)

    batch = provider.fetch_many(
        [security_request],
        "20260827",
        {identity: _compressed_previous(identity)},
        7,
    )

    metric = batch.metrics[identity]
    assert metric.metric_ready is True
    assert metric.metric_minute_label == "09:37"
    assert metric.previous_1m_body_high == Decimal("6.5")
    assert metric.previous_5m_body_high == Decimal("5.5")
    assert metric.previous_30m_body_high == Decimal("240.5")
    assert metric.previous_120m_body_high == Decimal("240.5")
    assert metric.current_5m_virtual_amount == Decimal(20) / Decimal(13) * Decimal(40)
    assert metric.current_30m_virtual_amount == Decimal(70) / Decimal(28) * Decimal(465)
    assert batch.pending_reason_counts == {}


def test_close_labelled_eltdx_rows_are_not_shifted_twice() -> None:
    request = StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安银行")
    client = _FakeClient([
        _raw_rows("20260826", 1, 240, start_labelled=False)
        + _raw_rows("20260827", 1, 7, start_labelled=False),
    ])
    provider = EltdxStockActionMetricProvider(client, max_workers=1)

    batch = provider.fetch_many(
        [request],
        "20260827",
        {request.identity_key: _compressed_previous(request.identity_key)},
        7,
    )

    metric = batch.metrics[request.identity_key]
    assert metric.metric_ready is True
    assert metric.observed_minute_index == 7
    assert metric.metric_minute_label == "09:37"


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
    assert batch.pending_reason_counts == {"expected_closed_minute_missing": 1}


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
    assert metric.error_summary == "previous_day_amount_context_incomplete"


@pytest.mark.parametrize(
    ("provider_class", "security_request", "expected_provider"),
    (
        (
            EltdxStockActionMetricProvider,
            StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安银行"),
            "eltdx.stock.closed_1m",
        ),
        (
            EltdxIndexActionMetricProvider,
            IndexSnapshotRequest("index:SH:000001", "SH", "000001", "上证指数"),
            "eltdx.index.closed_1m",
        ),
        (
            EltdxBoardActionMetricProvider,
            BoardSnapshotRequest("board:SH:881333", "SH", "881333", "元器件"),
            "eltdx.board.closed_1m",
        ),
    ),
)
def test_three_channels_report_previous_price_context_pending_reason(
    provider_class,
    security_request,
    expected_provider,
) -> None:
    client = _FakeClient([_raw_rows("20260827", 1, 1)])
    provider = provider_class(client, max_workers=1)

    batch = provider.fetch_many(
        [security_request],
        "20260827",
        {security_request.identity_key: _compressed_previous(security_request.identity_key)},
        1,
    )

    metric = batch.metrics[security_request.identity_key]
    assert metric.metric_ready is False
    assert metric.error_summary == "previous_day_price_context_incomplete"
    assert batch.provider == expected_provider
    assert batch.pending_reason_counts == {
        "previous_day_price_context_incomplete": 1,
    }


@pytest.mark.parametrize(
    ("asset_kind", "provider_class", "security_request"),
    (
        (
            "stock",
            EltdxStockActionMetricProvider,
            StockSnapshotRequest("stock:SZ:000001", "SZ", "000001", "平安银行"),
        ),
        (
            "index",
            EltdxIndexActionMetricProvider,
            IndexSnapshotRequest("index:SH:000001", "SH", "000001", "上证指数"),
        ),
        (
            "board",
            EltdxBoardActionMetricProvider,
            BoardSnapshotRequest("board:SH:881333", "SH", "881333", "元器件"),
        ),
    ),
)
def test_three_channels_convert_metric_build_exception_to_structured_pending(
    asset_kind,
    provider_class,
    security_request,
) -> None:
    template = _persisted_previous_template()
    broken_context = replace(
        template,
        identity_key=security_request.identity_key,
        cumulative_day_amounts=(Decimal("NaN"),)
        + template.cumulative_day_amounts[1:],
    )
    client = _SharedRowsClient(
        _raw_rows("20260831", 1, 240)
        + _raw_rows("20260901", 1, 1)
    )
    provider = provider_class(client, max_workers=1)

    batch = provider.fetch_many(
        [security_request],
        "20260901",
        {security_request.identity_key: broken_context},
        1,
    )

    metric = batch.metrics[security_request.identity_key]
    assert metric.metric_ready is False
    assert metric.metric_quality_status == "pending"
    assert metric.error_summary == "provider_metric_build_failed"
    assert metric.observed_minute_index == 1
    assert batch.missing_identity_keys == (security_request.identity_key,)
    assert batch.pending_reason_counts == {
        "provider_metric_build_failed": 1,
    }
    assert len(batch.errors) == 1
    assert f"asset_kind={asset_kind}" in batch.errors[0]
    assert f"identity_key={security_request.identity_key}" in batch.errors[0]
    assert "phase=build_action_metric" in batch.errors[0]
    assert "error_type=InvalidOperation" in batch.errors[0]


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
