-- A-share monitor v3 N3T action-confirmation metric schema rollback draft.
-- Use only after a later explicit final migration gate.
-- Guard: all N3T Option A tables must be empty before table removal.

\set ON_ERROR_STOP on

DO $$
DECLARE
  stock_count BIGINT;
  index_count BIGINT;
  board_count BIGINT;
BEGIN
  SELECT count(*) INTO stock_count FROM stock_n3t_action_confirmation_metric;
  SELECT count(*) INTO index_count FROM index_n3t_action_confirmation_metric;
  SELECT count(*) INTO board_count FROM board_n3t_action_confirmation_metric;

  IF stock_count <> 0 OR index_count <> 0 OR board_count <> 0 THEN
    RAISE EXCEPTION
      'n3t action-confirmation schema rollback blocked: non-empty tables stock=%, index=%, board=%',
      stock_count,
      index_count,
      board_count;
  END IF;
END $$;

BEGIN;

DROP TABLE IF EXISTS board_n3t_action_confirmation_metric;
DROP TABLE IF EXISTS index_n3t_action_confirmation_metric;
DROP TABLE IF EXISTS stock_n3t_action_confirmation_metric;

COMMIT;
