-- A-share monitor v3 N4 trigger context rollback.
-- Execute only after confirming this N4 context run has not been consumed downstream.
-- This rollback deletes only N4 trigger context/run/quality rows for one run_id.
-- Optional N6/user tables are checked with to_regclass so the rollback is portable.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1';
  v_allowed TEXT := current_setting('ashare_v3.allow_n4_context_rollback_run_id', true);
  v_count BIGINT;
BEGIN
  IF v_allowed IS DISTINCT FROM v_run_id THEN
    RAISE EXCEPTION 'N4 context rollback hard-fail: set ashare_v3.allow_n4_context_rollback_run_id=% before mutation', v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id
    AND status IN ('delivered', 'delivering');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: scoped outbox already delivered/delivering has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE (source_layer = 'N4_trigger' AND source_run_id = v_run_id)
     OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: outbox has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id
     OR raw_json::TEXT LIKE '%' || v_run_id || '%'
     OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: inbox has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%'
     OR last_event_id LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: checkpoint has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_match
  WHERE run_id = v_run_id
     OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: trigger_match has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_state
  WHERE run_id = v_run_id
     OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: trigger_state has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_run
  WHERE source_trigger_run_id = v_run_id
     OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: N5 action_run has % rows for %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_event
  WHERE source_trigger_run_id = v_run_id
     OR payload_json::TEXT LIKE '%' || v_run_id || '%'
     OR trace_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N4 context rollback: N5 action_event has % rows for %', v_count, v_run_id;
  END IF;

  IF to_regclass('public.user_projection_run') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_projection_run
      WHERE to_jsonb(user_projection_run)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N4 context rollback: user_projection_run has % rows for %', v_count, v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_projection
      WHERE to_jsonb(user_signal_projection)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N4 context rollback: user_signal_projection has % rows for %', v_count, v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_card
      WHERE to_jsonb(user_signal_card)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N4 context rollback: user_signal_card has % rows for %', v_count, v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_notification_queue
      WHERE to_jsonb(user_notification_queue)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N4 context rollback: user_notification_queue has % rows for %', v_count, v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_order') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_sim_order
      WHERE to_jsonb(user_sim_order)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N4 context rollback: user_sim_order has % rows for %', v_count, v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_position') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_sim_position
      WHERE to_jsonb(user_sim_position)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N4 context rollback: user_sim_position has % rows for %', v_count, v_run_id;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_sim_trade
      WHERE to_jsonb(user_sim_trade)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N4 context rollback: user_sim_trade has % rows for %', v_count, v_run_id;
    END IF;
  END IF;
END $$;

DELETE FROM common_trigger_quality_item WHERE run_id = 'trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1';
DELETE FROM stock_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1';
DELETE FROM index_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1';
DELETE FROM board_trigger_context_snapshot WHERE run_id = 'trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1';
DELETE FROM common_trigger_run WHERE run_id = 'trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1';

COMMIT;

-- Boundary:
-- - Does not touch common_condition_run or condition tables.
-- - Does not touch common_market_data_* or market data fact tables.
-- - Does not touch common_event_outbox.
-- - Does not touch trigger_state / trigger_match because N4-3 never writes them.
-- - Does not touch action/user/voice/mobile/sim/position tables.
