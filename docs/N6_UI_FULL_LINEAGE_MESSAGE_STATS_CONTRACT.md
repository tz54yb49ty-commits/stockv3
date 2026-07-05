# N6 UI Full Lineage Message Stats Contract

Status: `CONTRACT_PASS`

Layer role: `N6_user`

Date: 2026-06-06

This gate defines a read-only UI contract for correcting the N6 admin console message statistics. It does not implement the endpoint, write the database, consume or update outbox rows, start workers, or create delivery/push/voice/mobile/sim/position/PnL/proposal/order/trade/real-trade side effects.

## Root Cause

The current message stats card is mixing labels from the full N4 -> N5 lineage with a data set that only counts N5-derived N6 projection/card rows. Because N6 projection/card rows are produced from N5 action events, the current stats path has no N4 `TriggerMatched` rows and therefore renders the N4 trigger count as zero. That is a UI aggregation-scope bug, not an N4 trigger absence.

## Recommended Model

Use a separate full-lineage message statistics model:

```text
lineage_stats.N4.TriggerMatched.pending
lineage_stats.N5.ActionExecuted.pending
lineage_stats.N5.ActionBlocked.pending
blocked_reason distribution for N5 ActionBlocked only
```

The top stats region title must be:

```text
全链路消息统计
```

It must display:

| statistic | value | source |
|---|---:|---|
| N4 TriggerMatched | 605 | `common_event_outbox` / `source_run_id=trigger_execute_20260605_condition_layer_20260604_source_20260604_v1` / `event_type=TriggerMatched` / `status=pending` |
| N5 ActionExecuted | 1 | `common_event_outbox` / `source_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1` / `event_type=ActionExecuted` / `status=pending` |
| N5 ActionBlocked | 604 | `common_event_outbox` / same N5 action run / `event_type=ActionBlocked` / `status=pending` |

The UI must not render a zero N4 trigger count for this source lineage.

## Blocked Reason Scope

`blocked_reason` statistics belong only to N5 `ActionBlocked` after N6 metadata repair:

| blocked_reason | count |
|---|---:|
| `price_confirmation_failed` | 587 |
| `amount_confirmation_failed` | 17 |
| `metric_missing` | 0 |

This is sourced from repaired N6 projection/card metadata and must not be confused with N4 trigger stats.

## API Contract

Add a read-only endpoint:

```text
GET /api/n6/ui/v1/lineage-stats
```

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
      "TriggerMatched": {"pending": 605}
    },
    "N5": {
      "ActionExecuted": {"pending": 1},
      "ActionBlocked": {"pending": 604}
    }
  },
  "blocked_reason": {
    "price_confirmation_failed": 587,
    "amount_confirmation_failed": 17,
    "metric_missing": 0
  }
}
```

Allowed method: `GET` only.

Forbidden methods: `POST`, `PUT`, `PATCH`, `DELETE`.

## Click Filter Contract

Clicking a stats card updates UI filter state only. It must not mutate any table.

| card | filter state |
|---|---|
| N4 TriggerMatched | `source_layer=N4_trigger`, `event_type=TriggerMatched`, `outbox_status=pending` |
| N5 ActionExecuted | `source_layer=N5_action`, `event_type=ActionExecuted`, `outbox_status=pending` |
| N5 ActionBlocked | `source_layer=N5_action`, `event_type=ActionBlocked`, `outbox_status=pending` |

Clicking N4 `TriggerMatched` must not set `blocked_reason` and must not mix in the N5 `ActionBlocked` filter.

## Existing Signals API Boundary

`GET /api/n6/ui/v1/signals` remains the N6 projection/card message list. It should not be broken by full-lineage stats.

If implementation later supports N4 `TriggerMatched` details, it must use a read-only source-layer filter or a separate read-only N4 outbox adapter. That implementation must not scan or modify N4 facts, and must not consume or update N4/N5 outbox status.

## UI Copy

Use:

- `全链路消息统计`
- `N4 TriggerMatched`
- `N5 ActionExecuted`
- `N5 ActionBlocked`

Do not display a zero N4 trigger count for this lineage.

## Forbidden Scope

- No database writes.
- No N4/N5 outbox consumption.
- No outbox status updates.
- No worker.
- No delivery/push/voice/mobile.
- No sim/position/PnL/real trade.
- No proposal/order/trade.
- No N4/N5 fact changes.
- No N6 projection/card data changes.

## Decision

`CONTRACT_PASS`

This contract may proceed to `N6_UI_FULL_LINEAGE_MESSAGE_STATS_IMPLEMENTATION_GATE`.
