# B Track V2 Virtual Buy Execution Schema Migration Execute Report

Result: MIGRATION_EXECUTE_PASS

Gate: B_TRACK_V2_VIRTUAL_ACCOUNT_BUY_EXECUTION_SCHEMA_MIGRATION_EXECUTE_GATE

Layer role: N6_user

## Scope

- Executed additive schema migration only.
- Did not implement `POST /api/n6/app/v2/virtual-account/buy`.
- Did not write virtual order/trade/cash/position business data.
- Did not modify historical seed data.
- Did not start worker, write outbox, read N4/N5 raw facts, or touch real trade / delivery / voice / mobile / sim real trade.

## DB Target

- database: ashare_v3
- user: ashare_v3_user
- host: 127.0.0.1
- port: 5432
- password output: false

## Migration

SQL:

`sql/B_TRACK_V2_virtual_buy_execution_schema.sql`

Command:

```bash
psql "postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3" -v ON_ERROR_STOP=1 -f sql/B_TRACK_V2_virtual_buy_execution_schema.sql
```

Result:

```text
BEGIN
ALTER TABLE
CREATE INDEX
ALTER TABLE
COMMIT
```

## Schema Proof

`n6_virtual_order` now has:

- idempotency_key: text
- source_message_key: text
- source_signal_identity_key: text
- source_condition_key: text
- source_event_time: timestamp with time zone
- source_for_trade_date: text
- source_json: jsonb

Idempotency index exists:

```text
ux_n6_virtual_order_principal_account_idempotency
CREATE UNIQUE INDEX ux_n6_virtual_order_principal_account_idempotency ON public.n6_virtual_order USING btree (principal_id, principal_type, virtual_account_id, idempotency_key) WHERE (idempotency_key IS NOT NULL)
```

`n6_virtual_position_event` now has:

- available_date: integer
- available_quantity_delta: numeric
- locked_quantity_delta: numeric
- price: numeric
- trade_date: integer

## No Business Data Write Proof

Before and after migration row counts remained:

```text
n6_virtual_cash_ledger=1
n6_virtual_order=0
n6_virtual_position_event=0
n6_virtual_trade=0
```

## Validation

```text
PYTHONPATH=src:scripts python3 -m unittest tests/test_n6_virtual_buy_execution_schema.py
PASS: 6 tests

PYTHONPATH=src:scripts python3 -m unittest tests/test_n6_user_app.py
PASS: 148 tests

python3 -m compileall src/ashare_v3/web tests/test_n6_user_app.py tests/test_n6_virtual_buy_execution_schema.py
PASS

git diff --check
PASS
```

## Next Gate

B_TRACK_V2_VIRTUAL_ACCOUNT_BUY_EXECUTION_SCHEMA_MIGRATION_POST_REVIEW_GATE
