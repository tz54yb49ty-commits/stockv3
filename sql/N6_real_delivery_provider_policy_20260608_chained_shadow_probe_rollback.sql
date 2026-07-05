BEGIN;

DO $$
DECLARE
  v_provider_policy_run_id CONSTANT TEXT := 'n6_real_delivery_provider_policy_20260608_chained_shadow_probe';
  v_source_projection_run_id CONSTANT TEXT := 'n4_n5_n6_chained_shadow_smoke_20260608_projection_probe';
  v_source_action_run_id CONSTANT TEXT := 'n4_n5_n6_chained_shadow_smoke_20260608_action_probe';
  v_noop_delivery_materialization_run_id CONSTANT TEXT := 'n6_delivery_noop_materialization_20260608_chained_shadow_probe';
  v_count BIGINT;
BEGIN
  IF current_setting('n6.real_provider.rollback_user_confirmed', true) IS DISTINCT FROM 'true' THEN
    RAISE EXCEPTION 'N6 real provider rollback blocked: no real provider execute was authorized by the contract gate. Set n6.real_provider.rollback_user_confirmed=true only in a separate approved rollback final gate.';
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE user_projection_run_id = v_source_projection_run_id
     AND source_action_run_id = v_source_action_run_id
     AND notification_source = 'n6_delivery_materialized_noop'
     AND projection_policy = 'noop_local_preview_materialized_no_delivery'
     AND notification_payload_json->>'delivery_materialization_run_id' = v_noop_delivery_materialization_run_id;

  IF v_count <> 50 THEN
    RAISE EXCEPTION 'N6 real provider rollback blocked: source noop preview rows changed, rows=%', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM common_event_outbox
   WHERE source_layer = 'N5_action'
     AND source_run_id = v_source_action_run_id
     AND status IN ('delivered', 'delivering');

  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 real provider rollback blocked: N5 outbox delivered/delivering refs exist, rows=%', v_count;
  END IF;

  RAISE EXCEPTION 'N6 real provider rollback blocked: provider_policy_run_id=% was contract-blocked and has no authorized provider delivery rows to delete', v_provider_policy_run_id;
END $$;

COMMIT;
