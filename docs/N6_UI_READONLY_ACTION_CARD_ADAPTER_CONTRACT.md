# N6 UI Readonly Action Card Adapter Contract

Status: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-06

This contract defines the read-only adapter changes required for the Track A
`N6_UI_v1_ADMIN_CONSOLE` action-card surface after the 20260605 N6 action
projection execute passed. It does not execute runners, write database rows,
consume or update N5 outbox, create notification queue rows, start workers,
deliver/push/voice/mobile, run sim/position/PnL/real trade, generate
proposal/order/trade, modify B-track, or expand N6_UI_v1 beyond the
administrator read-only console.

## 1. Source State

```text
source_action_run_id=action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
user_projection_run_id=user_projection_shadow_20260605__action_consumer_action_pipeline_20260605_trigger_execute_20260605_condition_layer_20260604_source_20260604_v1
user_projection_run.status=passed
user_signal_projection=605
user_signal_card=605
user_notification_queue=0
N5 outbox pending=605
```

Action-card distribution:

```text
ActionExecuted / action_confirmed = 1
ActionBlocked / blocked = 604
```

ActionBlocked reason distribution:

```text
price_confirmation_failed=305
metric_missing=289
amount_confirmation_failed=10
```

## 2. Current Blockers

P0:

```text
/api/n6/ui/v1/signals read path fails with:
PostgreSQL AmbiguousParameter: could not determine data type of parameter $2
```

Observed failing paths:

```text
empty filters -> fails
normal filters action_state=blocked&blocked_reason=price_confirmation_failed -> fails
```

Root cause hypothesis:

```text
fetch_ui_v1_signals uses nullable named parameters inside predicates such as
(%(trade_date)s IS NULL OR expression = %(trade_date)s).
When a parameter value is NULL and no explicit SQL type is available,
PostgreSQL cannot infer the data type for the NULL placeholder.
```

P1:

```text
signal_detail_model() uses proposal_eligibility_model().
For ActionExecuted/executed, current behavior text is proposal_candidate.
That wording is unsafe for Track A because N6_UI_v1 is an administrator
read-only console and this gate forbids proposal/order/trade generation.
```

## 3. Adapter Scope

Allowed implementation scope for the next gate:

```text
fix GET /api/n6/ui/v1/signals read path only
fix Signal Detail proposal wording for Track A
update read-only UI tests
update readiness/post-review docs if needed
```

Forbidden implementation scope:

```text
no POST/PUT/PATCH/DELETE
no database writes
no user_notification_queue writes
no N5 outbox consumption or status update
no N5 inbox/checkpoint writes
no worker
no delivery/push/voice/mobile
no sim/position/PnL/real trade
no proposal/order/trade generation
no B-track route/API/schema changes
no N6_UI_v1 expansion into multi-user front office
```

## 4. Signals API Fix Contract

The implementation must keep the route:

```text
GET /api/n6/ui/v1/signals
```

Required behavior:

```text
empty filters do not raise AmbiguousParameter
normal filters do not raise AmbiguousParameter
response remains read-only
response returns 605 cards for the 20260605 projection when no filters are applied
ActionExecuted count=1
ActionBlocked count=604
no mutation routes are added
```

Allowed implementation approaches:

```text
preferred: build WHERE clauses dynamically and include only non-empty filters
allowed: cast nullable parameters explicitly, for example %(trade_date)s::text
```

The preferred dynamic WHERE approach avoids asking PostgreSQL to infer the type
of NULL placeholders and keeps the SQL easier to reason about.

## 5. Action Card Adapter Contract

Data source:

```text
user_signal_card
user_signal_projection
```

Required list display:

```text
total cards=605
ActionExecuted=1 -> 市场动作确认成立
ActionBlocked=604 -> 市场动作未确认
```

Blocked reason display:

```text
price_confirmation_failed=305
metric_missing=289
amount_confirmation_failed=10
```

Forbidden wording:

```text
交易失败
已下单
已成交
真实交易
投资建议
```

## 6. Detail Proposal Wording

For Track A `N6_UI_v1_ADMIN_CONSOLE`, `ActionExecuted` must not display:

```text
proposal_candidate
```

Allowed replacements:

```text
display_only
projection_only
no_order_no_trade
```

Recommended replacement:

```text
behavior=projection_only
future_eligible=false
display_text=管理员只读投影，不生成 proposal / order / trade / position / PnL
```

The detail response must continue to state:

```text
proposal_generated=false
order_generated=false
trade_generated=false
position_updated=false
pnl_updated=false
real_trade_enabled=false
```

## 7. Safety Banner

Page/API safety text must retain:

```text
READ ONLY
NO ORDER
NO TRADE
NO POSITION UPDATE
NO REAL TRADE
NOT INVESTMENT ADVICE
```

## 8. Hidden / Disabled Modules

Track A must continue to hide or disable:

```text
监控筛选
持仓
手机播报
delivery
push
voice
mobile
proposal
order
trade
position
pnl
```

## 9. Implementation Gate Acceptance

The next implementation gate must prove:

```text
/api/n6/ui/v1/signals empty filters returns 200
/api/n6/ui/v1/signals normal filters returns 200
unfiltered item count=605
ActionExecuted=1
ActionBlocked=604
ActionBlocked reason distribution=305/289/10
proposal_eligibility no longer displays proposal_candidate in Track A
no POST/PUT/PATCH/DELETE routes added under /api/n6/ui/v1
B-track files/routes/API unchanged unless explicitly read-only test fixtures require updates
```

## 10. Gate Result

```text
contract_result=CONTRACT_PASS
dry_run_current_result=BLOCKED_BY_CURRENT_IMPLEMENTATION
P0=1
P1=1
P2=0
allow_implementation_gate=true
next_allowed_gate=N6_UI_READONLY_ACTION_CARD_ADAPTER_IMPLEMENTATION_GATE
```
