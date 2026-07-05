-- N6 Phase 3 038D virtual position schema migration draft.
-- Do not execute without explicit user confirmation.
-- Scope: create n6_virtual_position and n6_virtual_position_event only.
-- Boundary: no business rows, no outbox change, no worker, no delivery,
-- no push/voice/mobile, no sim/real position/real trade.

BEGIN;

CREATE TABLE IF NOT EXISTS n6_virtual_position (
  virtual_position_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL CHECK (principal_type IN ('admin', 'human_user', 'ai_user')),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL CHECK (identity_key <> ''),
  position_status TEXT NOT NULL DEFAULT 'open_virtual'
    CHECK (position_status IN (
      'open_virtual',
      'closed_virtual',
      'suspended_virtual',
      'superseded_virtual',
      'failed_virtual'
    )),
  quantity NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (quantity >= 0),
  available_quantity NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (available_quantity >= 0),
  locked_quantity NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (locked_quantity >= 0),
  average_cost NUMERIC(24, 6) NOT NULL DEFAULT 0 CHECK (average_cost >= 0),
  market_value NUMERIC(24, 4) CHECK (market_value IS NULL OR market_value >= 0),
  unrealized_pnl NUMERIC(24, 4),
  last_virtual_trade_id BIGINT REFERENCES n6_virtual_trade(virtual_trade_id),
  source_position_event_id BIGINT,
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
  CHECK (quantity = available_quantity + locked_quantity),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  UNIQUE (virtual_account_id, asset_kind, identity_key)
);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_account_status
ON n6_virtual_position(virtual_account_id, position_status);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_principal
ON n6_virtual_position(principal_id, principal_type, position_status);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_asset
ON n6_virtual_position(asset_kind, identity_key);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_last_trade
ON n6_virtual_position(last_virtual_trade_id);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_run
ON n6_virtual_position(run_id);

CREATE TABLE IF NOT EXISTS n6_virtual_position_event (
  position_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_position_id BIGINT REFERENCES n6_virtual_position(virtual_position_id),
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL CHECK (principal_type IN ('admin', 'human_user', 'ai_user')),
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL CHECK (identity_key <> ''),
  event_type TEXT NOT NULL
    CHECK (event_type IN (
      'virtual_buy_fill',
      'virtual_sell_fill',
      'adjustment',
      'split_adjustment',
      'close_position',
      'rollback_adjustment'
    )),
  quantity_delta NUMERIC(24, 4) NOT NULL,
  cost_delta NUMERIC(24, 4) NOT NULL DEFAULT 0,
  source_virtual_order_id BIGINT REFERENCES n6_virtual_order(virtual_order_id),
  source_virtual_trade_id BIGINT REFERENCES n6_virtual_trade(virtual_trade_id),
  event_time TIMESTAMPTZ NOT NULL,
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'passed'
    CHECK (quality_status IN ('passed', 'warning', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (principal_id, principal_type) REFERENCES n6_principal(principal_id, principal_type),
  CHECK (jsonb_typeof(source_lineage_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_event_position
ON n6_virtual_position_event(virtual_position_id, event_time);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_event_account_time
ON n6_virtual_position_event(virtual_account_id, event_time);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_event_principal
ON n6_virtual_position_event(principal_id, principal_type, event_type);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_event_source_order
ON n6_virtual_position_event(source_virtual_order_id);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_event_source_trade
ON n6_virtual_position_event(source_virtual_trade_id);

CREATE INDEX IF NOT EXISTS idx_038d_n6_virtual_position_event_run
ON n6_virtual_position_event(run_id);

COMMIT;
