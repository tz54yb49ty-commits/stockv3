# N4/N5 Downstream Ref Registration Repair

- result: `REPAIR_PASS`
- gate: `N4_N5_DOWNSTREAM_REF_REGISTRATION_REPAIR_GATE`
- layer_role: `runtime_control`
- generated_at: `2026-06-08T21:46:33+08:00`
- finding closed: `N1N5-P0-002`

## Decision

The N4 corrected execute post-review proof that reported `N5_N6_refs=0` is registered as point-in-time evidence only. It is now superseded by the later N5 action pipeline execute run.

Current rollback or downstream decisions for:

```text
trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

must use fresh downstream refs proof, not the stale N4 post-review `N5_N6_refs=0` snapshot.

## Fresh Readonly DB Proof

- DB time: `2026-06-08 21:46:33.484505+08`
- target DB: `ashare_v3 / ashare_v3_user / 127.0.0.1:5432`
- target N4 run: `trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- successor N5 action run: `action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`

Rows:

```text
common_trigger_match = 605
N4 outbox TriggerMatched:pending = 605
common_action_run refs = 1
common_action_event refs = 605
common_event_inbox refs for N4 source = 605
common_event_consumer_checkpoint refs for action_run = 73
N5 outbox ActionBlocked:pending = 604
N5 outbox ActionExecuted:pending = 1
```

## Boundary

This gate did not modify code, write the database, execute a runner, consume/update outbox, start workers, run rollback, enter N6 implementation, generate proposal/order/trade, update position/PnL, or submit real trade.

## Remaining Work

This closes the control-plane contradiction for `N1N5-P0-002`; it does not close `N1N5-P0-001`. The next required gate remains:

```text
N5_ACTION_PIPELINE_ARTIFACT_BASELINE_RECONCILIATION_GATE
```
