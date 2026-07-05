# N6 Full Metric-Union Historical Projection Repair Preflight

Status: `PREFLIGHT_PASS`

Layer role: `N6_user`

Date: 2026-06-06

This preflight confirms the current N6 metadata baseline and the repaired N5 target metadata before any future repair execute. No database write was performed.

## Baseline Checks

| check | result |
|---|---|
| source action run | `action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1` |
| source N6 projection run | `user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1` |
| user_signal_projection rows | 605 |
| user_signal_card rows | 605 |
| user_notification_queue rows | 0 |
| ActionExecuted rows | 1 |
| ActionBlocked rows | 604 |
| old `metric_missing` rows | 289 |
| planned affected projection rows | 289 |
| planned affected card rows | 289 |

## Current And Target Distribution

| blocked_reason | current N6 | target after metadata repair |
|---|---:|---:|
| `price_confirmation_failed` | 305 | 587 |
| `metric_missing` | 289 | 0 |
| `amount_confirmation_failed` | 10 | 17 |

## P0 / P1 / P2

- P0: 0
- P1: 0
- P2: 0

## Write Boundary

Future execute is allowed to update metadata in existing N6 projection/card rows only. It must not write `user_notification_queue`, consume or update N5 outbox, start workers, or create delivery/push/voice/mobile/sim/position/PnL/proposal/order/trade/real trade side effects.

## Rollback Readiness

Rollback SQL exists:

```text
sql/N6_full_metric_union_historical_projection_repair_20260605_rollback.sql
```

Rollback hard-fails before the first metadata `UPDATE` unless exactly 289 repaired projection rows and 289 repaired card rows are present and no downstream refs exist.

## Decision

`PREFLIGHT_PASS`
