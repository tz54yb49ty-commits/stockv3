-- N3-A1 previous-day minute cumulative amount product schema draft.
-- Artifact only: do not execute outside an explicit schema migration gate.

CREATE TABLE IF NOT EXISTS stock_previous_day_minute_cumulative (
  cumulative_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  source_previous_day_minute_run_id TEXT NOT NULL,
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL,
  identity_key TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT,
  canonical_minute_label TEXT NOT NULL,
  canonical_bar_time TIMESTAMPTZ NOT NULL,
  raw_bar_time TIMESTAMPTZ NOT NULL,
  elapsed_index INTEGER NOT NULL,
  elapsed_count INTEGER NOT NULL,
  full_count INTEGER NOT NULL,
  cumulative_amount_yuan NUMERIC NOT NULL,
  full_day_amount_yuan NUMERIC NOT NULL,
  source_amount_unit TEXT NOT NULL,
  canonical_amount_unit TEXT NOT NULL,
  unit_conversion_factor NUMERIC NOT NULL,
  normalization_policy TEXT NOT NULL,
  raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  trace_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (asset_kind IN ('stock', 'index', 'board')),
  CHECK (canonical_amount_unit = 'yuan'),
  CHECK (full_count = 240),
  CHECK (canonical_minute_label !~ ' 11:30$'),
  CHECK (elapsed_index BETWEEN 1 AND full_count),
  CHECK (elapsed_count = elapsed_index),
  CHECK (cumulative_amount_yuan >= 0),
  CHECK (full_day_amount_yuan >= cumulative_amount_yuan)
);

CREATE UNIQUE INDEX IF NOT EXISTS stock_previous_day_minute_cumulative_source_identity_minute_uidx
  ON stock_previous_day_minute_cumulative (source_previous_day_minute_run_id, identity_key, canonical_minute_label);

CREATE INDEX IF NOT EXISTS stock_previous_day_minute_cumulative_run_identity_idx
  ON stock_previous_day_minute_cumulative (run_id, identity_key);

CREATE INDEX IF NOT EXISTS stock_previous_day_minute_cumulative_trade_date_idx
  ON stock_previous_day_minute_cumulative (for_trade_date, source_trade_date);

CREATE INDEX IF NOT EXISTS stock_previous_day_minute_cumulative_identity_minute_idx
  ON stock_previous_day_minute_cumulative (identity_key, canonical_minute_label);

COMMENT ON TABLE stock_previous_day_minute_cumulative IS
  'N3-A1 previous-day per-minute cumulative amount rows for N3P trigger-proof input; stock physical table.';

CREATE TABLE IF NOT EXISTS index_previous_day_minute_cumulative (
  cumulative_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  source_previous_day_minute_run_id TEXT NOT NULL,
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL,
  identity_key TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT,
  canonical_minute_label TEXT NOT NULL,
  canonical_bar_time TIMESTAMPTZ NOT NULL,
  raw_bar_time TIMESTAMPTZ NOT NULL,
  elapsed_index INTEGER NOT NULL,
  elapsed_count INTEGER NOT NULL,
  full_count INTEGER NOT NULL,
  cumulative_amount_yuan NUMERIC NOT NULL,
  full_day_amount_yuan NUMERIC NOT NULL,
  source_amount_unit TEXT NOT NULL,
  canonical_amount_unit TEXT NOT NULL,
  unit_conversion_factor NUMERIC NOT NULL,
  normalization_policy TEXT NOT NULL,
  raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  trace_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (asset_kind IN ('stock', 'index', 'board')),
  CHECK (canonical_amount_unit = 'yuan'),
  CHECK (full_count = 240),
  CHECK (canonical_minute_label !~ ' 11:30$'),
  CHECK (elapsed_index BETWEEN 1 AND full_count),
  CHECK (elapsed_count = elapsed_index),
  CHECK (cumulative_amount_yuan >= 0),
  CHECK (full_day_amount_yuan >= cumulative_amount_yuan)
);

CREATE UNIQUE INDEX IF NOT EXISTS index_previous_day_minute_cumulative_source_identity_minute_uidx
  ON index_previous_day_minute_cumulative (source_previous_day_minute_run_id, identity_key, canonical_minute_label);

CREATE INDEX IF NOT EXISTS index_previous_day_minute_cumulative_run_identity_idx
  ON index_previous_day_minute_cumulative (run_id, identity_key);

CREATE INDEX IF NOT EXISTS index_previous_day_minute_cumulative_trade_date_idx
  ON index_previous_day_minute_cumulative (for_trade_date, source_trade_date);

CREATE INDEX IF NOT EXISTS index_previous_day_minute_cumulative_identity_minute_idx
  ON index_previous_day_minute_cumulative (identity_key, canonical_minute_label);

COMMENT ON TABLE index_previous_day_minute_cumulative IS
  'N3-A1 previous-day per-minute cumulative amount rows for N3P trigger-proof input; index physical table.';

CREATE TABLE IF NOT EXISTS board_previous_day_minute_cumulative (
  cumulative_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  source_previous_day_minute_run_id TEXT NOT NULL,
  for_trade_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL,
  identity_key TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT,
  canonical_minute_label TEXT NOT NULL,
  canonical_bar_time TIMESTAMPTZ NOT NULL,
  raw_bar_time TIMESTAMPTZ NOT NULL,
  elapsed_index INTEGER NOT NULL,
  elapsed_count INTEGER NOT NULL,
  full_count INTEGER NOT NULL,
  cumulative_amount_yuan NUMERIC NOT NULL,
  full_day_amount_yuan NUMERIC NOT NULL,
  source_amount_unit TEXT NOT NULL,
  canonical_amount_unit TEXT NOT NULL,
  unit_conversion_factor NUMERIC NOT NULL,
  normalization_policy TEXT NOT NULL,
  raw_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  trace_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (asset_kind IN ('stock', 'index', 'board')),
  CHECK (canonical_amount_unit = 'yuan'),
  CHECK (full_count = 240),
  CHECK (canonical_minute_label !~ ' 11:30$'),
  CHECK (elapsed_index BETWEEN 1 AND full_count),
  CHECK (elapsed_count = elapsed_index),
  CHECK (cumulative_amount_yuan >= 0),
  CHECK (full_day_amount_yuan >= cumulative_amount_yuan)
);

CREATE UNIQUE INDEX IF NOT EXISTS board_previous_day_minute_cumulative_source_identity_minute_uidx
  ON board_previous_day_minute_cumulative (source_previous_day_minute_run_id, identity_key, canonical_minute_label);

CREATE INDEX IF NOT EXISTS board_previous_day_minute_cumulative_run_identity_idx
  ON board_previous_day_minute_cumulative (run_id, identity_key);

CREATE INDEX IF NOT EXISTS board_previous_day_minute_cumulative_trade_date_idx
  ON board_previous_day_minute_cumulative (for_trade_date, source_trade_date);

CREATE INDEX IF NOT EXISTS board_previous_day_minute_cumulative_identity_minute_idx
  ON board_previous_day_minute_cumulative (identity_key, canonical_minute_label);

COMMENT ON TABLE board_previous_day_minute_cumulative IS
  'N3-A1 previous-day per-minute cumulative amount rows for N3P trigger-proof input; board physical table.';
