# N6 UI N4 v4 Event Type Classification Repair Contract

Status: `CONTRACT_PASS`

Layer role: `N6_user`

Date: 2026-06-06

This gate defines a read-only contract for expanding the N6 admin console full-lineage message statistics so that N4 v4 event categories are complete. It does not implement the adapter, write the database, consume or update outbox rows, start workers, or create delivery/push/voice/mobile/sim/position/PnL/proposal/order/trade/real-trade side effects.

## Root Cause

The current `GET /api/n6/ui/v1/lineage-stats` contract and implementation only count the N4 `TriggerMatched` event. That is sufficient for the current 20260605 run, but it is incomplete for the N4 v4 standard message model because future runs may also emit:

- `TriggerPendingMarketData`
- `TriggerStateChanged`

If those event types appear, the current UI would omit them from full-lineage statistics.

## N4 v4 Classification Model

N6 UI full-lineage statistics must classify N4 v4 standard events as:

| layer | event_type | UI meaning | N5 action entry |
|---|---|---|---|
| N4 | `TriggerMatched` | 触发成立 | yes, the only N5 action-confirmation entry |
| N4 | `TriggerPendingMarketData` | 候选存在，等待行情/质量证据 | no |
| N4 | `TriggerStateChanged` | 触发状态变化广播 | no |

Legacy N4 events remain compatibility-only:

| layer | event_type | UI handling |
|---|---|---|
| N4 legacy | `TriggerCleared` | hidden by default or displayed only with a legacy label |
| N4 legacy | `TriggerLiveChanged` | hidden by default or displayed only with a legacy label |

N6 must not treat legacy events as new v4 standard output.

## UI Model

The top full-lineage stats region should be grouped as:

```text
全链路消息统计

N4 Events
  TriggerMatched
  TriggerPendingMarketData
  TriggerStateChanged

N5 Actions
  ActionExecuted
  ActionBlocked
```

The current run should render:

| group | statistic | pending |
|---|---|---:|
| N4 Events | `TriggerMatched` | 605 |
| N4 Events | `TriggerPendingMarketData` | 0 |
| N4 Events | `TriggerStateChanged` | 0 |
| N5 Actions | `ActionExecuted` | 1 |
| N5 Actions | `ActionBlocked` | 604 |

The new zero-valued N4 v4 categories are expected and must not change the existing visible counts for `TriggerMatched`, `ActionExecuted`, or `ActionBlocked`.

## Click Filter Contract

Clicking a stats card changes filter state only. It must not mutate any table, consume any outbox, or update any outbox status.

| card | filter state |
|---|---|
| N4 `TriggerMatched` | `source_layer=N4_trigger`, `event_type=TriggerMatched`, `outbox_status=pending` |
| N4 `TriggerPendingMarketData` | `source_layer=N4_trigger`, `event_type=TriggerPendingMarketData`, `outbox_status=pending` |
| N4 `TriggerStateChanged` | `source_layer=N4_trigger`, `event_type=TriggerStateChanged`, `outbox_status=pending` |
| N5 `ActionExecuted` | `source_layer=N5_action`, `event_type=ActionExecuted`, `outbox_status=pending` |
| N5 `ActionBlocked` | `source_layer=N5_action`, `event_type=ActionBlocked`, `outbox_status=pending` |

`blocked_reason` filters belong only to N5 `ActionBlocked`. N4 `TriggerPendingMarketData` must not be grouped under `blocked_reason`, because it is a trigger-layer market-data/quality pending state, not an N5 blocked action.

## API Contract

Extend the existing read-only endpoint:

```text
GET /api/n6/ui/v1/lineage-stats
```

Allowed method: `GET` only.

Forbidden methods: `POST`, `PUT`, `PATCH`, `DELETE`.

Response shape:

```json
{
  "status": "LINEAGE_STATS_PASS",
  "title": "全链路消息统计",
  "source_runs": {
    "N4": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
    "N5": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
    "N6": "user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
  },
  "lineage_stats": {
    "N4": {
      "TriggerMatched": {"pending": 605},
      "TriggerPendingMarketData": {"pending": 0},
      "TriggerStateChanged": {"pending": 0}
    },
    "N5": {
      "ActionExecuted": {"pending": 1},
      "ActionBlocked": {"pending": 604}
    }
  },
  "legacy": {
    "N4": {
      "TriggerCleared": {"pending": 0, "display": "hidden_by_default"},
      "TriggerLiveChanged": {"pending": 0, "display": "hidden_by_default"}
    }
  },
  "blocked_reason": {
    "price_confirmation_failed": 587,
    "amount_confirmation_failed": 17,
    "metric_missing": 0
  }
}
```

## Existing Signals API Boundary

`GET /api/n6/ui/v1/signals` remains the N6 projection/card list API. This contract does not require implementing N4 event list rendering.

If a later implementation supports N4 event list details, it must use a read-only `source_layer=N4_trigger` adapter or a separate read-only N4 outbox endpoint. It must not scan or modify N4 facts, and it must not consume or update N4/N5 outbox status.

## UI Copy

Use:

- `全链路消息统计`
- `N4 Events`
- `TriggerMatched`
- `TriggerPendingMarketData`
- `TriggerStateChanged`
- `N5 Actions`
- `ActionExecuted`
- `ActionBlocked`

Legacy items may be hidden by default or shown with an explicit `legacy` label.

Do not display:

- `TriggerMatched 0` for this source lineage.
- `TriggerPendingMarketData` as `blocked_reason`.
- `TriggerStateChanged` as an N5 action entry.
- `TriggerCleared` or `TriggerLiveChanged` as new v4 standard output.

## Forbidden Scope

- No database writes.
- No N4/N5 facts modification.
- No N6 projection/card modification.
- No notification queue modification.
- No N4/N5 outbox consumption.
- No N4/N5 outbox status update.
- No worker.
- No delivery/push/voice/mobile.
- No sim/position/PnL/real trade.
- No proposal/order/trade.

## Decision

`CONTRACT_PASS`

This contract may proceed to `N6_UI_N4_V4_EVENT_TYPE_CLASSIFICATION_REPAIR_IMPLEMENTATION_GATE`.
