-- N6 Track B owner/principal/account additive schema rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: rollback only objects created by
-- sql/036_n6_multi_user_ai_owner_principal_schema.sql.
-- Boundary: no N5 outbox status change, no N1-N5 fact change, no projection
-- rollback, no worker, no delivery/push/voice/mobile/sim/position/real trade.

BEGIN;

DO $$
DECLARE
  v_table TEXT;
  v_count BIGINT;
  v_tables TEXT[] := ARRAY[
    'n6_strategy',
    'n6_watchlist_ownership',
    'n6_principal_account',
    'n6_ai_user',
    'n6_principal'
  ];
BEGIN
  FOREACH v_table IN ARRAY v_tables LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I', v_table) INTO v_count;
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'rollback blocked: table % has % business rows', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DROP VIEW IF EXISTS v_n6_board_membership_fact;
DROP VIEW IF EXISTS v_n6_index_membership_fact;
DROP VIEW IF EXISTS v_n6_board_condition_display_basis;
DROP VIEW IF EXISTS v_n6_index_condition_display_basis;
DROP VIEW IF EXISTS v_n6_stock_condition_display_basis;

DROP TABLE IF EXISTS n6_strategy;
DROP TABLE IF EXISTS n6_watchlist_ownership;
DROP TABLE IF EXISTS n6_principal_account;
DROP TABLE IF EXISTS n6_ai_user;
DROP TABLE IF EXISTS n6_principal;

COMMIT;
