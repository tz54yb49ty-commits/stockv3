# N6 UI Full-Lineage Message Stats Closeout

Status: CLOSEOUT_PASS

Layer role: runtime_control

Generated at: 2026-06-06T23:24:10+08:00

## Scope

This gate only registers closeout for the N6 UI full-lineage message stats repair. It did not write database rows, execute rollback, update projection/card data, consume or update outbox, start workers, enter delivery/push/voice/mobile, touch sim/position/PnL/real trade, or generate proposal/order/trade.

## Root Cause

Old behavior:

```text
UI message statistics read N5/N6 projection/card rows while labeling one statistic as TriggerMatched.
N6 projection/card rows are derived from N5 action events and contain no N4 TriggerMatched rows.
Result: TriggerMatched displayed as 0.
```

New behavior:

```text
Full-lineage stats read N4 TriggerMatched from N4 outbox.
Full-lineage stats read N5 ActionExecuted/ActionBlocked from N5 outbox.
/api/n6/ui/v1/signals remains the projection/card list API.
```

## API Summary

Route:

```text
GET /api/n6/ui/v1/lineage-stats
```

Proof:

```text
title=全链路消息统计
N4.TriggerMatched.pending=605
N5.ActionExecuted.pending=1
N5.ActionBlocked.pending=604
blocked_reason.price_confirmation_failed=587
blocked_reason.amount_confirmation_failed=17
blocked_reason.metric_missing=0
```

## UI Summary

Route:

```text
/n6/action-events
```

The page displays:

```text
全链路消息统计
N4 TriggerMatched 605
N5 ActionExecuted 1
N5 ActionBlocked 604
price_confirmation_failed 587
amount_confirmation_failed 17
metric_missing 0
```

The page no longer displays the misleading `TriggerMatched 0` stats card.

Click behavior for the N4 card:

```text
source_layer=N4_trigger
event_type=TriggerMatched
outbox_status=pending
```

## Projection/Card Regression

`GET /api/n6/ui/v1/signals` remains scoped to the projection/card list.

```text
ActionExecuted=1
ActionBlocked=604
TriggerMatched in projection/card list=0
blocked_reason.price_confirmation_failed=587
blocked_reason.amount_confirmation_failed=17
blocked_reason.metric_missing=0
```

## Boundary Proof

```text
N4 TriggerMatched outbox pending=605
N5 ActionExecuted outbox pending=1
N5 ActionBlocked outbox pending=604
user_projection_run=1
user_signal_projection=605
user_signal_card=605
scoped user_notification_queue=0
delivery_attempt=0
position_state/position_event=0/0
virtual_order/virtual_trade/virtual_position=0/0/0
```

Existing N4 -> N5 inbox/checkpoint refs are prior approved lineage refs, not writes from this closeout gate.

## Forbidden Scope

```text
database_writes=false
rollback_executed=false
N4/N5 facts modified=false
N6 projection/card modified=false
notification_queue_updated=false
outbox_consumed=false
outbox_status_updated=false
inbox_checkpoint_updated_by_this_gate=false
worker_started=false
delivery/push/voice/mobile=false
sim/position/PnL/real_trade=false
proposal/order/trade=false
```

## Validation Summary

```text
test_n6_user_app.py: PASS, 44 tests
test_n6_*.py: PASS, 124 tests
compileall: PASS
JSON parse: PASS
GET-only route scan: PASS
git diff --check: PASS
```

## Decision

```text
N6_UI_FULL_LINEAGE_MESSAGE_STATS complete
```
