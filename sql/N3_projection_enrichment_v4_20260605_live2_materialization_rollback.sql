-- N3 projection enrichment v4 20260605 live2 materialization rollback.
-- Boundary: rollback only rows scoped to the target N3 run_id.
-- Hard-fail before row removal if event infra or downstream N4/N5/N6 refs exist.
\set ON_ERROR_STOP on
BEGIN;

SELECT set_config('app.n3_target_run_id', 'projection_enrichment_v4_20260605_live2__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1', false);

DO $$
DECLARE
  target_run_id TEXT := current_setting('app.n3_target_run_id');
  outbox_refs BIGINT := 0;
  inbox_refs BIGINT := 0;
  checkpoint_refs BIGINT := 0;
  n4_refs BIGINT := 0;
  n5_refs BIGINT := 0;
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

  IF to_regclass('common_trigger_match') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_trigger_match WHERE to_jsonb(common_trigger_match)::TEXT LIKE $1'
      INTO n4_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('common_trigger_state') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM common_trigger_state WHERE to_jsonb(common_trigger_state)::TEXT LIKE $2'
      INTO n4_refs USING n4_refs, '%' || target_run_id || '%';
  END IF;

  IF to_regclass('common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE to_jsonb(common_action_event)::TEXT LIKE $1'
      INTO n5_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('common_action_confirmation') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM common_action_confirmation WHERE to_jsonb(common_action_confirmation)::TEXT LIKE $2'
      INTO n5_refs USING n5_refs, '%' || target_run_id || '%';
  END IF;

  IF to_regclass('user_projection_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_projection_run WHERE to_jsonb(user_projection_run)::TEXT LIKE $1'
      INTO n6_refs USING '%' || target_run_id || '%';
  END IF;
  IF to_regclass('user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT $1 + count(*) FROM user_signal_projection WHERE to_jsonb(user_signal_projection)::TEXT LIKE $2'
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

  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0
     OR n4_refs <> 0 OR n5_refs <> 0 OR n6_refs <> 0 OR downstream_flags <> 0 THEN
    RAISE EXCEPTION 'rollback blocked for %, refs outbox=% inbox=% checkpoint=% n4=% n5=% n6=% downstream_or_worker=%',
      target_run_id, outbox_refs, inbox_refs, checkpoint_refs, n4_refs, n5_refs, n6_refs, downstream_flags;
  END IF;
END $$;

DELETE FROM common_market_data_quality_item
WHERE run_id = current_setting('app.n3_target_run_id')
   OR details::TEXT LIKE '%' || current_setting('app.n3_target_run_id') || '%';

DELETE FROM stock_projection_enrichment_v4_metric WHERE projection_run_id = target_run_id;
DELETE FROM index_projection_enrichment_v4_metric WHERE projection_run_id = target_run_id;
DELETE FROM board_projection_enrichment_v4_metric WHERE projection_run_id = target_run_id;

DELETE FROM common_market_data_run
WHERE run_id = current_setting('app.n3_target_run_id');

COMMIT;
