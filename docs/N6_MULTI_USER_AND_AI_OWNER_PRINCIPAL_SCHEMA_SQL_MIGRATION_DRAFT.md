# N6 Multi User and AI Owner Principal Schema SQL Migration Draft

Status: SQL_MIGRATION_DRAFT_PASS

Layer role: N6_user

Date: 2026-06-04

Migration draft:

```text
sql/036_n6_multi_user_ai_owner_principal_schema.sql
```

This is a draft artifact only. It was not executed and did not write the
database.

## 1. Source Contract

Source artifacts:

```text
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_DRAFT.md
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_DRAFT.json
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_TRACEABILITY.md
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_TRACEABILITY.json
```

The migration draft binds the owner/principal/account rules to concrete DDL
evidence while preserving Track A isolation.

## 2. Migration Scope

Review section A: owner/principal/account tables.

New tables:

```text
n6_principal
n6_ai_user
n6_principal_account
n6_watchlist_ownership
n6_strategy
```

Review section B: N6 display/membership read views.

New read-only view proposals:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

New indexes:

```text
idx_n6_principal_owner_user
idx_n6_principal_type_status
idx_n6_ai_user_status
idx_n6_ai_user_strategy_profile
idx_n6_principal_account_owner_status
idx_n6_principal_account_type_status
idx_n6_principal_account_virtual_ref
idx_n6_watchlist_ownership_principal
idx_n6_watchlist_ownership_watchlist
idx_n6_strategy_owner_status
idx_n6_strategy_type_status
idx_n6_strategy_policy
```

## 3. Additive Boundary

Allowed DDL in the draft:

```text
CREATE TABLE IF NOT EXISTS
CREATE UNIQUE INDEX IF NOT EXISTS
CREATE INDEX IF NOT EXISTS
DO blocks that create views only if missing
CREATE VIEW inside guarded DO blocks
BEGIN / COMMIT
```

Forbidden and absent from the migration draft:

```text
ALTER old tables
business INSERT
business UPDATE
business DELETE
TRUNCATE
COPY
DROP
GRANT
INSTEAD OF trigger
N5 outbox status changes
N1-N5 fact changes
N6 projection/card/queue changes
N6_UI_v1/API/shadow-pipeline changes
worker / delivery / push / voice / mobile / sim / position / real trade
```

## 4. Owner / Principal Evidence

`n6_principal` freezes the Track B owner root:

```text
principal_id
principal_type = human_user / ai_user / admin / system
owner_user_id
principal_status
created_at / updated_at
```

Shape constraints:

```text
human_user/admin require owner_user_id
ai_user requires no owner_user_id
system requires no owner_user_id
```

`owner_user_id` references existing `user_account(user_id)` without altering
`user_account`. The SQL draft stores no reverse AI id on `n6_principal`; this
avoids a cyclic or guessed AI id binding. AI users are modeled as
profile/extension rows in `n6_ai_user`.

AI principal profile semantics:

```text
principal_type=ai_user without n6_ai_user profile is allowed only as a reserved
owner root; it is not an active AI actor and cannot run AI decision/evaluation.
n6_ai_user.principal_id is UNIQUE.
n6_ai_user.principal_type is fixed to ai_user.
n6_ai_user(principal_id, principal_type) references
n6_principal(principal_id, principal_type).
non-ai_user principals cannot bind an n6_ai_user profile.
```

## 5. AI User Evidence

`n6_ai_user` binds:

```text
ai_user_id
principal_id
principal_type = ai_user
ai_name
strategy_profile_id
status
readable_scope_policy
```

The default `readable_scope_policy` allowlists only N6 read-safe views,
N6 shadow projection tables, and reviewed artifacts. It explicitly lists
forbidden sources such as raw K, direct live market data, condition internals,
N3/N4/N5 raw facts, real account/funds/position, broker sessions, and real
trade APIs.

## 5.1 AI Principal Static Creation Paths

The final gate must check these combinations at contract/static level:

| Path | Expected result | Reason |
|---|---|---|
| `principal_type=human_user`, `owner_user_id` set | allowed | Human principal binds existing user account. |
| `principal_type=admin`, `owner_user_id` set | allowed | Admin principal binds existing admin user account. |
| `principal_type=system`, `owner_user_id` null | allowed | System principal is reserved/system-owned. |
| `principal_type=ai_user`, `owner_user_id` null, no profile | allowed as reserved only | Owner root may be provisioned before profile. |
| `principal_type=ai_user` + one `n6_ai_user` profile | allowed | AI user profile/extension is complete. |
| `n6_ai_user` referencing non-`ai_user` principal | blocked | Composite FK requires principal type `ai_user`. |
| second `n6_ai_user` profile for same principal | blocked | `n6_ai_user.principal_id` is unique. |

## 6. Account Evidence

`n6_principal_account` binds:

```text
account_id
principal_id
account_type = virtual / ai_virtual / admin_shadow
virtual_account_id
account_status
account_policy_version
account_policy_hash
```

No real broker fields, real-fund fields, or real-trade fields are present.
`virtual_account_source` is limited to `future_virtual_account` and
`user_sim_account_adapter` so current shadow sim evidence can be referenced by a
future adapter without rewriting existing `user_sim_*` tables.

## 7. Watchlist / Strategy Evidence

`n6_watchlist_ownership` adds principal-scoped ownership for current
`user_watchlist` rows without altering that table.

`n6_strategy` adds owner principal, immutable policy version/hash, status,
visibility, and marketplace risk-label shape. It does not execute strategy
logic and does not write N1-N5 or N6 projection rows.

## 8. Display / Membership Views

The view draft exposes only display-safe columns from:

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
index_membership_fact
board_membership_fact
```

The view draft excludes raw payload columns by default:

```text
raw_json
raw_payload
```

The board views enforce the board type enum:

```text
tdx_industry
tdx_concept
tdx_region
tdx_other
```

Read-only permission contract:

```text
CREATE VIEW does not make a PostgreSQL object physically immutable.
This gate does not grant write permissions.
The SQL draft creates no INSTEAD OF trigger.
The SQL draft contains no GRANT.
The SQL draft grants no UPDATE / INSERT / DELETE on these views.
Future APIs may only SELECT from these views unless a separate permission gate
explicitly changes grants and tests the boundary.
```

## 9. Review Notes

The SQL draft is designed for a future migration final gate. Before execution,
runtime_control should still review:

```text
target database proof
additive DDL scan
view updatability / grant policy
rollback hard-fail behavior
no business row baseline
dependent object check
```

Required same-name object baseline before any future execute final gate:

```text
n6_principal does not exist
n6_ai_user does not exist
n6_principal_account does not exist
n6_watchlist_ownership does not exist
n6_strategy does not exist
v_n6_stock_condition_display_basis does not exist
v_n6_index_condition_display_basis does not exist
v_n6_board_condition_display_basis does not exist
v_n6_index_membership_fact does not exist
v_n6_board_membership_fact does not exist
```

`IF NOT EXISTS` is a defensive draft guard only. It must not be used by the
final gate to treat pre-existing incompatible objects as success.

## 10. Next Gate

Allowed next step:

```text
runtime_control N6 owner/principal SQL migration draft review gate
```

Still forbidden:

```text
executing sql/036_n6_multi_user_ai_owner_principal_schema.sql
database writes
N6 business implementation
N6_UI_v1/API/projection/shadow-pipeline modification
outbox consumption/update
worker / delivery / push / voice / mobile / sim / position / real trade
```
