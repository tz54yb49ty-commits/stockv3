from __future__ import annotations

from pathlib import Path

import pytest

from ashare_v3.action.windows_n5_delivery import (
    N4OutboxDelivery,
    WindowsN5DeliveryPlan,
    n4_outbox_delivery_from_row,
    persist_windows_n5_delivery,
    plan_n4_deliveries,
    plan_output_events,
)
from ashare_v3.action.windows_n5_episode import WindowsN5EpisodePlanner
from tests.test_windows_n5_episode import _matched, _metric, _state_changed


class _FakeCursor:
    def __init__(self) -> None:
        self.inbox: set[tuple[str, str]] = set()
        self.outbox: set[str] = set()
        self.checkpoints: dict[tuple[str, str, str], int] = {}
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._returned = None

    def execute(self, query, params) -> None:
        sql = " ".join(str(query).split())
        values = tuple(params)
        self.calls.append((sql, values))
        self._returned = None
        if "INSERT INTO common_event_inbox" in sql:
            key = (str(values[0]), str(values[1]))
            if key not in self.inbox:
                self.inbox.add(key)
                self._returned = (values[1],)
            return
        if "INSERT INTO common_event_outbox" in sql:
            event_id = str(values[0])
            if event_id not in self.outbox:
                self.outbox.add(event_id)
                self._returned = (event_id,)
            return
        if "INSERT INTO common_event_consumer_checkpoint" in sql:
            key = (str(values[0]), str(values[1]), str(values[2]))
            outbox_id = int(values[5])
            if outbox_id > self.checkpoints.get(key, 0):
                self.checkpoints[key] = outbox_id
                self._returned = (values[1],)
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._returned


def _row(event, outbox_id: int) -> dict[str, object]:
    return {
        **event.as_record(),
        "outbox_id": outbox_id,
        "status": "pending",
    }


def test_outbox_row_round_trip_and_candidate_plan() -> None:
    matched = _matched()
    delivery = n4_outbox_delivery_from_row(_row(matched, 10))
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_delivery_fixture",
    )

    plan = plan_n4_deliveries(planner, [delivery])

    assert delivery.event.event_id == matched.event_id
    assert plan.source_events == (delivery,)
    assert [event.event_type for event in plan.output_events] == [
        "ActionEligible"
    ]
    assert len(plan.snapshot.active) == 1


def test_delivery_persistence_is_atomic_intent_and_idempotent() -> None:
    matched = _matched()
    changed = _state_changed(
        matched,
        trigger_live=True,
        formal_periods=("W", "D"),
    )
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_delivery_fixture",
    )
    plan = plan_n4_deliveries(
        planner,
        [
            N4OutboxDelivery(10, matched),
            N4OutboxDelivery(12, changed),
        ],
    )
    cursor = _FakeCursor()

    first = persist_windows_n5_delivery(
        cursor,
        plan=plan,
        consumer_name="windows_n5_state_v1",
        json_adapter=lambda value: value,
    )
    replay = persist_windows_n5_delivery(
        cursor,
        plan=plan,
        consumer_name="windows_n5_state_v1",
        json_adapter=lambda value: value,
    )

    assert first.inbox_insert_count == 2
    assert first.outbox_insert_count == 1
    assert first.checkpoint_upsert_count == 1
    assert first.database_write_count == 4
    assert replay.database_write_count == 0
    checkpoint_key = (
        "windows_n5_state_v1",
        matched.partition_key,
        "N4_trigger",
    )
    assert cursor.checkpoints[checkpoint_key] == 12


def test_metric_output_persists_without_new_n4_acknowledgement() -> None:
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_delivery_fixture",
    )
    planner.consume_trigger_event(_matched())
    metric_batch = planner.consume_metric(_metric())
    plan = plan_output_events(metric_batch.snapshot, metric_batch.events)
    cursor = _FakeCursor()

    result = persist_windows_n5_delivery(
        cursor,
        plan=plan,
        consumer_name="windows_n5_state_v1",
        json_adapter=lambda value: value,
    )

    assert result.inbox_insert_count == 0
    assert result.checkpoint_upsert_count == 0
    assert result.outbox_insert_count == 1
    assert next(iter(cursor.outbox)) == metric_batch.events[0].event_id


def test_duplicate_source_outbox_id_is_rejected_before_planning() -> None:
    matched = _matched()
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_delivery_fixture",
    )

    with pytest.raises(ValueError, match="duplicate source outbox_id"):
        plan_n4_deliveries(
            planner,
            [
                N4OutboxDelivery(10, matched),
                N4OutboxDelivery(10, matched),
            ],
        )

    assert planner.read().active == {}


def test_delivery_module_never_connects_or_commits() -> None:
    source = Path(
        "src/ashare_v3/action/windows_n5_delivery.py"
    ).read_text(encoding="utf-8")

    assert "psycopg.connect" not in source
    assert ".commit(" not in source
    assert "eltdx" not in source
    assert "ashare_v3.user" not in source
