# N6 UI Full-Lineage Message Stats Post-Review

Status: POST_REVIEW_PASS

Layer role: runtime_control

Generated at: 2026-06-06T23:20:40+08:00

## Scope

This post-review is read-only. It did not write database rows, did not execute N6 repair, did not consume or update outbox/inbox/checkpoint, did not start a worker, did not trigger delivery/push/voice/mobile, did not touch sim/position/PnL/real trade, did not generate proposal/order/trade, and did not modify N4/N5 facts or N6 projection/card rows.

## API Proof

`GET /api/n6/ui/v1/lineage-stats` returned HTTP 200.

```text
title=全链路消息统计
N4.TriggerMatched.pending=605
N5.ActionExecuted.pending=1
N5.ActionBlocked.pending=604
blocked_reason.price_confirmation_failed=587
blocked_reason.amount_confirmation_failed=17
blocked_reason.metric_missing=0
```

The response side-effect flags remain false:

```text
writes_database=false
outbox_status_updates=0
delivery/push/voice/mobile=false
sim/position/real_trade=false
proposal/order/trade=false
```

## UI Proof

`GET /n6/action-events` rendered HTTP 200.

Verified page signals:

```text
contains "全链路消息统计" = true
contains "N4 TriggerMatched" = true
displays N4 TriggerMatched count 605 = true
does not display misleading TriggerMatched 0 card = true
N4 card href includes source_layer=N4_trigger&event_type=TriggerMatched&outbox_status=pending
N5 ActionExecuted displays 1
N5 ActionBlocked displays 604
price_confirmation_failed displays 587
amount_confirmation_failed displays 17
metric_missing displays 0
```

## Regression Proof

`GET /api/n6/ui/v1/signals` remains the projection/card list API.

```text
total_count=605
filtered_count=605
first_page_item_count=100
ActionExecuted=1
ActionBlocked=604
TriggerMatched in projection/card list=0
blocked_reason.price_confirmation_failed=587
blocked_reason.amount_confirmation_failed=17
blocked_reason.metric_missing=0
```

Filter proof:

```text
action_state=blocked&blocked_reason=price_confirmation_failed -> 587
action_state=blocked&blocked_reason=amount_confirmation_failed -> 17
action_state=blocked&blocked_reason=metric_missing -> 0
```

## Boundary Proof

Live DB read-only proof:

```text
target_db=ashare_v3 / ashare_v3_user / 127.0.0.1:5432
N4 TriggerMatched outbox pending=605
N5 ActionBlocked outbox pending=604
N5 ActionExecuted outbox pending=1
user_projection_run=1
user_signal_projection=605
user_signal_card=605
scoped user_notification_queue=0
delivery_attempt=0
position_state/position_event=0/0
virtual_order/virtual_trade/virtual_position=0/0/0
```

Existing event-consumer refs are present from the already approved N4 -> N5 action pipeline:

```text
common_event_inbox: n5_action_consumer_v1 / N4_trigger / processed = 605
common_event_consumer_checkpoint: n5_action_consumer_v1 / N4_trigger = 605
```

These are pre-existing lineage refs, not writes from this UI stats post-review. This gate did not consume or update N4/N5 outbox and did not update inbox/checkpoint.

## Validation

```text
HTTP readonly proof: PASS
test_n6_user_app.py: PASS, 44 tests
test_n6_*.py: PASS, 124 tests
compileall: PASS
JSON parse: PASS
GET-only route scan: PASS
git diff --check: PASS
```

## Decision

N6 UI full-lineage message stats post-review passes.

Allowed next gate:

```text
N6_UI_FULL_LINEAGE_MESSAGE_STATS_CLOSEOUT_GATE
```
