# N4 FULL Semantic Repair Contract

Result: **CONTRACT_PASS**

Layer role: `N4_trigger`

This gate only defines the contract. It does not execute N4, write trigger facts, consume outbox, start a worker, or enter N5/N6.

## Approved Semantic Rule

`BUY:FULL / SELL:FULL` are no longer globally forbidden from `TriggerMatched`.

N4 still must not discover FULL by itself. A FULL trigger is legal only when N2 localized context already proves the FULL prerequisite via `condition_key=BUY:FULL` or `condition_key=SELL:FULL`.

### BUY:FULL

- Input condition: `condition_key=BUY:FULL`
- Direction: `buy`
- Required period: `D`
- Required D current transition: `volume_up`
- Required amount chain: pass
- Output `signal_type=B_BUY`

### SELL:FULL

- Input condition: `condition_key=SELL:FULL`
- Direction: `sell`
- Required period: `D`
- Required D current transition: `low_volume_down`
- Required amount chain: pass
- Output `signal_type=S_SELL`

## TriggerMatched Payload

Legal FULL `TriggerMatched` must emit:

- `trigger_period=D`
- `triggered_periods=["D"]`
- `all_trigger_periods=["D"]`
- `primary_trigger_period=D`
- `trigger_kind=trigger`
- `trigger_mark_candidate=normal`
- `projection_30m_flag=false`
- `projection_30m_type=none`
- `n5_entry_allowed=true`
- non-null `trigger_price`

## Blockers

N4 must block before write if FULL is produced without explicit N2 context, if the period is not exactly `D`, if any formal period field contains `30m`, if `trigger_price` is missing, or if `signal_type` is not `B_BUY / S_SELL`.

## Unchanged Scope

Ordinary BUY/SELL rules are unchanged. HINT 30m semantics are unchanged. N5 action confirmation rules are unchanged. N6 user policy is unchanged.

## Required Repairs

- `src/ashare_v3/trigger/rule_v4_matcher.py`: replace the early `full_semantics_blocked` branch with a D-only FULL evaluator.
- `src/ashare_v3/trigger/v4_enforcement.py`: replace global `full_condition_matched_forbidden` with strict FULL payload validation.
- `src/ashare_v3/trigger/v4_corrected_dry_run.py`: report FULL semantic pass/block reasons rather than `FULL forbidden`.
- `src/ashare_v3/trigger/v4_corrected_execute_contract.py`: replace `FULL_forbidden_by_default` with `full_semantic_contract_guard`.

## Forbidden Scope Proof

- `n4_execute_performed=false`
- `db_write_performed=false`
- `outbox_inbox_checkpoint_updated=false`
- `n5_entered=false`
- `n6_entered=false`
- `worker_started=false`
- `market_data_pulled=false`
- `old_system_touched=false`

Next gate: `N4_FULL_SEMANTIC_REPAIR_IMPLEMENTATION_GATE`
