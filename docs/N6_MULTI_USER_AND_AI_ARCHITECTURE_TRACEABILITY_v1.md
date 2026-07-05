# N6 Multi User and AI Architecture Traceability v1

Status: ARCHITECTURE_FREEZE_PASS

Layer role: N6_user

Date: 2026-06-04

This traceability matrix maps the architecture freeze requirements to approved
runtime_control changes, source spec rules, evidence, and future test targets.

Coverage:

```text
architecture_rules_total=45
architecture_rules_mapped=45
architecture_coverage=100%
source_spec_rules_total=65
source_spec_rules_referenced=65
source_spec_coverage=100%
approved_changes_total=10
approved_changes_covered=10
approved_changes_coverage=100%
```

Status legend:

```text
architecture_frozen: requirement is frozen in architecture only
evidence_bound: current existing evidence is explicitly bound
future_gate_required: implementation/migration/execute requires a later gate
boundary: normative prohibition or isolation boundary
```

## Architecture Rule Matrix

| Rule | Approved change | Architecture section | Source spec rules | Evidence / data source | Test target | Status |
|---|---|---|---|---|---|---|
| N6ARCH-001 | canonical ownership model | 2 Canonical Ownership Model | N6AI-001, N6AI-026 | `user_id` / owner principal model | owner identifier coverage test | architecture_frozen |
| N6ARCH-002 | canonical ownership model | 2 Canonical Ownership Model | N6AI-006, N6AI-028 | future `ai_user_id`, `principal_type` | AI principal schema test | future_gate_required |
| N6ARCH-003 | canonical ownership model | 2 Canonical Ownership Model | N6AI-011, N6AI-015 | future `virtual_account_id`; current `user_sim_account` evidence | virtual account ownership test | future_gate_required |
| N6ARCH-004 | canonical ownership model | 2 Canonical Ownership Model | N6AI-016, N6AI-020 | owner principal strategy model | strategy owner/version test | future_gate_required |
| N6ARCH-005 | canonical ownership model | 2 Canonical Ownership Model | N6AI-021, N6AI-055 | watchlist owner and leaderboard approved read source | watchlist/leaderboard source test | architecture_frozen |
| N6ARCH-006 | AI readable boundary | 3 AI Readable Boundary | N6AI-007 | approved N2 summaries | AI N2 source allowlist test | architecture_frozen |
| N6ARCH-007 | AI readable boundary | 3 AI Readable Boundary | N6AI-007 | approved N3 projection summaries | AI N3 source allowlist test | architecture_frozen |
| N6ARCH-008 | AI readable boundary | 3 AI Readable Boundary | N6AI-007, N6AI-018 | reviewed N4 trigger artifacts | AI N4 artifact allowlist test | architecture_frozen |
| N6ARCH-009 | AI readable boundary | 3 AI Readable Boundary | N6AI-007, N6AI-018 | reviewed N5 action artifacts | AI N5 artifact allowlist test | architecture_frozen |
| N6ARCH-010 | AI readable boundary | 3 AI Readable Boundary | N6AI-007 | N6 shadow projection | AI N6 projection allowlist test | architecture_frozen |
| N6ARCH-011 | AI readable boundary | 3 AI Readable Boundary | N6AI-008, N6AI-037 | raw K/live/N1 raw/real account/funds/position forbidden | AI forbidden source denial test | boundary |
| N6ARCH-012 | AI readable boundary | 3 AI Readable Boundary | N6AI-008, N6AI-061 | broker session and real trade API forbidden | AI broker/real trade denial test | boundary |
| N6ARCH-013 | run/policy/rollback/quality | 4 Run / Policy / Rollback / Quality Model | N6AI-011..N6AI-015 | virtual account run model | virtual account run/policy test | future_gate_required |
| N6ARCH-014 | run/policy/rollback/quality | 4 Run / Policy / Rollback / Quality Model | N6AI-013, N6AI-014 | virtual order run model | virtual order rollback/quality test | future_gate_required |
| N6ARCH-015 | run/policy/rollback/quality | 4 Run / Policy / Rollback / Quality Model | N6AI-014, N6AI-039 | virtual position run model | virtual position fact/event test | future_gate_required |
| N6ARCH-016 | run/policy/rollback/quality | 4 Run / Policy / Rollback / Quality Model | N6AI-041..N6AI-045 | AI decision run model | AI decision run/policy test | future_gate_required |
| N6ARCH-017 | run/policy/rollback/quality | 4 Run / Policy / Rollback / Quality Model | N6AI-046..N6AI-050 | AI evaluation run model | AI evaluation sealed-input test | future_gate_required |
| N6ARCH-018 | run/policy/rollback/quality | 4 Run / Policy / Rollback / Quality Model | N6AI-051..N6AI-055 | leaderboard run model | leaderboard approved-source test | future_gate_required |
| N6ARCH-019 | existing evidence binding | 5 Existing Status Evidence Binding | N6AI-001 | `user_account`, tests/test_n6_user_app.py | existing user account evidence test | evidence_bound |
| N6ARCH-020 | existing evidence binding | 5 Existing Status Evidence Binding | N6AI-004 | `user_account.role`, admin tests | existing admin role evidence test | evidence_bound |
| N6ARCH-021 | existing evidence binding | 5 Existing Status Evidence Binding | N6AI-011 | `user_sim_account` | shadow virtual account evidence test | evidence_bound |
| N6ARCH-022 | existing evidence binding | 5 Existing Status Evidence Binding | N6AI-021 | `user_watchlist` | watchlist table evidence test | evidence_bound |
| N6ARCH-023 | existing evidence binding | 5 Existing Status Evidence Binding | N6AI-022 | `user_watchlist_item.asset_kind`, `identity_key` | identity-key evidence test | evidence_bound |
| N6ARCH-024 | existing evidence binding | 5 Existing Status Evidence Binding | N6AI-031 | `user_session.session_token_hash` | session hash evidence test | evidence_bound |
| N6ARCH-025 | existing evidence binding | 5 Existing Status Evidence Binding | N6AI-032 | `user_account.password_hash` | password hash redaction evidence test | evidence_bound |
| N6ARCH-026 | existing evidence binding | 5 Existing Status Evidence Binding | N6AI-035 | session side-effect tests | session no-projection/no-sim evidence test | evidence_bound |
| N6ARCH-027 | existing evidence binding | 5 Existing Status Evidence Binding | N6AI-062 | N6 UI v1 wording tests/artifacts | ActionExecuted wording evidence test | evidence_bound |
| N6ARCH-028 | independent gates | 6 Independent Gates | N6AI-011..N6AI-015 | virtual account schema gate | virtual account schema final gate test | future_gate_required |
| N6ARCH-029 | independent gates | 6 Independent Gates | N6AI-013, N6AI-040 | virtual order gate | virtual order gate test | future_gate_required |
| N6ARCH-030 | independent gates | 6 Independent Gates | N6AI-014, N6AI-036..N6AI-040 | virtual position gate | virtual position gate test | future_gate_required |
| N6ARCH-031 | independent gates | 6 Independent Gates | N6AI-041..N6AI-045 | AI decision engine gate | AI decision gate test | future_gate_required |
| N6ARCH-032 | independent gates | 6 Independent Gates | N6AI-046..N6AI-050 | AI evaluation gate | AI evaluation gate test | future_gate_required |
| N6ARCH-033 | independent gates | 6 Independent Gates | N6AI-051..N6AI-055 | leaderboard gate | leaderboard gate test | future_gate_required |
| N6ARCH-034 | independent gates | 6 Independent Gates | N6AI-056..N6AI-060 | strategy marketplace gate | marketplace gate test | future_gate_required |
| N6ARCH-035 | independent gates | 6 Independent Gates | N6AI-048, N6AI-060 | notification/delivery gate | delivery side-effect gate test | future_gate_required |
| N6ARCH-036 | independent gates | 6 Independent Gates | N6AI-013..N6AI-015 | sim gate | sim gate isolation test | future_gate_required |
| N6ARCH-037 | independent gates | 6 Independent Gates | N6AI-061..N6AI-065 | real trade gate | real trade disabled/gated test | boundary |
| N6ARCH-038 | AI proposal lifecycle | 7 AI Proposal Lifecycle | N6AI-009, N6AI-041..N6AI-045 | draft/reviewed/accepted/rejected/virtual_intent | AI lifecycle transition test | architecture_frozen |
| N6ARCH-039 | AI proposal lifecycle | 7 AI Proposal Lifecycle | N6AI-042, N6AI-063 | virtual_intent only enters virtual account | no real-trade from proposal test | boundary |
| N6ARCH-040 | leaderboard disclaimer | 8 Leaderboard Disclaimer | N6AI-051..N6AI-055 | not real return / not advice / not future return | leaderboard disclaimer test | architecture_frozen |
| N6ARCH-041 | marketplace risk labels | 9 Strategy Marketplace Risk Labels | N6AI-056..N6AI-060 | high_volatility/drawdown/insufficient_history/experimental/ai_generated | marketplace risk label test | architecture_frozen |
| N6ARCH-042 | visibility model | 10 Visibility Model | N6AI-025, N6AI-027, N6AI-030, N6AI-054 | private/shared/admin/public_leaderboard | visibility/privacy test | architecture_frozen |
| N6ARCH-043 | A/B track isolation | 11 A-Track / B-Track Isolation | N6AI-005, N6AI-024, N6AI-048 | B track must not modify N6_UI_v1/API/projection/shadow | track isolation static test | boundary |
| N6ARCH-044 | A/B track isolation | 11 A-Track / B-Track Isolation | N6AI-057, N6AI-060 | future adapter requires separate gate | adapter gate test | boundary |
| N6ARCH-045 | design-only safeguard | 1, 5, 13 | N6AI-001..N6AI-065 | current architecture artifacts | no DESIGN_ONLY as IMPLEMENTATION_PASS test | boundary |

## Approved Changes Coverage

| Approved change | Covered by architecture rules | Status |
|---|---|---|
| Canonical ownership model | N6ARCH-001..N6ARCH-005 | covered |
| AI readable boundary | N6ARCH-006..N6ARCH-012 | covered |
| Run / policy / rollback / quality model | N6ARCH-013..N6ARCH-018 | covered |
| Existing status evidence binding | N6ARCH-019..N6ARCH-027 | covered |
| Independent gates | N6ARCH-028..N6ARCH-037 | covered |
| AI proposal lifecycle | N6ARCH-038..N6ARCH-039 | covered |
| Leaderboard disclaimer | N6ARCH-040 | covered |
| Strategy marketplace risk labels | N6ARCH-041 | covered |
| Visibility model | N6ARCH-042 | covered |
| A/B track isolation | N6ARCH-043..N6ARCH-044 | covered |

## Source Spec Rule Coverage

The source spec uses `N6AI-001..N6AI-065`. All 65 source rules are referenced
by this architecture traceability matrix through either explicit rule rows,
rule ranges, or evidence-binding rows.

```text
source_spec_rule_ids=N6AI-001..N6AI-065
missing_source_rules=0
duplicate_architecture_rules=0
```

## Remaining Gaps

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

## Next Gate

Allowed next step:

```text
runtime_control N6 multi-user and AI architecture freeze review
```

Implementation, migration, execution, worker startup, delivery, push, voice,
mobile, sim, position, or real trade remain blocked until separate explicitly
authorized gates.
