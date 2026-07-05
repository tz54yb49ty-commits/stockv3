-- N1 20260612 trade calendar repair rollback draft.
-- Scope:
--   n1_trade_calendar_repair_20260612_v1 / SSE:20260612
-- This rollback does not touch N1 source facts, condition source, N2/N3/N4/N5/N6 facts,
-- outbox/inbox/checkpoint, workers, old system, delivery, sim, positions, or trading state.

BEGIN;

DO $$
DECLARE
  v_batch_id text := 'n1_trade_calendar_repair_20260612_v1';
  v_source_version text := 'n1_trade_calendar_repair_20260612_v1';
  v_scope_key text := 'SSE:20260612';
  v_trade_date text := '20260612';
  v_outbox_refs bigint;
  v_inbox_refs bigint;
  v_checkpoint_refs bigint;
  v_n1_fact_refs bigint;
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
     OR payload_json::text LIKE '%' || v_source_version || '%'
     OR payload_json::text LIKE '%' || v_scope_key || '%'
     OR trade_date::text = v_trade_date;

  SELECT count(*) INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%'
     OR payload_json::text LIKE '%' || v_scope_key || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%';

  SELECT count(*) INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_batch_id || '%'
     OR checkpoint_payload::text LIKE '%' || v_source_version || '%'
     OR checkpoint_payload::text LIKE '%' || v_scope_key || '%';

  SELECT
      (SELECT count(*) FROM stock_daily_bar_fact WHERE trade_date::text = v_trade_date)
    + (SELECT count(*) FROM index_daily_bar_fact WHERE trade_date::text = v_trade_date)
    + (SELECT count(*) FROM board_daily_bar_fact WHERE trade_date::text = v_trade_date)
    + (SELECT count(*) FROM stock_daily_basic WHERE trade_date::text = v_trade_date)
    + (SELECT count(*) FROM stock_financial_metrics_fact WHERE source_trade_date::text = v_trade_date)
    + (SELECT count(*) FROM index_membership_fact WHERE trade_date::text = v_trade_date)
    + (SELECT count(*) FROM board_membership_fact WHERE trade_date::text = v_trade_date)
  INTO v_n1_fact_refs;

  SELECT count(*) INTO v_n2_refs
  FROM common_condition_run
  WHERE for_trade_date::text = v_trade_date
     OR source_trade_date::text = v_trade_date
     OR source_versions::text LIKE '%' || v_batch_id || '%'
     OR source_versions::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%';

  SELECT count(*) INTO v_n3_refs
  FROM common_market_data_run
  WHERE for_trade_date::text = v_trade_date
     OR source_trade_date::text = v_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%';

  SELECT count(*) INTO v_n4_refs
  FROM common_trigger_run
  WHERE for_trade_date::text = v_trade_date
     OR source_trade_date::text = v_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%';

  SELECT count(*) INTO v_n5_refs
  FROM common_action_run
  WHERE for_trade_date::text = v_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_scope_key || '%';

  SELECT count(*) INTO v_n6_refs
  FROM user_projection_run
  WHERE quality_summary_json::text LIKE '%' || v_batch_id || '%'
     OR quality_summary_json::text LIKE '%' || v_source_version || '%'
     OR quality_summary_json::text LIKE '%' || v_scope_key || '%'
     OR source_display_condition_run_id LIKE '%' || v_trade_date || '%'
     OR source_action_run_id LIKE '%' || v_trade_date || '%';

  IF v_outbox_refs <> 0
     OR v_inbox_refs <> 0
     OR v_checkpoint_refs <> 0
     OR v_n1_fact_refs <> 0
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0 THEN
    RAISE EXCEPTION
      'Refusing 20260612 calendar repair rollback: outbox %, inbox %, checkpoint %, N1 facts %, N2 %, N3 %, N4 %, N5 %, N6 %',
      v_outbox_refs, v_inbox_refs, v_checkpoint_refs, v_n1_fact_refs, v_n2_refs, v_n3_refs, v_n4_refs, v_n5_refs, v_n6_refs;
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE data_domain = 'common'
  AND data_type = 'trade_calendar'
  AND scope_key = 'SSE:20260612'
  AND source_batch_id = 'n1_trade_calendar_repair_20260612_v1'
  AND source_version = 'n1_trade_calendar_repair_20260612_v1';

DELETE FROM common_trade_calendar
WHERE trade_date::text = '20260612'
  AND source_batch_id = 'n1_trade_calendar_repair_20260612_v1'
  AND source_version = 'n1_trade_calendar_repair_20260612_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'n1_trade_calendar_repair_20260612_v1'
  AND source_version = 'n1_trade_calendar_repair_20260612_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'n1_trade_calendar_repair_20260612_v1'
  AND source_version = 'n1_trade_calendar_repair_20260612_v1'
  AND data_domain = 'common'
  AND data_type = 'trade_calendar';

COMMIT;
