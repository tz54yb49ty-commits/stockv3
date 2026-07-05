# N6_LOCAL_DISPLAY_CACHE_MAPPING_REPAIR_DRY_RUN

Status: DRY_RUN_PASS

Layer role: runtime_control

Review date: 2026-06-07

Mode: read-only fan-out mapping dry-run. No schema migration was executed, no
tables were created, no rows were written, no cache was activated, no outbox was
consumed, and no worker was started.

## Fan-out Formula

For each display source row:

```text
fanout_rows = cardinality(selected_directions) * cardinality(selected_condition_keys)
```

Each fan-out row gets:

```text
direction = one selected_directions value
condition_key = one selected_condition_keys value
source_identity_key = original source object identity
source_row_hash = hash of the unexpanded source display row
row_hash = hash of the expanded cache row
expansion_strategy = cartesian_fanout_v1
```

## Source Array Stats

| Asset | Source rows | Single direction | Multi direction | Single condition | Multi condition | Max direction len | Max condition len | Fan-out rows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| stock | 1952 | 2 | 1950 | 2 | 1950 | 2 | 3 | 8370 |
| index | 9 | 0 | 9 | 0 | 9 | 2 | 3 | 40 |
| board | 428 | 0 | 428 | 0 | 428 | 2 | 3 | 1824 |

Display cache total after fan-out:

```text
10234
```

Membership cache rows:

```text
index_membership=12841
board_membership=56960
membership_total=69801
```

Total cache rows excluding run metadata:

```text
80035
```

Total cache rows including `n6_display_cache_run`:

```text
80036
```

## Duplicate Risk

Fan-out duplicate checks:

| Asset | Fan-out rows | Duplicate source/direction/condition | Duplicate identity/direction/condition | Duplicate fanout hash |
|---|---:|---:|---:|---:|
| stock | 8370 | 0 | 0 | 0 |
| index | 40 | 0 | 0 | 0 |
| board | 1824 | 0 | 0 | 0 |

Membership duplicate checks:

| Membership | Rows | Duplicate pair |
|---|---:|---:|
| index | 12841 | 0 |
| board | 56960 | 0 |

## Hash Collision Risk

Observed fan-out hash duplicates:

```text
stock=0
index=0
board=0
```

Observed membership row_hash duplicates remain:

```text
index_membership=0
board_membership=0
```

Hash algorithm remains deterministic over source lineage and expanded fields.
MD5 collision probability is not zero in theory, but this dry-run observed no
collisions and the schema also uses composite unique indexes for semantic
duplicate protection.

## Validation

```text
JSON parse: PASS
mapping assertion: PASS
schema assertion: PASS
duplicate assertion: PASS
git diff --check: PASS
```

## Decision

DRY_RUN_PASS for mapping repair.

Allowed next gate:

```text
N6_LOCAL_DISPLAY_CACHE_SCHEMA_EXECUTE_GATE
```

Still forbidden:

```text
N6_LOCAL_DISPLAY_CACHE_SYNC_EXECUTE_GATE
```

The sync execute gate must wait until schema execute passes and a fresh sync
dry-run/preflight is regenerated against the live target schema.
