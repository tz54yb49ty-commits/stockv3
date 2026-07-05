# N3 Previous-Day Minute Historical Preload V6 Contract

Status: CONTRACT_PASS

Generated at: 2026-06-07T16:30:24+08:00

## Scope

This runtime_control gate generates contract artifacts for the historical preload of `previous_day_minute_bar_1m`.

```text
source_subscription_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
source_condition_run_id=condition_layer_20260528_source_20260528_v6
preload_run_id=previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
required_data_kind=previous_day_minute_bar_1m
data_trade_date=20260528
for_trade_date=20260529
```

This gate did not execute preload, did not pull market data, did not write minute/status rows, did not write outbox events, did not consume or update outbox/inbox/checkpoint, did not start workers, did not enter N4/N5/N6, did not execute rollback SQL, and did not touch the old system.

## Input Proof

```text
subscription run exists/status=passed
subscription P0/P1/P2=0/0/0
market_data_pulled=false
market_data_fact_written=false
downstream_layers_touched=false
worker_started=false
pull_plan previous_day_minute_bar_1m rows=3
pull_plan execute_allowed=false: 3/3
pull_plan plan_status=planned: 3/3
object counts stock/index/board/total=234/3/19/256
data_trade_date=20260528
```

Target preload baseline is zero:

```text
common_market_data_run=0
common_market_data_quality_item=0
stock/index/board_minute_bar_1m=0/0/0
stock/index/board_previous_day_minute_preload_status=0/0/0
projection/outbox/inbox/checkpoint/N4/N5/N6 refs=0
```

## Planned Execute Scope

Allowed write tables only:

```text
stock_minute_bar_1m
index_minute_bar_1m
board_minute_bar_1m
stock_previous_day_minute_preload_status
index_previous_day_minute_preload_status
board_previous_day_minute_preload_status
common_market_data_quality_item
common_market_data_run
```

Forbidden in this scope:

```text
realtime snapshot
today minute
common_event_outbox
N4/N5/N6 facts
projection/card/notification
worker
```

## Planned Rows

| Table family | Stock | Index | Board | Total |
|---|---:|---:|---:|---:|
| minute rows | 56160 | 720 | 4560 | 61440 |
| preload status rows | 234 | 3 | 19 | 256 |

Additional planned rows:

```text
common_market_data_run=1
common_market_data_quality_item=12
event_outbox=0
```

## Date And Replay Policy

Historical preload is allowed because:

```text
data_trade_date=prev_trade_date=20260528
for_trade_date=20260529
current_date=20260607
current_date == for_trade_date is not required for previous-day historical preload
explicit historical preload mode is required
live outbox is forbidden
```

Ordinary `realtime_daily_snapshot` remains blocked when `current_date != for_trade_date`.

## Execute Command Candidates

Current runner-compatible command:

```text
PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py \
  --contract-path docs/N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_V6_PREFLIGHT.json \
  --execute --user-confirmed \
  --pre-backup-path docs/N3_previous_day_minute_historical_preload_v6_execute_backup_before.json \
  --post-backup-path docs/N3_previous_day_minute_historical_preload_v6_execute_backup_after.json \
  --json-report-path docs/N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_V6_EXECUTE_REPORT.json \
  --markdown-report-path docs/N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_V6_EXECUTE_REPORT.md
```

Requested direct-alias shape recorded for runner alignment:

```text
PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py \
  --historical-preload \
  --source-subscription-run-id market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6 \
  --preload-run-id previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6 \
  --data-trade-date 20260528 \
  --execute --user-confirmed
```

P1: the current runner does not yet expose the direct aliases above. The semantic fields are present in the contract/preflight artifacts and the current runner remains protected by `--execute --user-confirmed`.

## Rollback Proof

Rollback SQL:

```text
sql/N3_previous_day_minute_historical_preload_v6_rollback.sql
```

Rollback policy:

```text
hard-fail before DELETE/UPDATE
delete only scoped preload minute/status/quality/run rows
do not delete subscription control rows
block if projection/outbox/N4/N5/N6 refs exist
no CASCADE/DROP/TRUNCATE
```

## P0/P1/P2

```text
P0=0
P1=1
P2=0
```

P1 is limited to runner direct-alias alignment; it does not affect the contract-path guarded execution semantics.

## Next Gate

Recommended:

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_RUNNER_GUARD_ALIGNMENT_GATE
```

If the next final gate accepts the current `--contract-path` runner command, it may proceed to:

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_EXECUTE_FINAL_GATE_REVIEW
```
