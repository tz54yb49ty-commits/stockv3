-- N5P active-monitor v2 additive schema rollback.
-- Scope: rollback only the additive fields/constraints/indexes introduced by
-- N5_20260626_active_monitor_v2_additive_schema_migration.sql.
-- Boundary: do not execute without an explicit rollback gate. This rollback
-- must not be used after runtime code depends on the new columns.
--
-- Safety contract:
-- - Do not delete runtime rows.
-- - Do not drop common_action_tracking_state.
-- - Block rollback if new columns contain non-null/non-empty data that would be
--   silently lost.

DO $$
DECLARE
  blocking_rows BIGINT;
BEGIN
  IF to_regclass('public.common_action_tracking_state') IS NULL THEN
    RAISE NOTICE 'common_action_tracking_state is absent; nothing to rollback';
    RETURN;
  END IF;

  SELECT COUNT(*)
  INTO blocking_rows
  FROM public.common_action_tracking_state
  WHERE
    (monitor_window_id IS NOT NULL AND monitor_window_id <> state_key)
    OR trigger_type IS NOT NULL
    OR triggered_periods <> '[]'::JSONB
    OR trigger_context_version IS NOT NULL
    OR last_seen_metric_key IS NOT NULL
    OR last_final_evaluated_metric_key IS NOT NULL;

  IF blocking_rows > 0 THEN
    RAISE EXCEPTION
      'rollback blocked: % rows contain active-monitor v2 additive data in common_action_tracking_state',
      blocking_rows;
  END IF;
END $$;

DROP INDEX IF EXISTS public.idx_common_action_tracking_state_trade_identity_status;
DROP INDEX IF EXISTS public.idx_common_action_tracking_state_run_tracking_time;
DROP INDEX IF EXISTS public.idx_common_action_tracking_state_run_monitor_window;

ALTER TABLE public.common_action_tracking_state
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_run_monitor_window_uniq,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_trigger_type_check_v2,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_last_final_metric_key_object_check,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_last_seen_metric_key_object_check,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_triggered_periods_array_check_v2,
  DROP CONSTRAINT IF EXISTS common_action_tracking_state_monitor_window_id_not_empty_check;

ALTER TABLE public.common_action_tracking_state
  ALTER COLUMN monitor_window_id DROP NOT NULL;

ALTER TABLE public.common_action_tracking_state
  DROP COLUMN IF EXISTS last_final_evaluated_metric_key,
  DROP COLUMN IF EXISTS last_seen_metric_key,
  DROP COLUMN IF EXISTS trigger_context_version,
  DROP COLUMN IF EXISTS triggered_periods,
  DROP COLUMN IF EXISTS trigger_type,
  DROP COLUMN IF EXISTS monitor_window_id;
