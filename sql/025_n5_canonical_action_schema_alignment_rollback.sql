-- A-share monitor v3 N5 canonical action schema alignment rollback draft.
-- Scope: schema rollback only; use after guards pass and before any final gate.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_action_event
  WHERE event_type IN ('ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped');
  IF v_count <> 0 THEN
    RAISE EXCEPTION '025 rollback blocked: canonical common_action_event rows exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM stock_action_fact
  WHERE source_trigger_event_type = 'TriggerStateChanged'
     OR decision_status IN ('quality_only', 'state_gate', 'blocked_unclosed', 'blocked_missing', 'confirmation_failed', 'confirmation_passed', 'pending_confirmation', 'deprecated_runtime_signal_type', 'unsupported_runtime_signal_type', 'eligible', 'blocked', 'executed', 'expired')
     OR source_trigger_state_id IS NOT NULL
     OR original_condition_key IS NOT NULL
     OR trigger_mark_candidate IS NOT NULL
     OR action_mark IS NOT NULL
     OR action_state IS NOT NULL
     OR confirmation_status IS NOT NULL
     OR tracking_until IS NOT NULL
     OR last_checked_minute_label IS NOT NULL
     OR trace_json IS NOT NULL
     OR action_policy IS NOT NULL;
  IF v_count <> 0 THEN
    RAISE EXCEPTION '025 rollback blocked: canonical stock_action_fact values exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM index_action_fact
  WHERE source_trigger_event_type = 'TriggerStateChanged'
     OR decision_status IN ('quality_only', 'state_gate', 'blocked_unclosed', 'blocked_missing', 'confirmation_failed', 'confirmation_passed', 'pending_confirmation', 'deprecated_runtime_signal_type', 'unsupported_runtime_signal_type', 'eligible', 'blocked', 'executed', 'expired')
     OR source_trigger_state_id IS NOT NULL
     OR original_condition_key IS NOT NULL
     OR trigger_mark_candidate IS NOT NULL
     OR action_mark IS NOT NULL
     OR action_state IS NOT NULL
     OR confirmation_status IS NOT NULL
     OR tracking_until IS NOT NULL
     OR last_checked_minute_label IS NOT NULL
     OR trace_json IS NOT NULL
     OR action_policy IS NOT NULL;
  IF v_count <> 0 THEN
    RAISE EXCEPTION '025 rollback blocked: canonical index_action_fact values exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM board_action_fact
  WHERE source_trigger_event_type = 'TriggerStateChanged'
     OR decision_status IN ('quality_only', 'state_gate', 'blocked_unclosed', 'blocked_missing', 'confirmation_failed', 'confirmation_passed', 'pending_confirmation', 'deprecated_runtime_signal_type', 'unsupported_runtime_signal_type', 'eligible', 'blocked', 'executed', 'expired')
     OR source_trigger_state_id IS NOT NULL
     OR original_condition_key IS NOT NULL
     OR trigger_mark_candidate IS NOT NULL
     OR action_mark IS NOT NULL
     OR action_state IS NOT NULL
     OR confirmation_status IS NOT NULL
     OR tracking_until IS NOT NULL
     OR last_checked_minute_label IS NOT NULL
     OR trace_json IS NOT NULL
     OR action_policy IS NOT NULL;
  IF v_count <> 0 THEN
    RAISE EXCEPTION '025 rollback blocked: canonical board_action_fact values exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_action_event
  WHERE source_trigger_state_id IS NOT NULL
     OR original_condition_key IS NOT NULL
     OR trigger_mark_candidate IS NOT NULL
     OR action_mark IS NOT NULL
     OR action_state IS NOT NULL
     OR confirmation_status IS NOT NULL
     OR tracking_until IS NOT NULL
     OR last_checked_minute_label IS NOT NULL
     OR trace_json IS NOT NULL
     OR action_policy IS NOT NULL;
  IF v_count <> 0 THEN
    RAISE EXCEPTION '025 rollback blocked: canonical common_action_event values exist: %', v_count;
  END IF;
END $$;

DROP INDEX IF EXISTS idx_common_action_event_canonical_state;
DROP INDEX IF EXISTS idx_board_action_fact_canonical_state;
DROP INDEX IF EXISTS idx_index_action_fact_canonical_state;
DROP INDEX IF EXISTS idx_stock_action_fact_canonical_state;

ALTER TABLE stock_action_fact
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_source_trigger_event_type_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_decision_status_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_signal_type_n5_legacy_compat,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_action_state_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_confirmation_status_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_action_mark_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_trigger_mark_candidate_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_trace_json_object,
  ADD CONSTRAINT chk_stock_action_fact_source_trigger_event_type_legacy
  CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerCleared', 'TriggerPendingMarketData')),
  ADD CONSTRAINT chk_stock_action_fact_decision_status_legacy
  CHECK (decision_status IN ('candidate', 'policy_pending', 'pending_market_data', 'blocked_quality', 'skipped'));

ALTER TABLE index_action_fact
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_source_trigger_event_type_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_decision_status_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_signal_type_n5_legacy_compat,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_action_state_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_confirmation_status_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_action_mark_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_trigger_mark_candidate_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_trace_json_object,
  ADD CONSTRAINT chk_index_action_fact_source_trigger_event_type_legacy
  CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerCleared', 'TriggerPendingMarketData')),
  ADD CONSTRAINT chk_index_action_fact_decision_status_legacy
  CHECK (decision_status IN ('candidate', 'policy_pending', 'pending_market_data', 'blocked_quality', 'skipped'));

ALTER TABLE board_action_fact
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_source_trigger_event_type_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_decision_status_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_signal_type_n5_legacy_compat,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_action_state_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_confirmation_status_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_action_mark_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_trigger_mark_candidate_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_trace_json_object,
  ADD CONSTRAINT chk_board_action_fact_source_trigger_event_type_legacy
  CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerCleared', 'TriggerPendingMarketData')),
  ADD CONSTRAINT chk_board_action_fact_decision_status_legacy
  CHECK (decision_status IN ('candidate', 'policy_pending', 'pending_market_data', 'blocked_quality', 'skipped'));

ALTER TABLE common_action_event
  DROP CONSTRAINT IF EXISTS chk_common_action_event_event_type_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_action_state_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_confirmation_status_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_action_mark_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_trigger_mark_candidate_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_trace_json_object,
  ADD CONSTRAINT chk_common_action_event_event_type_legacy
  CHECK (event_type IN ('ActionEvent', 'HintEvent', 'RiskEvent', 'PositionEvent'));

ALTER TABLE stock_action_fact
  DROP COLUMN IF EXISTS source_trigger_state_id,
  DROP COLUMN IF EXISTS original_condition_key,
  DROP COLUMN IF EXISTS trigger_mark_candidate,
  DROP COLUMN IF EXISTS action_mark,
  DROP COLUMN IF EXISTS action_state,
  DROP COLUMN IF EXISTS confirmation_status,
  DROP COLUMN IF EXISTS tracking_until,
  DROP COLUMN IF EXISTS last_checked_minute_label,
  DROP COLUMN IF EXISTS trace_json,
  DROP COLUMN IF EXISTS action_policy;

ALTER TABLE index_action_fact
  DROP COLUMN IF EXISTS source_trigger_state_id,
  DROP COLUMN IF EXISTS original_condition_key,
  DROP COLUMN IF EXISTS trigger_mark_candidate,
  DROP COLUMN IF EXISTS action_mark,
  DROP COLUMN IF EXISTS action_state,
  DROP COLUMN IF EXISTS confirmation_status,
  DROP COLUMN IF EXISTS tracking_until,
  DROP COLUMN IF EXISTS last_checked_minute_label,
  DROP COLUMN IF EXISTS trace_json,
  DROP COLUMN IF EXISTS action_policy;

ALTER TABLE board_action_fact
  DROP COLUMN IF EXISTS source_trigger_state_id,
  DROP COLUMN IF EXISTS original_condition_key,
  DROP COLUMN IF EXISTS trigger_mark_candidate,
  DROP COLUMN IF EXISTS action_mark,
  DROP COLUMN IF EXISTS action_state,
  DROP COLUMN IF EXISTS confirmation_status,
  DROP COLUMN IF EXISTS tracking_until,
  DROP COLUMN IF EXISTS last_checked_minute_label,
  DROP COLUMN IF EXISTS trace_json,
  DROP COLUMN IF EXISTS action_policy;

ALTER TABLE common_action_event
  DROP COLUMN IF EXISTS source_trigger_state_id,
  DROP COLUMN IF EXISTS original_condition_key,
  DROP COLUMN IF EXISTS trigger_mark_candidate,
  DROP COLUMN IF EXISTS action_mark,
  DROP COLUMN IF EXISTS action_state,
  DROP COLUMN IF EXISTS confirmation_status,
  DROP COLUMN IF EXISTS tracking_until,
  DROP COLUMN IF EXISTS last_checked_minute_label,
  DROP COLUMN IF EXISTS trace_json,
  DROP COLUMN IF EXISTS action_policy;

COMMIT;
