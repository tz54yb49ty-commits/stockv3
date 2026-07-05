# N3/N4/N5 Structured Query Audit Remaining Trigger/Action/Scripts Adoption Contract

Gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_REMAINING_TRIGGER_ACTION_SCRIPTS_ADOPTION_CONTRACT_GATE`

Result: `CONTRACT_PASS`

Layer role: `runtime_control`

Generated on: `2026-06-07`

## Objective

Define the final structured query audit adoption contract for direct `psycopg.connect` sites that remain after:

- Phase 1 N4 adoption post-review pass
- Phase 2 N5 adoption post-review pass
- Phase 3 N3 market adoption post-review pass

This gate is contract-only. It does not modify code, execute runners, write database rows, consume outbox/inbox/checkpoint rows, or start workers.

## Current State

Remaining direct `psycopg.connect` sites: `64`

By scope:

| Scope | Remaining sites |
|---|---:|
| `src/ashare_v3/trigger` | 24 |
| `src/ashare_v3/action` | 2 |
| `scripts` | 38 |

## Adoption Strategy

The next implementation gate should adopt only the remaining in-scope trigger/action/script audit paths:

- Remaining N4 trigger runtime/write paths
- Remaining N4 trigger read-only plan, dry-run, preflight, and replay paths
- Remaining trigger/action schema-review helper paths
- N4 full-lineage dry-run script
- N3 board market-data probe script

Selected next implementation scope: `31` sites.

Deferred cross-layer remainder: `33` sites.

The deferred sites are N1/N2/ingestion/condition scripts and must not be adopted inside this runtime-control gate unless a future `N1_ingestion` or `N2_condition` gate explicitly authorizes that layer.

## Classification Baseline

| Classification | Count |
|---|---:|
| `must_wrap` | 3 |
| `explicit_bypass_readonly_plan` | 24 |
| `out_of_scope_migration_or_schema_review` | 4 |
| `out_of_scope_n1_n2_or_migration` | 33 |
| `blocked_until_refactored` | 0 |
| `unclassified` | 0 |
| Total | 64 |

## Selected Implementation Scope

### Trigger

| File | Sites | Classification | Target helper |
|---|---:|---|---|
| `src/ashare_v3/trigger/action_confirmation_metric_execute.py` | 209 | `must_wrap` | `audited_n4_trigger_connect` |
| `src/ashare_v3/trigger/c3_replay_audit_execute.py` | 269, 675, 689, 705, 722 | `explicit_bypass_readonly_plan` | `audited_n4_readonly_plan_connect` |
| `src/ashare_v3/trigger/c3_replay_audit_execute.py` | 771 | `must_wrap` | `audited_n4_trigger_connect` |
| `src/ashare_v3/trigger/c3_replay_plan.py` | 123, 1362 | `explicit_bypass_readonly_plan` | `audited_n4_readonly_plan_connect` |
| `src/ashare_v3/trigger/context_preflight.py` | 90 | `explicit_bypass_readonly_plan` | `audited_n4_readonly_plan_connect` |
| `src/ashare_v3/trigger/local_trigger_dry_run.py` | 123, 166, 1093, 1121 | `explicit_bypass_readonly_plan` | `audited_n4_readonly_plan_connect` |
| `src/ashare_v3/trigger/migration_execute.py` | 153, 177 | `out_of_scope_migration_or_schema_review` | `audited_n4_schema_review_connect` |
| `src/ashare_v3/trigger/projection_matcher.py` | 128, 169, 780 | `explicit_bypass_readonly_plan` | `audited_n4_readonly_plan_connect` |
| `src/ashare_v3/trigger/projection_matcher_execute.py` | 571 | `explicit_bypass_readonly_plan` | `audited_n4_readonly_plan_connect` |
| `src/ashare_v3/trigger/projection_matcher_execute.py` | 738 | `must_wrap` | `audited_n4_trigger_connect` |
| `src/ashare_v3/trigger/synthetic_dry_run.py` | 95, 702, 725 | `explicit_bypass_readonly_plan` | `audited_n4_readonly_plan_connect` |

### Action

| File | Sites | Classification | Target helper |
|---|---:|---|---|
| `src/ashare_v3/action/schema_migration_execute.py` | 174, 197 | `out_of_scope_migration_or_schema_review` | `audited_n5_schema_review_connect` |

### Scripts

| File | Sites | Classification | Target helper |
|---|---:|---|---|
| `scripts/plan_n4_trigger_rule_v4_full_lineage_dry_run.py` | 240, 295, 369, 400 | `explicit_bypass_readonly_plan` | `audited_n4_readonly_plan_connect` |
| `scripts/probe_board_market_data_adapter.py` | 34 | `explicit_bypass_readonly_plan` | `audited_n3_market_readonly_plan_connect` |

## Deferred Cross-Layer Remainder

The following `33` sites are classified as `out_of_scope_n1_n2_or_migration` and are not authorized for adoption in this gate:

- `scripts/check_condition_source_ready.py`: 274
- `scripts/plan_condition_full_dry_run.py`: 232, 332
- `scripts/plan_n2_context_enrichment_dry_run.py`: 115
- `scripts/plan_n2_context_enrichment_materialization.py`: 139
- `scripts/repair_index_daily_000001_history.py`: 799
- `scripts/run_condition_source_activation_20260526_once.py`: 52
- `scripts/run_condition_source_activation_20260526_v2_once.py`: 50
- `scripts/run_condition_source_activation_20260527_once.py`: 45
- `scripts/run_condition_source_activation_20260528_once.py`: 47
- `scripts/run_condition_source_activation_20260529_once.py`: 47
- `scripts/run_condition_source_activation_20260601_once.py`: 47
- `scripts/run_condition_source_activation_20260602_once.py`: 46
- `scripts/run_index_daily_20260526_expansion_once.py`: 47
- `scripts/run_n2_context_enrichment_materialization_execute.py`: 81
- `scripts/run_official_daily_ingestion_20260525_once.py`: 59
- `scripts/run_official_daily_ingestion_20260526_once.py`: 57
- `scripts/run_official_daily_ingestion_20260526_v2_once.py`: 55
- `scripts/run_official_daily_ingestion_20260527_once.py`: 55
- `scripts/run_official_daily_ingestion_20260528_once.py`: 57
- `scripts/run_official_daily_ingestion_20260529_once.py`: 57
- `scripts/run_official_daily_ingestion_20260601_once.py`: 59
- `scripts/run_official_daily_ingestion_20260602_once.py`: 61
- `scripts/run_real_daily_incremental.py`: 1387
- `scripts/run_real_initial_ingestion.py`: 1646
- `scripts/run_stock_financial_canonical_metrics_20260529_once.py`: 40
- `scripts/run_stock_identity_20260527_refresh_once.py`: 46
- `scripts/run_stock_identity_refresh_20260529_once.py`: 48
- `scripts/run_trade_calendar_patch_20260526_once.py`: 80
- `scripts/run_trade_calendar_patch_20260527_once.py`: 81
- `scripts/run_trade_calendar_patch_20260528_once.py`: 81
- `scripts/run_trade_calendar_patch_20260529_once.py`: 81
- `scripts/run_trade_calendar_patch_once.py`: 96

## Helper Contract

Trigger paths should reuse `src/ashare_v3/trigger/query_audit_phase1.py`.

Required trigger helper behavior:

- `audited_n4_trigger_connect` for execute/write paths
- `audited_n4_readonly_plan_connect` for dry-run/preflight/plan paths
- `audited_n4_schema_review_connect` for schema-review helper paths

Action paths should reuse `src/ashare_v3/action/query_audit_phase2.py`.

Required action helper behavior:

- `audited_n5_schema_review_connect` for action schema-review helper paths

Script paths should import the existing layer helper that matches the script purpose:

- N4 full-lineage dry-run: `audited_n4_readonly_plan_connect`
- N3 board market-data probe: `audited_n3_market_readonly_plan_connect`

## Denylist Policy

The audit guard must block direct reads before cursor execution for:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

The guard also preserves the established boundary against raw K, N1 raw facts, direct live market access from N4/N5, N4 raw facts bypass from N5, N5 raw facts bypass from N6, and unreviewed outbox direct consumption.

## Acceptance Criteria

- Selected remaining implementation scope direct `psycopg.connect` sites become zero.
- All selected sites carry layer, source run, stage, gate, and application-name context.
- Denied display-basis and membership-fact SQL blocks before cursor execution.
- Artifact audit sink remains file-based only; no DB audit table is introduced.
- No real N3/N4/N5 runner execution is performed by adoption validation.
- Global remaining direct sites after selected implementation are only documented N1/N2/ingestion cross-layer scripts.
- Existing structured query audit tests and new remaining-adoption static tests pass.
- No database writes, outbox/inbox/checkpoint mutation, worker startup, delivery, sim, position, PnL, real trade, proposal, order, or trade occurs.

## P0/P1/P2

`P0/P1/P2 = 0/2/0`

P1 items:

- `REMAINING-ADOPTION-P1-001`: 31 selected remaining trigger/action/script sites still require implementation adoption.
- `REMAINING-ADOPTION-P1-002`: 33 N1/N2/ingestion script sites remain out of runtime-control adoption scope and require layer-specific gates if they need audit wrapper adoption.

## Forbidden Scope Proof

This gate did not authorize:

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

`N3_N4_N5_STRUCTURED_QUERY_AUDIT_REMAINING_TRIGGER_ACTION_SCRIPTS_ADOPTION_IMPLEMENTATION_GATE`
