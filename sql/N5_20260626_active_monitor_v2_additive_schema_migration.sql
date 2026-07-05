-- N5P active-monitor v2 additive schema readiness migration.
-- Scope: alter only common_action_tracking_state for N5_action.
-- Boundary: additive schema only. Do not execute without an explicit schema
-- execute gate. No N5 runtime execute, no inbox/checkpoint consumption, no
-- outbox delivery, no worker, no rollback, no N6.
--
-- Compatibility contract:
-- - state_key remains the legacy-compatible persistence key for existing
--   run-once/upsert paths.
-- - monitor_window_id is added as the active-monitor v2 primary window key.
-- - This migration does not tighten stock/index/board_action_fact,
--   common_action_event, or legacy event compatibility constraints.

ALTER TABLE public.common_action_tracking_state
  ADD COLUMN IF NOT EXISTS monitor_window_id TEXT,
  ADD COLUMN IF NOT EXISTS trigger_type TEXT,
  ADD COLUMN IF NOT EXISTS triggered_periods JSONB NOT NULL DEFAULT '[]'::JSONB,
  ADD COLUMN IF NOT EXISTS trigger_context_version TEXT,
  ADD COLUMN IF NOT EXISTS last_seen_metric_key JSONB,
  ADD COLUMN IF NOT EXISTS last_final_evaluated_metric_key JSONB;

UPDATE public.common_action_tracking_state
SET monitor_window_id = state_key
WHERE monitor_window_id IS NULL
  AND state_key IS NOT NULL
  AND state_key <> '';

UPDATE public.common_action_tracking_state
SET trigger_type = CASE
  WHEN direction = 'buy' THEN 'BUY'
  WHEN direction = 'sell' THEN 'SELL'
  ELSE NULL
END
WHERE trigger_type IS NULL;

ALTER TABLE public.common_action_tracking_state
  ALTER COLUMN monitor_window_id SET NOT NULL;

ALTER TABLE public.common_action_tracking_state
  ADD CONSTRAINT common_action_tracking_state_monitor_window_id_not_empty_check
    CHECK (btrim(monitor_window_id) <> ''),
  ADD CONSTRAINT common_action_tracking_state_triggered_periods_array_check_v2
    CHECK (jsonb_typeof(triggered_periods) = 'array'),
  ADD CONSTRAINT common_action_tracking_state_last_seen_metric_key_object_check
    CHECK (
      last_seen_metric_key IS NULL
      OR jsonb_typeof(last_seen_metric_key) = 'object'
    ),
  ADD CONSTRAINT common_action_tracking_state_last_final_metric_key_object_check
    CHECK (
      last_final_evaluated_metric_key IS NULL
      OR jsonb_typeof(last_final_evaluated_metric_key) = 'object'
    ),
  ADD CONSTRAINT common_action_tracking_state_trigger_type_check_v2
    CHECK (
      trigger_type IN ('BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT')
    ),
  ADD CONSTRAINT common_action_tracking_state_run_monitor_window_uniq
    UNIQUE (run_id, monitor_window_id);

CREATE INDEX IF NOT EXISTS idx_common_action_tracking_state_run_monitor_window
ON public.common_action_tracking_state (run_id, monitor_window_id);

CREATE INDEX IF NOT EXISTS idx_common_action_tracking_state_run_tracking_time
ON public.common_action_tracking_state (run_id, tracking_status, latest_n4_event_time);

CREATE INDEX IF NOT EXISTS idx_common_action_tracking_state_trade_identity_status
ON public.common_action_tracking_state (trade_date, asset_kind, identity_key, tracking_status);
