# N6 Multi User App Shell API Traceability

Status: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-05

Coverage: 100%

Rule count: 46

Duplicate / missing rule check: 0

This traceability artifact maps the B-track read-only API contract to endpoint,
principal-scope, source-boundary, Track A isolation, and future test targets.
`contracted` means the response and boundary are frozen by this gate.
`empty_planned` means the endpoint may return an empty planned response and
must not materialize business rows. `test_planned` means future implementation
must add tests before claiming implementation pass.

| Rule ID | Spec section | Component | Data source | Test target | Status |
|---|---|---|---|---|---|
| N6API-001 | API Design Principle | API namespace | Route registry | All B-track APIs use `/api/n6/app/v1` | contracted |
| N6API-002 | API Design Principle | A-track API isolation | Route/API registry | No user app API under `/api/n6/ui/v1` | contracted |
| N6API-003 | API Design Principle | GET-only policy | Route registry | No POST/PUT/PATCH/DELETE under `/api/n6/app/v1` | contracted |
| N6API-004 | Current Principal Resolver | Principal resolver | session, user_account, n6_principal | Resolver exists before scoped data reads | contracted |
| N6API-005 | Current Principal Resolver | Admin first user | user_account, n6_principal | Admin maps to exactly one admin principal | test_planned |
| N6API-006 | Current Principal Resolver | Zero/multiple guard | n6_principal | Reject zero or multiple principal matches | test_planned |
| N6API-007 | Current Principal Resolver | System boundary | n6_principal | System principal cannot be normal front-office principal | contracted |
| N6API-008 | Common Response Envelope | Response envelope | API serializer | Response includes result/api_version/principal_context/data/disclaimers/side_effects | contracted |
| N6API-009 | Principal Scope SQL Policy | Principal predicate | SQL builder | Owner-scoped reads include principal_id/principal_type | contracted |
| N6API-010 | GET /me | Me endpoint | session, user_account, n6_principal | Returns principal_id/principal_type/display_name/role/app_scope/permissions | contracted |
| N6API-011 | GET /me | Secret redaction | user_account, user_session | No password_hash/session_token_hash returned | contracted |
| N6API-012 | GET /account | Account endpoint | n6_virtual_account, n6_virtual_cash_snapshot | Returns virtual_account_id/account_name/cash/status fields | contracted |
| N6API-013 | GET /account | Account scope | n6_virtual_account | Account query scoped to current principal | test_planned |
| N6API-014 | GET /account | Real account boundary | API serializer | No broker/real funds/real position semantics | contracted |
| N6API-015 | GET /watchlist | Watchlist endpoint | future watchlist | Returns empty/planned and writable=false | empty_planned |
| N6API-016 | GET /watchlist | Watchlist write boundary | future watchlist | No create/update/delete watchlist | contracted |
| N6API-017 | GET /signals | Signals endpoint | reviewed N5/N6 artifacts, N6 projection | Returns principal-visible signal summaries | contracted |
| N6API-018 | GET /signals | Signals source boundary | reviewed artifacts | No raw K/N1 raw/live direct/N4 raw/N5 raw bypass | contracted |
| N6API-019 | GET /signals | Proposal eligibility display | proposal spec | Eligibility is display-only and does not generate proposal | contracted |
| N6API-020 | GET /proposals | Proposals endpoint | future proposal source | Returns empty/planned, generation_enabled=false | empty_planned |
| N6API-021 | GET /proposals | Proposal mutation boundary | future proposal source | No generate/review/accept/reject proposal | contracted |
| N6API-022 | GET /portfolio | Portfolio endpoint | n6_virtual_position | Returns current principal positions or empty | contracted |
| N6API-023 | GET /portfolio | Portfolio scope | n6_virtual_position | Portfolio query scoped to current principal | test_planned |
| N6API-024 | GET /portfolio | Position mutation boundary | n6_virtual_position | No position create/update/T+1 execution | contracted |
| N6API-025 | GET /pnl | PnL endpoint | n6_virtual_pnl_snapshot | Returns current principal PnL snapshots or empty | contracted |
| N6API-026 | GET /pnl | PnL disclaimers | API serializer | Includes non-real-return/non-advice/future-return disclaimers | contracted |
| N6API-027 | GET /pnl | PnL source boundary | valuation artifacts | No live price/raw K/real performance/investment advice | contracted |
| N6API-028 | GET /ai-users | AI users endpoint | future AI profile source | Returns empty/planned and AI execution disabled | empty_planned |
| N6API-029 | GET /ai-users | AI side-effect boundary | AI architecture | No AI user/decision/evaluation/virtual intent creation | contracted |
| N6API-030 | GET /leaderboard | Leaderboard endpoint | future approved leaderboard | Returns empty/planned and materialized=false | empty_planned |
| N6API-031 | GET /leaderboard | Leaderboard disclaimers | API serializer | Includes non-real-return/non-advice/future-return disclaimers | contracted |
| N6API-032 | GET /leaderboard | Leaderboard materialization boundary | future leaderboard source | No materialization or private principal leakage | contracted |
| N6API-033 | P0 Constraints | Principal resolver P0 | resolver | Missing resolver is P0 blocker | contracted |
| N6API-034 | P0 Constraints | Principal-scope P0 | SQL builder | Unscoped owner read is P0 blocker | contracted |
| N6API-035 | P0 Constraints | Cross-principal P0 | permission policy | Cross-principal account/watchlist/proposal/portfolio/PnL read is P0 blocker | contracted |
| N6API-036 | P0 Constraints | Write method P0 | route registry | POST/PUT/PATCH/DELETE is P0 blocker | contracted |
| N6API-037 | P0 Constraints | DB write P0 | DB access audit | Any DB write is P0 blocker for this contract | contracted |
| N6API-038 | P0 Constraints | Business mutation P0 | runtime checks | proposal/order/trade/position/PnL mutation is P0 blocker | contracted |
| N6API-039 | P0 Constraints | Outbox P0 | outbox access audit | N5 outbox consume/status update is P0 blocker | contracted |
| N6API-040 | P0 Constraints | Market data P0 | source access audit | direct live market/raw K/N1 raw read is P0 blocker | contracted |
| N6API-041 | Track A Isolation | A-track pages | existing routes | Does not modify `/n6/action-events`, `/n6/admin/account`, `/n6/admin/users` | contracted |
| N6API-042 | Track A Isolation | Shared component gate | gate registry | Track A/B shared display requires adapter gate | contracted |
| N6API-043 | Boundary Flags | Side effects | response envelope | side_effect flags remain false | contracted |
| N6API-044 | Implementation Readiness | Endpoint tests | future tests | Each endpoint has read-only response tests | test_planned |
| N6API-045 | Implementation Readiness | Scope tests | future tests | Cross-principal access denied tests required | test_planned |
| N6API-046 | Implementation Readiness | A-track regression tests | future tests | A-track API/page namespace unchanged tests required | test_planned |

## Current Gaps

```text
B-track APIs are not implemented.
Current principal resolver for /api/n6/app/v1 is not implemented.
Watchlist, proposal, AI user, and leaderboard APIs are empty/planned only.
Portfolio and PnL may return empty until materialization/valuation gates create rows.
Shared component adapter is not defined.
```

