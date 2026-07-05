# N3-C1 today_minute_bar_1m execute report

## Result

- status: EXECUTED
- today_minute_run_id: `today_minute_bar_1m_20260603_until_1500__market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- source_run_id: `market_data_subscription_20260603_condition_layer_20260602_source_20260602_v1`
- for_trade_date: `20260603`
- latest_closed_minute: `2026-06-03T15:00:00+08:00`
- P0/P1/P2: 0/0/0

## Writes

- minute_rows_written: 66480
- stock/index/board rows: {"board": 8160, "index": 480, "stock": 57840}
- quality_item_rows_written: 8
- event_outbox_rows_written: 0

## Boundaries

- market_data_pulled: True
- minute_bar_written: True
- event_outbox_written: False
- outbox_consumed: False
- downstream_layers_touched: False
- worker_started: False

## Rollback

- rollback_sql_path: `sql/N3_C1_today_minute_bar_1m_20260603_until_1500_rollback.sql`
