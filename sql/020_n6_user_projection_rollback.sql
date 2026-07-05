-- N6 user projection MVP schema rollback draft.
-- Safe only when every N6-owned table below has row_count = 0.
-- If business rows exist, first rollback by user_projection_run_id and/or sim_run_id
-- in a separately reviewed N6 business rollback. This draft must not delete rows.

BEGIN;

DO $$
DECLARE
  v_table TEXT;
  v_count BIGINT;
  v_total BIGINT := 0;
  v_tables TEXT[] := ARRAY[
    'user_notification_queue',
    'user_sim_trade',
    'user_sim_order',
    'user_signal_decision',
    'user_signal_card',
    'user_signal_projection',
    'user_sim_position',
    'user_sim_account',
    'user_watchlist_item',
    'user_watchlist',
    'user_filter_profile',
    'user_session',
    'user_projection_run',
    'user_account'
  ];
BEGIN
  FOREACH v_table IN ARRAY v_tables LOOP
    IF to_regclass(v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I', v_table) INTO v_count;
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'N6 schema rollback blocked: table % has % rows. Roll back business data by user_projection_run_id/sim_run_id first.', v_table, v_count;
      END IF;
      v_total := v_total + v_count;
    END IF;
  END LOOP;

  IF v_total <> 0 THEN
    RAISE EXCEPTION 'N6 schema rollback blocked: total N6 row count is %', v_total;
  END IF;
END $$;

DROP TABLE IF EXISTS user_notification_queue;
DROP TABLE IF EXISTS user_sim_trade;
DROP TABLE IF EXISTS user_sim_order;
DROP TABLE IF EXISTS user_signal_decision;
DROP TABLE IF EXISTS user_signal_card;
DROP TABLE IF EXISTS user_signal_projection;
DROP TABLE IF EXISTS user_sim_position;
DROP TABLE IF EXISTS user_sim_account;
DROP TABLE IF EXISTS user_watchlist_item;
DROP TABLE IF EXISTS user_watchlist;
DROP TABLE IF EXISTS user_filter_profile;
DROP TABLE IF EXISTS user_session;
DROP TABLE IF EXISTS user_projection_run;
DROP TABLE IF EXISTS user_account;

COMMIT;
