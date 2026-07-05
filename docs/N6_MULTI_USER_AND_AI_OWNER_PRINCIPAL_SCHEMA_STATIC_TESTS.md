# N6 Multi User and AI Owner Principal Schema Static Tests

Status: STATIC_TEST_ARTIFACT_PASS

Layer role: N6_user

Date: 2026-06-04

This artifact defines static validation for the 036 owner/principal schema draft.
It does not execute SQL and does not connect to the database.

## 1. Target Files

```text
sql/036_n6_multi_user_ai_owner_principal_schema.sql
sql/036_n6_multi_user_ai_owner_principal_schema_rollback.sql
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_SQL_MIGRATION_DRAFT.md
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_SQL_MIGRATION_DRAFT.json
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_ROLLBACK_DRAFT.md
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_ROLLBACK_DRAFT.json
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_STATIC_TESTS.md
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_STATIC_TESTS.json
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_TRACEABILITY.md
docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_TRACEABILITY.json
```

## 2. Static Checks

JSON parse checks:

```text
python3 -m json.tool docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_SQL_MIGRATION_DRAFT.json
python3 -m json.tool docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_ROLLBACK_DRAFT.json
python3 -m json.tool docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_STATIC_TESTS.json
python3 -m json.tool docs/N6_MULTI_USER_AND_AI_OWNER_PRINCIPAL_SCHEMA_TRACEABILITY.json
```

Migration SQL checks:

```text
036 migration creates exactly 5 Track B tables
036 migration creates exactly 5 N6 read-only view proposals
036 migration creates only n6_* tables and v_n6_* views
036 migration uses no business DML tokens
036 migration does not ALTER existing tables
036 migration does not DROP objects
036 migration does not GRANT UPDATE/INSERT/DELETE
036 migration does not create INSTEAD OF triggers
036 migration does not reference N5 outbox status updates
036 migration does not modify N6_UI_v1/API/projection/shadow pipeline
```

AI principal static checks:

```text
human_user principal with owner_user_id is legal
admin principal with owner_user_id is legal
system principal without owner_user_id is legal
ai_user principal without owner_user_id is legal as a reserved owner root
ai_user principal without n6_ai_user profile is not an active AI actor
n6_ai_user.principal_id is UNIQUE
n6_ai_user.principal_type is fixed to ai_user
n6_ai_user(principal_id, principal_type) references n6_principal(principal_id, principal_type)
non-ai_user principal cannot bind n6_ai_user profile
```

Same-name object baseline checks required before future execute:

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

`IF NOT EXISTS` is a defensive draft guard only. The final gate must not rely on
it to silently skip old same-name objects.

Read-only view permission assertions:

```text
CREATE VIEW is not treated as physical immutability
this gate grants no write permissions
this gate creates no INSTEAD OF trigger
this gate grants no UPDATE/INSERT/DELETE
future API may only SELECT these views unless a separate permission gate passes
```

Rollback SQL checks:

```text
rollback has RAISE EXCEPTION guard before first DROP
rollback guards all 5 target Track B tables
rollback drops views before tables
rollback drops only 036-created objects
rollback uses no CASCADE
rollback does not target N5 outbox or N1-N5 facts
rollback does not delete existing N6 projection/user/sim rows
```

Traceability checks:

```text
N6OP-001..N6OP-040 remain continuous
principal/account rules have SQL evidence binding
display input conclusions remain covered
no DESIGN_ONLY rule is upgraded to implementation pass
```

## 3. Expected Result

```text
STATIC_TEST_PASS
```

Expected next gate:

```text
runtime_control N6 owner/principal SQL migration draft review gate
```
