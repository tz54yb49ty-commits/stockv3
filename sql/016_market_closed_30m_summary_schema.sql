-- A-share monitor v3 N3 closed 30m summary schema draft.
-- Stage N3-C2: additive schema only.
-- Boundary: N3 market-data replay / confirmation facts only.
-- No outbox, inbox, checkpoint, trigger, action, user, voice, mobile, sim,
-- position, worker, or existing B1/B2/N4/N5 runtime changes.

CREATE TABLE IF NOT EXISTS stock_closed_30m_summary (
  summary_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_today_minute_run_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'stock' CHECK (asset_kind = 'stock'),
  stock_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  bucket_id TEXT NOT NULL CHECK (bucket_id IN (
    '0931_1000',
    '1001_1030',
    '1031_1100',
    '1101_1130',
    '1301_1330',
    '1331_1400',
    '1401_1430',
    '1431_1500'
  )),
  bucket_start TIMESTAMPTZ NOT NULL,
  bucket_end TIMESTAMPTZ NOT NULL,
  expected_minute_count INTEGER NOT NULL DEFAULT 30 CHECK (expected_minute_count > 0),
  actual_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (actual_minute_count >= 0),
  missing_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_minute_count >= 0),
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC CHECK (volume IS NULL OR volume >= 0),
  amount NUMERIC CHECK (amount IS NULL OR amount >= 0),
  closed_status TEXT NOT NULL CHECK (closed_status IN ('closed', 'partial', 'missing', 'failed')),
  quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (quality_status IN ('pending', 'passed', 'warning', 'partial', 'missing', 'failed', 'blocked')),
  source_minute_bar_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  replay_diff_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, stock_identity_key, trade_date, bucket_id),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (stock_identity_key LIKE 'stock:%'),
  CHECK (bucket_end > bucket_start),
  CHECK (actual_minute_count <= expected_minute_count),
  CHECK (missing_minute_count <= expected_minute_count),
  CHECK (closed_status = 'failed' OR actual_minute_count + missing_minute_count = expected_minute_count),
  CHECK (closed_status <> 'closed' OR (actual_minute_count = expected_minute_count AND missing_minute_count = 0)),
  CHECK (closed_status <> 'missing' OR actual_minute_count = 0),
  CHECK (cardinality(source_today_minute_run_ids) > 0)
);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_summary_run
ON stock_closed_30m_summary(run_id);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_summary_trade_bucket
ON stock_closed_30m_summary(trade_date, bucket_id);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_summary_identity_trade
ON stock_closed_30m_summary(stock_identity_key, trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_summary_closed_status
ON stock_closed_30m_summary(closed_status);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_summary_quality_status
ON stock_closed_30m_summary(quality_status);

CREATE TABLE IF NOT EXISTS index_closed_30m_summary (
  summary_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_today_minute_run_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'index' CHECK (asset_kind = 'index'),
  index_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  bucket_id TEXT NOT NULL CHECK (bucket_id IN (
    '0931_1000',
    '1001_1030',
    '1031_1100',
    '1101_1130',
    '1301_1330',
    '1331_1400',
    '1401_1430',
    '1431_1500'
  )),
  bucket_start TIMESTAMPTZ NOT NULL,
  bucket_end TIMESTAMPTZ NOT NULL,
  expected_minute_count INTEGER NOT NULL DEFAULT 30 CHECK (expected_minute_count > 0),
  actual_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (actual_minute_count >= 0),
  missing_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_minute_count >= 0),
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC CHECK (volume IS NULL OR volume >= 0),
  amount NUMERIC CHECK (amount IS NULL OR amount >= 0),
  closed_status TEXT NOT NULL CHECK (closed_status IN ('closed', 'partial', 'missing', 'failed')),
  quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (quality_status IN ('pending', 'passed', 'warning', 'partial', 'missing', 'failed', 'blocked')),
  source_minute_bar_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  replay_diff_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, index_identity_key, trade_date, bucket_id),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (index_identity_key LIKE 'index:%'),
  CHECK (bucket_end > bucket_start),
  CHECK (actual_minute_count <= expected_minute_count),
  CHECK (missing_minute_count <= expected_minute_count),
  CHECK (closed_status = 'failed' OR actual_minute_count + missing_minute_count = expected_minute_count),
  CHECK (closed_status <> 'closed' OR (actual_minute_count = expected_minute_count AND missing_minute_count = 0)),
  CHECK (closed_status <> 'missing' OR actual_minute_count = 0),
  CHECK (cardinality(source_today_minute_run_ids) > 0)
);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_summary_run
ON index_closed_30m_summary(run_id);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_summary_trade_bucket
ON index_closed_30m_summary(trade_date, bucket_id);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_summary_identity_trade
ON index_closed_30m_summary(index_identity_key, trade_date);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_summary_closed_status
ON index_closed_30m_summary(closed_status);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_summary_quality_status
ON index_closed_30m_summary(quality_status);

CREATE TABLE IF NOT EXISTS board_closed_30m_summary (
  summary_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_today_minute_run_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'board' CHECK (asset_kind = 'board'),
  board_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  bucket_id TEXT NOT NULL CHECK (bucket_id IN (
    '0931_1000',
    '1001_1030',
    '1031_1100',
    '1101_1130',
    '1301_1330',
    '1331_1400',
    '1401_1430',
    '1431_1500'
  )),
  bucket_start TIMESTAMPTZ NOT NULL,
  bucket_end TIMESTAMPTZ NOT NULL,
  expected_minute_count INTEGER NOT NULL DEFAULT 30 CHECK (expected_minute_count > 0),
  actual_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (actual_minute_count >= 0),
  missing_minute_count INTEGER NOT NULL DEFAULT 0 CHECK (missing_minute_count >= 0),
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC CHECK (volume IS NULL OR volume >= 0),
  amount NUMERIC CHECK (amount IS NULL OR amount >= 0),
  closed_status TEXT NOT NULL CHECK (closed_status IN ('closed', 'partial', 'missing', 'failed')),
  quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (quality_status IN ('pending', 'passed', 'warning', 'partial', 'missing', 'failed', 'blocked')),
  source_minute_bar_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  replay_diff_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, board_identity_key, trade_date, bucket_id),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (board_identity_key LIKE 'board:%'),
  CHECK (bucket_end > bucket_start),
  CHECK (actual_minute_count <= expected_minute_count),
  CHECK (missing_minute_count <= expected_minute_count),
  CHECK (closed_status = 'failed' OR actual_minute_count + missing_minute_count = expected_minute_count),
  CHECK (closed_status <> 'closed' OR (actual_minute_count = expected_minute_count AND missing_minute_count = 0)),
  CHECK (closed_status <> 'missing' OR actual_minute_count = 0),
  CHECK (cardinality(source_today_minute_run_ids) > 0)
);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_summary_run
ON board_closed_30m_summary(run_id);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_summary_trade_bucket
ON board_closed_30m_summary(trade_date, bucket_id);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_summary_identity_trade
ON board_closed_30m_summary(board_identity_key, trade_date);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_summary_closed_status
ON board_closed_30m_summary(closed_status);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_summary_quality_status
ON board_closed_30m_summary(quality_status);
