# N3-C2B Closed Signal Enrichment Execute Report

## Summary

- result: `EXECUTED`
- layer_role: `N3_market_data`
- c2b_run_id: `closed_signal_enrichment_20260525__closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- c2_run_id: `closed_minute_30m_replay_20260525_until_1500__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- enrichment_rows_written: `17504`
- enrichment_rows_by_asset: `{'stock': 16416, 'index': 72, 'board': 1016, 'total': 17504}`
- signal_distribution: `{'unknown': 72, 'up_volume_flat': 2494, 'up_volume_shrinking': 2260, 'flat': 2653, 'down_volume_expanding': 2806, 'down_volume_shrinking': 2011, 'down_volume_flat': 2408, 'up_volume_expanding': 2800}`
- P0/P1/P2: `0/3/0`
- rollback_safe: `True`

## Boundary

- event_outbox_written: `False`
- outbox_consumed: `False`
- inbox_or_checkpoint_written: `False`
- downstream_layers_touched: `False`
- worker_started: `False`
