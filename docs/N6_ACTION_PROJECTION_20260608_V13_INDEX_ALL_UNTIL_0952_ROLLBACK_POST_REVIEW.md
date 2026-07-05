# N6 Action Projection 20260608 v13 index-all Rollback Post-review

- result: `POST_REVIEW_PASS`
- layer_role: `runtime_control`
- reviewed_at: `2026-06-08T13:51:51+08:00`
- projection_run_id: `user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952`
- source_action_run_id: `action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`

## Rollback Proof Summary

- rollback report status: `ROLLBACK_PASS`
- deleted `user_projection_run=1`
- deleted `user_signal_projection=201`
- deleted `user_signal_card=201`
- deleted `user_notification_queue=0`
- live scoped rows after rollback are all `0`

## Live Post-check Proof

| table | remaining |
|---|---:|
| `user_projection_run` | 0 |
| `user_signal_projection` | 0 |
| `user_signal_card` | 0 |
| `user_notification_queue` | 0 |
| `N6 common_event_outbox refs` | 0 |
| `N6 common_event_inbox refs` | 0 |
| `N6 checkpoint refs` | 0 |

## Upstream Unchanged Proof

- N5 outbox remains: `[{'event_type': 'ActionEligible', 'status': 'pending', 'count': 201}]`
- N5 action rows still present: common_action_event `201`, stock/index/board action facts `195/6/0`
- N5 inbox from N4 remains `3920`
- N4 outbox remains `[{'event_type': 'TriggerMatched', 'status': 'pending', 'count': 320}, {'event_type': 'TriggerPendingMarketData', 'status': 'pending', 'count': 3600}]`
- N4 trigger_match/state remains `3920/3920`

## Rollback Static Check

- hard-fail before first DELETE/UPDATE: `True`
- delete targets: `['USER_NOTIFICATION_QUEUE', 'USER_SIGNAL_CARD', 'USER_SIGNAL_PROJECTION', 'USER_PROJECTION_RUN']`
- no CASCADE/DROP/TRUNCATE: `True/True/True`

## Forbidden Scope Proof

- `n5_rollback_executed` = `False`
- `n4_rollback_executed` = `False`
- `n3_n2_n1_mutated` = `False`
- `outbox_inbox_checkpoint_consumed_or_updated_by_this_gate` = `False`
- `worker_started` = `False`
- `delivery_push_voice_mobile` = `False`
- `sim_position_pnl_real_trade` = `False`
- `proposal_order_trade` = `False`
- `old_system_touched` = `False`

## Validation Summary

- rollback report JSON parse: `PASS`
- rollback static check: `PASS`
- live DB post-check: `PASS`
- new artifact JSON parse: `PASS`
- git diff check: `PASS`

Recommended next gate: `N5_ACTION_CONFIRMATION_20260608_V13_INDEX_ALL_UNTIL_0952_ROLLBACK_FINAL_GATE_REVIEW`
