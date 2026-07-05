# N5 Action Event HINT 30m Passthrough Implementation Report

Result: `IMPLEMENTATION_PASS`

Layer role: `N5_action`

Generated at: `2026-06-08`

## Scope

This gate implements the forward fix for legal N4 HINT 30m trigger fact passthrough into N5 action event payloads.

No N5 runner was executed. No database writes were performed. No N4 outbox rows were consumed or updated. No N5 inbox/checkpoint/action fact/action event/outbox business rows were written. N6, worker, rollback, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal/order/trade, and the old system were not touched.

## Root Cause

The failed retry reached:

```text
build_n5_action_event -> validate_n5_trigger_fact_passthrough_payload
```

The contract failure was:

```text
N5 trigger fact passthrough payload must not include 30m in triggered_periods/all_trigger_periods/primary_trigger_period
```

The N4 HINT 30m payload is legal when it keeps formal trigger periods empty:

```text
trigger_kind=hint
condition_key=BUY_HINT / SELL_HINT
trigger_period=30m
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
```

The bug was in `build_action_event_passthrough_payload`: it reconstructed `primary_trigger_period=30m` by falling back to `row.trigger_period` or `source_payload.trigger_period`.

## Implementation

Changed:

```text
src/ashare_v3/action/execute.py
tests/test_action_execute.py
```

Generated:

```text
docs/N5_ACTION_EVENT_HINT_30M_PASSTHROUGH_IMPLEMENTATION_REPORT.md
docs/N5_ACTION_EVENT_HINT_30M_PASSTHROUGH_IMPLEMENTATION_REPORT.json
```

The forward fix makes `primary_trigger_period` come only from explicit formal primary fields:

```text
row.primary_trigger_period
source_payload.primary_trigger_period
```

It no longer falls back to:

```text
row.trigger_period
source_payload.trigger_period
```

`event_factory.py` was not changed. `events/models.py` guard was not relaxed.

## Regression Proof

The new RED test failed before the fix:

```text
AssertionError: '30m' is not None
```

Regression coverage now confirms:

```text
legal BUY_HINT 30m passthrough PASS
legal SELL_HINT 30m passthrough PASS
HINT 30m primary_trigger_period is not reconstructed as 30m
build_n5_action_event accepts legal HINT 30m passthrough
ordinary trigger_kind=trigger + trigger_period=30m still BLOCKS
30m inside triggered_periods/all_trigger_periods/primary_trigger_period still BLOCKS
TriggerPendingMarketData remains quality-only and creates no action output
```

## Validation

```text
PYTHONPATH=src python3 -m unittest tests/test_action_execute.py
PASS

PYTHONPATH=src python3 -m unittest tests/test_n4_v4_enforcement.py
PASS

PYTHONPATH=src python3 -m unittest tests/test_trigger_projection_matcher_execute.py
PASS

python3 -m compileall src/ashare_v3/action src/ashare_v3/events tests
PASS

python3 -m json.tool docs/N5_ACTION_EVENT_HINT_30M_PASSTHROUGH_IMPLEMENTATION_REPORT.json >/dev/null
PASS

git diff --check
PASS
```

## Boundary Proof

```text
n5_runner_executed=false
database_written=false
n4_outbox_consumed_or_updated=false
action_fact_event_outbox_written=false
n5_inbox_checkpoint_written=false
n6_entered=false
worker_started=false
rollback_sql_executed=false
delivery_push_voice_mobile_touched=false
sim_position_pnl_real_trade_touched=false
proposal_order_trade_touched=false
old_system_touched=false
```

## Recommendation

This implementation is ready for:

```text
N5_ACTION_EVENT_HINT_30M_PASSTHROUGH_IMPLEMENTATION_POST_REVIEW_GATE
```
