-- N6 B-track V2 user monitor preference schema.
-- Scope: user_monitor_* only. Do not execute from runtime_control without a migration gate.

CREATE SEQUENCE IF NOT EXISTS user_monitor_id_seq;

CREATE TABLE IF NOT EXISTS user_monitor_stock (
    monitor_id bigint PRIMARY KEY DEFAULT nextval('user_monitor_id_seq'),
    principal_id bigint NOT NULL,
    principal_type text NOT NULL,
    user_id bigint NOT NULL,
    asset_kind text NOT NULL DEFAULT 'stock',
    identity_key text NOT NULL,
    direction text NOT NULL,
    source_type text NOT NULL DEFAULT 'single_row',
    source_run_id text,
    projection_run_id text,
    condition_key text,
    status text NOT NULL DEFAULT 'active',
    quality_status text NOT NULL DEFAULT 'reviewed',
    last_signal_state text,
    source_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    valid_source_trade_date text,
    valid_for_trade_date text,
    valid_source_run_id text,
    expired_at timestamptz,
    expired_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    removed_at timestamptz,
    CONSTRAINT user_monitor_stock_asset_kind_ck CHECK (asset_kind = 'stock'),
    CONSTRAINT user_monitor_stock_direction_ck CHECK (direction IN ('buy', 'sell')),
    CONSTRAINT user_monitor_stock_status_ck CHECK (status IN ('active', 'paused', 'expired', 'removed'))
);

CREATE TABLE IF NOT EXISTS user_monitor_index (
    monitor_id bigint PRIMARY KEY DEFAULT nextval('user_monitor_id_seq'),
    principal_id bigint NOT NULL,
    principal_type text NOT NULL,
    user_id bigint NOT NULL,
    asset_kind text NOT NULL DEFAULT 'index',
    identity_key text NOT NULL,
    direction text NOT NULL,
    source_type text NOT NULL DEFAULT 'single_row',
    source_run_id text,
    projection_run_id text,
    condition_key text,
    status text NOT NULL DEFAULT 'active',
    quality_status text NOT NULL DEFAULT 'reviewed',
    last_signal_state text,
    source_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    valid_source_trade_date text,
    valid_for_trade_date text,
    valid_source_run_id text,
    expired_at timestamptz,
    expired_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    removed_at timestamptz,
    CONSTRAINT user_monitor_index_asset_kind_ck CHECK (asset_kind = 'index'),
    CONSTRAINT user_monitor_index_direction_ck CHECK (direction IN ('buy', 'sell')),
    CONSTRAINT user_monitor_index_status_ck CHECK (status IN ('active', 'paused', 'expired', 'removed'))
);

CREATE TABLE IF NOT EXISTS user_monitor_board (
    monitor_id bigint PRIMARY KEY DEFAULT nextval('user_monitor_id_seq'),
    principal_id bigint NOT NULL,
    principal_type text NOT NULL,
    user_id bigint NOT NULL,
    asset_kind text NOT NULL DEFAULT 'board',
    identity_key text NOT NULL,
    direction text NOT NULL,
    source_type text NOT NULL DEFAULT 'single_row',
    source_run_id text,
    projection_run_id text,
    condition_key text,
    status text NOT NULL DEFAULT 'active',
    quality_status text NOT NULL DEFAULT 'reviewed',
    last_signal_state text,
    source_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    valid_source_trade_date text,
    valid_for_trade_date text,
    valid_source_run_id text,
    expired_at timestamptz,
    expired_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    removed_at timestamptz,
    CONSTRAINT user_monitor_board_asset_kind_ck CHECK (asset_kind = 'board'),
    CONSTRAINT user_monitor_board_direction_ck CHECK (direction IN ('buy', 'sell')),
    CONSTRAINT user_monitor_board_status_ck CHECK (status IN ('active', 'paused', 'expired', 'removed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS user_monitor_stock_active_uk
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
CREATE UNIQUE INDEX IF NOT EXISTS user_monitor_index_active_uk
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
CREATE UNIQUE INDEX IF NOT EXISTS user_monitor_board_active_uk
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

CREATE INDEX IF NOT EXISTS user_monitor_stock_principal_idx
    ON user_monitor_stock (principal_id, principal_type, user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS user_monitor_index_principal_idx
    ON user_monitor_index (principal_id, principal_type, user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS user_monitor_board_principal_idx
    ON user_monitor_board (principal_id, principal_type, user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS user_monitor_stock_valid_batch_idx
    ON user_monitor_stock (principal_id, principal_type, user_id, status, valid_source_trade_date, valid_for_trade_date, valid_source_run_id);
CREATE INDEX IF NOT EXISTS user_monitor_index_valid_batch_idx
    ON user_monitor_index (principal_id, principal_type, user_id, status, valid_source_trade_date, valid_for_trade_date, valid_source_run_id);
CREATE INDEX IF NOT EXISTS user_monitor_board_valid_batch_idx
    ON user_monitor_board (principal_id, principal_type, user_id, status, valid_source_trade_date, valid_for_trade_date, valid_source_run_id);
