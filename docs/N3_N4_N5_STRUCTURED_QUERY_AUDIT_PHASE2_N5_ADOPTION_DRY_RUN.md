# N3/N4/N5 Structured Query Audit Phase 2 N5 Adoption Dry Run

Gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_N5_ADOPTION_DRY_RUN`

Date: 2026-06-07

Layer role: `runtime_control`

Result: `DRY_RUN_PASS_WITH_P1_REMAINDERS`

## Scope

This dry-run inventories and classifies N5 action connection sites for Phase 2 structured query audit adoption.

It does not modify code, write database rows, execute N5 runners, integrate execute/worker paths, consume event infrastructure, start workers, or enter N6.

## Current Inventory

| scope | direct sites |
|---|---:|
| `src/ashare_v3/market` | 70 |
| `src/ashare_v3/trigger` | 24 |
| `src/ashare_v3/action` | 8 |
| `scripts` | 38 |
| global total | 140 |

N5 action direct sites:

- total: 8
- selected Phase 2 action sites: 6
- out-of-scope schema migration sites: 2
- selected N5 script direct sites: 0

## Proposed Phase 2 Targets

| file | direct site | classification |
|---|---|---|
| `src/ashare_v3/action/execute.py` | `execute.py:874` | `must_wrap` |
| `src/ashare_v3/action/metadata_repair.py` | `metadata_repair.py:423` | `explicit_bypass_metadata_repair` |
| `src/ashare_v3/action/execute_preflight.py` | `execute_preflight.py:62` | `explicit_bypass_readonly_plan` |
| `src/ashare_v3/action/preflight.py` | `preflight.py:66` | `explicit_bypass_readonly_plan` |
| `src/ashare_v3/action/consumer_dry_run.py` | `consumer_dry_run.py:59` | `explicit_bypass_readonly_plan` |
| `src/ashare_v3/action/run_once_dry_run.py` | `run_once_dry_run.py:159` | `explicit_bypass_readonly_plan` |

Out of scope:

| file | direct sites | classification |
|---|---|---|
| `src/ashare_v3/action/schema_migration_execute.py` | `schema_migration_execute.py:174`, `schema_migration_execute.py:197` | `out_of_scope_migration_or_schema_review` |

## Classification Draft Counts

| classification | site count |
|---|---:|
| `must_wrap` | 1 |
| `explicit_bypass_metadata_repair` | 1 |
| `explicit_bypass_readonly_plan` | 4 |
| `out_of_scope_migration_or_schema_review` | 2 |
| `blocked_until_refactored` | 0 |

Phase 2 selected scope:

- unclassified: 0
- `blocked_until_refactored`: 0

## Script Entrypoint Inventory

Direct sites in selected N5 script entrypoints: 0

Runtime execute entrypoint:

- `scripts/run_action_consumer_once.py`

Metadata repair entrypoint:

- `scripts/run_n5_full_metric_union_metadata_repair.py`

Read-only plan/review entrypoints:

- `scripts/plan_action_consumer_dry_run.py`
- `scripts/plan_action_consumer_run_once_dry_run.py`
- `scripts/plan_action_preflight_dry_run.py`
- `scripts/review_action_execute_preflight.py`
- `scripts/check_n5_contract.py`

Out-of-scope schema entrypoints:

- `scripts/run_action_schema_011_migration.py`
- `scripts/review_action_schema_migration.py`
- `scripts/review_action_schema_event_contract.py`

## Blockers

P0/P1/P2: `0 / 2 / 1`

P1:

- Phase 2 selected N5 sites are classified but not yet adopted into code.
- Global remaining direct sites outside selected Phase 2 scope remain documented for later N3/trigger/scripts gates.

P2:

- Phase 2 taxonomy introduces metadata-repair and migration/schema classifications not yet present in `VALID_CONNECTION_SITE_CLASSIFICATIONS`.

## Forbidden Scope Proof

This dry-run did not:

- modify code
- write database rows
- execute N5 runners
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

## Next Gate

Recommended next gate:

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_PHASE2_N5_ADOPTION_IMPLEMENTATION_GATE`

## Validation

- JSON parse: PASS
- static inventory: PASS, Phase 2 selected action direct sites = 6, action total = 8, global direct sites = 140
- existing structured query audit tests: PASS, 7 + 4 + 2 tests
- `git diff --check`: PASS
