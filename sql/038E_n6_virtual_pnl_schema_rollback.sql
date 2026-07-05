-- N6 Phase 3 038E virtual PnL snapshot schema rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: rollback only n6_virtual_pnl_snapshot.
-- Boundary: no 038A/038B/038C/038D/036/037 object drop, no N1-N6
-- fact/outbox change, no N6_UI_v1 change, no worker, no delivery/push/
-- voice/mobile/sim/position/real trade.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
BEGIN
  IF to_regclass('public.n6_virtual_pnl_snapshot') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_pnl_snapshot;
    IF v_count <> 0 THEN
      RAISE EXCEPTION '038E rollback blocked: n6_virtual_pnl_snapshot has % rows', v_count;
    END IF;
  END IF;
END $$;

DROP TABLE IF EXISTS n6_virtual_pnl_snapshot;

COMMIT;
