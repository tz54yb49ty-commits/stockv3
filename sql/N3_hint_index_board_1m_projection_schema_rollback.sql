-- N3 index/board 1m HINT projection proof schema rollback draft.
-- Use only after a separate rollback gate, and only when both proof tables
-- are empty. Business rows must be removed through run-id scoped rollback.

\set ON_ERROR_STOP on

DO $$
DECLARE
  index_count BIGINT := 0;
  board_count BIGINT := 0;
BEGIN
  IF to_regclass('index_realtime_hint_projection_metric') IS NOT NULL THEN
    SELECT count(*) INTO index_count FROM index_realtime_hint_projection_metric;
  END IF;

  IF to_regclass('board_realtime_hint_projection_metric') IS NOT NULL THEN
    SELECT count(*) INTO board_count FROM board_realtime_hint_projection_metric;
  END IF;

  IF index_count <> 0 OR board_count <> 0 THEN
    RAISE EXCEPTION
      'N3 HINT projection schema rollback blocked: non-empty tables index=%, board=%',
      index_count,
      board_count;
  END IF;
END $$;

BEGIN;

DROP TABLE IF EXISTS board_realtime_hint_projection_metric;
DROP TABLE IF EXISTS index_realtime_hint_projection_metric;

COMMIT;
