# N6 Phase 3 Virtual Account Seed Execute Contract

Status: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-05

This contract freezes the executable boundary for the first Phase 3 virtual
account seed. It does not execute the runner, write database rows, consume or
update outbox rows, start workers, modify N6_UI_v1, modify existing APIs,
modify projection or shadow pipelines, deliver notifications, push to voice or
mobile, run sim, materialize positions, or place real trades.

## 1. Basis

Source artifacts:

```text
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SEED_OPERATION_DESIGN.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SEED_OPERATION_DESIGN.json
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SEED_OPERATION_TRACEABILITY.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SEED_OPERATION_TRACEABILITY.json
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_FOUNDATION_CLOSEOUT.md
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_FOUNDATION_CLOSEOUT.json
runtime_control design review APPROVED
```

Schema references:

```text
sql/038A_n6_virtual_account_schema.sql
sql/038B_n6_virtual_cash_schema.sql
sql/038C_n6_virtual_order_trade_schema.sql
sql/038D_n6_virtual_position_schema.sql
sql/038E_n6_virtual_pnl_schema.sql
```

## 2. Seed Identity

```text
seed_run_id = n6_phase3_virtual_account_seed_20260605_v1
policy_version = n6_phase3_virtual_account_seed_policy_v1
policy_hash = b85a7bc71353a5ccfe0479fa67f2b403e91eb3f2fa1a0ba89ebddfb6f5cd4377
rollback_scope = n6_phase3_virtual_account_seed_20260605_v1
created_by_gate = N6_PHASE3_VIRTUAL_ACCOUNT_SEED_EXECUTE_CONTRACT_GATE
rollback_sql = sql/N6_phase3_virtual_account_seed_rollback.sql
```

## 3. Planned Writes

The future execute path may write only:

| Table | Planned rows |
|---|---:|
| `n6_virtual_account` | 1 |
| `n6_virtual_cash_ledger` | 1 |
| `n6_virtual_cash_snapshot` | 1 |
| `n6_virtual_order` | 0 |
| `n6_virtual_trade` | 0 |
| `n6_virtual_position` | 0 |
| `n6_virtual_position_event` | 0 |
| `n6_virtual_pnl_snapshot` | 0 |

No other table is in scope.

## 4. Seed Policy

```text
principal = admin
initial_cash = 1000000.0000
currency = CNY
ledger_type = initial_deposit
virtual_account_status = active
cash_snapshot_status = active
quality_status = passed
```

`initial_cash` is a policy value, not a schema constant and not a market rule.
Fee, tax, T+1, execution, valuation, order, trade, position, and PnL policies
remain out of scope until separate gates.

## 5. Write Semantics

The future runner must use a single transaction:

```text
1. insert n6_virtual_account
2. insert n6_virtual_cash_ledger
3. insert n6_virtual_cash_snapshot
4. update n6_virtual_account.current_cash_snapshot_id = created snapshot id
```

The account pointer update is scoped to the newly inserted account row in the
same transaction. It must not create additional rows and must not alter ledger
lineage.

## 6. Explicitly Forbidden

The execute path must not create or modify:

```text
human demo virtual account
AI virtual account
system virtual account
n6_virtual_order
n6_virtual_trade
n6_virtual_position
n6_virtual_position_event
n6_virtual_pnl_snapshot
n6_principal
n6_ai_user
n6_principal_account
n6_watchlist_ownership
n6_strategy
user_account
user_session
user_projection_run
user_signal_projection
user_signal_card
user_notification_queue
N1-N6 facts/outbox/inbox/checkpoint
delivery / push / voice / mobile / sim / position / real trade
```

## 7. Runner Contract

Executable command for a future user-confirmed gate:

```bash
PYTHONPATH=src:scripts python3 scripts/run_n6_virtual_account_seed_once.py \
  --seed-run-id n6_phase3_virtual_account_seed_20260605_v1 \
  --contract-path docs/N6_PHASE3_VIRTUAL_ACCOUNT_SEED_execute_contract.json \
  --execute \
  --user-confirmed
```

Runner requirements:

```text
missing --execute => BLOCKED before repository read/write
missing --user-confirmed => BLOCKED before repository read/write
contract result must be CONTRACT_PASS
contract seed_run_id must match CLI seed_run_id
contract planned rows must be exactly 1/1/1/0/0/0/0/0
contract policy_hash must match seed policy hash
preflight must PASS before write
execute path must refresh preflight inside the write transaction
single transaction writes only account + initial cash ledger + initial cash snapshot
post report must not contain password_hash, session token, raw outbox payload, or provider payload
```

## 8. Rollback Contract

Rollback path:

```text
sql/N6_phase3_virtual_account_seed_rollback.sql
```

Rollback must:

```text
SET n6.phase3_virtual_account_seed_run_id = n6_phase3_virtual_account_seed_20260605_v1
hard-fail before first DELETE
delete only this seed_run_id / rollback_scope rows
delete in order: n6_virtual_cash_snapshot -> n6_virtual_cash_ledger -> n6_virtual_account
hard-fail if linked order/trade/position/position_event/pnl rows exist
hard-fail if future AI decision/evaluation/leaderboard refs exist
not drop 038A-E schema
not drop 036/037 objects
not delete Phase 2 principal rows
not touch N1-N6 facts/outbox/inbox/checkpoint
```

## 9. Execute Gate Status

This contract is ready for runtime_control execute final gate review. It does
not itself authorize execution; execution still requires explicit user
confirmation with the command above.
