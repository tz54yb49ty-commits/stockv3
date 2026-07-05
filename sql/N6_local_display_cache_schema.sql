-- A-share monitor v3 N6 local display cache schema.
-- Scope: N6-owned readonly cache tables for B Track display/filter surfaces.
-- This schema creates empty cache containers only. It does not materialize,
-- activate, or sync cache rows.

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS n6_display_cache_run (
  cache_run_id TEXT PRIMARY KEY,
  source_condition_run_id TEXT NOT NULL,
  source_trade_date TEXT NOT NULL CHECK (source_trade_date ~ '^[0-9]{8}$'),
  cache_version TEXT NOT NULL DEFAULT 'n6_display_cache_v1',
  status TEXT NOT NULL CHECK (status IN ('building', 'passed', 'failed', 'rolled_back')),
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  row_counts_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  hash_summary_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  validation_summary_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  error_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (NOT is_active OR status = 'passed')
);

CREATE UNIQUE INDEX IF NOT EXISTS n6_display_cache_run_active_once
  ON n6_display_cache_run (cache_version)
  WHERE is_active;

CREATE INDEX IF NOT EXISTS idx_n6_display_cache_run_active
  ON n6_display_cache_run (cache_version, is_active, source_trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_n6_display_cache_run_source
  ON n6_display_cache_run (source_condition_run_id, source_trade_date);

CREATE TABLE IF NOT EXISTS n6_stock_display_cache (
  n6_stock_display_cache_id BIGSERIAL PRIMARY KEY,
  cache_run_id TEXT NOT NULL REFERENCES n6_display_cache_run(cache_run_id),
  cache_version TEXT NOT NULL DEFAULT 'n6_display_cache_v1',
  source_condition_run_id TEXT NOT NULL,
  source_trade_date TEXT NOT NULL CHECK (source_trade_date ~ '^[0-9]{8}$'),
  source_table TEXT NOT NULL,
  source_version TEXT,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  row_hash TEXT NOT NULL,
  source_row_hash TEXT NOT NULL,
  source_identity_key TEXT NOT NULL CHECK (source_identity_key LIKE 'stock:%'),
  source_selected_directions_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  source_selected_condition_keys_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  expansion_strategy TEXT NOT NULL DEFAULT 'cartesian_fanout_v1'
    CHECK (expansion_strategy = 'cartesian_fanout_v1'),
  asset_kind TEXT NOT NULL CHECK (asset_kind = 'stock'),
  identity_key TEXT NOT NULL CHECK (identity_key LIKE 'stock:%'),
  stock_identity_key TEXT NOT NULL CHECK (stock_identity_key LIKE 'stock:%'),
  index_identity_key TEXT,
  board_identity_key TEXT,
  code TEXT NOT NULL,
  name TEXT,
  display_code TEXT,
  display_name TEXT,
  display_title TEXT,
  display_summary TEXT,
  condition_key TEXT NOT NULL,
  original_condition_key TEXT,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  selected_signal_types_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  period_summary_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  year_overheat_level TEXT,
  quarter_overheat_level TEXT,
  month_overheat_level TEXT,
  week_overheat_level TEXT,
  day_overheat_level TEXT,
  target_price_context_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  label_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  explanation_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'unknown',
  source_condition_display_basis_id BIGINT NOT NULL,
  source_updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_n6_stock_display_cache_run
  ON n6_stock_display_cache (cache_run_id, cache_version);

CREATE INDEX IF NOT EXISTS idx_n6_stock_display_cache_identity
  ON n6_stock_display_cache (identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_stock_display_cache_stock_identity
  ON n6_stock_display_cache (stock_identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_stock_display_cache_direction_condition
  ON n6_stock_display_cache (direction, condition_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_stock_display_cache_trade_date
  ON n6_stock_display_cache (source_trade_date, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_stock_display_cache_hash
  ON n6_stock_display_cache (row_hash);

CREATE UNIQUE INDEX IF NOT EXISTS uq_n6_stock_display_cache_source_fanout
  ON n6_stock_display_cache (cache_run_id, source_condition_display_basis_id, direction, condition_key);

CREATE TABLE IF NOT EXISTS n6_index_display_cache (
  n6_index_display_cache_id BIGSERIAL PRIMARY KEY,
  cache_run_id TEXT NOT NULL REFERENCES n6_display_cache_run(cache_run_id),
  cache_version TEXT NOT NULL DEFAULT 'n6_display_cache_v1',
  source_condition_run_id TEXT NOT NULL,
  source_trade_date TEXT NOT NULL CHECK (source_trade_date ~ '^[0-9]{8}$'),
  source_table TEXT NOT NULL,
  source_version TEXT,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  row_hash TEXT NOT NULL,
  source_row_hash TEXT NOT NULL,
  source_identity_key TEXT NOT NULL CHECK (source_identity_key LIKE 'index:%'),
  source_selected_directions_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  source_selected_condition_keys_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  expansion_strategy TEXT NOT NULL DEFAULT 'cartesian_fanout_v1'
    CHECK (expansion_strategy = 'cartesian_fanout_v1'),
  asset_kind TEXT NOT NULL CHECK (asset_kind = 'index'),
  identity_key TEXT NOT NULL CHECK (identity_key LIKE 'index:%'),
  stock_identity_key TEXT,
  index_identity_key TEXT NOT NULL CHECK (index_identity_key LIKE 'index:%'),
  board_identity_key TEXT,
  code TEXT NOT NULL,
  name TEXT,
  display_code TEXT,
  display_name TEXT,
  display_title TEXT,
  display_summary TEXT,
  condition_key TEXT NOT NULL,
  original_condition_key TEXT,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  selected_signal_types_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  period_summary_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  year_overheat_level TEXT,
  quarter_overheat_level TEXT,
  month_overheat_level TEXT,
  week_overheat_level TEXT,
  day_overheat_level TEXT,
  target_price_context_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  label_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  explanation_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'unknown',
  source_condition_display_basis_id BIGINT NOT NULL,
  source_updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_n6_index_display_cache_run
  ON n6_index_display_cache (cache_run_id, cache_version);

CREATE INDEX IF NOT EXISTS idx_n6_index_display_cache_identity
  ON n6_index_display_cache (identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_index_display_cache_index_identity
  ON n6_index_display_cache (index_identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_index_display_cache_direction_condition
  ON n6_index_display_cache (direction, condition_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_index_display_cache_trade_date
  ON n6_index_display_cache (source_trade_date, cache_run_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_n6_index_display_cache_source_fanout
  ON n6_index_display_cache (cache_run_id, source_condition_display_basis_id, direction, condition_key);

CREATE TABLE IF NOT EXISTS n6_board_display_cache (
  n6_board_display_cache_id BIGSERIAL PRIMARY KEY,
  cache_run_id TEXT NOT NULL REFERENCES n6_display_cache_run(cache_run_id),
  cache_version TEXT NOT NULL DEFAULT 'n6_display_cache_v1',
  source_condition_run_id TEXT NOT NULL,
  source_trade_date TEXT NOT NULL CHECK (source_trade_date ~ '^[0-9]{8}$'),
  source_table TEXT NOT NULL,
  source_version TEXT,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  row_hash TEXT NOT NULL,
  source_row_hash TEXT NOT NULL,
  source_identity_key TEXT NOT NULL CHECK (source_identity_key LIKE 'board:%'),
  source_selected_directions_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  source_selected_condition_keys_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  expansion_strategy TEXT NOT NULL DEFAULT 'cartesian_fanout_v1'
    CHECK (expansion_strategy = 'cartesian_fanout_v1'),
  asset_kind TEXT NOT NULL CHECK (asset_kind = 'board'),
  identity_key TEXT NOT NULL CHECK (identity_key LIKE 'board:%'),
  stock_identity_key TEXT,
  index_identity_key TEXT,
  board_identity_key TEXT NOT NULL CHECK (board_identity_key LIKE 'board:%'),
  board_type TEXT,
  code TEXT NOT NULL,
  name TEXT,
  display_code TEXT,
  display_name TEXT,
  display_title TEXT,
  display_summary TEXT,
  condition_key TEXT NOT NULL,
  original_condition_key TEXT,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  selected_signal_types_json JSONB NOT NULL DEFAULT '[]'::JSONB,
  period_summary_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  year_overheat_level TEXT,
  quarter_overheat_level TEXT,
  month_overheat_level TEXT,
  week_overheat_level TEXT,
  day_overheat_level TEXT,
  target_price_context_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  label_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  explanation_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'unknown',
  source_condition_display_basis_id BIGINT NOT NULL,
  source_updated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_n6_board_display_cache_run
  ON n6_board_display_cache (cache_run_id, cache_version);

CREATE INDEX IF NOT EXISTS idx_n6_board_display_cache_identity
  ON n6_board_display_cache (identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_display_cache_board_identity
  ON n6_board_display_cache (board_identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_display_cache_identity_board_type
  ON n6_board_display_cache (identity_key, board_type, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_display_cache_direction_condition
  ON n6_board_display_cache (direction, condition_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_display_cache_board_type
  ON n6_board_display_cache (board_type, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_display_cache_trade_date
  ON n6_board_display_cache (source_trade_date, cache_run_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_n6_board_display_cache_source_fanout
  ON n6_board_display_cache (cache_run_id, source_condition_display_basis_id, direction, condition_key);

CREATE TABLE IF NOT EXISTS n6_index_membership_display_cache (
  n6_index_membership_display_cache_id BIGSERIAL PRIMARY KEY,
  cache_run_id TEXT NOT NULL REFERENCES n6_display_cache_run(cache_run_id),
  cache_version TEXT NOT NULL DEFAULT 'n6_display_cache_v1',
  source_condition_run_id TEXT NOT NULL,
  source_trade_date TEXT NOT NULL CHECK (source_trade_date ~ '^[0-9]{8}$'),
  source_table TEXT NOT NULL,
  source_version TEXT,
  source_batch_id TEXT,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  row_hash TEXT NOT NULL,
  membership_kind TEXT NOT NULL CHECK (membership_kind = 'index'),
  parent_identity_key TEXT NOT NULL CHECK (parent_identity_key LIKE 'index:%'),
  parent_code TEXT NOT NULL,
  parent_name TEXT,
  index_identity_key TEXT NOT NULL CHECK (index_identity_key LIKE 'index:%'),
  board_identity_key TEXT,
  board_type TEXT,
  stock_identity_key TEXT NOT NULL CHECK (stock_identity_key LIKE 'stock:%'),
  stock_code TEXT NOT NULL,
  stock_name TEXT,
  display_title TEXT,
  display_summary TEXT,
  label_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  explanation_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'unknown',
  trade_date TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_n6_index_membership_display_cache_run
  ON n6_index_membership_display_cache (cache_run_id, cache_version);

CREATE INDEX IF NOT EXISTS idx_n6_index_membership_display_cache_parent
  ON n6_index_membership_display_cache (parent_identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_index_membership_display_cache_stock
  ON n6_index_membership_display_cache (stock_identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_index_membership_display_cache_index_identity
  ON n6_index_membership_display_cache (index_identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_index_membership_display_cache_trade_date
  ON n6_index_membership_display_cache (source_trade_date, cache_run_id);

CREATE TABLE IF NOT EXISTS n6_board_membership_display_cache (
  n6_board_membership_display_cache_id BIGSERIAL PRIMARY KEY,
  cache_run_id TEXT NOT NULL REFERENCES n6_display_cache_run(cache_run_id),
  cache_version TEXT NOT NULL DEFAULT 'n6_display_cache_v1',
  source_condition_run_id TEXT NOT NULL,
  source_trade_date TEXT NOT NULL CHECK (source_trade_date ~ '^[0-9]{8}$'),
  source_table TEXT NOT NULL,
  source_version TEXT,
  source_batch_id TEXT,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  row_hash TEXT NOT NULL,
  membership_kind TEXT NOT NULL CHECK (membership_kind = 'board'),
  parent_identity_key TEXT NOT NULL CHECK (parent_identity_key LIKE 'board:%'),
  parent_code TEXT NOT NULL,
  parent_name TEXT,
  index_identity_key TEXT,
  board_identity_key TEXT NOT NULL CHECK (board_identity_key LIKE 'board:%'),
  board_type TEXT,
  stock_identity_key TEXT NOT NULL CHECK (stock_identity_key LIKE 'stock:%'),
  stock_code TEXT NOT NULL,
  stock_name TEXT,
  display_title TEXT,
  display_summary TEXT,
  label_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  explanation_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'unknown',
  trade_date TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_n6_board_membership_display_cache_run
  ON n6_board_membership_display_cache (cache_run_id, cache_version);

CREATE INDEX IF NOT EXISTS idx_n6_board_membership_display_cache_parent
  ON n6_board_membership_display_cache (parent_identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_membership_display_cache_stock
  ON n6_board_membership_display_cache (stock_identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_membership_display_cache_board_identity
  ON n6_board_membership_display_cache (board_identity_key, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_membership_display_cache_parent_board_type
  ON n6_board_membership_display_cache (parent_identity_key, board_type, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_membership_display_cache_stock_board_type
  ON n6_board_membership_display_cache (stock_identity_key, board_type, cache_run_id);

CREATE INDEX IF NOT EXISTS idx_n6_board_membership_display_cache_trade_date
  ON n6_board_membership_display_cache (source_trade_date, cache_run_id);

COMMIT;
