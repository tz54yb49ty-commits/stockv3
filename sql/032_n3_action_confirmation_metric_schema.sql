-- A-share monitor v3 N3 action-confirmation projection metric schema draft.
-- Stage: N3 action-confirmation projection facts schema readiness.
-- Boundary: additive schema draft only. Do not execute without a separate
-- migration final gate. No business rows, no outbox/inbox/checkpoint writes,
-- no N4/N5/N6 writes, no worker, and no real trading.

CREATE TABLE IF NOT EXISTS stock_action_confirmation_projection_metric (
  action_confirmation_metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  projection_schema_version TEXT NOT NULL DEFAULT 'n3.action_confirmation_metric.v1',
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_snapshot_id BIGINT NOT NULL REFERENCES stock_realtime_daily_snapshot(snapshot_id),
  source_snapshot_event_id TEXT,
  source_today_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_previous_day_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'stock' CHECK (asset_kind = 'stock'),
  identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  metric_time TIMESTAMPTZ NOT NULL,
  metric_minute_label TEXT NOT NULL,
  current_price NUMERIC,
  current_price_source TEXT NOT NULL DEFAULT 'unknown'
    CHECK (current_price_source IN ('realtime_daily_snapshot', 'minute_bar_1m', 'adapter_projection', 'unknown')),
  current_price_time TIMESTAMPTZ,
  previous_120m_body_high NUMERIC,
  previous_120m_body_low NUMERIC,
  previous_30m_body_high NUMERIC,
  previous_30m_body_low NUMERIC,
  previous_5m_body_high NUMERIC,
  previous_5m_body_low NUMERIC,
  previous_1m_body_high NUMERIC,
  previous_1m_body_low NUMERIC,
  current_1m_amount NUMERIC CHECK (current_1m_amount IS NULL OR current_1m_amount >= 0),
  previous_1m_amount NUMERIC CHECK (previous_1m_amount IS NULL OR previous_1m_amount >= 0),
  current_5m_virtual_amount NUMERIC CHECK (current_5m_virtual_amount IS NULL OR current_5m_virtual_amount >= 0),
  previous_5m_full_amount NUMERIC CHECK (previous_5m_full_amount IS NULL OR previous_5m_full_amount >= 0),
  current_30m_virtual_amount NUMERIC CHECK (current_30m_virtual_amount IS NULL OR current_30m_virtual_amount >= 0),
  previous_day_same_window_amount NUMERIC CHECK (previous_day_same_window_amount IS NULL OR previous_day_same_window_amount >= 0),
  previous_30m_full_amount NUMERIC CHECK (previous_30m_full_amount IS NULL OR previous_30m_full_amount >= 0),
  is_first_1m_of_day BOOLEAN NOT NULL DEFAULT false,
  is_first_5m_of_day BOOLEAN NOT NULL DEFAULT false,
  is_first_30m_of_day BOOLEAN NOT NULL DEFAULT false,
  is_first_120m_of_day BOOLEAN NOT NULL DEFAULT false,
  first_1m_amount_default_pass BOOLEAN NOT NULL DEFAULT false,
  first_5m_amount_default_pass BOOLEAN NOT NULL DEFAULT false,
  previous_1m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_1m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  previous_5m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_5m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  previous_30m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_30m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  previous_120m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_120m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  boundary_policy_version TEXT NOT NULL DEFAULT 'n3.action_confirmation_boundary.v1',
  buy_120m_price_pass BOOLEAN,
  buy_30m_price_pass BOOLEAN,
  buy_5m_price_pass BOOLEAN,
  buy_5m_amount_pass BOOLEAN,
  buy_1m_price_pass BOOLEAN,
  buy_1m_amount_pass BOOLEAN,
  sell_120m_price_pass BOOLEAN,
  sell_30m_price_pass BOOLEAN,
  sell_5m_price_pass BOOLEAN,
  sell_5m_amount_pass BOOLEAN,
  sell_1m_price_pass BOOLEAN,
  sell_1m_amount_pass BOOLEAN,
  metric_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  metric_ready BOOLEAN NOT NULL DEFAULT false,
  source_fact_ids JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_minute_refs JSONB NOT NULL DEFAULT '[]'::JSONB,
  previous_day_minute_refs JSONB NOT NULL DEFAULT '[]'::JSONB,
  calculation_config_hash TEXT NOT NULL,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'stock:%'),
  CHECK (metric_ready = false OR (
    metric_quality_status = 'passed'
    AND current_price IS NOT NULL
    AND current_price_time IS NOT NULL
    AND previous_120m_body_high IS NOT NULL
    AND previous_120m_body_low IS NOT NULL
    AND previous_30m_body_high IS NOT NULL
    AND previous_30m_body_low IS NOT NULL
    AND previous_5m_body_high IS NOT NULL
    AND previous_5m_body_low IS NOT NULL
    AND previous_1m_body_high IS NOT NULL
    AND previous_1m_body_low IS NOT NULL
    AND current_1m_amount IS NOT NULL
    AND current_5m_virtual_amount IS NOT NULL
    AND (is_first_1m_of_day OR previous_1m_amount IS NOT NULL)
    AND (is_first_5m_of_day OR previous_5m_full_amount IS NOT NULL)
    AND previous_1m_period_source <> 'not_available'
    AND previous_5m_period_source <> 'not_available'
    AND previous_30m_period_source <> 'not_available'
    AND previous_120m_period_source <> 'not_available'
    AND jsonb_typeof(source_fact_ids) = 'object'
    AND source_fact_ids <> '{}'::JSONB
    AND jsonb_typeof(source_minute_refs) = 'array'
    AND jsonb_array_length(source_minute_refs) > 0
    AND (
      previous_1m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
    AND (
      previous_5m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
    AND (
      previous_30m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
    AND (
      previous_120m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
  )),
  CHECK (first_1m_amount_default_pass = is_first_1m_of_day),
  CHECK (first_5m_amount_default_pass = is_first_5m_of_day)
);

CREATE INDEX IF NOT EXISTS idx_stock_action_confirmation_metric_run
ON stock_action_confirmation_projection_metric(projection_run_id, metric_quality_status, metric_ready);

CREATE INDEX IF NOT EXISTS idx_stock_action_confirmation_metric_trade_identity
ON stock_action_confirmation_projection_metric(trade_date, identity_key, metric_time DESC);

CREATE INDEX IF NOT EXISTS idx_stock_action_confirmation_metric_snapshot
ON stock_action_confirmation_projection_metric(source_snapshot_run_id, source_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_stock_action_confirmation_metric_boundary
ON stock_action_confirmation_projection_metric(trade_date, metric_minute_label, metric_ready);

CREATE TABLE IF NOT EXISTS index_action_confirmation_projection_metric (
  action_confirmation_metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  projection_schema_version TEXT NOT NULL DEFAULT 'n3.action_confirmation_metric.v1',
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_snapshot_id BIGINT NOT NULL REFERENCES index_realtime_daily_snapshot(snapshot_id),
  source_snapshot_event_id TEXT,
  source_today_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_previous_day_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'index' CHECK (asset_kind = 'index'),
  identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  metric_time TIMESTAMPTZ NOT NULL,
  metric_minute_label TEXT NOT NULL,
  current_price NUMERIC,
  current_price_source TEXT NOT NULL DEFAULT 'unknown'
    CHECK (current_price_source IN ('realtime_daily_snapshot', 'minute_bar_1m', 'adapter_projection', 'unknown')),
  current_price_time TIMESTAMPTZ,
  previous_120m_body_high NUMERIC,
  previous_120m_body_low NUMERIC,
  previous_30m_body_high NUMERIC,
  previous_30m_body_low NUMERIC,
  previous_5m_body_high NUMERIC,
  previous_5m_body_low NUMERIC,
  previous_1m_body_high NUMERIC,
  previous_1m_body_low NUMERIC,
  current_1m_amount NUMERIC CHECK (current_1m_amount IS NULL OR current_1m_amount >= 0),
  previous_1m_amount NUMERIC CHECK (previous_1m_amount IS NULL OR previous_1m_amount >= 0),
  current_5m_virtual_amount NUMERIC CHECK (current_5m_virtual_amount IS NULL OR current_5m_virtual_amount >= 0),
  previous_5m_full_amount NUMERIC CHECK (previous_5m_full_amount IS NULL OR previous_5m_full_amount >= 0),
  current_30m_virtual_amount NUMERIC CHECK (current_30m_virtual_amount IS NULL OR current_30m_virtual_amount >= 0),
  previous_day_same_window_amount NUMERIC CHECK (previous_day_same_window_amount IS NULL OR previous_day_same_window_amount >= 0),
  previous_30m_full_amount NUMERIC CHECK (previous_30m_full_amount IS NULL OR previous_30m_full_amount >= 0),
  is_first_1m_of_day BOOLEAN NOT NULL DEFAULT false,
  is_first_5m_of_day BOOLEAN NOT NULL DEFAULT false,
  is_first_30m_of_day BOOLEAN NOT NULL DEFAULT false,
  is_first_120m_of_day BOOLEAN NOT NULL DEFAULT false,
  first_1m_amount_default_pass BOOLEAN NOT NULL DEFAULT false,
  first_5m_amount_default_pass BOOLEAN NOT NULL DEFAULT false,
  previous_1m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_1m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  previous_5m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_5m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  previous_30m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_30m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  previous_120m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_120m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  boundary_policy_version TEXT NOT NULL DEFAULT 'n3.action_confirmation_boundary.v1',
  buy_120m_price_pass BOOLEAN,
  buy_30m_price_pass BOOLEAN,
  buy_5m_price_pass BOOLEAN,
  buy_5m_amount_pass BOOLEAN,
  buy_1m_price_pass BOOLEAN,
  buy_1m_amount_pass BOOLEAN,
  sell_120m_price_pass BOOLEAN,
  sell_30m_price_pass BOOLEAN,
  sell_5m_price_pass BOOLEAN,
  sell_5m_amount_pass BOOLEAN,
  sell_1m_price_pass BOOLEAN,
  sell_1m_amount_pass BOOLEAN,
  metric_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  metric_ready BOOLEAN NOT NULL DEFAULT false,
  source_fact_ids JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_minute_refs JSONB NOT NULL DEFAULT '[]'::JSONB,
  previous_day_minute_refs JSONB NOT NULL DEFAULT '[]'::JSONB,
  calculation_config_hash TEXT NOT NULL,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'index:%'),
  CHECK (metric_ready = false OR (
    metric_quality_status = 'passed'
    AND current_price IS NOT NULL
    AND current_price_time IS NOT NULL
    AND previous_120m_body_high IS NOT NULL
    AND previous_120m_body_low IS NOT NULL
    AND previous_30m_body_high IS NOT NULL
    AND previous_30m_body_low IS NOT NULL
    AND previous_5m_body_high IS NOT NULL
    AND previous_5m_body_low IS NOT NULL
    AND previous_1m_body_high IS NOT NULL
    AND previous_1m_body_low IS NOT NULL
    AND current_1m_amount IS NOT NULL
    AND current_5m_virtual_amount IS NOT NULL
    AND (is_first_1m_of_day OR previous_1m_amount IS NOT NULL)
    AND (is_first_5m_of_day OR previous_5m_full_amount IS NOT NULL)
    AND previous_1m_period_source <> 'not_available'
    AND previous_5m_period_source <> 'not_available'
    AND previous_30m_period_source <> 'not_available'
    AND previous_120m_period_source <> 'not_available'
    AND jsonb_typeof(source_fact_ids) = 'object'
    AND source_fact_ids <> '{}'::JSONB
    AND jsonb_typeof(source_minute_refs) = 'array'
    AND jsonb_array_length(source_minute_refs) > 0
    AND (
      previous_1m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
    AND (
      previous_5m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
    AND (
      previous_30m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
    AND (
      previous_120m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
  )),
  CHECK (first_1m_amount_default_pass = is_first_1m_of_day),
  CHECK (first_5m_amount_default_pass = is_first_5m_of_day)
);

CREATE INDEX IF NOT EXISTS idx_index_action_confirmation_metric_run
ON index_action_confirmation_projection_metric(projection_run_id, metric_quality_status, metric_ready);

CREATE INDEX IF NOT EXISTS idx_index_action_confirmation_metric_trade_identity
ON index_action_confirmation_projection_metric(trade_date, identity_key, metric_time DESC);

CREATE INDEX IF NOT EXISTS idx_index_action_confirmation_metric_snapshot
ON index_action_confirmation_projection_metric(source_snapshot_run_id, source_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_index_action_confirmation_metric_boundary
ON index_action_confirmation_projection_metric(trade_date, metric_minute_label, metric_ready);

CREATE TABLE IF NOT EXISTS board_action_confirmation_projection_metric (
  action_confirmation_metric_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  projection_schema_version TEXT NOT NULL DEFAULT 'n3.action_confirmation_metric.v1',
  source_condition_run_id TEXT NOT NULL REFERENCES common_condition_run(run_id),
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_snapshot_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_snapshot_id BIGINT NOT NULL REFERENCES board_realtime_daily_snapshot(snapshot_id),
  source_snapshot_event_id TEXT,
  source_today_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_previous_day_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  for_trade_date TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  asset_kind TEXT NOT NULL DEFAULT 'board' CHECK (asset_kind = 'board'),
  identity_key TEXT NOT NULL,
  exchange TEXT NOT NULL,
  code TEXT NOT NULL,
  display_code TEXT,
  name TEXT,
  metric_time TIMESTAMPTZ NOT NULL,
  metric_minute_label TEXT NOT NULL,
  current_price NUMERIC,
  current_price_source TEXT NOT NULL DEFAULT 'unknown'
    CHECK (current_price_source IN ('realtime_daily_snapshot', 'minute_bar_1m', 'adapter_projection', 'unknown')),
  current_price_time TIMESTAMPTZ,
  previous_120m_body_high NUMERIC,
  previous_120m_body_low NUMERIC,
  previous_30m_body_high NUMERIC,
  previous_30m_body_low NUMERIC,
  previous_5m_body_high NUMERIC,
  previous_5m_body_low NUMERIC,
  previous_1m_body_high NUMERIC,
  previous_1m_body_low NUMERIC,
  current_1m_amount NUMERIC CHECK (current_1m_amount IS NULL OR current_1m_amount >= 0),
  previous_1m_amount NUMERIC CHECK (previous_1m_amount IS NULL OR previous_1m_amount >= 0),
  current_5m_virtual_amount NUMERIC CHECK (current_5m_virtual_amount IS NULL OR current_5m_virtual_amount >= 0),
  previous_5m_full_amount NUMERIC CHECK (previous_5m_full_amount IS NULL OR previous_5m_full_amount >= 0),
  current_30m_virtual_amount NUMERIC CHECK (current_30m_virtual_amount IS NULL OR current_30m_virtual_amount >= 0),
  previous_day_same_window_amount NUMERIC CHECK (previous_day_same_window_amount IS NULL OR previous_day_same_window_amount >= 0),
  previous_30m_full_amount NUMERIC CHECK (previous_30m_full_amount IS NULL OR previous_30m_full_amount >= 0),
  is_first_1m_of_day BOOLEAN NOT NULL DEFAULT false,
  is_first_5m_of_day BOOLEAN NOT NULL DEFAULT false,
  is_first_30m_of_day BOOLEAN NOT NULL DEFAULT false,
  is_first_120m_of_day BOOLEAN NOT NULL DEFAULT false,
  first_1m_amount_default_pass BOOLEAN NOT NULL DEFAULT false,
  first_5m_amount_default_pass BOOLEAN NOT NULL DEFAULT false,
  previous_1m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_1m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  previous_5m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_5m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  previous_30m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_30m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  previous_120m_period_source TEXT NOT NULL DEFAULT 'not_available'
    CHECK (previous_120m_period_source IN ('same_trade_date_previous_period', 'previous_trade_date_last_period', 'not_available')),
  boundary_policy_version TEXT NOT NULL DEFAULT 'n3.action_confirmation_boundary.v1',
  buy_120m_price_pass BOOLEAN,
  buy_30m_price_pass BOOLEAN,
  buy_5m_price_pass BOOLEAN,
  buy_5m_amount_pass BOOLEAN,
  buy_1m_price_pass BOOLEAN,
  buy_1m_amount_pass BOOLEAN,
  sell_120m_price_pass BOOLEAN,
  sell_30m_price_pass BOOLEAN,
  sell_5m_price_pass BOOLEAN,
  sell_5m_amount_pass BOOLEAN,
  sell_1m_price_pass BOOLEAN,
  sell_1m_amount_pass BOOLEAN,
  metric_quality_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (metric_quality_status IN ('passed', 'warning', 'missing', 'failed', 'blocked')),
  metric_ready BOOLEAN NOT NULL DEFAULT false,
  source_fact_ids JSONB NOT NULL DEFAULT '{}'::JSONB,
  source_minute_refs JSONB NOT NULL DEFAULT '[]'::JSONB,
  previous_day_minute_refs JSONB NOT NULL DEFAULT '[]'::JSONB,
  calculation_config_hash TEXT NOT NULL,
  raw_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(projection_run_id, identity_key, trade_date, metric_minute_label, projection_schema_version),
  CHECK (for_trade_date ~ '^[0-9]{8}$'),
  CHECK (trade_date ~ '^[0-9]{8}$'),
  CHECK (identity_key LIKE 'board:%'),
  CHECK (metric_ready = false OR (
    metric_quality_status = 'passed'
    AND current_price IS NOT NULL
    AND current_price_time IS NOT NULL
    AND previous_120m_body_high IS NOT NULL
    AND previous_120m_body_low IS NOT NULL
    AND previous_30m_body_high IS NOT NULL
    AND previous_30m_body_low IS NOT NULL
    AND previous_5m_body_high IS NOT NULL
    AND previous_5m_body_low IS NOT NULL
    AND previous_1m_body_high IS NOT NULL
    AND previous_1m_body_low IS NOT NULL
    AND current_1m_amount IS NOT NULL
    AND current_5m_virtual_amount IS NOT NULL
    AND (is_first_1m_of_day OR previous_1m_amount IS NOT NULL)
    AND (is_first_5m_of_day OR previous_5m_full_amount IS NOT NULL)
    AND previous_1m_period_source <> 'not_available'
    AND previous_5m_period_source <> 'not_available'
    AND previous_30m_period_source <> 'not_available'
    AND previous_120m_period_source <> 'not_available'
    AND jsonb_typeof(source_fact_ids) = 'object'
    AND source_fact_ids <> '{}'::JSONB
    AND jsonb_typeof(source_minute_refs) = 'array'
    AND jsonb_array_length(source_minute_refs) > 0
    AND (
      previous_1m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
    AND (
      previous_5m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
    AND (
      previous_30m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
    AND (
      previous_120m_period_source <> 'previous_trade_date_last_period'
      OR (
        jsonb_typeof(previous_day_minute_refs) = 'array'
        AND jsonb_array_length(previous_day_minute_refs) > 0
      )
    )
  )),
  CHECK (first_1m_amount_default_pass = is_first_1m_of_day),
  CHECK (first_5m_amount_default_pass = is_first_5m_of_day)
);

CREATE INDEX IF NOT EXISTS idx_board_action_confirmation_metric_run
ON board_action_confirmation_projection_metric(projection_run_id, metric_quality_status, metric_ready);

CREATE INDEX IF NOT EXISTS idx_board_action_confirmation_metric_trade_identity
ON board_action_confirmation_projection_metric(trade_date, identity_key, metric_time DESC);

CREATE INDEX IF NOT EXISTS idx_board_action_confirmation_metric_snapshot
ON board_action_confirmation_projection_metric(source_snapshot_run_id, source_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_board_action_confirmation_metric_boundary
ON board_action_confirmation_projection_metric(trade_date, metric_minute_label, metric_ready);
