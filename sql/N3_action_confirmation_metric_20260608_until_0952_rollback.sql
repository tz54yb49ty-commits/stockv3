-- Rollback for 20260608 until 09:52 N3 action-confirmation metric materialization.
-- Scope: projection_run_id=action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry';
  v_ref_count BIGINT := 0;
  v_table TEXT;
BEGIN
  FOR v_table IN
    SELECT table_name
    FROM (VALUES
      ('common_event_outbox'),
      ('common_event_inbox'),
      ('common_event_consumer_checkpoint'),
      ('common_trigger_match'),
      ('common_trigger_state'),
      ('common_trigger_run'),
      ('common_action_run'),
      ('common_action_event'),
      ('common_action_quality_item'),
      ('stock_action_fact'),
      ('index_action_fact'),
      ('board_action_fact'),
      ('user_card_projection'),
      ('user_signal_projection'),
      ('user_signal_card'),
      ('user_notification_queue'),
      ('user_signal_decision'),
      ('user_sim_order'),
      ('user_sim_trade'),
      ('user_sim_position'),
      ('n6_virtual_account'),
      ('n6_virtual_order'),
      ('n6_virtual_trade'),
      ('n6_virtual_position'),
      ('n6_virtual_position_event'),
      ('n6_virtual_pnl_snapshot'),
      ('n6_virtual_order_proposal')
    ) AS guarded(table_name)
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*)::bigint FROM %I AS t WHERE to_jsonb(t)::text LIKE $1', v_table)
        INTO v_ref_count
        USING '%' || v_run_id || '%';
      IF v_ref_count <> 0 THEN
        RAISE EXCEPTION 'N3 action-confirmation metric rollback blocked: table % has % downstream refs for run %', v_table, v_ref_count, v_run_id;
      END IF;
    END IF;
  END LOOP;

  SELECT count(*)::bigint
    INTO v_ref_count
  FROM common_market_data_run
  WHERE run_id = v_run_id
    AND (COALESCE(downstream_layers_touched, false) OR COALESCE(worker_started, false));
  IF v_ref_count <> 0 THEN
    RAISE EXCEPTION 'N3 action-confirmation metric rollback blocked: run % has downstream_layers_touched or worker_started', v_run_id;
  END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric
WHERE projection_run_id = 'action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry';

DELETE FROM index_action_confirmation_projection_metric
WHERE projection_run_id = 'action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry';

DELETE FROM board_action_confirmation_projection_metric
WHERE projection_run_id = 'action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry'
  AND layer_scope = 'market_data_run'
  AND details ->> 'metric_scope' = 'action_confirmation_projection_metric';

DELETE FROM common_market_data_run
WHERE run_id = 'action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry'
  AND COALESCE(downstream_layers_touched, false) = false
  AND COALESCE(worker_started, false) = false;

COMMIT;
