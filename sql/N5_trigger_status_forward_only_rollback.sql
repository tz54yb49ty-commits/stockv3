-- N5 trigger-status-forward-only exact rollback draft.
-- Required psql variables: action_run_id, source_trigger_run_id, consumer_name.
-- This draft deletes only pending/failed/dead-letter N5 status messages from
-- common_event_outbox. It never touches N4 or common_action_event.

BEGIN;

SET LOCAL n5.rollback_action_run_id = :'action_run_id';
SET LOCAL n5.rollback_source_trigger_run_id = :'source_trigger_run_id';
SET LOCAL n5.rollback_consumer_name = :'consumer_name';

DO $$
DECLARE
  v_action_run_id text := current_setting('n5.rollback_action_run_id');
  v_source_trigger_run_id text := current_setting('n5.rollback_source_trigger_run_id');
  v_consumer_name text := current_setting('n5.rollback_consumer_name');
  v_count bigint;
BEGIN
  IF v_action_run_id = '' OR v_source_trigger_run_id = '' OR v_consumer_name = '' THEN
    RAISE EXCEPTION 'N5 status rollback requires exact action/source/consumer scope';
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id
    AND event_type IN ('TriggerStatusUpdated', 'TriggerStatusInvalidated')
    AND payload_json ->> 'contract_version' = 'N5-N6-trigger-status-forward-v1'
    AND payload_json ->> 'message_role' = 'n6_trigger_status_projection_only'
    AND payload_json ->> 'source_trigger_run_id' = v_source_trigger_run_id
    AND payload_json #>> '{trace_json,consumer_name}' = v_consumer_name
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 status rollback blocked: scoped messages already delivering/delivered (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox inbox
  WHERE inbox.event_id IN (
    SELECT outbox.event_id
    FROM common_event_outbox outbox
    WHERE outbox.source_layer = 'N5_action'
      AND outbox.source_run_id = v_action_run_id
      AND outbox.event_type IN ('TriggerStatusUpdated', 'TriggerStatusInvalidated')
      AND outbox.payload_json ->> 'contract_version' = 'N5-N6-trigger-status-forward-v1'
      AND outbox.payload_json ->> 'message_role' = 'n6_trigger_status_projection_only'
      AND outbox.payload_json ->> 'source_trigger_run_id' = v_source_trigger_run_id
      AND outbox.payload_json #>> '{trace_json,consumer_name}' = v_consumer_name
  );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 status rollback blocked: scoped messages have downstream inbox refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_delivery_attempt attempt
  WHERE attempt.event_id IN (
    SELECT outbox.event_id
    FROM common_event_outbox outbox
    WHERE outbox.source_layer = 'N5_action'
      AND outbox.source_run_id = v_action_run_id
      AND outbox.event_type IN ('TriggerStatusUpdated', 'TriggerStatusInvalidated')
      AND outbox.payload_json ->> 'contract_version' = 'N5-N6-trigger-status-forward-v1'
      AND outbox.payload_json ->> 'message_role' = 'n6_trigger_status_projection_only'
      AND outbox.payload_json ->> 'source_trigger_run_id' = v_source_trigger_run_id
      AND outbox.payload_json #>> '{trace_json,consumer_name}' = v_consumer_name
  );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 status rollback blocked: scoped messages have delivery attempts (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_event action_event
  WHERE action_event.event_id IN (
    SELECT outbox.event_id
    FROM common_event_outbox outbox
    WHERE outbox.source_layer = 'N5_action'
      AND outbox.source_run_id = v_action_run_id
      AND outbox.event_type IN ('TriggerStatusUpdated', 'TriggerStatusInvalidated')
      AND outbox.payload_json ->> 'contract_version' = 'N5-N6-trigger-status-forward-v1'
      AND outbox.payload_json ->> 'message_role' = 'n6_trigger_status_projection_only'
      AND outbox.payload_json ->> 'source_trigger_run_id' = v_source_trigger_run_id
      AND outbox.payload_json #>> '{trace_json,consumer_name}' = v_consumer_name
  );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 status rollback blocked: status event leaked into common_action_event (%)', v_count;
  END IF;
END
$$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N5_action'
  AND source_run_id = current_setting('n5.rollback_action_run_id')
  AND event_type IN ('TriggerStatusUpdated', 'TriggerStatusInvalidated')
  AND payload_json ->> 'contract_version' = 'N5-N6-trigger-status-forward-v1'
  AND payload_json ->> 'message_role' = 'n6_trigger_status_projection_only'
  AND payload_json ->> 'source_trigger_run_id' = current_setting('n5.rollback_source_trigger_run_id')
  AND payload_json #>> '{trace_json,consumer_name}' = current_setting('n5.rollback_consumer_name')
  AND status IN ('pending', 'failed', 'dead_letter');

COMMIT;
