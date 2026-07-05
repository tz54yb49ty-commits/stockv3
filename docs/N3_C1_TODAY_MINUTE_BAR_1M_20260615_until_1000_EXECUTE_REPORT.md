# N3-C1 today_minute_bar_1m execute report

## Result

- status: EXECUTED
- today_minute_run_id: `today_minute_bar_1m_20260615_until_1000__market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1`
- source_run_id: `market_data_subscription_20260615_condition_layer_20260612_source_20260612_for_20260615_v1`
- for_trade_date: `20260615`
- latest_closed_minute: `2026-06-15T10:00:00+08:00`
- P0/P1/P2: 0/2/0

## Writes

- minute_rows_written: 15630
- stock/index/board rows: {"board": 1290, "index": 1170, "stock": 13170}
- quality_item_rows_written: 9
- event_outbox_rows_written: 0

## Boundaries

- market_data_pulled: True
- minute_bar_written: True
- event_outbox_written: False
- outbox_consumed: False
- downstream_layers_touched: False
- worker_started: False

## Rollback

- rollback_sql_path: `sql/N3_C1_today_minute_bar_1m_20260615_until_1000_rollback.sql`
