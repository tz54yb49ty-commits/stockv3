BEGIN;

DROP INDEX IF EXISTS user_realtime_monitor_scope_active_lookup_idx;
DROP INDEX IF EXISTS user_realtime_monitor_scope_user_identity_uidx;
DROP TABLE IF EXISTS user_realtime_monitor_scope;

COMMIT;
