# N3-A1 Previous-Day Minute Execute Contract

## Summary

- stage: `N3-A1-preflight`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260615_action_confirmation_until_1458_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1458_v1`
- preload_run_id: `previous_day_minute_preload_20260615_until_1458_action_confirmation_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1458_v1`
- source_condition_run_id: `condition_layer_20260612_source_20260612_for_20260615_v1`
- for_trade_date: `20260615`
- previous_day_minute_date: `20260612`
- expected_row_count: `222000`
- writes_outbox: `False`
- P0/P1/P2: `0/0/0`

## Expected Asset Counts

- stock: objects=`925` subscriptions=`925` expected_minute_rows=`222000`
- index: objects=`0` subscriptions=`0` expected_minute_rows=`0`
- board: objects=`0` subscriptions=`0` expected_minute_rows=`0`

## Target Tables

- stock: minute_fact=`stock_minute_bar_1m` preload_status=`stock_previous_day_minute_preload_status`
- index: minute_fact=`index_minute_bar_1m` preload_status=`index_previous_day_minute_preload_status`
- board: minute_fact=`board_minute_bar_1m` preload_status=`board_previous_day_minute_preload_status`

## Source Adapter Plan

- stock: adapter=`StockRealtimeQuoteAdapter` source_pull_plan_id=`198` objects=`925` expected_rows=`222000`

## Policies

- idempotency_policy: `upsert_or_noop_by_unique_key_after validating same source_run_id`
- execute_runner: `scripts/run_previous_day_minute_preload_execute.py`
- execute_requires_flags: `--execute, --user-confirmed`
- overwrite_policy: `no_silent_overwrite`
- rollback_sql_path: `sql/N3_20260615_action_confirmation_previous_day_preload_until_1458_rollback.sql`
- rollback_touches_event_outbox: `False`

## Post-Execute Quality Gates

- P0 n3_a1_asset_object_count_matches_a0: stock/index/board preload_status object_count must match A0 expected asset counts
- P0 n3_a1_minute_rows_reasonable: actual minute rows must be non-negative and not exceed expected A-share minute rows; missing/partial rows must create quality items
- P0 n3_a1_duplicate_minute_key_zero: duplicate key (run_id, trade_date, identity_key, bar_time, source_adapter) must be zero in each physical minute table
- P1/P2 n3_a1_missing_object_not_silent: missing object can be P1/P2 by threshold, but cannot pass without preload_status and quality_item evidence
- P0 n3_a1_physical_table_isolation: identity_key prefix must match physical table family
- P0 n3_a1_outbox_rows_zero: N3-A1 previous-day preload writes_outbox=false; common_event_outbox must not receive rows

## Preflight Quality

- P0 passed n3_a1_a0_report_stage_valid: expected=N3-A0 actual=N3-A0
- P0 passed n3_a1_a0_report_p0_zero: expected=P0=0 blocked=false actual=P0=0 blocked=False
- P1 passed n3_a1_a0_p1_carried: expected=0 actual=0
- P0 passed n3_a1_source_run_id_matches_n3_6: expected=market_data_subscription_20260615_action_confirmation_until_1458_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1458_v1 actual=market_data_subscription_20260615_action_confirmation_until_1458_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1458_v1
- P0 passed n3_a1_n3_6_source_p0_zero: expected=P0=0 passed=true actual=P0=0 passed=True
- P0 passed n3_a1_previous_day_minute_date_matches_prev_trade_date: expected=20260612 actual=20260612
- P0 passed n3_a1_preload_run_id_distinct: expected=distinct non-empty preload_run_id actual=previous_day_minute_preload_20260615_until_1458_action_confirmation_scope__n4_production_semantic_replay_20260615_market_snapshot_updated_until_1458_v1
- P0 passed n3_a1_asset_counts_match_n3_6: expected={'stock': 925, 'index': 0, 'board': 0} actual={'stock': 925, 'index': 0, 'board': 0}
- P0 passed n3_a1_source_adapter_plan_covers_assets: expected=stock actual=stock
- P0 passed n3_a1_target_tables_no_runtime_names: expected=no *_runtime target table actual=none
- P0 passed n3_a1_target_tables_no_outbox: expected=common_event_outbox absent actual=absent
- P0 passed n3_a1_contract_writes_outbox_false: expected=false actual=false
- P0 passed n3_a1_preflight_no_market_pull_or_write: expected=None actual=None
- P0 passed n3_a1_rollback_sql_does_not_touch_event_outbox: expected=no DML against common_event_outbox actual=absent

## Boundary

- read_only_database_checks: `true`
- will_execute_sql: `false`
- migration_executed: `false`
- writes_performed: `false`
- market_data_pulled: `false`
- market_data_fact_written: `false`
- event_outbox_written: `false`
- downstream_layers_touched: `false`
- worker_started: `false`
- old_system_touched: `false`

## Rollback

Rollback SQL was generated at `sql/N3_20260615_action_confirmation_previous_day_preload_until_1458_rollback.sql`. It deletes rows by `source_run_id` and `preload_run_id` and does not touch `common_event_outbox`.
