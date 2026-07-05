# N6 User Projection Execute Preflight Retry

Result: `PREFLIGHT_PASS`

Gate: `N6_USER_PROJECTION_AFTER_N5_TRANSITION_PREVIOUS_AMOUNT_SOURCE_REPAIR_PASS_EXECUTE_CONTRACT_GATE_RETRY_AFTER_QUEUE_POLICY_ALIAS_ALIGNMENT`

This is a read-only execute preflight. It does not execute N6 projection.

## Preflight Builder Proof

- result: `PREFLIGHT_PASS`
- P0 blockers: `0`
- notification_queue_policy: `deferred_no_queue_write`
- user_message_event_filter: `ActionEligible`, `ActionExecuted`

Planned rows:

| row type | planned |
|---|---:|
| user_projection_run | 1 |
| user_signal_projection | 22 |
| user_signal_card | 22 |
| user_notification_queue | 0 |
| n5_outbox_status_updates | 0 |
| user_signal_decision | 0 |
| user_sim_rows | 0 |

Notification plan:

- planned_notification_count: `0`
- actual_push: `false`
- voice_mobile_push: `false`
- provider_delivery_attempt: `false`
- deferred: `true`

## Write Plan Proof

In-memory write plan:

| write target | count |
|---|---:|
| user_projection_run | 1 |
| user_signal_projection | 22 |
| user_signal_card | 22 |
| user_notification_queue | 0 |

Write tables exclude `user_notification_queue`.

## Live Baseline

| proof | value |
|---|---:|
| N5 ActionBlocked pending | 469 |
| N5 ActionExecuted pending | 22 |
| N5 delivered/delivering | 0 |
| scoped user_projection_run | 0 |
| scoped user_signal_projection | 0 |
| scoped user_signal_card | 0 |
| scoped user_notification_queue | 0 |

N4 rows are not N6 input.

## Forbidden Scope

- N6 projection executed: no
- database written: no
- N5 outbox consumed/updated: no
- N4 outbox updated: no
- scheduler/worker started: no
- voice/mobile/sim/position/order/real trade touched: no
- old system read/modified: no
