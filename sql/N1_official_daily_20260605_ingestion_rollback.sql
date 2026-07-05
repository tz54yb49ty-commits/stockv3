-- N1 official daily 20260605 rollback draft.
-- Scope: official_daily_ingest_20260605_v1.
-- Safe only before condition source, N2, N3, N4, N5, or N6 downstream refs.

BEGIN;

DO $$
DECLARE
  v_batch_id text := 'official_daily_ingest_20260605_v1';
  v_stock_source_version text := 'stock_daily_20260605_v1';
  v_index_source_version text := 'index_daily_20260605_v1';
  v_board_source_version text := 'board_daily_20260605_v1';
  v_trade_date text := '20260605';
  v_for_trade_date text := '20260608';
  v_condition_batch_id text := 'condition_source_activation_20260605_v1';
  v_outbox_refs bigint;
  v_inbox_refs bigint;
  v_checkpoint_refs bigint;
  v_condition_source_refs bigint;
  v_n2_refs bigint;
  v_n3_refs bigint;
  v_n4_refs bigint;
  v_n5_refs bigint;
  v_n6_refs bigint;
BEGIN
  SELECT count(*) INTO v_outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%' || v_stock_source_version || '%'
     OR payload_json::text LIKE '%' || v_index_source_version || '%'
     OR payload_json::text LIKE '%' || v_board_source_version || '%';

  SELECT count(*) INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%' || v_stock_source_version || '%'
     OR raw_json::text LIKE '%' || v_stock_source_version || '%'
     OR payload_json::text LIKE '%' || v_index_source_version || '%'
     OR raw_json::text LIKE '%' || v_index_source_version || '%'
     OR payload_json::text LIKE '%' || v_board_source_version || '%'
     OR raw_json::text LIKE '%' || v_board_source_version || '%';

  SELECT count(*) INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_batch_id || '%'
     OR checkpoint_payload::text LIKE '%' || v_stock_source_version || '%'
     OR checkpoint_payload::text LIKE '%' || v_index_source_version || '%'
     OR checkpoint_payload::text LIKE '%' || v_board_source_version || '%';

  SELECT
    (SELECT count(*) FROM common_ingest_batch WHERE batch_id = v_condition_batch_id)
    + (SELECT count(*) FROM common_active_source_version WHERE source_batch_id = v_condition_batch_id)
    + (SELECT count(*) FROM stock_daily_basic WHERE source_batch_id = v_condition_batch_id)
    + (SELECT count(*) FROM stock_financial_metrics_fact WHERE source_batch_id = v_condition_batch_id)
    + (SELECT count(*) FROM index_membership_fact WHERE source_batch_id = v_condition_batch_id)
    + (SELECT count(*) FROM board_membership_fact WHERE source_batch_id = v_condition_batch_id)
  INTO v_condition_source_refs;

  SELECT count(*) INTO v_n2_refs
  FROM common_condition_run
  WHERE source_trade_date = v_trade_date
     OR for_trade_date = v_for_trade_date
     OR input_ingest_batch_id = v_batch_id
     OR source_versions::text LIKE '%' || v_batch_id || '%'
     OR source_versions::text LIKE '%' || v_stock_source_version || '%'
     OR source_versions::text LIKE '%' || v_index_source_version || '%'
     OR source_versions::text LIKE '%' || v_board_source_version || '%';

  SELECT count(*) INTO v_n3_refs
  FROM common_market_data_run
  WHERE source_trade_date = v_trade_date
     OR for_trade_date = v_for_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%';

  SELECT count(*) INTO v_n4_refs
  FROM common_trigger_run
  WHERE source_trade_date = v_trade_date
     OR for_trade_date = v_for_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%';

  SELECT count(*) INTO v_n5_refs
  FROM common_action_run
  WHERE for_trade_date = v_for_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%';

  SELECT count(*) INTO v_n6_refs
  FROM user_projection_run
  WHERE quality_summary_json::text LIKE '%' || v_batch_id || '%'
     OR source_action_run_id LIKE '%' || v_for_trade_date || '%';

  IF v_outbox_refs <> 0
     OR v_inbox_refs <> 0
     OR v_checkpoint_refs <> 0
     OR v_condition_source_refs <> 0
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0 THEN
    RAISE EXCEPTION
      'Refusing official daily 20260605 rollback: outbox %, inbox %, checkpoint %, condition_source %, N2 %, N3 %, N4 %, N5 %, N6 %',
      v_outbox_refs, v_inbox_refs, v_checkpoint_refs, v_condition_source_refs, v_n2_refs, v_n3_refs, v_n4_refs, v_n5_refs, v_n6_refs;
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE scope_key = '20260605'
  AND source_batch_id = 'official_daily_ingest_20260605_v1'
  AND source_version IN (
    'stock_daily_20260605_v1',
    'index_daily_20260605_v1',
    'board_daily_20260605_v1'
  )
  AND data_type IN ('stock_daily', 'index_daily', 'board_daily');

DELETE FROM stock_daily_bar_fact
WHERE trade_date = '20260605'
  AND source_batch_id = 'official_daily_ingest_20260605_v1'
  AND source_version = 'stock_daily_20260605_v1';

DELETE FROM index_daily_bar_fact
WHERE trade_date = '20260605'
  AND source_batch_id = 'official_daily_ingest_20260605_v1'
  AND source_version = 'index_daily_20260605_v1';

DELETE FROM board_daily_bar_fact
WHERE trade_date = '20260605'
  AND source_batch_id = 'official_daily_ingest_20260605_v1'
  AND source_version = 'board_daily_20260605_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'official_daily_ingest_20260605_v1'
   OR source_version IN (
     'official_daily_ingest_20260605_v1',
     'stock_daily_20260605_v1',
     'index_daily_20260605_v1',
     'board_daily_20260605_v1'
   );

DELETE FROM common_ingest_batch
WHERE batch_id = 'official_daily_ingest_20260605_v1'
   OR source_version IN (
     'official_daily_ingest_20260605_v1',
     'stock_daily_20260605_v1',
     'index_daily_20260605_v1',
     'board_daily_20260605_v1'
   );

COMMIT;

