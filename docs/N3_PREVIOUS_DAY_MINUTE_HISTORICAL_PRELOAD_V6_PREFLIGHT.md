# N3 Previous-Day Minute Historical Preload V6 Preflight

Status: PREFLIGHT_PASS

Generated at: 2026-06-07T16:30:24+08:00

## Executable Contract Fields

The current N3-A1 previous-day preload runner reads a contract file. This preflight artifact keeps the runner-required schema:

```text
stage=N3-A1-preflight
layer_role=N3_market_data
source_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
preload_run_id=previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
source_condition_run_id=condition_layer_20260528_source_20260528_v6
for_trade_date=20260529
source_trade_date=20260528
previous_day_minute_date=20260528
writes_outbox=false
writes_event_outbox=false
```

## Checks

```text
subscription_run_exists_and_passed=true
pull_plan_previous_day_rows_equal_3=true
object_counts_match_contract=true
execute_allowed_currently_false=true
preload_target_baseline_zero=true
downstream_refs_zero=true
historical_preload_policy_allows_data_trade_date=true
no_outbox_policy=true
rollback_sql_exists=true
```

## Planned Writes

```text
common_market_data_run=1
common_market_data_quality_item=12
stock_minute_bar_1m=56160
index_minute_bar_1m=720
board_minute_bar_1m=4560
stock_previous_day_minute_preload_status=234
index_previous_day_minute_preload_status=3
board_previous_day_minute_preload_status=19
common_event_outbox=0
```

## P0/P1/P2

```text
P0=0
P1=1
P2=0
```

P1 is limited to direct CLI alias support. The contract-path runner command is double-confirm guarded.

## Forbidden Scope Proof

```text
database_written=false
preload_executed=false
market_data_pulled=false
minute_rows_written=false
preload_status_written=false
outbox_written=false
outbox_consumed_or_updated=false
inbox_or_checkpoint_updated=false
worker_started=false
entered_n4_n5_n6=false
rollback_sql_executed=false
old_system_touched=false
```
