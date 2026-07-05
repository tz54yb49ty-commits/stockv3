# B Track Readonly Remediation Contract

Gate: B_TRACK_READONLY_REMEDIATION_CONTRACT_GATE

Result: CONTRACT_PASS

Implementation status: BLOCKED_UNTIL_B_TRACK_SIGNALS_IMPLEMENTATION

Layer role: runtime_control

Date: 2026-06-07

This contract converts the B Track readonly boundary review into an implementation
contract. It is a documentation and dry-run artifact only. It does not change
code, execute SQL, write database rows, consume outbox rows, start workers,
deliver notifications, write sim or position rows, generate orders, or submit
real trades.

## 1. Current Findings Carried Forward

The previous review found:

```text
Signals Adapter currently delegates to A Track fetch_ui_v1_signals.
Signals Adapter currently ignores principal_id / principal_type in the B Track path.
The required N6 display cache allowlist is missing from B Track source policy.
Forbidden source policy is incomplete.
GET-only B Track route surface is OK.
```

Current implementation therefore remains blocked. This gate passes only the
remediation contract and dry-run scope.

## 2. Non-Negotiable Boundary

B Track V1 is a readonly multi-user frontend, not a trading terminal.

Required invariants:

```text
READ ONLY
GET-only page/API surface
NO ORDER
NO TRADE
NO POSITION UPDATE
NO REAL TRADE
NOT INVESTMENT ADVICE
principal scoped
no A Track /api/n6/ui/v1 adapter reuse
no direct N1/N2/N3/N4/N5 bypass reads outside the allowlist
no database business-fact writes
no outbox consumption
no worker
no push / voice / mobile delivery
```

## 3. Route Model

The Signals remediation is scoped to these B Track surfaces:

| Surface | Route | Allowed methods | Required state |
|---|---|---|---|
| HTML page | `/n6/app/signals` | `GET` | readonly, principal scoped |
| API | `/api/n6/app/v1/signals` | `GET` | readonly, principal scoped |

All B Track `/n6/app*` and `/api/n6/app/v1/*` routes must remain GET-only.

Forbidden methods for B Track app routes:

```text
POST
PUT
PATCH
DELETE
```

A Track routes under `/api/n6/ui/v1/*` are out of scope for B Track V1 and must
not be called by the B Track Signals Adapter.

## 4. Signals Adapter Contract

The B Track Signals Adapter must be independent from A Track.

Forbidden calls:

```text
fetch_ui_v1_signals
fetch_ui_v1_signal_detail
fetch_ui_v1_signal_statistics
_ui_v1_signal_from_sql
_ui_v1_signal_where
signal_source_user_id fallback for B Track signals
/api/n6/ui/v1/signals
```

Required adapter behavior:

```text
Use current principal resolver output.
Require principal_id and principal_type as first-class query inputs.
Do not discard principal_id / principal_type.
Return only the current principal's reviewed N6 projections and reviewed signal cards.
Attach display cache context only as explanation.
Attach membership cache context only as explanation.
Return safety policy and source policy in the model.
Never expose buy/sell action buttons, trade intent, order fields, or advice wording.
```

Principal scope rule:

```text
principal_id must be matched to the row owner or reviewed principal mapping.
principal_type must be part of the read predicate.
admin source-user fallback must not widen B Track user-visible data.
If principal scope cannot be resolved, return principal_scope_unavailable.
```

## 5. Required Allowlist

The B Track Signals read model may read only these source classes:

```text
reviewed N6 projections
reviewed signal cards
n6_display_stock_condition_cache
n6_display_index_condition_cache
n6_display_board_condition_cache
n6_display_index_membership_cache
n6_display_board_membership_cache
```

Source intent:

| Source | Use | Forbidden use |
|---|---|---|
| reviewed N6 projections | Signal inbox rows already reviewed for user display | Recompute N4/N5 facts or create new signals |
| reviewed signal cards | Display-ready card payload and evidence summary | Generate trade/order/position/PnL intent |
| `n6_display_stock_condition_cache` | Stock condition explanation | Rebuild condition_basis or condition_pool |
| `n6_display_index_condition_cache` | Index condition explanation | Rebuild index trigger scope |
| `n6_display_board_condition_cache` | Board condition explanation | Rebuild board trigger scope |
| `n6_display_index_membership_cache` | Index membership display context | Infer trade universe or pull market data |
| `n6_display_board_membership_cache` | Board membership display context | Infer trade universe or pull market data |

Allowed display fields are explanatory only:

```text
asset_kind
identity_key
display_name
condition_key
direction
selected_signal_types / allowed_signal_types display
target candidate display
period/reference display
index membership display
board membership display
reviewed N4/N5 -> N6 evidence summary already materialized by N6
```

## 6. Forbidden Sources

The B Track Signals Adapter and source policy must explicitly reject:

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

Required proof flags:

```text
raw_k_read=false
n1_raw_facts_read=false
direct_live_market_read=false
n4_raw_facts_bypass=false
n5_raw_facts_bypass=false
condition_basis_read=false
condition_pool_read=false
minute_target_scope_read=false
unreviewed_outbox_or_raw_facts_read=false
```

The adapter must not directly join `common_event_outbox` unless a later reviewed
N6 projection contract explicitly materializes that data into a reviewed N6
source. For this remediation contract, unreviewed outbox/raw-fact reads are
forbidden.

## 7. Page/API Readonly Policy

For `/n6/app/signals` and `/api/n6/app/v1/signals`:

```text
request method = GET only
database writes = false
outbox consumed = false
outbox status updated = false
worker started = false
notification delivery = false
order generated = false
trade generated = false
position updated = false
PnL generated = false
real trade submitted = false
```

The page may show:

```text
signal list
signal state
asset identity and display name
N6-reviewed evidence chain
blocked/executed display state from reviewed card/projection
condition explanation from display cache
membership explanation from display cache
safety banner
```

The page must not show:

```text
buy button
sell button
place order button
auto-trade toggle
position update control
investment advice label
raw K chart sourced directly from raw K/live market
N4/N5 raw fact debug table
outbox debug table
```

## 8. Acceptance Criteria

This contract is accepted when all are true:

```text
JSON artifact parses.
JSON schema assertions pass.
Required allowlist entries are present.
Required forbidden sources are present.
Route scan proves B Track app routes are GET-only.
git diff --check passes.
Contract recommends B_TRACK_SIGNALS_IMPLEMENTATION as next gate.
```

## 9. Remediation Recommendation

Proceed to implementation only after this contract is accepted.

Recommended implementation gate:

```text
B_TRACK_SIGNALS_IMPLEMENTATION
```

Implementation should replace the current B Track Signals Adapter with a
principal-scoped read model that does not call A Track `fetch_ui_v1_signals`,
adds the required allowlist/forbidden source policy, and keeps all B Track app
routes GET-only.

