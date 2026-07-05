-- N6 Phase 3 038A virtual account schema migration draft.
-- Do not execute without explicit user confirmation.
-- Scope: create n6_virtual_account only.
-- Boundary: no business rows, no N5 outbox change, no worker, no delivery,
-- no push/voice/mobile, no sim/position/real trade.

BEGIN;

CREATE TABLE IF NOT EXISTS n6_virtual_account (
  virtual_account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL CHECK (principal_type IN ('admin', 'human_user', 'ai_user')),
  account_name TEXT NOT NULL CHECK (account_name <> ''),
  virtual_account_status TEXT NOT NULL DEFAULT 'draft'
    CHECK (virtual_account_status IN ('draft', 'active', 'suspended', 'closed')),
  base_currency TEXT NOT NULL DEFAULT 'CNY' CHECK (base_currency = 'CNY'),
  initial_cash NUMERIC(24, 4) NOT NULL DEFAULT 0 CHECK (initial_cash >= 0),
  current_cash_snapshot_id BIGINT,
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
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  UNIQUE(principal_id, account_name, run_id)
);

CREATE INDEX IF NOT EXISTS idx_038a_n6_virtual_account_principal_status
ON n6_virtual_account(principal_id, principal_type, virtual_account_status);

CREATE INDEX IF NOT EXISTS idx_038a_n6_virtual_account_run
ON n6_virtual_account(run_id);

COMMIT;
