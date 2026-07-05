# N3 Previous-Day Minute Historical Preload Failed Run Decision

Result: DECISION_REQUIRED

Generated at: 2026-06-07T16:30:24+08:00

## Current State

```text
source_subscription_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
preload_run_id=previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
data_trade_date=20260528
common_market_data_run.status=failed
P0/P1/P2=1/2/0
failed gate=n3_a1_total_minute_rows_present
```

Live rows:

```text
minute rows stock/index/board/total=0/0/0/0
preload status rows stock/index/board/total=234/3/19/256
quality rows=12
status distribution=missing for all 256 objects
```

Boundary proof:

```text
outbox/inbox/checkpoint refs=0/0/0
N4 refs=0
N5 refs=0
N6 projection/signal/card refs=0/0/0
downstream_layers_touched=false
worker_started=false
```

## Completion Audit

The one-shot closeout cannot be completed under the current no-rollback constraint.

```text
runner guard alignment=complete
execute final gate review=complete
execute attempt=executed but failed quality gate
post-review=blocked
closeout_complete=false
```

Why:

```text
the required preload_run_id already exists with status=failed
the runner blocks dirty preload targets before re-execute
the active objective forbids executing rollback SQL
without rollback or a newly authorized repair run_id, the same preload_run_id cannot be retried into a passed closeout state
```

## Decision Options

Option A: rollback failed run, repair adapter/window policy, then retry the same run id.

```text
requires rollback execution=true
allowed under current objective=false
benefit=preserves original preload_run_id closeout
risk=requires explicit rollback authorization outside current no-rollback constraint
```

Option B: preserve failed evidence and create a new repair run id.

```text
requires rollback execution=false
allowed under current objective=requires new user scope
benefit=no rollback; failed evidence remains auditable
risk=original preload_run_id closeout remains blocked
```

Option C: stop and keep failed evidence.

```text
requires rollback execution=false
allowed under current objective=true
benefit=no additional mutation
risk=N3 previous-day preload v6 remains incomplete
```

## Recommendation

Recommended option:

```text
A_ROLLBACK_FAILED_RUN_THEN_REPAIR_AND_RETRY_SAME_RUN_ID
```

Recommended next gate:

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_FAILED_RUN_ROLLBACK_FINAL_GATE_REVIEW
```

Alternate no-rollback next gate:

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_REPAIR_RUN_CONTRACT_GATE
```

## Repair Hypothesis

Likely cause:

```text
MootdxPreviousDayMinuteAdapter uses mootdx.bars frequency=8 offset=800
requested historical date=20260528
result=0 normalized rows for all 256 objects
```

Required repair topics:

```text
historical minute adapter source and window capability
sample proof for 20260528 stock/index/board identities
no raw K bypass outside reviewed N3 adapter
restored or new clean preload target baseline
rollback SQL for repair run or same-run retry
```

## Rollback Safety

Rollback SQL:

```text
sql/N3_previous_day_minute_historical_preload_v6_rollback.sql
```

Current scoped downstream refs are zero. Rollback was not executed in this gate.

## Forbidden Scope Proof

```text
database_written_by_runtime_control=false
rollback_executed=false
outbox_consumed_or_updated=false
inbox_or_checkpoint_updated=false
worker_started=false
entered_n4_n5_n6=false
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
old_system_touched=false
```
