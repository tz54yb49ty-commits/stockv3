-- N5 full-day trigger-state closed-loop tracking runtime rollback draft.
-- Scope: delete only common_action_tracking_state rows for the exact
-- run_id/source_trigger_run_id pair below. Do not execute without a separate
-- rollback execute gate. This rollback does not touch N4 outbox, N5 action
-- facts/events/outbox, inbox/checkpoint, N6, voice/mobile/sim/position/order,
-- real trade, or old system tables.

DO $$
DECLARE
  target_action_run_id TEXT := 'action_consumer_dry_run_20260617_full_day_state_closed_loop__trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
  target_source_trigger_run_id TEXT := 'trigger_action_confirmation_metric_execute_20260617_full_day_after_n3_full_day_b2_pass__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';
  scoped_row_count BIGINT;
  wrong_source_row_count BIGINT;
BEGIN
  IF to_regclass('public.common_action_tracking_state') IS NULL THEN
    RAISE NOTICE 'common_action_tracking_state is absent; nothing to rollback';
    RETURN;
  END IF;

  SELECT COUNT(*) INTO wrong_source_row_count
  FROM common_action_tracking_state
  WHERE run_id = target_action_run_id
    AND source_trigger_run_id <> target_source_trigger_run_id;

  IF wrong_source_row_count <> 0 THEN
    RAISE EXCEPTION
      'tracking rollback blocked: % rows share target run_id but not target source_trigger_run_id',
      wrong_source_row_count;
  END IF;

  SELECT COUNT(*) INTO scoped_row_count
  FROM common_action_tracking_state
  WHERE run_id = target_action_run_id
    AND source_trigger_run_id = target_source_trigger_run_id;

  DELETE FROM common_action_tracking_state
  WHERE run_id = target_action_run_id
    AND source_trigger_run_id = target_source_trigger_run_id;

  RAISE NOTICE 'deleted % common_action_tracking_state rows for % / %',
    scoped_row_count,
    target_action_run_id,
    target_source_trigger_run_id;
END $$;

