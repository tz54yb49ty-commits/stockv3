-- N5 20260602 11:05 live action execute rollback.
-- Scope: action_run_id=action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1
-- Execute only after confirming N5 outbox rows for this action_run_id were not consumed by N6.

BEGIN;

DO $$
DECLARE
  downstream_refs bigint;
BEGIN
  SELECT COALESCE((SELECT count(*) FROM user_projection_run WHERE source_action_run_id = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1'), 0)
       + COALESCE((SELECT count(*) FROM user_signal_projection WHERE source_action_run_id = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1'), 0)
    INTO downstream_refs;
  IF downstream_refs > 0 THEN
    RAISE EXCEPTION 'Rollback blocked: downstream N6 refs exist for %', 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';
  END IF;
END $$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';

DELETE FROM common_action_event
WHERE run_id = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';

DELETE FROM stock_action_fact WHERE run_id = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';
DELETE FROM index_action_fact WHERE run_id = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';
DELETE FROM board_action_fact WHERE run_id = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';

DELETE FROM common_action_quality_item WHERE run_id = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';

DELETE FROM common_event_inbox
WHERE consumer_name = 'n5_action_consumer_v1'
  AND raw_json ->> 'action_run_id' = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';

DELETE FROM common_event_consumer_checkpoint
WHERE consumer_name = 'n5_action_consumer_v1'
  AND checkpoint_payload ->> 'action_run_id' = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';

DELETE FROM common_action_run WHERE run_id = 'action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1';

COMMIT;
