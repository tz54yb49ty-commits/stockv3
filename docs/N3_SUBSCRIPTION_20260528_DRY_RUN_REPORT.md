# N3 Subscription 20260528 Dry-Run Report

## Summary

- result: `DRY_RUN_PASS`
- layer_role: `N3_market_data`
- source_condition_run_id: `condition_layer_20260527_source_20260527_v1`
- source_trade_date: `20260527`
- for_trade_date: `20260528`
- prev_trade_date: `20260527`
- dry_run_market_data_run_id: `market_data_subscription_20260528_condition_layer_20260527_source_20260527_v1_dry_run`
- suggested_execute_run_id: `market_data_subscription_20260528_condition_layer_20260527_source_20260527_v1`

## Counts

- source_scope_rows: `4602`
- source_scope_rows_by_asset_kind: `stock=4307, index=22, board=273`
- candidate_rows: `13806`
- subscription_rows: `6438`
- subscription_object_count: `2146`
- object_count_by_asset_kind: `stock=2010, index=9, board=127`
- pull_plan_rows: `9`

## Required Data Kind

- minute_bar_1m: `2146`
- previous_day_minute_bar_1m: `2146`
- realtime_daily_snapshot: `2146`

## Calendar Gate

- row_exists: `True`
- is_open: `True`
- prev_trade_date: `20260527`
- source_version: `trade_calendar_20260528_patch_v1`
- final_execute_gate: `READY`

## Quality

- P0/P1/P2: `0/0/0`

## Boundary

- dry-run only: `true`
- market_data_pulled: `false`
- market_data_fact_written: `false`
- event_outbox_written: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
