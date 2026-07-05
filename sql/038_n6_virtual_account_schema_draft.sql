-- N6 Phase 3 virtual account schema draft.
-- Do not execute without explicit user confirmation.
-- Scope: draft only. Creates N6 Track B virtual account tables if a future
-- migration gate approves this file or a split subset of it.
-- Boundary: no business rows, no N5 outbox change, no worker, no delivery,
-- no push/voice/mobile, no sim/position real trade.

BEGIN;

CREATE TABLE IF NOT EXISTS n6_virtual_account (
  virtual_account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  account_id BIGINT REFERENCES n6_principal_account(account_id),
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  principal_type TEXT NOT NULL CHECK (principal_type IN ('human_user', 'ai_user', 'admin')),
  account_mode TEXT NOT NULL CHECK (account_mode IN ('admin_shadow_virtual', 'human_virtual', 'ai_virtual')),
  virtual_account_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (virtual_account_status IN ('draft', 'active', 'paused', 'closed', 'deleted')),
  initial_cash NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (initial_cash >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY' CHECK (currency IN ('CNY')),
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (quality_status IN ('draft', 'passed', 'warning', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  CHECK (
    (principal_type = 'admin' AND account_mode = 'admin_shadow_virtual')
    OR (principal_type = 'human_user' AND account_mode = 'human_virtual')
    OR (principal_type = 'ai_user' AND account_mode = 'ai_virtual')
  ),
  UNIQUE(principal_id, account_mode, run_id)
);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_account_principal_status
ON n6_virtual_account(principal_id, virtual_account_status);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_account_run
ON n6_virtual_account(run_id);

CREATE TABLE IF NOT EXISTS n6_virtual_cash_ledger (
  virtual_cash_ledger_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  cash_ledger_type TEXT NOT NULL
    CHECK (cash_ledger_type IN (
      'initial_deposit',
      'buy_cash_out',
      'sell_cash_in',
      'fee',
      'tax',
      'pnl_adjustment',
      'manual_adjustment',
      'reversal',
      'rollback_adjustment'
    )),
  amount_delta NUMERIC(24, 4) NOT NULL,
  cash_balance_after NUMERIC(24, 4) NOT NULL CHECK (cash_balance_after >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY' CHECK (currency IN ('CNY')),
  trade_date INTEGER,
  event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
  source_virtual_order_id BIGINT,
  source_virtual_trade_id BIGINT,
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (quality_status IN ('draft', 'passed', 'warning', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_cash_ledger_account_time
ON n6_virtual_cash_ledger(virtual_account_id, event_time);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_cash_ledger_run
ON n6_virtual_cash_ledger(run_id);

CREATE TABLE IF NOT EXISTS n6_virtual_cash_snapshot (
  virtual_cash_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  snapshot_trade_date INTEGER NOT NULL,
  cash_balance NUMERIC(24, 4) NOT NULL CHECK (cash_balance >= 0),
  available_cash NUMERIC(24, 4) NOT NULL CHECK (available_cash >= 0),
  frozen_cash NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (frozen_cash >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY' CHECK (currency IN ('CNY')),
  cash_snapshot_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (cash_snapshot_status IN ('draft', 'active', 'superseded', 'deleted')),
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (quality_status IN ('draft', 'passed', 'warning', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  CHECK (available_cash + frozen_cash <= cash_balance),
  UNIQUE(virtual_account_id, snapshot_trade_date, run_id)
);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_cash_snapshot_account_date
ON n6_virtual_cash_snapshot(virtual_account_id, snapshot_trade_date);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_cash_snapshot_run
ON n6_virtual_cash_snapshot(run_id);

CREATE TABLE IF NOT EXISTS n6_virtual_position (
  virtual_position_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL CHECK (identity_key <> ''),
  code TEXT,
  name TEXT,
  quantity NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
  available_quantity NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (available_quantity >= 0),
  locked_quantity NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (locked_quantity >= 0),
  avg_cost NUMERIC(24, 6) NOT NULL DEFAULT 0 CHECK (avg_cost >= 0),
  mark_price NUMERIC(24, 6) CHECK (mark_price IS NULL OR mark_price >= 0),
  market_value NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (market_value >= 0),
  unrealized_pnl NUMERIC(24, 4) NOT NULL DEFAULT 0,
  t_plus_one_locked_until_trade_date INTEGER,
  position_status TEXT NOT NULL DEFAULT 'open'
    CHECK (position_status IN ('open', 'closed', 'locked', 'suspended', 'deleted')),
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_virtual_trade_id BIGINT,
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (quality_status IN ('draft', 'passed', 'warning', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  CHECK (available_quantity + locked_quantity <= quantity),
  UNIQUE(virtual_account_id, asset_kind, identity_key)
);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_position_account_asset
ON n6_virtual_position(virtual_account_id, asset_kind, identity_key);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_position_run
ON n6_virtual_position(run_id);

CREATE TABLE IF NOT EXISTS n6_virtual_position_event (
  virtual_position_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_position_id BIGINT REFERENCES n6_virtual_position(virtual_position_id),
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL CHECK (identity_key <> ''),
  position_event_type TEXT NOT NULL
    CHECK (position_event_type IN (
      'initial_open',
      'buy_increase',
      'sell_reduce',
      'mark_to_market',
      't_plus_one_unlock',
      'manual_adjustment',
      'reversal',
      'close',
      'rollback_adjustment'
    )),
  quantity_delta NUMERIC(24, 4) NOT NULL,
  quantity_after NUMERIC(24, 4) NOT NULL CHECK (quantity_after >= 0),
  available_quantity_after NUMERIC(24, 4) NOT NULL CHECK (available_quantity_after >= 0),
  locked_quantity_after NUMERIC(24, 4) NOT NULL CHECK (locked_quantity_after >= 0),
  avg_cost_after NUMERIC(24, 6) NOT NULL CHECK (avg_cost_after >= 0),
  source_virtual_trade_id BIGINT,
  event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (quality_status IN ('draft', 'passed', 'warning', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  CHECK (available_quantity_after + locked_quantity_after <= quantity_after)
);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_position_event_account_asset
ON n6_virtual_position_event(virtual_account_id, asset_kind, identity_key, event_time);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_position_event_run
ON n6_virtual_position_event(run_id);

CREATE TABLE IF NOT EXISTS n6_virtual_order (
  virtual_order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  source_signal_projection_id BIGINT REFERENCES user_signal_projection(user_signal_projection_id),
  source_signal_card_id BIGINT REFERENCES user_signal_card(user_signal_card_id),
  source_decision_id BIGINT REFERENCES user_signal_decision(user_signal_decision_id),
  source_ai_decision_id BIGINT,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL CHECK (identity_key <> ''),
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
  order_type TEXT NOT NULL DEFAULT 'limit_virtual'
    CHECK (order_type IN ('market_virtual', 'limit_virtual')),
  quantity NUMERIC(24, 4) NOT NULL CHECK (quantity > 0),
  limit_price NUMERIC(24, 6) CHECK (limit_price IS NULL OR limit_price >= 0),
  order_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (order_status IN (
      'draft',
      'submitted_virtual',
      'partially_filled_virtual',
      'filled_virtual',
      'cancelled_virtual',
      'rejected_virtual',
      'expired_virtual'
    )),
  submitted_at TIMESTAMPTZ,
  filled_quantity NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (filled_quantity >= 0),
  avg_fill_price NUMERIC(24, 6) CHECK (avg_fill_price IS NULL OR avg_fill_price >= 0),
  cancelled_at TIMESTAMPTZ,
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (quality_status IN ('draft', 'passed', 'warning', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  CHECK (filled_quantity <= quantity)
);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_order_account_status
ON n6_virtual_order(virtual_account_id, order_status);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_order_run
ON n6_virtual_order(run_id);

CREATE TABLE IF NOT EXISTS n6_virtual_trade (
  virtual_trade_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_order_id BIGINT NOT NULL REFERENCES n6_virtual_order(virtual_order_id),
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL CHECK (identity_key <> ''),
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
  trade_status TEXT NOT NULL DEFAULT 'filled_virtual'
    CHECK (trade_status IN ('filled_virtual', 'reversed_virtual', 'cancelled_virtual')),
  quantity NUMERIC(24, 4) NOT NULL CHECK (quantity > 0),
  price NUMERIC(24, 6) NOT NULL CHECK (price >= 0),
  gross_amount NUMERIC(24, 4) NOT NULL CHECK (gross_amount >= 0),
  fee_amount NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (fee_amount >= 0),
  tax_amount NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
  net_amount NUMERIC(24, 4) NOT NULL CHECK (net_amount >= 0),
  trade_date INTEGER NOT NULL,
  trade_time TIMESTAMPTZ NOT NULL,
  fill_policy_version TEXT NOT NULL CHECK (fill_policy_version <> ''),
  fill_policy_hash TEXT NOT NULL CHECK (fill_policy_hash <> ''),
  replay_deterministic_seed TEXT NOT NULL CHECK (replay_deterministic_seed <> ''),
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (quality_status IN ('draft', 'passed', 'warning', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  UNIQUE(virtual_order_id, replay_deterministic_seed)
);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_trade_account_date
ON n6_virtual_trade(virtual_account_id, trade_date);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_trade_run
ON n6_virtual_trade(run_id);

CREATE TABLE IF NOT EXISTS n6_virtual_pnl_snapshot (
  virtual_pnl_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL REFERENCES n6_principal(principal_id),
  trade_date INTEGER NOT NULL,
  cash_balance NUMERIC(24, 4) NOT NULL CHECK (cash_balance >= 0),
  market_value NUMERIC(24, 4) NOT NULL CHECK (market_value >= 0),
  total_equity NUMERIC(24, 4) NOT NULL CHECK (total_equity >= 0),
  realized_pnl NUMERIC(24, 4) NOT NULL DEFAULT 0,
  unrealized_pnl NUMERIC(24, 4) NOT NULL DEFAULT 0,
  daily_return_pct NUMERIC(18, 8),
  max_drawdown_pct NUMERIC(18, 8),
  benchmark_identity_key TEXT,
  source_price_policy TEXT NOT NULL
    CHECK (source_price_policy IN ('n6_display_snapshot', 'reviewed_artifact', 'virtual_mark_policy')),
  valuation_policy_version TEXT NOT NULL CHECK (valuation_policy_version <> ''),
  valuation_policy_hash TEXT NOT NULL CHECK (valuation_policy_hash <> ''),
  pnl_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (pnl_status IN ('draft', 'passed', 'warning', 'superseded', 'deleted')),
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (quality_status IN ('draft', 'passed', 'warning', 'blocked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  CHECK (total_equity = cash_balance + market_value),
  UNIQUE(virtual_account_id, trade_date, run_id)
);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_pnl_account_date
ON n6_virtual_pnl_snapshot(virtual_account_id, trade_date);

CREATE INDEX IF NOT EXISTS idx_n6_virtual_pnl_run
ON n6_virtual_pnl_snapshot(run_id);

COMMIT;
