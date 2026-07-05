# N3 Subscription 20260529 Execute Contract

- result: PASS
- market_data_run_id: `market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1`
- source_condition_run_id: `condition_layer_20260528_source_20260528_v1`
- source_trade_date: `20260528`
- for_trade_date: `20260529`
- prev_trade_date: `20260528`
- P0/P1/P2: `0/0/0`

## Expected Rows

- source_scope_rows: `4552`
- source_scope_rows_by_asset_kind: `{'stock': 4271, 'index': 18, 'board': 263}`
- candidate_rows: `5038`
- subscription_rows: `2643`
- pull_plan_rows: `7`
- object_count_by_asset_kind: `{'stock': 2021, 'index': 9, 'board': 127}`
- required_data_kind_counts: `{'minute_bar_1m': 243, 'previous_day_minute_bar_1m': 243, 'realtime_daily_snapshot': 2157}`

## Boundary

- no market data pull
- no market fact write
- no outbox/inbox/checkpoint write
- no N4/N5/N6
- no worker / old system / real trading

rollback_sql_path: `sql/N3_subscription_20260529_rollback.sql`
