# N3-A1 Previous-Day Minute Execute Preflight

## Summary

- result: `PREFLIGHT_PASS`
- stage: `N3-A1-execute-preflight`
- layer_role: `N3_market_data`
- source_run_id: `market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1`
- preload_run_id: `previous_day_minute_preload_20260604_for_20260605_action_metric_board_lineage_repair__market_data_subscription_20260605_action_metric_board_lineage_repair_condition_layer_20260604_source_20260604_v1`
- source_condition_run_id: `condition_layer_20260604_source_20260604_v1`
- for_trade_date: `20260605`
- previous_day_minute_date: `20260604`
- expected_row_count: `6720`
- expected_bar_count_per_object: `240`
- writes_outbox: `False`
- execute_authorized: `False`
- P0/P1/P2: `0/0/0`

## Expected Asset Counts

- stock: objects=`0` subscriptions=`0` expected_minute_rows=`0`
- index: objects=`0` subscriptions=`0` expected_minute_rows=`0`
- board: objects=`28` subscriptions=`28` expected_minute_rows=`6720`

## Baseline Guard

- common_market_data_run: `0`
- common_market_data_quality_item: `0`
- common_event_outbox: `0`
- common_event_inbox: `0`
- common_event_consumer_checkpoint: `0`
- stock_minute_bar_1m: `0`
- stock_previous_day_minute_preload_status: `0`
- index_minute_bar_1m: `0`
- index_previous_day_minute_preload_status: `0`
- board_minute_bar_1m: `0`
- board_previous_day_minute_preload_status: `0`
- total: `0`

## Allowed Future Writes

- `common_market_data_run`
- `common_market_data_quality_item`
- `stock_minute_bar_1m`
- `index_minute_bar_1m`
- `board_minute_bar_1m`
- `stock_previous_day_minute_preload_status`
- `index_previous_day_minute_preload_status`
- `board_previous_day_minute_preload_status`

## Forbidden

- `stock_realtime_daily_snapshot`
- `index_realtime_daily_snapshot`
- `board_realtime_daily_snapshot`
- `stock_realtime_projection_metric`
- `index_realtime_projection_metric`
- `board_realtime_projection_metric`
- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- `trigger tables`
- `action tables`
- `user tables`
- `voice/mobile/sim/position tables`
- `worker`
- `old system`
- `real trading`

## Quality

- P0 passed n3_a1_contract_stage_valid: expected=N3-A1-preflight actual=N3-A1-preflight
- P0 passed n3_a1_contract_p0_zero: expected=0 actual=0
- P0 passed n3_a1_preload_scoped_baseline_zero: expected=0 actual=0
- P0 passed n3_a1_preflight_writes_outbox_false: expected=false actual=false
- P0 passed n3_a1_preflight_no_execute_authorization: expected=execute_authorized=false actual=false

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

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py --contract-path docs/N3_A1_BOARD_MINUTE_LINEAGE_PULL_EXECUTE_CONTRACT.json --execute --user-confirmed
```

- execute_runner: `scripts/run_previous_day_minute_preload_execute.py`
- execute_requires_flags: `--execute, --user-confirmed`
- This preflight artifact is not execute authorization.

## Rollback

- rollback_sql_path: `sql/N3_A1_board_minute_lineage_pull_20260605_rollback.sql`
- rollback guard requires scoped outbox/inbox/checkpoint refs to remain zero.
