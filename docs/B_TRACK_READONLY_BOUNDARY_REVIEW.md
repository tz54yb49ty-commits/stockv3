# B Track Readonly Boundary Review

Result: BLOCKED

Layer role: runtime_control

Date: 2026-06-07

Review mode: read-only static review. This gate did not write business data,
execute SQL, consume or update outbox/inbox/checkpoint rows, start workers,
trigger delivery/push/voice/mobile, enter sim/position/PnL/real trade, or
generate proposal/order/trade rows. Only review artifacts are updated.

## 1. Scope

Reviewed B Track app routes and source policy:

```text
/api/n6/app/v1/signals
/api/n6/app/v1/watchlist
/api/n6/app/v1/ai-users
/api/n6/app/v1/account
/n6/app
/n6/app/{page_key}
```

Required allowlist additions:

```text
N2 display_basis:
  stock_condition_display_basis
  index_condition_display_basis
  board_condition_display_basis

N1 membership_fact:
  index_membership_fact
  board_membership_fact
```

Preferred N6-facing view names already present in schema/seed foundations:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

Forbidden sources:

```text
condition_basis
condition_pool
minute_target_scope
raw K
N1 raw facts except reviewed membership_fact allowlist
direct live market
N4 raw facts bypass
N5 raw facts bypass
unreviewed outbox direct consumption
```

## 2. Passing Evidence

GET-only route surface:

```text
src/ashare_v3/web/n6_user_app.py:2230-2338 defines /api/n6/app/v1/* routes with @app.get.
src/ashare_v3/web/n6_user_app.py:2567-2572 defines /n6/app and /n6/app/{page_key} with @app.get.
No app-scope POST/PUT/PATCH/DELETE routes were found by static scan.
```

Principal scope:

```text
All app routes call current_session() and resolve_app_principal().
resolve_app_principal() requires exactly one active admin/human_user/ai_user principal.
```

Readonly side-effect flags:

```text
src/ashare_v3/web/n6_app_v1.py marks database writes, outbox updates,
proposal/order/trade generation, position/PnL mutation, delivery, voice,
mobile, sim, and real trade effects as false.
```

Existing N6 view foundation:

```text
sql/036_n6_multi_user_ai_owner_principal_schema.sql defines guarded views for
v_n6_stock_condition_display_basis, v_n6_index_condition_display_basis,
v_n6_board_condition_display_basis, v_n6_index_membership_fact, and
v_n6_board_membership_fact.
sql/037_n6_view_readonly_permission.sql grants readonly role SELECT on those views.
owner_principal_initialization and virtual_account_seed preflight code checks those views.
```

## 3. Findings

### BTR-P1-001: B Track Signals still delegates to A Track UI query

`fetch_app_signals()` receives `principal_id` and `principal_type`, discards
them, and calls `fetch_ui_v1_signals(user_id, filters, limit)`.

Impact:

```text
B Track Signals is user-scoped through A Track adapter behavior, not
principal-scoped through a B Track-owned allowlist adapter.
```

Remediation:

```text
Create B Track owned signal adapter.
Do not call fetch_ui_v1_signals().
Read only reviewed N6 projection/card sources plus approved B Track display context.
Enforce principal_id/principal_type in the adapter query.
```

### BTR-P1-002: B Track allowlist does not expose N2 display_basis to the app layer

Current B Track `APP_ALLOWED_SIGNAL_SOURCES` does not include:

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
```

Impact:

```text
Signals, Watchlist, Dashboard, and AI Users cannot be contractually grounded in
the N2 display input intended for N6 user display.
```

Remediation:

```text
Add N6-facing display_basis views to the B Track allowlist.
Use them only for condition names, condition_key, periods, direction, target
candidate display, and user-readable explanation.
Do not use them to rebuild N2 conditions or N3/N4/N5 trading decisions.
```

### BTR-P1-003: B Track allowlist does not expose N1 membership_fact to the app layer

Current B Track `APP_ALLOWED_SIGNAL_SOURCES` does not include:

```text
index_membership_fact
board_membership_fact
v_n6_index_membership_fact
v_n6_board_membership_fact
```

Impact:

```text
B Track cannot safely explain index/board constituents or stock membership
without either missing context or taking an uncontracted read path.
```

Remediation:

```text
Add N6-facing membership views to the allowlist.
Use membership only for display grouping and explanation.
Never infer trade conditions from membership_fact.
```

### BTR-P1-004: Forbidden source policy is incomplete

Current forbidden sources include raw K, N1 raw facts, direct live market, N4
raw facts bypass, and N5 raw facts bypass. They do not explicitly include:

```text
condition_basis
condition_pool
minute_target_scope
unreviewed outbox direct consumption
```

Remediation:

```text
Add explicit forbidden entries and boolean proof flags.
```

### BTR-P1-005: Missing global NOT INVESTMENT ADVICE wording

Global B Track safety labels include:

```text
READ ONLY
NO ORDER
NO TRADE
NO POSITION UPDATE
NO REAL TRADE
```

They do not include:

```text
NOT INVESTMENT ADVICE
```

Remediation:

```text
Add the exact label to all B Track API/page safety models and tests.
```

### BTR-P1-006: Watchlist and AI Users remain planned placeholders

`/api/n6/app/v1/watchlist` and `/api/n6/app/v1/ai-users` return planned empty
models. They do not yet read the required display_basis or membership context.

Remediation:

```text
Keep them GET-only and principal-scoped.
Add B Track-owned readonly DTOs after remediation contract.
```

### BTR-P1-007: Portfolio/PnL read future runtime tables too early

`/api/n6/app/v1/portfolio` reads `n6_virtual_position`.
`/api/n6/app/v1/pnl` reads `n6_virtual_pnl_snapshot`.

Impact:

```text
V1 locked modules can appear more complete than they are.
```

Remediation:

```text
For V1, render portfolio and PnL as locked/empty planned modules unless a
separate virtual position/PnL allowlist gate is approved.
```

## 4. Current Allowlist Status

| Source | Required | Current status |
|---|---:|---|
| user_signal_projection | yes | present through A/N6 adapter path |
| user_signal_card | yes | present through A/N6 adapter path |
| reviewed N6 dashboard artifacts | yes | present in wording |
| stock_condition_display_basis | yes | missing from B Track source policy |
| index_condition_display_basis | yes | missing from B Track source policy |
| board_condition_display_basis | yes | missing from B Track source policy |
| index_membership_fact | yes | missing from B Track source policy |
| board_membership_fact | yes | missing from B Track source policy |
| N6-facing readonly views | preferred | schema foundation exists, app adapter not using them |

## 5. Page/API Review

| Route | GET-only | Principal scoped | Display basis | Membership | Result |
|---|---:|---:|---:|---:|---|
| `/api/n6/app/v1/signals` | yes | route yes, adapter weak | missing | missing | BLOCKED |
| `/api/n6/app/v1/watchlist` | yes | yes | missing | missing | BLOCKED |
| `/api/n6/app/v1/ai-users` | yes | yes | missing | missing | BLOCKED |
| `/api/n6/app/v1/account` | yes | yes | not required | not required | REVIEW_PASS for account-only scope |

## 6. Boundary Decision

```text
REVIEW_RESULT = BLOCKED
P0 = 0
P1 = 7
P2 = 0
```

The route surface is safely read-only, but the B Track V1 source contract is
not complete enough for product implementation.

## 7. Next Gate

```text
B_TRACK_READONLY_REMEDIATION_CONTRACT_GATE
```
