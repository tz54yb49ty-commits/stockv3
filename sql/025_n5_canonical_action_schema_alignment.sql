-- A-share monitor v3 N5 canonical action schema alignment draft.
-- Stage: N5 canonical action schema compatibility.
-- Boundary: schema draft only; run only after a separate final gate.

BEGIN;

ALTER TABLE stock_action_fact
  ADD COLUMN IF NOT EXISTS source_trigger_state_id BIGINT,
  ADD COLUMN IF NOT EXISTS original_condition_key TEXT,
  ADD COLUMN IF NOT EXISTS trigger_mark_candidate TEXT,
  ADD COLUMN IF NOT EXISTS action_mark TEXT,
  ADD COLUMN IF NOT EXISTS action_state TEXT,
  ADD COLUMN IF NOT EXISTS confirmation_status TEXT,
  ADD COLUMN IF NOT EXISTS tracking_until TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_checked_minute_label TEXT,
  ADD COLUMN IF NOT EXISTS trace_json JSONB,
  ADD COLUMN IF NOT EXISTS action_policy TEXT;

ALTER TABLE index_action_fact
  ADD COLUMN IF NOT EXISTS source_trigger_state_id BIGINT,
  ADD COLUMN IF NOT EXISTS original_condition_key TEXT,
  ADD COLUMN IF NOT EXISTS trigger_mark_candidate TEXT,
  ADD COLUMN IF NOT EXISTS action_mark TEXT,
  ADD COLUMN IF NOT EXISTS action_state TEXT,
  ADD COLUMN IF NOT EXISTS confirmation_status TEXT,
  ADD COLUMN IF NOT EXISTS tracking_until TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_checked_minute_label TEXT,
  ADD COLUMN IF NOT EXISTS trace_json JSONB,
  ADD COLUMN IF NOT EXISTS action_policy TEXT;

ALTER TABLE board_action_fact
  ADD COLUMN IF NOT EXISTS source_trigger_state_id BIGINT,
  ADD COLUMN IF NOT EXISTS original_condition_key TEXT,
  ADD COLUMN IF NOT EXISTS trigger_mark_candidate TEXT,
  ADD COLUMN IF NOT EXISTS action_mark TEXT,
  ADD COLUMN IF NOT EXISTS action_state TEXT,
  ADD COLUMN IF NOT EXISTS confirmation_status TEXT,
  ADD COLUMN IF NOT EXISTS tracking_until TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_checked_minute_label TEXT,
  ADD COLUMN IF NOT EXISTS trace_json JSONB,
  ADD COLUMN IF NOT EXISTS action_policy TEXT;

ALTER TABLE common_action_event
  ADD COLUMN IF NOT EXISTS source_trigger_state_id BIGINT,
  ADD COLUMN IF NOT EXISTS original_condition_key TEXT,
  ADD COLUMN IF NOT EXISTS trigger_mark_candidate TEXT,
  ADD COLUMN IF NOT EXISTS action_mark TEXT,
  ADD COLUMN IF NOT EXISTS action_state TEXT,
  ADD COLUMN IF NOT EXISTS confirmation_status TEXT,
  ADD COLUMN IF NOT EXISTS tracking_until TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_checked_minute_label TEXT,
  ADD COLUMN IF NOT EXISTS trace_json JSONB,
  ADD COLUMN IF NOT EXISTS action_policy TEXT;

DO $$
DECLARE
  v_table TEXT;
  v_constraint RECORD;
BEGIN
  FOREACH v_table IN ARRAY ARRAY['stock_action_fact', 'index_action_fact', 'board_action_fact']
  LOOP
    FOR v_constraint IN
      SELECT c.conname
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
      JOIN pg_namespace n ON n.oid = t.relnamespace
      WHERE n.nspname = 'public'
        AND t.relname = v_table
        AND c.contype = 'c'
        AND (
          pg_get_constraintdef(c.oid) LIKE '%source_trigger_event_type%'
          OR pg_get_constraintdef(c.oid) LIKE '%decision_status%'
        )
    LOOP
      EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', v_table, v_constraint.conname);
    END LOOP;
  END LOOP;

  FOR v_constraint IN
    SELECT c.conname
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = 'common_action_event'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%event_type%'
      AND pg_get_constraintdef(c.oid) LIKE '%ActionEvent%'
  LOOP
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', 'common_action_event', v_constraint.conname);
  END LOOP;
END $$;

ALTER TABLE stock_action_fact
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_source_trigger_event_type_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_decision_status_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_signal_type_n5_legacy_compat,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_action_state_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_confirmation_status_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_action_mark_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_trigger_mark_candidate_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_stock_action_fact_trace_json_object;

ALTER TABLE stock_action_fact
  ADD CONSTRAINT chk_stock_action_fact_source_trigger_event_type_n5_canonical_compat
  CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged', 'TriggerCleared')) NOT VALID,
  ADD CONSTRAINT chk_stock_action_fact_decision_status_n5_canonical_compat
  CHECK (decision_status IN ('candidate', 'policy_pending', 'pending_market_data', 'blocked_quality', 'skipped', 'quality_only', 'state_gate', 'blocked_unclosed', 'blocked_missing', 'confirmation_failed', 'confirmation_passed', 'pending_confirmation', 'deprecated_runtime_signal_type', 'unsupported_runtime_signal_type', 'eligible', 'blocked', 'executed', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_stock_action_fact_signal_type_n5_legacy_compat
  CHECK (signal_type IN ('B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT')) NOT VALID,
  ADD CONSTRAINT chk_stock_action_fact_action_state_n5_canonical
  CHECK (action_state IS NULL OR action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_stock_action_fact_confirmation_status_n5_canonical
  CHECK (confirmation_status IS NULL OR confirmation_status IN ('pending', 'passed', 'failed', 'expired', 'quality_only', 'state_gate', 'blocked_unclosed', 'confirmation_failed', 'pending_confirmation')) NOT VALID,
  ADD CONSTRAINT chk_stock_action_fact_action_mark_n5_canonical
  CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_stock_action_fact_trigger_mark_candidate_n5_canonical
  CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_stock_action_fact_trace_json_object
  CHECK (trace_json IS NULL OR jsonb_typeof(trace_json) = 'object') NOT VALID;

ALTER TABLE index_action_fact
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_source_trigger_event_type_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_decision_status_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_signal_type_n5_legacy_compat,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_action_state_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_confirmation_status_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_action_mark_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_trigger_mark_candidate_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_index_action_fact_trace_json_object;

ALTER TABLE index_action_fact
  ADD CONSTRAINT chk_index_action_fact_source_trigger_event_type_n5_canonical_compat
  CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged', 'TriggerCleared')) NOT VALID,
  ADD CONSTRAINT chk_index_action_fact_decision_status_n5_canonical_compat
  CHECK (decision_status IN ('candidate', 'policy_pending', 'pending_market_data', 'blocked_quality', 'skipped', 'quality_only', 'state_gate', 'blocked_unclosed', 'blocked_missing', 'confirmation_failed', 'confirmation_passed', 'pending_confirmation', 'deprecated_runtime_signal_type', 'unsupported_runtime_signal_type', 'eligible', 'blocked', 'executed', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_index_action_fact_signal_type_n5_legacy_compat
  CHECK (signal_type IN ('B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT')) NOT VALID,
  ADD CONSTRAINT chk_index_action_fact_action_state_n5_canonical
  CHECK (action_state IS NULL OR action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_index_action_fact_confirmation_status_n5_canonical
  CHECK (confirmation_status IS NULL OR confirmation_status IN ('pending', 'passed', 'failed', 'expired', 'quality_only', 'state_gate', 'blocked_unclosed', 'confirmation_failed', 'pending_confirmation')) NOT VALID,
  ADD CONSTRAINT chk_index_action_fact_action_mark_n5_canonical
  CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_index_action_fact_trigger_mark_candidate_n5_canonical
  CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_index_action_fact_trace_json_object
  CHECK (trace_json IS NULL OR jsonb_typeof(trace_json) = 'object') NOT VALID;

ALTER TABLE board_action_fact
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_source_trigger_event_type_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_decision_status_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_signal_type_n5_legacy_compat,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_action_state_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_confirmation_status_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_action_mark_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_trigger_mark_candidate_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_board_action_fact_trace_json_object;

ALTER TABLE board_action_fact
  ADD CONSTRAINT chk_board_action_fact_source_trigger_event_type_n5_canonical_compat
  CHECK (source_trigger_event_type IN ('TriggerMatched', 'TriggerPendingMarketData', 'TriggerStateChanged', 'TriggerCleared')) NOT VALID,
  ADD CONSTRAINT chk_board_action_fact_decision_status_n5_canonical_compat
  CHECK (decision_status IN ('candidate', 'policy_pending', 'pending_market_data', 'blocked_quality', 'skipped', 'quality_only', 'state_gate', 'blocked_unclosed', 'blocked_missing', 'confirmation_failed', 'confirmation_passed', 'pending_confirmation', 'deprecated_runtime_signal_type', 'unsupported_runtime_signal_type', 'eligible', 'blocked', 'executed', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_board_action_fact_signal_type_n5_legacy_compat
  CHECK (signal_type IN ('B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT')) NOT VALID,
  ADD CONSTRAINT chk_board_action_fact_action_state_n5_canonical
  CHECK (action_state IS NULL OR action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_board_action_fact_confirmation_status_n5_canonical
  CHECK (confirmation_status IS NULL OR confirmation_status IN ('pending', 'passed', 'failed', 'expired', 'quality_only', 'state_gate', 'blocked_unclosed', 'confirmation_failed', 'pending_confirmation')) NOT VALID,
  ADD CONSTRAINT chk_board_action_fact_action_mark_n5_canonical
  CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_board_action_fact_trigger_mark_candidate_n5_canonical
  CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_board_action_fact_trace_json_object
  CHECK (trace_json IS NULL OR jsonb_typeof(trace_json) = 'object') NOT VALID;

ALTER TABLE common_action_event
  DROP CONSTRAINT IF EXISTS chk_common_action_event_event_type_n5_canonical_compat,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_action_state_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_confirmation_status_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_action_mark_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_trigger_mark_candidate_n5_canonical,
  DROP CONSTRAINT IF EXISTS chk_common_action_event_trace_json_object;

ALTER TABLE common_action_event
  ADD CONSTRAINT chk_common_action_event_event_type_n5_canonical_compat
  CHECK (event_type IN ('ActionEvent', 'HintEvent', 'RiskEvent', 'PositionEvent', 'ActionEligible', 'ActionBlocked', 'ActionExecuted', 'ActionSkipped')) NOT VALID,
  ADD CONSTRAINT chk_common_action_event_action_state_n5_canonical
  CHECK (action_state IS NULL OR action_state IN ('eligible', 'blocked', 'executed', 'skipped', 'expired')) NOT VALID,
  ADD CONSTRAINT chk_common_action_event_confirmation_status_n5_canonical
  CHECK (confirmation_status IS NULL OR confirmation_status IN ('pending', 'passed', 'failed', 'expired', 'quality_only', 'state_gate', 'blocked_unclosed', 'confirmation_failed', 'pending_confirmation')) NOT VALID,
  ADD CONSTRAINT chk_common_action_event_action_mark_n5_canonical
  CHECK (action_mark IS NULL OR action_mark IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_common_action_event_trigger_mark_candidate_n5_canonical
  CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink')) NOT VALID,
  ADD CONSTRAINT chk_common_action_event_trace_json_object
  CHECK (trace_json IS NULL OR jsonb_typeof(trace_json) = 'object') NOT VALID;

CREATE INDEX IF NOT EXISTS idx_stock_action_fact_canonical_state
ON stock_action_fact(run_id, action_state, action_mark);

CREATE INDEX IF NOT EXISTS idx_index_action_fact_canonical_state
ON index_action_fact(run_id, action_state, action_mark);

CREATE INDEX IF NOT EXISTS idx_board_action_fact_canonical_state
ON board_action_fact(run_id, action_state, action_mark);

CREATE INDEX IF NOT EXISTS idx_common_action_event_canonical_state
ON common_action_event(run_id, event_type, action_state, created_at);

COMMIT;
