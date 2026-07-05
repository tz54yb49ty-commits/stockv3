# V3 20260615 N6 User Projection After N5 Metric Replay Dry Run

## Result

`DRY_RUN_PASS`; source `n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1`; projection `v3_n6_user_projection_20260615_after_n5_metric_replay_until_1000_v1`.

## Source Distribution

- `ActionBlocked:pending`: `786`
- `ActionExecuted:pending`: `49`

## User Message Filter

`ActionEligible / ActionExecuted`; ActionBlocked/ActionSkipped stay diagnosis/status-monitor only.

## Planned Writes With Deferred Notifications

- `user_projection_run`: `1`
- `user_signal_projection`: `49`
- `user_signal_card`: `49`
- `user_notification_queue`: `0`

## Forbidden Scope

No DB write, no N5 outbox consume/update, no voice/mobile/sim/position/order/trade.
