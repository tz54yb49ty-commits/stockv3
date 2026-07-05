# N6 UI Full Lineage Message Stats Dry Run

Status: `DRY_RUN_PASS`

Layer role: `N6_user`

Date: 2026-06-06

This dry-run confirms the full-lineage stats source counts using read-only database queries. No implementation or database write was performed.

## Read-Only Proof

| layer | event | status | count |
|---|---|---|---:|
| N4 | `TriggerMatched` | `pending` | 605 |
| N5 | `ActionExecuted` | `pending` | 1 |
| N5 | `ActionBlocked` | `pending` | 604 |

Delivered/delivering rows for this N5 action run are 0/0.

## N6 Repaired Metadata Proof

N6 projection/card metadata is aligned with the full metric-union repair:

| blocked_reason | count |
|---|---:|
| `price_confirmation_failed` | 587 |
| `amount_confirmation_failed` | 17 |
| `metric_missing` | 0 |

## UI Dry Run

The stats card region would render:

- title: `全链路消息统计`
- `N4 TriggerMatched`: 605
- `N5 ActionExecuted`: 1
- `N5 ActionBlocked`: 604

It must not render a zero N4 trigger count for this source lineage.

## Click Filters

| click target | resulting filter state |
|---|---|
| N4 TriggerMatched | `source_layer=N4_trigger`, `event_type=TriggerMatched`, `outbox_status=pending` |
| N5 ActionExecuted | `source_layer=N5_action`, `event_type=ActionExecuted`, `outbox_status=pending` |
| N5 ActionBlocked | `source_layer=N5_action`, `event_type=ActionBlocked`, `outbox_status=pending` |

## Boundary Proof

- No database write.
- No outbox consumption or status update.
- No notification queue write; scoped queue remains 0.
- No worker.
- No delivery/push/voice/mobile.
- No sim/position/PnL/real trade.
- No proposal/order/trade.
- No N4/N5 facts modified.
- No N6 projection/card data modified.

## Decision

`DRY_RUN_PASS`
