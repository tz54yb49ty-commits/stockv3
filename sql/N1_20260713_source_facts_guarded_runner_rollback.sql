-- N1 20260713 source facts guarded runner rollback.
-- Scope:
--   official_daily_ingest_20260713_v1
--   condition_source_activation_20260713_v1
-- Forbidden: N2/N3/N4/N5/N6 DML, outbox/inbox/checkpoint DML, DROP, TRUNCATE, CASCADE.

BEGIN;

DO $$
DECLARE
  v_trade_date text := '20260713';
  v_official_batch_id text := 'official_daily_ingest_20260713_v1';
  v_condition_batch_id text := 'condition_source_activation_20260713_v1';
  v_ref_text text := 'official_daily_ingest_20260713_v1|condition_source_activation_20260713_v1|stock_daily_20260713_v1|index_daily_20260713_v1|board_daily_20260713_v1|stock_daily_basic_20260713_v1|stock_financial_20260713_v1|index_membership_20260713_v1|board_membership_20260713_v1';
  v_outbox_refs bigint;
  v_inbox_refs bigint;
  v_checkpoint_refs bigint;
  v_n2_refs bigint;
  v_n3_refs bigint;
  v_n4_refs bigint;
  v_n5_refs bigint;
  v_n6_refs bigint;
BEGIN
  SELECT count(*) INTO v_outbox_refs
  FROM common_event_outbox
  WHERE source_run_id IN (v_official_batch_id, v_condition_batch_id)
     OR payload_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id IN (v_official_batch_id, v_condition_batch_id)
     OR payload_json::text SIMILAR TO '%' || v_ref_text || '%'
     OR raw_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n2_refs
  FROM common_condition_run
  WHERE input_ingest_batch_id IN (v_official_batch_id, v_condition_batch_id)
     OR source_versions::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n3_refs
  FROM common_market_data_run
  WHERE raw_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n4_refs
  FROM common_trigger_run
  WHERE raw_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n5_refs
  FROM common_action_run
  WHERE raw_json::text SIMILAR TO '%' || v_ref_text || '%';

  SELECT count(*) INTO v_n6_refs
  FROM user_projection_run
  WHERE quality_summary_json::text SIMILAR TO '%' || v_ref_text || '%'
     OR source_action_run_id IN (v_official_batch_id, v_condition_batch_id);

  IF v_outbox_refs <> 0
     OR v_inbox_refs <> 0
     OR v_checkpoint_refs <> 0
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0 THEN
    RAISE EXCEPTION
      'Refusing N1 20260713 source facts rollback: outbox %, inbox %, checkpoint %, N2 %, N3 %, N4 %, N5 %, N6 %',
      v_outbox_refs, v_inbox_refs, v_checkpoint_refs, v_n2_refs, v_n3_refs, v_n4_refs, v_n5_refs, v_n6_refs;
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE source_batch_id = 'condition_source_activation_20260713_v1'
  AND source_version IN (
    'stock_daily_basic_20260713_v1',
    'stock_financial_20260713_v1',
    'index_membership_20260713_v1',
    'board_membership_20260713_v1'
  )
  AND (
    (data_domain = 'stock' AND data_type IN ('stock_daily_basic', 'stock_financial') AND scope_key = '20260713')
    OR (data_domain = 'index' AND data_type = 'index_membership' AND scope_key = 'TDX:20260713')
    OR (data_domain = 'board' AND data_type = 'board_membership' AND scope_key = 'TDX:20260713')
  );

DELETE FROM stock_daily_basic
WHERE trade_date = '20260713'
  AND source_batch_id = 'condition_source_activation_20260713_v1'
  AND source_version = 'stock_daily_basic_20260713_v1';

DELETE FROM stock_financial_metrics_fact
WHERE source_trade_date = '20260713'
  AND source_batch_id = 'condition_source_activation_20260713_v1'
  AND source_version = 'stock_financial_20260713_v1';

DELETE FROM index_membership_fact
WHERE trade_date = '20260713'
  AND source_batch_id = 'condition_source_activation_20260713_v1'
  AND source_version = 'index_membership_20260713_v1';

DELETE FROM board_membership_fact
WHERE trade_date = '20260713'
  AND source_batch_id = 'condition_source_activation_20260713_v1'
  AND source_version = 'board_membership_20260713_v1';

DELETE FROM common_active_source_version
WHERE scope_key = '20260713'
  AND source_batch_id = 'official_daily_ingest_20260713_v1'
  AND source_version IN (
    'stock_daily_20260713_v1',
    'index_daily_20260713_v1',
    'board_daily_20260713_v1'
  )
  AND data_type IN ('stock_daily', 'index_daily', 'board_daily');

DELETE FROM stock_daily_bar_fact
WHERE trade_date = '20260713'
  AND source_batch_id = 'official_daily_ingest_20260713_v1'
  AND source_version = 'stock_daily_20260713_v1';

DELETE FROM index_daily_bar_fact
WHERE trade_date = '20260713'
  AND source_batch_id = 'official_daily_ingest_20260713_v1'
  AND source_version = 'index_daily_20260713_v1';

DELETE FROM board_daily_bar_fact
WHERE trade_date = '20260713'
  AND source_batch_id = 'official_daily_ingest_20260713_v1'
  AND source_version = 'board_daily_20260713_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id IN (
    'official_daily_ingest_20260713_v1',
    'condition_source_activation_20260713_v1'
  )
   OR source_version IN (
     'official_daily_ingest_20260713_v1',
     'condition_source_activation_20260713_v1',
     'stock_daily_20260713_v1',
     'index_daily_20260713_v1',
     'board_daily_20260713_v1',
     'stock_daily_basic_20260713_v1',
     'stock_financial_20260713_v1',
     'index_membership_20260713_v1',
     'board_membership_20260713_v1'
   );

DELETE FROM common_ingest_batch
WHERE batch_id IN (
    'official_daily_ingest_20260713_v1',
    'condition_source_activation_20260713_v1'
  )
   OR source_version IN (
     'official_daily_ingest_20260713_v1',
     'condition_source_activation_20260713_v1',
     'stock_daily_20260713_v1',
     'index_daily_20260713_v1',
     'board_daily_20260713_v1',
     'stock_daily_basic_20260713_v1',
     'stock_financial_20260713_v1',
     'index_membership_20260713_v1',
     'board_membership_20260713_v1'
   );

COMMIT;
