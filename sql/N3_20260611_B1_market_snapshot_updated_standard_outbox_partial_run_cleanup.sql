-- N3 20260611 B1 MarketSnapshotUpdated standard outbox partial-run cleanup.
-- Scope: only the failed-attempt running run row for
-- realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1.
-- This cleanup must not delete snapshot facts, quality rows, outbox rows, inbox/checkpoint rows, or downstream rows.
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
    AND status = 'running'
    AND COALESCE(market_data_pulled, false) = false
    AND COALESCE(market_data_fact_written, false) = false
    AND COALESCE(downstream_layers_touched, false) = false
    AND COALESCE(worker_started, false) = false;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'cleanup blocked: expected exactly one safe running common_market_data_run row for %, found %', v_snapshot_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count FROM common_market_data_quality_item WHERE run_id = v_snapshot_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'cleanup blocked: quality rows exist for %. count=%', v_snapshot_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count FROM stock_realtime_daily_snapshot WHERE run_id = v_snapshot_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'cleanup blocked: stock snapshot rows exist for %. count=%', v_snapshot_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count FROM index_realtime_daily_snapshot WHERE run_id = v_snapshot_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'cleanup blocked: index snapshot rows exist for %. count=%', v_snapshot_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count FROM board_realtime_daily_snapshot WHERE run_id = v_snapshot_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'cleanup blocked: board snapshot rows exist for %. count=%', v_snapshot_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_snapshot_run_id
     OR payload_json::text LIKE '%' || v_snapshot_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'cleanup blocked: common_event_outbox refs exist for %. count=%', v_snapshot_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_snapshot_run_id
     OR event_id IN (
          SELECT event_id FROM common_event_outbox
          WHERE source_run_id = v_snapshot_run_id
             OR payload_json::text LIKE '%' || v_snapshot_run_id || '%'
        )
     OR payload_json::text LIKE '%' || v_snapshot_run_id || '%'
     OR raw_json::text LIKE '%' || v_snapshot_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'cleanup blocked: common_event_inbox refs exist for %. count=%', v_snapshot_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE last_event_id IN (
          SELECT event_id FROM common_event_outbox
          WHERE source_run_id = v_snapshot_run_id
             OR payload_json::text LIKE '%' || v_snapshot_run_id || '%'
        )
     OR checkpoint_payload::text LIKE '%' || v_snapshot_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'cleanup blocked: common_event_consumer_checkpoint refs exist for %. count=%', v_snapshot_run_id, v_count;
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
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'cleanup blocked: downstream refs in %. count=%', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM common_market_data_run
WHERE run_id = 'realtime_daily_snapshot_20260611_standard_outbox__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
  AND status = 'running'
  AND COALESCE(market_data_pulled, false) = false
  AND COALESCE(market_data_fact_written, false) = false
  AND COALESCE(downstream_layers_touched, false) = false
  AND COALESCE(worker_started, false) = false;

COMMIT;
