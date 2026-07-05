# N6 UI Readonly Refresh Closeout

Status: POST_REVIEW_PASS

Gate: N6_UI_READONLY_REFRESH_CLOSEOUT_GATE

Layer role: N6_user

Date: 2026-06-06

## Scope

This closeout records the read-only refresh status for the Track A
`N6_UI_v1_ADMIN_CONSOLE` message filter and card layout.

The closeout verifies:

- `/n6/action-events` renders normally.
- `GET /api/n6/ui/v1/signals` matches contract and dry-run counts.
- The latest 20260605 N6 projection scope remains `run/projection/card/queue = 1/605/605/0`.
- The N5 outbox remains pending and unchanged for the 20260605 source action run.
- No forbidden downstream or mutation scope was entered.

No real login was performed. API and page verification used a TestClient-only
read-only session resolver backed by the real PostgreSQL read-only repository.
This avoids creating or updating `user_session`.

## Input Artifacts

- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_CONTRACT.md`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_CONTRACT.json`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_DRY_RUN.md`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_DRY_RUN.json`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_IMPLEMENTATION.md`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_IMPLEMENTATION.json`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_POST_REVIEW.md`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_POST_REVIEW.json`

## Page Proof

```text
/n6/action-events -> 200
```

Rendered content proof:

```text
消息筛选 = true
统计点击过滤 = true
消息卡片 = true
详情抽屉 = true
市场动作确认成立 = true
市场动作未确认 = true
projection_only = true
```

The page renders 100 cards on the first page and displays `total 605`. The full
matching count is represented by API pagination metadata.

## API Proof

Reviewed route:

```text
GET /api/n6/ui/v1/signals
```

Fresh closeout counts:

```text
empty total_count = 605
empty filtered_count = 605
empty first page item_count = 100
ActionExecuted = 1
ActionBlocked = 604
blocked_reason=price_confirmation_failed = 305
blocked_reason=metric_missing = 289
blocked_reason=amount_confirmation_failed = 10
date range 2026-06-05 by event_time = 605
offset=100 item_count = 100
limit=999 clamped_limit = 500
```

Statistics payload:

```text
total_count = 605
ActionExecuted = 1
ActionBlocked = 604
TriggerMatched = 0
price_confirmation_failed = 305
metric_missing = 289
amount_confirmation_failed = 10
```

## Scoped Rows Proof

Projection run:

```text
user_projection_run_id=user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

Scoped rows:

```text
user_projection_run = 1
user_signal_projection = 605
user_signal_card = 605
user_notification_queue = 0
```

## N5 Outbox Proof

Source action run:

```text
action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
```

N5 outbox remains:

```text
ActionExecuted pending = 1
ActionBlocked pending = 604
```

No N5 outbox consumption or status update was performed by this closeout.

## Forbidden Scope Proof

Confirmed false:

```text
writes_business_data
n5_outbox_consumed
n5_outbox_status_updated
notification_queue_written
worker_started
delivery_push_voice_mobile
sim_position_pnl_virtual_order_trade_mutated
b_track_modified
```

UI route and SQL scans:

```text
/api/n6/ui/v1 mutation routes = []
UI v1 SQL DML findings = []
```

Forbidden user-facing wording remains absent from the rendered page:

```text
已下单
已成交
真实交易
虚拟成交
建议买入
交易失败
下单失败
持仓失败
```

## Validation

Passed:

```text
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
python3 -m compileall src tests scripts
python3 -m json.tool contract/dry-run/implementation/post-review artifacts
route scan GET-only
UI v1 SQL DML scan
git diff --check
```

## Result

```text
POST_REVIEW_PASS
```

Allowed next step:

```text
runtime_control N6 readonly lineage/UI closeout registration
```
