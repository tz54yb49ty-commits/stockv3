-- N4 HINT matcher scoped rollback.
-- Scope: trigger_run_id=trigger_provisional_b2_20260703_until_1040__realtime_hint_projection_metric_20260703_until_1040__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1
-- Use only before downstream N5/N6/user consumption. Does not touch N3 metric/source facts.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'trigger_provisional_b2_20260703_until_1040__realtime_hint_projection_metric_20260703_until_1040__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1';
  v_count BIGINT;
  v_table TEXT;
  v_predicate TEXT;
BEGIN
  IF current_setting('ashare_v3.allow_n4_hint_matcher_rollback_run_id', true) IS DISTINCT FROM v_run_id THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_n4_hint_matcher_rollback_run_id=% before DELETE', v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 HINT matcher rollback blocked: scoped outbox delivered/delivering refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 HINT matcher rollback blocked: downstream inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint AS cp
  JOIN common_event_outbox AS o
    ON o.outbox_id = cp.last_outbox_id
  WHERE o.source_layer = 'N4_trigger'
    AND o.source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 HINT matcher rollback blocked: downstream checkpoint refs = %', v_count;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: N5 action_run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: N5 action_event refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.stock_action_fact') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM stock_action_fact WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: stock_action_fact refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.index_action_fact') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM index_action_fact WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: index_action_fact refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.board_action_fact') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM board_action_fact WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: board_action_fact refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_projection AS u
      JOIN common_event_outbox AS o
        ON o.event_id = u.source_event_id
      WHERE o.source_layer = 'N4_trigger'
        AND o.source_run_id = $1
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: user_signal_projection refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_card AS u
      JOIN common_event_outbox AS o
        ON o.event_id = u.source_event_id
      WHERE o.source_layer = 'N4_trigger'
        AND o.source_run_id = $1
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: user_signal_card refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_notification_queue AS u
      JOIN common_event_outbox AS o
        ON o.event_id = u.source_event_id
      WHERE o.source_layer = 'N4_trigger'
        AND o.source_run_id = $1
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: user_notification_queue refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_position_state') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_position_state WHERE run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: position_state refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_position_event') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM common_position_event AS p
      JOIN common_event_outbox AS o
        ON o.event_id = p.source_trigger_event_id
      WHERE o.source_layer = 'N4_trigger'
        AND o.source_run_id = $1
    $SQL$
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 HINT matcher rollback blocked: position_event refs = %', v_count;
    END IF;
  END IF;

  FOR v_table IN SELECT unnest(ARRAY[
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_notification_queue',
    'user_voice_delivery',
    'user_device_ack',
    'voice_delivery',
    'mobile_push',
    'sim_projection',
    'sim_account',
    'sim_order',
    'sim_trade',
    'sim_position',
    'user_sim_order',
    'user_sim_trade',
    'user_sim_position',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'real_trade_order'
  ])
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      SELECT string_agg(format('%I = $1', column_name), ' OR ')
      INTO v_predicate
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = v_table
        AND column_name IN (
          'run_id',
          'source_run_id',
          'trigger_run_id',
          'source_trigger_run_id',
          'action_run_id',
          'source_action_run_id'
        );

      IF v_predicate IS NOT NULL THEN
        EXECUTE format('SELECT count(*) FROM %I WHERE %s', v_table, v_predicate)
        INTO v_count
        USING v_run_id;
        IF v_count <> 0 THEN
          RAISE EXCEPTION 'N4 HINT matcher rollback blocked: downstream refs in % = %', v_table, v_count;
        END IF;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'trigger_provisional_b2_20260703_until_1040__realtime_hint_projection_metric_20260703_until_1040__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1';

DELETE FROM common_trigger_match
WHERE run_id = 'trigger_provisional_b2_20260703_until_1040__realtime_hint_projection_metric_20260703_until_1040__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1';

DELETE FROM common_trigger_state
WHERE run_id = 'trigger_provisional_b2_20260703_until_1040__realtime_hint_projection_metric_20260703_until_1040__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'trigger_provisional_b2_20260703_until_1040__realtime_hint_projection_metric_20260703_until_1040__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1';

DELETE FROM common_trigger_run
WHERE run_id = 'trigger_provisional_b2_20260703_until_1040__realtime_hint_projection_metric_20260703_until_1040__asset_index_board__index_board_1m_hint_projection_v1_midday_bridge_v1__atomic_rule_v1';

COMMIT;

-- Boundary:
-- - Does not touch common_market_data_run, common_market_data_quality_item, or N3 metric/source fact tables.
-- - Does not update N3 outbox, N4 outbox status, inbox, or checkpoint rows.
-- - Deletes only scoped N4 rows: common_event_outbox, common_trigger_match,
--   common_trigger_state, common_trigger_quality_item, common_trigger_run.
-- - Does not touch N5/N6/user/voice/mobile/sim/position/order/real trade rows.
