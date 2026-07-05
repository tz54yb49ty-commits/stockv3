-- N1 condition source activation 20260605 rollback draft.
-- Scope: condition_source_activation_20260605_v1.
-- This rollback does not touch official daily daily-bar facts, N2/N3/N4/N5/N6,
-- outbox/inbox/checkpoint, workers, old system, or trading state.

BEGIN;

DO $$
DECLARE
  v_batch_id text := 'condition_source_activation_20260605_v1';
  v_trade_date text := '20260605';
  v_for_trade_date text := '20260608';
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
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%stock_daily_basic_20260605_v1%'
     OR payload_json::text LIKE '%stock_financial_20260605_v1%'
     OR payload_json::text LIKE '%index_membership_20260605_v1%'
     OR payload_json::text LIKE '%board_membership_20260605_v1%';

  SELECT count(*) INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%stock_daily_basic_20260605_v1%'
     OR raw_json::text LIKE '%stock_daily_basic_20260605_v1%'
     OR payload_json::text LIKE '%stock_financial_20260605_v1%'
     OR raw_json::text LIKE '%stock_financial_20260605_v1%'
     OR payload_json::text LIKE '%index_membership_20260605_v1%'
     OR raw_json::text LIKE '%index_membership_20260605_v1%'
     OR payload_json::text LIKE '%board_membership_20260605_v1%'
     OR raw_json::text LIKE '%board_membership_20260605_v1%';

  SELECT count(*) INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_batch_id || '%'
     OR checkpoint_payload::text LIKE '%stock_daily_basic_20260605_v1%'
     OR checkpoint_payload::text LIKE '%stock_financial_20260605_v1%'
     OR checkpoint_payload::text LIKE '%index_membership_20260605_v1%'
     OR checkpoint_payload::text LIKE '%board_membership_20260605_v1%';

  SELECT count(*) INTO v_n2_refs
  FROM common_condition_run
  WHERE source_trade_date = v_trade_date
     OR for_trade_date = v_for_trade_date
     OR source_versions::text LIKE '%' || v_batch_id || '%'
     OR source_versions::text LIKE '%stock_daily_basic_20260605_v1%'
     OR source_versions::text LIKE '%stock_financial_20260605_v1%'
     OR source_versions::text LIKE '%index_membership_20260605_v1%'
     OR source_versions::text LIKE '%board_membership_20260605_v1%';

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
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0 THEN
    RAISE EXCEPTION
      'Refusing condition source 20260605 rollback: outbox %, inbox %, checkpoint %, N2 %, N3 %, N4 %, N5 %, N6 %',
      v_outbox_refs, v_inbox_refs, v_checkpoint_refs, v_n2_refs, v_n3_refs, v_n4_refs, v_n5_refs, v_n6_refs;
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE source_batch_id = 'condition_source_activation_20260605_v1'
  AND (
    (data_domain = 'stock' AND data_type IN ('stock_daily_basic', 'stock_financial') AND scope_key = '20260605')
    OR (data_domain = 'index' AND data_type = 'index_membership' AND scope_key = 'TDX:20260605')
    OR (data_domain = 'board' AND data_type = 'board_membership' AND scope_key = 'TDX:20260605')
  );

DELETE FROM stock_daily_basic
WHERE trade_date = '20260605'
  AND source_batch_id = 'condition_source_activation_20260605_v1'
  AND source_version = 'stock_daily_basic_20260605_v1';

DELETE FROM stock_financial_metrics_fact
WHERE source_trade_date = '20260605'
  AND source_batch_id = 'condition_source_activation_20260605_v1'
  AND source_version = 'stock_financial_20260605_v1';

DELETE FROM index_membership_fact
WHERE trade_date = '20260605'
  AND source_batch_id = 'condition_source_activation_20260605_v1'
  AND source_version = 'index_membership_20260605_v1';

DELETE FROM board_membership_fact
WHERE trade_date = '20260605'
  AND source_batch_id = 'condition_source_activation_20260605_v1'
  AND source_version = 'board_membership_20260605_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'condition_source_activation_20260605_v1'
   OR source_version IN (
     'condition_source_activation_20260605_v1',
     'stock_daily_basic_20260605_v1',
     'stock_financial_20260605_v1',
     'index_membership_20260605_v1',
     'board_membership_20260605_v1'
   );

DELETE FROM common_ingest_batch
WHERE batch_id = 'condition_source_activation_20260605_v1'
   OR source_version = 'condition_source_activation_20260605_v1';

COMMIT;

