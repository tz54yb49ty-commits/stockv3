# N6 20260608 Until 1500 Metric-Aware Retry Rollback Report

result=ROLLBACK_EXECUTED

```json
{
  "result": "ROLLBACK_EXECUTED",
  "layer_role": "N6_user",
  "user_projection_run_id": "user_projection_shadow_20260608_until_1500_metric_aware_retry__action_consumer_execute_20260608_until_1500_metric_aware_retry",
  "source_action_run_id": "action_consumer_execute_20260608_until_1500_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
  "started_at": "2026-06-09T04:29:48.725824+00:00",
  "finished_at": "2026-06-09T04:29:48.961956+00:00",
  "before_counts": {
    "user_projection_run": 1,
    "user_signal_projection": 122,
    "user_signal_card": 122,
    "user_notification_queue": 0
  },
  "deleted_counts": {
    "user_notification_queue": 0,
    "user_signal_card": 122,
    "user_signal_projection": 122,
    "user_projection_run": 1
  },
  "after_counts": {
    "user_projection_run": 0,
    "user_signal_projection": 0,
    "user_signal_card": 0,
    "user_notification_queue": 0
  },
  "guards": {
    "n5_outbox_delivered_or_delivering": 0,
    "user_signal_decision": 0,
    "user_sim_order": 0,
    "user_sim_trade": 0,
    "user_sim_position": 0
  },
  "optional_downstream_ref_counts": {
    "common_position_state": 0,
    "common_position_event": 0
  },
  "rollback_sql_path": "sql/N6_projection_20260608_until_1500_metric_aware_retry_rollback.sql",
  "forbidden_scope_proof": {
    "n1_n2_n3_n4_n5_modified": false,
    "n5_outbox_consumed_or_status_updated": false,
    "delivery_push_voice_mobile": false,
    "sim_order_trade_position_pnl": false,
    "worker_started": false,
    "old_system_touched": false,
    "real_trade": false
  }
}
```
