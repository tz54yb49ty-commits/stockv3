-- N5 full metric union historical metadata repair rollback.
-- Scope: restore only payload metadata keys for action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1.
-- This rollback does not DELETE rows, does not touch N4/N3/N2/N6 facts, and does not consume outbox.

BEGIN;

\set action_run_id 'action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1'
\set source_trigger_run_id 'trigger_execute_20260605_condition_layer_20260604_source_20260604_v1'
\set repair_policy_version 'n5.full_metric_union_historical_metadata_repair.v1'

SET LOCAL n5.full_metric_union_metadata_repair_action_run_id = :'action_run_id';
SET LOCAL n5.full_metric_union_metadata_repair_policy_version = :'repair_policy_version';

-- Hard-fail guard: every check below runs before the first UPDATE.
DO $$
DECLARE
  v_action_run_id text := current_setting('n5.full_metric_union_metadata_repair_action_run_id');
  v_policy_version text := current_setting('n5.full_metric_union_metadata_repair_policy_version');
  v_count bigint := 0;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer='N5_action'
    AND source_run_id=v_action_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: N5 outbox delivered/delivering rows exist (%)', v_count;
  END IF;

  WITH scoped_events AS (
    SELECT event_id, partition_key FROM common_event_outbox WHERE source_layer='N5_action' AND source_run_id=v_action_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer='N5_action'
    AND source_run_id=v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: downstream inbox refs exist (%)', v_count;
  END IF;

  WITH scoped_events AS (
    SELECT event_id, partition_key FROM common_event_outbox WHERE source_layer='N5_action' AND source_run_id=v_action_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer='N5_action'
    AND partition_key IN (SELECT partition_key FROM scoped_events);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: downstream checkpoint refs exist (%)', v_count;
  END IF;

  WITH scoped_events AS (
    SELECT event_id FROM common_event_outbox WHERE source_layer='N5_action' AND source_run_id=v_action_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_delivery_attempt
  WHERE event_id IN (SELECT event_id FROM scoped_events);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: delivery refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_event
  WHERE run_id=v_action_run_id
    AND payload_json::jsonb ->> 'metric_union_policy_version' = v_policy_version
    AND NOT (payload_json::jsonb ? 'repair_trace');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: repaired payload missing repair_trace (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer='N5_action'
    AND source_run_id=v_action_run_id
    AND payload_json::jsonb ->> 'metric_union_policy_version' = v_policy_version
    AND NOT (payload_json::jsonb ? 'repair_trace');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: repaired outbox payload missing repair_trace (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM user_signal_projection
  WHERE source_action_run_id=v_action_run_id
    AND COALESCE(source_payload_json::text, '') LIKE '%' || v_policy_version || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: N6 projection already repaired from this metadata repair (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM user_signal_card
  WHERE source_action_run_id=v_action_run_id
    AND COALESCE(card_payload_json::text, '') LIKE '%' || v_policy_version || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: N6 card already repaired from this metadata repair (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM user_notification_queue
  WHERE source_action_run_id=v_action_run_id
    AND COALESCE(notification_payload_json::text, '') LIKE '%' || v_policy_version || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: notification refs from this repair exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_position_state
  WHERE run_id=v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: position state refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_position_event
  WHERE run_id=v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: position event refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM n6_virtual_order
  WHERE run_id=v_action_run_id OR COALESCE(source_lineage_json::text, '') LIKE '%' || v_policy_version || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: virtual order refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM n6_virtual_trade
  WHERE run_id=v_action_run_id OR COALESCE(source_lineage_json::text, '') LIKE '%' || v_policy_version || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: virtual trade refs exist (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM n6_virtual_position
  WHERE run_id=v_action_run_id OR COALESCE(source_lineage_json::text, '') LIKE '%' || v_policy_version || '%';
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 metadata repair rollback blocked: virtual position refs exist (%)', v_count;
  END IF;
END $$;

WITH restored AS (
  SELECT
    action_event_row_id,
    CASE
      WHEN payload_json::jsonb #>> '{repair_trace,previous_blocked_reason}' IS NULL
        OR payload_json::jsonb #>> '{repair_trace,previous_blocked_reason}' = ''
      THEN (payload_json::jsonb - 'blocked_reason')
      ELSE jsonb_set(payload_json::jsonb, '{blocked_reason}', to_jsonb(payload_json::jsonb #>> '{repair_trace,previous_blocked_reason}'), true)
    END AS restored_payload
  FROM common_action_event
  WHERE run_id = :'action_run_id'
    AND payload_json::jsonb ->> 'metric_union_policy_version' = :'repair_policy_version'
)
UPDATE common_action_event e
SET payload_json = r.restored_payload
  - 'action_confirmation_metric_run_refs'
  - 'metric_union_policy_version'
  - 'metric_union_source_runs'
  - 'metric_coverage_status'
  - 'metric_missing_resolved'
  - 'repair_trace'
FROM restored r
WHERE e.action_event_row_id = r.action_event_row_id;

WITH restored AS (
  SELECT
    outbox_id,
    CASE
      WHEN payload_json::jsonb #>> '{repair_trace,previous_blocked_reason}' IS NULL
        OR payload_json::jsonb #>> '{repair_trace,previous_blocked_reason}' = ''
      THEN (payload_json::jsonb - 'blocked_reason')
      ELSE jsonb_set(payload_json::jsonb, '{blocked_reason}', to_jsonb(payload_json::jsonb #>> '{repair_trace,previous_blocked_reason}'), true)
    END AS restored_payload
  FROM common_event_outbox
  WHERE source_layer='N5_action'
    AND source_run_id = :'action_run_id'
    AND payload_json::jsonb ->> 'metric_union_policy_version' = :'repair_policy_version'
)
UPDATE common_event_outbox o
SET payload_json = r.restored_payload
  - 'action_confirmation_metric_run_refs'
  - 'metric_union_policy_version'
  - 'metric_union_source_runs'
  - 'metric_coverage_status'
  - 'metric_missing_resolved'
  - 'repair_trace'
FROM restored r
WHERE o.outbox_id = r.outbox_id;

COMMIT;
