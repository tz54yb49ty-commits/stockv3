-- N1 stock_identity 920211.BJ 20260605 refresh rollback draft.
-- Scope: stock_identity_refresh_20260605_920211_v1 / stock_identity_20260605_v1.
-- This rollback is intentionally hard-failed until an operator re-reviews
-- downstream refs and removes the first RAISE EXCEPTION in the correct
-- N1_ingestion rollback gate.
--
-- It must not touch official daily facts, condition source, N2/N3/N4/N5/N6,
-- outbox/inbox/checkpoint, Parquet, worker state, old system state, or trading.

BEGIN;

DO $$
BEGIN
  RAISE EXCEPTION 'Refusing N1 stock_identity 920211 20260605 rollback: manual N1_ingestion rollback gate required before DELETE/UPDATE';
END $$;

DO $$
DECLARE
  daily_ref_count integer;
  quality_ref_count integer;
  event_ref_count integer;
BEGIN
  SELECT COUNT(*)
  INTO daily_ref_count
  FROM stock_daily_bar_fact
  WHERE trade_date = '20260605'
    AND stock_identity_key = 'stock:BJ:920211';

  IF daily_ref_count > 0 THEN
    RAISE EXCEPTION 'Refusing N1 stock_identity 920211 rollback: official daily facts already reference stock:BJ:920211';
  END IF;

  SELECT COUNT(*)
  INTO quality_ref_count
  FROM common_quality_gate_result
  WHERE source_batch_id = 'official_daily_ingest_20260605_v1'
     OR source_version IN ('stock_daily_20260605_v1', 'index_daily_20260605_v1', 'board_daily_20260605_v1');

  IF quality_ref_count > 0 THEN
    RAISE EXCEPTION 'Refusing N1 stock_identity 920211 rollback: 20260605 official daily quality/fact lineage exists';
  END IF;

  SELECT
    (SELECT COUNT(*) FROM common_event_outbox WHERE source_run_id = 'stock_identity_refresh_20260605_920211_v1')
    + (SELECT COUNT(*) FROM common_event_inbox WHERE source_run_id = 'stock_identity_refresh_20260605_920211_v1')
  INTO event_ref_count;

  IF event_ref_count > 0 THEN
    RAISE EXCEPTION 'Refusing N1 stock_identity 920211 rollback: event infra refs exist';
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE data_domain = 'stock'
  AND data_type = 'stock_identity'
  AND scope_key = 'A_STOCK:20260605'
  AND source_batch_id = 'stock_identity_refresh_20260605_920211_v1'
  AND source_version = 'stock_identity_20260605_v1';

DELETE FROM stock_identity
WHERE stock_identity_key = 'stock:BJ:920211'
  AND ts_code = '920211.BJ'
  AND source_batch_id = 'stock_identity_refresh_20260605_920211_v1'
  AND source_version = 'stock_identity_20260605_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'stock_identity_refresh_20260605_920211_v1'
   OR source_version = 'stock_identity_20260605_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'stock_identity_refresh_20260605_920211_v1'
   OR source_version = 'stock_identity_20260605_v1';

COMMIT;
