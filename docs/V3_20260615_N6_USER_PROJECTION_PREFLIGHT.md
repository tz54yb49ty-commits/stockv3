# V3 20260615 N6 User Projection Preflight

- result: `PREFLIGHT_PASS`
- mode: artifact only, no execute, no DB write
- P0/P1/P2: `0/1/0`
- source_action_run_id: `n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`
- projection_run_id: `v3_n6_user_projection_20260615_after_n5_action_bounded_20260615_from_n4_production_semantic_replay_20260615_market_snapshot_updated_until_1000`

## Passed Checks

- N5 action run exists and status is `passed`.
- N5 P0/P1/P2 is `0/0/0`.
- N5 outbox distribution is `ActionBlocked:pending=836`.
- ActionEligible and ActionExecuted counts are `0`.
- Target N6 scoped baseline rows are all `0`.
- Source N5 payload has canonical N6 required fields for `836/836` rows.
- Planned user-message projection/card/queue rows are `0/0/0`.
- Rollback SQL is scoped to this `projection_run_id`.

## Non-Blocking Alignment Note

The existing generic N6 runner historically projects all canonical Action* events. This contract changes the product filter so `ActionBlocked` and `ActionSkipped` are diagnosis/status-only. Before an execute final gate, run a zero-user-message runner alignment gate so the runner creates only the scoped `user_projection_run` row and no projection/card/queue rows.

## Boundary

No N6 execute, no DB write, no N5 outbox/inbox/checkpoint update, no scheduler restart, no worker, no delivery/push/voice/mobile, no sim/position/PnL/real trade, no proposal/order/trade, no old system touch.
