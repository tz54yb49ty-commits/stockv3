-- A-share monitor v3 N4 C3 replay audit schema rollback.
--
-- Scope: schema rollback only.
-- Execute only if all replay audit tables are empty. This rollback does not
-- touch common_trigger_run, common_trigger_quality_item, trigger_match/state,
-- event outbox/inbox/checkpoint, N3 facts, N4 current runtime, or N5 runtime.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
BEGIN
  IF to_regclass('public.stock_trigger_replay_audit') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM stock_trigger_replay_audit;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing to drop stock_trigger_replay_audit: table contains % rows', v_count;
    END IF;
  END IF;

  IF to_regclass('public.index_trigger_replay_audit') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM index_trigger_replay_audit;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing to drop index_trigger_replay_audit: table contains % rows', v_count;
    END IF;
  END IF;

  IF to_regclass('public.board_trigger_replay_audit') IS NOT NULL THEN
    SELECT count(*) INTO v_count FROM board_trigger_replay_audit;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'Refusing to drop board_trigger_replay_audit: table contains % rows', v_count;
    END IF;
  END IF;
END $$;

DROP TABLE IF EXISTS board_trigger_replay_audit;
DROP TABLE IF EXISTS index_trigger_replay_audit;
DROP TABLE IF EXISTS stock_trigger_replay_audit;

COMMIT;
