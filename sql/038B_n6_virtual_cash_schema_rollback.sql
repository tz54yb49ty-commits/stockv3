-- N6 Phase 3 038B virtual cash schema rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: rollback only n6_virtual_cash_snapshot and n6_virtual_cash_ledger.
-- Boundary: no n6_virtual_account drop, no 036/037 object drop, no N1-N6
-- fact/outbox change, no N6_UI_v1 change, no worker, no delivery/push/
-- voice/mobile/sim/position/real trade.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
  v_table TEXT;
  v_future_tables TEXT[] := ARRAY[
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_pnl_snapshot'
  ];
BEGIN
  IF to_regclass('public.n6_virtual_cash_snapshot') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_cash_snapshot;
    IF v_count <> 0 THEN
      RAISE EXCEPTION '038B rollback blocked: n6_virtual_cash_snapshot has % rows', v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_cash_ledger') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_cash_ledger;
    IF v_count <> 0 THEN
      RAISE EXCEPTION '038B rollback blocked: n6_virtual_cash_ledger has % rows', v_count;
    END IF;
  END IF;

  FOREACH v_table IN ARRAY v_future_tables LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I', v_table) INTO v_count;
      IF v_count <> 0 THEN
        RAISE EXCEPTION '038B rollback blocked: future dependent table % has % rows', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DROP TABLE IF EXISTS n6_virtual_cash_snapshot;
DROP TABLE IF EXISTS n6_virtual_cash_ledger;

COMMIT;
