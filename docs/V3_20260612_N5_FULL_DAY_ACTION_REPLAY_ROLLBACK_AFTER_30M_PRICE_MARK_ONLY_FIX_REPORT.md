# V3 20260612 N5 Full-Day Action Replay Rollback After 30m Price Mark-Only Fix

Result: `ROLLBACK_PASS`

- target_run_id: `v3_n5_action_replay_20260612_after_n4_full_day_trigger_v1`
- source_trigger_run_id: `v3_n4_trigger_replay_20260612_after_n3_full_day_metric_v1`
- consumer_name: `v3_n5_action_replay_20260612_full_day_consumer_v1`

## Delete Counts

- `common_event_consumer_checkpoint`: `2080`
- `common_event_inbox`: `24255`
- `common_event_outbox`: `23068`
- `common_action_event`: `23068`
- `stock_action_fact`: `21075`
- `index_action_fact`: `686`
- `board_action_fact`: `1307`
- `common_action_quality_item`: `0`
- `common_action_run`: `1`

## Boundary

- N4 preserved: `True`
- N5 scoped rows zero: `True`
- N6/voice/mobile/sim/position/trade untouched.

