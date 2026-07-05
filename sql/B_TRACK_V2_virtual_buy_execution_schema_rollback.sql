BEGIN;

DO $$
DECLARE
  order_business_row_count INTEGER := 0;
  position_event_business_row_count INTEGER := 0;
BEGIN
  IF to_regclass('public.n6_virtual_order') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'n6_virtual_order'
         AND column_name = 'idempotency_key'
     ) THEN
    EXECUTE $guard$
      SELECT COUNT(*)
      FROM n6_virtual_order
      WHERE idempotency_key IS NOT NULL
         OR source_message_key IS NOT NULL
         OR source_signal_identity_key IS NOT NULL
         OR source_condition_key IS NOT NULL
         OR source_event_time IS NOT NULL
         OR source_for_trade_date IS NOT NULL
         OR source_json <> '{}'::jsonb
    $guard$
    INTO order_business_row_count;

    IF order_business_row_count > 0 THEN
      RAISE EXCEPTION 'B-track virtual buy schema rollback blocked: n6_virtual_order has scoped source values';
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_position_event') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'n6_virtual_position_event'
         AND column_name = 'available_quantity_delta'
     ) THEN
    EXECUTE $guard$
      SELECT COUNT(*)
      FROM n6_virtual_position_event
      WHERE available_quantity_delta <> 0
         OR locked_quantity_delta <> 0
         OR price IS NOT NULL
         OR trade_date IS NOT NULL
         OR available_date IS NOT NULL
    $guard$
    INTO position_event_business_row_count;

    IF position_event_business_row_count > 0 THEN
      RAISE EXCEPTION 'B-track virtual buy schema rollback blocked: n6_virtual_position_event has scoped quantity or price values';
    END IF;
  END IF;
END $$;

DROP INDEX IF EXISTS ux_n6_virtual_order_principal_account_idempotency;

ALTER TABLE n6_virtual_position_event
  DROP COLUMN IF EXISTS available_date,
  DROP COLUMN IF EXISTS trade_date,
  DROP COLUMN IF EXISTS price,
  DROP COLUMN IF EXISTS locked_quantity_delta,
  DROP COLUMN IF EXISTS available_quantity_delta;

ALTER TABLE n6_virtual_order
  DROP COLUMN IF EXISTS source_json,
  DROP COLUMN IF EXISTS source_for_trade_date,
  DROP COLUMN IF EXISTS source_event_time,
  DROP COLUMN IF EXISTS source_condition_key,
  DROP COLUMN IF EXISTS source_signal_identity_key,
  DROP COLUMN IF EXISTS source_message_key,
  DROP COLUMN IF EXISTS idempotency_key;

COMMIT;
