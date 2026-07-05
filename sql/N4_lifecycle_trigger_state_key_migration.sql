-- N4 lifecycle-only trigger state key migration draft.
--
-- Purpose:
--   New action-confirmation metric runtime state identity is:
--     run_id, for_trade_date, asset_kind, identity_key, direction, signal_type, condition_key
--
-- Legacy rows used trigger_period/trigger_bucket in the unique key, which creates
-- one state row per minute/period bucket.  This partial unique index applies only
-- to rows written with raw_json.lifecycle_state_key_version='n4_lifecycle_state_key_v1'
-- so historical rows are not silently rewritten.

BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS common_trigger_state_lifecycle_key_v1
ON common_trigger_state (
  run_id,
  for_trade_date,
  asset_kind,
  identity_key,
  direction,
  signal_type,
  condition_key
)
WHERE ((raw_json ->> 'lifecycle_state_key_version') = 'n4_lifecycle_state_key_v1');

COMMIT;
