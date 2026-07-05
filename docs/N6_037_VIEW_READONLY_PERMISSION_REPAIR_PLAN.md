# N6 037 View Readonly Permission Repair Plan

Status: REPAIR_PLAN_PASS

Layer role: N6_user

Date: 2026-06-05

This gate creates a permission-only migration draft for the 036 N6 Track B
read-only views. It does not execute DDL, write business rows, consume/update
outbox rows, start workers, modify N6_UI_v1, modify existing APIs/projection/
shadow pipeline, or run delivery/push/voice/mobile/sim/position/real trade.

## 1. Blocker Being Repaired

036 migration post-review proved:

```text
5 Track B tables exist and row_count=0
5 N6 views exist
views have no INSTEAD OF trigger
AI principal FK/unique/check exists
rollback SQL static check passes
```

The blocker is permission proof:

```text
information_schema.role_table_grants shows owner role ashare_v3_user has
INSERT / UPDATE / DELETE / TRUNCATE / REFERENCES / TRIGGER / SELECT on the views.
```

That owner role cannot be used as a runtime/API read-only proof.

## 2.方案评估

### 2.1 Can PostgreSQL owner permissions be fully revoked?

No for this proof. PostgreSQL object ownership carries inherent object control.
Even if explicit ACL entries are revoked, the owner remains the owner and cannot
serve as a reliable runtime read-only proof.

Conclusion:

```text
owner role ashare_v3_user must not be the read-only proof target
```

### 2.2 Recommended role strategy

Use a dedicated NOLOGIN runtime permission role:

```text
n6_ui_readonly_role
```

The role receives only:

```text
USAGE ON SCHEMA public
SELECT ON the 5 N6 read-only views
```

The role receives no privileges on:

```text
n6_principal
n6_ai_user
n6_principal_account
n6_watchlist_ownership
n6_strategy
```

The role receives no:

```text
INSERT
UPDATE
DELETE
TRUNCATE
REFERENCES
TRIGGER
```

### 2.3 Runtime/API proof target

The post-review proof must shift from owner grants to runtime role grants:

```text
prove n6_ui_readonly_role can SELECT the 5 views
prove n6_ui_readonly_role has no write privileges on 5 views
prove n6_ui_readonly_role has no privileges on 5 base Track B tables
prove views have no INSTEAD OF trigger
```

API contract:

```text
future API must use a readonly provider or SET ROLE n6_ui_readonly_role
before querying these views
```

This gate does not modify API code and does not change DSN configuration.

## 3. 037 Migration Draft

Migration draft:

```text
sql/037_n6_view_readonly_permission.sql
```

The migration draft:

```text
creates n6_ui_readonly_role as NOLOGIN if missing
uses existing n6_ui_readonly_role if present and clean
blocks if an existing role has unexpected target grants
revokes all target grants from that role
grants USAGE ON SCHEMA public
grants SELECT on exactly the 5 N6 views
grants no write privileges
creates no trigger
does not modify view definitions
does not touch 036 tables except permission revokes from the readonly role
```

Current preflight note:

```text
ashare_v3_user.rolcreaterole=false
n6_ui_readonly_role does not exist
```

Therefore a future execute gate with the same DB user is expected to be blocked
unless either:

```text
a privileged DBA/session creates n6_ui_readonly_role first
or the migration is executed by a role with CREATEROLE permission
```

If the role is pre-created, `ashare_v3_user` can apply grants because it owns
the 036 objects.

## 4. Rollback Draft

Rollback draft:

```text
sql/037_n6_view_readonly_permission_rollback.sql
```

Rollback scope:

```text
REVOKE SELECT on the 5 views from n6_ui_readonly_role
REVOKE USAGE on schema public from n6_ui_readonly_role
DROP ROLE only if the role comment proves it was created by 037
```

Rollback does not:

```text
drop 036 tables/views
write business rows
touch N1-N6 facts/outbox
modify N6_UI_v1/API/projection/shadow pipeline
```

Rollback hard-fail guard runs before the first REVOKE/DROP and blocks if:

```text
n6_ui_readonly_role is missing
any 036 view is missing
n6_ui_readonly_role owns objects
```

## 5. Post-Review Proof Queries

Role grant proof:

```sql
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND grantee = 'n6_ui_readonly_role'
  AND table_name IN (
    'v_n6_stock_condition_display_basis',
    'v_n6_index_condition_display_basis',
    'v_n6_board_condition_display_basis',
    'v_n6_index_membership_fact',
    'v_n6_board_membership_fact',
    'n6_principal',
    'n6_ai_user',
    'n6_principal_account',
    'n6_watchlist_ownership',
    'n6_strategy'
  )
ORDER BY table_name, privilege_type;
```

Expected post-review result:

```text
for 5 views: SELECT only
for 5 Track B tables: no rows
```

View trigger proof:

```sql
SELECT tgrelid::regclass::text AS relation_name, tgname, pg_get_triggerdef(oid)
FROM pg_trigger
WHERE tgrelid IN (
  'v_n6_stock_condition_display_basis'::regclass,
  'v_n6_index_condition_display_basis'::regclass,
  'v_n6_board_condition_display_basis'::regclass,
  'v_n6_index_membership_fact'::regclass,
  'v_n6_board_membership_fact'::regclass
)
  AND NOT tgisinternal;
```

Expected result:

```text
0 rows
```

## 6. Forbidden Scope

Still forbidden:

```text
business rows
outbox consumption/update
worker startup
N6_UI_v1 changes
existing API changes
projection/shadow pipeline changes
delivery / push / voice / mobile / sim / position / real trade
```

## 7. Next Gate

Allowed next step:

```text
runtime_control N6 037 view readonly permission final gate review
```

Expected review caveat:

```text
execute remains blocked under ashare_v3_user until n6_ui_readonly_role exists
or the executor has CREATEROLE.
```
