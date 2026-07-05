-- A-share monitor v3 market data layer schema draft.
-- Stage N3-0 only: review before running in any PostgreSQL database.
-- Boundary: subscription planning metadata only; no market data facts,
-- no trigger/action/mobile/voice/sim objects, and no worker state.

BEGIN;

CREATE TABLE common_market_data_run (
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

CREATE INDEX idx_common_market_data_run_condition_run
ON common_market_data_run(source_condition_run_id);

CREATE INDEX idx_common_market_data_run_for_trade_date
ON common_market_data_run(for_trade_date, status);

CREATE TABLE common_market_data_quality_item (
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

CREATE INDEX idx_common_market_data_quality_run
ON common_market_data_quality_item(run_id);

CREATE INDEX idx_common_market_data_quality_status
ON common_market_data_quality_item(severity, status);

CREATE TABLE common_market_data_subscription_candidate (
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

CREATE INDEX idx_common_market_data_candidate_key
ON common_market_data_subscription_candidate(run_id, asset_kind, identity_key, required_data_kind, for_trade_date);

CREATE INDEX idx_common_market_data_candidate_scope
ON common_market_data_subscription_candidate(source_scope_table, source_scope_id);

-- Logical stage: market_data_subscription_dedup.
-- This table is the deduplicated market_data_subscription task set.
CREATE TABLE common_market_data_subscription (
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

CREATE INDEX idx_common_market_data_subscription_kind
ON common_market_data_subscription(run_id, required_data_kind, asset_kind, data_trade_date);

CREATE INDEX idx_common_market_data_subscription_object
ON common_market_data_subscription(for_trade_date, asset_kind, identity_key);

CREATE TABLE common_market_data_pull_plan (
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

CREATE INDEX idx_common_market_data_pull_plan_kind
ON common_market_data_pull_plan(run_id, required_data_kind, asset_kind, data_trade_date);

COMMIT;
