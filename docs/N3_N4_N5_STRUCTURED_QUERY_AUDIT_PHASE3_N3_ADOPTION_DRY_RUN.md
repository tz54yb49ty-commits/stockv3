# N3/N4/N5 Structured Query Audit Phase 3 N3 Adoption Dry-Run

Result: `DRY_RUN_PASS_WITH_P1_REMAINDERS`

Date: `2026-06-07`

Layer role: `runtime_control`

## Purpose

This dry-run inventories and classifies N3 market-data `psycopg.connect` sites for Phase 3 structured query audit adoption.

This gate does not change code, write the database, execute any N3 runner, pull market data, consume outbox/inbox/checkpoint, or start workers.

## Current Inventory

After Phase 2 N5 adoption:

| Scope | Direct sites |
|---|---:|
| `src/ashare_v3/market` | 70 |
| `src/ashare_v3/trigger` | 24 |
| `src/ashare_v3/action` | 2 |
| `scripts` | 38 |
| Total | 134 |

Phase 3 selected scope:

```text
src/ashare_v3/market
```

## Classification Draft

| Classification | Direct sites | Meaning |
|---|---:|---|
| `must_wrap` | 40 | N3 execute/write paths; must route through audit guard before DB execution |
| `explicit_bypass_readonly_plan` | 26 | Read-only plan, dry-run, preflight, readiness, probe, or payload-builder paths |
| `out_of_scope_migration_or_schema_review` | 4 | Schema/migration review helpers, not N3 runtime adoption |
| `blocked_until_refactored` | 0 | None in selected scope |
| unclassified | 0 | None in selected scope |

Mixed files that require line-level treatment:

| File | `must_wrap` lines | read-only lines |
|---|---:|---:|
| `src/ashare_v3/market/action_confirmation_metric_materialization_execute.py` | 365 | 600, 663, 748, 931, 2437 |
| `src/ashare_v3/market/previous_day_full_context_expansion_subscription_scope.py` | 459 | 74, 581, 586 |

## Proposed Implementation Shape

Create:

```text
src/ashare_v3/market/query_audit_phase3.py
```

Required helpers:

```text
audited_n3_market_execute_connect
audited_n3_market_readonly_plan_connect
audited_n3_market_schema_review_connect
```

All helpers must use artifact-first audit sinks and must not write audit rows to the database.

## Blockers / P0/P1/P2

```text
P0=0
P1=2
P2=0
```

P1:

1. Phase 3 selected N3 sites are classified but not yet adopted into code.
2. Global remaining direct sites outside Phase 3 stay documented for later trigger/action/scripts gates.

## Validation

```text
JSON parse = PASS
static inventory = PASS, phase3_selected=70, market_total=70, global=134
classification baseline = PASS, unclassified=0, blocked_until_refactored=0
existing tests = PASS, 7 + 4 + 2 + 4
git diff --check = PASS
```

## Forbidden Scope Proof

This dry-run did not:

- modify code
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
