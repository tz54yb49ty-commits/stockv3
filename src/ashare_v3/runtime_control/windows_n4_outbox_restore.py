"""Read-only startup loader for Windows N4 lifecycle Outbox events.

The loader selects same-day Windows N4 lifecycle events, groups them by
stock/index/board, and freezes the last N4 state version for each channel.
It owns no writes and does not mutate the event rows.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ashare_v3.action.windows_n5_delivery import (
    n4_outbox_delivery_from_row,
)
from ashare_v3.events.models import (
    EventEnvelope,
    N4_SOURCE_LAYER,
    validate_event_envelope,
)
from ashare_v3.trigger.windows_n4_state_transition import (
    RULE_POLICY_VERSION,
)


ASSET_KINDS = ("stock", "index", "board")
RESTORE_EVENT_TYPES = ("TriggerMatched", "TriggerStateChanged")
OUTBOX_RESTORE_SELECT = """
    SELECT outbox_id, event_id, event_type, event_schema_version,
           trade_date, asset_kind, identity_key, event_time,
           source_layer, source_run_id, dedup_key, partition_key,
           payload_json, created_at
    FROM common_event_outbox
    WHERE source_layer = 'N4_trigger'
      AND trade_date = %s
      AND event_type = ANY(%s)
      AND asset_kind = ANY(%s)
      AND payload_json->>'source_condition_run_id' = %s
      AND payload_json->>'rule_policy_version' = %s
    ORDER BY outbox_id, event_id
"""


@dataclass(frozen=True, slots=True)
class WindowsN4OutboxRestoreBundle:
    events: Mapping[str, tuple[EventEnvelope, ...]]
    last_versions: Mapping[str, int]

    def __post_init__(self) -> None:
        expected = set(ASSET_KINDS)
        if set(self.events) != expected or set(self.last_versions) != expected:
            raise ValueError(
                "restore bundle must contain exactly stock/index/board"
            )
        events = {
            kind: tuple(self.events[kind])
            for kind in ASSET_KINDS
        }
        versions = dict(self.last_versions)
        if any(type(value) is not int or value < 0 for value in versions.values()):
            raise ValueError("restore versions must be non-negative integers")
        object.__setattr__(self, "events", MappingProxyType(events))
        object.__setattr__(
            self,
            "last_versions",
            MappingProxyType(versions),
        )


def build_windows_n4_outbox_restore_bundle(
    events: Sequence[EventEnvelope],
    *,
    source_condition_run_id: str,
    for_trade_date: str,
) -> WindowsN4OutboxRestoreBundle:
    grouped: dict[str, dict[str, EventEnvelope]] = {
        kind: {} for kind in ASSET_KINDS
    }
    for event in events:
        validate_event_envelope(event)
        payload = event.payload_json
        if (
            event.source_layer != N4_SOURCE_LAYER
            or event.event_type not in RESTORE_EVENT_TYPES
            or event.asset_kind not in grouped
            or event.trade_date != for_trade_date
            or payload.get("source_condition_run_id")
            != source_condition_run_id
            or payload.get("rule_policy_version")
            != RULE_POLICY_VERSION
        ):
            raise ValueError("event is outside the requested N4 restore lineage")
        version = payload.get("n4_state_version")
        if type(version) is not int or version < 1:
            raise ValueError("N4 restore event requires positive n4_state_version")
        previous = grouped[event.asset_kind].get(event.event_id)
        if previous is not None and previous.as_record() != event.as_record():
            raise ValueError(f"conflicting duplicate event_id: {event.event_id}")
        grouped[event.asset_kind][event.event_id] = event

    ordered = {
        kind: tuple(
            sorted(
                values.values(),
                key=lambda event: (
                    int(event.payload_json["n4_state_version"]),
                    event.event_time,
                    event.event_id,
                ),
            )
        )
        for kind, values in grouped.items()
    }
    return WindowsN4OutboxRestoreBundle(
        events=ordered,
        last_versions={
            kind: max(
                (
                    int(event.payload_json["n4_state_version"])
                    for event in channel_events
                ),
                default=0,
            )
            for kind, channel_events in ordered.items()
        },
    )


class WindowsN4OutboxReadOnlyRepository:
    def __init__(
        self,
        dsn: str,
        *,
        connect: Callable[..., Any] = psycopg.connect,
    ) -> None:
        self.dsn = dsn
        self._connect = connect

    def load(
        self,
        *,
        source_condition_run_id: str,
        for_trade_date: str,
    ) -> WindowsN4OutboxRestoreBundle:
        with self._connect(self.dsn, row_factory=dict_row) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(
                    OUTBOX_RESTORE_SELECT,
                    (
                        for_trade_date,
                        list(RESTORE_EVENT_TYPES),
                        list(ASSET_KINDS),
                        source_condition_run_id,
                        RULE_POLICY_VERSION,
                    ),
                )
                rows = tuple(cur.fetchall())
        events = tuple(
            n4_outbox_delivery_from_row(row).event
            for row in rows
        )
        return build_windows_n4_outbox_restore_bundle(
            events,
            source_condition_run_id=source_condition_run_id,
            for_trade_date=for_trade_date,
        )
