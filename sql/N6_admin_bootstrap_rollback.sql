-- N6 admin bootstrap business rollback draft.
-- Do not execute without explicit user confirmation.
-- Scope: rollback only the future initial admin bootstrap rows.
-- Boundary: no N1-N5 mutation, no N5 outbox consumption, no session rollback,
-- no projection/sim/notification rollback, no voice/mobile push, no real trade.
--
-- This rollback is safe only immediately after admin bootstrap, before any
-- session, watchlist, projection, notification, sim, or other user rows exist.

BEGIN;

DO $$
DECLARE
  v_admin_user_id BIGINT;
  v_count BIGINT;
  v_deleted_profiles INTEGER;
  v_deleted_accounts INTEGER;
BEGIN
  SELECT count(*) INTO v_count FROM user_account;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: expected exactly 1 user_account row, found %', v_count;
  END IF;

  SELECT user_id
    INTO v_admin_user_id
    FROM user_account
   WHERE login_name = 'admin'
     AND role = 'admin'
     AND status = 'active';

  IF v_admin_user_id IS NULL THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: active admin account not found';
  END IF;

  SELECT count(*) INTO v_count
    FROM user_filter_profile
   WHERE user_id = v_admin_user_id;
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: expected exactly 1 admin filter profile, found %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_filter_profile
   WHERE user_id = v_admin_user_id
     AND profile_name = 'MVP default'
     AND is_default = true
     AND status = 'active';
  IF v_count <> 1 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: default active admin filter profile not found';
  END IF;

  SELECT count(*) INTO v_count FROM user_session;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_session has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_watchlist;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_watchlist has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_watchlist_item;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_watchlist_item has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_projection_run;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_projection_run has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_signal_projection;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_signal_projection has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_signal_card;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_signal_card has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_signal_decision;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_signal_decision has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_notification_queue;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_notification_queue has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_sim_account;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_sim_account has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_sim_order;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_sim_order has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_sim_trade;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_sim_trade has % rows', v_count;
  END IF;

  SELECT count(*) INTO v_count FROM user_sim_position;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: user_sim_position has % rows', v_count;
  END IF;

  DELETE FROM user_filter_profile
   WHERE user_id = v_admin_user_id
     AND profile_name = 'MVP default'
     AND is_default = true
     AND status = 'active';
  GET DIAGNOSTICS v_deleted_profiles = ROW_COUNT;
  IF v_deleted_profiles <> 1 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: expected to delete 1 profile, deleted %', v_deleted_profiles;
  END IF;

  DELETE FROM user_account
   WHERE user_id = v_admin_user_id
     AND login_name = 'admin'
     AND role = 'admin'
     AND status = 'active';
  GET DIAGNOSTICS v_deleted_accounts = ROW_COUNT;
  IF v_deleted_accounts <> 1 THEN
    RAISE EXCEPTION 'N6 admin bootstrap rollback blocked: expected to delete 1 admin account, deleted %', v_deleted_accounts;
  END IF;
END $$;

COMMIT;
