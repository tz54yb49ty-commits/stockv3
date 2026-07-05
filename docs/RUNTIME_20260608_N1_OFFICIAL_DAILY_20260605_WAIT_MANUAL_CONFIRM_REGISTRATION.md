# RUNTIME 20260608 N1 Official Daily 20260605 Wait Manual Confirm Registration

Result: `WAIT_MANUAL_CONFIRM_REGISTERED`

This runtime_control registration does not execute official daily ingestion and does not write the database.

## Proof

```text
20260608 calendar patch = passed
20260608 prev_trade_date = 20260605
920211.BJ stock_identity refresh = POST_REVIEW_PASS
active stock identity = A_STOCK:20260605 -> stock_identity_20260605_v1
official daily active identity guard alignment = ALIGNMENT_PASS
official daily final gate = PASS
manual gate = WAIT_MANUAL_CONFIRM
```

## Execute Command

Run only after switching to `layer_role=N1_ingestion` and explicitly confirming N1 official daily execute:

```bash
PYTHONPATH=src python3 scripts/run_official_daily_ingestion_20260605_once.py --trade-date 20260605 --execute --user-confirmed --source-fetch-enabled --postgres-commit-enabled
```

## Expected Writes

```text
stock_daily_bar_fact = 5514
index_daily_bar_fact = 83
board_daily_bar_fact = 428
total_daily_fact = 6025
common_ingest_batch = 1
common_active_source_version = 3
common_quality_gate_result = per runner validation report
```

## Baseline

```text
20260605 daily fact rows = 0/0/0
metadata conflicts = 0/0/0
outbox/inbox/checkpoint = 188736/90362/5170
```

## Rollback

```text
sql/N1_official_daily_20260605_ingestion_rollback.sql
hard-fail before DELETE/UPDATE = true
no CASCADE/DROP/TRUNCATE = true
does not rollback stock_identity 920211 repair
```

## Forbidden Scope

```text
runtime_control official daily execute = false
runtime_control DB write = false
condition source = not written
N2/N3/N4/N5/N6 = not entered
outbox/inbox/checkpoint = not consumed or updated
worker = not started
rollback SQL = not executed
Parquet = not written
old system = untouched
real trade = false
```

After execute, return to:

`N1_OFFICIAL_DAILY_20260605_INGESTION_POST_REVIEW_GATE`

Remaining chain after N1 official daily execute:

```text
N1 condition source readiness/activation for 20260608
N2 condition execute/readiness for 20260608
N3-A1 previous-day minute preload readiness/contract/execute for prev close 20260605
```
