from __future__ import annotations

from pathlib import Path

import pytest

from ashare_v3.action.windows_n5_delivery import N4OutboxDelivery
from ashare_v3.action.windows_n5_episode import WindowsN5EpisodePlanner
from ashare_v3.action.windows_n5_transaction import (
    WindowsN5TransactionCoordinator,
)
from tests.test_windows_n5_delivery import _FakeCursor
from tests.test_windows_n5_episode import (
    _matched,
    _metric,
    _state_changed,
    _time,
)


class _CursorContext:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor = cursor

    def __enter__(self) -> _FakeCursor:
        return self.cursor

    def __exit__(self, _exc_type, _exc, _traceback) -> bool:
        return False


class _TransactionContext:
    def __init__(self, connection: "_FakeConnection") -> None:
        self.connection = connection
        self._before = None

    def __enter__(self) -> "_TransactionContext":
        cursor = self.connection.fake_cursor
        self.connection.begin_count += 1
        self._before = (
            set(cursor.inbox),
            set(cursor.outbox),
            dict(cursor.checkpoints),
        )
        return self

    def __exit__(self, exc_type, _exc, _traceback) -> bool:
        if exc_type is not None or self.connection.fail_commit:
            assert self._before is not None
            cursor = self.connection.fake_cursor
            cursor.inbox, cursor.outbox, cursor.checkpoints = self._before
            self.connection.rollback_count += 1
            if exc_type is None:
                raise RuntimeError("fixture commit failure")
            return False
        self.connection.commit_count += 1
        return False


class _FakeConnection:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.fake_cursor = _FakeCursor()
        self.fail_commit = fail_commit
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.cursor_count = 0

    def transaction(self) -> _TransactionContext:
        return _TransactionContext(self)

    def cursor(self) -> _CursorContext:
        self.cursor_count += 1
        return _CursorContext(self.fake_cursor)


def _planner(asset_kind: str = "stock") -> WindowsN5EpisodePlanner:
    return WindowsN5EpisodePlanner(
        asset_kind=asset_kind,
        action_run_id=f"windows_n5_transaction_{asset_kind}_fixture",
    )


def _coordinator() -> WindowsN5TransactionCoordinator:
    return WindowsN5TransactionCoordinator(
        consumer_name="windows_n5_state_v1",
        json_adapter=lambda value: value,
    )


def _outbox_values(cursor: _FakeCursor) -> tuple[object, ...]:
    return next(
        values
        for sql, values in cursor.calls
        if "INSERT INTO common_event_outbox" in sql
    )


@pytest.mark.parametrize("asset_kind", ["stock", "index", "board"])
def test_n4_delivery_commits_then_exposes_candidate_for_all_channels(
    asset_kind: str,
) -> None:
    planner = _planner(asset_kind)
    matched = _matched(asset_kind=asset_kind)
    changed = _state_changed(
        matched,
        trigger_live=True,
        formal_periods=("W", "D"),
    )
    connection = _FakeConnection()

    committed = _coordinator().deliver_n4(
        connection,
        planner=planner,
        deliveries=(
            N4OutboxDelivery(12, changed),
            N4OutboxDelivery(10, matched),
        ),
    )

    assert planner.read().active == {}
    assert [event.event_type for event in committed.output_events] == [
        "ActionEligible"
    ]
    episode = next(iter(committed.planner.read().active.values()))
    assert episode.current_source_event["event_id"] == changed.event_id
    assert committed.snapshot == committed.planner.read()
    assert committed.persistence.inbox_insert_count == 2
    assert committed.persistence.outbox_insert_count == 1
    assert committed.persistence.checkpoint_upsert_count == 1
    assert connection.begin_count == 1
    assert connection.commit_count == 1
    assert connection.rollback_count == 0


def test_commit_failure_discards_candidate_and_retry_is_identical() -> None:
    planner = _planner()
    delivery = N4OutboxDelivery(10, _matched())
    failed_connection = _FakeConnection(fail_commit=True)

    with pytest.raises(RuntimeError, match="fixture commit failure"):
        _coordinator().deliver_n4(
            failed_connection,
            planner=planner,
            deliveries=(delivery,),
        )

    assert planner.read().active == {}
    assert failed_connection.fake_cursor.inbox == set()
    assert failed_connection.fake_cursor.outbox == set()
    assert failed_connection.fake_cursor.checkpoints == {}
    assert failed_connection.commit_count == 0
    assert failed_connection.rollback_count == 1
    failed_values = _outbox_values(failed_connection.fake_cursor)

    retry_connection = _FakeConnection()
    committed = _coordinator().deliver_n4(
        retry_connection,
        planner=planner,
        deliveries=(delivery,),
    )
    retry_values = _outbox_values(retry_connection.fake_cursor)

    assert failed_values[0] == retry_values[0]
    assert failed_values[9] == retry_values[9]
    assert committed.output_events[0].event_id == retry_values[0]
    assert len(committed.planner.read().active) == 1


@pytest.mark.parametrize("asset_kind", ["stock", "index", "board"])
def test_closed_minute_action_executed_commits_without_n4_ack(
    asset_kind: str,
) -> None:
    planner = _planner(asset_kind)
    planner.consume_trigger_event(_matched(asset_kind=asset_kind))
    connection = _FakeConnection()

    committed = _coordinator().deliver_metric(
        connection,
        planner=planner,
        metric=_metric(asset_kind=asset_kind),
    )

    original = next(iter(planner.read().active.values()))
    adopted = next(iter(committed.planner.read().active.values()))
    assert original.action_state == "eligible"
    assert adopted.action_state == "executed"
    assert [event.event_type for event in committed.output_events] == [
        "ActionExecuted"
    ]
    assert committed.persistence.inbox_insert_count == 0
    assert committed.persistence.checkpoint_upsert_count == 0
    assert committed.persistence.outbox_insert_count == 1
    assert connection.commit_count == 1


def test_trigger_deactivation_and_close_expiry_write_action_skipped() -> None:
    matched = _matched()
    deactivation_planner = _planner()
    deactivation_planner.consume_trigger_event(matched)
    deactivation = _state_changed(matched, trigger_live=False)

    deactivated = _coordinator().deliver_n4(
        _FakeConnection(),
        planner=deactivation_planner,
        deliveries=(N4OutboxDelivery(20, deactivation),),
    )

    assert [event.event_type for event in deactivated.output_events] == [
        "ActionSkipped"
    ]
    assert deactivated.output_events[0].payload_json["skipped_reason"] == (
        "trigger_live_false"
    )
    assert deactivated.planner.read().active == {}
    assert len(deactivation_planner.read().active) == 1

    expiry_planner = _planner()
    expiry_planner.consume_trigger_event(_matched())
    expired = _coordinator().deliver_expiry(
        _FakeConnection(),
        planner=expiry_planner,
        observed_at=_time(15, 0),
    )

    assert [event.event_type for event in expired.output_events] == [
        "ActionSkipped"
    ]
    assert expired.output_events[0].payload_json["skipped_reason"] == (
        "window_expired"
    )
    assert expired.planner.read().active == {}
    assert len(expiry_planner.read().active) == 1


def test_transaction_module_has_no_connection_market_or_n6_boundary() -> None:
    source = Path(
        "src/ashare_v3/action/windows_n5_transaction.py"
    ).read_text(encoding="utf-8")

    assert "psycopg.connect" not in source
    assert "eltdx" not in source
    assert "ashare_v3.trigger" not in source
    assert "ashare_v3.user" not in source
    assert ".commit(" not in source
