BEGIN;

-- Guard: legacy CHECK restoration is safe only before canonical-only rows exist.
DO $$
DECLARE
  v_canonical_only text[] := ARRAY['BUY', 'BUY:FULL', 'SELL', 'SELL:FULL']::text[];
  v_found boolean;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM stock_condition_pool WHERE allowed_signal_types && v_canonical_only
    UNION ALL SELECT 1 FROM index_condition_pool WHERE allowed_signal_types && v_canonical_only
    UNION ALL SELECT 1 FROM board_condition_pool WHERE allowed_signal_types && v_canonical_only
    UNION ALL SELECT 1 FROM stock_minute_target_scope WHERE allowed_signal_types && v_canonical_only
    UNION ALL SELECT 1 FROM index_minute_target_scope WHERE allowed_signal_types && v_canonical_only
    UNION ALL SELECT 1 FROM board_minute_target_scope WHERE allowed_signal_types && v_canonical_only
    UNION ALL SELECT 1 FROM stock_condition_display_basis WHERE selected_signal_types && v_canonical_only
    UNION ALL SELECT 1 FROM index_condition_display_basis WHERE selected_signal_types && v_canonical_only
    UNION ALL SELECT 1 FROM board_condition_display_basis WHERE selected_signal_types && v_canonical_only
  )
  INTO v_found;

  IF v_found THEN
    RAISE EXCEPTION 'canonical-only signal rows exist; restore legacy CHECK only after scoped business rollback';
  END IF;
END $$;

-- Restore legacy CHECK constraints.
ALTER TABLE stock_condition_pool
  DROP CONSTRAINT IF EXISTS stock_condition_pool_allowed_signal_types_check,
  ADD CONSTRAINT stock_condition_pool_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT'
  ]::text[]);

ALTER TABLE index_condition_pool
  DROP CONSTRAINT IF EXISTS index_condition_pool_allowed_signal_types_check,
  ADD CONSTRAINT index_condition_pool_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT'
  ]::text[]);

ALTER TABLE board_condition_pool
  DROP CONSTRAINT IF EXISTS board_condition_pool_allowed_signal_types_check,
  ADD CONSTRAINT board_condition_pool_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT'
  ]::text[]);

ALTER TABLE stock_minute_target_scope
  DROP CONSTRAINT IF EXISTS stock_minute_target_scope_allowed_signal_types_check,
  ADD CONSTRAINT stock_minute_target_scope_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT'
  ]::text[]);

ALTER TABLE index_minute_target_scope
  DROP CONSTRAINT IF EXISTS index_minute_target_scope_allowed_signal_types_check,
  ADD CONSTRAINT index_minute_target_scope_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT'
  ]::text[]);

ALTER TABLE board_minute_target_scope
  DROP CONSTRAINT IF EXISTS board_minute_target_scope_allowed_signal_types_check,
  ADD CONSTRAINT board_minute_target_scope_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT'
  ]::text[]);

ALTER TABLE stock_condition_display_basis
  DROP CONSTRAINT IF EXISTS stock_condition_display_basis_selected_signal_types_check,
  ADD CONSTRAINT stock_condition_display_basis_selected_signal_types_check
  CHECK (selected_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT'
  ]::text[]);

ALTER TABLE index_condition_display_basis
  DROP CONSTRAINT IF EXISTS index_condition_display_basis_selected_signal_types_check,
  ADD CONSTRAINT index_condition_display_basis_selected_signal_types_check
  CHECK (selected_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT'
  ]::text[]);

ALTER TABLE board_condition_display_basis
  DROP CONSTRAINT IF EXISTS board_condition_display_basis_selected_signal_types_check,
  ADD CONSTRAINT board_condition_display_basis_selected_signal_types_check
  CHECK (selected_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL', 'BUY_HINT', 'SELL_HINT'
  ]::text[]);

COMMIT;
