# N4 Projection Matcher v4 Repair Retry Pending State Persistence Fix Report

## Result

IMPLEMENTATION_PASS

## Scope

Layer role: `N4_trigger`

This gate only repaired N4 projection matcher code, tests, and report artifacts. It did not execute the N4 matcher, did not write business database rows, did not consume or update N3/N4/N5 outbox/inbox/checkpoint, and did not enter N5/N6.

## Root Cause

The v4 repair retry execute was blocked before completion by PostgreSQL:

```text
psycopg.errors.NotNullViolation:
null value in column "trigger_period" of relation "common_trigger_state"
```

The failing row was a `TriggerPendingMarketData` state row:

```text
current_status=pending_market_data
trigger_period=NULL
```

`common_trigger_state.trigger_period` is currently `NOT NULL`. The projection matcher correctly avoided writing `common_trigger_match` for pending rows, but it still writes a state row and outbox event for pending market data. The state write therefore needs a schema-compatible period value.

## Persistence Strategy

For `TriggerPendingMarketData` in the projection matcher execute path:

- persist `common_trigger_state.trigger_period=30m` when `projection_period=30m`
- keep `current_status=pending_market_data`
- keep `trigger_live=false`
- keep `n5_entry_allowed=false`
- do not write `common_trigger_match`
- do not treat the row as a N5 entry
- keep `triggered_periods=[]`
- keep `all_trigger_periods=[]`
- keep `primary_trigger_period=null`

This is a projection-state persistence compatibility rule, not a formal-period rule.

## v4 Semantic Proof

The fix does not relax `TriggerMatched` enforcement:

- ordinary `trigger_kind=trigger` with `trigger_period=30m` still blocks before write
- HINT `trigger_kind=hint` with `condition_key=BUY_HINT/SELL_HINT` may use `TriggerMatched.trigger_period=30m`
- `30m` remains forbidden in `triggered_periods`, `all_trigger_periods`, and `primary_trigger_period`
- `TriggerPendingMarketData` remains non-N5-entry

## Modified Files

- `src/ashare_v3/trigger/projection_matcher_execute.py`
- `tests/test_trigger_projection_matcher_execute.py`
- `docs/N4_PROJECTION_MATCHER_V4_REPAIR_RETRY_PENDING_STATE_PERSISTENCE_FIX_REPORT.md`
- `docs/N4_PROJECTION_MATCHER_V4_REPAIR_RETRY_PENDING_STATE_PERSISTENCE_FIX_REPORT.json`

## Tests And Validation

Passed:

- `PYTHONPATH=src python3 -m unittest tests.test_trigger_projection_matcher_execute.TriggerProjectionMatcherExecuteTest.test_pending_market_data_state_uses_projection_period_for_schema_compatibility`
- `PYTHONPATH=src python3 -m unittest tests.test_trigger_projection_matcher_execute`
- `PYTHONPATH=src python3 -m unittest tests.test_trigger_projection_matcher_execute tests.test_n4_v4_enforcement`
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger_projection_matcher*.py'`
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'`
- `python3 -m compileall scripts src tests`
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`
- static scan for pending compatibility branch and regression tests

Passed final mechanical checks after report creation:

- JSON parse of this report
- `git diff --check`

## Forbidden Scope Proof

This gate did not:

- execute N4 matcher
- write business DB rows
- consume or update N3 outbox/inbox/checkpoint
- enter N5/N6
- start worker
- perform delivery/push/voice/mobile
- perform sim/position/pnl/real trade
- perform proposal/order/trade
- touch old system

## Next Gate

Allowed to return to runtime_control for:

```text
N4_PROJECTION_MATCHER_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_REGENERATION_GATE
```
