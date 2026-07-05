# N6 Action Projection 20260608 v13 Index-All Until 09:52 v4 Repair Retry Preflight

Result: `PREFLIGHT_PASS`

## Input

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

## Notification Policy

`deferred_no_queue_rows`, planned notification queue rows = `0`.

P0/P1/P2: `0/0/0`
