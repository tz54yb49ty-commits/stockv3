# N3-EOD Snapshot Refresh Dry-Run Report

## Summary

- result: `DRY_RUN_PASS`
- blocked: `False`
- eod_run_id: `eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- expected_eod_snapshot_rows: `{'stock': 2052, 'index': 9, 'board': 127, 'total': 2188}`
- official_daily_available: `True`
- official_daily_missing_count: `0`
- execute_final_gate_allowed: `True`
- execute_blocker: `None`
- P0/P1/P2: `0/2/0`

## Source Summary

- B1 snapshot rows: `{'stock': 2052, 'index': 9, 'board': 127, 'total': 2188}`
- C2 summary rows: `{'by_asset': {'stock': 16416, 'index': 72, 'board': 1016, 'total': 17504}, 'total': 17504, 'closed': 17432, 'partial': 0, 'missing': 72, 'failed': 0, 'status_distribution': {'closed': 17432, 'missing': 72}}`
- C2B enrichment rows: `{'by_asset': {'stock': 16416, 'index': 72, 'board': 1016, 'total': 17504}, 'total': 17504, 'computable': 17432, 'unknown': 72, 'missing': 72, 'signal_distribution': {'down_volume_flat': 2408, 'down_volume_shrinking': 2011, 'unknown': 72, 'up_volume_flat': 2494, 'up_volume_shrinking': 2260, 'up_volume_expanding': 2800, 'down_volume_expanding': 2806, 'flat': 2653}, 'quality_distribution': {'passed': 17432, 'missing': 72}}`
- C3 outbox status: `{'pending': 17432, 'total': 17432, 'delivered': 0, 'delivering': 0}`
- N4 replay audit: `{'by_asset': {'stock': 33762, 'index': 144, 'board': 2064, 'total': 35970}, 'total': 35970, 'classification_distribution': {'unchanged': 30730, 'missing': 18, 'would_change': 243, 'would_clear': 245, 'would_match': 4734}, 'missing': 18, 'not_ready': 0}`

## Reconciliation Preview

- counts: `{'official_daily_missing': 0, 'official_price_diff': 0, 'official_volume_diff': 0, 'official_amount_diff': 0, 'b1_snapshot_diff': 0, 'c2_closed_summary_missing': 72, 'c2b_signal_enrichment_unknown': 72, 'c3_outbox_status': 1, 'n4_replay_audit_missing': 18, 'stale_candidate': 0, 'boundary_check': 1}`
- stale_candidate_count: `0`

## Boundary

- writes_database: `False`
- writes_outbox: `False`
- consumes_c3_outbox: `False`
- downstream_layers_touched: `False`
- worker_started: `False`

## Decision

EOD business execute remains blocked unless this report and execute preflight both allow the final gate.
