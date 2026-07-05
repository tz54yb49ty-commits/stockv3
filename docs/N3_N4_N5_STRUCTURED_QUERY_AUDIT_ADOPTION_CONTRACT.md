# N3_N4_N5_STRUCTURED_QUERY_AUDIT_ADOPTION_CONTRACT_GATE

Result: **CONTRACT_PASS**

Layer role: `runtime_control`

This contract defines phased adoption of the structured query audit wrapper. It does not modify code, integrate real N3/N4/N5 runners, write database rows, enable `pg_stat_statements`, change PostgreSQL config, run migrations, consume outbox/inbox/checkpoint, start workers, or enter downstream delivery/sim/trade scopes.

## Current State

- wrapper implementation: `IMPLEMENTATION_PASS`
- tests passed previously: `7 + 4`
- current direct `psycopg.connect` sites: 164
- current wrapper adoption into real N3/N4/N5 runners: none
- previous P0/P1/P2: `0 / 2 / 1`

## Adoption Strategy

Adopt in phases. Do not change all 164 sites at once.

1. Phase 1: N4 trigger high-risk files
2. Phase 2: N5 action execute and metadata paths
3. Phase 3: N3 market execute paths
4. Phase 4: scripts and remaining readonly plan paths

Script buckets:

- N3/N4/N5 runtime entrypoints
- N1/N2/ingestion/condition out-of-scope
- migration/review helpers out-of-scope

Valid classifications:

- `must_wrap`
- `explicit_bypass_readonly_plan`
- `explicit_bypass_one_time_context_refresh`
- `out_of_scope_n1_n2_or_migration`
- `blocked_until_refactored`

## Phase 1 Recommendation

Target files:

- `src/ashare_v3/trigger/context_execute.py`
- `src/ashare_v3/trigger/run_once_execute.py`
- `src/ashare_v3/trigger/rule_v4_execute.py`
- `src/ashare_v3/trigger/standard_trigger_execute.py`
- `src/ashare_v3/trigger/action_confirmation_metric_matcher.py`
- `scripts/run_n4_20260605_matched_only_execute_once.py`
- `scripts/run_n4_20260605_v4_corrected_execute_once.py`
- `scripts/plan_n4_20260605_v4_corrected_execute_contract.py`
- `scripts/plan_n4_20260605_v4_corrected_dry_run.py`

Phase 1 sites:

- total direct sites: 24
- unclassified: 0
- `must_wrap`: 12
- `explicit_bypass_one_time_context_refresh`: 9
- `explicit_bypass_readonly_plan`: 3

`scripts/run_n4_20260605_matched_only_execute_once.py` is a phase target but currently has no direct `psycopg.connect` site.

## Classification Baseline Summary

Current 164-site draft:

| classification | site count |
|---|---:|
| `must_wrap` | 12 |
| `explicit_bypass_one_time_context_refresh` | 9 |
| `explicit_bypass_readonly_plan` | 39 |
| `out_of_scope_n1_n2_or_migration` | 40 |
| `blocked_until_refactored` | 64 |
| total | 164 |

The draft classifies all currently inventoried sites, but `blocked_until_refactored` remains a P1 status, not adoption success.

## Acceptance Criteria

- Phase 1 scope unclassified = 0
- denied table guard tests still pass
- no real runner execution
- artifact sink only
- wrapper adoption does not mutate DB
- static coverage report can show phase-specific PASS/BLOCKED
- remaining global unwrapped sites allowed only as documented P1
- JSON parse passes
- `git diff --check` passes

## P0/P1/P2

P0/P1/P2: `0 / 2 / 1`

P1:

- 164 global direct connect sites remain unwrapped; this contract only classifies adoption intent.
- 64 sites remain `blocked_until_refactored`.

P2:

- optional `pg_stat_statements` supplement remains unavailable.

## Forbidden Scope Proof

This gate does not:

- modify code
- write database rows
- enable `pg_stat_statements`
- change PostgreSQL config
- execute migration
- integrate real N3/N4/N5 runner paths
- consume/update outbox/inbox/checkpoint
- start worker
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade

## Next Gate

Recommended next gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE1_N4_ADOPTION_IMPLEMENTATION_GATE`

## Validation

- JSON parse: PASS
- static inventory command: PASS, current raw inventory remains 164 sites / 164 unclassified before applying the adoption baseline
- existing wrapper tests: PASS, 7 + 4 tests
- `git diff --check`: PASS
