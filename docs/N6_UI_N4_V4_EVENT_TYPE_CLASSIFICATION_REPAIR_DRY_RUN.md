# N6 UI N4 v4 Event Type Classification Repair Dry Run

Status: `DRY_RUN_PASS`

Layer role: `N6_user`

Date: 2026-06-06

This dry-run verifies the proposed N4 v4 classification expansion against the current database state using read-only checks only. No implementation or database write was performed.

## Read-Only N4 Proof

Source run:

```text
trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

| event_type | pending |
|---|---:|
| `TriggerMatched` | 605 |
| `TriggerPendingMarketData` | 0 |
| `TriggerStateChanged` | 0 |

Legacy compatibility events:

| event_type | pending |
|---|---:|
| `TriggerCleared` | 0 |
| `TriggerLiveChanged` | 0 |

The current DB only contains `TriggerMatched` for this source run. Adding the two missing N4 v4 categories would not change existing visible counts; it would only make future runs complete.

## Read-Only N5 Proof

Source run:

```text
action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

| event_type | pending |
|---|---:|
| `ActionExecuted` | 1 |
| `ActionBlocked` | 604 |

## Blocked Reason Proof

`blocked_reason` remains scoped to N5 `ActionBlocked` only:

| blocked_reason | count |
|---|---:|
| `price_confirmation_failed` | 587 |
| `amount_confirmation_failed` | 17 |
| `metric_missing` | 0 |

`TriggerPendingMarketData` must not be counted as `blocked_reason`.

## UI Dry Run

The expanded stats region would render:

```text
全链路消息统计

N4 Events
  TriggerMatched 605
  TriggerPendingMarketData 0
  TriggerStateChanged 0

N5 Actions
  ActionExecuted 1
  ActionBlocked 604
```

Current user-visible non-zero values remain unchanged:

- `TriggerMatched`: 605
- `ActionExecuted`: 1
- `ActionBlocked`: 604

## Click Filters

| click target | resulting filter state |
|---|---|
| N4 `TriggerMatched` | `source_layer=N4_trigger`, `event_type=TriggerMatched`, `outbox_status=pending` |
| N4 `TriggerPendingMarketData` | `source_layer=N4_trigger`, `event_type=TriggerPendingMarketData`, `outbox_status=pending` |
| N4 `TriggerStateChanged` | `source_layer=N4_trigger`, `event_type=TriggerStateChanged`, `outbox_status=pending` |
| N5 `ActionExecuted` | `source_layer=N5_action`, `event_type=ActionExecuted`, `outbox_status=pending` |
| N5 `ActionBlocked` | `source_layer=N5_action`, `event_type=ActionBlocked`, `outbox_status=pending` |

## Boundary Proof

- No database write.
- No N4/N5 fact modification.
- No N6 projection/card modification.
- No notification queue modification.
- No N4/N5 outbox consumption.
- No N4/N5 outbox status update.
- No worker.
- No delivery/push/voice/mobile.
- No sim/position/PnL/real trade.
- No proposal/order/trade.

## Decision

`DRY_RUN_PASS`
