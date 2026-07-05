-- A-share monitor v3 N3 EOD snapshot schema draft.
-- Stage N3-EOD: additive schema only.
-- Boundary: N3 settlement / official close confirmation facts only.
-- No outbox, inbox, checkpoint, trigger, action, user, voice, mobile, sim,
-- position, worker, or existing B1/B2/C2/C2B/C3/N4/N5 runtime changes.

CREATE TABLE IF NOT EXISTS stock_eod_snapshot (
  eod_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  eod_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_b1_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c2_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c2b_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c3_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_n4_replay_audit_run_id TEXT,
  official_daily_run_id TEXT,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'stock' CHECK (asset_kind = 'stock'),
  identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC CHECK (volume IS NULL OR volume >= 0),
  amount NUMERIC CHECK (amount IS NULL OR amount >= 0),
  official_close_price NUMERIC,
  official_volume NUMERIC CHECK (official_volume IS NULL OR official_volume >= 0),
  official_amount NUMERIC CHECK (official_amount IS NULL OR official_amount >= 0),
  eod_source_status TEXT NOT NULL DEFAULT 'runtime_only'
    CHECK (eod_source_status IN ('runtime_only', 'official_confirmed', 'official_missing', 'mixed', 'missing', 'blocked')),
  settlement_quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (settlement_quality_status IN ('pending', 'passed', 'warning', 'missing', 'failed', 'blocked')),
  stale_candidate BOOLEAN NOT NULL DEFAULT false,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(eod_run_id, identity_key, trade_date),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'stock:%')
);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_run
ON stock_eod_snapshot(eod_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_subscription_run
ON stock_eod_snapshot(source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_b1_run
ON stock_eod_snapshot(source_b1_snapshot_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_c2_run
ON stock_eod_snapshot(source_c2_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_c2b_run
ON stock_eod_snapshot(source_c2b_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_trade_identity
ON stock_eod_snapshot(trade_date, identity_key);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_source_status
ON stock_eod_snapshot(eod_source_status);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_quality_status
ON stock_eod_snapshot(settlement_quality_status);

CREATE INDEX IF NOT EXISTS idx_stock_eod_snapshot_stale_candidate
ON stock_eod_snapshot(stale_candidate);

CREATE TABLE IF NOT EXISTS index_eod_snapshot (
  eod_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  eod_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_b1_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c2_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c2b_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c3_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_n4_replay_audit_run_id TEXT,
  official_daily_run_id TEXT,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'index' CHECK (asset_kind = 'index'),
  identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC CHECK (volume IS NULL OR volume >= 0),
  amount NUMERIC CHECK (amount IS NULL OR amount >= 0),
  official_close_price NUMERIC,
  official_volume NUMERIC CHECK (official_volume IS NULL OR official_volume >= 0),
  official_amount NUMERIC CHECK (official_amount IS NULL OR official_amount >= 0),
  eod_source_status TEXT NOT NULL DEFAULT 'runtime_only'
    CHECK (eod_source_status IN ('runtime_only', 'official_confirmed', 'official_missing', 'mixed', 'missing', 'blocked')),
  settlement_quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (settlement_quality_status IN ('pending', 'passed', 'warning', 'missing', 'failed', 'blocked')),
  stale_candidate BOOLEAN NOT NULL DEFAULT false,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(eod_run_id, identity_key, trade_date),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'index:%')
);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_run
ON index_eod_snapshot(eod_run_id);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_subscription_run
ON index_eod_snapshot(source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_b1_run
ON index_eod_snapshot(source_b1_snapshot_run_id);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_c2_run
ON index_eod_snapshot(source_c2_run_id);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_c2b_run
ON index_eod_snapshot(source_c2b_run_id);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_trade_identity
ON index_eod_snapshot(trade_date, identity_key);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_source_status
ON index_eod_snapshot(eod_source_status);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_quality_status
ON index_eod_snapshot(settlement_quality_status);

CREATE INDEX IF NOT EXISTS idx_index_eod_snapshot_stale_candidate
ON index_eod_snapshot(stale_candidate);

CREATE TABLE IF NOT EXISTS board_eod_snapshot (
  eod_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  eod_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_b1_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c2_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c2b_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_c3_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_n4_replay_audit_run_id TEXT,
  official_daily_run_id TEXT,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'board' CHECK (asset_kind = 'board'),
  identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC CHECK (volume IS NULL OR volume >= 0),
  amount NUMERIC CHECK (amount IS NULL OR amount >= 0),
  official_close_price NUMERIC,
  official_volume NUMERIC CHECK (official_volume IS NULL OR official_volume >= 0),
  official_amount NUMERIC CHECK (official_amount IS NULL OR official_amount >= 0),
  eod_source_status TEXT NOT NULL DEFAULT 'runtime_only'
    CHECK (eod_source_status IN ('runtime_only', 'official_confirmed', 'official_missing', 'mixed', 'missing', 'blocked')),
  settlement_quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (settlement_quality_status IN ('pending', 'passed', 'warning', 'missing', 'failed', 'blocked')),
  stale_candidate BOOLEAN NOT NULL DEFAULT false,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(eod_run_id, identity_key, trade_date),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'board:%')
);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_run
ON board_eod_snapshot(eod_run_id);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_subscription_run
ON board_eod_snapshot(source_subscription_run_id);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_b1_run
ON board_eod_snapshot(source_b1_snapshot_run_id);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_c2_run
ON board_eod_snapshot(source_c2_run_id);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_c2b_run
ON board_eod_snapshot(source_c2b_run_id);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_trade_identity
ON board_eod_snapshot(trade_date, identity_key);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_source_status
ON board_eod_snapshot(eod_source_status);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_quality_status
ON board_eod_snapshot(settlement_quality_status);

CREATE INDEX IF NOT EXISTS idx_board_eod_snapshot_stale_candidate
ON board_eod_snapshot(stale_candidate);

CREATE TABLE IF NOT EXISTS stock_eod_reconciliation_item (
  reconciliation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  eod_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  eod_snapshot_id BIGINT REFERENCES stock_eod_snapshot(eod_snapshot_id),
  asset_kind TEXT NOT NULL DEFAULT 'stock' CHECK (asset_kind = 'stock'),
  identity_key TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  source_run_id TEXT NOT NULL,
  source_layer TEXT NOT NULL CHECK (source_layer IN ('N1_ingestion', 'N3_market_data', 'N4_trigger', 'N5_action', 'common')),
  source_fact_type TEXT NOT NULL,
  diff_type TEXT NOT NULL,
  diff_severity TEXT NOT NULL DEFAULT 'info' CHECK (diff_severity IN ('P0', 'P1', 'P2', 'info')),
  stale_candidate BOOLEAN NOT NULL DEFAULT false,
  expected_value_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  actual_value_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'passed'
    CHECK (quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked', 'skipped')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(eod_run_id, identity_key, trade_date, source_run_id, source_fact_type, diff_type),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'stock:%')
);

CREATE INDEX IF NOT EXISTS idx_stock_eod_reconciliation_run
ON stock_eod_reconciliation_item(eod_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_eod_reconciliation_snapshot
ON stock_eod_reconciliation_item(eod_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_stock_eod_reconciliation_trade_identity
ON stock_eod_reconciliation_item(trade_date, identity_key);

CREATE INDEX IF NOT EXISTS idx_stock_eod_reconciliation_source
ON stock_eod_reconciliation_item(source_layer, source_fact_type);

CREATE INDEX IF NOT EXISTS idx_stock_eod_reconciliation_diff
ON stock_eod_reconciliation_item(diff_type, diff_severity);

CREATE INDEX IF NOT EXISTS idx_stock_eod_reconciliation_quality
ON stock_eod_reconciliation_item(quality_status);

CREATE INDEX IF NOT EXISTS idx_stock_eod_reconciliation_stale
ON stock_eod_reconciliation_item(stale_candidate);

CREATE TABLE IF NOT EXISTS index_eod_reconciliation_item (
  reconciliation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  eod_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  eod_snapshot_id BIGINT REFERENCES index_eod_snapshot(eod_snapshot_id),
  asset_kind TEXT NOT NULL DEFAULT 'index' CHECK (asset_kind = 'index'),
  identity_key TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  source_run_id TEXT NOT NULL,
  source_layer TEXT NOT NULL CHECK (source_layer IN ('N1_ingestion', 'N3_market_data', 'N4_trigger', 'N5_action', 'common')),
  source_fact_type TEXT NOT NULL,
  diff_type TEXT NOT NULL,
  diff_severity TEXT NOT NULL DEFAULT 'info' CHECK (diff_severity IN ('P0', 'P1', 'P2', 'info')),
  stale_candidate BOOLEAN NOT NULL DEFAULT false,
  expected_value_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  actual_value_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'passed'
    CHECK (quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked', 'skipped')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(eod_run_id, identity_key, trade_date, source_run_id, source_fact_type, diff_type),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'index:%')
);

CREATE INDEX IF NOT EXISTS idx_index_eod_reconciliation_run
ON index_eod_reconciliation_item(eod_run_id);

CREATE INDEX IF NOT EXISTS idx_index_eod_reconciliation_snapshot
ON index_eod_reconciliation_item(eod_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_index_eod_reconciliation_trade_identity
ON index_eod_reconciliation_item(trade_date, identity_key);

CREATE INDEX IF NOT EXISTS idx_index_eod_reconciliation_source
ON index_eod_reconciliation_item(source_layer, source_fact_type);

CREATE INDEX IF NOT EXISTS idx_index_eod_reconciliation_diff
ON index_eod_reconciliation_item(diff_type, diff_severity);

CREATE INDEX IF NOT EXISTS idx_index_eod_reconciliation_quality
ON index_eod_reconciliation_item(quality_status);

CREATE INDEX IF NOT EXISTS idx_index_eod_reconciliation_stale
ON index_eod_reconciliation_item(stale_candidate);

CREATE TABLE IF NOT EXISTS board_eod_reconciliation_item (
  reconciliation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  eod_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  eod_snapshot_id BIGINT REFERENCES board_eod_snapshot(eod_snapshot_id),
  asset_kind TEXT NOT NULL DEFAULT 'board' CHECK (asset_kind = 'board'),
  identity_key TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  source_run_id TEXT NOT NULL,
  source_layer TEXT NOT NULL CHECK (source_layer IN ('N1_ingestion', 'N3_market_data', 'N4_trigger', 'N5_action', 'common')),
  source_fact_type TEXT NOT NULL,
  diff_type TEXT NOT NULL,
  diff_severity TEXT NOT NULL DEFAULT 'info' CHECK (diff_severity IN ('P0', 'P1', 'P2', 'info')),
  stale_candidate BOOLEAN NOT NULL DEFAULT false,
  expected_value_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  actual_value_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'passed'
    CHECK (quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked', 'skipped')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(eod_run_id, identity_key, trade_date, source_run_id, source_fact_type, diff_type),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'board:%')
);

CREATE INDEX IF NOT EXISTS idx_board_eod_reconciliation_run
ON board_eod_reconciliation_item(eod_run_id);

CREATE INDEX IF NOT EXISTS idx_board_eod_reconciliation_snapshot
ON board_eod_reconciliation_item(eod_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_board_eod_reconciliation_trade_identity
ON board_eod_reconciliation_item(trade_date, identity_key);

CREATE INDEX IF NOT EXISTS idx_board_eod_reconciliation_source
ON board_eod_reconciliation_item(source_layer, source_fact_type);

CREATE INDEX IF NOT EXISTS idx_board_eod_reconciliation_diff
ON board_eod_reconciliation_item(diff_type, diff_severity);

CREATE INDEX IF NOT EXISTS idx_board_eod_reconciliation_quality
ON board_eod_reconciliation_item(quality_status);

CREATE INDEX IF NOT EXISTS idx_board_eod_reconciliation_stale
ON board_eod_reconciliation_item(stale_candidate);
