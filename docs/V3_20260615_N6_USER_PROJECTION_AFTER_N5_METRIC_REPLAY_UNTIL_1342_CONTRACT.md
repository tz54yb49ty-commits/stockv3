# V3 20260615 N6 user projection after N5 metric replay until 1342 contract

- result: `CONTRACT_PASS`
- source_action_run_id: `n5_action_bounded_20260615_after_n3_action_confirmation_metric_until_1342_v1`
- projection_run_id: `v3_n6_user_projection_20260615_after_n5_metric_replay_until_1342_v1`
- expected: `ActionBlocked:pending=867`, `ActionExecuted:pending=4`
- user message filter: `ActionEligible / ActionExecuted` only
- planned writes: user_projection_run=1, user_signal_projection=4, user_signal_card=4, user_notification_queue=0
