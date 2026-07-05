# N3-EOD Snapshot Refresh Execute Report

## Summary

- result: `EXECUTED`
- layer_role: `N3_market_data`
- eod_run_id: `eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- snapshot_rows_written: `2188`
- snapshot_rows_by_asset: `{'stock': 2052, 'index': 9, 'board': 127, 'total': 2188}`
- reconciliation_rows_written: `2194`
- reconciliation_diff_distribution: `{'official_daily_confirmed': 2188, 'c2_closed_summary_missing': 3, 'n4_replay_audit_missing': 3}`
- P0/P1/P2: `0/2/0`
- rollback_safe: `True`

## Boundary

- event_outbox_written: `False`
- outbox_consumed: `False`
- inbox_or_checkpoint_written: `False`
- downstream_layers_touched: `False`
- worker_started: `False`
