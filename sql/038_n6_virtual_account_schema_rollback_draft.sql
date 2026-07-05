-- N6 Phase 3 virtual account schema rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: rollback only objects created by
-- sql/038_n6_virtual_account_schema_draft.sql.
-- Boundary: no 036/037 table/view/permission drop, no N1-N6 fact/outbox change,
-- no N6_UI_v1 change, no worker, no delivery/push/voice/mobile/sim/position
-- real trade.

BEGIN;

DO $$
DECLARE
  v_table TEXT;
  v_count BIGINT;
  v_tables TEXT[] := ARRAY[
    'n6_virtual_pnl_snapshot',
    'n6_virtual_position_event',
    'n6_virtual_cash_snapshot',
    'n6_virtual_cash_ledger',
    'n6_virtual_trade',
    'n6_virtual_order',
    'n6_virtual_position',
    'n6_virtual_account'
  ];
BEGIN
  FOREACH v_table IN ARRAY v_tables LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I', v_table) INTO v_count;
      IF v_count <> 0 THEN
        RAISE EXCEPTION '038 rollback blocked: table % has % rows', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DROP TABLE IF EXISTS n6_virtual_pnl_snapshot;
DROP TABLE IF EXISTS n6_virtual_position_event;
DROP TABLE IF EXISTS n6_virtual_cash_snapshot;
DROP TABLE IF EXISTS n6_virtual_cash_ledger;
DROP TABLE IF EXISTS n6_virtual_trade;
DROP TABLE IF EXISTS n6_virtual_order;
DROP TABLE IF EXISTS n6_virtual_position;
DROP TABLE IF EXISTS n6_virtual_account;

COMMIT;
