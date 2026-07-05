-- N4P ordinary rollback for trigger_provisional_ordinary_20260629_until_1455__realtime_action_confirmation_metric_20260629_until_1455__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__atomic_rule_v1
DO $$
DECLARE
  v_run_id text := 'trigger_provisional_ordinary_20260629_until_1455__realtime_action_confirmation_metric_20260629_until_1455__asset_all__b1_source_returned_snapshot_amount_chain_v2_asset_unit_fix_v1_current_period_avg_v1__atomic_rule_v1';
  v_ref_table text;
  v_ref_count bigint;
BEGIN
  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    EXECUTE
      'SELECT count(*) FROM common_event_outbox AS t '
      || 'WHERE to_jsonb(t)::text LIKE $1 '
      || 'AND NOT (t.source_layer = ''N4_trigger'' AND t.source_run_id = $2)'
      INTO v_ref_count
      USING '%' || v_run_id || '%', v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: non-scoped common_event_outbox refs exist for %', v_run_id;
    END IF;
    EXECUTE
      'SELECT count(*) FROM common_event_outbox AS t '
      || 'WHERE t.source_layer = ''N4_trigger'' '
      || 'AND t.source_run_id = $1 '
      || 'AND t.status IN (''delivered'', ''delivering'')'
      INTO v_ref_count
      USING v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: scoped outbox already delivered/delivering for %', v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.common_trigger_match') IS NOT NULL THEN
    EXECUTE
      'SELECT count(*) FROM common_trigger_match AS t '
      || 'WHERE to_jsonb(t)::text LIKE $1 AND t.run_id <> $2'
      INTO v_ref_count
      USING '%' || v_run_id || '%', v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: non-scoped common_trigger_match refs exist for %', v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.common_trigger_state') IS NOT NULL THEN
    EXECUTE
      'SELECT count(*) FROM common_trigger_state AS t '
      || 'WHERE to_jsonb(t)::text LIKE $1 AND t.run_id <> $2'
      INTO v_ref_count
      USING '%' || v_run_id || '%', v_run_id;
    IF v_ref_count > 0 THEN
      RAISE EXCEPTION 'rollback blocked: non-scoped common_trigger_state refs exist for %', v_run_id;
    END IF;
  END IF;

  FOR v_ref_table IN SELECT unnest(ARRAY[
      'common_event_inbox',
      'common_event_consumer_checkpoint',
      'common_action_run',
      'common_action_event',
      'common_action_quality_item',
      'common_action_tracking_state',
      'stock_action_fact',
      'index_action_fact',
      'board_action_fact',
      'user_projection_run',
      'user_signal_projection',
      'user_signal_card',
      'user_signal_card_projection',
      'user_signal_projection_event',
      'user_notification_queue',
      'user_card_projection',
      'user_voice_delivery',
      'user_device_ack',
      'sim_projection',
      'sim_account',
      'sim_order',
      'sim_trade',
      'sim_position',
      'n6_virtual_account',
      'n6_virtual_order',
      'n6_virtual_trade',
      'n6_virtual_position',
      'real_trade_order',
      'voice_delivery',
      'mobile_push'
  ])
  LOOP
    IF to_regclass('public.' || v_ref_table) IS NOT NULL THEN
      EXECUTE format(
        'SELECT count(*) FROM %I AS t WHERE to_jsonb(t)::text LIKE $1',
        v_ref_table
      )
      INTO v_ref_count
      USING '%' || v_run_id || '%';
      IF v_ref_count > 0 THEN
        RAISE EXCEPTION 'rollback blocked: downstream refs exist in % for %', v_ref_table, v_run_id;
      END IF;
    END IF;
  END LOOP;

  DELETE FROM common_event_outbox
  WHERE source_layer = 'N4_trigger' AND source_run_id = v_run_id;
  DELETE FROM common_trigger_match WHERE run_id = v_run_id;
  DELETE FROM common_trigger_state WHERE run_id = v_run_id;
  DELETE FROM common_trigger_quality_item WHERE run_id = v_run_id;
  DELETE FROM common_trigger_run WHERE run_id = v_run_id;
END $$;
