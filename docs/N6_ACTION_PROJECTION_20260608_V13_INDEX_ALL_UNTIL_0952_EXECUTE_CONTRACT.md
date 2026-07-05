# N6 Action Projection 20260608 v13 Index-All Until 09:52 Execute Contract

Status: `CONTRACT_PASS`

Layer role: `N6_user`

This contract authorizes only a future N6 shadow projection/card execute after final gate and user confirmation. It does not authorize runtime_control execution.

## Source

- source action run: `action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- source trigger run: `trigger_projection_matcher_execute_20260608_v13_index_all_until_0952`
- projection run: `user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952`
- expected N5 outbox: `ActionEligible:pending=201`

## Input Policy

Accepted input event types: `ActionEligible`, `ActionBlocked`, `ActionExecuted`, `ActionSkipped`, plus legacy compatibility `ActionEvent` / `HintEvent`.

Forbidden input event types include `TriggerMatched`, `TriggerPendingMarketData`, `MarketSnapshotUpdated`, `MinuteBarClosed`, `RiskEvent`, `PositionEvent`, `BUY_HINT`, and `SELL_HINT`. N6 reads N5 outbox only; naked N4/N3/N2 fact substitution is not allowed.

## Write Scope

Notification queue policy: `deferred`

Planned writes:

```json
{
  "user_projection_run": 1,
  "user_signal_projection": 201,
  "user_signal_card": 201,
  "user_notification_queue": 0,
  "user_signal_decision": 0,
  "user_session": 0,
  "user_watchlist": 0,
  "user_watchlist_item": 0,
  "user_sim_order": 0,
  "user_sim_trade": 0,
  "user_sim_position": 0,
  "n5_outbox_status_updates": 0
}
```

Allowed write tables: `user_projection_run`, `user_signal_projection`, `user_signal_card`.

Forbidden: N5 outbox consumption/status updates, N5 inbox/checkpoint writes, `user_notification_queue`, decisions, sessions, watchlists, sim, position, delivery, push, voice, mobile, order, trade, real trade, worker, and N1-N5 mutation.

## Rollback

- SQL: `sql/N6_projection_20260608_v13_index_all_until_0952_rollback.sql`
- scoped run id: `user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952`
- delete order: `user_notification_queue -> user_signal_card -> user_signal_projection -> user_projection_run`
- hard-fail guards: decision/sim/voice/mobile/position/downstream refs
- no `CASCADE/DROP/TRUNCATE`

## Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_n6_projection_once.py --projection-run-id user_projection_shadow_20260608_v13_index_all_until_0952__action_consumer_execute_20260608_v13_index_all_until_0952 --source-action-run-id action_consumer_execute_20260608_v13_index_all_until_0952__trigger_projection_matcher_execute_20260608_v13_index_all_until_0952 --contract-json-path docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_CONTRACT.json --preflight-json-path docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_PREFLIGHT.json --expected-n5-outbox-count ActionEligible:pending=201 --execute --user-confirmed --json > docs/N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_REPORT.json
```

Next gate: `N6_ACTION_PROJECTION_20260608_V13_INDEX_ALL_UNTIL_0952_EXECUTE_FINAL_GATE_REVIEW`
