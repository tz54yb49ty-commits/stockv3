-- N4->N5->N6 chained shadow smoke rollback guard.
--
-- Scope:
--   N5 action_run_id:
--     n4_n5_n6_chained_shadow_smoke_20260608_action_probe
--   N5 consumer:
--     n5_action_worker_v1_n4_n5_n6_chained_shadow_probe
--   N6 user_projection_run_id:
--     n4_n5_n6_chained_shadow_smoke_20260608_projection_probe
--
-- N4 leg policy for this contract:
--   read-only source preservation from
--   trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry
--   No N4 trigger rows are deleted by this rollback.
--
-- This file is intentionally guarded. Do not execute unless a separate
-- rollback final gate authorizes it.

DO $$
BEGIN
  RAISE EXCEPTION 'N4->N5->N6 chained shadow smoke rollback is disabled by default; remove this guard only after rollback final gate approval.';
END $$;

BEGIN;

-- Guard: N4 source outbox must not have been delivered or marked delivering.
DO $$
DECLARE
  v_count bigint;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = 'trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry'
    AND event_type = 'TriggerMatched'
    AND status IN ('delivered', 'delivering');

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: N4 source outbox delivered/delivering rows exist (%)', v_count;
  END IF;
END $$;

-- Guard: scoped N5 outbox rows must not have been delivered or marked delivering.
DO $$
DECLARE
  v_count bigint;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe'
    AND status IN ('delivered', 'delivering');

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: scoped N5 outbox delivered/delivering rows exist (%)', v_count;
  END IF;
END $$;

-- Guard: N6 projection run, if present, must point to the scoped N5 action run.
DO $$
DECLARE
  v_source_action_run_id text;
BEGIN
  IF EXISTS (
    SELECT 1
    FROM user_projection_run
    WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe'
  ) THEN
    SELECT source_action_run_id INTO v_source_action_run_id
    FROM user_projection_run
    WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';

    IF v_source_action_run_id IS DISTINCT FROM 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe' THEN
      RAISE EXCEPTION 'rollback blocked: N6 projection source_action_run_id mismatch (%)', v_source_action_run_id;
    END IF;
  END IF;
END $$;

-- Guard: no downstream user/delivery/sim/order/trade/position refs may point at this scoped chain.
DO $$
DECLARE
  v_count bigint := 0;
  v_tmp bigint := 0;
BEGIN
  IF to_regclass('user_signal_decision') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM user_signal_decision d
    JOIN user_signal_projection p ON p.user_signal_projection_id = d.user_signal_projection_id
    WHERE p.user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('user_notification_delivery') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM user_notification_delivery
    WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe'
       OR source_action_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('user_push_delivery') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM user_push_delivery
    WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe'
       OR source_action_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('user_voice_delivery') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM user_voice_delivery
    WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe'
       OR source_action_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('user_mobile_delivery') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM user_mobile_delivery
    WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe'
       OR source_action_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('common_position_state') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM common_position_state
    WHERE run_id IN (
      'n4_n5_n6_chained_shadow_smoke_20260608_action_probe',
      'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe'
    );
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('common_position_event') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM common_position_event
    WHERE run_id IN (
      'n4_n5_n6_chained_shadow_smoke_20260608_action_probe',
      'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe'
    )
       OR source_action_event_id IN (
         SELECT event_id
         FROM common_action_event
         WHERE run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe'
       );
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('user_sim_order') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM user_sim_order
    WHERE sim_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe'
       OR user_signal_projection_id IN (
         SELECT user_signal_projection_id
         FROM user_signal_projection
         WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe'
       );
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('user_sim_trade') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM user_sim_trade
    WHERE sim_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('user_sim_position') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM user_sim_position
    WHERE sim_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('common_order') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM common_order
    WHERE source_action_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';
    v_count := v_count + v_tmp;
  END IF;

  IF to_regclass('common_trade') IS NOT NULL THEN
    SELECT count(*) INTO v_tmp
    FROM common_trade
    WHERE source_action_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';
    v_count := v_count + v_tmp;
  END IF;

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'rollback blocked: downstream refs exist for chained shadow smoke (%)', v_count;
  END IF;
END $$;

-- Reverse-order rollback if authorized: N6 projection rows first.
DELETE FROM user_notification_queue
WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';

DELETE FROM user_signal_card
WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';

DELETE FROM user_signal_projection
WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';

DELETE FROM user_projection_run
WHERE user_projection_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';

-- Then scoped N5 action rows and N5 outbox rows.
DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = 'n5_action_worker_v1_n4_n5_n6_chained_shadow_probe';

DELETE FROM common_event_inbox
WHERE consumer_name = 'n5_action_worker_v1_n4_n5_n6_chained_shadow_probe'
  AND source_run_id = 'trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry';

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';

DELETE FROM common_action_event
WHERE run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';

DELETE FROM stock_action_fact
WHERE run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';

DELETE FROM index_action_fact
WHERE run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';

DELETE FROM board_action_fact
WHERE run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';

DELETE FROM common_action_quality_item
WHERE run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';

DELETE FROM common_action_run
WHERE run_id = 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';

COMMIT;
