# N3 Market Data Subscription Rebuild V6 Runner Guard Alignment Report

Status: ALIGNMENT_PASS

## Scope

This gate aligned `scripts/run_market_data_subscription_execute.py` with the runtime_control final gate requirement for explicit manual confirmation before any N3 subscription control-row write.

No N3 subscription execute was performed. No runtime database write, market data pull, minute/snapshot write, outbox/inbox/checkpoint mutation, worker start, rollback SQL execution, N4/N5/N6 entry, or old-system touch occurred.

## Implementation Summary

- Added `--execute`.
- Added `--user-confirmed`.
- Added `--source-condition-run-id` as a clear alias for `--run-id`.
- Added `--report-path` as a clear alias for `--json-report-path`.
- Preserved legacy `--run-id`, `--json-report-path`, and `--market-data-run-id`.
- Added `main(argv=None)` testability.
- Added before-write guard: missing `--execute` or `--user-confirmed` returns blocked before calling `run_market_data_subscription_execute`.
- Added alias conflict guard before DB write.
- Updated V6 contract/preflight execute command candidates to use the double-confirmed command.

## Runner Guard Proof

```text
missing --execute -> BLOCK before DB write
missing --user-confirmed -> BLOCK before DB write
alias conflict -> BLOCK before DB write
guard executes before run_market_data_subscription_execute()
manual missing --execute probe wrote no report file
manual missing --user-confirmed probe wrote no report file
```

## Compatibility Proof

```text
--source-condition-run-id maps to condition_run_id
--report-path maps to json_report_path
--run-id remains supported
--json-report-path remains supported
--market-data-run-id remains supported
legacy parameter names remain supported when --execute and --user-confirmed are present
```

## Updated Execute Command Candidate

```bash
PYTHONPATH=src:scripts python3 scripts/run_market_data_subscription_execute.py \
  --source-condition-run-id condition_layer_20260528_source_20260528_v6 \
  --source-trade-date 20260528 \
  --for-trade-date 20260529 \
  --market-data-run-id market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6 \
  --execute --user-confirmed \
  --pre-backup-path docs/N3_market_data_subscription_rebuild_v6_execute_backup_before.json \
  --post-backup-path docs/N3_market_data_subscription_rebuild_v6_execute_backup_after.json \
  --report-path docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_V6_EXECUTE_REPORT.json \
  --markdown-report-path docs/N3_MARKET_DATA_SUBSCRIPTION_REBUILD_V6_EXECUTE_REPORT.md
```

## Planned Write Scope Unchanged

```text
common_market_data_run=1
common_market_data_quality_item=34
common_market_data_subscription_candidate=5807
common_market_data_subscription=3034
common_market_data_pull_plan=9
pull_plan.execute_allowed=false
minute/snapshot facts=0
outbox events=0
```

## Rollback Static Check

```text
sql/N3_market_data_subscription_rebuild_v6_rollback.sql exists
RAISE EXCEPTION before first DELETE=true
DELETE count=5
no CASCADE/DROP/TRUNCATE=true
```

## Validation

```text
runner help shows --execute / --user-confirmed / --source-condition-run-id / --report-path
missing --execute probe PASS
missing --user-confirmed probe PASS
subscription tests PASS: 50 tests
market data tests PASS: 166 tests
compileall PASS
JSON parse PASS
rollback static check PASS
git diff --check PASS
```

## Forbidden Scope Proof

```text
n3_subscription_execute_performed=false
runtime_db_written=false
market_data_pulled=false
minute_rows_written=false
snapshot_rows_written=false
outbox/inbox/checkpoint_consumed_or_updated=false
worker_started=false
entered_n4_n5_n6=false
rollback_sql_executed=false
old_system_touched=false
```

## Next Gate

Allowed to re-enter `N3_MARKET_DATA_SUBSCRIPTION_REBUILD_V6_EXECUTE_FINAL_GATE_REVIEW`.
