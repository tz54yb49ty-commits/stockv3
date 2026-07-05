# N6 Phase 3 038B Virtual Cash Traceability

Status: DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This matrix maps 038B requirements to the split migration draft and static
tests.

Coverage:

```text
rule_count=22
rules_mapped=22
coverage=100%
```

| Rule | Source | Requirement | Evidence | Test target | Status |
|---|---|---|---|---|---|
| N6VA038B-001 | 038B scope | create only cash ledger and cash snapshot | SQL has two CREATE TABLE statements | create table count test | draft |
| N6VA038B-002 | 038B scope | do not create 038C-E tables | SQL lacks future table CREATE | future table absence scan | boundary |
| N6VA038B-003 | ledger | ledger is immutable cash ledger | no `updated_at`; append-only contract | immutable ledger scan | draft |
| N6VA038B-004 | ledger | ledger FK to virtual account | `virtual_account_id` FK | FK static scan | draft |
| N6VA038B-005 | ledger | ledger_type values fixed | CHECK values | enum test | draft |
| N6VA038B-006 | ledger | amount can be positive or negative | no amount nonnegative CHECK | amount check scan | draft |
| N6VA038B-007 | ledger | source_event fields present | SQL field list | field presence test | draft |
| N6VA038B-008 | ledger | source order/trade refs nullable and no future FK | nullable BIGINT fields only | future FK absence scan | draft |
| N6VA038B-009 | snapshot | snapshot FK to virtual account | `virtual_account_id` FK | FK static scan | draft |
| N6VA038B-010 | snapshot | balance fields nonnegative | CHECK constraints | cash nonnegative test | draft |
| N6VA038B-011 | snapshot | no overdraft policy | nonnegative total/available/frozen cash | overdraft scan | boundary |
| N6VA038B-012 | snapshot | snapshot keeps ledger lineage | `source_ledger_max_id` FK | ledger lineage test | draft |
| N6VA038B-013 | snapshot | snapshot_status values fixed | CHECK values | status enum test | draft |
| N6VA038B-014 | policy | run/policy/rollback fields present | SQL field list | policy field test | draft |
| N6VA038B-015 | policy | source_lineage_json object | JSONB CHECK | JSONB object test | draft |
| N6VA038B-016 | deferred rules | no fee/tax/T+1 hardcoded rule | no rate/T+1 fields | deferred policy scan | boundary |
| N6VA038B-017 | boundary | no broker/real trade fields | no forbidden fields | static scan | boundary |
| N6VA038B-018 | rollback | hard-fail before DROP | rollback DO block | rollback order test | rollback_draft |
| N6VA038B-019 | rollback | block if cash rows exist | row_count guards | row guard test | rollback_draft |
| N6VA038B-020 | rollback | block if future deps have rows | `to_regclass` loop | split dependency test | rollback_draft |
| N6VA038B-021 | rollback | drop only 038B tables | DROP table list | rollback scope test | rollback_draft |
| N6VA038B-022 | boundary | no N1-N6 facts/outbox touched | no forbidden refs | static scan | boundary |

## Remaining Gaps

```text
no DDL executed
no live DB proof
no 038B final gate
no cash rows
no virtual account rows
no 038C-E tables
no fee/tax/T+1 policy
no runner
```
