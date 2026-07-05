# v3 现有 raw 表到原始数据入库层映射盘点

版本：V0.1
日期：2026-05-22
范围：只盘点目标机现有条件层相关 raw/cache 表与脚本名称，整理到 v3 原始数据入库层的映射边界。
不包含：条件计算、触发、动作、语音、模拟账户、前端、真实交易、旧系统读取、旧系统迁移。

## 1. 边界声明

本文件只基于用户提供的现有表名和脚本名做入库层映射，不读取目标机旧系统，不连接旧数据库，不修改旧系统。

本文件不设计新表。v3 目标对象只引用 `V3_RAW_DATA_INGESTION_DESIGN.md` 已定义的入库层对象：

```text
common_*
stock_*
index_*
board_*
Parquet data_lake
DuckDB 离线读取归档
```

硬约束：

```text
stock / index / board 入库时必须物理分开。
不能先混表再靠 asset_kind 过滤。
identity_key 必须保留，但不能替代物理隔离。
禁止裸 code join。
latest/state/snapshot/cache 不能覆盖 official daily。
条件层、触发层、动作层、语音、模拟账户、前端、真实交易全部排除。
```

## 2. 映射判定标准

现有表按三类处理：

```text
A. 可进入 v3 入库层：外部原始事实或基础身份数据，可标准化为 v3 fact / identity。
B. 只作对账证据：由旧条件层或缓存层生成，不作为 v3 事实源，只可用于迁移前后的差异核对。
C. 禁止进入入库层：条件结果、信号结果、动作/模拟账户/持仓状态，属于 v3 入库层边界外。
```

所有 A 类入库必须补齐：

```text
source_batch_id
source_version
identity_key coverage
quality gate
可按 source_batch_id 回滚
Parquet 归档或 manifest 策略
```

## 3. 现有表映射盘点

| 现有表 | 判断 | v3 入库层映射 | 处理说明 |
|---|---|---|---|
| `stock_info` | A. 可进入 | `stock_identity` | 个股身份来源。生成 `stock:EXCHANGE:CODE` 形式的 `stock_identity_key`。保留 `ts_code`、`code`、`exchange`、`name`、上市/退市/ST/状态等可用字段。不得用裸 `code` 作为跨资产 join key。 |
| `daily_kline` | A. 可进入，但必须先分流 | `stock_daily_bar_fact` / `index_daily_bar_fact` / `board_daily_bar_fact` | 若现有表混有个股、指数、板块，v3 入库前必须按 identity namespace 分流。个股只进 `stock_daily_bar_fact`，指数只进 `index_daily_bar_fact`，板块只进 `board_daily_bar_fact`。不能落入单张混合 fact。 |
| `period_agg_identity_cache` | B. 只作对账证据 | 对账 `stock_identity` / `index_identity` / `board_identity` 覆盖率 | 名称显示为周期聚合身份缓存，属于缓存/派生结果。不得作为 v3 identity 主来源。可用于检查 identity coverage、same-code conflict、历史条件层对象覆盖差异。 |
| `filter_fact_cache` | C. 禁止进入入库层 | 无 | 条件筛选事实缓存，属于条件层派生结果。不得写入 v3 原始 fact，不得参与 source version 激活。 |
| `filter_fact_baseline` | C. 禁止进入入库层 | 无 | 条件筛选 baseline，属于条件层口径。可在总负责会话确认后用于离线差异说明，但不是 v3 入库事实源。 |
| `financial_metrics_cache` | A. 可进入 | `stock_financial_metrics_fact` | 个股财务指标来源候选。必须映射到 `stock_identity_key`，与 stock universe 做数量对齐；必须有 `source_batch_id`、`source_version`、raw payload 和质量闸门。 |
| `monitor_list` | B. 只作运行输入线索 | 后续 `minute_target_scope` 输入契约的参考，不进入 N0-N5 fact | 监控列表属于条件/运行对象范围，不是原始市场事实。可用于理解旧系统分钟K拉取范围，但本阶段不实现条件 scope，也不写入 v3 入库事实。 |
| `monitor_link` | C. 禁止进入入库层 | 无 | 监控对象关联关系更接近条件/前端/运行编排，不是原始事实。不得进入 v3 入库层。 |
| `candidate_list` | C. 禁止进入入库层 | 无 | 候选池是条件计算结果。v3 入库层只能提供事实，不生成或迁移 candidate。 |
| `sim_position` | C. 禁止进入入库层 | 无 | 模拟账户持仓，明确属于 v3 禁止范围。不得读取、迁移、引用或回写；如任务要求处理该表，应停止并交回总负责会话确认。 |
| `state_snapshot` | B. 仅可作快照来源线索 | 未来可分流到 N3 `stock_realtime_daily_snapshot` / `index_realtime_daily_snapshot` / `board_realtime_daily_snapshot`，不能覆盖 daily fact | 名称显示为状态快照，不是 official daily。若后续作为行情快照来源，必须先剥离状态/条件/动作字段，再按 stock/index/board 物理分表写 N3 runtime 快照事实。不得覆盖 `stock_daily_bar_fact` 等日K事实；正式表名不得使用 `*_runtime`。 |
| `latest_snapshot_cache` | B. 仅可作快照来源线索 | 未来可分流到 N3 `stock_realtime_daily_snapshot` / `index_realtime_daily_snapshot` / `board_realtime_daily_snapshot`，不能覆盖 official daily | 最新快照缓存不能作为 official daily，也不能补写日K事实。若用于盘中 runtime，必须有批次、来源、时间戳、identity 分流；正式表名不得使用 `*_runtime`。 |
| `minute_kline` | A. 有条件进入 | N3 `stock_minute_bar_1m` / `index_minute_bar_1m` / `board_minute_bar_1m`；历史归档由 N1/archive 写 Parquet | v3 不把全量历史分钟K写入 PostgreSQL 主运行库。仅 condition scope 内对象的一分钟K写 N3 本地 runtime 表。N3 盘后只封账并生成 archive_request；如需长期保留，由 N1/archive 只读 sealed runtime 分区写 Parquet 和 manifest，并由 DuckDB 离线读取。 |
| `amount_context_cache` | B. 只作对账证据 | 从 daily/minute fact 或 Parquet 重算 | 金额上下文缓存属于派生上下文。v3 入库层不把它当作标准事实源，应从日K/分钟K事实重算；可用于迁移对账。 |
| `daily_cum_series` | B. 只作对账证据 | 从 `stock_daily_bar_fact` / `index_daily_bar_fact` / `board_daily_bar_fact` 或 Parquet 重算 | 日累计序列是派生序列，不是原始日K事实。v3 不迁移为入库 fact。 |
| `identity_minute_amount_curve_cache` | B. 只作对账证据 | 从 minute runtime 或 minute Parquet 重算 | identity 级分钟成交额曲线缓存属于派生曲线。不得作为 v3 标准事实表来源；可用 DuckDB 基于分钟K归档重算后对账。 |

## 4. 入库映射摘要

可作为 v3 入库来源候选：

```text
stock_info -> stock_identity
daily_kline -> stock_daily_bar_fact / index_daily_bar_fact / board_daily_bar_fact
financial_metrics_cache -> stock_financial_metrics_fact
minute_kline -> N3 stock_minute_bar_1m / index_minute_bar_1m / board_minute_bar_1m，或由 N1/archive 归档到 Parquet minute archive
```

只作对账或覆盖率证据：

```text
period_agg_identity_cache
monitor_list
state_snapshot
latest_snapshot_cache
amount_context_cache
daily_cum_series
identity_minute_amount_curve_cache
```

禁止进入 v3 入库层：

```text
filter_fact_cache
filter_fact_baseline
monitor_link
candidate_list
sim_position
```

## 5. 现有脚本边界盘点

| 现有脚本 | v3 入库层判断 | 映射说明 |
|---|---|---|
| `run_afterhours.py` | 可作为流程线索，不直接复用 | 名称显示为收盘后总流程。v3 可借鉴其顺序，但必须拆成独立入库步骤：stock daily、index daily、board daily、financial、membership、quality gate、activate、archive。不得直接启动旧 worker 或旧服务。 |
| `run_filter_finalize_job.py` | 条件层，排除 | filter finalize 属于条件筛选定稿，不属于原始入库层。不得迁移到 v3 入库。 |
| `run_stock_finalize_official_daily_guard.py` | 可映射为 stock quality gate 线索 | 对应 v3 `stock_daily_bar_fact` 的 official daily proof、缺失检查、qfq proof、identity coverage。只迁移规则语义，不执行旧脚本。 |
| `run_tdx_finalize_official_daily_guard.py` | 可映射为 board/index quality gate 线索 | 对应 TDX 板块/行业日K或相关官方日K guard。v3 必须写入 `board_daily_bar_fact` 或 `index_daily_bar_fact`，不能污染 stock fact。 |
| `run_qfq_state_snapshot_guard.py` | 可映射为 qfq / snapshot 防污染线索 | qfq proof 属于 stock gate；state snapshot 只能作 runtime snapshot 线索，不能覆盖 official daily。 |
| `run_period_identity_cache_guard.py` | 可映射为 identity coverage / cross gate 线索 | 用于检查 identity cache 覆盖和同码风险的规则可迁移为 v3 quality gate 思路，但不迁移旧缓存为事实源。 |
| `run_financial_metrics_update.py` | 可映射为 N4 财务入库线索 | 对应 `stock_financial_metrics_fact` 入库。必须和 `stock_identity` / stock universe 对齐，有 batch、version、quality gate。 |
| `run_signal_precompute.py` | 条件/信号层，排除 | signal precompute 属于条件层或触发前计算，不属于原始入库。 |
| `run_layered_signal_pools.py` | 条件/信号池，排除 | layered signal pools 属于条件/候选池构建，不属于原始入库。 |

## 6. 质量闸门映射

从现有 raw/cache 进入 v3 入库层时，至少要守住以下检查：

```text
stock_info -> stock_identity_key coverage = 100%
daily_kline -> stock/index/board 入库前物理分流
daily_kline -> official daily proof 不得由 latest/state snapshot 代替
daily_kline -> 000001.SH / 000001.SZ 同码污染 = 0
daily_kline -> 000688.SH / 000905.SH 不得进入 stock fact
daily_kline -> 88xxxx 不得进入 stock fact
financial_metrics_cache -> 财务指标与 stock universe 对齐
minute_kline -> N3 本地 PostgreSQL runtime 只接 condition scope，不接全量历史分钟K；长期归档由 N1/archive 执行
snapshot/cache -> 只能进 runtime snapshot，不得覆盖 official daily
filter/candidate/signal/sim -> 不进入入库层
```

## 7. 回滚与审计要求

所有 A 类来源真正进入 v3 时，必须能够回答：

```text
这批数据来自哪个 source_batch_id？
它属于哪个 source_version？
质量闸门是否通过？
失败时如何按 source_batch_id 删除事实表写入？
Parquet 归档是否通过 manifest 控制 active，而不是直接物理删除？
是否有 raw_hash、row_count、error_count、started_at、finished_at？
```

## 8. 待确认事项

以下信息需要未来在不触碰旧系统或经总负责会话确认后再核实：

```text
daily_kline 是否混有 stock/index/board，还是只含个股。
state_snapshot / latest_snapshot_cache 是否含有条件、动作、模拟账户字段。
minute_kline 是全量历史分钟K，还是只含监控对象分钟K。
financial_metrics_cache 的 asof_date / report_period / stock universe 口径。
TDX 板块身份来源是否独立于 daily_kline。
现有脚本是否只读校验，还是会写旧系统状态。
```

在这些事项确认前，本文档只作为 v3 入库映射边界，不作为执行迁移方案。
