# N6 Readonly View Field Widening Post Review

Gate: `N6_READONLY_VIEW_FIELD_WIDENING_POST_REVIEW_REGISTRATION_GATE`  
Layer role: `runtime_control`  
Status: `POST_REVIEW_PASS`  
Review time: `2026-06-07 16:08:19+08:00`

## Execution Summary

N6 readonly view field widening migration executed successfully.

Target DB:

```text
database=ashare_v3
user=ashare_v3_user
host=127.0.0.1
port=5432
```

Executed scope:

```text
CREATE OR REPLACE VIEW v_n6_stock_condition_display_basis
CREATE OR REPLACE VIEW v_n6_index_condition_display_basis
CREATE OR REPLACE VIEW v_n6_board_condition_display_basis
CREATE OR REPLACE VIEW v_n6_index_membership_fact
CREATE OR REPLACE VIEW v_n6_board_membership_fact
GRANT SELECT ON readonly views TO n6_ui_readonly_role
```

## View Column Count Proof

| View | Column count |
|---|---:|
| `v_n6_stock_condition_display_basis` | 131 |
| `v_n6_index_condition_display_basis` | 100 |
| `v_n6_board_condition_display_basis` | 100 |
| `v_n6_index_membership_fact` | 13 |
| `v_n6_board_membership_fact` | 14 |

## Field Coverage Proof

Required field missing count:

```text
v_n6_stock_condition_display_basis = 0
v_n6_index_condition_display_basis = 0
v_n6_board_condition_display_basis = 0
v_n6_index_membership_fact = 0
v_n6_board_membership_fact = 0
```

Validated field groups:

```text
source trace
period_trigger_baseline_json
structural trace
symmetry / target trace
secondary anchor fields
structure score fields
stock-only financial / risk fields
membership raw_payload
```

## Permission Proof

`n6_ui_readonly_role` exists:

```text
true
```

`n6_ui_readonly_role` can SELECT:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

`n6_ui_readonly_role` cannot SELECT:

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
index_membership_fact
board_membership_fact
```

## Compatibility Proof

The widened views preserve the 036-era column prefix:

```text
v_n6_stock_condition_display_basis existing prefix = 68 columns
v_n6_index_condition_display_basis existing prefix = 57 columns
v_n6_board_condition_display_basis existing prefix = 57 columns
v_n6_index_membership_fact existing prefix = 12 columns
v_n6_board_membership_fact existing prefix = 13 columns
```

New fields are appended after the existing prefix for all five views. Existing B-track API readers should not break because existing column names and order are preserved.

Field display/hide behavior remains a future UI/API gate. This migration only widens readonly source availability.

## Forbidden Scope Proof

Event infrastructure counts after post-review:

| Table | Count |
|---|---:|
| `common_event_outbox` | 188736 |
| `common_event_inbox` | 90362 |
| `common_event_consumer_checkpoint` | 5170 |

Forbidden scope remained false:

```text
business_rows_written=false
base_tables_modified=false
base_tables_granted=false
local_display_cache_synced=false
local_display_cache_activated=false
local_display_cache_rollback=false
outbox_consumed_or_updated=false
worker_started=false
proposal_order_trade_generated=false
position_pnl_updated=false
real_trade_submitted=false
action_flow_modified=false
```

Local display cache remains:

```text
experimental/tainted_for_b_track_filter_center
```

## Rollback Summary

Rollback SQL:

```text
sql/N6_readonly_view_field_widening_rollback.sql
```

Rollback proof:

```text
RAISE EXCEPTION before first DROP VIEW = true
drop/recreate only five readonly views = true
restores 036-era view definitions = true
no CASCADE = true
no DROP TABLE = true
no TRUNCATE = true
does not touch source tables = true
does not touch action flow = true
does not touch outbox/inbox/checkpoint = true
does not touch local display cache = true
```

## Closeout Decision

N6 readonly view field widening can be marked complete.

Next recommended gate:

```text
B_TRACK_V2_FIELD_VISIBILITY_POLICY_DESIGN_GATE
```

Purpose: decide which newly available readonly fields should be shown in B-track UI/API, hidden by default, or exposed only in detail/audit panels.
