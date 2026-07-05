# N6 Phase 3 038A Virtual Account Static Tests

Status: STATIC_TESTS_PASS

Layer role: N6_user

Date: 2026-06-05

Static validation targets for the 038A migration draft. These tests do not
execute DDL or write the database.

## 1. JSON Parse

Required JSON files:

```text
docs/N6_PHASE3_038A_VIRTUAL_ACCOUNT_MIGRATION_DRAFT.json
docs/N6_PHASE3_038A_VIRTUAL_ACCOUNT_STATIC_TESTS.json
docs/N6_PHASE3_038A_VIRTUAL_ACCOUNT_TRACEABILITY.json
```

## 2. Migration Static Scan

Expected:

```text
CREATE TABLE IF NOT EXISTS count = 1
created table = n6_virtual_account
CREATE INDEX IF NOT EXISTS only
no INSERT / UPDATE / DELETE / TRUNCATE / COPY
no ALTER old table
no DROP
no CASCADE
no 038B-E table creation
no N1-N6 fact/outbox references
no broker / real trade fields
```

## 3. Principal Ownership Proof

Expected SQL evidence:

```text
FOREIGN KEY (principal_id, principal_type) REFERENCES n6_principal(principal_id, principal_type)
principal_type CHECK allows admin/human_user/ai_user
principal_type CHECK does not allow system
```

## 4. Account Linkage Proof

Expected:

```text
account_id not present in 038A
no FK to n6_principal_account
account linkage deferred to future gate
```

## 5. Rollback Static Scan

Expected:

```text
RAISE EXCEPTION before first DROP
checks n6_virtual_account row_count
checks future 038B-E table row_count using to_regclass
no CASCADE
drops only n6_virtual_account
does not drop 036/037 objects
does not touch N1-N6 facts/outbox
```
