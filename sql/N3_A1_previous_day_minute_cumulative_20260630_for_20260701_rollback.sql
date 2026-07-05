-- Scoped rollback for N3-A1 previous-day cumulative amount materialization.
-- Execute only under an explicit rollback gate.
DO $$
DECLARE
  outbox_refs bigint;
  inbox_refs bigint;
  checkpoint_refs bigint;
  trigger_refs bigint;
  action_refs bigint;
BEGIN
  SELECT count(*) INTO outbox_refs
  FROM common_event_outbox
  WHERE source_run_id = 'previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1' OR payload_json::text LIKE '%previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1%';

  SELECT count(*) INTO inbox_refs
  FROM common_event_inbox
  WHERE source_run_id = 'previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1' OR payload_json::text LIKE '%previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1%';

  SELECT count(*) INTO checkpoint_refs
  FROM common_event_consumer_checkpoint
  WHERE checkpoint_payload::text LIKE '%previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1%';

  SELECT count(*) INTO trigger_refs
  FROM common_trigger_run
  WHERE source_market_data_run_id = 'previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1'
     OR raw_json::text LIKE '%previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1%';

  SELECT count(*) INTO action_refs
  FROM common_action_run
  WHERE raw_json::text LIKE '%previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1%';

  IF outbox_refs <> 0 OR inbox_refs <> 0 OR checkpoint_refs <> 0 OR trigger_refs <> 0 OR action_refs <> 0 THEN
    RAISE EXCEPTION 'blocked rollback for previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1: event refs exist';
  END IF;

  DELETE FROM stock_previous_day_minute_cumulative WHERE source_previous_day_minute_run_id = 'previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1';
  DELETE FROM index_previous_day_minute_cumulative WHERE source_previous_day_minute_run_id = 'previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1';
  DELETE FROM board_previous_day_minute_cumulative WHERE source_previous_day_minute_run_id = 'previous_day_minute_preload_20260630_for_20260701__market_data_subscription_20260701_condition_layer_20260630_source_20260630_for_20260701_v1';
END $$;
