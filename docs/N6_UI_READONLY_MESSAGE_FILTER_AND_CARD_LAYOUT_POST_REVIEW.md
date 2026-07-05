# N6 UI Readonly Message Filter And Card Layout Post Review

Status: POST_REVIEW_PASS

Gate: N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_POST_REVIEW_GATE

Layer role: N6_user

Date: 2026-06-06

## Scope

This post-review is read-only. It reviews the implemented Track A `N6_UI_v1_ADMIN_CONSOLE`
message filter and card layout against the approved contract, dry-run, and
implementation artifacts.

No real login was performed during this review. The HTTP GET API was exercised
with a TestClient-only read-only session resolver, backed by the real PostgreSQL
read-only repository. This avoids creating `user_session` rows while still
verifying the route implementation and real data counts.

## Input Artifacts

- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_CONTRACT.md`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_CONTRACT.json`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_DRY_RUN.md`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_DRY_RUN.json`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_IMPLEMENTATION.md`
- `docs/N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_IMPLEMENTATION.json`

## API Proof

Reviewed route:

```text
GET /api/n6/ui/v1/signals
```

HTTP proof with read-only injected session:

```text
/api/n6/ui/v1/signals -> 200
/api/n6/ui/v1/signals?blocked_reason=metric_missing -> 200
/api/n6/ui/v1/signals?action_state=blocked&blocked_reason=price_confirmation_failed -> 200
/api/n6/ui/v1/signals?event_type=ActionExecuted -> 200
/api/n6/ui/v1/signals?event_type=ActionBlocked -> 200
/api/n6/ui/v1/signals?date_from=2026-06-05&date_to=2026-06-05&time_field=event_time -> 200
/api/n6/ui/v1/signals?limit=100&offset=100 -> 200
/api/n6/ui/v1/signals?limit=999 -> 200
```

Count proof:

```text
empty total_count = 605
empty filtered_count = 605
empty first page item_count = 100
blocked_reason=metric_missing filtered_count = 289
action_state=blocked + blocked_reason=price_confirmation_failed filtered_count = 305
event_type=ActionExecuted filtered_count = 1
event_type=ActionBlocked filtered_count = 604
date range 2026-06-05 by event_time filtered_count = 605
offset=100 item_count = 100
limit=999 clamped_limit = 500
```

Statistics proof:

```text
total_count = 605
ActionExecuted = 1
ActionBlocked = 604
TriggerMatched = 0
price_confirmation_failed = 305
metric_missing = 289
amount_confirmation_failed = 10
```

## UI Proof

Reviewed page:

```text
/n6/action-events -> 200
```

The rendered page contains:

- `消息筛选`
- `统计点击过滤`
- `消息卡片`
- `市场动作确认成立`
- `市场动作未确认`
- `class="detail-drawer"`
- `projection_only`
- statistics click filter links such as `event_type=ActionExecuted`
- blocked reason click filter links such as `blocked_reason=metric_missing`

The current page displays `total 605` and renders the first page of 100 cards by
default. The complete matching card count is represented by `total_count=605`
and `filtered_count=605`.

## Detail Drawer Proof

The detail drawer exposes the required read-only details:

- event id
- N4 trigger event id
- N5 action event id
- action run id
- source action status
- blocked reason
- trigger price
- triggered periods
- baseline source
- `proposal_eligibility.behavior=projection_only`

The drawer contains only read-only lineage and safety context. It does not expose
proposal acceptance, order creation, trade creation, position mutation, PnL
mutation, or real-trade controls.

## Boundary Proof

DB and event boundary:

```text
N5 outbox ActionBlocked pending = 604
N5 outbox ActionExecuted pending = 1
delivered/delivering not introduced by this gate
scoped user_projection_run rows = 1
scoped user_signal_projection rows = 605
scoped user_signal_card rows = 605
scoped user_notification_queue rows = 0
```

Forbidden scope remains false:

```text
writes_business_data = false
n5_outbox_consumed = false
n5_outbox_status_updated = false
notification_queue_written = false
worker_started = false
delivery_push_voice_mobile = false
sim_position_pnl_virtual_order_trade_mutated = false
b_track_modified = false
```

Route and DML scan:

```text
/api/n6/ui/v1 mutation routes = []
UI v1 SQL DML findings = []
```

Forbidden user-facing wording scan:

```text
已下单 = absent
已成交 = absent
真实交易 = absent
虚拟成交 = absent
建议买入 = absent
交易失败 = absent
下单失败 = absent
持仓失败 = absent
```

## Validation

Passed:

```text
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
python3 -m compileall src tests scripts
python3 -m json.tool contract/dry-run/implementation artifacts
route scan GET-only
UI v1 SQL DML boundary scan
git diff --check
```

## Result

```text
POST_REVIEW_PASS
```

Allowed next gate:

```text
N6_UI_READONLY_REFRESH_CLOSEOUT_GATE
```
