-- N6 B-track product V3 additive schema draft.
-- DO NOT EXECUTE without a separate N6_user migration gate and rollback preflight.
-- N6-only: no N1-N5 table, event, outbox, checkpoint, or real-trade mutation.

BEGIN;

CREATE TABLE IF NOT EXISTS n6_virtual_trade_proposal (
  proposal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL CHECK (principal_type IN ('admin', 'human_user')),
  user_id BIGINT NOT NULL REFERENCES user_account(user_id),
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  source_type TEXT NOT NULL CHECK (source_type IN ('signal', 'manual_position', 'stop_loss')),
  source_id TEXT NOT NULL CHECK (source_id <> ''),
  source_signal_projection_id BIGINT REFERENCES user_signal_projection(user_signal_projection_id),
  source_virtual_position_id BIGINT REFERENCES n6_virtual_position(virtual_position_id),
  holding_episode_no INTEGER,
  asset_kind TEXT NOT NULL CHECK (asset_kind = 'stock'),
  identity_key TEXT NOT NULL CHECK (identity_key LIKE 'stock:%'),
  proposal_side TEXT NOT NULL CHECK (proposal_side IN ('buy', 'sell')),
  signal_reference_kind TEXT CHECK (signal_reference_kind IN ('trigger_price', 'action_price', 'manual', 'stop_loss')),
  signal_reference_price NUMERIC(24, 8) CHECK (signal_reference_price IS NULL OR signal_reference_price > 0),
  locked_target_price NUMERIC(24, 8) CHECK (locked_target_price IS NULL OR locked_target_price > 0),
  proposal_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (proposal_status IN ('pending', 'confirmed', 'processing', 'executed', 'expired', 'rejected', 'failed')),
  expires_at TIMESTAMPTZ NOT NULL,
  confirmed_at TIMESTAMPTZ,
  confirm_idempotency_key TEXT,
  executed_virtual_order_id BIGINT REFERENCES n6_virtual_order(virtual_order_id),
  executed_virtual_trade_id BIGINT REFERENCES n6_virtual_trade(virtual_trade_id),
  executor_run_id TEXT,
  failure_reason TEXT,
  policy_version TEXT NOT NULL DEFAULT 'n6_virtual_trade_proposal_v1',
  policy_hash TEXT NOT NULL,
  source_lineage_json JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (principal_id, principal_type) REFERENCES n6_principal(principal_id, principal_type),
  CHECK (jsonb_typeof(source_lineage_json) = 'object'),
  CHECK (holding_episode_no IS NULL OR holding_episode_no > 0),
  CHECK (expires_at > created_at),
  CHECK ((source_type = 'signal') = (source_signal_projection_id IS NOT NULL)),
  CHECK ((source_type IN ('manual_position', 'stop_loss')) = (source_virtual_position_id IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_041_n6_virtual_trade_proposal_signal_once
ON n6_virtual_trade_proposal(principal_id, principal_type, source_signal_projection_id)
WHERE source_signal_projection_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_041_n6_virtual_trade_proposal_open
ON n6_virtual_trade_proposal(principal_id, principal_type, source_type, source_id, proposal_side)
WHERE proposal_status IN ('pending', 'confirmed', 'processing');

CREATE UNIQUE INDEX IF NOT EXISTS idx_041_n6_virtual_trade_proposal_confirm_idempotency
ON n6_virtual_trade_proposal(principal_id, principal_type, confirm_idempotency_key)
WHERE confirm_idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_041_n6_virtual_trade_proposal_executor
ON n6_virtual_trade_proposal(proposal_status, expires_at, proposal_id);

CREATE INDEX IF NOT EXISTS idx_041_n6_virtual_trade_proposal_principal
ON n6_virtual_trade_proposal(principal_id, principal_type, created_at DESC);

CREATE TABLE IF NOT EXISTS n6_virtual_position_lot (
  virtual_position_lot_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  virtual_position_id BIGINT NOT NULL REFERENCES n6_virtual_position(virtual_position_id),
  virtual_account_id BIGINT NOT NULL REFERENCES n6_virtual_account(virtual_account_id),
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL CHECK (principal_type IN ('admin', 'human_user')),
  identity_key TEXT NOT NULL CHECK (identity_key LIKE 'stock:%'),
  holding_episode_no INTEGER NOT NULL CHECK (holding_episode_no > 0),
  source_virtual_trade_id BIGINT NOT NULL REFERENCES n6_virtual_trade(virtual_trade_id),
  open_trade_date DATE NOT NULL,
  available_trade_date DATE NOT NULL,
  original_quantity NUMERIC(24, 4) NOT NULL CHECK (original_quantity > 0),
  remaining_quantity NUMERIC(24, 4) NOT NULL CHECK (remaining_quantity >= 0),
  cost_price NUMERIC(24, 8) NOT NULL CHECK (cost_price > 0),
  lot_status TEXT NOT NULL DEFAULT 'locked_t1'
    CHECK (lot_status IN ('locked_t1', 'available', 'closed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (principal_id, principal_type) REFERENCES n6_principal(principal_id, principal_type),
  CHECK (remaining_quantity <= original_quantity),
  CHECK (available_trade_date > open_trade_date),
  UNIQUE (source_virtual_trade_id)
);

CREATE INDEX IF NOT EXISTS idx_041_n6_virtual_position_lot_available
ON n6_virtual_position_lot(virtual_position_id, available_trade_date, lot_status, virtual_position_lot_id);

ALTER TABLE n6_virtual_position
  ADD COLUMN IF NOT EXISTS holding_episode_no INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS first_open_trade_date DATE,
  ADD COLUMN IF NOT EXISTS locked_target_price NUMERIC(24, 8),
  ADD COLUMN IF NOT EXISTS target_price_status TEXT NOT NULL DEFAULT 'not_ready',
  ADD COLUMN IF NOT EXISTS target_price_source_signal_projection_id BIGINT REFERENCES user_signal_projection(user_signal_projection_id),
  ADD COLUMN IF NOT EXISTS stop_loss_price NUMERIC(24, 8),
  ADD COLUMN IF NOT EXISTS stop_loss_status TEXT NOT NULL DEFAULT 'not_ready',
  ADD COLUMN IF NOT EXISTS stop_loss_source_quote_snapshot_id BIGINT REFERENCES n6_virtual_quote_snapshot(virtual_quote_snapshot_id),
  ADD COLUMN IF NOT EXISTS stop_loss_frozen_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS stop_loss_effective_trade_date DATE,
  ADD COLUMN IF NOT EXISTS stop_loss_policy_version TEXT,
  ADD COLUMN IF NOT EXISTS stop_loss_policy_hash TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'n6_virtual_position_holding_episode_no_ck'
  ) THEN
    ALTER TABLE n6_virtual_position
      ADD CONSTRAINT n6_virtual_position_holding_episode_no_ck
      CHECK (holding_episode_no > 0);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'n6_virtual_position_target_price_status_ck'
  ) THEN
    ALTER TABLE n6_virtual_position
      ADD CONSTRAINT n6_virtual_position_target_price_status_ck
      CHECK (target_price_status IN ('not_ready', 'frozen'));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'n6_virtual_position_stop_loss_status_ck'
  ) THEN
    ALTER TABLE n6_virtual_position
      ADD CONSTRAINT n6_virtual_position_stop_loss_status_ck
      CHECK (stop_loss_status IN ('not_ready', 'provisional_first_day', 'frozen', 'disabled'));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'n6_virtual_position_locked_target_price_ck'
  ) THEN
    ALTER TABLE n6_virtual_position
      ADD CONSTRAINT n6_virtual_position_locked_target_price_ck
      CHECK (locked_target_price IS NULL OR locked_target_price > 0);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'n6_virtual_position_stop_loss_price_ck'
  ) THEN
    ALTER TABLE n6_virtual_position
      ADD CONSTRAINT n6_virtual_position_stop_loss_price_ck
      CHECK (stop_loss_price IS NULL OR stop_loss_price > 0);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'n6_virtual_position_target_price_frozen_ck'
  ) THEN
    ALTER TABLE n6_virtual_position
      ADD CONSTRAINT n6_virtual_position_target_price_frozen_ck
      CHECK (
        target_price_status <> 'frozen'
        OR (locked_target_price IS NOT NULL AND target_price_source_signal_projection_id IS NOT NULL)
      );
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'n6_virtual_position_stop_loss_frozen_ck'
  ) THEN
    ALTER TABLE n6_virtual_position
      ADD CONSTRAINT n6_virtual_position_stop_loss_frozen_ck
      CHECK (
        stop_loss_status <> 'frozen'
        OR (
          stop_loss_price IS NOT NULL
          AND stop_loss_source_quote_snapshot_id IS NOT NULL
          AND stop_loss_frozen_at IS NOT NULL
          AND stop_loss_effective_trade_date IS NOT NULL
          AND first_open_trade_date IS NOT NULL
          AND stop_loss_effective_trade_date > first_open_trade_date
        )
      );
  END IF;
END $$;

ALTER TABLE n6_virtual_order
  ADD COLUMN IF NOT EXISTS source_proposal_id BIGINT REFERENCES n6_virtual_trade_proposal(proposal_id),
  ADD COLUMN IF NOT EXISTS signal_reference_kind TEXT,
  ADD COLUMN IF NOT EXISTS signal_reference_price NUMERIC(24, 8),
  ADD COLUMN IF NOT EXISTS fill_quote_snapshot_id BIGINT REFERENCES n6_virtual_quote_snapshot(virtual_quote_snapshot_id);

ALTER TABLE n6_virtual_trade
  ADD COLUMN IF NOT EXISTS source_proposal_id BIGINT REFERENCES n6_virtual_trade_proposal(proposal_id),
  ADD COLUMN IF NOT EXISTS signal_reference_kind TEXT,
  ADD COLUMN IF NOT EXISTS signal_reference_price NUMERIC(24, 8),
  ADD COLUMN IF NOT EXISTS fill_quote_snapshot_id BIGINT REFERENCES n6_virtual_quote_snapshot(virtual_quote_snapshot_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_041_n6_virtual_order_source_proposal
ON n6_virtual_order(source_proposal_id)
WHERE source_proposal_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_041_n6_virtual_trade_source_proposal
ON n6_virtual_trade(source_proposal_id)
WHERE source_proposal_id IS NOT NULL;

-- Roles are created only by a separate runtime-control credential gate.
-- This block grants least privilege only when the named roles already exist.
-- Role privileges are intentionally deferred.  A separate gate must first
-- establish principal-scoped database policy and proposal-status migration.

COMMIT;
