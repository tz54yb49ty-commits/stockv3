# N3 Previous-Day Minute Historical Preload Runner Guard Alignment Report

Result: ALIGNMENT_PASS

Generated at: 2026-06-07T16:30:24+08:00

## Scope

Runner:

```text
scripts/run_previous_day_minute_preload_execute.py
```

Preload lineage:

```text
source_subscription_run_id=market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
preload_run_id=previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6
data_trade_date=20260528
contract_path=docs/N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_V6_PREFLIGHT.json
```

## Implementation Summary

The runner now accepts direct alias guards:

```text
--historical-preload
--source-subscription-run-id
--preload-run-id
--data-trade-date
```

The aliases are validated against the reviewed contract artifact before DB access or market-data adapter execution. The existing `--contract-path` runner path remains compatible.

## Runner Guard Proof

```text
help displays direct aliases=true
missing --execute blocks before DB write=true
missing --user-confirmed blocks before DB write=true
alias/contract mismatch blocks before DB write=true
legacy contract-path validator pass=true
```

Blocked responses keep side-effect flags false:

```text
writes_performed=false
market_data_pulled=false
market_data_fact_written=false
event_outbox_written=false
downstream_layers_touched=false
worker_started=false
```

## Allowed Execute Command Candidate

```text
PYTHONPATH=src:scripts python3 scripts/run_previous_day_minute_preload_execute.py \
  --contract-path docs/N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_V6_PREFLIGHT.json \
  --historical-preload \
  --source-subscription-run-id market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6 \
  --preload-run-id previous_day_minute_preload_20260528__market_data_subscription_20260529_condition_layer_20260528_source_20260528_v6 \
  --data-trade-date 20260528 \
  --execute --user-confirmed \
  --pre-backup-path docs/N3_previous_day_minute_historical_preload_v6_execute_backup_before.json \
  --post-backup-path docs/N3_previous_day_minute_historical_preload_v6_execute_backup_after.json \
  --json-report-path docs/N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_V6_EXECUTE_REPORT.json \
  --markdown-report-path docs/N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_V6_EXECUTE_REPORT.md
```

## Forbidden Scope Proof

```text
preload_executed=false
database_written=false
market_data_pulled=false
minute_rows_written=false
preload_status_written=false
outbox_written_or_consumed=false
inbox_or_checkpoint_updated=false
worker_started=false
entered_n4_n5_n6=false
rollback_sql_executed=false
old_system_touched=false
```

## Validation

```text
red test observed before implementation
tests/test_market_data_previous_day_preload_execute.py: 13 OK
help probe PASS
missing --execute probe PASS
missing --user-confirmed probe PASS
legacy contract-path validator PASS
```

## P0/P1/P2

```text
P0=0
P1=0
P2=0
```

## Next Gate

```text
N3_PREVIOUS_DAY_MINUTE_HISTORICAL_PRELOAD_EXECUTE_FINAL_GATE_REVIEW
```
