# N6_LOCAL_DISPLAY_CACHE_SCHEMA_IMPLEMENTATION

Status: `IMPLEMENTATION_PASS`

Layer role: `N6_user`

Date: `2026-06-07`

Scope: Implement the empty N6 local display cache schema for B轨 V2 filter
surfaces. This gate creates schema SQL and rollback SQL only. It does not sync
rows, activate cache, read upstream data, consume outbox, start workers, or
generate proposal/order/trade/position/PnL.

## 1. Background

B轨 V2 filter pages currently read these N6-owned cache tables:

```text
n6_display_cache_run
n6_stock_display_cache
n6_index_display_cache
n6_board_display_cache
n6_index_membership_display_cache
n6_board_membership_display_cache
```

Before this gate, those tables were absent, so the filter APIs correctly
returned:

```text
status = data_not_ready
empty_state = 筛选数据尚未准备完成
```

Latest upstream readiness evidence, gathered read-only before this gate:

```text
N2 active run = condition_layer_20260604_source_20260604_v1
stock display rows = 1952
index display rows = 9
board display rows = 428
index membership rows = 128410
board membership rows = 569332
```

This gate does not copy those rows. It only prepares the N6 local schema for a
future sync dry-run and explicit sync execute gate.

## 2. Created Schema

Schema SQL:

```text
sql/N6_local_display_cache_schema.sql
```

Created empty tables:

```text
n6_display_cache_run
n6_stock_display_cache
n6_index_display_cache
n6_board_display_cache
n6_index_membership_display_cache
n6_board_membership_display_cache
```

`n6_display_cache_run` supports:

```text
cache_run_id
source_condition_run_id
source_trade_date
cache_version
status
is_active
started_at
finished_at
row_counts_json
hash_summary_json
validation_summary_json
error_json
created_at
updated_at
```

Display cache tables support:

```text
cache_run_id
cache_version
source_condition_run_id
source_trade_date
source_table
source_version
synced_at
row_hash
asset_kind
identity_key
stock_identity_key
index_identity_key
board_identity_key
code
name
display_code
display_name
display_title
display_summary
condition_key
original_condition_key
direction
selected_signal_types_json
period_summary_json
year_overheat_level
quarter_overheat_level
month_overheat_level
week_overheat_level
day_overheat_level
target_price_context_json
label_json
explanation_json
quality_status
source_condition_display_basis_id
source_updated_at
created_at
```

Mapping repair update 2026-06-07:

```text
sql/N6_local_display_cache_schema.sql has been revised by
N6_LOCAL_DISPLAY_CACHE_SCHEMA_EXECUTE_OR_MAPPING_REPAIR_GATE.

New fan-out trace fields:
  source_row_hash
  source_identity_key
  source_selected_directions_json
  source_selected_condition_keys_json
  expansion_strategy

source_condition_display_basis_id is now required for display cache rows.

Fan-out unique indexes:
  uq_n6_stock_display_cache_source_fanout
  uq_n6_index_display_cache_source_fanout
  uq_n6_board_display_cache_source_fanout
```

Membership cache tables support:

```text
cache_run_id
cache_version
source_condition_run_id
source_trade_date
source_table
source_version
source_batch_id
synced_at
row_hash
membership_kind
parent_identity_key
parent_code
parent_name
index_identity_key
board_identity_key
board_type
stock_identity_key
stock_code
stock_name
display_title
display_summary
label_json
explanation_json
quality_status
trade_date
created_at
```

## 3. Index Coverage

Active lookup:

```text
n6_display_cache_run_active_once
idx_n6_display_cache_run_active
idx_n6_display_cache_run_source
```

Display cache lookup:

```text
idx_n6_stock_display_cache_identity
idx_n6_stock_display_cache_stock_identity
idx_n6_stock_display_cache_direction_condition
idx_n6_index_display_cache_identity
idx_n6_index_display_cache_index_identity
idx_n6_index_display_cache_direction_condition
idx_n6_board_display_cache_identity
idx_n6_board_display_cache_board_identity
idx_n6_board_display_cache_identity_board_type
idx_n6_board_display_cache_direction_condition
idx_n6_board_display_cache_board_type
```

Membership lookup:

```text
idx_n6_index_membership_display_cache_parent
idx_n6_index_membership_display_cache_stock
idx_n6_index_membership_display_cache_index_identity
idx_n6_board_membership_display_cache_parent
idx_n6_board_membership_display_cache_stock
idx_n6_board_membership_display_cache_board_identity
idx_n6_board_membership_display_cache_parent_board_type
idx_n6_board_membership_display_cache_stock_board_type
```

## 4. Rollback Proof

Rollback SQL:

```text
sql/N6_local_display_cache_schema_rollback.sql
```

Rollback behavior:

```text
hard_fail_before_drop = true
business_delete = false
source_table_mutation = false
```

Rollback first counts all six N6 cache tables. If any cache table is non-empty,
it raises:

```text
N6 local display cache schema rollback blocked
```

Only when all six cache tables are empty does rollback drop the six tables
created by this gate.

## 5. Boundary Proof

This gate does not:

```text
sync display cache rows
activate a cache run
write upstream N1/N2 source tables
read forbidden N2 runtime tables
touch N3/N4/N5 facts
touch N6 projection/card tables
consume/update outbox, inbox, or checkpoint
start worker
generate proposal/order/trade
generate position/PnL
submit real trade
```

## 6. Next Gate

```text
N6_LOCAL_DISPLAY_CACHE_SYNC_DRY_RUN_GATE
```

That gate should produce a dry-run mapping from the latest active N2 display
rows and N1 membership rows into the six N6 cache tables, with row counts,
hash summary, validation summary, rollback plan, and no database writes unless
a later execute gate is explicitly authorized.
