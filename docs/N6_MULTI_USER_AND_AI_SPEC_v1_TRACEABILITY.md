# N6 Multi User and AI Spec v1 Traceability

Status: DESIGN_ONLY

Layer role: N6_user

Date: 2026-06-04

This traceability matrix maps every design-only multi-user / AI / virtual-account /
strategy-center rule to its spec section, component target, data source, test
target, and current status.

Coverage:

```text
rules_total=65
mapped_rules=65
coverage=100%
```

Status legend:

```text
existing: current N6 data/auth/projection object already exists
planned: future implementation required
gap: known missing schema/API/runner/UI evidence
doc: normative boundary only
```

| Rule | Spec section | Component | Data source | Test target | Status |
|---|---|---|---|---|---|
| N6AI-001 | 1 Human User | Human user account | `user_account` | user account identity test | existing |
| N6AI-002 | 1 Human User | User isolation | `user_filter_profile`, `user_watchlist`, future virtual account | per-user isolation test | planned |
| N6AI-003 | 1 Human User | Human user UX policy | N6 UI/user API policy | regular user/admin core feature parity test | planned |
| N6AI-004 | 1 Human User | Admin governance | `user_account.role` | admin-only management test | existing |
| N6AI-005 | 1 Human User | Cross-layer boundary | N1-N5 facts/outbox | no upstream writes static test | doc |
| N6AI-006 | 2 AI User | AI principal | future AI principal/user extension | AI principal schema test | gap |
| N6AI-007 | 2 AI User | AI input repository | N2/N3/N4/N5/N6 approved summaries/artifacts | AI source allowlist test | planned |
| N6AI-008 | 2 AI User | AI permission boundary | real account/funds/position forbidden sources | AI forbidden resource denial test | doc |
| N6AI-009 | 2 AI User | AI proposal output | future AI proposal table/artifact | AI writes proposal only test | gap |
| N6AI-010 | 2 AI User | AI traceability | strategy/model/source projection ids | AI proposal traceability test | gap |
| N6AI-011 | 3 Virtual Account | Virtual account owner | `user_sim_account` or future virtual account table | virtual owner scope test | existing |
| N6AI-012 | 3 Virtual Account | Virtual cash labeling | virtual-account display payload | virtual cash label test | planned |
| N6AI-013 | 3 Virtual Account | Virtual execution source | N6 decisions / AI proposals | no direct N5 side-effect source test | planned |
| N6AI-014 | 3 Virtual Account | Virtual replay/rollback | virtual run/account scope | virtual rollback scope test | gap |
| N6AI-015 | 3 Virtual Account | Virtual policy version | fee/slippage/T+1 policy artifact | virtual policy version test | gap |
| N6AI-016 | 4 Strategy | Strategy versioning | future strategy table/artifact | immutable strategy version test | gap |
| N6AI-017 | 4 Strategy | Strategy input contract | N6 projections / N2 display summaries | strategy input allowlist test | gap |
| N6AI-018 | 4 Strategy | Upstream truth boundary | N4/N5 reviewed facts/artifacts | no N4/N5 reinterpretation test | doc |
| N6AI-019 | 4 Strategy | Strategy output typing | future strategy run output | strategy output type test | gap |
| N6AI-020 | 4 Strategy | Strategy run audit | future strategy run artifact | strategy run audit fields test | gap |
| N6AI-021 | 5 Watchlist | Watchlist ownership | `user_watchlist` | watchlist user scope test | existing |
| N6AI-022 | 5 Watchlist | Watchlist identity | `user_watchlist_item.asset_kind`, `identity_key` | no naked code identity test | existing |
| N6AI-023 | 5 Watchlist | Strategy watchlist lineage | future strategy watchlist payload | strategy-generated watchlist trace test | gap |
| N6AI-024 | 5 Watchlist | Watchlist boundary | N2/N3/N4/N5 forbidden writes | watchlist does not expand upstream scope test | doc |
| N6AI-025 | 5 Watchlist | Watchlist visibility | permission/share policy | watchlist visibility test | planned |
| N6AI-026 | 6 User Permission | Owned rows | N6 user-owned tables | owned row user_id coverage test | planned |
| N6AI-027 | 6 User Permission | Cross-user reads | permission scope / admin role | cross-user permission denial test | planned |
| N6AI-028 | 6 User Permission | AI permission profile | future AI permission profile | AI permission isolation test | gap |
| N6AI-029 | 6 User Permission | Permission enforcement | UI/API/runner access layer | permission-before-render/run test | planned |
| N6AI-030 | 6 User Permission | Permission audit | future permission audit artifact | denial audit redaction test | gap |
| N6AI-031 | 7 User Session | Session token safety | `user_session.session_token_hash` | raw token not stored test | existing |
| N6AI-032 | 7 User Session | Password safety | `user_account.password_hash` | password hash redaction test | existing |
| N6AI-033 | 7 User Session | AI service token | future service token table/artifact | AI token revocation test | gap |
| N6AI-034 | 7 User Session | Session audit | `user_session` audit fields | admin session audit redaction test | planned |
| N6AI-035 | 7 User Session | Session side-effect boundary | session create/revoke routes | session does not create projection/decision/sim rows test | existing |
| N6AI-036 | 8 Portfolio | Portfolio virtual label | virtual-account display | portfolio virtual label test | planned |
| N6AI-037 | 8 Portfolio | Real position boundary | broker/real position forbidden sources | no real position read test | doc |
| N6AI-038 | 8 Portfolio | Portfolio sections | candidate / virtual position / virtual trade / placeholder | portfolio section separation test | planned |
| N6AI-039 | 8 Portfolio | Target-price interpretation | N6 position policy, N2 target candidates | no N2/N4/N5 target writeback test | doc |
| N6AI-040 | 8 Portfolio | Portfolio execute gate | virtual order/decision runner | portfolio side-effect gate test | gap |
| N6AI-041 | 9 AI Decision Engine | AI immutable input | N6 projection snapshots / strategy/model settings | AI input snapshot immutability test | gap |
| N6AI-042 | 9 AI Decision Engine | AI proposal-only output | future AI proposal table/artifact | no real order from AI test | gap |
| N6AI-043 | 9 AI Decision Engine | AI explainability | proposal explanation/source ids/model version | AI proposal explanation fields test | gap |
| N6AI-044 | 9 AI Decision Engine | AI idempotency | decision run id / input range | AI idempotency test | gap |
| N6AI-045 | 9 AI Decision Engine | Human review gate | proposal review workflow | human review required test | planned |
| N6AI-046 | 10 AI Evaluation | Evaluation input window | sealed inputs / market outcomes | sealed evaluation input test | gap |
| N6AI-047 | 10 AI Evaluation | Evaluation metrics | evaluation artifact | metric family coverage test | gap |
| N6AI-048 | 10 AI Evaluation | Evaluation boundary | N5 outbox/status forbidden writes | no outbox consumption/update test | doc |
| N6AI-049 | 10 AI Evaluation | Evaluation reproducibility | eval run id / strategy / AI / artifacts | evaluation reproducibility test | gap |
| N6AI-050 | 10 AI Evaluation | Evaluation mode labeling | evaluation report | backtest/replay/shadow mode label test | gap |
| N6AI-051 | 11 Leaderboard | Leaderboard source | approved evaluation / virtual-account runs | leaderboard approved source test | gap |
| N6AI-052 | 11 Leaderboard | Leaderboard metric context | mode/date/version/sample metadata | leaderboard metadata test | gap |
| N6AI-053 | 11 Leaderboard | Leaderboard mode separation | leaderboard rows | no unlabeled mixed-mode ranking test | gap |
| N6AI-054 | 11 Leaderboard | Leaderboard privacy | user holdings/funds/session/prompt forbidden fields | leaderboard privacy redaction test | gap |
| N6AI-055 | 11 Leaderboard | Leaderboard reproducibility | immutable evaluation artifacts | leaderboard reproducibility test | gap |
| N6AI-056 | 12 Strategy Marketplace | Marketplace listing | future marketplace strategy metadata | marketplace required fields test | gap |
| N6AI-057 | 12 Strategy Marketplace | Marketplace opt-in | user strategy subscription | user opt-in enforcement test | gap |
| N6AI-058 | 12 Strategy Marketplace | Marketplace version immutability | strategy version records | no historical mutation test | gap |
| N6AI-059 | 12 Strategy Marketplace | Marketplace claims | evaluation artifacts/mode labels | claim evidence test | gap |
| N6AI-060 | 12 Strategy Marketplace | Marketplace real-trade boundary | real-trade disabled policy | no real-trade marketplace action test | doc |
| N6AI-061 | 13 Future Real Trade Boundary | Real trade global default | global policy/config | real trade disabled default test | doc |
| N6AI-062 | 13 Future Real Trade Boundary | ActionExecuted wording boundary | N5/N6 action state UI/policy | ActionExecuted not trade wording test | existing |
| N6AI-063 | 13 Future Real Trade Boundary | Real trade gate | future real-trade gate artifacts | explicit opt-in/admin/risk/final gate test | gap |
| N6AI-064 | 13 Future Real Trade Boundary | Broker separation | future broker credential/position storage | physical/logical separation test | gap |
| N6AI-065 | 13 Future Real Trade Boundary | Real trade rollback boundary | future real-trade reconciliation report | no broker-fill undo claim test | doc |

## Current Gaps

Schema gaps:

```text
AI principal / AI permission profile schema
strategy center / strategy version schema
AI proposal and evaluation schema
leaderboard materialization schema
marketplace subscription schema
virtual-account run/version policy schema
real-trade credential and broker separation schema, if ever authorized
```

API/UI gaps:

```text
multi-user admin governance API beyond current MVP
AI user management API
strategy center API
watchlist sharing API
portfolio virtual-account API with gated writes
AI decision/evaluation API
leaderboard and marketplace UI
real-trade UI remains disabled
```

Runner gaps:

```text
AI decision dry-run/execute runner
AI evaluation runner
strategy run materializer
leaderboard materializer
virtual-account execution runner
real-trade runner explicitly out of scope
```

## Review Gate

Allowed next step:

```text
N6_MULTI_USER_AND_AI_SPEC_v1 review gate
```

Implementation may start only after this track separately receives
`SPEC_FREEZE_PASS` and runtime_control `APPROVED`.

Implementation, migration, execution, worker startup, delivery, push, voice,
mobile, sim, position, or real trade remain blocked until separate explicitly
authorized gates.
