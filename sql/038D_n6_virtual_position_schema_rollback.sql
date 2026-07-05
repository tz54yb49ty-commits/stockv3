-- N6 Phase 3 038D virtual position schema rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: rollback only n6_virtual_position_event and n6_virtual_position.
-- Boundary: no 038A/038B/038C/036/037 object drop, no N1-N6 fact/outbox
-- change, no N6_UI_v1 change, no worker, no delivery/push/voice/mobile/sim
-- real position/real trade.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
BEGIN
  IF to_regclass('public.n6_virtual_position_event') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_position_event;
    IF v_count <> 0 THEN
      RAISE EXCEPTION '038D rollback blocked: n6_virtual_position_event has % rows', v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_position') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_position;
    IF v_count <> 0 THEN
      RAISE EXCEPTION '038D rollback blocked: n6_virtual_position has % rows', v_count;
    END IF;
  END IF;

  IF to_regclass('public.n6_virtual_pnl_snapshot') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM n6_virtual_pnl_snapshot;
    IF v_count <> 0 THEN
      RAISE EXCEPTION '038D rollback blocked: future dependent table n6_virtual_pnl_snapshot has % rows', v_count;
    END IF;
  END IF;
END $$;

DROP TABLE IF EXISTS n6_virtual_position_event;
DROP TABLE IF EXISTS n6_virtual_position;

COMMIT;
