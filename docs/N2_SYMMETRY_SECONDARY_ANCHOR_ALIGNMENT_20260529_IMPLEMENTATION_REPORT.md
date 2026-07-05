# N2 Symmetry Secondary Anchor Alignment 20260529 Implementation Report

Status: `IMPLEMENTATION_PASS_WITH_FULL_DRY_RUN_BLOCKER`

This pass only changed N2 code, tests, docs, and schema migration drafts. It did
not execute an N2 active run, did not write condition business rows, did not pull
market data, and did not enter N3/N4/N5/N6.

## Scope

- Fix A-segment identification to use the anchor period's own aggregate bars.
- Do not automatically merge an initial `unknown` aggregate bar into the current
  A segment.
- Find `trend_break_date` on `lower(anchor)` aggregate bars:
  `Y -> Q`, `Q -> M`, `M -> W`, `W -> D`.
- Compute secondary target price from the second anchor run by repeating the
  same formula, not by discounting the primary target.
- Add explicit up/down secondary-anchor fields to N2 schema drafts and writer
  column lists.

## Golden Proof

```text
300327 / 20260529:
  main_up_anchor = Y
  up_reference_period = Q
  buy_target_price = 38.27
  reference_target_price = 38.27
  up_secondary_anchor = W
  up_secondary_reference_period = D
  up_secondary_target_price = 33.04
  secondary_symmetry_anchor = W
  secondary_target_price = 33.04

000600 / 20260529:
  buy_target_price = 12.93

000543 / 20260529:
  buy_target_price = 10.82

000027 / 20260529:
  buy_target_price = 8.45

000027 / 20260528:
  buy_target_price = 8.42
```

## Schema Draft

Migration draft:

```text
sql/030_condition_symmetry_secondary_anchor_columns_migration.sql
```

Rollback draft:

```text
sql/030_condition_symmetry_secondary_anchor_columns_rollback.sql
```

The migration is additive and nullable over the 12 N2 condition tables:

```text
stock/index/board_condition_basis
stock/index/board_condition_pool
stock/index/board_minute_target_scope
stock/index/board_condition_display_basis
```

It does not touch index/board differently from stock, does not drop/backfill
historical rows, and does not add `locked_target_price` or
`target_lock_status`.

## Current Blocker

The full live DB preflight refresh was started in read-only mode for
`condition_layer_20260529_source_20260529_v5`, but it did not finish after more
than five minutes and was terminated to avoid leaving a dangling process. No
report file was written and no DB writes were performed.

Before any active supersede final gate, rerun the full N2 dry-run/preflight
after 030 migration is explicitly reviewed and, if approved, executed.

## Verification

```text
compileall scripts src tests: OK
test_condition_symmetry_target_price.py: 8 OK
test_condition_execute_preflight.py: 14 OK
test_condition_symmetry_secondary_anchor_migration_draft.py: 4 OK
test_condition*.py: 207 OK
git diff --check: OK
```
