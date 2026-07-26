# N6 Human Virtual Account Provisioning 074 Contract

## Gate identity

```text
layer_role=N6_user
mode=FULL
risk=high
implementation_base=78bea7c61e560d01cb781b07f682ffc17e0125c8
migration=074
run_id=n6_human_virtual_account_provisioning_074_v1
initial_cash=100000000.0000 CNY
```

This gate separates `user_sim_account` from the N6 B-track chain. The former is the existing Web shadow-simulation account; the latter is the principal-owned chain `n6_virtual_account -> n6_virtual_cash_ledger/n6_virtual_cash_snapshot` plus `n6_principal_account` mapping. Neither one proves the other exists.

## Execution DAG and kernel decision

```text
PLAN -> VALIDATE -> MODIFY -> VERIFY -> FINALIZE
```

Kernel decision is `ACCEPT` only for N6-owned schema function, runner, Web transaction integration, UI copy, contract, and tests in the reviewed allowlist. Migration execution, live backfill, deployment, executor/scheduler/LaunchAgent changes, proposal/order/trade/position/lot/outbox writes, and real trading remain rejected. `blocked_by_layer=none` for this implementation gate.

## Provisioning invariant

`public.n6_provision_human_virtual_account(principal_id)` is the only write primitive. It is owned by `ashare_v3_user`, is `SECURITY DEFINER`, fixes `search_path=pg_catalog`, revokes `PUBLIC`, and grants execute only to `n6_btrack_web`.

For one active `human_user` principal owned by one active Web user with `role=user`, a successful create atomically writes exactly:

- one active `n6_virtual_account` with CNY 100,000,000 initial cash;
- one active `n6_principal_account` mapping;
- one `initial_deposit` cash-ledger row for CNY 100,000,000;
- one active cash snapshot for CNY 100,000,000;
- the account `current_cash_snapshot_id` pointing at that snapshot.

It writes zero proposal, order, trade, position, position-lot, position-event, PnL, event-ledger, outbox, or inbox rows. A complete valid existing chain returns `noop`. A partial, duplicated, inactive, mismatched, or otherwise drifted chain raises and rolls back the entire transaction.

## New users

`PostgresN6UserRepository.create_user_with_defaults` creates the Web user, N6 principal, filter profile, separate `user_sim_account`, and (for `role=user`) calls the fixed provisioning function as the final operation in the same transaction. A provisioning error rolls back every new-user row. Admin principals are not human B-track targets and remain `not_applicable`.

## Existing-user backfill

The bounded runner defaults to read-only dry-run. Its only authorized execute set is exact and indivisible:

```text
principal_id=8 login_name=csl666
principal_id=9 login_name=csl888
```

Execute requires `--execute --execute-authorized --principal-id 8 --principal-id 9`. A changed identity, inactive owner/principal, missing target, partial chain, extra/missing target, or function error blocks and rolls back the batch. Deployment and execute require separate gates; this implementation gate performs neither.

## Rollback contract

Rollback is a separate, explicit gate. It locks the account/cash/downstream/event relations and only removes pristine rows carrying the exact 074 run, policy, hash, and lineage markers. It clears `current_cash_snapshot_id`, then deletes the snapshot, ledger, mapping, and account before removing function privileges and the function.

Any direct downstream reference or recursive JSON reference in common event ledger/outbox/inbox makes rollback `BLOCKED`. Any provenance, ownership, count, cash, status, pointer, or mapping drift also makes the whole rollback `BLOCKED`; it never partially cleans up and never deletes pre-existing chains.

## Verification and gates

- Targeted unit/static tests cover SQL authority, atomic chain shape, idempotent `noop`, fail-closed partial state, runner authorization, Web same-transaction ordering/rollback, API counts, and UI text.
- PostgreSQL integration tests require an explicitly marked disposable database. They must never target live `ashare_v3`.
- Full N6 regression must pass before commit review.
- Commit, migration execute, backfill execute, deployment, and live read-only acceptance are independent later gates.

The account empty state is intentionally explicit: `账户尚未初始化，请联系管理员`. It must not imply executor or scheduler status.
