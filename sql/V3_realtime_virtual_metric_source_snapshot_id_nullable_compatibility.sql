-- V3 realtime virtual metric source_snapshot_id compatibility migration.
-- Stage: V3 realtime virtual metric writer source_snapshot_id compatibility.
-- Purpose:
--   Allow minute-source realtime virtual metric rows to use source_minute_refs,
--   source_fact_ids, and trace_json lineage without requiring a realtime snapshot
--   foreign-key row.
--
-- This migration is schema-only. It writes no business rows, no event rows, no
-- N4/N5/N6 rows, and starts no worker. Do not execute without a separate
-- runtime_control final gate and user confirmation.

ALTER TABLE stock_action_confirmation_projection_metric
  ALTER COLUMN source_snapshot_id DROP NOT NULL;

COMMENT ON COLUMN stock_action_confirmation_projection_metric.source_snapshot_id IS
  'source_snapshot_id nullable for minute-source realtime virtual metrics; when null, use source_minute_refs/source_fact_ids/trace_json lineage';

ALTER TABLE index_action_confirmation_projection_metric
  ALTER COLUMN source_snapshot_id DROP NOT NULL;

COMMENT ON COLUMN index_action_confirmation_projection_metric.source_snapshot_id IS
  'source_snapshot_id nullable for minute-source realtime virtual metrics; when null, use source_minute_refs/source_fact_ids/trace_json lineage';

ALTER TABLE board_action_confirmation_projection_metric
  ALTER COLUMN source_snapshot_id DROP NOT NULL;

COMMENT ON COLUMN board_action_confirmation_projection_metric.source_snapshot_id IS
  'source_snapshot_id nullable for minute-source realtime virtual metrics; when null, use source_minute_refs/source_fact_ids/trace_json lineage';
