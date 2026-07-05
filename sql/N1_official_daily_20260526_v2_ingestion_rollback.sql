-- N1 official daily 20260526 v2 rollback draft.
-- Scope: official daily fact ingestion batch official_daily_ingest_20260526_v2.
-- This rollback does not touch v1 artifacts, the 20260526 calendar patch,
-- Parquet, outbox/inbox/checkpoint, or any N2-N6 tables.

BEGIN;

DELETE FROM common_active_source_version
WHERE scope_key = '20260526'
  AND source_batch_id = 'official_daily_ingest_20260526_v2'
  AND (
    (data_domain = 'stock' AND data_type = 'stock_daily' AND source_version = 'stock_daily_20260526_v2')
    OR (data_domain = 'index' AND data_type = 'index_daily' AND source_version = 'index_daily_20260526_v2')
    OR (data_domain = 'board' AND data_type = 'board_daily' AND source_version = 'board_daily_20260526_v2')
  );

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'official_daily_ingest_20260526_v2'
   OR source_version IN (
     'official_daily_ingest_20260526_v2',
     'stock_daily_20260526_v2',
     'index_daily_20260526_v2',
     'board_daily_20260526_v2'
   );

DELETE FROM stock_daily_bar_fact
WHERE trade_date = '20260526'
  AND source_batch_id = 'official_daily_ingest_20260526_v2'
  AND source_version = 'stock_daily_20260526_v2';

DELETE FROM index_daily_bar_fact
WHERE trade_date = '20260526'
  AND source_batch_id = 'official_daily_ingest_20260526_v2'
  AND source_version = 'index_daily_20260526_v2';

DELETE FROM board_daily_bar_fact
WHERE trade_date = '20260526'
  AND source_batch_id = 'official_daily_ingest_20260526_v2'
  AND source_version = 'board_daily_20260526_v2';

DELETE FROM common_ingest_batch
WHERE batch_id = 'official_daily_ingest_20260526_v2';

COMMIT;
