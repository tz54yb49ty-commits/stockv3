# N3/N4/N5 Structured Query Audit Phase 2 N5 Adoption Implementation Report

Gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_N5_ADOPTION_IMPLEMENTATION_GATE`

Date: 2026-06-07

Layer role: `runtime_control`

Result: `IMPLEMENTATION_PASS`

## Scope

This gate only adopted the structured query audit wrapper for the selected Phase 2 N5 action files.

It did not execute real N5 runners, write database rows, consume outbox/inbox/checkpoint rows, start workers, enter N6, enable `pg_stat_statements`, change PostgreSQL config, or execute migrations.

## Implementation Summary

- Added N5 Phase 2 helper: `src/ashare_v3/action/query_audit_phase2.py`.
- Extended static classification taxonomy with:
  - `explicit_bypass_metadata_repair`
  - `out_of_scope_migration_or_schema_review`
- Routed selected N5 action paths through audited helpers:
  - `audited_n5_action_connect`
  - `audited_n5_metadata_repair_connect`
  - `audited_n5_readonly_plan_connect`
- Added Phase 2 adoption tests: `tests/test_structured_query_audit_phase2_adoption.py`.

## Phase 2 Adoption Proof

| item | value |
|---|---:|
| baseline selected direct sites | 6 |
| remaining selected direct `psycopg.connect` sites | 0 |
| selected unclassified | 0 |
| selected `blocked_until_refactored` | 0 |
| `must_wrap` adopted | 1/1 |
| `explicit_bypass_metadata_repair` adopted | 1/1 |
| `explicit_bypass_readonly_plan` adopted | 4/4 |

Selected file proof:

| file | baseline sites | remaining direct sites | classification | helper |
|---|---:|---:|---|---|
| `src/ashare_v3/action/execute.py` | 1 | 0 | `must_wrap` | `audited_n5_action_connect` |
| `src/ashare_v3/action/metadata_repair.py` | 1 | 0 | `explicit_bypass_metadata_repair` | `audited_n5_metadata_repair_connect` |
| `src/ashare_v3/action/execute_preflight.py` | 1 | 0 | `explicit_bypass_readonly_plan` | `audited_n5_readonly_plan_connect` |
| `src/ashare_v3/action/preflight.py` | 1 | 0 | `explicit_bypass_readonly_plan` | `audited_n5_readonly_plan_connect` |
| `src/ashare_v3/action/consumer_dry_run.py` | 1 | 0 | `explicit_bypass_readonly_plan` | `audited_n5_readonly_plan_connect` |
| `src/ashare_v3/action/run_once_dry_run.py` | 1 | 0 | `explicit_bypass_readonly_plan` | `audited_n5_readonly_plan_connect` |

## Guard Proof

N5 action denied-table guard:

- denied external display/membership table access blocks before cursor execution.
- covered by `tests/test_structured_query_audit_phase2_adoption.py::test_n5_action_denied_table_blocks_before_cursor_execute`.

Metadata repair audit proof:

- `explicit_bypass_metadata_repair` is a supported classification.
- metadata repair write attempt records `db_write_attempted=true`.
- metadata repair entries retain `bypass_classification=explicit_bypass_metadata_repair`.
- metadata repair denied external display/membership access blocks.

Denied tables:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

## Static Coverage Summary

| item | value |
|---|---:|
| global direct sites before Phase 2 | 140 |
| global direct sites after Phase 2 | 134 |
| `src/ashare_v3/action` direct sites after Phase 2 | 2 |
| selected Phase 2 direct sites after Phase 2 | 0 |

Remaining by scope after Phase 2:

| scope | direct sites |
|---|---:|
| `src/ashare_v3/market` | 70 |
| `src/ashare_v3/trigger` | 24 |
| `src/ashare_v3/action` | 2 |
| `scripts` | 38 |

The two remaining action sites are in `src/ashare_v3/action/schema_migration_execute.py` and remain classified as `out_of_scope_migration_or_schema_review`.

## Forbidden Scope Proof

This gate did not:

- write database rows
- execute real N5 runners
- integrate real N5 execute/worker paths
- consume/update outbox/inbox/checkpoint
- start workers
- enter N6
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade
- enable `pg_stat_statements`
- change PostgreSQL config
- execute migration

## P0/P1/P2

P0/P1/P2: `0 / 1 / 0`

P1:

- 134 global direct `psycopg.connect` sites remain outside Phase 2 selected N5 scope.

This P1 does not block Phase 2 selected N5 adoption completion.

## Validation

- `python3 -m unittest tests/test_structured_query_audit.py`: PASS
- `python3 -m unittest tests/test_structured_query_audit_static_coverage.py`: PASS
- `python3 -m unittest tests/test_structured_query_audit_phase1_adoption.py`: PASS
- `python3 -m unittest tests/test_structured_query_audit_phase2_adoption.py`: PASS
- `python3 -m compileall src/ashare_v3/observability src/ashare_v3/action`: PASS
- Phase 2 static scan: PASS, selected = 0, action = 2, global = 134
- JSON parse: PASS
- `git diff --check`: PASS

## Next Gate

Recommended next gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_N5_ADOPTION_POST_REVIEW_GATE`
