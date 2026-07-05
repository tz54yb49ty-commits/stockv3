# N6 Phase 3 Virtual Account Seed Execute Preflight

Status: EXECUTE_PREFLIGHT_CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-05

This preflight artifact defines checks required before a future execute. It is
not a database proof and does not execute the seed.

## 1. Required Checks

Preflight must confirm:

```text
Phase 3 schema foundation complete:
  n6_virtual_account
  n6_virtual_cash_ledger
  n6_virtual_cash_snapshot
  n6_virtual_order
  n6_virtual_trade
  n6_virtual_position
  n6_virtual_position_event
  n6_virtual_pnl_snapshot

Phase 3 target row baseline:
  n6_virtual_account = 0
  n6_virtual_cash_ledger = 0
  n6_virtual_cash_snapshot = 0
  n6_virtual_order = 0
  n6_virtual_trade = 0
  n6_virtual_position = 0
  n6_virtual_position_event = 0
  n6_virtual_pnl_snapshot = 0

seed_run_id scoped rows = 0 in all Phase 3 tables

admin principal:
  exactly one n6_principal row with principal_type='admin'
  principal_status='active'
  linked user_account.login_name='admin'
  linked user_account.status='active'

system principal:
  exactly one n6_principal row with principal_type='system'
  principal_status='system_reserved'
  not selected for virtual account

admin active virtual account:
  count = 0

037 readonly permission proof:
  n6_ui_readonly_role exists
  role has exactly SELECT on the 5 v_n6_* views
  role has no grants on n6 Track B owner/principal base tables
  views have no non-internal trigger

side effects:
  outbox refs = 0
  worker/downstream refs = 0
```

## 2. Blockers

Preflight must BLOCK on:

```text
Phase 3 table missing
any Phase 3 table baseline nonzero
seed_run_id scoped rows nonzero
admin principal missing, duplicate, disabled, deleted, or not linked to active admin user
system principal missing or duplicate
admin active virtual account already exists
037 readonly proof failure
view trigger count nonzero
outbox/inbox/checkpoint refs nonzero
worker/downstream/side-effect refs nonzero
planned rows mismatch
any planned write outside n6_virtual_account / n6_virtual_cash_ledger / n6_virtual_cash_snapshot
```

## 3. Runner Probe

The runner must also enforce:

```text
missing --execute -> BLOCKED
missing --user-confirmed -> BLOCKED
contract result not CONTRACT_PASS -> BLOCKED
contract seed_run_id mismatch -> BLOCKED
contract planned rows mismatch -> BLOCKED
contract policy hash mismatch -> BLOCKED
```

## 4. Minimum Proof Query Set

These are the minimum SQL probes for the future final gate:

```sql
SELECT c.relname, c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN (
    'n6_virtual_account',
    'n6_virtual_cash_ledger',
    'n6_virtual_cash_snapshot',
    'n6_virtual_order',
    'n6_virtual_trade',
    'n6_virtual_position',
    'n6_virtual_position_event',
    'n6_virtual_pnl_snapshot'
  )
ORDER BY c.relname;
```

```sql
SELECT 'n6_virtual_account' AS table_name, count(*) AS row_count FROM n6_virtual_account
UNION ALL SELECT 'n6_virtual_cash_ledger', count(*) FROM n6_virtual_cash_ledger
UNION ALL SELECT 'n6_virtual_cash_snapshot', count(*) FROM n6_virtual_cash_snapshot
UNION ALL SELECT 'n6_virtual_order', count(*) FROM n6_virtual_order
UNION ALL SELECT 'n6_virtual_trade', count(*) FROM n6_virtual_trade
UNION ALL SELECT 'n6_virtual_position', count(*) FROM n6_virtual_position
UNION ALL SELECT 'n6_virtual_position_event', count(*) FROM n6_virtual_position_event
UNION ALL SELECT 'n6_virtual_pnl_snapshot', count(*) FROM n6_virtual_pnl_snapshot;
```

```sql
SELECT p.principal_id, p.principal_type, p.principal_status, p.owner_user_id, u.login_name, u.status
FROM n6_principal p
JOIN user_account u ON u.user_id = p.owner_user_id
WHERE p.principal_type = 'admin'
  AND u.login_name = 'admin';
```

```sql
SELECT count(*) AS system_principal_count
FROM n6_principal
WHERE principal_type = 'system'
  AND principal_status = 'system_reserved';
```

```sql
SELECT table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public'
  AND grantee = 'n6_ui_readonly_role'
ORDER BY table_name, privilege_type;
```

## 5. Status

This preflight contract is ready for runtime_control final gate review. The
future execute gate must still refresh these checks against the live database
before allowing any write.
