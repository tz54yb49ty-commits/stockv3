-- Runtime dirty hot keep-2 cleanup event-infra index draft.
-- Artifact only: do not execute outside an explicit schema migration gate.
-- Purpose: speed up plan-only event inbox/outbox count queries for old hot runtime cleanup.

CREATE INDEX IF NOT EXISTS idx_common_event_outbox_trade_source_event
  ON common_event_outbox (trade_date, source_layer, event_id);

CREATE INDEX IF NOT EXISTS idx_common_event_inbox_source_event
  ON common_event_inbox (source_layer, event_id);
