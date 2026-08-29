-- Code-only rollback companion for 043.  Execute only in an authorized N6 gate.

BEGIN;

DROP INDEX IF EXISTS user_signal_projection_windows_episode_lookup_idx;
DROP INDEX IF EXISTS user_signal_projection_windows_event_user_uidx;

COMMIT;
