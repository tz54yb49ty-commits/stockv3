# V3 20260616 Intraday N3 Source and Metric Run Once Contract

- result: `CONTRACT_PASS`
- for_trade_date: `20260616`
- latest_closed_minute_hhmm: `1401`
- subscription_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- previous_day_preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- b1 rows: `{'by_asset_kind': {'stock': 1822, 'index': 83, 'board': 127}, 'total': 2032}`
- c1 rows: `{'by_asset_kind': {'stock': 102084, 'index': 3077, 'board': 9593}, 'total': 114754}`
- metric rows: `{'by_asset_kind': {'stock': 564, 'index': 17, 'board': 53}, 'total': 634, 'metric_ready': 'derived_from_payload_after_C1', 'metric_not_ready': 'derived_from_payload_after_C1'}`
- rollback_sql_path: `sql/V3_20260616_intraday_n3_source_and_metric_run_once_rollback.sql`

## Boundary

- N4/N5/N6 execute: `false`
- outbox/inbox/checkpoint consume or update: `false`
- scheduler/worker: `false`

## B1 Fact-Only Source-Time Policy Refresh

- untrusted_source_time_label_handling: `NORMALIZE_TO_OBSERVED_AT`
- normalization scope: `index,board`
- normalized quality severity: `P1`
- standard outbox inherits policy: `false`
- B1 writes_outbox: `false`
