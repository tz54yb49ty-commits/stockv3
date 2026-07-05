# N3 Subscription 20260528 Execute Preflight

## Summary

- result: `PREFLIGHT_PASS`
- layer_role: `N3_market_data`
- market_data_run_id: `market_data_subscription_20260528_condition_layer_20260527_source_20260527_v1`
- source_condition_run_id: `condition_layer_20260527_source_20260527_v1`
- active_condition_run_count: `1`
- active_condition_status: `passed_active`
- rollback_sql_path: `sql/N3_subscription_20260528_rollback.sql`

## Baseline

- common_market_data_run: `0`
- same_n2_subscription_run_count: `0`
- common_market_data_subscription_candidate: `0`
- common_market_data_subscription: `0`
- common_market_data_pull_plan: `0`
- common_market_data_quality_item: `0`
- common_event_outbox: `0`
- common_event_inbox: `0`
- common_event_consumer_checkpoint_refs: `0`

## Calendar Gate

- row_exists: `True`
- is_open: `True`
- prev_trade_date: `20260527`
- final_execute_blocker: `none`

## Boundary

- execute now: `false`
- market_data_pulled: `false`
- market_data_fact_written: `false`
- event_outbox_written: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
