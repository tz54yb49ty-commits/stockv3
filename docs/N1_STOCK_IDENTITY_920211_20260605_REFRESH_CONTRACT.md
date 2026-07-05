# N1 Stock Identity 920211 20260605 Refresh Contract

Result: `CONTRACT_PASS`

This is a runtime_control contract only. It does not execute the identity refresh and does not write the database.

Target:

```text
trade_date = 20260605
target_ts_code = 920211.BJ
target_identity_key = stock:BJ:920211
source_batch_id = stock_identity_refresh_20260605_920211_v1
source_version = stock_identity_20260605_v1
active_scope_key = A_STOCK:20260605
```

Why this is required:

```text
N1 official daily 20260605 preflight is blocked:
stock_source_identity_coverage failed
stock_identity_refresh_required failed
unmapped = 920211.BJ
```

Future N1 write scope is limited to:

```text
stock_identity
common_ingest_batch
common_quality_gate_result
common_active_source_version
```

Forbidden:

```text
stock/index/board daily facts
condition source
N2/N3/N4/N5/N6
outbox/inbox/checkpoint
Parquet
worker
old system
real trading
```

Source evidence must be fetched and validated in `layer_role=N1_ingestion`, not in runtime_control:

```text
tushare.stock_basic
tushare.daily
tushare.adj_factor
tushare.bak_daily
tushare.suspend_d
```

After the identity execute passes, N1 must regenerate:

```text
docs/N1_official_daily_20260605_stock_source_probe.json
docs/N1_official_daily_20260605_ingestion_execute_preflight.json
docs/N1_official_daily_20260605_ingestion_execute_contract.json
```

Rollback draft:

```text
sql/N1_stock_identity_920211_20260605_refresh_rollback.sql
```

Next gate: `N1_STOCK_IDENTITY_920211_20260605_REFRESH_IMPLEMENTATION_GATE`.
