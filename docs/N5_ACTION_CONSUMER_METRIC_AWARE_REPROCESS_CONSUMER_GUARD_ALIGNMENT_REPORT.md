# N5 Action Consumer Metric-Aware Reprocess Consumer Guard Alignment Report

Result: **ALIGNMENT_PASS**

This gate aligned the N5 run-once dry-run and execute contract consumer guard so the 20260608 until 09:52 metric-aware rerun can use a reviewed dedicated reprocess consumer:

```text
n5_action_consumer_v1_until_0952_metric_aware_reprocess
```

No N5 execute was run, no database business rows were written, no N4 outbox was consumed or updated, N6 was not entered, no worker was started, and no delivery/push/voice/mobile/sim/position/PnL/real-trade/proposal/order/trade path was touched.

## Root Cause

Runtime control blocked the final gate with:

```text
blocker=n5_5_consumer_name_contract
```

The old guard required:

```text
consumer_name == n5_action_consumer_v1
```

That is wrong for this 09:52 replay because the default consumer already has a later watermark and would skip most 09:52 events. The correct route is a dedicated reprocess consumer, but only when it is explicitly declared and empty.

## Guard Contract

Default consumer remains legal:

```text
n5_action_consumer_v1
```

Dedicated reprocess consumer is legal only when all conditions hold:

```text
consumer_strategy.uses_dedicated_consumer=true
consumer_strategy.dedicated_consumer_name == current consumer_name
source_trigger_run_id matches current source_trigger_run_id
metric_run_id / n3_action_metric_run_id / action_metric_run_id is present
dedicated consumer live inbox refs=0
dedicated consumer live checkpoint refs=0
```

Still blocked:

```text
arbitrary consumer without baseline declaration
dedicated consumer name mismatch
source_trigger_run_id mismatch
missing metric run binding
dedicated consumer with existing inbox/checkpoint refs
```

## Code Changes

```text
src/ashare_v3/action/run_once_dry_run.py
  - added build_consumer_guard
  - added consumer_guard to dry-run report
  - changed n5_5_consumer_name_contract to use default-or-declared-dedicated policy

src/ashare_v3/action/execute.py
  - added n5_execute_consumer_guard P0 quality item
  - execute contract now blocks arbitrary consumers too

tests/test_action_dry_run.py
  - default consumer PASS
  - declared dedicated reprocess consumer PASS
  - arbitrary consumer BLOCK
  - dedicated consumer with existing inbox/checkpoint BLOCK

tests/test_action_execute.py
  - declared dedicated reprocess consumer execute contract PASS
  - arbitrary consumer execute contract BLOCK
```

## Smoke Proof

Read-only smoke artifact:

```text
docs/N5_ACTION_CONSUMER_METRIC_AWARE_REPROCESS_CONSUMER_GUARD_ALIGNMENT_SMOKE.json
docs/N5_ACTION_CONSUMER_METRIC_AWARE_REPROCESS_CONSUMER_GUARD_ALIGNMENT_SMOKE.md
```

Key result:

```text
passed=true
P0/P1/P2=0/0/0
read_event_count=3920
baseline_read_event_count=3920
consumer_guard.passed=true
consumer_guard.strategy=dedicated_reprocess
n5_5_consumer_name_contract=passed
inbox_ref_count=0
checkpoint_ref_count=0
before/after row counts unchanged=true
```

## Validation

```text
focused consumer guard tests=PASS
focused execute guard tests=PASS
PYTHONPATH=src python3 -m unittest tests/test_action_dry_run.py tests/test_action_execute.py = PASS
python3 -m compileall src/ashare_v3/action scripts tests = PASS
JSON parse = required
git diff --check = required
```

## Forbidden Scope Proof

```text
N5 execute=false
database_written=false
N4 outbox consumed/updated=false
N5 inbox/checkpoint written=false
entered_N6=false
worker_started=false
delivery/push/voice/mobile=false
sim/position/pnl/real_trade=false
proposal/order/trade=false
old_system_touched=false
```

## Decision

Allow re-entering:

```text
N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_METRIC_AWARE_RERUN_CONTRACT_PREFLIGHT_GATE
```
