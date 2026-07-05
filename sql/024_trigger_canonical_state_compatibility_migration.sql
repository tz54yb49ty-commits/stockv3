-- A-share monitor v3 N4 canonical trigger state compatibility draft.
-- Stage: N4 canonical TriggerStateChanged schema migration draft.
-- Boundary: schema compatibility only; execute in a later final gate.

BEGIN;

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
      AND t.relname = 'common_trigger_state'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%condition_key%'
      AND pg_get_constraintdef(c.oid) LIKE '%signal_type%'
      AND (
        pg_get_constraintdef(c.oid) LIKE '%BUY_HINT%'
        OR pg_get_constraintdef(c.oid) LIKE '%SELL_HINT%'
      )
  LOOP
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', 'common_trigger_state', v_constraint.conname);
  END LOOP;

  FOR v_constraint IN
    SELECT c.conname
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname = 'common_trigger_match'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%condition_key%'
      AND pg_get_constraintdef(c.oid) LIKE '%signal_type%'
      AND (
        pg_get_constraintdef(c.oid) LIKE '%BUY_HINT%'
        OR pg_get_constraintdef(c.oid) LIKE '%SELL_HINT%'
      )
  LOOP
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', 'common_trigger_match', v_constraint.conname);
  END LOOP;
END $$;

ALTER TABLE common_trigger_state
  ADD COLUMN IF NOT EXISTS trigger_live BOOLEAN,
  ADD COLUMN IF NOT EXISTS trigger_mark_candidate TEXT,
  ADD COLUMN IF NOT EXISTS primary_trigger_period TEXT,
  ADD COLUMN IF NOT EXISTS all_trigger_periods JSONB,
  ADD COLUMN IF NOT EXISTS projection_30m_flag BOOLEAN,
  ADD COLUMN IF NOT EXISTS projection_30m_type TEXT;

ALTER TABLE common_trigger_match
  ADD COLUMN IF NOT EXISTS trigger_mark_candidate TEXT;

ALTER TABLE common_trigger_state
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_buy_hint_signal_compat,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_sell_hint_signal_compat,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_trigger_mark_candidate,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_primary_trigger_period,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_projection_30m_type;

ALTER TABLE common_trigger_state
  ADD CONSTRAINT chk_common_trigger_state_buy_hint_signal_compat
  CHECK (condition_key <> 'BUY_HINT' OR signal_type IN ('B_BUY', 'BUY_HINT')),
  ADD CONSTRAINT chk_common_trigger_state_sell_hint_signal_compat
  CHECK (condition_key <> 'SELL_HINT' OR signal_type IN ('S_SELL', 'SELL_HINT')),
  ADD CONSTRAINT chk_common_trigger_state_trigger_mark_candidate
  CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink')),
  ADD CONSTRAINT chk_common_trigger_state_primary_trigger_period
  CHECK (primary_trigger_period IS NULL OR primary_trigger_period IN ('Y', 'Q', 'M', 'W', 'D', '30m')),
  ADD CONSTRAINT chk_common_trigger_state_projection_30m_type
  CHECK (projection_30m_type IS NULL OR projection_30m_type IN ('none', 'volume_up', 'shrink_down'));

ALTER TABLE common_trigger_match
  DROP CONSTRAINT IF EXISTS chk_common_trigger_match_buy_hint_signal_compat,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_match_sell_hint_signal_compat,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_match_trigger_mark_candidate;

ALTER TABLE common_trigger_match
  ADD CONSTRAINT chk_common_trigger_match_buy_hint_signal_compat
  CHECK (condition_key <> 'BUY_HINT' OR signal_type IN ('B_BUY', 'BUY_HINT')),
  ADD CONSTRAINT chk_common_trigger_match_sell_hint_signal_compat
  CHECK (condition_key <> 'SELL_HINT' OR signal_type IN ('S_SELL', 'SELL_HINT')),
  ADD CONSTRAINT chk_common_trigger_match_trigger_mark_candidate
  CHECK (trigger_mark_candidate IS NULL OR trigger_mark_candidate IN ('normal', '30m_volume', '30m_shrink'));

COMMIT;
