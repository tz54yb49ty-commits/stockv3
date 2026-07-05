# N6 Multi User and AI Spec v1

Status: DESIGN_ONLY

Layer role: N6_user

Date: 2026-06-04

This document starts the future N6 multi-user, virtual-account, AI-user, and
strategy-center design track. It is a design artifact only. It does not modify
N6_UI_v1, existing APIs, existing projection rows, existing shadow pipelines, or
database schema. It does not execute runners, consume outbox rows, start
workers, deliver notifications, push to mobile, run voice, create sim trades,
create positions, or place real trades.

## 0. Scope and Boundary

N6 remains the user-facing layer. N1-N5 continue to produce market facts,
signals, trigger outcomes, and action events. N6 may display, filter, evaluate,
simulate, and audit those outputs for different users, but it must not
recalculate or reinterpret upstream facts.

This v1 design draft defines future modules:

```text
Multi-user Login
Human User
AI User
Virtual Account
Virtual Cash
Virtual Position
Virtual Order
Strategy
Watchlist
User Permission
User Session
Portfolio
AI Decision Engine
AI Evaluation
AI PnL
Leaderboard
Strategy Marketplace
Future Real Trade Boundary
```

Explicit coverage:

```text
multi-user login = Human User + User Session
user_id / account_id isolation = Human User + User Permission + Virtual Account
virtual account / cash / position / order = Virtual Account + Portfolio
watchlist = Watchlist
strategy = Strategy + Strategy Marketplace
AI user / decision / evaluation / PnL = AI User + AI Decision Engine + AI Evaluation + Leaderboard
real trade boundary = Future Real Trade Boundary
```

Required preservation boundary:

```text
N6_UI_v1 unchanged
existing N6 Web auth/API unchanged
existing user_projection_run / user_signal_projection / user_signal_card / user_notification_queue unchanged
existing N6 shadow projection pipeline unchanged
N5 outbox consumption unchanged and not authorized here
```

## 1. Human User

Human users are natural-person accounts that log in, view projections, manage
their own preferences, and optionally participate in future virtual-account or
strategy features. Human users may be `admin` or regular `user`.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-001 | Human users must be represented by a stable `user_id` and authenticated `user_account` row. |
| N6AI-002 | Human users must have isolated filter/profile/watchlist/virtual-account state scoped by `user_id`. |
| N6AI-003 | Regular human users and admin users have the same signal, portfolio-preview, and notification-preview abilities by default. |
| N6AI-004 | Admin-only differences are user-management and future governance controls, not stronger market-signal privileges. |
| N6AI-005 | Human users must not mutate N1-N5 facts, N5 outbox rows, trigger facts, or action facts. |

## 2. AI User

AI users are system-controlled user principals used for analysis, decision
proposal, strategy evaluation, and virtual-account competition. AI users are
not broker accounts and do not own real money.

Allowed AI user inputs:

```text
N2 condition/display summaries
N3 standardized market facts or display projections
N4 trigger signals and reviewed artifacts
N5 canonical action events and reviewed artifacts
N6 user projections/cards/queues
```

Forbidden AI user resources:

```text
real account
real cash/funds
real position
real broker session
real trade route
```

Rules:

| Rule | Requirement |
|---|---|
| N6AI-006 | AI users must be first-class N6 principals with stable `ai_user_id` or `user_id` plus `principal_type=ai`. |
| N6AI-007 | AI users may read N2/N3/N4/N5/N6 signals only through approved summaries, projections, or reviewed artifacts. |
| N6AI-008 | AI users must not access real accounts, real funds, real positions, broker credentials, or broker sessions. |
| N6AI-009 | AI users may create only proposals, explanations, evaluations, or virtual-account intents until a separate gate authorizes more. |
| N6AI-010 | AI user output must be traceable to source projection rows, strategy version, model/version, and evaluation run. |

## 3. Virtual Account

Virtual accounts are N6-only paper accounts. They can model cash, orders,
trades, and positions for users or AI users without touching real brokers.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-011 | Virtual accounts must be scoped to an owner principal and must not reference real broker accounts. |
| N6AI-012 | Virtual cash is synthetic and must be labeled `virtual` or `paper`; it must not be displayed as real cash. |
| N6AI-013 | Virtual orders/trades/positions must be derived from N6 decisions or AI proposals, never from direct N5 execution side effects. |
| N6AI-014 | Virtual-account execution must remain replayable and rollbackable by virtual run/account scope. |
| N6AI-015 | Virtual account defaults, including initial cash, fee model, slippage, and T+1 policy, must be versioned. |

## 4. Strategy

A strategy is a versioned N6 policy that maps N6-visible signals and optional
N2 display context into user-facing filters, proposals, scores, or virtual
actions. A strategy is not a replacement for N5 action confirmation.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-016 | Strategies must be immutable once published; changes create a new `strategy_version_id`. |
| N6AI-017 | Strategy inputs must declare allowed sources, such as N6 projections and N2 display summaries. |
| N6AI-018 | Strategies must not rescore N4 trigger truth or N5 action truth as if they were upstream authorities. |
| N6AI-019 | Strategy outputs must be typed as filter, rank, proposal, notification policy, or virtual-account intent. |
| N6AI-020 | Strategy runs must record owner, version, input projection range, output counts, quality summary, and rollback scope. |

## 5. Watchlist

Watchlists are N6 user-scoped lists of assets. They may be manual, strategy
generated, or system generated. They do not expand N3/N4/N5 scope unless a
future upstream gate explicitly accepts them.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-021 | Watchlists must be scoped by `user_id` and optionally by strategy or AI owner. |
| N6AI-022 | Watchlist items must use `asset_kind + identity_key`; naked code must not be the primary identity. |
| N6AI-023 | Strategy-generated watchlists must retain `strategy_version_id` and generation run id. |
| N6AI-024 | Watchlist changes must not write N2 condition scope, N3 subscription scope, N4 trigger facts, or N5 action facts. |
| N6AI-025 | Watchlist visibility must obey user permission and sharing policy. |

## 6. User Permission

Permissions define who may see, configure, evaluate, or administer N6 user
objects. Permissions must keep user data isolated while allowing admin
governance.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-026 | Every user-owned row must carry `user_id` or an explicit owner principal. |
| N6AI-027 | Cross-user reads must require admin or explicit shared-scope permission. |
| N6AI-028 | AI users must have a permission profile separate from human users. |
| N6AI-029 | Permission scope must be enforced before rendering UI, returning APIs, or running AI/strategy jobs. |
| N6AI-030 | Permission denials must be audited without revealing other users' private data. |

## 7. User Session

Sessions authenticate human users and future AI service principals. Session
security must remain compatible with the current N6 auth boundary.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-031 | Human sessions must continue to store only token hashes, never raw session tokens. |
| N6AI-032 | Password hashes must remain non-reversible and must not be returned by any API. |
| N6AI-033 | AI service sessions or service tokens must be separately scoped, revocable, and non-interactive by default. |
| N6AI-034 | Session expiry, revocation, and audit fields must be visible to admins without exposing secrets. |
| N6AI-035 | Session creation must not create projections, decisions, virtual trades, or delivery rows. |

## 8. Portfolio

The N6 portfolio view is future-facing. It may display virtual-account holdings
and evaluated proposals, but it must not imply real holdings unless a separate
real-trade gate exists.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-036 | Portfolio v1 must label synthetic holdings as virtual or paper. |
| N6AI-037 | Portfolio must not read real broker positions by default. |
| N6AI-038 | Portfolio must separate candidate signals, virtual positions, realized virtual trades, and real-trade placeholders. |
| N6AI-039 | Portfolio target-price interpretation belongs to N6/position policy and must not be written back to N2/N4/N5. |
| N6AI-040 | Portfolio actions that could create virtual orders or decisions require their own execute gate. |

## 9. AI Decision Engine

The AI Decision Engine evaluates signals and strategies and may produce
explainable proposals. It cannot place real trades and cannot mutate upstream
facts.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-041 | AI decisions must be generated from immutable input snapshots and versioned strategy/model settings. |
| N6AI-042 | AI decisions must produce proposal records, not real orders. |
| N6AI-043 | Every AI proposal must include explanation, confidence, source signal ids, strategy version, and model/version. |
| N6AI-044 | AI proposal generation must be idempotent by decision run id and input projection range. |
| N6AI-045 | AI proposals must be reviewable by human users before any future virtual or real side effect. |

## 10. AI Evaluation

AI Evaluation measures AI users and strategies in reproducible dry-run,
backtest, replay, or shadow-forward contexts.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-046 | AI evaluation must use sealed input windows and recorded market outcomes. |
| N6AI-047 | Evaluation metrics must separate signal quality, proposal quality, virtual PnL, drawdown, turnover, and risk. |
| N6AI-048 | Evaluation must not consume live N5 outbox rows or update N5 delivery status. |
| N6AI-049 | Evaluation results must be reproducible by evaluation run id, strategy version, AI version, and source artifact set. |
| N6AI-050 | Evaluation reports must distinguish historical backtest, replay, and live shadow modes. |

## 11. Leaderboard

Leaderboard ranks AI users, strategies, or virtual accounts using audited
evaluation results. It is informational and must not imply real performance or
investment advice.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-051 | Leaderboard entries must be derived from approved AI evaluation or virtual-account runs. |
| N6AI-052 | Leaderboard metrics must show mode, date range, strategy version, and sample size. |
| N6AI-053 | Leaderboard must not mix backtest, replay, and live shadow results without labels. |
| N6AI-054 | Leaderboard must not expose private user holdings, funds, sessions, or raw AI prompts. |
| N6AI-055 | Leaderboard ranking must be reproducible from immutable evaluation artifacts. |

## 12. Strategy Marketplace

Strategy Marketplace is a future N6 module for publishing, reviewing,
selecting, and subscribing to strategies. It is not a broker or trade-execution
marketplace.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-056 | Marketplace strategies must have owner, version, status, allowed input sources, and risk labels. |
| N6AI-057 | Users must opt in before a marketplace strategy can affect their watchlist, filters, AI proposals, or virtual account. |
| N6AI-058 | Marketplace install/update must not mutate existing historical strategy versions. |
| N6AI-059 | Marketplace strategy claims must be backed by evaluation artifacts and mode labels. |
| N6AI-060 | Marketplace must not expose real-trade execution without a separate real-trade gate. |

## 13. Future Real Trade Boundary

Real trading is out of scope for this spec. Any real trading feature requires a
separate layer/gate sequence, schema review, broker adapter review, risk review,
user confirmation, rollback/kill-switch plan, and post-review.

Rules:

| Rule | Requirement |
|---|---|
| N6AI-061 | Real trade is disabled by default for human users, AI users, strategies, virtual accounts, and marketplace entries. |
| N6AI-062 | ActionExecuted must still mean market-action confirmation only, not order placement, fill, or account mutation. |
| N6AI-063 | Any future real-trade path must require explicit user opt-in, admin enablement, risk checks, and separate final execute gate. |
| N6AI-064 | Real-trade credentials, broker sessions, and real positions must be physically and logically separated from N6 virtual-account state. |
| N6AI-065 | Future real-trade rollback must not claim to undo broker-side fills; it may only reconcile, disable, and audit. |

## Current Gaps

This spec intentionally starts future requirements without implementation.

Known gaps:

```text
multi-user schema expansion not drafted
AI user principal schema not drafted
strategy center schema not drafted
AI decision/evaluation runners not designed
leaderboard/materialized metrics not designed
marketplace governance not designed
virtual account execution gates remain separate
delivery gates remain separate
sim gates remain separate
position gates remain separate
real trade remains disabled and out of scope
```

## Review Gate

Allowed next step:

```text
runtime_control or N6_user review gate for N6_MULTI_USER_AND_AI_SPEC_v1
```

Implementation, migration, execution, worker startup, delivery, push, voice,
mobile, sim, position, or real trade remain blocked until separate explicitly
authorized gates.
