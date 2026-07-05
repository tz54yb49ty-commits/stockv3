# N4 Formal Amount Guard 20260615 Polluted Lineage Rollback Execute Report

Result: `ROLLBACK_PASS`

Executed SQL:

`sql/V3_20260615_formal_amount_guard_polluted_lineage_rollback.sql`

Rollback order:

1. N6 user projection
2. N5 action facts/events/outbox/inbox/checkpoint
3. N4 trigger run/match/state/outbox/inbox/checkpoint

Post-check zero proof:

- `user_projection_run=0`
- `user_signal_projection=0`
- `user_signal_card=0`
- `user_notification_queue=0`
- `common_action_run=0`
- `common_action_quality_item=0`
- `common_action_event=0`
- `stock/index/board_action_fact=0/0/0`
- `N5 outbox=0`
- `N5 inbox/checkpoint refs=0/0`
- `common_trigger_run=0`
- `common_trigger_quality_item=0`
- `common_trigger_match=0`
- `common_trigger_state=0`
- `N4 outbox=0`
- `N4 inbox/checkpoint refs=0/0`

Preserved scope:

- N3 facts preserved
- N3 outbox status preserved
- old system not touched
- scheduler/worker not started
- voice/mobile/sim/position/order/real trade not touched
