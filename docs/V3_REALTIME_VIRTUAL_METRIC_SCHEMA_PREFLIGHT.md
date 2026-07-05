# V3 Realtime Virtual Metric Schema Preflight

Result: `PREFLIGHT_PASS`

This preflight does not authorize migration execution. It only confirms the schema draft, dry-run artifact, contract artifact, and rollback draft are internally consistent.

Future write scope, after a separate final gate only:

- `stock_action_confirmation_projection_metric`
- `index_action_confirmation_projection_metric`
- `board_action_confirmation_projection_metric`

Forbidden in this gate:

- DB write
- outbox/inbox/checkpoint mutation
- N4/N5/N6 execute
- worker/scheduler start
- voice/mobile/sim/trade

## Field name canonicalization

- DB columns use PostgreSQL lowercase identifiers.
- Display aliases such as `current_D_body_high` map to lowercase DB columns such as `current_d_body_high`.
- Mixed-case DB identifiers are not allowed.
