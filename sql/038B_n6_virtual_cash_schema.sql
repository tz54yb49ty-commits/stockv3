-- N6 Phase 3 038B virtual cash schema migration draft.
-- Do not execute without explicit user confirmation.
-- Scope: create n6_virtual_cash_ledger and n6_virtual_cash_snapshot only.
-- Boundary: no business rows, no outbox change, no worker, no delivery,
-- no push/voice/mobile, no sim/position/real trade.

BEGIN;

CREATE TABLE IF NOT EXISTS n6_virtual_cash_ledger (
  cash_ledger_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  ledger_type TEXT NOT NULL
    CHECK (ledger_type IN (
      'initial_deposit',
      'order_freeze',
      'order_unfreeze',
      'virtual_buy',
      'virtual_sell',
      'fee',
      'tax',
      'adjustment'
    )),
  amount NUMERIC(24, 4) NOT NULL,
  currency TEXT NOT NULL DEFAULT 'CNY' CHECK (currency = 'CNY'),
  trade_date INTEGER,
  event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
  source_event_type TEXT NOT NULL CHECK (source_event_type <> ''),
  source_event_id TEXT,
  source_virtual_order_id BIGINT,
  source_virtual_trade_id BIGINT,
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'passed'
    CHECK (quality_status IN ('passed', 'warning', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_038b_n6_virtual_cash_ledger_account_time
ON n6_virtual_cash_ledger(virtual_account_id, event_time);

CREATE INDEX IF NOT EXISTS idx_038b_n6_virtual_cash_ledger_run
ON n6_virtual_cash_ledger(run_id);

CREATE INDEX IF NOT EXISTS idx_038b_n6_virtual_cash_ledger_type
ON n6_virtual_cash_ledger(ledger_type);

CREATE TABLE IF NOT EXISTS n6_virtual_cash_snapshot (
  cash_snapshot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  snapshot_time TIMESTAMPTZ NOT NULL DEFAULT now(),
  trade_date INTEGER NOT NULL,
  available_cash NUMERIC(24, 4) NOT NULL CHECK (available_cash >= 0),
  frozen_cash NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (frozen_cash >= 0),
  total_cash NUMERIC(24, 4) NOT NULL CHECK (total_cash >= 0),
  currency TEXT NOT NULL DEFAULT 'CNY' CHECK (currency = 'CNY'),
  source_ledger_max_id BIGINT NOT NULL REFERENCES n6_virtual_cash_ledger(cash_ledger_id),
  snapshot_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (snapshot_status IN ('draft', 'active', 'superseded', 'failed')),
  run_id TEXT NOT NULL CHECK (run_id <> ''),
  policy_version TEXT NOT NULL CHECK (policy_version <> ''),
  policy_hash TEXT NOT NULL CHECK (policy_hash <> ''),
  rollback_scope TEXT NOT NULL CHECK (rollback_scope <> ''),
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  quality_status TEXT NOT NULL DEFAULT 'passed'
    CHECK (quality_status IN ('passed', 'warning', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  CHECK (total_cash = available_cash + frozen_cash)
);

CREATE INDEX IF NOT EXISTS idx_038b_n6_virtual_cash_snapshot_account_date
ON n6_virtual_cash_snapshot(virtual_account_id, trade_date, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_038b_n6_virtual_cash_snapshot_run
ON n6_virtual_cash_snapshot(run_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_038b_n6_virtual_cash_snapshot_one_active
ON n6_virtual_cash_snapshot(virtual_account_id, trade_date)
WHERE snapshot_status = 'active';

COMMIT;
