-- A-share monitor v3 action layer schema draft.
-- Stage N5-2 only: review before running in any PostgreSQL database.
-- Boundary: action fact / action event / position event contract only;
-- no user projection, no voice delivery, no sim trade, no true trading,
-- no market data pull, no N4 mutation, and no worker state.
--
-- Depends on:
--   sql/008_common_event_infra_schema.sql
--   sql/010_trigger_layer_schema.sql

BEGIN;

CREATE TABLE common_action_run (
  run_id TEXT PRIMARY KEY,
  source_trigger_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_condition_run_id TEXT REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  layer_role TEXT NOT NULL DEFAULT 'N5_action' CHECK (layer_role = 'N5_action'),
  mode TEXT NOT NULL DEFAULT 'dry_run' CHECK (mode IN ('dry_run', 'preflight', 'execute')),
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'running', 'passed', 'failed', 'blocked', 'superseded', 'rolled_back')),
  p0_count INTEGER NOT NULL DEFAULT 0 CHECK (p0_count >= 0),
  p1_count INTEGER NOT NULL DEFAULT 0 CHECK (p1_count >= 0),
  p2_count INTEGER NOT NULL DEFAULT 0 CHECK (p2_count >= 0),
  trigger_outbox_row_count INTEGER NOT NULL DEFAULT 0 CHECK (trigger_outbox_row_count >= 0),
  action_candidate_row_count INTEGER NOT NULL DEFAULT 0 CHECK (action_candidate_row_count >= 0),
  action_fact_row_count INTEGER NOT NULL DEFAULT 0 CHECK (action_fact_row_count >= 0),
  action_event_outbox_count INTEGER NOT NULL DEFAULT 0 CHECK (action_event_outbox_count >= 0),
  position_event_row_count INTEGER NOT NULL DEFAULT 0 CHECK (position_event_row_count >= 0),
  generated_by TEXT NOT NULL DEFAULT 'action_layer',
  market_data_pulled BOOLEAN NOT NULL DEFAULT false,
  trigger_layer_mutated BOOLEAN NOT NULL DEFAULT false,
  user_layer_touched BOOLEAN NOT NULL DEFAULT false,
  voice_touched BOOLEAN NOT NULL DEFAULT false,
  sim_touched BOOLEAN NOT NULL DEFAULT false,
  real_trade_touched BOOLEAN NOT NULL DEFAULT false,
  worker_started BOOLEAN NOT NULL DEFAULT false,
  consumer_checkpoint_updated BOOLEAN NOT NULL DEFAULT false,
  common_event_inbox_updated BOOLEAN NOT NULL DEFAULT false,
  raw_json JSONB,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (finished_at IS NULL OR finished_at >= started_at),
  CHECK (market_data_pulled = false),
  CHECK (trigger_layer_mutated = false),
  CHECK (user_layer_touched = false),
  CHECK (voice_touched = false),
  CHECK (sim_touched = false),
  CHECK (real_trade_touched = false),
  CHECK (worker_started = false),
  CHECK (mode <> 'dry_run' OR action_fact_row_count = 0),
  CHECK (mode <> 'dry_run' OR action_event_outbox_count = 0),
  CHECK (mode <> 'preflight' OR consumer_checkpoint_updated = false),
  CHECK (mode <> 'preflight' OR common_event_inbox_updated = false)
);

CREATE INDEX idx_common_action_run_trigger
ON common_action_run(source_trigger_run_id);

CREATE INDEX idx_common_action_run_date_status
ON common_action_run(for_trade_date, status);

CREATE TABLE common_action_quality_item (
  quality_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_action_run(run_id) ON DELETE CASCADE,
  source_trigger_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  for_trade_date TEXT NOT NULL,
  data_domain TEXT NOT NULL CHECK (data_domain IN ('common', 'stock', 'index', 'board')),
  layer_scope TEXT NOT NULL CHECK (layer_scope IN ('trigger_outbox_preflight', 'action_fact', 'action_event', 'position_event', 'position_state', 'event_contract')),
  table_name TEXT,
  gate_code TEXT NOT NULL,
  gate_name TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('P0', 'P1', 'P2')),
  status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'warning', 'skipped')),
  expected_value TEXT,
  actual_value TEXT,
  identity_key TEXT,
  details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$')
);

CREATE INDEX idx_common_action_quality_run
ON common_action_quality_item(run_id);

CREATE INDEX idx_common_action_quality_status
ON common_action_quality_item(severity, status);

CREATE TABLE stock_action_fact (
  action_fact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_action_run(run_id) ON DELETE CASCADE,
  source_trigger_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_trigger_event_id TEXT NOT NULL,
  source_trigger_event_type TEXT NOT NULL CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged')),
  event_schema_version TEXT NOT NULL DEFAULT 'v1',
  source_trigger_match_id BIGINT,
  trigger_state_id BIGINT,
  source_trigger_state_id BIGINT,
  source_condition_run_id TEXT REFERENCES common_condition_run(run_id),
  source_market_data_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_market_trace JSONB NOT NULL DEFAULT '{}'::JSONB,
  for_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'stock' CHECK (asset_kind = 'stock'),
  identity_key TEXT NOT NULL,
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  signal_type TEXT NOT NULL CHECK (signal_type IN ('B_BUY', 'S_SELL')),
  condition_key TEXT NOT NULL,
  original_condition_key TEXT NOT NULL,
  trigger_period TEXT NOT NULL CHECK (trigger_period IN ('Y', 'Q', 'M', 'W', 'D', '30m')),
  trigger_time TIMESTAMPTZ,
  trigger_price NUMERIC,
  trigger_mark_candidate TEXT CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink')),
  action_mark TEXT CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')),
  action_state TEXT NOT NULL CHECK (action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')),
  confirmation_status TEXT NOT NULL CHECK (confirmation_status IN ('pending', 'passed', 'failed', 'expired')),
  tracking_until TIMESTAMPTZ,
  last_checked_minute_label TEXT,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  action_policy TEXT NOT NULL DEFAULT 'n5_confirmation_only',
  action_type TEXT NOT NULL CHECK (action_type IN ('buy_candidate', 'sell_candidate', 'clear_candidate', 'pending_market_data', 'risk_candidate')),
  lane TEXT NOT NULL CHECK (lane IN ('stock_trade', 'stock_alert', 'market_alert', 'hint', 'policy_pending')),
  decision_status TEXT NOT NULL DEFAULT 'candidate' CHECK (decision_status IN ('candidate', 'policy_pending', 'pending_market_data', 'blocked_quality', 'skipped')),
  data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('pending', 'passed', 'partial', 'missing', 'delayed', 'failed')),
  closed_minute_required BOOLEAN NOT NULL DEFAULT false,
  closed_minute_verified BOOLEAN NOT NULL DEFAULT false,
  minute_context_status TEXT NOT NULL DEFAULT 'not_required' CHECK (minute_context_status IN ('not_required', 'closed', 'missing', 'unclosed')),
  action_bucket TEXT NOT NULL,
  action_key TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  source_payload_json JSONB NOT NULL,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, source_trigger_event_id, action_type),
  UNIQUE(run_id, action_key),
  UNIQUE(run_id, dedup_key),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key = stock_identity_key),
  CHECK (identity_key LIKE 'stock:%'),
  CHECK (condition_key !~ '^(BUY:|BUY_HINT)' OR direction = 'buy'),
  CHECK (condition_key !~ '^(SELL:|SELL_HINT)' OR direction = 'sell'),
  CHECK (signal_type <> 'B_BUY' OR direction = 'buy'),
  CHECK (signal_type <> 'S_SELL' OR direction = 'sell'),
  CHECK (minute_context_status <> 'unclosed' OR decision_status <> 'candidate'),
  CHECK (source_market_data_run_id IS NOT NULL OR source_market_trace <> '{}'::JSONB),
  CHECK (action_key <> ''),
  CHECK (dedup_key <> ''),
  CHECK (action_bucket <> '')
);

CREATE INDEX idx_stock_action_fact_lookup
ON stock_action_fact(run_id, stock_identity_key, direction, signal_type);

CREATE INDEX idx_stock_action_fact_source
ON stock_action_fact(source_trigger_run_id, source_trigger_event_id);

CREATE TABLE index_action_fact (
  action_fact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_action_run(run_id) ON DELETE CASCADE,
  source_trigger_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_trigger_event_id TEXT NOT NULL,
  source_trigger_event_type TEXT NOT NULL CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged')),
  event_schema_version TEXT NOT NULL DEFAULT 'v1',
  source_trigger_match_id BIGINT,
  trigger_state_id BIGINT,
  source_trigger_state_id BIGINT,
  source_condition_run_id TEXT REFERENCES common_condition_run(run_id),
  source_market_data_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_market_trace JSONB NOT NULL DEFAULT '{}'::JSONB,
  for_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'index' CHECK (asset_kind = 'index'),
  identity_key TEXT NOT NULL,
  index_identity_key TEXT NOT NULL REFERENCES index_identity(index_identity_key),
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  signal_type TEXT NOT NULL CHECK (signal_type IN ('B_BUY', 'S_SELL')),
  condition_key TEXT NOT NULL,
  original_condition_key TEXT NOT NULL,
  trigger_period TEXT NOT NULL CHECK (trigger_period IN ('Y', 'Q', 'M', 'W', 'D', '30m')),
  trigger_time TIMESTAMPTZ,
  trigger_price NUMERIC,
  trigger_mark_candidate TEXT CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink')),
  action_mark TEXT CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')),
  action_state TEXT NOT NULL CHECK (action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')),
  confirmation_status TEXT NOT NULL CHECK (confirmation_status IN ('pending', 'passed', 'failed', 'expired')),
  tracking_until TIMESTAMPTZ,
  last_checked_minute_label TEXT,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  action_policy TEXT NOT NULL DEFAULT 'n5_confirmation_only',
  action_type TEXT NOT NULL CHECK (action_type IN ('buy_candidate', 'sell_candidate', 'clear_candidate', 'pending_market_data', 'risk_candidate')),
  lane TEXT NOT NULL DEFAULT 'market_alert' CHECK (lane IN ('market_alert', 'hint', 'policy_pending')),
  decision_status TEXT NOT NULL DEFAULT 'candidate' CHECK (decision_status IN ('candidate', 'policy_pending', 'pending_market_data', 'blocked_quality', 'skipped')),
  data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('pending', 'passed', 'partial', 'missing', 'delayed', 'failed')),
  closed_minute_required BOOLEAN NOT NULL DEFAULT false,
  closed_minute_verified BOOLEAN NOT NULL DEFAULT false,
  minute_context_status TEXT NOT NULL DEFAULT 'not_required' CHECK (minute_context_status IN ('not_required', 'closed', 'missing', 'unclosed')),
  action_bucket TEXT NOT NULL,
  action_key TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  source_payload_json JSONB NOT NULL,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, source_trigger_event_id, action_type),
  UNIQUE(run_id, action_key),
  UNIQUE(run_id, dedup_key),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key = index_identity_key),
  CHECK (identity_key LIKE 'index:%'),
  CHECK (condition_key !~ '^(BUY:|BUY_HINT)' OR direction = 'buy'),
  CHECK (condition_key !~ '^(SELL:|SELL_HINT)' OR direction = 'sell'),
  CHECK (signal_type <> 'B_BUY' OR direction = 'buy'),
  CHECK (signal_type <> 'S_SELL' OR direction = 'sell'),
  CHECK (minute_context_status <> 'unclosed' OR decision_status <> 'candidate'),
  CHECK (source_market_data_run_id IS NOT NULL OR source_market_trace <> '{}'::JSONB),
  CHECK (action_key <> ''),
  CHECK (dedup_key <> ''),
  CHECK (action_bucket <> '')
);

CREATE INDEX idx_index_action_fact_lookup
ON index_action_fact(run_id, index_identity_key, direction, signal_type);

CREATE INDEX idx_index_action_fact_source
ON index_action_fact(source_trigger_run_id, source_trigger_event_id);

CREATE TABLE board_action_fact (
  action_fact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_action_run(run_id) ON DELETE CASCADE,
  source_trigger_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_trigger_event_id TEXT NOT NULL,
  source_trigger_event_type TEXT NOT NULL CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged')),
  event_schema_version TEXT NOT NULL DEFAULT 'v1',
  source_trigger_match_id BIGINT,
  trigger_state_id BIGINT,
  source_trigger_state_id BIGINT,
  source_condition_run_id TEXT REFERENCES common_condition_run(run_id),
  source_market_data_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_market_trace JSONB NOT NULL DEFAULT '{}'::JSONB,
  for_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'board' CHECK (asset_kind = 'board'),
  identity_key TEXT NOT NULL,
  board_identity_key TEXT NOT NULL REFERENCES board_identity(board_identity_key),
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  signal_type TEXT NOT NULL CHECK (signal_type IN ('B_BUY', 'S_SELL')),
  condition_key TEXT NOT NULL,
  original_condition_key TEXT NOT NULL,
  trigger_period TEXT NOT NULL CHECK (trigger_period IN ('Y', 'Q', 'M', 'W', 'D', '30m')),
  trigger_time TIMESTAMPTZ,
  trigger_price NUMERIC,
  trigger_mark_candidate TEXT CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink')),
  action_mark TEXT CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')),
  action_state TEXT NOT NULL CHECK (action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')),
  confirmation_status TEXT NOT NULL CHECK (confirmation_status IN ('pending', 'passed', 'failed', 'expired')),
  tracking_until TIMESTAMPTZ,
  last_checked_minute_label TEXT,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  action_policy TEXT NOT NULL DEFAULT 'n5_confirmation_only',
  action_type TEXT NOT NULL CHECK (action_type IN ('buy_candidate', 'sell_candidate', 'clear_candidate', 'pending_market_data', 'risk_candidate')),
  lane TEXT NOT NULL DEFAULT 'market_alert' CHECK (lane IN ('market_alert', 'hint', 'policy_pending')),
  decision_status TEXT NOT NULL DEFAULT 'candidate' CHECK (decision_status IN ('candidate', 'policy_pending', 'pending_market_data', 'blocked_quality', 'skipped')),
  data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('pending', 'passed', 'partial', 'missing', 'delayed', 'failed')),
  closed_minute_required BOOLEAN NOT NULL DEFAULT false,
  closed_minute_verified BOOLEAN NOT NULL DEFAULT false,
  minute_context_status TEXT NOT NULL DEFAULT 'not_required' CHECK (minute_context_status IN ('not_required', 'closed', 'missing', 'unclosed')),
  action_bucket TEXT NOT NULL,
  action_key TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  source_payload_json JSONB NOT NULL,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, source_trigger_event_id, action_type),
  UNIQUE(run_id, action_key),
  UNIQUE(run_id, dedup_key),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key = board_identity_key),
  CHECK (identity_key LIKE 'board:%'),
  CHECK (condition_key !~ '^(BUY:|BUY_HINT)' OR direction = 'buy'),
  CHECK (condition_key !~ '^(SELL:|SELL_HINT)' OR direction = 'sell'),
  CHECK (signal_type <> 'B_BUY' OR direction = 'buy'),
  CHECK (signal_type <> 'S_SELL' OR direction = 'sell'),
  CHECK (minute_context_status <> 'unclosed' OR decision_status <> 'candidate'),
  CHECK (source_market_data_run_id IS NOT NULL OR source_market_trace <> '{}'::JSONB),
  CHECK (action_key <> ''),
  CHECK (dedup_key <> ''),
  CHECK (action_bucket <> '')
);

CREATE INDEX idx_board_action_fact_lookup
ON board_action_fact(run_id, board_identity_key, direction, signal_type);

CREATE INDEX idx_board_action_fact_source
ON board_action_fact(source_trigger_run_id, source_trigger_event_id);

CREATE TABLE common_action_event (
  action_event_row_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  event_schema_version TEXT NOT NULL DEFAULT 'v1',
  run_id TEXT NOT NULL REFERENCES common_action_run(run_id) ON DELETE CASCADE,
  source_trigger_run_id TEXT NOT NULL REFERENCES common_trigger_run(run_id),
  source_trigger_event_id TEXT NOT NULL,
  source_trigger_match_id BIGINT,
  source_trigger_state_id BIGINT,
  source_condition_run_id TEXT REFERENCES common_condition_run(run_id),
  source_market_data_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_market_trace JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_action_fact_table TEXT NOT NULL CHECK (source_action_fact_table IN ('stock_action_fact', 'index_action_fact', 'board_action_fact')),
  source_action_fact_id BIGINT NOT NULL,
  for_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  signal_type TEXT NOT NULL CHECK (signal_type IN ('B_BUY', 'S_SELL')),
  condition_key TEXT NOT NULL,
  original_condition_key TEXT NOT NULL,
  trigger_period TEXT NOT NULL CHECK (trigger_period IN ('Y', 'Q', 'M', 'W', 'D', '30m')),
  trigger_mark_candidate TEXT CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink')),
  action_mark TEXT CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')),
  action_state TEXT NOT NULL CHECK (action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')),
  confirmation_status TEXT NOT NULL CHECK (confirmation_status IN ('pending', 'passed', 'failed', 'expired')),
  tracking_until TIMESTAMPTZ,
  last_checked_minute_label TEXT,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  action_policy TEXT NOT NULL DEFAULT 'n5_confirmation_only',
  event_type TEXT NOT NULL CHECK (event_type IN ('ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped')),
  action_type TEXT NOT NULL CHECK (action_type IN ('buy_candidate', 'sell_candidate', 'clear_candidate', 'pending_market_data', 'risk_candidate')),
  lane TEXT NOT NULL CHECK (lane IN ('stock_trade', 'stock_alert', 'market_alert', 'hint', 'policy_pending')),
  data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('pending', 'passed', 'partial', 'missing', 'delayed', 'failed')),
  action_key TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, action_key),
  UNIQUE(run_id, dedup_key),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE asset_kind || ':%'),
  CHECK (condition_key !~ '^(BUY:|BUY_HINT)' OR direction = 'buy'),
  CHECK (condition_key !~ '^(SELL:|SELL_HINT)' OR direction = 'sell'),
  CHECK (signal_type <> 'B_BUY' OR direction = 'buy'),
  CHECK (signal_type <> 'S_SELL' OR direction = 'sell'),
  CHECK (source_market_data_run_id IS NOT NULL OR source_market_trace <> '{}'::JSONB),
  CHECK (action_key <> ''),
  CHECK (dedup_key <> ''),
  CHECK (partition_key <> '')
);

CREATE INDEX idx_common_action_event_run_type
ON common_action_event(run_id, event_type, created_at);

CREATE INDEX idx_common_action_event_identity
ON common_action_event(for_trade_date, asset_kind, identity_key, created_at DESC);

CREATE TABLE common_position_state (
  position_state_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_action_run(run_id) ON DELETE CASCADE,
  for_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  lane TEXT NOT NULL CHECK (lane IN ('stock_trade', 'stock_alert', 'market_alert', 'hint', 'policy_pending')),
  position_status TEXT NOT NULL CHECK (position_status IN ('unknown', 'open', 'closed', 'policy_pending')),
  source_action_event_id TEXT,
  quantity NUMERIC,
  avg_price NUMERIC,
  state_hash TEXT NOT NULL,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, asset_kind, identity_key, lane),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE asset_kind || ':%'),
  CHECK (state_hash <> '')
);

CREATE INDEX idx_common_position_state_identity
ON common_position_state(asset_kind, identity_key, lane, updated_at DESC);

CREATE TABLE common_position_event (
  position_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  event_schema_version TEXT NOT NULL DEFAULT 'v1',
  run_id TEXT NOT NULL REFERENCES common_action_run(run_id) ON DELETE CASCADE,
  source_trigger_event_id TEXT NOT NULL,
  source_trigger_match_id BIGINT,
  source_condition_run_id TEXT REFERENCES common_condition_run(run_id),
  source_market_data_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_market_trace JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_action_event_id TEXT,
  source_position_state_id BIGINT REFERENCES common_position_state(position_state_id),
  for_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  signal_type TEXT CHECK (signal_type IS NULL OR signal_type IN ('B_BUY', 'S_SELL')),
  condition_key TEXT,
  action_type TEXT NOT NULL CHECK (action_type IN ('buy_candidate', 'sell_candidate', 'clear_candidate', 'pending_market_data', 'risk_candidate')),
  lane TEXT NOT NULL CHECK (lane IN ('stock_trade', 'stock_alert', 'market_alert', 'hint', 'policy_pending')),
  position_event_type TEXT NOT NULL CHECK (position_event_type IN ('position_candidate', 'position_opened', 'position_closed', 'position_policy_pending')),
  data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('pending', 'passed', 'partial', 'missing', 'delayed', 'failed')),
  action_key TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, action_key),
  UNIQUE(run_id, dedup_key),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE asset_kind || ':%'),
  CHECK (source_market_data_run_id IS NOT NULL OR source_market_trace <> '{}'::JSONB),
  CHECK (action_key <> ''),
  CHECK (dedup_key <> '')
);

CREATE INDEX idx_common_position_event_run
ON common_position_event(run_id, position_event_type, created_at);

COMMIT;
