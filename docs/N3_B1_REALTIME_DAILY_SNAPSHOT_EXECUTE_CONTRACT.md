# N3-B1 Realtime Daily Snapshot Execute Contract

## Summary

- stage: `N3-B1-preflight`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- snapshot_run_id: `realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- source_condition_run_id: `condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- expected_row_count: `2188`
- writes_outbox: `True`
- writes_market_display_snapshot_updated: `False`
- P0/P1/P2: `0/1/0`

## Expected Asset Counts

- stock: objects=`2052` subscriptions=`2052` expected_snapshot_rows=`2052`
- index: objects=`9` subscriptions=`9` expected_snapshot_rows=`9`
- board: objects=`127` subscriptions=`127` expected_snapshot_rows=`127`

## Target Tables

- stock: snapshot_fact=`stock_realtime_daily_snapshot` quality=`common_market_data_quality_item` outbox=`common_event_outbox`
- index: snapshot_fact=`index_realtime_daily_snapshot` quality=`common_market_data_quality_item` outbox=`common_event_outbox`
- board: snapshot_fact=`board_realtime_daily_snapshot` quality=`common_market_data_quality_item` outbox=`common_event_outbox`

## Source Adapter Plan

- board: adapter=`BoardMarketDataAdapter` source_pull_plan_id=`30` objects=`127` expected_rows=`127`
- index: adapter=`IndexMarketDataAdapter` source_pull_plan_id=`33` objects=`9` expected_rows=`9`
- stock: adapter=`StockMarketDataAdapter` source_pull_plan_id=`36` objects=`2052` expected_rows=`2052`

## Event Contract

- `MarketSnapshotUpdated`
- `MarketDataDelayed`
- `MarketDataMissing`
- publish_display_event: `False`
- display_policy_does_not_trigger_voice: `True`

## Policies

- idempotency_policy: `upsert_or_noop_by_snapshot_unique_key_after validating same source_run_id`
- overwrite_policy: `no_silent_overwrite`
- rollback_sql_path: `sql/N3_B1_realtime_daily_snapshot_rollback.sql`
- rollback_touches_event_outbox: `True`
- rollback_requires_outbox_not_delivered: `True`

## Post-Execute Quality Gates

- P0 n3_b1_snapshot_object_count_matches_b0: stock/index/board snapshot object_count must match B0 expected asset counts
- P0 n3_b1_snapshot_rows_reasonable: actual snapshot rows must be non-negative and missing objects must create quality items and missing events
- P0 n3_b1_market_snapshot_outbox_matches_successful_facts: successful snapshot fact writes must have same-transaction MarketSnapshotUpdated outbox rows
- P0 n3_b1_quality_outbox_matches_missing_or_delayed: missing/delayed objects must have quality evidence and same-transaction quality event
- P0 n3_b1_duplicate_snapshot_key_zero: duplicate key (run_id, trade_date, identity_key, snapshot_time, source_adapter) must be zero in each physical snapshot table
- P0 n3_b1_physical_table_isolation: identity_key prefix must match physical snapshot table family
- P0 n3_b1_display_event_policy: MarketDisplaySnapshotUpdated is low-frequency display material only and never triggers voice or action cards
- P0 n3_b1_no_downstream_consumption_before_rollback: rollback is only safe before outbox rows are delivered or consumed by downstream inbox

## Preflight Quality

- P0 passed n3_b1_b0_report_stage_valid: expected=N3-B0 actual=N3-B0
- P0 passed n3_b1_b0_report_p0_zero: expected=P0=0 blocked=false actual=P0=0 blocked=False
- P1 warning n3_b1_b0_p1_carried: expected=0 actual=2
- P0 passed n3_b1_source_run_id_matches_n3_6: expected=market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute actual=market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- P0 passed n3_b1_n3_6_source_p0_zero: expected=P0=0 passed=true actual=P0=0 passed=True
- P0 passed n3_b1_snapshot_run_id_distinct: expected=distinct non-empty snapshot_run_id actual=realtime_daily_snapshot_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute
- P0 passed n3_b1_asset_counts_match_n3_6: expected={'stock': 2052, 'index': 9, 'board': 127} actual={'stock': 2052, 'index': 9, 'board': 127}
- P0 passed n3_b1_source_adapter_plan_covers_assets: expected=stock,index,board actual=board,index,stock
- P0 passed n3_b1_target_tables_no_runtime_names: expected=no *_runtime target table actual=none
- P0 passed n3_b1_snapshot_tables_physically_separated: expected=stock/index/board table prefixes actual=separated
- P0 passed n3_b1_target_tables_no_downstream_tables: expected=downstream table names absent actual=absent
- P0 passed n3_b1_target_tables_include_event_outbox: expected=common_event_outbox present actual=present
- P0 passed n3_b1_event_contract_allowed_n3_events: expected=allowed N3 snapshot/quality/display events actual=allowed
- P0 passed n3_b1_event_payload_trace_fields_required: expected=subscription_id/pull_plan_id/run_id/source_adapter/data_quality_status plus id actual=present
- P0 passed n3_b1_snapshot_target_tables_complete: expected=board_realtime_daily_snapshot,index_realtime_daily_snapshot,stock_realtime_daily_snapshot actual=board_realtime_daily_snapshot,index_realtime_daily_snapshot,stock_realtime_daily_snapshot
- P0 passed n3_b1_contract_writes_outbox_true: expected=true actual=true
- P0 passed n3_b1_preflight_no_market_pull_or_write: expected=no side effects actual=contract only
- P0 passed n3_b1_rollback_sql_scopes_event_outbox: expected=common_event_outbox scoped by source_run_id=snapshot_run_id actual=scoped
- P0 passed n3_b1_rollback_sql_has_delivery_guards: expected=delivery and downstream inbox precheck present actual=present
- P0 passed n3_b1_rollback_sql_does_not_touch_downstream_tables: expected=no downstream DML actual=absent

## Boundary

- read_only_database_checks: `true`
- will_execute_sql: `false`
- migration_executed: `false`
- writes_performed: `false`
- market_data_pulled: `false`
- realtime_snapshot_written: `false`
- event_outbox_written: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
- old_system_touched: `false`

## Rollback

Rollback SQL was generated at `sql/N3_B1_realtime_daily_snapshot_rollback.sql`. It deletes rows by `source_run_id`, `snapshot_run_id`, and `for_trade_date`; it includes outbox delivery/inbox prechecks and does not modify downstream tables.
