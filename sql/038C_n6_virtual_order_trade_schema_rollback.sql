-- N6 Phase 3 038C virtual order/trade schema rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: rollback only n6_virtual_trade and n6_virtual_order.
-- Boundary: no 038A/038B/036/037 object drop, no N1-N6 fact/outbox change,
-- no N6_UI_v1 change, no worker, no delivery/push/voice/mobile/sim/position
-- real trade.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
  v_table TEXT;
  v_future_tables TEXT[] := ARRAY[
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_pnl_snapshot'
  ];
BEGIN
  IF to_regclass('public.n6_virtual_trade') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_trade;
    IF v_count <> 0 THEN
      RAISE EXCEPTION '038C rollback blocked: n6_virtual_trade has % rows', v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_order') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_order;
    IF v_count <> 0 THEN
      RAISE EXCEPTION '038C rollback blocked: n6_virtual_order has % rows', v_count;
    END IF;
  END IF;

  FOREACH v_table IN ARRAY v_future_tables LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I', v_table) INTO v_count;
      IF v_count <> 0 THEN
        RAISE EXCEPTION '038C rollback blocked: future dependent table % has % rows', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DROP TABLE IF EXISTS n6_virtual_trade;
DROP TABLE IF EXISTS n6_virtual_order;

COMMIT;
