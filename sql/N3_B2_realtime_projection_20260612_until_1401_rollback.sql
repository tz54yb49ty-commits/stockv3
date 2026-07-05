-- N3-B2 realtime projection rollback.
-- Boundary: rollback only projection facts/quality/run for the listed projection_run_id.
-- Hard-fail before row removal if event infra or downstream N4/N5/N6 refs exist.
\set ON_ERROR_STOP on

BEGIN;

SELECT set_config('app.n3_b2_projection_run_id', 'realtime_projection_metric_20260612_until_1401__realtime_daily_snapshot_20260612_until_1401__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.n3_b2_projection_run_id');
  outbox_refs BIGINT := 0;
  inbox_refs BIGINT := 0;
  checkpoint_refs BIGINT := 0;
  trigger_state_refs BIGINT := 0;
  trigger_match_refs BIGINT := 0;
  action_refs BIGINT := 0;
  n6_refs BIGINT := 0;
  downstream_flags BIGINT := 0;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = target_run_id OR payload_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = target_run_id
     OR payload_json::TEXT LIKE '%' || target_run_id || '%'
     OR raw_json::TEXT LIKE '%' || target_run_id || '%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || target_run_id || '%'
     OR last_event_id LIKE '%' || target_run_id || '%';

  IF to_regclass('common_trigger_state') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_trigger_state WHERE to_jsonb(common_trigger_state)::TEXT LIKE $1'
      INTO trigger_state_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('common_trigger_match') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_trigger_match WHERE to_jsonb(common_trigger_match)::TEXT LIKE $1'
      INTO trigger_match_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE to_jsonb(common_action_event)::TEXT LIKE $1'
      INTO action_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_projection_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_projection_run WHERE to_jsonb(user_projection_run)::TEXT LIKE $1'
      INTO n6_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_signal_projection WHERE to_jsonb(user_signal_projection)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_signal_card WHERE to_jsonb(user_signal_card)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_notification_queue') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_notification_queue WHERE to_jsonb(user_notification_queue)::TEXT LIKE $2'
      INTO n6_refs USING n6_refs, '%' || target_run_id || '%';
  END IF;

  SELECT count(*) INTO downstream_flags
  FROM common_market_data_run
  WHERE run_id = target_run_id
    AND (coalesce(downstream_layers_touched, false) OR coalesce(worker_started, false));

  IF outbox_refs <> 0
     OR inbox_refs <> 0
     OR checkpoint_refs <> 0
     OR trigger_state_refs <> 0
     OR trigger_match_refs <> 0
     OR action_refs <> 0
     OR n6_refs <> 0
     OR downstream_flags <> 0 THEN
    RAISE EXCEPTION 'N3-B2 rollback blocked for %, outbox=%, inbox=%, checkpoint=%, trigger_state=%, trigger_match=%, action=%, n6=%, downstream_or_worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, trigger_state_refs, trigger_match_refs, action_refs, n6_refs, downstream_flags;
  END IF;
END $$;

DELETE FROM common_market_data_quality_item
WHERE run_id = current_setting('app.n3_b2_projection_run_id')
   OR details::TEXT LIKE '%' || current_setting('app.n3_b2_projection_run_id') || '%';

DELETE FROM stock_realtime_projection_metric
WHERE projection_run_id = current_setting('app.n3_b2_projection_run_id');

DELETE FROM index_realtime_projection_metric
WHERE projection_run_id = current_setting('app.n3_b2_projection_run_id');

DELETE FROM board_realtime_projection_metric
WHERE projection_run_id = current_setting('app.n3_b2_projection_run_id');

DELETE FROM common_market_data_run
WHERE run_id = current_setting('app.n3_b2_projection_run_id')
  AND coalesce(downstream_layers_touched, false) = false
  AND coalesce(worker_started, false) = false;

COMMIT;
