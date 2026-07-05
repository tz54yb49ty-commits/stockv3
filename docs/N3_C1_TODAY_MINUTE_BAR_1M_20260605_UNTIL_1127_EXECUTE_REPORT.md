# N3-C1 today_minute_bar_1m execute report

## Result

- status: EXECUTED
- today_minute_run_id: `today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- source_run_id: `market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1`
- for_trade_date: `20260605`
- latest_closed_minute: `2026-06-05T11:27:00+08:00`
- P0/P1/P2: 0/0/0

## Writes

- minute_rows_written: 40014
- stock/index/board rows: {"board": 6552, "index": 234, "stock": 33228}
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

- rollback_sql_path: `sql/N3_C1_today_minute_bar_1m_20260605_until_1127_rollback.sql`
