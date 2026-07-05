-- Scoped cleanup draft for 20260612 pre-new-plan runtime messages.
-- This SQL is blocked by default. It must not be executed unless a later
-- final gate explicitly authorizes cleanup after refreshing live refs.
--
-- Scope:
--   N5 -> N4 -> N3 derived only.
-- Preserve:
--   N1/N2 facts, N3 subscriptions/pull plans, previous-day preload,
--   today minute_bar_1m source facts, and fact-only B1 snapshot source facts.

BEGIN;

DO $$
DECLARE
    v_cleanup_run_id text := 'v3_20260612_pre_new_plan_runtime_messages_cleanup_v1';
    v_trade_date_text text := '20260612';
    v_trade_date_date date := DATE '2026-06-12';
    v_now timestamptz := now();

    v_n3_standard_runs text[] := ARRAY[
        'realtime_daily_snapshot_20260612_standard_outbox_until_1107__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1113__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1120__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1307__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1314__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1333__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1413__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1430__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1444__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1452__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_daily_snapshot_20260612_standard_outbox_until_1500__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1'
    ];
    v_n3_trace_b2_runs text[] := ARRAY[
        'realtime_projection_metric_20260612_trace_aligned_standard_outbox_until_1413__realtime_daily_snapshot_20260612_standard_outbox_until_1413__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_projection_metric_20260612_trace_aligned_standard_outbox_until_1444__realtime_daily_snapshot_20260612_standard_outbox_until_1444__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_projection_metric_20260612_trace_aligned_standard_outbox_until_1452__realtime_daily_snapshot_20260612_standard_outbox_until_1452__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1',
        'realtime_projection_metric_20260612_trace_aligned_standard_outbox_until_1500__realtime_daily_snapshot_20260612_standard_outbox_until_1500__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1'
    ];
    v_n4_runs text[] := ARRAY[
        'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1413',
        'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1444',
        'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1452',
        'n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500'
    ];
    v_n5_runs text[] := ARRAY[
        'n5_action_bounded_20260612_from_n4_production_semantic_replay_20260612_market_snapshot_updated_until_1444',
        'n5_action_bounded_20260612_from_n4_production_semantic_replay_20260612_market_snapshot_updated_until_1452',
        'n5_action_bounded_20260612_from_n4_production_semantic_replay_20260612_market_snapshot_updated_until_1500'
    ];
    v_n4_consumers text[] := v_n4_runs;
    v_n5_consumers text[] := ARRAY[
        'n5_action_bounded_consumer_20260612_from_n4_until_1444',
        'n5_action_bounded_consumer_20260612_from_n4_until_1452',
        'n5_action_bounded_consumer_20260612_from_n4_until_1500'
    ];

    v_count bigint;
    v_user_refs bigint;
    v_sim_refs bigint;
    v_n5_outbox_downstream_refs bigint;
BEGIN
    IF current_setting('ashare_v3.allow_v3_20260612_pre_new_plan_cleanup', true) <> 'true' THEN
        RAISE EXCEPTION 'cleanup blocked: SET ashare_v3.allow_v3_20260612_pre_new_plan_cleanup = true is required';
    END IF;

    RAISE EXCEPTION 'cleanup blocked by default; remove this line only in an approved execute gate after refreshing live refs';

    SELECT
        (SELECT count(*) FROM user_projection_run WHERE source_action_run_id = ANY(v_n5_runs))
      + (SELECT count(*) FROM user_signal_projection WHERE source_action_run_id = ANY(v_n5_runs))
      + (SELECT count(*) FROM user_signal_card WHERE source_action_run_id = ANY(v_n5_runs))
      + (SELECT count(*) FROM user_notification_queue WHERE source_action_run_id = ANY(v_n5_runs))
      INTO v_user_refs;
    IF v_user_refs <> 0 THEN
        RAISE EXCEPTION 'N6/user refs must be zero before N5 cleanup: %', v_user_refs;
    END IF;

    SELECT
        (SELECT count(*) FROM n6_virtual_order WHERE run_id = ANY(v_n5_runs))
      + (SELECT count(*) FROM n6_virtual_trade WHERE run_id = ANY(v_n5_runs))
      + (SELECT count(*) FROM n6_virtual_position WHERE run_id = ANY(v_n5_runs))
      + (SELECT count(*) FROM n6_virtual_position_event WHERE run_id = ANY(v_n5_runs))
      + (SELECT count(*) FROM n6_virtual_pnl_snapshot WHERE trade_date = v_trade_date_date OR run_id = ANY(v_n5_runs))
      + (SELECT count(*) FROM user_sim_order WHERE trade_date = v_trade_date_text)
      + (SELECT count(*) FROM user_sim_trade WHERE trade_date = v_trade_date_text)
      + (SELECT count(*) FROM user_sim_position WHERE sim_run_id = ANY(v_n5_runs))
      INTO v_sim_refs;
    IF v_sim_refs <> 0 THEN
        RAISE EXCEPTION 'N6 virtual/user sim refs must be zero before cleanup: %', v_sim_refs;
    END IF;

    WITH n5_events AS (
        SELECT event_id
          FROM common_event_outbox
         WHERE source_layer = 'N5_action'
           AND source_run_id = ANY(v_n5_runs)
    )
    SELECT
        (SELECT count(*) FROM common_event_inbox i JOIN n5_events e ON i.event_id = e.event_id)
      + (SELECT count(*) FROM common_event_consumer_checkpoint c JOIN n5_events e ON c.last_event_id = e.event_id)
      INTO v_n5_outbox_downstream_refs;
    IF v_n5_outbox_downstream_refs <> 0 THEN
        RAISE EXCEPTION 'N5 outbox downstream refs must be zero before cleanup: %', v_n5_outbox_downstream_refs;
    END IF;

    SELECT count(*) INTO v_count FROM common_action_run WHERE run_id = ANY(v_n5_runs);
    IF v_count <> 3 THEN RAISE EXCEPTION 'unexpected N5 action_run count: %', v_count; END IF;
    SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_layer = 'N5_action' AND source_run_id = ANY(v_n5_runs);
    IF v_count <> 2437 THEN RAISE EXCEPTION 'unexpected N5 outbox count: %', v_count; END IF;
    SELECT count(*) INTO v_count FROM common_trigger_run WHERE run_id = ANY(v_n4_runs);
    IF v_count <> 4 THEN RAISE EXCEPTION 'unexpected N4 trigger_run count: %', v_count; END IF;
    SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_layer = 'N4_trigger' AND source_run_id = ANY(v_n4_runs);
    IF v_count <> 4865 THEN RAISE EXCEPTION 'unexpected N4 outbox count: %', v_count; END IF;
    SELECT count(*) INTO v_count FROM common_market_data_run WHERE run_id = ANY(v_n3_standard_runs);
    IF v_count <> 11 THEN RAISE EXCEPTION 'unexpected N3 standard run count: %', v_count; END IF;
    SELECT count(*) INTO v_count FROM common_market_data_run WHERE run_id = ANY(v_n3_trace_b2_runs);
    IF v_count <> 4 THEN RAISE EXCEPTION 'unexpected N3 trace B2 run count: %', v_count; END IF;
    SELECT count(*) INTO v_count FROM common_event_outbox WHERE source_layer = 'N3_market_data' AND source_run_id = ANY(v_n3_standard_runs) AND event_type = 'MarketSnapshotUpdated';
    IF v_count <> 22902 THEN RAISE EXCEPTION 'unexpected N3 MarketSnapshotUpdated count: %', v_count; END IF;

    CREATE TABLE IF NOT EXISTS common_runtime_cleanup_backup (
        cleanup_run_id text NOT NULL,
        table_name text NOT NULL,
        pk_json jsonb NOT NULL,
        row_json jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (cleanup_run_id, table_name, pk_json)
    );

    -- Backup scoped N5 rows.
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_event_consumer_checkpoint', jsonb_build_object('consumer_name', consumer_name, 'partition_key', partition_key), to_jsonb(t), v_now
      FROM common_event_consumer_checkpoint t WHERE consumer_name = ANY(v_n5_consumers)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_event_inbox', jsonb_build_object('inbox_id', inbox_id), to_jsonb(t), v_now
      FROM common_event_inbox t WHERE consumer_name = ANY(v_n5_consumers)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_event_outbox', jsonb_build_object('outbox_id', outbox_id), to_jsonb(t), v_now
      FROM common_event_outbox t WHERE source_layer = 'N5_action' AND source_run_id = ANY(v_n5_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_action_event', jsonb_build_object('action_event_row_id', action_event_row_id), to_jsonb(t), v_now
      FROM common_action_event t WHERE run_id = ANY(v_n5_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'stock_action_fact', jsonb_build_object('action_fact_id', action_fact_id), to_jsonb(t), v_now
      FROM stock_action_fact t WHERE run_id = ANY(v_n5_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'index_action_fact', jsonb_build_object('action_fact_id', action_fact_id), to_jsonb(t), v_now
      FROM index_action_fact t WHERE run_id = ANY(v_n5_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'board_action_fact', jsonb_build_object('action_fact_id', action_fact_id), to_jsonb(t), v_now
      FROM board_action_fact t WHERE run_id = ANY(v_n5_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_action_quality_item', jsonb_build_object('quality_item_id', quality_item_id), to_jsonb(t), v_now
      FROM common_action_quality_item t WHERE run_id = ANY(v_n5_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_action_run', jsonb_build_object('run_id', run_id), to_jsonb(t), v_now
      FROM common_action_run t WHERE run_id = ANY(v_n5_runs)
    ON CONFLICT DO NOTHING;

    DELETE FROM common_event_consumer_checkpoint WHERE consumer_name = ANY(v_n5_consumers);
    DELETE FROM common_event_inbox WHERE consumer_name = ANY(v_n5_consumers);
    DELETE FROM common_event_outbox WHERE source_layer = 'N5_action' AND source_run_id = ANY(v_n5_runs);
    DELETE FROM common_action_event WHERE run_id = ANY(v_n5_runs);
    DELETE FROM stock_action_fact WHERE run_id = ANY(v_n5_runs);
    DELETE FROM index_action_fact WHERE run_id = ANY(v_n5_runs);
    DELETE FROM board_action_fact WHERE run_id = ANY(v_n5_runs);
    DELETE FROM common_action_quality_item WHERE run_id = ANY(v_n5_runs);
    DELETE FROM common_action_run WHERE run_id = ANY(v_n5_runs);

    SELECT count(*) INTO v_count FROM common_action_run WHERE source_trigger_run_id = ANY(v_n4_runs);
    IF v_count <> 0 THEN RAISE EXCEPTION 'N5 refs remain after N5 cleanup: %', v_count; END IF;

    -- Backup scoped N4 rows.
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_event_consumer_checkpoint', jsonb_build_object('consumer_name', consumer_name, 'partition_key', partition_key), to_jsonb(t), v_now
      FROM common_event_consumer_checkpoint t WHERE consumer_name = ANY(v_n4_consumers)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_event_inbox', jsonb_build_object('inbox_id', inbox_id), to_jsonb(t), v_now
      FROM common_event_inbox t WHERE consumer_name = ANY(v_n4_consumers)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_event_outbox', jsonb_build_object('outbox_id', outbox_id), to_jsonb(t), v_now
      FROM common_event_outbox t WHERE source_layer = 'N4_trigger' AND source_run_id = ANY(v_n4_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_trigger_match', jsonb_build_object('trigger_match_id', trigger_match_id), to_jsonb(t), v_now
      FROM common_trigger_match t WHERE run_id = ANY(v_n4_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_trigger_state', jsonb_build_object('trigger_state_id', trigger_state_id), to_jsonb(t), v_now
      FROM common_trigger_state t WHERE run_id = ANY(v_n4_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_trigger_quality_item', jsonb_build_object('quality_item_id', quality_item_id), to_jsonb(t), v_now
      FROM common_trigger_quality_item t WHERE run_id = ANY(v_n4_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_trigger_run', jsonb_build_object('run_id', run_id), to_jsonb(t), v_now
      FROM common_trigger_run t WHERE run_id = ANY(v_n4_runs)
    ON CONFLICT DO NOTHING;

    DELETE FROM common_event_consumer_checkpoint WHERE consumer_name = ANY(v_n4_consumers);
    DELETE FROM common_event_inbox WHERE consumer_name = ANY(v_n4_consumers);
    DELETE FROM common_event_outbox WHERE source_layer = 'N4_trigger' AND source_run_id = ANY(v_n4_runs);
    DELETE FROM common_trigger_match WHERE run_id = ANY(v_n4_runs);
    DELETE FROM common_trigger_state WHERE run_id = ANY(v_n4_runs);
    DELETE FROM common_trigger_quality_item WHERE run_id = ANY(v_n4_runs);
    DELETE FROM common_trigger_run WHERE run_id = ANY(v_n4_runs);

    SELECT count(*) INTO v_count FROM common_event_inbox WHERE source_run_id = ANY(v_n3_standard_runs);
    IF v_count <> 0 THEN RAISE EXCEPTION 'N4 inbox refs to N3 remain after N4 cleanup: %', v_count; END IF;
    SELECT count(*) INTO v_count
      FROM common_event_consumer_checkpoint cp
      JOIN common_event_outbox ob ON ob.event_id = cp.last_event_id
     WHERE ob.source_run_id = ANY(v_n3_standard_runs);
    IF v_count <> 0 THEN RAISE EXCEPTION 'N4 checkpoint refs to N3 remain after N4 cleanup: %', v_count; END IF;

    -- Backup scoped N3 derived rows only.
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_event_outbox', jsonb_build_object('outbox_id', outbox_id), to_jsonb(t), v_now
      FROM common_event_outbox t WHERE source_layer = 'N3_market_data' AND source_run_id = ANY(v_n3_standard_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'stock_realtime_projection_metric', jsonb_build_object('projection_id', projection_id), to_jsonb(t), v_now
      FROM stock_realtime_projection_metric t WHERE projection_run_id = ANY(v_n3_trace_b2_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'index_realtime_projection_metric', jsonb_build_object('projection_id', projection_id), to_jsonb(t), v_now
      FROM index_realtime_projection_metric t WHERE projection_run_id = ANY(v_n3_trace_b2_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'board_realtime_projection_metric', jsonb_build_object('projection_id', projection_id), to_jsonb(t), v_now
      FROM board_realtime_projection_metric t WHERE projection_run_id = ANY(v_n3_trace_b2_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'stock_realtime_daily_snapshot', jsonb_build_object('snapshot_id', snapshot_id), to_jsonb(t), v_now
      FROM stock_realtime_daily_snapshot t WHERE run_id = ANY(v_n3_standard_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'index_realtime_daily_snapshot', jsonb_build_object('snapshot_id', snapshot_id), to_jsonb(t), v_now
      FROM index_realtime_daily_snapshot t WHERE run_id = ANY(v_n3_standard_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'board_realtime_daily_snapshot', jsonb_build_object('snapshot_id', snapshot_id), to_jsonb(t), v_now
      FROM board_realtime_daily_snapshot t WHERE run_id = ANY(v_n3_standard_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_market_data_quality_item', jsonb_build_object('quality_item_id', quality_item_id), to_jsonb(t), v_now
      FROM common_market_data_quality_item t WHERE run_id = ANY(v_n3_standard_runs) OR run_id = ANY(v_n3_trace_b2_runs)
    ON CONFLICT DO NOTHING;
    INSERT INTO common_runtime_cleanup_backup(cleanup_run_id, table_name, pk_json, row_json, created_at)
    SELECT v_cleanup_run_id, 'common_market_data_run', jsonb_build_object('run_id', run_id), to_jsonb(t), v_now
      FROM common_market_data_run t WHERE run_id = ANY(v_n3_standard_runs) OR run_id = ANY(v_n3_trace_b2_runs)
    ON CONFLICT DO NOTHING;

    DELETE FROM common_event_outbox WHERE source_layer = 'N3_market_data' AND source_run_id = ANY(v_n3_standard_runs);
    DELETE FROM stock_realtime_projection_metric WHERE projection_run_id = ANY(v_n3_trace_b2_runs);
    DELETE FROM index_realtime_projection_metric WHERE projection_run_id = ANY(v_n3_trace_b2_runs);
    DELETE FROM board_realtime_projection_metric WHERE projection_run_id = ANY(v_n3_trace_b2_runs);
    DELETE FROM stock_realtime_daily_snapshot WHERE run_id = ANY(v_n3_standard_runs);
    DELETE FROM index_realtime_daily_snapshot WHERE run_id = ANY(v_n3_standard_runs);
    DELETE FROM board_realtime_daily_snapshot WHERE run_id = ANY(v_n3_standard_runs);
    DELETE FROM common_market_data_quality_item WHERE run_id = ANY(v_n3_standard_runs) OR run_id = ANY(v_n3_trace_b2_runs);
    DELETE FROM common_market_data_run WHERE run_id = ANY(v_n3_standard_runs) OR run_id = ANY(v_n3_trace_b2_runs);
END $$;

COMMIT;
