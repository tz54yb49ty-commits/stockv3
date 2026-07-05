# N6 Phase 3 038C Order/Trade Traceability

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This matrix maps 038C requirements to the split migration draft and static
tests.

Coverage:

```text
rule_count=24
rules_mapped=24
coverage=100%
```

| Rule | Source | Requirement | Evidence | Test target | Status |
|---|---|---|---|---|---|
| N6VA038C-001 | 038C scope | create only virtual order and virtual trade | SQL has two CREATE TABLE statements | create table count test | draft |
| N6VA038C-002 | 038C scope | do not create 038D-E tables | SQL lacks future table CREATE | future table absence scan | boundary |
| N6VA038C-003 | order | order FK to virtual account | `virtual_account_id` FK | FK static scan | draft |
| N6VA038C-004 | order | order principal composite FK | `(principal_id, principal_type)` FK | principal FK scan | draft |
| N6VA038C-005 | order | order required fields present | SQL field list | field presence test | draft |
| N6VA038C-006 | order | order side values are buy/sell | CHECK values | enum test | draft |
| N6VA038C-007 | order | order status values virtual-only | status CHECK values | status enum test | draft |
| N6VA038C-008 | order | requested quantity positive | CHECK constraint | quantity test | draft |
| N6VA038C-009 | order | fee/tax estimate fields are amount fields only | amount columns and no rate fields | deferred policy scan | draft |
| N6VA038C-010 | order | source refs are nullable lineage ids | nullable source columns and no outbox FK | lineage scan | draft |
| N6VA038C-011 | trade | trade FK to virtual order | `virtual_order_id` FK | FK static scan | draft |
| N6VA038C-012 | trade | trade FK to virtual account | `virtual_account_id` FK | FK static scan | draft |
| N6VA038C-013 | trade | trade principal composite FK | `(principal_id, principal_type)` FK | principal FK scan | draft |
| N6VA038C-014 | trade | trade required fields present | SQL field list | field presence test | draft |
| N6VA038C-015 | trade | trade side values are buy/sell | CHECK values | enum test | draft |
| N6VA038C-016 | trade | fill quantity and amounts constrained | CHECK constraints | amount test | draft |
| N6VA038C-017 | trade | fee component consistency check | total fee CHECK | fee consistency test | draft |
| N6VA038C-018 | trade | deterministic replay fields required | SQL field list | deterministic field test | draft |
| N6VA038C-019 | boundary | no broker/real execution fields | no forbidden field names | static scan | boundary |
| N6VA038C-020 | boundary | no T+1/fee/tax hardcoded rules | no rate/T+1 fields | deferred rule scan | boundary |
| N6VA038C-021 | boundary | no common_position or user_sim writes | no references | static scan | boundary |
| N6VA038C-022 | rollback | hard-fail before DROP | rollback DO block | rollback order test | rollback_draft |
| N6VA038C-023 | rollback | block if order/trade or future deps have rows | row_count guards | rollback guard test | rollback_draft |
| N6VA038C-024 | rollback | drop only 038C tables | DROP table list | rollback scope test | rollback_draft |

## Remaining Gaps

```text
no DDL executed
no live DB proof
no 038C final gate
no order rows
no trade rows
no 038D-E tables
no fee/tax/T+1 policy
no execution runner
```
