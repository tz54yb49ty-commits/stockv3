# N6 Action Projection 20260608 v13 Index-All Until 09:52 Execute Preflight

Status: `PREFLIGHT_PASS`

Layer role: `N6_user`

This preflight is read-only. It did not execute N6, did not write projection/card rows, did not consume or update N5 outbox, did not start workers, and did not enter notification delivery, voice, mobile, sim, position, PnL, order, trade, or real trade.

## Summary

```text
N6 projection shadow execute
  result=PREFLIGHT_PASS
  preflight_result=PREFLIGHT_PASS
  projection_run_id=user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952
  planned_projection_run=1
  planned_signal_projection=201
  planned_signal_card=201
  planned_notification_queue=0
  p0_count=0 p1_count=5 p2_count=2
  blockers=[]
  committed=false write_tables=[]
  n5_outbox_consumed=false updates_n5_outbox_status=false
```

## Baseline Guard

```json
{
  "scoped_counts": {
    "user_projection_run": 0,
    "user_signal_projection": 0,
    "user_signal_card": 0,
    "user_notification_queue": 0
  },
  "linked_counts": {
    "user_signal_decision": 0,
    "user_sim_order": 0,
    "user_sim_trade": 0,
    "user_sim_position": 0
  },
  "forbidden_zero_counts": {
    "user_signal_decision": 0,
    "user_watchlist": 0,
    "user_watchlist_item": 0,
    "user_sim_order": 0,
    "user_sim_trade": 0,
    "user_sim_position": 0
  }
}
```

## Planned Rows

```json
{
  "user_projection_run": 1,
  "user_signal_projection": 201,
  "user_signal_card": 201,
  "user_notification_queue": 0,
  "user_signal_decision": 0,
  "user_sim_account": 0,
  "user_sim_order": 0,
  "user_sim_trade": 0,
  "user_sim_position": 0,
  "user_sim_rows": 0,
  "user_session": 0,
  "n5_outbox_status_updates": 0
}
```

Notification queue policy is `deferred`, so `user_notification_queue` planned writes are zero for this readonly projection/card closeout path.

## Event Summary

```json
{
  "input_event_count": 201,
  "by_event_type": {
    "ActionEligible": 201
  },
  "by_direction": {
    "buy": 197,
    "sell": 4
  },
  "by_signal_type": {
    "B_BUY": 197,
    "S_SELL": 4
  },
  "distribution": [
    {
      "event_type": "ActionEligible",
      "direction": "buy",
      "signal_type": "B_BUY",
      "action_type": "buy_candidate",
      "lane": "policy_pending",
      "count": 197
    },
    {
      "event_type": "ActionEligible",
      "direction": "sell",
      "signal_type": "S_SELL",
      "action_type": "sell_candidate",
      "lane": "policy_pending",
      "count": 4
    }
  ]
}
```

## Forbidden Scope

```json
{
  "read_n4_n5_naked_facts_as_input": false,
  "consume_n5_outbox": false,
  "update_n5_outbox_status": false,
  "write_user_projection_run": false,
  "write_user_signal_projection": false,
  "write_user_signal_card": false,
  "write_user_notification_queue": false,
  "write_user_signal_decision": false,
  "write_user_session": false,
  "write_user_sim_tables": false,
  "write_user_watchlist": false,
  "write_voice_mobile_delivery": false,
  "write_position": false,
  "start_worker": false,
  "actual_push": false,
  "voice_mobile_push": false,
  "real_trade": false
}
```

## Rollback

- rollback SQL: `sql/N6_projection_20260608_v13_index_all_until_0952_rollback.sql`
- rollback scope: `user_projection_run_id=user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952`
- delete scope only: `user_notification_queue`, `user_signal_card`, `user_signal_projection`, `user_projection_run`
- future rollback must hard-fail before first `DELETE` and block linked decision/sim/voice/mobile/position refs.

## Next Gate

`N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_FINAL_GATE_REVIEW`
