# N3-B1 Realtime Daily Snapshot Execute Readiness

## Summary

- stage: `N3-B1-readiness-gate`
- layer_role: `N3_market_data`
- ready: `false`
- blocked_reason: `current_date_after_for_trade_date`
- current_date: `20260617`
- for_trade_date: `20260616`
- source_run_id: `market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- snapshot_run_id: `realtime_daily_snapshot_20260616_until_1401__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- preload_run_id: `previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4`
- P0/P1/P2: `1/0/0`

## Readiness Inputs

- calendar_row_count: `1`
- is_trade_date: `True`
- snapshot_existing_row_count: `0`
- outbox_existing_row_count: `0`

## Preload Status Counts

- stock: passed=`550` partial=`0` missing=`0` failed=`0` total=`550`
- index: passed=`17` partial=`0` missing=`0` failed=`0` total=`17`
- board: passed=`53` partial=`0` missing=`0` failed=`0` total=`53`

## Quality

- P0 passed n3_b1_readiness_contract_clean: expected=stage=N3-B1-preflight P0=0 actual=stage=N3-B1-preflight P0=0
- P0 passed n3_b1_readiness_source_run_matches_contract: expected=market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 actual=market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4
- P0 passed n3_b1_execute_runner_ready_for_contract: expected=runner_exists=true execute_final_gate_allowed=true actual=runner_exists=True execute_final_gate_allowed=True reason=None
- P0 failed n3_b1_current_date_equals_for_trade_date: expected=20260616 actual=20260617
- P0 passed n3_b1_trade_calendar_row_exists: expected=trade_date=20260616 actual=row_count=1
- P0 passed n3_b1_trade_calendar_is_open: expected=is_open=true actual=is_open=True
- P0 passed n3_b1_source_subscription_run_passed: expected=status=passed P0=0 actual=run_id=market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 status=passed P0=0
- P0 passed n3_b1_previous_day_preload_completed: expected=status=passed P0=0 preload_status_rows>0 actual=run_id=previous_day_minute_preload_20260615_for_20260616__market_data_subscription_20260616_condition_layer_20260615_source_20260615_for_20260616_v4 status=passed P0=0 preload_status_rows=620
- P1 passed n3_b1_previous_day_preload_missing_carried: expected=0 actual=0
- P0 passed n3_b1_snapshot_run_id_not_previously_executed: expected=no existing snapshot run, fact rows, or outbox rows actual=run_exists=False snapshot_rows=0 outbox_rows=0
- P1 passed n3_b1_repeat_requires_idempotent_review: expected=no repeat actual=allow_repeat_idempotent=False
- P0 passed n3_b1_readiness_no_market_pull_or_write: expected=read-only actual=read-only

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
