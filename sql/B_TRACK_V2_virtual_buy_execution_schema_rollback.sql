BEGIN;

DO $$
DECLARE
  v_has_business_value BOOLEAN := false;
BEGIN
  SELECT EXISTS (
    SELECT 1
    FROM n6_virtual_order
    WHERE idempotency_key IS NOT NULL
       OR source_message_key IS NOT NULL
       OR source_signal_identity_key IS NOT NULL
       OR source_condition_key IS NOT NULL
       OR source_event_time IS NOT NULL
       OR source_for_trade_date IS NOT NULL
       OR source_json <> '{}'::jsonb
  )
  INTO v_has_business_value;

  IF v_has_business_value THEN
    RAISE EXCEPTION 'B_TRACK_V2 rollback blocked: n6_virtual_order patch columns contain business values';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM n6_virtual_position_event
    WHERE available_quantity_delta <> 0
       OR locked_quantity_delta <> 0
       OR price IS NOT NULL
       OR trade_date IS NOT NULL
       OR available_date IS NOT NULL
  )
  INTO v_has_business_value;

  IF v_has_business_value THEN
    RAISE EXCEPTION 'B_TRACK_V2 rollback blocked: n6_virtual_position_event patch columns contain business values';
  END IF;
END
$$;

DROP INDEX IF EXISTS ux_n6_virtual_order_principal_account_idempotency;

ALTER TABLE n6_virtual_order
  DROP COLUMN IF EXISTS idempotency_key,
  DROP COLUMN IF EXISTS source_message_key,
  DROP COLUMN IF EXISTS source_signal_identity_key,
  DROP COLUMN IF EXISTS source_condition_key,
  DROP COLUMN IF EXISTS source_event_time,
  DROP COLUMN IF EXISTS source_for_trade_date,
  DROP COLUMN IF EXISTS source_json;

ALTER TABLE n6_virtual_position_event
  DROP COLUMN IF EXISTS available_quantity_delta,
  DROP COLUMN IF EXISTS locked_quantity_delta,
  DROP COLUMN IF EXISTS price,
  DROP COLUMN IF EXISTS trade_date,
  DROP COLUMN IF EXISTS available_date;

COMMIT;
