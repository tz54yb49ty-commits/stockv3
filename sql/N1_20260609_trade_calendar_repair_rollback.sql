-- N1 trade calendar 20260609 repair rollback draft.
-- Scope: trade_calendar_20260609_repair_v1.
-- This rollback does not touch daily facts, condition source, N2/N3/N4/N5/N6 facts,
-- outbox/inbox/checkpoint, workers, old system, delivery, sim, positions, or trading state.

BEGIN;

DO $$
DECLARE
  v_batch_id text := 'trade_calendar_20260609_repair_v1';
  v_source_version text := 'trade_calendar_20260609_repair_v1';
  v_scope_key text := 'SSE:20260609';
  v_trade_date text := '20260609';
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
     OR payload_json::text LIKE '%' || v_source_version || '%'
     OR payload_json::text LIKE '%' || v_scope_key || '%'
     OR payload_json::text LIKE '%' || v_trade_date || '%';

  SELECT count(*) INTO v_inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = v_batch_id
     OR payload_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR payload_json::text LIKE '%' || v_source_version || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%'
     OR payload_json::text LIKE '%' || v_trade_date || '%'
     OR raw_json::text LIKE '%' || v_trade_date || '%';

  SELECT count(*) INTO v_checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || v_batch_id || '%'
     OR checkpoint_payload::text LIKE '%' || v_source_version || '%'
     OR checkpoint_payload::text LIKE '%' || v_trade_date || '%';

  SELECT count(*) INTO v_n2_refs
  FROM common_condition_run
  WHERE for_trade_date = v_trade_date
     OR source_versions::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%';

  SELECT count(*) INTO v_n3_refs
  FROM common_market_data_run
  WHERE for_trade_date = v_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%';

  SELECT count(*) INTO v_n4_refs
  FROM common_trigger_run
  WHERE for_trade_date = v_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%';

  SELECT count(*) INTO v_n5_refs
  FROM common_action_run
  WHERE for_trade_date = v_trade_date
     OR raw_json::text LIKE '%' || v_batch_id || '%'
     OR raw_json::text LIKE '%' || v_source_version || '%';

  SELECT count(*) INTO v_n6_refs
  FROM user_projection_run
  WHERE quality_summary_json::text LIKE '%' || v_batch_id || '%'
     OR quality_summary_json::text LIKE '%' || v_source_version || '%'
     OR source_display_condition_run_id LIKE '%' || v_trade_date || '%'
     OR source_action_run_id LIKE '%' || v_trade_date || '%';

  IF v_outbox_refs <> 0
     OR v_inbox_refs <> 0
     OR v_checkpoint_refs <> 0
     OR v_n2_refs <> 0
     OR v_n3_refs <> 0
     OR v_n4_refs <> 0
     OR v_n5_refs <> 0
     OR v_n6_refs <> 0 THEN
    RAISE EXCEPTION
      'Refusing 20260609 calendar repair rollback: outbox %, inbox %, checkpoint %, N2 %, N3 %, N4 %, N5 %, N6 %',
      v_outbox_refs, v_inbox_refs, v_checkpoint_refs, v_n2_refs, v_n3_refs, v_n4_refs, v_n5_refs, v_n6_refs;
  END IF;
END $$;

DELETE FROM common_active_source_version
WHERE data_domain = 'common'
  AND data_type = 'trade_calendar'
  AND scope_key = 'SSE:20260609'
  AND source_batch_id = 'trade_calendar_20260609_repair_v1'
  AND source_version = 'trade_calendar_20260609_repair_v1';

DELETE FROM common_trade_calendar
WHERE trade_date = '20260609'
  AND source_batch_id = 'trade_calendar_20260609_repair_v1'
  AND source_version = 'trade_calendar_20260609_repair_v1';

DELETE FROM common_quality_gate_result
WHERE source_batch_id = 'trade_calendar_20260609_repair_v1'
  AND source_version = 'trade_calendar_20260609_repair_v1';

DELETE FROM common_ingest_batch
WHERE batch_id = 'trade_calendar_20260609_repair_v1'
  AND source_version = 'trade_calendar_20260609_repair_v1'
  AND data_domain = 'common'
  AND data_type = 'trade_calendar';

COMMIT;
