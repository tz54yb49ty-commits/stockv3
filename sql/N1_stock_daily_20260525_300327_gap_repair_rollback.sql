-- Rollback for N1 20260525 stock_daily 300327 single-row gap repair.
-- Scope: only stock:SZ:300327 inserted by stock_daily_20260525_300327_gap_repair_v1.
-- Does not touch original official_daily_ingest_20260525_v1 rows, active_source_version,
-- condition tables, outbox/inbox/checkpoint, downstream layers, Parquet, workers, old system, or trading.

BEGIN;

DELETE FROM stock_daily_bar_fact
WHERE stock_identity_key = 'stock:SZ:300327'
  AND trade_date = '20260525'
  AND source_version = 'stock_daily_20260525_v1'
  AND source_batch_id = 'stock_daily_20260525_300327_gap_repair_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'stock_daily_20260525_300327_gap_repair_v1'
  AND source_version = 'stock_daily_20260525_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'stock_daily_20260525_300327_gap_repair_v1'
  AND source_version = 'stock_daily_20260525_v1'
  AND data_domain = 'stock'
  AND data_type = 'stock_daily_gap_repair';

COMMIT;
