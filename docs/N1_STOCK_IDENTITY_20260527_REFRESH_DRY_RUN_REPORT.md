# N1 Stock Identity 20260527 Refresh Dry-Run Report

状态：`DRY_RUN_PASS`

本轮只读确认 20260527 stock_identity 缺口，不写数据库，不写 daily fact，不改 active source_version，不进入 N2/N3/N4/N5/N6，不启动 worker。

## Missing Identity

Tushare `stock_basic` 已确认两只当日上市股票：

```text
688635.SH 长进光子 list_date=20260527 market=科创板
920161.BJ 龙辰科技 list_date=20260527 market=北交所
```

当前 `stock_identity` 中两只均缺失：

```text
stock:SH:688635 = 0 rows
stock:BJ:920161 = 0 rows
```

## New Rows

将来 execute 应新增：

```text
stock_identity_key = stock:SH:688635
ts_code = 688635.SH
code = 688635
exchange = SH
name = 长进光子
area = 湖北
industry = 通信设备
market = 科创板
listed_date = 20260527
status = active
source_batch_id = stock_identity_refresh_20260527_v1
source_version = stock_identity_20260527_v1
```

```text
stock_identity_key = stock:BJ:920161
ts_code = 920161.BJ
code = 920161
exchange = BJ
name = 龙辰科技
area = 湖北
industry = 元器件
market = 北交所
listed_date = 20260527
status = active
source_batch_id = stock_identity_refresh_20260527_v1
source_version = stock_identity_20260527_v1
```

## Active Source Version

项目已有 `stock_identity` active source_version 机制。将来 execute 应写：

```text
data_domain = stock
data_type = stock_identity
scope_key = A_STOCK:20260527
source_batch_id = stock_identity_refresh_20260527_v1
source_version = stock_identity_20260527_v1
previous_source_version = stock_identity_20260522_v1
```

## Stale Identity Decision

本轮不修改：

```text
stock:SZ:300114 -> stock:SZ:302132
```

原因：本 gate 只解除 20260527 official daily 的新股 identity P0 blocker。`300114 -> 302132` 已在 official daily stale identity manifest 中处理；如要改 `stock_identity` 状态，应另开独立 identity correction gate，避免把新股补录和历史 identity 修正混在同一小批次。

## Quality

```text
P0/P1/P2 = 0/1/0
```

P1：

```text
stale_identity_not_modified = stock:SZ:300114 unchanged
```

## Boundary

本轮不写：

```text
stock_daily_bar_fact
index_daily_bar_fact
board_daily_bar_fact
condition source
N2/N3/N4/N5/N6
outbox/inbox/checkpoint
Parquet
worker
old system
real trading
```
