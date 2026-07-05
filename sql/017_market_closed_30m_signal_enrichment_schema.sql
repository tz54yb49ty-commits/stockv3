-- A-share monitor v3 N3 closed 30m signal enrichment schema draft.
-- Stage N3-C2B: additive schema only.
-- Boundary: N3 closed signal enrichment facts only.

CREATE TABLE IF NOT EXISTS stock_closed_30m_signal_enrichment (
  enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  c2b_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  c2_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  current_summary_id BIGINT NOT NULL REFERENCES stock_closed_30m_summary(summary_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_previous_day_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'stock' CHECK (asset_kind = 'stock'),
  identity_key TEXT NOT NULL,
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
  current_window_amount NUMERIC CHECK (current_window_amount IS NULL OR current_window_amount >= 0),
  baseline_window_amount NUMERIC CHECK (baseline_window_amount IS NULL OR baseline_window_amount >= 0),
  closed_amount_ratio NUMERIC CHECK (closed_amount_ratio IS NULL OR closed_amount_ratio >= 0),
  closed_price_change_pct NUMERIC,
  closed_price_direction_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (closed_price_direction_status IN ('up', 'down', 'flat', 'unknown')),
  closed_market_shape_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (closed_market_shape_status IN (
      'up_volume_expanding',
      'up_volume_flat',
      'up_volume_shrinking',
      'down_volume_expanding',
      'down_volume_flat',
      'down_volume_shrinking',
      'flat',
      'unknown'
    )),
  closed_signal_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (closed_signal_status IN (
      'up_volume_expanding',
      'up_volume_flat',
      'up_volume_shrinking',
      'down_volume_expanding',
      'down_volume_flat',
      'down_volume_shrinking',
      'flat',
      'unknown'
    )),
  closed_signal_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (closed_signal_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  closed_signal_basis_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  baseline_trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  calculation_config_hash TEXT NOT NULL,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(c2b_run_id, identity_key, trade_date, bucket_id),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'stock:%'),
  CHECK (bucket_end > bucket_start),
  CHECK (closed_signal_quality_status <> 'passed'
    OR (
      current_window_amount IS NOT NULL
      AND baseline_window_amount IS NOT NULL
      AND baseline_window_amount > 0
      AND closed_amount_ratio IS NOT NULL
      AND closed_price_direction_status <> 'unknown'
      AND closed_signal_status <> 'unknown'
    ))
);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_signal_enrichment_c2b_run
ON stock_closed_30m_signal_enrichment(c2b_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_signal_enrichment_c2_run
ON stock_closed_30m_signal_enrichment(c2_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_signal_enrichment_summary
ON stock_closed_30m_signal_enrichment(current_summary_id);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_signal_enrichment_trade_bucket
ON stock_closed_30m_signal_enrichment(trade_date, bucket_id);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_signal_enrichment_identity_trade
ON stock_closed_30m_signal_enrichment(identity_key, trade_date);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_signal_enrichment_signal
ON stock_closed_30m_signal_enrichment(closed_signal_status);

CREATE INDEX IF NOT EXISTS idx_stock_closed_30m_signal_enrichment_quality
ON stock_closed_30m_signal_enrichment(closed_signal_quality_status);

CREATE TABLE IF NOT EXISTS index_closed_30m_signal_enrichment (
  enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  c2b_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  c2_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  current_summary_id BIGINT NOT NULL REFERENCES index_closed_30m_summary(summary_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_previous_day_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'index' CHECK (asset_kind = 'index'),
  identity_key TEXT NOT NULL,
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
  current_window_amount NUMERIC CHECK (current_window_amount IS NULL OR current_window_amount >= 0),
  baseline_window_amount NUMERIC CHECK (baseline_window_amount IS NULL OR baseline_window_amount >= 0),
  closed_amount_ratio NUMERIC CHECK (closed_amount_ratio IS NULL OR closed_amount_ratio >= 0),
  closed_price_change_pct NUMERIC,
  closed_price_direction_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (closed_price_direction_status IN ('up', 'down', 'flat', 'unknown')),
  closed_market_shape_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (closed_market_shape_status IN (
      'up_volume_expanding',
      'up_volume_flat',
      'up_volume_shrinking',
      'down_volume_expanding',
      'down_volume_flat',
      'down_volume_shrinking',
      'flat',
      'unknown'
    )),
  closed_signal_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (closed_signal_status IN (
      'up_volume_expanding',
      'up_volume_flat',
      'up_volume_shrinking',
      'down_volume_expanding',
      'down_volume_flat',
      'down_volume_shrinking',
      'flat',
      'unknown'
    )),
  closed_signal_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (closed_signal_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  closed_signal_basis_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  baseline_trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  calculation_config_hash TEXT NOT NULL,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(c2b_run_id, identity_key, trade_date, bucket_id),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'index:%'),
  CHECK (bucket_end > bucket_start),
  CHECK (closed_signal_quality_status <> 'passed'
    OR (
      current_window_amount IS NOT NULL
      AND baseline_window_amount IS NOT NULL
      AND baseline_window_amount > 0
      AND closed_amount_ratio IS NOT NULL
      AND closed_price_direction_status <> 'unknown'
      AND closed_signal_status <> 'unknown'
    ))
);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_signal_enrichment_c2b_run
ON index_closed_30m_signal_enrichment(c2b_run_id);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_signal_enrichment_c2_run
ON index_closed_30m_signal_enrichment(c2_run_id);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_signal_enrichment_summary
ON index_closed_30m_signal_enrichment(current_summary_id);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_signal_enrichment_trade_bucket
ON index_closed_30m_signal_enrichment(trade_date, bucket_id);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_signal_enrichment_identity_trade
ON index_closed_30m_signal_enrichment(identity_key, trade_date);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_signal_enrichment_signal
ON index_closed_30m_signal_enrichment(closed_signal_status);

CREATE INDEX IF NOT EXISTS idx_index_closed_30m_signal_enrichment_quality
ON index_closed_30m_signal_enrichment(closed_signal_quality_status);

CREATE TABLE IF NOT EXISTS board_closed_30m_signal_enrichment (
  enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  c2b_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  c2_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  current_summary_id BIGINT NOT NULL REFERENCES board_closed_30m_summary(summary_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_previous_day_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'board' CHECK (asset_kind = 'board'),
  identity_key TEXT NOT NULL,
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
  current_window_amount NUMERIC CHECK (current_window_amount IS NULL OR current_window_amount >= 0),
  baseline_window_amount NUMERIC CHECK (baseline_window_amount IS NULL OR baseline_window_amount >= 0),
  closed_amount_ratio NUMERIC CHECK (closed_amount_ratio IS NULL OR closed_amount_ratio >= 0),
  closed_price_change_pct NUMERIC,
  closed_price_direction_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (closed_price_direction_status IN ('up', 'down', 'flat', 'unknown')),
  closed_market_shape_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (closed_market_shape_status IN (
      'up_volume_expanding',
      'up_volume_flat',
      'up_volume_shrinking',
      'down_volume_expanding',
      'down_volume_flat',
      'down_volume_shrinking',
      'flat',
      'unknown'
    )),
  closed_signal_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (closed_signal_status IN (
      'up_volume_expanding',
      'up_volume_flat',
      'up_volume_shrinking',
      'down_volume_expanding',
      'down_volume_flat',
      'down_volume_shrinking',
      'flat',
      'unknown'
    )),
  closed_signal_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (closed_signal_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  closed_signal_basis_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  baseline_trace_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  calculation_config_hash TEXT NOT NULL,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(c2b_run_id, identity_key, trade_date, bucket_id),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'board:%'),
  CHECK (bucket_end > bucket_start),
  CHECK (closed_signal_quality_status <> 'passed'
    OR (
      current_window_amount IS NOT NULL
      AND baseline_window_amount IS NOT NULL
      AND baseline_window_amount > 0
      AND closed_amount_ratio IS NOT NULL
      AND closed_price_direction_status <> 'unknown'
      AND closed_signal_status <> 'unknown'
    ))
);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_signal_enrichment_c2b_run
ON board_closed_30m_signal_enrichment(c2b_run_id);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_signal_enrichment_c2_run
ON board_closed_30m_signal_enrichment(c2_run_id);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_signal_enrichment_summary
ON board_closed_30m_signal_enrichment(current_summary_id);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_signal_enrichment_trade_bucket
ON board_closed_30m_signal_enrichment(trade_date, bucket_id);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_signal_enrichment_identity_trade
ON board_closed_30m_signal_enrichment(identity_key, trade_date);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_signal_enrichment_signal
ON board_closed_30m_signal_enrichment(closed_signal_status);

CREATE INDEX IF NOT EXISTS idx_board_closed_30m_signal_enrichment_quality
ON board_closed_30m_signal_enrichment(closed_signal_quality_status);
