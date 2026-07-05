# V3 20260615 N6 User Projection After N5 Metric Replay Preflight

## Preflight Result

`PREFLIGHT_PASS` / P0 `0` P1 `5` P2 `2`.

## Source Distribution

- `ActionBlocked:pending`: `786`
- `ActionExecuted:pending`: `49`

## Planned Writes

- `user_projection_run`: `1`
- `user_signal_projection`: `49`
- `user_signal_card`: `49`
- `user_notification_queue`: `0`
- `user_signal_decision`: `0`
- `user_sim_account`: `0`
- `user_sim_order`: `0`
- `user_sim_trade`: `0`
- `user_sim_position`: `0`
- `user_sim_rows`: `0`
- `user_session`: `0`
- `n5_outbox_status_updates`: `0`

## Baseline Guard

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

## Forbidden Scope

No N5 outbox consumption/update, no notification queue rows, no voice/mobile/sim/position/order/trade.
