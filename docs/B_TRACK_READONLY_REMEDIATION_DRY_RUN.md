# B Track Readonly Remediation Dry Run

Gate: B_TRACK_READONLY_REMEDIATION_CONTRACT_GATE

Result: DRY_RUN_PASS_FOR_CONTRACT

Implementation status: BLOCKED_UNTIL_B_TRACK_SIGNALS_IMPLEMENTATION

Layer role: runtime_control

Date: 2026-06-07

This dry-run validates the remediation contract without changing code or data.
It demonstrates the controlled read capability that the next implementation
gate must build.

## 1. Static Input State

Current state from boundary review:

```text
Signals Adapter reuses A Track fetch_ui_v1_signals.
Required N6 display cache allowlist is missing.
Forbidden source policy is incomplete.
B Track app routes are GET-only.
```

Therefore:

```text
current_implementation_pass=false
contract_scope_safe=true
implementation_required=true
```

## 2. Controlled Read Plan

Route:

```text
GET /n6/app/signals
GET /api/n6/app/v1/signals
```

Principal scope:

```text
Resolve current principal from the current session.
Use principal_id and principal_type in the adapter query.
Reject unresolved principal with principal_scope_unavailable.
Do not use A Track source-user fallback to widen the result set.
```

Allowed reads:

```text
reviewed N6 projections
reviewed signal cards
n6_display_stock_condition_cache
n6_display_index_condition_cache
n6_display_board_condition_cache
n6_display_index_membership_cache
n6_display_board_membership_cache
```

Allowed output:

```text
signal list
signal status
asset display name
N6-reviewed evidence summary
condition explanation
index/board membership explanation
safety labels
readonly source policy
```

## 3. Rejected Read Plan

The next implementation gate must reject any B Track Signals read path that
touches:

```text
raw K
N1 raw facts
direct live market
N4 raw facts bypass
N5 raw facts bypass
condition_basis
condition_pool
minute_target_scope
unreviewed outbox / raw facts
```

Rejected adapter behavior:

```text
calling fetch_ui_v1_signals
calling _ui_v1_signal_from_sql
joining common_event_outbox directly
discarding principal_id / principal_type
using signal_source_user_id fallback for B Track Signals
returning buy/sell/order controls
returning investment advice
```

## 4. Dry-Run Route Matrix

| Route | Method | Current state | Contract target |
|---|---|---|---|
| `/n6/app/signals` | GET | route OK, adapter blocked | GET-only, principal scoped, B Track adapter |
| `/api/n6/app/v1/signals` | GET | route OK, adapter blocked | GET-only, principal scoped, B Track adapter |
| `/api/n6/ui/v1/signals` | GET | A Track route exists | forbidden as B Track dependency |

Forbidden methods for B Track app routes:

```text
POST
PUT
PATCH
DELETE
```

## 5. Side-Effect Dry Run

Expected side effects:

```text
database_written=false
sql_executed=false
outbox_consumed=false
outbox_status_updated=false
worker_started=false
delivery_triggered=false
push_triggered=false
voice_triggered=false
mobile_triggered=false
sim_written=false
position_updated=false
pnl_generated=false
order_generated=false
trade_generated=false
real_trade_submitted=false
```

## 6. Assertions

This dry-run is valid only if:

```text
contract JSON parses
dry-run JSON parses
required contract keys exist
required allowlist entries exist
required forbidden source entries exist
B Track route scan is GET-only
git diff --check passes
```

## 7. Decision

```text
DRY_RUN_PASS_FOR_CONTRACT=true
CURRENT_IMPLEMENTATION_BLOCKED=true
NEXT_GATE=B_TRACK_SIGNALS_IMPLEMENTATION
```

The remediation is safe and scoped. It should proceed to
`B_TRACK_SIGNALS_IMPLEMENTATION`, where the actual B Track Signals Adapter can
be replaced and verified.

