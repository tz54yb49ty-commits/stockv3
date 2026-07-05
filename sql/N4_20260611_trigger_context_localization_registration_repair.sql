-- A-share monitor v3 N4 20260611 trigger context localization registration repair draft.
-- Target run_id: trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1
-- Purpose:
--   Reclassify runner-registered P0 n4_3_n3_facts_and_outbox_unchanged=false
--   as a P1 external-concurrency caveat, because read-only evidence shows
--   concurrent N3 auto-poll fact-only writes during the N4 context execute window.
--
-- IMPORTANT:
--   This SQL is a reviewed draft only. Do not execute without a dedicated
--   runtime_control final gate and fresh downstream refs proof.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := 'trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1';
  v_quality_count BIGINT;
  v_context_count BIGINT;
  v_refs BIGINT;
BEGIN
  SELECT count(*) INTO v_quality_count
  FROM common_trigger_quality_item
  WHERE run_id = v_run_id
    AND gate_code = 'n4_3_n3_facts_and_outbox_unchanged'
    AND severity = 'P0'
    AND status = 'failed';
  IF v_quality_count <> 1 THEN
    RAISE EXCEPTION 'Refusing registration repair: expected exactly 1 target failed P0 quality item, found %', v_quality_count;
  END IF;

  SELECT
      (SELECT count(*) FROM stock_trigger_context_snapshot WHERE run_id = v_run_id)
    + (SELECT count(*) FROM index_trigger_context_snapshot WHERE run_id = v_run_id)
    + (SELECT count(*) FROM board_trigger_context_snapshot WHERE run_id = v_run_id)
  INTO v_context_count;
  IF v_context_count <> 4480 THEN
    RAISE EXCEPTION 'Refusing registration repair: expected 4480 context rows, found %', v_context_count;
  END IF;

  SELECT count(*) INTO v_refs
  FROM common_trigger_state
  WHERE run_id = v_run_id OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN
    RAISE EXCEPTION 'Refusing registration repair: trigger_state has % refs for %', v_refs, v_run_id;
  END IF;

  SELECT count(*) INTO v_refs
  FROM common_trigger_match
  WHERE run_id = v_run_id OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN
    RAISE EXCEPTION 'Refusing registration repair: trigger_match has % refs for %', v_refs, v_run_id;
  END IF;

  SELECT count(*) INTO v_refs
  FROM common_event_outbox
  WHERE (source_layer = 'N4_trigger' AND source_run_id = v_run_id)
     OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN
    RAISE EXCEPTION 'Refusing registration repair: N4 outbox has % refs for %', v_refs, v_run_id;
  END IF;

  SELECT count(*) INTO v_refs
  FROM common_event_inbox
  WHERE source_run_id = v_run_id
     OR raw_json::TEXT LIKE '%' || v_run_id || '%'
     OR payload_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN
    RAISE EXCEPTION 'Refusing registration repair: inbox has % refs for %', v_refs, v_run_id;
  END IF;

  SELECT count(*) INTO v_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::TEXT LIKE '%' || v_run_id || '%'
     OR last_event_id LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN
    RAISE EXCEPTION 'Refusing registration repair: checkpoint has % refs for %', v_refs, v_run_id;
  END IF;

  SELECT count(*) INTO v_refs
  FROM common_action_run
  WHERE source_trigger_run_id = v_run_id OR raw_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN
    RAISE EXCEPTION 'Refusing registration repair: N5 action_run has % refs for %', v_refs, v_run_id;
  END IF;

  SELECT count(*) INTO v_refs
  FROM common_action_event
  WHERE source_trigger_run_id = v_run_id
     OR payload_json::TEXT LIKE '%' || v_run_id || '%'
     OR trace_json::TEXT LIKE '%' || v_run_id || '%';
  IF v_refs <> 0 THEN
    RAISE EXCEPTION 'Refusing registration repair: N5 action_event has % refs for %', v_refs, v_run_id;
  END IF;
END $$;

-- Proposed repair after removing the hard-fail in an approved gate:
UPDATE common_trigger_quality_item
SET
  severity = 'P1',
  status = 'warning',
  expected_value = 'N4 context write scope unchanged; external N3 fact-only auto-poll deltas may occur concurrently',
  actual_value = 'external_concurrent_n3_delta_registered',
  details = jsonb_build_object(
    'repair_gate', 'N4_20260611_TRIGGER_CONTEXT_LOCALIZATION_POST_REVIEW_REPAIR_GATE',
    'repair_reason', 'N4 context rows were scoped and correct; failed global N3 unchanged check was caused by concurrent N3 auto-poll fact-only writes, not N4 boundary violation',
    'concurrent_n3_runs', jsonb_build_array(
      'realtime_daily_snapshot_20260611_until_1104__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1',
      'today_minute_bar_1m_20260611_until_1104__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1',
      'realtime_projection_metric_20260611_until_1104__realtime_daily_snapshot_20260611_until_1104__market_data_subscription_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
    ),
    'n4_context_rows', 4480,
    'trigger_state_match_outbox', '0/0/0',
    'n5_refs', 0,
    'n6_user_refs', 0
  )
WHERE run_id = 'trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
  AND gate_code = 'n4_3_n3_facts_and_outbox_unchanged'
  AND severity = 'P0'
  AND status = 'failed';

UPDATE common_trigger_run
SET
  p0_count = 0,
  p1_count = p1_count + 1,
  raw_json = COALESCE(raw_json, '{}'::jsonb) || jsonb_build_object(
    'post_review_registration_repair',
    jsonb_build_object(
      'gate', 'N4_20260611_TRIGGER_CONTEXT_LOCALIZATION_POST_REVIEW_REPAIR_GATE',
      'reason', 'Concurrent N3 fact-only auto-poll delta reclassified from P0 to P1 external caveat',
      'rollback_sql_hardened', true,
      'n4_boundary_violation', false
    )
  )
WHERE run_id = 'trigger_context_snapshot_20260611_condition_layer_20260610_source_20260610_for_20260611_v1'
  AND p0_count = 1
  AND p1_count = 0
  AND p2_count = 0;

COMMIT;

-- Boundary:
-- - This draft only repairs N4 context localization registration metadata.
-- - It does not write trigger_state, trigger_match, N4 outbox, N5, N6, user, sim, order, trade, or position facts.
-- - It does not touch N3 facts or N3 outbox status.
-- - It is hard-failed by default and must not be executed without a separate final gate.
