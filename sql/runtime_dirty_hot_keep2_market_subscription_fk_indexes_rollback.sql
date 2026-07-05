-- Rollback for runtime dirty hot keep-2 cleanup market-subscription FK child index draft.
-- Artifact only: do not execute outside an explicit rollback gate.

DROP INDEX IF EXISTS idx_common_trigger_match_market_subscription;
DROP INDEX IF EXISTS idx_board_trigger_context_subscription;
DROP INDEX IF EXISTS idx_index_trigger_context_subscription;
DROP INDEX IF EXISTS idx_stock_trigger_context_subscription;
DROP INDEX IF EXISTS idx_board_realtime_projection_metric_subscription;
DROP INDEX IF EXISTS idx_index_realtime_projection_metric_subscription;
DROP INDEX IF EXISTS idx_stock_realtime_projection_metric_subscription;
DROP INDEX IF EXISTS idx_board_prev_day_preload_status_subscription;
DROP INDEX IF EXISTS idx_index_prev_day_preload_status_subscription;
DROP INDEX IF EXISTS idx_stock_prev_day_preload_status_subscription;
DROP INDEX IF EXISTS idx_board_minute_bar_1m_subscription;
DROP INDEX IF EXISTS idx_index_minute_bar_1m_subscription;
DROP INDEX IF EXISTS idx_stock_minute_bar_1m_subscription;
DROP INDEX IF EXISTS idx_board_realtime_daily_snapshot_subscription;
DROP INDEX IF EXISTS idx_index_realtime_daily_snapshot_subscription;
DROP INDEX IF EXISTS idx_stock_realtime_daily_snapshot_subscription;
