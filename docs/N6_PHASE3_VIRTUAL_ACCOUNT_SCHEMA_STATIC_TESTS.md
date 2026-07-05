# N6 Phase 3 Virtual Account Schema Static Tests

Status: STATIC_TESTS_PASS

Layer role: N6_user

Date: 2026-06-05

These are static validation targets for the Phase 3 schema draft. They do not
execute DDL or write the database.

## 1. JSON Parse

Required files must parse:

```text
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_DRAFT.json
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_TRACEABILITY.json
docs/N6_PHASE3_VIRTUAL_ACCOUNT_SCHEMA_STATIC_TESTS.json
```

## 2. Migration SQL Static Scan

Expected:

```text
CREATE TABLE IF NOT EXISTS only for 8 Phase 3 tables
CREATE INDEX IF NOT EXISTS only for Phase 3 indexes
no INSERT
no UPDATE
no DELETE
no TRUNCATE
no COPY
no ALTER
no DROP
no CASCADE
no common_event_outbox / common_event_inbox / checkpoint references
no common_position_* references
no user_sim_* references
no broker_order_id / real_trade_id / real_execution_id fields
```

Required table names:

```text
n6_virtual_account
n6_virtual_cash_ledger
n6_virtual_cash_snapshot
n6_virtual_position
n6_virtual_position_event
n6_virtual_order
n6_virtual_trade
n6_virtual_pnl_snapshot
```

Required common fields on every table:

```text
run_id
policy_version
policy_hash
rollback_scope
source_lineage_json
quality_status
created_at
```

## 3. Model Separation Tests

Cash model:

```text
n6_virtual_cash_ledger exists
n6_virtual_cash_snapshot exists
cash_ledger_type CHECK exists
cash_snapshot_status CHECK exists
```

Position model:

```text
n6_virtual_position exists
n6_virtual_position_event exists
position_status CHECK exists
position_event_type CHECK exists
```

## 4. Deterministic / Valuation Tests

Virtual trade must include:

```text
fill_policy_version
fill_policy_hash
replay_deterministic_seed
```

PnL must include:

```text
source_price_policy
valuation_policy_version
valuation_policy_hash
```

PnL must not allow:

```text
live price direct
raw K recompute
```

## 5. Rollback Static Scan

Expected:

```text
RAISE EXCEPTION before first DROP
blocks if any Phase 3 table has rows
no CASCADE
does not drop 036/037 objects
does not touch N1-N6 facts/outbox
does not touch N6_UI_v1
```

## 6. Traceability Static Scan

Expected:

```text
N6VAS-001..N6VAS-040 continuous
no duplicate rule ids
coverage=100%
approved changes covered:
  cash ledger/snapshot split
  position state/event split
```
