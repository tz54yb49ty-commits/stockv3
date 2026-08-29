from __future__ import annotations

from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from ashare_v3.action.windows_n5_episode import (
    WindowsN5EpisodePlanner,
)
from ashare_v3.action.windows_n5_transaction import (
    WindowsN5TransactionCoordinator,
)
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
from ashare_v3.trigger.windows_n4_transaction import (
    WindowsN4TransactionCoordinator,
)
from ashare_v3.runtime_control.windows_n3_n4_n5_memory import (
    N5ChannelTransactionBoundary,
    WindowsN3N4N5MemoryOrchestrator,
)
from ashare_v3.trigger.windows_n4_memory import (
    BoardRuntimeState,
    IndexRuntimeState,
    N4MemoryCycleResult,
    RuntimeStateSnapshot,
    StockRuntimeState,
)
from tests.test_windows_n4_transaction import (
    _FakeConnection as _N4FakeConnection,
)
from tests.test_windows_n5_transaction import (
    _FakeConnection as _N5FakeConnection,
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


class _FailOnTransactionConnection(_N5FakeConnection):
    def __init__(self, fail_on_transaction: int) -> None:
        super().__init__()
        self.fail_on_transaction = fail_on_transaction

    def transaction(self):
        self.fail_commit = (
            self.begin_count + 1 == self.fail_on_transaction
        )
        return super().transaction()


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


def _orchestrator(
    n4_runtime,
    providers,
    *,
    n4_restore_events=None,
    n5_restore_events=None,
    n5_transaction_boundaries=None,
):
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
        n5_transaction_boundaries=n5_transaction_boundaries,
        n4_restore_events=n4_restore_events,
        n5_restore_events=n5_restore_events,
    )


def _transaction_boundaries(
    *,
    n4_connections=None,
    n5_connections=None,
):
    n4_values = (
        {
            kind: _N4FakeConnection()
            for kind in IDENTITIES
        }
        if n4_connections is None
        else dict(n4_connections)
    )
    n5_values = (
        {
            kind: _N5FakeConnection()
            for kind in IDENTITIES
        }
        if n5_connections is None
        else dict(n5_connections)
    )
    boundaries = {
        kind: N5ChannelTransactionBoundary(
            n4_connection=n4_values[kind],
            n4_coordinator=WindowsN4TransactionCoordinator(
                json_adapter=lambda value: value,
            ),
            connection=n5_values[kind],
            coordinator=WindowsN5TransactionCoordinator(
                consumer_name=f"windows_n5_{kind}_state_v1",
                json_adapter=lambda value: value,
            ),
        )
        for kind in IDENTITIES
    }
    return boundaries, n4_values, n5_values


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


def test_market_close_expires_pending_when_all_providers_fail() -> None:
    observed_at = _time("15:00:05")
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
        kind: _MetricProvider(kind, fail=True)
        for kind in IDENTITIES
    }
    runtime = _orchestrator(n4_runtime, providers)

    result = runtime.consume_cycle(SimpleNamespace(generated_at=observed_at))

    for kind in IDENTITIES:
        channel = getattr(result, kind)
        assert [event.event_type for event in channel.n5_events] == [
            "ActionEligible",
            "ActionSkipped",
        ]
        assert (
            channel.n5_events[-1].payload_json["skipped_reason"]
            == "window_expired"
        )
        assert channel.requested_identity_keys == (IDENTITIES[kind][0],)
        assert len(channel.n5_snapshot.runtime_states) == 0
        assert providers[kind].calls == [((IDENTITIES[kind][0],), 240)]

    summary = runtime.read_summary().as_dict()
    assert summary["completed_minute_index"] == 240
    assert summary["n5_state_counts"] == {
        "stock": 0,
        "index": 0,
        "board": 0,
    }
    for kind in IDENTITIES:
        assert summary["n5_action_event_counts"][kind] == {
            "ActionEligible": 1,
            "ActionSkipped": 1,
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
    assert "WindowsN4OutboxReadOnlyRepository" in source
    assert "initial_versions=n4_restore.last_versions" in source
    assert "n4_restore_events=n4_restore.events" in source
    assert "WindowsN5EpisodeReadOnlyRepository" in source
    assert "n5_restore_events=n5_restore.events" in source
    assert "_open_transaction_boundaries" in source
    assert "n5_transaction_boundaries=transaction_boundaries" in source
    assert "event_persistence_count" in source
    assert 'payload["database_write_count"] = sum(' in source



def test_0915_entry_opens_six_managed_transaction_connections() -> None:
    from scripts.run_windows_n3_n4_memory import (
        N5_CONSUMER_NAME,
        _open_transaction_boundaries,
    )

    opened = []

    def connect(dsn):
        assert dsn == "postgresql://fixture"
        connection = (
            _N4FakeConnection()
            if len(opened) % 2 == 0
            else _N5FakeConnection()
        )
        opened.append(connection)
        return nullcontext(connection)

    with ExitStack() as stack:
        boundaries = _open_transaction_boundaries(
            stack,
            "postgresql://fixture",
            connect=connect,
        )

    assert set(boundaries) == set(IDENTITIES)
    assert len(opened) == 6
    assert len({id(connection) for connection in opened}) == 6
    for index, kind in enumerate(IDENTITIES):
        boundary = boundaries[kind]
        assert boundary.n4_connection is opened[index * 2]
        assert boundary.connection is opened[index * 2 + 1]
        assert boundary.coordinator.consumer_name == N5_CONSUMER_NAME


def test_restart_restores_three_n4_channels_before_first_cycle() -> None:
    matched_at = _time("09:35:05")
    providers = {
        kind: _MetricProvider(kind)
        for kind in IDENTITIES
    }
    original = _orchestrator(
        _FakeN4Runtime(
            [
                _memory_result(
                    version=7,
                    observed_at=matched_at,
                    active=True,
                )
            ]
        ),
        providers,
    )
    first = original.consume_cycle(
        SimpleNamespace(generated_at=matched_at)
    )
    restore_events = {
        kind: getattr(first, kind).trigger_batch.events
        for kind in IDENTITIES
    }
    assert {
        kind: len(events)
        for kind, events in restore_events.items()
    } == {"stock": 1, "index": 1, "board": 1}

    unchanged = _orchestrator(
        _FakeN4Runtime(
            [
                _memory_result(
                    version=8,
                    observed_at=_time("09:40:05"),
                    active=True,
                )
            ]
        ),
        {
            kind: _MetricProvider(kind)
            for kind in IDENTITIES
        },
        n4_restore_events=restore_events,
    )
    unchanged_result = unchanged.consume_cycle(
        SimpleNamespace(generated_at=_time("09:40:05"))
    )
    for kind in IDENTITIES:
        assert getattr(unchanged_result, kind).trigger_batch.events == ()
    unchanged_summary = unchanged.read_summary().as_dict()
    assert unchanged_summary["n4_restored_event_counts"] == {
        "stock": 1,
        "index": 1,
        "board": 1,
    }
    assert unchanged_summary["n4_restored_versions"] == {
        "stock": 7,
        "index": 7,
        "board": 7,
    }

    inactive = _orchestrator(
        _FakeN4Runtime(
            [
                _memory_result(
                    version=8,
                    observed_at=_time("09:40:05"),
                    active=False,
                )
            ]
        ),
        {
            kind: _MetricProvider(kind)
            for kind in IDENTITIES
        },
        n4_restore_events=restore_events,
    )
    inactive_result = inactive.consume_cycle(
        SimpleNamespace(generated_at=_time("09:40:05"))
    )
    for kind in IDENTITIES:
        events = getattr(inactive_result, kind).trigger_batch.events
        assert [event.event_type for event in events] == [
            "TriggerStateChanged"
        ]
        assert events[0].payload_json["trigger_live"] is False


def test_restart_restores_three_n5_channels_before_first_cycle() -> None:
    matched_at = _time("09:35:05")
    original = _orchestrator(
        _FakeN4Runtime(
            [
                _memory_result(
                    version=7,
                    observed_at=matched_at,
                    active=True,
                )
            ]
        ),
        {
            kind: _MetricProvider(kind)
            for kind in IDENTITIES
        },
    )
    first = original.consume_cycle(
        SimpleNamespace(generated_at=matched_at)
    )
    n4_restore_events = {
        kind: getattr(first, kind).trigger_batch.events
        for kind in IDENTITIES
    }
    n5_restore_events = {}
    for kind in IDENTITIES:
        matched = n4_restore_events[kind][0]
        planner = WindowsN5EpisodePlanner(
            asset_kind=kind,
            action_run_id=f"action_{kind}_fixture",
        )
        eligible = planner.consume_trigger_event(matched).events[0]
        n5_restore_events[kind] = (matched, eligible)

    restored = _orchestrator(
        _FakeN4Runtime(
            [
                _memory_result(
                    version=8,
                    observed_at=_time("09:40:05"),
                    active=True,
                )
            ]
        ),
        {
            kind: _MetricProvider(kind)
            for kind in IDENTITIES
        },
        n4_restore_events=n4_restore_events,
        n5_restore_events=n5_restore_events,
    )
    before_first_cycle = restored.read_summary().as_dict()
    assert before_first_cycle["n5_restored_event_counts"] == {
        "stock": 2,
        "index": 2,
        "board": 2,
    }
    assert before_first_cycle["n5_restored_episode_counts"] == {
        "stock": 1,
        "index": 1,
        "board": 1,
    }
    assert before_first_cycle["n5_restored_versions"] == {
        "stock": 2,
        "index": 2,
        "board": 2,
    }
    assert before_first_cycle["n5_state_counts"] == {
        "stock": 1,
        "index": 1,
        "board": 1,
    }

    first_after_restart = restored.consume_cycle(
        SimpleNamespace(generated_at=_time("09:40:05"))
    )
    for kind in IDENTITIES:
        result = getattr(first_after_restart, kind)
        assert result.trigger_batch.events == ()
        assert all(
            event.event_type != "ActionEligible"
            for event in result.n5_events
        )


def test_three_channels_commit_n4_and_closed_minute_in_separate_transactions() -> None:
    observed_at = _time("09:31:05")
    boundaries, n4_connections, n5_connections = (
        _transaction_boundaries()
    )
    runtime = _orchestrator(
        _FakeN4Runtime(
            [
                _memory_result(
                    version=1,
                    observed_at=observed_at,
                    active=True,
                )
            ]
        ),
        {
            kind: _MetricProvider(kind)
            for kind in IDENTITIES
        },
        n5_transaction_boundaries=boundaries,
    )

    result = runtime.consume_cycle(
        SimpleNamespace(generated_at=observed_at)
    )

    for kind in IDENTITIES:
        channel = getattr(result, kind)
        n4_connection = n4_connections[kind]
        n5_connection = n5_connections[kind]
        assert [event.event_type for event in channel.n5_events] == [
            "ActionEligible",
            "ActionExecuted",
        ]
        assert n4_connection.begin_count == 1
        assert n4_connection.commit_count == 1
        assert n4_connection.rollback_count == 0
        assert len(n4_connection.fake_cursor.rows) == 1
        authoritative_outbox_id = next(
            iter(n4_connection.fake_cursor.rows.values())
        )[0]
        assert n5_connection.begin_count == 2
        assert n5_connection.commit_count == 2
        assert n5_connection.rollback_count == 0
        assert len(n5_connection.fake_cursor.inbox) == 1
        assert len(n5_connection.fake_cursor.outbox) == 2
        assert len(n5_connection.fake_cursor.checkpoints) == 1
        assert set(n5_connection.fake_cursor.checkpoints.values()) == {
            authoritative_outbox_id
        }
    summary = runtime.read_summary().as_dict()
    assert summary["database_write_counts"] == {
        "stock": 5,
        "index": 5,
        "board": 5,
    }
    assert summary["event_persistence_counts"] == {
        "stock": 3,
        "index": 3,
        "board": 3,
    }


def test_n4_failure_keeps_n4_planner_and_never_calls_n5() -> None:
    observed_at = _time("09:30:05")
    n4_connections = {
        kind: _N4FakeConnection()
        for kind in IDENTITIES
    }
    n4_connections["stock"].fail_commit = True
    boundaries, n4_connections, n5_connections = (
        _transaction_boundaries(n4_connections=n4_connections)
    )
    runtime = _orchestrator(
        _FakeN4Runtime([]),
        {
            kind: _MetricProvider(kind)
            for kind in IDENTITIES
        },
        n5_transaction_boundaries=boundaries,
    )
    stock = runtime._channels["stock"]
    snapshot = _snapshot(
        "stock",
        version=1,
        observed_at=observed_at,
        active=True,
    )

    with pytest.raises(RuntimeError, match="fixture commit failure"):
        stock.consume(snapshot, 0)

    with pytest.raises(RuntimeError, match="no N4 snapshot"):
        stock.n4.read()
    assert stock.n5.read().active == {}
    assert n4_connections["stock"].rollback_count == 1
    assert n5_connections["stock"].begin_count == 0
    assert stock._pending_n4_deliveries == ()
    assert stock.database_write_count == 0
    assert stock.event_persistence_count == 0
    failed_insert = n4_connections["stock"].fake_cursor.calls[0][1]

    n4_connections["stock"].fail_commit = False
    retry = stock.consume(snapshot, 0)
    retry_insert = n4_connections["stock"].fake_cursor.calls[1][1]

    assert [event.event_type for event in retry.n5_events] == [
        "ActionEligible"
    ]
    assert failed_insert[0] == retry_insert[0]
    assert failed_insert[9] == retry_insert[9]
    assert stock.n4.read().source_n4_version == 1
    assert len(stock.n5.read().active) == 1


def test_n5_failure_replays_already_committed_authoritative_n4_row() -> None:
    first_at = _time("09:30:05")
    second_at = _time("09:30:30")
    n5_connections = {
        kind: _N5FakeConnection()
        for kind in IDENTITIES
    }
    n5_connections["stock"].fail_commit = True
    boundaries, n4_connections, n5_connections = (
        _transaction_boundaries(n5_connections=n5_connections)
    )
    runtime = _orchestrator(
        _FakeN4Runtime([]),
        {
            kind: _MetricProvider(kind)
            for kind in IDENTITIES
        },
        n5_transaction_boundaries=boundaries,
    )
    stock = runtime._channels["stock"]

    with pytest.raises(RuntimeError, match="fixture commit failure"):
        stock.consume(
            _snapshot(
                "stock",
                version=1,
                observed_at=first_at,
                active=True,
            ),
            0,
        )

    assert stock.n4.read().source_n4_version == 1
    assert stock.n5.read().active == {}
    assert n4_connections["stock"].commit_count == 1
    assert len(n4_connections["stock"].fake_cursor.rows) == 1
    authoritative_outbox_id = next(
        iter(n4_connections["stock"].fake_cursor.rows.values())
    )[0]
    assert tuple(
        delivery.outbox_id
        for delivery in stock._pending_n4_deliveries
    ) == (authoritative_outbox_id,)
    assert n5_connections["stock"].rollback_count == 1
    assert stock.database_write_count == 1
    assert stock.event_persistence_count == 1

    n5_connections["stock"].fail_commit = False
    retry = stock.consume(
        _snapshot(
            "stock",
            version=2,
            observed_at=second_at,
            active=True,
        ),
        0,
    )

    assert [event.event_type for event in retry.n5_events] == [
        "ActionEligible"
    ]
    assert len(stock.n5.read().active) == 1
    assert stock._pending_n4_deliveries == ()
    assert any(
        values[9]["source_outbox_id"] == authoritative_outbox_id
        for sql, values in n5_connections["stock"].fake_cursor.calls
        if "INSERT INTO common_event_inbox" in sql
    )


def test_closed_minute_failure_keeps_eligible_planner_then_retries() -> None:
    first_at = _time("09:31:05")
    second_at = _time("09:31:30")
    n5_connections = {
        "stock": _FailOnTransactionConnection(2),
        "index": _N5FakeConnection(),
        "board": _N5FakeConnection(),
    }
    boundaries, n4_connections, n5_connections = (
        _transaction_boundaries(n5_connections=n5_connections)
    )
    providers = {
        kind: _MetricProvider(kind)
        for kind in IDENTITIES
    }
    runtime = _orchestrator(
        _FakeN4Runtime(
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
                ),
            ]
        ),
        providers,
        n5_transaction_boundaries=boundaries,
    )

    with pytest.raises(RuntimeError, match="fixture commit failure"):
        runtime.consume_cycle(SimpleNamespace(generated_at=first_at))

    stock_channel = runtime._channels["stock"]
    active = next(iter(stock_channel.n5.read().active.values()))
    assert active.action_state == "eligible"
    assert stock_channel.metric_watermarks == {}
    assert n4_connections["stock"].commit_count == 1
    assert n5_connections["stock"].commit_count == 1
    assert n5_connections["stock"].rollback_count == 1
    assert runtime.read_summary().n5_action_event_counts["stock"] == {
        "ActionEligible": 1,
    }

    retry = runtime.consume_cycle(
        SimpleNamespace(generated_at=second_at)
    )

    assert [event.event_type for event in retry.stock.n5_events] == [
        "ActionExecuted"
    ]
    executed = next(iter(retry.stock.n5_snapshot.active.values()))
    assert executed.action_state == "executed"
    assert providers["stock"].calls == [
        ((IDENTITIES["stock"][0],), 1),
        ((IDENTITIES["stock"][0],), 1),
    ]
    executed_writes = [
        values
        for sql, values in n5_connections["stock"].fake_cursor.calls
        if "INSERT INTO common_event_outbox" in sql
        and values[1] == "ActionExecuted"
    ]
    assert len(executed_writes) == 2
    assert executed_writes[0][0] == executed_writes[1][0]
    assert executed_writes[0][9] == executed_writes[1][9]


def test_market_close_action_skipped_uses_transaction_boundary() -> None:
    observed_at = _time("15:00:05")
    boundaries, n4_connections, n5_connections = (
        _transaction_boundaries()
    )
    runtime = _orchestrator(
        _FakeN4Runtime(
            [
                _memory_result(
                    version=1,
                    observed_at=observed_at,
                    active=True,
                )
            ]
        ),
        {
            kind: _MetricProvider(kind, fail=True)
            for kind in IDENTITIES
        },
        n5_transaction_boundaries=boundaries,
    )

    result = runtime.consume_cycle(
        SimpleNamespace(generated_at=observed_at)
    )

    for kind in IDENTITIES:
        channel = getattr(result, kind)
        n4_connection = n4_connections[kind]
        n5_connection = n5_connections[kind]
        assert [event.event_type for event in channel.n5_events] == [
            "ActionEligible",
            "ActionSkipped",
        ]
        assert n4_connection.begin_count == 1
        assert n4_connection.commit_count == 1
        assert n4_connection.rollback_count == 0
        assert n5_connection.begin_count == 2
        assert n5_connection.commit_count == 2
        assert n5_connection.rollback_count == 0
        event_types = [
            values[1]
            for sql, values in n5_connection.fake_cursor.calls
            if "INSERT INTO common_event_outbox" in sql
        ]
        assert event_types == ["ActionEligible", "ActionSkipped"]


def test_transaction_mode_requires_three_channel_local_connections() -> None:
    providers = {
        kind: _MetricProvider(kind)
        for kind in IDENTITIES
    }
    boundaries, _n4_connections, _n5_connections = (
        _transaction_boundaries()
    )

    incomplete = dict(boundaries)
    del incomplete["board"]
    with pytest.raises(
        ValueError,
        match="must contain stock/index/board",
    ):
        _orchestrator(
            _FakeN4Runtime([]),
            providers,
            n5_transaction_boundaries=incomplete,
        )

    shared_n4 = dict(boundaries)
    shared_n4["board"] = N5ChannelTransactionBoundary(
        n4_connection=shared_n4["stock"].n4_connection,
        n4_coordinator=shared_n4["board"].n4_coordinator,
        connection=shared_n4["board"].connection,
        coordinator=shared_n4["board"].coordinator,
    )
    with pytest.raises(
        ValueError,
        match="N4 transaction connections must be channel-local",
    ):
        _orchestrator(
            _FakeN4Runtime([]),
            providers,
            n5_transaction_boundaries=shared_n4,
        )

    shared_n5 = dict(boundaries)
    shared_n5["board"] = N5ChannelTransactionBoundary(
        n4_connection=shared_n5["board"].n4_connection,
        n4_coordinator=shared_n5["board"].n4_coordinator,
        connection=shared_n5["stock"].connection,
        coordinator=shared_n5["board"].coordinator,
    )
    with pytest.raises(
        ValueError,
        match="N5 transaction connections must be channel-local",
    ):
        _orchestrator(
            _FakeN4Runtime([]),
            providers,
            n5_transaction_boundaries=shared_n5,
        )


def test_transaction_runtime_constructs_no_external_clients() -> None:
    source = Path(
        "src/ashare_v3/runtime_control/windows_n3_n4_n5_memory.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "psycopg.connect",
        "TdxClient(",
        "Register-ScheduledTask",
        "ashare_v3.user",
    ):
        assert forbidden not in source
