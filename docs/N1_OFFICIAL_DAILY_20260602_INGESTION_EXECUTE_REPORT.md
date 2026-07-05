# N1 Official Daily 20260602 Ingestion Execute Report

layer_role: `N1_ingestion`

Status: `EXECUTE_PASS / POST_REVIEW_PASS`

```text
trade_date = 20260602
source_batch_id = official_daily_ingest_20260602_v1
stock source_version = stock_daily_20260602_v1
index source_version = index_daily_20260602_v1
board source_version = board_daily_20260602_v1
```

## Row Summary

```text
stock_daily_bar_fact = 5507
index_daily_bar_fact = 83
board_daily_bar_fact = 428
total = 6018
```

## Metadata Summary

```text
common_ingest_batch = 1
common_quality_gate_result = 31
common_active_source_version = 3
```

## Quality Summary

```text
source validation P0/P1/P2 = 0/19/0
persisted P0 passed = 28
persisted P1 warning = 3
P0 failed = 0
```

P1 warnings are scoped to the expected official no-trade/stale identity manifest evidence:

```text
official_no_trade_manifest = 18
stale_identity_excluded = 1
manifest details = stale=1,no_trade=18,supplemental=0
```

## Boundary Proof

```text
outbox delta = 0
inbox delta = 0
checkpoint delta = 0
condition source refs = 0/0/0/0
downstream N2/N3/N4/N5/N6 refs = 0/0/0/0/0
Parquet written = false
worker_started = false
old_system_touched = false
real_trading = false
```

## Rollback

```text
rollback_safe = true
rollback_sql = sql/N1_official_daily_20260602_ingestion_rollback.sql
rollback_scope = ROLLBACK_SCOPE_PASS
hard_fail_before_delete = true
```

Next allowed N1 step: `20260602 condition source dry-run/preflight gate`.
