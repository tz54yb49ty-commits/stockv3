# N6 Projection Bounded Smoke Execute Report

- result: `EXECUTE_PASS`
- runner result: `EXECUTED`
- preflight_result: `PREFLIGHT_PASS`
- notification_queue_policy: `deferred`
- committed: `True`

## Row Count Proof

- user_projection_run: `1`
- user_signal_projection: `200`
- user_signal_card: `200`
- user_notification_queue: `0`

## Distribution Proof

- ActionBlocked projection/card: `199/199`
- ActionExecuted projection/card: `1/1`
- projection action_state: blocked=`199`, executed=`1`

## N5 Outbox Unchanged

- ActionBlocked pending: `199`
- ActionExecuted pending: `1`
- pending total: `200`
- delivered/delivering: `0/0`
- delivery attempt refs: `0`
- inbox refs: `0`

## Forbidden Scope Proof

- user_notification_queue: `0`
- decision/sim/order/trade/position/pnl/virtual refs: `0`
- worker/delivery/push/voice/mobile/real_trade/proposal/order/trade: `false`

## Rollback Proof

Rollback SQL: `sql/N6_projection_bounded_smoke_20260608_larger_scope_semantic_action_probe_rollback.sql`

- hard-fail before DELETE/UPDATE: `true`
- no CASCADE/DROP/TRUNCATE: `true`
- rollback executed: `false`
