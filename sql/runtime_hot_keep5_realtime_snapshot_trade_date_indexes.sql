CREATE INDEX IF NOT EXISTS idx_stock_realtime_daily_snapshot_trade_date
ON stock_realtime_daily_snapshot (trade_date);

CREATE INDEX IF NOT EXISTS idx_index_realtime_daily_snapshot_trade_date
ON index_realtime_daily_snapshot (trade_date);

CREATE INDEX IF NOT EXISTS idx_board_realtime_daily_snapshot_trade_date
ON board_realtime_daily_snapshot (trade_date);
