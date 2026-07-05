# N6 UI N4 v4 Event Type Classification Repair Implementation

Status: `IMPLEMENTATION_PASS`

Layer role: `N6_user`

Date: 2026-06-06

This gate implements the read-only N4 v4 event type classification repair for the N6 admin console full-lineage message statistics. It extends the existing N6 UI read-only API/model/template only. It does not write the database, consume or update outbox rows, start workers, or trigger delivery/push/voice/mobile/sim/position/PnL/proposal/order/trade/real-trade side effects.

## Implemented API Model

The existing endpoint remains:

```text
GET /api/n6/ui/v1/lineage-stats
```

The endpoint now returns N4 v4 standard event categories:

```text
N4.TriggerMatched.pending
N4.TriggerPendingMarketData.pending
N4.TriggerStateChanged.pending
```

It also returns N4 legacy compatibility counters under `legacy.N4`:

```text
TriggerCleared
TriggerLiveChanged
```

Legacy entries are marked `hidden_by_default`.

N5 action categories are unchanged:

```text
N5.ActionExecuted.pending
N5.ActionBlocked.pending
```

`blocked_reason` remains scoped only to N5 `ActionBlocked`.

## UI Model

The full-lineage stats region still uses:

```text
全链路消息统计
```

It now groups cards as:

```text
N4 Events
  N4 TriggerMatched
  N4 TriggerPendingMarketData
  N4 TriggerStateChanged

N5 Actions
  N5 ActionExecuted
  N5 ActionBlocked
```

Blocked reason cards remain separate and are not displayed as N4 event categories.

## Click Filter Behavior

| card | filter state |
|---|---|
| N4 TriggerMatched | `source_layer=N4_trigger`, `event_type=TriggerMatched`, `outbox_status=pending` |
| N4 TriggerPendingMarketData | `source_layer=N4_trigger`, `event_type=TriggerPendingMarketData`, `outbox_status=pending` |
| N4 TriggerStateChanged | `source_layer=N4_trigger`, `event_type=TriggerStateChanged`, `outbox_status=pending` |
| N5 ActionExecuted | `source_layer=N5_action`, `event_type=ActionExecuted`, `outbox_status=pending` |
| N5 ActionBlocked | `source_layer=N5_action`, `event_type=ActionBlocked`, `outbox_status=pending` |

The event type dropdown now includes the three N4 v4 standard types.

## Dry-Run Proof

Current read-only DB proof remains:

| layer | event_type | pending |
|---|---|---:|
| N4 | `TriggerMatched` | 605 |
| N4 | `TriggerPendingMarketData` | 0 |
| N4 | `TriggerStateChanged` | 0 |
| N5 | `ActionExecuted` | 1 |
| N5 | `ActionBlocked` | 604 |

Blocked reason distribution:

| blocked_reason | count |
|---|---:|
| `price_confirmation_failed` | 587 |
| `amount_confirmation_failed` | 17 |
| `metric_missing` | 0 |

## Modified Files

- `src/ashare_v3/web/n6_user_app.py`
- `src/ashare_v3/web/n6_ui_v1.py`
- `src/ashare_v3/web/templates/n6_action_events.html`
- `tests/test_n6_user_app.py`

## Validation

- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'`
- JSON artifact parse
- GET-only route scan
- UI wording scan
- compileall
- boundary scan
- `git diff --check`

## Forbidden Scope

- No database writes.
- No N4/N5 facts modified.
- No N6 projection/card modified.
- No notification queue modified.
- No N4/N5 outbox consumption.
- No N4/N5 outbox status update.
- No worker.
- No delivery/push/voice/mobile.
- No sim/position/PnL/real trade.
- No proposal/order/trade.

## Decision

`IMPLEMENTATION_PASS`
