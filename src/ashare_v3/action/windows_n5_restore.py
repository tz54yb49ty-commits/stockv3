"""Read-only same-day Windows N5 episode restoration.

N4 source events are restored only from N5's processed inbox evidence. N5
action lifecycle events are restored from the N5 outbox. The repository never
writes inbox, outbox, checkpoint, action facts, or any upstream/downstream
state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from ashare_v3.action.windows_n5_episode import (
    SUPPORTED_SOURCE_RULE_POLICY_VERSIONS,
    WindowsN5EpisodePlanner,
)
from ashare_v3.events.models import (
    EventEnvelope,
    N4_SOURCE_LAYER,
    N5_SOURCE_LAYER,
    validate_event_envelope,
)


ASSET_KINDS = ("stock", "index", "board")
N4_EVENT_TYPES = ("TriggerMatched", "TriggerStateChanged")
N5_EVENT_TYPES = (
    "ActionEligible",
    "ActionBlocked",
    "ActionExecuted",
    "ActionSkipped",
)

N4_INBOX_RESTORE_SELECT = """
    SELECT inbox_id, raw_json
    FROM common_event_inbox
    WHERE consumer_name = %s
      AND status = 'processed'
      AND source_layer = 'N4_trigger'
      AND event_type = ANY(%s)
      AND raw_json ? 'source_event'
      AND raw_json->'source_event'->>'trade_date' = %s
      AND raw_json->'source_event'->>'asset_kind' = ANY(%s)
      AND raw_json->'source_event'->'payload_json'
            ->>'source_condition_run_id' = %s
      AND raw_json->'source_event'->'payload_json'
            ->>'rule_policy_version' = ANY(%s)
    ORDER BY
      (raw_json->'source_event'->>'event_time')::timestamptz,
      inbox_id
"""

N5_OUTBOX_RESTORE_SELECT = """
    SELECT outbox_id, event_id, event_type, event_schema_version,
           trade_date, asset_kind, identity_key, event_time,
           source_layer, source_run_id, dedup_key, partition_key,
           payload_json, created_at
    FROM common_event_outbox
    WHERE source_layer = 'N5_action'
      AND event_type = ANY(%s)
      AND trade_date = %s
      AND asset_kind = ANY(%s)
      AND source_run_id = ANY(%s)
      AND payload_json->>'source_condition_run_id' = %s
    ORDER BY event_time, outbox_id
"""


@dataclass(frozen=True, slots=True)
class WindowsN5EpisodeRestoreBundle:
    source_condition_run_id: str
    for_trade_date: str
    consumer_name: str
    events: Mapping[str, tuple[EventEnvelope, ...]]
    n4_inbox_event_counts: Mapping[str, int]
    n5_outbox_event_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        for field_name in (
            "events",
            "n4_inbox_event_counts",
            "n5_outbox_event_counts",
        ):
            value = dict(getattr(self, field_name))
            if set(value) != set(ASSET_KINDS):
                raise ValueError(
                    f"{field_name} must contain stock/index/board"
                )
            object.__setattr__(self, field_name, MappingProxyType(value))

    def restore_planners(
        self,
        action_run_ids: Mapping[str, str],
    ) -> Mapping[str, WindowsN5EpisodePlanner]:
        _validate_action_run_ids(action_run_ids)
        planners: dict[str, WindowsN5EpisodePlanner] = {}
        for asset_kind in ASSET_KINDS:
            planner = WindowsN5EpisodePlanner(
                asset_kind=asset_kind,
                action_run_id=action_run_ids[asset_kind],
            )
            planner.restore_from_outbox(self.events[asset_kind])
            planners[asset_kind] = planner
        return MappingProxyType(planners)


def build_windows_n5_episode_restore_bundle(
    *,
    n4_inbox_events: Sequence[EventEnvelope],
    n5_outbox_events: Sequence[EventEnvelope],
    source_condition_run_id: str,
    for_trade_date: str,
    consumer_name: str,
    action_run_ids: Mapping[str, str],
) -> WindowsN5EpisodeRestoreBundle:
    if not source_condition_run_id:
        raise ValueError("source_condition_run_id is required")
    if len(for_trade_date) != 8 or not for_trade_date.isdigit():
        raise ValueError("for_trade_date must be YYYYMMDD")
    if not consumer_name.strip():
        raise ValueError("consumer_name is required")
    _validate_action_run_ids(action_run_ids)

    grouped: dict[str, dict[str, EventEnvelope]] = {
        kind: {} for kind in ASSET_KINDS
    }
    n4_counts = {kind: 0 for kind in ASSET_KINDS}
    n5_counts = {kind: 0 for kind in ASSET_KINDS}
    for event in n4_inbox_events:
        _validate_restore_event(
            event,
            source_condition_run_id=source_condition_run_id,
            for_trade_date=for_trade_date,
            action_run_ids=action_run_ids,
        )
        if event.event_id not in grouped[event.asset_kind]:
            grouped[event.asset_kind][event.event_id] = event
            n4_counts[event.asset_kind] += 1
    for event in n5_outbox_events:
        _validate_restore_event(
            event,
            source_condition_run_id=source_condition_run_id,
            for_trade_date=for_trade_date,
            action_run_ids=action_run_ids,
        )
        if event.event_id not in grouped[event.asset_kind]:
            grouped[event.asset_kind][event.event_id] = event
            n5_counts[event.asset_kind] += 1

    return WindowsN5EpisodeRestoreBundle(
        source_condition_run_id=source_condition_run_id,
        for_trade_date=for_trade_date,
        consumer_name=consumer_name,
        events={
            kind: tuple(
                sorted(grouped[kind].values(), key=_event_order_key)
            )
            for kind in ASSET_KINDS
        },
        n4_inbox_event_counts=n4_counts,
        n5_outbox_event_counts=n5_counts,
    )


class WindowsN5EpisodeReadOnlyRepository:
    def __init__(
        self,
        dsn: str,
        *,
        consumer_name: str,
        connect: Callable[..., Any] | None = None,
    ) -> None:
        if not dsn:
            raise ValueError("dsn is required")
        if not consumer_name.strip():
            raise ValueError("consumer_name is required")
        self.dsn = dsn
        self.consumer_name = consumer_name
        self._connect = connect or _default_connect

    def load(
        self,
        *,
        source_condition_run_id: str,
        for_trade_date: str,
        action_run_ids: Mapping[str, str],
    ) -> WindowsN5EpisodeRestoreBundle:
        _validate_action_run_ids(action_run_ids)
        with self._connect(self.dsn) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(
                    N4_INBOX_RESTORE_SELECT,
                    (
                        self.consumer_name,
                        list(N4_EVENT_TYPES),
                        for_trade_date,
                        list(ASSET_KINDS),
                        source_condition_run_id,
                        list(SUPPORTED_SOURCE_RULE_POLICY_VERSIONS),
                    ),
                )
                n4_events = tuple(
                    _n4_event_from_inbox_row(row)
                    for row in cur.fetchall()
                )
                cur.execute(
                    N5_OUTBOX_RESTORE_SELECT,
                    (
                        list(N5_EVENT_TYPES),
                        for_trade_date,
                        list(ASSET_KINDS),
                        [action_run_ids[kind] for kind in ASSET_KINDS],
                        source_condition_run_id,
                    ),
                )
                n5_events = tuple(
                    _event_from_record(row)
                    for row in cur.fetchall()
                )
        return build_windows_n5_episode_restore_bundle(
            n4_inbox_events=n4_events,
            n5_outbox_events=n5_events,
            source_condition_run_id=source_condition_run_id,
            for_trade_date=for_trade_date,
            consumer_name=self.consumer_name,
            action_run_ids=action_run_ids,
        )


def _validate_action_run_ids(action_run_ids: Mapping[str, str]) -> None:
    if set(action_run_ids) != set(ASSET_KINDS):
        raise ValueError("action_run_ids must contain stock/index/board")
    if any(not str(action_run_ids[kind]).strip() for kind in ASSET_KINDS):
        raise ValueError("action_run_ids values are required")


def _validate_restore_event(
    event: EventEnvelope,
    *,
    source_condition_run_id: str,
    for_trade_date: str,
    action_run_ids: Mapping[str, str],
) -> None:
    validate_event_envelope(event)
    if event.trade_date != for_trade_date:
        raise ValueError("N5 restore event outside for_trade_date")
    if event.asset_kind not in ASSET_KINDS:
        raise ValueError("N5 restore event outside stock/index/board")
    payload = event.payload_json
    if (
        str(payload.get("source_condition_run_id") or "")
        != source_condition_run_id
    ):
        raise ValueError("N5 restore event outside N2 lineage")
    if event.source_layer == N4_SOURCE_LAYER:
        if event.event_type not in N4_EVENT_TYPES:
            raise ValueError("unsupported N4 inbox restore event")
        if (
            str(payload.get("rule_policy_version") or "")
            not in SUPPORTED_SOURCE_RULE_POLICY_VERSIONS
        ):
            raise ValueError("unsupported N4 restore rule_policy_version")
        return
    if event.source_layer == N5_SOURCE_LAYER:
        if event.event_type not in N5_EVENT_TYPES:
            raise ValueError("unsupported N5 outbox restore event")
        if event.source_run_id != action_run_ids[event.asset_kind]:
            raise ValueError("N5 restore event outside action_run_id")
        if str(payload.get("run_id") or "") != event.source_run_id:
            raise ValueError("N5 restore payload run_id mismatch")
        return
    raise ValueError("N5 restore accepts only N4 inbox and N5 outbox events")


def _n4_event_from_inbox_row(row: Mapping[str, Any]) -> EventEnvelope:
    raw_json = row.get("raw_json")
    if not isinstance(raw_json, Mapping):
        raise ValueError("N4 inbox raw_json must be a mapping")
    source_event = raw_json.get("source_event")
    if not isinstance(source_event, Mapping):
        raise ValueError("N4 inbox raw_json.source_event must be a mapping")
    return _event_from_record(source_event)


def _event_from_record(record: Mapping[str, Any]) -> EventEnvelope:
    payload = record.get("payload_json")
    if not isinstance(payload, Mapping):
        raise ValueError("restore payload_json must be a mapping")
    event = EventEnvelope(
        event_id=str(record.get("event_id") or ""),
        event_type=str(record.get("event_type") or ""),
        event_schema_version=str(record.get("event_schema_version") or ""),
        trade_date=str(record.get("trade_date") or ""),
        asset_kind=str(record.get("asset_kind") or ""),
        identity_key=str(record.get("identity_key") or ""),
        event_time=_datetime_value(record.get("event_time"), "event_time"),
        source_layer=str(record.get("source_layer") or ""),
        source_run_id=str(record.get("source_run_id") or ""),
        dedup_key=str(record.get("dedup_key") or ""),
        partition_key=str(record.get("partition_key") or ""),
        payload_json=dict(payload),
        created_at=_datetime_value(record.get("created_at"), "created_at"),
    )
    validate_event_envelope(event)
    return event


def _datetime_value(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"invalid restore {field_name}") from error
    raise ValueError(f"restore {field_name} must be datetime")


def _event_order_key(event: EventEnvelope) -> tuple[Any, ...]:
    return (
        event.event_time,
        event.created_at,
        0 if event.source_layer == N4_SOURCE_LAYER else 1,
        event.event_id,
    )


def _default_connect(dsn: str):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(dsn, row_factory=dict_row)
