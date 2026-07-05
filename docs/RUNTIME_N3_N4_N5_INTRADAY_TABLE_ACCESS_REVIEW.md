# RUNTIME_N3_N4_N5_INTRADAY_TABLE_ACCESS_REVIEW

Result: **BLOCKED**

Layer role: `runtime_control`

Mode: read-only DB catalog/statistics review plus static SQL scan. This gate did not write business data, execute rollback, consume/update outbox/inbox/checkpoint, start workers, trigger delivery/push/voice/mobile, enter sim/position/PnL/real trade, or generate proposal/order/trade.

## Executive Summary

The good news: static review of N3/N4/N5 source paths did **not** find direct trading-path SQL against:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

N4 has the expected one-time context localization/preflight path that reads N2 `minute_target_scope` / `condition_pool` / `condition_basis` and local `condition_context_enrichment`, then writes/uses local trigger context snapshots.

The gate is still **BLOCKED** because PostgreSQL cannot currently provide per-SQL access records with timestamps, and the target external tables show aggregate direct reads while the requested local display/membership cache tables do not exist. That means this review cannot prove that all trading-time direct display/membership reads are absent or localized.

P0/P1/P2:

- P0: 1
- P1: 2
- P2: 1

## Audit Limitations

Observed DB settings:

- `pg_stat_statements`: unavailable
- `log_statement`: `none`
- `log_min_duration_statement`: `-1`
- `track_io_timing`: `off`
- `pg_postmaster_start_time`: `2026-06-01 03:47:18.224814+08`
- `pg_stat_database.stats_reset`: `null`

Impact: exact historical SQL text, per-query scan rows, and execution timestamps are unavailable. This report therefore combines:

- N3/N4/N5 run timestamps from `common_market_data_run`, `common_trigger_run`, `common_action_run`
- aggregate table access counters from `pg_stat_user_tables`
- static SQL/code scan of `src/ashare_v3/market`, `src/ashare_v3/trigger`, `src/ashare_v3/action`, and `scripts`

## Intraday Job Timeline

Definition: `coalesce(started_at, created_at)::time between 09:15 and 15:30`.

These timestamps identify jobs, not individual SQL statements.

### N3 Examples

| run_id | started_at | finished_at | worker |
|---|---:|---:|---:|
| `realtime_projection_metric_20260605_live2_compat__realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` | `2026-06-05 13:40:52.120987+08` | `2026-06-05 13:41:09.988046+08` | false |
| `today_minute_bar_1m_20260605_until_1127__market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` | `2026-06-05 11:48:55.861523+08` | `2026-06-05 11:49:32.063914+08` | false |
| `realtime_snapshot_20260605_live2_market_data_subscription_20260605_condition_layer_20260604_source_20260604_v1` | `2026-06-05 11:05:55.638193+08` | `2026-06-05 11:07:44.809945+08` | false |

### N4 Examples

| run_id | started_at | finished_at | worker |
|---|---:|---:|---:|
| `trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1` | `2026-06-04 11:45:41.414279+08` | `2026-06-04 11:45:41.414279+08` | false |
| `trigger_execute_20260603_condition_layer_20260602_source_20260602_v1` | `2026-06-03 13:51:21.682914+08` | `2026-06-03 13:51:21.682914+08` | false |
| `trigger_context_snapshot_20260603_condition_layer_20260602_source_20260602_v1` | `2026-06-03 11:19:45.28063+08` | `2026-06-03 11:19:45.28063+08` | false |

### N5 Examples

| run_id | started_at | finished_at | worker | inbox/checkpoint |
|---|---:|---:|---:|---:|
| `action_consumer_market_action_confirmation_v1_20260603_trigger_rule_v4_execute_20260603_condition_layer_20260602_source_20260602_v1` | `2026-06-04 14:48:24.093856+08` | `2026-06-04 14:48:24.093856+08` | false | true/true |
| `action_consumer_execute_20260602_1105__condition_layer_20260601_source_20260601_v1` | `2026-06-02 12:55:49.320212+08` | `2026-06-02 12:55:49.320212+08` | false | true/true |

Worker summary:

- `common_market_data_run`: `worker_started=true` count 0 / 65
- `common_trigger_run`: `worker_started=true` count 0 / 21
- `common_action_run`: `worker_started=true` count 0 / 9

## Target External Table Stats

Aggregate counters are since PostgreSQL stats start/reset. They are not per N3/N4/N5 job.

| table | seq_scan | seq_tup_read | idx_scan | idx_tup_fetch | live rows | size | status |
|---|---:|---:|---:|---:|---:|---:|---|
| `stock_condition_display_basis` | 28 | 1,486,564 | 11,202 | 395,651 | 63,713 | 304 MB | BLOCKED |
| `index_condition_display_basis` | 89 | 95,336 | 124 | 4,684 | 1,362 | 6.8 MB | BLOCKED |
| `board_condition_display_basis` | 44 | 298,340 | 169 | 58,718 | 8,259 | 42 MB | BLOCKED |
| `index_membership_fact` | 6 | 462,276 | 343 | 2,992,580 | 128,410 | 73 MB | BLOCKED |
| `board_membership_fact` | 18 | 2,048,952 | 326 | 13,044,498 | 569,336 | 334 MB | BLOCKED |

Interpretation: these external N2/N1-derived tables have direct aggregate reads. Because statement-level logging is unavailable, the review cannot attribute those reads to a layer or timestamp. Under this gate's rule, external direct access remains **BLOCKED** until localized or proven outside N3/N4/N5 trading paths.

## Requested Cache Tables

All requested display/membership cache tables are absent:

- `n6_display_stock_condition_cache`: missing
- `n6_display_index_condition_cache`: missing
- `n6_display_board_condition_cache`: missing
- `n6_display_index_membership_cache`: missing
- `n6_display_board_membership_cache`: missing

## Runtime Local Tables

The N4/N5 high-frequency path is partly localized:

| table | exists | seq_scan | seq_tup_read | idx_scan | size | assessment |
|---|---:|---:|---:|---:|---:|---|
| `stock_condition_context_enrichment` | true | 19 | 25,008 | 20,963 | 93 MB | local N2 context enrichment exists |
| `index_condition_context_enrichment` | true | 23 | 1,740 | 32 | 3.6 MB | local N2 context enrichment exists |
| `board_condition_context_enrichment` | true | 21 | 8,032 | 43 | 23 MB | local N2 context enrichment exists |
| `stock_trigger_context_snapshot` | true | 312 | 10,720,255 | 174 | 151 MB | local N4 context exists; performance hotspot |
| `index_trigger_context_snapshot` | true | 384 | 145,996 | 95 | 2.1 MB | local N4 context exists |
| `board_trigger_context_snapshot` | true | 388 | 1,194,924 | 88 | 18 MB | local N4 context exists; review seq scans |

## Static SQL Review

No N3/N4/N5 static direct matches were found for:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

Expected one-time N4 localization SQL:

- `src/ashare_v3/trigger/context_preflight.py:249-452`
- reads `stock/index/board_minute_target_scope`
- joins `stock/index/board_condition_pool`
- joins `stock/index/board_condition_basis`
- joins `stock/index/board_condition_context_enrichment`

Non-target matches:

- N1 ingestion scripts read/write `index_membership_fact` and `board_membership_fact`.
- N6 schema/view drafts expose `v_n6_*` views over display/membership tables.

These are not N3/N4/N5 worker paths, but they explain why aggregate table stats may show reads.

## Performance Hotspots

Local high-read tables:

| table | seq_scan | seq_tup_read | idx_scan | idx_tup_fetch | live rows | recommendation |
|---|---:|---:|---:|---:|---:|---|
| `common_trigger_match` | 13,211 | 1,339,564,096 | 38,123 | 1,739,243 | 111,102 | review run/status/source-event indexes |
| `common_trigger_state` | 254 | 16,731,112 | 117,937 | 1,291,479 | 75,566 | verify run/status/identity predicates |
| `stock_trigger_context_snapshot` | 312 | 10,720,255 | 174 | 592,732 | 42,894 | review context lookup predicates |
| `common_action_event` | 402 | 5,896,617 | 17,230 | 1,644,911 | 16,594 | review action_run/source_trigger indexes |

## Findings

### ACCESS-P0-001: Per-SQL access log with timestamps is unavailable

Evidence:

- `pg_stat_statements` absent
- `log_statement=none`
- `log_min_duration_statement=-1`

Impact: cannot prove each N3/N4/N5 job's SQL access count, scan rows, and timestamp at statement granularity.

Required remediation: add a reviewed observability path with `pg_stat_statements` or structured application query audit using `application_name` / `run_id` tags. This must be a separate DB/config gate.

### ACCESS-P1-001: External display/membership tables have direct aggregate reads and caches are absent

Evidence:

- `stock_condition_display_basis` seq_tup_read = 1,486,564
- `board_membership_fact` seq_tup_read = 2,048,952
- requested `n6_display_*_cache` tables are all missing

Impact: cannot prove trading-time display/membership reads are localized.

Required remediation: either create local display/membership cache tables or prove these reads are outside N3/N4/N5 trading paths with statement-level instrumentation.

### ACCESS-P1-002: Local runtime tables show sequential-scan hotspots

Evidence:

- `common_trigger_match` seq_tup_read = 1,339,564,096
- `common_trigger_state` seq_tup_read = 16,731,112
- `stock_trigger_context_snapshot` seq_tup_read = 10,720,255
- `common_action_event` seq_tup_read = 5,896,617

Required remediation: review predicates and add/adjust indexes for `run_id`, event/status fields, source ids, identity keys, and trade date.

### ACCESS-P2-001: N4 context localization still reads N2 basis/pool/scope

This is expected for one-time context refresh, but it must remain outside high-frequency worker loops.

Required remediation: add static boundary tests proving N4 worker/executor paths consume local `trigger_context_snapshot` / `condition_context_enrichment`, not display/membership/source facts.

## Remediation Recommendations

1. BLOCK until statement-level access attribution exists or a fresh run can be observed with `application_name`/`run_id` tagging.
2. Do not use `stock/index/board_condition_display_basis` or `index/board_membership_fact` directly in any N3/N4/N5 intraday worker path.
3. If display/membership reads are needed during trading hours, introduce reviewed local cache tables:
   - `n6_display_stock_condition_cache`
   - `n6_display_index_condition_cache`
   - `n6_display_board_condition_cache`
   - `n6_display_index_membership_cache`
   - `n6_display_board_membership_cache`
4. Keep N4/N5 high-frequency paths on local runtime tables:
   - `stock/index/board_condition_context_enrichment`
   - `stock/index/board_trigger_context_snapshot`
   - `common_trigger_state`
   - `common_trigger_match`
   - N3 metric/minute facts
   - `common_action_event`
5. Review indexes for `common_trigger_match`, `common_trigger_state`, `stock_trigger_context_snapshot`, and `common_action_event`.

## Forbidden Scope Proof

This review did not:

- write database rows
- execute SQL writes or rollback
- modify N2/N3/N4/N5/N6 facts
- consume or update outbox/inbox/checkpoint
- start workers
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade
- modify application code

## Validation

- JSON parse: PASS
- `git diff --check`: PASS
- Targeted static scan in `src/ashare_v3/market`, `src/ashare_v3/trigger`, `src/ashare_v3/action`: PASS, zero direct matches for the five target display/membership tables
- DB catalog/stat read-only probe: PASS
- DB write/execute commands: none

## Next Gate

Recommended next gate:

`N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_CONTRACT_GATE`
