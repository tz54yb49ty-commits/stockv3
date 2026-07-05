# N6 UI N4 v4 Status Monitor Contract

Status: `CONTRACT_PASS`

Layer role: `N6_user`

Date: 2026-06-07

Gate: `N6_UI_N4_V4_STATUS_MONITOR_CONTRACT_GATE`

This gate defines a read-only administrator page contract for monitoring the relationship between N4 v4 trigger events and N5 action outcomes. It is contract and UI-spec only. It does not implement a route, write the database, modify N4/N5 facts, modify N6 projection/card data, write notification queue rows, consume or update outbox rows, start workers, deliver/push/voice/mobile, write sim/position/PnL, create proposal/order/trade, or perform real trading.

## Purpose

Add a separate administrator status page:

```text
/n6/status-monitor
```

The page must separate two flows:

```text
Action flow:
TriggerMatched
-> ActionExecuted / ActionBlocked

Status flow:
TriggerPendingMarketData
TriggerStateChanged
```

`TriggerPendingMarketData` and `TriggerStateChanged` are status-monitoring inputs only. They must not be treated as N5 action entries, must not enter the N6 action projection/card list, and must not create delivery, voice, mobile, sim, position, PnL, proposal, order, or trade behavior.

## Current Data

The current reviewed N6 UI lineage data is:

| layer | event_type | pending |
|---|---|---:|
| N4 | `TriggerMatched` | 605 |
| N4 | `TriggerPendingMarketData` | 0 |
| N4 | `TriggerStateChanged` | 0 |
| N5 | `ActionExecuted` | 1 |
| N5 | `ActionBlocked` | 604 |

The current action-flow reconciliation is:

```text
TriggerMatched = ActionExecuted + ActionBlocked
605 = 1 + 604
```

The current status-flow action count is:

```text
TriggerPendingMarketData action entries = 0
TriggerStateChanged action entries = 0
```

## Page Model

Route:

```text
GET /n6/status-monitor
```

Audience:

```text
admin only
read only
```

Primary zones:

| zone | content |
|---|---|
| Header | `N6 Status Monitor`, source run labels, read-only badges |
| N4 Events | `TriggerMatched`, `TriggerPendingMarketData`, `TriggerStateChanged` counts |
| N5 Relationship | `ActionExecuted`, `ActionBlocked`, matched-to-action reconciliation |
| Status List | `active`, `pending_market_data`, `inactive` tabs and rows |
| Detail Drawer | read-only event payload summary and relationship trace |

The status list must expose exactly these canonical UI status keys:

| status_key | canonical N4 state | trigger_live | action entry |
|---|---|---:|---:|
| `active` | `matched` | true | only when source event is `TriggerMatched` |
| `pending_market_data` | `pending_market_data` | false | no |
| `inactive` | `inactive` | false | no |

`active` is the UI label for canonical `current_status=matched`; it must not become an N5 action state.

## Allowed Read Sources

Future implementation may read only approved event/projection surfaces:

- N4 standard event rows from `common_event_outbox` or `common_event_ledger`.
- N5 standard action event rows from `common_event_outbox` or `common_event_ledger`.
- Existing reviewed N6 projection/card metadata only for already-approved N5 blocked-reason display.

Future implementation must not read or mutate N4/N5 internal naked facts to replace standard events:

- no direct `common_trigger_state` / `*_trigger_state` UI source
- no direct `common_trigger_match` / `*_trigger_match` UI source
- no direct `common_action_fact` / `*_action_fact` UI source
- no database write, status update, outbox consumption, inbox/checkpoint update, or worker

## Status Derivation

Status rows are derived from N4 standard event payloads:

| N4 event_type | status derivation |
|---|---|
| `TriggerMatched` | `status_key=active`, `current_status=matched`, `trigger_live=true` |
| `TriggerPendingMarketData` | `status_key=pending_market_data`, `current_status=pending_market_data`, `trigger_live=false` |
| `TriggerStateChanged` | use payload `current_status`; map `matched -> active`, `pending_market_data -> pending_market_data`, `inactive -> inactive` |

`TriggerStateChanged` can broadcast a live state, but it remains a state event. It must not create an action relationship unless a separate `TriggerMatched` event exists for the same trigger grain.

## API Contract

Add a future read-only endpoint:

```text
GET /api/n6/ui/v1/status-monitor
```

Allowed method: `GET` only.

Forbidden methods: `POST`, `PUT`, `PATCH`, `DELETE`.

Allowed query parameters:

| parameter | meaning |
|---|---|
| `trade_date` | business date filter |
| `source_n4_run_id` | N4 run override; default latest reviewed UI lineage |
| `source_n5_run_id` | N5 run override; default matching reviewed action lineage |
| `status` | `active`, `pending_market_data`, `inactive` |
| `event_type` | N4/N5 event type filter |
| `action_event_type` | `ActionExecuted` or `ActionBlocked` |
| `asset_kind` | `stock`, `index`, `board` |
| `direction` | `buy`, `sell` |
| `signal_type` | `B_BUY`, `S_SELL` |
| `q` | code, identity_key, event_id, condition_key keyword |
| `limit` | default 100, max 500 |
| `offset` | default 0 |

Response model:

```json
{
  "status": "STATUS_MONITOR_PASS",
  "title": "N6 Status Monitor",
  "page_route": "/n6/status-monitor",
  "source_runs": {
    "N4": "trigger_execute_20260605_condition_layer_20260604_source_20260604_v1",
    "N5": "action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1"
  },
  "event_summary": {
    "N4": {
      "TriggerMatched": {"pending": 605, "action_entry": true},
      "TriggerPendingMarketData": {"pending": 0, "action_entry": false},
      "TriggerStateChanged": {"pending": 0, "action_entry": false}
    },
    "N5": {
      "ActionExecuted": {"pending": 1},
      "ActionBlocked": {"pending": 604}
    }
  },
  "relationship_summary": {
    "matched_to_action": {
      "TriggerMatched": 605,
      "ActionExecuted": 1,
      "ActionBlocked": 604,
      "unmatched": 0
    },
    "status_only": {
      "TriggerPendingMarketData_action_entries": 0,
      "TriggerStateChanged_action_entries": 0
    }
  },
  "status_summary": {
    "active": {"count": 605, "trigger_live": true},
    "pending_market_data": {"count": 0, "trigger_live": false},
    "inactive": {"count": 0, "trigger_live": false}
  },
  "items": [],
  "pagination": {"total_count": 605, "filtered_count": 605, "limit": 100, "offset": 0},
  "side_effects": {"writes_database": false}
}
```

## Click Behavior

All clicks update local filter state only.

| click target | resulting filter |
|---|---|
| N4 `TriggerMatched` count | `source_layer=N4_trigger`, `event_type=TriggerMatched`, `status=active`, `outbox_status=pending` |
| N4 `TriggerPendingMarketData` count | `source_layer=N4_trigger`, `event_type=TriggerPendingMarketData`, `status=pending_market_data`, `outbox_status=pending` |
| N4 `TriggerStateChanged` count | `source_layer=N4_trigger`, `event_type=TriggerStateChanged`, `outbox_status=pending` |
| N5 `ActionExecuted` count | `source_layer=N5_action`, `action_event_type=ActionExecuted`, `status=active`, `outbox_status=pending` |
| N5 `ActionBlocked` count | `source_layer=N5_action`, `action_event_type=ActionBlocked`, `status=active`, `outbox_status=pending` |
| Status tab `active` | `status=active` |
| Status tab `pending_market_data` | `status=pending_market_data` |
| Status tab `inactive` | `status=inactive` |
| Row click | open read-only detail drawer |

Clicks must not navigate into `/n6/action-events` by default. The status monitor is a separate page and must not reuse the N6 action projection/card list as its primary data set.

## UI Mock

```text
N6 Status Monitor                                      READ ONLY
Source: N4 trigger_execute_20260605...  N5 action_consumer_action_pipeline_20260605...

N4 Events
+----------------------+----------------------------+----------------------+
| TriggerMatched 605   | TriggerPendingMarketData 0 | TriggerStateChanged 0|
+----------------------+----------------------------+----------------------+

N5 Relationship
+-------------------+------------------+-----------------------------+
| ActionExecuted 1  | ActionBlocked 604| matched reconciliation PASS |
+-------------------+------------------+-----------------------------+

Status
[active 605] [pending_market_data 0] [inactive 0]

List columns:
status | event_type | asset | direction | signal_type | condition_key |
trigger_live | N5 relationship | event_time | detail

Detail drawer:
N4 event summary
N5 relationship summary
canonical boundary: status-only events do not create action entries
side effects: all disabled
```

## UI Wording

Allowed rendered labels:

- `N6 Status Monitor`
- `N4 Events`
- `N5 Relationship`
- `TriggerMatched`
- `TriggerPendingMarketData`
- `TriggerStateChanged`
- `ActionExecuted`
- `ActionBlocked`
- `active`
- `pending_market_data`
- `inactive`
- `READ ONLY`
- `No action entry`
- `Matched reconciliation PASS`

Forbidden rendered labels:

- `已下单`
- `已成交`
- `真实交易`
- `虚拟成交`
- `建议买入`
- `交易失败`
- `下单失败`
- `持仓失败`
- `proposal`
- `order`
- `trade`
- `voice`
- `mobile push`

## Forbidden Scope

- No database writes.
- No N4/N5 facts modification.
- No N6 projection/card modification.
- No notification queue modification.
- No outbox consumption.
- No outbox status update.
- No inbox/checkpoint update.
- No worker.
- No delivery/push/voice/mobile.
- No sim/position/PnL.
- No proposal/order/trade.
- No real trading.

## Decision

`CONTRACT_PASS`

This contract may proceed to `N6_UI_N4_V4_STATUS_MONITOR_IMPLEMENTATION_GATE` after the matching dry-run artifacts pass validation.
