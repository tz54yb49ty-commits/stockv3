# N6 Action Projection 20260608 Until 15:00 Unified Output Retry Post Review

Result: `POST_REVIEW_PASS`

This runtime_control gate only registered the N6 shadow projection/card execute result. It did not execute N6, write the database, consume or update N5 outbox, start a worker, execute rollback SQL, deliver push/voice/mobile output, create proposal/order/trade rows, update sim/position/PnL, touch real trade, or touch the old system.

## Lineage

- source_action_run_id: `action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- user_projection_run_id: `user_projection_shadow_20260608_until_1500_unified_output_retry__action_consumer_execute_20260608_until_1500_unified_output_retry`
- source layer: `N5_action`
- execute report result: `EXECUTED`
- preflight result: `PREFLIGHT_PASS`

## Row Count Proof

Live readonly DB proof on `ashare_v3 / ashare_v3_user / 127.0.0.1:5432`, with `transaction_read_only=on`:

| table | rows |
|---|---:|
| `user_projection_run` | 1 |
| `user_signal_projection` | 556 |
| `user_signal_card` | 556 |
| `user_notification_queue` | 0 |

## Distribution Proof

| distribution | value |
|---|---:|
| `ActionExecuted` projection/card | 7 / 7 |
| `ActionBlocked` projection/card | 549 / 549 |
| `price_confirmation_failed` projection/card | 535 / 535 |
| `amount_confirmation_failed` projection/card | 14 / 14 |
| `ActionExecuted` `normal` action_mark projection/card | 6 / 6 |
| `ActionExecuted` `30m_volume` action_mark projection/card | 1 / 1 |
| `ActionBlocked` null action_mark projection/card | 549 / 549 |

## N5 Outbox Unchanged Proof

The scoped N5 outbox rows remain pending and were not consumed or updated by this N6 projection:

| event_type | pending |
|---|---:|
| `ActionExecuted` | 7 |
| `ActionBlocked` | 549 |

`delivered=0`, `delivering=0`, and delivery attempt refs are `0`. The execute report also records `n5_outbox_unchanged=true`.

## Forbidden Scope Proof

- N6 inbox refs: `0`
- N6 checkpoint refs: `0`
- Upstream N5 checkpoint refs found by broad text scan: `541`, registered as upstream N5 action lineage and not N6 consumer/checkpoint scope.
- delivery / push / voice / mobile refs: `0`
- decision / sim / order / trade / position / PnL / virtual refs: `0`
- proposal/order/trade refs: `0`
- worker started: `false`
- old system touched: `false`

## Rollback Safety

Rollback SQL: `sql/N6_projection_20260608_until_1500_unified_output_retry_rollback.sql`

Static proof:

- scoped by `user_projection_run_id`
- hard-fails before the first executable `DELETE`
- delete order is `user_notification_queue`, `user_signal_card`, `user_signal_projection`, `user_projection_run`
- no `CASCADE`, `DROP`, or `TRUNCATE`
- no event infra DML
- preserves N5/N4/N3/N2/N1 facts
- rollback was not executed

## Validation

- JSON parse: `PASS`
- live DB row count proof: `PASS`
- N5 outbox unchanged proof: `PASS`
- forbidden scope proof: `PASS`
- rollback static check: `PASS`
- `git diff --check`: `PASS`

Decision: this N6 unified output retry projection/card run can be marked complete.
