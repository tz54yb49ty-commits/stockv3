-- N4 action-confirmation metric business execute rollback.
-- Scope: execute_run_id=n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1
-- Use only before downstream N5/N6 consumption. Does not touch N2/N3 facts,
-- N3 action-confirmation metric rows, N3 outbox, or N4 context snapshots.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1';
  v_count BIGINT;
  v_table TEXT;
BEGIN
  IF current_setting('ashare_v3.allow_n4_action_confirmation_metric_rollback_run_id', true) <> v_run_id THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_n4_action_confirmation_metric_rollback_run_id=% before DELETE', v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: outbox delivered/delivering refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: downstream inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: downstream checkpoint refs = %', v_count;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: N5 action run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE source_trigger_run_id = $1 OR to_jsonb(common_action_event)::TEXT LIKE $2'
    INTO v_count
    USING v_run_id, '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: N5 action event refs = %', v_count;
    END IF;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_action_fact',
    'index_action_fact',
    'board_action_fact',
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_notification_queue',
    'user_sim_order',
    'user_sim_position',
    'user_sim_trade',
    'common_position_state',
    'common_position_event',
    'n6_virtual_order',
    'n6_virtual_position',
    'n6_virtual_trade'
  ]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I WHERE to_jsonb(%I)::TEXT LIKE $1', v_table, v_table)
      INTO v_count
      USING '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: downstream refs in % = %', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1';

DELETE FROM common_trigger_match
WHERE run_id = 'n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1';

DELETE FROM common_trigger_state
WHERE run_id = 'n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1';

DELETE FROM common_trigger_run
WHERE run_id = 'n4_20260615_repaired_formal_price_amount_chain_replay_after_n3_coverage_repair_v1';

COMMIT;
