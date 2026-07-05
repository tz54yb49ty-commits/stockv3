# N6 Phase 3 038A Virtual Account Traceability

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This matrix maps 038A requirements to the split migration draft and static
tests.

Coverage:

```text
rule_count=18
rules_mapped=18
coverage=100%
```

| Rule | Source | Requirement | Evidence | Test target | Status |
|---|---|---|---|---|---|
| N6VA038A-001 | 038A scope | create only `n6_virtual_account` | SQL has one CREATE TABLE | create table count test | draft |
| N6VA038A-002 | 038A scope | do not create 038B-E tables | SQL lacks future table CREATE | future table absence scan | boundary |
| N6VA038A-003 | ownership | composite principal FK | `(principal_id, principal_type)` FK | FK static scan | draft |
| N6VA038A-004 | ownership | allow admin principal | principal_type CHECK | enum test | draft |
| N6VA038A-005 | ownership | allow human_user principal | principal_type CHECK | enum test | draft |
| N6VA038A-006 | ownership | allow ai_user principal | principal_type CHECK | enum test | future_gate_required |
| N6VA038A-007 | ownership | forbid system principal | principal_type CHECK excludes system | system denial scan | boundary |
| N6VA038A-008 | account_id | defer account_id linkage | no account_id column | account linkage scan | draft |
| N6VA038A-009 | fields | required core fields present | SQL field list | field presence test | draft |
| N6VA038A-010 | enum | virtual_account_status values fixed | CHECK values | status enum test | draft |
| N6VA038A-011 | enum | base_currency CNY default | `base_currency` CHECK | currency test | draft |
| N6VA038A-012 | enum | quality_status values fixed | CHECK values | quality enum test | draft |
| N6VA038A-013 | policy | run/policy/rollback fields present | SQL field list | policy field test | draft |
| N6VA038A-014 | rollback | hard-fail before DROP | rollback DO block | rollback order test | rollback_draft |
| N6VA038A-015 | rollback | block if account rows exist | row_count guard | row guard test | rollback_draft |
| N6VA038A-016 | rollback | block if future deps have rows | `to_regclass` loop | split dependency test | rollback_draft |
| N6VA038A-017 | boundary | no N1-N6 facts/outbox touched | no forbidden refs | static scan | boundary |
| N6VA038A-018 | boundary | no broker/real trade fields | no forbidden fields | static scan | boundary |

## Remaining Gaps

```text
no DDL executed
no live DB proof
no 038A final gate
no account rows
no account_id linkage
no 038B-E tables
```
