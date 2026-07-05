# N6 Action Projection 20260608 v13 Index-All Until 09:52 v4 Repair Retry Dry Run

Result: `DRY_RUN_PASS`

Read-only artifact generation only. No N6 execute, no DB write, no N5 outbox consumption/update.

## Input Summary

- source_action_run_id: `action_consumer_execute_20260608_v13_index_all_until_0952_v4_repair_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952_v4_repair_retry`
- input events: `119 ActionEligible`
- BUY_HINT / SELL_HINT: `116 / 3`

## Distribution

```json
{
  "input_event_count": 119,
  "by_event_type": {
    "ActionEligible": 119
  },
  "by_asset_kind": {
    "index": 6,
    "stock": 113
  },
  "by_direction": {
    "buy": 116,
    "sell": 3
  },
  "by_signal_type": {
    "B_BUY": 116,
    "S_SELL": 3
  },
  "condition_key_distribution": {
    "BUY_HINT": 116,
    "SELL_HINT": 3
  }
}
```

## Planned Rows

```json
{
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
}
```

## Baseline

```json
{
  "table_counts": {
    "user_account": 4,
    "user_filter_profile": 4,
    "user_projection_run": 5,
    "user_signal_projection": 6270,
    "user_signal_card": 6270,
    "user_notification_queue": 5665,
    "user_signal_decision": 0,
    "user_sim_order": 0,
    "user_sim_trade": 0,
    "user_sim_position": 0
  },
  "n5_outbox_counts": {
    "ActionEligible:pending": 119
  },
  "n5_outbox_expected": {
    "ActionEligible:pending": 119
  },
  "n5_outbox_expected_source": "explicit_gate",
  "baseline_scoped_n6_counts": {
    "user_projection_run": 0,
    "user_signal_projection": 0,
    "user_signal_card": 0,
    "user_notification_queue": 0
  },
  "downstream_refs": {
    "user_signal_decision": 0,
    "common_position_state": 0,
    "common_position_event": 0,
    "user_sim_order": 0,
    "user_sim_trade": 0,
    "user_sim_position": 0,
    "n6_virtual_order": 0,
    "n6_virtual_trade": 0,
    "n6_virtual_position": 0,
    "n6_virtual_pnl_snapshot": 0,
    "common_event_delivery_attempt": 0
  },
  "n5_outbox_downstream_refs": {
    "common_event_inbox": 0,
    "common_event_consumer_checkpoint": 0
  }
}
```

P0/P1/P2: `0/0/0`
