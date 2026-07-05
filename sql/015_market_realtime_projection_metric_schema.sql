-- A-share monitor v3 N3 realtime projection metric schema draft.
-- Stage N3-P1: additive schema draft only.
-- Boundary: N3 market-data projection facts only; no trigger/action/user/voice/mobile/sim
-- objects, no event type changes, no outbox consumption, and no worker state.
--
-- This migration intentionally does not alter existing pending MarketSnapshotUpdated
-- outbox payloads. Projection facts are canonical v1 storage for N4 to read by
-- snapshot_id / projection_id after N4 consumes N3 standard events.

BEGIN;

CREATE TABLE IF NOT EXISTS stock_realtime_projection_metric (
  projection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  source_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  snapshot_id BIGINT NOT NULL REFERENCES stock_realtime_daily_snapshot(snapshot_id) ON DELETE CASCADE,
  snapshot_event_id TEXT NOT NULL,
  subscription_id BIGINT NOT NULL REFERENCES common_market_data_subscription(subscription_id),
  pull_plan_id BIGINT NOT NULL REFERENCES common_market_data_pull_plan(pull_plan_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  stock_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  projection_schema_version TEXT NOT NULL DEFAULT 'n3.realtime_projection.v1',
  projection_window_kind TEXT NOT NULL DEFAULT 'active_30m_bucket_projection'
    CHECK (projection_window_kind IN ('active_30m_bucket_projection')),
  projection_window_id TEXT NOT NULL,
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  snapshot_time TIMESTAMPTZ NOT NULL,
  elapsed_seconds INTEGER NOT NULL CHECK (elapsed_seconds >= 0),
  window_total_seconds INTEGER NOT NULL CHECK (window_total_seconds > 0),
  completion_ratio NUMERIC NOT NULL CHECK (completion_ratio >= 0),
  is_window_closed BOOLEAN NOT NULL DEFAULT false,
  session_id TEXT NOT NULL,
  rolling_5m_amount_avg NUMERIC CHECK (rolling_5m_amount_avg IS NULL OR rolling_5m_amount_avg >= 0),
  elapsed_amount NUMERIC CHECK (elapsed_amount IS NULL OR elapsed_amount >= 0),
  projected_30m_amount NUMERIC CHECK (projected_30m_amount IS NULL OR projected_30m_amount >= 0),
  previous_day_same_window_amount NUMERIC CHECK (previous_day_same_window_amount IS NULL OR previous_day_same_window_amount >= 0),
  previous_day_same_elapsed_amount NUMERIC CHECK (previous_day_same_elapsed_amount IS NULL OR previous_day_same_elapsed_amount >= 0),
  amount_projection_ratio NUMERIC CHECK (amount_projection_ratio IS NULL OR amount_projection_ratio >= 0),
  elapsed_amount_ratio NUMERIC CHECK (elapsed_amount_ratio IS NULL OR elapsed_amount_ratio >= 0),
  latest_price NUMERIC,
  window_open_price NUMERIC,
  window_high_price NUMERIC,
  window_low_price NUMERIC,
  price_change_pct NUMERIC,
  price_direction_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (price_direction_status IN ('up', 'down', 'flat', 'unknown')),
  projection_status TEXT NOT NULL DEFAULT 'not_ready'
    CHECK (projection_status IN ('ready', 'not_ready', 'quality_blocked')),
  projection_signal_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (projection_signal_status IN (
      'up_volume_expanding',
      'down_volume_shrinking',
      'up_volume_flat',
      'down_volume_flat',
      'up_volume_shrinking',
      'down_volume_expanding',
      'flat',
      'unknown'
    )),
  projection_quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (projection_quality_status IN ('passed', 'pending', 'warning', 'failed', 'blocked')),
  trace_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (trace_status IN ('passed', 'pending', 'warning', 'failed', 'blocked')),
  amount_basis_kind TEXT NOT NULL DEFAULT 'not_available'
    CHECK (amount_basis_kind IN (
      'previous_day_same_window',
      'previous_day_same_elapsed',
      'snapshot_delta_anchor',
      'minute_bar_elapsed',
      'adapter_projection',
      'not_available'
    )),
  source_fact_kind TEXT NOT NULL DEFAULT 'mixed'
    CHECK (source_fact_kind IN (
      'realtime_daily_snapshot',
      'minute_bar_1m_elapsed',
      'snapshot_delta_anchor',
      'previous_day_minute_bar_1m',
      'adapter_projection',
      'mixed'
    )),
  source_fact_ids JSONB NOT NULL DEFAULT '{}'::JSONB,
  minute_bar_ids_used BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  previous_day_minute_bar_ids_used BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  quality_item_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_adapter TEXT NOT NULL,
  calculation_method TEXT NOT NULL,
  calculation_config_hash TEXT NOT NULL,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (
    projection_run_id,
    trade_date,
    stock_identity_key,
    projection_window_id,
    snapshot_time,
    source_adapter,
    projection_schema_version
  ),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (stock_identity_key LIKE 'stock:%'),
  CHECK (window_end > window_start),
  CHECK (snapshot_time >= window_start),
  CHECK (snapshot_time <= window_end)
);

CREATE INDEX IF NOT EXISTS idx_stock_realtime_projection_metric_lookup
ON stock_realtime_projection_metric(trade_date, stock_identity_key, projection_window_id, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_stock_realtime_projection_metric_run
ON stock_realtime_projection_metric(projection_run_id, projection_quality_status, projection_status);

CREATE INDEX IF NOT EXISTS idx_stock_realtime_projection_metric_snapshot
ON stock_realtime_projection_metric(source_snapshot_run_id, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_stock_realtime_projection_metric_signal
ON stock_realtime_projection_metric(for_trade_date, projection_signal_status, projection_quality_status);

CREATE TABLE IF NOT EXISTS index_realtime_projection_metric (
  projection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  source_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  snapshot_id BIGINT NOT NULL REFERENCES index_realtime_daily_snapshot(snapshot_id) ON DELETE CASCADE,
  snapshot_event_id TEXT NOT NULL,
  subscription_id BIGINT NOT NULL REFERENCES common_market_data_subscription(subscription_id),
  pull_plan_id BIGINT NOT NULL REFERENCES common_market_data_pull_plan(pull_plan_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  index_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  projection_schema_version TEXT NOT NULL DEFAULT 'n3.realtime_projection.v1',
  projection_window_kind TEXT NOT NULL DEFAULT 'active_30m_bucket_projection'
    CHECK (projection_window_kind IN ('active_30m_bucket_projection')),
  projection_window_id TEXT NOT NULL,
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  snapshot_time TIMESTAMPTZ NOT NULL,
  elapsed_seconds INTEGER NOT NULL CHECK (elapsed_seconds >= 0),
  window_total_seconds INTEGER NOT NULL CHECK (window_total_seconds > 0),
  completion_ratio NUMERIC NOT NULL CHECK (completion_ratio >= 0),
  is_window_closed BOOLEAN NOT NULL DEFAULT false,
  session_id TEXT NOT NULL,
  rolling_5m_amount_avg NUMERIC CHECK (rolling_5m_amount_avg IS NULL OR rolling_5m_amount_avg >= 0),
  elapsed_amount NUMERIC CHECK (elapsed_amount IS NULL OR elapsed_amount >= 0),
  projected_30m_amount NUMERIC CHECK (projected_30m_amount IS NULL OR projected_30m_amount >= 0),
  previous_day_same_window_amount NUMERIC CHECK (previous_day_same_window_amount IS NULL OR previous_day_same_window_amount >= 0),
  previous_day_same_elapsed_amount NUMERIC CHECK (previous_day_same_elapsed_amount IS NULL OR previous_day_same_elapsed_amount >= 0),
  amount_projection_ratio NUMERIC CHECK (amount_projection_ratio IS NULL OR amount_projection_ratio >= 0),
  elapsed_amount_ratio NUMERIC CHECK (elapsed_amount_ratio IS NULL OR elapsed_amount_ratio >= 0),
  latest_price NUMERIC,
  window_open_price NUMERIC,
  window_high_price NUMERIC,
  window_low_price NUMERIC,
  price_change_pct NUMERIC,
  price_direction_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (price_direction_status IN ('up', 'down', 'flat', 'unknown')),
  projection_status TEXT NOT NULL DEFAULT 'not_ready'
    CHECK (projection_status IN ('ready', 'not_ready', 'quality_blocked')),
  projection_signal_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (projection_signal_status IN (
      'up_volume_expanding',
      'down_volume_shrinking',
      'up_volume_flat',
      'down_volume_flat',
      'up_volume_shrinking',
      'down_volume_expanding',
      'flat',
      'unknown'
    )),
  projection_quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (projection_quality_status IN ('passed', 'pending', 'warning', 'failed', 'blocked')),
  trace_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (trace_status IN ('passed', 'pending', 'warning', 'failed', 'blocked')),
  amount_basis_kind TEXT NOT NULL DEFAULT 'not_available'
    CHECK (amount_basis_kind IN (
      'previous_day_same_window',
      'previous_day_same_elapsed',
      'snapshot_delta_anchor',
      'minute_bar_elapsed',
      'adapter_projection',
      'not_available'
    )),
  source_fact_kind TEXT NOT NULL DEFAULT 'mixed'
    CHECK (source_fact_kind IN (
      'realtime_daily_snapshot',
      'minute_bar_1m_elapsed',
      'snapshot_delta_anchor',
      'previous_day_minute_bar_1m',
      'adapter_projection',
      'mixed'
    )),
  source_fact_ids JSONB NOT NULL DEFAULT '{}'::JSONB,
  minute_bar_ids_used BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  previous_day_minute_bar_ids_used BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  quality_item_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_adapter TEXT NOT NULL,
  calculation_method TEXT NOT NULL,
  calculation_config_hash TEXT NOT NULL,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (
    projection_run_id,
    trade_date,
    index_identity_key,
    projection_window_id,
    snapshot_time,
    source_adapter,
    projection_schema_version
  ),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (index_identity_key LIKE 'index:%'),
  CHECK (window_end > window_start),
  CHECK (snapshot_time >= window_start),
  CHECK (snapshot_time <= window_end)
);

CREATE INDEX IF NOT EXISTS idx_index_realtime_projection_metric_lookup
ON index_realtime_projection_metric(trade_date, index_identity_key, projection_window_id, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_index_realtime_projection_metric_run
ON index_realtime_projection_metric(projection_run_id, projection_quality_status, projection_status);

CREATE INDEX IF NOT EXISTS idx_index_realtime_projection_metric_snapshot
ON index_realtime_projection_metric(source_snapshot_run_id, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_index_realtime_projection_metric_signal
ON index_realtime_projection_metric(for_trade_date, projection_signal_status, projection_quality_status);

CREATE TABLE IF NOT EXISTS board_realtime_projection_metric (
  projection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id) ON DELETE CASCADE,
  source_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  snapshot_id BIGINT NOT NULL REFERENCES board_realtime_daily_snapshot(snapshot_id) ON DELETE CASCADE,
  snapshot_event_id TEXT NOT NULL,
  subscription_id BIGINT NOT NULL REFERENCES common_market_data_subscription(subscription_id),
  pull_plan_id BIGINT NOT NULL REFERENCES common_market_data_pull_plan(pull_plan_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  board_identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  projection_schema_version TEXT NOT NULL DEFAULT 'n3.realtime_projection.v1',
  projection_window_kind TEXT NOT NULL DEFAULT 'active_30m_bucket_projection'
    CHECK (projection_window_kind IN ('active_30m_bucket_projection')),
  projection_window_id TEXT NOT NULL,
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  snapshot_time TIMESTAMPTZ NOT NULL,
  elapsed_seconds INTEGER NOT NULL CHECK (elapsed_seconds >= 0),
  window_total_seconds INTEGER NOT NULL CHECK (window_total_seconds > 0),
  completion_ratio NUMERIC NOT NULL CHECK (completion_ratio >= 0),
  is_window_closed BOOLEAN NOT NULL DEFAULT false,
  session_id TEXT NOT NULL,
  rolling_5m_amount_avg NUMERIC CHECK (rolling_5m_amount_avg IS NULL OR rolling_5m_amount_avg >= 0),
  elapsed_amount NUMERIC CHECK (elapsed_amount IS NULL OR elapsed_amount >= 0),
  projected_30m_amount NUMERIC CHECK (projected_30m_amount IS NULL OR projected_30m_amount >= 0),
  previous_day_same_window_amount NUMERIC CHECK (previous_day_same_window_amount IS NULL OR previous_day_same_window_amount >= 0),
  previous_day_same_elapsed_amount NUMERIC CHECK (previous_day_same_elapsed_amount IS NULL OR previous_day_same_elapsed_amount >= 0),
  amount_projection_ratio NUMERIC CHECK (amount_projection_ratio IS NULL OR amount_projection_ratio >= 0),
  elapsed_amount_ratio NUMERIC CHECK (elapsed_amount_ratio IS NULL OR elapsed_amount_ratio >= 0),
  latest_price NUMERIC,
  window_open_price NUMERIC,
  window_high_price NUMERIC,
  window_low_price NUMERIC,
  price_change_pct NUMERIC,
  price_direction_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (price_direction_status IN ('up', 'down', 'flat', 'unknown')),
  projection_status TEXT NOT NULL DEFAULT 'not_ready'
    CHECK (projection_status IN ('ready', 'not_ready', 'quality_blocked')),
  projection_signal_status TEXT NOT NULL DEFAULT 'unknown'
    CHECK (projection_signal_status IN (
      'up_volume_expanding',
      'down_volume_shrinking',
      'up_volume_flat',
      'down_volume_flat',
      'up_volume_shrinking',
      'down_volume_expanding',
      'flat',
      'unknown'
    )),
  projection_quality_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (projection_quality_status IN ('passed', 'pending', 'warning', 'failed', 'blocked')),
  trace_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (trace_status IN ('passed', 'pending', 'warning', 'failed', 'blocked')),
  amount_basis_kind TEXT NOT NULL DEFAULT 'not_available'
    CHECK (amount_basis_kind IN (
      'previous_day_same_window',
      'previous_day_same_elapsed',
      'snapshot_delta_anchor',
      'minute_bar_elapsed',
      'adapter_projection',
      'not_available'
    )),
  source_fact_kind TEXT NOT NULL DEFAULT 'mixed'
    CHECK (source_fact_kind IN (
      'realtime_daily_snapshot',
      'minute_bar_1m_elapsed',
      'snapshot_delta_anchor',
      'previous_day_minute_bar_1m',
      'adapter_projection',
      'mixed'
    )),
  source_fact_ids JSONB NOT NULL DEFAULT '{}'::JSONB,
  minute_bar_ids_used BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  previous_day_minute_bar_ids_used BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  quality_item_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
  source_adapter TEXT NOT NULL,
  calculation_method TEXT NOT NULL,
  calculation_config_hash TEXT NOT NULL,
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (
    projection_run_id,
    trade_date,
    board_identity_key,
    projection_window_id,
    snapshot_time,
    source_adapter,
    projection_schema_version
  ),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (board_identity_key LIKE 'board:%'),
  CHECK (window_end > window_start),
  CHECK (snapshot_time >= window_start),
  CHECK (snapshot_time <= window_end)
);

CREATE INDEX IF NOT EXISTS idx_board_realtime_projection_metric_lookup
ON board_realtime_projection_metric(trade_date, board_identity_key, projection_window_id, snapshot_time DESC);

CREATE INDEX IF NOT EXISTS idx_board_realtime_projection_metric_run
ON board_realtime_projection_metric(projection_run_id, projection_quality_status, projection_status);

CREATE INDEX IF NOT EXISTS idx_board_realtime_projection_metric_snapshot
ON board_realtime_projection_metric(source_snapshot_run_id, snapshot_id);

CREATE INDEX IF NOT EXISTS idx_board_realtime_projection_metric_signal
ON board_realtime_projection_metric(for_trade_date, projection_signal_status, projection_quality_status);

COMMIT;
