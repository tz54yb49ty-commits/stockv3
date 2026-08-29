-- Windows N6 canonical action projection idempotency and episode lookup.
-- N6_user only.  Does not consume Outbox or create projection/card rows.

BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS user_signal_projection_windows_event_user_uidx
  ON user_signal_projection (
    source_outbox_id,
    source_event_id,
    user_id
  )
  WHERE source_outbox_id IS NOT NULL
    AND source_action_event_type IN (
      'ActionEligible',
      'ActionBlocked',
      'ActionExecuted',
      'ActionSkipped'
    );

CREATE INDEX IF NOT EXISTS user_signal_projection_windows_episode_lookup_idx
  ON user_signal_projection (
    user_id, asset_kind, identity_key, direction,
    ((source_payload_json #>> '{payload_json,episode_entry_event_id}'))
  )
  WHERE source_action_event_type = 'ActionEligible';
