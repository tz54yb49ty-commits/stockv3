# N3-C1 20260602 Until 11:05 Execute Post-Review

status = POST_REVIEW_PASS
run_id = today_minute_bar_1m_20260602_until_1105__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
for_trade_date = 20260602
latest_closed_minute = 2026-06-02T11:05:00+08:00

## Rows

```text
stock_minute_bar_1m = 72675
index_minute_bar_1m = 5130
board_minute_bar_1m = 14250
total = 92055
quality_item = 8
P0/P1/P2 = 0/0/0
```

## Boundary

```text
outbox refs = 0
inbox refs = 0
checkpoint refs = 0
downstream refs = {'common_trigger_run': 0, 'common_action_run': 0, 'user_projection_run': 'no_ref_columns', 'user_signal_projection': 'no_ref_columns'}
market_data_pulled = True
market_data_fact_written = True
downstream_layers_touched = False
worker_started = False
rollback_safe = true
```

Rollback SQL: `sql/N3_C1_today_minute_bar_1m_20260602_until_1105_rollback.sql`
