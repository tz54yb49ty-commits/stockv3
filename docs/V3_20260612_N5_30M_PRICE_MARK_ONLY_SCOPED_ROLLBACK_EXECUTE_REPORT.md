# V3 20260612 N5 30m Price Mark-Only Scoped Rollback Execute Report

Result: `ROLLBACK_PASS`

- action_run_id: `v3_n5_action_mark_aligned_replay_20260612_from_n4_action_confirmation_metric_after_n3_repair_v1`
- source_trigger_run_id: `v3_n4_action_confirmation_metric_20260612_after_realtime_virtual_metric_writer_v1`
- consumer_name: `n5_action_consumer_v1`
- rollback SQL reference: `sql/V3_20260612_n5_action_mark_aligned_replay_rollback.sql`

## Delete Counts

- `common_event_delivery_attempt`: `0`
- `common_event_consumer_checkpoint`: `2082`
- `common_event_inbox`: `4454`
- `common_event_outbox`: `0`
- `common_event_ledger`: `0`
- `common_action_event`: `0`
- `board_action_fact`: `0`
- `index_action_fact`: `0`
- `stock_action_fact`: `0`
- `common_action_quality_item`: `0`
- `common_action_run`: `0`

## After Counts

- `common_action_run`: `0`
- `common_action_quality_item`: `0`
- `stock_action_fact`: `0`
- `index_action_fact`: `0`
- `board_action_fact`: `0`
- `common_action_event`: `0`
- `common_event_outbox_n5`: `0`
- `common_event_inbox_n5_consumer`: `0`
- `common_event_consumer_checkpoint_n5_consumer`: `0`
- `n4_trigger_run`: `1`
- `n4_trigger_match`: `4454`
- `n4_trigger_state`: `4454`
- `n4_outbox`: `4454`

## Boundary

- N4 preserved: `True`
- N6/user refs zero: `True`
- Scheduler/worker not started; voice/mobile/sim/position/trade untouched.

