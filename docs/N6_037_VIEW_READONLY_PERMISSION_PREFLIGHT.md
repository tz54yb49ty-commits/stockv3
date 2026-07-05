# N6 037 View Readonly Permission Preflight

Status: PREFLIGHT_BLOCKED_BY_ROLE_CREATION_PRIVILEGE

Layer role: N6_user

Date: 2026-06-05

This preflight is read-only. It did not execute 037, write business rows,
consume/update outbox rows, start workers, modify N6_UI_v1, modify existing
APIs/projection/shadow pipeline, or run delivery/push/voice/mobile/sim/position/
real trade.

## 1. Target

Permission migration draft:

```text
sql/037_n6_view_readonly_permission.sql
```

Rollback draft:

```text
sql/037_n6_view_readonly_permission_rollback.sql
```

## 2. Current DB Proof

Target DB proof from read-only query:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1
port=5432
```

Role proof:

```text
ashare_v3_user rolcanlogin=true
ashare_v3_user rolcreaterole=false
ashare_v3_user rolsuper=false
n6_ui_readonly_role exists=false
```

036 object proof:

```text
5 Track B tables exist
5 N6 views exist
views non-internal trigger count=0
```

Current owner grant proof:

```text
ashare_v3_user still shows owner privileges on 036 tables/views
owner privileges are not the readonly proof target
```

## 3. Preflight Result

Current preflight status:

```text
PREFLIGHT_BLOCKED_BY_ROLE_CREATION_PRIVILEGE
```

Reason:

```text
n6_ui_readonly_role does not exist
ashare_v3_user cannot CREATE ROLE
```

Resolution options before execute:

```text
Option A: execute 037 with a DB role that has CREATEROLE
Option B: have a privileged DBA/session pre-create n6_ui_readonly_role NOLOGIN,
          then execute 037 as ashare_v3_user to apply grants
```

## 4. Expected Post-Execute Checks

After a future successful 037 execute, post-review must verify:

```text
n6_ui_readonly_role exists
n6_ui_readonly_role has SELECT on exactly the 5 N6 views
n6_ui_readonly_role has no INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER on the 5 views
n6_ui_readonly_role has no INSERT/UPDATE/DELETE/TRUNCATE on 5 Track B base tables
views have no INSTEAD OF trigger
036 tables still have row_count=0 unless a separate business gate inserted rows
no N5 outbox/status changes
```

## 5. Proof Queries

Role existence and executor capability:

```sql
SELECT rolname, rolcanlogin, rolcreaterole, rolsuper
FROM pg_roles
WHERE rolname IN (current_user, 'n6_ui_readonly_role')
ORDER BY rolname;
```

Readonly role grant proof:

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

## 6. Final Gate Recommendation

Allowed next step:

```text
runtime_control N6 037 view readonly permission final gate review
```

Execute should remain blocked until the role-creation blocker is resolved.
