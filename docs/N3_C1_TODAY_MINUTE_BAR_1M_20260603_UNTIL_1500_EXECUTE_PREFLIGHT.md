# N3-C1 Today Minute Bar 1m 20260603 Execute Preflight

- result: `PREFLIGHT_PASS`
- today_minute_run_id: `today_minute_bar_1m_20260603_until_1500__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- source_market_data_run_id: `market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- source_snapshot_run_id: `realtime_snapshot_20260603_market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- source_previous_day_minute_run_id: `previous_day_minute_preload_20260602_for_20260603__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- for_trade_date: `20260603`
- latest_closed_minute_hhmm: `1500`
- expected objects stock/index/board/total: `241/2/34/277`
- expected rows stock/index/board/total: `57840/480/8160/66480`
- source statuses subscription/snapshot/A1: `passed/passed/passed`
- minute adapter coverage: `['board', 'index', 'stock']` via `['BoardMarketDataAdapter', 'IndexMarketDataAdapter', 'StockMarketDataAdapter']`
- P0/P1/P2: `0/0/0`
- execute_final_gate_allowed: `true`

## Boundary

- will_execute_sql: `false`
- market_data_pulled: `false`
- minute_bar_written: `false`
- event_outbox_written: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`

## Rollback

- rollback_sql: `sql/N3_C1_today_minute_bar_1m_20260603_until_1500_rollback.sql`
- rollback guard: hard-fail before DELETE for outbox/inbox/checkpoint and downstream refs.
