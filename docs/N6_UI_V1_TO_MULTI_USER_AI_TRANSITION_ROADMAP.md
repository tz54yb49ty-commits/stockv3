# N6 UI v1 to Multi User and AI Transition Roadmap

Result: `ROADMAP_PASS`

Layer role: `runtime_control`

Generated at: `2026-06-05T00:15:40+08:00`

This roadmap connects the frozen A-track `N6_UI_v1` read-only administrator
dashboard to the future B-track `N6_MULTI_USER_AND_AI` architecture. It is a
planning artifact only. It does not modify code, write database rows, execute
DDL, run migrations, consume outbox rows, start workers, modify existing N6 UI
APIs, modify projection or shadow pipelines, deliver notifications, push to
voice/mobile, run sim, create positions, or place real trades.

## 1. Current Baseline

### Track A: N6_UI_v1

```text
status=IMPLEMENTATION_PASS / FINAL_FREEZE_PASS
purpose=administrator/internal read-only dashboard
components=Dashboard, Signal List, Signal Detail, Audit Panel, Notification Preview
write_behavior=none
outbox_consumption=false
delivery_push_voice_mobile_sim_position_real_trade=false
```

Track A remains stable. It must not be modified by Track B work unless a future
adapter compatibility gate explicitly approves the change.

### Track B: N6_MULTI_USER_AND_AI

```text
spec=N6_MULTI_USER_AND_AI_SPEC_v1 SPEC_FREEZE_PASS
architecture=N6_MULTI_USER_AND_AI_ARCHITECTURE_v1 APPROVED
036_owner_principal_account_schema=executed
037_readonly_role_permission=PREFLIGHT_BLOCKED_BY_ROLE_CREATION_PRIVILEGE
```

Current blocker:

```text
n6_ui_readonly_role does not exist
ashare_v3_user.rolcreaterole=false
037 cannot execute with current user until the role is pre-created or a role
with CREATEROLE executes the permission migration
```

## 2. Transition Principles

```text
Phase order is dependency order, not automatic execution order.
Every phase requires its own gate, contract, preflight, rollback, and post-review
before any database write or runtime behavior is allowed.
A-track APIs/projection/shadow pipeline remain unchanged until Phase 8 adapter.
B-track may not consume or update N4/N5 outbox.
Real delivery, push, voice, mobile, sim, position, and real trade remain out of
scope through Phase 8.
Phase 9 is explicitly out of scope and only lists future gates.
```

## 3. Phase Plan

| Phase | Name | Goal | Current status |
|---|---|---|---|
| 0 | A-track freeze | Preserve N6_UI_v1 as read-only admin dashboard | complete |
| 1 | B-track base permission | Establish safe readonly access to 036 views | blocked by 037 role creation |
| 2 | Owner / principal / account foundation | Use 036 tables for principal/account governance | ready after Phase 1 |
| 3 | Virtual account schema | Design paper account/cash/position/order schema | not started |
| 4 | Watchlist / strategy | Add principal-owned watchlists and strategy ownership | not started |
| 5 | AI user MVP | Add AI principal reads and draft proposals | not started |
| 6 | AI virtual intent | Route accepted AI proposals into virtual intent only | not started |
| 7 | AI evaluation / leaderboard | Evaluate virtual outcomes and publish safe rankings | not started |
| 8 | A/B adapter | Add non-breaking summaries into A-track-compatible surfaces | not started |
| 9 | Notification / sim / position / real trade | Future side-effect gates only | out of scope |

## 4. Phase Details

### Phase 0: A-track Freeze

Goal:

```text
Keep N6_UI_v1 as an administrator/internal read-only dashboard.
Display only Dashboard, Signal List, Signal Detail, Audit Panel, and Preview.
Do not add multi-user writes or Track B business behavior.
```

Forbidden scope:

```text
no N6_UI_v1 API mutation
no projection/shadow pipeline mutation
no outbox consumption
no delivery / push / voice / mobile / sim / position / real trade
```

Prerequisites:

```text
docs/N6_UI_v1_FINAL_FREEZE_REPORT.md
docs/N6_UI_v1_FINAL_FREEZE_REPORT.json
N6_UI_v1 implementation tests passed
```

Acceptance criteria:

```text
status remains FINAL_FREEZE_PASS
read-only route map remains stable
N6UI-017 remains future_enhancement and non-blocking
Track B work does not modify A-track files or API behavior
```

### Phase 1: B-track Base Permission

Goal:

```text
Resolve the 037 readonly role blocker.
Create or use n6_ui_readonly_role, or an equivalent read-only access mode.
Allow SELECT only on the five 036 read-only views.
Keep all 036 base Track B tables protected from runtime/API writes.
```

Forbidden scope:

```text
no business rows
no N6_UI_v1 API changes
no projection/shadow pipeline changes
no outbox consumption/update
no worker
no delivery / push / voice / mobile / sim / position / real trade
```

Prerequisites:

```text
036 owner/principal/account schema migration passed
5 Track B tables exist
5 N6 read-only views exist
037 repair plan exists
role creation blocker resolved by DBA pre-create or privileged migration session
```

Acceptance criteria:

```text
n6_ui_readonly_role exists or equivalent read-only role/mode is documented
role has USAGE ON SCHEMA public
role has SELECT on exactly five v_n6_* views
role has no INSERT / UPDATE / DELETE / TRUNCATE / REFERENCES / TRIGGER
role has no privileges on n6_principal / n6_ai_user / n6_principal_account /
n6_watchlist_ownership / n6_strategy
views have no INSTEAD OF trigger
rollback for 037 is present and hard-fail guarded
```

### Phase 2: Owner / Principal / Account Foundation

Goal:

```text
Use 036 tables as the Track B owner root.
Define initialization rules for human/admin/system/ai_user principals.
Do not create virtual trading behavior.
```

Forbidden scope:

```text
no virtual order
no virtual position
no virtual trade
no real account / real cash / real position / broker credential
no N5 outbox consumption
no A-track API mutation
```

Prerequisites:

```text
Phase 1 readonly permission passed
036 schema post-review passed
principal initialization contract generated
rollback SQL scoped to initialization rows
```

Acceptance criteria:

```text
human/admin principals bind only existing user_account.user_id
system principal is reserved and non-user-owned
ai_user principal may exist as reserved root before profile
n6_ai_user profile binds only principal_type=ai_user
all initialization rows have source artifact / policy_version / rollback scope
```

### Phase 3: Virtual Account Schema

Goal:

```text
Design virtual account, virtual cash, virtual position, and virtual order schema.
Keep this phase to schema draft / migration gates only.
No real trade and no virtual execution runner yet.
```

Forbidden scope:

```text
no order execution
no position mutation
no sim runner
no real broker fields
no N5 side-effect interpretation
no N6_UI_v1 mutation
```

Prerequisites:

```text
Phase 2 owner/principal/account foundation passed
virtual account spec contract drafted
fee / slippage / T+1 / initial cash policy defined
rollback strategy hard-fails on linked orders/positions
```

Acceptance criteria:

```text
schema separates virtual cash, virtual order, virtual trade, and virtual position
all objects are scoped by principal_id / account_id
all monetary values are labeled virtual or paper
no broker account identifiers or real funds fields exist
migration remains additive and rollback-safe
```

### Phase 4: Watchlist / Strategy

Goal:

```text
Add user monitoring objects and strategy ownership.
Support visibility values private / shared / admin / public_leaderboard.
```

Forbidden scope:

```text
watchlists do not expand N2/N3/N4/N5 scope
strategies do not rewrite N4 trigger truth or N5 action truth
no strategy execute runner
no marketplace publication
no A-track API mutation
```

Prerequisites:

```text
Phase 2 passed
watchlist ownership contract generated
strategy ownership/version contract generated
visibility and sharing policy drafted
```

Acceptance criteria:

```text
watchlist rows use asset_kind + identity_key
strategy rows have owner principal, policy_version, policy_hash, status
visibility enforcement has test plan
upstream write boundary is explicitly tested
rollback is principal/run scoped
```

### Phase 5: AI User MVP

Goal:

```text
Create an AI user MVP that reads only approved N2/N3/N4/N5/N6 shadow inputs.
AI output is draft proposal only.
AI cannot create orders.
```

Forbidden scope:

```text
no raw K
no live market data direct connection
no N1 raw facts
no real account / real funds / real position
no broker session / real trade API
no virtual_intent without Phase 6
no N5 outbox consumption/update
```

Prerequisites:

```text
Phase 1 readonly view permission passed
Phase 2 AI principal/profile foundation passed
AI readable_scope_policy enforcement contract generated
proposal schema draft generated
source artifact allowlist frozen
```

Acceptance criteria:

```text
AI input is snapshot/artifact based
each proposal records source projection/artifact lineage
forbidden source denial tests pass
proposal status starts as draft
no order / sim / position / real trade rows are written
```

### Phase 6: AI Virtual Intent

Goal:

```text
Implement the proposal lifecycle:
draft -> reviewed -> accepted/rejected -> virtual_intent.
virtual_intent can only feed virtual account flows.
```

Forbidden scope:

```text
virtual_intent is not a real order
accepted proposal is not broker instruction
no real trade
no N5 outbox status mutation
no push / voice / mobile side effects
```

Prerequisites:

```text
Phase 3 virtual account schema passed
Phase 5 AI proposal MVP passed
human review policy contract generated
virtual_intent rollback model generated
```

Acceptance criteria:

```text
draft/reviewed/accepted/rejected/virtual_intent state machine is enforced
only reviewed proposals can become accepted/rejected
accepted proposal creates at most virtual_intent
virtual_intent is scoped to virtual account
rollback hard-fails if downstream virtual order/position refs exist
```

### Phase 7: AI Evaluation / Leaderboard

Goal:

```text
Evaluate AI and strategy outputs using virtual results only.
Publish leaderboard metrics for virtual PnL, drawdown, win rate, and ranking.
```

Forbidden scope:

```text
leaderboard is not real return
leaderboard is not investment advice
leaderboard does not imply future returns
no private holdings/funds/session/prompt leakage
no real trade or broker data
```

Prerequisites:

```text
Phase 3 virtual account schema passed
Phase 5 proposal lineage passed
Phase 6 virtual_intent path passed if forward evaluation uses intents
evaluation policy/version/hash drafted
privacy redaction policy drafted
```

Acceptance criteria:

```text
evaluation input window is sealed
mode labels are explicit: backtest / replay / shadow_forward / virtual_live
metrics include virtual PnL, drawdown, win rate, sample count
leaderboard rows reference approved evaluation artifacts
disclaimers are rendered and tested
```

### Phase 8: A/B Adapter

Goal:

```text
Add an adapter that lets A-track surfaces display B-track multi-user/AI summary
without modifying existing N6_UI_v1 APIs, projection, or shadow pipeline.
```

Forbidden scope:

```text
no mutation of existing N6_UI_v1 endpoints
no migration of existing projection/card/queue rows
no replacement of A-track dashboard semantics
no outbox consumption
no delivery / push / voice / mobile / sim / position / real trade
```

Prerequisites:

```text
Phase 1 readonly access passed
Phase 2 owner/principal foundation passed
at least one B-track summary source has passed post-review
adapter compatibility contract generated
```

Acceptance criteria:

```text
adapter exposes new additive endpoints or artifacts only
existing A-track endpoint responses remain backward compatible
adapter can be disabled without affecting N6_UI_v1
tests prove no existing API/projection/shadow mutation
```

### Phase 9: Notification / Sim / Position / Real Trade

Goal:

```text
Keep all side-effect paths explicitly out of scope for this transition roadmap.
Future work must open separate readiness, final gate, execute, and post-review
cycles for each side-effect domain.
```

Forbidden scope:

```text
no notification delivery execute
no push
no voice
no mobile
no sim execution
no position mutation
no real trade
no broker credential storage or broker session
```

Prerequisites:

```text
none in this roadmap; future explicit user request required
separate specs, contracts, preflights, rollback SQL, tests, and final gates
```

Acceptance criteria:

```text
side-effect domains remain disabled by default
no hidden dependency in Phase 0-8 enables real delivery/sim/position/trade
future gates must prove user confirmation and rollback boundaries separately
```

## 5. Current Blockers

```text
P0 blocker: 037 readonly role permission cannot execute with ashare_v3_user
because n6_ui_readonly_role does not exist and ashare_v3_user.rolcreaterole=false.
```

Non-blocking future gaps:

```text
principal initialization run not implemented
virtual account schema not drafted
watchlist/strategy ownership implementation not started
AI proposal/evaluation/leaderboard runners not started
A/B adapter not started
real delivery/sim/position/trade intentionally out of scope
```

## 6. Current Next Recommended Gate

```text
N6_037_VIEW_READONLY_PERMISSION_BLOCKER_RESOLUTION_GATE
```

Recommended goal:

```text
choose one safe 037 resolution:
  A. privileged DBA/session pre-creates n6_ui_readonly_role NOLOGIN
  B. execute 037 with a role that has CREATEROLE

then return to runtime_control for 037 execute final gate review
```

Still forbidden in the next gate:

```text
N6_UI_v1 API/projection/shadow changes
business rows
outbox consumption/update
worker
delivery / push / voice / mobile / sim / position / real trade
```

## 7. Final Decision

```text
ROADMAP_PASS
current_track_a_status=FINAL_FREEZE_PASS
current_track_b_status=architecture approved, 036 executed, 037 blocked
current_next_gate=N6_037_VIEW_READONLY_PERMISSION_BLOCKER_RESOLUTION_GATE
```
