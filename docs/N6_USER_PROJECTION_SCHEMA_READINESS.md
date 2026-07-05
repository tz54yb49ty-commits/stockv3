# N6 User Projection MVP Schema Readiness

## Summary

- result: SCHEMA_READINESS_PASS
- layer_role: N6_user
- scope: schema readiness / migration draft only
- schema draft: `sql/020_n6_user_projection_schema.sql`
- rollback draft: `sql/020_n6_user_projection_rollback.sql`
- execute: false
- database_write: false
- N5 outbox consumed: false
- user projection rows written: false
- worker_started: false
- actual push: false
- real_trade: false

## Read Inputs

- `AGENTS.md`
- `docs/Architecture.md`
- `docs/Roadmap.md`
- `docs/Tasks.md`
- `sql/014_condition_display_basis_schema.sql`
- `docs/N5_CURRENT_REAL_ACTION_EXECUTE_CONTRACT.md`
- `docs/N5_CURRENT_REAL_ACTION_EXECUTE_REPORT.md`

## Current Upstream Contract

N6 MVP may read N2 display-input tables:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`

Future N6 projection execution may consume only N5 standard pending outbox:

- `ActionEvent = 479`
- `HintEvent = 9`

It must not consume current `RiskEvent = 0`, `PositionEvent = 0`, N4 trigger events, N3 market events, or old synthetic outbox in this MVP path.

## New Tables

The schema draft adds these N6-owned tables:

- `user_account`
- `user_session`
- `user_filter_profile`
- `user_watchlist`
- `user_watchlist_item`
- `user_projection_run`
- `user_signal_projection`
- `user_signal_card`
- `user_signal_decision`
- `user_notification_queue`
- `user_sim_account`
- `user_sim_order`
- `user_sim_trade`
- `user_sim_position`

## Key Field Summary

`user_account`:

- `login_name` is unique.
- `password_hash` and `password_hash_algo` are required.
- `role` is constrained to `admin/user`.
- `status` is constrained to `active/disabled/deleted`.
- No plaintext password field exists.

`user_session`:

- Stores `session_token_hash`, not raw session token.
- Includes `expires_at` and `revoked_at`.

`user_filter_profile`:

- Stores MVP checkbox flags: chase, ultra-short, short, mid, long.
- Stores default strong-board rule JSON for year/quarter/month `volume_up`.

`user_projection_run`:

- Tracks N6 projection run id, `source_action_run_id`, `source_n5_outbox_range`, source event types, status, and P0/P1/P2 counts.

`user_signal_projection` and `user_signal_card`:

- Bind every projection to `user_id`.
- Preserve N5 trace fields: `source_event_id`, `source_action_event_id`, `source_action_run_id`, schema version, dedup key.
- Store `asset_kind`, `identity_key`, `code`, `name`, `direction`, `signal_type`, `target_price`, `current_price`, `expected_return_pct`, `board_code`, and `board_name`.
- Store optional N2 display-basis trace without writing back to N2.

`user_signal_decision`:

- Records `buy/sell/discard` intent only.
- Constrains `execution_mode = n6_intent_only`.
- Constrains `real_trade_status = not_applicable`.

`user_notification_queue`:

- Constrains queue status to `queued_only/suppressed/discarded/ready_for_future_push`.
- Represents a queue only; no provider delivery table or push execution is created.

`user_sim_*`:

- Provides shadow simulation schema only.
- `user_sim_account.initial_cash` defaults to `1000000000`.
- T+1 fields are reserved with `settlement_mode = T_PLUS_1`, `t_plus_one_locked`, `available_from_trade_date`, and locked quantity fields.
- Real trade flags are constrained to false.

## Index Summary

The draft adds indexes for:

- account role/status
- session user/expiry/revocation lookup
- default filter profile lookup by user
- watchlist and watchlist item lookup
- projection run source/status
- signal projection user/status/source/identity lookup
- signal card user/status/priority lookup
- signal decision user/type lookup
- notification queue user/status/source lookup
- sim account/order/trade/position lookup

## Strictly Additive Check

Passed:

- Schema draft only uses `CREATE TABLE IF NOT EXISTS`.
- Schema draft only uses `CREATE INDEX IF NOT EXISTS`.
- No `ALTER` statements.
- No `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, or `COPY` statements.
- No migration execution was performed.
- No database connection was made.
- No N5 outbox was consumed.
- No user projection rows were written.
- No worker, push, sim execution, or real trade was started.

## Boundary Gates

P0 blockers for any future N6 execution:

- consuming anything other than N5 `ActionEvent / HintEvent`;
- reading N4/N5 naked facts to replace event consumption;
- writing back to N1-N5;
- using C3 `MinuteBarClosed` or N4-C3 replay audit output as N6 input;
- writing real trade/order state;
- actual voice/mobile push;
- starting any worker without a separate gate.

## Rollback Strategy

Rollback draft: `sql/020_n6_user_projection_rollback.sql`.

The rollback checks every N6-owned table row count first. It only drops tables when all row counts are zero.

If any N6 business rows exist, rollback is blocked. In that case, first perform a separately reviewed N6 business rollback by `user_projection_run_id` and/or `sim_run_id`; only then may the schema rollback be used.

The rollback does not touch N1-N5 tables, N5 outbox, action facts, trigger facts, market data facts, voice/mobile delivery, or real trading state.

## Decision

SCHEMA_READINESS_PASS.

Allowed next gate: 020 migration review only.

Still blocked: migration execution, N5 outbox consumption, N6 execute, user projection row writes, worker, actual push, sim execution, position execution, and real trade.
