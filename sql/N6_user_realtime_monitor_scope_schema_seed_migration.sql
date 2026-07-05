BEGIN;

CREATE TABLE IF NOT EXISTS user_realtime_monitor_scope (
  realtime_scope_id BIGSERIAL PRIMARY KEY,
  principal_id BIGINT NOT NULL,
  principal_type TEXT NOT NULL,
  user_id BIGINT NOT NULL,
  asset_kind TEXT NOT NULL CHECK (asset_kind IN ('stock', 'index', 'board')),
  identity_key TEXT NOT NULL,
  display_name TEXT,
  source_type TEXT NOT NULL DEFAULT 'manual',
  source_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_default_seed BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted')),
  deleted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS user_realtime_monitor_scope_user_identity_uidx
  ON user_realtime_monitor_scope (
    principal_id,
    principal_type,
    user_id,
    asset_kind,
    identity_key
  );

CREATE INDEX IF NOT EXISTS user_realtime_monitor_scope_active_lookup_idx
  ON user_realtime_monitor_scope (
    principal_id,
    principal_type,
    user_id,
    asset_kind,
    identity_key
  )
  WHERE status = 'active';

INSERT INTO user_realtime_monitor_scope (
  principal_id,
  principal_type,
  user_id,
  asset_kind,
  identity_key,
  display_name,
  source_type,
  source_snapshot_json,
  is_default_seed,
  status
)
WITH active_user_principals AS (
  SELECT u.user_id AS principal_id,
         CASE
           WHEN u.role = 'admin' THEN 'admin'
           ELSE 'human_user'
         END AS principal_type,
         u.user_id AS user_id
  FROM user_account u
  WHERE u.status = 'active'
)
SELECT p.principal_id,
       p.principal_type,
       p.user_id,
       seed.asset_kind,
       seed.identity_key,
       seed.display_name,
       'default_seed',
       jsonb_build_object(
         'asset_kind', seed.asset_kind,
         'identity_key', seed.identity_key,
         'display_name', seed.display_name,
         'seed_policy', 'n6_default_realtime_monitor_scope_v1'
       ),
       true,
       'active'
FROM active_user_principals p
CROSS JOIN (
  VALUES
    ('index', 'index:SH:000001', '上证指数'),
    ('index', 'index:SH:000016', '上证50'),
    ('index', 'index:SH:000300', '沪深300'),
    ('index', 'index:SH:000688', '科创50'),
    ('index', 'index:SH:000852', '中证1000'),
    ('index', 'index:SH:000905', '中证500'),
    ('index', 'index:SZ:399001', '深证成指'),
    ('index', 'index:SZ:399006', '创业板指'),
    ('index', 'index:SZ:399303', '国证2000')
) AS seed(asset_kind, identity_key, display_name)
ON CONFLICT (principal_id, principal_type, user_id, asset_kind, identity_key)
DO NOTHING;

COMMIT;
