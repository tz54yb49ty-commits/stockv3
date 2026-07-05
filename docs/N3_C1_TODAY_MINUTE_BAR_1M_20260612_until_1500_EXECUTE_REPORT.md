# N3-C1 today_minute_bar_1m execute report

## Result

- status: EXECUTED
- today_minute_run_id: `today_minute_bar_1m_20260612_until_1500__market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- source_run_id: `market_data_subscription_20260612_condition_layer_20260611_source_20260611_for_20260612_v1`
- for_trade_date: `20260612`
- latest_closed_minute: `2026-06-12T15:00:00+08:00`
- P0/P1/P2: 0/2/0

## Writes

- minute_rows_written: 70983
- stock/index/board rows: {"board": 4541, "index": 7887, "stock": 58555}
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

- rollback_sql_path: `sql/N3_C1_today_minute_bar_1m_20260612_until_1500_rollback.sql`
