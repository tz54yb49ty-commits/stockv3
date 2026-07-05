-- Scoped rollback for N3P mixed realtime source payload run registration.
-- Execute only after an explicit rollback gate. This file is a frozen artifact,
-- not an authorization to rollback.

\set source_payload_run_id 'n3p_mixed_realtime_source_payload_20260629_until_1455_v1'

BEGIN;

DO $$
DECLARE
  source_run text := 'n3p_mixed_realtime_source_payload_20260629_until_1455_v1';
  ref_count bigint;
BEGIN
  SELECT count(*) INTO ref_count
  FROM common_event_outbox
  WHERE source_run_id = source_run
    AND status IN ('delivered', 'delivering');
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: delivered_or_delivering_outbox_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM common_event_inbox
  WHERE source_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: inbox_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%' || source_run || '%';
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: checkpoint_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM stock_action_confirmation_projection_metric
  WHERE source_snapshot_run_id = source_run
     OR source_today_minute_run_id = source_run
     OR source_previous_day_minute_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: stock_n3p_metric_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM index_action_confirmation_projection_metric
  WHERE source_snapshot_run_id = source_run
     OR source_today_minute_run_id = source_run
     OR source_previous_day_minute_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: index_n3p_metric_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM board_action_confirmation_projection_metric
  WHERE source_snapshot_run_id = source_run
     OR source_today_minute_run_id = source_run
     OR source_previous_day_minute_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: board_n3p_metric_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM common_trigger_run
  WHERE source_market_data_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: n4_trigger_run_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM common_trigger_state
  WHERE run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: n4_trigger_state_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM common_trigger_match
  WHERE run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: n4_trigger_match_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM common_action_event
  WHERE source_market_data_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: n5_action_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM user_projection_run
  WHERE source_action_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: user_projection_run_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM user_signal_projection
  WHERE source_action_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: user_signal_projection_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM user_signal_card
  WHERE source_action_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: user_signal_card_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM user_notification_queue
  WHERE source_action_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: user_notification_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM user_sim_order
  WHERE sim_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: user_sim_order_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM user_sim_trade
  WHERE sim_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: user_sim_trade_refs=%', ref_count;
  END IF;

  SELECT count(*) INTO ref_count
  FROM user_sim_position
  WHERE sim_run_id = source_run;
  IF ref_count <> 0 THEN
    RAISE EXCEPTION 'rollback_blocked: user_sim_position_refs=%', ref_count;
  END IF;
END $$;

DELETE FROM common_market_data_quality_item
WHERE run_id = :'source_payload_run_id';

DELETE FROM common_market_data_run
WHERE run_id = :'source_payload_run_id';

COMMIT;
