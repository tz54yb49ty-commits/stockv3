# N3-C1 today_minute_bar_1m execute report

## Result

- status: EXECUTED
- today_minute_run_id: `today_minute_bar_1m_20260617_until_1352__market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- source_run_id: `market_data_subscription_20260617_condition_layer_20260616_source_20260616_for_20260617_semantic_repair_v1`
- for_trade_date: `20260617`
- latest_closed_minute: `2026-06-17T13:52:00+08:00`
- P0/P1/P2: 0/2/0

## Writes

- minute_rows_written: 38528
- stock/index/board rows: {"board": 2924, "index": 1204, "stock": 34400}
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

- rollback_sql_path: `sql/V3_20260617_N3_rebuild_after_n2_repair_c1_today_minute_rollback.sql`
