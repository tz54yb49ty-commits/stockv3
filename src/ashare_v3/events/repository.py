"""Repository facade for common event infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.types.json import Jsonb

from ashare_v3.events.models import EventEnvelope, validate_event_envelope
from ashare_v3.events.outbox import insert_outbox_event


@dataclass
class EventRepository:
    """Small persistence facade used by layer services.

    The repository never owns transaction boundaries. The caller must open a
    transaction, write its fact table, then call this repository before commit.
    """

    cursor: Any

    def insert_outbox(self, envelope: EventEnvelope) -> str:
        validate_event_envelope(envelope)
        return insert_outbox_event(self.cursor, envelope)

    def insert_ledger(self, envelope: EventEnvelope) -> str:
        validate_event_envelope(envelope)
        record = envelope.as_record()
        columns = (
            "event_id",
            "event_type",
            "event_schema_version",
            "trade_date",
            "asset_kind",
            "identity_key",
            "event_time",
            "source_layer",
            "source_run_id",
            "dedup_key",
            "partition_key",
            "payload_json",
            "created_at",
        )
        placeholders = ", ".join(["%s"] * len(columns))
        self.cursor.execute(
            f"""
            INSERT INTO common_event_ledger ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT (event_id) DO NOTHING
            RETURNING event_id
            """,
            [Jsonb(record[column]) if column == "payload_json" else record[column] for column in columns],
        )
        fetched = self.cursor.fetchone()
        if isinstance(fetched, dict):
            return str(fetched["event_id"])
        if isinstance(fetched, tuple):
            return str(fetched[0])
        return envelope.event_id
