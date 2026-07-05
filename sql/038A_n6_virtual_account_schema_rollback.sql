-- N6 Phase 3 038A virtual account schema rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: rollback only n6_virtual_account from 038A.
-- Boundary: no 036/037 table/view/permission drop, no N1-N6 fact/outbox change,
-- no N6_UI_v1 change, no worker, no delivery/push/voice/mobile/sim/position
-- real trade.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
  v_table TEXT;
  v_future_tables TEXT[] := ARRAY[
    'n6_virtual_cash_ledger',
    'n6_virtual_cash_snapshot',
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_pnl_snapshot'
  ];
BEGIN
  IF to_regclass('public.n6_virtual_account') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_account;
    IF v_count <> 0 THEN
      RAISE EXCEPTION '038A rollback blocked: n6_virtual_account has % rows', v_count;
    END IF;
  END IF;

  FOREACH v_table IN ARRAY v_future_tables LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I', v_table) INTO v_count;
      IF v_count <> 0 THEN
        RAISE EXCEPTION '038A rollback blocked: future dependent table % has % rows', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DROP TABLE IF EXISTS n6_virtual_account;

COMMIT;
