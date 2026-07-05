# N5 Execute Retry After Workspace Restore Post Review

Result: `N5_ACTION_EXECUTE_PASS`

- source_trigger_run_id: `trigger_action_confirmation_metric_execute_20260617_true_full_day_lifecycle_replay_after_performance_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- action_run_id: `action_consumer_execute_20260617_true_full_day_after_n4_lifecycle_performance_repair__trigger_action_confirmation_metric_execute_20260617_true_full_day_lifecycle_replay_after_performance_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1`
- preflight_post_review: `docs/N5_ACTION_AFTER_N4_20260617_TRUE_FULL_DAY_LIFECYCLE_REPLAY_AFTER_PERFORMANCE_REPAIR_PASS_PREFLIGHT_POST_REVIEW.json`
- execute_report_json: `docs/N5_ACTION_AFTER_N4_20260617_TRUE_FULL_DAY_LIFECYCLE_REPLAY_AFTER_PERFORMANCE_REPAIR_PASS_EXECUTE_REPORT.json`
- rollback_sql_path: `sql/N5_action_after_n4_20260617_true_full_day_lifecycle_performance_repair_rollback.sql`

## Counts

```json
{
  "common_action_run": 1,
  "stock_action_fact": 4026,
  "index_action_fact": 170,
  "board_action_fact": 292,
  "common_action_event": 4488,
  "n5_common_event_outbox": 4488,
  "n5_common_event_inbox": 10062,
  "n5_common_event_consumer_checkpoint_scoped_partitions": 1249,
  "common_action_tracking_state": 1445,
  "common_action_quality_item": 0
}
```

## N5 outbox by event type/status

```json
[
  {
    "event_type": "ActionBlocked",
    "status": "pending",
    "count": 3425
  },
  {
    "event_type": "ActionExecuted",
    "status": "pending",
    "count": 1063
  }
]
```

## N4 outbox after N5

```json
{
  "by_event_type_status": [
    {
      "event_type": "TriggerMatched",
      "status": "pending",
      "count": 4488
    },
    {
      "event_type": "TriggerStateChanged",
      "status": "pending",
      "count": 5574
    }
  ],
  "delivered_delivering": 0
}
```

## Checks

```json
[
  {
    "check": "execute_report_result_executed",
    "ok": true,
    "value": "EXECUTED"
  },
  {
    "check": "execute_report_allow_execute",
    "ok": true,
    "value": true
  },
  {
    "check": "execute_report_p0_zero",
    "ok": true,
    "value": 0
  },
  {
    "check": "db_count_common_action_run",
    "ok": true,
    "expected": 1,
    "value": 1
  },
  {
    "check": "db_count_stock_action_fact",
    "ok": true,
    "expected": 4026,
    "value": 4026
  },
  {
    "check": "db_count_index_action_fact",
    "ok": true,
    "expected": 170,
    "value": 170
  },
  {
    "check": "db_count_board_action_fact",
    "ok": true,
    "expected": 292,
    "value": 292
  },
  {
    "check": "db_count_common_action_event",
    "ok": true,
    "expected": 4488,
    "value": 4488
  },
  {
    "check": "db_count_n5_common_event_outbox",
    "ok": true,
    "expected": 4488,
    "value": 4488
  },
  {
    "check": "db_count_n5_common_event_inbox",
    "ok": true,
    "expected": 10062,
    "value": 10062
  },
  {
    "check": "db_count_n5_common_event_consumer_checkpoint_scoped_partitions",
    "ok": true,
    "expected": 1249,
    "value": 1249
  },
  {
    "check": "db_count_common_action_tracking_state_1445",
    "ok": true,
    "expected": 1445,
    "value": 1445
  },
  {
    "check": "n5_ActionExecuted_pending_1063",
    "ok": true,
    "expected": 1063,
    "value": 1063
  },
  {
    "check": "n5_ActionBlocked_pending_3425",
    "ok": true,
    "expected": 3425,
    "value": 3425
  },
  {
    "check": "n4_outbox_not_delivered_or_delivering",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "TriggerMatched_created_action_events_4488",
    "ok": true,
    "expected": 4488,
    "value": 4488
  },
  {
    "check": "TriggerStateChanged_created_no_action_events",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "missing_n4_outbox_source_events_zero",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "downstream_forbidden_zero_user_projection_run",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "downstream_forbidden_zero_user_signal_projection",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "downstream_forbidden_zero_user_signal_decision",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "downstream_forbidden_zero_user_notification_queue",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "downstream_forbidden_zero_user_sim_order",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "downstream_forbidden_zero_user_sim_trade",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "downstream_forbidden_zero_user_sim_position",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "downstream_forbidden_zero_common_position_state",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "downstream_forbidden_zero_common_position_event",
    "ok": true,
    "expected": 0,
    "value": 0
  },
  {
    "check": "common_action_run_flag_worker_started_false",
    "ok": true,
    "expected": false,
    "value": false
  },
  {
    "check": "common_action_run_flag_user_layer_touched_false",
    "ok": true,
    "expected": false,
    "value": false
  },
  {
    "check": "common_action_run_flag_voice_touched_false",
    "ok": true,
    "expected": false,
    "value": false
  },
  {
    "check": "common_action_run_flag_sim_touched_false",
    "ok": true,
    "expected": false,
    "value": false
  },
  {
    "check": "common_action_run_flag_real_trade_touched_false",
    "ok": true,
    "expected": false,
    "value": false
  },
  {
    "check": "common_action_run_flag_market_data_pulled_false",
    "ok": true,
    "expected": false,
    "value": false
  },
  {
    "check": "common_action_run_flag_trigger_layer_mutated_false",
    "ok": true,
    "expected": false,
    "value": false
  },
  {
    "check": "common_action_run_status_passed",
    "ok": true,
    "expected": "passed",
    "value": "passed"
  }
]
```

## Forbidden Scope

No N6/user projection executed. No worker/scheduler, market pull, N2/N3/N4 mutation, voice/mobile/sim/position/order/real-trade, or old-system access.

Allowed next prompt:

```text
layer_role=N6_user. Enter N6_USER_PROJECTION_AFTER_N5_20260617_TRUE_FULL_DAY_ACTION_PASS_PREFLIGHT. Use source_action_run_id=action_consumer_execute_20260617_true_full_day_after_n4_lifecycle_performance_repair__trigger_action_confirmation_metric_execute_20260617_true_full_day_lifecycle_replay_after_performance_repair__condition_layer_20260616_source_20260616_for_20260617_d_anchor_repair_v1 and n5_post_review=docs/N5_ACTION_AFTER_N4_20260617_TRUE_FULL_DAY_LIFECYCLE_REPLAY_AFTER_PERFORMANCE_REPAIR_PASS_EXECUTE_RETRY_AFTER_WORKSPACE_RESTORE_POST_REVIEW.json. Preflight only first.
```
