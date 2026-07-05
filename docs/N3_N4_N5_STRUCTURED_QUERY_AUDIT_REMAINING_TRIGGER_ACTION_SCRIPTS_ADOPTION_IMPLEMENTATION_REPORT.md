# N3/N4/N5 Structured Query Audit Remaining Trigger/Action/Scripts Adoption Implementation Report

Gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_REMAINING_TRIGGER_ACTION_SCRIPTS_ADOPTION_IMPLEMENTATION_GATE`

Result: `IMPLEMENTATION_PASS`

Layer role: `runtime_control`

Generated on: `2026-06-07`

## Objective

Adopt the structured query audit wrapper for the `31` selected remaining trigger/action/script direct `psycopg.connect` sites, without executing N3/N4/N5 runners, writing database rows, consuming outbox/inbox/checkpoint rows, or starting workers.

## Implementation Summary

| Item | Count |
|---|---:|
| Selected direct sites before | 31 |
| Selected direct sites after | 0 |
| `src/ashare_v3/trigger` direct sites after | 0 |
| `src/ashare_v3/action` direct sites after | 0 |
| `scripts` direct sites after | 33 |
| Global remaining direct sites after | 33 |

The remaining `33` sites are the contract-deferred N1/N2/ingestion scripts. They remain out of this runtime-control implementation scope.

## Helper Changes

- `src/ashare_v3/trigger/query_audit_phase1.py`
  - N4 audited helper now supports injected `sink` / `connect` for tests.
  - Added `audited_n4_schema_review_connect`.
  - Schema-review helper records `out_of_scope_migration_or_schema_review`.

- `src/ashare_v3/action/query_audit_phase2.py`
  - Added `audited_n5_schema_review_connect`.
  - Schema-review helper records `out_of_scope_migration_or_schema_review`.

## Adopted Files

- `src/ashare_v3/trigger/action_confirmation_metric_execute.py`
- `src/ashare_v3/trigger/c3_replay_audit_execute.py`
- `src/ashare_v3/trigger/c3_replay_plan.py`
- `src/ashare_v3/trigger/context_preflight.py`
- `src/ashare_v3/trigger/local_trigger_dry_run.py`
- `src/ashare_v3/trigger/migration_execute.py`
- `src/ashare_v3/trigger/projection_matcher.py`
- `src/ashare_v3/trigger/projection_matcher_execute.py`
- `src/ashare_v3/trigger/synthetic_dry_run.py`
- `src/ashare_v3/action/schema_migration_execute.py`
- `scripts/plan_n4_trigger_rule_v4_full_lineage_dry_run.py`
- `scripts/probe_board_market_data_adapter.py`

## TDD Proof

Red command:

```bash
python3 -m unittest tests/test_structured_query_audit_remaining_adoption.py
```

Red result:

- Failed with `31` selected direct `psycopg.connect` sites.
- Failed on missing `audited_n5_schema_review_connect`.

Green command:

```bash
python3 -m unittest tests/test_structured_query_audit_remaining_adoption.py
```

Green result:

- `Ran 2 tests OK`

## Static Coverage Summary

Selected scope direct sites: `0`

By scope:

| Scope | Direct sites |
|---|---:|
| `src/ashare_v3/trigger` | 0 |
| `src/ashare_v3/action` | 0 |
| `scripts` | 33 |

Remaining script sites are the deferred N1/N2/ingestion sites documented by the contract.

## Validation

Commands run:

```bash
PYTHONPATH=src:scripts python3 -m unittest tests/test_structured_query_audit.py tests/test_structured_query_audit_static_coverage.py tests/test_structured_query_audit_phase1_adoption.py tests/test_structured_query_audit_phase2_adoption.py tests/test_structured_query_audit_phase3_adoption.py tests/test_structured_query_audit_remaining_adoption.py
PYTHONPATH=src:scripts python3 -m compileall src/ashare_v3/observability src/ashare_v3/trigger src/ashare_v3/action scripts/plan_n4_trigger_rule_v4_full_lineage_dry_run.py scripts/probe_board_market_data_adapter.py
git diff --check
```

Results:

- Structured query audit suite: `Ran 22 tests OK`
- Compileall: `PASS`
- `git diff --check`: `PASS`

## P0/P1/P2

`P0/P1/P2 = 0/1/0`

P1:

- `REMAINING-IMPL-P1-001`: 33 N1/N2/ingestion script direct connect sites remain out of runtime-control adoption scope and require layer-specific gates if they need audit wrapper adoption.

## Forbidden Scope Proof

This implementation did not perform or authorize:

- DB writes or migrations
- `pg_stat_statements` enablement
- PostgreSQL config changes
- N3/N4/N5 runner execution
- worker startup
- outbox/inbox/checkpoint consumption or mutation
- delivery, push, voice, or mobile
- sim, position, PnL, or real trade
- proposal, order, or trade

## Next Gate Recommendation

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_REMAINING_TRIGGER_ACTION_SCRIPTS_ADOPTION_POST_REVIEW_GATE`
