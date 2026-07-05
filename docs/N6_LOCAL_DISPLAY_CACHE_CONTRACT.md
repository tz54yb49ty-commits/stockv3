# N6 Local Display Cache Contract

Result: CONTRACT_PASS

Layer role: N6_user

Date: 2026-06-07

This contract proposes a local readonly display cache for N6/B Track. It does
not execute schema changes, write rows, copy data, start sync jobs, or modify
N1/N2 source tables.

## 1. Objective

Create an N6-owned cache layer that makes B Track display and explanation fast
without reading N2 internal trading tables or mutating upstream facts.

Source tables:

```text
N2 display_basis:
  stock_condition_display_basis
  index_condition_display_basis
  board_condition_display_basis

N1 membership_fact:
  index_membership_fact
  board_membership_fact
```

Preferred input views:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

## 2. Cache Schema Proposal

N6 cache tables:

```text
n6_display_cache_run
n6_stock_display_cache
n6_index_display_cache
n6_board_display_cache
n6_index_membership_display_cache
n6_board_membership_display_cache
```

`n6_display_cache_run` fields:

```text
cache_run_id
source_condition_run_id
source_version_summary_json
cache_status
started_at
finished_at
row_count_json
quality_status
rollback_scope
created_at
```

Display cache common fields:

```text
cache_run_id
asset_kind
identity_key
code
name
trade_date
direction
condition_key
selected_signal_types_json
display_title
display_summary
period_summary_json
target_price_context_json
quality_status
source_display_table
source_condition_display_basis_id
source_run_id
source_updated_at
created_at
```

Mapping repair update 2026-06-07:

```text
recommended_mapping=cartesian_fanout_v1
direction and condition_key remain scalar filter fields
one source display_basis row expands to selected_directions × selected_condition_keys
source_row_hash, source_identity_key, source_selected_directions_json,
source_selected_condition_keys_json, and expansion_strategy are required
source_condition_display_basis_id is required
fanout uniqueness is scoped by cache_run_id + source_condition_display_basis_id + direction + condition_key
```

Membership cache common fields:

```text
cache_run_id
membership_kind
parent_identity_key
parent_code
parent_name
stock_identity_key
stock_code
stock_name
board_type
source_version
source_batch_id
trade_date
created_at
```

## 3. Index Strategy

Recommended indexes:

```text
n6_stock_display_cache(cache_run_id, identity_key)
n6_stock_display_cache(cache_run_id, direction, condition_key)
n6_index_display_cache(cache_run_id, identity_key)
n6_board_display_cache(cache_run_id, identity_key, board_type)
n6_index_membership_display_cache(cache_run_id, stock_identity_key)
n6_index_membership_display_cache(cache_run_id, parent_identity_key)
n6_board_membership_display_cache(cache_run_id, stock_identity_key, board_type)
n6_board_membership_display_cache(cache_run_id, parent_identity_key, board_type)
```

## 4. Sync Strategy

Daily sync:

```text
run after N2 condition_display_basis is active and N1 membership source is active
read through N6 readonly views
write only N6 cache tables
mark one cache_run_id active after row-count and quality checks pass
keep previous active cache until new cache passes
```

Incremental sync:

```text
allowed only by source_run_id/source_version delta
must be idempotent by cache_run_id + source primary key
must not patch upstream rows
must not re-evaluate conditions
```

## 5. Allowlist Update

B Track app allowlist may read:

```text
n6_stock_display_cache
n6_index_display_cache
n6_board_display_cache
n6_index_membership_display_cache
n6_board_membership_display_cache
```

Only after:

```text
N6_LOCAL_DISPLAY_CACHE_SCHEMA_IMPLEMENTATION_GATE passes
N6_LOCAL_DISPLAY_CACHE_MAPPING_REPAIR_GATE passes
N6_LOCAL_DISPLAY_CACHE_SYNC_DRY_RUN passes
N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE receives explicit authorization
```

## 6. Rollback Strategy

Rollback by `cache_run_id`:

```text
delete N6 cache rows for failed cache_run_id
restore previous active cache pointer
leave N1/N2 source tables unchanged
leave N4/N5/N6 projection/card rows unchanged
do not consume or update outbox
```

## 7. Safety Boundary

Forbidden:

```text
write N1/N2 source tables
read condition_basis / condition_pool / minute_target_scope
read raw K
read direct live market
read N4/N5 raw facts
consume outbox
start worker without explicit bounded sync gate
generate signal/proposal/order/trade/position/PnL
```

## 8. Next Gate

```text
N6_LOCAL_DISPLAY_CACHE_SCHEMA_IMPLEMENTATION_GATE
```

That gate must include SQL schema, rollback SQL, dry-run, and static tests. It
is not authorized by this contract.
