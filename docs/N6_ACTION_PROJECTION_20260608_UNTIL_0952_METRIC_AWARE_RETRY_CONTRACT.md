# N6 Action Projection 20260608 Until 09:52 Metric-Aware Retry Contract

- result: `CONTRACT_PASS`
- notification queue policy: `deferred`
- allowed future write tables: `user_projection_run`, `user_signal_projection`, `user_signal_card`
- forbidden: N5 outbox consumption/update, N6 inbox/checkpoint, notification delivery, sim/position/real trade.

```json
{
  "status": "CONTRACT_PASS",
  "result": "CONTRACT_PASS",
  "gate": "N6_ACTION_PROJECTION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_CONTRACT_GATE",
  "layer_role": "runtime_control",
  "execute_layer_role": "N6_user",
  "date": "2026-06-08",
  "created_at": "2026-06-09T01:28:41.315229+00:00",
  "mode": "n6_20260608_until_0952_metric_aware_retry_action_projection_execute_contract",
  "execute_performed": false,
  "business_write_performed": false,
  "source": {
    "action_run_id": "action_consumer_execute_20260608_until_0952_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry",
    "source_trigger_run_id": "trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry",
    "metric_run_id": "action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry",
    "user_projection_run_id": "user_projection_shadow_20260608_until_0952_metric_aware_retry__action_consumer_execute_20260608_until_0952_metric_aware_retry",
    "expected_outbox_counts": {
      "ActionBlocked:pending": 119
    },
    "delivered": 0,
    "delivering": 0
  },
  "readiness_proof": {
    "readiness_json": "docs/N6_ACTION_PROJECTION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_READINESS.json",
    "result": "READINESS_PASS",
    "n5_action_run_status": "passed",
    "n5_outbox_actionblocked_pending": 119,
    "n6_clean_baseline_rows": {
      "user_projection_run": 0,
      "user_signal_projection": 0,
      "user_signal_card": 0,
      "user_notification_queue": 0
    },
    "downstream_ref_total": 0
  },
  "input_policy": {
    "only_n5_outbox": true,
    "source_layer": "N5_action",
    "source_run_id": "action_consumer_execute_20260608_until_0952_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry",
    "event_type": "ActionBlocked",
    "status": "pending",
    "naked_fact_substitution_allowed": false,
    "consume_outbox_allowed": false
  },
  "accepted_input_event_types": [
    "ActionBlocked"
  ],
  "canonical_input_event_types": [
    "ActionBlocked"
  ],
  "legacy_compat_input_event_types": [],
  "forbidden_input_event_types": [
    "ActionEligible",
    "ActionExecuted",
    "ActionSkipped",
    "ActionEvent",
    "HintEvent",
    "RiskEvent",
    "PositionEvent",
    "TriggerMatched",
    "TriggerPendingMarketData",
    "TriggerStateChanged",
    "MarketSnapshotUpdated",
    "MinuteBarClosed"
  ],
  "notification_queue_policy": "deferred",
  "projection_policy": {
    "ActionBlocked": {
      "card_status": "blocked",
      "display_label": "确认失败/暂不动作",
      "notification_source": "n5_action_blocked",
      "queue_status": "deferred_no_queue_write",
      "delivery_allowed": false,
      "push_allowed": false,
      "voice_mobile_allowed": false,
      "decision_buttons": false,
      "sim_allowed": false,
      "position_allowed": false,
      "real_trade_allowed": false
    }
  },
  "dry_run_baseline": {
    "result": "DRY_RUN_PASS",
    "input_events": 119,
    "by_event_type": {
      "ActionBlocked": 119
    },
    "by_direction": {
      "buy": 116,
      "sell": 3
    },
    "by_signal_type": {
      "B_BUY": 116,
      "S_SELL": 3
    },
    "raw_planned_notification_candidates": 119,
    "planned_row_counts_deferred": {
      "user_projection_run": 1,
      "user_signal_projection": 119,
      "user_signal_card": 119,
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
    "p0_count": 0,
    "p1_count": 5,
    "p2_count": 2
  },
  "planned_writes": {
    "user_projection_run": 1,
    "user_signal_projection": 119,
    "user_signal_card": 119,
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
  "future_execute_allowed_write_tables": [
    "user_projection_run",
    "user_signal_projection",
    "user_signal_card"
  ],
  "future_execute_forbidden_scope": {
    "consume_n5_outbox": true,
    "update_n5_outbox_status": true,
    "write_n5_inbox_checkpoint": true,
    "write_user_notification_queue": true,
    "write_user_signal_decision": true,
    "write_user_session": true,
    "write_user_watchlist": true,
    "write_user_sim": true,
    "write_voice_mobile": true,
    "write_delivery_push": true,
    "write_position": true,
    "real_trade": true,
    "start_worker": true,
    "write_n1_to_n5": true
  },
  "metric_aware_projection_card_trace_contract": {
    "source_event_type": "ActionBlocked",
    "action_state": "blocked",
    "confirmation_status": "failed",
    "blocked_reason": "price_confirmation_failed",
    "metric_run_id": "action_confirmation_metric_20260608_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry",
    "source_action_run_id": "action_consumer_execute_20260608_until_0952_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry",
    "source_trigger_run_id": "trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry",
    "trigger_period": "30m",
    "primary_trigger_period": null,
    "triggered_periods": [],
    "all_trigger_periods": [],
    "condition_key": "BUY_HINT/SELL_HINT",
    "action_mark": "none_or_null",
    "ActionExecuted_zero_not_executable_recommendation": true,
    "projection_policy": "blocked_unconfirmed_no_push_no_decision_no_sim_no_trade"
  },
  "rollback": {
    "sql_path": "sql/N6_projection_20260608_until_0952_metric_aware_retry_rollback.sql",
    "scope": "user_projection_run_id",
    "scoped_user_projection_run_id": "user_projection_shadow_20260608_until_0952_metric_aware_retry__action_consumer_execute_20260608_until_0952_metric_aware_retry",
    "delete_order": [
      "user_notification_queue",
      "user_signal_card",
      "user_signal_projection",
      "user_projection_run"
    ],
    "block_if_linked_downstream_refs_exist": true,
    "guard_before_first_delete": true,
    "raise_exception_before_first_delete": true,
    "optional_downstream_tables_use_to_regclass": true,
    "touches_n5_outbox": false,
    "touches_n1_to_n5": false,
    "no_cascade_drop_truncate": true
  },
  "execute_command_candidate": "PYTHONPATH=src:scripts python3 scripts/run_n6_projection_once.py --projection-run-id user_projection_shadow_20260608_until_0952_metric_aware_retry__action_consumer_execute_20260608_until_0952_metric_aware_retry --source-action-run-id action_consumer_execute_20260608_until_0952_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry --contract-json-path docs/N6_ACTION_PROJECTION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_CONTRACT.json --preflight-json-path docs/N6_ACTION_PROJECTION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_PREFLIGHT.json --expected-n5-outbox-count ActionBlocked:pending=119 --execute --user-confirmed --json > docs/N6_ACTION_PROJECTION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_EXECUTE_REPORT.json",
  "next_gate": "N6_ACTION_PROJECTION_20260608_UNTIL_0952_METRIC_AWARE_RETRY_EXECUTE_FINAL_GATE_REVIEW"
}
```
