# N6 Multi User and AI Architecture v1

Status: ARCHITECTURE_FREEZE_PASS

Layer role: N6_user

Date: 2026-06-04

Source spec:

```text
docs/N6_MULTI_USER_AND_AI_SPEC_v1.md
docs/N6_MULTI_USER_AND_AI_SPEC_v1_TRACEABILITY.md
```

Review basis:

```text
runtime_control APPROVED_WITH_CHANGES conclusion as provided in the
N6_MULTI_USER_AND_AI_ARCHITECTURE_FREEZE_GATE prompt.
```

This architecture freeze is a documentation artifact only. It does not modify
N6_UI_v1, existing APIs, existing projection rows, existing shadow pipelines, or
database schema. It does not execute runners, consume outbox rows, start
workers, deliver notifications, push to mobile, run voice, create sim trades,
create positions, or place real trades.

## 1. Architecture Goal

Track B defines future multi-user, virtual-account, AI-user, strategy,
evaluation, leaderboard, and marketplace architecture without touching Track A
N6_UI_v1. The architecture gives future gates a canonical ownership model,
readable-source boundary, run/policy/rollback/quality model, visibility model,
and explicit side-effect isolation.

The architecture does not upgrade `DESIGN_ONLY` source rules into
`IMPLEMENTATION_PASS`. Any rule marked `existing` in the source traceability is
bound only to current evidence such as a table, test, or reviewed artifact.
Future modules remain unimplemented until their own gates pass.

## 2. Canonical Ownership Model

Canonical identifiers:

| Identifier | Meaning | Current / Future status |
|---|---|---|
| `user_id` | Human user account owner in N6 | current N6 schema |
| `account_id` | Canonical account owner identifier for future human/AI account views | future alias or bridge; not current DB requirement |
| `ai_user_id` | AI principal identity | future schema |
| `principal_type` | Principal kind: `human_user`, `ai_user`, `admin`, `system` | future schema/policy |
| `virtual_account_id` | N6-only virtual account identity | future canonical wrapper; current shadow table has `user_sim_account_id` |

Ownership rules:

| Object | Owner | Ownership requirement |
|---|---|---|
| human user | `user_id` | owns preferences, watchlists, sessions, and virtual accounts |
| virtual account | human principal | `human_user owns virtual_account` |
| AI user | `ai_user_id` or principal row | owns AI runs, proposals, and AI virtual accounts |
| AI virtual account | AI principal | `ai_user owns ai_virtual_account` |
| strategy | owner principal | belongs to human/admin/AI/system owner principal |
| watchlist | owner principal | belongs to human/admin/AI/system owner principal |
| signal projection | principal scope | belongs to a user/principal visibility scope, sourced from N6 projection rows |
| leaderboard | read-only aggregate | only reads approved virtual performance/evaluation artifacts |

Normative ownership constraints:

```text
all owner-scoped rows carry user_id, ai_user_id, or owner_principal_id
asset identity is asset_kind + identity_key
strategy and watchlist ownership never expands N2/N3/N4/N5 scope by itself
leaderboard does not own trades or accounts; it reads approved virtual results
```

## 3. AI Readable Boundary

AI may read only approved, layer-safe summaries or artifacts:

```text
approved N2 summaries
approved N3 projection summaries
reviewed N4 trigger artifacts
reviewed N5 action artifacts
N6 shadow projection
```

AI must not read:

```text
raw K
live market data direct connection
N1 raw facts
real account
real funds
real position
broker session
real trade API
```

AI source policy:

```text
AI input is snapshot-based.
AI input must record source artifact paths or projection row ranges.
AI must not poll live providers directly.
AI must not consume or update N5 outbox status.
AI must not call broker adapters.
```

## 4. Run / Policy / Rollback / Quality Model

Every future Track B materialized module must have these fields or equivalent
artifact fields before execute can be allowed:

```text
run_id
policy_version
policy_hash
rollback_scope
quality gate
source lineage
immutable event/fact distinction
```

Module requirements:

| Module | run_id | policy version/hash | rollback scope | quality gate | source lineage | event/fact distinction |
|---|---|---|---|---|---|---|
| virtual_account | `virtual_account_run_id` | account policy, fee, slippage, T+1 | account/run scoped | cash/position consistency | owner principal, source decisions | account state fact; account events immutable |
| virtual_order | `virtual_order_run_id` | order policy and fill model | order run scoped | order status and quantity checks | source signal/proposal/decision | order fact plus immutable order event |
| virtual_position | `virtual_position_run_id` | position policy and mark policy | position run scoped | position quantity/cost consistency | source virtual trades | position fact plus immutable adjustment event |
| ai_decision | `ai_decision_run_id` | strategy/model prompt policy | decision run scoped | proposal completeness and forbidden-source check | N6 projection range, approved artifacts | proposal fact plus immutable decision event |
| ai_evaluation | `ai_evaluation_run_id` | evaluation policy and metric policy | evaluation run scoped | sealed input and metric quality | source decision/proposal/market outcome artifacts | evaluation fact plus immutable evaluation event |
| leaderboard | `leaderboard_run_id` | ranking policy and display policy | leaderboard run scoped | approved source and privacy redaction | approved evaluation/virtual performance | leaderboard snapshot fact; no trade event |

Rollback must be hard-fail before delete if downstream decision, sim, voice,
mobile, position, real-trade, or external-delivery references exist.

## 5. Existing Status Evidence Binding

The source traceability file contains rules with `status=existing`. This
architecture binds those statuses to current evidence. `existing` means
"evidence exists for this narrow current object", not "future Track B module is
implemented".

| Source rule | Existing evidence | Evidence type | Interpretation |
|---|---|---|---|
| N6AI-001 | `user_account` in `sql/020_n6_user_projection_schema.sql`; auth tests in `tests/test_n6_user_app.py` | current table/test | human user account exists |
| N6AI-004 | `user_account.role`; admin tests in `tests/test_n6_user_app.py` | current table/test | admin governance exists only for current user management |
| N6AI-011 | `user_sim_account` in `sql/020_n6_user_projection_schema.sql` | current shadow table | virtual account table exists as shadow schema, not full future architecture |
| N6AI-021 | `user_watchlist` in `sql/020_n6_user_projection_schema.sql` | current table | watchlist ownership table exists, feature still future-gated |
| N6AI-022 | `user_watchlist_item.asset_kind`, `identity_key` | current table | identity-key shape exists |
| N6AI-031 | `user_session.session_token_hash`; session tests | current table/test | session hash safety exists |
| N6AI-032 | `user_account.password_hash`; auth tests | current table/test | password hash redaction exists |
| N6AI-035 | session tests in `tests/test_n6_user_app.py` | current test | login/session does not create projection/decision/sim rows |
| N6AI-062 | N6 UI v1 wording tests and artifact | current test/artifact | ActionExecuted wording boundary exists in UI v1 |

Reviewed report/artifact anchors:

```text
docs/N6_USER_INTERFACE_SPEC_v1_IMPLEMENTATION_READINESS.json
docs/N6_USER_INTERFACE_SPEC_v1_IMPLEMENTATION_READINESS.md
docs/N6_MULTI_USER_AND_AI_SPEC_v1.md
docs/N6_MULTI_USER_AND_AI_SPEC_v1_TRACEABILITY.md
```

## 6. Independent Gates

Each module below must open a separate gate before schema, implementation,
execute, or side effects:

```text
virtual account schema
virtual order
virtual position
AI decision engine
AI evaluation
leaderboard
strategy marketplace
notification/delivery
sim
real trade
```

Gate rule:

```text
no shared execute gate may silently enable two modules
no module may use Track A N6_UI_v1 implementation as implicit approval
no module may update N5 outbox or N1-N5 facts
```

## 7. AI Proposal Lifecycle

Canonical lifecycle:

```text
draft -> reviewed -> accepted | rejected -> virtual_intent
```

Lifecycle requirements:

| State | Meaning | Allowed transition |
|---|---|---|
| `draft` | AI-generated proposal, not reviewed | to `reviewed` or `rejected` |
| `reviewed` | human/admin reviewed proposal | to `accepted` or `rejected` |
| `accepted` | accepted for virtual workflow only | to `virtual_intent` |
| `rejected` | closed proposal | terminal |
| `virtual_intent` | virtual-account intent only | may enter virtual-account gate |

Hard boundary:

```text
virtual_intent can enter only virtual account flow
virtual_intent must not enter real trade
accepted AI proposal is not an order
reviewed AI proposal is not a broker instruction
```

## 8. Leaderboard Disclaimer

Leaderboard display must always include:

```text
not real return
not investment advice
not representative of future return
AI ranking is based only on virtual-account or approved evaluation results
```

Leaderboard must label mode:

```text
backtest
replay
shadow_forward
virtual_live
```

## 9. Strategy Marketplace Risk Labels

Minimum risk labels:

```text
high_volatility
drawdown_risk
insufficient_history
experimental
ai_generated
```

Marketplace rules:

```text
strategy claims require evaluation artifacts
strategy install requires explicit user opt-in
strategy update creates a new immutable strategy version
marketplace cannot expose real-trade execution without a separate gate
```

## 10. Visibility Model

Canonical visibility values:

| Visibility | Meaning |
|---|---|
| `private` | visible only to owner principal |
| `shared` | visible to explicitly granted principals |
| `admin` | visible to admin/governance roles |
| `public_leaderboard` | visible only as approved aggregate leaderboard output |

Visibility constraints:

```text
private is the default
shared requires explicit grant
admin visibility must not expose secrets
public_leaderboard must not expose private holdings, funds, sessions, prompts, or raw traces
```

## 11. A-Track / B-Track Isolation

Track A:

```text
N6_UI_v1
current read-only UI/API/component work
existing projection/card/queue display
```

Track B:

```text
N6_MULTI_USER_AND_AI future design
multi-user architecture
AI user / strategy / virtual-account / leaderboard / marketplace design
```

Track B hard isolation:

```text
B track must not modify N6_UI_v1
B track must not modify existing API
B track must not modify existing projection
B track must not modify shadow pipeline
future adapter must have a separate gate
```

Adapter rule:

```text
future Track B adapter to Track A UI or existing projection must be proposed,
reviewed, tested, and approved in a separate compatibility gate.
```

## 12. Remaining Gaps

Architecture gaps remaining after this freeze:

```text
no Track B schema draft yet
no AI principal schema yet
no strategy version schema yet
no virtual-account run schema yet
no AI decision/evaluation runner yet
no leaderboard materializer yet
no marketplace governance implementation yet
no future adapter to N6_UI_v1 yet
real trade remains disabled and out of scope
```

## 13. Next Allowed Step

Allowed next gate:

```text
runtime_control N6 multi-user and AI architecture freeze review
```

Still forbidden:

```text
business code changes
database writes
migration
execute
outbox consumption/update
worker startup
N6_UI_v1 modification
existing API modification
existing projection/shadow pipeline modification
delivery / push / voice / mobile / sim / position / real trade
```
