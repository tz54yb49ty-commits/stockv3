-- Rollback for N3 market_data_subscription / pull_plan rebuild after N2-Display.
-- Generated: 2026-05-25T10:40:28+0800
-- Scope: v3 development database only.
-- Run to delete: market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
-- Source condition run: condition_layer_20260522_to_20260525_20260525102249_execute
-- This SQL deletes only N3 control rows for this run_id.
-- It does not touch common_event_outbox, market data fact tables, N2 condition tables, N4/N5/N6 tables, workers, or old systems.

BEGIN;

DELETE FROM common_market_data_pull_plan
WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute'
  AND source_condition_run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM common_market_data_subscription
WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute'
  AND source_condition_run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM common_market_data_subscription_candidate
WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute'
  AND source_condition_run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM common_market_data_quality_item
WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute'
  AND source_condition_run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute';

DELETE FROM common_market_data_run
WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute'
  AND source_condition_run_id = 'condition_layer_20260522_to_20260525_20260525102249_execute'
  AND market_data_pulled = false
  AND market_data_fact_written = false
  AND downstream_layers_touched = false
  AND worker_started = false;

COMMIT;

-- Post-rollback verification:
-- SELECT count(*) FROM common_market_data_run WHERE run_id = 'market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute'; -- expected 0
-- SELECT count(*) FROM common_event_outbox; -- must remain unchanged
-- SELECT count(*) FROM stock_realtime_daily_snapshot; -- must remain unchanged
-- SELECT count(*) FROM stock_minute_bar_1m; -- must remain unchanged
