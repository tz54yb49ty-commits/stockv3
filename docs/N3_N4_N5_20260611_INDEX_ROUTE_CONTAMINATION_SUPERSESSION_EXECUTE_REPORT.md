# N3/N4/N5 20260611 Index Route Contamination Supersession Execute Report

## Result

- result: `SUPERSESSION_EXECUTE_PASS`
- decision: `CONTAMINATED_LINEAGE_SUPERSEDED_AND_BLOCKED_FROM_FUTURE_CONSUMPTION`
- SQL: `sql/N3_N4_N5_20260611_index_route_contamination_supersession.sql`
- rollback registry: `sql/N3_N4_N5_20260611_index_route_contamination_supersession_rollback.sql`

## Superseded Runs

- N3 B1 standard outbox: `superseded`
- N3 B2 trace-aligned projection: `superseded`
- N4 production semantic replay: `superseded`
- N5 action run: `superseded`

## Outbox Post Status

- N3 `MarketSnapshotUpdated`: dead_letter `2100`, pending `0`
- N4 `TriggerMatched`: dead_letter `548`
- N4 `TriggerPendingMarketData`: dead_letter `251`
- N4 pending outbox: `0`
- N5 `ActionBlocked`: dead_letter `548`
- N5 pending outbox: `0`

## Audit Facts Retained

- N4 trigger_state rows: `799`
- N4 trigger_match rows: `548`
- N5 action_event rows: `548`

These rows are retained as superseded historical evidence. No row deletion was performed.

## Scheduler State

- N3 chain scheduler: `not_loaded`
- N4 bounded polling scheduler: `not_loaded`

## Boundary Proof

- deleted rows: `0`
- rollback executed: `false`
- N6/user projection entered: `false`
- voice/mobile/sim/trade touched: `false`
- old system touched: `false`
