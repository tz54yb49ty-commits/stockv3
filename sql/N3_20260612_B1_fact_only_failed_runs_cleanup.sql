-- N3 20260612 B1 fact-only failed/interrupted scoped cleanup.
-- Scope:
--   realtime_daily_snapshot_20260612_until_1005__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1
--   realtime_daily_snapshot_20260612_until_1008__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1
--   realtime_daily_snapshot_20260612_until_1011__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1
--   realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1
-- Default: blocked. Runtime-control final gate must explicitly enable:
--   SET ashare_v3.allow_n3_b1_20260612_failed_cleanup = 'true';

DO $$
DECLARE
  v_run_ids text[] := ARRAY[
    'realtime_daily_snapshot_20260612_until_1005__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
    'realtime_daily_snapshot_20260612_until_1008__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
    'realtime_daily_snapshot_20260612_until_1011__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
    'realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1'
  ];
  v_table text;
  v_column text;
  v_count bigint;
  v_failed_count bigint;
  v_running_count bigint;
  v_has_column boolean;
  v_payload_predicates text;
BEGIN
  IF current_setting('ashare_v3.allow_n3_b1_20260612_failed_cleanup', true) IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION
      'cleanup blocked by default hard-fail: set ashare_v3.allow_n3_b1_20260612_failed_cleanup=true only after runtime_control final gate';
  END IF;

  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = ANY(v_run_ids);
  IF v_count <> array_length(v_run_ids, 1) THEN
    RAISE EXCEPTION 'cleanup blocked: expected 4 target common_market_data_run rows, found %', v_count;
  END IF;

  SELECT count(*) INTO v_failed_count
  FROM common_market_data_run
  WHERE run_id = ANY(v_run_ids)
    AND status = 'failed';
  SELECT count(*) INTO v_running_count
  FROM common_market_data_run
  WHERE run_id = ANY(v_run_ids)
    AND status = 'running';
  IF v_failed_count <> 3 OR v_running_count <> 1 THEN
    RAISE EXCEPTION 'cleanup blocked: expected failed/running status counts 3/1, found %/%', v_failed_count, v_running_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_market_data_run
  WHERE run_id = ANY(v_run_ids)
    AND (COALESCE(downstream_layers_touched, false) OR COALESCE(worker_started, false));
  IF v_count > 0 THEN
    RAISE EXCEPTION 'cleanup blocked: downstream_layers_touched or worker_started target rows exist. count=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = ANY(v_run_ids)
     OR payload_json::text LIKE ANY(SELECT '%' || unnest(v_run_ids) || '%');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'cleanup blocked: common_event_outbox refs exist. count=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE payload_json::text LIKE ANY(SELECT '%' || unnest(v_run_ids) || '%')
     OR raw_json::text LIKE ANY(SELECT '%' || unnest(v_run_ids) || '%');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'cleanup blocked: common_event_inbox refs exist. count=%', v_count;
  END IF;

  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL THEN
    v_payload_predicates := '';
    FOREACH v_column IN ARRAY ARRAY['source_run_id', 'checkpoint_payload', 'payload_json', 'raw_json', 'last_event_id']
    LOOP
      SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'common_event_consumer_checkpoint'
          AND column_name = v_column
      ) INTO v_has_column;
      IF v_has_column THEN
        IF v_payload_predicates <> '' THEN
          v_payload_predicates := v_payload_predicates || ' OR ';
        END IF;
        IF v_column = 'source_run_id' THEN
          v_payload_predicates := v_payload_predicates || format('%I = ANY($1)', v_column);
        ELSE
          v_payload_predicates := v_payload_predicates || format('%I::text LIKE ANY(SELECT ''%%'' || unnest($1) || ''%%'')', v_column);
        END IF;
      END IF;
    END LOOP;
    IF v_payload_predicates <> '' THEN
      EXECUTE 'SELECT count(*) FROM common_event_consumer_checkpoint WHERE ' || v_payload_predicates
        INTO v_count USING v_run_ids;
      IF v_count > 0 THEN
        RAISE EXCEPTION 'cleanup blocked: common_event_consumer_checkpoint refs exist. count=%', v_count;
      END IF;
    END IF;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_realtime_projection_metric',
    'index_realtime_projection_metric',
    'board_realtime_projection_metric',
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
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_pnl_snapshot'
  ]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      v_payload_predicates := '';
      FOREACH v_column IN ARRAY ARRAY['source_run_id', 'run_id', 'snapshot_run_id', 'source_snapshot_run_id', 'payload_json', 'raw_json']
      LOOP
        SELECT EXISTS (
          SELECT 1 FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name = v_table
            AND column_name = v_column
        ) INTO v_has_column;
        IF v_has_column THEN
          IF v_payload_predicates <> '' THEN
            v_payload_predicates := v_payload_predicates || ' OR ';
          END IF;
          IF v_column IN ('source_run_id', 'run_id', 'snapshot_run_id', 'source_snapshot_run_id') THEN
            v_payload_predicates := v_payload_predicates || format('%I = ANY($1)', v_column);
          ELSE
            v_payload_predicates := v_payload_predicates || format('%I::text LIKE ANY(SELECT ''%%'' || unnest($1) || ''%%'')', v_column);
          END IF;
        END IF;
      END LOOP;
      IF v_payload_predicates <> '' THEN
        EXECUTE format('SELECT count(*) FROM %I WHERE %s', v_table, v_payload_predicates)
          INTO v_count USING v_run_ids;
        IF v_count > 0 THEN
          RAISE EXCEPTION 'cleanup blocked: downstream refs exist in %. count=%', v_table, v_count;
        END IF;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM stock_realtime_daily_snapshot
WHERE run_id = ANY(ARRAY[
  'realtime_daily_snapshot_20260612_until_1005__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1008__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1011__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1'
]);

DELETE FROM index_realtime_daily_snapshot
WHERE run_id = ANY(ARRAY[
  'realtime_daily_snapshot_20260612_until_1005__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1008__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1011__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1'
]);

DELETE FROM board_realtime_daily_snapshot
WHERE run_id = ANY(ARRAY[
  'realtime_daily_snapshot_20260612_until_1005__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1008__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1011__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1'
]);

DELETE FROM common_market_data_quality_item
WHERE run_id = ANY(ARRAY[
  'realtime_daily_snapshot_20260612_until_1005__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1008__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1011__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1'
]);

DELETE FROM common_market_data_run
WHERE run_id = ANY(ARRAY[
  'realtime_daily_snapshot_20260612_until_1005__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1008__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1011__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
  'realtime_daily_snapshot_20260612_until_1014__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1'
]);
