# N3/N4/N5 Structured Query Audit Phase 1 N4 Adoption Implementation Report

Gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE1_N4_ADOPTION_IMPLEMENTATION_GATE`

Date: 2026-06-07

Layer role: `runtime_control`

Result: `IMPLEMENTATION_PASS`

## Scope

This gate only adopted the artifact-first structured query audit wrapper for the Phase 1 N4 trigger high-risk scope.

It did not execute real N4 runners, write database rows, consume outbox/inbox/checkpoint rows, start workers, or enter N5/N6.

## Implementation Summary

- Added audited connection and cursor proxies in `src/ashare_v3/observability/query_audit.py`.
- Added N4 Phase 1 helper `src/ashare_v3/trigger/query_audit_phase1.py`.
- Routed Phase 1 N4 direct connection sites through audited helpers.
- Added Phase 1 adoption tests in `tests/test_structured_query_audit_phase1_adoption.py`.

Audited cursor behavior:

- `execute` and `executemany` route through the audit guard before database cursor execution.
- denied-table references in N4 intraday execute path block before cursor execution.
- `application_name` is built from layer/source_run/stage/gate context.
- audit sink is local artifact-first JSON only; no DB audit table is created.

## Phase 1 Adoption Proof

Baseline Phase 1 direct `psycopg.connect` sites: 24

Remaining Phase 1 direct `psycopg.connect` sites after implementation: 0

Phase 1 unclassified: 0

Phase 1 `blocked_until_refactored`: 0

| classification | baseline sites | adopted sites | helper |
|---|---:|---:|---|
| `must_wrap` | 12 | 12 | `audited_n4_trigger_connect` |
| `explicit_bypass_one_time_context_refresh` | 9 | 9 | `audited_n4_context_refresh_connect` |
| `explicit_bypass_readonly_plan` | 3 | 3 | `audited_n4_readonly_plan_connect` |

Target file proof:

| file | baseline sites | remaining direct sites | classification |
|---|---:|---:|---|
| `src/ashare_v3/trigger/context_execute.py` | 9 | 0 | `explicit_bypass_one_time_context_refresh` |
| `src/ashare_v3/trigger/run_once_execute.py` | 4 | 0 | `must_wrap` |
| `src/ashare_v3/trigger/rule_v4_execute.py` | 1 | 0 | `must_wrap` |
| `src/ashare_v3/trigger/standard_trigger_execute.py` | 2 | 0 | `must_wrap` |
| `src/ashare_v3/trigger/action_confirmation_metric_matcher.py` | 3 | 0 | `must_wrap` |
| `scripts/run_n4_20260605_matched_only_execute_once.py` | 0 | 0 | no direct site |
| `scripts/run_n4_20260605_v4_corrected_execute_once.py` | 2 | 0 | `must_wrap` |
| `scripts/plan_n4_20260605_v4_corrected_execute_contract.py` | 2 | 0 | `explicit_bypass_readonly_plan` |
| `scripts/plan_n4_20260605_v4_corrected_dry_run.py` | 1 | 0 | `explicit_bypass_readonly_plan` |

## Static Coverage Summary

Global direct `psycopg.connect` sites before Phase 1: 164

Global direct `psycopg.connect` sites after Phase 1: 140

Remaining global unwrapped sites: 140, retained as P1 for later N5/N3/scripts adoption gates.

After Phase 1 by scope:

| scope | direct sites |
|---|---:|
| `src/ashare_v3/market` | 70 |
| `src/ashare_v3/trigger` | 24 |
| `src/ashare_v3/action` | 8 |
| `scripts` | 38 |

## Denied Table Guard Proof

The Phase 1 adoption test verifies that a denied table query in an N4 intraday execute path raises before the wrapped cursor executes SQL.

Covered test:

`tests/test_structured_query_audit_phase1_adoption.py::test_audited_connection_blocks_denied_table_before_cursor_execute`

Denied direct tables:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

## Forbidden Scope Proof

This gate did not:

- write database rows
- execute real N4 runners
- enter N5/N6
- consume/update outbox/inbox/checkpoint
- start workers
- enable `pg_stat_statements`
- change PostgreSQL config
- execute migration
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade

## P0/P1/P2

P0/P1/P2: `0 / 1 / 1`

P1:

- 140 global direct connection sites remain outside Phase 1.

P2:

- optional `pg_stat_statements` supplement remains unavailable.

## Validation

- `python3 -m unittest tests/test_structured_query_audit.py`: PASS
- `python3 -m unittest tests/test_structured_query_audit_static_coverage.py`: PASS
- `python3 -m unittest tests/test_structured_query_audit_phase1_adoption.py`: PASS
- `python3 -m compileall src/ashare_v3/observability src/ashare_v3/trigger scripts/plan_n4_20260605_v4_corrected_execute_contract.py scripts/plan_n4_20260605_v4_corrected_dry_run.py scripts/run_n4_20260605_v4_corrected_execute_once.py`: PASS
- Phase 1 static scan: PASS
- JSON parse: PASS
- `git diff --check`: PASS

## Next Gate

Recommended next gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE1_N4_ADOPTION_POST_REVIEW_GATE`
