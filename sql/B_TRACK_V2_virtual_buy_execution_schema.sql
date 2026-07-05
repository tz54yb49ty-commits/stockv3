BEGIN;

ALTER TABLE n6_virtual_order
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS source_message_key TEXT,
  ADD COLUMN IF NOT EXISTS source_signal_identity_key TEXT,
  ADD COLUMN IF NOT EXISTS source_condition_key TEXT,
  ADD COLUMN IF NOT EXISTS source_event_time TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS source_for_trade_date TEXT,
  ADD COLUMN IF NOT EXISTS source_json JSONB NOT NULL DEFAULT '{}'::JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS ux_n6_virtual_order_principal_account_idempotency
ON n6_virtual_order(principal_id, principal_type, virtual_account_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

ALTER TABLE n6_virtual_position_event
  ADD COLUMN IF NOT EXISTS available_quantity_delta NUMERIC(24, 4) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS locked_quantity_delta NUMERIC(24, 4) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS price NUMERIC(24, 6),
  ADD COLUMN IF NOT EXISTS trade_date INTEGER,
  ADD COLUMN IF NOT EXISTS available_date INTEGER;

COMMIT;
