# N2 20260609 Period Context Query Optimization

Result: `OPTIMIZATION_PASS`

This gate changed N2 code/tests/docs only. It did not execute N2, did not write database rows, did not pull market data, did not consume event infrastructure, and did not enter N3/N4/N5/N6.

## Root Cause

The previous blocker was in:

```text
src/ashare_v3/condition/basis.py:fetch_period_contexts
```

The old query built a full-window facts CTE with:

```text
DISTINCT ON (identity_key, trade_date)
ORDER BY identity_key, trade_date, source preference
```

For `stock_daily_bar_fact` over `20240101 -> 20260608`, the window contains:

```text
rows = 3157982
duplicate(identity_key, trade_date) pairs = 0
```

So the defensive de-dup sort was redundant for the active 20260608 source window and made the dry-run too slow. The dry-run runner also rebuilt the same basis preview repeatedly while constructing basis / pool / scope.

## Repair

Changed:

- `src/ashare_v3/condition/basis.py`
- `tests/test_condition_basis.py`

Implemented:

```text
1. fetch_period_contexts uses a fast fact scan without DISTINCT ON.
2. source_trade_date rows are still constrained to current_source_version.
3. daily rows are ordered by identity/date for deterministic target-price calculations.
4. build_condition_basis_dry_run now has an in-process cache keyed by DSN, source date, active source versions, and readiness universe markers.
```

No DB index or schema migration was required.

## Performance Proof

Fast stock window count probe:

```text
rows = 3157982
elapsed_sec = 8.373
```

Execute-runner preflight probe completed:

```text
P0/P1/P2 = 0/6/3
blocked_reasons = [user_confirmation_required]
writes_performed = false
will_execute_sql = false
```

Full dry-run planner completed and refreshed the official 20260609 artifacts:

```text
status = FULL_DRY_RUN_PASS
P0/P1/P2 = 0/6/3
```

## Refreshed Row Counts

| stage | stock | index | board |
|---|---:|---:|---:|
| condition_basis | 5514 | 83 | 428 |
| condition_pool | 4063 | 216 | 265 |
| minute_target_scope | 4043 | 216 | 265 |
| condition_display_basis | 1880 | 83 | 127 |
| monitor_target | 5514 | 83 | 428 |

`common_condition_quality_item = 106`

## Semantic Safety

```text
period baseline semantics changed = false
uses only N1 active facts = true
N3/N4/N5/N6 data used = false
market data pulled = false
old system accessed = false
DDL required = false
```

## Next Gate

Allowed next step:

```text
N2_20260609_CONDITION_LAYER_DRY_RUN_PREFLIGHT_GATE
```

N2 execute still requires a separate final gate and explicit user confirmation.
