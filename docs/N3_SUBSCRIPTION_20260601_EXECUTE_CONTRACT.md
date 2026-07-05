# N3 Subscription 20260601 Execute Contract

## Result

```text
CONTRACT_PASS
layer_role = N3_market_data
market_data_run_id = market_data_subscription_20260601_condition_layer_20260529_source_20260529_v6
source_condition_run_id = condition_layer_20260529_source_20260529_v6
source_trade_date = 20260529
for_trade_date = 20260601
prev_trade_date = 20260529
```

## Expected Writes

Future execute may write only N3 subscription control rows:

```text
common_market_data_run = 1
common_market_data_quality_item = dry-run quality item count
common_market_data_subscription_candidate = 6162
common_market_data_subscription = 3319
common_market_data_pull_plan = 9
```

It must not write:

```text
market data facts
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
N4/N5/N6 facts
worker state
old system
real trading
```

## Expected Plan

```text
source_scope_rows = 5216
candidate_rows = 6162
subscription_rows = 3319
subscription_object_count = 2373
required_data_kind_counts = realtime_daily_snapshot=2373, minute_bar_1m=473, previous_day_minute_bar_1m=473
pull_plan_rows = 9
```

## Quality

```text
P0/P1/P2 = 0/1/0
```

P1 warning:

```text
20260601 common_trade_calendar detail row missing.
```

This does not block subscription control-row execute. It must be rechecked before N3-B1 realtime snapshot readiness.

## Rollback

```text
rollback_sql = sql/N3_subscription_20260601_rollback.sql
```
