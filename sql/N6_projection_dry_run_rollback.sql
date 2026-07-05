-- N6 projection business rollback draft.
-- Do not execute without explicit user confirmation and a reviewed
-- user_projection_run_id.
--
-- Scope: rollback only N6 projection rows created by one future projection
-- execute run. Dry-run writes no rows and does not need this rollback.
--
-- Boundary: no N1-N5 mutation, no N5 outbox status update, no admin/profile
-- rollback, no session rollback, no watchlist rollback, no sim rollback,
-- no voice/mobile push rollback, and no real trade rollback.
--
-- Usage draft:
--   1. Review the target user_projection_run_id.
--   2. In this file, uncomment the SET LOCAL line below and replace the
--      placeholder.
--   3. Execute the file once under the reviewed N6 rollback gate.

BEGIN;

-- SET LOCAL n6.rollback_user_projection_run_id = '<reviewed_user_projection_run_id>';

DO $$
DECLARE
  v_run_id TEXT := current_setting('n6.rollback_user_projection_run_id', true);
  v_count BIGINT;
  v_deleted_notifications INTEGER;
  v_deleted_cards INTEGER;
  v_deleted_projections INTEGER;
  v_deleted_runs INTEGER;
BEGIN
  IF v_run_id IS NULL OR btrim(v_run_id) = '' THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: n6.rollback_user_projection_run_id is not set';
  END IF;

  SELECT count(*) INTO v_count
    FROM user_projection_run
   WHERE user_projection_run_id = v_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: expected 1 user_projection_run row for %, found %', v_run_id, v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_signal_decision d
    JOIN user_signal_projection p
      ON p.user_signal_projection_id = d.user_signal_projection_id
   WHERE p.user_projection_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_signal_decision has % rows for run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_order o
   WHERE o.sim_run_id = v_run_id
      OR o.user_signal_projection_id IN (
           SELECT user_signal_projection_id
             FROM user_signal_projection
            WHERE user_projection_run_id = v_run_id
         );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_sim_order has % rows linked to run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_trade
   WHERE sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_sim_trade has % rows linked to run %', v_count, v_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_position
   WHERE sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: user_sim_position has % rows linked to run %', v_count, v_run_id;
  END IF;

  DELETE FROM user_notification_queue
   WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

  DELETE FROM user_signal_card
   WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_cards = ROW_COUNT;

  DELETE FROM user_signal_projection
   WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_projections = ROW_COUNT;

  DELETE FROM user_projection_run
   WHERE user_projection_run_id = v_run_id;
  GET DIAGNOSTICS v_deleted_runs = ROW_COUNT;

  IF v_deleted_runs <> 1 THEN
    RAISE EXCEPTION 'N6 projection rollback blocked: expected to delete 1 projection run, deleted %', v_deleted_runs;
  END IF;

  RAISE NOTICE 'N6 projection rollback completed for %, notification_rows=%, card_rows=%, projection_rows=%, run_rows=%',
    v_run_id, v_deleted_notifications, v_deleted_cards, v_deleted_projections, v_deleted_runs;
END $$;

COMMIT;
