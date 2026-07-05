-- N6 Phase 3 038C virtual order/trade schema migration draft.
-- Do not execute without explicit user confirmation.
-- Scope: create n6_virtual_order and n6_virtual_trade only.
-- Boundary: no business rows, no outbox change, no worker, no delivery,
-- no push/voice/mobile, no sim/position/real trade.

BEGIN;

CREATE TABLE IF NOT EXISTS n6_virtual_order (
  virtual_order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL CHECK (principal_type IN ('admin', 'human_user', 'ai_user')),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL CHECK (identity_key <> ''),
  signal_type TEXT NOT NULL CHECK (signal_type <> ''),
  order_side TEXT NOT NULL CHECK (order_side IN ('buy', 'sell')),
  order_type TEXT NOT NULL DEFAULT 'limit_virtual'
    CHECK (order_type IN ('market_virtual', 'limit_virtual')),
  order_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (order_status IN (
      'draft',
      'staged_virtual',
      'accepted_virtual',
      'partially_filled_virtual',
      'filled_virtual',
      'cancelled_virtual',
      'rejected_virtual',
      'expired_virtual'
    )),
  requested_quantity NUMERIC(24, 4) NOT NULL CHECK (requested_quantity > 0),
  requested_price NUMERIC(24, 6) CHECK (requested_price IS NULL OR requested_price >= 0),
  estimated_fee_amount NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (estimated_fee_amount >= 0),
  estimated_tax_amount NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (estimated_tax_amount >= 0),
  fee_policy_version TEXT NOT NULL CHECK (fee_policy_version <> ''),
  tax_policy_version TEXT NOT NULL CHECK (tax_policy_version <> ''),
  execution_policy_version TEXT NOT NULL CHECK (execution_policy_version <> ''),
  execution_policy_hash TEXT NOT NULL CHECK (execution_policy_hash <> ''),
  market_rule_set TEXT NOT NULL CHECK (market_rule_set <> ''),
  source_action_event_id TEXT,
  source_signal_projection_id BIGINT,
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'passed'
    CHECK (quality_status IN ('passed', 'warning', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (principal_id, principal_type) REFERENCES n6_principal(principal_id, principal_type),
  CHECK (jsonb_typeof(source_lineage_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_038c_n6_virtual_order_account_status
ON n6_virtual_order(virtual_account_id, order_status);

CREATE INDEX IF NOT EXISTS idx_038c_n6_virtual_order_principal
ON n6_virtual_order(principal_id, principal_type, order_status);

CREATE INDEX IF NOT EXISTS idx_038c_n6_virtual_order_asset
ON n6_virtual_order(asset_kind, identity_key, order_side);

CREATE INDEX IF NOT EXISTS idx_038c_n6_virtual_order_run
ON n6_virtual_order(run_id);

CREATE TABLE IF NOT EXISTS n6_virtual_trade (
  virtual_trade_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_order_id BIGINT NOT NULL REFERENCES n6_virtual_order(virtual_order_id),
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL CHECK (principal_type IN ('admin', 'human_user', 'ai_user')),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL CHECK (identity_key <> ''),
  trade_side TEXT NOT NULL CHECK (trade_side IN ('buy', 'sell')),
  filled_quantity NUMERIC(24, 4) NOT NULL CHECK (filled_quantity > 0),
  filled_price NUMERIC(24, 6) NOT NULL CHECK (filled_price >= 0),
  gross_amount NUMERIC(24, 4) NOT NULL CHECK (gross_amount >= 0),
  commission_amount NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (commission_amount >= 0),
  stamp_tax_amount NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (stamp_tax_amount >= 0),
  transfer_fee_amount NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (transfer_fee_amount >= 0),
  total_fee_amount NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (total_fee_amount >= 0),
  net_amount NUMERIC(24, 4) NOT NULL CHECK (net_amount >= 0),
  fill_policy_version TEXT NOT NULL CHECK (fill_policy_version <> ''),
  fill_policy_hash TEXT NOT NULL CHECK (fill_policy_hash <> ''),
  replay_deterministic_seed TEXT NOT NULL CHECK (replay_deterministic_seed <> ''),
  trade_status TEXT NOT NULL DEFAULT 'filled_virtual'
    CHECK (trade_status IN (
      'filled_virtual',
      'reversed_virtual',
      'cancelled_virtual',
      'failed_virtual'
    )),
  trade_time TIMESTAMPTZ NOT NULL,
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  quality_status TEXT NOT NULL DEFAULT 'passed'
    CHECK (quality_status IN ('passed', 'warning', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (principal_id, principal_type) REFERENCES n6_principal(principal_id, principal_type),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  CHECK (total_fee_amount = commission_amount + stamp_tax_amount + transfer_fee_amount),
  UNIQUE(virtual_order_id, replay_deterministic_seed)
);

CREATE INDEX IF NOT EXISTS idx_038c_n6_virtual_trade_order
ON n6_virtual_trade(virtual_order_id);

CREATE INDEX IF NOT EXISTS idx_038c_n6_virtual_trade_account_time
ON n6_virtual_trade(virtual_account_id, trade_time);

CREATE INDEX IF NOT EXISTS idx_038c_n6_virtual_trade_principal
ON n6_virtual_trade(principal_id, principal_type, trade_status);

CREATE INDEX IF NOT EXISTS idx_038c_n6_virtual_trade_asset
ON n6_virtual_trade(asset_kind, identity_key, trade_side);

CREATE INDEX IF NOT EXISTS idx_038c_n6_virtual_trade_run
ON n6_virtual_trade(run_id);

COMMIT;
