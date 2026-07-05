# N3/N4/N5 20260602 11:05 Mock Full Flow Report

- result: MOCK_FLOW_PASS
- source_condition_run_id: condition_layer_20260601_source_20260601_v1
- projection_run_id: realtime_projection_metric_20260602_live3__realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- projection rows recomputed: 2487
- N4 context rows: 5941
- N4 dry-run P0/P1/P2: 0/1/0
- N4 execute-plan P0/P1/P2: 0/0/0
- N4 matched/pending: 177/150
- N5 passed: True
- N5 P0/P1/P2: 0/0/0
- N5 read events: 327
- N5 planned action facts: 177
- N5 output planned events: 177

## Side Effects

- writes_performed: false
- database_modified: false
- worker_started: false
- N6 touched: false
- real_trade_touched: false

## Next Production Confirmation Points

- N3-B2 realtime projection live3 execute writes projection facts/outbox: requires user confirmation
- N4 trigger context snapshot execute writes N4 context: requires user confirmation
- N4 projection matcher execute consumes N3 outbox and writes trigger facts/outbox: requires user confirmation
- N5 action consumer execute consumes N4 outbox and writes action facts/outbox: requires user confirmation
