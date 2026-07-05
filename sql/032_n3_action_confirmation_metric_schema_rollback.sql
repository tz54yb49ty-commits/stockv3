-- A-share monitor v3 N3 action-confirmation projection metric schema rollback draft.
-- Use only after a separate schema migration final gate, and only when all
-- three action-confirmation metric tables are empty. If business rows exist,
-- run the projection_run_id scoped business rollback first.

\set ON_ERROR_STOP on

-- Hard guard: all counts must be 0 before schema rollback. Any business row
-- must be removed through the projection_run_id scoped business rollback first.
DO $$
DECLARE
  stock_count BIGINT;
  index_count BIGINT;
  board_count BIGINT;
BEGIN
  SELECT count(*) INTO stock_count FROM stock_action_confirmation_projection_metric;
  SELECT count(*) INTO index_count FROM index_action_confirmation_projection_metric;
  SELECT count(*) INTO board_count FROM board_action_confirmation_projection_metric;

  IF stock_count <> 0 OR index_count <> 0 OR board_count <> 0 THEN
    RAISE EXCEPTION
      'action_confirmation metric schema rollback blocked: non-empty tables stock=%, index=%, board=%',
      stock_count,
      index_count,
      board_count;
  END IF;
END $$;

BEGIN;

DROP TABLE IF EXISTS board_action_confirmation_projection_metric;
DROP TABLE IF EXISTS index_action_confirmation_projection_metric;
DROP TABLE IF EXISTS stock_action_confirmation_projection_metric;

COMMIT;
