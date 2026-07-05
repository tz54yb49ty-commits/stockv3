# N2 Final Condition Layer Closure

## Summary

N2 条件层在 v3 开发库中已经完成闭环：

```text
condition_basis: generated and executable
condition_pool: generated with default selection policy
minute_target_scope: generated from condition_pool
active condition run: passed
scope consumption contract: documented
```

N2 条件层到此收口。后续 `market_data_subscription_candidate`、`market_data_subscription_dedup`、`market_data_pull_plan`、`previous_day_minute_bar_1m preload`、`realtime_daily_snapshot`、`minute_bar_1m` 均属于 N3 实时行情层，不再算条件层任务。

## Active Run

```text
active_run_id=condition_layer_20260522_to_20260525_20260523223042_execute
previous_active_run_id=condition_layer_20260522_to_20260525_20260523191307_execute
previous_active_run_status=superseded
active_run_status=passed
active_passed_run_count=1
```

Dates:

```text
source_trade_date=20260522
for_trade_date=20260525
prev_trade_date=20260522
```

Source versions:

```text
stock_daily=stock_daily_20260522_v1
stock_daily_basic=stock_daily_basic_20260522_v1
stock_financial=stock_financial_20260522_v2
index_daily=index_daily_20260522_v1
index_membership=index_membership_20260522_v1
board_daily=board_daily_20260522_v1
board_membership=board_membership_20260522_v1
```

## Final Row Counts

Rows written for the active run:

```text
common_condition_run=1
common_condition_quality_item=67

stock_monitor_target=5504
index_monitor_target=80
board_monitor_target=428

stock_condition_basis=5504
index_condition_basis=80
board_condition_basis=428

stock_condition_pool=7384
index_condition_pool=26
board_condition_pool=465

stock_minute_target_scope=7384
index_minute_target_scope=26
board_minute_target_scope=465
```

Schema status after N2-E10:

```text
migration_required=false
missing_column_count=0
type_mismatch_count=0
not_null_risk_count=0
constraint_deferred_count=0
```

## Quality Status

N2-E10 preflight quality:

```text
P0=0
P1=5
P2=3
```

Post-execute active run audit:

```text
P0=0
P1=0
P2=0
needs_remediation=false
```

The remaining P1/P2 items from preflight are recorded quality notes, not blockers for the active run:

```text
P1: for_trade_calendar_row_missing was tolerated as a known calendar-detail gap.
P1: amount baseline coverage gaps remain reportable samples.
P2: static structure coverage gaps remain reportable samples where targets/anchors are not safely inferable.
```

## Default Condition Pool Policy

Policy:

```text
policy_name=default_scope_policy
policy_hash=2f42483ab68688fd5cd3f79b00d1c1fdc6efc42eaae345ff41ce5c71fdab44ec
```

Default selection:

```text
index_condition_pool:
  fixed index universe only:
  000905, 399303, 000001, 000852, 399001, 399006, 000300, 000016, 000688
  only objects with eligible condition_pool rows enter the active pool

board_condition_pool:
  board_code LIKE '881%'
  only eligible industry board rows enter the active pool

stock_condition_pool:
  eligible ordinary BUY/SELL, BUY:FULL/SELL:FULL, BUY_HINT/SELL_HINT condition rows
  total_mv >= 1,000,000 万元
  non-ST / non-risk
  official daily proof exists
  financial snapshot basic fields available
  lane / monitor_type valid
```

Post-execute pool audit:

```text
index_condition_pool:
  objects=8
  rows=26
  out_of_range_rows=0

board_condition_pool:
  objects=127
  rows=465
  out_of_range_rows=0

stock_condition_pool:
  objects=2052
  rows=7384
  out_of_range_rows=0
```

## Minute Target Scope

`minute_target_scope` is generated from the active `condition_pool`.

Post-execute scope audit:

```text
index_minute_target_scope:
  objects=8
  rows=26
  scope_source={condition_pool: 26}
  pool_link_violations=0

board_minute_target_scope:
  objects=127
  rows=465
  scope_source={condition_pool: 465}
  pool_link_violations=0

stock_minute_target_scope:
  objects=2052
  rows=7384
  scope_source={condition_pool: 7384}
  pool_link_violations=0
  market_value_violations=0
```

Scope grain:

```text
asset_kind + identity_key + direction + condition_key
```

This is a condition-source/audit grain. For example:

```text
index_minute_target_scope=26
index objects=8
```

The 26 rows preserve condition provenance; they do not mean the market data layer should pull index data 26 times.

## Scope Consumption Contract

N2-F fixed the boundary:

```text
minute_target_scope = condition-source detail table
market_data_subscription = realtime market data layer deduped pull task
```

N3 must consume scope by first producing:

```text
minute_target_scope
-> market_data_subscription_candidate
-> market_data_subscription_dedup
-> market_data_pull_plan
```

Dedup grain:

```text
asset_kind + identity_key + required_data_kind + for_trade_date
```

Required data kinds:

```text
realtime_daily_snapshot
minute_bar_1m
previous_day_minute_bar_1m
```

N3 must preserve:

```text
source_scope_ids
source_condition_pool_ids
```

Forbidden:

```text
P0: market data layer pulls one request per minute_target_scope detail row.
P0: market data layer expands objects outside condition_pool / minute_target_scope.
P0: trigger/action/user layer directly calls external market data APIs.
P0: condition layer pulls realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m.
```

## Rollback

Manual rollback SQL for the N2-E10 overwrite:

```text
sql/N2_E10_condition_layer_overwrite_rollback.sql
```

Rollback intent:

```text
1. Delete rows for execute_run_id=condition_layer_20260522_to_20260525_20260523223042_execute.
2. Restore condition_layer_20260522_to_20260525_20260523191307_execute to status=passed.
3. Verify exactly one passed active run remains for 20260522 -> 20260525.
```

Rollback has not been executed.

## N3-0 Inputs

N3-0 should start from:

```text
active_run_id=condition_layer_20260522_to_20260525_20260523223042_execute
for_trade_date=20260525
prev_trade_date=20260522

stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
```

N3-0 first deliverable should be read-only:

```text
market_data_subscription dry-run / preflight
```

It should output:

```text
source_scope_row_count
subscription_row_count
subscription_object_count
required_data_kind_counts
dedup_ratio
source_scope_ids_sample
P0/P1/P2
```

N3-0 must not pull market data until its own preflight contract is reviewed.

## Boundary Confirmation

N2 final closure confirms:

```text
old_system_touched=false
market_data_pulled=false
minute_kline_pulled=false
trigger_layer_entered=false
action_layer_entered=false
voice_mobile_sim_worker_entered=false
```

Condition layer responsibilities are complete for this phase.
