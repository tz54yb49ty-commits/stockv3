-- B_TRACK_V1 virtual execution patch schema migration draft.
-- Do not execute without an explicit database migration gate.
-- Scope: additive patch for n6_virtual_order and n6_virtual_position_event only.

BEGIN;

-- catalog type preflight: existing V1 columns must match the draft type.
DO $$
DECLARE
  v_mismatch RECORD;
BEGIN
  SELECT
    e.table_name,
    e.column_name,
    e.expected_udt_name,
    c.udt_name AS actual_udt_name
  INTO v_mismatch
  FROM (
    VALUES
      ('n6_virtual_order', 'idempotency_key', 'text'),
      ('n6_virtual_order', 'source_message_key', 'text'),
      ('n6_virtual_order', 'source_signal_identity_key', 'text'),
      ('n6_virtual_order', 'source_condition_key', 'text'),
      ('n6_virtual_order', 'source_event_time', 'timestamptz'),
      ('n6_virtual_order', 'source_for_trade_date', 'date'),
      ('n6_virtual_order', 'source_trade_date', 'date'),
      ('n6_virtual_order', 'source_monitor_id', 'int8'),
      ('n6_virtual_order', 'source_strategy_id', 'int8'),
      ('n6_virtual_order', 'source_action_state', 'text'),
      ('n6_virtual_order', 'source_blocked_reason', 'text'),
      ('n6_virtual_order', 'source_json', 'jsonb'),
      ('n6_virtual_position_event', 'available_quantity_delta', 'numeric'),
      ('n6_virtual_position_event', 'locked_quantity_delta', 'numeric'),
      ('n6_virtual_position_event', 'price', 'numeric'),
      ('n6_virtual_position_event', 'trade_date', 'date'),
      ('n6_virtual_position_event', 'available_date', 'date'),
      ('n6_virtual_position_event', 'source_order_side', 'text'),
      ('n6_virtual_position_event', 'source_for_trade_date', 'date'),
      ('n6_virtual_position_event', 'source_trade_date', 'date'),
      ('n6_virtual_position_event', 'source_json', 'jsonb')
  ) AS e(table_name, column_name, expected_udt_name)
  JOIN information_schema.columns c
    ON c.table_schema = 'public'
   AND c.table_name = e.table_name
   AND c.column_name = e.column_name
  WHERE c.udt_name <> e.expected_udt_name
  LIMIT 1;

  IF FOUND THEN
    RAISE EXCEPTION
      'B_TRACK_V1 catalog type preflight failed: %.% expected %, found %',
      v_mismatch.table_name,
      v_mismatch.column_name,
      v_mismatch.expected_udt_name,
      v_mismatch.actual_udt_name;
  END IF;
END
$$;

-- duplicate preflight: existing non-null idempotency_key groups must be unique.
DO $$
DECLARE
  v_duplicate_groups BIGINT := 0;
BEGIN
  IF to_regclass('public.n6_virtual_order') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM information_schema.columns
       WHERE table_schema = 'public'
         AND table_name = 'n6_virtual_order'
         AND column_name = 'idempotency_key'
     ) THEN
    EXECUTE $dup$
      SELECT count(*)
      FROM (
        SELECT principal_id, virtual_account_id, idempotency_key
        FROM public.n6_virtual_order
        WHERE idempotency_key IS NOT NULL
        GROUP BY principal_id, virtual_account_id, idempotency_key
        HAVING count(*) > 1
      ) AS duplicate_groups
    $dup$
    INTO v_duplicate_groups;

    IF v_duplicate_groups > 0 THEN
      RAISE EXCEPTION
        'B_TRACK_V1 duplicate preflight failed: n6_virtual_order has % duplicate idempotency groups',
        v_duplicate_groups;
    END IF;
  END IF;
END
$$;

ALTER TABLE public.n6_virtual_order
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS source_message_key TEXT,
  ADD COLUMN IF NOT EXISTS source_signal_identity_key TEXT,
  ADD COLUMN IF NOT EXISTS source_condition_key TEXT,
  ADD COLUMN IF NOT EXISTS source_event_time TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS source_for_trade_date DATE,
  ADD COLUMN IF NOT EXISTS source_trade_date DATE,
  ADD COLUMN IF NOT EXISTS source_monitor_id BIGINT,
  ADD COLUMN IF NOT EXISTS source_strategy_id BIGINT,
  ADD COLUMN IF NOT EXISTS source_action_state TEXT,
  ADD COLUMN IF NOT EXISTS source_blocked_reason TEXT,
  ADD COLUMN IF NOT EXISTS source_json JSONB DEFAULT '{}'::jsonb NOT NULL;

ALTER TABLE public.n6_virtual_position_event
  ADD COLUMN IF NOT EXISTS available_quantity_delta NUMERIC(24,4) DEFAULT 0 NOT NULL,
  ADD COLUMN IF NOT EXISTS locked_quantity_delta NUMERIC(24,4) DEFAULT 0 NOT NULL,
  ADD COLUMN IF NOT EXISTS price NUMERIC(24,6),
  ADD COLUMN IF NOT EXISTS trade_date DATE,
  ADD COLUMN IF NOT EXISTS available_date DATE,
  ADD COLUMN IF NOT EXISTS source_order_side TEXT,
  ADD COLUMN IF NOT EXISTS source_for_trade_date DATE,
  ADD COLUMN IF NOT EXISTS source_trade_date DATE,
  ADD COLUMN IF NOT EXISTS source_json JSONB DEFAULT '{}'::jsonb NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_b_track_v1_n6_virtual_order_principal_account_idempotency
ON public.n6_virtual_order (principal_id, virtual_account_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ck_b_track_v1_n6_virtual_order_source_json_object'
      AND conrelid = to_regclass('public.n6_virtual_order')
  ) THEN
    ALTER TABLE public.n6_virtual_order
      ADD CONSTRAINT ck_b_track_v1_n6_virtual_order_source_json_object
      CHECK (jsonb_typeof(source_json) = 'object');
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ck_b_track_v1_n6_virtual_order_source_action_state'
      AND conrelid = to_regclass('public.n6_virtual_order')
  ) THEN
    ALTER TABLE public.n6_virtual_order
      ADD CONSTRAINT ck_b_track_v1_n6_virtual_order_source_action_state
      CHECK (
        source_action_state IS NULL
        OR source_action_state IN ('eligible','executed','blocked','skipped','expired')
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ck_b_track_v1_n6_virtual_position_event_source_json_object'
      AND conrelid = to_regclass('public.n6_virtual_position_event')
  ) THEN
    ALTER TABLE public.n6_virtual_position_event
      ADD CONSTRAINT ck_b_track_v1_n6_virtual_position_event_source_json_object
      CHECK (jsonb_typeof(source_json) = 'object');
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ck_b_track_v1_n6_virtual_position_event_source_order_side'
      AND conrelid = to_regclass('public.n6_virtual_position_event')
  ) THEN
    ALTER TABLE public.n6_virtual_position_event
      ADD CONSTRAINT ck_b_track_v1_n6_virtual_position_event_source_order_side
      CHECK (
        source_order_side IS NULL
        OR source_order_side IN ('buy','sell')
      );
  END IF;
END
$$;

COMMIT;
