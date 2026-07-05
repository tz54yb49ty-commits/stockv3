# V3 20260612 Stale N5 Trigger Period Fabrication Rollback Dry-Run

Result: `DRY_RUN_PASS`

This dry-run is scoped to the two reviewed stale N5 runs:

- `v3_n5_action_replay_20260612_after_n4_state_machine_v3`
- `v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1`

No rollback was executed. No database rows were written or updated.

## Stale Run Rows

`v3_n5_action_replay_20260612_after_n4_state_machine_v3`:

- `common_action_run=1`
- `common_action_quality_item=0`
- stock/index/board facts: `22223/975/1829`
- `common_action_event=25027`
- N5 outbox: `25027 pending`
- N5 consumer inbox/checkpoint: `25282/2078`

`v3_n5_hint_basis_aligned_replay_20260612_from_n4_action_confirmation_metric_after_hint_basis_fix_v1`:

- `common_action_run=1`
- `common_action_quality_item=4449`
- stock/index/board facts: `3/0/2`
- `common_action_event=5`
- N5 outbox: `5 pending`
- N5 consumer inbox/checkpoint currently in scope: `0/0`

## Fabrication Evidence

The state-machine replay has stale N5 formal-period contamination:

- action_event column `trigger_period=30m`: `25027`
- action_event payload contains `"30m"`: `1187`
- ordinary action_event rows containing 30m formal-period evidence: `23840`
- outbox payload contains `"30m"`: `1187`

The hint-basis replay has column-level contamination:

- action_event column `trigger_period=30m`: `5`
- action_event ordinary rows containing 30m formal-period evidence: `5`
- outbox payload contains `"30m"`: `0`

## Downstream Safety

- N5 outbox delivered/delivering: `0/0`
- N5 downstream inbox/checkpoint refs: `0/0`
- N6/user refs: `0`
- position refs: `0`
- voice/mobile/sim/order/real_trade refs: `0`

## N4 Preservation

N4 source runs remain preserved and must not be rolled back by this gate:

- `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3`
- `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`

All N4 outbox rows remain pending; this gate did not consume or update them.
