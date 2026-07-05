# N1 Index Daily 20260526 Expansion Dry-run Report

日期：2026-05-27
layer_role：`N1_ingestion`
状态：`DRY_RUN_PASS`

## Summary

本 dry-run 只复核 20260526 `index_daily` universe 扩展，不执行入库、不写 PostgreSQL、不改 active source version、不进入 N2/N3/N4/N5/N6。

```text
source_batch_id = official_daily_ingest_20260526_index_expansion_v1
source_version = index_daily_20260526_v3
previous_source_version = index_daily_20260526_v2
expected index_daily rows = 83
current active index_daily rows = 9
existing v3 rows = 0
P0/P1/P2 = 0/1/0
```

## Universe

扩展口径：

```text
20260526 index_membership 涉及指数 + 固定 9 指数
```

只读核验：

```text
index_identity total = 8109
active index_identity = 7381
index_membership_fact(20260526) 涉及指数 = 82
固定 9 指数 = 9
union before canonical mapping = 83
canonical universe after mapping = 83
fixed 9 included = 9/9
```

## Source Breakdown

```text
Mootdx index daily = 81
Tushare index_daily fallback = 2
combined identity coverage = 83/83
missing = 0
duplicate identity_key = 0
UNKNOWN writes = 0
```

Tushare fallback 覆盖的 BJ 指数：

```text
index:BJ:899050 北证50
index:BJ:899601 北证专精特新
```

## Canonical Mapping

本地 TDX `指数板块.txt` 中两只北交所指数 membership 当前挂在 `UNKNOWN` identity：

```text
index:UNKNOWN:899050 -> index:BJ:899050
index:UNKNOWN:899601 -> index:BJ:899601
```

合同要求：

```text
日 K fact 只能写 canonical BJ identity。
禁止写 index:UNKNOWN:* 日 K。
membership 的 UNKNOWN 来源只作为 mapping evidence，不作为 fact identity。
```

## Quality

```text
P0 = 0
P1 = 1
P2 = 0
```

P1 说明：

```text
canonical_bj_mapping_from_tdx_unknown_membership
rows = 2
原因：TDX membership 缺少 BJ exchange namespace，但 index_identity 已有 canonical BJ identity，且 Tushare index_daily 对 BJ ts_code 有 20260526 日 K。
不阻断，但必须写入 quality details。
```

## N2 Impact

本轮不进入 N2，不重跑条件层。预期影响仅作为交接说明：

```text
index_condition_basis 重新跑后应从 9 扩到 83。
index_condition_pool 默认仍只筛固定 9。
index_minute_target_scope 不应自动扩大。
index_condition_display_basis 可随 basis 扩到 83，后续由 N2 合同确认。
```

## Boundary

```text
writes_postgres = false
updates_active_source_version = false
writes_parquet = false
writes_outbox = false
writes_inbox_or_checkpoint = false
enters_n2_n3_n4_n5_n6 = false
worker_started = false
old_system_touched = false
real_trading = false
```
