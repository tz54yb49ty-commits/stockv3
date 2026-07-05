-- A-share monitor v3 N6 canonical user projection schema alignment rollback draft.
-- Scope: schema rollback only; use after guards pass and before any final gate.
--
-- If canonical N6 projection business rows exist, first run the reviewed N6
-- business rollback by user_projection_run_id. This schema rollback does not
-- delete projection/card/notification rows and does not touch N5 outbox rows.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
    FROM user_projection_run
   WHERE source_event_types && ARRAY['ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped']::TEXT[];
  IF v_count <> 0 THEN
    RAISE EXCEPTION '026 rollback blocked: canonical user_projection_run source_event_types exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_signal_projection
   WHERE source_event_type IN ('ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped')
      OR source_action_event_type IS NOT NULL
      OR action_state IS NOT NULL
      OR action_mark IS NOT NULL
      OR condition_key IS NOT NULL
      OR original_condition_key IS NOT NULL
      OR trace_json IS NOT NULL
      OR projection_policy IS NOT NULL;
  IF v_count <> 0 THEN
    RAISE EXCEPTION '026 rollback blocked: canonical user_signal_projection values exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_signal_card
   WHERE source_action_event_id IS NOT NULL
      OR source_action_event_type IS NOT NULL
      OR action_state IS NOT NULL
      OR action_mark IS NOT NULL
      OR condition_key IS NOT NULL
      OR original_condition_key IS NOT NULL
      OR trace_json IS NOT NULL
      OR projection_policy IS NOT NULL
      OR card_type IN ('blocked', 'action_confirmed', 'skipped', 'informational')
      OR card_status IN ('candidate', 'action_confirmed', 'skipped', 'expired');
  IF v_count <> 0 THEN
    RAISE EXCEPTION '026 rollback blocked: canonical user_signal_card values exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
    FROM user_notification_queue
   WHERE source_action_event_id IS NOT NULL
      OR source_action_event_type IS NOT NULL
      OR action_state IS NOT NULL
      OR action_mark IS NOT NULL
      OR condition_key IS NOT NULL
      OR original_condition_key IS NOT NULL
      OR trace_json IS NOT NULL
      OR projection_policy IS NOT NULL
      OR notification_source IN ('n5_action_eligible', 'n5_action_blocked', 'n5_action_executed', 'n5_action_skipped');
  IF v_count <> 0 THEN
    RAISE EXCEPTION '026 rollback blocked: canonical user_notification_queue values exist: %', v_count;
  END IF;
END $$;

DROP INDEX IF EXISTS idx_user_notification_queue_canonical_action;
DROP INDEX IF EXISTS idx_user_signal_card_canonical_action;
DROP INDEX IF EXISTS idx_user_signal_projection_canonical_action;

ALTER TABLE user_projection_run
  DROP CONSTRAINT IF EXISTS chk_user_projection_run_source_event_types_n6_canonical_compat,
  ADD CONSTRAINT chk_user_projection_run_source_event_types_legacy
  CHECK (source_event_types <@ ARRAY['ActionEvent', 'HintEvent']::TEXT[]) NOT VALID;

ALTER TABLE user_projection_run
  ALTER COLUMN source_event_types SET DEFAULT ARRAY['ActionEvent', 'HintEvent']::TEXT[];

ALTER TABLE user_signal_projection
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_source_event_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_source_action_event_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_action_state_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_action_mark_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_trace_json_object,
  DROP CONSTRAINT IF EXISTS chk_user_signal_projection_projection_policy_nonempty,
  ADD CONSTRAINT chk_user_signal_projection_source_event_type_legacy
  CHECK (source_event_type IN ('ActionEvent', 'HintEvent')) NOT VALID;

ALTER TABLE user_signal_card
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_card_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_card_status_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_source_action_event_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_action_state_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_action_mark_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_trace_json_object,
  DROP CONSTRAINT IF EXISTS chk_user_signal_card_projection_policy_nonempty,
  ADD CONSTRAINT chk_user_signal_card_card_type_legacy
  CHECK (card_type IN ('signal', 'hint', 'buy_candidate', 'sell_candidate')) NOT VALID,
  ADD CONSTRAINT chk_user_signal_card_card_status_legacy
  CHECK (card_status IN ('active', 'hidden', 'acknowledged', 'discarded', 'blocked')) NOT VALID;

ALTER TABLE user_notification_queue
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_notification_source_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_source_action_event_type_n6_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_action_state_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_action_mark_n6_canonical,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_trace_json_object,
  DROP CONSTRAINT IF EXISTS chk_user_notification_queue_projection_policy_nonempty,
  ADD CONSTRAINT chk_user_notification_queue_notification_source_legacy
  CHECK (notification_source IN ('index_signal', 'board_signal', 'stock_filter_signal', 'n5_action_event', 'n5_hint_event')) NOT VALID;

ALTER TABLE user_signal_projection
  DROP COLUMN IF EXISTS source_action_event_type,
  DROP COLUMN IF EXISTS action_state,
  DROP COLUMN IF EXISTS action_mark,
  DROP COLUMN IF EXISTS condition_key,
  DROP COLUMN IF EXISTS original_condition_key,
  DROP COLUMN IF EXISTS trace_json,
  DROP COLUMN IF EXISTS projection_policy;

ALTER TABLE user_signal_card
  DROP COLUMN IF EXISTS source_action_event_id,
  DROP COLUMN IF EXISTS source_action_event_type,
  DROP COLUMN IF EXISTS action_state,
  DROP COLUMN IF EXISTS action_mark,
  DROP COLUMN IF EXISTS condition_key,
  DROP COLUMN IF EXISTS original_condition_key,
  DROP COLUMN IF EXISTS trace_json,
  DROP COLUMN IF EXISTS projection_policy;

ALTER TABLE user_notification_queue
  DROP COLUMN IF EXISTS source_action_event_id,
  DROP COLUMN IF EXISTS source_action_event_type,
  DROP COLUMN IF EXISTS action_state,
  DROP COLUMN IF EXISTS action_mark,
  DROP COLUMN IF EXISTS condition_key,
  DROP COLUMN IF EXISTS original_condition_key,
  DROP COLUMN IF EXISTS trace_json,
  DROP COLUMN IF EXISTS projection_policy;

COMMIT;
