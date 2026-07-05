# N3-C0 Today Minute Bar 1m Dry-Run Report

## Summary

- stage: `N3-C0`
- layer_role: `N3_market_data`
- result: `DRY_RUN_PASS`
- source_market_data_run_id: `market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`
- today_minute_run_id: `today_minute_bar_1m_20260602_until_1018__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`
- for_trade_date: `20260602`
- latest_closed_minute: `2026-06-02T10:18:00+08:00`
- expected_bar_count_per_object: `48`
- expected_minute_rows: `46512`
- object_count_by_asset: `{'stock': 765, 'index': 54, 'board': 150}`
- P0/P1/P2: `0/0/0`

## Boundary

- market_data_pulled: `false`
- minute_bar_written: `false`
- event_outbox_written: `false`
- outbox_consumed: `false`
- downstream_layers_touched: `false`
- worker_started: `false`

## Execute Contract

```text
N3-C1 may only write common_market_data_run, common_market_data_quality_item,
stock/index/board_minute_bar_1m with is_previous_day_preload=false.
N3-C1 writes_outbox=false; MinuteBarClosed belongs to later N3-C2.
```

## Rollback SQL

```sql
-- N3-C1 today minute_bar_1m rollback plan.
-- Safe only before downstream MinuteBarClosed/C2 consumption; C1 itself writes no outbox.
DELETE FROM common_market_data_quality_item WHERE run_id = 'today_minute_bar_1m_20260602_until_1018__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1';
DELETE FROM stock_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260602_until_1018__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1' AND is_previous_day_preload = false;
DELETE FROM index_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260602_until_1018__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1' AND is_previous_day_preload = false;
DELETE FROM board_minute_bar_1m WHERE run_id = 'today_minute_bar_1m_20260602_until_1018__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1' AND is_previous_day_preload = false;
DELETE FROM common_market_data_run WHERE run_id = 'today_minute_bar_1m_20260602_until_1018__market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1';
```
