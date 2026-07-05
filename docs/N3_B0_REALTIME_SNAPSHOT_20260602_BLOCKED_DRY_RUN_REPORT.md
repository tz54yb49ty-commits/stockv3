# N3-B0 Realtime Daily Snapshot Dry-Run Report

## Summary

- stage: `N3-B0`
- layer_role: `N3_market_data`
- market_data_run_id: `market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`
- source_condition_run_id: `None`
- for_trade_date: `None`
- snapshot_subscription_count: `0`
- snapshot_object_count: `0`
- expected_snapshot_rows: `0`
- writes_outbox: `true`
- event_outbox_write_planned_in_dry_run: `False`
- event_outbox_write_required_in_execute: `True`
- P0/P1/P2: `2/0/0`

## Object Counts

- stock: `0`
- index: `0`
- board: `0`

## Adapter Plan


## Event Contract

- `MarketSnapshotUpdated`
- `MarketDataDelayed`
- `MarketDataMissing`
- `MarketDisplaySnapshotUpdated`

## Previous-Day Preload Context

- preload_run_id: `None`
- status: `None`
- missing_object_count: `0`

## Quality

- P0 failed n3_b0_subscription_run_clean: expected=N3-6 subscription run passed and P0=0 actual=passed=False p0=1
- P1 passed n3_b0_subscription_run_p1_carried: expected=0 actual=0
- P0 failed realtime_snapshot_subscriptions_present: expected=>0 actual=0
- P0 passed realtime_snapshot_subscription_trace_present: expected=trace present actual=present
- P0 passed realtime_snapshot_pull_plan_asset_coverage: expected=pull plan for each asset kind in subscriptions actual=covered
- P0 passed realtime_snapshot_pull_plan_counts_match_subscriptions: expected=counts match actual=matched
- P0 passed realtime_snapshot_pull_plan_execute_not_allowed_in_b0: expected=execute_allowed=false actual=false
- P0 passed realtime_snapshot_estimated_tables_physically_separated: expected=stock/index/board target table prefixes actual=separated
- P0 passed n3_b0_no_runtime_table_names: expected=no *_runtime target table actual=none
- P0 passed n3_b0_event_contract_allowed_n3_events: expected=MarketSnapshotUpdated/MarketDataDelayed/MarketDataMissing/MarketDisplaySnapshotUpdated actual=allowed
- P0 passed n3_b0_preload_p0_zero: expected=0 actual=0
- P1 passed n3_b0_preload_missing_carried_non_blocking: expected=0 actual=0
- P0 passed n3_b0_no_market_pull_or_write: expected=read-only dry-run actual=read-only dry-run

## Boundary

- read_only_database_checks: `True`
- will_execute_sql: `False`
- migration_executed: `False`
- writes_performed: `False`
- market_data_pulled: `False`
- realtime_snapshot_written: `False`
- event_outbox_written: `False`
- downstream_layers_touched: `False`
- worker_started: `False`
- old_system_touched: `False`
