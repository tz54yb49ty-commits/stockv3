# N6 Action Projection 20260608 Until 15:00 Metric-Aware Retry Preflight

- result: `PREFLIGHT_PASS`
- planned rows: `1/122/122/0`
- expected N5 outbox: `ActionBlocked:pending=122`
- no execute in this artifact gate.

```json
{
  "status": "PREFLIGHT_PASS",
  "result": "PREFLIGHT_PASS",
  "preflight_result": "PREFLIGHT_PASS",
  "layer_role": "N6_user",
  "mode": "n6_20260608_until_1500_metric_aware_retry_action_projection_execute_preflight",
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
  "contract_json_path": "docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_CONTRACT.json",
  "dry_run_json_path": "docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_DRY_RUN.json",
  "notification_queue_policy": "deferred",
  "planned_writes": {
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
  "expected_n5_outbox_counts": {
    "ActionBlocked:pending": 122
  },
  "input_event_count": 122,
  "event_distribution": {
    "ActionBlocked": 122
  },
  "p0_p1_p2": "0/5/2",
  "blockers": [],
  "warnings": [
    "board_context_missing",
    "current_price_missing",
    "display_basis_missing",
    "expected_return_pct_missing",
    "target_price_missing"
  ],
  "notes": [
    "canonical_dry_run_uses_n5_outbox_only",
    "n5_outbox_status_remains_pending_in_dry_run"
  ],
  "allow_execute_final_gate_review": true,
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
  "rollback_sql_path": "sql/N6_projection_20260608_until_1500_metric_aware_retry_rollback.sql",
  "next_gate": "N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_EXECUTE_FINAL_GATE_REVIEW"
}
```
