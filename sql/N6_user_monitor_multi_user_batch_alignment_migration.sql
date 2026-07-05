-- N6 user monitor multi-user + batch identity alignment.
-- Scope: user_monitor_stock / user_monitor_index / user_monitor_board only.
-- Do not execute without an explicit N6_user schema execute gate.

BEGIN;

ALTER TABLE user_monitor_stock ADD COLUMN IF NOT EXISTS user_id bigint;
ALTER TABLE user_monitor_index ADD COLUMN IF NOT EXISTS user_id bigint;
ALTER TABLE user_monitor_board ADD COLUMN IF NOT EXISTS user_id bigint;

ALTER TABLE user_monitor_stock ADD COLUMN IF NOT EXISTS valid_source_trade_date text;
ALTER TABLE user_monitor_stock ADD COLUMN IF NOT EXISTS valid_for_trade_date text;
ALTER TABLE user_monitor_stock ADD COLUMN IF NOT EXISTS valid_source_run_id text;

ALTER TABLE user_monitor_index ADD COLUMN IF NOT EXISTS valid_source_trade_date text;
ALTER TABLE user_monitor_index ADD COLUMN IF NOT EXISTS valid_for_trade_date text;
ALTER TABLE user_monitor_index ADD COLUMN IF NOT EXISTS valid_source_run_id text;

ALTER TABLE user_monitor_board ADD COLUMN IF NOT EXISTS valid_source_trade_date text;
ALTER TABLE user_monitor_board ADD COLUMN IF NOT EXISTS valid_for_trade_date text;
ALTER TABLE user_monitor_board ADD COLUMN IF NOT EXISTS valid_source_run_id text;

UPDATE user_monitor_stock
SET valid_source_trade_date = COALESCE(valid_source_trade_date, source_snapshot_json->>'source_trade_date'),
    valid_for_trade_date = COALESCE(valid_for_trade_date, source_snapshot_json->>'for_trade_date'),
    valid_source_run_id = COALESCE(valid_source_run_id, source_snapshot_json->>'source_run_id');

UPDATE user_monitor_index
SET valid_source_trade_date = COALESCE(valid_source_trade_date, source_snapshot_json->>'source_trade_date'),
    valid_for_trade_date = COALESCE(valid_for_trade_date, source_snapshot_json->>'for_trade_date'),
    valid_source_run_id = COALESCE(valid_source_run_id, source_snapshot_json->>'source_run_id');

UPDATE user_monitor_board
SET valid_source_trade_date = COALESCE(valid_source_trade_date, source_snapshot_json->>'source_trade_date'),
    valid_for_trade_date = COALESCE(valid_for_trade_date, source_snapshot_json->>'for_trade_date'),
    valid_source_run_id = COALESCE(valid_source_run_id, source_snapshot_json->>'source_run_id');

UPDATE user_monitor_stock m
SET user_id = p.owner_user_id
FROM n6_principal p
WHERE m.user_id IS NULL
  AND p.principal_id = m.principal_id
  AND p.principal_type = m.principal_type
  AND p.owner_user_id IS NOT NULL;

UPDATE user_monitor_index m
SET user_id = p.owner_user_id
FROM n6_principal p
WHERE m.user_id IS NULL
  AND p.principal_id = m.principal_id
  AND p.principal_type = m.principal_type
  AND p.owner_user_id IS NOT NULL;

UPDATE user_monitor_board m
SET user_id = p.owner_user_id
FROM n6_principal p
WHERE m.user_id IS NULL
  AND p.principal_id = m.principal_id
  AND p.principal_type = m.principal_type
  AND p.owner_user_id IS NOT NULL;

UPDATE user_monitor_stock m
SET user_id = m.principal_id
WHERE m.user_id IS NULL
  AND EXISTS (SELECT 1 FROM user_account u WHERE u.user_id = m.principal_id);

UPDATE user_monitor_index m
SET user_id = m.principal_id
WHERE m.user_id IS NULL
  AND EXISTS (SELECT 1 FROM user_account u WHERE u.user_id = m.principal_id);

UPDATE user_monitor_board m
SET user_id = m.principal_id
WHERE m.user_id IS NULL
  AND EXISTS (SELECT 1 FROM user_account u WHERE u.user_id = m.principal_id);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM user_monitor_stock WHERE user_id IS NULL
    UNION ALL
    SELECT 1 FROM user_monitor_index WHERE user_id IS NULL
    UNION ALL
    SELECT 1 FROM user_monitor_board WHERE user_id IS NULL
  ) THEN
    RAISE EXCEPTION 'N6 user_monitor user_id backfill incomplete';
  END IF;
END $$;

ALTER TABLE user_monitor_stock ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE user_monitor_index ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE user_monitor_board ALTER COLUMN user_id SET NOT NULL;

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
    ON user_monitor_stock (
        principal_id,
        principal_type,
        user_id,
        asset_kind,
        identity_key,
        direction,
        COALESCE(valid_source_trade_date, ''),
        COALESCE(valid_for_trade_date, ''),
        COALESCE(valid_source_run_id, '')
    )
    WHERE status <> 'removed';

CREATE UNIQUE INDEX user_monitor_index_active_uk
    ON user_monitor_index (
        principal_id,
        principal_type,
        user_id,
        asset_kind,
        identity_key,
        direction,
        COALESCE(valid_source_trade_date, ''),
        COALESCE(valid_for_trade_date, ''),
        COALESCE(valid_source_run_id, '')
    )
    WHERE status <> 'removed';

CREATE UNIQUE INDEX user_monitor_board_active_uk
    ON user_monitor_board (
        principal_id,
        principal_type,
        user_id,
        asset_kind,
        identity_key,
        direction,
        COALESCE(valid_source_trade_date, ''),
        COALESCE(valid_for_trade_date, ''),
        COALESCE(valid_source_run_id, '')
    )
    WHERE status <> 'removed';

CREATE INDEX user_monitor_stock_principal_idx
    ON user_monitor_stock (principal_id, principal_type, user_id, status, created_at DESC);
CREATE INDEX user_monitor_index_principal_idx
    ON user_monitor_index (principal_id, principal_type, user_id, status, created_at DESC);
CREATE INDEX user_monitor_board_principal_idx
    ON user_monitor_board (principal_id, principal_type, user_id, status, created_at DESC);

CREATE INDEX user_monitor_stock_valid_batch_idx
    ON user_monitor_stock (principal_id, principal_type, user_id, status, valid_source_trade_date, valid_for_trade_date, valid_source_run_id);
CREATE INDEX user_monitor_index_valid_batch_idx
    ON user_monitor_index (principal_id, principal_type, user_id, status, valid_source_trade_date, valid_for_trade_date, valid_source_run_id);
CREATE INDEX user_monitor_board_valid_batch_idx
    ON user_monitor_board (principal_id, principal_type, user_id, status, valid_source_trade_date, valid_for_trade_date, valid_source_run_id);

COMMIT;
