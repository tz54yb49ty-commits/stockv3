# N6 UI v1 Admin Virtual Account Readonly Adapter Implementation Readiness

Status: IMPLEMENTATION_PASS

Layer role: N6_user

Date: 2026-06-05

This artifact records the implementation readiness for the N6_UI_v1 admin
virtual account read-only adapter. The implementation added only read APIs,
page rendering, component models, and tests. It did not write database rows,
execute runners, consume or update outbox rows, start workers, generate
proposals, generate virtual orders, generate virtual trades, materialize
positions, generate PnL, deliver notifications, push to voice or mobile, run
sim, update positions, place real trades, modify N1-N5 facts, or modify
036/037/038 schema.

## 1. Implemented API

```text
GET /api/n6/ui/v1/virtual-account
GET /api/n6/ui/v1/cash-snapshot
GET /api/n6/ui/v1/cash-ledger
```

All three routes require an active N6 session and return read-only models with
side-effect flags:

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

## 2. Implemented UI

Dashboard `/n6/action-events` now includes `Virtual Account Summary`:

```text
account_name
base_currency
initial_cash
available_cash
frozen_cash
total_cash
quality_status
seed_run_id
```

Admin account page:

```text
/n6/admin/account
```

It displays:

```text
virtual_account
current_cash_snapshot
recent cash ledger rows
```

Safety banner labels:

```text
READ ONLY
NO ORDER
NO TRADE
NO POSITION UPDATE
NO REAL TRADE
```

Feature flags continue to hide:

```text
监控筛选
持仓
手机播报
```

## 3. Proposal Eligibility

Signal Detail API now includes `proposal_eligibility`:

| Source action | Behavior | Current side effect |
|---|---|---|
| `ActionBlocked` | `display_only` | no proposal |
| `ActionExecuted` | `proposal_candidate` | no proposal |
| `ActionEligible` | `policy_candidate` | no proposal |
| `ActionSkipped` | `informational_only` | no proposal |

Forbidden wording remains absent:

```text
已下单
已成交
真实交易
投资建议
```

## 4. Modified Files

```text
src/ashare_v3/web/n6_ui_v1.py
src/ashare_v3/web/n6_user_app.py
src/ashare_v3/web/templates/n6_action_events.html
src/ashare_v3/web/templates/n6_admin_account.html
src/ashare_v3/web/templates/n6_admin_users.html
tests/test_n6_user_app.py
docs/N6_UI_V1_ADMIN_VIRTUAL_ACCOUNT_READONLY_ADAPTER_IMPLEMENTATION_READINESS.md
docs/N6_UI_V1_ADMIN_VIRTUAL_ACCOUNT_READONLY_ADAPTER_IMPLEMENTATION_READINESS.json
```

## 5. Validation

Required validation commands:

```text
python3 -m compileall scripts src tests
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_n6_user_app.py'
python3 -m json.tool docs/N6_UI_V1_ADMIN_VIRTUAL_ACCOUNT_READONLY_ADAPTER_DESIGN.json
python3 -m json.tool docs/N6_UI_V1_ADMIN_VIRTUAL_ACCOUNT_READONLY_ADAPTER_TRACEABILITY.json
python3 -m json.tool docs/N6_UI_V1_ADMIN_VIRTUAL_ACCOUNT_READONLY_ADAPTER_IMPLEMENTATION_READINESS.json
git diff --check
```

## 6. Next Recommended Gate

Recommended next gate:

```text
runtime_control N6 UI adapter post-review
```

Alternative allowed gate:

```text
N6_UI_V1_RUNTIME_PREVIEW_AND_MESSAGE_DASHBOARD_GATE
```

Neither next gate is authorized by this artifact to execute writes or trigger
delivery, proposal, order, trade, position, PnL, sim, or real trade behavior.
