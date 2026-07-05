# N3-B0 Realtime Daily Snapshot Dry-Run Report

## Summary

- stage: `N3-B0`
- layer_role: `N3_market_data`
- market_data_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- source_condition_run_id: `condition_layer_20260615_source_20260615_for_20260616_v1`
- for_trade_date: `20260616`
- snapshot_subscription_count: `2032`
- snapshot_object_count: `2032`
- expected_snapshot_rows: `2032`
- writes_outbox: `false`
- event_outbox_write_planned_in_dry_run: `False`
- event_outbox_write_required_in_execute: `False`
- P0/P1/P2: `0/0/0`

## Object Counts

- stock: `1822`
- index: `83`
- board: `127`

## Adapter Plan

- board: adapter=`BoardMarketDataAdapter` objects=`127` expected_snapshot_rows=`127` target=`board_realtime_daily_snapshot`
- index: adapter=`IndexMarketDataAdapter` objects=`83` expected_snapshot_rows=`83` target=`index_realtime_daily_snapshot`
- stock: adapter=`StockMarketDataAdapter` objects=`1822` expected_snapshot_rows=`1822` target=`stock_realtime_daily_snapshot`

## Event Contract


## Previous-Day Preload Context

- preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v1`
- status: `passed`
- missing_object_count: `0`

## Quality

- P0 passed n3_b0_subscription_run_clean: expected=N3-6 subscription run passed and P0=0 actual=passed=True p0=0
- P1 passed n3_b0_subscription_run_p1_carried: expected=0 actual=0
- P0 passed realtime_snapshot_subscriptions_present: expected=>0 actual=2032
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
