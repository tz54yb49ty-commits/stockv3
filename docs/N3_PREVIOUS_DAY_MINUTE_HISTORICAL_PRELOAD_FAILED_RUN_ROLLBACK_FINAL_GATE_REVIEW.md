# N3 Previous-Day Minute Historical Preload Failed Run Rollback Final Gate Review

Result: PASS

Generated at: 2026-06-07T16:30:24+08:00

## Target

```text
target_preload_run_id=previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
source_subscription_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
source_condition_run_id=condition_layer_20260528_source_20260528_v6
data_trade_date=20260528
```

This runtime_control gate reviewed rollback readiness only. It did not execute rollback SQL and did not write the database.

## Live Failed Run Proof

```text
run_exists=true
run_status=failed
P0/P1/P2=1/2/0
market_data_pulled=true
market_data_fact_written=false
downstream_layers_touched=false
worker_started=false
quality_rows=12
```

Rows:

```text
minute rows stock/index/board/total=0/0/0/0
preload status rows stock/index/board/total=234/3/19/256
status distribution=missing for all 256 objects
```

## Downstream Refs Proof

```text
common_event_outbox=0
common_event_inbox=0
common_event_consumer_checkpoint=0
stock/index/board realtime projection refs=0/0/0
N4 refs=0
N5 refs=0
N6 projection/signal/card refs=0/0/0
notification refs=0
```

## Rollback Scope

Expected live delete scope:

```text
common_market_data_run=1
common_market_data_quality_item=12
stock_previous_day_minute_preload_status=234
index_previous_day_minute_preload_status=3
board_previous_day_minute_preload_status=19
stock/index/board_minute_bar_1m=0/0/0
```

Forbidden delete scope:

```text
common_market_data_pull_plan
common_market_data_subscription
common_market_data_subscription_candidate
source subscription run
N2 v6 condition rows
outbox/inbox/checkpoint
N4/N5/N6 rows
old system
```

## Rollback Static Check

```text
rollback_sql_path=sql/N3_previous_day_minute_historical_preload_v6_rollback.sql
hard-fail before first DELETE/UPDATE=true
no CASCADE/DROP/TRUNCATE=true
does not delete subscription control rows=true
guards event infra refs=true
guards projection refs=true
guards N4/N5/N6 refs=true
```

## Allowed Rollback Command

```text
psql postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3 \
  -v ON_ERROR_STOP=1 \
  -f sql/N3_previous_day_minute_historical_preload_v6_rollback.sql
```

Note: the rollback SQL intentionally contains a hard-fail `RAISE EXCEPTION` before mutation. Execution requires explicit user confirmation and removal/override under the N3 rollback user-confirmation gate.

## Approved Scope

```text
rollback only failed N3 previous-day preload evidence for target preload_run_id
restore clean target baseline for retrying same preload_run_id after adapter/window repair
```

## Blocked Scope

```text
rollback source subscription control rows
rollback N2 v6 condition rows
consume/update outbox/inbox/checkpoint
enter N4/N5/N6
start worker
delivery/push/voice/mobile
sim/position/pnl/real_trade
proposal/order/trade
old system
```

## P0/P1/P2

```text
P0=0
P1=0
P2=0
```

## Next Gate

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_FAILED_RUN_ROLLBACK_USER_CONFIRMATION_GATE
```
