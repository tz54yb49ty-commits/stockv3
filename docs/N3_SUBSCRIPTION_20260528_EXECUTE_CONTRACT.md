# N3 Subscription 20260528 Execute Contract

## Summary

- result: `PASS`
- layer_role: `N3_market_data`
- market_data_run_id: `market_data_subscription_20260528_condition_layer_20260527_source_20260527_v1`
- source_condition_run_id: `condition_layer_20260527_source_20260527_v1`
- source_trade_date: `20260527`
- for_trade_date: `20260528`
- prev_trade_date: `20260527`
- dry_run_report_path: `docs/N3_subscription_20260528_dry_run_report.json`
- rollback_sql_path: `sql/N3_subscription_20260528_rollback.sql`

## Expected Rows

- source_scope_rows: `4602`
- candidate_rows: `13806`
- subscription_rows: `6438`
- pull_plan_rows: `9`
- object_count_by_asset_kind: `stock=2010, index=9, board=127`

## Write Scope

Allowed future execute writes:

- `common_market_data_run`
- `common_market_data_quality_item`
- `common_market_data_subscription_candidate`
- `common_market_data_subscription`
- `common_market_data_pull_plan`

Forbidden:

- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- `stock_minute_bar_1m`
- `index_minute_bar_1m`
- `board_minute_bar_1m`
- `stock_realtime_daily_snapshot`
- `index_realtime_daily_snapshot`
- `board_realtime_daily_snapshot`
- `stock_realtime_projection_metric`
- `index_realtime_projection_metric`
- `board_realtime_projection_metric`
- `N4`
- `N5`
- `N6`
- `worker`
- `old_system`
- `real_trading`

## Execute Gate

- current_execute_gate_status: `READY_FOR_FINAL_GATE`
- blockers: `0`
- P0/P1/P2: `0/0/0`
