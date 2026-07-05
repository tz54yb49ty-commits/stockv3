# N1 Official Daily 20260526 V2 Ingestion Execute Report

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`EXECUTE_PASS`

## Summary

```text
source_batch_id = official_daily_ingest_20260526_v2
stock source_version = stock_daily_20260526_v2
index source_version = index_daily_20260526_v2
board source_version = board_daily_20260526_v2
actual rows = stock 5520 / index 9 / board 428 / total 5957
quality P0/P1/P2 = 0/19/0
rollback_safe = true
rollback_sql = sql/N1_official_daily_20260526_v2_ingestion_rollback.sql
```

## Stock Gap Policy

```text
Tushare daily + adj_factor rows = 5504/5504
TDX/Mootdx supplemental_source_bar rows = 16/16
supplemental rows with raw_payload.source_proof_json = 16/16
official_no_trade manifest rows = 2
official_no_trade rows inserted into stock_daily_bar_fact = 0
stale_identity_excluded rows = 1
stale identity inserted into stock_daily_bar_fact = 0
unresolved_source_gap = 0
```

## Coverage

```text
fixed 9 index coverage = 9/9
board 881 coverage = 127/127
duplicate identity_key groups = 0
same-code contamination = 0
```

## Active Source Version

```text
stock / stock_daily / 20260526 -> stock_daily_20260526_v2
index / index_daily / 20260526 -> index_daily_20260526_v2
board / board_daily / 20260526 -> board_daily_20260526_v2
```

## Boundary Proof

```text
writes_postgres = true
writes_parquet = false
writes_outbox = false
writes_inbox_or_checkpoint = false
enters_n2_n3_n4_n5_n6 = false
worker_started = false
old_system_touched = false
real_trading = false
```

Post-run event counts remained unchanged:

```text
common_event_outbox = 74176
common_event_inbox = 2952
common_event_consumer_checkpoint = 2803
```

## Notes

After commit, the 16 supplemental stock rows were normalized so their `raw_payload` carries a `source_proof_json` key. This stayed inside the authorized N1 table `stock_daily_bar_fact` and remains covered by the same batch/version rollback.
