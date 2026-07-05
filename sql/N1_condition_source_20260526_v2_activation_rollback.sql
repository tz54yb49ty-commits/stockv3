-- N1 condition source activation 20260526 v2 rollback draft.
-- Scope: condition source activation batch condition_source_activation_20260526_v2.
-- This rollback does not touch:
--   - v1 condition_source_activation_20260526_v1 artifacts
--   - official_daily_ingest_20260526_v2 daily bar facts
--   - trade_calendar_20260526_patch_v1
--   - Parquet
--   - outbox/inbox/checkpoint
--   - any N2/N3/N4/N5/N6 table
--   - old system or trading state

BEGIN;

DO $$
DECLARE
  missing_previous_batch_count integer;
BEGIN
  SELECT COUNT(*)
  INTO missing_previous_batch_count
  FROM common_active_source_version a
  WHERE a.source_batch_id = 'condition_source_activation_20260526_v2'
    AND (
      (a.data_domain = 'stock' AND a.data_type IN ('stock_daily_basic', 'stock_financial') AND a.scope_key = '20260526')
      OR (a.data_domain = 'index' AND a.data_type = 'index_membership' AND a.scope_key = 'TDX:20260526')
      OR (a.data_domain = 'board' AND a.data_type = 'board_membership' AND a.scope_key = 'TDX:20260526')
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
    RAISE EXCEPTION 'Refusing condition source 20260526 v2 rollback: previous_source_version cannot be resolved';
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
    activated_by = 'rollback:n1_condition_source_activation_20260526_v2'
WHERE a.source_batch_id = 'condition_source_activation_20260526_v2'
  AND a.previous_source_version IS NOT NULL
  AND (
    (a.data_domain = 'stock' AND a.data_type IN ('stock_daily_basic', 'stock_financial') AND a.scope_key = '20260526')
    OR (a.data_domain = 'index' AND a.data_type = 'index_membership' AND a.scope_key = 'TDX:20260526')
    OR (a.data_domain = 'board' AND a.data_type = 'board_membership' AND a.scope_key = 'TDX:20260526')
  );

DELETE FROM common_active_source_version
WHERE source_batch_id = 'condition_source_activation_20260526_v2'
  AND previous_source_version IS NULL
  AND (
    (data_domain = 'stock' AND data_type IN ('stock_daily_basic', 'stock_financial') AND scope_key = '20260526')
    OR (data_domain = 'index' AND data_type = 'index_membership' AND scope_key = 'TDX:20260526')
    OR (data_domain = 'board' AND data_type = 'board_membership' AND scope_key = 'TDX:20260526')
  );

DELETE FROM stock_daily_basic
WHERE trade_date = '20260526'
  AND source_batch_id = 'condition_source_activation_20260526_v2'
  AND source_version = 'stock_daily_basic_20260526_v2';

DELETE FROM stock_financial_metrics_fact
WHERE source_trade_date = '20260526'
  AND source_batch_id = 'condition_source_activation_20260526_v2'
  AND source_version = 'stock_financial_20260526_v2';

DELETE FROM index_membership_fact
WHERE trade_date = '20260526'
  AND source_batch_id = 'condition_source_activation_20260526_v2'
  AND source_version = 'index_membership_20260526_v2';

DELETE FROM board_membership_fact
WHERE trade_date = '20260526'
  AND source_batch_id = 'condition_source_activation_20260526_v2'
  AND source_version = 'board_membership_20260526_v2';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'condition_source_activation_20260526_v2'
   OR source_version IN (
     'condition_source_activation_20260526_v2',
     'stock_daily_basic_20260526_v2',
     'stock_financial_20260526_v2',
     'index_membership_20260526_v2',
     'board_membership_20260526_v2'
   );

DELETE FROM common_ingest_batch
WHERE batch_id = 'condition_source_activation_20260526_v2'
   OR source_version = 'condition_source_activation_20260526_v2';

COMMIT;
