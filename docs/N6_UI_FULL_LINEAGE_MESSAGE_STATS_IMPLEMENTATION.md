# N6 UI Full Lineage Message Stats Implementation

Status: `IMPLEMENTATION_PASS`

Layer role: `N6_user`

Date: 2026-06-06

This implementation adds a read-only full-lineage stats adapter for the N6 admin console. It fixes the misleading zero-valued `TriggerMatched` display by reading N4 `TriggerMatched` counts from the N4 outbox and N5 action counts from the N5 outbox, while preserving the existing N6 projection/card message list.

## Modified Files

- `src/ashare_v3/web/n6_ui_v1.py`
- `src/ashare_v3/web/n6_user_app.py`
- `src/ashare_v3/web/templates/n6_action_events.html`
- `tests/test_n6_user_app.py`
- `docs/N6_UI_FULL_LINEAGE_MESSAGE_STATS_IMPLEMENTATION.md`
- `docs/N6_UI_FULL_LINEAGE_MESSAGE_STATS_IMPLEMENTATION.json`

## API

New read-only endpoint:

```text
GET /api/n6/ui/v1/lineage-stats
```

Response includes:

```json
{
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

Only `GET` is added. No mutation route was added.

## UI

The action events page now renders the stats section as:

```text
全链路消息统计
N4 TriggerMatched 605
N5 ActionExecuted 1
N5 ActionBlocked 604
price_confirmation_failed 587
amount_confirmation_failed 17
metric_missing 0
```

The previous misleading zero-valued `TriggerMatched` stats card is removed from this section.

## Click Filters

- N4 TriggerMatched: `source_layer=N4_trigger&event_type=TriggerMatched&outbox_status=pending`
- N5 ActionExecuted: `source_layer=N5_action&event_type=ActionExecuted&outbox_status=pending`
- N5 ActionBlocked: `source_layer=N5_action&event_type=ActionBlocked&outbox_status=pending`

These links only set GET query parameters. They do not mutate data.

## Preserved Behavior

- `/api/n6/ui/v1/signals` remains the N6 projection/card list endpoint.
- Existing projection/card list filtering remains unchanged.
- N4 TriggerMatched detail-list rendering remains a future read-only adapter concern.

## Forbidden Scope Proof

- No database writes.
- No outbox consumption.
- No outbox status updates.
- No worker startup.
- No delivery/push/voice/mobile.
- No sim/position/PnL/real trade.
- No proposal/order/trade.
- No N4/N5 fact modification.
- No N6 projection/card data modification.

## Validation

- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'`: 44 tests OK.
- Additional validation is recorded in the final gate output.
