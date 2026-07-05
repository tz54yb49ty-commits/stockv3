# N6 Phase 3 038D Position Static Tests

Status: DRAFT_PASS

These checks validate the 038D draft without executing DDL or writing database rows.

## SQL Static Scan

- `CREATE TABLE` count must be 2.
- Created tables must be only `n6_virtual_position` and `n6_virtual_position_event`.
- SQL must not include business DML: `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `COPY`.
- SQL must not alter old tables.
- SQL must not include `DROP`.
- SQL must not include `GRANT`.
- SQL must not include broker, real position, real trade, or real execution fields.

## Model Static Checks

- `n6_virtual_position` must include current-state fields and deterministic run/policy/rollback/lineage fields.
- `n6_virtual_position_event` must include immutable event fields and deterministic run/policy/rollback/lineage fields.
- `n6_virtual_position_event` must not include `updated_at`.
- Quantity fields in `n6_virtual_position` must be non-negative.
- `quantity = available_quantity + locked_quantity` must be checked.
- `last_virtual_trade_id` must reference `n6_virtual_trade`.
- `source_virtual_order_id` and `source_virtual_trade_id` must reference 038C tables.
- Principal ownership must use `(principal_id, principal_type)` composite FK.

## T+1 Static Check

038D may include `available_quantity` and `locked_quantity`; it must not encode T+1 settlement timing, fee/tax rates, or live valuation rules.

## Rollback Static Scan

- Rollback must include `RAISE EXCEPTION` before the first `DROP TABLE`.
- Rollback must block if `n6_virtual_position` has rows.
- Rollback must block if `n6_virtual_position_event` has rows.
- Rollback must block if future `n6_virtual_pnl_snapshot` has rows.
- Rollback must not use `CASCADE`.
- Rollback must drop only `n6_virtual_position_event` and `n6_virtual_position`.
- Rollback must not touch 038A/038B/038C/036/037 objects.
- Rollback must not touch N1-N6 facts or outbox.
