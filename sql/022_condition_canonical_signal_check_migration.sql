BEGIN;

-- N2 canonical signal CHECK compatibility migration.
-- Scope: signal whitelist CHECK constraints only.
-- Historical runs still contain legacy action-mark signal names, so this
-- migration uses a compatibility superset while N2 writers enforce canonical
-- future output in code and quality gates.

ALTER TABLE stock_condition_pool
  DROP CONSTRAINT IF EXISTS stock_condition_pool_allowed_signal_types_check,
  ADD CONSTRAINT stock_condition_pool_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'B_BUY_30M_VOL', 'S_SELL', 'S_SELL_30M_SHRINK'
  ]::text[]);

ALTER TABLE index_condition_pool
  DROP CONSTRAINT IF EXISTS index_condition_pool_allowed_signal_types_check,
  ADD CONSTRAINT index_condition_pool_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'B_BUY_30M_VOL', 'S_SELL', 'S_SELL_30M_SHRINK'
  ]::text[]);

ALTER TABLE board_condition_pool
  DROP CONSTRAINT IF EXISTS board_condition_pool_allowed_signal_types_check,
  ADD CONSTRAINT board_condition_pool_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'B_BUY_30M_VOL', 'S_SELL', 'S_SELL_30M_SHRINK'
  ]::text[]);

ALTER TABLE stock_minute_target_scope
  DROP CONSTRAINT IF EXISTS stock_minute_target_scope_allowed_signal_types_check,
  ADD CONSTRAINT stock_minute_target_scope_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'B_BUY_30M_VOL', 'S_SELL', 'S_SELL_30M_SHRINK'
  ]::text[]);

ALTER TABLE index_minute_target_scope
  DROP CONSTRAINT IF EXISTS index_minute_target_scope_allowed_signal_types_check,
  ADD CONSTRAINT index_minute_target_scope_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'B_BUY_30M_VOL', 'S_SELL', 'S_SELL_30M_SHRINK'
  ]::text[]);

ALTER TABLE board_minute_target_scope
  DROP CONSTRAINT IF EXISTS board_minute_target_scope_allowed_signal_types_check,
  ADD CONSTRAINT board_minute_target_scope_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'B_BUY_30M_VOL', 'S_SELL', 'S_SELL_30M_SHRINK'
  ]::text[]);

ALTER TABLE stock_condition_display_basis
  DROP CONSTRAINT IF EXISTS stock_condition_display_basis_selected_signal_types_check,
  ADD CONSTRAINT stock_condition_display_basis_selected_signal_types_check
  CHECK (selected_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'B_BUY_30M_VOL', 'S_SELL', 'S_SELL_30M_SHRINK'
  ]::text[]);

ALTER TABLE index_condition_display_basis
  DROP CONSTRAINT IF EXISTS index_condition_display_basis_selected_signal_types_check,
  ADD CONSTRAINT index_condition_display_basis_selected_signal_types_check
  CHECK (selected_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'B_BUY_30M_VOL', 'S_SELL', 'S_SELL_30M_SHRINK'
  ]::text[]);

ALTER TABLE board_condition_display_basis
  DROP CONSTRAINT IF EXISTS board_condition_display_basis_selected_signal_types_check,
  ADD CONSTRAINT board_condition_display_basis_selected_signal_types_check
  CHECK (selected_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'B_BUY_30M_VOL', 'S_SELL', 'S_SELL_30M_SHRINK'
  ]::text[]);

COMMIT;
