# V3 20260615 N6 User Projection After N5 Metric Replay Closeout

## Result

`CLOSEOUT_PASS` / marker `V3_20260615_N6_USER_PROJECTION_AFTER_N5_METRIC_REPLAY_COMPLETE`.

## Final Summary

N6 consumed the new N5 replay source read-only and wrote ordinary user projection/card rows for the 49 `ActionExecuted` events only.

## Row Count Proof

- `user_projection_run`: `1`
- `user_signal_projection`: `49`
- `user_signal_card`: `49`
- `user_notification_queue`: `0`

## Action Distribution

[
  {
    "action_state": "executed",
    "action_mark": "30m_volume",
    "count": 4
  },
  {
    "action_state": "executed",
    "action_mark": "normal",
    "count": 45
  }
]

## N5 Boundary

N5 outbox remains pending: `[{'event_type': 'ActionBlocked', 'status': 'pending', 'count': 786}, {'event_type': 'ActionExecuted', 'status': 'pending', 'count': 49}]`; delivered/delivering `0/0`.

## Forbidden Scope

No user notification queue rows, no voice/mobile/push, no sim/position/PnL/order/trade, no scheduler/worker restart, no old system touch.

## Next Gate

layer_role=runtime_control。进入 V3_20260615_REALTIME_ENGINE_REACTIVATION_FINAL_GATE_AFTER_N6_PROJECTION_CLOSEOUT。目标：只读复核 N3/N4/N5/N6 已打通且 scheduler 当前 not_loaded，确认是否允许重新启用 V3 realtime engine scheduler。
