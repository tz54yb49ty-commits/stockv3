-- N4 20260605 context refresh post-review registration repair.
-- Scope: correct only the stale quality registration for one already-written
-- N4 trigger_context_snapshot run after read-only DB proof shows required
-- periods are ready. Do not execute without runtime_control approval.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1';
  v_condition_run_id TEXT := 'condition_layer_20260604_source_20260604_v1';
  v_for_trade_date TEXT := '20260605';
  v_source_trade_date TEXT := '20260604';
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_trigger_run
  WHERE run_id = v_run_id
    AND source_condition_run_id = v_condition_run_id
    AND for_trade_date = v_for_trade_date
    AND status = 'passed'
    AND context_snapshot_row_count = 5118
    AND trigger_state_row_count = 0
    AND trigger_match_row_count = 0
    AND trigger_event_outbox_count = 0;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: trigger run shape mismatch for %', v_run_id;
  END IF;

  SELECT count(*) INTO v_count FROM stock_trigger_context_snapshot WHERE run_id = v_run_id;
  IF v_count <> 4186 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: stock context rows = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM index_trigger_context_snapshot WHERE run_id = v_run_id;
  IF v_count <> 20 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: index context rows = %', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM board_trigger_context_snapshot WHERE run_id = v_run_id;
  IF v_count <> 912 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: board context rows = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_match
  WHERE run_id = v_run_id
     OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: trigger_match refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_state
  WHERE run_id = v_run_id
     OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: trigger_state refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_run_id = v_run_id
     OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: outbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_run_id = v_run_id
     OR payload_json::TEXT LIKE '%' || v_run_id || '%'
     OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%'
     OR last_event_id LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: checkpoint refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_run
  WHERE source_trigger_run_id = v_run_id
     OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: N5 action_run refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_event
  WHERE source_trigger_run_id = v_run_id
     OR payload_json::TEXT LIKE '%' || v_run_id || '%'
     OR trace_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: N5 action_event refs = %', v_count;
  END IF;

  IF to_regclass('public.user_projection_run') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*) FROM user_projection_run
      WHERE to_jsonb(user_projection_run)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 context registration repair blocked: user_projection_run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*) FROM user_signal_projection
      WHERE to_jsonb(user_signal_projection)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 context registration repair blocked: user_signal_projection refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*) FROM user_signal_card
      WHERE to_jsonb(user_signal_card)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 context registration repair blocked: user_signal_card refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*) FROM user_notification_queue
      WHERE to_jsonb(user_notification_queue)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 context registration repair blocked: user_notification_queue refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_order') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*) FROM user_sim_order
      WHERE to_jsonb(user_sim_order)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 context registration repair blocked: user_sim_order refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_position') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*) FROM user_sim_position
      WHERE to_jsonb(user_sim_position)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 context registration repair blocked: user_sim_position refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*) FROM user_sim_trade
      WHERE to_jsonb(user_sim_trade)::TEXT LIKE '%' || $1 || '%'
    $SQL$ INTO v_count USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 context registration repair blocked: user_sim_trade refs = %', v_count;
    END IF;
  END IF;

  WITH all_ctx AS (
    SELECT identity_key, condition_key, source_trade_date, raw_json
    FROM stock_trigger_context_snapshot
    WHERE run_id = v_run_id
    UNION ALL
    SELECT identity_key, condition_key, source_trade_date, raw_json
    FROM index_trigger_context_snapshot
    WHERE run_id = v_run_id
    UNION ALL
    SELECT identity_key, condition_key, source_trade_date, raw_json
    FROM board_trigger_context_snapshot
    WHERE run_id = v_run_id
  ), required_periods AS (
    SELECT identity_key, condition_key, source_trade_date,
           unnest(
             CASE
               WHEN condition_key IN ('BUY:FULL', 'SELL:FULL') THEN ARRAY['D']::TEXT[]
               WHEN condition_key LIKE 'BUY:%' THEN string_to_array(substring(condition_key FROM 5), ',')
               WHEN condition_key LIKE 'SELL:%' THEN string_to_array(substring(condition_key FROM 6), ',')
               ELSE ARRAY[]::TEXT[]
             END
           ) AS period,
           raw_json
    FROM all_ctx
  ), failures AS (
    SELECT *
    FROM required_periods
    WHERE raw_json #>> ARRAY['period_trigger_baseline_json','periods',period,'trigger_previous_entity_high'] IS NULL
       OR raw_json #>> ARRAY['period_trigger_baseline_json','periods',period,'trigger_previous_entity_low'] IS NULL
       OR raw_json #>> ARRAY['period_trigger_baseline_json','periods',period,'trigger_previous_amount_baseline'] IS NULL
       OR COALESCE(raw_json #>> ARRAY['period_trigger_baseline_json','periods',period,'baseline_source_trade_date'], '') <> v_source_trade_date
  )
  SELECT count(*) INTO v_count FROM failures;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 context registration repair blocked: required-period proof failures = %', v_count;
  END IF;
END $$;

UPDATE common_trigger_quality_item
SET status = 'passed',
    actual_value = 'true',
    details = coalesce(details, '{}'::jsonb) || jsonb_build_object(
      'registration_repair',
      jsonb_build_object(
        'reason', 'post_review_required_period_not_ready_rows_false_positive',
        'required_period_not_ready_rows', 0,
        'trigger_previous_entity_high_low_missing', 0,
        'trigger_previous_amount_baseline_missing', 0,
        'baseline_source_trade_date_mismatch', 0
      )
    )
WHERE run_id = 'trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1'
  AND gate_code = 'n4_3_required_period_not_ready_rows_zero';

UPDATE common_trigger_run
SET p0_count = 0,
    p1_count = 0,
    p2_count = 0,
    raw_json = coalesce(raw_json, '{}'::jsonb) || jsonb_build_object(
      'post_review_registration_repair',
      jsonb_build_object(
        'status', 'ready_for_runtime_control_final_gate',
        'required_period_not_ready_rows', 0,
        'forbidden_scope_refs', 0
      )
    ),
    updated_at = now()
WHERE run_id = 'trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1';

COMMIT;
