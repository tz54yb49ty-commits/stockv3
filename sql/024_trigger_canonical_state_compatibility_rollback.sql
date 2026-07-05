-- A-share monitor v3 N4 canonical trigger state compatibility rollback draft.
-- Scope: schema compatibility rollback only; run only after scoped guards pass.

BEGIN;

DO $$
DECLARE
  v_count BIGINT;
BEGIN
  SELECT count(*) INTO v_count
  FROM common_trigger_state
  WHERE (condition_key = 'BUY_HINT' AND signal_type = 'B_BUY')
     OR (condition_key = 'SELL_HINT' AND signal_type = 'S_SELL');
  IF v_count <> 0 THEN
    RAISE EXCEPTION '024 rollback blocked: canonical HINT rows exist in common_trigger_state: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_match
  WHERE (condition_key = 'BUY_HINT' AND signal_type = 'B_BUY')
     OR (condition_key = 'SELL_HINT' AND signal_type = 'S_SELL');
  IF v_count <> 0 THEN
    RAISE EXCEPTION '024 rollback blocked: canonical HINT rows exist in common_trigger_match: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_state
  WHERE trigger_live IS NOT NULL
     OR trigger_mark_candidate IS NOT NULL
     OR primary_trigger_period IS NOT NULL
     OR all_trigger_periods IS NOT NULL
     OR projection_30m_flag IS NOT NULL
     OR projection_30m_type IS NOT NULL;
  IF v_count <> 0 THEN
    RAISE EXCEPTION '024 rollback blocked: additive common_trigger_state values exist: %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_trigger_match
  WHERE trigger_mark_candidate IS NOT NULL;
  IF v_count <> 0 THEN
    RAISE EXCEPTION '024 rollback blocked: additive common_trigger_match values exist: %', v_count;
  END IF;
END $$;

ALTER TABLE common_trigger_state
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_buy_hint_signal_compat,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_sell_hint_signal_compat,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_trigger_mark_candidate,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_primary_trigger_period,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_projection_30m_type,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_buy_hint_signal_legacy,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_state_sell_hint_signal_legacy;

ALTER TABLE common_trigger_match
  DROP CONSTRAINT IF EXISTS chk_common_trigger_match_buy_hint_signal_compat,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_match_sell_hint_signal_compat,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_match_trigger_mark_candidate,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_match_buy_hint_signal_legacy,
  DROP CONSTRAINT IF EXISTS chk_common_trigger_match_sell_hint_signal_legacy;

ALTER TABLE common_trigger_state
  ADD CONSTRAINT chk_common_trigger_state_buy_hint_signal_legacy
  CHECK (condition_key <> 'BUY_HINT' OR signal_type = 'BUY_HINT'),
  ADD CONSTRAINT chk_common_trigger_state_sell_hint_signal_legacy
  CHECK (condition_key <> 'SELL_HINT' OR signal_type = 'SELL_HINT');

ALTER TABLE common_trigger_match
  ADD CONSTRAINT chk_common_trigger_match_buy_hint_signal_legacy
  CHECK (condition_key <> 'BUY_HINT' OR signal_type = 'BUY_HINT'),
  ADD CONSTRAINT chk_common_trigger_match_sell_hint_signal_legacy
  CHECK (condition_key <> 'SELL_HINT' OR signal_type = 'SELL_HINT');

ALTER TABLE common_trigger_state
  DROP COLUMN IF EXISTS trigger_live,
  DROP COLUMN IF EXISTS trigger_mark_candidate,
  DROP COLUMN IF EXISTS primary_trigger_period,
  DROP COLUMN IF EXISTS all_trigger_periods,
  DROP COLUMN IF EXISTS projection_30m_flag,
  DROP COLUMN IF EXISTS projection_30m_type;

ALTER TABLE common_trigger_match
  DROP COLUMN IF EXISTS trigger_mark_candidate;

COMMIT;
