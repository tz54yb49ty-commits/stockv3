# N6 B-track Product V3 multi-user virtual-account bootstrap 047

Status: exact-eight-file implementation draft. Database connection, migration,
rollback, runtime activation, staging and commit are not authorized by this
gate.

## Scope

047 bootstraps one active N6 virtual account for each active human authority.
Principal 1 is the existing admin authority. Principals 3, 4, 5 and 6 are the
human authorities registered by 043. A target must resolve to exactly one
active `admin` or `human_user` principal whose active `user_account` owner has
the same id. `system`, `ai_user`, inactive, disabled, deleted and
`system_reserved` authorities fail closed.

The only row-DML targets are:

- `n6_virtual_account`
- `n6_virtual_cash_ledger`
- `n6_virtual_cash_snapshot`

No monitor, realtime scope, projection, quote, proposal, order, trade,
position, lot, position-event, PnL, outbox, inbox or checkpoint row is created
or changed. The migration does not invoke an executor, worker, scheduler,
market-data path or N1-N5 path.

## Cash bootstrap

Principals 3, 4, 5 and 6 must have no virtual-account row before first
execution. Each receives its own active CNY account with
`initial_cash=100000000.0000`, one `initial_deposit` ledger, one active cash
snapshot, and an account pointer to that snapshot.

Principal 1 must have exactly the audited Phase 3 admin account: one original
`initial_deposit` ledger and one current active snapshot for
`1000000.0000`, with no proposal, order, trade, position, lot,
position-event or PnL dependency. 047 never updates or deletes the original
ledger, never changes the account's original `initial_cash`, and never changes
old snapshot cash values or provenance. It adds a separate
`adjustment=99000000.0000` ledger and a new `100000000.0000` snapshot. The
only permitted change to the old snapshot is the cash-authority lifecycle
transition from `active` to `superseded`.

After execution every target has exactly one active account, exactly one active
cash snapshot, and an account pointer equal to that snapshot.

## Idempotency and concurrency

The migration is one transaction. It takes one transaction-scoped advisory
lock, locks target `n6_principal` rows with `FOR UPDATE`, and locks the
account/cash and dependency tables. Exactly-one account and cash authority are
checked inside the same transaction before and after controlled DML. 047 does
not create an index or constraint and does not alter the 038A/038B schema
contract. An exact completed rerun produces zero row DML. Partial state,
marker drift, role/status drift, account contamination or cash-authority
ambiguity raises before new business rows are committed.

## One-shot boundary

Running `scripts/run_n6_virtual_account_bootstrap_once.py` without `--execute`
performs a local contract/file plan only. It makes zero database connections.

Execution additionally requires `--user-confirmed`, the exact libpq service
`PGSERVICE=ashare_v3_owner`, `PGSERVICEFILE`, `PGPASSFILE`, exact database
`ashare_v3`, and database, session and current owner identity
`ashare_v3_user`. Both file variables must be absolute paths without NUL, CR or
LF; the planner does not read their contents and does not print their paths.
The CLI has no DSN or password option. Password/DSN environment variables are
rejected before connection, and connection secrets are never included in
output.

The fixed owner service and its credentials still require a later
`runtime_control` credential-provisioning and connection preflight gate. This
implementation does not assert that the service currently exists and does not
authorize execute.

## Rollback boundary

Human accounts can be physically removed only when account, seed ledger and
snapshot have exact 047 provenance and there is no later cash row or business
dependency. Sequences are never lowered.

Admin top-up history is never deleted or rewritten. Rollback is blocked by
default. A separately approved rollback may set
`n6.bootstrap_047_allow_admin_reverse_adjustment=true`; only then may rollback append a
negative adjustment ledger and a new `1000000.0000` snapshot after proving the
047 snapshot is still current and no later dependency exists. This explicit
override is a future execute gate, not authorization in this implementation
gate.
