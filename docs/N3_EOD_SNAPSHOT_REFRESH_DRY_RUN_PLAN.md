# N3-EOD Snapshot Refresh Dry-Run Plan

## Summary

- result: `DESIGN_PASS`
- layer_role: `N3_market_data`
- stage: `N3-EOD snapshot refresh dry-run plan`
- eod_run_id: `eod_snapshot_refresh_20260525__market_data_subscription_20260525_condition_layer_20260522_to_20260525_20260525102249_execute`
- for_trade_date: `20260525`
- dry_run_only: `true`
- pulls_market_data: `false`
- writes_database: `false`
- consumes_c3_outbox: `false`
- enters_n4_n5_n6: `false`
- worker_started: `false`

## Purpose

EOD dry-run checks whether N3 can produce settlement snapshots and
reconciliation evidence for the current lineage. It does not write EOD facts and
does not decide whether B1/B2/N4/N5 are stale.

## Read Inputs

The dry-run runner should read only:

```text
common_market_data_run
common_market_data_quality_item
stock/index/board_realtime_daily_snapshot
stock/index/board_closed_30m_summary
stock/index/board_closed_30m_signal_enrichment
common_event_outbox for C3 status
N4 replay audit report / audit tables if available
N1 official daily fact tables, read-only, if an active official source exists
```

No external行情接口 is allowed.

## Expected Rows

EOD snapshot rows should align with the current subscription object count:

```text
stock=2052
index=9
board=127
total=2188
```

Reconciliation item rows are variable. The dry-run should report counts by:

```text
official_daily_missing
official_price_diff
official_volume_diff
official_amount_diff
b1_snapshot_diff
c2_closed_summary_diff
c2b_signal_enrichment_diff
c3_outbox_status
n4_replay_audit_diff
stale_candidate
boundary_check
```

## Dry-Run Checks

1. Validate `eod_run_id` is absent from `common_market_data_run`.
2. Validate EOD snapshot and reconciliation target rows for `eod_run_id` are 0.
3. Validate outbox/inbox/checkpoint refs for `eod_run_id` are 0.
4. Validate all allowlisted source runs are present and passed.
5. Validate C3 outbox remains `pending=17432` and delivered/delivering=0.
6. Validate 019 schema tables exist after migration, or report `schema_missing`.
7. Validate official daily active source availability for stock/index/board.
8. If official daily is missing, report `missing_official_daily_fact` and block EOD execute.
9. Build preview EOD snapshots from B1/C2/C2B material without writing them.
10. Build preview reconciliation items and stale candidates without changing upstream rows.

## Quality Gates

P0:

```text
lineage mismatch
source run not passed
019 schema missing after migration
eod_run_id already exists
target rows for eod_run_id not zero
outbox/inbox/checkpoint refs for eod_run_id not zero
C3 outbox already delivered/consumed unexpectedly
official daily source missing when official-confirm execute is requested
duplicate EOD snapshot key
forbidden write scope detected
```

P1:

```text
individual official row missing
runtime close differs from official close
runtime amount/volume differs from official value
BJ 920xxx remains missing in settlement evidence
N4 C3 replay audit has missing comparison rows
```

P2:

```text
manual stale review recommended
rounding-only diff within tolerance
```

## Official Daily Missing Policy

Dry-run must never pull行情. If N1 official daily fact is missing:

```text
result may still complete as a dry-run report
dry-run emits missing_official_daily_fact
EOD execute remains blocked
next gate is N1 official daily ingestion
```

## Future Execute Scope

Allowed writes:

```text
common_market_data_run
common_market_data_quality_item
stock/index/board_eod_snapshot
stock/index/board_eod_reconciliation_item
```

Forbidden:

```text
common_event_outbox
common_event_inbox / checkpoint
realtime_projection_metric
realtime_daily_snapshot
closed_30m_summary
closed_30m_signal_enrichment
minute_bar_1m
C3 outbox
N4/N5/N6
worker
```

## Output Report

Future dry-run should output:

```text
result
P0/P1/P2
source lineage proof
official_daily_status
expected_eod_snapshot_rows
preview_eod_snapshot_rows
reconciliation_item_preview_counts
stale_candidate_counts
rollback_sql_path
whether N1 official daily ingestion gate is needed
whether EOD execute final gate is allowed
```

## Decision

`DESIGN_PASS`. Dry-run runner implementation can be planned after 019 migration
review/execute. EOD business execute remains blocked.
