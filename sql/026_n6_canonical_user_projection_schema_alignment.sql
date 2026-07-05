-- A-share monitor v3 N6 canonical user projection schema alignment draft.
-- Stage: N6 canonical Action* compatibility.
-- Boundary: schema draft only; run only after a separate final gate.
--
-- This draft widens N6 projection constraints from the historical
-- ActionEvent / HintEvent MVP to canonical N5 Action* events while keeping
-- historical projection rows readable. It does not consume N5 outbox rows and
-- does not write projection/card/notification business rows.

BEGIN;

ALTER TABLE user_projection_run
  ALTER COLUMN source_event_types SET DEFAULT ARRAY[
    'ActionEvent',
    'HintEvent',
    'ActionEligible',
    'ActionBlocked',
    'ActionExecuted',
    'ActionSkipped'
  ]::TEXT[];

ALTER TABLE user_signal_projection
  ADD COLUMN IF NOT EXISTS source_action_event_type TEXT,
  ADD COLUMN IF NOT EXISTS action_state TEXT,
  ADD COLUMN IF NOT EXISTS action_mark TEXT,
  ADD COLUMN IF NOT EXISTS condition_key TEXT,
  ADD COLUMN IF NOT EXISTS original_condition_key TEXT,
  ADD COLUMN IF NOT EXISTS trace_json JSONB,
  ADD COLUMN IF NOT EXISTS projection_policy TEXT;

ALTER TABLE user_signal_card
  ADD COLUMN IF NOT EXISTS source_action_event_id TEXT,
  ADD COLUMN IF NOT EXISTS source_action_event_type TEXT,
  ADD COLUMN IF NOT EXISTS action_state TEXT,
  ADD COLUMN IF NOT EXISTS action_mark TEXT,
  ADD COLUMN IF NOT EXISTS condition_key TEXT,
  ADD COLUMN IF NOT EXISTS original_condition_key TEXT,
  ADD COLUMN IF NOT EXISTS trace_json JSONB,
  ADD COLUMN IF NOT EXISTS projection_policy TEXT;

ALTER TABLE user_notification_queue
  ADD COLUMN IF NOT EXISTS source_action_event_id TEXT,
  ADD COLUMN IF NOT EXISTS source_action_event_type TEXT,
  ADD COLUMN IF NOT EXISTS action_state TEXT,
  ADD COLUMN IF NOT EXISTS action_mark TEXT,
  ADD COLUMN IF NOT EXISTS condition_key TEXT,
  ADD COLUMN IF NOT EXISTS original_condition_key TEXT,
  ADD COLUMN IF NOT EXISTS trace_json JSONB,
  ADD COLUMN IF NOT EXISTS projection_policy TEXT;

DO $$
DECLARE
  v_constraint RECORD;
BEGIN
  FOR v_constraint IN
    SELECT c.conname
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
     WHERE n.nspname = 'public'
       AND t.relname = 'user_projection_run'
       AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) LIKE '%source_event_types%'
  LOOP
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', 'user_projection_run', v_constraint.conname);
  END LOOP;

  FOR v_constraint IN
    SELECT c.conname
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
     WHERE n.nspname = 'public'
       AND t.relname = 'user_signal_projection'
       AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) LIKE '%source_event_type%'
       AND pg_get_constraintdef(c.oid) LIKE '%ActionEvent%'
  LOOP
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', 'user_signal_projection', v_constraint.conname);
  END LOOP;

  FOR v_constraint IN
    SELECT c.conname
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
     WHERE n.nspname = 'public'
       AND t.relname = 'user_signal_card'
       AND c.contype = 'c'
       AND (
         pg_get_constraintdef(c.oid) LIKE '%card_type%'
         OR pg_get_constraintdef(c.oid) LIKE '%card_status%'
       )
  LOOP
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', 'user_signal_card', v_constraint.conname);
  END LOOP;

  FOR v_constraint IN
    SELECT c.conname
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
     WHERE n.nspname = 'public'
       AND t.relname = 'user_notification_queue'
       AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) LIKE '%notification_source%'
  LOOP
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', 'user_notification_queue', v_constraint.conname);
  END LOOP;
END $$;

ALTER TABLE user_projection_run
  DROP CONSTRAINT IF EXISTS chk_user_projection_run_source_event_types_n6_canonical_compat;

ALTER TABLE user_projection_run
  ADD CONSTRAINT chk_user_projection_run_source_event_types_n6_canonical_compat
  CHECK (source_event_types <@ ARRAY[
    'ActionEvent',
    'HintEvent',
    'ActionEligible',
    'ActionBlocked',
    'ActionExecuted',
    'ActionSkipped'
  ]::TEXT[]) NOT VALID;

ALTER TABLE user_signal_projection
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_source_event_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_source_action_event_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_action_state_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_action_mark_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_trace_json_object,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_projection_policy_nonempty;

ALTER TABLE user_signal_projection
  ADD CONSTRAINT chk_user_signal_projection_source_event_type_n6_canonical_compat
  CHECK (source_event_type IN ('ActionEvent', 'HintEvent', 'ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_projection_source_action_event_type_n6_canonical_compat
  CHECK (source_action_event_type IS NULL OR source_action_event_type IN ('ActionEvent', 'HintEvent', 'ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_projection_action_state_n6_canonical
  CHECK (action_state IS NULL OR action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_projection_action_mark_n6_canonical
  CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_projection_trace_json_object
  CHECK (trace_json IS NULL OR jsonb_typeof(trace_json) = 'object') NOT VALID,
  ADD CONSTRAINT chk_user_signal_projection_projection_policy_nonempty
  CHECK (projection_policy IS NULL OR btrim(projection_policy) <> '') NOT VALID;

ALTER TABLE user_signal_card
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_card_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_card_status_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_source_action_event_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_action_state_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_action_mark_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_trace_json_object,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_projection_policy_nonempty;

ALTER TABLE user_signal_card
  ADD CONSTRAINT chk_user_signal_card_card_type_n6_canonical_compat
  CHECK (card_type IN ('signal', 'hint', 'buy_candidate', 'sell_candidate', 'blocked', 'action_confirmed', 'skipped', 'informational')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_card_card_status_n6_canonical_compat
  CHECK (card_status IN ('active', 'hidden', 'acknowledged', 'discarded', 'blocked', 'candidate', 'action_confirmed', 'skipped', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_card_source_action_event_type_n6_canonical_compat
  CHECK (source_action_event_type IS NULL OR source_action_event_type IN ('ActionEvent', 'HintEvent', 'ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_card_action_state_n6_canonical
  CHECK (action_state IS NULL OR action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_card_action_mark_n6_canonical
  CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_card_trace_json_object
  CHECK (trace_json IS NULL OR jsonb_typeof(trace_json) = 'object') NOT VALID,
  ADD CONSTRAINT chk_user_signal_card_projection_policy_nonempty
  CHECK (projection_policy IS NULL OR btrim(projection_policy) <> '') NOT VALID;

ALTER TABLE user_notification_queue
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_notification_source_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_source_action_event_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_action_state_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_action_mark_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_trace_json_object,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_projection_policy_nonempty;

ALTER TABLE user_notification_queue
  ADD CONSTRAINT chk_user_notification_queue_notification_source_n6_canonical_compat
  CHECK (notification_source IN ('index_signal', 'board_signal', 'stock_filter_signal', 'n5_action_event', 'n5_hint_event', 'n5_action_eligible', 'n5_action_blocked', 'n5_action_executed', 'n5_action_skipped')) NOT VALID,
  ADD CONSTRAINT chk_user_notification_queue_source_action_event_type_n6_canonical_compat
  CHECK (source_action_event_type IS NULL OR source_action_event_type IN ('ActionEvent', 'HintEvent', 'ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped')) NOT VALID,
  ADD CONSTRAINT chk_user_notification_queue_action_state_n6_canonical
  CHECK (action_state IS NULL OR action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_user_notification_queue_action_mark_n6_canonical
  CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_user_notification_queue_trace_json_object
  CHECK (trace_json IS NULL OR jsonb_typeof(trace_json) = 'object') NOT VALID,
  ADD CONSTRAINT chk_user_notification_queue_projection_policy_nonempty
  CHECK (projection_policy IS NULL OR btrim(projection_policy) <> '') NOT VALID;

CREATE INDEX IF NOT EXISTS idx_user_signal_projection_canonical_action
ON user_signal_projection(source_action_run_id, source_action_event_type, action_state);

CREATE INDEX IF NOT EXISTS idx_user_signal_card_canonical_action
ON user_signal_card(source_action_run_id, source_action_event_type, action_state);

CREATE INDEX IF NOT EXISTS idx_user_notification_queue_canonical_action
ON user_notification_queue(source_action_run_id, source_action_event_type, action_state, queue_status);

COMMIT;
