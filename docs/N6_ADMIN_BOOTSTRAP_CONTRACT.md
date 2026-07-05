# N6 Admin Bootstrap Contract Review

## Summary

- result: REVIEW_PASS
- layer_role: N6_user
- scope: admin bootstrap contract / CLI design / rollback draft only
- execute: false
- database_write: false
- admin_initialized: false
- user_account_written: false
- user_session_written: false
- N5 outbox consumed: false
- user projection rows written: false
- sim rows written: false
- worker_started: false
- actual push: false
- real_trade: false

## Background

020 N6 user projection schema migration has passed post-review. The 14 N6-owned tables exist and are empty. N5 outbox is unchanged and remains pending:

- `ActionEvent = 479`
- `HintEvent = 9`

This contract designs the first admin bootstrap path only. It does not authorize bootstrap execution.

## Bootstrap Goal

Create exactly one initial administrator account for N6 MVP:

- `login_name = admin`
- `role = admin`
- `status = active`
- password stored only as `password_hash` and `password_hash_algo`
- one default `user_filter_profile` for that admin

The bootstrap must not create sessions, projections, decisions, notification queue rows, sim rows, or consume any N5 event.

## CLI Design

Future runner target:

```text
python -m ashare_v3.user.bootstrap_admin
```

MVP CLI behavior:

- Default and only MVP `login_name` is `admin`.
- The runner must require an explicit PostgreSQL DSN through `ASHARE_V3_POSTGRES_DSN`.
- The initial password must come from exactly one of:
  - environment variable `ASHARE_V3_N6_ADMIN_PASSWORD`
  - interactive `getpass` prompt when a TTY is available
- The password must not be accepted through a command-line argument because process lists and shell history can leak it.
- The runner must not print, log, persist, or include the password in exceptions.
- The runner must print only redacted status such as `BLOCKED`, `EXECUTED`, table names, and row counts.

No password value or example password may be written into source code, docs, JSON reports, tests, command logs, or migration reports.

## Password Hashing Contract

The runner must hash the password before writing `user_account`.

Preferred:

```text
argon2id
```

Fallback only if argon2 dependencies are unavailable:

```text
bcrypt
```

Stored fields:

- `password_hash`
- `password_hash_algo`
- `password_updated_at`

Forbidden fields and outputs:

- plaintext password column
- raw password in logs
- raw password in JSON reports
- raw password in exceptions
- reversible encryption

Recommended minimum checks before hashing:

- password is non-empty
- password length is at least 12 characters
- password is not equal to `admin`
- password is not equal to `login_name`

## Idempotency And Blocking Rules

The runner must execute the final existence check and insert in one database transaction.

P0 blocking rules:

- If `user_account.login_name = 'admin'` exists with `status = active`, return `BLOCKED` and do not overwrite the password.
- If `user_account.login_name = 'admin'` exists with `status IN ('disabled', 'deleted')`, return `BLOCKED` and require manual handling.
- If any `user_account` row already exists in MVP bootstrap, return `BLOCKED` because this is an initial-admin-only path.
- If `user_filter_profile` already contains rows, return `BLOCKED` because the bootstrap must create the first default profile itself.
- If argon2id and bcrypt are both unavailable, return `BLOCKED`.
- If the password source is missing or ambiguous, return `BLOCKED`.
- If `user_account` or `user_filter_profile` schema checks fail, return `BLOCKED`.

No idempotent rerun may update, rotate, or reset an existing admin password. Password reset must be a separate contract.

## Allowed Write Scope

When a future execute gate explicitly authorizes bootstrap, the runner may write only:

1. One `user_account` row:
   - `login_name = admin`
   - `role = admin`
   - `status = active`
   - `password_hash`
   - `password_hash_algo`
   - `display_name` may be `Initial Admin`
   - `user_policy_json` may store non-secret bootstrap metadata

2. One `user_filter_profile` row for that admin:
   - `profile_name = MVP default`
   - `is_default = true`
   - `enable_chase = true`
   - `enable_ultra_short = true`
   - `enable_short = true`
   - `enable_mid = true`
   - `enable_long = true`
   - `permission_scope = self`
   - `status = active`
   - `strong_board_rule_json` keeps the MVP year/quarter/month `volume_up` rule

The two inserts must commit atomically. If either insert fails, the transaction must roll back.

## Forbidden Scope

The bootstrap must not:

- initialize admin in this contract-review phase
- write `user_session`
- write `user_projection_run`
- write `user_signal_projection`
- write `user_signal_card`
- write `user_signal_decision`
- write `user_notification_queue`
- write `user_watchlist` or `user_watchlist_item`
- write `user_sim_account`, `user_sim_order`, `user_sim_trade`, or `user_sim_position`
- consume N5 outbox
- update N5 outbox status
- read or write N4/N5 naked facts as a replacement for events
- write back N1/N2/N3/N4/N5
- start worker
- send voice/mobile push
- create session tokens
- place real trades

## Safety Checks

Preflight checks for a future runner:

1. Confirm `ASHARE_V3_POSTGRES_DSN` is set.
2. Confirm 020 N6 schema tables exist:
   - `user_account`
   - `user_filter_profile`
   - `user_session`
   - `user_projection_run`
   - `user_signal_projection`
   - `user_signal_card`
   - `user_signal_decision`
   - `user_notification_queue`
   - `user_sim_account`
   - `user_sim_order`
   - `user_sim_trade`
   - `user_sim_position`
   - `user_watchlist`
   - `user_watchlist_item`
3. Confirm `user_account` contains no rows.
4. Confirm `user_filter_profile` contains no rows.
5. Confirm `user_session`, projection, notification, watchlist, and sim tables contain no rows.
6. Confirm N5 outbox counts are unchanged before and after bootstrap:
   - `ActionEvent pending = 479`
   - `HintEvent pending = 9`
7. Confirm `password_hash` and `password_hash_algo` are present and no plaintext password column exists.
8. Confirm exactly one password input source is provided.
9. Confirm hash generation succeeds before insert.
10. Confirm post-write row counts:
   - `user_account = 1`
   - `user_filter_profile = 1`
   - all other N6 tables remain `0`

## Rollback Strategy

Rollback draft:

```text
sql/N6_admin_bootstrap_rollback.sql
```

The rollback is a business rollback for the future admin bootstrap only. It is not a schema rollback.

It may be used only if:

- exactly one `user_account` row exists
- that row is `login_name = admin`, `role = admin`, `status = active`
- exactly one default `user_filter_profile` exists for that admin
- no `user_session` rows exist
- no watchlist rows exist
- no projection rows exist
- no signal decision rows exist
- no notification queue rows exist
- no sim rows exist
- no other N6 business rows exist

Rollback deletes only:

1. the default `user_filter_profile` for admin
2. the admin `user_account` row

Rollback must not touch N1-N5, N5 outbox, action facts, trigger facts, market data facts, voice/mobile delivery, or real trading state.

If any N6 business rows exist after bootstrap, this rollback is blocked and a separate business rollback contract is required.

## Decision

REVIEW_PASS.

Allowed next gate:

```text
admin bootstrap runner implementation
```

Still blocked:

- admin bootstrap execute
- writing `user_account`
- writing `user_filter_profile`
- creating sessions
- N5 outbox consumption
- user projection execution
- worker
- actual push
- sim execution
- real trade
