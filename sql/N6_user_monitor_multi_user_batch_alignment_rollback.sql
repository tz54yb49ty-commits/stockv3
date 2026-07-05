-- Rollback for N6 user monitor multi-user + batch identity alignment.
-- Do not execute without an explicit user-approved rollback gate.

BEGIN;

DROP INDEX IF EXISTS user_monitor_stock_active_uk;
DROP INDEX IF EXISTS user_monitor_index_active_uk;
DROP INDEX IF EXISTS user_monitor_board_active_uk;
DROP INDEX IF EXISTS user_monitor_stock_principal_idx;
DROP INDEX IF EXISTS user_monitor_index_principal_idx;
DROP INDEX IF EXISTS user_monitor_board_principal_idx;
DROP INDEX IF EXISTS user_monitor_stock_valid_batch_idx;
DROP INDEX IF EXISTS user_monitor_index_valid_batch_idx;
DROP INDEX IF EXISTS user_monitor_board_valid_batch_idx;

CREATE UNIQUE INDEX user_monitor_stock_active_uk
    ON user_monitor_stock (principal_id, principal_type, asset_kind, identity_key, direction)
    WHERE status <> 'removed';
CREATE UNIQUE INDEX user_monitor_index_active_uk
    ON user_monitor_index (principal_id, principal_type, asset_kind, identity_key, direction)
    WHERE status <> 'removed';
CREATE UNIQUE INDEX user_monitor_board_active_uk
    ON user_monitor_board (principal_id, principal_type, asset_kind, identity_key, direction)
    WHERE status <> 'removed';

CREATE INDEX user_monitor_stock_principal_idx
    ON user_monitor_stock (principal_id, principal_type, status, created_at DESC);
CREATE INDEX user_monitor_index_principal_idx
    ON user_monitor_index (principal_id, principal_type, status, created_at DESC);
CREATE INDEX user_monitor_board_principal_idx
    ON user_monitor_board (principal_id, principal_type, status, created_at DESC);

CREATE INDEX user_monitor_stock_valid_batch_idx
    ON user_monitor_stock (principal_id, principal_type, status, valid_source_trade_date, valid_for_trade_date, valid_source_run_id);
CREATE INDEX user_monitor_index_valid_batch_idx
    ON user_monitor_index (principal_id, principal_type, status, valid_source_trade_date, valid_for_trade_date, valid_source_run_id);
CREATE INDEX user_monitor_board_valid_batch_idx
    ON user_monitor_board (principal_id, principal_type, status, valid_source_trade_date, valid_for_trade_date, valid_source_run_id);

ALTER TABLE user_monitor_stock ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE user_monitor_index ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE user_monitor_board ALTER COLUMN user_id DROP NOT NULL;

COMMIT;
