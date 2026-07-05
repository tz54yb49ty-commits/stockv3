# N3-C1 today_minute_bar_1m execute report

## Result

- status: EXECUTED
- today_minute_run_id: `today_minute_bar_1m_20260615_until_1005_action_confirmation_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1`
- source_run_id: `market_data_subscription_20260615_action_confirmation_c1_1005_merged_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000_v1`
- for_trade_date: `20260615`
- latest_closed_minute: `2026-06-15T10:05:00+08:00`
- P0/P1/P2: 0/1/0

## Writes

- minute_rows_written: 28175
- stock/index/board rows: {"board": 0, "index": 0, "stock": 28175}
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

- rollback_sql_path: `sql/V3_20260615_C1_today_minute_refresh_until_1005_for_action_confirmation_rollback.sql`
