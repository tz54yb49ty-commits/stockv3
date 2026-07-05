# N3-C3 MinuteBarClosed Outbox Dry-Run Report

## Summary

- result: `DRY_RUN_PASS`
- layer_role: `N3_market_data`
- c2_run_id: `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- c3_run_id: `minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- candidate_count_by_asset: `{'stock': 16344, 'index': 72, 'board': 1016, 'total': 17432}`
- excluded_by_status: `{'missing': 72, 'partial': 0, 'failed': 0, 'total': 72}`
- bj_920xxx_excluded_summary_rows: `72`
- payload_validated_count: `17432`
- trace_blocked_count: `0`
- duplicate_candidate_count: `0`
- P0/P1/P2: `0/1/0`

## Boundary

- writes_performed: `false`
- quality_written: `false`
- event_outbox_written: `false`
- outbox_consumed: `false`
- inbox_or_checkpoint_written: `false`
- downstream_layers_touched: `false`
- worker_started: `false`

## Trace Enrichment

- subscription_trace_count: `2188`
- pull_plan_trace_count: `3`
- missing trace rows block event generation; placeholder `pull_plan_id` is forbidden.

## Future Write Scope

Allowed future execute writes:

```text
common_market_data_run
common_market_data_quality_item
common_event_outbox
```

Forbidden:

```text
stock_closed_30m_summary
index_closed_30m_summary
board_closed_30m_summary
stock_minute_bar_1m
index_minute_bar_1m
board_minute_bar_1m
stock_realtime_projection_metric
index_realtime_projection_metric
board_realtime_projection_metric
stock_realtime_daily_snapshot
index_realtime_daily_snapshot
board_realtime_daily_snapshot
common_event_inbox
common_event_consumer_checkpoint
common_event_delivery_attempt
condition tables
trigger/action/user/voice/mobile/sim/position tables
N4/N5/N6
worker
old system
```

## Replay Guard

- C3 dry-run does not consume outbox.
- C3 future execute only writes pending outbox rows after explicit gate.
- N4/N5 replay requires explicit C3 run_id allowlist and owning-layer contracts.

## Next Step

- next_allowed_step: `N3-C3 dry-run review`
- C3 execute remains forbidden until a separate execute contract, preflight, rollback review, and explicit user confirmation.
