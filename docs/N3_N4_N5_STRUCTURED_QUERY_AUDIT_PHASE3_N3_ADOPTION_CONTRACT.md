# N3/N4/N5 Structured Query Audit Phase 3 N3 Adoption Contract

Result: `CONTRACT_PASS`

Date: `2026-06-07`

Layer role: `runtime_control`

## Purpose

This contract defines Phase 3 adoption of the artifact-first structured query audit wrapper for N3 market-data paths. This gate is contract and classification only.

No code is changed in this gate. No database writes, N3 runner execution, market-data pull, outbox/inbox/checkpoint mutation, worker startup, delivery, simulation, position, PnL, order, trade, or real trade is allowed.

## Inputs

- `docs/N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_N5_ADOPTION_POST_REVIEW.md/json`
- `docs/N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_N5_ADOPTION_IMPLEMENTATION_REPORT.md/json`
- `docs/N3_N4_N5_STRUCTURED_QUERY_AUDIT_ADOPTION_CONTRACT.md/json`
- `docs/N3_N4_N5_STRUCTURED_QUERY_AUDIT_ADOPTION_DRY_RUN.md/json`
- `src/ashare_v3/observability/query_audit.py`

## Current State

Phase 1 N4 adoption is `POST_REVIEW_PASS`.

Phase 2 N5 adoption is `POST_REVIEW_PASS`.

Current direct `psycopg.connect` remainder after Phase 2:

| Scope | Direct sites |
|---|---:|
| `src/ashare_v3/market` | 70 |
| `src/ashare_v3/trigger` | 24 |
| `src/ashare_v3/action` | 2 |
| `scripts` | 38 |
| Total | 134 |

## Phase 3 Scope

Phase 3 selected scope is `src/ashare_v3/market`.

Script entrypoints are classified for traceability only in this contract gate. They are not modified here.

Implementation must create an N3 helper:

```text
src/ashare_v3/market/query_audit_phase3.py
```

Required helper functions:

```text
audited_n3_market_execute_connect
audited_n3_market_readonly_plan_connect
audited_n3_market_schema_review_connect
```

## Classification Baseline

All 70 selected N3 market direct sites are classified.

| Classification | Count |
|---|---:|
| `must_wrap` | 40 |
| `explicit_bypass_readonly_plan` | 26 |
| `out_of_scope_migration_or_schema_review` | 4 |
| `blocked_until_refactored` | 0 |
| unclassified | 0 |

`must_wrap` covers N3 execute/write paths such as subscription execute, A1 previous-day preload, B1 realtime snapshot, C1 today-minute, B2 projection, action-confirmation metric materialization, C2/C2B/EOD, MinuteBarClosed outbox, and scoped repair/fill writes.

`explicit_bypass_readonly_plan` covers plan, dry-run, readiness, preflight, probe, and payload-builder paths that must remain read-only.

`out_of_scope_migration_or_schema_review` covers schema/migration helpers and is not part of N3 runtime adoption.

## Guard Policy

N3 runtime/execute paths must block before DB execution if SQL references:

```text
stock_condition_display_basis
index_condition_display_basis
board_condition_display_basis
index_membership_fact
board_membership_fact
```

Allowed N3 sources are limited to approved condition scope, N3 subscription/pull-plan/control rows, N3 market facts, N3 quality/run rows, event guard metadata, and reviewed N4 TriggerMatched artifacts only for N3 action-confirmation metric materialization.

N3 must not mutate N4/N5/N6. This adoption stream must not consume or update outbox/inbox/checkpoint.

## Acceptance Criteria

- Phase 3 selected `src/ashare_v3/market` direct `psycopg.connect` sites become zero after implementation.
- Phase 3 selected unclassified sites remain zero.
- Phase 3 selected `blocked_until_refactored` sites remain zero.
- Denied display/membership table SQL blocks before cursor execution for N3 execute paths.
- Artifact sink remains local JSON only.
- Application name includes `layer_role`, `source_run_id`, `stage_id`, and `gate_id`.
- No real N3 runner is executed by tests.
- No DB writes occur in contract, dry-run, or post-review gates.
- Remaining trigger/action/scripts sites stay documented as P1 until later gates.

## P0/P1/P2

```text
P0=0
P1=2
P2=0
```

P1 items:

1. Phase 3 selected N3 sites are classified but not yet adopted into code.
2. Global remaining trigger/action/scripts direct sites remain documented for later gates.

## Validation

```text
JSON parse contract = PASS
JSON parse dry-run = PASS
test_structured_query_audit.py = PASS, 7 tests
test_structured_query_audit_static_coverage.py = PASS, 4 tests
test_structured_query_audit_phase1_adoption.py = PASS, 2 tests
test_structured_query_audit_phase2_adoption.py = PASS, 4 tests
phase3 static inventory = PASS, market=70, must_wrap=40, readonly=26, out_of_scope=4, global=134
git diff --check = PASS
```

## Forbidden Scope Proof

This gate did not:

- change code
- write database rows
- execute N3 runners
- pull market data
- write minute rows
- consume/update outbox, inbox, or checkpoint
- start workers
- enter N4/N5/N6
- trigger delivery, push, voice, mobile, sim, position, PnL, real trade, proposal, order, or trade
- enable `pg_stat_statements`
- change PostgreSQL config
- execute migration

## Next Gate

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE3_N3_ADOPTION_IMPLEMENTATION_GATE`
