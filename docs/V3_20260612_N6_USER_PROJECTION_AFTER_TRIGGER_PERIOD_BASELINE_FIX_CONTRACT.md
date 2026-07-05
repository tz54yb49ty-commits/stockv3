# V3 20260612 N6 User Projection After Trigger Period Baseline Fix Contract

- result: `CONTRACT_PASS`
- source_action_run_id: `v3_n5_action_replay_20260612_after_n4_trigger_period_baseline_fix_v1`
- projection_run_id: `v3_n6_user_projection_20260612_after_n5_trigger_period_baseline_fix_v1`
- user_message_event_filter: `ActionEligible / ActionExecuted`
- ActionBlocked / ActionSkipped: status-monitor/diagnosis only
- notification_queue_policy: `deferred`
- planned_writes: `{'user_projection_run': 1, 'user_signal_projection': 276, 'user_signal_card': 276, 'user_notification_queue': 0}`
- rollback_sql_path: `sql/V3_20260612_N6_USER_PROJECTION_AFTER_TRIGGER_PERIOD_BASELINE_FIX_ROLLBACK.sql`
