-- V3 20260616 realtime virtual metric writer rollback.
-- Scope: delete only metric rows/run/quality for action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1.
-- Default hard-fail; only runtime_control may review removal of the guard.
\set ON_ERROR_STOP on
\set target_run_id 'action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1'

DO $$
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260616_metric_writer_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'V3 20260616 metric writer rollback hard-fail: set ashare_v3.allow_v3_20260616_metric_writer_rollback=true after final gate review';
  END IF;
END $$;

DO $$
DECLARE
  target_run_id TEXT := 'action_confirmation_projection_metric_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1';
  outbox_refs BIGINT := 0;
  inbox_refs BIGINT := 0;
  checkpoint_refs BIGINT := 0;
  n4_refs BIGINT := 0;
  n5_refs BIGINT := 0;
  n6_refs BIGINT := 0;
  downstream_refs BIGINT := 0;
  worker_refs BIGINT := 0;
BEGIN
  SELECT count(*) INTO outbox_refs FROM common_event_outbox WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';
  SELECT count(*) INTO inbox_refs FROM common_event_inbox WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%' OR raw_json::TEXT LIKE '%' || target_run_id || '%';
  SELECT count(*) INTO checkpoint_refs FROM common_event_consumer_checkpoint WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%' OR last_event_id LIKE '%' || target_run_id || '%';
  IF to_regclass('common_trigger_match') IS NOT NULL THEN EXECUTE 'SELECT count(*) FROM common_trigger_match WHERE to_jsonb(common_trigger_match)::TEXT LIKE $1' INTO n4_refs USING '%' || target_run_id || '%'; END IF;
  IF to_regclass('common_trigger_state') IS NOT NULL THEN EXECUTE 'SELECT $1 + count(*) FROM common_trigger_state WHERE to_jsonb(common_trigger_state)::TEXT LIKE $2' INTO n4_refs USING n4_refs, '%' || target_run_id || '%'; END IF;
  IF to_regclass('common_action_event') IS NOT NULL THEN EXECUTE 'SELECT count(*) FROM common_action_event WHERE to_jsonb(common_action_event)::TEXT LIKE $1' INTO n5_refs USING '%' || target_run_id || '%'; END IF;
  IF to_regclass('user_signal_projection') IS NOT NULL THEN EXECUTE 'SELECT count(*) FROM user_signal_projection WHERE to_jsonb(user_signal_projection)::TEXT LIKE $1' INTO n6_refs USING '%' || target_run_id || '%'; END IF;
  IF to_regclass('user_signal_card') IS NOT NULL THEN EXECUTE 'SELECT $1 + count(*) FROM user_signal_card WHERE to_jsonb(user_signal_card)::TEXT LIKE $2' INTO n6_refs USING n6_refs, '%' || target_run_id || '%'; END IF;
  SELECT count(*) INTO downstream_refs FROM common_market_data_run WHERE run_id = target_run_id AND downstream_layers_touched = true;
  SELECT count(*) INTO worker_refs FROM common_market_data_run WHERE run_id = target_run_id AND worker_started = true;
  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0 OR n4_refs <> 0 OR n5_refs <> 0 OR n6_refs <> 0 OR downstream_refs <> 0 OR worker_refs <> 0 THEN
    RAISE EXCEPTION 'V3 metric rollback blocked for %, outbox=%, inbox=%, checkpoint=%, n4=%, n5=%, n6=%, downstream=%, worker=%', target_run_id, outbox_refs, inbox_refs, checkpoint_refs, n4_refs, n5_refs, n6_refs, downstream_refs, worker_refs;
  END IF;
END $$;

BEGIN;
DELETE FROM stock_action_confirmation_projection_metric WHERE projection_run_id = :'target_run_id';
DELETE FROM index_action_confirmation_projection_metric WHERE projection_run_id = :'target_run_id';
DELETE FROM board_action_confirmation_projection_metric WHERE projection_run_id = :'target_run_id';
DELETE FROM common_market_data_quality_item WHERE run_id = :'target_run_id';
DELETE FROM common_market_data_run WHERE run_id = :'target_run_id' AND downstream_layers_touched = false AND worker_started = false;
COMMIT;
