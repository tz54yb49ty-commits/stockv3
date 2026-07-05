# N3-B1 Realtime Daily Snapshot Execute Readiness

## Summary

- stage: `N3-B1-readiness-gate`
- layer_role: `N3_market_data`
- ready: `false`
- blocked_reason: `n3_b1_readiness_contract_clean`
- current_date: `20260602`
- for_trade_date: `None`
- source_run_id: `market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`
- snapshot_run_id: `realtime_snapshot_20260602_condition_layer_20260601_source_20260601_v1`
- preload_run_id: `previous_day_minute_preload__for___market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1`
- P0/P1/P2: `6/0/0`

## Readiness Inputs

- calendar_row_count: `0`
- is_trade_date: `False`
- snapshot_existing_row_count: `0`
- outbox_existing_row_count: `0`

## Preload Status Counts

- stock: passed=`0` partial=`0` missing=`0` failed=`0` total=`0`
- index: passed=`0` partial=`0` missing=`0` failed=`0` total=`0`
- board: passed=`0` partial=`0` missing=`0` failed=`0` total=`0`

## Quality

- P0 failed n3_b1_readiness_contract_clean: expected=stage=N3-B1-preflight P0=0 actual=stage=N3-B1-preflight P0=3
- P0 passed n3_b1_readiness_source_run_matches_contract: expected=market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1 actual=market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1
- P0 passed n3_b1_execute_runner_ready_for_contract: expected=runner_exists=true execute_final_gate_allowed=true actual=runner_exists=True execute_final_gate_allowed=True reason=None
- P0 failed n3_b1_current_date_equals_for_trade_date: expected= actual=20260602
- P0 failed n3_b1_trade_calendar_row_exists: expected=trade_date= actual=row_count=0
- P0 failed n3_b1_trade_calendar_is_open: expected=is_open=true actual=is_open=False
- P0 failed n3_b1_source_subscription_run_passed: expected=status=passed P0=0 actual=missing
- P0 failed n3_b1_previous_day_preload_completed: expected=status=passed P0=0 preload_status_rows>0 actual=missing preload_status_rows=0
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
