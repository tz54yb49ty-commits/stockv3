-- N1 trade calendar 20260528 patch rollback draft.
-- Scope: trade_calendar_20260528_patch_v1.
-- This rollback does not touch 20260527 calendar, daily fact, condition source,
-- Parquet, outbox/inbox/checkpoint, N2/N3/N4/N5/N6, worker, old system, or
-- trading state.

BEGIN;

DO $$
DECLARE
  missing_previous_batch_count integer;
BEGIN
  SELECT COUNT(*)
  INTO missing_previous_batch_count
  FROM common_active_source_version a
  WHERE a.data_domain = 'common'
    AND a.data_type = 'trade_calendar'
    AND a.scope_key = 'SSE:20260528'
    AND a.source_batch_id = 'trade_calendar_20260528_patch_v1'
    AND a.source_version = 'trade_calendar_20260528_patch_v1'
    AND a.previous_source_version IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM common_ingest_batch b
      WHERE b.data_domain = a.data_domain
        AND b.data_type = a.data_type
        AND b.source_version = a.previous_source_version
        AND b.status = 'passed'
    );

  IF missing_previous_batch_count > 0 THEN
    RAISE EXCEPTION 'Refusing 20260528 calendar patch rollback: previous_source_version cannot be resolved';
  END IF;
END $$;

UPDATE common_active_source_version a
SET source_version = a.previous_source_version,
    source_batch_id = (
      SELECT b.batch_id
      FROM common_ingest_batch b
      WHERE b.data_domain = a.data_domain
        AND b.data_type = a.data_type
        AND b.source_version = a.previous_source_version
        AND b.status = 'passed'
      ORDER BY b.finished_at DESC NULLS LAST, b.started_at DESC, b.batch_id DESC
      LIMIT 1
    ),
    previous_source_version = NULL,
    activated_at = now(),
    activated_by = 'rollback:n1_trade_calendar_20260528_patch'
WHERE a.data_domain = 'common'
  AND a.data_type = 'trade_calendar'
  AND a.scope_key = 'SSE:20260528'
  AND a.source_batch_id = 'trade_calendar_20260528_patch_v1'
  AND a.source_version = 'trade_calendar_20260528_patch_v1'
  AND a.previous_source_version IS NOT NULL;

DELETE FROM common_active_source_version
WHERE data_domain = 'common'
  AND data_type = 'trade_calendar'
  AND scope_key = 'SSE:20260528'
  AND source_batch_id = 'trade_calendar_20260528_patch_v1'
  AND source_version = 'trade_calendar_20260528_patch_v1'
  AND previous_source_version IS NULL;

DELETE FROM common_trade_calendar
WHERE trade_date = '20260528'
  AND source_batch_id = 'trade_calendar_20260528_patch_v1'
  AND source_version = 'trade_calendar_20260528_patch_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'trade_calendar_20260528_patch_v1'
   OR source_version = 'trade_calendar_20260528_patch_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'trade_calendar_20260528_patch_v1'
   OR source_version = 'trade_calendar_20260528_patch_v1';

COMMIT;
