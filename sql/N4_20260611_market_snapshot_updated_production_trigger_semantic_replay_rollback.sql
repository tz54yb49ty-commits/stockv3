-- N4 20260611 MarketSnapshotUpdated production trigger semantic replay rollback.
-- Scope: replay_run_id=n4_production_semantic_replay_20260611_market_snapshot_updated_v1
-- Consumer: n4_trigger_production_semantic_replay_20260611_market_snapshot_updated_v1
-- This SQL is guarded by default. Do not remove the hard-fail except inside an approved runtime_control rollback execute gate.
-- It must not touch N3 source facts/outbox status, bounded polling consumers, fixture smoke rows, N5/N6/user/sim/virtual/downstream rows, or old system data.

BEGIN;

DO $$
DECLARE
  target_run_id text := 'n4_production_semantic_replay_20260611_market_snapshot_updated_v1';
  target_consumer_name text := 'n4_trigger_production_semantic_replay_20260611_market_snapshot_updated_v1';
  v_count bigint := 0;
  v_downstream_refs bigint := 0;
  v_table text;
BEGIN
  RAISE EXCEPTION 'rollback blocked by default: remove this hard-fail only inside an approved runtime_control rollback execute gate for %', target_run_id;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = target_run_id
    AND status IN ('delivered', 'delivering');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: delivered/delivering N4 outbox exists for % (% rows)', target_run_id, v_count;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'common_action_run',
    'common_action_event',
    'stock_action_fact',
    'index_action_fact',
    'board_action_fact',
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_notification_queue',
    'user_sim_projection',
    'user_virtual_position',
    'virtual_order',
    'virtual_trade',
    'sim_order',
    'sim_trade',
    'stock_position_fact',
    'common_position_event',
    'voice_delivery_queue',
    'mobile_push_queue'
  ] LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*)::bigint FROM %I WHERE to_jsonb(%I)::text LIKE $1', v_table, v_table)
      INTO v_count
      USING '%' || target_run_id || '%';
      v_downstream_refs := v_downstream_refs + COALESCE(v_count, 0);
    END IF;
  END LOOP;

  IF v_downstream_refs <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N5/N6/user/sim/virtual/downstream refs exist for % (% rows)', target_run_id, v_downstream_refs;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM common_trigger_run
    WHERE run_id = target_run_id
      AND (COALESCE(worker_started, false) OR raw_json::text LIKE '%"downstream_layers_touched": true%')
  ) THEN
    RAISE EXCEPTION 'rollback blocked: worker/downstream flag set for %', target_run_id;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM common_event_outbox
    WHERE source_layer = 'N3_market_data'
      AND source_run_id = 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
      AND event_type = 'MarketSnapshotUpdated'
      AND status <> 'pending'
  ) THEN
    RAISE EXCEPTION 'rollback blocked: upstream N3 source outbox status is not fully pending; review before N4 replay rollback';
  END IF;

  DELETE FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = target_run_id
    AND status NOT IN ('delivered', 'delivering');

  DELETE FROM common_trigger_match
  WHERE run_id = target_run_id;

  DELETE FROM common_trigger_state
  WHERE run_id = target_run_id;

  DELETE FROM common_trigger_quality_item
  WHERE run_id = target_run_id;

  DELETE FROM common_event_consumer_checkpoint
  WHERE consumer_name = target_consumer_name
    AND source_layer = 'N3_market_data'
    AND checkpoint_payload ->> 'execute_run_id' = target_run_id;

  DELETE FROM common_event_inbox
  WHERE consumer_name = target_consumer_name
    AND raw_json ->> 'execute_run_id' = target_run_id;

  DELETE FROM common_trigger_run
  WHERE run_id = target_run_id;
END $$;

COMMIT;
