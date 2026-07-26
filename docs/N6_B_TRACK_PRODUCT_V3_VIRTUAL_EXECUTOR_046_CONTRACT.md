# N6 B-track Product V3 virtual executor 046 contract

Status: implementation draft only. Migration, DB connection, runtime, scheduler,
8786, feature activation, staging, and commit are not authorized by this gate.

## Interface

`public.n6_executor_apply_claimed_proposal(bigint,text)` accepts only a claimed
`proposal_id` and its `executor_run_id`. It is `SECURITY DEFINER`, uses
`search_path=pg_catalog`, and is executable only by `n6_virtual_executor`.
PUBLIC and `n6_btrack_web` are explicitly revoked. The executor retains zero
direct table and sequence privileges.

The caller cannot supply price, quantity, account, position, principal, asset,
side, or trade date. The function locks and revalidates the unexpired processing proposal,
principal/account/current cash snapshot/current position, a fresh passed N6
quote, and T+1 lots before any write.

## Execution policy

- stock SH/SZ only; BJ, index, board, nonfinite/nonpositive/not-ready/stale quote
  and `source_type=stop_loss` fail closed;
- latest N6 passed quote and fetch time must both be within two minutes, on the
  current Asia/Shanghai open trade date, and inside 09:30–11:30 or 13:00–15:00;
- buy quantity is `floor(min(CNY 300,000, available_cash) / fresh_quote / 100)
  * 100`; cash below CNY 300,000 automatically scales down and capacity below
  one 100-share lot fails closed;
- first/reopened signal buy freezes the proposal target price and source signal
  projection onto the position; same-episode adds preserve the existing freeze;
- first/reopened buy sets stop loss to `provisional_first_day`; reopen clears all
  old stop-loss price/source/frozen/effective/policy fields, while same-episode
  adds preserve them;
- sell quantity is all currently T+1-sellable lots, allocated FIFO across lots;
- every sell requires a non-null proposal holding episode exactly equal to the
  locked current position episode; null or stale-episode proposals perform zero
  writes and return `holding_episode_mismatch`;
- matured `locked_t1` lots are locked, reconciled to position quantity, promoted
  atomically, and then sold; unavailable future lots remain locked;
- the function locks every active cash snapshot for the account and requires
  exact-one equal to `account.current_cash_snapshot_id`; a future-dated pointer
  or any hidden active snapshot fails closed;
- zero fee/tax is explicit policy v1;
- position-event sell `cost_delta` is the negative removed cost basis
  (`average_cost × filled_quantity`), never sale proceeds;
- one function statement atomically writes order, trade, cash ledger, active
  cash snapshot, lot, position, and position event, then marks the proposal
  executed;
- after inserting the position event, the same transaction updates
  `position.source_position_event_id` to that event and requires exactly one
  updated position row; mismatch raises and rolls back the entire chain;
- order writes `source_signal_projection_id` directly from the proposal, giving
  signal executions a canonical order-to-projection foreign key while
  manual-position executions remain NULL; trade lineage remains proposal,
  signal-reference, and quote-snapshot based;
- unique `source_proposal_id`, proposal row locking, and replay return make
  sequential and concurrent retries idempotent;
- validation failure performs zero DML; SQL failure rolls back the full statement.

No broker/real trade, outbox, N1-N5, projection, monitor, realtime, voice,
mobile, delivery, or feature-flag DML exists in 046.

## Runner and rollback

`run_n6_virtual_executor_once.py` is a KeepAlive=false one-shot. Without
`--execute` it emits a read-only preflight/plan, opens no DB connection, never
calls the 042 claim function, and performs zero DML. Every claim changes
proposal state and belongs only to the explicit execute transaction.

With `--execute`, one outer transaction calls 042 claim and only after a
successful claim calls 046 apply on the same connection. The 046 function
itself performs the trigger-authorized
executor transition `processing -> executed`, so a separate 042 finish call is
neither required nor allowed after success. A rejected apply explicitly rolls
back the outer transaction, and any Python/SQL/process exception before commit
also rolls it back; therefore the claim cannot be left as a half-completed
`processing` proposal. A failed/not-claimed claim returns immediately without
calling apply. Direct replay of an already executed proposal returns the
existing order/trade; runner replay fails closed at claim. Neither path can
insert a second fill.

Runtime credentials are fail-closed. The runner has no `--dsn` option and
accepts execute only when `PGSERVICE` is exactly `n6_virtual_executor`.
`PGSERVICEFILE` and `PGPASSFILE` must be existing runtime-provided absolute path
settings and are passed through for libpq to resolve; the runner never opens or
reads either file. `PGPASSWORD`, custom DSN/password variables, and other `PG*`
connection overrides are rejected. The connection string is the constant
`service=n6_virtual_executor`, with autocommit disabled. Read-only preflight
returns before any credential validation or connection attempt. No credential
or secret is accepted through argv.

Rollback revokes and drops only the 046 function. It preserves all business
history and all 041-045 objects.
