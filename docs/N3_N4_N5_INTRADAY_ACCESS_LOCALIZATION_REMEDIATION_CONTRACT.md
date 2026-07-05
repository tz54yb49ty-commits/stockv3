# N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_REMEDIATION_CONTRACT_GATE

Result: **CONTRACT_PASS**

Layer role: `runtime_control`

This contract defines remediation and validation requirements for N3/N4/N5 intraday table-access localization. It does not authorize DB writes, PostgreSQL config changes, migrations, N3/N4/N5 execute-code edits, worker startup, outbox/inbox/checkpoint consumption, delivery/push/voice/mobile, sim/position/PnL/real trade, or proposal/order/trade generation.

## Background

Source review:

`docs/RUNTIME_N3_N4_N5_INTRADAY_TABLE_ACCESS_REVIEW.json`

The previous gate was **BLOCKED** because:

- `pg_stat_statements` is absent.
- `log_statement=none`.
- `log_min_duration_statement=-1`.
- N3/N4/N5 static scan did not directly hit the five display/membership tables, but DB aggregate stats show those tables have historical reads.
- Requested local display/membership cache tables do not exist.
- Local runtime hotspots exist in `common_trigger_match`, `common_trigger_state`, `stock_trigger_context_snapshot`, and `common_action_event`.

## Forbidden Scope

This gate does not:

- write database rows
- enable `pg_stat_statements`
- execute migration
- modify N3/N4/N5 execute or worker code
- consume/update outbox/inbox/checkpoint
- start worker
- trigger delivery/push/voice/mobile
- enter sim/position/PnL/real trade
- generate proposal/order/trade

## Observability Contract

Problem: current DB settings cannot provide statement-level SQL text, per-query timestamp, scan rows, or run attribution for historical N3/N4/N5 jobs.

Allowed future options:

### OBS-A: `pg_stat_statements` + `application_name`

Enable `pg_stat_statements` in an independent DB/config gate and require every N3/N4/N5 runner connection to set an `application_name` containing:

- layer
- run_id
- stage
- gate_id

Pros:

- captures normalized SQL, calls, rows, timing
- strong aggregate hotspot evidence
- low code overhead once configured

Risks:

- requires PostgreSQL config/extension gate
- does not retain exact per-call timestamp by default
- needs pre/post snapshots per observed run

### OBS-B: Structured query audit wrapper

Add an application-side audit wrapper in a separate implementation gate. The wrapper records:

- layer
- run_id
- stage
- statement fingerprint
- referenced tables
- started_at / finished_at
- rowcount
- EXPLAIN metadata when enabled

Pros:

- gives per-query timestamps
- can enforce denylist before execution
- does not depend on DB extension availability

Risks:

- requires N3/N4/N5 code changes in a later gate
- audit sink must be separately authorized
- must avoid logging sensitive payload content

### OBS-C: Interim fresh-run probe

For a future manually confirmed dry-run only, set `application_name` and compare `pg_stat_user_tables` before/after.

Pros:

- no extension required
- useful interim guard

Risks:

- still lacks SQL text
- cluster-wide counters can be noisy
- proves only the fresh observed run, not historical runs

Minimum acceptance:

- Observability path must be approved by an independent DB/config or code gate.
- Every observed N3/N4/N5 run must include layer/run/stage attribution.
- The five denied external display/membership tables must show zero direct access in the observed N3/N4/N5 run.

## Static Boundary Guard

N3/N4/N5 worker/execute runtime paths must not directly access:

- `stock_condition_display_basis`
- `index_condition_display_basis`
- `board_condition_display_basis`
- `index_membership_fact`
- `board_membership_fact`

Allowed one-time N4 context refresh sources:

- `stock_condition_basis`
- `index_condition_basis`
- `board_condition_basis`
- `stock_condition_pool`
- `index_condition_pool`
- `board_condition_pool`
- `stock_minute_target_scope`
- `index_minute_target_scope`
- `board_minute_target_scope`
- `stock_condition_context_enrichment`
- `index_condition_context_enrichment`
- `board_condition_context_enrichment`

Allowed intraday local sources:

- `stock_condition_context_enrichment`
- `index_condition_context_enrichment`
- `board_condition_context_enrichment`
- `stock_trigger_context_snapshot`
- `index_trigger_context_snapshot`
- `board_trigger_context_snapshot`
- `common_trigger_state`
- `common_trigger_match`
- `common_action_event`
- N3 minute and metric fact tables
- standard event/outbox/inbox/checkpoint tables only when explicitly authorized by the layer gate

Suggested static scan:

```bash
rg -n "stock_condition_display_basis|index_condition_display_basis|board_condition_display_basis|index_membership_fact|board_membership_fact" \
  src/ashare_v3/market src/ashare_v3/trigger src/ashare_v3/action scripts
```

Required result:

- zero denied-table matches in N3/N4/N5 worker/execute runtime paths
- N1/N2/N6 non-runtime matches must be classified separately

## Cache Strategy

Principle: if trading-time display or membership data is needed, it must be served from a local reviewed cache/materialized artifact refreshed outside N3/N4/N5 worker loops.

### Cache Table Schema Draft

These are schema drafts only. This gate does not create tables.

`n6_display_stock_condition_cache`

- grain: `cache_run_id + source_run_id + stock_identity_key + for_trade_date`
- required columns: `cache_id`, `cache_run_id`, `source_run_id`, `source_table`, `source_display_basis_id`, `stock_identity_key`, `for_trade_date`, `source_trade_date`, `display_payload_json`, `cache_hash`, `cache_status`, `created_at`, `refreshed_at`
- suggested indexes: `unique(cache_run_id, stock_identity_key, for_trade_date)`, `btree(source_run_id, for_trade_date)`, `btree(stock_identity_key, for_trade_date)`, `gin(display_payload_json)`

`n6_display_index_condition_cache`

- grain: `cache_run_id + source_run_id + index_identity_key + for_trade_date`
- required columns: `cache_id`, `cache_run_id`, `source_run_id`, `source_table`, `source_display_basis_id`, `index_identity_key`, `for_trade_date`, `source_trade_date`, `display_payload_json`, `cache_hash`, `cache_status`, `created_at`, `refreshed_at`
- suggested indexes: `unique(cache_run_id, index_identity_key, for_trade_date)`, `btree(source_run_id, for_trade_date)`, `btree(index_identity_key, for_trade_date)`

`n6_display_board_condition_cache`

- grain: `cache_run_id + source_run_id + board_identity_key + for_trade_date`
- required columns: `cache_id`, `cache_run_id`, `source_run_id`, `source_table`, `source_display_basis_id`, `board_identity_key`, `for_trade_date`, `source_trade_date`, `display_payload_json`, `cache_hash`, `cache_status`, `created_at`, `refreshed_at`
- suggested indexes: `unique(cache_run_id, board_identity_key, for_trade_date)`, `btree(source_run_id, for_trade_date)`, `btree(board_identity_key, for_trade_date)`

`n6_display_index_membership_cache`

- grain: `cache_run_id + source_version + trade_date + index_identity_key + stock_identity_key`
- required columns: `cache_id`, `cache_run_id`, `source_version`, `source_table`, `trade_date`, `index_identity_key`, `stock_identity_key`, `membership_payload_json`, `cache_hash`, `cache_status`, `created_at`, `refreshed_at`
- suggested indexes: `unique(cache_run_id, trade_date, index_identity_key, stock_identity_key)`, `btree(trade_date, index_identity_key)`, `btree(stock_identity_key, trade_date)`

`n6_display_board_membership_cache`

- grain: `cache_run_id + source_version + trade_date + board_identity_key + stock_identity_key`
- required columns: `cache_id`, `cache_run_id`, `source_version`, `source_table`, `trade_date`, `board_identity_key`, `stock_identity_key`, `membership_payload_json`, `cache_hash`, `cache_status`, `created_at`, `refreshed_at`
- suggested indexes: `unique(cache_run_id, trade_date, board_identity_key, stock_identity_key)`, `btree(trade_date, board_identity_key)`, `btree(stock_identity_key, trade_date)`

Refresh boundary:

- cache refresh must be a separate N6/display or runtime_control-reviewed pre-market/after-hours gate
- cache refresh must not run inside N3/N4/N5 worker loops
- cache refresh must not consume outbox/inbox/checkpoint
- cache refresh must not mutate N3/N4/N5 facts
- any future cache execute requires contract, preflight, rollback, and user confirmation

Approved no-cache alternative:

- provide static scan plus statement-level observed-run proof showing zero reads for the five denied tables
- document the no-cache proof as an accepted exception with expiry before enabling long-running workers

## Hotspot Remediation Plan

This gate creates no indexes and runs no `EXPLAIN ANALYZE`.

### `common_trigger_match`

Observed `seq_tup_read`: `1,339,564,096`

Plan:

- inventory SELECT predicates
- run EXPLAIN-only for top query shapes in a later gate
- check indexes for `run_id`, `event_type`, outbox/source ids, identity, trade_date, `trigger_live`, `current_status`

### `common_trigger_state`

Observed `seq_tup_read`: `16,731,112`

Plan:

- inventory state lookup predicates
- check `run_id`, identity, status, trade date index support
- propose composite indexes only in a later schema/index gate

### `stock_trigger_context_snapshot`

Observed `seq_tup_read`: `10,720,255`

Plan:

- inventory context lookup predicates by `run_id`, `stock_identity_key`, `direction`, `condition_key`, `allowed_signal_types`
- verify matcher paths use context lookup indexes
- propose index refinements separately

### `common_action_event`

Observed `seq_tup_read`: `5,896,617`

Plan:

- inventory N5/N6 metadata and repair query predicates
- check `action_run_id`, `source_trigger_event_id`, `event_type`, `action_state`, outbox refs
- propose indexes separately

## Acceptance Criteria

The remediation is not complete until all are true:

1. Static scan returns zero denied-table matches in N3/N4/N5 worker/execute runtime paths.
2. Either the five local cache tables exist and are used by trading-time display paths, or an approved no-cache proof shows zero trading-time reads.
3. Statement-level attribution is available through `pg_stat_statements`, structured audit, or an approved fresh-run probe.
4. Observed N3/N4/N5 intraday run shows zero direct reads of the five denied external display/membership tables.
5. `worker_started=false` unless a later worker gate explicitly authorizes bounded worker smoke.

## Planned Future Gates

- `N3_N4_N5_INTRADAY_ACCESS_OBSERVABILITY_CONTRACT_GATE`
- `N6_DISPLAY_MEMBERSHIP_CACHE_SCHEMA_CONTRACT_GATE`
- `N3_N4_N5_INTRADAY_ACCESS_STATIC_GUARD_IMPLEMENTATION_GATE`
- `N3_N4_N5_RUNTIME_HOTSPOT_INDEX_REVIEW_GATE`
- `N3_N4_N5_INTRADAY_ACCESS_LOCALIZATION_POST_REVIEW_GATE`

## Validation

- JSON parse: PASS
- `git diff --check`: PASS
- static denylist scan over `src/ashare_v3/market`, `src/ashare_v3/trigger`, `src/ashare_v3/action`: PASS, direct target matches = 0
- read-only DB probe: PASS, no DB writes, no migration, `pg_stat_statements` not enabled, worker not started
