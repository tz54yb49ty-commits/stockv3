# V3 20260612 N6 User Projection After Trigger Period Baseline Fix Post Review

Result: `POST_REVIEW_PASS`

```text
projection_run_id=v3_n6_user_projection_20260612_after_n5_trigger_period_baseline_fix_v1
source_action_run_id=v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1
scoped_row_counts={'user_projection_run': 1, 'user_signal_projection': 276, 'user_signal_card': 276, 'user_notification_queue': 0}
projection_distribution={'ActionExecuted': 276}
action_state_distribution={'executed': 276}
n5_outbox_after=[{'event_type': 'ActionBlocked', 'status': 'pending', 'c': 911}, {'event_type': 'ActionExecuted', 'status': 'pending', 'c': 276}]
forbidden_scope={'n5_outbox_delivered_or_delivering': 0, 'user_signal_decision': 0, 'user_sim_order': 0, 'user_sim_trade': 0, 'user_sim_position': 0}
```

