-- N3 20260611 B1 MarketSnapshotUpdated standard outbox rollback.
-- Scope: only snapshot_run_id=realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
-- This rollback is intentionally scoped to the standard-outbox B1 run. It must not touch existing fact-only B1/C1/B2 runs.
\set ON_ERROR_STOP on

BEGIN;

DO $$
DECLARE
  v_snapshot_run_id text := 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';
  v_table text;
  v_count bigint;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = v_snapshot_run_id
    AND (COALESCE(downstream_layers_touched, false) OR COALESCE(worker_started, false));
  IF v_count > 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream_layers_touched or worker_started for %', v_snapshot_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_snapshot_run_id
    AND event_type = 'MarketSnapshotUpdated'
    AND status NOT IN ('pending', 'failed', 'dead_letter');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'rollback blocked: MarketSnapshotUpdated outbox already delivered/delivering for %. count=%', v_snapshot_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_snapshot_run_id
     OR event_id IN (
          SELECT event_id FROM common_event_outbox
          WHERE source_run_id = v_snapshot_run_id
            AND event_type = 'MarketSnapshotUpdated'
        )
     OR payload_json::text LIKE '%' || v_snapshot_run_id || '%'
     OR raw_json::text LIKE '%' || v_snapshot_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_inbox refs exist for %. count=%', v_snapshot_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE last_event_id IN (
          SELECT event_id FROM common_event_outbox
          WHERE source_run_id = v_snapshot_run_id
            AND event_type = 'MarketSnapshotUpdated'
        )
     OR checkpoint_payload::text LIKE '%' || v_snapshot_run_id || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'rollback blocked: common_event_consumer_checkpoint refs exist for %. count=%', v_snapshot_run_id, v_count;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_realtime_projection_metric',
    'index_realtime_projection_metric',
    'board_realtime_projection_metric',
    'stock_minute_bar_1m',
    'index_minute_bar_1m',
    'board_minute_bar_1m',
    'common_trigger_state',
    'common_trigger_match',
    'common_action_confirmation',
    'common_action_event',
    'user_card_projection',
    'user_signal_projection',
    'user_signal_card',
    'user_notification_queue',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'n6_virtual_account',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_pnl_snapshot'
  ]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I WHERE to_jsonb(%I)::text LIKE $1', v_table, v_table)
        INTO v_count
        USING '%' || v_snapshot_run_id || '%';
      IF v_count > 0 THEN
        RAISE EXCEPTION 'rollback blocked: downstream refs in %. count=%', v_table, v_count;
      END IF;
    END IF;
  END LOOP;

  -- Default hard-fail: runtime_control must explicitly authorize removing this
  -- block before executing the scoped rollback.
  RAISE EXCEPTION
    'rollback blocked by default for %. Remove the default hard-fail only after runtime_control final gate review authorizes this exact scoped rollback.',
    v_snapshot_run_id;
END $$;

DELETE FROM common_event_outbox
WHERE source_run_id = 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
  AND event_type = 'MarketSnapshotUpdated'
  AND status IN ('pending', 'failed', 'dead_letter');

DELETE FROM stock_realtime_daily_snapshot
WHERE run_id = 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';

DELETE FROM index_realtime_daily_snapshot
WHERE run_id = 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';

DELETE FROM board_realtime_daily_snapshot
WHERE run_id = 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';

DELETE FROM common_market_data_run
WHERE run_id = 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';

COMMIT;
