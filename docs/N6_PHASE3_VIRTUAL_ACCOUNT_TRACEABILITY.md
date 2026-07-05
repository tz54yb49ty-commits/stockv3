# N6 Phase 3 Virtual Account Traceability

Status: ARCHITECTURE_DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This traceability matrix maps Phase 3 virtual-account architecture rules to
component targets, data sources, test targets, and implementation status.

Coverage:

```text
rule_count=36
rules_mapped=36
coverage=100%
```

Status legend:

```text
architecture_draft: requirement frozen as architecture only
future_gate_required: implementation/schema/execute requires a separate gate
boundary: hard prohibition
evidence_bound: current evidence exists but is not Phase 3 implementation
```

## Rule Matrix

| Rule | Architecture section | Component | Data source / evidence | Test target | Status |
|---|---|---|---|---|---|
| N6VA-001 | 1 Goal | Virtual account system is N6-only | Architecture artifact | no N1-N5 write static test | architecture_draft |
| N6VA-002 | 1 Goal | Current `user_sim_*` remains shadow evidence only | `sql/020_n6_user_projection_schema.sql` | no shadow-to-canonical promotion test | evidence_bound |
| N6VA-003 | 3 Ownership Boundary | Every virtual object has principal ownership | `n6_principal` / 036 schema | principal_id required schema test | future_gate_required |
| N6VA-004 | 3 Ownership Boundary | Admin virtual mode is `admin_shadow_virtual` | Phase 2 admin principal | admin virtual ownership test | future_gate_required |
| N6VA-005 | 3 Ownership Boundary | Human virtual mode is future-gated | future human principal | human ownership gate test | future_gate_required |
| N6VA-006 | 3 Ownership Boundary | AI virtual mode is future-gated | future `n6_ai_user` | AI profile required test | future_gate_required |
| N6VA-007 | 3 Ownership Boundary | System principal owns no virtual account by default | Phase 2 system principal | system no-account default test | architecture_draft |
| N6VA-008 | 4 Virtual Account | `virtual_account_id` required | future `n6_virtual_account` | virtual account PK test | future_gate_required |
| N6VA-009 | 4 Virtual Account | `account_id` bridge required | `n6_principal_account` future bridge | account bridge FK test | future_gate_required |
| N6VA-010 | 4 Virtual Account | No broker credentials/real account field | future schema | forbidden field static test | boundary |
| N6VA-011 | 5 Virtual Cash | Cash ledger has immutable events | future `n6_virtual_cash` | cash event immutability test | future_gate_required |
| N6VA-012 | 5 Virtual Cash | Cash cannot be negative without margin policy | future cash policy | negative cash P0 test | future_gate_required |
| N6VA-013 | 6 Virtual Position | Quantity fields nonnegative and consistent | future `n6_virtual_position` | position quantity quality test | future_gate_required |
| N6VA-014 | 6 Virtual Position | T+1 lock is virtual-only | future position policy | T+1 lock boundary test | future_gate_required |
| N6VA-015 | 6 Virtual Position | No write to real/common position state | `common_position_*` forbidden | no common_position write test | boundary |
| N6VA-016 | 7 Virtual Order | Virtual order is not broker order | future `n6_virtual_order` | no broker adapter call test | boundary |
| N6VA-017 | 7 Virtual Order | Order lifecycle is virtual-only | future order status enum | virtual order lifecycle test | future_gate_required |
| N6VA-018 | 7 Virtual Order | Order source lineage required | N6 signal/decision/AI intent refs | source lineage required test | future_gate_required |
| N6VA-019 | 8 Virtual Trade | Virtual trade is immutable fill event | future `n6_virtual_trade` | trade immutability test | future_gate_required |
| N6VA-020 | 8 Virtual Trade | Fill policy deterministic for replay | future fill policy artifact | replay determinism test | future_gate_required |
| N6VA-021 | 8 Virtual Trade | Virtual trade never means real成交 | UI/API label boundary | wording boundary test | boundary |
| N6VA-022 | 9 Virtual PnL | PnL snapshot is virtual only | future `n6_virtual_pnl` | PnL disclaimer test | boundary |
| N6VA-023 | 9 Virtual PnL | `total_equity = cash + market_value` | future PnL quality | PnL math test | future_gate_required |
| N6VA-024 | 9 Virtual PnL | Leaderboard reads approved PnL only | future leaderboard gate | leaderboard source allowlist test | future_gate_required |
| N6VA-025 | 10 Run / Policy / Rollback | Every module carries `run_id` | future all Phase 3 tables | run_id required test | future_gate_required |
| N6VA-026 | 10 Run / Policy / Rollback | Every module carries policy version/hash | future policy fields | policy hash required test | future_gate_required |
| N6VA-027 | 10 Run / Policy / Rollback | Rollback scope by run/account/principal | rollback SQL future gates | rollback scope test | future_gate_required |
| N6VA-028 | 10 Run / Policy / Rollback | Rollback hard-fails on downstream refs | future rollback SQL | hard-fail before DELETE test | future_gate_required |
| N6VA-029 | 10 Run / Policy / Rollback | Rollback does not touch N1-N5/outbox | future rollback SQL | forbidden table static scan | boundary |
| N6VA-030 | 11 Quality Gate | P0 blockers defined | quality policy artifact | P0 quality gate test | architecture_draft |
| N6VA-031 | 11 Quality Gate | P1/P2 warnings defined | quality policy artifact | warning classification test | architecture_draft |
| N6VA-032 | 12 AI Account Compatibility | AI virtual requires AI principal/profile | future `n6_ai_user` | AI account profile test | future_gate_required |
| N6VA-033 | 12 AI Account Compatibility | AI virtual requires `virtual_intent` lifecycle | future AI decision artifact | virtual_intent lifecycle test | future_gate_required |
| N6VA-034 | 12 AI Account Compatibility | AI cannot access real account/funds/position | AI readable boundary | AI forbidden-source test | boundary |
| N6VA-035 | 13 Data Source Boundary | Allowed sources are N6/approved artifacts | N6 projection/reviewed artifacts | source allowlist test | architecture_draft |
| N6VA-036 | 14 Independent Future Gates | Each virtual module needs separate gate | runtime_control review | gate isolation test | boundary |

## Required Coverage Topics

| Topic | Covered by rules |
|---|---|
| `virtual_account` | N6VA-008..010 |
| `virtual_cash` | N6VA-011..012 |
| `virtual_position` | N6VA-013..015 |
| `virtual_order` | N6VA-016..018 |
| `virtual_trade` | N6VA-019..021 |
| `virtual_pnl` | N6VA-022..024 |
| `run_id` | N6VA-025 |
| `policy_version` | N6VA-026 |
| `rollback_scope` | N6VA-027..029 |
| `quality_gate` | N6VA-030..031 |
| `principal ownership` | N6VA-003..007 |
| `AI account compatibility` | N6VA-032..034 |

## Current Gaps

```text
no Phase 3 SQL schema
no Phase 3 migration
no Phase 3 runner
no virtual account/cash/position/order/trade/pnl rows
no AI virtual intent implementation
no leaderboard approved-PnL reader
no UI/API adapter
```

## Next Gate

Allowed next step:

```text
runtime_control N6 Phase 3 virtual account architecture review gate
```
