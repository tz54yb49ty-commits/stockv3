# N2 Symmetry Target Price Canonical Compatibility Draft

Status: **DRAFT_PASS**

Layer: `N2_condition`

This review drafts schema compatibility for the frozen symmetry target price spec. It does not execute migration, does not write database rows, and does not enter N1/N3/N4/N5/N6.

## Scope

The draft migration adds nullable canonical target fields to these N2 tables:

```text
stock_condition_basis
index_condition_basis
board_condition_basis
stock_condition_pool
index_condition_pool
board_condition_pool
stock_minute_target_scope
index_minute_target_scope
board_minute_target_scope
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
```

## New Nullable Fields

```text
symmetry_anchor
secondary_symmetry_anchor
amplitude_source_period
a_segment_start_date
a_segment_end_date
a_segment_high
a_segment_low
a_segment_amplitude
base_price_policy
base_price
reference_target_price
secondary_target_price
target_price_trace_json
```

The draft intentionally does not add:

```text
locked_target_price
target_lock_status
position_id
action_id
user_policy_hint
```

## Constraints

The draft adds nullable CHECK constraints:

```text
symmetry_anchor / secondary_symmetry_anchor / amplitude_source_period:
  NULL or Y/Q/M/W

base_price_policy:
  NULL or MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN

a_segment_start_date / a_segment_end_date:
  NULL or YYYYMMDD text

a_segment_high / a_segment_low / a_segment_amplitude:
  NULL or >= 0

base_price / reference_target_price / secondary_target_price:
  NULL or >= 0

target_price_trace_json:
  NULL or JSON object
```

`clear_sell_ref_period` remains a legacy alias and must continue to satisfy:

```text
clear_sell_ref_period = up_sell_reference_period
```

This alias invariant is not changed by the draft migration; readiness/tests assert it remains part of the N2 contract.

## Migration Files

```text
sql/027_condition_symmetry_target_price_compatibility_migration.sql
sql/027_condition_symmetry_target_price_compatibility_rollback.sql
```

The migration draft is schema-only:

```text
ADD COLUMN IF NOT EXISTS
nullable fields
CHECK constraints only
no INSERT
no UPDATE
no DELETE
no business row backfill
```

## Rollback Strategy

Rollback is schema-only and removes only the 027 columns and constraints from the same 12 N2 tables.

The rollback draft intentionally does not clean historical business rows and does not touch:

```text
common_condition_run
common_condition_quality_item
monitor_target
N1 source_version
N3/N4/N5/N6 facts
outbox/inbox/checkpoint
```

## No-Migration Compatibility

No-migration compatibility remains available.

Current N2 can continue to expose target candidates through:

```text
buy_target_price
sell_target_price
up_sell_reference_period
down_buy_reference_period
clear_sell_ref_period
```

Compatibility mapping remains:

```text
buy_target_price  -> buy-side reference_target_price
sell_target_price -> sell-side reference_target_price
clear_sell_ref_period = up_sell_reference_period
```

Until 027 is executed and code alignment is separately authorized, N2 writers should not assume the new columns exist.

## Remaining Blockers Before Execution

```text
1. User confirmation is required before executing 027.
2. The 027 migration has not been applied.
3. N2 business writers do not yet populate the new canonical fields.
4. Existing policy/UI divergence around require_clear_sell_ref_period still needs a separate code alignment gate.
```

The `base_price_policy` enum is reconciled with `docs/V3_SYMMETRY_TARGET_PRICE_SPEC.md`:

```text
MIN_CLOSE_AFTER_LAST_LOWER_UP_SEGMENT_PLUS_TRIGGER_OPEN
```

`reference_body_boundary` is only a legacy descriptive phrase and is not a DB enum.

## Readiness

```text
DRAFT_PASS
ready_to_execute_migration=false
requires_user_confirmation=true
database_touched=false
business_rows_written=false
downstream_layers_touched=false
old_system_touched=false
```
