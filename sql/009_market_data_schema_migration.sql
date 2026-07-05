-- A-share monitor v3 N3 market-data schema migration gap draft.
-- Stage N3-3 only: generated for review; do not execute without explicit user confirmation.
-- This file is additive only: CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
-- CREATE INDEX IF NOT EXISTS, and guarded ADD CONSTRAINT blocks.
-- N3-3 itself did not execute this SQL.

BEGIN;

CREATE TABLE IF NOT EXISTS common_market_data_run (
  run_id TEXT PRIMARY KEY,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  prev_trade_date TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'dry_run' CHECK (mode IN ('dry_run', 'execute')),
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'running', 'passed', 'failed', 'blocked', 'superseded', 'rolled_back')),
  p0_count INTEGER NOT NULL DEFAULT 0 CHECK (p0_count >= 0),
  p1_count INTEGER NOT NULL DEFAULT 0 CHECK (p1_count >= 0),
  p2_count INTEGER NOT NULL DEFAULT 0 CHECK (p2_count >= 0),
  source_scope_row_count INTEGER NOT NULL DEFAULT 0 CHECK (source_scope_row_count >= 0),
  candidate_row_count INTEGER NOT NULL DEFAULT 0 CHECK (candidate_row_count >= 0),
  subscription_row_count INTEGER NOT NULL DEFAULT 0 CHECK (subscription_row_count >= 0),
  subscription_object_count INTEGER NOT NULL DEFAULT 0 CHECK (subscription_object_count >= 0),
  dedup_ratio NUMERIC,
  generated_by TEXT NOT NULL DEFAULT 'market_data_layer',
  market_data_pulled BOOLEAN NOT NULL DEFAULT false,
  market_data_fact_written BOOLEAN NOT NULL DEFAULT false,
  downstream_layers_touched BOOLEAN NOT NULL DEFAULT false,
  worker_started BOOLEAN NOT NULL DEFAULT false,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (prev_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date = prev_trade_date),
  CHECK (finished_at IS NULL OR finished_at >= started_at),
  CHECK (dedup_ratio IS NULL OR dedup_ratio >= 0),
  CHECK (mode <> 'dry_run' OR market_data_pulled = false),
  CHECK (mode <> 'dry_run' OR market_data_fact_written = false),
  CHECK (mode <> 'dry_run' OR downstream_layers_touched = false),
  CHECK (mode <> 'dry_run' OR worker_started = false)
);

CREATE TABLE IF NOT EXISTS common_market_data_quality_item (
  quality_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  data_domain TEXT NOT NULL CHECK (data_domain IN ('common', 'stock', 'index', 'board')),
  layer_scope TEXT NOT NULL CHECK (layer_scope IN ('active_condition_run', 'market_data_subscription_candidate', 'market_data_subscription_dedup', 'market_data_pull_plan', 'market_data_run')),
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
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$')
);

CREATE TABLE IF NOT EXISTS common_market_data_subscription_candidate (
  candidate_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  prev_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  required_data_kind TEXT NOT NULL CHECK (required_data_kind IN ('realtime_daily_snapshot', 'minute_bar_1m', 'previous_day_minute_bar_1m')),
  data_trade_date TEXT NOT NULL,
  source_scope_table TEXT NOT NULL CHECK (source_scope_table IN ('stock_minute_target_scope', 'index_minute_target_scope', 'board_minute_target_scope')),
  source_scope_id BIGINT NOT NULL,
  source_condition_pool_id BIGINT NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  condition_key TEXT NOT NULL,
  allowed_signal_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  source_scope_required_flags JSONB NOT NULL DEFAULT '{}'::JSONB,
  candidate_status TEXT NOT NULL DEFAULT 'planned' CHECK (candidate_status IN ('planned', 'blocked', 'skipped')),
  selected_reason TEXT,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, source_scope_table, source_scope_id, required_data_kind),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (prev_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date = prev_trade_date),
  CHECK (data_trade_date ~ '^[0-9]{8}$'),
  CHECK (allowed_signal_types <@ ARRAY['B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT']::TEXT[]),
  CHECK (required_data_kind <> 'previous_day_minute_bar_1m' OR data_trade_date = prev_trade_date),
  CHECK (required_data_kind IN ('realtime_daily_snapshot', 'minute_bar_1m') OR data_trade_date <> for_trade_date OR prev_trade_date = for_trade_date)
);

CREATE TABLE IF NOT EXISTS common_market_data_subscription (
  subscription_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  prev_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  required_data_kind TEXT NOT NULL CHECK (required_data_kind IN ('realtime_daily_snapshot', 'minute_bar_1m', 'previous_day_minute_bar_1m')),
  data_trade_date TEXT NOT NULL,
  source_scope_row_count INTEGER NOT NULL CHECK (source_scope_row_count > 0),
  source_scope_tables TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  condition_keys TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  directions TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  allowed_signal_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  priority INTEGER NOT NULL DEFAULT 100,
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'active', 'blocked', 'skipped', 'expired')),
  selected_reason TEXT,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, asset_kind, identity_key, required_data_kind, for_trade_date),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (prev_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date = prev_trade_date),
  CHECK (data_trade_date ~ '^[0-9]{8}$'),
  CHECK (directions <@ ARRAY['buy', 'sell']::TEXT[]),
  CHECK (allowed_signal_types <@ ARRAY['B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT']::TEXT[]),
  CHECK (required_data_kind <> 'previous_day_minute_bar_1m' OR data_trade_date = prev_trade_date),
  CHECK (cardinality(source_scope_ids) > 0),
  CHECK (cardinality(source_condition_pool_ids) > 0)
);

CREATE TABLE IF NOT EXISTS common_market_data_pull_plan (
  pull_plan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  prev_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  required_data_kind TEXT NOT NULL CHECK (required_data_kind IN ('realtime_daily_snapshot', 'minute_bar_1m', 'previous_day_minute_bar_1m')),
  data_trade_date TEXT NOT NULL,
  adapter_name TEXT NOT NULL,
  subscription_count INTEGER NOT NULL CHECK (subscription_count >= 0),
  object_count INTEGER NOT NULL CHECK (object_count >= 0),
  subscription_ids_sample BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  subscription_refs_sample JSONB NOT NULL DEFAULT '[]'::JSONB,
  identity_keys_sample JSONB NOT NULL DEFAULT '[]'::JSONB,
  plan_status TEXT NOT NULL DEFAULT 'planned' CHECK (plan_status IN ('planned', 'blocked', 'skipped', 'executed')),
  execute_allowed BOOLEAN NOT NULL DEFAULT false,
  selected_reason TEXT,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, asset_kind, required_data_kind, data_trade_date, for_trade_date),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (prev_trade_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date = prev_trade_date),
  CHECK (data_trade_date ~ '^[0-9]{8}$'),
  CHECK (execute_allowed = false OR plan_status IN ('planned', 'executed'))
);

CREATE TABLE IF NOT EXISTS stock_realtime_daily_snapshot (
  snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES common_market_data_subscription(subscription_id) ON DELETE SET NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  snapshot_time TIMESTAMPTZ NOT NULL,
  stock_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  current_price NUMERIC,
  pre_close NUMERIC,
  volume NUMERIC,
  amount NUMERIC,
  source_adapter TEXT NOT NULL,
  source_version TEXT,
  quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (quality_status IN ('pending', 'passed', 'partial', 'missing', 'failed')),
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, trade_date, stock_identity_key, snapshot_time, source_adapter),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (stock_identity_key LIKE 'stock:%')
);

CREATE TABLE IF NOT EXISTS index_realtime_daily_snapshot (
  snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES common_market_data_subscription(subscription_id) ON DELETE SET NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  snapshot_time TIMESTAMPTZ NOT NULL,
  index_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  current_price NUMERIC,
  pre_close NUMERIC,
  volume NUMERIC,
  amount NUMERIC,
  source_adapter TEXT NOT NULL,
  source_version TEXT,
  quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (quality_status IN ('pending', 'passed', 'partial', 'missing', 'failed')),
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, trade_date, index_identity_key, snapshot_time, source_adapter),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (index_identity_key LIKE 'index:%')
);

CREATE TABLE IF NOT EXISTS board_realtime_daily_snapshot (
  snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES common_market_data_subscription(subscription_id) ON DELETE SET NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  snapshot_time TIMESTAMPTZ NOT NULL,
  board_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  current_price NUMERIC,
  pre_close NUMERIC,
  volume NUMERIC,
  amount NUMERIC,
  source_adapter TEXT NOT NULL,
  source_version TEXT,
  quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (quality_status IN ('pending', 'passed', 'partial', 'missing', 'failed')),
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, trade_date, board_identity_key, snapshot_time, source_adapter),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (board_identity_key LIKE 'board:%')
);

CREATE TABLE IF NOT EXISTS stock_minute_bar_1m (
  bar_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES common_market_data_subscription(subscription_id) ON DELETE SET NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  bar_time TIMESTAMPTZ NOT NULL,
  stock_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC,
  amount NUMERIC,
  source_adapter TEXT NOT NULL,
  source_version TEXT,
  quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (quality_status IN ('pending', 'passed', 'partial', 'missing', 'failed')),
  is_previous_day_preload BOOLEAN NOT NULL DEFAULT false,
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, trade_date, stock_identity_key, bar_time, source_adapter),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (stock_identity_key LIKE 'stock:%')
);

CREATE TABLE IF NOT EXISTS index_minute_bar_1m (
  bar_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES common_market_data_subscription(subscription_id) ON DELETE SET NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  bar_time TIMESTAMPTZ NOT NULL,
  index_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC,
  amount NUMERIC,
  source_adapter TEXT NOT NULL,
  source_version TEXT,
  quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (quality_status IN ('pending', 'passed', 'partial', 'missing', 'failed')),
  is_previous_day_preload BOOLEAN NOT NULL DEFAULT false,
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, trade_date, index_identity_key, bar_time, source_adapter),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (index_identity_key LIKE 'index:%')
);

CREATE TABLE IF NOT EXISTS board_minute_bar_1m (
  bar_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES common_market_data_subscription(subscription_id) ON DELETE SET NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  bar_time TIMESTAMPTZ NOT NULL,
  board_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC,
  amount NUMERIC,
  source_adapter TEXT NOT NULL,
  source_version TEXT,
  quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (quality_status IN ('pending', 'passed', 'partial', 'missing', 'failed')),
  is_previous_day_preload BOOLEAN NOT NULL DEFAULT false,
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, trade_date, board_identity_key, bar_time, source_adapter),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (board_identity_key LIKE 'board:%')
);

CREATE TABLE IF NOT EXISTS stock_previous_day_minute_preload_status (
  preload_status_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES common_market_data_subscription(subscription_id) ON DELETE SET NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  stock_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  expected_bar_count INTEGER CHECK (expected_bar_count IS NULL OR expected_bar_count >= 0),
  actual_bar_count INTEGER NOT NULL DEFAULT 0 CHECK (actual_bar_count >= 0),
  missing_bar_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_bar_count >= 0),
  first_bar_time TIMESTAMPTZ,
  last_bar_time TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'running', 'passed', 'partial', 'missing', 'failed', 'skipped')),
  quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (quality_status IN ('pending', 'passed', 'partial', 'missing', 'failed')),
  source_adapter TEXT NOT NULL,
  error_message TEXT,
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, trade_date, stock_identity_key, source_adapter),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (stock_identity_key LIKE 'stock:%')
);

CREATE TABLE IF NOT EXISTS index_previous_day_minute_preload_status (
  preload_status_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES common_market_data_subscription(subscription_id) ON DELETE SET NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  index_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  expected_bar_count INTEGER CHECK (expected_bar_count IS NULL OR expected_bar_count >= 0),
  actual_bar_count INTEGER NOT NULL DEFAULT 0 CHECK (actual_bar_count >= 0),
  missing_bar_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_bar_count >= 0),
  first_bar_time TIMESTAMPTZ,
  last_bar_time TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'running', 'passed', 'partial', 'missing', 'failed', 'skipped')),
  quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (quality_status IN ('pending', 'passed', 'partial', 'missing', 'failed')),
  source_adapter TEXT NOT NULL,
  error_message TEXT,
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, trade_date, index_identity_key, source_adapter),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (index_identity_key LIKE 'index:%')
);

CREATE TABLE IF NOT EXISTS board_previous_day_minute_preload_status (
  preload_status_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES common_market_data_subscription(subscription_id) ON DELETE SET NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  board_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  expected_bar_count INTEGER CHECK (expected_bar_count IS NULL OR expected_bar_count >= 0),
  actual_bar_count INTEGER NOT NULL DEFAULT 0 CHECK (actual_bar_count >= 0),
  missing_bar_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_bar_count >= 0),
  first_bar_time TIMESTAMPTZ,
  last_bar_time TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'running', 'passed', 'partial', 'missing', 'failed', 'skipped')),
  quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (quality_status IN ('pending', 'passed', 'partial', 'missing', 'failed')),
  source_adapter TEXT NOT NULL,
  error_message TEXT,
  source_scope_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_condition_pool_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, trade_date, board_identity_key, source_adapter),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (board_identity_key LIKE 'board:%')
);

CREATE TABLE IF NOT EXISTS common_event_ledger (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  event_schema_version TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board', 'common')),
  identity_key TEXT NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,
  source_layer TEXT NOT NULL CHECK (source_layer IN ('N3_market_data', 'N4_trigger', 'N5_action', 'N6_user')),
  source_run_id TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  first_outbox_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (event_type !~ '^User'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (event_id <> ''),
  CHECK (identity_key <> ''),
  CHECK (source_run_id <> ''),
  CHECK (dedup_key <> ''),
  CHECK (partition_key <> ''),
  CHECK (
    source_layer <> 'N3_market_data'
    OR event_type IN (
      'MarketSnapshotUpdated',
      'MinuteBarClosed',
      'MinuteBarCorrected',
      'MarketDataDelayed',
      'MarketDataMissing',
      'MarketDisplaySnapshotUpdated'
    )
  )
);

CREATE TABLE IF NOT EXISTS common_event_outbox (
  outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_schema_version TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board', 'common')),
  identity_key TEXT NOT NULL,
  event_time TIMESTAMPTZ NOT NULL,
  source_layer TEXT NOT NULL CHECK (source_layer IN ('N3_market_data', 'N4_trigger', 'N5_action', 'N6_user')),
  source_run_id TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivering', 'delivered', 'failed', 'dead_letter')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_attempt_at TIMESTAMPTZ,
  locked_by TEXT,
  locked_at TIMESTAMPTZ,
  delivered_at TIMESTAMPTZ,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_common_event_outbox_event_id UNIQUE(event_id),
  CONSTRAINT uq_common_event_outbox_dedup UNIQUE(source_layer, event_type, source_run_id, dedup_key, event_schema_version),
  CHECK (event_type !~ '^User'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (event_id <> ''),
  CHECK (identity_key <> ''),
  CHECK (source_run_id <> ''),
  CHECK (dedup_key <> ''),
  CHECK (partition_key <> ''),
  CHECK (
    source_layer <> 'N3_market_data'
    OR event_type IN (
      'MarketSnapshotUpdated',
      'MinuteBarClosed',
      'MinuteBarCorrected',
      'MarketDataDelayed',
      'MarketDataMissing',
      'MarketDisplaySnapshotUpdated'
    )
  )
);

CREATE TABLE IF NOT EXISTS common_event_inbox (
  inbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  consumer_name TEXT NOT NULL,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  event_schema_version TEXT NOT NULL,
  source_layer TEXT NOT NULL,
  source_run_id TEXT NOT NULL,
  dedup_key TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'received' CHECK (status IN ('received', 'processing', 'processed', 'failed', 'skipped')),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ,
  last_error TEXT,
  raw_json JSONB,
  CONSTRAINT uq_common_event_inbox_consumer_event UNIQUE(consumer_name, event_id),
  CONSTRAINT uq_common_event_inbox_consumer_dedup UNIQUE(consumer_name, source_layer, event_type, source_run_id, dedup_key, event_schema_version),
  CHECK (consumer_name <> ''),
  CHECK (event_id <> ''),
  CHECK (dedup_key <> ''),
  CHECK (partition_key <> '')
);

CREATE TABLE IF NOT EXISTS common_event_consumer_checkpoint (
  consumer_name TEXT NOT NULL,
  partition_key TEXT NOT NULL,
  source_layer TEXT NOT NULL,
  last_event_id TEXT,
  last_event_time TIMESTAMPTZ,
  last_outbox_id BIGINT,
  checkpoint_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (consumer_name, partition_key, source_layer),
  CHECK (consumer_name <> ''),
  CHECK (partition_key <> '')
);

CREATE TABLE IF NOT EXISTS common_event_delivery_attempt (
  delivery_attempt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id TEXT NOT NULL,
  outbox_id BIGINT REFERENCES common_event_outbox(outbox_id) ON DELETE SET NULL,
  consumer_name TEXT,
  attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
  status TEXT NOT NULL CHECK (status IN ('started', 'delivered', 'failed', 'skipped')),
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  error_message TEXT,
  raw_json JSONB,
  CHECK (event_id <> ''),
  CHECK (finished_at IS NULL OR finished_at >= attempted_at)
);

CREATE INDEX IF NOT EXISTS idx_common_market_data_run_condition_run ON common_market_data_run(source_condition_run_id);

CREATE INDEX IF NOT EXISTS idx_common_market_data_run_for_trade_date ON common_market_data_run(for_trade_date, status);

CREATE INDEX IF NOT EXISTS idx_common_market_data_quality_run ON common_market_data_quality_item(run_id);

CREATE INDEX IF NOT EXISTS idx_common_market_data_quality_status ON common_market_data_quality_item(severity, status);

CREATE INDEX IF NOT EXISTS idx_common_market_data_candidate_key ON common_market_data_subscription_candidate(run_id, asset_kind, identity_key, required_data_kind, for_trade_date);

CREATE INDEX IF NOT EXISTS idx_common_market_data_candidate_scope ON common_market_data_subscription_candidate(source_scope_table, source_scope_id);

CREATE INDEX IF NOT EXISTS idx_common_market_data_subscription_kind ON common_market_data_subscription(run_id, required_data_kind, asset_kind, data_trade_date);

CREATE INDEX IF NOT EXISTS idx_common_market_data_subscription_object ON common_market_data_subscription(for_trade_date, asset_kind, identity_key);

CREATE INDEX IF NOT EXISTS idx_common_market_data_pull_plan_kind ON common_market_data_pull_plan(run_id, required_data_kind, asset_kind, data_trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_realtime_daily_snapshot_lookup ON stock_realtime_daily_snapshot(for_trade_date, stock_identity_key, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_index_realtime_daily_snapshot_lookup ON index_realtime_daily_snapshot(for_trade_date, index_identity_key, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_board_realtime_daily_snapshot_lookup ON board_realtime_daily_snapshot(for_trade_date, board_identity_key, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_stock_minute_bar_1m_lookup ON stock_minute_bar_1m(trade_date, stock_identity_key, bar_time);

CREATE INDEX IF NOT EXISTS idx_stock_minute_bar_1m_run ON stock_minute_bar_1m(run_id, is_previous_day_preload, quality_status);

CREATE INDEX IF NOT EXISTS idx_index_minute_bar_1m_lookup ON index_minute_bar_1m(trade_date, index_identity_key, bar_time);

CREATE INDEX IF NOT EXISTS idx_index_minute_bar_1m_run ON index_minute_bar_1m(run_id, is_previous_day_preload, quality_status);

CREATE INDEX IF NOT EXISTS idx_board_minute_bar_1m_lookup ON board_minute_bar_1m(trade_date, board_identity_key, bar_time);

CREATE INDEX IF NOT EXISTS idx_board_minute_bar_1m_run ON board_minute_bar_1m(run_id, is_previous_day_preload, quality_status);

CREATE INDEX IF NOT EXISTS idx_stock_previous_day_minute_preload_status_lookup ON stock_previous_day_minute_preload_status(for_trade_date, trade_date, status, quality_status);

CREATE INDEX IF NOT EXISTS idx_index_previous_day_minute_preload_status_lookup ON index_previous_day_minute_preload_status(for_trade_date, trade_date, status, quality_status);

CREATE INDEX IF NOT EXISTS idx_board_previous_day_minute_preload_status_lookup ON board_previous_day_minute_preload_status(for_trade_date, trade_date, status, quality_status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_common_event_ledger_dedup ON common_event_ledger(source_layer, event_type, source_run_id, dedup_key, event_schema_version);

CREATE INDEX IF NOT EXISTS idx_common_event_ledger_partition ON common_event_ledger(source_layer, partition_key, event_time, event_id);

CREATE INDEX IF NOT EXISTS idx_common_event_ledger_trade_date ON common_event_ledger(trade_date, event_type, asset_kind);

CREATE INDEX IF NOT EXISTS idx_common_event_outbox_pending ON common_event_outbox(status, next_attempt_at NULLS FIRST, created_at, outbox_id);

CREATE INDEX IF NOT EXISTS idx_common_event_outbox_partition ON common_event_outbox(source_layer, partition_key, event_time, event_id);

CREATE INDEX IF NOT EXISTS idx_common_event_inbox_status ON common_event_inbox(consumer_name, status, received_at);

CREATE INDEX IF NOT EXISTS idx_common_event_delivery_attempt_event ON common_event_delivery_attempt(event_id, attempted_at DESC);

CREATE INDEX IF NOT EXISTS idx_common_event_delivery_attempt_consumer ON common_event_delivery_attempt(consumer_name, status, attempted_at DESC);

COMMIT;

-- Rollback note:
-- N3-3 did not execute this SQL. If a later confirmed migration applies it,
-- rollback must be planned per object and only before dependent business rows exist.
-- This draft intentionally does not include rollback SQL statements.
