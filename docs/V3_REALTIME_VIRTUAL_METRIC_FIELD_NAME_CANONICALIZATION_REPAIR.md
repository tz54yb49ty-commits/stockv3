# V3 Realtime Virtual Metric Field Name Canonicalization Repair

Result: `REPAIR_PASS`

## Decision

- DB column canonical form: PostgreSQL lowercase identifiers.
- Uppercase period names `D/W/M/Q/Y` remain display and payload aliases only.
- Writers canonicalize aliases before insert.

## Alias Examples

- `current_D_body_high` -> `current_d_body_high`
- `current_Y_virtual_amount` -> `current_y_virtual_amount`
- `previous_Y_amount` -> `previous_y_amount`

## Live DB Proof

- `stock_action_confirmation_projection_metric`: canonical columns `56/56`, mixed-case period columns `0`, rows `2914`
- `index_action_confirmation_projection_metric`: canonical columns `56/56`, mixed-case period columns `0`, rows `214`
- `board_action_confirmation_projection_metric`: canonical columns `56/56`, mixed-case period columns `0`, rows `499`

## Boundary

No business data was written. No migration, rollback, wrapper/N3/N4/N5 execution, outbox/inbox/checkpoint consume/update, N6, voice, mobile, sim, or trade path was run.

## Validation

- targeted tests: `13 OK`
- compileall: `PASS`
- JSON parse: `PASS`
- canonical name scan: `PASS`
- git diff --check: `PASS`
