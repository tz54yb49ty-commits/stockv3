# N6 UI Readonly Message Filter And Card Layout Implementation

Status: IMPLEMENTATION_PASS

Gate: N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_IMPLEMENTATION_GATE

Layer role: N6_user

Date: 2026-06-06

## Scope

This implementation keeps N6_UI_v1 as the A-track admin readonly console.

Implemented:

- Extended `GET /api/n6/ui/v1/signals` with readonly filters.
- Added pagination metadata with `total_count` and `filtered_count`.
- Added readonly statistics for click-to-filter summary cards.
- Replaced the action-events message table area with filter controls, statistics cards, message cards, and detail drawers.
- Kept ActionExecuted wording as `市场动作确认成立`.
- Kept ActionBlocked wording as `市场动作未确认`.
- Kept proposal eligibility as `projection_only` / display-only for the admin console.

Not implemented:

- No proposal generation.
- No order/trade generation.
- No position/pnl update.
- No notification queue write.
- No delivery, push, voice, mobile, sim, position, pnl, or real trade.
- No B-track route/API changes.

## Modified Files

- `src/ashare_v3/web/n6_user_app.py`
- `src/ashare_v3/web/n6_ui_v1.py`
- `src/ashare_v3/web/templates/n6_action_events.html`
- `tests/test_n6_user_app.py`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_IMPLEMENTATION.md`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_IMPLEMENTATION.json`

## API Implementation

Only the existing GET route is extended:

```text
GET /api/n6/ui/v1/signals
```

Supported readonly query parameters:

- `date_from`
- `date_to`
- `time_field=event_time|created_at`
- `event_type`
- `action_state`
- `asset_kind`
- `direction`
- `signal_type`
- `blocked_reason`
- `q`
- `limit`
- `offset`

Pagination:

- Default `limit=100`
- Maximum `limit=500`
- Response includes `total_count`, `filtered_count`, `limit`, and `offset`

## Readonly DB Proof

Executed with explicit local DSN and readonly repository methods.

```text
empty filters count = 605
empty page size = 100
blocked_reason=metric_missing = 289
action_state=blocked + blocked_reason=price_confirmation_failed = 305
event_type=ActionExecuted = 1
event_type=ActionBlocked = 604
date range 2026-06-05 by event_time = 605
```

Statistics:

```text
total_count = 605
ActionExecuted = 1
ActionBlocked = 604
TriggerMatched = 0
amount_confirmation_failed = 10
metric_missing = 289
price_confirmation_failed = 305
```

## UI Implementation

The `/n6/action-events` page now contains:

- Safety banner.
- Top filter bar for dates and time field.
- Category filters for event type, asset kind, direction, signal type, blocked reason, and keyword.
- Statistics cards for ActionExecuted, ActionBlocked, TriggerMatched, and blocked_reason distribution.
- Card list for messages.
- Detail drawer for lineage, blocked reason, trigger context, and admin-console safety status.

The list no longer displays long `event_id` values directly. Full identifiers appear only inside the detail drawer.

## Detail Drawer

Each card exposes a readonly detail drawer with:

- `event_id`
- `N4 trigger event id`
- `N5 action event id`
- `action_run_id`
- `source_action_status`
- `blocked_reason`
- `trigger_price`
- `triggered_periods`
- `baseline_source`
- `proposal_eligibility.behavior=projection_only`
- `READ ONLY / NO ORDER / NO TRADE / NO POSITION UPDATE / NO REAL TRADE / NOT INVESTMENT ADVICE`

## Forbidden Wording

The implementation avoids the following user-facing phrases in the tested page and action detail path:

- `已下单`
- `已成交`
- `真实交易`
- `虚拟成交`
- `建议买入`
- `交易失败`
- `下单失败`
- `持仓失败`

## Boundary Proof

Confirmed:

- `writes_database=false`
- `n5_outbox_consumed=false`
- `n5_outbox_status_updated=false`
- `notification_queue_written=false`
- `worker_started=false`
- `delivery_push_voice_mobile=false`
- `sim_position_pnl_real_trade=false`
- `proposal_order_trade_generated=false`
- `b_track_modified=false`

## Validation

Passed:

- `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'`
- Real DB readonly filter proof

Additional final verification commands are recorded in the JSON artifact.

## Post Review

Allowed next gate:

```text
N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_POST_REVIEW_GATE
```
