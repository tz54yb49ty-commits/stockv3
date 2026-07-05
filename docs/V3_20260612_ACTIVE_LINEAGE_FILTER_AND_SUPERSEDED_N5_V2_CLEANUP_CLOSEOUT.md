# V3 20260612 Active Lineage Filter And Superseded N5 V2 Cleanup Closeout

Result: `CLOSEOUT_PASS`

## Root Cause

N6 raw N5 message view displayed all same-date N5 outbox events without default active lineage filtering. For `stock:SZ:002056` at `2026-06-12 09:31`, the superseded `mark_only_fix_v2` N5 replay and the active `state_machine_v3` N5 replay both emitted an `ActionExecuted`, so the page showed two visually identical messages.

## Fix

- N4/N5 raw message APIs now default to active 20260612 lineage.
- `show_all=1` remains the audit path for historical/superseded runs.
- `source_run_id` is now a supported raw message filter.

Active lineage:

- N4: `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_state_machine_v3`
- N5: `v3_n5_action_replay_20260612_after_n4_state_machine_v3`

## Cleanup

Executed scoped rollback:

`sql/V3_20260612_n5_action_replay_after_n4_mark_only_fix_rollback.sql`

Target:

- N5 run: `v3_n5_action_replay_20260612_after_n4_mark_only_fix_v2`
- consumer: `v3_n5_action_replay_20260612_mark_only_fix_consumer_v2`

Post-check old scoped rows:

- `common_action_run=0`
- `stock/index/board_action_fact=0/0/0`
- `common_action_event=0`
- `common_event_outbox=0`
- scoped inbox/checkpoint=`0/0`

## Duplicate Proof

For `stock:SZ:002056`, `ActionExecuted`, `2026-06-12 09:31`, remaining rows:

- `v3_n5_action_replay_20260612_after_n4_state_machine_v3 = 1`

## Boundary

Active N4/N5 lineage preserved:

- N4 run/outbox=`1/45006`
- N5 run/outbox=`1/25027`

N6/user/sim/position refs remain `0`. No scheduler was started or modified. No N3/N4 active lineage was changed.
