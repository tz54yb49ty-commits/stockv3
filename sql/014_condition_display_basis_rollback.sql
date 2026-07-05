-- N2-Display-1 manual rollback draft for 014 condition display basis schema.
-- Do not execute without explicit user confirmation.
-- This removes only the three display basis tables created by 014.
-- It does not alter condition_basis / condition_pool / minute_target_scope.

BEGIN;

DROP TABLE IF EXISTS stock_condition_display_basis;
DROP TABLE IF EXISTS index_condition_display_basis;
DROP TABLE IF EXISTS board_condition_display_basis;

COMMIT;
