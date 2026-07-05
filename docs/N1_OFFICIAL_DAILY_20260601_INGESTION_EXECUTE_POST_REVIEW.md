# N1 Official Daily 20260601 Ingestion Execute Post-Review

Result: `POST_REVIEW_PASS`

```text
source_batch_id = official_daily_ingest_20260601_v1
stock source_version = stock_daily_20260601_v1
index source_version = index_daily_20260601_v1
board source_version = board_daily_20260601_v1
```

Actual rows:

```text
stock_daily_bar_fact = 5508
index_daily_bar_fact = 83
board_daily_bar_fact = 428
total = 6019
```

Batch / active source versions:

```text
common_ingest_batch = 1, status=passed, row_count=6019
active stock / stock_daily / 20260601 -> stock_daily_20260601_v1
active index / index_daily / 20260601 -> index_daily_20260601_v1
active board / board_daily / 20260601 -> board_daily_20260601_v1
```

Quality:

```text
persisted quality rows = 31
P0 passed rows = 28
P1 warning rows = 3
execute source validation P0/P1/P2 = 0/18/0
```

Manifest guards:

```text
official no-trade fact rows = 0
stale stock:SZ:300114 fact rows = 0
duplicate identity groups stock/index/board = 0/0/0
UNKNOWN index writes = 0
fixed 9 index rows = 9/9
tdx_industry board rows = 127
```

Boundary:

```text
condition source batch refs = 0/0/0/0
outbox/inbox/checkpoint = 151341/56170/4368
delta = 0/0/0
Parquet written = false
condition_* written = false
N2/N3/N4/N5/N6 entered = false
worker_started = false
old_system / real trading touched = false
```

Rollback:

```text
rollback_safe = true
rollback_sql = sql/N1_official_daily_20260601_ingestion_rollback.sql
```

Next route: stop after N1 post-review. N2 active v6 and N3 A1 prep remain the opening-prep handoff state; do not automatically execute N2/N3.
