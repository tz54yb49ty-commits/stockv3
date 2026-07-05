-- N6 full metric-union historical projection metadata repair rollback.
-- Scope: restore only N6 projection/card metadata for the 20260605 action projection repair.
-- This rollback does not DELETE projection/card rows and does not touch N5/N4/N3 facts or outbox.

BEGIN;

\set projection_run_id 'user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1'
\set action_run_id 'action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1'
\set repair_run_id 'n6_full_metric_union_historical_projection_repair_20260605_v1'
\set repair_policy_version 'n6.full_metric_union_historical_projection_repair.v1'

SET LOCAL n6.full_metric_union_projection_repair_projection_run_id = :'projection_run_id';
SET LOCAL n6.full_metric_union_projection_repair_action_run_id = :'action_run_id';
SET LOCAL n6.full_metric_union_projection_repair_run_id = :'repair_run_id';
SET LOCAL n6.full_metric_union_projection_repair_policy_version = :'repair_policy_version';

-- Hard-fail guard: every check below runs before the first UPDATE.
DO $$
DECLARE
  v_projection_run_id text := current_setting('n6.full_metric_union_projection_repair_projection_run_id');
  v_action_run_id text := current_setting('n6.full_metric_union_projection_repair_action_run_id');
  v_repair_run_id text := current_setting('n6.full_metric_union_projection_repair_run_id');
  v_policy_version text := current_setting('n6.full_metric_union_projection_repair_policy_version');
  v_count bigint := 0;
BEGIN
  SELECT count(*) INTO v_count
  FROM user_signal_projection
  WHERE user_projection_run_id = v_projection_run_id
    AND source_action_run_id = v_action_run_id
    AND trace_json::jsonb #>> '{repair_trace,repair_run_id}' = v_repair_run_id
    AND trace_json::jsonb #>> '{repair_trace,policy_version}' = v_policy_version;
  IF v_count <> 289 THEN
    RAISE EXCEPTION 'N6 metadata repair rollback blocked: expected 289 repaired projection rows, found %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM user_signal_card
  WHERE user_projection_run_id = v_projection_run_id
    AND source_action_run_id = v_action_run_id
    AND trace_json::jsonb #>> '{repair_trace,repair_run_id}' = v_repair_run_id
    AND trace_json::jsonb #>> '{repair_trace,policy_version}' = v_policy_version;
  IF v_count <> 289 THEN
    RAISE EXCEPTION 'N6 metadata repair rollback blocked: expected 289 repaired card rows, found %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM user_notification_queue
  WHERE source_action_run_id = v_action_run_id
    AND (
      COALESCE(notification_payload_json::text, '') LIKE '%' || v_policy_version || '%'
      OR COALESCE(trace_json::text, '') LIKE '%' || v_policy_version || '%'
    );
  IF v_count > 0 THEN
    RAISE EXCEPTION 'N6 metadata repair rollback blocked: notification_queue refs exist (%)', v_count;
  END IF;

  IF to_regclass('public.user_signal_decision') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM user_signal_decision WHERE user_signal_projection_id IN (SELECT user_signal_projection_id FROM user_signal_projection WHERE user_projection_run_id = $1)'
      INTO v_count
      USING v_projection_run_id;
    IF v_count > 0 THEN
      RAISE EXCEPTION 'N6 metadata repair rollback blocked: decision refs exist (%)', v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_order') IS NOT NULL THEN
    SELECT count(*) INTO v_count
    FROM n6_virtual_order
    WHERE COALESCE(source_lineage_json::text, '') LIKE '%' || v_policy_version || '%'
       OR COALESCE(source_lineage_json::text, '') LIKE '%' || v_action_run_id || '%';
    IF v_count > 0 THEN
      RAISE EXCEPTION 'N6 metadata repair rollback blocked: virtual order refs exist (%)', v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_trade') IS NOT NULL THEN
    SELECT count(*) INTO v_count
    FROM n6_virtual_trade
    WHERE COALESCE(source_lineage_json::text, '') LIKE '%' || v_policy_version || '%'
       OR COALESCE(source_lineage_json::text, '') LIKE '%' || v_action_run_id || '%';
    IF v_count > 0 THEN
      RAISE EXCEPTION 'N6 metadata repair rollback blocked: virtual trade refs exist (%)', v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_position') IS NOT NULL THEN
    SELECT count(*) INTO v_count
    FROM n6_virtual_position
    WHERE COALESCE(source_lineage_json::text, '') LIKE '%' || v_policy_version || '%'
       OR COALESCE(source_lineage_json::text, '') LIKE '%' || v_action_run_id || '%';
    IF v_count > 0 THEN
      RAISE EXCEPTION 'N6 metadata repair rollback blocked: virtual position refs exist (%)', v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_pnl_snapshot') IS NOT NULL THEN
    SELECT count(*) INTO v_count
    FROM n6_virtual_pnl_snapshot
    WHERE COALESCE(source_lineage_json::text, '') LIKE '%' || v_policy_version || '%'
       OR COALESCE(source_lineage_json::text, '') LIKE '%' || v_action_run_id || '%';
    IF v_count > 0 THEN
      RAISE EXCEPTION 'N6 metadata repair rollback blocked: virtual pnl refs exist (%)', v_count;
    END IF;
  END IF;
END $$;

WITH restored AS (
  SELECT
    user_signal_projection_id,
    trace_json::jsonb #>> '{repair_trace,previous_metadata,source_payload_blocked_reason}' AS previous_source_payload_blocked_reason,
    trace_json::jsonb #>> '{repair_trace,previous_metadata,projection_trace_blocked_reason}' AS previous_trace_blocked_reason
  FROM user_signal_projection
  WHERE user_projection_run_id = :'projection_run_id'
    AND source_action_run_id = :'action_run_id'
    AND trace_json::jsonb #>> '{repair_trace,repair_run_id}' = :'repair_run_id'
    AND trace_json::jsonb #>> '{repair_trace,policy_version}' = :'repair_policy_version'
)
UPDATE user_signal_projection p
SET source_payload_json = CASE
      WHEN r.previous_source_payload_blocked_reason IS NULL OR r.previous_source_payload_blocked_reason = ''
      THEN p.source_payload_json::jsonb #- '{payload_json,blocked_reason}'
      ELSE jsonb_set(p.source_payload_json::jsonb, '{payload_json,blocked_reason}', to_jsonb(r.previous_source_payload_blocked_reason), true)
    END #- '{payload_json,action_confirmation_metric_run_refs}'
        #- '{payload_json,metric_union_policy_version}'
        #- '{payload_json,metric_union_source_runs}'
        #- '{payload_json,metric_coverage_status}'
        #- '{payload_json,metric_missing_resolved}'
        #- '{payload_json,n6_projection_repair_trace}',
    trace_json = CASE
      WHEN r.previous_trace_blocked_reason IS NULL OR r.previous_trace_blocked_reason = ''
      THEN p.trace_json::jsonb - 'blocked_reason'
      ELSE jsonb_set(p.trace_json::jsonb, '{blocked_reason}', to_jsonb(r.previous_trace_blocked_reason), true)
    END
      - 'action_confirmation_metric_run_refs'
      - 'metric_union_policy_version'
      - 'metric_union_source_runs'
      - 'metric_coverage_status'
      - 'metric_missing_resolved'
      - 'repair_trace'
FROM restored r
WHERE p.user_signal_projection_id = r.user_signal_projection_id;

WITH restored AS (
  SELECT
    user_signal_card_id,
    trace_json::jsonb #>> '{repair_trace,previous_metadata,card_payload_blocked_reason}' AS previous_card_payload_blocked_reason,
    trace_json::jsonb #>> '{repair_trace,previous_metadata,card_trace_blocked_reason}' AS previous_trace_blocked_reason
  FROM user_signal_card
  WHERE user_projection_run_id = :'projection_run_id'
    AND source_action_run_id = :'action_run_id'
    AND trace_json::jsonb #>> '{repair_trace,repair_run_id}' = :'repair_run_id'
    AND trace_json::jsonb #>> '{repair_trace,policy_version}' = :'repair_policy_version'
)
UPDATE user_signal_card c
SET card_payload_json = CASE
      WHEN r.previous_card_payload_blocked_reason IS NULL OR r.previous_card_payload_blocked_reason = ''
      THEN c.card_payload_json::jsonb - 'blocked_reason'
      ELSE jsonb_set(c.card_payload_json::jsonb, '{blocked_reason}', to_jsonb(r.previous_card_payload_blocked_reason), true)
    END
      - 'action_confirmation_metric_run_refs'
      - 'metric_union_policy_version'
      - 'metric_union_source_runs'
      - 'metric_coverage_status'
      - 'metric_missing_resolved'
      - 'n6_projection_repair_trace',
    trace_json = CASE
      WHEN r.previous_trace_blocked_reason IS NULL OR r.previous_trace_blocked_reason = ''
      THEN c.trace_json::jsonb - 'blocked_reason'
      ELSE jsonb_set(c.trace_json::jsonb, '{blocked_reason}', to_jsonb(r.previous_trace_blocked_reason), true)
    END
      - 'action_confirmation_metric_run_refs'
      - 'metric_union_policy_version'
      - 'metric_union_source_runs'
      - 'metric_coverage_status'
      - 'metric_missing_resolved'
      - 'repair_trace'
FROM restored r
WHERE c.user_signal_card_id = r.user_signal_card_id;

COMMIT;
