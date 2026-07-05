-- N1 condition source activation 20260602 rollback.
-- Scope: condition_source_activation_20260602_v1.
-- This rollback must not touch:
--   - official_daily_ingest_20260602_v1 daily bar facts
--   - stock identity rows or identity refresh artifacts
--   - trade_calendar_20260602_patch_v1
--   - Parquet
--   - outbox/inbox/checkpoint
--   - any N2/N3/N4/N5/N6 table
--   - old system, delivery, notification, worker, sim, position, or real trade

BEGIN;

DO $$
DECLARE
  v_batch_id text := 'condition_source_activation_20260602_v1';
  v_condition_run_prefix text := 'condition_layer_20260602_source_20260602';
  v_outbox_refs bigint;
  v_inbox_refs bigint;
  v_checkpoint_refs bigint;
  v_n2_refs bigint;
  v_n3_refs bigint;
  v_n4_refs bigint;
  v_n5_refs bigint;
  v_n6_refs bigint;
  missing_previous_batch_count integer;
BEGIN
  SELECT count(*) INTO v_outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%stock_daily_basic_20260602_v1%'
     OR payload_json::text LIKE '%stock_financial_20260602_v1%'
     OR payload_json::text LIKE '%index_membership_20260602_v1%'
     OR payload_json::text LIKE '%board_membership_20260602_v1%';

  SELECT count(*) INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%stock_daily_basic_20260602_v1%'
     OR raw_json::text LIKE '%stock_daily_basic_20260602_v1%'
     OR payload_json::text LIKE '%stock_financial_20260602_v1%'
     OR raw_json::text LIKE '%stock_financial_20260602_v1%'
     OR payload_json::text LIKE '%index_membership_20260602_v1%'
     OR raw_json::text LIKE '%index_membership_20260602_v1%'
     OR payload_json::text LIKE '%board_membership_20260602_v1%'
     OR raw_json::text LIKE '%board_membership_20260602_v1%';

  SELECT count(*) INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_batch_id || '%'
     OR checkpoint_payload::text LIKE '%stock_daily_basic_20260602_v1%'
     OR checkpoint_payload::text LIKE '%stock_financial_20260602_v1%'
     OR checkpoint_payload::text LIKE '%index_membership_20260602_v1%'
     OR checkpoint_payload::text LIKE '%board_membership_20260602_v1%';

  SELECT count(*) INTO v_n2_refs
  FROM common_condition_run
  WHERE source_trade_date = '20260602'
     OR source_versions::text LIKE '%' || v_batch_id || '%'
     OR source_versions::text LIKE '%stock_daily_basic_20260602_v1%'
     OR source_versions::text LIKE '%stock_financial_20260602_v1%'
     OR source_versions::text LIKE '%index_membership_20260602_v1%'
     OR source_versions::text LIKE '%board_membership_20260602_v1%'
     OR run_id LIKE v_condition_run_prefix || '%';

  SELECT count(*) INTO v_n3_refs
  FROM common_market_data_run
  WHERE source_condition_run_id LIKE v_condition_run_prefix || '%'
     OR raw_json::text LIKE '%' || v_batch_id || '%';

  SELECT count(*) INTO v_n4_refs
  FROM common_trigger_run
  WHERE source_condition_run_id LIKE v_condition_run_prefix || '%'
     OR raw_json::text LIKE '%' || v_batch_id || '%';

  SELECT count(*) INTO v_n5_refs
  FROM common_action_run
  WHERE source_condition_run_id LIKE v_condition_run_prefix || '%'
     OR raw_json::text LIKE '%' || v_batch_id || '%';

  SELECT count(*) INTO v_n6_refs
  FROM user_projection_run
  WHERE source_action_run_id LIKE '%' || v_condition_run_prefix || '%'
     OR quality_summary_json::text LIKE '%' || v_batch_id || '%';

  SELECT COUNT(*)
  INTO missing_previous_batch_count
  FROM common_active_source_version a
  WHERE a.source_batch_id = v_batch_id
    AND (
      (a.data_domain = 'stock' AND a.data_type IN ('stock_daily_basic', 'stock_financial') AND a.scope_key = '20260602')
      OR (a.data_domain = 'index' AND a.data_type = 'index_membership' AND a.scope_key = 'TDX:20260602')
      OR (a.data_domain = 'board' AND a.data_type = 'board_membership' AND a.scope_key = 'TDX:20260602')
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

  IF v_outbox_refs <> 0
     OR v_inbox_refs <> 0
     OR v_checkpoint_refs <> 0
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0
     OR missing_previous_batch_count <> 0 THEN
    RAISE EXCEPTION
      'Refusing N1 condition source 20260602 rollback: outbox %, inbox %, checkpoint %, N2 %, N3 %, N4 %, N5 %, N6 %, missing_previous_batch %',
      v_outbox_refs,
      v_inbox_refs,
      v_checkpoint_refs,
      v_n2_refs,
      v_n3_refs,
      v_n4_refs,
      v_n5_refs,
      v_n6_refs,
      missing_previous_batch_count;
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
    activated_by = 'rollback:n1_condition_source_activation_20260602_v1'
WHERE a.source_batch_id = 'condition_source_activation_20260602_v1'
  AND a.previous_source_version IS NOT NULL
  AND (
    (a.data_domain = 'stock' AND a.data_type IN ('stock_daily_basic', 'stock_financial') AND a.scope_key = '20260602')
    OR (a.data_domain = 'index' AND a.data_type = 'index_membership' AND a.scope_key = 'TDX:20260602')
    OR (a.data_domain = 'board' AND a.data_type = 'board_membership' AND a.scope_key = 'TDX:20260602')
  );

DELETE FROM common_active_source_version
WHERE source_batch_id = 'condition_source_activation_20260602_v1'
  AND previous_source_version IS NULL
  AND (
    (data_domain = 'stock' AND data_type IN ('stock_daily_basic', 'stock_financial') AND scope_key = '20260602')
    OR (data_domain = 'index' AND data_type = 'index_membership' AND scope_key = 'TDX:20260602')
    OR (data_domain = 'board' AND data_type = 'board_membership' AND scope_key = 'TDX:20260602')
  );

DELETE FROM stock_daily_basic
WHERE trade_date = '20260602'
  AND source_batch_id = 'condition_source_activation_20260602_v1'
  AND source_version = 'stock_daily_basic_20260602_v1';

DELETE FROM stock_financial_metrics_fact
WHERE source_trade_date = '20260602'
  AND source_batch_id = 'condition_source_activation_20260602_v1'
  AND source_version = 'stock_financial_20260602_v1';

DELETE FROM index_membership_fact
WHERE trade_date = '20260602'
  AND source_batch_id = 'condition_source_activation_20260602_v1'
  AND source_version = 'index_membership_20260602_v1';

DELETE FROM board_membership_fact
WHERE trade_date = '20260602'
  AND source_batch_id = 'condition_source_activation_20260602_v1'
  AND source_version = 'board_membership_20260602_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'condition_source_activation_20260602_v1'
   OR source_version IN (
     'condition_source_activation_20260602_v1',
     'stock_daily_basic_20260602_v1',
     'stock_financial_20260602_v1',
     'index_membership_20260602_v1',
     'board_membership_20260602_v1'
   );

DELETE FROM common_ingest_batch
WHERE batch_id = 'condition_source_activation_20260602_v1'
   OR source_version = 'condition_source_activation_20260602_v1';

COMMIT;
