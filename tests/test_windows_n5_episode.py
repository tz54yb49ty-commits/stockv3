from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from ashare_v3.events.models import (
    EventContractError,
    validate_n5_trigger_fact_passthrough_payload,
)
from ashare_v3.market.windows_n3_action_metric import ActionConfirmationMetric
from ashare_v3.trigger.event_factory import build_n4_trigger_event
from ashare_v3.action.windows_n5_episode import (
    ACTION_POLICY_VERSION,
    WindowsN5EpisodePlanner,
    evaluate_confirmation,
)


CST = timezone(timedelta(hours=8))
TRADE_DATE = "20260827"
SOURCE_CONDITION_RUN_ID = "condition_20260826_to_20260827"
RULE_POLICY_VERSION = "windows_n4_state_transition_v1"


def _time(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 27, hour, minute, tzinfo=CST)


def _identity(asset_kind: str) -> str:
    return {
        "stock": "stock:SZ:000001",
        "index": "index:SH:000001",
        "board": "board:SH:881333",
    }[asset_kind]


def _direction_fields(direction: str) -> tuple[str, str]:
    if direction == "buy":
        return "B_BUY", "BUY:STATE_V1"
    return "S_SELL", "SELL:STATE_V1"


def _matched(
    *,
    asset_kind: str = "stock",
    direction: str = "buy",
    formal_periods: tuple[str, ...] = ("D",),
    episode_number: int = 1,
    version: int = 1,
    event_time: datetime | None = None,
):
    signal_type, condition_key = _direction_fields(direction)
    identity = _identity(asset_kind)
    primary = formal_periods[0] if formal_periods else None
    trigger_period = primary or "30m"
    at = event_time or _time(9, 35)
    payload = {
        "rule_policy_version": RULE_POLICY_VERSION,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "source_trade_date": "20260826",
        "for_trade_date": TRADE_DATE,
        "code": identity.rsplit(":", 1)[-1],
        "name": "fixture",
        "n4_state_version": version,
        "source_n3_version": version,
        "effective_time": at.isoformat(),
        "data_quality_status": "ready",
        "source_w_average_amount": "1000000000",
        "rule_flags": {"A": direction == "buy", "B": False, "C": direction == "sell", "D30": False},
        "activation_sources": list(formal_periods or ("B" if direction == "buy" else "D30",)),
        "formal_triggered_periods": list(formal_periods),
        "triggered_periods": list(formal_periods),
        "all_trigger_periods": list(formal_periods),
        "primary_trigger_period": primary,
        "projection_30m_flag": not formal_periods,
        "projection_30m_type": (
            "none"
            if formal_periods
            else ("volume_up" if direction == "buy" else "shrink_down")
        ),
        "trigger_live": True,
        "current_status": "matched",
        "episode_number": episode_number,
        "episode_entry_event_id": None,
    }
    kwargs = {
        "event_type": "TriggerMatched",
        "asset_kind": asset_kind,
        "identity_key": identity,
        "trade_date": TRADE_DATE,
        "event_time": at,
        "trigger_run_id": "windows_n4_fixture",
        "source_event_id": f"n4-memory:{identity}:{version}",
        "direction": direction,
        "signal_type": signal_type,
        "condition_key": condition_key,
        "trigger_mark_candidate": (
            "normal"
            if formal_periods
            else ("30m_volume" if direction == "buy" else "30m_shrink")
        ),
        "trigger_period": trigger_period,
        "trigger_bucket": f"episode:{episode_number}",
        "match_basis": f"{RULE_POLICY_VERSION}:fixture",
        "data_quality_status": "ready",
        "payload": payload,
        "created_at": at,
    }
    event = build_n4_trigger_event(**kwargs)
    kwargs["payload"] = {**payload, "episode_entry_event_id": event.event_id}
    return build_n4_trigger_event(**kwargs)


def _state_changed(
    matched,
    *,
    trigger_live: bool,
    formal_periods: tuple[str, ...] = (),
    version: int = 2,
    event_time: datetime | None = None,
    data_quality_status: str = "ready",
):
    previous = dict(matched.payload_json)
    direction = previous["direction"]
    primary = formal_periods[0] if formal_periods else None
    at = event_time or _time(10, 0)
    projection = (
        "none"
        if formal_periods or not trigger_live
        else ("volume_up" if direction == "buy" else "shrink_down")
    )
    payload = {
        "rule_policy_version": RULE_POLICY_VERSION,
        "source_condition_run_id": SOURCE_CONDITION_RUN_ID,
        "source_trade_date": "20260826",
        "for_trade_date": TRADE_DATE,
        "code": previous.get("code"),
        "name": previous.get("name"),
        "n4_state_version": version,
        "source_n3_version": version,
        "effective_time": at.isoformat(),
        "data_quality_status": data_quality_status,
        "source_w_average_amount": "1000000000",
        "rule_flags": {"A": False, "B": trigger_live and direction == "buy", "C": False, "D30": trigger_live and direction == "sell"},
        "activation_sources": list(formal_periods or (("B",) if trigger_live and direction == "buy" else ("D30",) if trigger_live else ())),
        "formal_triggered_periods": list(formal_periods),
        "triggered_periods": list(formal_periods),
        "all_trigger_periods": list(formal_periods),
        "primary_trigger_period": primary,
        "projection_30m_flag": trigger_live and not formal_periods,
        "projection_30m_type": projection,
        "trigger_live": trigger_live,
        "current_status": "matched" if trigger_live else "inactive",
        "episode_number": previous["episode_number"],
        "episode_entry_event_id": previous["episode_entry_event_id"],
        "previous_trigger_live": True,
        "previous_status": "matched",
        "previous_primary_trigger_period": previous["primary_trigger_period"],
        "previous_all_trigger_periods": previous["all_trigger_periods"],
        "previous_projection_30m_flag": previous["projection_30m_flag"],
        "previous_projection_30m_type": previous["projection_30m_type"],
        "previous_trigger_mark_candidate": previous["trigger_mark_candidate"],
        "state_change_reason": "matched_changed" if trigger_live else "matched_to_inactive",
        "source_outcome_event_type": "N4RuntimeStateVersion",
        "source_outcome_event_id": f"n4-memory:{matched.identity_key}:{version}",
    }
    return build_n4_trigger_event(
        event_type="TriggerStateChanged",
        asset_kind=matched.asset_kind,
        identity_key=matched.identity_key,
        trade_date=matched.trade_date,
        event_time=at,
        trigger_run_id=matched.source_run_id,
        source_event_id=payload["source_outcome_event_id"],
        direction=direction,
        signal_type=previous["signal_type"],
        condition_key=previous["condition_key"],
        trigger_mark_candidate=(
            "normal"
            if formal_periods or not trigger_live
            else ("30m_volume" if direction == "buy" else "30m_shrink")
        ),
        trigger_period=primary or previous["trigger_period"],
        trigger_bucket=f"episode:{previous['episode_number']}",
        match_basis=f"{RULE_POLICY_VERSION}:fixture-change",
        data_quality_status=data_quality_status,
        payload=payload,
        created_at=at,
    )


def _metric(
    *,
    asset_kind: str = "stock",
    direction: str = "buy",
    minute_index: int = 7,
    ready: bool = True,
    equality: bool = False,
    first_amounts: bool = False,
) -> ActionConfirmationMetric:
    buy = direction == "buy"
    price = Decimal("10") if equality else Decimal("11" if buy else "9")
    current_5m = None if first_amounts else Decimal("200" if buy else "50")
    previous_5m = None if first_amounts else Decimal("100")
    current_1m = None if first_amounts else Decimal("20" if buy else "5")
    previous_1m = None if first_amounts else Decimal("10")
    return ActionConfirmationMetric(
        asset_kind=asset_kind,
        identity_key=_identity(asset_kind),
        trade_date=TRADE_DATE,
        provider=f"fixture.{asset_kind}.closed_1m",
        metric_time=_time(15, 0) if minute_index >= 240 else _time(9, 30 + minute_index),
        metric_minute_label="15:00" if minute_index >= 240 else f"09:{30 + minute_index:02d}",
        current_price=price if ready else None,
        previous_120m_body_high=Decimal("10"),
        previous_120m_body_low=Decimal("10"),
        previous_30m_body_high=Decimal("10"),
        previous_30m_body_low=Decimal("10"),
        previous_5m_body_high=Decimal("10"),
        previous_5m_body_low=Decimal("10"),
        previous_1m_body_high=Decimal("10"),
        previous_1m_body_low=Decimal("10"),
        current_5m_virtual_amount=current_5m,
        previous_5m_full_amount=previous_5m,
        current_1m_amount=current_1m,
        previous_1m_amount=previous_1m,
        current_30m_virtual_amount=Decimal("200" if buy else "50"),
        previous_day_same_window_amount=Decimal("100"),
        previous_30m_full_amount=Decimal("100"),
        is_first_1m_of_day=first_amounts,
        is_first_5m_of_day=first_amounts,
        first_1m_amount_default_pass=first_amounts,
        first_5m_amount_default_pass=first_amounts,
        previous_1m_period_source="fixture",
        previous_5m_period_source="fixture",
        previous_30m_period_source="fixture",
        previous_120m_period_source="fixture",
        amount_unit="yuan",
        boundary_policy_version="n3.action_confirmation_boundary.v1",
        virtual_amount_policy_version="previous_day_same_window_elapsed_ratio_v1",
        metric_policy_version="windows_n3_action_metric_v1",
        metric_ready=ready,
        metric_quality_status="ready" if ready else "pending",
        error_summary=None if ready else "expected_closed_minute_missing",
        expected_minute_index=minute_index,
        observed_minute_index=minute_index if ready else minute_index - 1,
    )


def _one_active(planner: WindowsN5EpisodePlanner):
    values = tuple(planner.read().active.values())
    assert len(values) == 1
    return values[0]


def test_trigger_matched_creates_one_eligible_and_replay_is_idempotent() -> None:
    planner = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    matched = _matched()

    first = planner.consume_trigger_event(matched)
    replay = planner.consume_trigger_event(matched)

    assert [event.event_type for event in first.events] == ["ActionEligible"]
    assert replay.events == ()
    episode = _one_active(planner)
    assert episode.key.episode_entry_event_id == matched.event_id
    assert episode.eligible_event_id == first.events[0].event_id


def test_state_change_true_refreshes_source_and_executed_keeps_entry_ref() -> None:
    planner = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    matched = _matched()
    eligible = planner.consume_trigger_event(matched).events[0]
    changed = _state_changed(matched, trigger_live=True, formal_periods=("W", "D"))

    assert planner.consume_trigger_event(changed).events == ()
    executed = planner.consume_metric(_metric(minute_index=8)).events[0]

    assert executed.event_type == "ActionExecuted"
    assert executed.payload_json["source_trigger_event_id"] == changed.event_id
    assert executed.payload_json["episode_entry_event_id"] == matched.event_id
    assert executed.payload_json["action_entry_trigger_matched_ref"]["event_id"] == matched.event_id
    assert executed.payload_json["current_active_source_ref"]["event_id"] == changed.event_id
    assert eligible.event_id != executed.event_id


def test_state_change_false_expires_pending_and_new_match_opens_new_episode() -> None:
    planner = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    matched = _matched()
    planner.consume_trigger_event(matched)
    inactive = _state_changed(matched, trigger_live=False)

    expired = planner.consume_trigger_event(inactive)
    assert [event.event_type for event in expired.events] == ["ActionSkipped"]
    assert expired.events[0].payload_json["action_state"] == "expired"
    assert expired.events[0].payload_json["skipped_reason"] == "trigger_live_false"
    assert planner.read().active == {}
    assert planner.consume_trigger_event(inactive).events == ()

    reopened = _matched(episode_number=2, version=3, event_time=_time(10, 20))
    reopened_batch = planner.consume_trigger_event(reopened)
    assert [event.event_type for event in reopened_batch.events] == ["ActionEligible"]
    assert _one_active(planner).key.episode_entry_event_id == reopened.event_id


def test_stale_state_change_does_not_deactivate_live_episode() -> None:
    planner = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    matched = _matched()
    planner.consume_trigger_event(matched)
    stale_inactive = _state_changed(
        matched,
        trigger_live=False,
        data_quality_status="stale",
    )

    assert planner.consume_trigger_event(stale_inactive).events == ()
    assert _one_active(planner).trigger_live is True


def test_strict_equality_fails_then_later_strict_buy_passes() -> None:
    planner = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    planner.consume_trigger_event(_matched())

    assert planner.consume_metric(_metric(equality=True, minute_index=7)).events == ()
    pending_proof = _one_active(planner).latest_metric_proof
    assert pending_proof is not None
    assert pending_proof["current_price"] == Decimal("10")
    assert pending_proof["previous_120m_body_high"] == Decimal("10")
    executed = planner.consume_metric(_metric(minute_index=8)).events[0]

    assert executed.event_type == "ActionExecuted"
    assert executed.payload_json["action_mark"] == "30m_volume"
    assert executed.payload_json["confirmation_checks"]["120m_price"] is True
    episode_proof = _one_active(planner).latest_metric_proof
    assert episode_proof is not None
    assert episode_proof["previous_5m_full_amount"] == Decimal("100")
    assert episode_proof["previous_1m_amount"] == Decimal("10")


def test_sell_confirmation_is_strict_and_uses_shrink_mark() -> None:
    planner = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    planner.consume_trigger_event(_matched(direction="sell"))

    executed = planner.consume_metric(_metric(direction="sell")).events[0]

    assert executed.payload_json["direction"] == "sell"
    assert executed.payload_json["action_mark"] == "30m_shrink"
    assert all(executed.payload_json["confirmation_checks"].values())


def test_first_amount_checks_default_pass_but_prices_do_not() -> None:
    equal = _metric(first_amounts=True, equality=True)
    equal_decision = evaluate_confirmation("buy", equal)
    assert equal_decision.checks["1m_amount"] is True
    assert equal_decision.checks["5m_amount"] is True
    assert equal_decision.checks["1m_price"] is False
    assert equal_decision.all_passed is False

    passed = evaluate_confirmation("buy", _metric(first_amounts=True))
    assert passed.all_passed is True


def test_missing_metric_stays_pending_and_close_expires() -> None:
    planner = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    planner.consume_trigger_event(_matched())

    assert planner.consume_metric(_metric(ready=False)).events == ()
    assert _one_active(planner).confirmation_status == "pending"

    expired = planner.consume_metric(_metric(equality=True, minute_index=240))
    assert [event.event_type for event in expired.events] == ["ActionSkipped"]
    assert expired.events[0].payload_json["skipped_reason"] == "window_expired"
    assert planner.read().active == {}


def test_restore_from_outbox_rebuilds_executed_episode_without_reemission() -> None:
    planner = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    matched = _matched()
    eligible = planner.consume_trigger_event(matched).events[0]
    executed = planner.consume_metric(_metric()).events[0]

    restored = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    snapshot = restored.restore_from_outbox([matched, eligible, executed])

    restored_episode = tuple(snapshot.active.values())[0]
    assert restored_episode.action_state == "executed"
    assert restored_episode.eligible_event_id == eligible.event_id
    assert restored_episode.latest_metric_proof is not None
    assert (
        restored_episode.latest_metric_proof["previous_120m_body_high"] == "10"
    )
    assert restored.consume_trigger_event(matched).events == ()
    assert restored.consume_metric(_metric(minute_index=8)).events == ()


def test_windows_state_30m_fallback_is_narrowly_accepted() -> None:
    planner = WindowsN5EpisodePlanner(asset_kind="stock", action_run_id="n5_fixture")
    matched = _matched(formal_periods=())

    eligible = planner.consume_trigger_event(matched).events[0]

    assert eligible.payload_json["trigger_period"] == "30m"
    assert eligible.payload_json["triggered_periods"] == []
    assert eligible.payload_json["primary_trigger_period"] is None

    with pytest.raises(EventContractError, match="ordinary trigger .*30m"):
        validate_n5_trigger_fact_passthrough_payload(
            {
                "n4_trigger_event_id": "evt",
                "trigger_price": "1",
                "trigger_period": "30m",
                "triggered_periods": [],
                "all_trigger_periods": [],
                "primary_trigger_period": None,
                "trigger_kind": "trigger",
                "condition_key": "BUY:D",
                "original_condition_key": "BUY:D",
                "period_trigger_baseline_trace": {"D": {}},
                "baseline_source": "trigger_baseline",
            }
        )


@pytest.mark.parametrize("asset_kind", ("stock", "index", "board"))
def test_three_asset_channels_are_independent(asset_kind: str) -> None:
    planner = WindowsN5EpisodePlanner(asset_kind=asset_kind, action_run_id=f"n5_{asset_kind}")
    matched = _matched(asset_kind=asset_kind)

    assert planner.consume_trigger_event(matched).events[0].asset_kind == asset_kind
    assert planner.consume_metric(_metric(asset_kind=asset_kind)).events[0].asset_kind == asset_kind


def test_module_has_no_market_database_or_n6_dependency() -> None:
    source = Path("src/ashare_v3/action/windows_n5_episode.py").read_text(encoding="utf-8")
    assert "psycopg" not in source
    assert "eltdx" not in source
    assert "ashare_v3.user" not in source
    assert ACTION_POLICY_VERSION == "windows_n5_closed_minute_confirmation_v1"
