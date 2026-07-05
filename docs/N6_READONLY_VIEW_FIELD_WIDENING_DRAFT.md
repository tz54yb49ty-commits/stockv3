# N6 Readonly View Field Widening Draft

Gate: `N6_READONLY_VIEW_FIELD_WIDENING_DRAFT_GATE`  
Layer role: `runtime_control`  
Status: `DRAFT_PASS`

## Goal

Generate a draft migration and rollback for widening N6/B-track readonly views so the official view layer can expose the N2 `condition_display_basis` source fields and membership audit fields without allowing B-track to read base tables directly.

## Generated Artifacts

```text
sql/N6_readonly_view_field_widening.sql
sql/N6_readonly_view_field_widening_rollback.sql
docs/N6_READONLY_VIEW_FIELD_WIDENING_DRAFT.md
docs/N6_READONLY_VIEW_FIELD_WIDENING_DRAFT.json
docs/N6_READONLY_VIEW_FIELD_WIDENING_FIELD_MAPPING.md
docs/N6_READONLY_VIEW_FIELD_WIDENING_FIELD_MAPPING.json
```

## Widened View Scope

The draft widens five readonly views:

```text
v_n6_stock_condition_display_basis
v_n6_index_condition_display_basis
v_n6_board_condition_display_basis
v_n6_index_membership_fact
v_n6_board_membership_fact
```

No base table is granted to B-track. The official B-track data boundary remains the `v_n6_*` readonly views.

## Field Mapping Summary

The display views preserve existing columns and append missing source fields at the end.

| View | Current columns | Draft widened columns | Main additions |
|---|---:|---:|---|
| `v_n6_stock_condition_display_basis` | 68 | 131 | source trace, trigger baseline, structural trace, symmetry/target trace, secondary anchors, structure scores, stock financial/risk fields |
| `v_n6_index_condition_display_basis` | 57 | 100 | source trace, trigger baseline, structural trace, symmetry/target trace, secondary anchors, structure scores |
| `v_n6_board_condition_display_basis` | 57 | 100 | source trace, trigger baseline, structural trace, symmetry/target trace, secondary anchors, structure scores |

The source-specific display basis id is appended in addition to the existing normalized `source_display_basis_id` alias. This keeps existing API compatibility while allowing full source-table field visibility.

## Membership View Decision

Membership views should also be widened lightly.

Reason:

```text
index_membership_fact and board_membership_fact currently expose all relational fields except raw_payload.
raw_payload is the only missing source field and is useful for audit/detail inspection.
Adding raw_payload does not change row grain, source filtering, or membership lookup behavior.
```

Draft additions:

```text
v_n6_index_membership_fact.raw_payload
v_n6_board_membership_fact.raw_payload
```

## Rollback Strategy

Forward widening uses `CREATE OR REPLACE VIEW`, which is compatible with appending columns while preserving existing column order.

Rollback cannot remove columns with `CREATE OR REPLACE VIEW`, so rollback uses:

```text
dependency guard with RAISE EXCEPTION before first DROP
DROP VIEW without CASCADE
CREATE VIEW with the original 036-era definitions
GRANT SELECT only on readonly views
```

Rollback does not drop schema tables, does not touch N1/N2 source tables, and does not touch N3/N4/N5/N6 action/projection/card/outbox/inbox/checkpoint objects.

## Permission Strategy

The draft re-grants SELECT on the five readonly views to `n6_ui_readonly_role` and does not grant SELECT on:

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
index_membership_fact
board_membership_fact
```

## Local Display Cache

The experimental local display cache remains:

```text
experimental/tainted_for_b_track_filter_center
```

This gate does not rollback, activate, sync, or read from local display cache physical tables.

## Forbidden Scope Proof

This draft does not execute migration, does not write database rows, does not modify B-track implementation code, does not consume or update outbox, does not start workers, does not generate proposal/order/trade, does not update position/PnL, and does not submit real trade.

## Next Gate

Allowed next gate:

```text
N6_READONLY_VIEW_FIELD_WIDENING_DRAFT_REVIEW_GATE
```
