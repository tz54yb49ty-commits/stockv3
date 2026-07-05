# N6 Multi User App Shell Implementation Readiness

Status: READINESS_PASS

Layer role: N6_user

Date: 2026-06-05

This readiness gate freezes P0/P1/P2 implementation requirements before any
read-only implementation of Track B `/n6/app/...` pages and
`/api/n6/app/v1/...` APIs. It is a documentation artifact only. It does not
write code, write database rows, execute runners, consume or update outbox
rows, start workers, modify Track A `N6_UI_v1`, deliver notifications, push to
voice/mobile, run sim, write positions, or place real trades.

## 1. Basis

Authoritative inputs:

```text
docs/N6_MULTI_USER_APP_SHELL_SPEC.md
docs/N6_MULTI_USER_APP_SHELL_SPEC.json
docs/N6_MULTI_USER_APP_SHELL_TRACEABILITY.md
docs/N6_MULTI_USER_APP_SHELL_TRACEABILITY.json
docs/N6_MULTI_USER_APP_SHELL_API_CONTRACT.md
docs/N6_MULTI_USER_APP_SHELL_API_CONTRACT.json
docs/N6_MULTI_USER_APP_SHELL_API_TRACEABILITY.md
docs/N6_MULTI_USER_APP_SHELL_API_TRACEABILITY.json
runtime_control APPROVED_WITH_CHANGES review
docs/N6_TRACK_SEPARATION_RESCUE_PLAN.md
docs/N6_TRACK_SEPARATION_RESCUE_PLAN.json
docs/N6_UI_V1_ADMIN_CONSOLE_FREEZE.md
docs/N6_UI_V1_ADMIN_CONSOLE_FREEZE.json
```

Canonical Track B namespaces:

```text
/n6/app/...
/api/n6/app/v1/...
```

Frozen Track A namespaces:

```text
/n6/action-events
/n6/admin/account
/n6/admin/users
/api/n6/ui/v1/...
```

## 2. Readiness Result

```text
READINESS_PASS
```

Quality summary:

| Severity | Count | Blocking now | Meaning |
|---|---:|---|---|
| P0 | 0 | yes if nonzero | No implementation blocker remains in the contract/readiness gate. |
| P1 | 8 | no | Mandatory tests/guards for the readonly implementation gate. |
| P2 | 5 | no | Non-blocking documentation and UI clarity items for implementation review. |

Readiness decision:

```text
allowed_next_gate = N6_MULTI_USER_APP_SHELL_READONLY_IMPLEMENTATION_GATE
```

This pass does not mean the B-track app is implemented. It means the readonly
implementation has a complete enough P0 contract and test checklist to begin.

## 3. P0 Requirements

The readonly implementation must block or fail tests if any P0 item below is
violated.

### P0-01 Current Principal Resolver

Requirement:

```text
Every /api/n6/app/v1/... request must resolve current principal before reading scoped data.
Admin as first user must resolve to the admin principal.
If the principal is missing, the API must return BLOCK/403/empty-safe.
Missing principal must never fallback to all rows.
Multiple principal matches must be rejected.
System principal must not resolve as a normal front-office principal.
```

Implementation target:

```text
session -> user_account -> n6_principal
```

Required admin predicate:

```text
n6_principal.principal_type = 'admin'
n6_principal.owner_user_id = user_account.user_id
```

### P0-02 Principal-Scoped SQL/API Filters

Requirement:

```text
/account reads only current principal virtual account.
/watchlist reads only current principal and currently returns empty/planned.
/proposals currently returns empty/planned.
/portfolio reads only current principal virtual_position and may be empty.
/pnl reads only current principal virtual_pnl_snapshot and may be empty.
Cross-principal reads are forbidden.
```

Required SQL predicate for owner-scoped resources:

```text
principal_id = :current_principal_id
principal_type = :current_principal_type
```

If a resource table does not yet support principal scope, its endpoint must
remain `empty/planned` until a schema/adapter gate fixes that gap.

### P0-03 Track A Non-Regression

Requirement:

```text
Do not modify /n6/action-events.
Do not modify /n6/admin/account.
Do not modify /n6/admin/users.
Do not reuse /api/n6/ui/v1/... for B-track APIs.
Do not add B-track menu items into Track A navigation.
Do not re-enable hidden Track A modules: 监控筛选 / 持仓 / 手机播报.
```

If shared display logic is needed, open:

```text
N6_SHARED_COMPONENT_ADAPTER_GATE
```

### P0-04 Forbidden Source Tests

`/signals` may only use this allowlist:

```text
reviewed N5/N6 artifacts
N6 shadow projection
user_signal_projection
user_signal_card
reviewed dashboard artifacts
approved/reviewed N3 snapshot
reviewed valuation policy
```

Forbidden:

```text
raw K
N1 raw facts
direct live market data
N4 raw facts used to bypass reviewed artifacts
N5 raw facts used to bypass reviewed artifacts
N5 outbox direct consumption or status update
```

### P0-05 Disclaimer Tests

`/pnl` must return and display:

```text
非真实收益
非投资建议
不代表未来收益
```

`/leaderboard` must return and display the same disclaimer set:

```text
非真实收益
非投资建议
不代表未来收益
```

### P0-06 Mutation Forbidden Tests

The readonly implementation must prove:

```text
No POST/PUT/PATCH/DELETE under /api/n6/app/v1.
No proposal generation.
No virtual order generation.
No virtual trade generation.
No position update.
No PnL materialization.
No leaderboard materialization.
No N4/N5 outbox consumption.
No N4/N5 outbox status update.
No delivery/push/voice/mobile/sim/position/real trade.
```

## 4. P1 Implementation Obligations

These are not blockers for this readiness gate because they belong to the
actual readonly implementation, but they are mandatory before claiming
implementation pass.

| ID | Obligation | Required proof in implementation gate |
|---|---|---|
| P1-01 | Implement current principal resolver. | Tests for admin principal success, missing principal block, multiple principal block, system principal block. |
| P1-02 | Implement GET-only route registry. | Route scan proving no POST/PUT/PATCH/DELETE under `/api/n6/app/v1`. |
| P1-03 | Implement principal-scoped account reads. | Tests proving account cannot leak cross-principal data. |
| P1-04 | Keep watchlist/proposals/ai-users/leaderboard empty/planned. | Tests proving no rows are generated and writable=false/materialized=false. |
| P1-05 | Implement signals source allowlist. | Static or unit tests proving no raw K/N1 raw/direct live/N4 raw/N5 raw bypass. |
| P1-06 | Implement PnL/leaderboard disclaimers. | Tests proving all three disclaimers are returned/displayed. |
| P1-07 | Preserve Track A. | Non-regression tests for A-track pages/API and hidden menus. |
| P1-08 | Prove zero side effects. | Tests or audit hooks proving no DB writes/outbox updates/worker/delivery/sim/real trade. |

## 5. P2 Implementation Notes

| ID | Note | Handling |
|---|---|---|
| P2-01 | B-track routes are not implemented yet. | Expected; implement only in next gate. |
| P2-02 | Shared component adapter is not defined. | Use local B-track components or open shared adapter gate. |
| P2-03 | Portfolio and PnL may be empty because no position/PnL rows exist. | Return empty scoped responses with disclaimers. |
| P2-04 | Watchlist, proposal, AI users, leaderboard are planned only. | Return empty/planned responses. |
| P2-05 | UI wording must avoid real-trade semantics. | Add forbidden wording tests in implementation gate. |

## 6. Implementation Allowlist

The next readonly implementation gate may add:

```text
B-track route definitions under /n6/app/...
B-track GET-only APIs under /api/n6/app/v1/...
B-track templates/components for app shell pages
current principal resolver for B-track APIs
read-only repository/query helpers with principal scope
empty/planned response adapters
signals read adapter using reviewed artifacts/projection allowlist
PnL and leaderboard disclaimer response fields
tests for readiness P0/P1 requirements
implementation readiness/update artifact
```

If the existing FastAPI app requires route mounting, the implementation may add
an additive B-track mount only. It must not change Track A handler behavior,
Track A menu content, or `/api/n6/ui/v1/...` semantics.

## 7. Forbidden Scope

The next readonly implementation gate remains forbidden from:

```text
modifying Track A N6_UI_v1 behavior
using /api/n6/ui/v1 as B-track API
writing database rows
consuming or updating N4/N5 outbox
starting workers
creating watchlist rows
generating proposals
reviewing or accepting proposals
generating virtual orders
generating virtual trades
updating virtual position
materializing virtual PnL
materializing leaderboard
creating AI users
creating AI decision/evaluation/virtual_intent
triggering delivery/push/voice/mobile/sim/position/real trade
reading raw K
reading N1 raw facts
pulling live market data
bypassing reviewed artifacts with N4/N5 raw facts
```

## 8. Required Endpoint Readiness Matrix

| Endpoint | Implementation posture | Principal scope | Empty allowed | Required P0 proof |
|---|---|---|---|---|
| `GET /api/n6/app/v1/me` | read-only | current session/principal | no | resolver exists and redacts secrets |
| `GET /api/n6/app/v1/account` | read-only | `n6_virtual_account.principal_id/principal_type` | yes | no cross-principal account read |
| `GET /api/n6/app/v1/watchlist` | empty/planned | current principal | yes | no write route / writable=false |
| `GET /api/n6/app/v1/signals` | read-only | approved projection adapter | yes | source allowlist only |
| `GET /api/n6/app/v1/proposals` | empty/planned | current principal | yes | generation_enabled=false |
| `GET /api/n6/app/v1/portfolio` | read-only empty allowed | `n6_virtual_position.principal_id/principal_type` | yes | no position write |
| `GET /api/n6/app/v1/pnl` | read-only empty allowed | `n6_virtual_pnl_snapshot.principal_id/principal_type` | yes | disclaimers present |
| `GET /api/n6/app/v1/ai-users` | empty/planned | current principal | yes | no AI creation/decision/evaluation |
| `GET /api/n6/app/v1/leaderboard` | empty/planned | approved public only | yes | disclaimers present / materialized=false |

## 9. Boundary Flags

```text
database_written = false
code_written = false
executed = false
outbox_consumed = false
outbox_status_updated = false
worker_started = false
track_a_modified = false
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
```

## 10. Next Gate

Allowed next gate:

```text
N6_MULTI_USER_APP_SHELL_READONLY_IMPLEMENTATION_GATE
```

That gate must implement only the allowlisted read-only shell/API surface and
must include tests for all P0 and P1 requirements above.

