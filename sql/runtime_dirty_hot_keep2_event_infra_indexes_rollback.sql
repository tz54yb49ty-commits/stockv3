-- Rollback for runtime dirty hot keep-2 cleanup event-infra index draft.
-- Artifact only: do not execute outside an explicit rollback gate.

DROP INDEX IF EXISTS idx_common_event_inbox_source_event;
DROP INDEX IF EXISTS idx_common_event_outbox_trade_source_event;
