# N6 Phase 3 Virtual Account Seed / Operation Traceability

Status: TRACEABILITY_PASS

Layer role: N6_user

Date: 2026-06-05

Traceability covers every rule in
`docs/N6_PHASE3_VIRTUAL_ACCOUNT_SEED_OPERATION_DESIGN.md`.

## Summary

```text
rule_count=24
coverage=100%
duplicate_rule_ids=0
missing_rule_ids=0
```

## Rules

| Rule ID | Spec section | Component | Data source | Test target | Status |
|---|---|---|---|---|---|
| N6VA-SEED-001 | Inputs | Schema foundation | `docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_FOUNDATION_CLOSEOUT.*` | Future seed preflight must verify 038A-E tables exist | existing |
| N6VA-SEED-002 | Inputs | Principal foundation | Phase 2 principal seed artifacts | Future seed preflight must verify admin principal exists | existing |
| N6VA-SEED-003 | Seed Recommendation | Admin virtual account | `n6_principal` admin row | Future contract planned rows include exactly one admin virtual account | planned |
| N6VA-SEED-004 | Seed Recommendation | Human demo account | Phase 2 principal seed | Future contract planned demo rows equal zero | planned |
| N6VA-SEED-005 | Seed Recommendation | AI virtual account | AI principal/profile gates | Future contract planned AI rows equal zero | planned |
| N6VA-SEED-006 | Seed Recommendation | System principal boundary | `n6_principal.principal_type='system'` | Future preflight blocks system virtual account | planned |
| N6VA-SEED-007 | Seed Run And Policy | Seed identity | Design policy payload | JSON validates seed_run_id and policy_hash | doc |
| N6VA-SEED-008 | Initial Cash Policy | Initial cash | Policy payload | Future preflight checks `1000000.0000 CNY` is policy, not schema constant | planned |
| N6VA-SEED-009 | Initialization Write Semantics | Account row | `n6_virtual_account` | Future execute writes one account row only | planned |
| N6VA-SEED-010 | Initialization Write Semantics | Cash ledger | `n6_virtual_cash_ledger` | Future execute writes one `initial_deposit` row | planned |
| N6VA-SEED-011 | Initialization Write Semantics | Cash snapshot | `n6_virtual_cash_snapshot` | Future execute writes one active snapshot with formula match | planned |
| N6VA-SEED-012 | Initialization Write Semantics | Snapshot pointer | `n6_virtual_account.current_cash_snapshot_id` | Future execute sets pointer after snapshot insert in one transaction | planned |
| N6VA-SEED-013 | Quality Gate | P0 blockers | Future seed preflight | Missing schema/admin/baseline causes BLOCKED | planned |
| N6VA-SEED-014 | Quality Gate | Cash consistency | Ledger and snapshot rows | Ledger amount and snapshot totals must equal policy initial cash | planned |
| N6VA-SEED-015 | Quality Gate | Forbidden rows | 038C-E tables | Future seed preflight requires order/trade/position/pnl rows remain zero for seed | planned |
| N6VA-SEED-016 | Boundary | Outbox safety | N1-N6 outbox/inbox/checkpoint | Future seed preflight proves no outbox/inbox/checkpoint write plan | planned |
| N6VA-SEED-017 | Boundary | Side-effect safety | Worker/delivery/push/voice/mobile/sim/position/real trade | Future seed preflight proves all side effects are absent | planned |
| N6VA-SEED-018 | Rollback Design | Rollback scope | `rollback_scope` | Future rollback deletes only seed scoped rows | planned |
| N6VA-SEED-019 | Rollback Design | Delete order | Snapshot, ledger, account | Future rollback SQL deletes snapshot before ledger before account | planned |
| N6VA-SEED-020 | Rollback Design | Hard-fail guard | 038C-E and future dependent refs | Future rollback blocks if order/trade/position/pnl refs exist | planned |
| N6VA-SEED-021 | Rollback Design | Forbidden rollback scope | N1-N6 facts/outbox and 036/037/038 schema | Future rollback static test proves no schema/outbox/fact deletion | planned |
| N6VA-SEED-022 | Operation Gates Roadmap | Order operation | `n6_virtual_order` | Future virtual order proposal gate required before order writes | planned |
| N6VA-SEED-023 | Operation Gates Roadmap | Position/PnL operation | Position and PnL tables | Future materialization/valuation gates required before position/PnL writes | planned |
| N6VA-SEED-024 | Review Decision | Gate boundary | Design artifacts | Runtime_control design review required before contract/execute | doc |

## Coverage

Every rule maps to a design section, component target, data source, and future
test or review target. No rule claims implementation completion for business
row writes. Rows with status `planned` require later contract, runner, preflight,
rollback, and execute gates.
