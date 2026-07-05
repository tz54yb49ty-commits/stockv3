# 000001.SH index_daily 入库层收口报告

日期：2026-05-24
范围：只涉及 v3 原始数据入库层 `index_daily_bar_fact` 与 Parquet 历史归档。
边界：不进入条件层，不进入 N3，不启动 worker，不写 trigger/action/mobile/voice/sim，不触碰旧系统。

## 1. 结论

本轮 `000001.SH / index:SH:000001` 历史补齐符合入库层职责。

原因：

```text
PostgreSQL 初始 index_daily_20230101_20260521_v1 中 000001.SH = 0 行。
Parquet 初始 index_daily_20230101_20260521_v1 中 000001.SH = 0 行。
排除历史补齐版本后，入库仓库只有 20260522 单日 1 行。
条件层不得外拉指数历史，也不得硬造 condition_basis。
因此必须由入库层补齐历史，并生成新的 source_version，保留 previous_source_version 以支持回滚。
```

用户已接受 `index_daily_20260522_v3` 作为本轮历史补齐收口版本，不回滚到缺历史版本。

## 2. 只读核验结果

### 2.1 PostgreSQL 初始全量版本

查询对象：

```text
table = index_daily_bar_fact
source_version = index_daily_20230101_20260521_v1
index_identity_key = index:SH:000001
```

结果：

```text
row_count = 0
min_trade_date = null
max_trade_date = null
trade_days = 0
```

### 2.2 Parquet 初始全量版本

查询对象：

```text
path = /Volumes/MacRaid/database/data_lake/index_daily_bar_fact/source_version=index_daily_20230101_20260521_v1
manifest = /Volumes/MacRaid/database/data_lake/_manifests/index_daily_bar_fact/source_version=index_daily_20230101_20260521_v1/index_daily_20230101_20260521_v1.manifest.json
index_identity_key = index:SH:000001
```

结果：

```text
manifest row_count = 64953
partition file_count = 816
000001.SH target_rows = 0
min_trade_date = null
max_trade_date = null
trade_days = 0
```

### 2.3 修复前可用 000001.SH 数据

当前可追溯版本分布：

```text
index_daily_20260522_v2  row_count=1    trade_date=20260522
index_daily_20260522_v3  row_count=575  trade_date=20240102-20260522
```

说明：

```text
v2 是当日缺口修复版本，只提供 20260522 单日 1 行。
v3 是历史补齐版本，补齐 N2 周期窗口所需 20240102-20260522 历史。
排除历史补齐版本 v3 后，仓库只有 v2 的 20260522 单日 1 行。
如果严格同时排除 v2 和 v3，则初始仓库中 000001.SH 为 0 行。
```

因此，“只有 20260522 单日 1 行”的判断成立于“不把 v2 单日修复视为历史补齐”的收口口径；无论采用该口径还是严格排除 v2/v3 的口径，结论都是：初始入库仓库缺少 `000001.SH` 历史。

## 3. 职责边界判断

`000001.SH` 属于固定 9 指数之一：

```text
index:SH:000001
```

固定 9 指数是后续条件层默认指数池的官方事实来源。条件层只能读取已激活的入库事实，不能：

```text
自己去 Tushare 拉数据
自己去 Mootdx 拉数据
自己从旧系统补数据
自己硬造 condition_basis
自己绕过 common_active_source_version 猜最新版本
```

因此，当 PostgreSQL fact 与 Parquet data_lake 都缺少历史窗口时，补齐动作只能发生在入库层。

## 4. source_version 收口

接受版本：

```text
source_version = index_daily_20260522_v3
source_batch_id = index_daily_20260522_v3
previous_source_version = index_daily_20260522_v2
```

收口语义：

```text
v1 = 缺 000001.SH 的初始当日版本，不作为条件层来源。
v2 = 补齐 20260522 当日 000001.SH，仍缺历史。
v3 = 入库层补齐 000001.SH 历史窗口，符合 source_version 可追溯与可回滚要求。
```

本报告只做收口说明和文档更新，不执行数据库回滚，不切换 active pointer，不删除任何 fact 或 Parquet 文件。

## 5. 后续规则

固定 9 指数历史补齐必须按以下顺序执行：

```text
1. 先查 PostgreSQL index_daily_bar_fact。
2. 再查 Parquet data_lake 历史归档。
3. PostgreSQL 与 Parquet 都缺所需历史窗口时，才允许入库层按既有 index_daily 数据源规则外拉。
4. 外拉后的修复必须生成新的 source_version。
5. common_active_source_version 必须保留 previous_source_version。
6. 条件层不得外拉、不得修补、不得硬造。
```
