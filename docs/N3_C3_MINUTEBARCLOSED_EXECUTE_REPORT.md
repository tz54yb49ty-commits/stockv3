# N3-C3 MinuteBarClosed Outbox Execute Report

## Summary

- result: `EXECUTED`
- layer_role: `N3_market_data`
- c3_run_id: `minute_bar_closed_outbox_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- c2_run_id: `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- outbox_rows_written: `17432`
- event_type_counts: `{'MinuteBarClosed': 17432}`
- excluded_by_status: `{'missing': 72, 'partial': 0, 'failed': 0, 'total': 72}`
- P0/P1/P2: `0/1/0`
- rollback_safe: `True`

## Boundary

- event_outbox_written: `True`
- outbox_consumed: `False`
- inbox_or_checkpoint_written: `False`
- downstream_layers_touched: `False`
- worker_started: `False`
