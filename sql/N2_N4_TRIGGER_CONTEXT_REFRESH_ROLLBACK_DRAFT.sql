-- N2/N4 trigger context refresh rollback draft.
-- Scope:
--   - Clear only the repaired N2 context enrichment materialization rows for the refresh run.
--   - Clear only the N4 trigger context snapshot/run/quality rows for the target context run.
--   - Do not touch N1 facts, N3 facts, N4 match/state/outbox, N5/N6 facts, or event infra rows.
-- Execute only after a separate execute final gate approves this rollback.

BEGIN;

DO $$
DECLARE
  v_context_run_id TEXT := 'trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1';
  v_condition_run_id TEXT := 'condition_layer_20260604_source_20260604_v1';
  v_context_refresh_run_id TEXT := 'condition_context_enrichment_v4_20260605_condition_layer_20260604_source_20260604_v1_semantic_repair';
  v_count BIGINT;
BEGIN
  -- Event infra guards. These must run before the first DELETE/UPDATE.
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND (
      source_run_id IN (v_context_run_id, v_context_refresh_run_id)
      OR payload_json::TEXT LIKE '%' || v_context_run_id || '%'
      OR payload_json::TEXT LIKE '%' || v_context_refresh_run_id || '%'
      OR payload_json::TEXT LIKE '%' || v_condition_run_id || '%'
    );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: outbox has % refs for %, %, or %',
      v_count, v_context_run_id, v_context_refresh_run_id, v_condition_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND (
      source_run_id IN (v_context_run_id, v_context_refresh_run_id)
      OR payload_json::TEXT LIKE '%' || v_context_run_id || '%'
      OR payload_json::TEXT LIKE '%' || v_context_refresh_run_id || '%'
      OR payload_json::TEXT LIKE '%' || v_condition_run_id || '%'
      OR raw_json::TEXT LIKE '%' || v_context_run_id || '%'
      OR raw_json::TEXT LIKE '%' || v_context_refresh_run_id || '%'
      OR raw_json::TEXT LIKE '%' || v_condition_run_id || '%'
    );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: inbox has % refs for %, %, or %',
      v_count, v_context_run_id, v_context_refresh_run_id, v_condition_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND (
      checkpoint_payload::TEXT LIKE '%' || v_context_run_id || '%'
      OR checkpoint_payload::TEXT LIKE '%' || v_context_refresh_run_id || '%'
      OR checkpoint_payload::TEXT LIKE '%' || v_condition_run_id || '%'
    );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: checkpoint has % refs for %, %, or %',
      v_count, v_context_run_id, v_context_refresh_run_id, v_condition_run_id;
  END IF;

  -- N4 guards.
  SELECT count(*) INTO v_count
  FROM common_trigger_match
  WHERE run_id = v_context_run_id
     OR source_condition_run_id = v_condition_run_id
     OR raw_json::TEXT LIKE '%' || v_context_run_id || '%'
     OR raw_json::TEXT LIKE '%' || v_context_refresh_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: trigger_match has % downstream refs', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_state
  WHERE run_id = v_context_run_id
     OR source_condition_run_id = v_condition_run_id
     OR raw_json::TEXT LIKE '%' || v_context_run_id || '%'
     OR raw_json::TEXT LIKE '%' || v_context_refresh_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: trigger_state has % downstream refs', v_count;
  END IF;

  -- N5 guards.
  SELECT count(*) INTO v_count
  FROM common_action_run
  WHERE source_trigger_run_id = v_context_run_id
     OR source_condition_run_id = v_condition_run_id
     OR raw_json::TEXT LIKE '%' || v_context_run_id || '%'
     OR raw_json::TEXT LIKE '%' || v_context_refresh_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: action_run has % downstream refs', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_event
  WHERE source_trigger_run_id = v_context_run_id
     OR source_condition_run_id = v_condition_run_id
     OR payload_json::TEXT LIKE '%' || v_context_run_id || '%'
     OR payload_json::TEXT LIKE '%' || v_context_refresh_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: action_event has % downstream refs', v_count;
  END IF;

  -- N6/user guards.
  IF to_regclass('public.user_projection_run') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_projection_run
      WHERE user_projection_run_id::TEXT LIKE '%' || $1 || '%'
         OR user_projection_run_id::TEXT LIKE '%' || $2 || '%'
         OR source_action_run_id::TEXT LIKE '%' || $1 || '%'
         OR source_action_run_id::TEXT LIKE '%' || $2 || '%'
         OR source_n5_outbox_range::TEXT LIKE '%' || $1 || '%'
         OR source_n5_outbox_range::TEXT LIKE '%' || $2 || '%'
         OR quality_summary_json::TEXT LIKE '%' || $1 || '%'
         OR quality_summary_json::TEXT LIKE '%' || $2 || '%'
    $SQL$
    INTO v_count
    USING v_context_run_id, v_context_refresh_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: user_projection_run has % downstream refs', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_projection
      WHERE user_projection_run_id::TEXT LIKE '%' || $1 || '%'
         OR user_projection_run_id::TEXT LIKE '%' || $2 || '%'
         OR source_action_run_id::TEXT LIKE '%' || $1 || '%'
         OR source_action_run_id::TEXT LIKE '%' || $2 || '%'
         OR source_event_id::TEXT LIKE '%' || $1 || '%'
         OR source_event_id::TEXT LIKE '%' || $2 || '%'
         OR source_payload_json::TEXT LIKE '%' || $1 || '%'
         OR source_payload_json::TEXT LIKE '%' || $2 || '%'
         OR display_payload_json::TEXT LIKE '%' || $1 || '%'
         OR display_payload_json::TEXT LIKE '%' || $2 || '%'
    $SQL$
    INTO v_count
    USING v_context_run_id, v_context_refresh_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: user_signal_projection has % downstream refs', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_signal_card
      WHERE user_projection_run_id::TEXT LIKE '%' || $1 || '%'
         OR user_projection_run_id::TEXT LIKE '%' || $2 || '%'
         OR source_action_run_id::TEXT LIKE '%' || $1 || '%'
         OR source_action_run_id::TEXT LIKE '%' || $2 || '%'
         OR source_event_id::TEXT LIKE '%' || $1 || '%'
         OR source_event_id::TEXT LIKE '%' || $2 || '%'
         OR card_payload_json::TEXT LIKE '%' || $1 || '%'
         OR card_payload_json::TEXT LIKE '%' || $2 || '%'
    $SQL$
    INTO v_count
    USING v_context_run_id, v_context_refresh_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: user_signal_card has % downstream refs', v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE $SQL$
      SELECT count(*)
      FROM user_notification_queue
      WHERE user_projection_run_id::TEXT LIKE '%' || $1 || '%'
         OR user_projection_run_id::TEXT LIKE '%' || $2 || '%'
         OR source_action_run_id::TEXT LIKE '%' || $1 || '%'
         OR source_action_run_id::TEXT LIKE '%' || $2 || '%'
         OR source_event_id::TEXT LIKE '%' || $1 || '%'
         OR source_event_id::TEXT LIKE '%' || $2 || '%'
         OR notification_payload_json::TEXT LIKE '%' || $1 || '%'
         OR notification_payload_json::TEXT LIKE '%' || $2 || '%'
    $SQL$
    INTO v_count
    USING v_context_run_id, v_context_refresh_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing N2/N4 context refresh rollback: user_notification_queue has % downstream refs', v_count;
    END IF;
  END IF;
END $$;

-- DELETE scope is intentionally narrow and starts only after all guards above.
DELETE FROM stock_condition_context_enrichment
WHERE materialization_run_id = 'condition_context_enrichment_v4_20260605_condition_layer_20260604_source_20260604_v1_semantic_repair';

DELETE FROM index_condition_context_enrichment
WHERE materialization_run_id = 'condition_context_enrichment_v4_20260605_condition_layer_20260604_source_20260604_v1_semantic_repair';

DELETE FROM board_condition_context_enrichment
WHERE materialization_run_id = 'condition_context_enrichment_v4_20260605_condition_layer_20260604_source_20260604_v1_semantic_repair';

DELETE FROM common_condition_context_enrichment_run
WHERE run_id = 'condition_context_enrichment_v4_20260605_condition_layer_20260604_source_20260604_v1_semantic_repair';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1';

DELETE FROM stock_trigger_context_snapshot
WHERE run_id = 'trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1';

DELETE FROM index_trigger_context_snapshot
WHERE run_id = 'trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1';

DELETE FROM board_trigger_context_snapshot
WHERE run_id = 'trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1';

DELETE FROM common_trigger_run
WHERE run_id = 'trigger_context_snapshot_20260605_condition_layer_20260604_source_20260604_v1';

COMMIT;

-- Boundary proof:
-- - Does not touch N1 facts or active source versions.
-- - Does not touch N3 market data facts, subscriptions, snapshots, projections, or pull plans.
-- - Does not delete/update common_event_outbox, common_event_inbox, or common_event_consumer_checkpoint.
-- - Does not delete/update common_trigger_match or common_trigger_state.
-- - Does not delete/update N5/N6 facts.
-- - Does not delete/update stock/index/board_condition_basis, condition_pool, minute_target_scope, or condition_display_basis.
