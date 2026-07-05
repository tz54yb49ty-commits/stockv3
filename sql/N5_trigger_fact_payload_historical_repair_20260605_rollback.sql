-- N5 trigger fact payload historical repair rollback.
-- Scope:
--   action_run_id: action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
--   source_trigger_run_id: trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
-- Boundary:
--   Reverts only payload passthrough keys added by the N5 historical payload repair.
--   It does not delete rows, does not touch N4/N3/N2 facts, does not touch N6/user
--   projection/card rows, and does not consume or update outbox status.

BEGIN;

\set action_run_id 'action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1'
\set source_trigger_run_id 'trigger_execute_20260605_condition_layer_20260604_source_20260604_v1'

SET LOCAL n5.payload_repair_action_run_id = :'action_run_id';
SET LOCAL n5.payload_repair_source_trigger_run_id = :'source_trigger_run_id';

-- Hard-fail guard: every check below runs before the first UPDATE.
DO $$
DECLARE
  v_action_run_id text := current_setting('n5.payload_repair_action_run_id');
  v_count bigint := 0;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 payload repair rollback blocked: scoped N5 outbox has delivered/delivering rows (%)', v_count;
  END IF;

  WITH scoped_n5_event_ids AS (
    SELECT event_id FROM common_event_outbox WHERE source_layer = 'N5_action' AND source_run_id = v_action_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_delivery_attempt
  WHERE event_id IN (SELECT event_id FROM scoped_n5_event_ids);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 payload repair rollback blocked: scoped N5 outbox has delivery attempt refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id;
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 payload repair rollback blocked: scoped N5 outbox has downstream inbox refs (%)', v_count;
  END IF;

  WITH scoped_n5_partitions AS (
    SELECT DISTINCT partition_key FROM common_event_outbox WHERE source_layer = 'N5_action' AND source_run_id = v_action_run_id
  )
  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N5_action'
    AND partition_key IN (SELECT partition_key FROM scoped_n5_partitions);
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 payload repair rollback blocked: scoped N5 outbox has downstream checkpoint refs (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_event
  WHERE run_id = v_action_run_id
    AND NOT (
      payload_json::jsonb ? 'n4_trigger_event_id'
      AND payload_json::jsonb ? 'trigger_price'
      AND payload_json::jsonb ? 'triggered_periods'
      AND payload_json::jsonb ? 'all_trigger_periods'
      AND payload_json::jsonb ? 'primary_trigger_period'
      AND payload_json::jsonb ? 'trigger_kind'
      AND payload_json::jsonb ? 'period_trigger_baseline_trace'
      AND payload_json::jsonb ? 'baseline_source'
    );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 payload repair rollback blocked: common_action_event payload is not fully repaired (%)', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N5_action'
    AND source_run_id = v_action_run_id
    AND NOT (
      payload_json::jsonb ? 'n4_trigger_event_id'
      AND payload_json::jsonb ? 'trigger_price'
      AND payload_json::jsonb ? 'triggered_periods'
      AND payload_json::jsonb ? 'all_trigger_periods'
      AND payload_json::jsonb ? 'primary_trigger_period'
      AND payload_json::jsonb ? 'trigger_kind'
      AND payload_json::jsonb ? 'period_trigger_baseline_trace'
      AND payload_json::jsonb ? 'baseline_source'
    );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N5 payload repair rollback blocked: N5 outbox payload is not fully repaired (%)', v_count;
  END IF;
END $$;

UPDATE common_action_event
SET payload_json = payload_json::jsonb
  - 'n4_trigger_event_id'
  - 'trigger_price'
  - 'triggered_periods'
  - 'all_trigger_periods'
  - 'primary_trigger_period'
  - 'trigger_kind'
  - 'period_trigger_baseline_trace'
  - 'baseline_source'
WHERE run_id = :'action_run_id';

UPDATE common_event_outbox
SET payload_json = payload_json::jsonb
  - 'n4_trigger_event_id'
  - 'trigger_price'
  - 'triggered_periods'
  - 'all_trigger_periods'
  - 'primary_trigger_period'
  - 'trigger_kind'
  - 'period_trigger_baseline_trace'
  - 'baseline_source'
WHERE source_layer = 'N5_action'
  AND source_run_id = :'action_run_id';

COMMIT;
