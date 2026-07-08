-- N5 active-monitor v2 unified N4 trigger events rollback.
-- Scope: target only the 20260626 provisional active-monitor v2 action run
-- and its two source trigger runs. This artifact is rollback-readiness SQL;
-- do not execute without an explicit rollback gate and current DB preflight.
--
-- Target action run:
-- action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1
--
-- Source trigger runs:
-- trigger_provisional_ordinary_20260626_until_1447__realtime_action_confirmation_metric_20260626_until_1447__asset_all__live_current_1m_amount_chain_v2_unified_payload_v1__atomic_rule_v1
-- trigger_provisional_b2_20260626_until_1447__realtime_projection_metric_20260626_until_1447__live_current_1m_unified_payload_v1__atomic_rule_v1
--
-- Boundaries: no N4 outbox status update, no user projection, no sim, no N6,
-- no worker, no voice/mobile/order/real trade.

BEGIN;

DO $$
DECLARE
  v_action_run_id TEXT := 'action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1';
  v_ordinary_trigger_run_id TEXT := 'trigger_provisional_ordinary_20260626_until_1447__realtime_action_confirmation_metric_20260626_until_1447__asset_all__live_current_1m_amount_chain_v2_unified_payload_v1__atomic_rule_v1';
  v_b2_trigger_run_id TEXT := 'trigger_provisional_b2_20260626_until_1447__realtime_projection_metric_20260626_until_1447__live_current_1m_unified_payload_v1__atomic_rule_v1';
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.common_event_inbox
    WHERE status IN ('delivering', 'delivered')
      AND consumer_name LIKE 'n5%'
      AND source_layer = 'N4_trigger'
      AND (
        source_run_id = v_ordinary_trigger_run_id
        OR source_run_id = v_b2_trigger_run_id
        OR payload_json::TEXT LIKE '%' || v_action_run_id || '%'
        OR payload_json::TEXT LIKE '%' || v_ordinary_trigger_run_id || '%'
        OR payload_json::TEXT LIKE '%' || v_b2_trigger_run_id || '%'
        OR raw_json::TEXT LIKE '%' || v_action_run_id || '%'
        OR raw_json::TEXT LIKE '%' || v_ordinary_trigger_run_id || '%'
        OR raw_json::TEXT LIKE '%' || v_b2_trigger_run_id || '%'
      )
    LIMIT 1
  ) THEN
    RAISE EXCEPTION 'rollback blocked: common_event_inbox has delivering/delivered rows for active-monitor v2 target';
  END IF;
END $$;

WITH target AS (
  SELECT
    'action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1'::TEXT AS action_run_id,
    'trigger_provisional_ordinary_20260626_until_1447__realtime_action_confirmation_metric_20260626_until_1447__asset_all__live_current_1m_amount_chain_v2_unified_payload_v1__atomic_rule_v1'::TEXT AS ordinary_trigger_run_id,
    'trigger_provisional_b2_20260626_until_1447__realtime_projection_metric_20260626_until_1447__live_current_1m_unified_payload_v1__atomic_rule_v1'::TEXT AS b2_trigger_run_id
)
DELETE FROM public.common_event_consumer_checkpoint checkpoint
USING target
WHERE checkpoint.consumer_name LIKE 'n5%'
  AND checkpoint.source_layer = 'N4_trigger'
  AND (
    checkpoint.checkpoint_payload::TEXT LIKE '%' || target.action_run_id || '%'
    OR checkpoint.checkpoint_payload::TEXT LIKE '%' || target.ordinary_trigger_run_id || '%'
    OR checkpoint.checkpoint_payload::TEXT LIKE '%' || target.b2_trigger_run_id || '%'
    OR checkpoint.last_event_id LIKE '%' || target.action_run_id || '%'
    OR checkpoint.last_event_id LIKE '%' || target.ordinary_trigger_run_id || '%'
    OR checkpoint.last_event_id LIKE '%' || target.b2_trigger_run_id || '%'
  );

WITH target AS (
  SELECT
    'action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1'::TEXT AS action_run_id,
    'trigger_provisional_ordinary_20260626_until_1447__realtime_action_confirmation_metric_20260626_until_1447__asset_all__live_current_1m_amount_chain_v2_unified_payload_v1__atomic_rule_v1'::TEXT AS ordinary_trigger_run_id,
    'trigger_provisional_b2_20260626_until_1447__realtime_projection_metric_20260626_until_1447__live_current_1m_unified_payload_v1__atomic_rule_v1'::TEXT AS b2_trigger_run_id
)
DELETE FROM public.common_event_inbox inbox
USING target
WHERE inbox.status NOT IN ('delivering', 'delivered')
  AND inbox.consumer_name LIKE 'n5%'
  AND inbox.source_layer = 'N4_trigger'
  AND (
    inbox.source_run_id = target.ordinary_trigger_run_id
    OR inbox.source_run_id = target.b2_trigger_run_id
    OR inbox.payload_json::TEXT LIKE '%' || target.action_run_id || '%'
    OR inbox.payload_json::TEXT LIKE '%' || target.ordinary_trigger_run_id || '%'
    OR inbox.payload_json::TEXT LIKE '%' || target.b2_trigger_run_id || '%'
    OR inbox.raw_json::TEXT LIKE '%' || target.action_run_id || '%'
    OR inbox.raw_json::TEXT LIKE '%' || target.ordinary_trigger_run_id || '%'
    OR inbox.raw_json::TEXT LIKE '%' || target.b2_trigger_run_id || '%'
  );

WITH target AS (
  SELECT
    'action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1'::TEXT AS action_run_id,
    'trigger_provisional_ordinary_20260626_until_1447__realtime_action_confirmation_metric_20260626_until_1447__asset_all__live_current_1m_amount_chain_v2_unified_payload_v1__atomic_rule_v1'::TEXT AS ordinary_trigger_run_id,
    'trigger_provisional_b2_20260626_until_1447__realtime_projection_metric_20260626_until_1447__live_current_1m_unified_payload_v1__atomic_rule_v1'::TEXT AS b2_trigger_run_id
)
DELETE FROM public.common_event_outbox outbox
USING target
WHERE outbox.source_layer = 'N5_action'
  AND outbox.source_run_id = target.action_run_id;

WITH target AS (
  SELECT 'action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1'::TEXT AS action_run_id
)
DELETE FROM public.common_action_event event
USING target
WHERE event.run_id = target.action_run_id;

WITH target AS (
  SELECT 'action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1'::TEXT AS action_run_id
)
DELETE FROM public.stock_action_fact fact
USING target
WHERE fact.run_id = target.action_run_id;

WITH target AS (
  SELECT 'action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1'::TEXT AS action_run_id
)
DELETE FROM public.index_action_fact fact
USING target
WHERE fact.run_id = target.action_run_id;

WITH target AS (
  SELECT 'action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1'::TEXT AS action_run_id
)
DELETE FROM public.board_action_fact fact
USING target
WHERE fact.run_id = target.action_run_id;

WITH target AS (
  SELECT 'action_provisional_active_monitor_v2_20260626_until_1447__unified_n4_trigger_events_live_current_v1'::TEXT AS action_run_id
)
DELETE FROM public.common_action_tracking_state state
USING target
WHERE state.run_id = target.action_run_id;

COMMIT;
