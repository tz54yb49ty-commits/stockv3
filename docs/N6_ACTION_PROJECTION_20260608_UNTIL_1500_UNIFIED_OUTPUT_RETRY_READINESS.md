# N6 Action Projection 20260608 Until 15:00 Unified Output Retry Readiness

Gate: `N6_ACTION_PROJECTION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_READINESS_GATE`  
Layer role: `runtime_control`  
Result: `READINESS_PASS`  
Generated at: `2026-06-10T00:47:06+08:00`

## Target Lineage

- N6 projection run: `user_projection_shadow_20260608_until_1500_unified_output_retry__action_consumer_execute_20260608_until_1500_unified_output_retry`
- N5 action run: `action_consumer_execute_20260608_until_1500_unified_output_retry__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- N4 source run: `trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`
- N3 metric run: `action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_until_1500_unified_output_retry`

## N5 Input Proof

Source artifacts parse and lineage status:

- N5 post-review: `POST_REVIEW_PASS`
- N5 execute report: `EXECUTED`
- N5 final gate review: `PASS`
- N4 post-review: `POST_REVIEW_PASS`
- N3 metric post-review: `POST_REVIEW_PASS`

Live DB proof:

| proof | value |
|---|---:|
| `common_action_run` | `1/status=passed` |
| `P0/P1/P2` | `0/0/0` |
| `ActionExecuted` | 7 |
| `ActionBlocked` | 549 |
| `ActionEligible` | 0 |
| `ActionSkipped` | 0 |
| legacy `ActionEvent/HintEvent/RiskEvent/PositionEvent` | 0 |
| N5 outbox pending | 556 |
| N5 outbox delivered/delivering | `0/0` |
| stock/index/board action facts | `412/60/84` |
| metric trace present in action facts | `556/556` |
| metric ready in action facts | `556/556` |

Blocked/action mark proof:

- `price_confirmation_failed=535`
- `amount_confirmation_failed=14`
- `ActionExecuted action_mark=normal=6`
- `ActionExecuted action_mark=30m_volume=1`
- `ActionBlocked action_mark=null=549`

N5 outbox has no downstream inbox/checkpoint refs:

- downstream inbox refs: `0`
- downstream checkpoint refs: `0`

## N6 Clean Baseline Proof

Scoped N6 baseline for the proposed projection run is clean:

| table | rows |
|---|---:|
| `user_projection_run` | 0 |
| `user_signal_projection` | 0 |
| `user_signal_card` | 0 |
| `user_notification_queue` | 0 |

Source-action-run N6/user refs are also clean:

| ref | rows |
|---|---:|
| `user_projection_run.source_action_run_id` | 0 |
| `user_signal_projection.source_action_run_id` | 0 |
| `user_signal_card.source_action_run_id` | 0 |
| `user_notification_queue.source_action_run_id` | 0 |
| position refs | 0 |
| sim/order/trade/PnL refs | 0 |
| delivery/push/voice/mobile refs | 0 |
| dedicated N6 inbox/checkpoint refs | `0/0` |

## Planned N6 Unified Output Retry Scope

Expected input events are 556 canonical N5 events:

- `ActionExecuted=7`
- `ActionBlocked=549`
- `ActionEligible=0`
- `ActionSkipped=0`

Expected scoped N6 writes for the future execute gate:

- `user_projection_run=1`
- `user_signal_projection=556`
- `user_signal_card=556`
- `user_notification_queue=0`, unless a later contract explicitly allows queued-only notification

Projection/card must preserve:

- `source_action_run_id`
- `source_trigger_run_id`
- `metric_run_id`
- `event_type=ActionExecuted/ActionBlocked`
- `action_state=executed/blocked`
- `blocked_reason` for `ActionBlocked`
- `action_mark` for `ActionExecuted` only
- `condition_key / original_condition_key`
- `trigger_mark_candidate`
- `trigger_period`
- `primary_trigger_period`
- `triggered_periods`
- `all_trigger_periods`

`BUY_HINT / SELL_HINT` may be displayed only as trace or policy in N6. They must not become N5 event types.

## Rollback Requirement

Future N6 rollback must:

- hard-fail before `DELETE` / `UPDATE`
- guard notification / delivery / sim / order / trade / position refs
- delete only scoped N6 unified output retry rows:
  - `user_notification_queue`
  - `user_signal_card`
  - `user_signal_projection`
  - `user_projection_run`
- preserve N5 action facts and N5 outbox status
- preserve N4 / N3 / N2 / N1 facts
- contain no `CASCADE`, `DROP`, or `TRUNCATE`

## Forbidden Scope Proof

This readiness gate did not execute N6, did not write DB rows, did not consume or update N5 outbox, did not write N6 inbox/checkpoint, did not start worker, did not touch delivery/push/voice/mobile, did not touch sim/position/PnL/real_trade, did not create proposal/order/trade, did not execute rollback SQL, and did not touch the old system.

## Validation

- source JSON parse: `PASS`
- live N5 input proof: `PASS`
- N6 clean baseline proof: `PASS`
- downstream refs scan: `PASS`
- rollback requirement proof: `PASS`
- readiness JSON parse: `PASS`
- `git diff --check`: `PASS`

## Decision

`READINESS_PASS`

P0/P1/P2: `0/0/0`

Allowed next gate:

```text
N6_ACTION_PROJECTION_20260608_UNTIL_1500_UNIFIED_OUTPUT_RETRY_CONTRACT_GATE
```
