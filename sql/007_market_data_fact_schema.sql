-- A-share monitor v3 market data fact schema draft.
-- Stage N3-A/B/C: physical market-data facts and preload status.
-- Boundary: market-data layer only; no condition recalculation,
-- no trigger/action/mobile/voice/sim objects, and no worker state.
--
-- Depends on sql/006_market_data_layer_schema.sql.

BEGIN;

CREATE TABLE stock_realtime_daily_snapshot (
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

CREATE INDEX idx_stock_realtime_daily_snapshot_lookup
ON stock_realtime_daily_snapshot(for_trade_date, stock_identity_key, snapshot_time DESC);

CREATE TABLE index_realtime_daily_snapshot (
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

CREATE INDEX idx_index_realtime_daily_snapshot_lookup
ON index_realtime_daily_snapshot(for_trade_date, index_identity_key, snapshot_time DESC);

CREATE TABLE board_realtime_daily_snapshot (
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

CREATE INDEX idx_board_realtime_daily_snapshot_lookup
ON board_realtime_daily_snapshot(for_trade_date, board_identity_key, snapshot_time DESC);

CREATE TABLE stock_minute_bar_1m (
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

CREATE INDEX idx_stock_minute_bar_1m_lookup
ON stock_minute_bar_1m(trade_date, stock_identity_key, bar_time);

CREATE INDEX idx_stock_minute_bar_1m_run
ON stock_minute_bar_1m(run_id, is_previous_day_preload, quality_status);

CREATE TABLE index_minute_bar_1m (
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

CREATE INDEX idx_index_minute_bar_1m_lookup
ON index_minute_bar_1m(trade_date, index_identity_key, bar_time);

CREATE INDEX idx_index_minute_bar_1m_run
ON index_minute_bar_1m(run_id, is_previous_day_preload, quality_status);

CREATE TABLE board_minute_bar_1m (
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

CREATE INDEX idx_board_minute_bar_1m_lookup
ON board_minute_bar_1m(trade_date, board_identity_key, bar_time);

CREATE INDEX idx_board_minute_bar_1m_run
ON board_minute_bar_1m(run_id, is_previous_day_preload, quality_status);

CREATE TABLE stock_previous_day_minute_preload_status (
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

CREATE INDEX idx_stock_previous_day_minute_preload_status_lookup
ON stock_previous_day_minute_preload_status(for_trade_date, trade_date, status, quality_status);

CREATE TABLE index_previous_day_minute_preload_status (
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

CREATE INDEX idx_index_previous_day_minute_preload_status_lookup
ON index_previous_day_minute_preload_status(for_trade_date, trade_date, status, quality_status);

CREATE TABLE board_previous_day_minute_preload_status (
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

CREATE INDEX idx_board_previous_day_minute_preload_status_lookup
ON board_previous_day_minute_preload_status(for_trade_date, trade_date, status, quality_status);

COMMIT;
