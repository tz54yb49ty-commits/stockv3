# N5 Action Confirmation 20260608 V13 Index All Until 09:52 Rollback Report

Status: ROLLBACK_PASS

```text
action_run_id=action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952
source_trigger_run_id=trigger_projection_matcher_execute_20260608_v13_index_all_until_0952
rollback_sql=sql/N5_action_confirmation_20260608_v13_index_all_until_0952_rollback.sql

Deleted rows:
{
  "common_action_run": 1,
  "common_action_quality_item": 3600,
  "stock_action_fact": 195,
  "index_action_fact": 6,
  "board_action_fact": 0,
  "common_action_event": 201,
  "common_event_outbox_n5": 201,
  "common_event_ledger_n5": 0,
  "common_event_inbox_n5_consumer": 3920,
  "common_event_consumer_checkpoint_scoped": 1997
}

Post counts:
{
  "common_action_run": 0,
  "common_action_quality_item": 0,
  "stock_action_fact": 0,
  "index_action_fact": 0,
  "board_action_fact": 0,
  "common_action_event": 0,
  "common_event_outbox_n5": 0,
  "common_event_ledger_n5": 0,
  "common_event_inbox_n5_consumer": 0,
  "common_event_consumer_checkpoint_scoped": 0
}

N4 outbox:
[
  {
    "event_type": "TriggerMatched",
    "status": "pending",
    "row_count": 320
  },
  {
    "event_type": "TriggerPendingMarketData",
    "status": "pending",
    "row_count": 3600
  }
]

N4 trigger counts:
{
  "common_trigger_match": 3920,
  "common_trigger_state": 3920,
  "common_trigger_run": 1
}

Downstream refs:
{
  "user_projection_run": 0,
  "user_signal_projection": 0,
  "user_signal_decision": 0,
  "user_notification_queue": 0,
  "user_sim_order": 0,
  "user_sim_trade": 0,
  "user_sim_position": 0,
  "common_position_state": 0,
  "common_position_event": 0,
  "n6_virtual_order": 0,
  "n6_virtual_trade": 0,
  "n6_virtual_position": 0,
  "n6_virtual_pnl_snapshot": 0
}

Forbidden scope: N4/N3/N2/N1 untouched, N6/user/voice/mobile/sim/position/pnl/real_trade untouched, worker_started=false
```
