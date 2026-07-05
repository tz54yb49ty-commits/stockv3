# N6 Multi User and AI Owner Principal Schema Traceability

Status: SCHEMA_TRACEABILITY_PASS

Layer role: N6_user

Date: 2026-06-04

This traceability matrix maps the owner / principal / account schema draft to
source architecture rules, display input boundary conclusions, proposed objects,
data sources, test targets, and current implementation status.

Coverage:

```text
schema_rules_total=40
schema_rules_mapped=40
coverage=100%
display_input_conclusions_total=4
display_input_conclusions_covered=4
display_input_conclusion_coverage=100%
```

Status legend:

```text
draft: schema requirement frozen as draft only
existing_evidence: current N6/N1/N2 table evidence exists, but no Track B implementation pass
boundary: prohibition or isolation rule
future_gate_required: implementation/migration/test requires a later gate
view_proposal: read-only view proposal only
```

## Schema Rule Matrix

| Rule | Source rules | Draft section | Component | Data source | Test target | Status |
|---|---|---|---|---|---|---|
| N6OP-001 | N6ARCH-001..005 | 3 Principal Model | `principal_id` owner root | future `n6_principal` | principal id required test | draft |
| N6OP-002 | N6ARCH-001..005 | 3 Principal Model | `principal_type` enum | future `n6_principal` | principal type enum test | draft |
| N6OP-003 | N6ARCH-001 | 3 Principal Model | human/admin owner binding | `user_account.user_id` | owner_user_id binding test | future_gate_required |
| N6OP-004 | N6ARCH-002 | 3 Principal Model | AI owner binding | future `n6_ai_user` | AI profile binding test | future_gate_required |
| N6OP-005 | N6ARCH-001..005 | 3 Principal Model | `principal_status` lifecycle | future `n6_principal` | status enum/lifecycle test | draft |
| N6OP-006 | N6ARCH-019, N6AI-001 | 4 Human User Model | `user_id` mapping | `user_account.user_id` | human user mapping test | existing_evidence |
| N6OP-007 | N6ARCH-019, N6AI-001 | 4 Human User Model | `login_identity` mapping | `user_account.login_name` | login identity exposure test | existing_evidence |
| N6OP-008 | N6ARCH-020, N6AI-004 | 4 Human User Model | role/status mapping | `user_account.role/status` | role/status mapping test | existing_evidence |
| N6OP-009 | N6ARCH-024..026 | 4 Human User Model | password/session secrecy | `user_account`, `user_session` | no password/session secret in view test | boundary |
| N6OP-010 | N6ARCH-002, N6AI-006 | 5 AI User Model | `ai_user_id` | future `n6_ai_user` | AI user id required test | draft |
| N6OP-011 | N6ARCH-002, N6AI-006 | 5 AI User Model | AI `principal_id` | future `n6_ai_user` + `n6_principal` | AI principal FK test | future_gate_required |
| N6OP-012 | N6ARCH-004, N6AI-016..020 | 5 AI User Model | `strategy_profile_id` | future strategy profile | AI strategy profile test | future_gate_required |
| N6OP-013 | N6ARCH-006..012 | 5 AI User Model | `readable_scope_policy` allowlist | approved summaries/artifacts | AI allowed-source test | draft |
| N6OP-014 | N6ARCH-011..012 | 5 AI User Model | forbidden AI sources | raw/live/real/broker sources | AI forbidden-source denial test | boundary |
| N6OP-015 | N6ARCH-003, N6AI-011 | 6 Account Model | `account_id` | future `n6_principal_account` | account id required test | draft |
| N6OP-016 | N6ARCH-003 | 6 Account Model | account owner principal | future `n6_principal_account` | account owner FK test | future_gate_required |
| N6OP-017 | N6ARCH-003, N6ARCH-021 | 6 Account Model | account type enum | future account + current `user_sim_account` evidence | account type enum test | draft |
| N6OP-018 | N6ARCH-011..012, N6ARCH-037 | 6 Account Model | no real broker account | forbidden broker/real sources | no real account fields test | boundary |
| N6OP-019 | N6ARCH-005, N6ARCH-022 | 7 Watchlist Ownership | `watchlist_id` bridge | `user_watchlist` | watchlist bridge test | existing_evidence |
| N6OP-020 | N6ARCH-005, N6AI-021..025 | 7 Watchlist Ownership | watchlist principal owner | future principal adapter | watchlist principal scope test | future_gate_required |
| N6OP-021 | N6ARCH-042 | 7 Watchlist Ownership | visibility enum | future visibility policy | visibility enum test | draft |
| N6OP-022 | N6ARCH-043..044 | 7 Watchlist Ownership | watchlist does not expand upstream scope | N1-N5 boundary | no upstream scope mutation test | boundary |
| N6OP-023 | N6ARCH-004, N6AI-016..020 | 8 Strategy Ownership | `strategy_id` | future `n6_strategy` | strategy id required test | draft |
| N6OP-024 | N6ARCH-004 | 8 Strategy Ownership | strategy owner principal | future `n6_strategy` | strategy owner FK test | future_gate_required |
| N6OP-025 | N6ARCH-013..018 | 8 Strategy Ownership | policy version/hash | future strategy policy | policy immutability test | draft |
| N6OP-026 | N6ARCH-041 | 8 Strategy Ownership | strategy risk/status lifecycle | future strategy marketplace | risk/status coverage test | future_gate_required |
| N6OP-027 | N6ARCH-006 | 9 Display Input Boundary | stock display basis input | `stock_condition_display_basis` | N6 stock display source allowlist test | view_proposal |
| N6OP-028 | N6ARCH-006 | 9 Display Input Boundary | index display basis input | `index_condition_display_basis` | N6 index display source allowlist test | view_proposal |
| N6OP-029 | N6ARCH-006 | 9 Display Input Boundary | board display basis input | `board_condition_display_basis` | N6 board display source allowlist test | view_proposal |
| N6OP-030 | N6ARCH-006, N6ARCH-011 | 9 Display Input Boundary | no condition_basis/pool/scope direct reads | N2 internal tables | forbidden N2 raw source static test | boundary |
| N6OP-031 | N6ARCH-011 | 9 Display Input Boundary | no N3/N4/N5 raw fact direct reads | N3/N4/N5 raw facts | forbidden upstream raw fact static test | boundary |
| N6OP-032 | N6ARCH-006 | 9 Display Input Boundary | index membership input | `index_membership_fact` | membership view allowlist test | view_proposal |
| N6OP-033 | N6ARCH-006 | 9 Display Input Boundary | board membership input | `board_membership_fact` | membership view allowlist test | view_proposal |
| N6OP-034 | N6ARCH-006 | 9 Display Input Boundary | board_type enum | `board_condition_display_basis`, `board_membership_fact` | board_type enum test | existing_evidence |
| N6OP-035 | N6ARCH-010 | 9 Display Input Boundary | N6 shadow projection input | `user_signal_projection/card/queue` | shadow projection read allowlist test | existing_evidence |
| N6OP-036 | N6ARCH-006..010 | 10 Suggested Read-Only Views | `v_n6_*display_basis` proposals | N2 display_basis tables | view definition review test | view_proposal |
| N6OP-037 | N6ARCH-006 | 10 Suggested Read-Only Views | `v_n6_*membership_fact` proposals | N1 membership facts | membership view definition review test | view_proposal |
| N6OP-038 | N6ARCH-043..045 | 11 Track A / Track B Isolation | no Track A modification | N6_UI_v1 / existing APIs | track isolation static test | boundary |
| N6OP-039 | N6ARCH-013..018 | 12 Rollback / Replay Contract | future run-scoped rollback | future Track B run ids | rollback guard test | future_gate_required |
| N6OP-040 | N6ARCH-028..037, N6ARCH-045 | 14 Next Allowed Gate | no migration/execute in this gate | docs only | no SQL/DDL/DB write scan | boundary |

## Display Input Conclusion Coverage

| Conclusion | Covered by rules | Status |
|---|---|---|
| N6 reads only three N2 display_basis physical tables for display input | N6OP-027..029, N6OP-036 | covered |
| N6 does not directly read condition_basis / condition_pool / minute_target_scope / N3 raw / N4 raw / N5 raw | N6OP-030..031 | covered |
| Stock-to-index/board association uses N1 membership facts only | N6OP-032..033, N6OP-037 | covered |
| `board_type` enum is tdx_industry / tdx_concept / tdx_region / tdx_other | N6OP-034 | covered |

## Current Evidence Binding

| Evidence | Interpretation |
|---|---|
| `user_account` | Human/admin account evidence only; not Track B principal implementation. |
| `user_session` | Session hash safety evidence only; not AI token implementation. |
| `user_watchlist` / `user_watchlist_item` | Current user watchlist evidence only; principal visibility sharing is future-gated. |
| `user_sim_account` | Shadow simulation table evidence only; canonical virtual account model is future-gated. |
| `stock_condition_display_basis` | Approved N2 display input candidate for N6 read-only view. |
| `index_condition_display_basis` | Approved N2 display input candidate for N6 read-only view. |
| `board_condition_display_basis` | Approved N2 display input candidate for N6 read-only view with board_type enum. |
| `index_membership_fact` | Approved N1 membership read candidate for stock-to-index display association. |
| `board_membership_fact` | Approved N1 membership read candidate for stock-to-board display association. |
| `user_projection_run`, `user_signal_projection`, `user_signal_card`, `user_notification_queue` | N6 shadow projection evidence and read source; no new writes in this gate. |

## SQL Migration Draft Evidence Binding

The SQL migration draft now binds owner/principal/account rules to concrete draft
DDL evidence. This is not execution evidence.

| Rules | SQL evidence | Rollback evidence | Static test evidence | Status |
|---|---|---|---|---|
| N6OP-001..005 | `n6_principal` in `sql/036_n6_multi_user_ai_owner_principal_schema.sql`; no reverse AI id binding | row-count hard-fail guard for `n6_principal`; no CASCADE | object/count, baseline object, and AI principal path checks | draft_evidence_bound |
| N6OP-006..009 | `owner_user_id` FK to `user_account(user_id)`; no password/session fields in new views | rollback does not touch `user_account` / `user_session` | forbidden exposure checks | draft_evidence_bound |
| N6OP-010..014 | `n6_ai_user.principal_id UNIQUE`; `principal_type='ai_user'`; composite FK to `n6_principal(principal_id, principal_type)` | row-count hard-fail guard for `n6_ai_user`; no CASCADE | AI profile binding and non-AI principal denial checks | draft_evidence_bound |
| N6OP-015..018 | `n6_principal_account` | row-count hard-fail guard for `n6_principal_account` | account enum and no real/broker field checks | draft_evidence_bound |
| N6OP-019..022 | `n6_watchlist_ownership` | row-count hard-fail guard for `n6_watchlist_ownership` | watchlist scope/isolation checks | draft_evidence_bound |
| N6OP-023..026 | `n6_strategy` | row-count hard-fail guard for `n6_strategy` | strategy policy/hash/risk-label checks | draft_evidence_bound |
| N6OP-027..037 | `v_n6_*display_basis` and `v_n6_*membership_fact` view drafts; no GRANT / no INSTEAD OF trigger | views dropped before tables; no CASCADE | view source allowlist, raw payload exclusion, SELECT-only API contract checks | draft_evidence_bound |
| N6OP-038..040 | migration/rollback/static artifacts only; no execution; same-name baseline must be absent before final gate | rollback targets only 036-created objects | no DML/no ALTER/no DROP-in-migration and baseline-object checks | draft_evidence_bound |

Evidence artifact paths:

```text
sql/036_n6_multi_user_ai_owner_principal_schema.sql
sql/036_n6_multi_user_ai_owner_principal_schema_rollback.sql
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_SQL_MIGRATION_DRAFT.md
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_SQL_MIGRATION_DRAFT.json
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_ROLLBACK_DRAFT.md
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_ROLLBACK_DRAFT.json
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_STATIC_TESTS.md
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_STATIC_TESTS.json
```

Final gate baseline evidence required before execute:

```text
n6_principal absent
n6_ai_user absent
n6_principal_account absent
n6_watchlist_ownership absent
n6_strategy absent
v_n6_stock_condition_display_basis absent
v_n6_index_condition_display_basis absent
v_n6_board_condition_display_basis absent
v_n6_index_membership_fact absent
v_n6_board_membership_fact absent
```

## Remaining Gaps

```text
no principal binding rows for existing users
no AI user schema implementation
no AI readable_scope_policy enforcement
no strategy ownership implementation
no shared visibility grant model
no virtual account canonical implementation
no N6_UI_v1 adapter
no execution, migration, worker, delivery, sim, position, or real trade
```

## Next Gate

Allowed next step:

```text
runtime_control N6 owner/principal SQL migration draft review gate
```

Implementation, migration, execution, database writes, outbox consumption,
worker startup, delivery, push, voice, mobile, sim, position, or real trade
remain blocked until separate explicitly authorized gates.
