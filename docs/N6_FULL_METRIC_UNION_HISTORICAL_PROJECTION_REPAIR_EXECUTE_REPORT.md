# N6 Full Metric-Union Historical Projection Repair Execute Report

Status: `EXECUTE_PASS`

Layer role: `N6_user`

Date: 2026-06-06

## Scope

- Source action run: `action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- Projection run: `user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1`
- Repair run: `n6_full_metric_union_historical_projection_repair_20260605_v1`
- Policy: `n6.full_metric_union_historical_projection_repair.v1`

## Actual Rows

| target | rows |
|---|---:|
| user_signal_projection metadata updated | 289 |
| user_signal_card metadata updated | 289 |
| user_notification_queue rows written | 0 |

## Blocked Reason Distribution After Repair

| blocked_reason | projection | card |
|---|---:|---:|
| price_confirmation_failed | 587 | 587 |
| amount_confirmation_failed | 17 | 17 |
| metric_missing | 0 | 0 |

## Action Counts Unchanged

- ActionExecuted projection/card: 1 / 1
- ActionBlocked projection/card: 604 / 604

## Sample Proof

`stock:SH:688690` now shows:

- projection blocked_reason: `amount_confirmation_failed`
- card blocked_reason: `amount_confirmation_failed`
- metric coverage: `full`
- repair policy: `n6.full_metric_union_historical_projection_repair.v1`

## Boundary Proof

- N5 outbox was not consumed or updated.
- `user_notification_queue` rows written: 0.
- decision/virtual order/trade/position/PnL refs: 0.
- No worker, delivery, push, voice, mobile, sim, position, PnL, proposal, order, trade, or real trade was started or generated.
- N5/N4/N3 rows were not updated.

## Rollback

Rollback SQL: `sql/N6_full_metric_union_historical_projection_repair_20260605_rollback.sql`

Rollback is metadata-only and does not delete projection/card rows or touch N5/N4/N3.
