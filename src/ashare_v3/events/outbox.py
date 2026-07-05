"""Outbox persistence helpers.

These helpers intentionally do not commit. Callers must run them inside the
same transaction that writes the layer fact or projection.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from ashare_v3.events.models import EventEnvelope, validate_event_envelope


OUTBOX_COLUMNS = (
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


def build_outbox_record(envelope: EventEnvelope) -> dict[str, Any]:
    """Validate and convert an envelope into a common_event_outbox row."""

    validate_event_envelope(envelope)
    record = envelope.as_record()
    return {column: record[column] for column in OUTBOX_COLUMNS}


def insert_outbox_event(cursor: Any, envelope: EventEnvelope) -> str:
    """Insert an event into common_event_outbox inside the caller transaction."""

    record = build_outbox_record(envelope)
    placeholders = ", ".join(["%s"] * len(OUTBOX_COLUMNS))
    columns = ", ".join(OUTBOX_COLUMNS)
    update_assignments = """
      payload_json = EXCLUDED.payload_json,
      event_time = EXCLUDED.event_time,
      partition_key = EXCLUDED.partition_key,
      updated_at = now()
    """
    cursor.execute(
        f"""
        INSERT INTO common_event_outbox ({columns})
        VALUES ({placeholders})
        ON CONFLICT (event_id) DO UPDATE SET
          {update_assignments}
        RETURNING event_id
        """,
        [Jsonb(record[column]) if column == "payload_json" else record[column] for column in OUTBOX_COLUMNS],
    )
    fetched = cursor.fetchone()
    if isinstance(fetched, dict):
        return str(fetched["event_id"])
    if isinstance(fetched, tuple):
        return str(fetched[0])
    return envelope.event_id
