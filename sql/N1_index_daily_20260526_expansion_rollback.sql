-- N1 index_daily 20260526 universe expansion rollback draft.
-- Scope: official_daily_ingest_20260526_index_expansion_v1 / index_daily_20260526_v3.
-- This rollback only touches index_daily expansion rows and common N1 batch/quality/active metadata.
-- It does not touch stock_daily_20260526_v2, board_daily_20260526_v2, condition source,
-- condition_* tables, N2/N3/N4/N5/N6, Parquet, outbox/inbox/checkpoint, worker, old system, or trading state.

BEGIN;

DO $$
DECLARE
  active_v3_count integer;
BEGIN
  SELECT COUNT(*)
  INTO active_v3_count
  FROM common_active_source_version
  WHERE data_domain = 'index'
    AND data_type = 'index_daily'
    AND scope_key = '20260526'
    AND source_batch_id = 'official_daily_ingest_20260526_index_expansion_v1'
    AND source_version = 'index_daily_20260526_v3';

  IF active_v3_count > 1 THEN
    RAISE EXCEPTION 'Refusing rollback: multiple active v3 rows for 20260526 index_daily';
  END IF;
END $$;

UPDATE common_active_source_version
SET source_version = 'index_daily_20260526_v2',
    source_batch_id = 'official_daily_ingest_20260526_v2',
    previous_source_version = NULL,
    activated_at = now(),
    activated_by = 'rollback:n1_index_daily_20260526_expansion'
WHERE data_domain = 'index'
  AND data_type = 'index_daily'
  AND scope_key = '20260526'
  AND source_batch_id = 'official_daily_ingest_20260526_index_expansion_v1'
  AND source_version = 'index_daily_20260526_v3';

DELETE FROM index_daily_bar_fact
WHERE trade_date = '20260526'
  AND source_batch_id = 'official_daily_ingest_20260526_index_expansion_v1'
  AND source_version = 'index_daily_20260526_v3';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'official_daily_ingest_20260526_index_expansion_v1'
   OR source_version = 'index_daily_20260526_v3';

DELETE FROM common_ingest_batch
WHERE batch_id = 'official_daily_ingest_20260526_index_expansion_v1'
   OR source_version = 'index_daily_20260526_v3';

COMMIT;
