-- A-share monitor v3 N3 realtime projection metric schema rollback draft.
-- Scope: rollback only the N3-P1 projection metric schema introduced by
-- sql/015_market_realtime_projection_metric_schema.sql.
--
-- This rollback is guarded: it refuses to drop projection tables after any
-- projection business rows exist. Future N3-B2 business-data rollback must
-- delete rows by projection_run_id before this schema rollback is considered.
-- It does not touch realtime_daily_snapshot, common_event_outbox, common_event_inbox,
-- trigger/action/user/voice/mobile/sim/position tables, N2 condition tables, or
-- old systems.

BEGIN;

DO $$
BEGIN
  IF to_regclass('public.stock_realtime_projection_metric') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.stock_realtime_projection_metric LIMIT 1) THEN
    RAISE EXCEPTION 'Refusing to drop stock_realtime_projection_metric: table contains projection rows';
  END IF;

  IF to_regclass('public.index_realtime_projection_metric') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.index_realtime_projection_metric LIMIT 1) THEN
    RAISE EXCEPTION 'Refusing to drop index_realtime_projection_metric: table contains projection rows';
  END IF;

  IF to_regclass('public.board_realtime_projection_metric') IS NOT NULL
     AND EXISTS (SELECT 1 FROM public.board_realtime_projection_metric LIMIT 1) THEN
    RAISE EXCEPTION 'Refusing to drop board_realtime_projection_metric: table contains projection rows';
  END IF;
END $$;

DROP TABLE IF EXISTS board_realtime_projection_metric;
DROP TABLE IF EXISTS index_realtime_projection_metric;
DROP TABLE IF EXISTS stock_realtime_projection_metric;

COMMIT;
