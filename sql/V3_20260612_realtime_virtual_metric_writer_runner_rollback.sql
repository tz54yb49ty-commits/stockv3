\set target_run_id 'action_confirmation_projection_metric_20260612_realtime_virtual_metric_new_plan__condition_layer_20260611_source_20260611_for_20260612_v1'

DO $$
BEGIN
  IF current_setting('ashare_v3.allow_v3_20260612_realtime_virtual_metric_writer_rollback', true) <> 'true' THEN
    RAISE EXCEPTION 'v3 realtime virtual metric writer rollback blocked by default; set reviewed session flag after final gate approval';
  END IF;
END $$;

BEGIN;

SET LOCAL ashare_v3.rollback_target_run_id = :'target_run_id';

DO $$
DECLARE
  target_run_id text := current_setting('ashare_v3.rollback_target_run_id');
  refs bigint := 0;
BEGIN
  IF to_regclass('public.common_event_outbox') IS NOT NULL THEN
    SELECT count(*) INTO refs
    FROM common_event_outbox
    WHERE source_run_id = target_run_id
       OR payload_json::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN
      RAISE EXCEPTION 'rollback blocked: common_event_outbox refs=%', refs;
    END IF;
  END IF;

  IF to_regclass('public.common_event_inbox') IS NOT NULL THEN
    SELECT count(*) INTO refs
    FROM common_event_inbox
    WHERE payload_json::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN
      RAISE EXCEPTION 'rollback blocked: common_event_inbox refs=%', refs;
    END IF;
  END IF;

  IF to_regclass('public.common_event_consumer_checkpoint') IS NOT NULL THEN
    SELECT count(*) INTO refs
    FROM common_event_consumer_checkpoint
    WHERE consumer_name::text LIKE '%' || target_run_id || '%'
       OR last_event_id::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN
      RAISE EXCEPTION 'rollback blocked: common_event_consumer_checkpoint refs=%', refs;
    END IF;
  END IF;

  IF to_regclass('public.common_trigger_match') IS NOT NULL THEN
    SELECT count(*) INTO refs
    FROM common_trigger_match
    WHERE row_to_json(common_trigger_match)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN
      RAISE EXCEPTION 'rollback blocked: common_trigger_match refs=%', refs;
    END IF;
  END IF;

  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    SELECT count(*) INTO refs
    FROM common_action_event
    WHERE row_to_json(common_action_event)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN
      RAISE EXCEPTION 'rollback blocked: common_action_event refs=%', refs;
    END IF;
  END IF;

  IF to_regclass('public.user_signal_projection') IS NOT NULL THEN
    SELECT count(*) INTO refs
    FROM user_signal_projection
    WHERE row_to_json(user_signal_projection)::text LIKE '%' || target_run_id || '%';
    IF refs > 0 THEN
      RAISE EXCEPTION 'rollback blocked: user_signal_projection refs=%', refs;
    END IF;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM common_market_data_run
    WHERE run_id = target_run_id
      AND (downstream_layers_touched IS TRUE OR worker_started IS TRUE)
  ) THEN
    RAISE EXCEPTION 'rollback blocked: downstream_layers_touched or worker_started is true';
  END IF;
END $$;

DELETE FROM stock_action_confirmation_projection_metric
WHERE projection_run_id = current_setting('ashare_v3.rollback_target_run_id');

DELETE FROM index_action_confirmation_projection_metric
WHERE projection_run_id = current_setting('ashare_v3.rollback_target_run_id');

DELETE FROM board_action_confirmation_projection_metric
WHERE projection_run_id = current_setting('ashare_v3.rollback_target_run_id');

DELETE FROM common_market_data_quality_item
WHERE run_id = current_setting('ashare_v3.rollback_target_run_id');

DELETE FROM common_market_data_run
WHERE run_id = current_setting('ashare_v3.rollback_target_run_id');

COMMIT;
