from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ashare_v3.action.windows_n5_delivery import (
    N4OutboxDelivery,
    WindowsN5DeliveryPlan,
    n4_outbox_delivery_from_row,
    persist_windows_n5_delivery,
    plan_expiry_delivery,
    plan_metric_delivery,
    plan_n4_deliveries,
)
from ashare_v3.action.windows_n5_episode import WindowsN5EpisodePlanner
from tests.test_windows_n5_episode import _matched, _metric, _state_changed, _time


class _FakeCursor:
    def __init__(self) -> None:
        self.inbox: set[tuple[str, str]] = set()
        self.outbox: set[str] = set()
        self.outbox_rows: dict[str, tuple[int, tuple[object, ...]]] = {}
        self.dedup_event_ids: dict[tuple[str, ...], str] = {}
        self.next_outbox_id = 1
        self.checkpoints: dict[tuple[str, str, str], int] = {}
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self._returned: list[tuple[object, ...]] = []

    def execute(self, query, params) -> None:
        sql = " ".join(str(query).split())
        values = tuple(params)
        self.calls.append((sql, values))
        self._returned = []
        if "INSERT INTO common_event_inbox" in sql:
            key = (str(values[0]), str(values[1]))
            if key not in self.inbox:
                self.inbox.add(key)
                self._returned = [(values[1],)]
            return
        if "INSERT INTO common_event_outbox" in sql:
            event_id = str(values[0])
            dedup_identity = tuple(
                str(value)
                for value in (
                    values[7],
                    values[1],
                    values[8],
                    values[9],
                    values[2],
                )
            )
            if (
                event_id in self.outbox
                or dedup_identity in self.dedup_event_ids
            ):
                return
            outbox_id = self.next_outbox_id
            self.next_outbox_id += 1
            self.outbox.add(event_id)
            self.outbox_rows[event_id] = (outbox_id, values)
            self.dedup_event_ids[dedup_identity] = event_id
            self._returned = [(outbox_id, *values)]
            return
        if "FROM common_event_outbox" in sql:
            event_id, layer, event_type, run_id, dedup_key, schema = values
            dedup_identity = tuple(
                str(value)
                for value in (
                    layer,
                    event_type,
                    run_id,
                    dedup_key,
                    schema,
                )
            )
            matching_event_ids = {str(event_id)} & set(self.outbox_rows)
            dedup_event_id = self.dedup_event_ids.get(dedup_identity)
            if dedup_event_id is not None:
                matching_event_ids.add(dedup_event_id)
            self._returned = [
                (self.outbox_rows[key][0], *self.outbox_rows[key][1])
                for key in sorted(
                    matching_event_ids,
                    key=lambda item: self.outbox_rows[item][0],
                )[:2]
            ]
            return
        if "INSERT INTO common_event_consumer_checkpoint" in sql:
            key = (str(values[0]), str(values[1]), str(values[2]))
            outbox_id = int(values[5])
            if outbox_id > self.checkpoints.get(key, 0):
                self.checkpoints[key] = outbox_id
                self._returned = [(values[1],)]
            return
        raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._returned[0] if self._returned else None

    def fetchall(self):
        return list(self._returned)


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
    assert planner.read().active == {}
    assert plan.candidate_planner is not None
    assert len(plan.candidate_planner.read().active) == 1


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
    assert first.outbox_rows[0].outbox_id == 1
    assert first.outbox_rows[0].inserted is True
    assert first.checkpoint_upsert_count == 1
    assert first.database_write_count == 4
    assert replay.database_write_count == 0
    assert replay.outbox_rows[0].outbox_id == 1
    assert replay.outbox_rows[0].inserted is False
    checkpoint_key = (
        "windows_n5_state_v1",
        matched.partition_key,
        "N4_trigger",
    )
    assert cursor.checkpoints[checkpoint_key] == 12


def test_json_adapter_receives_only_json_safe_values() -> None:
    matched = _matched()
    matched = replace(
        matched,
        payload_json={
            **matched.payload_json,
            "nested": {
                "observed_at": _time(9, 36),
                "trade_date": date(2026, 8, 31),
                "amount": Decimal("12.34"),
            },
        },
    )
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_delivery_fixture",
    )
    plan = plan_n4_deliveries(
        planner,
        [N4OutboxDelivery(10, matched)],
    )
    cursor = _FakeCursor()
    adapted: list[object] = []

    def strict_json_adapter(value):
        json.dumps(value)
        adapted.append(value)
        return value

    result = persist_windows_n5_delivery(
        cursor,
        plan=plan,
        consumer_name="windows_n5_state_v1",
        json_adapter=strict_json_adapter,
    )

    assert result.database_write_count == 3
    assert len(adapted) == 4
    inbox_values = next(
        values
        for sql, values in cursor.calls
        if "INSERT INTO common_event_inbox" in sql
    )
    payload = inbox_values[8]
    raw_json = inbox_values[9]
    assert payload["nested"] == {
        "observed_at": _time(9, 36).isoformat(),
        "trade_date": "2026-08-31",
        "amount": "12.34",
    }
    assert raw_json["source_event"]["event_time"] == (
        matched.event_time.isoformat()
    )
    assert raw_json["source_event"]["created_at"] == (
        matched.created_at.isoformat()
    )


def test_metric_output_persists_without_new_n4_acknowledgement() -> None:
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_delivery_fixture",
    )
    planner.consume_trigger_event(_matched())
    plan = plan_metric_delivery(planner, _metric())
    cursor = _FakeCursor()

    assert next(iter(planner.read().active.values())).action_state == "eligible"
    assert plan.candidate_planner is not None
    assert plan.candidate_planner.read().active == {}
    result = persist_windows_n5_delivery(
        cursor,
        plan=plan,
        consumer_name="windows_n5_state_v1",
        json_adapter=lambda value: value,
    )

    assert result.inbox_insert_count == 0
    assert result.checkpoint_upsert_count == 0
    assert result.outbox_insert_count == 1
    assert next(iter(cursor.outbox)) == plan.output_events[0].event_id
    assert result.outbox_rows[0].event == plan.output_events[0]


def test_failed_persistence_discards_candidate_and_retry_still_emits() -> None:
    matched = _matched()
    delivery = N4OutboxDelivery(10, matched)
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_delivery_fixture",
    )
    first_plan = plan_n4_deliveries(planner, [delivery])

    class FailingCursor:
        def execute(self, _query, _params) -> None:
            raise RuntimeError("fixture transaction failure")

    with pytest.raises(RuntimeError, match="fixture transaction failure"):
        persist_windows_n5_delivery(
            FailingCursor(),
            plan=first_plan,
            consumer_name="windows_n5_state_v1",
            json_adapter=lambda value: value,
        )

    assert planner.read().active == {}
    retry_plan = plan_n4_deliveries(planner, [delivery])
    assert [event.event_type for event in retry_plan.output_events] == [
        "ActionEligible"
    ]


def test_expiry_delivery_is_candidate_only_until_adopted() -> None:
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_delivery_fixture",
    )
    planner.consume_trigger_event(_matched())

    plan = plan_expiry_delivery(planner, _time(15, 0))

    assert len(planner.read().active) == 1
    assert [event.event_type for event in plan.output_events] == [
        "ActionSkipped"
    ]
    assert plan.candidate_planner is not None
    assert plan.candidate_planner.read().active == {}


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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("event_type", "ActionSkipped"),
        ("dedup_key", "windows-n5-conflicting-dedup"),
        ("source_run_id", "windows-n5-conflicting-run"),
        ("payload_json", "fixture_conflict"),
    ),
)
def test_idempotent_conflict_must_match_authoritative_event_identity(
    field: str,
    value: str,
) -> None:
    planner = WindowsN5EpisodePlanner(
        asset_kind="stock",
        action_run_id="windows_n5_delivery_fixture",
    )
    plan = plan_n4_deliveries(
        planner,
        [N4OutboxDelivery(10, _matched())],
    )
    cursor = _FakeCursor()
    persist_windows_n5_delivery(
        cursor,
        plan=plan,
        consumer_name="windows_n5_state_v1",
        json_adapter=lambda payload: payload,
    )
    if field == "event_type":
        payload = {
            **plan.output_events[0].payload_json,
            "action_state": "expired",
            "confirmation_status": "expired",
            "eligibility_reason": None,
            "skipped_reason": "fixture_conflict",
        }
        conflicting_event = replace(
            plan.output_events[0], event_type=value, payload_json=payload
        )
    elif field == "payload_json":
        conflicting_event = replace(
            plan.output_events[0],
            payload_json={**plan.output_events[0].payload_json, value: True},
        )
    else:
        conflicting_event = replace(plan.output_events[0], **{field: value})
    conflicting_plan = replace(plan, output_events=(conflicting_event,))

    with pytest.raises(
        RuntimeError,
        match="authoritative N5 outbox row does not match planned event",
    ):
        persist_windows_n5_delivery(
            cursor,
            plan=conflicting_plan,
            consumer_name="windows_n5_state_v1",
            json_adapter=lambda payload: payload,
        )


def test_delivery_module_never_connects_or_commits() -> None:
    source = Path(
        "src/ashare_v3/action/windows_n5_delivery.py"
    ).read_text(encoding="utf-8")

    assert "psycopg.connect" not in source
    assert ".commit(" not in source
    assert "eltdx" not in source
    assert "ashare_v3.user" not in source
