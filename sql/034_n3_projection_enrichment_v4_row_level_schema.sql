-- N3 projection enrichment v4 row-level materialization additive schema draft.
-- Scope: stock/index/board row-level N3 projection enrichment facts.
-- Boundary: DDL only. No business rows, no outbox/inbox/checkpoint writes,
-- no N4/N5/N6 tables, no worker, no old-system or trade side effects.

BEGIN;

CREATE TABLE IF NOT EXISTS stock_projection_enrichment_v4_metric (
  projection_enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  spec_version TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_today_minute_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_previous_day_minute_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_trigger_context_run_id TEXT,
  source_trigger_context_id BIGINT,
  source_condition_context_enrichment_id BIGINT REFERENCES stock_condition_context_enrichment(stock_condition_context_enrichment_id),
  source_snapshot_id BIGINT REFERENCES stock_realtime_daily_snapshot(snapshot_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'stock' CHECK (asset_kind = 'stock'),
  identity_key TEXT NOT NULL,
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  direction TEXT CHECK (direction IS NULL OR direction IN ('buy', 'sell')),
  condition_key TEXT,
  allowed_signal_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  materialization_row_key TEXT NOT NULL,
  current_price_or_close NUMERIC,
  current_amount_metric NUMERIC CHECK (current_amount_metric IS NULL OR current_amount_metric >= 0),
  current_metric_time TIMESTAMPTZ,
  current_metric_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (current_metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  projection_period TEXT NOT NULL DEFAULT '30m',
  projection_30m_flag BOOLEAN,
  projection_30m_type TEXT NOT NULL DEFAULT 'unknown'
    CHECK (projection_30m_type IN ('volume_up', 'shrink_down', 'none', 'unknown')),
  current_30m_virtual_amount NUMERIC CHECK (current_30m_virtual_amount IS NULL OR current_30m_virtual_amount >= 0),
  reference_30m_amount NUMERIC CHECK (reference_30m_amount IS NULL OR reference_30m_amount >= 0),
  reference_30m_entity_high NUMERIC,
  reference_30m_entity_low NUMERIC,
  trigger_amount_chain_pass JSONB NOT NULL DEFAULT '{}'::JSONB,
  projection_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_freshness_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (source_freshness_status IN ('fresh_complete_lineage', 'source_minute_missing_quality_visible', 'fresh', 'stale', 'missing', 'unknown')),
  metric_ready BOOLEAN NOT NULL DEFAULT false,
  metric_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  quality_visible BOOLEAN NOT NULL DEFAULT false,
  quality_reason TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key = stock_identity_key),
  CHECK (identity_key LIKE 'stock:%'),
  CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (materialization_row_key ~ '^[0-9a-f]{64}$'),
  CHECK (allowed_signal_types <@ ARRAY['BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT']::TEXT[]),
  CHECK (jsonb_typeof(trigger_amount_chain_pass) = 'object'),
  CHECK (jsonb_typeof(projection_lineage_json) = 'object'),
  CHECK (jsonb_typeof(payload_json) = 'object'),
  CHECK (jsonb_typeof(raw_json) = 'object'),
  CHECK (reference_30m_entity_high IS NULL OR reference_30m_entity_low IS NULL OR reference_30m_entity_high >= reference_30m_entity_low),
  CHECK (source_trigger_context_id IS NOT NULL OR source_condition_context_enrichment_id IS NOT NULL),
  CHECK (metric_ready = false OR (
    metric_quality_status = 'passed'
    AND current_metric_quality_status = 'passed'
    AND current_price_or_close IS NOT NULL
    AND current_amount_metric IS NOT NULL
    AND current_metric_time IS NOT NULL
    AND projection_period = '30m'
    AND projection_30m_flag IS NOT NULL
    AND projection_30m_type <> 'unknown'
    AND current_30m_virtual_amount IS NOT NULL
    AND reference_30m_amount IS NOT NULL
    AND reference_30m_entity_high IS NOT NULL
    AND reference_30m_entity_low IS NOT NULL
    AND source_snapshot_run_id IS NOT NULL
    AND source_snapshot_id IS NOT NULL
    AND source_today_minute_run_id IS NOT NULL
    AND source_previous_day_minute_run_id IS NOT NULL
    AND source_freshness_status IN ('fresh_complete_lineage', 'fresh')
    AND trigger_amount_chain_pass <> '{}'::JSONB
    AND projection_lineage_json <> '{}'::JSONB
  )),
  UNIQUE(projection_run_id, materialization_row_key),
  UNIQUE(projection_run_id, spec_version, source_trigger_context_run_id, source_trigger_context_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_projection_enrichment_v4_run
ON stock_projection_enrichment_v4_metric(projection_run_id, metric_quality_status, metric_ready);

CREATE INDEX IF NOT EXISTS idx_stock_projection_enrichment_v4_context
ON stock_projection_enrichment_v4_metric(source_trigger_context_run_id, source_trigger_context_id);

CREATE INDEX IF NOT EXISTS idx_stock_projection_enrichment_v4_condition_context
ON stock_projection_enrichment_v4_metric(source_condition_context_enrichment_id);

CREATE INDEX IF NOT EXISTS idx_stock_projection_enrichment_v4_identity
ON stock_projection_enrichment_v4_metric(trade_date, identity_key, current_metric_time DESC);

CREATE INDEX IF NOT EXISTS idx_stock_projection_enrichment_v4_lineage
ON stock_projection_enrichment_v4_metric(source_snapshot_run_id, source_today_minute_run_id, source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_stock_projection_enrichment_v4_30m
ON stock_projection_enrichment_v4_metric(projection_30m_type, projection_30m_flag, metric_ready);

CREATE INDEX IF NOT EXISTS idx_stock_projection_enrichment_v4_freshness
ON stock_projection_enrichment_v4_metric(source_freshness_status, quality_visible);

CREATE INDEX IF NOT EXISTS idx_stock_projection_enrichment_v4_payload
ON stock_projection_enrichment_v4_metric USING GIN (payload_json);

CREATE INDEX IF NOT EXISTS idx_stock_projection_enrichment_v4_lineage_json
ON stock_projection_enrichment_v4_metric USING GIN (projection_lineage_json);

CREATE TABLE IF NOT EXISTS index_projection_enrichment_v4_metric (
  projection_enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  spec_version TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_today_minute_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_previous_day_minute_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_trigger_context_run_id TEXT,
  source_trigger_context_id BIGINT,
  source_condition_context_enrichment_id BIGINT REFERENCES index_condition_context_enrichment(index_condition_context_enrichment_id),
  source_snapshot_id BIGINT REFERENCES index_realtime_daily_snapshot(snapshot_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'index' CHECK (asset_kind = 'index'),
  identity_key TEXT NOT NULL,
  index_identity_key TEXT NOT NULL REFERENCES index_identity(index_identity_key),
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  direction TEXT CHECK (direction IS NULL OR direction IN ('buy', 'sell')),
  condition_key TEXT,
  allowed_signal_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  materialization_row_key TEXT NOT NULL,
  current_price_or_close NUMERIC,
  current_amount_metric NUMERIC CHECK (current_amount_metric IS NULL OR current_amount_metric >= 0),
  current_metric_time TIMESTAMPTZ,
  current_metric_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (current_metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  projection_period TEXT NOT NULL DEFAULT '30m',
  projection_30m_flag BOOLEAN,
  projection_30m_type TEXT NOT NULL DEFAULT 'unknown'
    CHECK (projection_30m_type IN ('volume_up', 'shrink_down', 'none', 'unknown')),
  current_30m_virtual_amount NUMERIC CHECK (current_30m_virtual_amount IS NULL OR current_30m_virtual_amount >= 0),
  reference_30m_amount NUMERIC CHECK (reference_30m_amount IS NULL OR reference_30m_amount >= 0),
  reference_30m_entity_high NUMERIC,
  reference_30m_entity_low NUMERIC,
  trigger_amount_chain_pass JSONB NOT NULL DEFAULT '{}'::JSONB,
  projection_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_freshness_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (source_freshness_status IN ('fresh_complete_lineage', 'source_minute_missing_quality_visible', 'fresh', 'stale', 'missing', 'unknown')),
  metric_ready BOOLEAN NOT NULL DEFAULT false,
  metric_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  quality_visible BOOLEAN NOT NULL DEFAULT false,
  quality_reason TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key = index_identity_key),
  CHECK (identity_key LIKE 'index:%'),
  CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (materialization_row_key ~ '^[0-9a-f]{64}$'),
  CHECK (allowed_signal_types <@ ARRAY['BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT']::TEXT[]),
  CHECK (jsonb_typeof(trigger_amount_chain_pass) = 'object'),
  CHECK (jsonb_typeof(projection_lineage_json) = 'object'),
  CHECK (jsonb_typeof(payload_json) = 'object'),
  CHECK (jsonb_typeof(raw_json) = 'object'),
  CHECK (reference_30m_entity_high IS NULL OR reference_30m_entity_low IS NULL OR reference_30m_entity_high >= reference_30m_entity_low),
  CHECK (source_trigger_context_id IS NOT NULL OR source_condition_context_enrichment_id IS NOT NULL),
  CHECK (metric_ready = false OR (
    metric_quality_status = 'passed'
    AND current_metric_quality_status = 'passed'
    AND current_price_or_close IS NOT NULL
    AND current_amount_metric IS NOT NULL
    AND current_metric_time IS NOT NULL
    AND projection_period = '30m'
    AND projection_30m_flag IS NOT NULL
    AND projection_30m_type <> 'unknown'
    AND current_30m_virtual_amount IS NOT NULL
    AND reference_30m_amount IS NOT NULL
    AND reference_30m_entity_high IS NOT NULL
    AND reference_30m_entity_low IS NOT NULL
    AND source_snapshot_run_id IS NOT NULL
    AND source_snapshot_id IS NOT NULL
    AND source_today_minute_run_id IS NOT NULL
    AND source_previous_day_minute_run_id IS NOT NULL
    AND source_freshness_status IN ('fresh_complete_lineage', 'fresh')
    AND trigger_amount_chain_pass <> '{}'::JSONB
    AND projection_lineage_json <> '{}'::JSONB
  )),
  UNIQUE(projection_run_id, materialization_row_key),
  UNIQUE(projection_run_id, spec_version, source_trigger_context_run_id, source_trigger_context_id)
);

CREATE INDEX IF NOT EXISTS idx_index_projection_enrichment_v4_run
ON index_projection_enrichment_v4_metric(projection_run_id, metric_quality_status, metric_ready);

CREATE INDEX IF NOT EXISTS idx_index_projection_enrichment_v4_context
ON index_projection_enrichment_v4_metric(source_trigger_context_run_id, source_trigger_context_id);

CREATE INDEX IF NOT EXISTS idx_index_projection_enrichment_v4_condition_context
ON index_projection_enrichment_v4_metric(source_condition_context_enrichment_id);

CREATE INDEX IF NOT EXISTS idx_index_projection_enrichment_v4_identity
ON index_projection_enrichment_v4_metric(trade_date, identity_key, current_metric_time DESC);

CREATE INDEX IF NOT EXISTS idx_index_projection_enrichment_v4_lineage
ON index_projection_enrichment_v4_metric(source_snapshot_run_id, source_today_minute_run_id, source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_index_projection_enrichment_v4_30m
ON index_projection_enrichment_v4_metric(projection_30m_type, projection_30m_flag, metric_ready);

CREATE INDEX IF NOT EXISTS idx_index_projection_enrichment_v4_freshness
ON index_projection_enrichment_v4_metric(source_freshness_status, quality_visible);

CREATE INDEX IF NOT EXISTS idx_index_projection_enrichment_v4_payload
ON index_projection_enrichment_v4_metric USING GIN (payload_json);

CREATE INDEX IF NOT EXISTS idx_index_projection_enrichment_v4_lineage_json
ON index_projection_enrichment_v4_metric USING GIN (projection_lineage_json);

CREATE TABLE IF NOT EXISTS board_projection_enrichment_v4_metric (
  projection_enrichment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  spec_version TEXT NOT NULL,
  policy_hash TEXT NOT NULL,
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_today_minute_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_previous_day_minute_run_id TEXT REFERENCES common_market_data_run(run_id),
  source_trigger_context_run_id TEXT,
  source_trigger_context_id BIGINT,
  source_condition_context_enrichment_id BIGINT REFERENCES board_condition_context_enrichment(board_condition_context_enrichment_id),
  source_snapshot_id BIGINT REFERENCES board_realtime_daily_snapshot(snapshot_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'board' CHECK (asset_kind = 'board'),
  identity_key TEXT NOT NULL,
  board_identity_key TEXT NOT NULL REFERENCES board_identity(board_identity_key),
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  direction TEXT CHECK (direction IS NULL OR direction IN ('buy', 'sell')),
  condition_key TEXT,
  allowed_signal_types TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  materialization_row_key TEXT NOT NULL,
  current_price_or_close NUMERIC,
  current_amount_metric NUMERIC CHECK (current_amount_metric IS NULL OR current_amount_metric >= 0),
  current_metric_time TIMESTAMPTZ,
  current_metric_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (current_metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  projection_period TEXT NOT NULL DEFAULT '30m',
  projection_30m_flag BOOLEAN,
  projection_30m_type TEXT NOT NULL DEFAULT 'unknown'
    CHECK (projection_30m_type IN ('volume_up', 'shrink_down', 'none', 'unknown')),
  current_30m_virtual_amount NUMERIC CHECK (current_30m_virtual_amount IS NULL OR current_30m_virtual_amount >= 0),
  reference_30m_amount NUMERIC CHECK (reference_30m_amount IS NULL OR reference_30m_amount >= 0),
  reference_30m_entity_high NUMERIC,
  reference_30m_entity_low NUMERIC,
  trigger_amount_chain_pass JSONB NOT NULL DEFAULT '{}'::JSONB,
  projection_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_freshness_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (source_freshness_status IN ('fresh_complete_lineage', 'source_minute_missing_quality_visible', 'fresh', 'stale', 'missing', 'unknown')),
  metric_ready BOOLEAN NOT NULL DEFAULT false,
  metric_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  quality_visible BOOLEAN NOT NULL DEFAULT false,
  quality_reason TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key = board_identity_key),
  CHECK (identity_key LIKE 'board:%'),
  CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (materialization_row_key ~ '^[0-9a-f]{64}$'),
  CHECK (allowed_signal_types <@ ARRAY['BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT']::TEXT[]),
  CHECK (jsonb_typeof(trigger_amount_chain_pass) = 'object'),
  CHECK (jsonb_typeof(projection_lineage_json) = 'object'),
  CHECK (jsonb_typeof(payload_json) = 'object'),
  CHECK (jsonb_typeof(raw_json) = 'object'),
  CHECK (reference_30m_entity_high IS NULL OR reference_30m_entity_low IS NULL OR reference_30m_entity_high >= reference_30m_entity_low),
  CHECK (source_trigger_context_id IS NOT NULL OR source_condition_context_enrichment_id IS NOT NULL),
  CHECK (metric_ready = false OR (
    metric_quality_status = 'passed'
    AND current_metric_quality_status = 'passed'
    AND current_price_or_close IS NOT NULL
    AND current_amount_metric IS NOT NULL
    AND current_metric_time IS NOT NULL
    AND projection_period = '30m'
    AND projection_30m_flag IS NOT NULL
    AND projection_30m_type <> 'unknown'
    AND current_30m_virtual_amount IS NOT NULL
    AND reference_30m_amount IS NOT NULL
    AND reference_30m_entity_high IS NOT NULL
    AND reference_30m_entity_low IS NOT NULL
    AND source_snapshot_run_id IS NOT NULL
    AND source_snapshot_id IS NOT NULL
    AND source_today_minute_run_id IS NOT NULL
    AND source_previous_day_minute_run_id IS NOT NULL
    AND source_freshness_status IN ('fresh_complete_lineage', 'fresh')
    AND trigger_amount_chain_pass <> '{}'::JSONB
    AND projection_lineage_json <> '{}'::JSONB
  )),
  UNIQUE(projection_run_id, materialization_row_key),
  UNIQUE(projection_run_id, spec_version, source_trigger_context_run_id, source_trigger_context_id)
);

CREATE INDEX IF NOT EXISTS idx_board_projection_enrichment_v4_run
ON board_projection_enrichment_v4_metric(projection_run_id, metric_quality_status, metric_ready);

CREATE INDEX IF NOT EXISTS idx_board_projection_enrichment_v4_context
ON board_projection_enrichment_v4_metric(source_trigger_context_run_id, source_trigger_context_id);

CREATE INDEX IF NOT EXISTS idx_board_projection_enrichment_v4_condition_context
ON board_projection_enrichment_v4_metric(source_condition_context_enrichment_id);

CREATE INDEX IF NOT EXISTS idx_board_projection_enrichment_v4_identity
ON board_projection_enrichment_v4_metric(trade_date, identity_key, current_metric_time DESC);

CREATE INDEX IF NOT EXISTS idx_board_projection_enrichment_v4_lineage
ON board_projection_enrichment_v4_metric(source_snapshot_run_id, source_today_minute_run_id, source_previous_day_minute_run_id);

CREATE INDEX IF NOT EXISTS idx_board_projection_enrichment_v4_30m
ON board_projection_enrichment_v4_metric(projection_30m_type, projection_30m_flag, metric_ready);

CREATE INDEX IF NOT EXISTS idx_board_projection_enrichment_v4_freshness
ON board_projection_enrichment_v4_metric(source_freshness_status, quality_visible);

CREATE INDEX IF NOT EXISTS idx_board_projection_enrichment_v4_payload
ON board_projection_enrichment_v4_metric USING GIN (payload_json);

CREATE INDEX IF NOT EXISTS idx_board_projection_enrichment_v4_lineage_json
ON board_projection_enrichment_v4_metric USING GIN (projection_lineage_json);

COMMIT;
