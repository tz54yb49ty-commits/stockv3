# N2-R2 Static Reference Period Migration Review

Date: 2026-05-24
Layer: N2_condition
Migration: `sql/011_condition_static_reference_period_migration.sql`
Status: safe for user-confirmed additive migration; not executed in this review

## Scope

This review covers only the N2 condition-layer schema migration draft for static reference period fields.

Boundary:

```text
old system touched: no
market data pulled: no
minute K pulled: no
N3/N4/N5/N6 entered: no
worker started: no
business data written: no
migration executed: no
overwrite executed: no
```

## SQL Review Result

The migration is additive only.

```text
ADD COLUMN IF NOT EXISTS only: yes
nullable columns only: yes
no DROP: yes
no UPDATE: yes
no INSERT: yes
no DELETE: yes
no TRUNCATE: yes
no COPY: yes
no backfill: yes
no NOT NULL enforcement: yes
no CHECK/FK enforcement: yes
no overwrite of condition rows: yes
```

Tables and columns added:

```text
stock_condition_basis.up_sell_reference_period
stock_condition_basis.down_buy_reference_period

index_condition_basis.up_sell_reference_period
index_condition_basis.down_buy_reference_period

board_condition_basis.up_sell_reference_period
board_condition_basis.down_buy_reference_period

stock_condition_pool.up_sell_reference_period
stock_condition_pool.down_buy_reference_period
```

The draft intentionally defers stricter constraints:

```text
NOT NULL checks
Y/Q/M/W/D CHECK constraints
clear_sell_ref_period = up_sell_reference_period compatibility validation
```

Those must be enforced by N2 dry-run / execute quality gates before overwrite, not by this additive migration.

## Current Development DB Gap

Read-only schema inspection shows all 8 target columns are currently missing:

```text
stock_condition_basis: up_sell_reference_period, down_buy_reference_period
index_condition_basis: up_sell_reference_period, down_buy_reference_period
board_condition_basis: up_sell_reference_period, down_buy_reference_period
stock_condition_pool: up_sell_reference_period, down_buy_reference_period
```

Applying 011 should close this specific N2-R2 schema gap without changing existing rows.

## Canonical Semantics

N2 canonical fields are:

```text
buy_target_price + up_sell_reference_period
sell_target_price + down_buy_reference_period
```

Compatibility alias:

```text
clear_sell_ref_period = up_sell_reference_period
```

`clear_sell_ref_period` remains only as a legacy alias. It must not be treated as the canonical N2 semantic field.

## Risk Assessment

Risk level: low, because this migration is additive and nullable.

Known follow-up requirements:

```text
1. Execute 011 only after user confirmation.
2. Re-run schema gap check after migration.
3. Re-run N2 full dry-run before overwrite.
4. Require P0=0.
5. Require up_sell_reference_period missing=0.
6. Require down_buy_reference_period missing=0.
7. Require clear_sell_ref_period = up_sell_reference_period.
8. Require fixed 9 index golden regression not to regress.
```

## Rollback Plan

Preferred rollback for additive schema migrations is usually forward-fix, not automatic drop, because dropping columns can remove any later data written after overwrite.

If rollback is required before any N2-R2 overwrite writes these columns, manual rollback SQL is:

```sql
BEGIN;

ALTER TABLE stock_condition_pool
  DROP COLUMN IF EXISTS up_sell_reference_period,
  DROP COLUMN IF EXISTS down_buy_reference_period;

ALTER TABLE board_condition_basis
  DROP COLUMN IF EXISTS up_sell_reference_period,
  DROP COLUMN IF EXISTS down_buy_reference_period;

ALTER TABLE index_condition_basis
  DROP COLUMN IF EXISTS up_sell_reference_period,
  DROP COLUMN IF EXISTS down_buy_reference_period;

ALTER TABLE stock_condition_basis
  DROP COLUMN IF EXISTS up_sell_reference_period,
  DROP COLUMN IF EXISTS down_buy_reference_period;

COMMIT;
```

Do not execute rollback automatically. If N2-R2 overwrite has already written a new active run, roll back the run first using its run-specific rollback SQL, then evaluate whether dropping additive columns is still appropriate.

## Recommendation

`sql/011_condition_static_reference_period_migration.sql` is safe to apply after explicit user confirmation.

Stop here and wait for user confirmation before executing 011 migration.
