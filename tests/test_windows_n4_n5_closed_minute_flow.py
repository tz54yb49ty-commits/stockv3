from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import MappingProxyType

import pytest

from ashare_v3.action.windows_n5_episode import WindowsN5EpisodePlanner
from ashare_v3.market.windows_n3_action_metric import (
    build_action_confirmation_metric,
)
from ashare_v3.trigger.windows_n4_memory import (
    BoardRuntimeState,
    IndexRuntimeState,
    RuntimeStateSnapshot,
    StockRuntimeState,
)
from ashare_v3.trigger.windows_n4_state_transition import (
    WindowsN4StateTransitionPlanner,
)
from tests.test_windows_n3_action_metric import _bars, _previous
from tests.test_windows_n4_state_transition import (
    SOURCE_RUN_ID,
    TRIGGER_RUN_ID,
    _planner as n4_planner,
    _snapshot,
    _state,
    _time,
)


def test_actual_n4_ab_lifecycle_drives_n5_episode_lifecycle() -> None:
    n4 = n4_planner()
    n5 = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_end_to_end_fixture",
    )
    sequence = [
        ("09:35", "volume_up", "10.80", "none"),
        ("09:40", "volume_up", "10.90", "none"),
        ("10:00", "volume_up", "10.90", "volume_up"),
        ("10:05", "flat", "9.80", "volume_up"),
        ("10:10", "flat", "9.80", "none"),
        ("10:20", "volume_up", "10.70", "none"),
    ]
    n4_event_types: list[str] = []
    n5_events = []
    n5_snapshots = []
    for version, (label, live_d, live_w, live_30m) in enumerate(sequence, 1):
        state = _state(
            version=version,
            observed_at=_time(label),
            source_d="low_volume_down",
            live_d=live_d,
            source_w="10.00",
            live_w=live_w,
            live_30m=live_30m,
        )
        n4_batch = n4.consume(_snapshot(version, state))
        n4_event_types.extend(event.event_type for event in n4_batch.events)
        for event in n4_batch.events:
            n5_batch = n5.consume_trigger_event(event)
            n5_events.extend(n5_batch.events)
            n5_snapshots.append(n5_batch.snapshot)

    assert n4_event_types == [
        "TriggerMatched",
        "TriggerStateChanged",
        "TriggerStateChanged",
        "TriggerStateChanged",
        "TriggerMatched",
    ]
    assert [event.event_type for event in n5_events] == [
        "ActionEligible",
        "ActionSkipped",
        "ActionEligible",
    ]
    assert n5_events[1].payload_json["skipped_reason"] == "trigger_live_false"
    assert (
        n5_events[0].payload_json["episode_entry_event_id"]
        != n5_events[2].payload_json["episode_entry_event_id"]
    )
    changed_runtime = next(iter(n5_snapshots[1].runtime_states.values()))
    assert changed_runtime.realtime_transitions["30m"] == "volume_up"
    assert changed_runtime.realtime_virtual_amounts["W"] == Decimal("10.90")
    assert changed_runtime.n4_current_price == Decimal("10.00")
    assert changed_runtime.n4_cumulative_amount == Decimal("100000000")
    assert changed_runtime.provider == "fixture"
    assert changed_runtime.live_status == "available"
    assert changed_runtime.fresh is True
    final_episode = tuple(n5.read().active.values())[0]
    assert final_episode.action_state == "eligible"
    assert final_episode.trigger_live is True


@pytest.mark.parametrize(
    ("state_type", "asset_kind", "identity_key", "exchange", "code"),
    [
        (StockRuntimeState, "stock", "stock:SZ:000001", "SZ", "000001"),
        (IndexRuntimeState, "index", "index:SH:000001", "SH", "000001"),
        (BoardRuntimeState, "board", "board:SH:881001", "SH", "881001"),
    ],
)
def test_actual_n4_event_builds_complete_n5_runtime_state_for_all_channels(
    state_type: type[StockRuntimeState]
    | type[IndexRuntimeState]
    | type[BoardRuntimeState],
    asset_kind: str,
    identity_key: str,
    exchange: str,
    code: str,
) -> None:
    stock = _state(
        version=1,
        observed_at=_time("09:35"),
        source_d="flat",
        live_d="volume_up",
        source_w="10",
        live_w="11",
        live_30m="none",
    )
    values = {
        field: getattr(stock, field)
        for field in stock.__dataclass_fields__
    }
    values.update(
        asset_kind=asset_kind,
        identity_key=identity_key,
        exchange=exchange,
        code=code,
    )
    state = state_type(**values)
    n4_snapshot = RuntimeStateSnapshot(
        source_condition_run_id=SOURCE_RUN_ID,
        source_trade_date="20260826",
        for_trade_date="20260827",
        version=1,
        source_n3_version=1,
        generated_at=_time("09:35"),
        channel_status="ready",
        states=MappingProxyType({identity_key: state}),
    )
    n4 = WindowsN4StateTransitionPlanner(
        asset_kind=asset_kind,
        trigger_run_id=TRIGGER_RUN_ID,
    )
    trigger_event = n4.consume(n4_snapshot).events[0]
    n5 = WindowsN5EpisodePlanner(
        asset_kind=asset_kind,
        action_run_id=f"windows_n5_{asset_kind}_runtime_state_fixture",
    )

    n5_snapshot = n5.consume_trigger_event(trigger_event).snapshot
    runtime = next(iter(n5_snapshot.runtime_states.values()))

    assert runtime.key.identity_key == identity_key
    assert runtime.code == code
    assert runtime.source_condition_run_id == SOURCE_RUN_ID
    assert runtime.source_trade_date == "20260826"
    assert runtime.for_trade_date == "20260827"
    assert runtime.source_transitions == state.source_transitions
    assert runtime.source_amounts == state.source_amounts
    assert runtime.comparison_amounts == state.comparison_amounts
    assert runtime.realtime_transitions == state.realtime_transitions
    assert runtime.realtime_virtual_amounts == state.realtime_virtual_amounts
    assert runtime.n4_current_price == state.current_price
    assert runtime.n4_cumulative_amount == state.cumulative_amount
    assert runtime.provider == state.provider
    assert runtime.live_status == state.live_status
    assert runtime.fresh is state.fresh


def test_actual_n3_buy_metric_executes_actual_n4_match() -> None:
    identity = "stock:SZ:000001"
    n4 = n4_planner()
    state = _state(
        version=1,
        observed_at=_time("09:35"),
        source_d="flat",
        live_d="volume_up",
        source_w="10",
        live_w="11",
        live_30m="none",
    )
    trigger_event = n4.consume(_snapshot(1, state)).events[0]
    n5 = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_end_to_end_buy",
    )
    eligible = n5.consume_trigger_event(trigger_event).events[0]

    metric = build_action_confirmation_metric(
        asset_kind="stock",
        identity_key=identity,
        trade_date="20260827",
        provider="fixture.stock.closed_1m",
        current_bars=_bars(
            identity,
            "20260827",
            7,
            amount_factory=lambda index: Decimal(index * 100),
            close_factory=lambda index: Decimal(300 + index),
        ),
        previous_context=_previous(identity),
        expected_minute_index=7,
    )
    executed = n5.consume_metric(metric).events[0]

    assert eligible.event_type == "ActionEligible"
    assert metric.metric_ready is True
    assert executed.event_type == "ActionExecuted"
    assert executed.payload_json["direction"] == "buy"
    assert executed.payload_json["action_mark"] == "30m_volume"
    assert all(executed.payload_json["confirmation_checks"].values())
    assert (
        executed.payload_json["action_entry_trigger_matched_ref"]["event_id"]
        == trigger_event.event_id
    )
    proof = executed.payload_json["final_market_proof"]
    assert proof["source_basis"] == "N3T_C1_CLOSED"
    assert proof["metric_minute_index"] == 7
    assert proof["current_price"] == str(metric.current_price)
    assert proof["previous_120m_body_high"] == str(
        metric.previous_120m_body_high
    )
    assert proof["previous_5m_full_amount"] == str(
        metric.previous_5m_full_amount
    )
    episode_proof = tuple(n5.read().active.values())[0].latest_metric_proof
    assert episode_proof is not None
    assert episode_proof["previous_1m_amount"] == metric.previous_1m_amount


def test_actual_n3_sell_metric_executes_actual_n4_match() -> None:
    identity = "stock:SH:600000"
    n4 = n4_planner()
    state = _state(
        identity_key=identity,
        code="600000",
        name="fixture",
        version=1,
        observed_at=_time("13:05"),
        source_d="volume_up",
        live_d="low_volume_down",
        source_w="20",
        live_w="18.5",
        live_30m="none",
    )
    trigger_event = n4.consume(_snapshot(1, state)).events[0]
    n5 = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_end_to_end_sell",
    )
    n5.consume_trigger_event(trigger_event)

    def amount(index: int) -> Decimal:
        if index <= 5:
            return Decimal("0.1")
        if index == 6:
            return Decimal("0.05")
        return Decimal("0.01")

    sell_bars = tuple(
        replace(
            bar,
            open=bar.close + Decimal("1"),
            high=bar.close + Decimal("2"),
            low=bar.close - Decimal("1"),
        )
        for bar in _bars(
            identity,
            "20260827",
            7,
            amount_factory=amount,
            close_factory=lambda index: Decimal(100 - index),
        )
    )
    metric = build_action_confirmation_metric(
        asset_kind="stock",
        identity_key=identity,
        trade_date="20260827",
        provider="fixture.stock.closed_1m",
        current_bars=sell_bars,
        previous_context=_previous(identity),
        expected_minute_index=7,
    )
    executed = n5.consume_metric(metric).events[0]

    assert metric.metric_ready is True
    assert executed.event_type == "ActionExecuted"
    assert executed.payload_json["direction"] == "sell"
    assert executed.payload_json["action_mark"] == "30m_shrink"
    assert all(executed.payload_json["confirmation_checks"].values())
