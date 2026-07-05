# N6 Phase 2 Owner Principal Initialization Execute Preflight

Status: EXECUTE_PREFLIGHT_CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-05

This preflight artifact defines checks required before a future execute. It is
not a database proof and does not execute the seed.

## 1. Required Checks

Preflight must confirm:

```text
036 tables exist:
  n6_principal
  n6_ai_user
  n6_principal_account
  n6_watchlist_ownership
  n6_strategy

036 views exist:
  v_n6_stock_condition_display_basis
  v_n6_index_condition_display_basis
  v_n6_board_condition_display_basis
  v_n6_index_membership_fact
  v_n6_board_membership_fact

037 readonly permission proof passed:
  n6_ui_readonly_role exists
  role has exactly SELECT on the 5 v_n6_* views
  role has no grants on the 5 n6_* base tables
  5 views have no non-internal trigger

admin account:
  exactly one user_account row where login_name='admin'
  role='admin'
  status='active'
  password_hash is not selected or reported

seed baseline:
  target seed_run_id scoped rows = 0
  no duplicate admin principal for admin owner_user_id
  no duplicate system principal
  no active AI without n6_ai_user profile

planned rows:
  n6_principal = 2
  n6_principal_account = 0
  n6_ai_user = 0
  n6_watchlist_ownership = 0
  n6_strategy = 0

side effects:
  outbox refs = 0
  worker/downstream/side-effect refs = 0
```

## 2. Blockers

Preflight must BLOCK on:

```text
missing 036 table or view
037 readonly proof failure
admin missing, duplicate, disabled, deleted, or not role=admin
seed scoped baseline nonzero
duplicate admin principal
duplicate system principal
active AI without profile
planned rows mismatch
any planned write outside n6_principal
outbox/inbox/checkpoint write plan
worker/delivery/push/voice/mobile/sim/position/real_trade plan
```

## 3. Runner Probe

The runner must also enforce:

```text
missing --execute -> BLOCKED
missing --user-confirmed -> BLOCKED
contract status not CONTRACT_PASS -> BLOCKED
contract seed_run_id mismatch -> BLOCKED
contract planned rows mismatch -> BLOCKED
```

## 4. Proof Query Set

These are the minimum SQL probes for the future final gate:

```sql
SELECT c.relname, c.relkind
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN (
    'n6_principal',
    'n6_ai_user',
    'n6_principal_account',
    'n6_watchlist_ownership',
    'n6_strategy',
    'v_n6_stock_condition_display_basis',
    'v_n6_index_condition_display_basis',
    'v_n6_board_condition_display_basis',
    'v_n6_index_membership_fact',
    'v_n6_board_membership_fact'
  )
ORDER BY c.relname;
```

```sql
SELECT table_name, privilege_type
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

```sql
SELECT user_id, login_name, role, status
FROM user_account
WHERE login_name = 'admin';
```

```sql
SELECT 'n6_principal' AS table_name, count(*) AS row_count
FROM n6_principal
WHERE principal_policy_json->>'seed_run_id' = 'n6_phase2_owner_principal_initialization_20260605_v1'
UNION ALL
SELECT 'n6_principal_account', count(*)
FROM n6_principal_account
WHERE account_policy_json->>'seed_run_id' = 'n6_phase2_owner_principal_initialization_20260605_v1'
UNION ALL
SELECT 'n6_ai_user', count(*)
FROM n6_ai_user
WHERE readable_scope_policy->>'seed_run_id' = 'n6_phase2_owner_principal_initialization_20260605_v1'
UNION ALL
SELECT 'n6_watchlist_ownership', count(*)
FROM n6_watchlist_ownership
WHERE ownership_policy_json->>'seed_run_id' = 'n6_phase2_owner_principal_initialization_20260605_v1'
UNION ALL
SELECT 'n6_strategy', count(*)
FROM n6_strategy
WHERE strategy_payload_json->>'seed_run_id' = 'n6_phase2_owner_principal_initialization_20260605_v1';
```

## 5. Boundary

This preflight does not authorize execute. Execution requires an explicit user
confirmation and the command frozen in the execute contract.
