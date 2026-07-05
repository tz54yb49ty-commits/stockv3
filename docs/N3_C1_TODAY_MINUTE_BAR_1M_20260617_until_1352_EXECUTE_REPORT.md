# N3-C1 today_minute_bar_1m execute report

## Result

- status: EXECUTED
- today_minute_run_id: `today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1`
- source_run_id: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_v1`
- for_trade_date: `20260617`
- latest_closed_minute: `2026-06-17T13:52:00+08:00`
- P0/P1/P2: 0/2/0

## Writes

- minute_rows_written: 38304
- stock/index/board rows: {"board": 2907, "index": 1197, "stock": 34200}
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

- rollback_sql_path: `sql/N3_C1_today_minute_bar_1m_20260617_until_1352_rollback.sql`
