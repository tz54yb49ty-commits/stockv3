# N6 Action Projection 20260608 Until 15:00 Metric-Aware Retry Final Gate Review

- result: `PASS`
- allowed execute command is recorded in JSON.
- rollback SQL is scoped and downstream guarded.
- execute requires `--execute --user-confirmed`.

```json
{
  "gate": "N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_EXECUTE_FINAL_GATE_REVIEW",
  "status": "PASS",
  "result": "PASS",
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
  "contract_proof": {
    "contract_json": "docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_CONTRACT.json",
    "status": "CONTRACT_PASS",
    "json_parse": "PASS"
  },
  "dry_run_proof": {
    "dry_run_json": "docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_DRY_RUN.json",
    "result": "DRY_RUN_PASS",
    "input_events": 122,
    "P0/P1/P2": "0/5/2"
  },
  "preflight_proof": {
    "preflight_json": "docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_PREFLIGHT.json",
    "result": "PREFLIGHT_PASS",
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
    }
  },
  "planned_write_scope": {
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
  "rollback_proof": {
    "rollback_sql_path": "sql/N6_projection_20260608_until_1500_metric_aware_retry_rollback.sql",
    "hard_fail_before_delete": true,
    "delete_scope": "scoped N6 projection run only",
    "preserves_n5_action_facts_outbox": true,
    "preserves_n4_n3_n2_n1": true,
    "no_cascade_drop_truncate": true
  },
  "forbidden_scope": {
    "execute_rollback": false,
    "consume_or_update_n5_outbox": false,
    "write_n5_inbox_checkpoint": false,
    "start_worker": false,
    "delivery_push_voice_mobile": false,
    "sim_position_pnl_real_trade": false,
    "proposal_order_trade": false,
    "old_system_touched": false
  },
  "allowed_execute_command": "PYTHONPATH=src:scripts python3 scripts/run_n6_projection_once.py --projection-run-id user_projection_shadow_20260608_until_1500_metric_aware_retry__action_consumer_execute_20260608_until_1500_metric_aware_retry --source-action-run-id action_consumer_execute_20260608_until_1500_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry --contract-json-path docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_CONTRACT.json --preflight-json-path docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_PREFLIGHT.json --expected-n5-outbox-count ActionBlocked:pending=122 --execute --user-confirmed --json > docs/N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_EXECUTE_REPORT.json",
  "allow_user_confirmation_gate": true,
  "next_gate": "N6_ACTION_PROJECTION_20260608_UNTIL_1500_METRIC_AWARE_RETRY_EXECUTE_USER_CONFIRMATION_GATE"
}
```
