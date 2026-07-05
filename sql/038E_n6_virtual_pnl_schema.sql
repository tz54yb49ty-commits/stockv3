-- N6 Phase 3 038E virtual PnL snapshot schema migration draft.
-- Do not execute without explicit user confirmation.
-- Scope: create n6_virtual_pnl_snapshot only.
-- Boundary: no business rows, no outbox change, no worker, no delivery,
-- no push/voice/mobile, no sim/position execution, no real trade.

BEGIN;

CREATE TABLE IF NOT EXISTS n6_virtual_pnl_snapshot (
  pnl_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL CHECK (principal_type IN ('admin', 'human_user', 'ai_user')),
  snapshot_time TIMESTAMPTZ NOT NULL,
  trade_date DATE NOT NULL,
  gross_pnl NUMERIC(24, 4) NOT NULL DEFAULT 0,
  realized_pnl NUMERIC(24, 4) NOT NULL DEFAULT 0,
  unrealized_pnl NUMERIC(24, 4) NOT NULL DEFAULT 0,
  total_fee NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (total_fee >= 0),
  total_tax NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (total_tax >= 0),
  net_pnl NUMERIC(24, 4) NOT NULL DEFAULT 0,
  total_asset_value NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (total_asset_value >= 0),
  cash_value NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (cash_value >= 0),
  position_market_value NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (position_market_value >= 0),
  source_price_policy TEXT NOT NULL
    CHECK (source_price_policy IN (
      'n6_display_snapshot',
      'reviewed_artifact',
      'virtual_mark_policy'
    )),
  valuation_policy_version TEXT NOT NULL CHECK (valuation_policy_version <> ''),
  valuation_policy_hash TEXT NOT NULL CHECK (valuation_policy_hash <> ''),
  source_cash_snapshot_id BIGINT REFERENCES n6_virtual_cash_snapshot(cash_snapshot_id),
  source_position_max_updated_at TIMESTAMPTZ,
  pnl_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (pnl_status IN (
      'draft',
      'passed',
      'warning',
      'superseded',
      'failed'
    )),
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'passed'
    CHECK (quality_status IN ('passed', 'warning', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (principal_id, principal_type) REFERENCES n6_principal(principal_id, principal_type),
  CHECK (net_pnl = gross_pnl - total_fee - total_tax),
  CHECK (total_asset_value = cash_value + position_market_value),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  UNIQUE (virtual_account_id, snapshot_time, run_id)
);

CREATE INDEX IF NOT EXISTS idx_038e_n6_virtual_pnl_account_date
ON n6_virtual_pnl_snapshot(virtual_account_id, trade_date, pnl_status);

CREATE INDEX IF NOT EXISTS idx_038e_n6_virtual_pnl_principal
ON n6_virtual_pnl_snapshot(principal_id, principal_type, pnl_status);

CREATE INDEX IF NOT EXISTS idx_038e_n6_virtual_pnl_source_cash
ON n6_virtual_pnl_snapshot(source_cash_snapshot_id);

CREATE INDEX IF NOT EXISTS idx_038e_n6_virtual_pnl_run
ON n6_virtual_pnl_snapshot(run_id);

COMMIT;
