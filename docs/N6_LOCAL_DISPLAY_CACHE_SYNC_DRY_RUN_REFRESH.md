# N6 Local Display Cache Sync Dry-Run Refresh

Gate: `N6_LOCAL_DISPLAY_CACHE_SYNC_DRY_RUN_REFRESH_GATE`  
Layer role: `runtime_control`  
Result: `DRY_RUN_PASS`  
Date: `2026-06-07`

This refresh was run after the N6 local display cache schema execute passed. It is a read-only sync preview only: no cache rows were inserted, no cache was activated, no outbox was consumed or updated, and no worker or N3/N4/N5/N6 action flow was triggered.

## Input

- Source condition run: `condition_layer_20260604_source_20260604_v1`
- Source trade date: `20260604`
- Cache version: `n6_display_cache_v1`
- Proposed cache run id: `n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1`
- Mapping strategy: `cartesian_fanout_v1`

Allowed source reads:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

## Live Target Schema Proof

All six N6 local display cache tables exist and remain empty:

| Table | Exists | Row Count |
|---|---:|---:|
| `n6_display_cache_run` | true | 0 |
| `n6_stock_display_cache` | true | 0 |
| `n6_index_display_cache` | true | 0 |
| `n6_board_display_cache` | true | 0 |
| `n6_index_membership_display_cache` | true | 0 |
| `n6_board_membership_display_cache` | true | 0 |

Target DB proof:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1
port=5432
transaction_read_only=on
db_time=2026-06-07T13:24:24.649743+08:00
```

## Source Counts

| Source | Rows |
|---|---:|
| `stock_condition_display_basis` | 1,952 |
| `index_condition_display_basis` | 9 |
| `board_condition_display_basis` | 428 |
| `index_membership_fact` | 12,841 |
| `board_membership_fact` | 56,960 |

## Fanout Preview

| Preview Target | Rows |
|---|---:|
| `n6_display_cache_run` | 1 |
| `n6_stock_display_cache` | 8,370 |
| `n6_index_display_cache` | 40 |
| `n6_board_display_cache` | 1,824 |
| `n6_index_membership_display_cache` | 12,841 |
| `n6_board_membership_display_cache` | 56,960 |
| Total excluding run | 80,035 |
| Total including run | 80,036 |

Display fanout is produced by:

```text
cardinality(selected_directions) * cardinality(selected_condition_keys)
```

Source array profile:

| Asset | Source Rows | Single Direction | Multi Direction | Single Condition | Multi Condition | Max Direction Len | Max Condition Len |
|---|---:|---:|---:|---:|---:|---:|---:|
| stock | 1,952 | 2 | 1,950 | 2 | 1,950 | 2 | 3 |
| index | 9 | 0 | 9 | 0 | 9 | 2 | 3 |
| board | 428 | 0 | 428 | 0 | 428 | 2 | 3 |

## Validation Summary

| Check | Result |
|---|---:|
| duplicate fanout key | 0 |
| duplicate row_hash | 0 |
| missing required | 0 |
| invalid board_type | 0 |
| invalid direction | 0 |
| null identity_key | 0 |

Per-target validation:

| Target Area | Preview Rows | Duplicate Key/Pair | Duplicate Row Hash | Missing Required | Invalid Direction | Invalid Board Type | Null Identity |
|---|---:|---:|---:|---:|---:|---:|---:|
| stock display | 8,370 | 0 | 0 | 0 | 0 | 0 | 0 |
| index display | 40 | 0 | 0 | 0 | 0 | 0 | 0 |
| board display | 1,824 | 0 | 0 | 0 | 0 | 0 | 0 |
| index membership | 12,841 | 0 | 0 | 0 | n/a | 0 | 0 |
| board membership | 56,960 | 0 | 0 | 0 | n/a | 0 | 0 |

`source_row_hash` is intentionally shared by multiple fanout rows from the same source display row. Expanded `row_hash` includes `direction` and `condition_key`, and remains unique.

Board type distribution was valid:

| Source | `tdx_region` | `tdx_concept` | `tdx_industry` |
|---|---:|---:|---:|
| board display | 32 | 269 | 127 |
| board membership | 5,525 | 45,910 | 5,525 |

## Execute Preflight Inputs

The next gate can use these inputs:

```text
cache_run_id=n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1
cache_version=n6_display_cache_v1
source_condition_run_id=condition_layer_20260604_source_20260604_v1
source_trade_date=20260604
mapping_strategy=cartesian_fanout_v1
expected_stock_display_rows=8370
expected_index_display_rows=40
expected_board_display_rows=1824
expected_index_membership_rows=12841
expected_board_membership_rows=56960
expected_total_excluding_run=80035
expected_total_including_run=80036
duplicate_fanout_key=0
duplicate_row_hash=0
missing_required=0
invalid_board_type=0
invalid_direction=0
null_identity_key=0
target_tables_exist=true
target_row_counts_zero=true
```

## Forbidden Source Proof

No forbidden source was read:

- `condition_basis`
- `condition_pool`
- `minute_target_scope`
- raw K
- N4/N5 raw bypass
- direct live market
- unreviewed outbox

## Forbidden Scope Proof

This gate did not:

- write DB rows
- sync N2/N1 data into cache
- activate cache
- consume or update outbox
- start a worker
- modify N3/N4/N5/N6 action flow
- generate proposal/order/trade
- update position/PnL
- submit real trade

## Validation

```text
JSON parse: PASS
schema exists assertion: PASS
target row count zero assertion: PASS
fanout count assertion: PASS
duplicate assertion: PASS
forbidden scope assertion: PASS
git diff --check: PASS
```

## Decision

`DRY_RUN_PASS`

Allowed next gate:

```text
N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_FINAL_GATE_REVIEW
```

Direct sync execute is not authorized by this gate. Cache activation remains out of scope.
