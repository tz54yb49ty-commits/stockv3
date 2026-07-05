# N3-C2 Closed 30m Replay Dry-Run Report

## Summary

- result: `DRY_RUN_PASS`
- layer_role: `N3_market_data`
- c2_run_id: `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- latest_closed_label: `14:11`
- object_counts: `{'stock': 2052, 'index': 9, 'board': 127, 'total': 2188}`
- baseline_rows: `{'stock': 390213, 'index': 1719, 'board': 24257, 'total': 416189}`
- delta_minute_rows_estimate: `106771`
- expected_summary_rows: `17504`
- summary_status_counts: `{'closed': 13074, 'partial': 2179, 'missing': 2251, 'failed': 0}`
- P0/P1/P2: `0/3/0`

## Boundary

- market_data_pulled: `false`
- minute_delta_written: `false`
- closed_summary_written: `false`
- quality_written: `false`
- event_outbox_written: `false`
- outbox_consumed: `false`
- inbox_or_checkpoint_written: `false`
- downstream_layers_touched: `false`
- worker_started: `false`

## Replay Plan

- full_day_minute_labels_per_object: `240`
- main_gap: `{'from_label': '14:12', 'to_label': '15:00', 'label_count': 49, 'available_non_bj_objects': 2179, 'estimated_rows': 106771}`
- BJ retry capacity: `{'objects': 9, 'labels_per_object': 240, 'estimated_rows_if_available': 2160}`
- replay_diff_check_required: `true`

## Write Scope

Allowed future execute writes:

```text
common_market_data_run
common_market_data_quality_item
stock_minute_bar_1m delta rows
index_minute_bar_1m delta rows
board_minute_bar_1m delta rows
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
```

Forbidden:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
common_event_delivery_attempt
stock_realtime_projection_metric
index_realtime_projection_metric
board_realtime_projection_metric
stock_realtime_daily_snapshot
index_realtime_daily_snapshot
board_realtime_daily_snapshot
B1/B2/N4/N5 existing runtime rows
condition tables
trigger/action/user/voice/mobile/sim/position tables
worker
```

## Next Step

- next_allowed_step: `N3-C2 dry-run review`
- C2 execute remains forbidden until a separate execute runner, preflight, rollback review, and explicit user confirmation.
