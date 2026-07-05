# V3 20260615 N6 User Projection After N5 Metric Replay Contract

## Contract Result

`CONTRACT_PASS`.

## Source N5 Run

`n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1000_v1` with `{'ActionBlocked:pending': 786, 'ActionExecuted:pending': 49}`.

## Projection Run

`v3_n6_user_projection_20260615_after_n5_metric_replay_until_1000_v1`.

## User Message Scope

`ActionExecuted=49` enters ordinary user projection/card; `ActionBlocked=786` does not.

## Planned Writes

- `user_projection_run`: `1`
- `user_signal_projection`: `49`
- `user_signal_card`: `49`
- `user_notification_queue`: `0`
- `user_signal_decision`: `0`
- `proposal`: `0`
- `order`: `0`
- `trade`: `0`
- `position`: `0`
- `pnl`: `0`

## Rollback

`sql/V3_20260615_N6_USER_PROJECTION_AFTER_N5_METRIC_REPLAY_ROLLBACK.sql` hard-fails before DELETE/UPDATE and preserves N5/N4/N3/outbox/inbox/checkpoint.
