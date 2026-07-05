-- N1 official daily 20260525 ingestion rollback draft.
-- Scope: PostgreSQL N1 official daily fact only.
-- Batch: official_daily_ingest_20260525_v1.
-- This SQL does not touch N2/N3/N4/N5/N6, C3 outbox, Parquet, workers, old system, or real trading.

BEGIN;

DO $$
DECLARE
  missing_previous_batch_count integer;
BEGIN
  SELECT COUNT(*)
  INTO missing_previous_batch_count
  FROM common_active_source_version a
  WHERE a.scope_key = '20260525'
    AND a.source_batch_id = 'official_daily_ingest_20260525_v1'
    AND (
      (a.data_domain = 'stock' AND a.data_type = 'stock_daily' AND a.source_version = 'stock_daily_20260525_v1')
      OR (a.data_domain = 'index' AND a.data_type = 'index_daily' AND a.source_version = 'index_daily_20260525_v1')
      OR (a.data_domain = 'board' AND a.data_type = 'board_daily' AND a.source_version = 'board_daily_20260525_v1')
    )
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
    RAISE EXCEPTION 'Refusing N1 official daily rollback: previous_source_version exists but previous source_batch_id cannot be resolved';
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
    activated_by = 'rollback:n1_official_daily_20260525'
WHERE a.scope_key = '20260525'
  AND a.source_batch_id = 'official_daily_ingest_20260525_v1'
  AND a.previous_source_version IS NOT NULL
  AND (
    (a.data_domain = 'stock' AND a.data_type = 'stock_daily' AND a.source_version = 'stock_daily_20260525_v1')
    OR (a.data_domain = 'index' AND a.data_type = 'index_daily' AND a.source_version = 'index_daily_20260525_v1')
    OR (a.data_domain = 'board' AND a.data_type = 'board_daily' AND a.source_version = 'board_daily_20260525_v1')
  );

DELETE FROM common_active_source_version
WHERE scope_key = '20260525'
  AND source_batch_id = 'official_daily_ingest_20260525_v1'
  AND previous_source_version IS NULL
  AND (
    (data_domain = 'stock' AND data_type = 'stock_daily' AND source_version = 'stock_daily_20260525_v1')
    OR (data_domain = 'index' AND data_type = 'index_daily' AND source_version = 'index_daily_20260525_v1')
    OR (data_domain = 'board' AND data_type = 'board_daily' AND source_version = 'board_daily_20260525_v1')
  );

DELETE FROM stock_daily_bar_fact
WHERE trade_date = '20260525'
  AND source_batch_id = 'official_daily_ingest_20260525_v1'
  AND source_version = 'stock_daily_20260525_v1';

DELETE FROM index_daily_bar_fact
WHERE trade_date = '20260525'
  AND source_batch_id = 'official_daily_ingest_20260525_v1'
  AND source_version = 'index_daily_20260525_v1';

DELETE FROM board_daily_bar_fact
WHERE trade_date = '20260525'
  AND source_batch_id = 'official_daily_ingest_20260525_v1'
  AND source_version = 'board_daily_20260525_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'official_daily_ingest_20260525_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'official_daily_ingest_20260525_v1';

COMMIT;
