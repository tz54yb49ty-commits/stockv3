# N4 FULL Semantic Repair Dry-Run

Result: **DRY_RUN_PASS**

This dry-run is read-only. It did not execute N4, write DB rows, consume/update outbox/inbox/checkpoint, or enter N5/N6.

## Live FULL Context

Source context run:

`trigger_context_snapshot_20260608_condition_layer_20260605_to_20260608_v13_index_all_execute`

FULL context rows:

| scope | rows |
|---|---:|
| stock `BUY:FULL` | 47 |
| stock `SELL:FULL` | 35 |
| board `SELL:FULL` | 4 |
| total | 86 |

All 86 joined to current 20260608 until 15:00 N3 projection/snapshot evidence.

## Current Code Behavior

Current code blocks all FULL rows before any TriggerMatched output:

```text
outcome_classification=quality_blocked: 86
blocked_reason=full_semantics_blocked: 86
TriggerMatched=0
n5_entry_allowed=true: 0
```

## Contract Simulation

I simulated the 86 FULL rows through the existing ordinary `D` transition evaluator, replacing only the hard FULL block.

```text
simulated outcome=no_op: 86
TriggerMatched=0
TriggerPendingMarketData=0
n5_entry_allowed=true: 0
signal_type B_BUY/S_SELL = 47/39
trigger_mark_candidate=normal: 86
```

Interpretation: the current 15:00 data set does not prove new FULL matches after the hard block is removed. That does not invalidate the semantic repair; it means the repair may produce zero additional rows for this already-completed 20260608 snapshot unless a row actually has D `volume_up` / `low_volume_down` plus amount-chain pass.

## Dry-Run Decision

The contract is still valid because the current blocker is categorical: `BUY:FULL / SELL:FULL` are forbidden even when they would otherwise satisfy valid D semantics. The implementation must replace that categorical block with strict whitelist validation.

## Forbidden Scope Proof

- `db_write_performed=false`
- `n4_execute_performed=false`
- `rollback_executed=false`
- `outbox_inbox_checkpoint_updated=false`
- `n5_entered=false`
- `n6_entered=false`
- `worker_started=false`
- `old_system_touched=false`
