# N6_LOCAL_DISPLAY_CACHE_SYNC_DRY_RUN

Status: BLOCKED

Layer role: runtime_control

Review date: 2026-06-07

Mode: read-only dry-run. No database rows were written, no cache was activated,
no outbox was consumed, no worker was started, and no N6 projection/action
message path was touched.

## Inputs

- N2 active run: `condition_layer_20260604_source_20260604_v1`
- N2 display source tables:
  - `stock_condition_display_basis`
  - `index_condition_display_basis`
  - `board_condition_display_basis`
- N1 membership source tables:
  - `index_membership_fact`
  - `board_membership_fact`
- N6 target schema artifact:
  - `sql/N6_local_display_cache_schema.sql`

Dry-run cache metadata:

```text
cache_run_id=n6_display_cache_sync_dry_run_20260604_condition_layer_20260604_source_20260604_v1
cache_version=n6_display_cache_v1
source_condition_run_id=condition_layer_20260604_source_20260604_v1
source_trade_date=20260604
```

Target DB proof:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1/32
port=5432
default_transaction_read_only=on
```

## Source Readiness

`common_condition_run` proof:

```text
run_id=condition_layer_20260604_source_20260604_v1
status=passed_active
source_trade_date=20260604
for_trade_date=20260605
source_version=condition_source_bundle_20260604
```

N1 membership active source versions:

```text
index_membership: source_version=index_membership_20260604_v1, source_batch_id=index_membership_20260604_v1
board_membership: source_version=board_membership_20260604_v1, source_batch_id=board_membership_20260604_v1
```

Preferred N6 readonly views exist:

```text
v_n6_stock_condition_display_basis=true
v_n6_index_condition_display_basis=true
v_n6_board_condition_display_basis=true
v_n6_index_membership_fact=true
v_n6_board_membership_fact=true
```

## Target Schema Readiness

Live DB target cache tables are missing:

```text
n6_display_cache_run=false
n6_stock_display_cache=false
n6_index_display_cache=false
n6_board_display_cache=false
n6_index_membership_display_cache=false
n6_board_membership_display_cache=false
```

This blocks the sync execute gate. The dry-run can still preview source rows and
hashes from allowed sources, but it cannot be promoted directly to execute until
the local display cache schema exists in the target database.

## Dry-run Row Counts

| Target table | Source table | Preview rows | Duplicate identity/pair | Missing required | Duplicate row_hash |
|---|---|---:|---:|---:|---:|
| `n6_stock_display_cache` | `stock_condition_display_basis` | 1952 | 0 | 0 | 0 |
| `n6_index_display_cache` | `index_condition_display_basis` | 9 | 0 | 0 | 0 |
| `n6_board_display_cache` | `board_condition_display_basis` | 428 | 0 | 0 | 0 |
| `n6_index_membership_display_cache` | `index_membership_fact` | 12841 | 0 | 0 | 0 |
| `n6_board_membership_display_cache` | `board_membership_fact` | 56960 | 0 | 0 | 0 |

Total preview rows excluding `n6_display_cache_run`: `72190`.

`n6_display_cache_run` would add one run metadata row in a future execute gate,
but no run row was written in this dry-run.

## Row Hash Proof

Every source preview row was assigned a deterministic `row_hash` using an MD5
hash over the cache run id, cache version, source lineage, source primary key,
identity key, display fields, selected signal arrays, quality status, and
membership pair fields where applicable.

Hash distinctness:

```text
stock display: distinct_row_hash=1952/1952
index display: distinct_row_hash=9/9
board display: distinct_row_hash=428/428
index membership: distinct_row_hash=12841/12841
board membership: distinct_row_hash=56960/56960
```

Sample row hashes:

```text
stock:SH:600000 -> 42b48bc22fd875fd6a007b60dae91969
index:SH:000001 -> c162c34269c410882b70499615835277
board:TDX:880201 -> 301914748baff0e7cdf6657ad5f5b49f
index:SH:000009|stock:SH:600007 -> 37b755d4efbebc1a57790939d03e8495
board:TDX:880201|stock:BJ:920091 -> 22d9cc43be8031727f5fbc2f4bb79b61
```

## Mapping Blocker

The current cache schema requires single-value `direction` and `condition_key`
columns on display cache rows:

```text
direction TEXT NOT NULL CHECK (direction IN ('buy', 'sell'))
condition_key TEXT NOT NULL
```

The active N2 display_basis rows are object-level display rows and mostly carry
multi-value arrays:

| Source table | Rows | Single-value ready | Multi-value rows |
|---|---:|---:|---:|
| `stock_condition_display_basis` | 1952 | 2 | 1950 |
| `index_condition_display_basis` | 9 | 0 | 9 |
| `board_condition_display_basis` | 428 | 0 | 428 |

Total multi-value display rows: `2387/2389`.

This is a P0 mapping blocker. A future execute gate must first choose one of
these policies:

- keep object-level cache rows and change/extend schema so `direction` and
  `condition_key` can preserve arrays without lossy compression;
- or fan out cache rows per selected condition/direction and explicitly relax
  the current identity-key uniqueness expectation to a composite uniqueness
  rule such as `(cache_run_id, identity_key, direction, condition_key)`.

The dry-run did not silently pick the first array value and did not compress
multi-value conditions into a single cache row.

## Insert Preview Boundary

Dry-run insert preview was generated only as a mapping model. It was not
executed.

Allowed source reads:

```text
common_condition_run
common_active_source_version
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
index_membership_fact
board_membership_fact
information_schema / to_regclass metadata
```

Forbidden sources were not read:

```text
condition_basis=false
condition_pool=false
minute_target_scope=false
raw K=false
N4/N5 raw bypass=false
direct live market=false
unreviewed outbox=false
```

## Validation Summary

```text
JSON parse: PASS
schema artifact assertion: PASS
live target schema assertion: BLOCKED
allowlist assertion: PASS
forbidden source proof: PASS
identity/pair uniqueness: PASS
row_hash uniqueness: PASS
source_trade_date/source_run/cache_version proof: PASS
git diff --check: PASS
```

## Decision

BLOCKED.

Dry-run source validation passed, but sync execute is not allowed yet because:

1. all six N6 target cache tables are missing in the live target DB;
2. current display cache schema is not semantically compatible with multi-value
   N2 display_basis rows.

Next required gate:

```text
N6_LOCAL_DISPLAY_CACHE_SCHEMA_EXECUTE_OR_MAPPING_REPAIR_GATE
```

Do not enter `N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_GATE` until the target schema
exists and the object-level versus fan-out mapping policy is repaired and
reviewed.
