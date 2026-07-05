# V3 20260615 N6 User Projection Dry-Run

- result: `DRY_RUN_PASS`
- mode: artifact only, no execute, no DB write
- source_action_run_id: `n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- projection_run_id: `v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`

## Input Counts

- ActionBlocked pending: `836`
- ActionEligible pending: `0`
- ActionExecuted pending: `0`
- ActionSkipped pending: `0`
- total pending: `836`

## User Message Filter

Only `ActionEligible` and `ActionExecuted` are ordinary user messages.

The current source has no included event type, so the eligible user-message count is `0`.

## Planned Rows

- user_projection_run: `1`
- user_signal_projection: `0`
- user_signal_card: `0`
- user_notification_queue: `0`

Expected result: `PROJECTION_PASS_ZERO_USER_MESSAGES`.

## Boundary

No N6 execute, no DB write, no notification queue, no N5 outbox consumption/update, no worker, no voice/mobile/push, no sim/position/PnL/real trade, no proposal/order/trade, no old system touch.
