-- N5 full-day trigger-state closed-loop tracking schema migration draft.
-- Scope: create only common_action_tracking_state for N5_action.
-- Boundary: additive schema only. Do not execute without an explicit schema
-- execute gate. No runtime rows, no N4 outbox status change, no inbox/checkpoint
-- write, no N6, no worker, no voice/mobile/sim/position/order/real trade.

CREATE TABLE IF NOT EXISTS common_action_tracking_state (
  tracking_state_row_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL,
  source_trigger_run_id TEXT NOT NULL,
  source_trigger_state_id BIGINT,
  source_trigger_event_id TEXT,
  source_trigger_event_type TEXT NOT NULL,
  source_trigger_match_id BIGINT,
  trade_date TEXT NOT NULL,
  state_key TEXT NOT NULL,
  asset_kind TEXT NOT NULL,
  identity_key TEXT NOT NULL,
  direction TEXT NOT NULL,
  signal_type TEXT NOT NULL,
  condition_key TEXT NOT NULL,
  trigger_live BOOLEAN NOT NULL DEFAULT false,
  current_status TEXT,
  primary_trigger_period TEXT,
  all_trigger_periods JSONB NOT NULL DEFAULT '[]'::JSONB,
  trigger_mark_candidate TEXT,
  latest_n4_event_id TEXT,
  latest_n4_event_type TEXT NOT NULL,
  latest_n4_event_time TIMESTAMPTZ,
  action_state TEXT NOT NULL,
  confirmation_status TEXT,
  tracking_status TEXT NOT NULL,
  planned_output_event_type TEXT,
  expired_reason TEXT,
  expired_at TIMESTAMPTZ,
  tracking_until TIMESTAMPTZ,
  last_checked_minute_label TEXT,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT common_action_tracking_state_run_state_key_uniq UNIQUE (run_id, state_key),
  CONSTRAINT common_action_tracking_state_asset_kind_check
    CHECK (asset_kind IN ('stock', 'index', 'board')),
  CONSTRAINT common_action_tracking_state_direction_check
    CHECK (direction IN ('buy', 'sell')),
  CONSTRAINT common_action_tracking_state_signal_type_check
    CHECK (signal_type IN ('B_BUY', 'S_SELL')),
  CONSTRAINT common_action_tracking_state_action_state_check
    CHECK (action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')),
  CONSTRAINT common_action_tracking_state_tracking_status_check
    CHECK (tracking_status IN ('tracking', 'blocked', 'executed', 'skipped', 'expired')),
  CONSTRAINT common_action_tracking_state_event_type_check
    CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerStateChanged')),
  CONSTRAINT common_action_tracking_state_latest_event_type_check
    CHECK (latest_n4_event_type IN ('TriggerMatched', 'TriggerStateChanged')),
  CONSTRAINT common_action_tracking_state_output_event_type_check
    CHECK (
      planned_output_event_type IS NULL
      OR planned_output_event_type IN ('ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped')
    ),
  CONSTRAINT common_action_tracking_state_trade_date_check
    CHECK (trade_date ~ '^[0-9]{8}$'),
  CONSTRAINT common_action_tracking_state_state_key_not_empty_check
    CHECK (state_key <> ''),
  CONSTRAINT common_action_tracking_state_raw_json_object_check
    CHECK (jsonb_typeof(raw_json) = 'object'),
  CONSTRAINT common_action_tracking_state_periods_array_check
    CHECK (jsonb_typeof(all_trigger_periods) = 'array')
);

CREATE INDEX IF NOT EXISTS idx_common_action_tracking_state_run_status
ON common_action_tracking_state(run_id, tracking_status, action_state);

CREATE INDEX IF NOT EXISTS idx_common_action_tracking_state_source_trigger
ON common_action_tracking_state(source_trigger_run_id, latest_n4_event_time, latest_n4_event_id);

CREATE INDEX IF NOT EXISTS idx_common_action_tracking_state_trade_identity
ON common_action_tracking_state(trade_date, asset_kind, identity_key);

CREATE INDEX IF NOT EXISTS idx_common_action_tracking_state_source_state
ON common_action_tracking_state(source_trigger_state_id)
WHERE source_trigger_state_id IS NOT NULL;
