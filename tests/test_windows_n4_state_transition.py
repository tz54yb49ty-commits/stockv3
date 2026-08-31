from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from ashare_v3.trigger.event_factory import build_n4_trigger_event
from ashare_v3.trigger.windows_n4_memory import (
    BoardRuntimeState,
    IndexRuntimeState,
    RuntimeStateSnapshot,
    StockRuntimeState,
)
from ashare_v3.trigger.windows_n4_state_transition import (
    BUY_CONDITION_KEY,
    LEGACY_BUY_CONDITION_KEY,
    LEGACY_RULE_POLICY_VERSION,
    RULE_POLICY_VERSION,
    SELL_CONDITION_KEY,
    OutOfOrderN4Snapshot,
    WindowsN4StateTransitionPlanner,
)


SOURCE_RUN_ID = "condition_layer_20260826_to_20260827_fixture"
TRIGGER_RUN_ID = "windows_n4_state_transition_20260827_fixture"


def _time(label: str) -> datetime:
    return datetime.fromisoformat(f"2026-08-27T{label}:00+08:00")


def _state(
    *,
    identity_key: str = "stock:SZ:000001",
    code: str = "000001",
    name: str = "平安银行",
    version: int,
    observed_at: datetime,
    source_d: str,
    live_d: str,
    source_w: str,
    live_w: str,
    live_30m: str,
    fresh: bool = True,
    live_status: str = "available",
    higher_source: dict[str, str] | None = None,
    higher_live: dict[str, str] | None = None,
) -> StockRuntimeState:
    source_transitions = {
        "30m": "unknown",
        "D": source_d,
        "W": "flat",
        "M": "flat",
        "Q": "flat",
        "Y": "flat",
        **(higher_source or {}),
    }
    realtime_transitions = {
        "30m": live_30m,
        "D": live_d,
        "W": "flat",
        "M": "flat",
        "Q": "flat",
        "Y": "flat",
        **(higher_live or {}),
    }
    return StockRuntimeState(
        source_condition_run_id=SOURCE_RUN_ID,
        source_trade_date="20260826",
        for_trade_date="20260827",
        asset_kind="stock",
        identity_key=identity_key,
        exchange=identity_key.split(":")[1],
        code=code,
        name=name,
        source_transitions=source_transitions,
        source_amounts={
            "30m": None,
            "D": Decimal("0"),
            "W": Decimal(source_w),
            "M": Decimal("0"),
            "Q": Decimal("0"),
            "Y": Decimal("0"),
        },
        comparison_amounts={
            "30m": None,
            "D": Decimal("0"),
            "W": Decimal(source_w),
            "M": Decimal("0"),
            "Q": Decimal("0"),
            "Y": Decimal("0"),
        },
        realtime_transitions=realtime_transitions,
        realtime_virtual_amounts={
            "30m": Decimal("1"),
            "D": Decimal("1"),
            "W": Decimal(live_w),
            "M": Decimal("1"),
            "Q": Decimal("1"),
            "Y": Decimal("1"),
        },
        current_price=Decimal("10.00") if fresh else None,
        cumulative_amount=Decimal("100000000") if fresh else None,
        source_time=observed_at if fresh else None,
        observed_at=observed_at if fresh else None,
        provider="fixture" if fresh else None,
        live_status=live_status,
        fresh=fresh,
        last_success_at=observed_at,
        last_error=None if fresh else "fixture stale",
        source_n3_version=version,
    )


def _snapshot(
    version: int,
    state: StockRuntimeState,
    *extra_states: StockRuntimeState,
) -> RuntimeStateSnapshot[StockRuntimeState]:
    states = {item.identity_key: item for item in (state, *extra_states)}
    return RuntimeStateSnapshot(
        source_condition_run_id=SOURCE_RUN_ID,
        source_trade_date="20260826",
        for_trade_date="20260827",
        version=version,
        source_n3_version=version,
        generated_at=state.observed_at or _time("09:35"),
        channel_status="ready",
        states=MappingProxyType(states),
    )


def _planner() -> WindowsN4StateTransitionPlanner:
    return WindowsN4StateTransitionPlanner(
        asset_kind="stock",
        trigger_run_id=TRIGGER_RUN_ID,
    )


def test_buy_daily_lifecycle_and_new_episode() -> None:
    planner = _planner()
    sequence = [
        ("09:35", "volume_up", "10.80", "none"),
        ("09:40", "volume_up", "10.90", "volume_up"),
        ("10:00", "flat", "9.80", "volume_up"),
        ("10:05", "flat", "9.80", "none"),
        ("10:20", "volume_up", "10.70", "none"),
    ]
    batches = []
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
        batches.append(planner.consume(_snapshot(version, state)))

    assert [event.event_type for event in batches[0].events] == ["TriggerMatched"]
    first = batches[0].events[0]
    assert first.payload_json["condition_key"] == BUY_CONDITION_KEY
    assert first.payload_json["rule_policy_version"] == RULE_POLICY_VERSION
    assert first.payload_json["match_basis"].startswith(RULE_POLICY_VERSION)
    assert first.payload_json["trigger_period"] == "D"
    assert first.payload_json["primary_trigger_period"] == "D"
    assert first.payload_json["activation_sources"] == ["D"]
    assert first.payload_json["formal_triggered_periods"] == ["D"]
    assert first.payload_json["projection_30m_flag"] is False
    assert first.payload_json["projection_30m_type"] == "none"
    assert first.payload_json["trigger_mark_candidate"] == "normal"
    assert first.payload_json["episode_entry_event_id"] == first.event_id
    assert first.payload_json["source_w_average_amount"] == "10.00"
    assert first.payload_json["source_transitions"]["D"] == "low_volume_down"
    assert first.payload_json["source_amounts"]["W"] == "10.00"
    assert first.payload_json["comparison_amounts"]["W"] == "10.00"
    assert first.payload_json["realtime_transitions"]["D"] == "volume_up"
    assert first.payload_json["realtime_virtual_amounts"]["W"] == "10.80"
    assert first.payload_json["current_price"] == "10.00"
    assert first.payload_json["cumulative_amount"] == "100000000"
    assert first.payload_json["provider"] == "fixture"
    assert first.payload_json["live_status"] == "available"
    assert first.payload_json["fresh"] is True
    assert first.payload_json["rule_flags"] == {
        "A": True,
        "B": False,
        "C": False,
        "D30": False,
    }
    assert batches[1].events == ()

    assert [event.event_type for event in batches[2].events] == [
        "TriggerStateChanged"
    ]
    inactive_payload = batches[2].events[0].payload_json
    assert inactive_payload["trigger_live"] is False
    assert inactive_payload["current_status"] == "inactive"
    assert inactive_payload["state_change_reason"] == "matched_to_inactive"
    assert batches[3].events == ()

    assert [event.event_type for event in batches[4].events] == ["TriggerMatched"]
    second = batches[4].events[0]
    assert first.event_id != second.event_id
    final_buy = batches[4].snapshot.states["stock:SZ:000001"].buy
    assert final_buy.episode_number == 2
    assert final_buy.episode_entry_event_id == second.event_id


def test_sell_daily_lifecycle_is_symmetric() -> None:
    planner = _planner()
    inputs = [
        ("13:05", "low_volume_down", "18.50", "none"),
        ("13:30", "low_volume_down", "18.00", "shrink_down"),
        ("14:00", "flat", "21.00", "none"),
    ]
    batches = []
    for version, (label, live_d, live_w, live_30m) in enumerate(inputs, 1):
        state = _state(
            identity_key="stock:SH:600000",
            code="600000",
            name="浦发银行",
            version=version,
            observed_at=_time(label),
            source_d="volume_up",
            live_d=live_d,
            source_w="20.00",
            live_w=live_w,
            live_30m=live_30m,
        )
        batches.append(planner.consume(_snapshot(version, state)))

    matched = batches[0].events[0]
    assert matched.event_type == "TriggerMatched"
    assert matched.payload_json["condition_key"] == SELL_CONDITION_KEY
    assert matched.payload_json["rule_flags"]["C"] is True
    assert matched.payload_json["activation_sources"] == ["D"]
    assert matched.payload_json["trigger_period"] == "D"
    assert batches[1].events == ()
    inactive = batches[2].events[0]
    assert inactive.event_type == "TriggerStateChanged"
    assert inactive.payload_json["trigger_live"] is False


def test_30m_and_higher_periods_never_activate_or_refresh() -> None:
    planner = _planner()
    ignored = _state(
        version=1,
        observed_at=_time("09:35"),
        source_d="flat",
        live_d="flat",
        source_w="10",
        live_w="10",
        live_30m="volume_up",
        higher_live={"Y": "volume_up", "M": "volume_up"},
    )
    first = planner.consume(_snapshot(1, ignored))
    assert first.events == ()
    assert first.snapshot.states[ignored.identity_key].buy.trigger_live is False

    active = _state(
        version=2,
        observed_at=_time("09:40"),
        source_d="flat",
        live_d="volume_up",
        source_w="10",
        live_w="11",
        live_30m="none",
    )
    matched = planner.consume(_snapshot(2, active))
    assert [event.event_type for event in matched.events] == ["TriggerMatched"]

    changed_context = _state(
        version=3,
        observed_at=_time("09:45"),
        source_d="flat",
        live_d="volume_up",
        source_w="10",
        live_w="12",
        live_30m="shrink_down",
        higher_source={"Y": "volume_up", "Q": "low_volume_down"},
        higher_live={"Y": "low_volume_down", "Q": "volume_up"},
    )
    unchanged = planner.consume(_snapshot(3, changed_context))
    assert unchanged.events == ()
    buy = unchanged.snapshot.states[active.identity_key].buy
    assert buy.activation_sources == ("D",)
    assert buy.formal_triggered_periods == ("D",)
    assert buy.primary_trigger_period == "D"
    assert buy.trigger_period == "D"
    assert buy.projection_30m_type == "none"
    assert buy.trigger_mark_candidate == "normal"


def test_one_hundred_live_snapshots_emit_one_match_and_no_true_change() -> None:
    planner = _planner()
    event_types = []
    for version in range(1, 101):
        state = _state(
            version=version,
            observed_at=_time("10:00"),
            source_d="flat",
            live_d="volume_up",
            source_w="10",
            live_w=str(11 + version),
            live_30m="volume_up" if version % 2 else "shrink_down",
            higher_live={"Y": "volume_up" if version % 2 else "flat"},
        )
        batch = planner.consume(_snapshot(version, state))
        event_types.extend(event.event_type for event in batch.events)
    assert event_types == ["TriggerMatched"]


@pytest.mark.parametrize(
    ("source_d", "live_d"),
    [
        ("flat", "volume_up"),
        ("flat", "low_volume_down"),
    ],
)
def test_equal_week_average_does_not_trigger(
    source_d: str,
    live_d: str,
) -> None:
    planner = _planner()
    state = _state(
        version=1,
        observed_at=_time("10:00"),
        source_d=source_d,
        live_d=live_d,
        source_w="10",
        live_w="10",
        live_30m="volume_up",
    )
    batch = planner.consume(_snapshot(1, state))
    assert batch.events == ()
    object_state = batch.snapshot.states[state.identity_key]
    assert object_state.buy.trigger_live is False
    assert object_state.sell.trigger_live is False


def test_ac_use_previous_complete_week_average_not_current_week_seed() -> None:
    planner = _planner()
    state = _state(
        version=1,
        observed_at=_time("09:35"),
        source_d="flat",
        live_d="volume_up",
        source_w="10",
        live_w="11",
        live_30m="none",
    )
    values = {
        field: getattr(state, field)
        for field in state.__dataclass_fields__
    }
    values["source_amounts"] = {
        **dict(state.source_amounts),
        "W": Decimal("100"),
    }
    state = StockRuntimeState(**values)
    batch = planner.consume(_snapshot(1, state))
    assert batch.snapshot.states[state.identity_key].buy.rule_flags["A"] is True
    assert batch.events[0].payload_json["source_w_average_amount"] == "10"


@pytest.mark.parametrize(
    ("state_type", "asset_kind", "identity_key", "exchange", "code"),
    [
        (StockRuntimeState, "stock", "stock:SZ:000001", "SZ", "000001"),
        (IndexRuntimeState, "index", "index:SH:000001", "SH", "000001"),
        (BoardRuntimeState, "board", "board:SH:881001", "SH", "881001"),
    ],
)
def test_all_channels_emit_complete_runtime_context(
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
    snapshot = RuntimeStateSnapshot(
        source_condition_run_id=SOURCE_RUN_ID,
        source_trade_date="20260826",
        for_trade_date="20260827",
        version=1,
        source_n3_version=1,
        generated_at=_time("09:35"),
        channel_status="ready",
        states=MappingProxyType({identity_key: state}),
    )
    planner = WindowsN4StateTransitionPlanner(
        asset_kind=asset_kind,
        trigger_run_id=TRIGGER_RUN_ID,
    )
    batch = planner.consume(snapshot)
    assert batch.events[0].asset_kind == asset_kind
    payload = batch.events[0].payload_json
    assert payload["source_transitions"] == dict(state.source_transitions)
    assert payload["source_amounts"] == {
        period: str(amount) if amount is not None else None
        for period, amount in state.source_amounts.items()
    }
    assert payload["comparison_amounts"] == {
        period: str(amount) if amount is not None else None
        for period, amount in state.comparison_amounts.items()
    }
    assert payload["realtime_transitions"] == dict(state.realtime_transitions)
    assert payload["realtime_virtual_amounts"] == {
        period: str(amount) if amount is not None else None
        for period, amount in state.realtime_virtual_amounts.items()
    }
    assert payload["current_price"] == "10.00"
    assert payload["cumulative_amount"] == "100000000"
    assert payload["provider"] == "fixture"
    assert payload["live_status"] == "available"
    assert payload["fresh"] is True
    assert batch.snapshot.states[identity_key].buy.trigger_live is True


def test_abcd_buy_sell_are_mutually_exclusive() -> None:
    cases = [
        ("low_volume_down", "volume_up", "11", "volume_up"),
        ("volume_up", "low_volume_down", "9", "shrink_down"),
        ("flat", "volume_up", "11", "none"),
        ("flat", "low_volume_down", "9", "none"),
    ]
    for source_d, live_d, live_w, live_30m in cases:
        planner = _planner()
        state = _state(
            version=1,
            observed_at=_time("09:35"),
            source_d=source_d,
            live_d=live_d,
            source_w="10",
            live_w=live_w,
            live_30m=live_30m,
        )
        batch = planner.consume(_snapshot(1, state))
        object_state = batch.snapshot.states[state.identity_key]
        assert not (object_state.buy.trigger_live and object_state.sell.trigger_live)


def test_stale_or_unknown_evidence_does_not_deactivate() -> None:
    planner = _planner()
    active = _state(
        version=1,
        observed_at=_time("09:35"),
        source_d="low_volume_down",
        live_d="volume_up",
        source_w="10",
        live_w="11",
        live_30m="none",
    )
    first = planner.consume(_snapshot(1, active))
    assert first.snapshot.states[active.identity_key].buy.trigger_live is True

    stale = _state(
        version=2,
        observed_at=_time("09:40"),
        source_d="low_volume_down",
        live_d="unknown",
        source_w="10",
        live_w="11",
        live_30m="unknown",
        fresh=False,
        live_status="stale",
    )
    second = planner.consume(_snapshot(2, stale))
    assert second.events == ()
    assert second.snapshot.states[active.identity_key].buy.trigger_live is True
    assert second.snapshot.states[active.identity_key].buy.source_n4_version == 2

    unknown = _state(
        version=3,
        observed_at=_time("09:45"),
        source_d="low_volume_down",
        live_d="unknown",
        source_w="10",
        live_w="11",
        live_30m="unknown",
    )
    third = planner.consume(_snapshot(3, unknown))
    assert third.events == ()
    assert third.snapshot.states[active.identity_key].buy.trigger_live is True
    assert third.snapshot.states[active.identity_key].buy.source_n4_version == 3

    unknown_source = _state(
        version=4,
        observed_at=_time("09:50"),
        source_d="unknown",
        live_d="flat",
        source_w="10",
        live_w="9",
        live_30m="none",
    )
    fourth = planner.consume(_snapshot(4, unknown_source))
    assert fourth.events == ()
    assert fourth.snapshot.states[active.identity_key].buy.trigger_live is True


def test_repeated_and_out_of_order_versions_are_safe_and_bounded() -> None:
    planner = _planner()
    first_state = _state(
        version=1,
        observed_at=_time("09:35"),
        source_d="flat",
        live_d="flat",
        source_w="10",
        live_w="10",
        live_30m="none",
    )
    extra = _state(
        identity_key="stock:SH:600000",
        code="600000",
        name="浦发银行",
        version=1,
        observed_at=_time("09:35"),
        source_d="flat",
        live_d="flat",
        source_w="20",
        live_w="20",
        live_30m="none",
    )
    first = planner.consume(_snapshot(1, first_state, extra))
    repeated = planner.consume(_snapshot(1, first_state, extra))
    assert repeated.events == ()
    assert len(repeated.snapshot.states) == 2

    second_state = replace_runtime_version(first_state, 2, _time("09:40"))
    extra_second = replace_runtime_version(extra, 2, _time("09:40"))
    second = planner.consume(_snapshot(2, second_state, extra_second))
    assert len(second.snapshot.states) == 2
    assert len(first.snapshot.states) == len(second.snapshot.states)

    with pytest.raises(OutOfOrderN4Snapshot):
        planner.consume(_snapshot(1, first_state, extra))


def replace_runtime_version(
    state: StockRuntimeState,
    version: int,
    observed_at: datetime,
) -> StockRuntimeState:
    values = {
        field: getattr(state, field)
        for field in state.__dataclass_fields__
    }
    values.update(
        {
            "source_n3_version": version,
            "source_time": observed_at,
            "observed_at": observed_at,
            "last_success_at": observed_at,
        }
    )
    return StockRuntimeState(**values)


def test_module_is_pure_and_does_not_write_events() -> None:
    source = Path(
        "src/ashare_v3/trigger/windows_n4_state_transition.py"
    ).read_text(encoding="utf-8").lower()
    for forbidden in (
        "psycopg",
        "insert into",
        "outboxrepository",
        "write_event",
        "actioneligible",
        "n5_action",
        "eltdx",
        "requests",
    ):
        assert forbidden not in source



@pytest.mark.parametrize(
    ("state_type", "asset_kind", "identity_key", "exchange", "code"),
    [
        (StockRuntimeState, "stock", "stock:SZ:000001", "SZ", "000001"),
        (IndexRuntimeState, "index", "index:SH:000001", "SH", "000001"),
        (BoardRuntimeState, "board", "board:SH:881001", "SH", "881001"),
    ],
)
def test_restore_outbox_lifecycle_is_symmetric_and_idempotent(
    state_type: type[StockRuntimeState]
    | type[IndexRuntimeState]
    | type[BoardRuntimeState],
    asset_kind: str,
    identity_key: str,
    exchange: str,
    code: str,
) -> None:
    def make_state(
        *,
        version: int,
        label: str,
        live_d: str,
        live_w: str,
        live_30m: str,
    ) -> StockRuntimeState | IndexRuntimeState | BoardRuntimeState:
        stock = _state(
            identity_key="stock:SZ:000001",
            code=code,
            name=f"{asset_kind}-{code}",
            version=version,
            observed_at=_time(label),
            source_d="low_volume_down",
            live_d=live_d,
            source_w="10",
            live_w=live_w,
            live_30m=live_30m,
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
        return state_type(**values)

    def make_snapshot(
        version: int,
        state: StockRuntimeState | IndexRuntimeState | BoardRuntimeState,
    ) -> RuntimeStateSnapshot:
        return RuntimeStateSnapshot(
            source_condition_run_id=SOURCE_RUN_ID,
            source_trade_date="20260826",
            for_trade_date="20260827",
            version=version,
            source_n3_version=version,
            generated_at=state.observed_at,
            channel_status="ready",
            states=MappingProxyType({identity_key: state}),
        )

    original = WindowsN4StateTransitionPlanner(
        asset_kind=asset_kind,
        trigger_run_id=TRIGGER_RUN_ID,
    )
    matched_state = make_state(
        version=7,
        label="09:35",
        live_d="volume_up",
        live_w="11",
        live_30m="none",
    )
    matched = original.consume(make_snapshot(7, matched_state)).events[0]
    assert matched.event_type == "TriggerMatched"

    restored_inactive = WindowsN4StateTransitionPlanner(
        asset_kind=asset_kind,
        trigger_run_id=f"{TRIGGER_RUN_ID}_restart_inactive",
    )
    restored_snapshot = restored_inactive.restore_from_outbox(
        [matched, matched]
    )
    assert restored_snapshot.source_n4_version == 7
    assert restored_snapshot.states[identity_key].buy.trigger_live is True
    assert (
        restored_inactive.restore_from_outbox([matched])
        is restored_snapshot
    )

    inactive_state = make_state(
        version=8,
        label="09:40",
        live_d="flat",
        live_w="9",
        live_30m="none",
    )
    inactive = restored_inactive.consume(
        make_snapshot(8, inactive_state)
    )
    assert [event.event_type for event in inactive.events] == [
        "TriggerStateChanged"
    ]
    assert inactive.events[0].payload_json["trigger_live"] is False
    assert (
        inactive.events[0].payload_json["episode_entry_event_id"]
        == matched.event_id
    )

    restored_after_inactive = WindowsN4StateTransitionPlanner(
        asset_kind=asset_kind,
        trigger_run_id=f"{TRIGGER_RUN_ID}_restart_after_inactive",
    )
    inactive_snapshot = restored_after_inactive.restore_from_outbox(
        [inactive.events[0], matched, inactive.events[0]]
    )
    assert inactive_snapshot.source_n4_version == 8
    assert inactive_snapshot.states[identity_key].buy.trigger_live is False
    assert restored_after_inactive.consume(
        make_snapshot(9, inactive_state)
    ).events == ()

    restored_live = WindowsN4StateTransitionPlanner(
        asset_kind=asset_kind,
        trigger_run_id=f"{TRIGGER_RUN_ID}_restart_live",
    )
    restored_live.restore_from_outbox([matched])
    unchanged = restored_live.consume(make_snapshot(8, matched_state))
    assert unchanged.events == ()

    changed_state = make_state(
        version=9,
        label="10:00",
        live_d="volume_up",
        live_w="11",
        live_30m="volume_up",
    )
    changed = restored_live.consume(make_snapshot(9, changed_state))
    assert changed.events == ()
    restored_buy = changed.snapshot.states[identity_key].buy
    assert restored_buy.trigger_live is True
    assert restored_buy.activation_sources == ("D",)


def test_legacy_v1_matched_event_remains_readable() -> None:
    original = _planner()
    state = _state(
        version=1,
        observed_at=_time("09:35"),
        source_d="flat",
        live_d="volume_up",
        source_w="10",
        live_w="11",
        live_30m="none",
    )
    matched = original.consume(_snapshot(1, state)).events[0]
    legacy_payload = dict(matched.payload_json)
    legacy_payload["rule_policy_version"] = LEGACY_RULE_POLICY_VERSION
    legacy_payload["episode_entry_event_id"] = "pending"
    arguments = {
        "event_type": "TriggerMatched",
        "asset_kind": matched.asset_kind,
        "identity_key": matched.identity_key,
        "trade_date": matched.trade_date,
        "event_time": matched.event_time,
        "trigger_run_id": "windows_n4_state_transition_v1_restore_fixture",
        "source_event_id": str(matched.payload_json["source_event_id"]),
        "direction": "buy",
        "signal_type": "B_BUY",
        "condition_key": LEGACY_BUY_CONDITION_KEY,
        "trigger_mark_candidate": "normal",
        "trigger_period": "D",
        "trigger_bucket": "episode:1",
        "match_basis": f"{LEGACY_RULE_POLICY_VERSION}:D",
        "data_quality_status": "ready",
        "created_at": matched.created_at,
    }
    first = build_n4_trigger_event(payload=legacy_payload, **arguments)
    legacy_payload["episode_entry_event_id"] = first.event_id
    legacy_event = build_n4_trigger_event(
        payload=legacy_payload,
        **arguments,
    )
    restored = _planner().restore_from_outbox([legacy_event, legacy_event])
    restored_buy = restored.states[state.identity_key].buy
    assert restored_buy.trigger_live is True
    assert restored_buy.condition_key == LEGACY_BUY_CONDITION_KEY


def test_restore_rejects_conflicting_duplicate_without_mutating_planner() -> None:
    original = _planner()
    state = _state(
        version=1,
        observed_at=_time("09:35"),
        source_d="low_volume_down",
        live_d="volume_up",
        source_w="10",
        live_w="11",
        live_30m="none",
    )
    matched = original.consume(_snapshot(1, state)).events[0]
    payload = dict(matched.payload_json)
    payload["source_condition_run_id"] = "different-lineage"
    mixed = type(matched)(
        **{
            **matched.as_record(),
            "payload_json": payload,
        }
    )
    restored = _planner()
    with pytest.raises(ValueError, match="conflicting duplicate event_id"):
        restored.restore_from_outbox([matched, mixed])
    with pytest.raises(RuntimeError, match="no N4 snapshot"):
        restored.read()
