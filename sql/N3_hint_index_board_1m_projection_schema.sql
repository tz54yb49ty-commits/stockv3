-- N3 index/board 1m HINT projection proof additive schema draft.
-- Scope: create index/board proof tables only; no business rows are inserted here.

CREATE TABLE IF NOT EXISTS index_realtime_hint_projection_metric (
  metric_id BIGSERIAL PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  trade_date TEXT NOT NULL CHECK (trade_date ~ '^[0-9]{8}$'),
  metric_minute_label TEXT NOT NULL CHECK (metric_minute_label ~ '^[0-9]{4}$'),
  asset_kind TEXT NOT NULL DEFAULT 'index' CHECK (asset_kind = 'index'),
  identity_key TEXT NOT NULL CHECK (identity_key LIKE 'index:%'),
  code TEXT NOT NULL,
  name TEXT,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  condition_key TEXT NOT NULL,
  original_condition_key TEXT NOT NULL,
  source_condition_pool_id BIGINT NOT NULL,
  source_minute_target_scope_id BIGINT NOT NULL,
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_artifact_path TEXT NOT NULL,
  source_artifact_sha256 TEXT NOT NULL,
  source_previous_day_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_context_run_id TEXT NOT NULL,
  proof_kind TEXT NOT NULL CHECK (proof_kind = 'index_board_1m_hint_projection_v1'),
  source_mode TEXT NOT NULL CHECK (source_mode = 'index_board_frequency8_1m'),
  metric_role TEXT NOT NULL CHECK (metric_role = 'hint_trigger_proof'),
  proof_owner TEXT NOT NULL CHECK (proof_owner = 'N3'),
  proof_consumer TEXT NOT NULL CHECK (proof_consumer = 'N4'),
  not_n5_final_proof BOOLEAN NOT NULL CHECK (not_n5_final_proof = true),
  current_window_start TEXT NOT NULL,
  current_window_end TEXT NOT NULL,
  previous_completed_window_start TEXT NOT NULL,
  previous_completed_window_end TEXT NOT NULL,
  current_window_elapsed_count INTEGER NOT NULL CHECK (current_window_elapsed_count > 0),
  full_window_count INTEGER NOT NULL CHECK (full_window_count > 0),
  current_30m_price NUMERIC,
  current_30m_elapsed_amount NUMERIC CHECK (current_30m_elapsed_amount IS NULL OR current_30m_elapsed_amount >= 0),
  previous_day_same_elapsed_30m_amount NUMERIC CHECK (previous_day_same_elapsed_30m_amount IS NULL OR previous_day_same_elapsed_30m_amount >= 0),
  previous_day_full_30m_amount NUMERIC CHECK (previous_day_full_30m_amount IS NULL OR previous_day_full_30m_amount >= 0),
  current_30m_virtual_amount NUMERIC CHECK (current_30m_virtual_amount IS NULL OR current_30m_virtual_amount >= 0),
  reference_30m_amount NUMERIC CHECK (reference_30m_amount IS NULL OR reference_30m_amount >= 0),
  reference_30m_entity_high NUMERIC,
  reference_30m_entity_low NUMERIC,
  projection_30m_type TEXT NOT NULL CHECK (projection_30m_type IN ('volume_up', 'shrink_down', 'none', 'unknown')),
  projection_30m_flag BOOLEAN NOT NULL,
  metric_ready BOOLEAN NOT NULL,
  blocked_reasons TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  raw_json JSONB,
  trace_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS board_realtime_hint_projection_metric (
  metric_id BIGSERIAL PRIMARY KEY,
  projection_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  trade_date TEXT NOT NULL CHECK (trade_date ~ '^[0-9]{8}$'),
  metric_minute_label TEXT NOT NULL CHECK (metric_minute_label ~ '^[0-9]{4}$'),
  asset_kind TEXT NOT NULL DEFAULT 'board' CHECK (asset_kind = 'board'),
  identity_key TEXT NOT NULL CHECK (identity_key LIKE 'board:%'),
  code TEXT NOT NULL,
  name TEXT,
  direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell')),
  condition_key TEXT NOT NULL,
  original_condition_key TEXT NOT NULL,
  source_condition_pool_id BIGINT NOT NULL,
  source_minute_target_scope_id BIGINT NOT NULL,
  source_subscription_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_artifact_path TEXT NOT NULL,
  source_artifact_sha256 TEXT NOT NULL,
  source_previous_day_minute_run_id TEXT NOT NULL REFERENCES common_market_data_run(run_id),
  source_context_run_id TEXT NOT NULL,
  proof_kind TEXT NOT NULL CHECK (proof_kind = 'index_board_1m_hint_projection_v1'),
  source_mode TEXT NOT NULL CHECK (source_mode = 'index_board_frequency8_1m'),
  metric_role TEXT NOT NULL CHECK (metric_role = 'hint_trigger_proof'),
  proof_owner TEXT NOT NULL CHECK (proof_owner = 'N3'),
  proof_consumer TEXT NOT NULL CHECK (proof_consumer = 'N4'),
  not_n5_final_proof BOOLEAN NOT NULL CHECK (not_n5_final_proof = true),
  current_window_start TEXT NOT NULL,
  current_window_end TEXT NOT NULL,
  previous_completed_window_start TEXT NOT NULL,
  previous_completed_window_end TEXT NOT NULL,
  current_window_elapsed_count INTEGER NOT NULL CHECK (current_window_elapsed_count > 0),
  full_window_count INTEGER NOT NULL CHECK (full_window_count > 0),
  current_30m_price NUMERIC,
  current_30m_elapsed_amount NUMERIC CHECK (current_30m_elapsed_amount IS NULL OR current_30m_elapsed_amount >= 0),
  previous_day_same_elapsed_30m_amount NUMERIC CHECK (previous_day_same_elapsed_30m_amount IS NULL OR previous_day_same_elapsed_30m_amount >= 0),
  previous_day_full_30m_amount NUMERIC CHECK (previous_day_full_30m_amount IS NULL OR previous_day_full_30m_amount >= 0),
  current_30m_virtual_amount NUMERIC CHECK (current_30m_virtual_amount IS NULL OR current_30m_virtual_amount >= 0),
  reference_30m_amount NUMERIC CHECK (reference_30m_amount IS NULL OR reference_30m_amount >= 0),
  reference_30m_entity_high NUMERIC,
  reference_30m_entity_low NUMERIC,
  projection_30m_type TEXT NOT NULL CHECK (projection_30m_type IN ('volume_up', 'shrink_down', 'none', 'unknown')),
  projection_30m_flag BOOLEAN NOT NULL,
  metric_ready BOOLEAN NOT NULL,
  blocked_reasons TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  raw_json JSONB,
  trace_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_index_realtime_hint_projection_metric_grain
  ON index_realtime_hint_projection_metric (
    projection_run_id,
    identity_key,
    trade_date,
    metric_minute_label,
    condition_key,
    original_condition_key,
    source_condition_pool_id,
    source_minute_target_scope_id
  );

CREATE UNIQUE INDEX IF NOT EXISTS idx_board_realtime_hint_projection_metric_grain
  ON board_realtime_hint_projection_metric (
    projection_run_id,
    identity_key,
    trade_date,
    metric_minute_label,
    condition_key,
    original_condition_key,
    source_condition_pool_id,
    source_minute_target_scope_id
  );

CREATE INDEX IF NOT EXISTS idx_index_realtime_hint_projection_metric_run
  ON index_realtime_hint_projection_metric (projection_run_id, projection_30m_type, metric_ready);

CREATE INDEX IF NOT EXISTS idx_board_realtime_hint_projection_metric_run
  ON board_realtime_hint_projection_metric (projection_run_id, projection_30m_type, metric_ready);

COMMENT ON TABLE index_realtime_hint_projection_metric IS
  'N3 index-only index_board_1m_hint_projection_v1 proof rows consumed by N4 HINT matcher.';
COMMENT ON TABLE board_realtime_hint_projection_metric IS
  'N3 board-only index_board_1m_hint_projection_v1 proof rows consumed by N4 HINT matcher.';
