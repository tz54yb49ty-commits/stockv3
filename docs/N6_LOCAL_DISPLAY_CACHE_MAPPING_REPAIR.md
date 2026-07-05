# N6_LOCAL_DISPLAY_CACHE_MAPPING_REPAIR

Status: MAPPING_REPAIR_PASS

Layer role: runtime_control

Review date: 2026-06-07

Scope: repair the N6 local display cache mapping/schema contract after sync
dry-run found multi-direction and multi-condition display_basis rows. This gate
does not execute schema migration, does not create tables, does not sync rows,
does not activate cache, and does not touch outbox, worker, N6 projection,
proposal/order/trade, position/PnL, or real trade.

## Source Structure Audit

Source run:

```text
condition_layer_20260604_source_20260604_v1
status=passed_active
source_trade_date=20260604
for_trade_date=20260605
```

N2 display_basis array structure:

| Source table | Source rows | Single direction | Multi direction | Single condition | Multi condition | Max direction len | Max condition len |
|---|---:|---:|---:|---:|---:|---:|---:|
| `stock_condition_display_basis` | 1952 | 2 | 1950 | 2 | 1950 | 2 | 3 |
| `index_condition_display_basis` | 9 | 0 | 9 | 0 | 9 | 2 | 3 |
| `board_condition_display_basis` | 428 | 0 | 428 | 0 | 428 | 2 | 3 |

Samples:

```text
stock:SH:600000
  selected_directions=[buy,sell]
  selected_condition_keys=[BUY:Y,Q,M,W,D, SELL:W]
  selected_signal_types=[BUY, SELL]

index:SH:000001
  selected_directions=[buy,sell]
  selected_condition_keys=[BUY:M,W,D, BUY_HINT, SELL:Y,Q]
  selected_signal_types=[BUY, BUY_HINT, SELL]

board:TDX:880201
  selected_directions=[buy,sell]
  selected_condition_keys=[BUY:Q,M,W, SELL:Y,Q,W,D]
  selected_signal_types=[BUY, SELL]
```

## Mapping Repair

Recommended strategy: `cartesian_fanout_v1`.

One N2 source row expands into one cache row per:

```text
selected_directions × selected_condition_keys
```

The expanded row keeps query-friendly scalar fields:

```text
direction TEXT
condition_key TEXT
```

and also preserves source lineage:

```text
source_identity_key
source_row_hash
source_condition_display_basis_id
source_condition_run_id
source_trade_date
source_selected_directions_json
source_selected_condition_keys_json
selected_signal_types_json
expansion_strategy=cartesian_fanout_v1
```

This repair explicitly forbids:

```text
dropping directions
dropping condition_key values
overwriting arrays with the first value
compressing multiple source meanings into one lossy cache row
```

## Schema Option Comparison

### Option A: fan-out rows with scalar `direction` and `condition_key`

Recommended.

Pros:

- Preserves all N2 source values without lossy compression.
- Keeps B-track filter queries simple: equality filters on `direction` and `condition_key`.
- Allows normal B-tree indexes and future composite uniqueness.
- Compatible with existing UI/filter API shape.
- Clear rollback scope by `cache_run_id`.

Costs:

- Increases display cache rows from 2,389 source object rows to 10,234 fan-out
  rows for this run.
- Requires source trace fields to explain why one object appears more than once.

### Option B: keep one row per source object with JSONB arrays

Not recommended for V1 execute.

Pros:

- Fewer display cache rows.
- Directly mirrors source display_basis object rows.

Costs:

- Direction and condition filtering become JSONB containment queries.
- Indexing becomes more complex and less predictable for UI filter latency.
- Existing B-track APIs already expose scalar `direction` and `condition_key`
  filters, so this option would push more compatibility work into API code.

## Schema Repair Applied To SQL Draft

`sql/N6_local_display_cache_schema.sql` was updated as a schema draft only.
No DDL was executed.

Added display cache fields:

```text
source_row_hash TEXT NOT NULL
source_identity_key TEXT NOT NULL
source_selected_directions_json JSONB NOT NULL DEFAULT '[]'::JSONB
source_selected_condition_keys_json JSONB NOT NULL DEFAULT '[]'::JSONB
expansion_strategy TEXT NOT NULL DEFAULT 'cartesian_fanout_v1'
```

Changed display source id:

```text
source_condition_display_basis_id BIGINT NOT NULL
```

Added unique fan-out indexes:

```text
uq_n6_stock_display_cache_source_fanout
uq_n6_index_display_cache_source_fanout
uq_n6_board_display_cache_source_fanout
```

Each unique index is scoped by:

```text
cache_run_id, source_condition_display_basis_id, direction, condition_key
```

## Expected Cache Rows

Display fan-out:

```text
stock=8370
index=40
board=1824
display_total=10234
```

Membership rows remain unchanged:

```text
index_membership=12841
board_membership=56960
membership_total=69801
```

Expected total rows excluding `n6_display_cache_run`:

```text
80035
```

Expected `n6_display_cache_run` rows:

```text
1
```

## Decision

MAPPING_REPAIR_PASS.

Allowed next gate:

```text
N6_LOCAL_DISPLAY_CACHE_SCHEMA_EXECUTE_GATE
```

Still forbidden:

```text
N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_GATE
```

Sync execute remains forbidden until the schema execute gate passes and a fresh
sync dry-run/preflight is regenerated against the live schema.
