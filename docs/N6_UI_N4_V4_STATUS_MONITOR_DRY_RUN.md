# N6 UI N4 v4 Status Monitor Dry Run

Status: `DRY_RUN_PASS`

Layer role: `N6_user`

Date: 2026-06-07

Gate: `N6_UI_N4_V4_STATUS_MONITOR_CONTRACT_GATE`

This dry-run validates the proposed `/n6/status-monitor` page model and `GET /api/n6/ui/v1/status-monitor` API contract using the current reviewed N6 UI lineage counts. It is artifact-only and read-only: no implementation, no database write, no route registration, no N4/N5 fact modification, no N6 projection/card modification, no notification queue write, no outbox consumption or status update, no worker, no delivery/push/voice/mobile, no sim/position/PnL, no proposal/order/trade, and no real trading.

## Input Counts

| layer | event_type | count |
|---|---|---:|
| N4 | `TriggerMatched` | 605 |
| N4 | `TriggerPendingMarketData` | 0 |
| N4 | `TriggerStateChanged` | 0 |
| N5 | `ActionExecuted` | 1 |
| N5 | `ActionBlocked` | 604 |

## Reconciliation Dry Run

Action-flow reconciliation:

```text
TriggerMatched = ActionExecuted + ActionBlocked
605 = 1 + 604
result = PASS
```

Status-flow isolation:

```text
TriggerPendingMarketData -> ActionExecuted/ActionBlocked = 0
TriggerStateChanged -> ActionExecuted/ActionBlocked = 0
result = PASS
```

## Page Model Dry Run

Route planned:

```text
/n6/status-monitor
```

Rendered stats:

| group | label | count |
|---|---|---:|
| N4 Events | `TriggerMatched` | 605 |
| N4 Events | `TriggerPendingMarketData` | 0 |
| N4 Events | `TriggerStateChanged` | 0 |
| N5 Relationship | `ActionExecuted` | 1 |
| N5 Relationship | `ActionBlocked` | 604 |

Status tabs:

| status | count | derivation |
|---|---:|---|
| `active` | 605 | `TriggerMatched -> current_status=matched -> active` |
| `pending_market_data` | 0 | `TriggerPendingMarketData` |
| `inactive` | 0 | `TriggerStateChanged(current_status=inactive)` |

The dry-run keeps `/n6/action-events` separate. No click navigates into the action-events page by default.

## API Dry Run

Planned endpoint:

```text
GET /api/n6/ui/v1/status-monitor
```

Allowed methods:

```text
GET
```

Forbidden methods:

```text
POST
PUT
PATCH
DELETE
```

Response preview:

```json
{
  "status": "STATUS_MONITOR_PASS",
  "title": "N6 Status Monitor",
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
  }
}
```

## Click Behavior Dry Run

| click target | result | side effect |
|---|---|---|
| `TriggerMatched` | filter `event_type=TriggerMatched`, `status=active` | none |
| `TriggerPendingMarketData` | filter `event_type=TriggerPendingMarketData`, `status=pending_market_data` | none |
| `TriggerStateChanged` | filter `event_type=TriggerStateChanged` | none |
| `ActionExecuted` | filter `action_event_type=ActionExecuted` | none |
| `ActionBlocked` | filter `action_event_type=ActionBlocked` | none |
| `active` tab | filter `status=active` | none |
| `pending_market_data` tab | filter `status=pending_market_data` | none |
| `inactive` tab | filter `status=inactive` | none |
| row click | open read-only drawer | none |

## UI Mock Dry Run

```text
N6 Status Monitor                                      READ ONLY

N4 Events
TriggerMatched 605 | TriggerPendingMarketData 0 | TriggerStateChanged 0

N5 Relationship
ActionExecuted 1 | ActionBlocked 604 | Matched reconciliation PASS

Status
[active 605] [pending_market_data 0] [inactive 0]

No action entry is shown for TriggerPendingMarketData or TriggerStateChanged rows.
```

## Boundary Proof

```text
implementation_performed=false
database_written=false
N4_N5_facts_modified=false
N6_projection_card_modified=false
notification_queue_modified=false
outbox_consumed=false
outbox_status_updated=false
inbox_checkpoint_updated=false
worker_started=false
delivery_push_voice_mobile=false
sim_position_pnl=false
proposal_order_trade=false
real_trade=false
```

## Validation Summary

```text
JSON parse: PASS
GET-only route scan: PASS
UI wording scan: PASS
git diff --check: PASS
```

## Decision

`DRY_RUN_PASS`

`N6_UI_N4_V4_STATUS_MONITOR_IMPLEMENTATION_GATE` is allowed from this contract/dry-run perspective.
