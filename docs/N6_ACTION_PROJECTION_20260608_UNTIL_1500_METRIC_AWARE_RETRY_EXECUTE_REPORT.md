# N6 Action Projection 20260608 Until 15:00 Metric-Aware Retry Execute Report

- result: `EXECUTED`
- preflight_result: `PREFLIGHT_PASS`
- projection_run_id: `user_projection_shadow_20260608_until_1500_metric_aware_retry__action_consumer_execute_20260608_until_1500_metric_aware_retry`
- source_action_run_id: `action_consumer_execute_20260608_until_1500_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry`
- notification_queue_policy: `deferred`
- P0/P1/P2: `0/5/2`

## Row Count

- `user_projection_run`: `1`
- `user_signal_projection`: `122`
- `user_signal_card`: `122`
- `user_notification_queue`: `0`

## Input / Output

- input: `ActionBlocked:pending=122`
- user_signal_projection/card: `122/122`
- user_notification_queue: `0`
- n5_outbox_unchanged: `True`

## Boundary

- N5 outbox consumed/updated: `false/false`
- N6 inbox/checkpoint written: `false`
- worker/delivery/push/voice/mobile: `false`
- sim/position/real_trade/proposal/order/trade: `false`
