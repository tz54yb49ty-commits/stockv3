# N3 Market Data Subscription Rebuild V6 Dry Run

Status: DRY_RUN_PASS

```text
source_condition_run_id=condition_layer_20260528_source_20260528_v6
market_data_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
source_trade_date=20260528
for_trade_date=20260529
prev_trade_date=20260528
source_scope rows stock/index/board=4251/169/875 total=5295
objects stock/index/board=2011/83/428 total=2522
candidate/subscription/pull_plan=5807/3034/9
required_data_kind realtime/minute/previous=2522/256/256
P0/P1/P2=0/0/0
```

## Dedup

```text
dedup_ratio=0.522473
dedup_reduction_ratio=0.477527
subscription_row_count <= candidate_row_count: 3034 <= 5807
```

## Required Data Kind

```json
{
  "minute_bar_1m": 256,
  "previous_day_minute_bar_1m": 256,
  "realtime_daily_snapshot": 2522
}
```

Dry-run JSON artifact includes candidate/subscription/pull_plan planned rows and samples.
