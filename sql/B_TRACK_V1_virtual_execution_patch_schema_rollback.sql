-- B_TRACK_V1 virtual execution patch schema rollback draft.
-- Fail closed when any V1 patch column contains business values.
-- Do not execute without an explicit rollback gate.

BEGIN;

DO $$
DECLARE
  v_check RECORD;
  v_count BIGINT := 0;
BEGIN
  FOR v_check IN
    SELECT *
    FROM (
      VALUES
        ('n6_virtual_order', 'idempotency_key', $$idempotency_key IS NOT NULL$$),
        ('n6_virtual_order', 'source_message_key', $$source_message_key IS NOT NULL$$),
        ('n6_virtual_order', 'source_signal_identity_key', $$source_signal_identity_key IS NOT NULL$$),
        ('n6_virtual_order', 'source_condition_key', $$source_condition_key IS NOT NULL$$),
        ('n6_virtual_order', 'source_event_time', $$source_event_time IS NOT NULL$$),
        ('n6_virtual_order', 'source_for_trade_date', $$source_for_trade_date IS NOT NULL$$),
        ('n6_virtual_order', 'source_trade_date', $$source_trade_date IS NOT NULL$$),
        ('n6_virtual_order', 'source_monitor_id', $$source_monitor_id IS NOT NULL$$),
        ('n6_virtual_order', 'source_strategy_id', $$source_strategy_id IS NOT NULL$$),
        ('n6_virtual_order', 'source_action_state', $$source_action_state IS NOT NULL$$),
        ('n6_virtual_order', 'source_blocked_reason', $$source_blocked_reason IS NOT NULL$$),
        ('n6_virtual_order', 'source_json', $$source_json <> '{}'::jsonb$$),
        ('n6_virtual_position_event', 'available_quantity_delta', $$available_quantity_delta <> 0$$),
        ('n6_virtual_position_event', 'locked_quantity_delta', $$locked_quantity_delta <> 0$$),
        ('n6_virtual_position_event', 'price', $$price IS NOT NULL$$),
        ('n6_virtual_position_event', 'trade_date', $$trade_date IS NOT NULL$$),
        ('n6_virtual_position_event', 'available_date', $$available_date IS NOT NULL$$),
        ('n6_virtual_position_event', 'source_order_side', $$source_order_side IS NOT NULL$$),
        ('n6_virtual_position_event', 'source_for_trade_date', $$source_for_trade_date IS NOT NULL$$),
        ('n6_virtual_position_event', 'source_trade_date', $$source_trade_date IS NOT NULL$$),
        ('n6_virtual_position_event', 'source_json', $$source_json <> '{}'::jsonb$$)
    ) AS checks(table_name, column_name, predicate_sql)
  LOOP
    IF to_regclass('public.' || v_check.table_name) IS NOT NULL
       AND EXISTS (
         SELECT 1
         FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = v_check.table_name
           AND column_name = v_check.column_name
       ) THEN
      EXECUTE format(
        'SELECT count(*) FROM public.%I WHERE %s',
        v_check.table_name,
        v_check.predicate_sql
      )
      INTO v_count;

      IF v_count > 0 THEN
        RAISE EXCEPTION
          'B_TRACK_V1 rollback blocked: %.% has % business value rows',
          v_check.table_name,
          v_check.column_name,
          v_count;
      END IF;
    END IF;
  END LOOP;
END
$$;

DROP INDEX IF EXISTS public.ux_b_track_v1_n6_virtual_order_principal_account_idempotency;

ALTER TABLE IF EXISTS public.n6_virtual_order
  DROP CONSTRAINT IF EXISTS ck_b_track_v1_n6_virtual_order_source_json_object,
  DROP CONSTRAINT IF EXISTS ck_b_track_v1_n6_virtual_order_source_action_state;

ALTER TABLE IF EXISTS public.n6_virtual_position_event
  DROP CONSTRAINT IF EXISTS ck_b_track_v1_n6_virtual_position_event_source_json_object,
  DROP CONSTRAINT IF EXISTS ck_b_track_v1_n6_virtual_position_event_source_order_side;

ALTER TABLE IF EXISTS public.n6_virtual_order
  DROP COLUMN IF EXISTS idempotency_key,
  DROP COLUMN IF EXISTS source_message_key,
  DROP COLUMN IF EXISTS source_signal_identity_key,
  DROP COLUMN IF EXISTS source_condition_key,
  DROP COLUMN IF EXISTS source_event_time,
  DROP COLUMN IF EXISTS source_for_trade_date,
  DROP COLUMN IF EXISTS source_trade_date,
  DROP COLUMN IF EXISTS source_monitor_id,
  DROP COLUMN IF EXISTS source_strategy_id,
  DROP COLUMN IF EXISTS source_action_state,
  DROP COLUMN IF EXISTS source_blocked_reason,
  DROP COLUMN IF EXISTS source_json;

ALTER TABLE IF EXISTS public.n6_virtual_position_event
  DROP COLUMN IF EXISTS available_quantity_delta,
  DROP COLUMN IF EXISTS locked_quantity_delta,
  DROP COLUMN IF EXISTS price,
  DROP COLUMN IF EXISTS trade_date,
  DROP COLUMN IF EXISTS available_date,
  DROP COLUMN IF EXISTS source_order_side,
  DROP COLUMN IF EXISTS source_for_trade_date,
  DROP COLUMN IF EXISTS source_trade_date,
  DROP COLUMN IF EXISTS source_json;

COMMIT;
