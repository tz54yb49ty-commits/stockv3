# N6 Multi User App Shell Traceability

Status: SPEC_PASS

Layer role: N6_user

Date: 2026-06-05

Coverage: 100%

Rule count: 36

Duplicate / missing rule check: 0

This traceability artifact maps the B-track app shell specification to route,
API, permission, data-boundary, isolation, and test targets. `planned` means a
future implementation gate must still build and verify the item. `doc` means
the boundary is frozen by this spec gate.

| Rule ID | Spec section | Component | Data source | Test target | Status |
|---|---|---|---|---|---|
| N6APP-001 | Product Identity | Track B identity | Boundary docs | Assert app identity is `N6_MULTI_USER_AND_AI_APP` | doc |
| N6APP-002 | Product Identity | Page namespace | Route registry | Assert Track B routes start with `/n6/app` | planned |
| N6APP-003 | Product Identity | API namespace | API registry | Assert Track B APIs start with `/api/n6/app/v1` | planned |
| N6APP-004 | Product Identity | Track A API isolation | Route/API registry | Assert `/api/n6/ui/v1` is not used by user app | doc |
| N6APP-005 | Routes | App Home | Route registry | `GET /n6/app` route registration | planned |
| N6APP-006 | Routes | Dashboard | Route registry | `GET /n6/app/dashboard` route registration | planned |
| N6APP-007 | Routes | Account | Route registry | `GET /n6/app/account` route registration | planned |
| N6APP-008 | Routes | Watchlist | Route registry | `GET /n6/app/watchlist` route registration | planned |
| N6APP-009 | Routes | Signals | Route registry | `GET /n6/app/signals` route registration | planned |
| N6APP-010 | Routes | Proposals | Route registry | `GET /n6/app/proposals` route registration | planned |
| N6APP-011 | Routes | Portfolio | Route registry | `GET /n6/app/portfolio` route registration | planned |
| N6APP-012 | Routes | PnL | Route registry | `GET /n6/app/pnl` route registration | planned |
| N6APP-013 | Routes | AI Users | Route registry | `GET /n6/app/ai-users` route registration | planned |
| N6APP-014 | Routes | Leaderboard | Route registry | `GET /n6/app/leaderboard` route registration | planned |
| N6APP-015 | API Prefix | Me API | Session/principal provider | `GET /api/n6/app/v1/me` read-only API | planned |
| N6APP-016 | API Prefix | Account API | Principal-scoped virtual account | `GET /api/n6/app/v1/account` read-only API | planned |
| N6APP-017 | API Prefix | Watchlist API | Principal-owned watchlist | `GET /api/n6/app/v1/watchlist` read-only API first | planned |
| N6APP-018 | API Prefix | Signals API | N6 projection adapter | `GET /api/n6/app/v1/signals` read-only API | planned |
| N6APP-019 | API Prefix | Proposals API | Future proposal source | `GET /api/n6/app/v1/proposals` read-only API first | planned |
| N6APP-020 | API Prefix | Portfolio API | Future virtual position adapter | `GET /api/n6/app/v1/portfolio` read-only API | planned |
| N6APP-021 | API Prefix | PnL API | Future virtual PnL adapter | `GET /api/n6/app/v1/pnl` read-only API | planned |
| N6APP-022 | API Prefix | AI Users API | Future AI profile adapter | `GET /api/n6/app/v1/ai-users` read-only API first | planned |
| N6APP-023 | API Prefix | Leaderboard API | Future approved performance adapter | `GET /api/n6/app/v1/leaderboard` read-only API | planned |
| N6APP-024 | Permission Model | Admin first user | `n6_principal`, `user_account` | Admin can resolve first principal | planned |
| N6APP-025 | Permission Model | Principal isolation | Principal-scoped stores | User cannot read another principal account/watchlist/proposal/portfolio/PnL | planned |
| N6APP-026 | Permission Model | Admin audit boundary | A/B route namespaces | Admin front office does not silently mix admin console pages | doc |
| N6APP-027 | Permission Model | AI user boundary | AI architecture artifacts | AI page has no decision/evaluation side effects | doc |
| N6APP-028 | Page Boundaries | Proposal boundary | Proposal spec | Shell does not generate or accept proposal | doc |
| N6APP-029 | Page Boundaries | Order/trade boundary | Virtual order/trade schema | Shell does not generate order/trade | doc |
| N6APP-030 | Page Boundaries | Position/PnL boundary | Virtual position/PnL schema | Shell does not update position/PnL | doc |
| N6APP-031 | Data Boundary | Allowed sources | Reviewed adapters/artifacts | User app reads only approved/principal-scoped summaries | doc |
| N6APP-032 | Data Boundary | Forbidden sources | Source access policy | No raw K, live market direct, N1 raw facts, broker sources | doc |
| N6APP-033 | Track A Isolation | Track A page isolation | Existing A-track routes | `/n6/action-events`, `/n6/admin/account`, `/n6/admin/users` unchanged | doc |
| N6APP-034 | Track A Isolation | Shared component gate | Gate registry | Shared display requires `N6_SHARED_COMPONENT_ADAPTER_GATE` | doc |
| N6APP-035 | Safety And Forbidden Scope | Side-effect boundary | Runtime/outbox/worker checks | No DB write, outbox update, worker, delivery, push, voice, mobile, sim, position, real trade | doc |
| N6APP-036 | Implementation Readiness | Future tests | Test suite | Route/API/principal/forbidden-wording/non-regression tests required before implementation pass | planned |

## Current Gaps

```text
B-track routes are not implemented.
B-track APIs are not implemented.
Principal-scoped user-front-office UI is not implemented.
Watchlist, proposal review, virtual order/trade operation, portfolio, PnL, AI users, and leaderboard remain separately gated.
Shared component adapter is not defined.
```

