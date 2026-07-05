# N3/N4/N5 Structured Query Audit Remaining Trigger/Action/Scripts Adoption Dry Run

Gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_REMAINING_TRIGGER_ACTION_SCRIPTS_ADOPTION_DRY_RUN`

Result: `DRY_RUN_PASS`

Layer role: `runtime_control`

Generated on: `2026-06-07`

## Objective

Read-only classification of the direct `psycopg.connect` sites still present after Phase 1, Phase 2, and Phase 3 structured query audit adoption.

No code was changed by this dry-run. No database writes, runner execution, worker startup, outbox/inbox/checkpoint mutation, delivery, sim, position, PnL, real trade, proposal, order, or trade was authorized.

## Current Static Inventory

Remaining direct sites: `64`

| Scope | Sites |
|---|---:|
| `src/ashare_v3/trigger` | 24 |
| `src/ashare_v3/action` | 2 |
| `scripts` | 38 |

The inventory matches the Phase 3 post-review global remaining count: `64`.

## Classification Summary

| Classification | Count |
|---|---:|
| `must_wrap` | 3 |
| `explicit_bypass_readonly_plan` | 24 |
| `out_of_scope_migration_or_schema_review` | 4 |
| `out_of_scope_n1_n2_or_migration` | 33 |
| `blocked_until_refactored` | 0 |
| `unclassified` | 0 |
| Total | 64 |

## Selected Next Implementation Scope

Selected sites: `31`

Files:

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

Expected remaining direct sites after implementation: `33`, all documented N1/N2/ingestion cross-layer scripts.

## Deferred Cross-Layer Remainder

Deferred sites: `33`

Classification: `out_of_scope_n1_n2_or_migration`

These sites require explicit `N1_ingestion` or `N2_condition` gates if structured audit adoption is later required. They are not authorized for modification by this runtime-control adoption gate.

## Planned Remediation Items

1. Extend or reuse N4 trigger audit helpers so execute, readonly plan, and schema-review paths have explicit helper functions.
2. Expose an N5 schema-review audit helper for action schema migration review paths.
3. Replace remaining direct trigger `psycopg.connect` sites with audited helpers while preserving original runner semantics.
4. Replace selected N4/N3 read-only script direct connects with audited readonly helpers.
5. Add remaining-adoption static coverage tests and denylist before-execution regression tests.

## P0/P1/P2

`P0/P1/P2 = 0/2/0`

P1 items:

- `REMAINING-DRY-P1-001`: 31 selected sites are classified but not yet adopted.
- `REMAINING-DRY-P1-002`: 33 N1/N2/ingestion script sites remain deferred to layer-specific gates.

No P0 blocker exists for contract generation.

## Forbidden Scope Proof

This dry-run did not authorize or perform:

- DB writes or migrations
- N3/N4/N5 runner execution
- worker startup
- outbox/inbox/checkpoint consumption or mutation
- `pg_stat_statements` enablement
- PostgreSQL config changes
- delivery, push, voice, or mobile
- sim, position, PnL, or real trade
- proposal, order, or trade

## Next Gate Recommendation

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_REMAINING_TRIGGER_ACTION_SCRIPTS_ADOPTION_IMPLEMENTATION_GATE`
