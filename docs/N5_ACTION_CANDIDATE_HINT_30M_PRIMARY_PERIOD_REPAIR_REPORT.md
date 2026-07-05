# N5 Action Candidate HINT 30m Primary Period Repair Report

Result: `IMPLEMENTATION_PASS`

Layer role: `N5_action`

Generated at: `2026-06-08`

## Scope

This gate fixes the N5 candidate/action_write_plan layer so legal HINT 30m rows keep `primary_trigger_period=null`.

No N5 execute was run. No database writes were performed. No N4 outbox rows were consumed or updated. No action fact/event/outbox rows, N5 inbox/checkpoint rows, N6 rows, worker state, rollback execution, delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, trade, or old-system state were touched.

## Root Cause

The blocker was:

```text
n5_action_candidate_reconstructs_hint_30m_primary_trigger_period
```

The polluted function was:

```text
src/ashare_v3/action/dry_run.py::build_candidate_from_trigger_event
```

Old logic:

```python
primary_trigger_period = str(payload.get("primary_trigger_period") or trigger_period)
```

For legal N4 HINT 30m rows:

```text
trigger_kind=hint
condition_key=BUY_HINT / SELL_HINT
trigger_period=30m
triggered_periods=[]
all_trigger_periods=[]
primary_trigger_period=null
trigger_price=present
n5_entry_allowed=true
```

the candidate layer reconstructed `primary_trigger_period=30m`. `run_once_dry_run.py` then copied the polluted value into `action_write_plan`, so the execute payload builder received an explicit invalid formal primary period.

## Code Repair

Changed:

```text
src/ashare_v3/action/dry_run.py
tests/test_action_dry_run.py
```

Generated:

```text
docs/N5_ACTION_CANDIDATE_HINT_30M_PRIMARY_PERIOD_REPAIR_REPORT.md
docs/N5_ACTION_CANDIDATE_HINT_30M_PRIMARY_PERIOD_REPAIR_REPORT.json
```

The new candidate rule is:

```text
If primary_trigger_period is explicitly present, preserve it.
If trigger_kind=hint and condition_key/original_condition_key is BUY_HINT/SELL_HINT and trigger_period=30m, keep primary_trigger_period=null.
Otherwise retain trigger_period fallback for existing formal trigger compatibility.
```

`action_write_plan` carries the candidate field unchanged, so legal HINT 30m remains null through planning.

For idempotency:

```text
action_confirmation_grain_key uses primary_trigger_period|null.
action_confirmation_merge_key may use trigger_period=30m when primary is null, preserving same-minute multi-condition provenance merging without polluting the persisted/action payload field.
```

No changes were made to `event_factory.py` or `events/models.py`; the formal-period guard was not relaxed.

## Regression Proof

RED before fix:

```text
PYTHONPATH=src python3 -m unittest \
  tests.test_action_dry_run.ActionDryRunTest.test_buy_hint_30m_candidate_keeps_primary_trigger_period_null \
  tests.test_action_dry_run.ActionDryRunTest.test_sell_hint_30m_candidate_keeps_primary_trigger_period_null \
  tests.test_action_dry_run.ActionDryRunTest.test_run_once_action_write_plan_keeps_hint_30m_primary_trigger_period_null
```

Observed failures:

```text
BUY_HINT candidate primary_trigger_period was '30m' instead of None
SELL_HINT candidate primary_trigger_period was '30m' instead of None
action_write_plan primary_trigger_period was '30m' instead of None
```

GREEN after fix:

```text
legal BUY_HINT 30m candidate primary_trigger_period=null
legal SELL_HINT 30m candidate primary_trigger_period=null
run_once action_write_plan HINT 30m primary_trigger_period=null
build_n5_action_event legal HINT 30m passthrough still PASS
ordinary trigger_kind=trigger + trigger_period=30m still BLOCKS
30m inside triggered_periods/all_trigger_periods/primary_trigger_period still BLOCKS
TriggerPendingMarketData remains quality-only/no action output
same-minute multi-condition provenance merge remains preserved
```

## Validation

```text
PYTHONPATH=src python3 -m unittest tests/test_action_dry_run.py
PASS

PYTHONPATH=src python3 -m unittest tests/test_action_execute.py
PASS

PYTHONPATH=src python3 -m unittest tests/test_action_event_contract.py
PASS

PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_action*.py'
PASS

python3 -m compileall src/ashare_v3/action src/ashare_v3/events tests
PASS

python3 -m json.tool docs/N5_ACTION_CANDIDATE_HINT_30M_PRIMARY_PERIOD_REPAIR_REPORT.json >/dev/null
PASS

git diff --check
PASS
```

## Forbidden Scope Proof

```text
n5_execute_performed=false
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

## Next Gate

Allowed next gate:

```text
N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_V4_REPAIR_RETRY_REGENERATION_GATE
```
