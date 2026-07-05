# N3-C1 today_minute_bar_1m execute report

## Result

- status: EXECUTED
- today_minute_run_id: `today_minute_bar_1m_20260608_until_1500_action_metric_coverage_repair_v1__market_data_subscription_20260608_action_metric_coverage_repair_v1`
- source_run_id: `market_data_subscription_20260608_action_metric_coverage_repair_v1__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry`
- for_trade_date: `20260608`
- latest_closed_minute: `2026-06-08T15:00:00+08:00`
- P0/P1/P2: 0/0/0

## Writes

- minute_rows_written: 91440
- stock/index/board rows: {"board": 18480, "index": 11520, "stock": 61440}
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

- rollback_sql_path: `sql/N3_C1_action_confirmation_metric_20260608_scoped_coverage_repair_today_minute_until_1500_rollback.sql`
