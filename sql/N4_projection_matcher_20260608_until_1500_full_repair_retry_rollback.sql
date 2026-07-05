-- N4 projection matcher FULL repair retry rollback draft.
-- Target run:
--   trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry
--
-- This rollback is intentionally guarded and must not be run as-is. It preserves
-- N1/N2/N3 facts, older N4 lineage, and all N5/N6/user/sim/order/trade facts.

BEGIN;

DO $$
DECLARE
  v_run_id text := 'trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry';
  v_consumer_name text := 'n4_projection_matcher_consumer_v1_until_1500_full_repair_retry';
  v_count bigint;
BEGIN
  SELECT count(*)
    INTO v_count
    FROM common_event_outbox
   WHERE source_layer = 'N4_trigger'
     AND source_run_id = v_run_id
     AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: delivered/delivering outbox rows exist for % (% rows)', v_run_id, v_count;
  END IF;

  SELECT count(*)
    INTO v_count
    FROM common_action_run
   WHERE source_trigger_run_id = v_run_id
      OR run_id LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: N5 common_action_run refs exist for % (% rows)', v_run_id, v_count;
  END IF;

  SELECT count(*)
    INTO v_count
    FROM common_action_event
   WHERE source_trigger_run_id = v_run_id
      OR run_id LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 rollback blocked: N5 common_action_event refs exist for % (% rows)', v_run_id, v_count;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_projection WHERE row_to_json(user_signal_projection)::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: user_signal_projection refs exist for % (% rows)', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_card') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_card WHERE row_to_json(user_signal_card)::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: user_signal_card refs exist for % (% rows)', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_notification_queue') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_notification_queue WHERE row_to_json(user_notification_queue)::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: user_notification_queue refs exist for % (% rows)', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_order') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_sim_order WHERE row_to_json(user_sim_order)::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: user_sim_order refs exist for % (% rows)', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_trade') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_sim_trade WHERE row_to_json(user_sim_trade)::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: user_sim_trade refs exist for % (% rows)', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.user_sim_position') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_sim_position WHERE row_to_json(user_sim_position)::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: user_sim_position refs exist for % (% rows)', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_order') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_order WHERE row_to_json(n6_virtual_order)::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: n6_virtual_order refs exist for % (% rows)', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_trade') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_trade WHERE row_to_json(n6_virtual_trade)::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: n6_virtual_trade refs exist for % (% rows)', v_run_id, v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_position') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM n6_virtual_position WHERE row_to_json(n6_virtual_position)::text LIKE $1'
      INTO v_count
      USING '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 rollback blocked: n6_virtual_position refs exist for % (% rows)', v_run_id, v_count;
    END IF;
  END IF;

  RAISE EXCEPTION 'N4 projection matcher rollback is hard-failed by default. Review guards, remove this hard-fail intentionally, and rerun only if scoped rollback is approved for % / %.', v_run_id, v_consumer_name;
END $$;

-- Safety preview.
SELECT event_type, status, count(*) AS row_count
FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry'
GROUP BY event_type, status
ORDER BY event_type, status;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = 'trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry';

DELETE FROM common_trigger_match
WHERE run_id = 'trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry';

DELETE FROM common_trigger_state
WHERE run_id = 'trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry';

DELETE FROM common_trigger_quality_item
WHERE run_id = 'trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry';

DELETE FROM common_event_inbox
WHERE consumer_name = 'n4_projection_matcher_consumer_v1_until_1500_full_repair_retry'
  AND raw_json ->> 'execute_run_id' = 'trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = 'n4_projection_matcher_consumer_v1_until_1500_full_repair_retry'
  AND source_layer = 'N3_market_data'
  AND checkpoint_payload ->> 'execute_run_id' = 'trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry';

DELETE FROM common_trigger_run
WHERE run_id = 'trigger_projection_matcher_execute_20260608_until_1500_full_repair_retry';

COMMIT;
