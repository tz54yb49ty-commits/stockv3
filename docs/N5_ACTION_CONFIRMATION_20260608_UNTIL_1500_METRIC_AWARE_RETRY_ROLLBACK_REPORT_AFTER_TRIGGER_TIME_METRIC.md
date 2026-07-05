# N5 20260608 Until 1500 Metric-Aware Retry Rollback Report

result=ROLLBACK_EXECUTED

```json
{
  "result": "ROLLBACK_EXECUTED",
  "layer_role": "N5_action",
  "action_run_id": "action_consumer_execute_20260608_until_1500_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
  "source_trigger_run_id": "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
  "consumer_name": "n5_action_consumer_v1",
  "started_at": "2026-06-09T04:30:58.092253+00:00",
  "finished_at": "2026-06-09T04:31:01.337806+00:00",
  "before_counts": {
    "common_action_run": 1,
    "stock_action_fact": 113,
    "index_action_fact": 6,
    "board_action_fact": 3,
    "common_action_event": 122,
    "common_event_outbox_n5": 122,
    "common_event_ledger_n5": 0,
    "common_event_inbox_n5_consumer": 3892,
    "common_event_consumer_checkpoint_n5_consumer": 2578
  },
  "deleted_counts": {
    "common_event_delivery_attempt": 0,
    "common_event_consumer_checkpoint": 1992,
    "common_event_inbox": 3892,
    "common_event_outbox": 122,
    "common_event_ledger": 0,
    "common_action_event": 122,
    "board_action_fact": 3,
    "index_action_fact": 6,
    "stock_action_fact": 113,
    "common_action_quality_item": 3770,
    "common_action_run": 1
  },
  "after_counts": {
    "common_action_run": 0,
    "stock_action_fact": 0,
    "index_action_fact": 0,
    "board_action_fact": 0,
    "common_action_event": 0,
    "common_event_outbox_n5": 0,
    "common_event_ledger_n5": 0,
    "common_event_inbox_n5_consumer": 0
  },
  "guards": {
    "n5_outbox_delivered_or_delivering": 0,
    "downstream_inbox_refs_to_n5_outbox": 0,
    "non_scoped_n4_inbox_refs": 0,
    "downstream_checkpoint_refs_to_n5_outbox": 0
  },
  "downstream_like_counts": {
    "user_projection_run": 0,
    "user_signal_projection": 0,
    "user_signal_decision": 0,
    "user_notification_queue": 0,
    "user_sim_order": 0,
    "user_sim_trade": 0,
    "user_sim_position": 0,
    "common_position_state": 0,
    "common_position_event": 0
  },
  "rollback_sql_path": "sql/N5_action_confirmation_20260608_until_1500_metric_aware_retry_rollback.sql",
  "forbidden_scope_proof": {
    "n1_n2_n3_n4_modified": false,
    "n4_outbox_status_updated": false,
    "n5_outbox_consumed": false,
    "n6_user_projection_written": false,
    "delivery_push_voice_mobile": false,
    "sim_order_trade_position_pnl": false,
    "worker_started": false,
    "old_system_touched": false,
    "real_trade": false
  }
}
```
