from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

from ashare_v3.market.windows_n3_action_metric import (
    ActionMetricBatch,
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
from ashare_v3.runtime_control.windows_n3_n4_n5_memory import (
    WindowsN3N4N5MemoryOrchestrator,
)
from ashare_v3.trigger.windows_n4_memory import (
    BoardRuntimeState,
    IndexRuntimeState,
    N4MemoryCycleResult,
    RuntimeStateSnapshot,
    StockRuntimeState,
)


SOURCE_RUN_ID = "condition_layer_20260826_to_20260827_fixture"
IDENTITIES = {
    "stock": ("stock:SZ:000001", "SZ", "000001", "stock fixture"),
    "index": ("index:SH:000001", "SH", "000001", "index fixture"),
    "board": ("board:SH:881333", "SH", "881333", "board fixture"),
}
INACTIVE_IDENTITIES = {
    "stock": ("stock:SZ:000002", "SZ", "000002", "stock inactive"),
    "index": ("index:SH:000002", "SH", "000002", "index inactive"),
    "board": ("board:SH:881334", "SH", "881334", "board inactive"),
}
REQUEST_TYPES = {
    "stock": StockSnapshotRequest,
    "index": IndexSnapshotRequest,
    "board": BoardSnapshotRequest,
}
STATE_TYPES = {
    "stock": StockRuntimeState,
    "index": IndexRuntimeState,
    "board": BoardRuntimeState,
}


def _time(label: str) -> datetime:
    return datetime.fromisoformat(f"2026-08-27T{label}+08:00")


def _label(index: int) -> str:
    if index <= 120:
        value = datetime(2000, 1, 1, 9, 30) + timedelta(minutes=index)
    else:
        value = datetime(2000, 1, 1, 13, 0) + timedelta(minutes=index - 120)
    return value.strftime("%H:%M")


def _bars(
    identity_key: str,
    trade_date: str,
    count: int,
    *,
    current: bool = False,
) -> tuple[NormalizedMinuteBar, ...]:
    offset = Decimal("300") if current else Decimal("0")
    return tuple(
        NormalizedMinuteBar(
            identity_key=identity_key,
            trade_date=trade_date,
            minute_index=index,
            time_label=_label(index),
            open=Decimal(index) + offset,
            high=Decimal(index + 1) + offset,
            low=Decimal(index - 1) + offset,
            close=Decimal(index) + Decimal("0.5") + offset,
            amount=Decimal("10"),
        )
        for index in range(1, count + 1)
    )


def _previous(identity_key: str):
    return build_minute_context(
        identity_key,
        "20260826",
        _bars(identity_key, "20260826", 240),
    )


def _state(
    asset_kind: str,
    identity: tuple[str, str, str, str],
    *,
    version: int,
    observed_at: datetime,
    active: bool,
    fresh: bool = True,
):
    identity_key, exchange, code, name = identity
    source_d = "low_volume_down" if active else "flat"
    live_d = "volume_up" if active else "flat"
    return STATE_TYPES[asset_kind](
        source_condition_run_id=SOURCE_RUN_ID,
        source_trade_date="20260826",
        for_trade_date="20260827",
        asset_kind=asset_kind,
        identity_key=identity_key,
        exchange=exchange,
        code=code,
        name=name,
        source_transitions={
            "30m": "unknown",
            "D": source_d,
            "W": "flat",
            "M": "flat",
            "Q": "flat",
            "Y": "flat",
        },
        source_amounts={
            "30m": None,
            "D": Decimal("10"),
            "W": Decimal("100"),
            "M": Decimal("100"),
            "Q": Decimal("100"),
            "Y": Decimal("100"),
        },
        comparison_amounts={
            "30m": None,
            "D": Decimal("10"),
            "W": Decimal("100"),
            "M": Decimal("100"),
            "Q": Decimal("100"),
            "Y": Decimal("100"),
        },
        realtime_transitions={
            "30m": "none",
            "D": live_d,
            "W": "flat",
            "M": "flat",
            "Q": "flat",
            "Y": "flat",
        },
        realtime_virtual_amounts={
            "30m": Decimal("10"),
            "D": Decimal("10"),
            "W": Decimal("110") if active else Decimal("100"),
            "M": Decimal("100"),
            "Q": Decimal("100"),
            "Y": Decimal("100"),
        },
        current_price=Decimal("300.5") if fresh else None,
        cumulative_amount=Decimal("100000000") if fresh else None,
        source_time=observed_at if fresh else None,
        observed_at=observed_at if fresh else None,
        provider="fixture.snapshot" if fresh else None,
        live_status="available" if fresh else "stale",
        fresh=fresh,
        last_success_at=observed_at,
        last_error=None if fresh else "fixture stale",
        source_n3_version=version,
    )


def _snapshot(
    asset_kind: str,
    *,
    version: int,
    observed_at: datetime,
    active: bool,
    fresh: bool = True,
):
    states = (
        _state(
            asset_kind,
            IDENTITIES[asset_kind],
            version=version,
            observed_at=observed_at,
            active=active,
            fresh=fresh,
        ),
        _state(
            asset_kind,
            INACTIVE_IDENTITIES[asset_kind],
            version=version,
            observed_at=observed_at,
            active=False,
        ),
    )
    return RuntimeStateSnapshot(
        source_condition_run_id=SOURCE_RUN_ID,
        source_trade_date="20260826",
        for_trade_date="20260827",
        version=version,
        source_n3_version=version,
        generated_at=observed_at,
        channel_status="ready",
        states=MappingProxyType(
            {state.identity_key: state for state in states}
        ),
    )


def _memory_result(
    *,
    version: int,
    observed_at: datetime,
    active: bool,
    fresh: bool = True,
) -> N4MemoryCycleResult:
    return N4MemoryCycleResult(
        stock=_snapshot(
            "stock",
            version=version,
            observed_at=observed_at,
            active=active,
            fresh=fresh,
        ),
        index=_snapshot(
            "index",
            version=version,
            observed_at=observed_at,
            active=active,
            fresh=fresh,
        ),
        board=_snapshot(
            "board",
            version=version,
            observed_at=observed_at,
            active=active,
            fresh=fresh,
        ),
    )


class _FakeN4Runtime:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def consume_cycle(self, cycle):
        self.calls.append(cycle)
        return self.results.pop(0)


@dataclass
class _MetricProvider:
    asset_kind: str
    fail: bool = False

    def __post_init__(self):
        self.calls = []

    def fetch_many(
        self,
        requests,
        trade_date,
        previous_contexts,
        expected_minute_index,
    ):
        self.calls.append(
            (
                tuple(request.identity_key for request in requests),
                expected_minute_index,
            )
        )
        if self.fail:
            raise RuntimeError(f"{self.asset_kind} provider failed")
        metrics = {
            request.identity_key: build_action_confirmation_metric(
                asset_kind=self.asset_kind,
                identity_key=request.identity_key,
                trade_date=trade_date,
                provider=f"fixture.{self.asset_kind}.closed_1m",
                current_bars=_bars(
                    request.identity_key,
                    trade_date,
                    expected_minute_index,
                    current=True,
                ),
                previous_context=previous_contexts[request.identity_key],
                expected_minute_index=expected_minute_index,
            )
            for request in requests
        }
        return ActionMetricBatch(
            metrics=metrics,
            missing_identity_keys=(),
            provider=f"fixture.{self.asset_kind}.closed_1m",
        )


def _orchestrator(n4_runtime, providers):
    requests = {}
    previous = {}
    for kind in IDENTITIES:
        request_type = REQUEST_TYPES[kind]
        requests[kind] = tuple(
            request_type(*identity)
            for identity in (
                IDENTITIES[kind],
                INACTIVE_IDENTITIES[kind],
            )
        )
        previous[kind] = {
            request.identity_key: _previous(request.identity_key)
            for request in requests[kind]
        }
    return WindowsN3N4N5MemoryOrchestrator(
        n4_runtime=n4_runtime,
        stock_requests=requests["stock"],
        index_requests=requests["index"],
        board_requests=requests["board"],
        previous_stock=previous["stock"],
        previous_index=previous["index"],
        previous_board=previous["board"],
        stock_metric_provider=providers["stock"],
        index_metric_provider=providers["index"],
        board_metric_provider=providers["board"],
        trigger_run_ids={
            kind: f"trigger_{kind}_fixture"
            for kind in IDENTITIES
        },
        action_run_ids={
            kind: f"action_{kind}_fixture"
            for kind in IDENTITIES
        },
    )


def test_three_channels_deliver_trigger_and_closed_minute_once() -> None:
    observed_at = _time("09:31:05")
    n4_runtime = _FakeN4Runtime(
        [
            _memory_result(
                version=1,
                observed_at=observed_at,
                active=True,
            ),
            _memory_result(
                version=2,
                observed_at=observed_at,
                active=True,
            ),
        ]
    )
    providers = {
        kind: _MetricProvider(kind)
        for kind in IDENTITIES
    }
    runtime = _orchestrator(n4_runtime, providers)

    first = runtime.consume_cycle(SimpleNamespace(generated_at=observed_at))
    second = runtime.consume_cycle(SimpleNamespace(generated_at=observed_at))

    for kind in IDENTITIES:
        channel = getattr(first, kind)
        assert [event.event_type for event in channel.n5_events] == [
            "ActionEligible",
            "ActionExecuted",
        ]
        assert channel.requested_identity_keys == (
            IDENTITIES[kind][0],
        )
        assert len(channel.n5_snapshot.runtime_states) == 1
        runtime_state = next(iter(channel.n5_snapshot.runtime_states.values()))
        assert runtime_state.action_state == "executed"
        assert runtime_state.metric_minute_label == "09:31"
        assert getattr(second, kind).requested_identity_keys == ()
        assert providers[kind].calls == [((IDENTITIES[kind][0],), 1)]

    summary = runtime.read_summary().as_dict()
    assert summary["completed_minute_index"] == 1
    assert summary["n5_state_counts"] == {
        "stock": 1,
        "index": 1,
        "board": 1,
    }
    assert summary["action_metric_identity_request_counts"] == {
        "stock": 1,
        "index": 1,
        "board": 1,
    }
    for kind in IDENTITIES:
        assert summary["n4_trigger_event_counts"][kind] == {
            "TriggerMatched": 1,
        }
        assert summary["n5_action_event_counts"][kind] == {
            "ActionEligible": 1,
            "ActionExecuted": 1,
        }


def test_deactivation_expires_pending_episode_without_market_request() -> None:
    first_at = _time("09:30:05")
    second_at = _time("09:30:30")
    n4_runtime = _FakeN4Runtime(
        [
            _memory_result(
                version=1,
                observed_at=first_at,
                active=True,
            ),
            _memory_result(
                version=2,
                observed_at=second_at,
                active=False,
            ),
        ]
    )
    providers = {
        kind: _MetricProvider(kind)
        for kind in IDENTITIES
    }
    runtime = _orchestrator(n4_runtime, providers)

    first = runtime.consume_cycle(SimpleNamespace(generated_at=first_at))
    second = runtime.consume_cycle(SimpleNamespace(generated_at=second_at))

    for kind in IDENTITIES:
        assert [event.event_type for event in getattr(first, kind).n5_events] == [
            "ActionEligible",
        ]
        assert [event.event_type for event in getattr(second, kind).n5_events] == [
            "ActionSkipped",
        ]
        assert len(getattr(second, kind).n5_snapshot.runtime_states) == 0
        assert providers[kind].calls == []


def test_one_provider_failure_does_not_stop_other_channels() -> None:
    observed_at = _time("09:31:05")
    n4_runtime = _FakeN4Runtime(
        [
            _memory_result(
                version=1,
                observed_at=observed_at,
                active=True,
            )
        ]
    )
    providers = {
        "stock": _MetricProvider("stock", fail=True),
        "index": _MetricProvider("index"),
        "board": _MetricProvider("board"),
    }
    runtime = _orchestrator(n4_runtime, providers)

    result = runtime.consume_cycle(SimpleNamespace(generated_at=observed_at))

    assert result.stock.provider_errors == (
        "RuntimeError:stock provider failed",
    )
    assert [event.event_type for event in result.stock.n5_events] == [
        "ActionEligible",
    ]
    assert [
        event.event_type for event in result.index.n5_events
    ] == ["ActionEligible", "ActionExecuted"]
    assert [
        event.event_type for event in result.board.n5_events
    ] == ["ActionEligible", "ActionExecuted"]
    assert runtime.read_summary().provider_error_counts == {
        "stock": 1,
        "index": 0,
        "board": 0,
    }


def test_stale_n4_evidence_keeps_episode_pending_without_metric_request() -> None:
    first_at = _time("09:30:05")
    second_at = _time("09:31:05")
    n4_runtime = _FakeN4Runtime(
        [
            _memory_result(
                version=1,
                observed_at=first_at,
                active=True,
            ),
            _memory_result(
                version=2,
                observed_at=second_at,
                active=True,
                fresh=False,
            ),
        ]
    )
    providers = {
        kind: _MetricProvider(kind)
        for kind in IDENTITIES
    }
    runtime = _orchestrator(n4_runtime, providers)

    first = runtime.consume_cycle(SimpleNamespace(generated_at=first_at))
    second = runtime.consume_cycle(SimpleNamespace(generated_at=second_at))

    for kind in IDENTITIES:
        assert [event.event_type for event in getattr(first, kind).n5_events] == [
            "ActionEligible",
        ]
        assert getattr(second, kind).n5_events == ()
        assert getattr(second, kind).requested_identity_keys == ()
        state = next(
            iter(getattr(second, kind).n5_snapshot.runtime_states.values())
        )
        assert state.action_state == "eligible"
        assert state.confirmation_status == "pending"
        assert providers[kind].calls == []


def test_0915_entry_uses_same_process_orchestrator() -> None:
    source = (
        Path(__file__).parents[1]
        / "scripts"
        / "run_windows_n3_n4_memory.py"
    ).read_text(encoding="utf-8")

    assert "WindowsN3N4N5MemoryOrchestrator" in source
    assert "EltdxStockActionMetricProvider" in source
    assert "n3_n4_n5_memory" in source
    assert "event_persistence_count" in source
