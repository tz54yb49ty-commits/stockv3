# N6 Multi User and AI Owner Principal Schema Rollback Draft

Status: ROLLBACK_DRAFT_PASS

Layer role: N6_user

Date: 2026-06-04

Rollback draft:

```text
sql/036_n6_multi_user_ai_owner_principal_schema_rollback.sql
```

This rollback is a draft artifact only. It was not executed and did not write
the database.

## 1. Rollback Scope

The rollback draft only targets objects created by:

```text
sql/036_n6_multi_user_ai_owner_principal_schema.sql
```

Rollback target views:

```text
v_n6_board_membership_fact
v_n6_index_membership_fact
v_n6_board_condition_display_basis
v_n6_index_condition_display_basis
v_n6_stock_condition_display_basis
```

Rollback target tables:

```text
n6_strategy
n6_watchlist_ownership
n6_principal_account
n6_ai_user
n6_principal
```

## 2. Hard-Fail Guard

The rollback draft hard-fails before the first `DROP` if any target Track B
table has business rows:

```text
n6_strategy
n6_watchlist_ownership
n6_principal_account
n6_ai_user
n6_principal
```

Guard behavior:

```text
if table does not exist: skip safely
if table exists and row_count=0: rollback may continue
if table exists and row_count>0: RAISE EXCEPTION and stop before DROP
```

The rollback draft does not use `CASCADE`. If a future dependent object exists,
PostgreSQL dependency checks must stop the rollback rather than silently
removing dependent objects.

## 3. Drop Order

Views are dropped before tables:

```text
v_n6_board_membership_fact
v_n6_index_membership_fact
v_n6_board_condition_display_basis
v_n6_index_condition_display_basis
v_n6_stock_condition_display_basis
```

Tables are dropped in dependency-safe order:

```text
n6_strategy
n6_watchlist_ownership
n6_principal_account
n6_ai_user
n6_principal
```

## 4. Forbidden Scope

The rollback draft does not target:

```text
user_account
user_session
user_watchlist
user_watchlist_item
user_sim_account
user_sim_order
user_sim_trade
user_sim_position
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
N5 outbox
N5 inbox/checkpoint
N1-N5 facts
common_position_*
```

The rollback draft does not perform business DML against upstream or existing
N6 tables.

## 5. Review Notes

Before any future rollback execution, runtime_control should verify:

```text
target database proof
all Track B target tables row_count=0
no dependent future Track B objects exist
no CASCADE
rollback SQL still references only 036-created objects
N5 outbox and N1-N5 facts are out of scope
```

## 6. Next Gate

Allowed next step:

```text
runtime_control N6 owner/principal SQL migration draft review gate
```

Executing rollback remains blocked until a separate explicit rollback execute
gate.
