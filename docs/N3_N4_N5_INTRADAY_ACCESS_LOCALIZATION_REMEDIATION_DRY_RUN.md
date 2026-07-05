# N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_DRY_RUN

Result: **BLOCKED_CURRENT_STATE**

Layer role: `runtime_control`

This dry-run rechecks the current state for the remediation contract. It does not write DB rows, enable `pg_stat_statements`, run migrations, modify N3/N4/N5 code, consume/update outbox/inbox/checkpoint, start workers, or enter delivery/push/voice/mobile/sim/position/PnL/real trade/proposal/order/trade.

## Current State

### Observability

- `pg_stat_statements`: absent
- `pg_stat_statements` extension rows: 0
- `log_statement`: `none`
- `log_min_duration_statement`: `-1 ms`
- `track_io_timing`: `off`

Decision: **BLOCKED** for statement-level attribution.

### Requested Cache Tables

All requested cache tables are absent:

- `n6_display_stock_condition_cache`: missing
- `n6_display_index_condition_cache`: missing
- `n6_display_board_condition_cache`: missing
- `n6_display_index_membership_cache`: missing
- `n6_display_board_membership_cache`: missing

Decision: **BLOCKED** until cache strategy or no-cache proof is approved.

### Static Boundary Scan

Paths scanned:

- `src/ashare_v3/market`
- `src/ashare_v3/trigger`
- `src/ashare_v3/action`

Denied patterns:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

Current result: **PASS**, zero direct matches.

### Local Runtime Tables

Existing local/runtime tables:

- `stock_condition_context_enrichment`
- `index_condition_context_enrichment`
- `board_condition_context_enrichment`
- `stock_trigger_context_snapshot`
- `index_trigger_context_snapshot`
- `board_trigger_context_snapshot`
- `common_trigger_match`
- `common_trigger_state`
- `common_action_event`

This confirms that N4/N5 have local context/runtime tables available, but it does not prove statement-level access behavior.

## Local Hotspot Recheck

| table | seq_scan | seq_tup_read | idx_scan | idx_tup_fetch | live rows | status |
|---|---:|---:|---:|---:|---:|---|
| `common_trigger_match` | 13,211 | 1,339,564,096 | 38,123 | 1,739,243 | 111,102 | HOTSPOT |
| `common_trigger_state` | 254 | 16,731,112 | 117,937 | 1,291,479 | 75,566 | HOTSPOT |
| `stock_trigger_context_snapshot` | 312 | 10,720,255 | 174 | 592,732 | 42,894 | HOTSPOT |
| `common_action_event` | 402 | 5,896,617 | 17,230 | 1,644,911 | 16,594 | HOTSPOT |

## Planned Remediation Items

1. `REM-001`: statement-level observability
   - next gate: `N3_N4_N5_INTRADAY_ACCESS_OBSERVABILITY_CONTRACT_GATE`
   - choose `pg_stat_statements`, structured query audit, or approved fresh-run probe

2. `REM-002`: static denylist guard
   - next gate: `N3_N4_N5_INTRADAY_ACCESS_STATIC_GUARD_IMPLEMENTATION_GATE`
   - turn current zero direct matches into enforceable tests/checks

3. `REM-003`: display/membership cache or no-cache proof
   - next gate: `N6_DISPLAY_MEMBERSHIP_CACHE_SCHEMA_CONTRACT_GATE`
   - create cache contract or prove no trading-time reads are needed

4. `REM-004`: local hotspot index/query review
   - next gate: `N3_N4_N5_RUNTIME_HOTSPOT_INDEX_REVIEW_GATE`
   - run EXPLAIN-only and predicate inventory in a later gate

## Blockers

P0:

- `DRY-P0-001`: statement-level attribution remains unavailable.

P1:

- `DRY-P1-001`: requested display/membership cache tables are absent.
- `DRY-P1-002`: local runtime hotspot tables require query/index review.

P2:

- `DRY-P2-001`: static zero-match guard is not yet enforced as a test.

P0/P1/P2: `1 / 2 / 1`

## Decision

Dry-run current state: **BLOCKED_UNTIL_REMEDIATION**

The contract can be registered, but localization cannot be marked complete until observability, cache/no-cache proof, and hotspot review gates are handled.

## Forbidden Scope Proof

This dry-run did not:

- write database rows
- enable `pg_stat_statements`
- execute migration
- modify N3/N4/N5 execute code
- consume/update outbox/inbox/checkpoint
- start worker
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade

## Validation

- JSON parse: PASS
- `git diff --check`: PASS
- static denylist scan over `src/ashare_v3/market`, `src/ashare_v3/trigger`, `src/ashare_v3/action`: PASS, direct target matches = 0
- read-only DB probe: PASS, no DB writes, no migration, `pg_stat_statements` not enabled, worker not started

## Next Gate

Recommended next gate:

`N3_N4_N5_INTRADAY_ACCESS_OBSERVABILITY_CONTRACT_GATE`
