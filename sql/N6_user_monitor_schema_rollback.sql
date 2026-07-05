-- HARD FAIL: this rollback is an artifact, not an executable command.
-- Remove this block only inside a dedicated, approved rollback gate.
DO $$
BEGIN
    RAISE EXCEPTION 'HARD FAIL: user_monitor rollback requires an approved rollback gate';
END $$;

-- Scope after explicit approval only:
-- DROP TABLE IF EXISTS user_monitor_stock;
-- DROP TABLE IF EXISTS user_monitor_index;
-- DROP TABLE IF EXISTS user_monitor_board;
-- DROP SEQUENCE IF EXISTS user_monitor_id_seq;
