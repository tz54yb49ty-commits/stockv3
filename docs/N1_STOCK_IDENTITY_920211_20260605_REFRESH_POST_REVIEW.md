# N1 Stock Identity 920211 20260605 Refresh Post-Review

Result: `POST_REVIEW_PASS`

Live DB proof confirms the scoped identity repair:

```text
stock_identity = stock:BJ:920211 / 920211.BJ / 新睿电子
listed_date = 20260605
source_batch_id = stock_identity_refresh_20260605_920211_v1
source_version = stock_identity_20260605_v1
active scope = stock / stock_identity / A_STOCK:20260605
previous_source_version = stock_identity_20260604_v1
```

Rows:

```text
stock_identity = 1
common_ingest_batch = 1
common_quality_gate_result = 8
common_active_source_version = 1
P0/P1/P2 = 0/0/0
```

Boundary proof:

```text
official daily fact stock/index/board = 0/0/0
condition source rows = 0/0/0/0
outbox/inbox/checkpoint delta = 0/0/0
N2-N6 entered = false
worker_started = false
Parquet written = false
```

Rollback:

```text
sql/N1_stock_identity_920211_20260605_refresh_rollback.sql
hard-fail before DELETE/UPDATE = true
no CASCADE/DROP/TRUNCATE = true
```

Next gate: `N1_OFFICIAL_DAILY_20260605_PREFLIGHT_REFRESH_AFTER_IDENTITY_REPAIR`.
