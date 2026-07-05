# N6 Phase 3 Virtual Account Schema Traceability

Status: SCHEMA_DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This matrix maps Phase 3 architecture rules to the schema draft, rollback draft,
and static test targets.

Coverage:

```text
schema_rules_total=40
schema_rules_mapped=40
coverage=100%
architecture_rules_referenced=N6VA-001..N6VA-036
```

Status legend:

```text
schema_draft: represented in SQL draft only
future_migration_gate_required: requires future execute review
boundary: hard prohibition
rollback_draft: represented in rollback draft
```

## Schema Rule Matrix

| Rule | Source architecture | Component | SQL / artifact evidence | Test target | Status |
|---|---|---|---|---|---|
| N6VAS-001 | N6VA-001 | N6-only virtual account schema | 8 `n6_virtual_*` tables | no N1-N5 table refs scan | schema_draft |
| N6VAS-002 | N6VA-002 | `user_sim_*` not canonical | no references to `user_sim_*` | no user_sim FK/static scan | boundary |
| N6VAS-003 | N6VA-003 | principal ownership | `principal_id REFERENCES n6_principal` | principal FK test | schema_draft |
| N6VAS-004 | N6VA-004 | admin virtual mode | `account_mode='admin_shadow_virtual'` | account_mode CHECK test | schema_draft |
| N6VAS-005 | N6VA-005 | human virtual mode | `account_mode='human_virtual'` | human mode CHECK test | future_migration_gate_required |
| N6VAS-006 | N6VA-006 | AI virtual mode | `account_mode='ai_virtual'` | AI mode CHECK test | future_migration_gate_required |
| N6VAS-007 | N6VA-007 | system principal default no account | no `system` principal_type in account CHECK | system denial test | boundary |
| N6VAS-008 | N6VA-008 | virtual account PK | `n6_virtual_account.virtual_account_id` | PK existence test | schema_draft |
| N6VAS-009 | N6VA-009 | account bridge | `account_id REFERENCES n6_principal_account` | FK existence test | schema_draft |
| N6VAS-010 | N6VA-010 | no broker/real account field | forbidden fields absent | forbidden column static scan | boundary |
| N6VAS-011 | N6VA-011 | cash ledger immutable lineage | `n6_virtual_cash_ledger` | ledger table exists test | schema_draft |
| N6VAS-012 | N6VA-011 | cash snapshot separated | `n6_virtual_cash_snapshot` | snapshot table exists test | schema_draft |
| N6VAS-013 | N6VA-012 | nonnegative cash | cash CHECKs | negative cash CHECK test | schema_draft |
| N6VAS-014 | N6VA-013 | position current state | `n6_virtual_position` | position state table test | schema_draft |
| N6VAS-015 | N6VA-013 | position event lineage | `n6_virtual_position_event` | event table exists test | schema_draft |
| N6VAS-016 | N6VA-014 | T+1 virtual lock | `t_plus_one_locked_until_trade_date` | T+1 field test | schema_draft |
| N6VAS-017 | N6VA-015 | no common_position write | no `common_position_*` refs in migration | static scan | boundary |
| N6VAS-018 | N6VA-016 | virtual order not broker order | `n6_virtual_order`, no broker fields | broker field scan | boundary |
| N6VAS-019 | N6VA-017 | virtual order lifecycle | `order_status` CHECK | status enum test | schema_draft |
| N6VAS-020 | N6VA-018 | order source lineage | signal/card/decision refs + source_lineage_json | source lineage test | schema_draft |
| N6VAS-021 | N6VA-019 | virtual trade table | `n6_virtual_trade` | trade table test | schema_draft |
| N6VAS-022 | N6VA-020 | deterministic fill replay | `fill_policy_*`, `replay_deterministic_seed` | deterministic fields test | schema_draft |
| N6VAS-023 | N6VA-021 | no real trade semantics | no `broker_order_id`, `real_trade_id` | forbidden field scan | boundary |
| N6VAS-024 | N6VA-022 | virtual PnL snapshot | `n6_virtual_pnl_snapshot` | pnl table test | schema_draft |
| N6VAS-025 | N6VA-023 | PnL math | `total_equity = cash_balance + market_value` | CHECK test | schema_draft |
| N6VAS-026 | N6VA-024 | leaderboard only future reads | no leaderboard FK in PnL schema | leaderboard isolation scan | boundary |
| N6VAS-027 | N6VA-025 | run_id on every table | `run_id` required | common fields test | schema_draft |
| N6VAS-028 | N6VA-026 | policy version/hash on every table | `policy_version`, `policy_hash` | common fields test | schema_draft |
| N6VAS-029 | N6VA-027 | rollback scope on every table | `rollback_scope` | common fields test | schema_draft |
| N6VAS-030 | N6VA-028 | rollback hard-fail | rollback DO block before first DROP | rollback order test | rollback_draft |
| N6VAS-031 | N6VA-029 | rollback no N1-N6/outbox touch | rollback lacks forbidden refs | rollback static scan | boundary |
| N6VAS-032 | N6VA-030 | quality status | `quality_status` on every table | common fields test | schema_draft |
| N6VAS-033 | N6VA-031 | P1/P2 future warnings | quality_status allows warning | quality enum test | schema_draft |
| N6VAS-034 | N6VA-032 | AI profile future gate | AI mode present but no n6_ai_user writes | AI isolation scan | future_migration_gate_required |
| N6VAS-035 | N6VA-033 | AI virtual intent future gate | source_ai_decision_id nullable, no AI table FK | AI intent future test | future_migration_gate_required |
| N6VAS-036 | N6VA-034 | AI real-source denial | forbidden real/broker fields absent | forbidden source scan | boundary |
| N6VAS-037 | N6VA-035 | source allowlist via lineage | source_lineage_json required | lineage JSON object test | schema_draft |
| N6VAS-038 | N6VA-036 | split migration allowed | split recommendation in docs/json | split gate review test | future_migration_gate_required |
| N6VAS-039 | APPROVED_WITH_CHANGES | cash ledger/snapshot split | two cash tables | approved-change coverage test | schema_draft |
| N6VAS-040 | APPROVED_WITH_CHANGES | position state/event split | two position tables | approved-change coverage test | schema_draft |

## Coverage Summary

Required topics:

```text
virtual_account: covered
virtual_cash: covered by ledger + snapshot
virtual_position: covered by state + event
virtual_order: covered
virtual_trade: covered
virtual_pnl: covered
run_id: covered on every table
policy_version: covered on every table
rollback_scope: covered on every table
quality_gate: covered through quality_status and CHECKs
principal ownership: covered through principal_id FK
AI account compatibility: covered as future-gated ai_virtual mode
```

## Remaining Gaps

```text
no migration final gate
no live DB post-review proof
no runner
no virtual rows
no AI principal/profile active gate
no UI/API adapter
```
