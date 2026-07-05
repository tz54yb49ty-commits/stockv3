# N4 HINT 30m Trigger Period Semantic Repair Implementation Report

## Result

IMPLEMENTATION_PASS

Generated at: 2026-06-08T15:39:51+08:00

Layer role: `N4_trigger`

## Scope

This gate repaired code, tests, and report artifacts only.

It did not execute N4 matcher, did not write business DB rows, did not execute rollback, did not consume/update outbox/inbox/checkpoint, did not enter N5/N6 execute, and did not start workers.

## Old Overbroad Rule

The previous N4 projection matcher v4 enforcement repair used an overbroad rule:

```text
TriggerMatched globally forbids trigger_period=30m.
```

That correctly blocked ordinary projection-only breaches, but it was too strict for HINT semantics.

## Corrected Semantic Rule

Ordinary triggers and HINT triggers use different period semantics:

```text
ordinary trigger_kind=trigger:
  trigger_period must be Y/Q/M/W/D
  triggered_periods / all_trigger_periods / primary_trigger_period must be Y/Q/M/W/D only
  30m projection-only must not write TriggerMatched

HINT trigger_kind=hint:
  condition_key must be BUY_HINT / SELL_HINT
  TriggerMatched.trigger_period may be 30m
  triggered_periods=[]
  all_trigger_periods=[]
  primary_trigger_period=null
  projection_period=30m
  projection_30m_flag=true
  trigger_price is required
  n5_entry_allowed=true
```

30m remains forbidden in:

```text
triggered_periods
all_trigger_periods
primary_trigger_period
```

## BUY_HINT Matched Contract

```text
event_type=TriggerMatched
signal_type=B_BUY
condition_key=BUY_HINT
original_condition_key=BUY_HINT
trigger_kind=hint
trigger_period=30m
trigger_price=<N3 approved projection price>
trigger_live=true
current_status=matched
n5_entry_allowed=true
projection_period=30m
projection_30m_flag=true
projection_30m_type=volume_up
trigger_mark_candidate=30m_volume
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
```

## SELL_HINT Matched Contract

```text
event_type=TriggerMatched
signal_type=S_SELL
condition_key=SELL_HINT
original_condition_key=SELL_HINT
trigger_kind=hint
trigger_period=30m
trigger_price=<N3 approved projection price>
trigger_live=true
current_status=matched
n5_entry_allowed=true
projection_period=30m
projection_30m_flag=true
projection_30m_type=shrink_down
trigger_mark_candidate=30m_shrink
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
```

## N4 Implementation Summary

- `src/ashare_v3/trigger/v4_enforcement.py`
  - Allows `trigger_period=30m` only for `trigger_kind=hint` with `condition_key=BUY_HINT / SELL_HINT`.
  - Still blocks ordinary `trigger_kind=trigger` with `trigger_period=30m`.
  - Still blocks any `30m` in `triggered_periods / all_trigger_periods / primary_trigger_period`.
  - Adds HINT projection checks for `projection_period`, `projection_30m_flag`, `projection_30m_type`, and `trigger_mark_candidate`.

- `src/ashare_v3/trigger/projection_matcher.py`
  - Emits `trigger_period=30m` for valid HINT `TriggerMatched`.
  - Keeps HINT formal period sets empty/null.
  - Keeps ordinary projection-only BUY/SELL as pending, not matched.

- `src/ashare_v3/trigger/projection_matcher_execute.py`
  - Preserves valid HINT `trigger_period=30m` in state/match/outbox payload.
  - Continues normalizing ordinary trigger periods to Y/Q/M/W/D only.
  - Continues omitting `action_mark` from N4 payload.

- `src/ashare_v3/events/models.py`
  - Updates shared N5 trigger fact passthrough validation as a pure guard.
  - Accepts HINT `trigger_period=30m` with empty formal periods.
  - Rejects ordinary `trigger_period=30m`.
  - Rejects any `30m` in formal period-set fields.

## N5 Guard Status

N5 execute was not run and N5 business code was not executed.

The shared event contract pure guard now supports the corrected HINT semantics:

```text
accept:
  trigger_kind=hint
  condition_key=BUY_HINT / SELL_HINT
  trigger_period=30m
  triggered_periods=[]
  all_trigger_periods=[]
  primary_trigger_period=null

reject:
  trigger_kind=trigger + trigger_period=30m
  any 30m in triggered_periods/all_trigger_periods/primary_trigger_period
```

If runtime_control requires N5 dry-run / execute runner input gating beyond shared event contract validation, that should proceed under a separate `layer_role=N5_action` gate.

## Tests Added / Updated

- Ordinary BUY/SELL `TriggerMatched` with `trigger_period=30m` blocks.
- Ordinary BUY/SELL with `30m` in formal period-set fields blocks.
- `BUY_HINT TriggerMatched` with `trigger_period=30m` and empty formal periods passes.
- `SELL_HINT TriggerMatched` with `trigger_period=30m` and empty formal periods passes.
- HINT missing `trigger_price` blocks.
- HINT missing/false `n5_entry_allowed` blocks.
- HINT with `primary_trigger_period=30m` blocks.
- HINT with `all_trigger_periods=["30m"]` blocks.
- Runtime `signal_type=BUY_HINT/SELL_HINT` remains invalid.
- Payload emits `trigger_mark_candidate`, not `action_mark`.
- `TriggerPendingMarketData` still does not write `common_trigger_match`.
- Shared N5 guard accepts HINT 30m and rejects ordinary 30m.

## Validation Summary

Passed:

- `PYTHONPATH=src python3 -m unittest tests.test_n4_v4_enforcement tests.test_trigger_projection_matcher tests.test_trigger_projection_matcher_execute`
- `PYTHONPATH=src python3 -m unittest tests.test_action_event_contract`
- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_trigger_projection_matcher*.py'`
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_n4*.py'`
- `PYTHONPATH=src:scripts python3 -m unittest discover -s tests -p 'test_trigger*.py'`
- `python3 -m compileall scripts src tests`
- `PYTHONPATH=src python3 scripts/check_n4_contract.py`

Pending final mechanical checks after report write:

- JSON parse for this report
- `git diff --check`

## Forbidden Scope Proof

- `n4_matcher_execute=false`
- `business_database_write=false`
- `rollback_execute=false`
- `n3_n4_n5_outbox_inbox_checkpoint_consumed_or_updated=false`
- `n5_n6_execute=false`
- `worker_started=false`
- `delivery_push_voice_mobile=false`
- `sim_position_pnl_real_trade=false`
- `proposal_order_trade=false`
- `old_system_touched=false`

## Next Gate

Allowed next route:

```text
runtime_control -> N4_HINT_30M_TRIGGER_PERIOD_SEMANTIC_REPAIR_POST_REVIEW_GATE
```

N4 projection matcher execute remains blocked until runtime_control post-review and refreshed dry-run/preflight/final gate pass.
