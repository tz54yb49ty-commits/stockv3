# N6 Action Projection 20260608 Until 15:00 Metric-Aware Retry Readiness

- result: `READINESS_PASS`
- input: `ActionBlocked:pending=122` from metric-aware N5
- planned writes: `user_projection_run=1 / user_signal_projection=122 / user_signal_card=122 / user_notification_queue=0`
- no execute, no DB write, no outbox consumption.

```json
{
  "gate": "N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_READINESS_GATE",
  "status": "READINESS_PASS",
  "result": "READINESS_PASS",
  "layer_role": "N6_user",
  "created_at": "2026-06-08T18:58:07.261709+00:00",
  "source": {
    "action_run_id": "action_consumer_execute_20260608_until_1500_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
    "source_trigger_run_id": "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
    "metric_run_id": "action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
    "user_projection_run_id": "user_projection_shadow_20260608_until_1500_metric_aware_retry__action_consumer_execute_20260608_until_1500_metric_aware_retry",
    "expected_outbox_counts": {
      "ActionBlocked:pending": 122
    },
    "delivered": 0,
    "delivering": 0
  },
  "dry_run_artifacts": {
    "json": "docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_DRY_RUN.json",
    "markdown": "docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_DRY_RUN.md"
  },
  "n5_input_proof": {
    "source_action_run_status": "passed",
    "ActionBlocked_pending": 122,
    "delivered_delivering": "0/0",
    "ActionEligible": 0,
    "ActionExecuted": 0,
    "ActionSkipped": 0,
    "metric_aware_confirmation": true,
    "not_eligibility_only": true
  },
  "clean_baseline": {
    "scoped_user_projection_run": 0,
    "scoped_user_signal_projection": 0,
    "scoped_user_signal_card": 0,
    "scoped_user_notification_queue": 0,
    "downstream_refs": 0
  },
  "planned_scope": {
    "user_projection_run": 1,
    "user_signal_projection": 122,
    "user_signal_card": 122,
    "user_notification_queue": 0,
    "user_signal_decision": 0,
    "user_session": 0,
    "user_watchlist": 0,
    "user_watchlist_item": 0,
    "user_sim_order": 0,
    "user_sim_trade": 0,
    "user_sim_position": 0,
    "n5_outbox_status_updates": 0,
    "n6_inbox_checkpoint": 0
  },
  "notification_queue_policy": "deferred",
  "forbidden_scope": {
    "execute_n6": false,
    "database_write": false,
    "consume_or_update_n5_outbox": false,
    "write_n6_inbox_checkpoint": false,
    "worker_started": false,
    "delivery_push_voice_mobile": false,
    "sim_position_pnl_real_trade": false,
    "proposal_order_trade": false,
    "old_system_touched": false
  },
  "p0_p1_p2": "0/5/2",
  "next_gate": "N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_CONTRACT_GATE"
}
```
