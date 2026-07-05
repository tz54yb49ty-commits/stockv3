# N1 Official Daily 20260526 Ingestion Dry-Run Plan

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`DRY_RUN_PASS`

## Scope

- trade_date: `20260526`
- source_batch_id: `official_daily_ingest_20260526_v1`
- stock source_version: `stock_daily_20260526_v1`
- index source_version: `index_daily_20260526_v1`
- board source_version: `board_daily_20260526_v1`

## Expected Rows

```text
stock active universe = 5523
fixed 9 index = 9
board total = 428
board 881 required coverage = 127
total daily fact rows = 5960
```

## Current N1 Fact

```json
{
  "stock_daily_bar_fact": 0,
  "index_daily_bar_fact": 0,
  "board_daily_bar_fact": 0,
  "total": 0
}
```

## Missing Official Daily

```json
{
  "stock": 5523,
  "index": 9,
  "board": 428,
  "total": 5960
}
```

## Source Fetch Plan

本计划不执行外部拉取。未来 execute 才允许在 final gate 下使用：

- stock: Tushare daily + adj_factor proof
- index: TDX/Mootdx preferred; Tushare index_daily fallback
- board: TDX/Mootdx board daily

## Quality

```text
P0/P1/P2 = 0/0/0
```

## Boundary

不写 PostgreSQL、不写 Parquet、不改 active_source_version、不进入 N2-N6、不启动 worker。
