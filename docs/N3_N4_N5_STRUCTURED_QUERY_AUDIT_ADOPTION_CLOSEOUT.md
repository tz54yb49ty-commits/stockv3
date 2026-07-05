# N3/N4/N5 Structured Query Audit Adoption Closeout

Gate: `N3_N4_N5_STRUCTURED_QUERY_AUDIT_ADOPTION_CLOSEOUT_GATE`

Result: `CLOSEOUT_PASS`

Layer role: `runtime_control`

Generated on: `2026-06-07`

## Objective

Close out the structured query audit adoption line for N3/N4/N5 intraday/runtime SQL attribution.

This closeout is documentation-only. It does not execute N3/N4/N5 runners, write database rows, run migrations, consume outbox/inbox/checkpoint rows, start workers, or enter delivery, sim, position, PnL, real trade, proposal, order, or trade flows.

## Lineage Summary

| Gate | Status |
|---|---|
| Structured query audit wrapper implementation | `IMPLEMENTATION_PASS` |
| Phase 1 N4 adoption | `POST_REVIEW_PASS` |
| Phase 2 N5 adoption | `POST_REVIEW_PASS` |
| Phase 3 N3 market adoption | `POST_REVIEW_PASS` |
| Remaining trigger/action/scripts adoption | `POST_REVIEW_PASS` |

Decision:

`selected_n3_n4_n5_adoption_complete = true`

## Static Coverage Closeout

Baseline direct sites before adoption: `164`

Current direct `psycopg.connect` sites:

| Scope | Sites |
|---|---:|
| `src/ashare_v3/market` | 0 |
| `src/ashare_v3/trigger` | 0 |
| `src/ashare_v3/action` | 0 |
| `scripts` | 33 |

N3/N4/N5 runtime direct sites: `0`

Global remaining direct sites: `33`

Global remaining scope: N1/N2/ingestion scripts only.

## Audit Capability Closeout

The adopted wrapper provides:

- artifact-first sink
- application-name tagging
- layer/source-run/stage/gate context
- SQL fingerprinting
- referenced table extraction
- denied table guard
- rowcount, duration, and timestamp capture
- side-effect flags
- explicit bypass classifications for schema review, metadata repair, and one-time context refresh

No DB audit table was created.

## Denied Table Policy

N3/N4/N5 guarded paths block these direct reads before cursor execution:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

Future proof of live intraday access should use audited fresh-run artifacts rather than relying on `pg_stat_statements`.

## Accepted Remainder

`P1`: 33 N1/N2/ingestion script direct connect sites remain outside runtime-control N3/N4/N5 adoption scope.

This does not block N3/N4/N5 structured query audit adoption closeout. If those scripts need coverage, open explicit `N1_ingestion` or `N2_condition` gates.

Remaining sites:

- `check_condition_source_ready.py:274`
- `plan_condition_full_dry_run.py:232`
- `plan_condition_full_dry_run.py:332`
- `plan_n2_context_enrichment_dry_run.py:115`
- `plan_n2_context_enrichment_materialization.py:139`
- `repair_index_daily_000001_history.py:799`
- `run_condition_source_activation_20260526_once.py:52`
- `run_condition_source_activation_20260526_v2_once.py:50`
- `run_condition_source_activation_20260527_once.py:45`
- `run_condition_source_activation_20260528_once.py:47`
- `run_condition_source_activation_20260529_once.py:47`
- `run_condition_source_activation_20260601_once.py:47`
- `run_condition_source_activation_20260602_once.py:46`
- `run_index_daily_20260526_expansion_once.py:47`
- `run_n2_context_enrichment_materialization_execute.py:81`
- `run_official_daily_ingestion_20260525_once.py:59`
- `run_official_daily_ingestion_20260526_once.py:57`
- `run_official_daily_ingestion_20260526_v2_once.py:55`
- `run_official_daily_ingestion_20260527_once.py:55`
- `run_official_daily_ingestion_20260528_once.py:57`
- `run_official_daily_ingestion_20260529_once.py:57`
- `run_official_daily_ingestion_20260601_once.py:59`
- `run_official_daily_ingestion_20260602_once.py:61`
- `run_real_daily_incremental.py:1387`
- `run_real_initial_ingestion.py:1646`
- `run_stock_financial_canonical_metrics_20260529_once.py:40`
- `run_stock_identity_20260527_refresh_once.py:46`
- `run_stock_identity_refresh_20260529_once.py:48`
- `run_trade_calendar_patch_20260526_once.py:80`
- `run_trade_calendar_patch_20260527_once.py:81`
- `run_trade_calendar_patch_20260528_once.py:81`
- `run_trade_calendar_patch_20260529_once.py:81`
- `run_trade_calendar_patch_once.py:96`

## Validation Summary

- JSON parse: `PASS`
- Static scan: `PASS`
- Structured query audit tests: `22 tests OK`
- Compileall: `PASS`
- `git diff --check`: `PASS`

## P0/P1/P2

`P0/P1/P2 = 0/1/0`

P1:

- `STRUCTURED-AUDIT-CLOSEOUT-P1-001`: 33 N1/N2/ingestion script direct connect sites remain outside runtime-control N3/N4/N5 scope.

## Forbidden Scope Proof

This closeout did not perform or authorize:

- DB writes or migrations
- `pg_stat_statements` enablement
- PostgreSQL config changes
- N3/N4/N5 runner execution
- worker startup
- outbox/inbox/checkpoint consumption or mutation
- delivery, push, voice, or mobile
- sim, position, PnL, or real trade
- proposal, order, or trade

## Closeout Decision

`mark_n3_n4_n5_structured_query_audit_adoption_complete = true`

`allow_intraday_access_localization_next_validation = true`

## Recommended Next Gate

`N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_AUDITED_FRESH_RUN_VALIDATION_CONTRACT_GATE`
