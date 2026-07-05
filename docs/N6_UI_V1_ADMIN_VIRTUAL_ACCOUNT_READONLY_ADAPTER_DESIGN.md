# N6 UI v1 Admin Virtual Account Readonly Adapter Design

Status: DESIGN_PASS

Layer role: N6_user

Date: 2026-06-05

This gate designs the read-only adapter that exposes the completed Phase 3
admin virtual account seed in N6_UI_v1. It does not change code, write
database rows, execute runners, generate proposals, generate virtual orders,
generate virtual trades, materialize positions, generate PnL, consume or update
outbox rows, start workers, modify the shadow projection pipeline, deliver
notifications, push to voice or mobile, run sim, update positions, or place
real trades.

## 1. Current Baseline

Phase 3 virtual account seed is available for admin display:

```text
virtual_account_id = 1
principal = admin
initial_cash = 1000000.0000 CNY
n6_virtual_account = 1
n6_virtual_cash_ledger = 1
n6_virtual_cash_snapshot = 1
n6_virtual_order = 0
n6_virtual_trade = 0
n6_virtual_position = 0
n6_virtual_position_event = 0
n6_virtual_pnl_snapshot = 0
```

The adapter must read Phase 3 virtual account tables, not legacy `user_sim_*`
tables.

## 2. Scope

Allowed read-only scope:

```text
n6_virtual_account
n6_virtual_cash_snapshot
n6_virtual_cash_ledger
user_signal_projection
user_signal_card
user_notification_queue
reviewed N6 UI v1 artifacts
reviewed Phase 3 virtual account seed artifacts
```

Forbidden scope:

```text
database writes
proposal generation
n6_virtual_order generation
n6_virtual_trade generation
n6_virtual_position generation or update
n6_virtual_pnl_snapshot generation
N4/N5 outbox consumption or status update
N5 inbox/checkpoint write
worker start
delivery / push / voice / mobile
sim execution
position execution
real trade
raw K / live market data pull
```

## 3. Implementation Plan

Future implementation should be limited to N6 web read-only repository, API
models, templates, and tests.

Recommended repository additions:

```text
fetch_ui_v1_virtual_account(user_id)
fetch_ui_v1_cash_snapshot(user_id)
fetch_ui_v1_cash_ledger(user_id, limit)
```

Recommended model additions in `ashare_v3.web.n6_ui_v1`:

```text
virtual_account_summary_model
cash_snapshot_model
cash_ledger_model
proposal_eligibility_model
virtual_account_safety_banner_model
```

Recommended UI additions:

```text
Dashboard: Virtual Account Summary section
Signal Detail: proposal eligibility section
Admin Account page: virtual_account + cash snapshot + recent cash ledger
Shared Safety Banner: READ ONLY / NO ORDER / NO TRADE / NO POSITION UPDATE
```

No POST, PUT, PATCH, DELETE, runner, migration, delivery adapter, order runner,
trade runner, position runner, or PnL runner is part of this adapter.

## 4. API Contract

All APIs require an active N6 session. The first version is scoped to the admin
principal and admin virtual account. The APIs are read-only `GET` endpoints.

### GET /api/n6/ui/v1/virtual-account

Reads the current admin virtual account.

Response fields:

```text
ok
component = Virtual Account Summary
readonly = true
virtual_account_id
principal_id
principal_type
account_name
virtual_account_status
base_currency
initial_cash
current_cash_snapshot_id
run_id
policy_version
policy_hash
rollback_scope
quality_status
created_at
updated_at
side_effects
```

Required side effects:

```text
writes_database=false
outbox_status_updates=0
proposal_generated=false
order_generated=false
trade_generated=false
position_updated=false
pnl_generated=false
real_trade_submitted=false
```

### GET /api/n6/ui/v1/cash-snapshot

Reads the active cash snapshot pointed to by
`n6_virtual_account.current_cash_snapshot_id`. If the pointer is missing, the
implementation may read the latest active snapshot for the same account, but
must mark `pointer_missing_warning=true`.

Response fields:

```text
ok
component = Cash Snapshot
readonly = true
cash_snapshot_id
virtual_account_id
snapshot_time
trade_date
available_cash
frozen_cash
total_cash
currency
source_ledger_max_id
snapshot_status
run_id
policy_version
policy_hash
rollback_scope
quality_status
created_at
pointer_missing_warning
side_effects
```

The model must preserve:

```text
total_cash = available_cash + frozen_cash
available_cash >= 0
frozen_cash >= 0
```

### GET /api/n6/ui/v1/cash-ledger

Reads recent immutable cash ledger rows for the admin virtual account.

Query parameters:

```text
limit: integer, default 20, max 100
```

Response fields:

```text
ok
component = Cash Ledger
readonly = true
items[]
cash_ledger_id
virtual_account_id
ledger_type
amount
currency
trade_date
event_time
source_event_type
source_event_id
source_virtual_order_id
source_virtual_trade_id
run_id
policy_version
policy_hash
rollback_scope
quality_status
created_at
side_effects
```

This endpoint must not mutate ledger rows. It only displays immutable ledger
lineage.

## 5. UI Mock

### Dashboard

```text
[READ ONLY] [NO ORDER] [NO TRADE] [NO POSITION UPDATE]

Virtual Account Summary
Admin Virtual Account
Currency: CNY
Initial cash: 1,000,000.00
Available cash: 1,000,000.00
Frozen cash: 0.00
Total cash: 1,000,000.00
Status: active
```

### Signal Detail

```text
Proposal Eligibility
ActionBlocked  -> 展示，不生成 proposal
ActionExecuted -> 可作为未来虚拟候选资格提示，本界面不生成 proposal
ActionEligible -> 可作为未来策略候选资格提示，本界面不生成 proposal
ActionSkipped  -> 信息展示，不生成 proposal

Current gate:
proposal_generated = false
order_generated = false
trade_generated = false
position_updated = false
```

### Admin Account Page

```text
[READ ONLY] [NO ORDER] [NO TRADE] [NO POSITION UPDATE]

Virtual Account
  account_name / status / initial_cash / policy_version / rollback_scope

Cash Snapshot
  available_cash / frozen_cash / total_cash / snapshot_time / source_ledger_max_id

Recent Cash Ledger
  event_time / ledger_type / amount / currency / source_event_type / run_id
```

## 6. Proposal Eligibility Policy

The UI adapter displays proposal eligibility only. It does not create proposal
rows or artifacts.

| Source action state | UI label | Future eligibility | Current behavior |
|---|---|---|---|
| `ActionBlocked` / `blocked` | 市场动作未确认 | false | display only |
| `ActionExecuted` / `executed` | 市场动作确认成立 | possible after future review policy | display only |
| `ActionEligible` / `eligible` | 可关注 | possible after future policy | display only |
| `ActionSkipped` / `skipped` | 已跳过 | false | display only |

Forbidden wording:

```text
已下单
已成交
已交易
真实交易
投资建议
```

Allowed wording:

```text
未来虚拟候选资格
仅展示
未生成 proposal
未生成 order
未生成 trade
```

## 7. Test Plan

Targeted tests for the future implementation:

```text
GET /api/n6/ui/v1/virtual-account requires login
GET /api/n6/ui/v1/virtual-account returns admin virtual account fields
GET /api/n6/ui/v1/virtual-account does not read user_sim_account
GET /api/n6/ui/v1/cash-snapshot returns active current_cash_snapshot_id
GET /api/n6/ui/v1/cash-snapshot preserves total_cash arithmetic
GET /api/n6/ui/v1/cash-ledger returns recent immutable ledger rows
cash-ledger limit is clamped to max 100
Dashboard renders Virtual Account Summary
Signal Detail renders proposal eligibility for ActionBlocked
Signal Detail renders proposal eligibility for ActionExecuted without trade wording
Safety Banner includes exact labels READ ONLY / NO ORDER / NO TRADE / NO POSITION UPDATE
No endpoint uses POST/PUT/PATCH/DELETE for virtual account operations
No endpoint writes n6_virtual_order
No endpoint writes n6_virtual_trade
No endpoint writes n6_virtual_position
No endpoint writes n6_virtual_pnl_snapshot
No endpoint consumes or updates N4/N5 outbox
No endpoint starts worker or delivery/push/voice/mobile
```

Static checks:

```text
adapter code has no INSERT/UPDATE/DELETE/TRUNCATE/COPY for Phase 3 tables
adapter SQL uses readonly connection options
adapter tests assert forbidden repository counters remain zero
adapter tests assert user_sim_* is not read for virtual account summary
```

## 8. Read-Only Boundary

The adapter must preserve these flags in API and page models:

```text
read_only = true
proposal_generated = false
order_generated = false
trade_generated = false
position_updated = false
pnl_generated = false
outbox_consumed = false
outbox_status_updated = false
worker_started = false
delivery_triggered = false
push_triggered = false
voice_triggered = false
mobile_triggered = false
sim_written = false
real_trade_submitted = false
```

## 9. Current Gaps

Implementation gaps:

```text
repository methods not implemented yet
GET /api/n6/ui/v1/virtual-account not implemented yet
GET /api/n6/ui/v1/cash-snapshot not implemented yet
GET /api/n6/ui/v1/cash-ledger not implemented yet
Dashboard Virtual Account Summary not implemented yet
Admin Account page not implemented yet
Signal Detail proposal eligibility adapter not implemented yet
tests not implemented yet
```

These are expected design gaps and do not block this design gate.

## 10. Next Recommended Gate

Recommended next gate:

```text
N6_UI_V1_ADMIN_VIRTUAL_ACCOUNT_READONLY_ADAPTER_IMPLEMENTATION_GATE
```

That gate may modify only N6 UI read-only repository/API/templates/tests. It
must still not write database rows, consume or update outbox rows, start
workers, generate proposals, generate virtual orders or trades, update
positions, generate PnL, deliver notifications, push to voice/mobile, run sim,
or place real trades.
