-- Runtime dirty hot keep-2 cleanup market-subscription FK child index draft.
-- Artifact only: do not execute outside an explicit schema migration gate.
-- Purpose: speed up common_market_data_subscription FK child lookups during old hot runtime cleanup.

CREATE INDEX IF NOT EXISTS idx_stock_realtime_daily_snapshot_subscription
  ON stock_realtime_daily_snapshot (subscription_id);

CREATE INDEX IF NOT EXISTS idx_index_realtime_daily_snapshot_subscription
  ON index_realtime_daily_snapshot (subscription_id);

CREATE INDEX IF NOT EXISTS idx_board_realtime_daily_snapshot_subscription
  ON board_realtime_daily_snapshot (subscription_id);

CREATE INDEX IF NOT EXISTS idx_stock_minute_bar_1m_subscription
  ON stock_minute_bar_1m (subscription_id);

CREATE INDEX IF NOT EXISTS idx_index_minute_bar_1m_subscription
  ON index_minute_bar_1m (subscription_id);

CREATE INDEX IF NOT EXISTS idx_board_minute_bar_1m_subscription
  ON board_minute_bar_1m (subscription_id);

CREATE INDEX IF NOT EXISTS idx_stock_prev_day_preload_status_subscription
  ON stock_previous_day_minute_preload_status (subscription_id);

CREATE INDEX IF NOT EXISTS idx_index_prev_day_preload_status_subscription
  ON index_previous_day_minute_preload_status (subscription_id);

CREATE INDEX IF NOT EXISTS idx_board_prev_day_preload_status_subscription
  ON board_previous_day_minute_preload_status (subscription_id);

CREATE INDEX IF NOT EXISTS idx_stock_realtime_projection_metric_subscription
  ON stock_realtime_projection_metric (subscription_id);

CREATE INDEX IF NOT EXISTS idx_index_realtime_projection_metric_subscription
  ON index_realtime_projection_metric (subscription_id);

CREATE INDEX IF NOT EXISTS idx_board_realtime_projection_metric_subscription
  ON board_realtime_projection_metric (subscription_id);

CREATE INDEX IF NOT EXISTS idx_stock_trigger_context_subscription
  ON stock_trigger_context_snapshot (source_market_subscription_id);

CREATE INDEX IF NOT EXISTS idx_index_trigger_context_subscription
  ON index_trigger_context_snapshot (source_market_subscription_id);

CREATE INDEX IF NOT EXISTS idx_board_trigger_context_subscription
  ON board_trigger_context_snapshot (source_market_subscription_id);

CREATE INDEX IF NOT EXISTS idx_common_trigger_match_market_subscription
  ON common_trigger_match (source_market_subscription_id);
