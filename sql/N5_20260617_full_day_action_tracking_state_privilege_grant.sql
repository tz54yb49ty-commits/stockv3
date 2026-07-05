-- N5 full-day trigger-state closed-loop tracking table privilege grant.
-- Scope: additive table privileges only for public.common_action_tracking_state
-- and runtime role ashare_v3_user.
-- Boundary: do not execute without explicit privilege repair execute gate.
-- No schema changes, no data writes, no N5 runtime, no N4 outbox change,
-- no inbox/checkpoint write, no N6, no worker, no voice/mobile/sim/position/order/real trade.

DO $$
BEGIN
  IF to_regclass('public.common_action_tracking_state') IS NULL THEN
    RAISE EXCEPTION 'common_action_tracking_state privilege grant blocked: table is absent';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ashare_v3_user') THEN
    RAISE EXCEPTION 'common_action_tracking_state privilege grant blocked: role ashare_v3_user is absent';
  END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.common_action_tracking_state
TO ashare_v3_user;
