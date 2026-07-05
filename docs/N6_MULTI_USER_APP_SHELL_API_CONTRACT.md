# N6 Multi User App Shell API Contract

Status: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-05

This contract freezes the read-only Track B API surface for
`N6_MULTI_USER_AND_AI_APP`. It defines response structures, principal scope,
permission boundaries, and Track A isolation for `/api/n6/app/v1/...`.

This gate is documentation only. It does not modify `N6_UI_v1`, does not reuse
`/api/n6/ui/v1/...`, does not write code, does not write database rows, does
not execute runners, does not consume or update outbox rows, does not start
workers, does not deliver notifications, does not push to voice or mobile, does
not run sim, does not write positions, does not create proposal/order/trade/PnL
runners, does not materialize leaderboards, and does not place real trades.

## 1. Basis

Authoritative inputs:

```text
docs/N6_MULTI_USER_APP_SHELL_SPEC.md
docs/N6_MULTI_USER_APP_SHELL_SPEC.json
docs/N6_MULTI_USER_APP_SHELL_TRACEABILITY.md
docs/N6_MULTI_USER_APP_SHELL_TRACEABILITY.json
runtime_control APPROVED review
docs/N6_TRACK_SEPARATION_RESCUE_PLAN.md
docs/N6_TRACK_SEPARATION_RESCUE_PLAN.json
docs/N6_UI_V1_ADMIN_CONSOLE_FREEZE.md
docs/N6_UI_V1_ADMIN_CONSOLE_FREEZE.json
```

Canonical B-track identity:

```text
N6_MULTI_USER_AND_AI_APP
```

Canonical B-track API prefix:

```text
/api/n6/app/v1/...
```

Forbidden A-track API reuse:

```text
/api/n6/ui/v1/...
```

## 2. API Design Principle

First API contract posture:

```text
GET only
read-only
principal-scoped
no writes
no outbox consumption
no N4/N5 status updates
no proposal/order/trade/position/PnL mutation
no leaderboard materialization
no delivery/push/voice/mobile/sim/real trade
```

All future write APIs must open a separate contract, preflight, rollback, and
execute gate. This contract does not authorize `POST`, `PUT`, `PATCH`, or
`DELETE`.

## 3. Current Principal Resolver

Every `/api/n6/app/v1/...` request must resolve a `principal_context` before
reading scoped data.

Resolver contract:

1. Validate the current authenticated N6 session.
2. Load the active `user_account` subject.
3. Resolve exactly one active front-office principal:
   - for `admin` first user: `n6_principal.principal_type='admin'` and
     `n6_principal.owner_user_id = user_account.user_id`;
   - for future human users: `principal_type='human_user'` and
     `owner_user_id = user_account.user_id`;
   - for future AI users: resolve through an approved AI principal adapter
     and `n6_ai_user.principal_id`.
4. Reject if no principal exists.
5. Reject if more than one principal matches.
6. Reject disabled/deleted users.
7. Reject `system` principal as a normal front-office principal.

Required principal context:

```json
{
  "principal_id": 1,
  "principal_type": "admin",
  "user_id": 1,
  "display_name": "Initial Admin",
  "role": "admin",
  "app_scope": "n6_multi_user_app",
  "permissions": [
    "read:own_account",
    "read:own_watchlist",
    "read:own_signals",
    "read:own_proposals",
    "read:own_portfolio",
    "read:own_pnl",
    "read:own_ai_users",
    "read:leaderboard"
  ]
}
```

The exact `principal_id` and `display_name` above are examples. Implementation
must derive them from database state and must not hard-code them.

## 4. Common Response Envelope

Every API response should use a stable envelope:

```json
{
  "result": "ok",
  "api_version": "n6_app_v1",
  "principal_context": {},
  "data": {},
  "disclaimers": [],
  "side_effects": {
    "database_written": false,
    "outbox_consumed": false,
    "outbox_status_updated": false,
    "worker_started": false,
    "delivery_triggered": false,
    "push_triggered": false,
    "voice_triggered": false,
    "mobile_triggered": false,
    "sim_triggered": false,
    "position_written": false,
    "real_trade_triggered": false
  }
}
```

Error responses must not leak cross-principal existence. For authorization
failures, return a generic permission error. For empty resources in the current
principal scope, return empty lists or `null` objects as defined below.

## 5. Principal Scope SQL Policy

All SQL/API reads for owner-scoped resources must include current principal
scope:

```text
principal_id = :current_principal_id
principal_type = :current_principal_type
```

Required scope by endpoint:

| Endpoint | Required scope |
|---|---|
| `/me` | current session -> current principal only |
| `/account` | `n6_virtual_account.principal_id/principal_type` |
| `/watchlist` | future watchlist owner principal |
| `/signals` | approved principal/user projection adapter; no cross-principal scan |
| `/proposals` | future proposal principal fields |
| `/portfolio` | `n6_virtual_position.principal_id/principal_type` |
| `/pnl` | `n6_virtual_pnl_snapshot.principal_id/principal_type` |
| `/ai-users` | future AI owner principal adapter |
| `/leaderboard` | approved public leaderboard only; no private account leakage |

If a future table does not yet carry `principal_id` and `principal_type`, the
endpoint must stay `empty/planned` until a schema gate adds principal scope.

## 6. Endpoint Contracts

### 6.1 GET /api/n6/app/v1/me

Purpose: return current principal summary and app permissions.

Allowed sources:

```text
current session
user_account
n6_principal
optional n6_ai_user for future AI principals
```

Response data:

```json
{
  "principal_id": 1,
  "principal_type": "admin",
  "display_name": "Initial Admin",
  "role": "admin",
  "app_scope": "n6_multi_user_app",
  "permissions": [
    "read:own_account",
    "read:own_watchlist",
    "read:own_signals",
    "read:own_proposals",
    "read:own_portfolio",
    "read:own_pnl",
    "read:own_ai_users",
    "read:leaderboard"
  ]
}
```

Forbidden:

```text
password_hash
session_token_hash
cross-principal permissions
write permissions
```

### 6.2 GET /api/n6/app/v1/account

Purpose: return current principal's virtual account and current cash summary.

Allowed sources:

```text
n6_virtual_account
n6_virtual_cash_snapshot
```

Required scope:

```text
n6_virtual_account.principal_id = current principal_id
n6_virtual_account.principal_type = current principal_type
```

Response data:

```json
{
  "virtual_account": {
    "virtual_account_id": 1,
    "account_name": "Admin Virtual Account",
    "base_currency": "CNY",
    "initial_cash": "1000000.0000",
    "available_cash": "1000000.0000",
    "frozen_cash": "0.0000",
    "total_cash": "1000000.0000",
    "status": "active",
    "quality_status": "passed",
    "updated_at": "2026-06-05T00:00:00+08:00"
  }
}
```

If no account exists for the current principal:

```json
{
  "virtual_account": null,
  "status": "empty"
}
```

Forbidden:

```text
broker account fields
real funds
real positions
cash ledger mutation
cash snapshot mutation
```

### 6.3 GET /api/n6/app/v1/watchlist

Purpose: define current principal watchlist API placeholder.

Current response data:

```json
{
  "status": "planned",
  "items": [],
  "writable": false
}
```

Forbidden:

```text
create watchlist
update watchlist
delete watchlist
cross-principal watchlist read
```

### 6.4 GET /api/n6/app/v1/signals

Purpose: return principal-visible signal summaries.

Allowed sources:

```text
reviewed N5/N6 artifacts
N6 shadow projection
user_signal_projection
user_signal_card
reviewed dashboard artifacts
approved N3 reviewed snapshot or N6 reviewed valuation policy for display prices
```

Forbidden sources:

```text
raw K
N1 raw facts
direct live market data
N4 raw facts used to bypass reviewed artifacts
N5 raw facts used to bypass reviewed artifacts
N5 outbox direct consumption/status update
```

Response data:

```json
{
  "items": [
    {
      "signal_id": "string",
      "trade_date": "2026-06-05",
      "asset_kind": "stock",
      "identity_key": "stock:SZ:000001",
      "signal_type": "B_BUY",
      "action_state": "executed",
      "action_mark": "30m_volume",
      "blocked_reason": null,
      "queue_status": "queued_only",
      "source_action_run_id": "string",
      "source_artifact": "docs/example.json",
      "proposal_eligibility": "proposal_candidate"
    }
  ],
  "count": 1
}
```

Proposal eligibility is display-only:

| Action state | Eligibility text |
|---|---|
| `ActionBlocked` / `blocked` | `display_only` |
| `ActionExecuted` / `executed` | `proposal_candidate` |
| `ActionEligible` / `eligible` | `policy_candidate` |
| `ActionSkipped` / `skipped` | `informational_only` |

Forbidden:

```text
generate proposal
accept proposal
generate order/trade
update position/PnL
push notification
```

### 6.5 GET /api/n6/app/v1/proposals

Purpose: define current principal proposal list API placeholder.

Current response data:

```json
{
  "status": "planned",
  "items": [],
  "writable": false,
  "generation_enabled": false
}
```

Forbidden:

```text
generate proposal
review proposal
accept proposal
reject proposal
create virtual order
bypass review
```

### 6.6 GET /api/n6/app/v1/portfolio

Purpose: return current principal virtual positions when available.

Allowed sources:

```text
n6_virtual_position
approved position materialization artifacts
```

Response data:

```json
{
  "positions": [],
  "count": 0,
  "status": "empty"
}
```

Required scope:

```text
n6_virtual_position.principal_id = current principal_id
n6_virtual_position.principal_type = current principal_type
```

Forbidden:

```text
position creation
position update
real position
broker position
T+1 rule execution
```

### 6.7 GET /api/n6/app/v1/pnl

Purpose: return current principal virtual PnL snapshots when available.

Allowed sources:

```text
n6_virtual_pnl_snapshot
approved valuation artifacts
```

Response data:

```json
{
  "snapshots": [],
  "count": 0,
  "status": "empty"
}
```

Required disclaimers:

```text
非真实收益
非投资建议
不代表未来收益
```

Required scope:

```text
n6_virtual_pnl_snapshot.principal_id = current principal_id
n6_virtual_pnl_snapshot.principal_type = current principal_type
```

Forbidden:

```text
live price pull
raw K read
real brokerage performance
investment advice
leaderboard materialization
```

### 6.8 GET /api/n6/app/v1/ai-users

Purpose: define current principal AI users API placeholder.

Current response data:

```json
{
  "status": "planned",
  "items": [],
  "writable": false,
  "ai_decision_enabled": false,
  "ai_evaluation_enabled": false
}
```

Forbidden:

```text
create AI user
create AI decision
create AI evaluation
create virtual intent
read raw K
read live market data
read real account/funds/position
```

### 6.9 GET /api/n6/app/v1/leaderboard

Purpose: define leaderboard display API placeholder.

Current response data:

```json
{
  "status": "planned",
  "items": [],
  "materialized": false
}
```

Required disclaimers:

```text
非真实收益
非投资建议
不代表未来收益
```

Forbidden:

```text
leaderboard materialization
strategy ranking materialization
real performance table
private principal account leakage
```

## 7. P0 Constraints

Any future implementation must hard-fail before serving data if these are
violated:

```text
current principal resolver missing
current principal resolver returns zero or multiple principals
SQL/API read is not principal-scoped
cross-principal account/watchlist/proposal/portfolio/PnL read is possible
Track B API reuses /api/n6/ui/v1
POST/PUT/PATCH/DELETE route exists in this API namespace
database write attempted
proposal/order/trade/position/PnL mutation attempted
leaderboard materialization attempted
N5 outbox consumed or status updated
N4/N5 raw facts used to bypass reviewed artifacts
N6 directly pulls live market data
raw K or N1 raw facts read by user app
delivery/push/voice/mobile/sim/real trade triggered
```

## 8. Track A Isolation Proof

This contract does not modify Track A pages:

```text
/n6/action-events
/n6/admin/account
/n6/admin/users
```

This contract does not modify or reuse Track A APIs:

```text
/api/n6/ui/v1/...
```

If a future B-track implementation needs shared display code or data shaping
from Track A, it must open:

```text
N6_SHARED_COMPONENT_ADAPTER_GATE
```

## 9. Implementation Readiness Tests Required Later

Future implementation gates must add tests for:

```text
all endpoints are GET-only
no POST/PUT/PATCH/DELETE in /api/n6/app/v1
current principal resolver required
current principal resolver rejects zero/multiple principal matches
account SQL includes principal_id/principal_type
portfolio SQL includes principal_id/principal_type
PnL SQL includes principal_id/principal_type
watchlist/proposals remain empty/planned until their gates
signals use reviewed artifacts/projection adapters only
no /api/n6/ui/v1 reuse
no DB writes
no outbox updates
no proposal/order/trade/position/PnL mutation
PnL and leaderboard disclaimers present
forbidden wording and real-trade semantics absent
```

## 10. Boundary Flags

```text
database_written = false
code_modified = false
executed = false
outbox_consumed = false
outbox_status_updated = false
worker_started = false
delivery_triggered = false
push_triggered = false
voice_triggered = false
mobile_triggered = false
sim_triggered = false
position_written = false
real_trade_triggered = false
proposal_generated = false
order_generated = false
trade_generated = false
pnl_generated = false
leaderboard_materialized = false
n6_ui_v1_modified = false
n6_ui_v1_api_reused = false
```

## 11. Next Recommended Gate

Recommended next gate:

```text
runtime_control N6_MULTI_USER_APP_SHELL_API_CONTRACT_REVIEW_GATE
```

After review passes, the next N6-user gate should be:

```text
N6_MULTI_USER_APP_SHELL_IMPLEMENTATION_READINESS_GATE
```

