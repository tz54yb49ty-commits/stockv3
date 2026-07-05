-- N1 official daily 20260527 rollback draft.
-- Scope: official_daily_ingest_20260527_v1.
-- This rollback is for a future execute after the current stock_identity blocker is resolved.
-- It must not touch calendar patch, condition source, N2/N3/N4/N5/N6, outbox/inbox/checkpoint, Parquet, worker, old system, or trading state.

BEGIN;

DELETE FROM common_active_source_version
WHERE scope_key = '20260527'
  AND source_batch_id = 'official_daily_ingest_20260527_v1'
  AND source_version IN (
    'stock_daily_20260527_v1',
    'index_daily_20260527_v1',
    'board_daily_20260527_v1'
  )
  AND data_type IN ('stock_daily', 'index_daily', 'board_daily');

DELETE FROM stock_daily_bar_fact
WHERE trade_date = '20260527'
  AND source_batch_id = 'official_daily_ingest_20260527_v1'
  AND source_version = 'stock_daily_20260527_v1';

DELETE FROM index_daily_bar_fact
WHERE trade_date = '20260527'
  AND source_batch_id = 'official_daily_ingest_20260527_v1'
  AND source_version = 'index_daily_20260527_v1';

DELETE FROM board_daily_bar_fact
WHERE trade_date = '20260527'
  AND source_batch_id = 'official_daily_ingest_20260527_v1'
  AND source_version = 'board_daily_20260527_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'official_daily_ingest_20260527_v1'
   OR source_version IN (
     'stock_daily_20260527_v1',
     'index_daily_20260527_v1',
     'board_daily_20260527_v1'
   );

DELETE FROM common_ingest_batch
WHERE batch_id = 'official_daily_ingest_20260527_v1'
   OR source_version IN (
     'official_daily_ingest_20260527_v1',
     'stock_daily_20260527_v1',
     'index_daily_20260527_v1',
     'board_daily_20260527_v1'
   );

COMMIT;
