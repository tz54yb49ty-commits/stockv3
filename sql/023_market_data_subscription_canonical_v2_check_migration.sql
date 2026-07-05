BEGIN;

-- N3 subscription canonical v2 CHECK compatibility migration.
-- Scope: allowed_signal_types CHECK constraints only.
-- This keeps historical legacy rows valid while N3 planner gates future
-- writes to canonical N2 v2 signal names.

ALTER TABLE common_market_data_subscription_candidate
  DROP CONSTRAINT IF EXISTS common_market_data_subscription_cand_allowed_signal_types_check,
  ADD CONSTRAINT common_market_data_subscription_cand_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'S_SELL', 'B_BUY_30M_VOL', 'S_SELL_30M_SHRINK'
  ]::text[]);

ALTER TABLE common_market_data_subscription
  DROP CONSTRAINT IF EXISTS common_market_data_subscription_allowed_signal_types_check,
  ADD CONSTRAINT common_market_data_subscription_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'BUY', 'BUY:FULL', 'SELL', 'SELL:FULL', 'BUY_HINT', 'SELL_HINT',
    'B_BUY', 'S_SELL', 'B_BUY_30M_VOL', 'S_SELL_30M_SHRINK'
  ]::text[]);

COMMIT;
