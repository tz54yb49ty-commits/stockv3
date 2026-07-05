-- N5 full-day trigger-state closed-loop tracking table privilege grant rollback.
-- Scope: revoke only the table privileges granted by
-- sql/N5_20260617_full_day_action_tracking_state_privilege_grant.sql.
-- Boundary: do not execute without explicit privilege rollback execute gate.
-- No schema drops, no data writes, no N5 runtime, no N4 outbox change,
-- no inbox/checkpoint write, no N6, no worker, no voice/mobile/sim/position/order/real trade.

DO $$
BEGIN
  IF to_regclass('public.common_action_tracking_state') IS NULL THEN
    RAISE EXCEPTION 'common_action_tracking_state privilege rollback blocked: table is absent';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ashare_v3_user') THEN
    RAISE EXCEPTION 'common_action_tracking_state privilege rollback blocked: role ashare_v3_user is absent';
  END IF;
END $$;

REVOKE SELECT, INSERT, UPDATE, DELETE
ON TABLE public.common_action_tracking_state
FROM ashare_v3_user;
