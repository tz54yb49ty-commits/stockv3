# A股监控系统 v3 原始数据入库层开发文档

版本：V0.1
日期：2026-05-22
范围：只涉及原始数据入库、标准事实表、质量闸门、归档与回滚。
不包含：条件层、触发层、动作层、语音播报、模拟账户、前端投影、真实交易。

## 1. 设计结论

v3 入库层采用：

```text
PostgreSQL：交易日运行事实库
Parquet：历史归档文件
DuckDB：离线回放、对账、报表、三表校验
```

核心原则：

```text
指数、板块、个股必须物理分表。
入库时就分开，不允许先混表再靠 asset_kind 过滤。
identity_key 必须保留，但不能替代物理隔离。
```

最终结构：

```text
stock_*   个股入库与事实表
index_*   指数入库与事实表
board_*   通达信行业/板块入库与事实表
common_*  批次、交易日历、质量报告、active source version
```

## 2. 为什么必须物理分表

过去系统反复出现的问题包括：

```text
000001.SH 上证指数污染 000001.SZ 平安银行
000688.SH 科创50 与股票同码风险
000905.SH 中证500 与股票同码风险
881xxx 板块/行业误进入股票交易口径
latest_snapshot/state_snapshot 覆盖 official daily
财务指标和个股筛选池数量不一致
```

因此 v3 不使用单张 `daily_bar_fact` 混放所有资产，而是：

```text
stock_daily_bar_fact
index_daily_bar_fact
board_daily_bar_fact
```

这样做到：

```text
分表防呆
identity_key 防错
source_batch_id 可追溯
quality_gate 防脏数据进入条件层
```

## 3. 入库层边界

入库层只负责：

```text
1. 获取外部数据
2. 写 raw staging
3. 标准化成 fact 表
4. 做质量校验
5. 写 active source version
6. 写 Parquet 归档
7. 提供只读 view 给后续层使用
```

入库层禁止：

```text
禁止计算 BUY_COND / SELL_COND
禁止生成 BUY_TRIGGER / SELL_TRIGGER
禁止生成 B_BUY / S_SELL / POS_CLEAR 等动作
禁止写 voice / mobile / sim
禁止写真实交易接口
禁止用 latest_snapshot 覆盖 official daily
禁止裸 code join
禁止在 P0 质量问题下继续定稿
```

## 4. 数据源范围

第一阶段支持这些数据：

```text
交易日历
个股身份表
指数身份表
板块身份表
指数成分
个股前复权日K
个股每日指标
指数日K
通达信行业/板块日K
通达信行业/板块成分
个股财务指标
盘中实时快照
条件对象一分钟K
```

说明：

```text
全量历史分钟K不进入 PostgreSQL 主运行库。
当日 condition scope 内对象的一分钟K属于 N3 实时行情层 runtime，不属于 N1/N2 入库层。
N3 runtime 必须写本地 SSD PostgreSQL，不写 /Volumes/MacRaid/database。
全量历史分钟K如需保留，由 N1/archive 写 Parquet 归档。
N3 盘后 runtime 如需长期保留，必须先由 N3 封账并生成 archive_request，再由 N1/archive 读取 sealed runtime 分区归档。
```

### 4.1 外部拉取接口到 v3 目标表映射

本方案只覆盖 PostgreSQL 运行事实库中的核心入库目标表，不包含 Parquet 归档表。

必须从外部拉取并标准化写入的目标表：

| v3 目标表 | 需要的外部接口 | 说明 |
|---|---|---|
| `common_trade_calendar` | 交易日历接口 | 交易日、是否开市、前后交易日。 |
| `stock_identity` | 个股基础信息接口 | 股票代码、交易所、名称、上市/退市、ST、状态。 |
| `index_identity` | 指数基础信息接口 | 指数代码、交易所、名称、分类。 |
| `board_identity` | 本地 TDX txt：`/Volumes/MacRaid/tdxdata/tdx`；兜底：TDX 行业/板块列表接口 | 板块代码、板块名称、板块类型、来源命名空间。每次入库都重新读取本机 TDX txt，接口只作兜底。 |
| `index_membership_fact` | 本地 TDX txt：`/Volumes/MacRaid/tdxdata/tdx/指数板块.txt` | 指数和个股成分关系，必须映射到 `index_identity_key` 和 `stock_identity_key`。每次入库都重新读取本机 TDX txt。 |
| `stock_daily_bar_fact` | Tushare 通用行情接口、official daily proof 接口 | 个股日K只进 stock 表，必须带 `stock_identity_key`；前复权口径由 Tushare 通用行情接口参数显式指定。 |
| `stock_daily_basic` | Tushare `daily_basic` 每日指标接口 | 个股每日估值、换手、市值、股本等指标只进 stock 表，必须带 `stock_identity_key`。 |
| `index_daily_bar_fact` | TDX/Mootdx 指数日K；兜底：Tushare `index_daily` 指数日K接口 | 指数日K只进 index 表，必须带 `index_identity_key`。优先使用 TDX/Mootdx，Tushare `index_daily` 只作兜底。每日 index_daily 拉取集合必须包含 TDX 指数成分涉及指数和固定 9 指数。 |
| `board_daily_bar_fact` | TDX 行业/板块日K接口 | 板块日K只进 board 表，必须带 `board_identity_key`。 |
| `stock_financial_metrics_fact` | TDX/Mootdx 财务包；补充/兜底：Tushare 财务指标接口 | 报告期财务指标优先使用 TDX/Mootdx 财务包，Tushare `fina_indicator` 只作补充或兜底；Tushare `daily_basic` 已独立进入 `stock_daily_basic`。 |
| `board_membership_fact` | 本地 TDX txt：`/Volumes/MacRaid/tdxdata/tdx`；兜底：TDX 行业/板块列表接口 | 板块和个股成分关系，必须映射到 `board_identity_key` 和 `stock_identity_key`。每次入库都重新读取本机 TDX txt，接口只作兜底。 |

推荐外部来源分工：

```text
Tushare：交易日历、个股基础信息、指数基础信息、个股日K通用行情接口、`daily_basic` 个股每日指标；Tushare `index_daily` 指数日K和 `fina_indicator` 财务指标只作补充或兜底。
TDX/Mootdx：指数日K优先使用 TDX/Mootdx；个股财务字段优先使用 TDX/Mootdx 财务包；`board_identity`、`index_membership_fact` 和 `board_membership_fact` 每次入库都从 `/Volumes/MacRaid/tdxdata/tdx` 本地 txt 重新读取，兜底使用行业/板块列表接口；行业/板块日K仍按 TDX 数据源处理。
```

本地 TDX txt 分流规则：

```text
指数板块.txt：只进入 index_membership_fact，不混入 board_membership_fact。
地区板块.txt / 概念板块.txt / 行业板块.txt：进入 board_identity 和 board_membership_fact。
每次入库都读取本地 txt 原文件，不依赖上次派生缓存，确保本地 txt 更新后可进入本批 source_version。
```

拉取顺序必须先 identity，后 fact：

```text
1. common_trade_calendar
2. stock_identity
3. index_identity
4. board_identity
5. index_membership_fact
6. board_membership_fact
7. stock_daily_bar_fact
8. stock_daily_basic
9. index_daily_bar_fact
10. board_daily_bar_fact
11. stock_financial_metrics_fact
```

每个外部拉取批次必须具备：

```text
source_batch_id
source_version
source
raw_payload
row_count
raw_hash
quality gate
按 source_batch_id 回滚的删除路径
```

本方案明确不拉取：

```text
Parquet 归档表
snapshot runtime 表
minute runtime 表
condition / filter / candidate / signal 表
sim / position / action / voice 表
旧系统表
```

### 4.2 外部接口连通性与格式验证结果

验证时间：2026-05-22
验证范围：只验证连通性和返回字段格式，不写数据库，不生成文件，不启动服务，不触碰旧系统。
安全要求：Tushare token 只允许来自运行环境或本机安全配置，不得写入代码库、文档或日志。

已验证通过的主用和兜底来源：

| v3 目标表 | 来源 | 角色 | 验证结果 | 关键返回字段 |
|---|---|---|---|---|
| `common_trade_calendar` | Tushare `trade_cal` | 主用 | 通过 | `exchange`, `cal_date`, `is_open`, `pretrade_date` |
| `stock_identity` | Tushare `stock_basic` | 主用 | 通过 | `ts_code`, `symbol`, `name`, `area`, `industry`, `market`, `list_date` |
| `index_identity` | Tushare `index_basic` | 主用 | 通过 | `ts_code`, `name`, `market`, `publisher`, `category`, `base_date`, `list_date` |
| `stock_daily_bar_fact` | Tushare `pro_bar`，`asset='E'`, `freq='D'`, `adj='qfq'` | 主用 | 通过 | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount` |
| `stock_daily_bar_fact` proof | Tushare `daily` | official daily proof | 通过 | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount` |
| `stock_daily_bar_fact` proof | Tushare `adj_factor` | qfq proof | 通过 | `ts_code`, `trade_date`, `adj_factor` |
| `stock_daily_basic` | Tushare `daily_basic` | 主用 | 通过 | `ts_code`, `trade_date`, `turnover_rate`, `volume_ratio`, `pe`, `pe_ttm`, `pb`, `ps`, `total_share`, `float_share`, `free_share`, `total_mv`, `circ_mv` |
| `index_daily_bar_fact` | Mootdx `index` | 主用 | 通过 | `open`, `close`, `high`, `low`, `vol`, `amount`, `datetime` |
| `index_daily_bar_fact` | Tushare `index_daily` | 兜底 | 通过 | `ts_code`, `trade_date`, `open`, `high`, `low`, `close`, `vol`, `amount` |
| `board_daily_bar_fact` | Mootdx `index` with `88xxxx` board code | 主用 | 通过 | `open`, `close`, `high`, `low`, `vol`, `amount`, `datetime` |
| `stock_financial_metrics_fact` | Mootdx `finance` | 主用 | 通过 | `code`, `updated_date`, `ipo_date`, `zongguben`, `liutongguben`, `jingzichan`, `zhuyingshouru`, `jinglirun`, `meigujingzichan` |
| `stock_financial_metrics_fact` | Tushare `fina_indicator` | 补充/兜底 | 通过 | `ts_code`, `end_date`, `roe`, `or_yoy`, `netprofit_yoy` |
| `board_identity` | `/Volumes/MacRaid/tdxdata/tdx/地区板块.txt`、`概念板块.txt`、`行业板块.txt` | 主用 | 通过 | GBK 编码，tab 分隔：`board_code`, `board_name`, `stock_code`, `stock_name` |
| `board_membership_fact` | `/Volumes/MacRaid/tdxdata/tdx/地区板块.txt`、`概念板块.txt`、`行业板块.txt` | 主用 | 通过 | GBK 编码，tab 分隔：`board_code`, `board_name`, `stock_code`, `stock_name` |
| `index_membership_fact` | `/Volumes/MacRaid/tdxdata/tdx/指数板块.txt` | 主用 | 通过 | GBK 编码，tab 分隔：`index_code`, `index_name`, `stock_code`, `stock_name` |
| `board_identity` / `board_membership_fact` | Mootdx `block` | 兜底 | 通过 | `blockname`, `block_type`, `code_index`, `code` |

本机 TDX 目录已验证存在以下板块文件：

```text
/Volumes/MacRaid/tdxdata/tdx/地区板块.txt
/Volumes/MacRaid/tdxdata/tdx/指数板块.txt
/Volumes/MacRaid/tdxdata/tdx/概念板块.txt
/Volumes/MacRaid/tdxdata/tdx/行业板块.txt
```

TDX 本地板块文件解析规则：

```text
编码：GBK
分隔符：tab
列顺序：board_code, board_name, stock_code, stock_name
指数板块.txt 在标准化时重命名为 index_code, index_name, stock_code, stock_name，并只写 index_membership_fact。
板块类 txt 每次入库都重读本地原文件，禁止用旧派生缓存代替本地 txt。
```

### 4.3 核心表具体入库方案

本方案只覆盖 PostgreSQL 运行事实库核心表，不执行 Parquet 归档，不拉 snapshot runtime，不拉 minute runtime。

#### 4.3.1 配置与安全

```text
TUSHARE_TOKEN 只从环境变量或本机安全配置读取。
TDX_ROOT 固定为 /Volumes/MacRaid/tdxdata/tdx。
不得把 token 写入 AGENTS.md、docs、configs、日志或提交记录。
```

#### 4.3.2 source_batch_id 与 source_version

每次入库按数据域生成独立批次：

```text
trade_calendar_YYYYMMDD_vN
stock_identity_YYYYMMDD_vN
index_identity_YYYYMMDD_vN
board_identity_YYYYMMDD_vN
index_membership_YYYYMMDD_vN
stock_daily_YYYYMMDD_vN
stock_daily_basic_YYYYMMDD_vN
index_daily_YYYYMMDD_vN
board_daily_YYYYMMDD_vN
stock_financial_YYYYMMDD_vN
board_membership_YYYYMMDD_vN
```

每个批次必须写入 `common_ingest_batch`，记录：

```text
batch_id
trade_date
data_domain
data_type
source
source_path / source_params
raw_hash
row_count
error_count
status
started_at
finished_at
```

#### 4.3.3 入库顺序

必须先 identity，后 fact：

```text
1. common_trade_calendar
2. stock_identity
3. index_identity
4. board_identity
5. index_membership_fact
6. board_membership_fact
7. stock_daily_bar_fact
8. stock_daily_basic
9. index_daily_bar_fact
10. board_daily_bar_fact
11. stock_financial_metrics_fact
```

#### 4.3.4 表级入库方案

| v3 目标表 | 主用来源 | 兜底/补充来源 | 标准化要点 |
|---|---|---|---|
| `common_trade_calendar` | Tushare `trade_cal` | 无 | `cal_date` -> `trade_date`; `is_open` 转 boolean; 补齐 `prev_trade_date` / `next_trade_date`。 |
| `stock_identity` | Tushare `stock_basic` | 无 | `ts_code` 拆出 `exchange` 和 `code`; 生成 `stock_identity_key = stock:EXCHANGE:CODE`。 |
| `index_identity` | Tushare `index_basic` | 无 | `ts_code` 拆出 `exchange` 和 `code`; 生成 `index_identity_key = index:EXCHANGE:CODE`。 |
| `board_identity` | TDX 本地 GBK 板块 txt | Mootdx `block` | 每次入库重读 `/Volumes/MacRaid/tdxdata/tdx` 下本地 txt；从地区/概念/行业等板块类文件提取唯一 `board_code` / `board_name`; 生成 `board_identity_key = board:TDX:BOARD_CODE`。 |
| `index_membership_fact` | TDX 本地 GBK `指数板块.txt` | 无 | 每次入库重读本地 txt；每行映射 `index_identity_key` + `stock_identity_key`; 无法映射的指数或个股进入质量问题，不得直接激活。 |
| `stock_daily_bar_fact` | Tushare `pro_bar(adj='qfq')` | Tushare `daily` + `adj_factor` 作 proof | 只写个股；必须映射 `stock_identity_key`; `vol` -> `volume`; `adjust_type='qfq'`; `official_daily_proof=true` 后才允许激活。 |
| `stock_daily_basic` | Tushare `daily_basic` | 无 | 只写个股每日指标；必须映射 `stock_identity_key`; 覆盖换手率、量比、PE/PB/PS、股息率、股本、市值等日频指标。 |
| `index_daily_bar_fact` | Mootdx `index` | Tushare `index_daily` | 只写指数；必须映射 `index_identity_key`; Mootdx `datetime` 取日期为 `trade_date`; `vol` -> `volume`。 |
| `board_daily_bar_fact` | Mootdx `index` with `88xxxx` board code | 无 | 只写板块；必须映射 `board_identity_key`; `88xxxx` 不得进入 stock 表。 |
| `stock_financial_metrics_fact` | Mootdx `finance` | Tushare `fina_indicator` | 财务字段优先 Mootdx；Tushare 只补 `roe`, `revenue_yoy`, `profit_yoy` 等报告期指标缺口；日频估值和市值指标进入 `stock_daily_basic`。 |
| `board_membership_fact` | TDX 本地 GBK 板块 txt | Mootdx `block` | 每次入库重读 `/Volumes/MacRaid/tdxdata/tdx` 下地区/概念/行业等板块类 txt；每行映射 `board_identity_key` + `stock_identity_key`; 无法映射的成员进入质量问题，不得直接激活。 |

#### 4.3.5 质量闸门

所有批次在激活 `source_version` 前必须通过：

```text
identity_key coverage = 100%
stock/index/board 物理分表
stock_daily_bar_fact official daily proof = true
stock_daily_basic 与 stock universe 对齐
qfq / adj_factor proof 通过
000001.SH 不得污染 000001.SZ
000688.SH / 000905.SH 不得进入 stock 表
88xxxx 不得进入 stock 表
stock_financial_metrics_fact 与 stock universe 对齐
index_membership_fact 的 index_identity_key 覆盖率 = 100%
index_membership_fact 的 stock_identity_key 覆盖率 = 100%
board_membership_fact 的 board_identity_key 覆盖率 = 100%
board_membership_fact 的 stock_identity_key 覆盖率 = 100%
board_identity / index_membership_fact / board_membership_fact 本批 raw_hash 来自本地 TDX txt
active source version 唯一
```

#### 4.3.6 回滚

任一 quality gate 失败：

```text
不激活 source_version
common_ingest_batch.status 标记 failed
按 source_batch_id 删除本批写入
保留 raw_hash、row_count、error_count 和错误摘要供审计
```

### 4.4 20230101-20260521 初始回填方案

本方案只覆盖 v3 原始数据入库层核心表，不包含条件、触发、动作、语音、模拟账户、前端、真实交易、worker 启动或旧系统读取。

回填范围：

```text
start_date = 20230101
end_date = 20260521
按 common_trade_calendar 的开市日展开日级事实表。
```

表级回填范围：

| v3 目标表 | 回填日期范围 | 入库口径 |
|---|---|---|
| `common_ingest_batch` | 全部批次 | 每个数据域、每个切片写批次审计，记录 `source_batch_id`、`source_version`、`raw_hash`、`row_count`、状态和回滚路径。 |
| `common_trade_calendar` | `20230101` - `20260521` | 拉取完整交易日历，作为所有日级事实表的日期基准。 |
| `stock_identity` | 截至 `20260521` | 拉取 A 股身份全集，保留上市/退市日期，用于判断历史交易日是否应有数据。 |
| `index_identity` | 截至 `20260521` | 拉取指数身份全集，生成 `index_identity_key`。 |
| `board_identity` | `20260521` 快照 | 每次入库重读本地 TDX txt，生成当前板块身份快照。 |
| `index_membership_fact` | `20260521` 快照 | 只读取本地 `指数板块.txt` 的当前快照，不把当前指数成分反填到 2023-2026 每个交易日。 |
| `board_membership_fact` | `20260521` 快照 | 只读取本地地区/概念/行业等板块 txt 的当前快照，不把当前板块成分反填到 2023-2026 每个交易日。 |
| `stock_daily_bar_fact` | `20230101` - `20260521` 所有开市日 | 个股前复权日K只写 stock 表，必须通过 official daily proof 和 qfq proof。 |
| `stock_daily_basic` | `20230101` - `20260521` 所有开市日 | Tushare `daily_basic` 个股每日指标只写 stock 表，必须映射到 `stock_identity_key`。 |
| `index_daily_bar_fact` | `20230101` - `20260521` 所有开市日 | 指数日K只写 index 表，主用 TDX/Mootdx，Tushare `index_daily` 只作兜底。 |
| `board_daily_bar_fact` | `20230101` - `20260521` 所有开市日 | 88xxxx 板块日K只写 board 表，不得进入 stock 表。 |
| `stock_financial_metrics_fact` | `20230101` - `20260521` | 报告期财务指标按报告期/披露可得口径写入；日频估值、市值、换手等指标进入 `stock_daily_basic`，不在入库层做条件计算。 |

初始回填批次建议：

```text
trade_calendar_20230101_20260521_v1
stock_identity_20260521_v1
index_identity_20260521_v1
board_identity_20260521_v1
index_membership_20260521_v1
board_membership_20260521_v1

stock_daily_202301_v1 ... stock_daily_202605_v1
stock_daily_basic_202301_v1 ... stock_daily_basic_202605_v1
index_daily_202301_v1 ... index_daily_202605_v1
board_daily_202301_v1 ... board_daily_202605_v1
stock_financial_202301_v1 ... stock_financial_202605_v1
```

初始回填激活版本建议：

```text
stock_daily_20230101_20260521_v1
stock_daily_basic_20230101_20260521_v1
index_daily_20230101_20260521_v1
board_daily_20230101_20260521_v1
stock_financial_20230101_20260521_v1
index_membership_20260521_v1
board_membership_20260521_v1
```

成分快照原则：

```text
本地 TDX txt 代表当前快照。
初始回填只写 trade_date=20260521 的 index_membership_fact 和 board_membership_fact。
不得将当前成分复制到 20230101-20260521 每个交易日，避免制造假的历史成分。
初始回填之后，每个交易日入库时都重新读取本地 TDX txt，并形成当日成分快照。
```

初始回填质量闸门：

```text
所有事实表 identity_key coverage = 100%
stock/index/board 物理分表正确
stock daily official daily proof 缺失 = 0
stock_daily_basic 与 stock universe 对齐
qfq / adj_factor proof 通过
index daily 缺失 = 0
board daily 缺失 = 0
000001.SH 不得污染 000001.SZ
000688.SH / 000905.SH 不得进入 stock 表
88xxxx stock violation = 0
stock_financial_metrics_fact 与 stock universe 对齐
index_membership_fact 只含 index_identity_key + stock_identity_key
board_membership_fact 只含 board_identity_key + stock_identity_key
board_identity / index_membership_fact / board_membership_fact 本批 raw_hash 来自本地 TDX txt
```

初始回填回滚：

```text
任一切片失败，不激活对应 source_version。
按 source_batch_id 删除本批写入的 PostgreSQL 事实表数据。
Parquet 归档通过 manifest 控制 active，不直接物理删除历史文件。
保留 common_ingest_batch 的 failed 状态、raw_hash、row_count、error_count 和错误摘要。
```

初始回填计划 dry-run：

```text
N2 阶段可以生成 20230101-20260521 初始回填批次计划。
计划只生成 source_batch_id、source_version、目标表、来源、日期切片、依赖、质量闸门和回滚策略。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

默认批次数：

```text
1 个 trade_calendar 全区间批次
5 个 identity/membership 快照批次
41 个月度切片 x 5 类事实批次
合计 211 个 source_batch_id
```

初始回填 source_version 原则：

```text
trade_calendar 使用 trade_calendar_20230101_20260521_v1。
identity/membership 快照使用 *_20260521_v1。
月度事实批次使用月度 source_batch_id，例如 stock_daily_202301_v1。
月度事实行的 source_version 使用全区间激活版本，例如 stock_daily_20230101_20260521_v1。
```

初始回填配置模板：

```text
configs/initial_backfill.example.toml 只保存 dry-run 配置。
允许保存 start_date、end_date、snapshot_date、version、data_root、tdx_root、目标表来源和分片策略。
Tushare token 和 PostgreSQL DSN 只能保存环境变量名，不能保存真实密钥。
配置中的 side_effects 开关必须全部为 false。
从配置生成计划时，只读取该 TOML 文件，不调用外部接口，不读取本地 TDX txt，不连接数据库，不写数据目录。
```

初始回填执行清单 dry-run：

```text
N2 阶段可以把 211 个 source_batch_id 汇总成执行清单。
执行清单只从已生成的 InitialBackfillPlan 派生，不拉取外部数据。
清单必须包含 domain_counts、slice_kind_counts、table_summaries、activation_groups、rollback_groups 和 execution_order。
清单必须显示 stock/index/board/common 物理分表统计，不允许出现 daily_bar_fact 混表。
清单必须显示 membership 只在 snapshot_date 入库，不反填历史月份。
清单必须显示月度事实批次的 source_batch_id 范围和全区间 source_version。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

入库验收清单 dry-run：

```text
N2 阶段可以从初始回填执行清单生成入库验收清单。
验收清单只包含验收项和证据，不读取真实数据库，不读取外部数据。
验收项至少覆盖 structure、source_trace、quality_gate、archive、rollback、safety 六类。
structure 必须验收 stock/index/board/common 物理分表，且不得出现 daily_bar_fact 混表。
source_trace 必须验收 source_batch_id 数量、domain 分布、source_version 激活组和月度事实全区间版本。
quality_gate 必须验收 identity_key、membership 快照、official daily proof、stock_daily_basic 与 stock universe、同码/88xxxx 防污染。
archive 必须验收 Parquet manifest 计划。
rollback 必须验收按 source_batch_id 删除和恢复 previous active source_version。
safety 必须验收不触碰条件/触发/动作/语音/模拟账户/前端/真实交易/旧系统。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

每日增量入库 dry-run：

```text
初始回填完成后，每个交易日必须生成单日增量入库计划。
每日增量不同于初始回填，不按月切片，只按单个 trade_date 生成批次。
每日增量默认覆盖 11 个核心目标表。
每日增量只生成计划，不拉取外部数据，不读取本地 TDX txt，不连接数据库，不写数据目录。
```

每日增量真实执行：

```text
真实执行脚本：scripts/run_real_daily_incremental.py
执行粒度：单个 trade_date。
默认顺序：严格按每日增量入库顺序执行 11 个核心目标表。
数据库：写入 v3 专用 PostgreSQL。
归档：写入 /Volumes/MacRaid/database/data_lake。
审计：每个目标表单独写 common_ingest_batch 和 common_quality_gate_result。
激活：每个目标表单独更新 common_active_source_version。
回滚：按 source_batch_id 删除本批数据，并删除对应 Parquet manifest/files，再恢复 previous active source version。
边界：不触碰旧系统，不启动 worker，不写条件/触发/动作/语音/模拟账户/前端/真实交易。
```

手动执行命令模板：

```bash
PYTHONPATH=src ASHARE_V3_POSTGRES_DSN='postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3' \
scripts/run_real_daily_incremental.py --trade-date YYYYMMDD --version v1 --mootdx-offset 300
```

当前运行建议：

```text
先手动跑每日增量，连续观察 2-3 个交易日。
确认 Tushare、TDX/Mootdx、本地 TDX txt、PostgreSQL、Parquet manifest 均稳定后，再增加定时自动导入。
核心日增和财务增量可以拆成两个阶段：先跑核心行情和成分，后跑慢速财务。
```

每日增量批次命名：

```text
trade_calendar_YYYYMMDD_vN
stock_identity_YYYYMMDD_vN
index_identity_YYYYMMDD_vN
board_identity_YYYYMMDD_vN
index_membership_YYYYMMDD_vN
board_membership_YYYYMMDD_vN
stock_daily_YYYYMMDD_vN
stock_daily_basic_YYYYMMDD_vN
index_daily_YYYYMMDD_vN
board_daily_YYYYMMDD_vN
stock_financial_YYYYMMDD_vN
```

每日增量入库顺序：

```text
1. common_trade_calendar
2. stock_identity
3. index_identity
4. board_identity
5. index_membership_fact
6. board_membership_fact
7. stock_daily_bar_fact
8. stock_daily_basic
9. index_daily_bar_fact
10. board_daily_bar_fact
11. stock_financial_metrics_fact
```

每日增量必须重新读取本地 TDX txt 的目标：

```text
board_identity
index_membership_fact
board_membership_fact
```

每日 index_daily 固定 9 指数保障：

```text
每日 index_daily 除读取 index_membership_fact 涉及的指数外，必须额外包含固定 9 指数：
index:SH:000905
index:SZ:399303
index:SH:000001
index:SH:000852
index:SZ:399001
index:SZ:399006
index:SH:000300
index:SH:000016
index:SH:000688
```

说明：

```text
固定 9 指数属于后续条件层默认指数池的必要官方事实来源。
index_daily 入库层必须用 exchange-qualified identity 检查固定 9 指数，不允许只用裸 code。
固定 9 指数缺 identity 或缺当日日K必须作为 P0 阻断，不得在条件层硬造 basis 或静默跳过。
```

固定 9 指数历史补齐规则：

```text
当固定 9 指数缺少条件层所需历史窗口时，必须先查 PostgreSQL 事实表 index_daily_bar_fact。
如果 PostgreSQL 缺失，再查 Parquet data_lake 历史归档。
只有 PostgreSQL fact 与 Parquet data_lake 都缺少所需历史窗口时，才允许入库层按既有 index_daily 数据源规则外拉。
外拉仍必须走入库层 source_batch_id、source_version、quality gate、Parquet manifest 和回滚方案。
修复后必须生成新的 index_daily source_version，不允许原地覆盖既有版本。
common_active_source_version 必须保留 previous_source_version，确保可回滚。
条件层不得外拉 Tushare/Mootdx，不得自行补历史，不得硬造 condition_basis。
```

说明：

```text
这样本地 TDX txt 更新后，可以在当日 source_version 中体现。
每日增量仍必须执行 PostgreSQL 写入计划、quality gate、Parquet manifest 计划、active source version 计划和 source_batch_id 回滚计划。
configs/daily_incremental.example.toml 只保存 dry-run 配置，不保存真实 token 或 DSN。
配置中的 side_effects 开关必须全部为 false。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

每日 identity 真实写入策略：

```text
stock_identity / index_identity / board_identity 每日重拉来源并生成当日审计批次。
真实写入采用 insert_missing_only：只补入新增 identity，不覆盖已有 identity 行。
原因：identity 表被历史事实表引用，覆盖更新会扩大回滚面。
当日 identity 批次仍保留 source_batch_id、source_version、raw_hash、quality gate 和 active source version 记录。
如果未来需要 identity 历史版本化，应另行设计 identity snapshot/history 表，不在当前入库阶段临时覆盖。
```

每日财务增量策略：

```text
stock_financial_metrics_fact 是 source_trade_date 的 as-of 财务快照，不是当天新增财报增量表。
每日 stock_financial 必须按当日 stock universe 生成一行一股。
source_trade_date=D 时，选择 announcement_date <= D 的最新可用财报。
优先 TDX/Mootdx 财务包；Tushare fina_indicator / income / cashflow / forecast 作为补充或兜底。
daily_basic / stock_daily_basic 只作为市值、PE 等辅助来源，不替代财报。
找不到财报的股票也必须写 placeholder 行，quality_status=warning，score=0，warning=未找到可用财报。
禁止激活 row_count=0 的 stock_financial source_version。
P0 要求 stock_financial row_count 等于当日 stock universe 行数。
```

每日增量耗时参考：

```text
20260522 实测：完整 11 个任务约 11 分 07 秒。
20260522 实测：不含 stock_financial_metrics_fact 的核心日增约 35 秒。
日常核心行情增量预期：1 分钟以内。
完整增量含财务预期：10-15 分钟；网络或接口波动时可能 20-30 分钟。
```

20260522 真实执行验收记录：

```text
trade_calendar_20260522_v1        row_count=1      passed
stock_identity_20260522_v1        row_count=5846   passed
index_identity_20260522_v1        row_count=8109   passed
board_identity_20260522_v1        row_count=428    passed
index_membership_20260522_v1      row_count=12841  passed
board_membership_20260522_v1      row_count=56872  passed
stock_daily_20260522_v1           row_count=5504   passed
stock_daily_basic_20260522_v1     row_count=5504   passed
index_daily_20260522_v1           row_count=80     已废弃为缺 000001.SH 的版本
index_daily_20260522_v2           row_count=81     passed，固定 9 指数齐全
index_daily_20260522_v3           row_count=655    000001.SH 历史补齐收口版本，用户接受，不回滚
index_daily_20260522_v4           row_count=897    后续完整历史窗口验证版本，当前本机 active；本收口不执行回滚/切换
board_daily_20260522_v1           row_count=428    passed
stock_financial_20260522_v1       row_count=0      已废弃为非快照口径
stock_financial_20260522_v2       row_count=5504   as-of 快照口径，passed

P0 quality gate failed = 0
P0 quality gate passed = 49（20260522 日增量主批次验收口径）
P2 quality gate passed = 6（20260522 日增量主批次验收口径）
stock/index/board 物理分表污染 = 0
active_source_version = 11（核心入库 domain；index_daily 当前 active 已切到 index_daily_20260522_v4）
Parquet manifest = 7（主批次；000001.SH 修复另生成 index_daily v2/v3/v4 manifest）
condition source ready check = passed（最新 active index_daily=index_daily_20260522_v4）
```

000001.SH index_daily 历史修复补充记录：

```text
修复工具必须先检查 PostgreSQL index_daily_bar_fact 和 Parquet data_lake 历史。
如果入库仓库已有所需 000001.SH 历史，直接复用仓库事实生成新 active source_version，不重新外拉 mootdx/Tushare。
只有仓库缺失所需历史交易日时，才按既有 index_daily 规则外拉补齐。
20260522 修复时，仓库已有 20240102-20260522 共 575 个交易日，缺 2023 年 242 个交易日。
因此生成 index_daily_20260522_v4：先记录 warehouse 缺口，再按既有 index_daily 规则补齐 20230103-20260522 共 817 个交易日。
回滚方式：恢复 previous_source_version=index_daily_20260522_v3，并删除 source_version/source_batch_id=index_daily_20260522_v4 的 fact、quality gate、batch 与 Parquet manifest/分区文件。
v3 收口报告见 docs/V3_INDEX_DAILY_000001_INGESTION_CLOSURE_REPORT.md。
```

每日增量执行清单 dry-run：

```text
N2 阶段可以从单日增量入库计划生成每日执行清单。
执行清单只汇总计划结果，不执行真实入库。
清单必须显示 11 个核心任务、domain 分布、table summary、source_version 激活组、source_batch_id 回滚组、执行顺序和本地 TDX txt 刷新项。
domain 分布必须为 common=1、stock=4、index=3、board=3。
每日 source_version 必须全部限定在单个 trade_date，例如 *_20260522_v1。
TDX 本地 txt 刷新项必须覆盖 board_identity、index_membership_fact、board_membership_fact。
回滚组必须覆盖全部 11 个 source_batch_id，策略为先按 source_batch_id 删除，再恢复 previous active source_version。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

每日增量验收清单 dry-run：

```text
N2 阶段可以从每日增量执行清单生成每日验收清单。
验收清单只包含验收项和证据，不读取真实数据库，不读取外部数据。
验收项至少覆盖 structure、source_trace、quality_gate、archive、rollback、safety 六类。
structure 必须验收 11 个每日核心任务、stock/index/board/common 物理分表，以及 stock_daily_basic 独立入库。
source_trace 必须验收 11 个 source_batch_id、domain 分布、单日 source_version 和本地 TDX txt 每日刷新项。
quality_gate 必须验收 identity_key、membership 每日刷新、official daily proof、stock_daily_basic 与 stock universe、同码/88xxxx 防污染。
archive 必须验收 7 个 Parquet manifest 计划。
rollback 必须验收 11 个 rollback group 覆盖全部 source_batch_id，并先按 source_batch_id 删除再恢复 previous active source_version。
safety 必须验收不触碰条件/触发/动作/语音/模拟账户/前端/真实交易/旧系统。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

入库 dry-run 总控清单：

```text
N2 阶段可以生成一个总控清单，把初始回填计划、初始回填执行清单、初始回填验收清单、每日增量计划、每日增量执行清单和每日增量验收清单串起来。
总控清单只读取 dry-run TOML 配置和内存中的计划对象，不执行真实入库。
总控清单必须显示初始回填 211 个 source_batch_id、每日增量 11 个任务、两类验收清单、archive manifest 数量、rollback group 数量和全局 quality gate。
总控清单必须验收每日增量 trade_date 晚于初始回填 end_date。
总控清单必须验收 stock/index/board/common 物理分表贯穿初始回填和每日增量。
总控清单必须验收两个阶段均无副作用。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

条件层只读版本接口：

```text
SQL 文件：sql/003_condition_source_interface.sql
只读 view：common_condition_active_source_version_view
检查脚本：scripts/check_condition_source_ready.py
```

目的：

```text
把 common_active_source_version 的内部字段包装成条件层稳定入口。
条件层只看 source_trade_date、data_domain、data_type、active_source_version、source_batch_id、activated_at、activated_by。
条件层不需要知道 scope_key 的内部前缀，例如 TDX:、A_STOCK:、SSE:、INDEX:。
条件层不得直接解析 common_active_source_version.scope_key。
```

view 字段：

```text
source_trade_date
data_domain
data_type
active_source_version
source_batch_id
activated_at
activated_by
```

scope_key 日期抽取规则：

```text
scope_key = 20260522         -> source_trade_date = 20260522
scope_key = TDX:20260522     -> source_trade_date = 20260522
scope_key = A_STOCK:20260522 -> source_trade_date = 20260522
scope_key = SSE:20260522     -> source_trade_date = 20260522
scope_key = INDEX:20260522   -> source_trade_date = 20260522
```

条件层固定读取示例：

```sql
SELECT *
FROM common_condition_active_source_version_view
WHERE source_trade_date = '20260522';
```

条件层读取事实表示例：

```sql
SELECT *
FROM stock_daily_bar_fact
WHERE trade_date = '20260522'
  AND source_version = 'stock_daily_20260522_v1';
```

ready check：

```bash
PYTHONPATH=src ASHARE_V3_POSTGRES_DSN='postgresql://ashare_v3_user@127.0.0.1:5432/ashare_v3' \
scripts/check_condition_source_ready.py --source-trade-date 20260522
```

ready check 必须检查：

```text
stock_daily active 存在，且 stock_daily_bar_fact 行数 > 0，identity_key coverage = 100%
stock_daily_basic active 存在，且 stock_daily_basic 行数 > 0，identity_key coverage = 100%
stock_financial active 存在，且 stock_financial_metrics_fact 行数 > 0，row_count 与 stock universe 对齐，identity_key coverage = 100%
index_daily active 存在，且 index_daily_bar_fact 行数 > 0，identity_key coverage = 100%
index_membership active 存在，且 index_membership_fact 行数 > 0，identity_key coverage = 100%
board_daily active 存在，且 board_daily_bar_fact 行数 > 0，identity_key coverage = 100%
board_membership active 存在，且 board_membership_fact 行数 > 0，identity_key coverage = 100%
```

说明：

```text
该 view 和 ready check 属于入库层给条件层的只读接口。
它们不做条件层计算，不写 condition_basis / condition_pool，不启动 worker。
如果某个 active source version 存在但事实表行数为 0，ready check 必须失败并指出缺口。
stock_financial 必须额外检查 source_trade_date 等于检查日期，且 row_count 等于当日 stock_daily universe 行数。
```

真实执行前确认清单 dry-run：

```text
N3.0 阶段可以生成真实执行前确认清单。
确认清单只从入库 dry-run 总控报告派生，不执行真实读取或写入。
确认清单必须列出进入真实执行前需要用户逐项确认的事项。
确认项至少覆盖 scope、stage、secret、source、database、archive、quality_gate、rollback、safety。
secret 必须确认 TUSHARE_TOKEN 和 ASHARE_V3_POSTGRES_DSN 只来自环境变量或本机安全配置，不写入仓库文件。
source 必须确认 Tushare/Mootdx 网络读取权限，以及 `/Volumes/MacRaid/tdxdata/tdx` 本地 TDX txt 读取权限。
database 必须确认 PostgreSQL schema 已单独审阅/应用，且真实写入另行授权。
archive 必须确认 `/Volumes/MacRaid/database` 写入权限，以及 Parquet manifest 可回滚策略。
quality_gate 必须确认 P0 失败阻止 active source_version 激活。
rollback 必须确认按 source_batch_id 删除并恢复 previous active source_version 的方案。
safety 必须确认不触碰旧系统、不启动 worker、不启动长期服务、不进入条件/触发/动作/语音/模拟账户/前端/真实交易。
默认所有确认项为 pending_user_confirmation，因此 ready_to_execute=false。
即使通过 `--confirm-item` 模拟确认，也只改变 JSON 清单，不等于真实执行授权。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

真实执行配置样板：

```text
N3.1 阶段可以生成 configs/real_execution.example.toml。
配置样板只集中表达未来真实执行需要的阶段、路径、环境变量名、权限开关、quality gate 和 rollback 策略。
配置样板不保存真实 Tushare token。
配置样板不保存真实 PostgreSQL DSN。
默认 mode=preflight_only。
默认 approved_stage=none。
默认 allow_real_execution=false。
默认所有 permissions 开关为 false，包括 allow_network、allow_tdx_file_read、allow_database_write、allow_data_file_write、allow_worker_start、allow_old_system_access。
quality_gate 必须要求 P0 阻断、identity_key 覆盖、物理分表、official daily proof、stock_daily_basic 与 stock universe、active source_version 回滚。
rollback 必须要求按 source_batch_id 删除、恢复 previous active source_version、manifest rollback 和 failed audit retention。
preflight 必须列出 N3.0 的全部确认项。
验证配置样板时只读取 TOML 文件，不读取环境变量值。
即使配置样板验证通过，也不等于真实执行授权。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

PostgreSQL schema readiness dry-run：

```text
N3.2 阶段可以对 sql/001_raw_ingestion_schema.sql 做静态 readiness 检查。
检查只读取 SQL 文件文本，不连接 PostgreSQL，不执行 SQL，不执行 migration。
schema readiness 必须覆盖 11 个核心目标表，以及 common_ingest_batch、common_quality_gate_result、common_active_source_version。
必须验收 stock/index/board/common 物理分表，禁止出现混合 daily_bar_fact 表。
必须验收核心目标表具备 source_batch_id 和 source_version。
必须验收 identity 表和 fact 表保留对应 identity_key。
必须验收 common_ingest_batch 具备 rollback_strategy、status、error_summary、quality_gate_summary 等审计/回滚字段。
必须验收 common_quality_gate_result 具备 source_batch_id、source_version、gate_name、severity、status、details。
必须验收 common_active_source_version 具备 source_batch_id、source_version、previous_source_version、activated_at。
必须验收 SQL 中不包含 trigger/action/voice/sim_trade 等越界对象。
schema readiness 通过只代表 SQL 草案结构对齐，不代表已经连接数据库或执行 migration。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

Parquet 归档目录 readiness dry-run：

```text
N3.3 阶段可以对 Parquet 归档目录规划做静态 readiness 检查。
检查只根据既定 dataset、partition key、manifest 和 rollback 路径规则生成报告。
必须覆盖 7 个归档 dataset：
stock_daily_bar_fact
stock_daily_basic
index_daily_bar_fact
board_daily_bar_fact
stock_financial_metrics_fact
index_membership_fact
board_membership_fact
必须验收数据根目录为 /Volumes/MacRaid/database，归档目录为 data_lake。
必须验收日级事实和成分表按 trade_date 分区，stock_financial_metrics_fact 按 asof_date 分区。
必须验收 manifest 路径位于 /Volumes/MacRaid/database/data_lake/_manifests/DATASET/source_version=SOURCE_VERSION/SOURCE_BATCH_ID.manifest.json。
必须验收 parquet 文件路径位于 /Volumes/MacRaid/database/data_lake/DATASET/source_version=SOURCE_VERSION/PARTITION/part-00000.parquet。
必须验收每个 dataset 均有 manifest path 和 parquet file path 组成的回滚路径样例。
必须验收不包含 daily_bar_fact 混表或 runtime 归档对象。
readiness 通过只代表目录和 manifest 规划对齐，不代表已经创建目录或写入 Parquet 文件。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

真实执行 readiness 汇总 dry-run：

```text
N3.4 阶段可以生成真实执行 readiness 汇总报告。
汇总报告只组合已完成的 dry-run 结果，不执行真实入库。
必须汇总以下组件：
ingestion dry-run control
execution preflight checklist
real_execution.example.toml 配置样板
PostgreSQL schema readiness
Parquet archive readiness
汇总报告必须区分 passed 和 ready_to_execute：
passed=true 只表示静态 readiness 检查通过。
ready_to_execute=false 表示仍未获得真实执行授权。
默认必须列出 execution_blockers：
pending_user_confirmation
real_execution_config_disabled
即使模拟确认所有 preflight item，只要 real_execution.example.toml 仍为 preflight_only / allow_real_execution=false，也必须保持 ready_to_execute=false。
必须验收 schema readiness table_count=14。
必须验收 Parquet readiness dataset_count=7。
必须验收初始回填 batch_count=211，每日增量 task_count=11。
必须验收配置样板不保存真实 Tushare token 或 PostgreSQL DSN，且所有真实权限开关为 false。
必须验收汇总报告不授权真实执行。
readiness 汇总通过只代表可以进入下一次人工确认讨论，不代表可以连接数据库、拉外部数据或写入归档目录。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

真实执行申请包 dry-run：

```text
N3.5 阶段可以生成真实执行申请包。
申请包只整理人工确认材料，不执行真实入库，不改变 real_execution.example.toml。
申请包必须拆成两个阶段：
initial_backfill
daily_incremental
每个阶段必须列出：
日期范围或 trade_date
目标表清单
外部来源和本地 TDX txt 来源
需要的权限类型：network、tdx_file_read、database_write、data_file_write
需要的环境变量：TUSHARE_TOKEN、ASHARE_V3_POSTGRES_DSN
Parquet dataset、dataset_root、manifest_root、partition key 和 rollback path 样例
quality gate 类别
rollback group 和 rollback strategy
执行顺序
初始回填申请必须显示 batch_count=211。
每日增量申请必须显示 task_count=11。
两个阶段都必须显示 11 个目标表、11 个 source request、7 个 archive request、11 个 rollback group。
申请包必须显示所有 operator approval item 仍为 pending_user_confirmation。
申请包必须显示 ready_to_execute=false。
申请包必须显示 readiness 的 execution_blockers，至少包括 pending_user_confirmation 和 real_execution_config_disabled。
申请包通过只代表确认材料完整，不代表可以连接数据库、拉外部数据或写入归档目录。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

真实执行前环境探测方案 dry-run：

```text
N3.6 阶段可以生成真实执行前环境探测方案。
探测方案只列出未来需要探测的环境条件，不执行探测。
必须覆盖以下探测类别：
security
database
archive
tdx
source
runtime
safety
必须列出的探测项包括：
TUSHARE_TOKEN 环境变量名是否存在
ASHARE_V3_POSTGRES_DSN 环境变量名是否存在
PostgreSQL DSN 是否可建立短连接
PostgreSQL schema 是否已应用 14 张入库表
/Volumes/MacRaid/database 是否存在
/Volumes/MacRaid/database 是否可写
/Volumes/MacRaid/database/data_lake/_manifests 是否可写
/Volumes/MacRaid/tdxdata/tdx 是否可读
地区板块.txt / 指数板块.txt / 概念板块.txt / 行业板块.txt 是否可读
Tushare 是否可达
Mootdx 是否可达
Python 依赖是否可 import：pandas、pyarrow、psycopg、tushare、mootdx
旧系统边界是否仍被排除
worker 或长期服务是否仍未启动
探测方案必须显示所有 probe item 均为 pending_user_confirmation。
探测方案必须显示 ready_to_probe=false。
探测方案必须显示 actual_status=not_checked。
探测方案通过只代表探测清单完整，不代表可以读取环境变量、访问文件系统、连接数据库或调用外部接口。
不读取环境变量值。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不检查文件系统。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

环境探测结果报告格式 dry-run：

```text
N3.7 阶段可以生成环境探测结果报告模板。
结果模板只定义未来真实探测后的报告结构，不执行探测。
每个 probe result 必须包含：
item_id
category
target_kind
target
planned_probe
result_status
severity
blocking
probe_executed
error_summary
evidence
result_status 只允许：
passed
failed
skipped
N3.7 默认所有 probe result 均为 skipped。
N3.7 默认所有 probe_executed=false。
N3.7 默认 failed/skipped 必须有 error_summary。
N3.7 默认 skipped 结果必须 blocking=true，阻止进入真实执行复核。
报告必须汇总 result_status_counts 和 blocking_result_item_ids。
报告必须显示 ready_for_execution_review=false。
结果模板通过只代表未来报告格式完整，不代表已经探测通过，也不代表可以进入真实执行。
不读取环境变量值。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不检查文件系统。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

环境探测结果复核 dry-run：

```text
N3.8 阶段可以生成环境探测结果复核报告。
复核报告只消费 N3.7 的结果模板对象，不执行任何真实探测。
复核报告必须检查：
N3.7 结果模板自身 quality gate 是否通过
14 个 required probe item 是否完整
result_status 是否只包含 passed / failed / skipped
failed / skipped 是否有 error_summary
skipped / failed / unexecuted 是否产生 blocking finding
probe_plan_ready_to_probe=false 是否产生 blocking finding
默认 N3.7 skipped 结果必须使 ready_for_execution_review=false。
默认复核报告必须显示 14 个 skipped result 和 15 个 blocking finding：
1 个 probe_plan_not_ready
14 个 probe_status_skipped
复核报告通过只代表阻断项识别规则完整，不代表环境探测通过。
复核报告不得授权真实执行。
不读取环境变量值。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不检查文件系统。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

环境探测执行申请包 dry-run：

```text
N3.9 阶段可以生成环境探测执行申请包。
申请包只整理未来真实环境探测所需的人工确认材料，不执行探测。
申请包必须继承 N3.8 的 blocking findings。
申请包必须覆盖 14 个 required probe item。
每个 probe request 必须包含：
item_id
category
target_kind
target
planned_probe
required_permission
redaction_policy
evidence_policy
expected_result_status_values
approval_status
will_run
默认所有 probe request 均为 pending_user_confirmation。
默认所有 probe request 均为 will_run=false。
申请包必须覆盖以下人工确认项：
probe.security_env_metadata
probe.database_readonly
probe.archive_filesystem_metadata
probe.tdx_local_file_metadata
probe.source_connectivity
probe.runtime_import_checks
probe.safety_boundary
probe.no_writes_or_workers
申请包必须显示 ready_to_probe=false。
申请包通过只代表未来探测的申请材料完整，不代表已经授权读取环境、检查文件、连接数据库或调用外部接口。
申请包不得授权真实入库。
不读取环境变量值。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不检查文件系统。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

环境探测执行顺序 runbook dry-run：

```text
N3.10 阶段可以生成环境探测执行顺序 runbook。
runbook 只把 N3.9 申请包转成未来探测时的有序步骤，不执行任何步骤。
runbook 必须继承 N3.9 的 pending approval item 和 N3.8 的 blocking findings。
runbook 必须覆盖 14 个 required probe item。
runbook 步骤顺序必须固定为：
security
database
archive
tdx
source
runtime
safety
每个 runbook step 必须包含：
step_id
step_order
item_id
category
target_kind
target
planned_probe
required_permission
approval_dependency
redaction_policy
evidence_policy
abort_on_failure
cleanup_policy
approval_status
will_run
默认所有 runbook step 均为 pending_user_confirmation。
默认所有 runbook step 均为 will_run=false。
默认 runbook 必须显示 ready_to_run=false。
runbook 通过只代表未来探测步骤编排完整，不代表已经授权探测。
runbook 不是可执行脚本，不得读取环境、检查文件、连接数据库、调用外部接口或写入数据目录。
不读取环境变量值。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不检查文件系统。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

环境探测结果落盘格式 dry-run：

```text
N3.11 阶段可以生成环境探测结果 artifact 计划。
artifact 计划只定义未来真实环境探测结果如何脱敏、审计保存和回滚删除，不写任何文件。
artifact 计划必须继承 N3.10 的 14 个 runbook step 和 N3.8 的 15 个 blocking findings。
未来 probe_run_id 格式建议：
env_probe_YYYYMMDDThhmmssZ_vN
未来 artifact 根路径建议：
/Volumes/MacRaid/database/audit/environment_probe/probe_run_id=env_probe_YYYYMMDDThhmmssZ_vN/
必须规划以下 artifact 文件：
results.json
manifest.json
quality_gates.json
rollback_manifest.json
results.json 必须包含：
probe_run_id
runbook_id
started_at
finished_at
result_status_counts
blocking_result_item_ids
probe_results
quality_gates
side_effect_summary
每个 probe result 必须包含：
item_id
category
target_kind
target
planned_probe
result_status
severity
blocking
probe_executed
error_summary
evidence
以下字段和值禁止落盘：
tushare_token_value
postgres_dsn_value
ashare_v3_postgres_dsn_value
tdx_file_content
tdx_directory_listing
external_api_payload
market_data_payload
postgres_result_rows
secret_environment_values
所有 artifact 必须声明 redaction_required=true。
所有 artifact 必须声明按 probe_run_id 删除的 rollback/deletion strategy。
默认 artifact 计划必须显示 ready_to_write=false。
artifact 计划通过只代表未来审计文件格式完整，不代表已经授权创建目录或写入文件。
不读取环境变量值。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不检查文件系统。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

环境探测授权边界汇总 dry-run：

```text
N3.12 阶段可以生成环境探测授权边界汇总报告。
汇总报告只收口 N3.6-N3.11 的 dry-run 状态，不执行真实环境探测。
汇总报告必须显示：
14 个 required probe item
14 个 runbook step
8 个 pending operator approval item
15 个 inherited blocking finding
4 个 artifact kind
artifact 计划 passed=true 但 ready_to_write=false
汇总报告必须明确 ready_for_real_probe=false。
汇总报告必须列出下一阶段如进入真实只读环境探测会变敏感的动作：
read_environment_variable_metadata
check_data_root_filesystem_metadata
check_tdx_root_and_txt_file_metadata
open_short_postgresql_readonly_connection
call_tushare_connectivity_probe
call_mootdx_connectivity_probe
import_runtime_dependencies
N3.12 默认所有 sensitive action 均为 allowed_in_n3_12=false。
汇总报告必须列出 authorization blockers：
pending_probe_operator_approvals
inherited_probe_plan_not_ready
artifact_plan_not_ready_to_write
real_probe_not_authorized
N3.12 通过只代表 dry-run 授权边界完整，不代表授权真实探测。
不读取环境变量值。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不检查文件系统。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

真实只读环境探测授权申请 dry-run：

```text
N3.13 阶段可以生成真实只读环境探测授权申请。
授权申请只整理未来真实只读探测需要用户明确授权的动作，不执行探测。
授权申请必须继承 N3.12 的 pending approval item、blocking finding 和 authorization blockers。
授权申请必须覆盖以下 7 个 sensitive action：
read_environment_variable_metadata
check_data_root_filesystem_metadata
check_tdx_root_and_txt_file_metadata
open_short_postgresql_readonly_connection
call_tushare_connectivity_probe
call_mootdx_connectivity_probe
import_runtime_dependencies
每个 action request 必须包含：
action_id
category
description
required_approval_item
requested_scope
allowed_outputs
forbidden_outputs
redaction_policy
approval_status
will_execute
默认所有 action request 均为 pending_user_confirmation。
默认所有 action request 均为 will_execute=false。
必须要求用户未来精确授权语句：
允许执行真实只读环境探测
N3.13 默认 authorization_phrase_present=false。
N3.13 默认 ready_for_real_probe=false。
授权申请必须明确允许输出只限：
action_id
result_status
error_summary
redacted_evidence
授权申请必须明确禁止输出：
tushare_token_value
postgres_dsn_value
tdx_file_content
external_api_payload
market_data_payload
postgres_result_rows
directory_listing
N3.13 通过只代表授权申请材料完整，不代表已经授权或执行真实只读探测。
用户说“继续”只能继续生成授权申请 dry-run，不能解释为授权真实只读探测。
不读取环境变量值。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不检查文件系统。
不连接 PostgreSQL。
不执行 SQL。
不创建目录。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

## 5. 命名规范

### 5.1 identity_key

必须使用带命名空间的 identity_key：

```text
stock:SH:600000
stock:SZ:000001
index:SH:000001
index:SH:000688
index:SH:000905
board:TDX:881319
```

### 5.2 source_batch_id

每次入库必须生成批次号：

```text
stock_daily_20260522_v1
stock_daily_basic_20260522_v1
index_daily_20260522_v1
board_daily_20260522_v1
stock_financial_20260522_v1
index_membership_20260522_v1
board_membership_20260522_v1
```

### 5.3 source_version

每个交易日必须显式激活 source version：

```text
active_stock_daily_source_version
active_stock_daily_basic_source_version
active_index_daily_source_version
active_board_daily_source_version
active_stock_financial_source_version
active_index_membership_source_version
active_board_membership_source_version
```

后续条件层只能读取 active source version。

## 6. PostgreSQL 表设计

### 6.1 common_ingest_batch

记录每次入库批次。

```sql
CREATE TABLE common_ingest_batch (
  batch_id TEXT PRIMARY KEY,
  trade_date TEXT NOT NULL,
  data_domain TEXT NOT NULL,
  data_type TEXT NOT NULL,
  source TEXT NOT NULL,
  source_path TEXT,
  source_params JSONB,
  raw_hash TEXT,
  status TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.2 common_trade_calendar

```sql
CREATE TABLE common_trade_calendar (
  trade_date TEXT PRIMARY KEY,
  is_open BOOLEAN NOT NULL,
  prev_trade_date TEXT,
  next_trade_date TEXT,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.3 stock_identity

```sql
CREATE TABLE stock_identity (
  stock_identity_key TEXT PRIMARY KEY,
  ts_code TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL,
  name TEXT NOT NULL,
  display_code TEXT,
  listed_date TEXT,
  delisted_date TEXT,
  is_st BOOLEAN NOT NULL DEFAULT false,
  status TEXT NOT NULL DEFAULT active,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(exchange, code)
);
```

### 6.4 index_identity

```sql
CREATE TABLE index_identity (
  index_identity_key TEXT PRIMARY KEY,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL,
  name TEXT NOT NULL,
  index_category TEXT,
  status TEXT NOT NULL DEFAULT active,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(exchange, code)
);
```

### 6.5 board_identity

```sql
CREATE TABLE board_identity (
  board_identity_key TEXT PRIMARY KEY,
  board_code TEXT NOT NULL,
  board_name TEXT NOT NULL,
  board_type TEXT NOT NULL DEFAULT tdx_industry,
  source_namespace TEXT NOT NULL DEFAULT TDX,
  status TEXT NOT NULL DEFAULT active,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(source_namespace, board_code)
);
```

## 7. 日K事实表

### 7.1 stock_daily_bar_fact

个股日K只进入此表。

```sql
CREATE TABLE stock_daily_bar_fact (
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  trade_date TEXT NOT NULL,
  ts_code TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL,
  name TEXT,
  open NUMERIC NOT NULL,
  high NUMERIC NOT NULL,
  low NUMERIC NOT NULL,
  close NUMERIC NOT NULL,
  volume NUMERIC,
  amount NUMERIC,
  adj_factor NUMERIC,
  adjust_type TEXT NOT NULL DEFAULT qfq,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  official_daily_proof BOOLEAN NOT NULL DEFAULT false,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(stock_identity_key, trade_date, source_version)
);

CREATE INDEX idx_stock_daily_trade_date
ON stock_daily_bar_fact(trade_date);

CREATE INDEX idx_stock_daily_code_date
ON stock_daily_bar_fact(code, trade_date DESC);
```

### 7.2 stock_daily_basic

个股每日指标只进入此表。

```sql
CREATE TABLE stock_daily_basic (
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  trade_date TEXT NOT NULL,
  ts_code TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL,
  close NUMERIC,
  turnover_rate NUMERIC,
  turnover_rate_f NUMERIC,
  volume_ratio NUMERIC,
  pe NUMERIC,
  pe_ttm NUMERIC,
  pb NUMERIC,
  ps NUMERIC,
  ps_ttm NUMERIC,
  dv_ratio NUMERIC,
  dv_ttm NUMERIC,
  total_share NUMERIC,
  float_share NUMERIC,
  free_share NUMERIC,
  total_mv NUMERIC,
  circ_mv NUMERIC,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(stock_identity_key, trade_date, source_version)
);

CREATE INDEX idx_stock_daily_basic_trade_date
ON stock_daily_basic(trade_date);

CREATE INDEX idx_stock_daily_basic_code_date
ON stock_daily_basic(code, trade_date DESC);
```

### 7.3 index_daily_bar_fact

指数日K只进入此表。

```sql
CREATE TABLE index_daily_bar_fact (
  index_identity_key TEXT NOT NULL REFERENCES index_identity(index_identity_key),
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL,
  name TEXT,
  open NUMERIC NOT NULL,
  high NUMERIC NOT NULL,
  low NUMERIC NOT NULL,
  close NUMERIC NOT NULL,
  volume NUMERIC,
  amount NUMERIC,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(index_identity_key, trade_date, source_version)
);

CREATE INDEX idx_index_daily_trade_date
ON index_daily_bar_fact(trade_date);
```

### 7.4 board_daily_bar_fact

通达信行业/板块日K只进入此表。

```sql
CREATE TABLE board_daily_bar_fact (
  board_identity_key TEXT NOT NULL REFERENCES board_identity(board_identity_key),
  trade_date TEXT NOT NULL,
  board_code TEXT NOT NULL,
  board_name TEXT,
  board_type TEXT NOT NULL DEFAULT tdx_industry,
  open NUMERIC NOT NULL,
  high NUMERIC NOT NULL,
  low NUMERIC NOT NULL,
  close NUMERIC NOT NULL,
  volume NUMERIC,
  amount NUMERIC,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(board_identity_key, trade_date, source_version)
);

CREATE INDEX idx_board_daily_trade_date
ON board_daily_bar_fact(trade_date);
```

## 8. 财务与成分

### 8.1 stock_financial_metrics_fact

财务只属于个股。`stock_financial_metrics_fact` 保存 source_trade_date 的一股一行 as-of 财务快照；日频估值、市值、换手、股本等 `daily_basic` 指标仍进入 `stock_daily_basic`，只可作为 PE/市值辅助字段补入财务快照。

```sql
CREATE TABLE stock_financial_metrics_fact (
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  asof_date TEXT NOT NULL,
  source_trade_date TEXT NOT NULL,
  announcement_date TEXT,
  report_period TEXT,
  ts_code TEXT NOT NULL,
  code TEXT NOT NULL,
  exchange TEXT NOT NULL,
  roe NUMERIC,
  revenue_yoy NUMERIC,
  profit_yoy NUMERIC,
  total_revenue NUMERIC,
  net_profit NUMERIC,
  net_assets NUMERIC,
  eps NUMERIC,
  bps NUMERIC,
  pe_core NUMERIC,
  total_mv NUMERIC,
  circ_mv NUMERIC,
  score NUMERIC,
  warning TEXT,
  quality_status TEXT NOT NULL DEFAULT 'passed',
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(stock_identity_key, asof_date, source_version)
);
```

as-of 快照规则：

```text
source_trade_date = 条件层读取的来源交易日。
asof_date 在 as-of 快照版本中等于 source_trade_date。
announcement_date 表示选中的财报披露日，必须 <= source_trade_date。
report_period 表示选中的财报报告期。
找不到可用财报时仍写一行 placeholder：report_period=null，pe_core=null，score=0，warning=未找到可用财报，quality_status=warning。
```

### 8.2 board_membership_fact

```sql
CREATE TABLE board_membership_fact (
  trade_date TEXT NOT NULL,
  board_identity_key TEXT NOT NULL REFERENCES board_identity(board_identity_key),
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  board_code TEXT NOT NULL,
  stock_code TEXT NOT NULL,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(trade_date, board_identity_key, stock_identity_key, source_version)
);
```

### 8.3 index_membership_fact

指数成分股只进入此表，不得混入 `board_membership_fact`。

```sql
CREATE TABLE index_membership_fact (
  trade_date TEXT NOT NULL,
  index_identity_key TEXT NOT NULL REFERENCES index_identity(index_identity_key),
  stock_identity_key TEXT NOT NULL REFERENCES stock_identity(stock_identity_key),
  index_code TEXT NOT NULL,
  stock_code TEXT NOT NULL,
  source TEXT NOT NULL,
  source_batch_id TEXT NOT NULL REFERENCES common_ingest_batch(batch_id),
  source_version TEXT NOT NULL,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(trade_date, index_identity_key, stock_identity_key, source_version)
);
```

## 9. 盘中运行态数据（由 N3 接管）

本节仅保留早期入库层设计中的物理分表原则。正式边界以 `docs/V3_N3_MARKET_DATA_LAYER_DEVELOPMENT_DESIGN.md` 为准：

```text
N1/N2 不创建、不写入、不维护盘中 runtime snapshot / minute 表。
N3 实时行情层统一负责 realtime_daily_snapshot / minute_bar_1m / previous_day_minute_bar_1m。
N3 runtime 必须落本地 SSD PostgreSQL，不写 /Volumes/MacRaid/database。
N3 runtime 不和 N1/N2 外接盘历史事实、归档、Parquet 混放。
```

### 9.1 实时快照分表

```text
stock_realtime_daily_snapshot
index_realtime_daily_snapshot
board_realtime_daily_snapshot
```

三张表结构相同，但物理隔离。

示例：

```sql
CREATE TABLE stock_realtime_daily_snapshot (
  stock_identity_key TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  snapshot_time TIMESTAMPTZ NOT NULL,
  code TEXT NOT NULL,
  price NUMERIC,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  amount NUMERIC,
  volume NUMERIC,
  change_pct NUMERIC,
  source TEXT NOT NULL,
  source_batch_id TEXT,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(stock_identity_key, snapshot_time)
);
```

### 9.2 一分钟K分表

```text
stock_minute_bar_1m
index_minute_bar_1m
board_minute_bar_1m
```

只拉 condition scope 经 N3 market_data_subscription 去重后的对象，不拉全市场，不按 minute_target_scope 明细行重复拉取。

示例：

```sql
CREATE TABLE stock_minute_bar_1m (
  stock_identity_key TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  bar_time TIMESTAMPTZ NOT NULL,
  code TEXT NOT NULL,
  open NUMERIC,
  high NUMERIC,
  low NUMERIC,
  close NUMERIC,
  volume NUMERIC,
  amount NUMERIC,
  source TEXT NOT NULL,
  source_batch_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(stock_identity_key, bar_time)
);
```

## 10. 条件层只读视图

入库层物理分表，但可以给后续条件层提供只读统一视图。

```sql
CREATE VIEW condition_daily_bar_view AS
SELECT
  stock_identity_key AS identity_key,
  stock AS asset_kind,
  trade_date,
  code,
  exchange,
  open,
  high,
  low,
  close,
  amount,
  volume,
  source_version
FROM stock_daily_bar_fact

UNION ALL

SELECT
  index_identity_key AS identity_key,
  index AS asset_kind,
  trade_date,
  code,
  exchange,
  open,
  high,
  low,
  close,
  amount,
  volume,
  source_version
FROM index_daily_bar_fact

UNION ALL

SELECT
  board_identity_key AS identity_key,
  board AS asset_kind,
  trade_date,
  board_code AS code,
  TDX AS exchange,
  open,
  high,
  low,
  close,
  amount,
  volume,
  source_version
FROM board_daily_bar_fact;
```

注意：

```text
condition_daily_bar_view 只读。
任何业务层不得回写该 view。
```

## 11. 入库流程

### 11.1 收盘后每日增量入库

```text
1. ingest_trade_calendar
2. ingest_stock_identity
3. ingest_index_identity
4. ingest_board_identity
5. ingest_index_membership
6. ingest_board_membership
7. ingest_stock_daily
8. ingest_stock_daily_basic
9. ingest_index_daily
10. ingest_board_daily
11. ingest_stock_financial
```

说明：

```text
每个 ingest 步骤内部都必须完成 source_batch_id 审计、quality gate、PostgreSQL 写入、Parquet manifest 和 active source version。
stock_financial 可以作为慢速阶段后置运行；核心日增先完成，不被财务接口耗时阻塞。
每日增量不启动 worker，不进入条件/触发/动作/语音/模拟账户/前端/真实交易。
```

### 11.2 盘前校验

```text
1. 检查 active source version
2. 检查上一交易日 stock/index/board 日K完整
3. 检查 stock_daily_basic 与 stock universe 对齐
4. 检查财务和 stock universe 对齐
5. 检查指数成分完整
6. 检查板块成分完整
7. 检查 same-code conflict 无污染
8. 通过后才允许条件层计算
```

### 11.3 盘中分钟K入库

```text
本小节已由 N3 实时行情层接管，N1/N2 不执行盘中分钟K入库。
1. 条件层只产出 minute_target_scope。
2. N3 根据 market_data_subscription 去重后拉分钟K。
3. stock 写 stock_minute_bar_1m。
4. index 写 index_minute_bar_1m。
5. board 写 board_minute_bar_1m。
6. N3 runtime 必须写本地 SSD PostgreSQL。
7. 触发层/动作层按 N3-N6 事件合同消费标准事件，不直接绕过 N3 拉行情。
```

## 12. 质量闸门

### 12.1 stock gate

```text
stock_identity active 数 > 0
stock_daily_bar_fact 当日缺失 = 0
stock_daily_basic 当日缺失 = 0
stock_daily_basic 与 stock universe 对齐
official_daily_proof = true
qfq/adj_factor proof 通过
非 ST
总市值 >= 90 亿
stock_financial_metrics_fact 与 stock universe 数量一致
```

### 12.2 index gate

```text
index_daily_bar_fact 当日缺失 = 0
index_membership_fact 当日可用
指数代码不得进入 stock_daily_bar_fact
000001.SH 不得污染 000001.SZ
000688.SH 不得污染股票
000905.SH 不得污染股票
```

### 12.3 board gate

```text
board_daily_bar_fact 当日缺失 = 0
board_membership_fact 当日可用
88xxxx 不得进入 stock_daily_bar_fact
88xxxx 不得进入 stock_trade
```

### 12.4 cross gate

```text
裸 code join = 0
identity_key coverage = 100%
same_code_conflict 只报告，不作为 join key
condition_daily_bar_view 无重复 identity_key/trade_date/source_version
active source version 唯一
```

## 13. Parquet 归档

v3 入库层数据文件根目录：

```text
/Volumes/MacRaid/database
```

说明：

```text
PostgreSQL 仍作为运行事实库，事实表由 PostgreSQL 管理。
N1/N2 Parquet 归档、manifest、入库审计导出和可删除的数据文件默认写入该目录。
N3 盘中 runtime PostgreSQL、行情事实、event ledger / outbox / inbox、quality、checkpoint 不写入该目录。
N3 不直接写 Parquet 或 manifest；N3 只负责 sealed_run / archive_request 元数据。
N1/archive 负责读取已封账 N3 runtime 分区，写 Parquet、manifest、归档审计和 rollback 元数据。
N1 阶段只生成 SQL schema 文件，不连接数据库，不创建真实数据库，不写入该数据目录。
```

目录：

```text
/Volumes/MacRaid/database/data_lake/
  stock_daily_bar_fact/source_version=SOURCE_VERSION/trade_date=YYYYMMDD/part-*.parquet
  stock_daily_basic/source_version=SOURCE_VERSION/trade_date=YYYYMMDD/part-*.parquet
  index_daily_bar_fact/source_version=SOURCE_VERSION/trade_date=YYYYMMDD/part-*.parquet
  board_daily_bar_fact/source_version=SOURCE_VERSION/trade_date=YYYYMMDD/part-*.parquet
  stock_financial_metrics_fact/source_version=SOURCE_VERSION/asof_date=YYYYMMDD/part-*.parquet
  index_membership_fact/source_version=SOURCE_VERSION/trade_date=YYYYMMDD/part-*.parquet
  board_membership_fact/source_version=SOURCE_VERSION/trade_date=YYYYMMDD/part-*.parquet
  _manifests/DATASET/source_version=SOURCE_VERSION/SOURCE_BATCH_ID.manifest.json
  minute_bars_historical_archive_or_replay_export/trade_date=YYYYMMDD/asset_kind=stock/part-*.parquet
```

Parquet manifest 至少记录：

```text
manifest_version
dataset
source_batch_id
source_version
schema_version
row_count
raw_hash
partition_keys
file_paths
rollback.paths
```

N3 runtime 归档交接：

```text
N1/archive 是 N1_ingestion 内的归档职责名称，不是新的 layer_role。
1. N3 在本地 PostgreSQL 完成 trade_date/run_id 质量检查。
2. N3 将对应分区标记为 sealed，并生成 archive_request。
3. N1/archive 只读 sealed runtime 分区，写入 Parquet 和 manifest。
4. N1/archive 完成归档校验和 rollback 元数据。
5. N3 在 manifest 校验通过后，按本地保留策略清理旧 runtime 分区。
```

禁止：

```text
N3 盘中行情 worker 直接写 /Volumes/MacRaid/database。
N3 直接生成 Parquet 或 manifest。
N1/archive 在未 sealed 的 N3 runtime 分区上归档。
归档流程阻塞 N3 当前交易日 runtime 写入、事件投递或用户投影。
```

N2 dry-run 只生成 manifest 计划，不实际写 `/Volumes/MacRaid/database`。

PostgreSQL 写入计划 dry-run：

```text
N2 阶段只生成 insert/upsert SQL 模板和 delete-by-source-batch 回滚 SQL 模板。
不连接 PostgreSQL。
不执行 SQL。
不创建 schema。
不修改 common_active_source_version。
每张写入表必须通过 source_batch_id/source_version/物理分表/列白名单检查。
```

Active source version 激活计划 dry-run：

```text
N2 阶段只生成 common_active_source_version 的 upsert SQL 模板和 rollback SQL 模板。
不连接 PostgreSQL。
不执行 SQL。
只有所有输入 quality gate 均为 passed 时，才允许生成 activation_allowed=true。
如果存在 previous_source_version，回滚计划必须同时具备 previous_source_batch_id。
```

整批入库编排 dry-run：

```text
N2 阶段可以生成单日整批入库编排计划。
编排计划只串联已存在的 source batch、PostgreSQL 写入计划、quality gate 写入计划、Parquet manifest 计划和 active source version 计划。
不调用 Tushare。
不调用 Mootdx。
不读取本地 TDX txt。
不连接 PostgreSQL。
不执行 SQL。
不写 `/Volumes/MacRaid/database`。
不启动 worker 或长期服务。
```

编排顺序必须保持：

```text
1. common_trade_calendar
2. stock_identity
3. index_identity
4. board_identity
5. index_membership_fact
6. board_membership_fact
7. stock_daily_bar_fact
8. stock_daily_basic
9. index_daily_bar_fact
10. board_daily_bar_fact
11. stock_financial_metrics_fact
```

DuckDB 只读这些归档做：

```text
回放
报表
A股三表对比
回测
质量审计
```

## 14. 幂等与回滚

### 14.1 幂等

```text
同一 source_batch_id 不重复执行
同一 source_version 可 overwrite 但必须显式 --overwrite
写入前记录 row_count/hash
写入后记录 row_count/hash
```

### 14.2 回滚

```text
按 source_batch_id 删除事实表写入
恢复 previous active source version
Parquet 不物理删除，通过 manifest 控制 active
```

## 15. 开发阶段拆分

### N0：项目骨架

```text
pyproject
src/ashare_v3
scripts
sql
configs
tests
docs
```

### N1：PostgreSQL schema

```text
common_ingest_batch
common_trade_calendar
stock_identity
index_identity
board_identity
stock_daily_bar_fact
stock_daily_basic
index_daily_bar_fact
board_daily_bar_fact
stock_financial_metrics_fact
index_membership_fact
board_membership_fact
```

### N2：个股日K与每日指标入库

```text
stock identity
stock qfq daily
stock daily basic
stock quality gate
stock parquet archive
```

### N3：指数/板块日K入库

```text
index daily
board daily
same-code guard
board code guard
```

### N4：财务与指数/板块成分

```text
stock financial
index membership
board membership
stock universe 对齐
```

### N5：active source version

```text
source version 管理
质量通过后 activate
失败则 block
```

### N6：condition 只读 view

```text
condition_daily_bar_view
minute_target_scope 输入契约
```

## 16. 验收标准

入库层完成时必须满足：

```text
1. stock/index/board 物理分表
2. identity_key 覆盖率 100%
3. 同码污染 0
4. 88xxxx stock violation 0
5. 个股财务与个股池数量一致
6. 个股每日指标与个股池数量一致
7. 指数成分股与 index/stock identity 对齐
8. official daily proof 完整
9. qfq proof 完整
10. source_batch_id 可追溯
11. source_version 可激活/回滚
12. Parquet 归档可被 DuckDB 读取
13. condition view 只读可用
14. 入库层不写 trigger/action/voice/sim
```

## 17. 一句话原则

```text
入库时物理隔离，事实层严格证明，条件层只读消费。
```

这是 v3 的第一块地基。只有这层稳定，后面的条件、触发、动作、用户层才有重构价值。
