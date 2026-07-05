# V3 20260612 Stale N5 Trigger Period Fabrication Rollback Contract

Result: `CONTRACT_PASS`

## Scope

Rollback is limited to these reviewed stale N5 runs:

- `v3_n5_action_replay_20260612_after_n4_state_machine_v3`
- `v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1`

Rollback SQL:

```text
sql/V3_20260612_stale_n5_trigger_period_fabrication_rollback.sql
```

## Why

These stale N5 runs contain fabricated formal-period evidence around `trigger_period=30m` / formal period passthrough. They predate the current N4/N5 trigger-period baseline alignment and must not remain as active N5 lineage.

## Delete Scope

The rollback may delete only scoped N5 outputs:

- scoped N5 delivery attempts
- scoped N5 outbox / ledger
- scoped N5 action events
- scoped stock/index/board action facts
- scoped N5 quality items
- scoped N5 run rows
- the unique stale state-machine consumer inbox/checkpoint rows:
  `v3_n5_action_replay_20260612_state_machine_consumer_v3`

The hint-basis run used the shared/default `n5_action_consumer_v1`. Current scoped inbox/checkpoint rows for that source are zero. The rollback must not delete shared `n5_action_consumer_v1` watermark rows because that could collide with current aligned replay lineage.

## Hard-Fail Guards

Rollback must hard-fail before the first DELETE if:

- scoped N5 outbox has delivered/delivering rows
- scoped N5 outbox has downstream inbox/checkpoint refs
- N6/user/voice/mobile/sim/position/order/trade refs exist
- ambiguous shared `n5_action_consumer_v1` inbox/checkpoint rows exist for the hint-basis source

## Forbidden Scope

The rollback must not touch:

- N4 trigger facts or N4 outbox status
- N3 facts or N3 metrics
- N6/user projection
- voice/mobile/sim/position/order/real trade
- scheduler/worker
- old system

`execute_authorized=false`; execute requires a separate final gate and explicit user confirmation.
