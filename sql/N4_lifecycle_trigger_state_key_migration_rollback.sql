-- Rollback draft for N4 lifecycle-only trigger state key migration.

BEGIN;

DROP INDEX IF EXISTS common_trigger_state_lifecycle_key_v1;

COMMIT;
