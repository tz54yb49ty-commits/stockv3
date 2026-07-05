-- Rollback for runtime dirty hot keep-2 cleanup stock minute-bar index draft.
-- Artifact only: do not execute outside an explicit rollback gate.

DROP INDEX IF EXISTS idx_stock_minute_bar_1m_trade_bar_time;
