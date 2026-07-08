# 20260608 Until 15:00 Unified Output Retry Lineage Dashboard

Result: `DASHBOARD_PASS`

This runtime_control dashboard is a readonly handoff for the current closed N6 shadow projection/card run. It did not execute N6, write the database, consume or update N5 outbox, start a worker, execute rollback SQL, deliver push/voice/mobile output, create proposal/order/trade rows, update sim/position/PnL, touch real trade, or touch the old system.

## Current Authority

Authority: `current_closed_shadow_projection`

- user_projection_run_id: `user_projection_shadow_20260608_until_1500_unified_output_retry__action_consumer_execute_20260608_until_1500_unified_output_retry`
- source_action_run_id: `action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- status: `passed`
- input/output: `556 / 556`
- superseded_by: `null`

This run supersedes:

- `user_projection_shadow_20260608_until_1500_formal_snapshot_fallback_metric_aware_retry__action_consumer_execute_20260608_until_1500_formal_snapshot_fallback_metric_aware_retry`

## Upstream Lineage

| Layer | Run | Result | Key Counts |
|---|---|---|---|
| N3 metric | `action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry` | `POST_REVIEW_PASS` | stock/index/board/total `412/60/84/556` |
| N4 trigger | `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry` | `POST_REVIEW_PASS` | TriggerMatched/outbox `556/556` |
| N5 action | `action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry` | `POST_REVIEW_PASS` | action events/outbox `556/556` |
| N6 projection | `user_projection_shadow_20260608_until_1500_unified_output_retry__action_consumer_execute_20260608_until_1500_unified_output_retry` | `CLOSEOUT_PASS` | projection/card/queue `556/556/0` |

N3 metric coverage: `556/556`, missing `0`, duplicate metric grain `0`.

N4 output: only `TriggerMatched=556`; outbox remains pending `556`.

N5 output: `ActionExecuted=7`, `ActionBlocked=549`; N5 outbox remains pending `556`.

N6 output: shadow projection/card rows only; notification queue remains deferred at `0`.

## Distribution

| Item | Rows |
|---|---:|
| `ActionExecuted` | 7 |
| `ActionBlocked` | 549 |
| `price_confirmation_failed` | 535 |
| `amount_confirmation_failed` | 14 |
| `ActionExecuted` `normal` action_mark | 6 |
| `ActionExecuted` `30m_volume` action_mark | 1 |
| `ActionBlocked` null action_mark | 549 |
| `B_BUY` | 415 |
| `S_SELL` | 141 |
| buy direction | 415 |
| sell direction | 141 |

## N5 Outbox Pending Boundary

| event_type | pending |
|---|---:|
| `ActionExecuted` | 7 |
| `ActionBlocked` | 549 |

- delivered / delivering: `0 / 0`
- consumed: `false`
- status updated: `false`
- N6 projection does not authorize delivery, notification, outbox ack, voice, mobile, sim, position, PnL, order, trade, or real trade.

## Forbidden Scope

- N6 execute performed in this gate: `false`
- database write performed in this gate: `false`
- N5 outbox consumed or updated: `false`
- worker started: `false`
- rollback executed: `false`
- delivery / push / voice / mobile touched: `false`
- sim / position / PnL / real trade touched: `false`
- proposal / order / trade touched: `false`
- old system touched: `false`

## Rollback Registry

Rollback SQL: `sql/N6_projection_20260608_until_1500_unified_output_retry_rollback.sql`

- purpose: emergency scoped rollback only
- rollback executed: `false`
- scoped by `user_projection_run_id`
- hard-fails before first executable `DELETE`
- delete order: `user_notification_queue`, `user_signal_card`, `user_signal_projection`, `user_projection_run`
- no `CASCADE`, `DROP`, or `TRUNCATE`
- preserves N5/N4/N3/N2/N1

## Safe Next Options

- read-only UI/dashboard review
- N6 delivery/push/voice/mobile readiness gate
- N6 virtual/sim/proposal policy gate
- keep as archived shadow projection

## Forbidden Without New Gate

- consume/update N5 outbox
- delivery/push/voice/mobile
- sim/position/PnL
- proposal/order/trade
- real trade
- rollback

## Validation

- JSON parse: `PASS`
- artifact consistency: `PASS`
- rollback static check: `PASS`
- `git diff --check`: `PASS`

Next recommended gate: `N6_DELIVERY_PUSH_VOICE_MOBILE_READINESS_OR_KEEP_ARCHIVED_DECISION_GATE`.
