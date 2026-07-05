DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM common_market_data_subscription_candidate
    WHERE allowed_signal_types && ARRAY['BUY', 'BUY:FULL', 'SELL', 'SELL:FULL']::text[]
  ) THEN
    RAISE EXCEPTION 'rollback blocked: common_market_data_subscription_candidate contains canonical v2 signal rows';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM common_market_data_subscription
    WHERE allowed_signal_types && ARRAY['BUY', 'BUY:FULL', 'SELL', 'SELL:FULL']::text[]
  ) THEN
    RAISE EXCEPTION 'rollback blocked: common_market_data_subscription contains canonical v2 signal rows';
  END IF;
END $$;

BEGIN;

-- Restore legacy CHECK constraints.

ALTER TABLE common_market_data_subscription_candidate
  DROP CONSTRAINT IF EXISTS common_market_data_subscription_cand_allowed_signal_types_check,
  ADD CONSTRAINT common_market_data_subscription_cand_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL',
    'BUY_HINT', 'SELL_HINT'
  ]::text[]);

ALTER TABLE common_market_data_subscription
  DROP CONSTRAINT IF EXISTS common_market_data_subscription_allowed_signal_types_check,
  ADD CONSTRAINT common_market_data_subscription_allowed_signal_types_check
  CHECK (allowed_signal_types <@ ARRAY[
    'B_BUY_30M_VOL', 'B_BUY', 'S_SELL_30M_SHRINK', 'S_SELL',
    'BUY_HINT', 'SELL_HINT'
  ]::text[]);

COMMIT;
