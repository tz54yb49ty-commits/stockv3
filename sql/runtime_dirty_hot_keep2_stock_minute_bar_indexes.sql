-- Runtime dirty hot keep-2 cleanup stock minute-bar index draft.
-- Artifact only: do not execute outside an explicit schema migration gate.
-- Purpose: speed up trade_date + bar_time cleanup count/delete probes.

CREATE INDEX IF NOT EXISTS idx_stock_minute_bar_1m_trade_bar_time
  ON stock_minute_bar_1m (trade_date, bar_time);
