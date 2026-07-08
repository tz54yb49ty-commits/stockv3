-- N5P active-monitor v2 additive schema rollback.
-- Scope: rollback only columns/indexes/constraints added by
-- N5_20260626_active_monitor_v2_additive_schema_migration.sql.
-- Boundary: schema rollback artifact only. Do not execute without an explicit
-- rollback gate. No runtime rows, no N4/N5 outbox update, no inbox/checkpoint
-- write, no N6, no worker, no voice/mobile/sim/position/order/real trade.

BEGIN;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.common_action_tracking_state
    WHERE (monitor_window_id is not null and monitor_window_id <> state_key)
       or trigger_type is not null
       or triggered_periods <> '[]'::jsonb
       or trigger_context_version is not null
       or last_seen_metric_key is not null
       or last_final_evaluated_metric_key is not null
    LIMIT 1
  ) THEN
    RAISE EXCEPTION 'rollback blocked: active-monitor v2 columns contain non-legacy data';
  END IF;
END $$;

DROP INDEX IF EXISTS public.idx_common_action_tracking_state_run_monitor_window;
DROP INDEX IF EXISTS public.idx_common_action_tracking_state_run_tracking_time;
DROP INDEX IF EXISTS public.idx_common_action_tracking_state_trade_identity_status;

ALTER TABLE public.common_action_tracking_state
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_run_monitor_window_uniq,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_monitor_window_id_not_empty_check,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_triggered_periods_array_check_v2,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_last_seen_metric_key_object_check,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_last_final_metric_key_object_check,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_trigger_type_check_v2,
  ALTER COLUMN monitor_window_id DROP NOT NULL,
  DROP COLUMN IF EXISTS monitor_window_id,
  DROP COLUMN IF EXISTS trigger_type,
  DROP COLUMN IF EXISTS triggered_periods,
  DROP COLUMN IF EXISTS trigger_context_version,
  DROP COLUMN IF EXISTS last_seen_metric_key,
  DROP COLUMN IF EXISTS last_final_evaluated_metric_key;

COMMIT;
