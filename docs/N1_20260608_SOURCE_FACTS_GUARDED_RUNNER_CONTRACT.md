# N1 20260608 Source Facts Guarded Runner Contract

Result: `CONTRACT_PASS`

Overall execute status: `POLICY_PASS_FINAL_GATE_REVIEW_ALLOWED`

Layer role: `N1_ingestion`

This gate only defines the guarded runner contract, preflight shape, and rollback plan for `source_trade_date=20260608`. It did not execute, write PostgreSQL, write Parquet, enter N2-N6, consume outbox/inbox/checkpoint, start a worker, pull realtime quotes, or touch the old system.

## Date Proof

- `for_trade_date=20260609`
- `source_trade_date=20260608`
- derivation: `common_trade_calendar(20260609).prev_trade_date=20260608`
- `20260608`: open, prev=`20260605`, next=`20260609`, source_version=`trade_calendar_20260608_patch_v1`
- `20260609`: open, prev=`20260608`, next=`20260610`, source_version=`trade_calendar_20260609_repair_v1`

## Runner Contract

The approved runner must be a dedicated guarded N1 runner, not direct use of `scripts/run_real_daily_incremental.py`.

Implemented guarded runner files:

- `src/ashare_v3/ingestion/source_facts_20260608_execute.py`
- `scripts/run_n1_20260608_source_facts_once.py`

Required execute flags:

```bash
--execute
--user-confirmed
--source-fetch-enabled
--postgres-commit-enabled
```

Missing any flag must block before source commit and before any database write. A wrong trade date must block before source fetch and before any database write.

Execution must be phased:

1. official daily stock/index/board facts
2. condition source activation only after official daily 20260608 post-check passes

## Planned Batches

Official daily:

- `source_batch_id=official_daily_ingest_20260608_v1`
- `stock_daily_20260608_v1`
- `index_daily_20260608_v1`
- `board_daily_20260608_v1`

Condition source:

- `source_batch_id=condition_source_activation_20260608_v1`
- `stock_daily_basic_20260608_v1`
- `stock_financial_20260608_v1`
- `index_membership_20260608_v1`
- `board_membership_20260608_v1`

## Missing Stock Identity Skip Policy

Policy: `skip_missing_stock_identity_when_count_lte_10`

- stock-only policy
- applies to missing `stock_identity` rows in stock daily / daily_basic / financial source rows
- threshold: `10`
- current missing count: `1`
- current skipped row: `stock:BJ:920206 / 920206.BJ`
- severity: `P1`
- skipped rows are written only to quality/report details
- skipped rows must not write `stock_daily_bar_fact`, `stock_daily_basic`, or `stock_financial_metrics_fact`
- missing count `>10` remains `P0`
- index/board missing identity remains `P0`
- fixed 9 index missing identity/source remains `P0`

## Adjusted Expected Rows

Before policy:

- official daily stock/index/board/total: `5515/83/428/6026`
- condition source stock_daily_basic/stock_financial/index_membership/board_membership/total: `5515/5515/12841/56962/80833`
- combined: `86859`

After policy:

- official daily stock/index/board/total: `5514/83/428/6025`
- condition source stock_daily_basic/stock_financial/index_membership/board_membership/total: `5514/5514/12841/56962/80831`
- combined: `86856`

## Allowed Write Scope

Only these tables may be written by the future execute:

- `common_ingest_batch`
- `common_quality_gate_result`
- `common_active_source_version`
- `stock_daily_bar_fact`
- `index_daily_bar_fact`
- `board_daily_bar_fact`
- `stock_daily_basic`
- `stock_financial_metrics_fact`
- `index_membership_fact`
- `board_membership_fact`

## Forbidden Scope

The guarded runner must not write or trigger:

- `condition_*` tables
- N2/N3/N4/N5/N6 execution
- `common_event_outbox`
- `common_event_inbox`
- `common_event_consumer_checkpoint`
- Parquet
- workers
- realtime quote pulls
- delivery / push / voice / mobile
- proposal / order / trade / sim / position / PnL / real trade
- old system files, services, or databases

## Quality Contract

P0 blockers:

- missing stock identity count `>10`
- index or board missing identity
- fixed 9 index missing identity/source
- duplicate identity_key
- same-code contamination
- UNKNOWN index writes
- row-count mismatch
- existing target rows or source_version conflicts
- writes outside allowed tables
- downstream refs to planned 20260608 source versions that make rollback unsafe

P1 warnings:

- `920206.BJ` skipped by `skip_missing_stock_identity_when_count_lte_10`
- official no-trade manifest rows are quality-only and must not write stock daily facts
- stale identity manifests remain quality-only unless they affect current writes
- existing 20260608 runtime lineage from `source_trade_date=20260605` is orthogonal and excluded from this repair rollback scope

P2 warnings:

- board membership unmapped raw rows may be filtered only if documented and non-blocking by contract

## Rollback

Rollback draft: `sql/N1_20260608_source_facts_guarded_runner_rollback.sql`

Rollback is scoped by the planned source batches/source versions and `trade_date=20260608`; it is intentionally not scoped by broad `for_trade_date=20260608`, because existing N2-N6 runtime lineage for `20260605 -> 20260608` is not a reference to this future source facts repair.

Rollback must hard-fail before the first `DELETE`, must not use `DROP`, `TRUNCATE`, or `CASCADE`, and must not touch N2-N6 or outbox/inbox/checkpoint tables.

## Next Gate

Allowed review gate:

`N1_20260608_SOURCE_FACTS_EXECUTE_FINAL_GATE_REVIEW`

Do not execute from this policy gate.
