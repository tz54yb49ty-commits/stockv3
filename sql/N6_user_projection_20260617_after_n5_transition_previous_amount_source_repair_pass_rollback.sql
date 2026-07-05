-- N6 scoped rollback for stale N5 transition_previous_amount_source_repair projection.
--
-- Target projection_run_id:
--   v3_n6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_v1
-- Target source_action_run_id:
--   action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1
--
-- Scope:
--   Delete only N6/user projection rows for this target N6 projection run and source N5 action run.
--   Do not touch N4/N5 facts, outbox, inbox, checkpoint, scheduler, worker, delivery, sim,
--   position, order, trade, or old-system data.

BEGIN;

SET LOCAL n6.rollback_user_projection_run_id = 'v3_n6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_v1';
SET LOCAL n6.rollback_source_action_run_id = 'action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1';

DO $$
DECLARE
  v_run_id TEXT := current_setting('n6.rollback_user_projection_run_id', true);
  v_source_action_run_id TEXT := current_setting('n6.rollback_source_action_run_id', true);
  v_count BIGINT;
  v_deleted_queue INTEGER;
  v_deleted_cards INTEGER;
  v_deleted_projections INTEGER;
  v_deleted_runs INTEGER;
BEGIN
  IF v_run_id IS NULL OR btrim(v_run_id) = '' THEN
    RAISE EXCEPTION 'N6 rollback blocked: n6.rollback_user_projection_run_id is not set';
  END IF;

  IF v_source_action_run_id IS NULL OR btrim(v_source_action_run_id) = '' THEN
    RAISE EXCEPTION 'N6 rollback blocked: n6.rollback_source_action_run_id is not set';
  END IF;

  IF v_run_id <> 'v3_n6_user_projection_20260617_after_n5_transition_previous_amount_source_repair_pass_v1' THEN
    RAISE EXCEPTION 'N6 rollback blocked: unexpected projection run id %', v_run_id;
  END IF;

  IF v_source_action_run_id <> 'action_consumer_execute_20260617_until_1352_after_n4_transition_previous_amount_source_repair__trigger_action_confirmation_metric_execute_20260617_until_1352_transition_previous_amount_source_repair__condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1' THEN
    RAISE EXCEPTION 'N6 rollback blocked: unexpected source action run id %', v_source_action_run_id;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_projection_run
   WHERE user_projection_run_id = v_run_id
     AND source_action_run_id = v_source_action_run_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N6 rollback blocked: expected 1 scoped user_projection_run row, found %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_signal_projection
   WHERE user_projection_run_id = v_run_id
     AND source_action_run_id = v_source_action_run_id;
  IF v_count <> 22 THEN
    RAISE EXCEPTION 'N6 rollback blocked: expected 22 scoped user_signal_projection rows, found %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_signal_projection
   WHERE user_projection_run_id = v_run_id
     AND source_action_run_id = v_source_action_run_id
     AND source_payload_json::text LIKE '%' || v_source_action_run_id || '%';
  IF v_count <> 22 THEN
    RAISE EXCEPTION 'N6 rollback blocked: expected 22 source_payload_json refs, found %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_signal_card
   WHERE user_projection_run_id = v_run_id
     AND source_action_run_id = v_source_action_run_id;
  IF v_count <> 22 THEN
    RAISE EXCEPTION 'N6 rollback blocked: expected 22 scoped user_signal_card rows, found %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE user_projection_run_id = v_run_id
      OR source_action_run_id = v_source_action_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: expected 0 scoped user_notification_queue rows, found %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE (user_projection_run_id = v_run_id OR source_action_run_id = v_source_action_run_id)
     AND queue_status IN ('delivered', 'delivering', 'delivery_started', 'sent');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: delivered/delivering notification refs exist, rows=%', v_count;
  END IF;

  -- Hard-fail before the first DELETE if any downstream N6/voice/mobile/sim/position/order/trade refs exist.
  SELECT count(*) INTO v_count
    FROM user_signal_decision d
    JOIN user_signal_projection p
      ON p.user_signal_projection_id = d.user_signal_projection_id
   WHERE p.user_projection_run_id = v_run_id
     AND p.source_action_run_id = v_source_action_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: user_signal_decision refs exist, rows=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_order o
   WHERE o.sim_run_id = v_run_id
      OR o.user_signal_projection_id IN (
           SELECT user_signal_projection_id
             FROM user_signal_projection
            WHERE user_projection_run_id = v_run_id
              AND source_action_run_id = v_source_action_run_id
         );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: user_sim_order refs exist, rows=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_trade t
   WHERE t.sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: user_sim_trade refs exist, rows=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_sim_position p
   WHERE p.sim_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: user_sim_position refs exist, rows=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_position_event e
   WHERE e.source_action_event_id IN (
           SELECT source_action_event_id
             FROM user_signal_projection
            WHERE user_projection_run_id = v_run_id
              AND source_action_run_id = v_source_action_run_id
         );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: common_position_event refs exist, rows=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_position_state s
   WHERE s.source_action_event_id IN (
           SELECT source_action_event_id
             FROM user_signal_projection
            WHERE user_projection_run_id = v_run_id
              AND source_action_run_id = v_source_action_run_id
         );
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: common_position_state refs exist, rows=%', v_count;
  END IF;

  IF to_regclass('public.n6_virtual_order') IS NOT NULL THEN
    SELECT count(*) INTO v_count
      FROM n6_virtual_order o
     WHERE o.source_signal_projection_id IN (
             SELECT user_signal_projection_id
               FROM user_signal_projection
              WHERE user_projection_run_id = v_run_id
                AND source_action_run_id = v_source_action_run_id
           )
        OR o.source_action_event_id IN (
             SELECT source_action_event_id
               FROM user_signal_projection
              WHERE user_projection_run_id = v_run_id
                AND source_action_run_id = v_source_action_run_id
           );
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N6 rollback blocked: n6_virtual_order refs exist, rows=%', v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_pnl_snapshot') IS NOT NULL THEN
    SELECT count(*) INTO v_count
      FROM n6_virtual_pnl_snapshot p
     WHERE p.source_lineage_json::text LIKE '%' || v_run_id || '%'
        OR p.source_lineage_json::text LIKE '%' || v_source_action_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N6 rollback blocked: n6_virtual_pnl_snapshot refs exist, rows=%', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_event_delivery_attempt') IS NOT NULL THEN
    SELECT count(*) INTO v_count
      FROM common_event_delivery_attempt d
     WHERE d.outbox_id IN (
             SELECT outbox_id
               FROM common_event_outbox
              WHERE source_layer = 'N5_action'
                AND source_run_id = v_source_action_run_id
           );
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N6 rollback blocked: common_event_delivery_attempt refs exist, rows=%', v_count;
    END IF;
  END IF;

  DELETE FROM user_notification_queue
   WHERE user_projection_run_id = v_run_id
      OR source_action_run_id = v_source_action_run_id;
  GET DIAGNOSTICS v_deleted_queue = ROW_COUNT;

  DELETE FROM user_signal_card
   WHERE user_projection_run_id = v_run_id
     AND source_action_run_id = v_source_action_run_id;
  GET DIAGNOSTICS v_deleted_cards = ROW_COUNT;

  DELETE FROM user_signal_projection
   WHERE user_projection_run_id = v_run_id
     AND source_action_run_id = v_source_action_run_id;
  GET DIAGNOSTICS v_deleted_projections = ROW_COUNT;

  DELETE FROM user_projection_run
   WHERE user_projection_run_id = v_run_id
     AND source_action_run_id = v_source_action_run_id;
  GET DIAGNOSTICS v_deleted_runs = ROW_COUNT;

  IF v_deleted_queue <> 0 THEN
    RAISE EXCEPTION 'N6 rollback blocked: expected to delete 0 notification rows, deleted %', v_deleted_queue;
  END IF;
  IF v_deleted_cards <> 22 THEN
    RAISE EXCEPTION 'N6 rollback blocked: expected to delete 22 card rows, deleted %', v_deleted_cards;
  END IF;
  IF v_deleted_projections <> 22 THEN
    RAISE EXCEPTION 'N6 rollback blocked: expected to delete 22 projection rows, deleted %', v_deleted_projections;
  END IF;
  IF v_deleted_runs <> 1 THEN
    RAISE EXCEPTION 'N6 rollback blocked: expected to delete 1 projection run row, deleted %', v_deleted_runs;
  END IF;

  RAISE NOTICE 'N6 scoped rollback complete: run=%, source_action_run_id=%, queue=%, cards=%, projections=%, runs=%',
    v_run_id, v_source_action_run_id, v_deleted_queue, v_deleted_cards, v_deleted_projections, v_deleted_runs;
END $$;

COMMIT;
