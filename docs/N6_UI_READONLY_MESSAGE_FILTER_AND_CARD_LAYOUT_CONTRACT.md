# N6 UI Readonly Message Filter And Card Layout Contract

Status: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-06

This contract defines the next read-only layout for the Track A
`N6_UI_v1_ADMIN_CONSOLE` message surface. It changes the administrator view from
a mixed N4/N5/N6 table into a date-filtered, category-filtered, clickable
statistics and card-detail experience.

This gate does not implement the UI, write business data, consume or update N5
outbox, write `user_notification_queue`, start workers, deliver/push/voice/mobile,
run sim/position/PnL/real trade, generate proposal/order/trade, or modify B-track.

## 1. Design Decision

Recommended approach:

```text
keep the existing Track A route family
extend GET /api/n6/ui/v1/signals with read-only filters and pagination
render the list as action cards rather than a raw table
open a right-side detail drawer from each card
derive filter fields from reviewed N6 projection/card payloads
do not add mutation routes
do not add B-track front-office behavior
```

Rejected approaches:

```text
new POST search endpoint: rejected because Track A must stay GET-only
direct N4/N5 raw table scan: rejected because N6_UI_v1 should use N6 projection/card
write normalized UI rows: rejected because this gate is read-only and no DB writes are allowed
```

## 2. Page Layout Contract

The administrator page should have four visible zones.

```text
top filter bar
statistics filter cards
message card list
right-side detail drawer
```

The top filter bar must include:

```text
date preset: today / yesterday / last_7_days / last_30_days / custom
date_from
date_to
time_field: event_time / created_at
event_type: TriggerMatched / ActionExecuted / ActionBlocked
asset_kind: stock / index / board
direction: buy / sell
signal_type: B_BUY / S_SELL
blocked_reason: price_confirmation_failed / metric_missing / amount_confirmation_failed
keyword q: stock code / event_id / condition_key
```

The default view must show the latest passed N6 projection scope and must not mix
older projection runs into the current action-card list.

## 3. Statistics Click Filter Contract

The statistics area must expose clickable cards. Clicking a statistics card only
sets client-side query filters and re-requests the GET API.

Required cards:

```text
ActionExecuted count -> sets event_type=ActionExecuted or action_state=executed
ActionBlocked count -> sets event_type=ActionBlocked or action_state=blocked
TriggerMatched count -> sets event_type=TriggerMatched
price_confirmation_failed count -> sets blocked_reason=price_confirmation_failed
metric_missing count -> sets blocked_reason=metric_missing
amount_confirmation_failed count -> sets blocked_reason=amount_confirmation_failed
```

Clicking a card must not write database rows and must not update N5 outbox status.

## 4. Message Card Contract

The list must be card-based. It must not display long `event_id` values in the
main list.

Each message card must display:

```text
status label
asset_kind + identity_key
direction
signal_type
condition_key
blocked_reason when present
event_time
detail button
```

Status label mapping:

```text
ActionExecuted -> 市场动作确认成立
ActionBlocked -> 市场动作未确认
TriggerMatched -> 触发已匹配
```

ActionExecuted forbidden wording:

```text
已下单
已成交
真实交易
虚拟成交
建议买入
```

ActionBlocked forbidden wording:

```text
交易失败
下单失败
持仓失败
```

## 5. Detail Drawer Contract

The right-side drawer opens from a card detail button. It remains read-only.

Required fields:

```text
event_id
N4 trigger event id
N5 action event id
action_run_id
source_action_status
blocked_reason
trigger_price
triggered_periods
baseline_source
proposal_eligibility.behavior=projection_only
```

Safety labels must be visible in the drawer:

```text
READ ONLY
NO ORDER
NO TRADE
NO POSITION UPDATE
NO REAL TRADE
NOT INVESTMENT ADVICE
```

The drawer must state:

```text
proposal_generated=false
order_generated=false
trade_generated=false
position_updated=false
pnl_generated=false
real_trade_submitted=false
```

## 6. API Contract

Primary route:

```text
GET /api/n6/ui/v1/signals
```

Allowed query params:

```text
date_from        YYYY-MM-DD, optional
date_to          YYYY-MM-DD, optional
time_field       event_time | created_at, default event_time
event_type       TriggerMatched | ActionExecuted | ActionBlocked, optional
action_state     executed | blocked, optional compatibility filter
asset_kind       stock | index | board, optional
direction        buy | sell, optional
signal_type      B_BUY | S_SELL, optional
blocked_reason   price_confirmation_failed | metric_missing | amount_confirmation_failed, optional
q                stock code / event_id / condition_key keyword, optional
limit            default 100, max 500
offset           default 0
```

Response must include:

```text
items
statistics
filters
pagination.total_count
pagination.filtered_count
pagination.limit
pagination.offset
side_effects
disabled_entrypoints
```

`total_count` is the latest passed projection scope before filters.
`filtered_count` is after all filters.

The route must stay GET-only. Do not add POST/PUT/PATCH/DELETE under
`/api/n6/ui/v1/...`.

## 7. Filter Field Derivation

The implementation must derive fields from reviewed N6 projection/card rows.

Allowed sources:

```text
user_signal_projection
user_signal_card
reviewed source_payload_json / display_payload_json / trace_json already stored in N6 projection rows
```

Forbidden sources:

```text
direct raw K
N1 raw facts
direct live market data
N4 raw facts as a replacement event source
N5 raw facts as a replacement event source
```

Field derivation:

```text
event_type: source_action_event_type or source_event_type
event_time: source_payload_json.event_time, with created_at only as display fallback
trade_date: source_payload_json.trade_date or existing adapter trade_date
blocked_reason: card_payload_json/display_payload_json/trace_json/source_payload_json reviewed values
N4 trigger event id: trace_json.condition_provenance.source_trigger_event_ids[0] when present
N5 action event id: source_action_event_id or source_event_id
baseline_source: trace_json.period_trigger_baseline_trace.baseline_source when present
triggered_periods: trace_json.period_trigger_baseline_trace.required_periods or card trigger_period
```

The implementation must not add columns or rewrite historical rows for this
contract.

## 8. Pagination Contract

```text
default limit=100
max limit=500
default offset=0
offset must be non-negative
limit values outside range are clamped
filtered_count must be computed independently from page size
```

## 9. Safety Boundary

The implementation gate must preserve:

```text
database_written=false
write_notification_queue=false
consume_n5_outbox=false
update_n5_outbox_status=false
start_worker=false
delivery=false
push=false
voice=false
mobile=false
sim=false
position=false
pnl=false
real_trade=false
proposal=false
order=false
trade=false
modify_b_track=false
```

Track A hidden/disabled modules remain:

```text
监控筛选
持仓
手机播报
delivery / push / voice / mobile
proposal / order / trade / position / pnl
```

## 10. Acceptance For Implementation Gate

The next implementation gate must prove:

```text
empty filters return 605 cards
blocked_reason=metric_missing returns 289 cards
ActionExecuted returns 1 card
ActionBlocked returns 604 cards
date_from=2026-06-05&date_to=2026-06-05&time_field=event_time covers 605 current cards
GET-only route method scan passes
forbidden wording is absent from rendered labels
detail drawer shows projection_only and safety labels
no mutation route is added
B-track is unchanged
```

## 11. Result

```text
contract_result=CONTRACT_PASS
remaining_blockers=none
allow_implementation_gate=true
next_allowed_gate=N6_UI_READONLY_MESSAGE_FILTER_AND_CARD_LAYOUT_IMPLEMENTATION_GATE
```
