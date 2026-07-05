# N6 Phase 2 Owner Principal Initialization Preflight Draft

Status: PREFLIGHT_DRAFT_PASS

Layer role: N6_user

Date: 2026-06-05

This is a draft preflight contract only. It does not execute seed SQL, write
database rows, consume or update outbox rows, start workers, modify N6_UI_v1,
modify existing APIs, modify projection or shadow pipeline code, deliver
notifications, push to voice/mobile, run sim, create positions, or place real
trades.

## 1. Target Seed Run

```text
seed_run_id = n6_phase2_owner_principal_initialization_20260605_v1
policy_version = n6_phase2_owner_principal_seed_policy_v1
policy_hash = 8334cb658002542819d0c970138b0bb3b8f5d8dadb414777408fcbd6aac6a8c4
```

## 2. Required Preflight Checks

### 2.1 036 Object Readiness

All 036 tables must exist:

```text
n6_principal
n6_ai_user
n6_principal_account
n6_watchlist_ownership
n6_strategy
```

All 036 views must exist:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

All 036 seed-target tables must have baseline row_count=0 before the first seed
execute for this phase:

```text
n6_principal = 0
n6_ai_user = 0
n6_principal_account = 0
n6_watchlist_ownership = 0
n6_strategy = 0
```

### 2.2 037 Readonly Permission Proof

`n6_ui_readonly_role` must exist.

The role must have exactly `SELECT` on the five `v_n6_*` views:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

The role must have no privileges on:

```text
n6_principal
n6_ai_user
n6_principal_account
n6_watchlist_ownership
n6_strategy
```

The five views must have no non-internal triggers and no `INSTEAD OF` trigger.

### 2.3 Admin User Readiness

Preflight must confirm exactly one active admin bootstrap account:

```text
user_account.login_name = admin
user_account.role = admin
user_account.status = active
```

The check must not select or report `password_hash`.

### 2.4 Seed Scoped Baseline

There must be no existing rows with this seed run id in any seed target JSON
field:

```text
n6_principal.principal_policy_json->>'seed_run_id'
n6_principal_account.account_policy_json->>'seed_run_id'
n6_strategy.strategy_payload_json->>'seed_run_id'
n6_ai_user.readable_scope_policy->>'seed_run_id'
```

There must be no duplicate seed keys:

```text
phase2_admin_principal__user_account_admin
phase2_system_principal__n6_system
phase2_admin_shadow_account__admin_principal
```

There must be no duplicate owner principal:

```text
n6_principal(principal_type='admin', owner_user_id=<admin user_id>)
n6_principal(principal_type='system')
```

### 2.5 AI Guard

Preflight must confirm:

```text
no active AI principal is created by this seed
no active AI principal exists without n6_ai_user profile
no n6_ai_user.status='active' row is inserted by this seed
no AI decision runner exists for this seed_run_id
no AI evaluation exists for this seed_run_id
no virtual_intent exists for this seed_run_id
```

If a future final gate includes the optional reserved AI principal, it must use
the compatibility status mapping:

```text
n6_principal.principal_status = system_reserved
n6_ai_user.status = sandbox_only
```

### 2.6 Outbox and Side-Effect Guard

Preflight must confirm no planned or actual writes to:

```text
common_event_outbox
common_event_inbox
common_event_consumer_checkpoint
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
user_signal_decision
user_session
user_watchlist
user_watchlist_item
user_sim_account
user_sim_order
user_sim_trade
user_sim_position
common_position_state
common_position_event
```

Preflight must confirm:

```text
worker_started = false
delivery = false
push = false
voice = false
mobile = false
sim = false
position = false
real_trade = false
```

## 3. Suggested Proof Queries

Object existence:

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

Readonly role grants:

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

Admin account proof without password hash:

```sql
SELECT user_id, login_name, role, status
FROM user_account
WHERE login_name = 'admin';
```

Seed scoped baseline:

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
SELECT 'n6_strategy', count(*)
FROM n6_strategy
WHERE strategy_payload_json->>'seed_run_id' = 'n6_phase2_owner_principal_initialization_20260605_v1';
```

## 4. Blockers

Preflight must BLOCK if any of these are true:

```text
036 table missing
036 view missing
037 readonly role proof fails
admin account missing, disabled, deleted, non-admin, or duplicated
any 036 target table baseline is nonzero for first Phase 2 seed
seed_run_id already exists in target JSON fields
duplicate admin/system principal exists
active AI principal would be created
active AI exists without profile
outbox/inbox/checkpoint write is planned
N6_UI_v1/API/projection/shadow-pipeline modification is planned
delivery/push/voice/mobile/sim/position/real_trade is planned
```

## 5. Final Gate Requirement

This draft does not authorize execute. A future execute final gate must provide:

```text
exact seed SQL or runner path
fresh preflight PASS
allowed write scope limited to n6_principal and optionally n6_principal_account
post-execute generated principal_id/account_id report
rollback SQL path
boundary proof
```
