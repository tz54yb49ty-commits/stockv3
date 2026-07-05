# N3 Market Data Historical Replay Pull Policy Dry Run

Status: DRY_RUN_PASS

Generated at: 2026-06-07T16:19:27+08:00

## Live Subscription Proof

```text
subscription_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
status=passed
P0/P1/P2=0/0/0
market_data_pulled=false
market_data_fact_written=false
downstream_layers_touched=false
worker_started=false
```

## Pull Plan Proof

```text
pull_plan rows=9
execute_allowed=false: 9/9
plan_status=planned: 9/9
lineage_fields_preserved=true
```

Distribution:

| required_data_kind | data_trade_date | stock | index | board | total |
|---|---|---:|---:|---:|---:|
| realtime_daily_snapshot | 20260529 | 2011 | 83 | 428 | 2522 |
| minute_bar_1m | 20260529 | 234 | 3 | 19 | 256 |
| previous_day_minute_bar_1m | 20260528 | 234 | 3 | 19 | 256 |

## Facts And Downstream Baseline

All scoped refs are zero:

```text
stock/index/board realtime_daily_snapshot rows=0/0/0
stock/index/board minute_bar_1m rows=0/0/0
stock/index/board previous_day_minute_preload_status rows=0/0/0
stock/index/board realtime_projection_metric refs=0/0/0
outbox/inbox/checkpoint refs=0/0/0
N4/N5 refs=0
total_refs=0
```

## Calendar And Freshness Proof

```text
20260528: is_open=true, prev=20260527, next=20260529
20260529: is_open=true, prev=20260528, next=20260601
current_date=20260607
current_date_equals_for_trade_date=false
days_after_for_trade_date=9
ordinary_realtime_daily_snapshot_execute_blocked=true
```

## Policy Dry Run Decision

Recommended path: A_SPLIT_GATE.

```text
previous_day_minute_bar_1m -> ALLOW_HISTORICAL_PRELOAD_CONTRACT
minute_bar_1m -> ALLOW_HISTORICAL_CLOSED_MINUTE_REPLAY_CONTRACT_WITH_CUTOFF
realtime_daily_snapshot -> BLOCK_ORDINARY_REALTIME_UNLESS_HISTORICAL_SNAPSHOT_ADAPTER_CONTRACT
```

## Side Effects

```text
database_written=false
pull_executed=false
market_data_pulled=false
facts_written=false
outbox_written_or_consumed=false
inbox_or_checkpoint_updated=false
worker_started=false
entered_n4_n5_n6=false
old_system_touched=false
```

## P0/P1/P2

```text
P0=0
P1=2
P2=0
```

P1 notes:

- Ordinary realtime snapshot is blocked by date policy.
- Today minute replay requires a closed-minute cutoff contract before execute.

## Next Gate Recommendation

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_CONTRACT_GATE_FOR_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
```

Optional later gate:

```text
N3_TODAY_MINUTE_HISTORICAL_CLOSED_MINUTE_REPLAY_CONTRACT_GATE_FOR_market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
```
