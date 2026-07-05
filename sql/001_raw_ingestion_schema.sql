-- A-share monitor v3 raw ingestion schema draft.
-- Stage N1 only: review before running in any PostgreSQL database.

BEGIN;

CREATE TABLE common_ingest_batch (
  batch_id TEXT PRIMARY KEY,
  trade_date TEXT NOT NULL,
  data_domain TEXT NOT NULL CHECK (data_domain IN ('common', 'stock', 'index', 'board')),
  data_type TEXT NOT NULL,
  source TEXT NOT NULL,
  source_version TEXT NOT NULL,
  source_path TEXT,
  source_params JSONB,
  raw_hash TEXT,
  row_count INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
  error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
  quality_gate_summary JSONB,
  error_summary TEXT,
  rollback_strategy TEXT NOT NULL DEFAULT 'delete_by_source_batch_id',
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'passed', 'failed', 'rolled_back')),
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX idx_common_ingest_batch_domain_type
ON common_ingest_batch(data_domain, data_type, trade_date);

CREATE INDEX idx_common_ingest_batch_source_version
ON common_ingest_batch(source_version);

CREATE TABLE common_quality_gate_result (
  gate_result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id) ON DELETE CASCADE,
  source_version TEXT NOT NULL,
  data_domain TEXT NOT NULL CHECK (data_domain IN ('common', 'stock', 'index', 'board')),
  data_type TEXT NOT NULL,
  gate_name TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('P0', 'P1', 'P2')),
  status TEXT NOT NULL CHECK (status IN ('passed', 'failed', 'warning')),
  expected_value TEXT,
  actual_value TEXT,
  details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_common_quality_gate_batch
ON common_quality_gate_result(source_batch_id);

CREATE INDEX idx_common_quality_gate_status
ON common_quality_gate_result(status, severity);

CREATE TABLE common_active_source_version (
  data_domain TEXT NOT NULL CHECK (data_domain IN ('common', 'stock', 'index', 'board')),
  data_type TEXT NOT NULL,
  scope_key TEXT NOT NULL,
  source_version TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  previous_source_version TEXT,
  activated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  activated_by TEXT NOT NULL DEFAULT 'ingestion',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(data_domain, data_type, scope_key)
);

CREATE INDEX idx_common_active_source_version_batch
ON common_active_source_version(source_batch_id);

CREATE TABLE common_trade_calendar (
  trade_date TEXT PRIMARY KEY,
  exchange TEXT NOT NULL DEFAULT 'SSE',
  is_open BOOLEAN NOT NULL,
  prev_trade_date TEXT,
  next_trade_date TEXT,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (trade_date ~ '^[0-9]{8}$')
);

CREATE INDEX idx_common_trade_calendar_open
ON common_trade_calendar(is_open, trade_date);

CREATE TABLE stock_identity (
  stock_identity_key TEXT PRIMARY KEY,
  ts_code TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ')),
  name TEXT NOT NULL,
  display_code TEXT,
  area TEXT,
  industry TEXT,
  market TEXT,
  listed_date TEXT,
  delisted_date TEXT,
  is_st BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'delisted', 'paused', 'unknown')),
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(ts_code),
  UNIQUE(exchange, code),
  CHECK (stock_identity_key = 'stock:' || exchange || ':' || code),
  CHECK (code ~ '^[0-9]{6}$'),
  CHECK (code !~ '^88[0-9]{4}$')
);

CREATE INDEX idx_stock_identity_status
ON stock_identity(status, exchange, code);

CREATE INDEX idx_stock_identity_source_batch
ON stock_identity(source_batch_id);

CREATE TABLE index_identity (
  index_identity_key TEXT PRIMARY KEY,
  ts_code TEXT,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ', 'CSI', 'CNI', 'SW', 'TDX', 'OTH', 'UNKNOWN')),
  name TEXT NOT NULL,
  source_namespace TEXT NOT NULL DEFAULT 'TUSHARE',
  publisher TEXT,
  index_category TEXT,
  base_date TEXT,
  listed_date TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'unknown')),
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(exchange, code),
  CHECK (index_identity_key = 'index:' || exchange || ':' || code),
  CHECK (code ~ '^[0-9]{6}$')
);

CREATE UNIQUE INDEX uniq_index_identity_ts_code
ON index_identity(ts_code)
WHERE ts_code IS NOT NULL;

CREATE INDEX idx_index_identity_status
ON index_identity(status, exchange, code);

CREATE INDEX idx_index_identity_source_batch
ON index_identity(source_batch_id);

CREATE TABLE board_identity (
  board_identity_key TEXT PRIMARY KEY,
  board_code TEXT NOT NULL,
  board_name TEXT NOT NULL,
  board_type TEXT NOT NULL CHECK (board_type IN ('tdx_region', 'tdx_concept', 'tdx_industry', 'tdx_other')),
  source_namespace TEXT NOT NULL DEFAULT 'TDX',
  source_file TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'unknown')),
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(source_namespace, board_code),
  CHECK (board_identity_key = 'board:' || source_namespace || ':' || board_code),
  CHECK (board_code ~ '^[0-9]{6}$')
);

CREATE INDEX idx_board_identity_type
ON board_identity(board_type, board_code);

CREATE INDEX idx_board_identity_source_batch
ON board_identity(source_batch_id);

CREATE TABLE stock_daily_bar_fact (
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  trade_date TEXT NOT NULL,
  ts_code TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ')),
  name TEXT,
  open NUMERIC NOT NULL,
  high NUMERIC NOT NULL,
  low NUMERIC NOT NULL,
  close NUMERIC NOT NULL,
  volume NUMERIC,
  amount NUMERIC,
  adj_factor NUMERIC,
  adjust_type TEXT NOT NULL DEFAULT 'qfq' CHECK (adjust_type IN ('qfq')),
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  official_daily_proof BOOLEAN NOT NULL DEFAULT false,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(stock_identity_key, trade_date, source_version),
  CHECK (stock_identity_key = 'stock:' || exchange || ':' || code),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (code ~ '^[0-9]{6}$'),
  CHECK (code !~ '^88[0-9]{4}$')
);

CREATE INDEX idx_stock_daily_trade_date
ON stock_daily_bar_fact(trade_date);

CREATE INDEX idx_stock_daily_code_date
ON stock_daily_bar_fact(code, trade_date DESC);

CREATE INDEX idx_stock_daily_source_batch
ON stock_daily_bar_fact(source_batch_id);

CREATE TABLE stock_daily_basic (
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  trade_date TEXT NOT NULL,
  ts_code TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ')),
  close NUMERIC,
  turnover_rate NUMERIC,
  turnover_rate_f NUMERIC,
  volume_ratio NUMERIC,
  pe NUMERIC,
  pe_ttm NUMERIC,
  pb NUMERIC,
  ps NUMERIC,
  ps_ttm NUMERIC,
  dv_ratio NUMERIC,
  dv_ttm NUMERIC,
  total_share NUMERIC,
  float_share NUMERIC,
  free_share NUMERIC,
  total_mv NUMERIC,
  circ_mv NUMERIC,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(stock_identity_key, trade_date, source_version),
  CHECK (stock_identity_key = 'stock:' || exchange || ':' || code),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (code ~ '^[0-9]{6}$'),
  CHECK (code !~ '^88[0-9]{4}$')
);

CREATE INDEX idx_stock_daily_basic_trade_date
ON stock_daily_basic(trade_date);

CREATE INDEX idx_stock_daily_basic_code_date
ON stock_daily_basic(code, trade_date DESC);

CREATE INDEX idx_stock_daily_basic_source_batch
ON stock_daily_basic(source_batch_id);

CREATE TABLE index_daily_bar_fact (
  index_identity_key TEXT NOT NULL REFERENCES index_identity(index_identity_key),
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ', 'CSI', 'CNI', 'SW', 'TDX', 'OTH', 'UNKNOWN')),
  name TEXT,
  open NUMERIC NOT NULL,
  high NUMERIC NOT NULL,
  low NUMERIC NOT NULL,
  close NUMERIC NOT NULL,
  volume NUMERIC,
  amount NUMERIC,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(index_identity_key, trade_date, source_version),
  CHECK (index_identity_key = 'index:' || exchange || ':' || code),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (code ~ '^[0-9]{6}$')
);

CREATE INDEX idx_index_daily_trade_date
ON index_daily_bar_fact(trade_date);

CREATE INDEX idx_index_daily_code_date
ON index_daily_bar_fact(code, trade_date DESC);

CREATE INDEX idx_index_daily_source_batch
ON index_daily_bar_fact(source_batch_id);

CREATE TABLE board_daily_bar_fact (
  board_identity_key TEXT NOT NULL REFERENCES board_identity(board_identity_key),
  trade_date TEXT NOT NULL,
  board_code TEXT NOT NULL,
  board_name TEXT,
  board_type TEXT NOT NULL CHECK (board_type IN ('tdx_region', 'tdx_concept', 'tdx_industry', 'tdx_other')),
  open NUMERIC NOT NULL,
  high NUMERIC NOT NULL,
  low NUMERIC NOT NULL,
  close NUMERIC NOT NULL,
  volume NUMERIC,
  amount NUMERIC,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(board_identity_key, trade_date, source_version),
  CHECK (board_identity_key = 'board:TDX:' || board_code),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (board_code ~ '^88[0-9]{4}$')
);

CREATE INDEX idx_board_daily_trade_date
ON board_daily_bar_fact(trade_date);

CREATE INDEX idx_board_daily_code_date
ON board_daily_bar_fact(board_code, trade_date DESC);

CREATE INDEX idx_board_daily_source_batch
ON board_daily_bar_fact(source_batch_id);

CREATE TABLE stock_financial_metrics_fact (
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  asof_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  announcement_date TEXT,
  report_period TEXT,
  ts_code TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL CHECK (exchange IN ('SH', 'SZ', 'BJ')),
  roe NUMERIC,
  revenue_yoy NUMERIC,
  profit_yoy NUMERIC,
  total_revenue NUMERIC,
  net_profit NUMERIC,
  net_assets NUMERIC,
  eps NUMERIC,
  bps NUMERIC,
  pe_core NUMERIC,
  total_mv NUMERIC,
  circ_mv NUMERIC,
  score NUMERIC,
  warning TEXT,
  quality_status TEXT NOT NULL DEFAULT 'passed' CHECK (quality_status IN ('passed', 'warning', 'failed')),
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(stock_identity_key, asof_date, source_version),
  CHECK (stock_identity_key = 'stock:' || exchange || ':' || code),
  CHECK (asof_date ~ '^[0-9]{8}$'),
  CHECK (source_trade_date ~ '^[0-9]{8}$'),
  CHECK (announcement_date IS NULL OR announcement_date ~ '^[0-9]{8}$'),
  CHECK (code ~ '^[0-9]{6}$'),
  CHECK (code !~ '^88[0-9]{4}$')
);

CREATE INDEX idx_stock_financial_asof_date
ON stock_financial_metrics_fact(asof_date);

CREATE INDEX idx_stock_financial_source_trade_date
ON stock_financial_metrics_fact(source_trade_date);

CREATE INDEX idx_stock_financial_source_trade_version
ON stock_financial_metrics_fact(source_trade_date, source_version);

CREATE INDEX idx_stock_financial_code_date
ON stock_financial_metrics_fact(code, asof_date DESC);

CREATE INDEX idx_stock_financial_source_batch
ON stock_financial_metrics_fact(source_batch_id);

CREATE TABLE index_membership_fact (
  trade_date TEXT NOT NULL,
  index_identity_key TEXT NOT NULL REFERENCES index_identity(index_identity_key),
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  index_code TEXT NOT NULL,
  index_name TEXT,
  stock_code TEXT NOT NULL,
  stock_name TEXT,
  source TEXT NOT NULL,
  source_file TEXT,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(trade_date, index_identity_key, stock_identity_key, source_version),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (index_code ~ '^[0-9]{6}$'),
  CHECK (stock_code ~ '^[0-9]{6}$'),
  CHECK (stock_code !~ '^88[0-9]{4}$')
);

CREATE INDEX idx_index_membership_stock
ON index_membership_fact(stock_identity_key, trade_date);

CREATE INDEX idx_index_membership_source_batch
ON index_membership_fact(source_batch_id);

CREATE TABLE board_membership_fact (
  trade_date TEXT NOT NULL,
  board_identity_key TEXT NOT NULL REFERENCES board_identity(board_identity_key),
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  board_code TEXT NOT NULL,
  board_name TEXT,
  board_type TEXT NOT NULL CHECK (board_type IN ('tdx_region', 'tdx_concept', 'tdx_industry', 'tdx_other')),
  stock_code TEXT NOT NULL,
  stock_name TEXT,
  source TEXT NOT NULL,
  source_file TEXT,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(trade_date, board_identity_key, stock_identity_key, source_version),
  CHECK (board_identity_key = 'board:TDX:' || board_code),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (board_code ~ '^[0-9]{6}$'),
  CHECK (stock_code ~ '^[0-9]{6}$'),
  CHECK (stock_code !~ '^88[0-9]{4}$')
);

CREATE INDEX idx_board_membership_stock
ON board_membership_fact(stock_identity_key, trade_date);

CREATE INDEX idx_board_membership_source_batch
ON board_membership_fact(source_batch_id);

COMMIT;
