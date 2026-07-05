# N3 Previous-Day Minute Historical Preload V6 Dry Run

Status: DRY_RUN_PASS

Generated at: 2026-06-07T16:30:24+08:00

## Live Input Proof

```text
source_subscription_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
status=passed
P0/P1/P2=0/0/0
market_data_pulled=false
market_data_fact_written=false
downstream_layers_touched=false
worker_started=false
```

Previous-day pull plan:

| asset_kind | pull_plan rows | objects | subscriptions | execute_allowed=false |
|---|---:|---:|---:|---|
| stock | 1 | 234 | 234 | true |
| index | 1 | 3 | 3 | true |
| board | 1 | 19 | 19 | true |

## Baseline

```text
preload_run_id=previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
common_market_data_run=0
common_market_data_quality_item=0
stock/index/board_minute_bar_1m=0/0/0
stock/index/board_previous_day_minute_preload_status=0/0/0
outbox/inbox/checkpoint=0/0/0
projection/N4/N5/N6 refs=0
```

## Planned Rows

```text
stock minute rows=234*240=56160
index minute rows=3*240=720
board minute rows=19*240=4560
total minute rows=61440
preload status rows=256
quality rows=12
common_market_data_run=1
outbox rows=0
```

## Calendar Proof

```text
20260528 is_open=true prev=20260527 next=20260529
20260529 is_open=true prev=20260528 next=20260601
current_date=20260607
historical previous-day preload allowed=true
ordinary realtime snapshot still blocked=true
```

## P0/P1/P2

```text
P0=0
P1=1
P2=0
```

P1: direct CLI aliases for the semantic fields are not yet implemented on the current runner; contract-path execution remains double-confirm guarded.

## Forbidden Scope Proof

```text
database_written=false
preload_executed=false
market_data_pulled=false
facts_written=false
outbox_written_or_consumed=false
inbox_or_checkpoint_updated=false
worker_started=false
entered_n4_n5_n6=false
old_system_touched=false
```
